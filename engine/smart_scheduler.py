"""
Smart Game-Time Scheduler
===========================
Autonomous daily engine that:

1. DISCOVERY  (9 AM, 3 PM, 6 PM) — ESPN (FREE) + Odds API /events (FREE)
   → Discovers all NBA games for today, extracts start times
   
2. WINDOW GROUPING — Groups games by start-time clusters (within 30 min)
   → e.g. 7:30 PM window, 8:00 PM window, 10:00 PM window
   
3. PRE-GAME ODDS FETCH — 20 min before each window
   → ONE Odds API /odds call (2-3 credits) → gets ALL games' final lines
   → Stores as "final snapshot" for RLM/divergence analysis
   
4. ANALYSIS — Runs full pipeline immediately after odds fetch
   → RLM, Total RLM, book disagreement, spread comparison
   → Outputs picks for games in this window

Credit Budget (500/month free tier):
   Discovery:    0 credits (ESPN + /events are free)
   Odds fetch:   ~3 per window × ~3-4 windows/day × 30 days = ~300 credits
   Safety:       200 credits buffer

Usage:
    python engine/smart_scheduler.py              # Start autonomous engine
    python engine/smart_scheduler.py --discover   # One-shot discovery only
    python engine/smart_scheduler.py --status     # Show scheduled windows
"""

import sys
import os
import json
import time
import requests
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.credit_tracker import CreditTracker
from engine.signals import SignalClassifier

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

from dotenv import load_dotenv
load_dotenv()

from config.api_registry import api
from alerts.pick_notifier import PickNotifier

# ─── Config ────────────────────────────────────────────────────────────
ODDS_API_KEY = api.odds_api.key
ODDS_API_BASE = api.odds_api.base_url
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# How many minutes before a window's first game to fetch odds
PRE_GAME_FETCH_MINUTES = 20

# Games starting within this many minutes of each other = same window
WINDOW_GROUP_MINUTES = 30

# ESPN endpoints (FREE)
ESPN_NBA = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ─── Data Structures ─────────────────────────────────────────────────
@dataclass
class DiscoveredGame:
    """A game discovered from ESPN / Odds API."""
    game_id: str
    home_team: str
    away_team: str
    commence_time: datetime  # UTC
    sport: str = "NBA"
    source: str = "espn"
    odds_api_id: Optional[str] = None  # Odds API event ID for matching
    status: str = "scheduled"

    @property
    def local_time_str(self) -> str:
        """ET display string."""
        et = self.commence_time - timedelta(hours=5)  # UTC → ET rough
        return et.strftime("%-I:%M %p ET") if os.name != "nt" else et.strftime("%#I:%M %p ET")

    def __repr__(self):
        return f"{self.away_team} @ {self.home_team} ({self.local_time_str})"


@dataclass
class GameWindow:
    """A cluster of games starting around the same time."""
    window_id: str
    window_start: datetime  # UTC — earliest game in this window
    games: List[DiscoveredGame] = field(default_factory=list)
    odds_fetched: bool = False
    odds_fetch_time: Optional[datetime] = None
    analysis_complete: bool = False
    odds_data: Optional[Dict] = None  # Raw odds response stored after fetch

    @property
    def fetch_at(self) -> datetime:
        """When to fetch odds — PRE_GAME_FETCH_MINUTES before window start."""
        return self.window_start - timedelta(minutes=PRE_GAME_FETCH_MINUTES)

    @property
    def game_count(self) -> int:
        return len(self.games)

    def local_time_str(self) -> str:
        et = self.window_start - timedelta(hours=5)
        return et.strftime("%-I:%M %p ET") if os.name != "nt" else et.strftime("%#I:%M %p ET")


# ─── Core Engine ──────────────────────────────────────────────────────
class SmartGameScheduler:
    """
    Autonomous engine that discovers games, groups by start time,
    and fetches final odds just before tip-off.
    """

    def __init__(self):
        self.credit_tracker = CreditTracker()
        self.notifier = PickNotifier()
        self.games: List[DiscoveredGame] = []
        self.windows: List[GameWindow] = []
        self.state_file = DATA_DIR / "scheduler_state.json"
        self._timers: List[threading.Timer] = []

    # ── Phase 1: Discovery (FREE) ────────────────────────────────────
    
    def discover_games(self) -> List[DiscoveredGame]:
        """
        Discover all NBA games for today using FREE endpoints.
        ESPN API (free) + Odds API /events (free) = 0 credits.
        """
        logger.info("=" * 70)
        logger.info("🔍 PHASE 1: GAME DISCOVERY (0 credits)")
        logger.info("=" * 70)

        espn_games = self._discover_from_espn()
        odds_events = self._discover_from_odds_api_events()

        # Merge: ESPN is primary (free, reliable), Odds API adds event IDs
        merged = self._merge_discoveries(espn_games, odds_events)

        # Filter to today's games only
        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1, hours=12)  # Include late night

        today_games = [
            g for g in merged
            if today_start <= g.commence_time <= tomorrow_start
            and g.status == "scheduled"
        ]

        # Filter out games that have already started
        today_games = [g for g in today_games if g.commence_time > now_utc]

        self.games = today_games
        logger.info(f"📋 Found {len(today_games)} upcoming NBA games for today")
        for g in sorted(today_games, key=lambda x: x.commence_time):
            logger.info(f"   {g}")

        return today_games

    def _discover_from_espn(self) -> List[DiscoveredGame]:
        """Fetch today's NBA games from ESPN (FREE, no credits)."""
        games = []
        try:
            resp = requests.get(ESPN_NBA, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            for event in data.get("events", []):
                comp = event["competitions"][0]
                home = next(t for t in comp["competitors"] if t["homeAway"] == "home")
                away = next(t for t in comp["competitors"] if t["homeAway"] == "away")

                # Parse status
                status_obj = comp.get("status", {})
                status_type = status_obj.get("type", {})
                state = status_type.get("state", "pre").lower()

                if state == "post":
                    status = "completed"
                elif state == "in":
                    status = "live"
                else:
                    status = "scheduled"

                commence = datetime.fromisoformat(
                    event["date"].replace("Z", "+00:00")
                )

                games.append(DiscoveredGame(
                    game_id=f"espn_{event['id']}",
                    home_team=home["team"]["displayName"],
                    away_team=away["team"]["displayName"],
                    commence_time=commence,
                    source="espn",
                    status=status,
                ))

            logger.info(f"   ESPN: {len(games)} games")
        except Exception as e:
            logger.error(f"   ESPN fetch failed: {e}")

        return games

    def _discover_from_odds_api_events(self) -> List[DiscoveredGame]:
        """
        Fetch NBA events from Odds API /events endpoint (FREE, 0 credits).
        This gives us event IDs we can use later for targeted odds queries.
        """
        games = []
        try:
            url = f"{ODDS_API_BASE}/sports/basketball_nba/events"
            params = {"apiKey": ODDS_API_KEY}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()

            # Track credit usage from headers (should be 0 for /events)
            self.credit_tracker.update_from_headers(dict(resp.headers))

            data = resp.json()
            for event in data:
                commence = datetime.fromisoformat(
                    event["commence_time"].replace("Z", "+00:00")
                )
                games.append(DiscoveredGame(
                    game_id=f"odds_{event['id']}",
                    home_team=event["home_team"],
                    away_team=event["away_team"],
                    commence_time=commence,
                    source="odds_api",
                    odds_api_id=event["id"],
                ))

            logger.info(f"   Odds API /events: {len(games)} events (0 credits)")
        except Exception as e:
            logger.error(f"   Odds API /events failed: {e}")

        return games

    def _merge_discoveries(
        self, espn_games: List[DiscoveredGame], odds_games: List[DiscoveredGame]
    ) -> List[DiscoveredGame]:
        """
        Merge ESPN + Odds API game lists. ESPN is primary.
        Attach Odds API event IDs to ESPN games via fuzzy team matching.
        """
        merged = list(espn_games)

        # Build lookup for Odds API games by normalized home team
        odds_lookup = {}
        for g in odds_games:
            key = self._normalize_team(g.home_team)
            odds_lookup[key] = g

        # Attach odds_api_id to ESPN games
        for game in merged:
            key = self._normalize_team(game.home_team)
            if key in odds_lookup:
                game.odds_api_id = odds_lookup[key].odds_api_id

        # Add any Odds API games not found in ESPN
        espn_keys = {self._normalize_team(g.home_team) for g in espn_games}
        for g in odds_games:
            key = self._normalize_team(g.home_team)
            if key not in espn_keys:
                merged.append(g)

        return merged

    @staticmethod
    def _normalize_team(name: str) -> str:
        """Normalize team name for matching."""
        # Handle common variations
        replacements = {
            "LA Clippers": "clippers",
            "L.A. Clippers": "clippers",
            "Los Angeles Clippers": "clippers",
            "LA Lakers": "lakers",
            "L.A. Lakers": "lakers",
            "Los Angeles Lakers": "lakers",
        }
        if name in replacements:
            return replacements[name]
        # Use last word as key (e.g., "Golden State Warriors" → "warriors")
        return name.strip().split()[-1].lower()

    # ── Phase 2: Window Grouping ─────────────────────────────────────

    def group_into_windows(self) -> List[GameWindow]:
        """
        Group games into time windows. Games starting within
        WINDOW_GROUP_MINUTES of the window start go into the same window.
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("📦 PHASE 2: WINDOW GROUPING")
        logger.info("=" * 70)

        if not self.games:
            logger.info("   No games to group.")
            return []

        # Sort by start time
        sorted_games = sorted(self.games, key=lambda g: g.commence_time)

        windows = []
        current_window = None

        for game in sorted_games:
            if current_window is None or (
                game.commence_time - current_window.window_start
            ) > timedelta(minutes=WINDOW_GROUP_MINUTES):
                # Start new window
                window_id = f"window_{game.commence_time.strftime('%H%M')}"
                current_window = GameWindow(
                    window_id=window_id,
                    window_start=game.commence_time,
                )
                windows.append(current_window)

            current_window.games.append(game)

        self.windows = windows

        for w in windows:
            game_list = ", ".join(f"{g.away_team}@{g.home_team}" for g in w.games)
            logger.info(
                f"   🕐 {w.local_time_str()} window | "
                f"{w.game_count} games | "
                f"Fetch at {w.fetch_at.strftime('%H:%M')} UTC | "
                f"{game_list}"
            )

        return windows

    # ── Phase 3: Pre-Game Odds Fetch (costs credits) ─────────────────

    def fetch_odds_for_window(self, window: GameWindow) -> Optional[Dict]:
        """
        Fetch current odds from Odds API for ALL NBA games.
        ONE call covers every game. Costs 2-3 credits depending on markets.
        
        Returns raw API response (list of games with bookmaker odds).
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"📡 PHASE 3: ODDS FETCH for {window.local_time_str()} window")
        logger.info(f"   Games: {window.game_count}")
        logger.info("=" * 70)

        # Determine optimal markets based on budget
        markets = self.credit_tracker.get_optimal_markets()
        cost = self.credit_tracker.get_market_cost(markets)

        if not self.credit_tracker.can_afford(cost):
            logger.warning(
                f"   ⚠️  Cannot afford {cost} credits! "
                f"Remaining: {self.credit_tracker.remaining}. Skipping."
            )
            return None

        logger.info(f"   Markets: {markets} | Cost: {cost} credits")
        logger.info(f"   {self.credit_tracker.summary()}")

        try:
            url = f"{ODDS_API_BASE}/sports/basketball_nba/odds"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": markets,
                "oddsFormat": "american",
            }

            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()

            # Record credit usage
            self.credit_tracker.record_call(
                endpoint="/odds",
                cost=cost,
                details=f"markets={markets}, window={window.window_id}",
            )
            self.credit_tracker.update_from_headers(dict(resp.headers))

            data = resp.json()
            window.odds_fetched = True
            window.odds_fetch_time = datetime.now(timezone.utc)
            window.odds_data = data

            logger.info(f"   ✅ Got odds for {len(data)} games")

            # Save raw response
            filename = DATA_DIR / f"odds_{window.window_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            with open(filename, "w") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"   💾 Saved to {filename.name}")

            return data

        except Exception as e:
            logger.error(f"   ❌ Odds fetch failed: {e}")
            return None

    # ── Phase 4: Analysis ────────────────────────────────────────────

    def analyze_window(self, window: GameWindow) -> Dict:
        """
        Run analysis pipeline on fetched odds for games in this window.
        Compares current lines across books, detects disagreements,
        identifies best lines.
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"🧠 PHASE 4: ANALYSIS for {window.local_time_str()} window")
        logger.info("=" * 70)

        if not window.odds_data:
            logger.warning("   No odds data available. Skipping analysis.")
            return {}

        results = {}
        classifier = SignalClassifier()  # Instantiate once, reuse per game
        window_game_teams = {
            self._normalize_team(g.home_team) for g in window.games
        }

        for game_odds in window.odds_data:
            home = game_odds.get("home_team", "")
            away = game_odds.get("away_team", "")
            norm_home = self._normalize_team(home)

            if norm_home not in window_game_teams:
                continue  # This game isn't in our window

            game_key = f"{away} @ {home}"
            commence = game_odds.get("commence_time", "")

            # Extract all bookmaker lines
            books = game_odds.get("bookmakers", [])
            spread_lines = []
            total_lines = []
            ml_lines = []

            for book in books:
                book_name = book.get("title", book.get("key", "Unknown"))
                for market in book.get("markets", []):
                    mkey = market.get("key", "")
                    outcomes = market.get("outcomes", [])

                    if mkey == "spreads":
                        for o in outcomes:
                            spread_lines.append({
                                "book": book_name,
                                "team": o["name"],
                                "line": o.get("point", 0),
                                "odds": o.get("price", -110),
                            })
                    elif mkey == "totals":
                        for o in outcomes:
                            total_lines.append({
                                "book": book_name,
                                "side": o["name"],  # Over/Under
                                "line": o.get("point", 0),
                                "odds": o.get("price", -110),
                            })
                    elif mkey == "h2h":
                        for o in outcomes:
                            ml_lines.append({
                                "book": book_name,
                                "team": o["name"],
                                "odds": o.get("price", 0),
                            })

            # Analyze spread consensus & disagreements
            spread_analysis = self._analyze_spreads(spread_lines, home, away)
            total_analysis = self._analyze_totals(total_lines)
            ml_analysis = self._analyze_moneylines(ml_lines, home, away)

            # ── Signal Classification ─────────────────────────────────
            # Construct input dicts for SignalClassifier
            # Note: classifier is instantiated once outside the loop (see below)
            
            # Note: Opening lines not always available at scheduler runtime
            # We'll use current lines and handle missing data gracefully
            spread_data = None
            if spread_analysis:
                spread_data = {
                    "open": None,  # Opening line not stored yet
                    "current": spread_analysis["consensus_line"],
                    "public_pct": None,  # Public data not available here
                }
            
            total_data = None
            if total_analysis:
                total_data = {
                    "open": None,  # Opening line not stored yet
                    "current": total_analysis["consensus_line"],
                    "over_pct": None,  # Public data not available here
                }
            
            book_data = None
            if spread_analysis:
                book_data = {
                    "spread_range": spread_analysis.get("spread_range", 0),
                }
            
            # Run signal classification
            signal_profile = classifier.classify(
                game_key=game_key,
                spread_data=spread_data,
                total_data=total_data,
                book_data=book_data,
            )

            results[game_key] = {
                "game": game_key,
                "commence_time": commence,
                "books_count": len(books),
                "spreads": spread_analysis,
                "totals": total_analysis,
                "moneylines": ml_analysis,
                "raw_spread_lines": spread_lines,
                "raw_total_lines": total_lines,
                "raw_ml_lines": ml_lines,
                "signal_profile": signal_profile.to_dict(),
            }

            # Print summary
            logger.info(f"\n   📊 {game_key}")
            logger.info(f"      Books: {len(books)}")
            if spread_analysis:
                logger.info(
                    f"      Spread: {home} {spread_analysis['consensus_line']:+.1f} "
                    f"(range: {spread_analysis['min_line']:+.1f} to {spread_analysis['max_line']:+.1f})"
                )
                if spread_analysis["disagreement"]:
                    logger.info(f"      ⚠️  SPREAD DISAGREEMENT: {spread_analysis['spread_range']:.1f} pts")
            if total_analysis:
                logger.info(
                    f"      Total: {total_analysis['consensus_line']:.1f} "
                    f"(range: {total_analysis['min_line']:.1f} to {total_analysis['max_line']:.1f})"
                )
                if total_analysis["disagreement"]:
                    logger.info(f"      ⚠️  TOTAL DISAGREEMENT: {total_analysis['total_range']:.1f} pts")
            if ml_analysis:
                logger.info(
                    f"      ML: {home} {ml_analysis['home_consensus']:+d} / "
                    f"{away} {ml_analysis['away_consensus']:+d}"
                )
            
            # Log signal classification results
            if signal_profile.tier != "PASS":
                logger.info(f"      🎯 SIGNAL: {signal_profile.tier} (confidence: {signal_profile.total_confidence:.0f}%)")
                if signal_profile.primary_signals:
                    for sig in signal_profile.primary_signals:
                        logger.info(f"         PRIMARY: {sig.signal_type.value}")
                if signal_profile.confirmation_signals:
                    logger.info(f"         +{len(signal_profile.confirmation_signals)} confirmation signals")
            elif signal_profile.confirmation_signals and not signal_profile.has_primary:
                logger.info(f"      ⚠️  {len(signal_profile.confirmation_signals)} confirmation signals but NO PRIMARY — PASS")

        window.analysis_complete = True

        # Save analysis
        analysis_file = DATA_DIR / f"analysis_{window.window_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(analysis_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\n   💾 Analysis saved to {analysis_file.name}")

        # 🔔 Send to Discord (if configured)
        self.notifier.send_window_analysis(window.window_id, results)

        # ⚠️ Credit warning if running low
        self.notifier.send_credit_warning(
            self.credit_tracker.remaining,
            self.credit_tracker.data.get("credits_remaining", 500),
        )

        return results

    def _analyze_spreads(self, lines: List[Dict], home: str, away: str) -> Optional[Dict]:
        """Analyze spread lines across books."""
        if not lines:
            return None

        home_lines = [l for l in lines if l["team"] == home]
        if not home_lines:
            return None

        points = [l["line"] for l in home_lines]
        consensus = sum(points) / len(points)
        min_line = min(points)
        max_line = max(points)
        spread_range = max_line - min_line

        # Find best line for each side
        best_home = min(home_lines, key=lambda l: l["line"])  # Closest to 0 or most positive
        away_lines = [l for l in lines if l["team"] == away]
        best_away = max(away_lines, key=lambda l: l["line"]) if away_lines else None

        return {
            "consensus_line": round(consensus, 1),
            "min_line": min_line,
            "max_line": max_line,
            "spread_range": spread_range,
            "disagreement": spread_range >= 1.5,
            "book_count": len(home_lines),
            "best_home": best_home,
            "best_away": best_away,
            "all_lines": home_lines,
        }

    def _analyze_totals(self, lines: List[Dict]) -> Optional[Dict]:
        """Analyze total lines across books."""
        if not lines:
            return None

        over_lines = [l for l in lines if l["side"].lower() == "over"]
        if not over_lines:
            return None

        points = [l["line"] for l in over_lines]
        consensus = sum(points) / len(points)
        min_line = min(points)
        max_line = max(points)
        total_range = max_line - min_line

        best_over = max(over_lines, key=lambda l: l["line"])  # Highest total for over value
        under_lines = [l for l in lines if l["side"].lower() == "under"]
        best_under = min(under_lines, key=lambda l: l["line"]) if under_lines else None

        return {
            "consensus_line": round(consensus, 1),
            "min_line": min_line,
            "max_line": max_line,
            "total_range": total_range,
            "disagreement": total_range >= 1.5,
            "book_count": len(over_lines),
            "best_over": best_over,
            "best_under": best_under,
        }

    def _analyze_moneylines(self, lines: List[Dict], home: str, away: str) -> Optional[Dict]:
        """Analyze moneyline across books."""
        if not lines:
            return None

        home_mls = [l for l in lines if l["team"] == home]
        away_mls = [l for l in lines if l["team"] == away]

        if not home_mls or not away_mls:
            return None

        home_odds = [l["odds"] for l in home_mls]
        away_odds = [l["odds"] for l in away_mls]

        return {
            "home_consensus": round(sum(home_odds) / len(home_odds)),
            "away_consensus": round(sum(away_odds) / len(away_odds)),
            "home_best": max(home_odds),  # Best price for home
            "away_best": max(away_odds),  # Best price for away
            "home_worst": min(home_odds),
            "away_worst": min(away_odds),
        }

    # ── Scheduling / Timer Management ────────────────────────────────

    def schedule_all_windows(self):
        """
        For each window, schedule a timer to fire PRE_GAME_FETCH_MINUTES
        before the window's first game. When it fires, fetch odds + analyze.
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("⏰ SCHEDULING ODDS FETCHES")
        logger.info("=" * 70)

        now = datetime.now(timezone.utc)
        self._cancel_all_timers()

        for window in self.windows:
            fetch_at = window.fetch_at
            delay = (fetch_at - now).total_seconds()

            if delay <= 0:
                # Window's fetch time already passed
                if not window.odds_fetched and window.window_start > now:
                    # Game hasn't started yet, fetch immediately
                    logger.info(
                        f"   ⚡ {window.local_time_str()} — fetch time passed, "
                        f"fetching NOW (game hasn't started)"
                    )
                    self._execute_window(window)
                else:
                    logger.info(
                        f"   ⏭️  {window.local_time_str()} — already passed, skipping"
                    )
                continue

            # Schedule future fetch
            timer = threading.Timer(delay, self._execute_window, args=[window])
            timer.daemon = True
            timer.name = f"fetch_{window.window_id}"
            timer.start()
            self._timers.append(timer)

            fetch_et = fetch_at - timedelta(hours=5)
            logger.info(
                f"   🕐 {window.local_time_str()} — "
                f"odds fetch scheduled for {fetch_et.strftime('%#I:%M %p ET')} "
                f"({delay/60:.0f} min from now) | "
                f"{window.game_count} games"
            )

    def _execute_window(self, window: GameWindow):
        """Execute odds fetch + analysis for a window."""
        logger.info(f"\n🚀 TIMER FIRED for {window.window_id} ({window.local_time_str()})")

        # Fetch odds
        odds = self.fetch_odds_for_window(window)
        if not odds:
            return

        # Run analysis
        results = self.analyze_window(window)

        # Print final summary
        self._print_window_summary(window, results)

    def _print_window_summary(self, window: GameWindow, results: Dict):
        """Print a clean summary for this window's picks."""
        logger.info("")
        logger.info("═" * 70)
        logger.info(f"  🏀 WINDOW REPORT: {window.local_time_str()}")
        logger.info(f"  Games: {window.game_count} | Books analyzed: varies")
        logger.info("═" * 70)

        for game_key, analysis in results.items():
            logger.info(f"\n  {game_key}")
            sp = analysis.get("spreads")
            tot = analysis.get("totals")
            ml = analysis.get("moneylines")

            if sp:
                logger.info(f"    Spread consensus: {sp['consensus_line']:+.1f}")
                if sp["disagreement"]:
                    logger.info(
                        f"    → SHOP ALERT: {sp['spread_range']:.1f}pt range "
                        f"({sp['min_line']:+.1f} to {sp['max_line']:+.1f})"
                    )
                if sp.get("best_away"):
                    ba = sp["best_away"]
                    logger.info(f"    → Best dog line: +{ba['line']} @ {ba['book']}")

            if tot:
                logger.info(f"    Total consensus: {tot['consensus_line']:.1f}")
                if tot["disagreement"]:
                    logger.info(
                        f"    → SHOP ALERT: {tot['total_range']:.1f}pt range "
                        f"({tot['min_line']:.1f} to {tot['max_line']:.1f})"
                    )

            if ml:
                logger.info(
                    f"    ML: Home {ml['home_consensus']:+d} / Away {ml['away_consensus']:+d}"
                )

        logger.info("")
        logger.info(f"  {self.credit_tracker.summary()}")
        logger.info("═" * 70)

    def _cancel_all_timers(self):
        """Cancel all pending timers."""
        for t in self._timers:
            t.cancel()
        self._timers.clear()

    # ── State Persistence ────────────────────────────────────────────

    def save_state(self):
        """Save current state to disk."""
        state = {
            "last_discovery": datetime.now(timezone.utc).isoformat(),
            "games_count": len(self.games),
            "windows_count": len(self.windows),
            "windows": [
                {
                    "window_id": w.window_id,
                    "window_start": w.window_start.isoformat(),
                    "game_count": w.game_count,
                    "odds_fetched": w.odds_fetched,
                    "analysis_complete": w.analysis_complete,
                    "games": [
                        {
                            "home_team": g.home_team,
                            "away_team": g.away_team,
                            "commence_time": g.commence_time.isoformat(),
                        }
                        for g in w.games
                    ],
                }
                for w in self.windows
            ],
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    # ── Main Entry Points ────────────────────────────────────────────

    def run_discovery_and_schedule(self):
        """
        Full pipeline: discover → group → schedule.
        Call this at 9 AM, 3 PM, 6 PM.
        """
        self.discover_games()
        self.group_into_windows()
        self.schedule_all_windows()
        self.save_state()

    def run_autonomous(self):
        """
        Run the full autonomous loop:
        1. Discover games now
        2. Schedule odds fetches for each window
        3. Keep running until all windows are processed
        4. Re-discover every 3 hours in case of schedule changes
        """
        logger.info("=" * 70)
        logger.info("  🤖 HOUSE EDGE — AUTONOMOUS GAME-TIME SCHEDULER")
        logger.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
        logger.info(f"  {self.credit_tracker.summary()}")
        logger.info("=" * 70)

        # Initial discovery
        self.run_discovery_and_schedule()

        if not self.windows:
            logger.info("\n🏁 No upcoming windows. Engine idle.")
            return

        # Calculate how long to stay alive
        last_window = max(self.windows, key=lambda w: w.window_start)
        end_time = last_window.window_start + timedelta(minutes=10)
        
        logger.info(f"\n🔄 Engine will stay active until {end_time.strftime('%H:%M')} UTC")
        logger.info("   (Re-discovers every 3 hours for schedule changes)")
        logger.info("   Press Ctrl+C to stop.\n")

        try:
            rediscovery_interval = 3 * 3600  # 3 hours
            last_discovery = time.time()
            
            while datetime.now(timezone.utc) < end_time:
                # Re-discover periodically
                if time.time() - last_discovery > rediscovery_interval:
                    logger.info("\n🔄 Periodic re-discovery...")
                    self.run_discovery_and_schedule()
                    last_discovery = time.time()

                time.sleep(30)  # Check every 30 seconds

        except KeyboardInterrupt:
            logger.info("\n🛑 Engine stopped by user.")
        finally:
            self._cancel_all_timers()
            self.save_state()
            logger.info("✅ State saved. Goodbye.")

    def run_one_shot(self):
        """
        One-shot mode: discover → fetch odds NOW for all windows → analyze.
        Useful for manual testing or immediate analysis.
        """
        logger.info("=" * 70)
        logger.info("  🎯 ONE-SHOT MODE: Discover + Fetch + Analyze NOW")
        logger.info("=" * 70)

        self.discover_games()
        self.group_into_windows()

        all_results = {}
        for window in self.windows:
            odds = self.fetch_odds_for_window(window)
            if odds:
                results = self.analyze_window(window)
                all_results.update(results)
                self._print_window_summary(window, results)

        self.save_state()
        return all_results


# ─── CLI Entry Point ─────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="HOUSE EDGE Smart Game-Time Scheduler")
    parser.add_argument("--discover", action="store_true", help="One-shot discovery only (no odds fetch)")
    parser.add_argument("--status", action="store_true", help="Show credit status and scheduled windows")
    parser.add_argument("--one-shot", action="store_true", help="Discover + fetch + analyze immediately")
    parser.add_argument("--autonomous", action="store_true", help="Run autonomous mode (default)")
    args = parser.parse_args()

    scheduler = SmartGameScheduler()

    if args.discover:
        scheduler.discover_games()
        scheduler.group_into_windows()
        scheduler.save_state()

    elif args.status:
        print(scheduler.credit_tracker.summary())
        if scheduler.state_file.exists():
            with open(scheduler.state_file) as f:
                state = json.load(f)
            print(f"\nLast discovery: {state.get('last_discovery', 'Never')}")
            print(f"Games: {state.get('games_count', 0)}")
            print(f"Windows: {state.get('windows_count', 0)}")
            for w in state.get("windows", []):
                status = "✅" if w["odds_fetched"] else "⏳"
                print(f"  {status} {w['window_id']} | {w['game_count']} games")

    elif args.one_shot:
        scheduler.run_one_shot()

    else:
        scheduler.run_autonomous()


if __name__ == "__main__":
    main()
