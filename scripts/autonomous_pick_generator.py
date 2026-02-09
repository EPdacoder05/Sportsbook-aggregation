#!/usr/bin/env python3
"""
Autonomous Pick Generator
Continuously monitors live games, calculates picks, publishes to Redis/EventBus
Zero manual input required — fully autonomous and resilient
"""
import os
import sys
import time
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict

import httpx
from dotenv import load_dotenv
from loguru import logger

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (autonomous-pick-gen)",
    "Accept": "application/json",
}

# Hard-coded fade thresholds
PUBLIC_FADE_THRESHOLD = 75  # Fade if >75% public on one side
RLM_THRESHOLD = 1.5  # Fade if line moved >1.5pts against heavy public


class AutonomousPickGenerator:
    def __init__(self, poll_interval: int = 30):
        self.poll_interval = poll_interval
        self.client = httpx.Client(timeout=15, headers=HEADERS)
        
        # Redis setup
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
                logger.info("✅ Connected to Redis for pick pub-sub")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self.redis_client = None
        
        # Track games to avoid duplicate picks
        self.processed_games = set()
        self.line_history = defaultdict(list)  # game_id -> [line, line, ...]

    def fetch_espn_games(self) -> List[Dict[str, Any]]:
        """Fetch live/upcoming games from ESPN NCAAB"""
        date_str = datetime.now().strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={date_str}&groups=50&limit=400"
        
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("events", [])
        except Exception as e:
            logger.error(f"ESPN fetch failed: {e}")
            return []

    def extract_game_info(self, event: Dict) -> Optional[Dict[str, Any]]:
        """Extract relevant game info from ESPN event"""
        try:
            comp = event.get("competitions", [{}])[0]
            teams = comp.get("competitors", [])
            if len(teams) < 2:
                return None
            
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[0])
            home = next((t for t in teams if t.get("homeAway") == "home"), teams[-1])
            
            status = event.get("status", {}).get("type", {})
            return {
                "game_id": event.get("id"),
                "short_name": event.get("shortName"),
                "away_team": away.get("team", {}).get("abbreviation", "?"),
                "home_team": home.get("team", {}).get("abbreviation", "?"),
                "away_score": away.get("score"),
                "home_score": home.get("score"),
                "state": status.get("state"),
                "period": event.get("status", {}).get("period"),
                "clock": event.get("status", {}).get("displayClock"),
            }
        except Exception as e:
            logger.warning(f"Extract game info failed: {e}")
            return None

    def fetch_betting_data(self, away: str, home: str) -> Optional[Dict[str, Any]]:
        """Fetch public betting %'s and lines (ESPN free endpoint)"""
        try:
            # For now, use ESPN betting data if available
            # In production, you'd scrape Covers/Reddit/Twitter
            return {
                "away_ml_pct": None,  # Placeholder
                "home_ml_pct": None,
                "away_spread_pct": None,
                "home_spread_pct": None,
                "current_spread": None,
                "opening_spread": None,
            }
        except Exception as e:
            logger.warning(f"Fetch betting data failed: {e}")
            return None

    def calculate_fade_score(self, game: Dict, bet_data: Dict) -> Optional[Dict[str, Any]]:
        """Calculate if game meets fade criteria"""
        # Simple logic: if public is >75% on one side, it's a potential fade
        ml_pcts = [bet_data.get("away_ml_pct"), bet_data.get("home_ml_pct")]
        spread_pcts = [bet_data.get("away_spread_pct"), bet_data.get("home_spread_pct")]
        
        # Check if public is heavily skewed
        if ml_pcts[0] and ml_pcts[0] > PUBLIC_FADE_THRESHOLD:
            # Heavy on away ML → fade away, take home
            return {
                "type": "fade_ml",
                "side": "home",
                "confidence": "high",
                "reason": f"ML: {ml_pcts[0]:.0f}% public on away",
                "size": "2u",
            }
        elif ml_pcts[1] and ml_pcts[1] > PUBLIC_FADE_THRESHOLD:
            # Heavy on home ML → fade home, take away
            return {
                "type": "fade_ml",
                "side": "away",
                "confidence": "high",
                "reason": f"ML: {ml_pcts[1]:.0f}% public on home",
                "size": "2u",
            }
        
        if spread_pcts[0] and spread_pcts[0] > PUBLIC_FADE_THRESHOLD:
            return {
                "type": "fade_spread",
                "side": "home_spread",
                "confidence": "medium",
                "reason": f"Spread: {spread_pcts[0]:.0f}% public on away spread",
                "size": "1.5u",
            }
        elif spread_pcts[1] and spread_pcts[1] > PUBLIC_FADE_THRESHOLD:
            return {
                "type": "fade_spread",
                "side": "away_spread",
                "confidence": "medium",
                "reason": f"Spread: {spread_pcts[1]:.0f}% public on home spread",
                "size": "1.5u",
            }
        
        return None

    def generate_pick(self, game: Dict, fade_signal: Dict) -> Dict[str, Any]:
        """Generate a pick from game + fade signal"""
        return {
            "type": "pick",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "autonomous_generator",
            "league": "ncaab",
            "game_id": game.get("game_id"),
            "matchup": f"{game.get('away_team')} @ {game.get('home_team')}",
            "away_team": game.get("away_team"),
            "home_team": game.get("home_team"),
            "away_score": game.get("away_score"),
            "home_score": game.get("home_score"),
            "state": game.get("state"),
            "period": game.get("period"),
            "clock": game.get("clock"),
            "pick": fade_signal.get("side"),
            "reason": fade_signal.get("reason"),
            "confidence": fade_signal.get("confidence"),
            "size": fade_signal.get("size"),
        }

    def publish_pick(self, pick: Dict[str, Any]):
        """Publish pick to Redis and console"""
        if self.redis_client:
            try:
                self.redis_client.publish(self.redis_channel, json.dumps(pick))
            except Exception as e:
                logger.warning(f"Redis publish failed: {e}")
        
        # Console output
        logger.info(
            f"🎯 PICK: {pick['matchup']} | Side: {pick['pick']} | Reason: {pick['reason']} | Size: {pick['size']}"
        )

    def run(self):
        """Main autonomous loop"""
        logger.info("=" * 100)
        logger.info(f"🤖 Autonomous Pick Generator | poll={self.poll_interval}s | channel={self.redis_channel}")
        logger.info("=" * 100)
        
        error_count = 0
        max_errors = 5
        
        while True:
            try:
                games = self.fetch_espn_games()
                if not games:
                    logger.warning("No games returned; retrying...")
                    time.sleep(self.poll_interval)
                    continue
                
                for event in games:
                    game = self.extract_game_info(event)
                    if not game:
                        continue
                    
                    gid = game.get("game_id")
                    
                    # Skip if already processed
                    if gid in self.processed_games:
                        continue
                    
                    # Fetch betting data
                    bet_data = self.fetch_betting_data(game["away_team"], game["home_team"])
                    if not bet_data:
                        continue
                    
                    # Calculate fade signal
                    fade_signal = self.calculate_fade_score(game, bet_data)
                    if not fade_signal:
                        continue
                    
                    # Generate and publish pick
                    pick = self.generate_pick(game, fade_signal)
                    self.publish_pick(pick)
                    
                    # Mark as processed
                    self.processed_games.add(gid)
                
                error_count = 0  # Reset error counter on success
                time.sleep(self.poll_interval)
                
            except Exception as e:
                error_count += 1
                logger.error(f"Loop error (attempt {error_count}/{max_errors}): {e}")
                if error_count >= max_errors:
                    logger.critical(f"Max errors reached; restarting in 60s...")
                    time.sleep(60)
                    error_count = 0
                else:
                    time.sleep(self.poll_interval * 2)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=30, help="Poll interval seconds")
    args = ap.parse_args()

    gen = AutonomousPickGenerator(poll_interval=args.poll)
    try:
        gen.run()
    except KeyboardInterrupt:
        logger.info("\n⏹️  Stopped by user")


if __name__ == "__main__":
    main()
