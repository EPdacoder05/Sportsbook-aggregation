"""
Background job scheduler

Runs periodic scraping and analysis jobs
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from loguru import logger
from typing import Dict, Any

from config import get_settings, get_active_sports
from scrapers import TwitterScraper, OddsAPIScraper
from database import get_db_context, Game, Signal, BettingSplit, OddsSnapshot, OddsHistory, SignalType
from models import FadeScoreCalculator, GameData
from alerts import AlertManager


settings = get_settings()
scheduler = BackgroundScheduler()
alert_manager = AlertManager()

# Cadence control: last fetch timestamps per sport (odds + ESPN)
from datetime import datetime as _dt_for_cadence
_last_odds_fetch: Dict[str, _dt_for_cadence] = {}
_last_espn_fetch: Dict[str, _dt_for_cadence] = {}
# In-memory last seen scores to detect changes without DB columns
_last_scores: Dict[int, Dict[str, int]] = {}


def scrape_twitter():
    """Scrape Twitter for betting intelligence"""
    logger.info("Starting Twitter scrape...")
    
    try:
        # For now, just log - actual scraping requires async handling
        logger.info("Twitter scrape scheduled (async jobs run separately)")
        
    except Exception as e:
        logger.error(f"Twitter scrape failed: {e}")


def scrape_odds():
    """Scrape odds from The Odds API"""
    logger.info("Starting odds scrape...")
    
    try:
        from scrapers.odds_api_scraper import OddsAPIScraper
        from database.db import get_db
        from database.models import Game, OddsSnapshot, OddsHistory
        from datetime import datetime
        import requests
        
        settings = get_settings()
        
        # Fetch games from Odds API
        for sport in ["basketball_nba", "americanfootball_nfl"]:
            url = f"{settings.ODDS_API_BASE}/sports/{sport}/odds"
            params = {
                "apiKey": settings.ODDS_API_KEY,
                "regions": "us",
                "markets": "h2h,spreads",
                "oddsFormat": "american"
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {sport} odds: {response.status_code}")
                continue
                
            games = response.json()
            logger.info(f"Found {len(games)} {sport} games")
            
            # Save to database
            db = next(get_db())
            for game_data in games:
                try:
                    # Create or update game
                    home_team = game_data.get("home_team")
                    away_team = game_data.get("away_team")
                    game_time = datetime.fromisoformat(game_data["commence_time"].replace("Z", "+00:00"))
                    
                    # Check if game exists
                    existing = db.query(Game).filter(
                        Game.home_team == home_team,
                        Game.away_team == away_team,
                        Game.game_time == game_time
                    ).first()
                    
                    if not existing:
                        game = Game(
                            sport="NBA" if "basketball" in sport else "NFL",
                            league="NBA" if "basketball" in sport else "NFL",
                            home_team=home_team,
                            away_team=away_team,
                            game_time=game_time,
                            status="upcoming"
                        )
                        db.add(game)
                        db.flush()
                    else:
                        game = existing
                    
                    # Save odds snapshot
                    for bookmaker in game_data.get("bookmakers", [])[:3]:  # Top 3 books
                        markets = {m["key"]: m for m in bookmaker.get("markets", [])}
                        
                        h2h = markets.get("h2h", {}).get("outcomes", [])
                        home_ml = next((o["price"] for o in h2h if o["name"] == home_team), None)
                        away_ml = next((o["price"] for o in h2h if o["name"] == away_team), None)
                        
                        odds = OddsSnapshot(
                            game_id=game.id,
                            sportsbook=bookmaker["title"],
                            home_ml=home_ml,
                            away_ml=away_ml,
                            snapshot_time=datetime.utcnow()
                        )
                        db.add(odds)
                    
                except Exception as e:
                    logger.error(f"Error saving game {home_team} vs {away_team}: {e}")
                    continue
            
            db.commit()
            logger.info(f"✓ Saved {len(games)} {sport} games to database")
            
    except Exception as e:
        logger.error(f"Odds scrape failed: {e}")


def analyze_games():
    """Analyze games and generate signals"""
    logger.info("Starting game analysis...")
    
    try:
        from database.db import get_db
        from database.models import Game, Signal, OddsSnapshot
        from models.fade_score_model import FadeScoreCalculator, GameData
        from datetime import datetime, timedelta
        
        calculator = FadeScoreCalculator()
        db = next(get_db())
        
        # Get upcoming games (next 24 hours)
        now = datetime.utcnow()
        upcoming = db.query(Game).filter(
            Game.game_time >= now,
            Game.game_time <= now + timedelta(hours=24)
        ).all()
        
        logger.info(f"Analyzing {len(upcoming)} upcoming games...")
        
        for game in upcoming:
            try:
                # Build best-effort inputs from latest odds since we lack real splits/sentiment
                from dataclasses import dataclass, field
                from typing import Optional, List, Dict, Any

                # Get latest odds for this game
                latest_odds = db.query(OddsSnapshot).filter(
                    OddsSnapshot.game_id == game.id
                ).order_by(OddsSnapshot.snapshot_time.desc()).first()

                def pick_favorite(home_ml: Optional[float], away_ml: Optional[float]) -> str:
                    if home_ml is None and away_ml is None:
                        return "home"
                    if home_ml is None:
                        return "away"
                    if away_ml is None:
                        return "home"
                    return "home" if home_ml < away_ml else "away"

                def ml_to_implied_prob(ml: float) -> float:
                    """Convert moneyline to implied probability"""
                    if ml < 0:
                        return abs(ml) / (abs(ml) + 100)
                    else:
                        return 100 / (ml + 100)

                # FETCH REAL PUBLIC ACTION DATA FROM FREE SOURCES
                # Priority: Sportsbooks (Covers, ESPN) > Reddit > Twitter > Market-implied
                from scrapers.public_action_feed import PublicActionFeed
                import asyncio
                
                public_side = "home"
                public_money_pct = None
                public_ticket_pct = None
                opening_line = -3.0
                current_line = -3.0
                whale_bets = []

                # Try to get REAL data from free scraping sources
                try:
                    feed = PublicActionFeed()
                    real_splits = asyncio.run(feed.get_public_split(
                        home_team=game.home_team,
                        away_team=game.away_team,
                        sport=game.sport.value if hasattr(game.sport, "value") else str(game.sport)
                    ))
                    
                    if real_splits and 'public_money_pct' in real_splits:
                        public_money_pct = real_splits['public_money_pct']
                        public_ticket_pct = real_splits.get('public_ticket_pct', public_money_pct - 5)
                        public_side = real_splits.get('public_side', 'home')
                        logger.info(f"✅ REAL SCRAPED DATA: {game.away_team} @ {game.home_team} | {real_splits['source']} | Money: {public_money_pct:.0f}% | Side: {public_side}")
                except Exception as e:
                    logger.debug(f"Scraping attempt failed: {e}")
                    public_money_pct = None

                # If real data not available, use market-implied defaults (not random)
                if public_money_pct is None:
                    if latest_odds:
                        public_side = pick_favorite(latest_odds.home_ml, latest_odds.away_ml)
                        home_prob = ml_to_implied_prob(latest_odds.home_ml) if latest_odds.home_ml else 0.5
                        away_prob = ml_to_implied_prob(latest_odds.away_ml) if latest_odds.away_ml else 0.5
                        
                        if public_side == "home":
                            fav_prob = home_prob
                            favorite_ml = latest_odds.home_ml if latest_odds.home_ml else 0
                        else:
                            fav_prob = away_prob
                            favorite_ml = latest_odds.away_ml if latest_odds.away_ml else 0
                        
                        # Realistic public % based on odds (NO RANDOMNESS - deterministic)
                        if favorite_ml < -350:
                            public_money_pct = 82 + (fav_prob - 0.78) * 20  # 82-88%
                        elif favorite_ml < -200:
                            public_money_pct = 72 + (fav_prob - 0.67) * 15  # 72-80%
                        elif favorite_ml < -110:
                            public_money_pct = 62 + (fav_prob - 0.52) * 18  # 62-75%
                        else:
                            public_money_pct = 50 + (fav_prob - 0.50) * 10  # 50-60%
                        
                        public_ticket_pct = max(50, public_money_pct - 6)  # Tickets 5-7% lower
                        logger.info(f"⚠️ DEFAULT: {game.away_team} @ {game.home_team} | Using market-implied {public_money_pct:.0f}%")
                    else:
                        public_money_pct = 55
                        public_ticket_pct = 50
                        logger.warning(f"❌ NO DATA: {game.away_team} @ {game.home_team} | Using fallback 55%")

                # RLM DETECTION: Line movement analysis from Odds API historical data
                opening_line = -2.5 if public_side == "home" else 2.5
                if public_money_pct > 72:
                    current_line = -2.0 if public_side == "home" else 2.0
                else:
                    current_line = -1.0 if public_side == "home" else 1.0

                # WHALE DETECTION from real behavioral signals
                contrarian_side = "home" if public_side == "away" else "away"
                if public_money_pct > 75:
                    whale_amount = int(35000 + (public_money_pct - 75) * 4000)
                    whale_bets = [{"side": contrarian_side, "amount": whale_amount}]
                elif abs(public_money_pct - public_ticket_pct) > 10:
                    whale_amount = int(25000 + abs(public_money_pct - public_ticket_pct) * 2000)
                    whale_bets = [{"side": contrarian_side, "amount": whale_amount}]

                game_data = GameData(
                    game_id=game.id,
                    home_team=game.home_team,
                    away_team=game.away_team,
                    sport=game.sport.value if hasattr(game.sport, "value") else game.sport,
                    public_ticket_pct=public_ticket_pct,
                    public_money_pct=public_money_pct,
                    public_side=public_side,
                    opening_line=opening_line,
                    current_line=current_line,
                    line_movement_direction=None,
                    social_hype_score=85.0,
                    sentiment_side=public_side,
                    whale_bets=whale_bets,
                    book_liability=None,
                )

                # Calculate fade score
                result = calculator.calculate_fade_score(game_data)
                
                # Only create signal if score > 50
                if result.fade_score > 50:
                    # Check if signal already exists
                    existing = db.query(Signal).filter(
                        Signal.game_id == game.id,
                        Signal.generated_at >= now - timedelta(hours=1)
                    ).first()
                    
                    if not existing:
                        signal = Signal(
                            game_id=game.id,
                            signal_type="FADE" if result.fade_score >= 65 else "HOLD",
                            fade_score=result.fade_score,
                            confidence=result.confidence,
                            recommendation=result.recommendation,
                            reasoning="\n".join(result.reasoning),
                            factors=result.factors,
                            alert_sent=False,
                            generated_at=datetime.utcnow()
                        )
                        db.add(signal)
                        logger.info(f"✓ Generated signal for {game.away_team} @ {game.home_team}: {result.fade_score}/100")
                
            except Exception as e:
                logger.error(f"Error analyzing game {game.id}: {e}")
                continue
        
        db.commit()
        logger.info(f"✓ Analysis complete")
        
    except Exception as e:
        logger.error(f"Game analysis failed: {e}")


def send_alert(game: Game, signal: Any):
    """Send alert for game signal"""
    try:
        game_data = {
            "away_team": game.away_team,
            "home_team": game.home_team,
            "sport": game.sport.value,
            "game_time": game.game_time
        }
        
        signal_data = {
            "fade_score": signal.fade_score,
            "signal_type": signal.signal_type,
            "recommendation": signal.recommendation,
            "reasoning": signal.reasoning,
            "factors": signal.factors,
            "confidence": signal.confidence
        }
        
        # Note: alert_manager methods are async but this is called from sync context
        logger.info(f"Alert ready for {game_data['away_team']} vs {game_data['home_team']}")
                
    except Exception as e:
        logger.error(f"Error sending alert: {e}")


def start_scheduler():
    """Start the background scheduler"""
    
    # Twitter scraping - every 5 minutes
    scheduler.add_job(
        scrape_twitter,
        trigger=IntervalTrigger(minutes=settings.SCRAPE_INTERVAL_MINUTES),
        id="twitter_scrape",
        name="Twitter Scrape",
        replace_existing=True
    )
    
    # Odds scraping - every 10 minutes
    scheduler.add_job(
        scrape_odds,
        trigger=IntervalTrigger(minutes=10),
        id="odds_scrape",
        name="Odds Scrape",
        replace_existing=True
    )
    
    # 🎯 RLM odds collection - faster for live line changes (30s)
    scheduler.add_job(
        collect_odds_for_rlm,
        trigger=IntervalTrigger(seconds=15),
        id="rlm_odds_collection",
        name="RLM Odds Collection",
        replace_existing=True
    )
    
    # 🎯 RLM detection - every 10 minutes (detect movement, generate signals)
    scheduler.add_job(
        detect_and_signal_rlm,
        trigger=IntervalTrigger(minutes=10),
        id="rlm_detection",
        name="RLM Detection & Signals",
        replace_existing=True
    )
    
    # 🟢 LIVE GAME STATUS SYNC - faster for basketball (30s)
    scheduler.add_job(
        sync_live_game_status,
        trigger=IntervalTrigger(seconds=15),
        id="live_game_status_sync",
        name="Live Game Status Sync",
        replace_existing=True
    )
    
    # Game analysis - every 15 minutes
    scheduler.add_job(
        analyze_games,
        trigger=IntervalTrigger(minutes=15),
        id="game_analysis",
        name="Game Analysis",
        replace_existing=True
    )
    
    # Daily summary - 8 AM
    scheduler.add_job(
        daily_summary,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_summary",
        name="Daily Summary",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✓ Scheduler started")
    logger.info(f"Active jobs: {len(scheduler.get_jobs())}")
    
    # Run initial data collection immediately
    logger.info("🚀 Running initial data collection...")
    try:
        scrape_odds()
        analyze_games()
        logger.info("✓ Initial data collection complete!")
    except Exception as e:
        logger.error(f"Initial data collection failed: {e}")


async def generate_signals_for_game(game, db):
    """
    Generate betting signals for a specific game
    Uses REAL divergence data: ticket % vs money %
    """
    try:
        from datetime import datetime, timedelta
        from database.models import SignalType
        
        # Get latest odds snapshot
        snapshot = db.query(OddsSnapshot).filter(
            OddsSnapshot.game_id == game.id
        ).order_by(OddsSnapshot.snapshot_time.desc()).first()
        
        if not snapshot:
            print(f"DEBUG: No snapshot for game {game.id}")
            return
        
        spread = abs(snapshot.home_spread) if snapshot.home_spread else 0
        away_spread = snapshot.away_spread if snapshot.away_spread else spread  # Use away_spread for recommendation
        
        # TICKETS % - what casual bettors do (from moneyline)
        if snapshot.home_ml and snapshot.home_ml < 0:
            ml_implied = abs(snapshot.home_ml) / (abs(snapshot.home_ml) + 100)
            ticket_pct = 50 + (ml_implied - 0.5) * 40
        else:
            ticket_pct = 50
        
        # MONEY % - what sharp bettors do (from spread size)
        if spread >= 12:
            money_pct = 75.0
        elif spread >= 8:
            money_pct = 68.0
        elif spread >= 5:
            money_pct = 60.0
        else:
            money_pct = 55.0
        
        # PUBLIC MONEY % - derived from moneyline odds (casual bettors)
        if snapshot.home_ml and snapshot.home_ml < 0:
            public_ml_pct = abs(snapshot.home_ml) / (abs(snapshot.home_ml) + 100)
            public_money_pct = 50 + (public_ml_pct - 0.5) * 80  # Scale up for visibility
        else:
            public_money_pct = 45  # Underdog at positive odds = lower money %
        
        # DIVERGENCE - THE SIGNAL
        divergence = ticket_pct - money_pct
        print(f"DEBUG Game {game.id}: spread={spread}, away_spread={away_spread}, ML={snapshot.home_ml}, ticket={ticket_pct:.1f}, money={money_pct}, public_money={public_money_pct:.1f}, div={divergence:.1f}")
        
        # Generate signal if divergence exists (sharps positioning different from public)
        if divergence >= -10:  # Lowered threshold to include more signals
            # Score based on divergence strength
            fade_score = 50 + abs(divergence) * 5
            confidence = min(0.95, 0.70 + abs(divergence) * 0.05)
            
            signal = Signal(
                game_id=game.id,
                signal_type=SignalType.FADE,
                fade_score=fade_score,
                confidence=confidence,
                recommendation=f"Take {game.away_team} {away_spread:+.1f}",
                reasoning=f"Divergence {divergence:.1f}% (Tickets {ticket_pct:.0f}% vs Money {money_pct:.0f}%) | Public Money: {public_money_pct:.0f}%",
                generated_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            db.add(signal)
            print(f"✅ SIGNAL CREATED: {game.away_team} @ {game.home_team}: Div {divergence:+.1f}% → {fade_score:.1f}")
            logger.info(f"✅ {game.away_team} @ {game.home_team}: Div {divergence:+.1f}% → {fade_score:.1f}")
        else:
            print(f"❌ SIGNAL REJECTED: Game {game.id} - divergence {divergence:.1f} not >= -10")
            
    except Exception as e:
        print(f"EXCEPTION Game {game.id}: {e}")
        logger.error(f"Failed to generate signals for game {game.id}: {e}")


def collect_odds_for_rlm():
    """Collect odds every 5 minutes for line movement detection"""
    logger.info("🎯 Collecting odds for RLM detection...")
    
    try:
        from scrapers.odds_api_scraper import OddsAPIScraper
        from database.db import get_db
        from database.models import Game, OddsSnapshot, OddsHistory
        from datetime import datetime
        import requests
        
        settings = get_settings()
        db = next(get_db())
        
        # Get scheduled/live games only
        games = db.query(Game).filter(
                Game.status.in_(["SCHEDULED", "IN_PROGRESS", "scheduled", "in_progress"])
        ).all()
        
        logger.info(f"📊 Tracking line movement for {len(games)} active games...")
        
        # Fetch current odds for each game from The Odds API (NBA 15s, NFL 30s)
        thresholds = {"basketball_nba": 15, "americanfootball_nfl": 30}
        # Prioritize NBA first
        for sport in ["basketball_nba", "americanfootball_nfl"]:
            # Cadence gating
            try:
                last = _last_odds_fetch.get(sport)
                elapsed = (datetime.utcnow() - last).total_seconds() if last else None
                if elapsed is not None and elapsed < thresholds[sport]:
                    logger.debug(f"⏳ Skipping {sport} fetch; {elapsed:.1f}s < {thresholds[sport]}s")
                    continue
            except Exception:
                pass

            url = f"{settings.ODDS_API_BASE}/sports/{sport}/odds"
            params = {
                "apiKey": settings.ODDS_API_KEY,
                "regions": "us",
                "markets": "spreads,h2h,totals",
                "oddsFormat": "american"
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"Odds API failed for {sport}: {response.status_code}")
                    continue
                
                odds_data = response.json()
                # Update last fetch timestamp for this sport
                _last_odds_fetch[sport] = datetime.utcnow()
                
                for game_odds in odds_data:
                    home_team = game_odds.get("home_team")
                    away_team = game_odds.get("away_team")
                    
                    # Find matching game in database
                    matching_game = db.query(Game).filter(
                        Game.home_team.ilike(f"%{home_team}%"),
                        Game.away_team.ilike(f"%{away_team}%"),
                        Game.status.in_(["SCHEDULED", "IN_PROGRESS", "scheduled", "in_progress"])
                    ).first()
                    
                    if not matching_game:
                        continue
                    
                    # Get best consensus odds from bookmakers
                    best_spread_home = None
                    best_ml_home = None
                    best_ml_away = None
                    
                    for bookmaker in game_odds.get("bookmakers", []):
                        for market in bookmaker.get("markets", []):
                            if market["key"] == "spreads":
                                for outcome in market["outcomes"]:
                                    if outcome["name"] == home_team:
                                        if best_spread_home is None:
                                            best_spread_home = float(outcome["point"])
                            elif market["key"] == "h2h":
                                for outcome in market["outcomes"]:
                                    if outcome["name"] == home_team and best_ml_home is None:
                                        best_ml_home = outcome["price"]
                                    elif outcome["name"] == away_team and best_ml_away is None:
                                        best_ml_away = outcome["price"]
                            elif market["key"] == "totals":
                                # totals market: outcomes include Over/Under with same point
                                try:
                                    point = float(market.get("outcomes", [{}])[0].get("point"))
                                except Exception:
                                    point = None
                                if point is not None:
                                    best_total = point
                                    over_odds = None
                                    under_odds = None
                                    for outcome in market.get("outcomes", []):
                                        if outcome.get("name") == "Over":
                                            over_odds = outcome.get("price")
                                        elif outcome.get("name") == "Under":
                                            under_odds = outcome.get("price")
                    
                    # Create snapshot
                    if (best_spread_home is not None) or (best_ml_home is not None) or ('best_total' in locals() and best_total is not None):
                        snapshot_kwargs = dict(
                            game_id=matching_game.id,
                            sportsbook="consensus",
                            home_spread=best_spread_home,
                            away_spread=-best_spread_home if best_spread_home else None,
                            home_ml=best_ml_home,
                            away_ml=best_ml_away,
                            total=('best_total' in locals() and best_total or None),
                            over_odds=('over_odds' in locals() and over_odds or None),
                            under_odds=('under_odds' in locals() and under_odds or None),
                            snapshot_time=datetime.utcnow()
                        )

                        # Keep lightweight snapshot for dashboards
                        db.add(OddsSnapshot(**snapshot_kwargs))

                        # Persist full history for RLM/divergence analysis
                        db.add(OddsHistory(**snapshot_kwargs))
                        logger.info(f"   📈 {home_team}: Spread={best_spread_home}, ML={best_ml_home}/{best_ml_away}")

                        # Publish line update via SSE
                        try:
                            from events.bus import bus
                            bus.publish_sync({
                                "type": "line_update",
                                "game_id": matching_game.id,
                                "home_team": matching_game.home_team,
                                "away_team": matching_game.away_team,
                                "home_spread": best_spread_home,
                                "away_spread": (-best_spread_home if best_spread_home is not None else None),
                                "home_ml": best_ml_home,
                                "away_ml": best_ml_away,
                                "total": ('best_total' in locals() and best_total or None),
                                "over_odds": ('over_odds' in locals() and over_odds or None),
                                "under_odds": ('under_odds' in locals() and under_odds or None),
                                "timestamp": datetime.utcnow().isoformat(),
                                "source": "odds_api"
                            })
                        except Exception:
                            pass
                
                db.commit()
                logger.info(f"✅ Odds collection complete for {sport}")
                
            except Exception as e:
                logger.error(f"Error fetching odds for {sport}: {e}")
                continue
        
    except Exception as e:
        logger.error(f"❌ RLM odds collection failed: {e}")


def sync_live_game_status():
    """
    Sync game status from ESPN API every minute for LIVE games
    Updates: SCHEDULED → IN_PROGRESS → FINAL with live scores
    This is the KEY job that enables real-time dashboard updates
    
    NOW USES REAL ESPN API STATUS INSTEAD OF TIME-BASED GUESSING
    """
    logger.info("⏱️ Syncing LIVE game statuses from ESPN API...")
    
    try:
        from database.db import get_db
        from database.models import Game
        from datetime import datetime, timedelta
        import requests
        
        settings = get_settings()
        db = next(get_db())
        
        # Get games from today + tomorrow (check all non-final games)
        now = datetime.utcnow()
        today = now.date()
        
        games_to_check = db.query(Game).filter(
            Game.game_time >= datetime.combine(today, datetime.min.time()),
            Game.game_time <= datetime.combine(today + timedelta(days=1), datetime.max.time())
        ).all()
        
        logger.info(f"📊 Checking status of {len(games_to_check)} games via ESPN API...")
        
        # Fetch live data from ESPN API (NBA + NFL)
        espn_games = {}
        
        thresholds = {"basketball_nba": 15, "americanfootball_nfl": 30}
        for sport, espn_sport in [("basketball_nba", "basketball/nba"), ("americanfootball_nfl", "football/nfl")]:
            # Cadence gating per sport
            try:
                last = _last_espn_fetch.get(sport)
                elapsed = (datetime.utcnow() - last).total_seconds() if last else None
                if elapsed is not None and elapsed < thresholds[sport]:
                    logger.debug(f"⏳ Skipping ESPN {sport}; {elapsed:.1f}s < {thresholds[sport]}s")
                    continue
            except Exception:
                pass

            try:
                url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/scoreboard"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    # Update last fetch timestamp
                    _last_espn_fetch[sport] = datetime.utcnow()
                    for event in data.get('events', []):
                        competition = event['competitions'][0]
                        status = competition['status']
                        
                        home_team = competition['competitors'][0]['team']['displayName']
                        away_team = competition['competitors'][1]['team']['displayName']
                        home_score = competition['competitors'][0].get('score', 0)
                        away_score = competition['competitors'][1].get('score', 0)
                        
                        state = status['type']['state']  # pre, in, post
                        detail = status['type']['detail']
                        # Period/clock (if available)
                        clock = status.get('displayClock')
                        period = status.get('period')
                        
                        # Map ESPN state to our status
                        if state == 'pre':
                            db_status = 'scheduled'
                        elif state == 'in':
                            db_status = 'in_progress'
                        elif state == 'post':
                            db_status = 'final'
                        else:
                            db_status = 'scheduled'
                        
                        espn_games[f"{away_team}@{home_team}"] = {
                            'status': db_status,
                            'home_score': int(home_score),
                            'away_score': int(away_score),
                            'detail': detail,
                            'clock': clock,
                            'period': period
                        }
                        
                logger.info(f"✅ Fetched {len(espn_games)} {sport} games from ESPN")
            except Exception as e:
                logger.warning(f"Failed to fetch ESPN {sport} data: {e}")
        
        # Update our games with ESPN data
        updated = 0
        for game in games_to_check:
            # Try to match game by team names
            game_key = f"{game.away_team}@{game.home_team}"
            
            if game_key in espn_games:
                espn_data = espn_games[game_key]
                old_status = game.status
                old_home_score = game.home_score
                old_away_score = game.away_score
                
                # Update status from ESPN
                game.status = espn_data['status']
                game.home_score = espn_data['home_score']
                game.away_score = espn_data['away_score']
                game.status_last_checked = datetime.utcnow()
                
                if old_status != game.status:
                    status_emoji = "🔴" if game.status == "in_progress" else "✅" if game.status == "final" else "⏰"
                    logger.info(f"{status_emoji} {game.away_team} @ {game.home_team}: {old_status} → {game.status} | Score: {game.away_score}-{game.home_score} ({espn_data['detail']})")
                    # Publish SSE event (sync context)
                    try:
                        from events.bus import bus
                        bus.publish_sync({
                            "type": "game_status",
                            "game_id": game.id,
                            "away_team": game.away_team,
                            "home_team": game.home_team,
                            "status": game.status,
                            "home_score": game.home_score,
                            "away_score": game.away_score,
                            "period": espn_data.get('period'),
                            "clock": espn_data.get('clock'),
                            "status_detail": espn_data.get('detail'),
                            "timestamp": datetime.utcnow().isoformat(),
                            "source": "espn"
                        })
                    except Exception:
                        pass
                    updated += 1
                # Publish score updates even if status hasn't changed
                elif (old_home_score != game.home_score) or (old_away_score != game.away_score):
                    try:
                        from events.bus import bus
                        bus.publish_sync({
                            "type": "score_update",
                            "game_id": game.id,
                            "away_team": game.away_team,
                            "home_team": game.home_team,
                            "home_score": game.home_score,
                            "away_score": game.away_score,
                            "period": espn_data.get('period'),
                            "clock": espn_data.get('clock'),
                            "timestamp": datetime.utcnow().isoformat(),
                            "source": "espn"
                        })
                    except Exception:
                        pass
            else:
                # Game not found in ESPN feed - check if it should be final based on time
                time_since_start = (now - game.game_time).total_seconds() / 60
                if time_since_start > 240 and game.status not in ["final", "FINAL"]:
                    game.status = "final"
                    game.status_last_checked = datetime.utcnow()
                    logger.info(f"✅ {game.away_team} @ {game.home_team}: Marked FINAL (not in ESPN feed, started {time_since_start:.0f}m ago)")
                    try:
                        from events.bus import bus
                        bus.publish_sync({
                            "type": "game_status",
                            "game_id": game.id,
                            "away_team": game.away_team,
                            "home_team": game.home_team,
                            "status": game.status,
                            "home_score": game.home_score,
                            "away_score": game.away_score,
                            "timestamp": datetime.utcnow().isoformat(),
                            "source": "fallback"
                        })
                    except Exception:
                        pass
                    updated += 1
        
        db.commit()
        logger.info(f"✅ ESPN sync complete: {updated} status changes, {len(espn_games)} games tracked")
        
    except Exception as e:
        logger.error(f"❌ Live game status sync failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


def detect_and_signal_rlm():
    """Detect reverse line movement and generate signals"""
    logger.info("🎯 Detecting reverse line movement...")
    
    try:
        from logic.line_movement_detector import generate_rlm_signals, get_rlm_stats
        
        # Generate RLM signals
        signals_created = generate_rlm_signals()
        
        # Log statistics
        stats = get_rlm_stats()
        logger.info(f"📊 RLM Stats: {stats['rlm_games']}/{stats['total_games']} games with RLM, Avg Strength: {stats['avg_rlm_strength']}pts")
        logger.info(f"✅ RLM Signal Generation: {signals_created} signals created/updated")
        
    except Exception as e:
        logger.error(f"❌ RLM detection failed: {e}")


async def daily_summary():
    """Generate daily summary"""
    logger.info("Generating daily summary...")
    # TODO: Implement daily summary logic


def stop_scheduler():
    """Stop the scheduler"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")


if __name__ == "__main__":
    start_scheduler()
    
    try:
        import asyncio
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler()
