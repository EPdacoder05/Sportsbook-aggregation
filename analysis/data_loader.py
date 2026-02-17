"""
Data Loader
===========
Loads and merges data from various sources:
- Odds API data (odds_window_*.json)
- Opening lines (opening_lines_*.json)
- Public betting splits (public_splits.json) - manual for now
- Covers consensus (covers_consensus.json) - manual for now
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    """Load and merge betting data from multiple sources."""
    
    def __init__(self, data_dir: str = "data"):
        """
        Args:
            data_dir: Directory containing data files (default: "data")
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def load_odds_window(self, window_file: str) -> Optional[Dict[str, Any]]:
        """
        Load odds data from a window file.
        
        Args:
            window_file: Filename like "odds_window_7pm_20260209.json"
        
        Returns:
            Dict with odds data or None if not found
        """
        file_path = self.data_dir / window_file
        
        if not file_path.exists():
            logger.warning(f"Odds window file not found: {file_path}")
            return None
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None
    
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
            logger.info(f"No opening lines file found for {date_str}")
            return {}
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return {}
    
    def save_opening_lines(self, date_str: str, opening_lines: Dict[str, Any]) -> bool:
        """
        Save opening lines for a specific date.
        
        Args:
            date_str: Date string like "20260209"
            opening_lines: Dict mapping game_id to opening line data
        
        Returns:
            True if saved successfully
        """
        file_path = self.data_dir / f"opening_lines_{date_str}.json"
        
        try:
            with open(file_path, 'w') as f:
                json.dump(opening_lines, f, indent=2, default=str)
            logger.info(f"Saved opening lines to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving opening lines: {e}")
            return False
    
    def load_public_splits(self) -> Dict[str, Any]:
        """
        Load public betting splits (manual input for now).
        
        Returns:
            Dict mapping game_id to public betting percentages
        """
        file_path = self.data_dir / "public_splits.json"
        
        if not file_path.exists():
            logger.info("No public splits file found, using defaults")
            return {}
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return {}
    
    def merge_game_data(
        self,
        odds_data: Dict[str, Any],
        opening_lines: Dict[str, Any],
        public_splits: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Merge odds, opening lines, and public splits into unified game data.
        
        Args:
            odds_data: Raw odds data from Odds API
            opening_lines: Opening line data
            public_splits: Public betting percentages
        
        Returns:
            List of unified game data dictionaries
        """
        if not odds_data or "games" not in odds_data:
            logger.warning("No games found in odds data")
            return []
        
        games = []
        
        for game in odds_data.get("games", []):
            game_id = game.get("id")
            home_team = game.get("home_team", "")
            away_team = game.get("away_team", "")
            
            # Get current odds
            bookmakers = game.get("bookmakers", [])
            current_spread = None
            current_total = None
            
            # Use first bookmaker with data (could be enhanced to find consensus)
            if bookmakers:
                markets = bookmakers[0].get("markets", [])
                for market in markets:
                    if market.get("key") == "spreads":
                        outcomes = market.get("outcomes", [])
                        for outcome in outcomes:
                            if outcome.get("name") == home_team:
                                current_spread = outcome.get("point")
                    
                    if market.get("key") == "totals":
                        outcomes = market.get("outcomes", [])
                        if outcomes:
                            current_total = outcomes[0].get("point")
            
            # Get opening lines
            opening_data = opening_lines.get(game_id, {})
            opening_spread = opening_data.get("spread")
            opening_total = opening_data.get("total")
            
            # Get public splits
            public_data = public_splits.get(game_id, {})
            public_pct_home = public_data.get("spread", {}).get("home", 0.5)
            public_pct_over = public_data.get("total", {}).get("over", 0.5)
            public_pct_home_ml = public_data.get("ml", {}).get("home", 0.5)
            public_pct_home_spread = public_data.get("spread", {}).get("home", 0.5)
            
            # Get ATS records
            home_ats_l10 = public_data.get("ats", {}).get("home", "")
            away_ats_l10 = public_data.get("ats", {}).get("away", "")
            
            # Build unified game data
            unified = {
                "game_id": game_id,
                "home_team": home_team,
                "away_team": away_team,
                "commence_time": game.get("commence_time"),
                "current_spread": current_spread,
                "current_total": current_total,
                "opening_spread": opening_spread,
                "opening_total": opening_total,
                "public_pct_home": public_pct_home,
                "public_pct_over": public_pct_over,
                "public_pct_home_ml": public_pct_home_ml,
                "public_pct_home_spread": public_pct_home_spread,
                "home_ats_l10": home_ats_l10,
                "away_ats_l10": away_ats_l10,
                "bookmakers": bookmakers,  # Keep full bookmaker data for best line finding
            }
            
            games.append(unified)
        
        logger.info(f"Merged data for {len(games)} games")
        return games
    
    def find_best_line(self, game_data: Dict[str, Any], market: str, side: str) -> Optional[Dict[str, Any]]:
        """
        Find the best line across all bookmakers for a specific bet.
        
        Args:
            game_data: Unified game data
            market: Market type ("spreads" or "totals")
            side: Side to bet ("home", "away", "over", "under")
        
        Returns:
            Dict with best_line, best_odds, bookmaker or None
        """
        bookmakers = game_data.get("bookmakers", [])
        
        if not bookmakers:
            return None
        
        best = None
        
        for bookmaker in bookmakers:
            book_name = bookmaker.get("title", "Unknown")
            markets = bookmaker.get("markets", [])
            
            for mkt in markets:
                if mkt.get("key") != market:
                    continue
                
                outcomes = mkt.get("outcomes", [])
                
                for outcome in outcomes:
                    outcome_name = outcome.get("name", "").lower()
                    outcome_point = outcome.get("point")
                    outcome_price = outcome.get("price")
                    
                    # Match side
                    if market == "spreads":
                        home_team = game_data.get("home_team", "").lower()
                        away_team = game_data.get("away_team", "").lower()
                        
                        if side == "home" and outcome_name == home_team:
                            if best is None or outcome_price > best["odds"]:
                                best = {
                                    "line": outcome_point,
                                    "odds": outcome_price,
                                    "bookmaker": book_name,
                                    "american_odds": self._decimal_to_american(outcome_price)
                                }
                        
                        elif side == "away" and outcome_name == away_team:
                            if best is None or outcome_price > best["odds"]:
                                best = {
                                    "line": outcome_point,
                                    "odds": outcome_price,
                                    "bookmaker": book_name,
                                    "american_odds": self._decimal_to_american(outcome_price)
                                }
                    
                    elif market == "totals":
                        if side == "over" and outcome_name == "over":
                            if best is None or outcome_price > best["odds"]:
                                best = {
                                    "line": outcome_point,
                                    "odds": outcome_price,
                                    "bookmaker": book_name,
                                    "american_odds": self._decimal_to_american(outcome_price)
                                }
                        
                        elif side == "under" and outcome_name == "under":
                            if best is None or outcome_price > best["odds"]:
                                best = {
                                    "line": outcome_point,
                                    "odds": outcome_price,
                                    "bookmaker": book_name,
                                    "american_odds": self._decimal_to_american(outcome_price)
                                }
        
        return best
    
    def _decimal_to_american(self, decimal_odds: float) -> int:
        """
        Convert decimal odds to American odds.
        
        Args:
            decimal_odds: Decimal odds (e.g., 1.91)
        
        Returns:
            American odds (e.g., -110)
        """
        if decimal_odds >= 2.0:
            return int((decimal_odds - 1) * 100)
        else:
            return int(-100 / (decimal_odds - 1))
