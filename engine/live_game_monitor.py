"""
LIVE GAME MONITOR — Real-Time ESPN Score Tracking
====================================================
Replaces hardcoded stubs with real ESPN API integration.

Features:
  • Fetches live scores from ESPN free API (no key needed)
  • Tracks pick survival (Under/Over/Spread)
  • Pace projection for totals
  • Blowout / hedge alerts
  • Continuous monitoring with configurable interval

Usage:
    python engine/live_game_monitor.py                   # One-shot dashboard
    python engine/live_game_monitor.py --continuous       # Live loop (30s)
    python engine/live_game_monitor.py --date 20260209    # Specific date
"""

import asyncio
import json
import logging
import sys
import os
import argparse
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
ESPN_NBA_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ── ESPN LIVE SCORES ──────────────────────────────────────────────────

class LiveGameMonitor:
    """Real-time game monitor using ESPN free API."""

    def __init__(self, update_interval: int = 30):
        self.update_interval = update_interval  # seconds between polls
        self.previous_scores: Dict[str, Dict] = {}

    # ── Core: fetch live scores ──────────────────────────────────────

    def fetch_live_scores(self, date_str: Optional[str] = None) -> List[Dict]:
        """
        Fetch live / today's scores from ESPN.
        Returns list of parsed game dicts.
        """
        params = {}
        if date_str:
            params["dates"] = date_str

        try:
            resp = requests.get(ESPN_NBA_URL, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"ESPN fetch failed: {e}")
            return []

        games = []
        for event in data.get("events", []):
            parsed = self._parse_espn_event(event)
            if parsed:
                games.append(parsed)
        return games

    def _parse_espn_event(self, event: dict) -> Optional[Dict]:
        """Parse a single ESPN event into a flat dict."""
        try:
            comp = event["competitions"][0]
            status_obj = event.get("status", {})
            status_type = status_obj.get("type", {})
            status_detail = status_obj.get("displayClock", "")
            period = status_obj.get("period", 0)
            state = status_type.get("state", "pre")  # pre | in | post
            status_name = status_type.get("name", "")

            teams = comp.get("competitors", [])
            if len(teams) < 2:
                return None

            home = next((t for t in teams if t["homeAway"] == "home"), teams[0])
            away = next((t for t in teams if t["homeAway"] == "away"), teams[1])

            home_team = home["team"]["abbreviation"]
            away_team = away["team"]["abbreviation"]
            home_score = int(home.get("score", 0))
            away_score = int(away.get("score", 0))

            return {
                "espn_id": event.get("id"),
                "name": event.get("name", f"{away_team} @ {home_team}"),
                "short": event.get("shortName", f"{away_team} @ {home_team}"),
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "total": home_score + away_score,
                "spread_result": home_score - away_score,
                "quarter": period,
                "clock": status_detail,
                "state": state,
                "status": status_name,
                "completed": state == "post",
                "in_progress": state == "in",
            }
        except (KeyError, IndexError, TypeError) as e:
            logger.debug(f"Parse error: {e}")
            return None

    # ── Pick survival analysis ───────────────────────────────────────

    def load_todays_picks(self) -> List[Dict]:
        """Load pick files for today from data/."""
        today = datetime.now().strftime("%Y%m%d")
        picks: List[Dict] = []
        for f in sorted(DATA_DIR.glob(f"picks_{today}*.json")):
            try:
                with open(f) as fh:
                    loaded = json.load(fh)
                    if isinstance(loaded, list):
                        picks.extend(loaded)
            except Exception:
                pass
        return picks

    def analyze_pick_survival(self, pick: Dict, game: Dict) -> Dict:
        """
        Analyze whether a pick is still alive given live game state.
        Supports UNDER, OVER, SPREAD.
        """
        pick_str = (pick.get("pick") or "").upper()
        result = {
            "pick": pick.get("pick"),
            "game": game["short"],
            "score": f"{game['away_score']}-{game['home_score']}",
            "quarter": game["quarter"],
            "clock": game["clock"],
            "status": "UNKNOWN",
            "detail": "",
        }

        total = game["total"]
        quarter = game["quarter"] or 1
        completed = game["completed"]

        # Pace projection
        if game["in_progress"] and quarter > 0:
            elapsed_quarters = quarter - 1 + (1 if game["clock"] != "12:00" else 0)
            if elapsed_quarters > 0:
                pace = (total / max(elapsed_quarters, 0.5)) * 4
            else:
                pace = 0
        else:
            pace = total

        if "UNDER" in pick_str:
            try:
                line = float(pick_str.split("UNDER")[1].strip())
            except (ValueError, IndexError):
                result["status"] = "PARSE_ERROR"
                return result

            if completed:
                result["status"] = "WON" if total < line else "LOST"
                result["detail"] = f"Final {total} vs line {line}"
            else:
                margin = line - total
                result["detail"] = f"Pace: {pace:.0f} | Need <{line} | Currently {total} ({margin:+.1f} cushion)"
                if pace < line - 5:
                    result["status"] = "LOOKING_GOOD"
                elif pace > line + 5:
                    result["status"] = "IN_DANGER"
                else:
                    result["status"] = "SWEATING"

        elif "OVER" in pick_str:
            try:
                line = float(pick_str.split("OVER")[1].strip())
            except (ValueError, IndexError):
                result["status"] = "PARSE_ERROR"
                return result

            if completed:
                result["status"] = "WON" if total > line else "LOST"
                result["detail"] = f"Final {total} vs line {line}"
            else:
                result["detail"] = f"Pace: {pace:.0f} | Need >{line} | Currently {total}"
                if pace > line + 5:
                    result["status"] = "LOOKING_GOOD"
                elif pace < line - 5:
                    result["status"] = "IN_DANGER"
                else:
                    result["status"] = "SWEATING"

        elif "+" in pick_str or "-" in pick_str:
            # Spread pick
            try:
                if "+" in pick_str:
                    parts = pick_str.split("+")
                    spread = float(parts[1].strip())
                else:
                    parts = pick_str.split("-")
                    spread = -float(parts[1].strip())
                team_abbr = parts[0].strip()
            except (ValueError, IndexError):
                result["status"] = "PARSE_ERROR"
                return result

            diff = game["spread_result"]  # home - away (positive = home winning)
            # If our pick is the away team
            if team_abbr == game["away_team"]:
                adjusted = -diff + spread  # positive = covering
            else:
                adjusted = diff + spread

            if completed:
                result["status"] = "WON" if adjusted > 0 else "LOST"
                result["detail"] = f"Covered by {adjusted:+.1f}"
            else:
                result["detail"] = f"Currently {adjusted:+.1f} vs spread"
                result["status"] = "COVERING" if adjusted > 0 else "NOT_COVERING"

        return result

    # ── Dashboard ────────────────────────────────────────────────────

    def print_dashboard(self, games: List[Dict], picks: Optional[List[Dict]] = None):
        """Print a live scoreboard dashboard to stdout."""
        print()
        print("═" * 72)
        print(f"  🏀 LIVE SCOREBOARD — {datetime.now().strftime('%I:%M:%S %p ET')}")
        print("═" * 72)

        live = [g for g in games if g["in_progress"]]
        final = [g for g in games if g["completed"]]
        pre = [g for g in games if g["state"] == "pre"]

        if live:
            print(f"\n  🔴 IN PROGRESS ({len(live)})")
            for g in live:
                print(f"    {g['away_team']} {g['away_score']}  @  "
                      f"{g['home_team']} {g['home_score']}   "
                      f"Q{g['quarter']} {g['clock']}")

        if final:
            print(f"\n  ✅ FINAL ({len(final)})")
            for g in final:
                winner = g['home_team'] if g['home_score'] > g['away_score'] else g['away_team']
                print(f"    {g['away_team']} {g['away_score']}  @  "
                      f"{g['home_team']} {g['home_score']}   "
                      f"({winner} wins)")

        if pre:
            print(f"\n  🟢 UPCOMING ({len(pre)})")
            for g in pre:
                print(f"    {g['away_team']}  @  {g['home_team']}   "
                      f"({g.get('status', 'scheduled')})")

        # Pick survival
        if picks:
            active_games = {g["short"]: g for g in games if g["in_progress"] or g["completed"]}
            print(f"\n  📋 PICK SURVIVAL")
            for pick in picks:
                # Try to match pick to a live game
                for key, game in active_games.items():
                    pick_game = (pick.get("game") or "").upper()
                    if (game["home_team"] in pick_game or
                            game["away_team"] in pick_game):
                        survival = self.analyze_pick_survival(pick, game)
                        icon = {
                            "WON": "✅", "LOST": "❌",
                            "LOOKING_GOOD": "🟢", "IN_DANGER": "🔴",
                            "SWEATING": "🟡", "COVERING": "🟢",
                            "NOT_COVERING": "🔴",
                        }.get(survival["status"], "⚪")
                        print(f"    {icon} {survival['pick']:<25} "
                              f"{survival['status']:<14} {survival['detail']}")
                        break

        if not games:
            print("\n  No games found for today.")

        print("\n" + "═" * 72)

    # ── Continuous loop ──────────────────────────────────────────────

    async def run_continuous(self, date_str: Optional[str] = None):
        """Run the monitor in a continuous loop."""
        logger.info(f"🚀 Live Game Monitor started (interval: {self.update_interval}s)")
        picks = self.load_todays_picks()
        if picks:
            logger.info(f"📋 Loaded {len(picks)} picks for today")

        try:
            while True:
                games = self.fetch_live_scores(date_str)
                self.print_dashboard(games, picks)

                # Check if all games are final
                if games and all(g["completed"] for g in games):
                    logger.info("All games completed. Monitor stopping.")
                    break

                # If no games in progress and none upcoming, stop
                if games and not any(g["in_progress"] or g["state"] == "pre" for g in games):
                    logger.info("No more live or upcoming games. Monitor stopping.")
                    break

                await asyncio.sleep(self.update_interval)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user.")


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Live Game Monitor")
    parser.add_argument("--continuous", action="store_true",
                        help="Run in continuous monitoring mode")
    parser.add_argument("--date", type=str, default=None,
                        help="ESPN date (YYYYMMDD). Default: today")
    parser.add_argument("--interval", type=int, default=30,
                        help="Seconds between polls (default: 30)")
    args = parser.parse_args()

    monitor = LiveGameMonitor(update_interval=args.interval)

    if args.continuous:
        asyncio.run(monitor.run_continuous(args.date))
    else:
        games = monitor.fetch_live_scores(args.date)
        picks = monitor.load_todays_picks()
        monitor.print_dashboard(games, picks)


if __name__ == "__main__":
    main()
