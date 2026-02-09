#!/usr/bin/env python3
"""
Free ESPN scoreboard watcher → publishes live scores to Redis Pub/Sub (and prints to console)
Targets men's college basketball by default.
"""
import os
import sys
import time
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from dotenv import load_dotenv
from loguru import logger

# Allow relative imports if needed
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Optional Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available; will only log to console")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (score-publisher)",
    "Accept": "application/json",
}


class ESPNScorePublisher:
    def __init__(self, poll_interval: int = 20, date_str: Optional[str] = None):
        self.poll_interval = poll_interval
        # ESPN expects YYYYMMDD (no dashes). Accept either and normalize.
        raw_date = date_str or datetime.now().strftime("%Y-%m-%d")
        self.date_str = raw_date.replace("-", "")
        self.client = httpx.Client(timeout=15, headers=HEADERS)

        self.redis_client = None
        self.redis_channel = os.getenv("REDIS_CHANNEL", "events")
        if REDIS_AVAILABLE and os.getenv("REDIS_HOST"):
            try:
                self.redis_client = redis.Redis(
                    host=os.getenv("REDIS_HOST", "localhost"),
                    port=int(os.getenv("REDIS_PORT", 6379)),
                    decode_responses=True,
                )
                self.redis_client.ping()
                logger.info("✅ Connected to Redis for score pub-sub")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self.redis_client = None

    def _scoreboard_url(self) -> str:
        # ESPN scoreboard endpoint for NCAAB uses the 'site' v2 path and group=50
        base = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
        return f"{base}?dates={self.date_str}&groups=50&limit=400"

    def fetch_scores(self) -> Dict[str, Any]:
        try:
            resp = self.client.get(self._scoreboard_url())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"ESPN HTTP error {e.response.status_code}: {e}")
        except Exception as e:
            logger.error(f"Fetch error: {e}")
        return {}

    @staticmethod
    def _extract_team(raw: Dict[str, Any]) -> Dict[str, Any]:
        team = raw.get("team", {})
        return {
            "id": raw.get("id"),
            "name": team.get("displayName"),
            "abbr": team.get("abbreviation"),
            "score": raw.get("score"),
            "rank": team.get("rank"),
            "homeAway": raw.get("homeAway"),
        }

    @staticmethod
    def _extract_status(raw: Dict[str, Any]) -> Dict[str, Any]:
        st = raw.get("status", {}).get("type", {})
        return {
            "state": st.get("state"),
            "detail": st.get("detail"),
            "shortDetail": st.get("shortDetail"),
            "period": raw.get("status", {}).get("period"),
            "clock": raw.get("status", {}).get("displayClock"),
        }

    def normalize_events(self, data: Dict[str, Any]):
        events = []
        for event in data.get("events", []):
            comp = event.get("competitions", [{}])[0]
            teams = comp.get("competitors", [])
            if len(teams) < 2:
                continue
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[0])
            home = next((t for t in teams if t.get("homeAway") == "home"), teams[-1])
            events.append(
                {
                    "type": "score_update",
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "espn_scoreboard",
                    "league": "ncaab",
                    "game_id": event.get("id"),
                    "short_name": event.get("shortName"),
                    "status": self._extract_status(event),
                    "away": self._extract_team(away),
                    "home": self._extract_team(home),
                }
            )
        return events

    def publish(self, evt: Dict[str, Any]):
        if self.redis_client:
            try:
                self.redis_client.publish(self.redis_channel, json.dumps(evt))
            except Exception as e:
                logger.warning(f"Redis publish failed: {e}")
        # Console fallback
        st = evt.get("status", {})
        clock = st.get("clock") or ""
        period = st.get("period")
        state = st.get("state")
        away = evt.get("away", {})
        home = evt.get("home", {})
        logger.info(
            f"[{state} P{period} {clock}] {away.get('abbr')} {away.get('score')} - {home.get('abbr')} {home.get('score')} ({evt.get('short_name')})"
        )

    def run(self):
        logger.info("=" * 80)
        logger.info(
            f"📡 ESPN Score Publisher | date={self.date_str} | poll={self.poll_interval}s | channel={self.redis_channel}"
        )
        logger.info("=" * 80)
        while True:
            data = self.fetch_scores()
            events = self.normalize_events(data)
            for evt in events:
                self.publish(evt)
            time.sleep(self.poll_interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=20, help="Poll interval seconds")
    ap.add_argument("--date", type=str, default=None, help="Date YYYY-MM-DD (defaults to today)")
    args = ap.parse_args()

    publisher = ESPNScorePublisher(poll_interval=args.poll, date_str=args.date)
    try:
        publisher.run()
    except KeyboardInterrupt:
        logger.info("\n⏹️  Stopped by user")


if __name__ == "__main__":
    main()
