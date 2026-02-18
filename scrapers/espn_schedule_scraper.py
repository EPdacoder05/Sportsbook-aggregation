"""
ESPN Schedule Scraper
=====================
Dynamic schedule puller using ESPN's free site API.
Fetches NCAAB and NCAAW schedules without requiring API keys.

Endpoints:
- NCAAB: https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard
- NCAAW: https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard
"""

import httpx
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ESPNScheduleScraper:
    """Pull NCAAB + NCAAW schedules dynamically from ESPN site API."""

    ENDPOINTS = {
        "NCAAB": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
        "NCAAW": "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard",
    }

    def __init__(self):
        """Initialize scraper."""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"  # noqa: E501
        }

    async def get_todays_games(self, sport: str = "NCAAB", date: str = None) -> List[dict]:
        """
        Fetch today's schedule from ESPN.

        Args:
            sport: "NCAAB" or "NCAAW"
            date: Optional date in YYYYMMDD format (default: today)

        Returns:
            List of game dictionaries with schedule info
        """
        if sport not in self.ENDPOINTS:
            logger.error(f"Invalid sport: {sport}. Must be NCAAB or NCAAW")
            return []

        url = self.ENDPOINTS[sport]

        # Add date parameter if provided
        params = {}
        if date:
            params["dates"] = date

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

            games = []
            for event in data.get("events", []):
                game = self._parse_event(event, sport)
                if game:
                    games.append(game)

            logger.info(f"Fetched {len(games)} {sport} games")
            return games

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {sport} schedule: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching {sport} schedule: {e}")
            return []

    def _parse_event(self, event: dict, sport: str) -> Dict[str, Any]:
        """
        Parse ESPN event into standardized game dict.

        Args:
            event: Raw event data from ESPN
            sport: Sport code

        Returns:
            Standardized game dictionary
        """
        try:
            competitions = event.get("competitions", [])
            if not competitions:
                return {}

            comp = competitions[0]
            competitors = comp.get("competitors", [])

            if len(competitors) < 2:
                return {}

            # Determine home/away (ESPN lists home first)
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            # Parse status
            status_obj = comp.get("status", {})
            status_type = status_obj.get("type", {})
            if isinstance(status_type, dict):
                status = status_type.get("description", "Scheduled")
                state = status_type.get("state", "pre")
            else:
                state = status_type
                status = "Scheduled"

            # Map state to readable status
            status_map = {
                "pre": "Scheduled",
                "in": "In Progress",
                "post": "Final"
            }
            status = status_map.get(state, status)

            # Parse start time
            date_str = event.get("date", "")
            start_time = None
            start_time_est = ""
            if date_str:
                try:
                    start_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    # Convert to EST
                    est_time = start_time - timedelta(hours=5)
                    start_time_est = est_time.strftime("%I:%M %p ET")
                except Exception:
                    pass

            # Rankings
            home_rank = home.get("curatedRank", {}).get("current") if "curatedRank" in home else None
            away_rank = away.get("curatedRank", {}).get("current") if "curatedRank" in away else None

            # Network/venue
            broadcasts = comp.get("broadcasts", [])
            network = broadcasts[0].get("names", [""])[0] if broadcasts else ""

            venue = comp.get("venue", {})
            venue_name = venue.get("fullName", "")

            return {
                "game_id": event.get("id", ""),
                "home_team": home.get("team", {}).get("displayName", "Unknown"),
                "away_team": away.get("team", {}).get("displayName", "Unknown"),
                "start_time": start_time,
                "start_time_est": start_time_est,
                "home_rank": home_rank,
                "away_rank": away_rank,
                "network": network,
                "venue": venue_name,
                "status": status,
                "sport": sport
            }

        except Exception as e:
            logger.error(f"Error parsing event: {e}")
            return {}

    async def get_live_scores(self, sport: str = "NCAAB") -> List[dict]:
        """
        Fetch live game data with scores, period, clock, etc.

        Args:
            sport: "NCAAB" or "NCAAW"

        Returns:
            List of GameScore-compatible dicts
        """
        if sport not in self.ENDPOINTS:
            logger.error(f"Invalid sport: {sport}")
            return []

        url = self.ENDPOINTS[sport]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

            games = []
            for event in data.get("events", []):
                game = self._parse_live_game(event, sport)
                if game:
                    games.append(game)

            logger.info(f"Fetched {len(games)} live {sport} games")
            return games

        except Exception as e:
            logger.error(f"Error fetching live {sport} scores: {e}")
            return []

    def _parse_live_game(self, event: dict, sport: str) -> Dict[str, Any]:
        """
        Parse live game data into GameScore-compatible format.

        Args:
            event: Raw event data
            sport: Sport code

        Returns:
            GameScore-compatible dictionary
        """
        try:
            competitions = event.get("competitions", [])
            if not competitions:
                return {}

            comp = competitions[0]
            competitors = comp.get("competitors", [])

            if len(competitors) < 2:
                return {}

            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            # Status
            status_obj = comp.get("status", {})
            status_type = status_obj.get("type", {})
            if isinstance(status_type, dict):
                status = status_type.get("description", "Scheduled")
            else:
                status = "Scheduled"

            return {
                "game_id": event.get("id", ""),
                "home_team": home.get("team", {}).get("displayName", "Unknown"),
                "away_team": away.get("team", {}).get("displayName", "Unknown"),
                "home_score": int(home.get("score", 0)),
                "away_score": int(away.get("score", 0)),
                "status": status,
                "sport": sport,
                "last_update": datetime.now().isoformat(timespec='seconds'),
            }

        except Exception as e:
            logger.error(f"Error parsing live game: {e}")
            return {}

    def format_schedule_table(self, games: List[dict]) -> str:
        """
        Format games into a clean markdown table grouped by time slot.

        Args:
            games: List of game dictionaries

        Returns:
            Markdown formatted table
        """
        if not games:
            return "No games found."

        # Group by time slot
        time_groups: Dict[str, List[dict]] = {}
        for game in games:
            time_slot = game.get("start_time_est", "Unknown")
            if time_slot not in time_groups:
                time_groups[time_slot] = []
            time_groups[time_slot].append(game)

        # Build table
        output = []
        output.append("## Schedule")
        output.append("")

        for time_slot in sorted(time_groups.keys()):
            output.append(f"### {time_slot}")
            output.append("")
            output.append("| Away | Home | Network | Venue |")
            output.append("|------|------|---------|-------|")

            for game in time_groups[time_slot]:
                away_team = game["away_team"]
                home_team = game["home_team"]
                network = game.get("network", "")
                venue = game.get("venue", "")

                # Add rankings if available
                if game.get("away_rank"):
                    away_team = f"#{game['away_rank']} {away_team}"
                if game.get("home_rank"):
                    home_team = f"#{game['home_rank']} {home_team}"

                output.append(f"| {away_team} | {home_team} | {network} | {venue} |")

            output.append("")

        return "\n".join(output)
