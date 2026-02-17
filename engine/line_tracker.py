"""
Line Tracker
============
Tracks opening lines and calculates line movement over time.

Strategy:
- First odds fetch of the day = "opening lines"
- Subsequent fetches compare current vs opening
- Stores line movement history
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class LineTracker:
    """Track opening lines and line movements."""
    
    def __init__(self, data_dir: str = "data"):
        """
        Args:
            data_dir: Directory for storing line data (default: "data")
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def is_first_fetch_of_day(self, date_str: str) -> bool:
        """
        Check if this is the first odds fetch of the day.
        
        Args:
            date_str: Date string like "20260209"
        
        Returns:
            True if no opening lines exist for this date
        """
        file_path = self.data_dir / f"opening_lines_{date_str}.json"
        return not file_path.exists()
    
    def save_opening_lines(self, date_str: str, odds_data: Dict[str, Any]) -> bool:
        """
        Save opening lines from odds data.
        
        Args:
            date_str: Date string like "20260209"
            odds_data: Raw odds data from Odds API
        
        Returns:
            True if saved successfully
        """
        opening_lines = {}
        
        for game in odds_data.get("games", []):
            game_id = game.get("id")
            home_team = game.get("home_team")
            away_team = game.get("away_team")
            
            # Extract lines from first bookmaker
            bookmakers = game.get("bookmakers", [])
            if not bookmakers:
                continue
            
            markets = bookmakers[0].get("markets", [])
            
            spread = None
            total = None
            
            for market in markets:
                if market.get("key") == "spreads":
                    outcomes = market.get("outcomes", [])
                    for outcome in outcomes:
                        if outcome.get("name") == home_team:
                            spread = outcome.get("point")
                
                if market.get("key") == "totals":
                    outcomes = market.get("outcomes", [])
                    if outcomes:
                        total = outcomes[0].get("point")
            
            opening_lines[game_id] = {
                "home_team": home_team,
                "away_team": away_team,
                "spread": spread,
                "total": total,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        file_path = self.data_dir / f"opening_lines_{date_str}.json"
        
        try:
            with open(file_path, 'w') as f:
                json.dump(opening_lines, f, indent=2)
            logger.info(f"Saved opening lines for {len(opening_lines)} games to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving opening lines: {e}")
            return False
    
    def load_opening_lines(self, date_str: str) -> Dict[str, Any]:
        """
        Load opening lines for a specific date.
        
        Args:
            date_str: Date string like "20260209"
        
        Returns:
            Dict mapping game_id to opening lines
        """
        file_path = self.data_dir / f"opening_lines_{date_str}.json"
        
        if not file_path.exists():
            logger.info(f"No opening lines found for {date_str}")
            return {}
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return {}
    
    def calculate_line_movement(
        self,
        game_id: str,
        current_spread: Optional[float],
        current_total: Optional[float],
        opening_lines: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate line movement for a game.
        
        Args:
            game_id: Game identifier
            current_spread: Current spread (negative = home favored)
            current_total: Current total
            opening_lines: Dict of opening lines by game_id
        
        Returns:
            Dict with line movement data
        """
        opening = opening_lines.get(game_id, {})
        
        if not opening:
            return {
                "spread_movement": None,
                "total_movement": None,
                "has_movement": False
            }
        
        opening_spread = opening.get("spread")
        opening_total = opening.get("total")
        
        spread_movement = None
        total_movement = None
        
        if opening_spread is not None and current_spread is not None:
            spread_movement = current_spread - opening_spread
        
        if opening_total is not None and current_total is not None:
            total_movement = current_total - opening_total
        
        has_movement = (
            (spread_movement is not None and abs(spread_movement) >= 0.5) or
            (total_movement is not None and abs(total_movement) >= 0.5)
        )
        
        return {
            "spread_movement": spread_movement,
            "total_movement": total_movement,
            "opening_spread": opening_spread,
            "opening_total": opening_total,
            "has_movement": has_movement
        }
    
    def save_line_history(
        self,
        date_str: str,
        game_id: str,
        line_data: Dict[str, Any]
    ) -> bool:
        """
        Append line movement to history file.
        
        Args:
            date_str: Date string like "20260209"
            game_id: Game identifier
            line_data: Line data to append
        
        Returns:
            True if saved successfully
        """
        file_path = self.data_dir / f"line_history_{date_str}.json"
        
        # Load existing history
        history = {}
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse existing history file {file_path}")
        
        # Initialize game history if needed
        if game_id not in history:
            history[game_id] = []
        
        # Append new data point
        line_data["timestamp"] = datetime.utcnow().isoformat()
        history[game_id].append(line_data)
        
        # Save
        try:
            with open(file_path, 'w') as f:
                json.dump(history, f, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Error saving line history: {e}")
            return False
    
    def get_line_movement_summary(self, date_str: str) -> str:
        """
        Get a human-readable summary of line movements for the day.
        
        Args:
            date_str: Date string like "20260209"
        
        Returns:
            Formatted summary string
        """
        opening_lines = self.load_opening_lines(date_str)
        
        if not opening_lines:
            return "No line movement data available"
        
        movements = []
        
        # This would need current lines to calculate actual movement
        # For now, just list games with opening lines
        for game_id, data in opening_lines.items():
            home = data.get("home_team", "")
            away = data.get("away_team", "")
            spread = data.get("spread")
            total = data.get("total")
            
            movements.append(f"{away} @ {home}: Spread {spread}, Total {total}")
        
        summary = f"📊 Opening lines saved for {len(opening_lines)} games\n"
        summary += "\n".join(movements[:10])  # First 10 games
        
        return summary
