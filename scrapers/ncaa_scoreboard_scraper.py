"""
NCAA Scoreboard Scraper
=======================
Fallback scraper using NCAA.com when ESPN is rate-limited.
Uses NCAA.com's JSON API for NCAAB and NCAAW live scores.

Endpoints:
- NCAAB: https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/{date}/scoreboard.json
- NCAAW: https://data.ncaa.com/casablanca/scoreboard/basketball-women/d1/{date}/scoreboard.json
"""

import httpx
from typing import List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class NCAAScoreboardScraper:
    """Fallback scraper using NCAA.com when ESPN is rate-limited."""

    BASE_URL = "https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/{date}/scoreboard.json"
    WOMENS_URL = "https://data.ncaa.com/casablanca/scoreboard/basketball-women/d1/{date}/scoreboard.json"

    def __init__(self):
        """Initialize scraper."""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def get_scoreboard(self, sport: str = "NCAAB", date: str = None) -> List[dict]:
        """
        Fetch scoreboard from NCAA.com.

        Args:
            sport: "NCAAB" or "NCAAW"
            date: Date in YYYYMMDD format (default: today)

        Returns:
            List of game dictionaries
        """
        if not date:
            date = datetime.now().strftime("%Y%m%d")

        # Select URL based on sport
        if sport == "NCAAW":
            url = self.WOMENS_URL.format(date=date)
        else:
            url = self.BASE_URL.format(date=date)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

            games = []
            for game_data in data.get("games", []):
                game = self._parse_game(game_data, sport)
                if game:
                    games.append(game)

            logger.info(f"Fetched {len(games)} {sport} games from NCAA.com")
            return games

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching NCAA {sport} scoreboard: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching NCAA {sport} scoreboard: {e}")
            return []

    def _parse_game(self, game_data: dict, sport: str) -> Dict[str, Any]:
        """
        Parse NCAA game data into standardized format.

        Args:
            game_data: Raw game data from NCAA.com
            sport: Sport code

        Returns:
            Standardized game dictionary
        """
        try:
            game_obj = game_data.get("game", {})
            home = game_obj.get("home", {})
            away = game_obj.get("away", {})

            # Parse status
            game_state = game_obj.get("gameState", "pre")
            status_map = {
                "pre": "Scheduled",
                "live": "In Progress",
                "final": "Final"
            }
            status = status_map.get(game_state, "Scheduled")

            # Parse start time
            start_date = game_obj.get("startDate", "")
            start_time_gmt = game_obj.get("startTimeGMT", "")
            start_time = None
            start_time_est = ""

            if start_date and start_time_gmt:
                try:
                    dt_str = f"{start_date}T{start_time_gmt}"
                    start_time = datetime.fromisoformat(dt_str)
                    start_time_est = start_time.strftime("%I:%M %p ET")
                except Exception:
                    pass

            return {
                "game_id": game_obj.get("gameID", ""),
                "home_team": home.get("names", {}).get("full", "Unknown"),
                "away_team": away.get("names", {}).get("full", "Unknown"),
                "home_score": int(home.get("score", 0)),
                "away_score": int(away.get("score", 0)),
                "start_time": start_time,
                "start_time_est": start_time_est,
                "status": status,
                "sport": sport,
                "venue": game_obj.get("location", ""),
                "network": game_obj.get("network", "")
            }

        except Exception as e:
            logger.error(f"Error parsing NCAA game: {e}")
            return {}

    async def get_live_game(self, game_id: str) -> dict:
        """
        Fetch detailed live game data for a specific game.

        Args:
            game_id: NCAA game ID

        Returns:
            Detailed game dictionary
        """
        # NCAA.com doesn't have a direct game endpoint in the same way
        # This would need to query the scoreboard and filter
        logger.warning("get_live_game not fully implemented for NCAA.com scraper")
        return {}
