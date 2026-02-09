"""
Autonomous Game Discovery Engine
Automatically finds upcoming games from multiple sources without manual input
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from database.db import get_db
from database.models import Game

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from config.api_registry import api
ODDS_API_KEY = api.odds_api.key


class GameDiscoveryEngine:
    """Automatically discover upcoming games from ESPN, The Odds API, etc."""
    
    def __init__(self):
        self.sources = {
            "odds_api": self.fetch_from_odds_api,
            "espn_api": self.fetch_from_espn,
        }
    
    async def discover_all_upcoming_games(self, days_ahead: int = 7) -> List[Dict]:
        """
        Scan all sources and return upcoming games
        
        Args:
            days_ahead: How many days in the future to look
            
        Returns:
            List of game dictionaries with standardized format
        """
        all_games = []
        
        for source_name, fetch_func in self.sources.items():
            try:
                logger.info(f"Discovering games from {source_name}...")
                games = await fetch_func(days_ahead)
                all_games.extend(games)
                logger.info(f"Found {len(games)} games from {source_name}")
            except Exception as e:
                logger.error(f"Failed to fetch from {source_name}: {e}")
        
        # Deduplicate games by matching team names and times
        unique_games = self._deduplicate_games(all_games)
        
        logger.info(f"Total unique games discovered: {len(unique_games)}")
        return unique_games
    
    async def fetch_from_odds_api(self, days_ahead: int = 7) -> List[Dict]:
        """
        Fetch upcoming games from The Odds API
        This is our primary source - most reliable
        """
        games = []
        
        # NFL
        try:
            url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": "spreads,totals",
                "oddsFormat": "american"
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for game in data:
                    games.append({
                        "source": "odds_api",
                        "sport": "NFL",
                        "game_id": game['id'],
                        "home_team": game['home_team'],
                        "away_team": game['away_team'],
                        "commence_time": game['commence_time'],
                        "bookmakers": game.get('bookmakers', [])
                    })
        except Exception as e:
            logger.error(f"Failed to fetch NFL from Odds API: {e}")
        
        # NBA
        try:
            url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": "spreads,totals",
                "oddsFormat": "american"
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for game in data:
                    games.append({
                        "source": "odds_api",
                        "sport": "NBA",
                        "game_id": game['id'],
                        "home_team": game['home_team'],
                        "away_team": game['away_team'],
                        "commence_time": game['commence_time'],
                        "bookmakers": game.get('bookmakers', [])
                    })
        except Exception as e:
            logger.error(f"Failed to fetch NBA from Odds API: {e}")

        # NCAAB — disabled to save Odds API credits (NBA focus)
        # Use ESPN (free) for NCAAB game discovery instead
        
        return games
    
    async def fetch_from_espn(self, days_ahead: int = 7) -> List[Dict]:
        """
        Fetch upcoming games from ESPN's public API
        Free backup source
        """
        games = []
        
        # ESPN NFL Schedule
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                for event in data.get('events', []):
                    competition = event['competitions'][0]
                    home_team = next(t for t in competition['competitors'] if t['homeAway'] == 'home')
                    away_team = next(t for t in competition['competitors'] if t['homeAway'] == 'away')
                    
                    games.append({
                        "source": "espn",
                        "sport": "NFL",
                        "game_id": event['id'],
                        "home_team": home_team['team']['displayName'],
                        "away_team": away_team['team']['displayName'],
                        "commence_time": event['date'],
                        "espn_data": event
                    })
        except Exception as e:
            logger.error(f"Failed to fetch from ESPN: {e}")
        
        # ESPN NCAAB Schedule
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                for event in data.get('events', []):
                    competition = event['competitions'][0]
                    home_team = next(t for t in competition['competitors'] if t['homeAway'] == 'home')
                    away_team = next(t for t in competition['competitors'] if t['homeAway'] == 'away')
                    
                    games.append({
                        "source": "espn",
                        "sport": "NCAAB",
                        "game_id": event['id'],
                        "home_team": home_team['team']['displayName'],
                        "away_team": away_team['team']['displayName'],
                        "commence_time": event['date'],
                        "espn_data": event
                    })
        except Exception as e:
            logger.error(f"Failed to fetch NCAAB from ESPN: {e}")

        # ESPN NBA Schedule
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                for event in data.get('events', []):
                    competition = event['competitions'][0]
                    home_team = next(t for t in competition['competitors'] if t['homeAway'] == 'home')
                    away_team = next(t for t in competition['competitors'] if t['homeAway'] == 'away')
                    
                    games.append({
                        "source": "espn",
                        "sport": "NBA",
                        "game_id": event['id'],
                        "home_team": home_team['team']['displayName'],
                        "away_team": away_team['team']['displayName'],
                        "commence_time": event['date'],
                        "espn_data": event
                    })
        except Exception as e:
            logger.error(f"Failed to fetch NBA from ESPN: {e}")
        
        return games
    
    def _deduplicate_games(self, games: List[Dict]) -> List[Dict]:
        """Remove duplicate games by matching teams and time"""
        unique = {}
        
        for game in games:
            # Create key: sport + teams + rough time
            key = f"{game['sport']}_{game['home_team']}_{game['away_team']}"
            
            # Prefer odds_api data over espn
            if key not in unique or game['source'] == 'odds_api':
                unique[key] = game
        
        return list(unique.values())
    
    def save_to_database(self, games: List[Dict], db: Session):
        """Save discovered games to database"""
        saved_count = 0
        
        for game_data in games:
            try:
                # Check if game already exists
                existing = db.query(Game).filter(
                    Game.home_team == game_data['home_team'],
                    Game.away_team == game_data['away_team']
                ).first()
                
                if not existing:
                    game = Game(
                        sport=game_data['sport'],
                        league=game_data['sport'],  # Use sport as league (e.g., NFL, NBA)
                        home_team=game_data['home_team'],
                        away_team=game_data['away_team'],
                        game_time=datetime.fromisoformat(game_data['commence_time'].replace('Z', '+00:00')),
                        status='scheduled'
                    )
                    db.add(game)
                    saved_count += 1
                else:
                    logger.debug(f"Game already exists: {game_data['home_team']} vs {game_data['away_team']}")
            
            except Exception as e:
                logger.error(f"Failed to save game: {e}")
        
        db.commit()
        logger.info(f"Saved {saved_count} new games to database")
        return saved_count
    
    def update_game_statuses(self, db: Session):
        """
        AUTHORITATIVE game status sync from ESPN API.
        
        ✅ ANSWERS THE 3 CRITICAL QUESTIONS:
        1. Is game scheduled? (future game_time + ESPN says STATUS_SCHEDULED)
        2. Is game live? (ESPN says STATUS_IN_PROGRESS)
        3. Is game finished? (ESPN says STATUS_FINAL or past game_time with no ESPN data)
        
        Status Outcomes:
        - 'scheduled' = Show signals (game is upcoming)
        - 'live' = Hide signals (game in progress, no bets allowed)
        - 'completed' = Hide signals (game finished, past betting window)
        """
        updated_count = 0
        now = datetime.utcnow()
        sports_apis = {
            'NFL': 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
            'NBA': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
        }
        
        try:
            # === FETCH ESPN DATA FOR ALL SPORTS ===
            for sport, url in sports_apis.items():
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code != 200:
                        logger.warning(f"ESPN API returned {response.status_code} for {sport}")
                        continue
                    
                    data = response.json()
                    
                    for event in data.get('events', []):
                        try:
                            competition = event['competitions'][0]
                            status_obj = competition.get('status', {})
                            espn_id = event.get('id')
                            
                            # Extract ESPN status (robust mapping)
                            if isinstance(status_obj, dict):
                                type_obj = status_obj.get('type', {})
                                if isinstance(type_obj, dict):
                                    state = (type_obj.get('state') or '').lower()  # pre | in | post
                                    name = str(type_obj.get('name', 'UNKNOWN')).upper()
                                else:
                                    state = ''
                                    name = str(type_obj or 'UNKNOWN').upper()
                                espn_status = name
                                # Determine final/in-progress using both state and name
                                is_final = (state == 'post') or ('FINAL' in name) or ('COMPLETED' in name) or status_obj.get('completed', False)
                                # Treat quarter/period transitions as live
                                live_markers = ['IN_PROGRESS', 'HALFTIME', 'END_PERIOD', 'FIRST_QUARTER', 'SECOND_QUARTER', 'THIRD_QUARTER', 'FOURTH_QUARTER']
                                is_in_progress = (state == 'in') or any(m in name for m in live_markers)
                            else:
                                espn_status = str(status_obj).upper()
                                is_final = 'FINAL' in espn_status or 'COMPLETED' in espn_status
                                live_markers = ['IN_PROGRESS', 'HALFTIME', 'END_PERIOD']
                                is_in_progress = any(m in espn_status for m in live_markers)
                            
                            # Extract teams
                            home_team = next((t for t in competition['competitors'] if t['homeAway'] == 'home'), None)
                            away_team = next((t for t in competition['competitors'] if t['homeAway'] == 'away'), None)
                            
                            if not (home_team and away_team):
                                continue
                            
                            home_name = home_team['team']['displayName']
                            away_name = away_team['team']['displayName']
                            
                            # DETERMINE STATUS based on ESPN
                            if is_final:
                                new_status = 'completed'
                            elif is_in_progress:
                                new_status = 'live'
                            else:
                                new_status = 'scheduled'
                            
                            # Update database
                            game = db.query(Game).filter(
                                Game.home_team == home_name,
                                Game.away_team == away_name,
                                Game.sport == sport
                            ).first()
                            
                            if game:
                                old_status = game.status
                                game.espn_id = espn_id
                                game.espn_status = espn_status
                                game.status = new_status
                                game.status_last_checked = now
                                db.add(game)
                                
                                if old_status != new_status:
                                    logger.info(f"STATUS: {away_name} @ {home_name} | {old_status} -> {new_status} | ESPN={espn_status}")
                                    updated_count += 1
                        
                        except Exception as e:
                            logger.error(f"Error processing event: {e}")
                            continue
                
                except Exception as e:
                    logger.error(f"Failed to fetch {sport} from ESPN: {e}")
                    continue
            
            # === SAFETY: Mark games past their time as 'completed' ===
            # (If we don't see them on ESPN, they're definitely finished)
            orphaned = db.query(Game).filter(
                Game.status != 'completed',
                Game.game_time < now,
                Game.espn_id == None  # We never saw this on ESPN
            ).all()
            
            for game in orphaned:
                old_status = game.status
                game.status = 'completed'
                db.add(game)
                logger.warning(f"ORPHAN: {game.away_team} @ {game.home_team} | {old_status} -> completed (past time, no ESPN data)")
                updated_count += 1
            
            db.commit()
            if updated_count > 0:
                logger.info(f"Updated {updated_count} game statuses from ESPN")
        
        except Exception as e:
            logger.error(f"Failed to update game statuses: {e}")
            db.rollback()


async def main():
    """Test the game discovery engine"""
    engine = GameDiscoveryEngine()
    
    logger.info("=" * 80)
    logger.info("AUTONOMOUS GAME DISCOVERY ENGINE")
    logger.info("=" * 80)
    
    games = await engine.discover_all_upcoming_games(days_ahead=7)
    
    logger.info(f"\nDiscovered {len(games)} upcoming games:")
    logger.info("")
    
    # Group by sport
    by_sport = {}
    for game in games:
        sport = game['sport']
        if sport not in by_sport:
            by_sport[sport] = []
        by_sport[sport].append(game)
    
    for sport, sport_games in by_sport.items():
        logger.info(f"\n{sport} ({len(sport_games)} games):")
        for game in sorted(sport_games, key=lambda x: x['commence_time'])[:5]:
            commence = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
            logger.info(f"  {game['away_team']} @ {game['home_team']}")
            logger.info(f"    {commence.strftime('%Y-%m-%d %H:%M')} | Source: {game['source']}")


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
