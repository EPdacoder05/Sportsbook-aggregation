#!/usr/bin/env python3
"""
HOUSE EDGE — Daily Autonomous Engine
======================================
Runs as a long-lived service. Uses APScheduler for:

  CRON JOBS (game discovery — FREE, 0 credits):
    • 9:00 AM ET  — Morning discovery: find all today's NBA games
    • 3:00 PM ET  — Afternoon refresh: catch schedule changes / additions
    • 6:00 PM ET  — Evening refresh: final pre-slate check

  DYNAMIC JOBS (per game-time window — 2-3 credits each):
    • Scheduled ~20 min before each unique start-time cluster
    • ONE Odds API call per window → gets ALL games' final lines
    • Immediately runs analysis pipeline → outputs picks

Credit budget (500/month free tier):
    Discovery:  0 credits  (ESPN + /events are free)
    Odds fetch: ~3 per window × ~3-4 windows/day × 30 days ≈ 300 credits
    Buffer:     200 credits for unexpected needs

Usage:
    python scripts/run_daily_engine.py                # Start the service
    python scripts/run_daily_engine.py --now           # Discover + analyze NOW
    python scripts/run_daily_engine.py --status        # Show credit status
    python scripts/run_daily_engine.py --test-fetch    # Test one odds fetch
"""

import sys
import os
import signal
import logging
import argparse
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from engine.smart_scheduler import SmartGameScheduler
from engine.credit_tracker import CreditTracker

# ─── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Global state ────────────────────────────────────────────────────
game_scheduler = SmartGameScheduler()
ap_scheduler = BlockingScheduler(timezone="US/Eastern")


def discovery_job():
    """
    Called at 9 AM, 3 PM, 6 PM ET.
    Discovers games via ESPN (free) + Odds API /events (free).
    Groups games into time windows and schedules dynamic odds fetches.
    """
    now_et = datetime.now().strftime("%I:%M %p")
    logger.info(f"\n{'='*70}")
    logger.info(f"  ⏰ SCHEDULED DISCOVERY — {now_et} ET")
    logger.info(f"{'='*70}")

    try:
        game_scheduler.run_discovery_and_schedule()
    except Exception as e:
        logger.error(f"Discovery job failed: {e}", exc_info=True)


def print_banner():
    """Print startup banner."""
    ct = CreditTracker()
    now = datetime.now()
    
    print()
    print("═" * 70)
    print("  🏀 HOUSE EDGE — DAILY AUTONOMOUS ENGINE")
    print(f"  Started: {now.strftime('%A, %B %d, %Y at %I:%M %p')}")
    print("═" * 70)
    print()
    print("  📋 SCHEDULED JOBS (ET timezone):")
    print("     9:00 AM — Morning game discovery")
    print("     3:00 PM — Afternoon schedule refresh")
    print("     6:00 PM — Evening pre-slate check")
    print()
    print("  ⚡ DYNAMIC JOBS:")
    print("     ~20 min before each game-time window → odds fetch + analysis")
    print()
    print(f"  {ct.summary()}")
    print()
    print("  🟢 ENGINE ACTIVE — Watching for NBA games")
    print("     Press Ctrl+C to stop.")
    print("═" * 70)
    print()


def run_service():
    """Start the long-lived scheduler service."""
    print_banner()

    # Schedule cron jobs: 9 AM, 3 PM, 6 PM ET
    ap_scheduler.add_job(
        discovery_job,
        CronTrigger(hour=9, minute=0),
        id="discovery_9am",
        name="Morning Discovery (9 AM ET)",
        replace_existing=True,
    )
    ap_scheduler.add_job(
        discovery_job,
        CronTrigger(hour=15, minute=0),
        id="discovery_3pm",
        name="Afternoon Refresh (3 PM ET)",
        replace_existing=True,
    )
    ap_scheduler.add_job(
        discovery_job,
        CronTrigger(hour=18, minute=0),
        id="discovery_6pm",
        name="Evening Pre-Slate (6 PM ET)",
        replace_existing=True,
    )

    # Run an immediate discovery on startup
    logger.info("Running initial discovery on startup...")
    discovery_job()

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("\n🛑 Shutting down...")
        game_scheduler._cancel_all_timers()
        game_scheduler.save_state()
        ap_scheduler.shutdown(wait=False)
        logger.info("✅ Saved state. Goodbye.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        ap_scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


def run_now():
    """One-shot: discover + fetch + analyze immediately."""
    print_banner()
    game_scheduler.run_one_shot()


def show_status():
    """Show credit status and last discovery info."""
    ct = CreditTracker()
    print(ct.summary())

    state_file = game_scheduler.state_file
    if state_file.exists():
        import json
        with open(state_file) as f:
            state = json.load(f)
        
        print(f"\n📅 Last Discovery: {state.get('last_discovery', 'Never')}")
        print(f"   Games found: {state.get('games_count', 0)}")
        print(f"   Windows: {state.get('windows_count', 0)}")
        
        for w in state.get("windows", []):
            icon = "✅" if w.get("odds_fetched") else "⏳"
            analysis = "📊" if w.get("analysis_complete") else "  "
            print(f"   {icon}{analysis} {w['window_id']} — {w['game_count']} games")
            for g in w.get("games", []):
                print(f"       {g['away_team']} @ {g['home_team']}")
    else:
        print("\n   No previous state found. Run --now or start the service.")


def test_fetch():
    """Test: discover games and do ONE odds fetch to verify connectivity."""
    print_banner()
    ct = CreditTracker()
    
    print(f"⚠️  This will use ~3 credits from your budget.")
    print(f"   Current usage: {ct.used}/{500}")
    print()

    game_scheduler.discover_games()
    game_scheduler.group_into_windows()

    if game_scheduler.windows:
        # Fetch odds for the first window only
        window = game_scheduler.windows[0]
        game_scheduler.fetch_odds_for_window(window)
        game_scheduler.analyze_window(window)
        game_scheduler._print_window_summary(window, {})
    else:
        print("No upcoming windows to test with.")

    game_scheduler.save_state()


# ─── CLI ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="HOUSE EDGE Daily Autonomous Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_daily_engine.py              Start as service (9am/3pm/6pm cron)
  python scripts/run_daily_engine.py --now         Discover + fetch + analyze NOW
  python scripts/run_daily_engine.py --status      Show credit status
  python scripts/run_daily_engine.py --test-fetch  Test one odds fetch
        """,
    )
    parser.add_argument("--now", action="store_true", help="One-shot: discover + fetch + analyze now")
    parser.add_argument("--status", action="store_true", help="Show credit status and state")
    parser.add_argument("--test-fetch", action="store_true", help="Test connectivity with one odds fetch")
    args = parser.parse_args()

    if args.now:
        run_now()
    elif args.status:
        show_status()
    elif args.test_fetch:
        test_fetch()
    else:
        run_service()


if __name__ == "__main__":
    main()
