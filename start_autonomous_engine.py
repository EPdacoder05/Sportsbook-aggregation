#!/usr/bin/env python3
"""
AUTONOMOUS ENGINE — Docker Entrypoint
=======================================
This is the entry point used by docker-compose for the `engine` service.
Runs the smart_scheduler in autonomous mode with graceful shutdown,
watchdog auto-restart, and state persistence.

Usage:
    python start_autonomous_engine.py              # Normal mode
    python start_autonomous_engine.py --once       # Run one cycle and exit
"""

import sys
import os
import signal
import time
import json
import logging
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.smart_scheduler import SmartScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

STATE_FILE = PROJECT_ROOT / "data" / "engine_state.json"
WATCHDOG_MAX_RESTARTS = 10
WATCHDOG_RESTART_DELAY = 30  # seconds


class AutonomousEngine:
    """Wraps SmartScheduler with watchdog, graceful shutdown, and state persistence."""

    def __init__(self):
        self.scheduler = SmartScheduler()
        self.running = False
        self.restart_count = 0
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _shutdown_handler(self, signum, frame):
        logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        self.running = False
        self._save_state()
        logger.info("State saved. Exiting.")
        sys.exit(0)

    def _save_state(self):
        """Persist engine state to disk so it can resume."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "last_shutdown": datetime.now().isoformat(),
                "restart_count": self.restart_count,
                "games_discovered": len(self.scheduler.games),
                "windows_scheduled": len(
                    getattr(self.scheduler, "windows", [])
                ),
            }
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            logger.info(f"State persisted to {STATE_FILE}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _load_state(self):
        """Load previous state if available."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                logger.info(
                    f"Loaded previous state: last shutdown "
                    f"{state.get('last_shutdown', 'unknown')}, "
                    f"restarts: {state.get('restart_count', 0)}"
                )
                return state
            except Exception:
                pass
        return {}

    def run_once(self):
        """Run a single discovery + scheduling cycle."""
        logger.info("=" * 70)
        logger.info("AUTONOMOUS ENGINE — Single Cycle")
        logger.info("=" * 70)
        self.scheduler.discover_games()
        windows = self.scheduler.group_into_windows()
        if windows:
            logger.info(f"Discovered {len(self.scheduler.games)} games "
                        f"in {len(windows)} windows.")
        else:
            logger.info("No games found for today.")

    def run(self):
        """
        Main loop with watchdog auto-restart.
        Runs discover → schedule → sleep → rediscover continuously.
        """
        self._load_state()
        self.running = True

        logger.info("=" * 70)
        logger.info("  HOUSE EDGE — Autonomous Engine Starting")
        logger.info(f"  PID: {os.getpid()}")
        logger.info(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        while self.running and self.restart_count < WATCHDOG_MAX_RESTARTS:
            try:
                # Discover + schedule
                self.scheduler.discover_games()
                windows = self.scheduler.group_into_windows()

                if hasattr(self.scheduler, "run_autonomous"):
                    self.scheduler.run_autonomous()
                else:
                    # Fallback: manual window execution loop
                    logger.info("Running manual window execution loop...")
                    for window in windows:
                        if not self.running:
                            break
                        self.scheduler.fetch_odds_for_window(window)
                        self.scheduler.analyze_window(window)

                # If run_autonomous returns (end of day), wait and rediscover
                logger.info("Daily cycle complete. Sleeping until next check...")
                self._save_state()

                # Sleep 30 minutes before checking for new day
                for _ in range(180):  # 180 × 10s = 30 min
                    if not self.running:
                        break
                    time.sleep(10)

                self.restart_count = 0  # Reset on clean cycle

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                self.restart_count += 1
                logger.error(
                    f"Engine crashed (attempt {self.restart_count}/"
                    f"{WATCHDOG_MAX_RESTARTS}): {e}"
                )
                self._save_state()
                if self.restart_count < WATCHDOG_MAX_RESTARTS:
                    logger.info(
                        f"Watchdog: restarting in {WATCHDOG_RESTART_DELAY}s..."
                    )
                    time.sleep(WATCHDOG_RESTART_DELAY)
                else:
                    logger.critical(
                        f"Max restarts ({WATCHDOG_MAX_RESTARTS}) reached. Exiting."
                    )

        self._save_state()
        logger.info("Autonomous engine stopped.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="House Edge Autonomous Engine")
    parser.add_argument(
        "--once", action="store_true", help="Run one cycle and exit"
    )
    args = parser.parse_args()

    engine = AutonomousEngine()

    if args.once:
        engine.run_once()
    else:
        engine.run()


if __name__ == "__main__":
    main()
