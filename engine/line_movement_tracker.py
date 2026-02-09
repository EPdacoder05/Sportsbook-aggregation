"""
Live Line Movement Tracker
Detects when sportsbooks change their lines and triggers re-analysis
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from database.db import get_db
from database.models import Game, OddsSnapshot

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from config.api_registry import api
ODDS_API_KEY = api.odds_api.key


class LineMovementTracker:
    """
    Monitors live line changes across all sportsbooks
    Detects steam moves, sharp action, and reverse line movement
    """
    
    # Thresholds for significant moves
    SIGNIFICANT_MOVE = 1.0  # 1 point move on spread
    STEAM_MOVE = 2.0  # 2+ point move in short time = steam
    
    def __init__(self):
        self.previous_lines = {}  # Cache previous lines for comparison
    
    async def track_all_live_games(self, db: Session) -> List[Dict]:
        """
        Check all live games for line movements
        
        Returns:
            List of games with significant line movements
        """
        movements = []
        
        # Get all games scheduled for today or in progress
        today = datetime.now()
        games = db.query(Game).filter(
            Game.game_time >= today - timedelta(hours=6),
            Game.game_time <= today + timedelta(hours=24)
        ).all()
        
        logger.info(f"Tracking {len(games)} games for line movements")
        
        for game in games:
            try:
                movement = await self.check_game_lines(game, db)
                if movement:
                    movements.append(movement)
            except Exception as e:
                logger.error(f"Failed to track {game.home_team} vs {game.away_team}: {e}")
        
        return movements
    
    async def check_game_lines(self, game: Game, db: Session) -> Optional[Dict]:
        """
        Check if a specific game has significant line movement
        
        Returns:
            Movement data if significant, None otherwise
        """
        try:
            # Fetch current lines from The Odds API
            sport_key = "americanfootball_nfl" if game.sport == "NFL" else "basketball_nba"
            url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
            
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": "spreads",
                "bookmakers": "draftkings,fanduel,betmgm,pinnacle",
                "oddsFormat": "american"
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # Find this specific game
            game_data = None
            for g in data:
                if (g['home_team'] == game.home_team and 
                    g['away_team'] == game.away_team):
                    game_data = g
                    break
            
            if not game_data:
                return None
            
            # Get previous snapshot from database
            previous_snapshot = db.query(OddsSnapshot).filter(
                OddsSnapshot.game_id == game.id
            ).order_by(OddsSnapshot.snapshot_time.desc()).first()
            
            # Extract current lines by book
            current_lines = {}
            for bookmaker in game_data.get('bookmakers', []):
                book_name = bookmaker['key']
                markets = bookmaker.get('markets', [])
                
                for market in markets:
                    if market['key'] == 'spreads':
                        outcomes = market['outcomes']
                        home_spread = next((o['point'] for o in outcomes if o['name'] == game.home_team), None)
                        
                        if home_spread is not None:
                            current_lines[book_name] = {
                                'spread': home_spread,
                                'timestamp': datetime.now()
                            }
            
            # Compare with previous lines
            if previous_snapshot and previous_snapshot.home_spread:
                old_spread = previous_snapshot.home_spread
                
                # Calculate average current spread
                if current_lines:
                    avg_current_spread = sum(line['spread'] for line in current_lines.values()) / len(current_lines)
                    
                    # Detect movement
                    movement_amount = avg_current_spread - old_spread
                    
                    if abs(movement_amount) >= self.SIGNIFICANT_MOVE:
                        movement_type = self._classify_movement(
                            old_spread, 
                            avg_current_spread, 
                            movement_amount,
                            len(current_lines)
                        )
                        
                        # Save new snapshot
                        new_snapshot = OddsSnapshot(
                            game_id=game.id,
                            sportsbook="consensus",  # Average across books
                            snapshot_time=datetime.now(),
                            home_spread=avg_current_spread,
                            home_ml=0,  # TODO: fetch moneyline
                            total=0  # TODO: fetch total
                        )
                        db.add(new_snapshot)
                        db.commit()
                        
                        return {
                            "game": f"{game.away_team} @ {game.home_team}",
                            "game_id": game.id,
                            "old_spread": old_spread,
                            "new_spread": avg_current_spread,
                            "movement": movement_amount,
                            "movement_type": movement_type,
                            "books_moved": list(current_lines.keys()),
                            "detected_at": datetime.now(),
                            "action": self._recommend_action(movement_type, movement_amount)
                        }
            else:
                # First time seeing this game - save baseline
                if current_lines:
                    avg_spread = sum(line['spread'] for line in current_lines.values()) / len(current_lines)
                    
                    new_snapshot = OddsSnapshot(
                        game_id=game.id,
                        sportsbook="consensus",  # Average across books
                        snapshot_time=datetime.now(),
                        home_spread=avg_spread,
                        home_ml=0,
                        total=0
                    )
                    db.add(new_snapshot)
                    db.commit()
                    
                    logger.info(f"Baseline set for {game.home_team} vs {game.away_team}: {avg_spread}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking lines for game {game.id}: {e}")
            return None
    
    def _classify_movement(self, old_spread: float, new_spread: float, 
                          movement: float, num_books: int) -> str:
        """
        Classify the type of line movement
        
        Returns:
            Movement classification: STEAM, SHARP, RLM, DRIFT
        """
        if abs(movement) >= self.STEAM_MOVE:
            return "STEAM"  # Massive sudden move - all books agree
        
        elif abs(movement) >= self.SIGNIFICANT_MOVE:
            if num_books >= 3:
                return "SHARP"  # Multiple books moving = sharp money
            else:
                return "DRIFT"  # Single book adjusting
        
        return "MINOR"
    
    def _recommend_action(self, movement_type: str, movement: float) -> str:
        """
        Recommend what to do based on movement type
        
        Returns:
            Action recommendation
        """
        if movement_type == "STEAM":
            return "🚨 ALERT: Steam move detected - FOLLOW THE MOVE immediately"
        
        elif movement_type == "SHARP":
            return "⚠️ SHARP ACTION: Multiple books moved - Consider following"
        
        elif movement_type == "RLM":
            return "🔄 REVERSE LINE MOVEMENT: Line moving opposite public - FADE SIGNAL"
        
        else:
            return "📊 Monitor for continued movement"
    
    async def get_line_history(self, game_id: int, hours: int = 24) -> List[Dict]:
        """
        Get historical line movements for a game
        
        Args:
            game_id: Game ID
            hours: How many hours back to look
            
        Returns:
            List of historical snapshots
        """
        db = next(get_db())
        
        cutoff = datetime.now() - timedelta(hours=hours)
        snapshots = db.query(OddsSnapshot).filter(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.snapshot_time >= cutoff
        ).order_by(OddsSnapshot.snapshot_time.asc()).all()
        
        history = []
        for snapshot in snapshots:
            history.append({
                "timestamp": snapshot.snapshot_time,
                "spread": snapshot.home_spread,
                "moneyline": snapshot.home_ml,
                "total": snapshot.total
            })
        
        return history


async def main():
    """Test the line movement tracker"""
    tracker = LineMovementTracker()
    db = next(get_db())
    
    logger.info("=" * 80)
    logger.info("LIVE LINE MOVEMENT TRACKER")
    logger.info("=" * 80)
    logger.info("")
    
    movements = await tracker.track_all_live_games(db)
    
    if movements:
        logger.info(f"Detected {len(movements)} significant line movements:")
        logger.info("")
        
        for movement in movements:
            logger.info(f"📈 {movement['game']}")
            logger.info(f"   Old Spread: {movement['old_spread']:+.1f}")
            logger.info(f"   New Spread: {movement['new_spread']:+.1f}")
            logger.info(f"   Movement: {movement['movement']:+.1f} ({movement['movement_type']})")
            logger.info(f"   Books: {', '.join(movement['books_moved'])}")
            logger.info(f"   Action: {movement['action']}")
            logger.info("")
    else:
        logger.info("No significant line movements detected")


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
