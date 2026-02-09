#!/usr/bin/env python3
"""
AUTONOMOUS BETTING ENGINE - SETUP & INTEGRATION GUIDE
One engine, runs daily, outputs picks in structured format
"""

setup_guide = """
================================================================================
AUTONOMOUS BETTING ENGINE v2 - DEPLOYMENT GUIDE
================================================================================

WHAT YOU GET:
- ONE continuous process that runs 24/7
- Monitors games every 60 seconds (configurable)
- Outputs picks in structured format (like PropJoe)
- Applies 3-1 winning formula automatically
- NO manual scripts needed

================================================================================
FILES CREATED:
================================================================================

1. autonomous_engine_continuous.py
   - Main engine that runs continuously
   - Polls ESPN API for live games
   - Applies RLM + public % analysis
   - Outputs picks in structured format
   - RUN THIS ONCE and it stays running

2. draftkings_realtime.py
   - Real-time betting % scraper
   - Pulls data from DraftKings/Action Network
   - Caches results to avoid rate limiting
   - Integrates with autonomous engine

3. scripts/example_signals.py
   - Example of pick output format
   - Shows how analysis is presented
   - Use as template for daily runs

================================================================================
TO START THE ENGINE:
================================================================================

Option 1: Run in terminal
$ cd c:/Users/epina/Devenvfoldher/Sportsbook-aggregation
$ python scripts/autonomous_engine_continuous.py

This will:
- Start at [time] with continuous mode message
- Check for new live games every 60 seconds
- Output any picks meeting criteria immediately
- Run until you press Ctrl+C

Option 2: Background process (Windows)
$ start /B python scripts/autonomous_engine_continuous.py

Option 3: Scheduled task (Windows Task Scheduler)
- Create task to run at 8:00 AM daily
- Point to: python scripts/autonomous_engine_continuous.py
- Set to repeat until manually stopped

================================================================================
WHAT THE ENGINE DOES:
================================================================================

EVERY 60 SECONDS:
1. Fetch live games from ESPN API (NCAAB, NBA)
2. For each game:
   - Get opening line (stored in cache)
   - Get current line (live scrape)
   - Get public % (DraftKings/Action Network scrape)
   - Calculate RLM = current - opening
   - Apply fade logic:
     * IF public 65%+ on one side AND RLM 2+ pts AGAINST them
     * THEN output PLAY (Tier 1 or 2)

OUTPUT FORMAT (when picks found):
---
PLAY [#]: [SIGNAL STRENGTH]
Game: [MATCHUP]
Pick: [SIDE @ LINE]

ML Public: X% | Spread Public: Y%
Opening: [LINE] | Current: [LINE] | RLM: [+/- pts]

Analysis: [REASONING]
Recommendation: PLAY at [CONFIDENCE]%
---

================================================================================
KEY SETTINGS TO ADJUST:
================================================================================

In autonomous_engine_continuous.py:

1. Checking interval (default: 60 seconds)
   engine.run_continuous(interval_seconds=60)
   
   For real-time mode: 30 seconds
   For less spam: 300 seconds (5 minutes)

2. RLM threshold (default: 2.0 pts)
   MIN_RLM_AGAINST_PUBLIC = 2.0  # Tier 2
   STRONG_RLM = 3.0  # Tier 1

3. Public % threshold (default: 65%)
   MIN_PUBLIC_DIVERGENCE = 65

4. Sport filters (add/remove as needed)
   ncaab_games = self.fetch_ncaab_games()
   nba_games = self.fetch_nba_games()

================================================================================
REAL-TIME DATA INTEGRATION:
================================================================================

The engine skeleton is built. To make it WORK with real data:

1. DraftKings scraping:
   - Uncomment the scraping functions in draftkings_realtime.py
   - May need to update CSS selectors based on current DK layout
   - Consider using Playwright/Selenium for JavaScript-rendered content

2. Opening line storage:
   - Create database table: games(game_id, opening_line, timestamp)
   - Store line at game start time
   - Query opening line when game goes live

3. Line movement detection:
   - Poll sportsbooks multiple times per game
   - Track historical lines: timestamp, book, line
   - Calculate RLM as current - opening

4. Public % source priority:
   a) DraftKings (most reliable)
   b) FanDuel (alternative)
   c) BetMGM (alternative)
   d) Action Network (consensus data)

================================================================================
PRODUCTION CHECKLIST:
================================================================================

[ ] Test engine for 1 hour (check console output)
[ ] Verify ESPN API pulls correct games
[ ] Set up database for opening line storage
[ ] Implement DraftKings scraper
[ ] Add logging to file (autonomous_engine.log)
[ ] Test with real betting % from screenshots
[ ] Verify pick output format matches your needs
[ ] Set up scheduled task or background process
[ ] Configure alerting (Discord/SMS for Tier 1 plays)

================================================================================
EXAMPLE RUN:
================================================================================

$ python scripts/autonomous_engine_continuous.py

================================================================================
AUTONOMOUS BETTING ENGINE v2 - CONTINUOUS MODE
================================================================================
Started: 2026-01-24 14:30:00
Checking for picks every 60 seconds
================================================================================

[checking games...]

PLAY 1: STRONG FADE - RLM 3+ pts vs public
----
Game: Nets @ Celtics
Pick: Celtics -8
ML Public: 98% Nets | 2% Celtics
Spread Public: 59% Nets -8 | 41% Celtics +8
Opening: -3.5 | Current: -8 | RLM: -4.5pts
Analysis: Public 98% on underdog Nets, but line moved 4.5pts AGAINST them to -8. Sharp money fading public.
Recommendation: PLAY at 92% confidence
----

[checking games...]
[no picks found]
[checking games...]

PLAY 2: MODERATE FADE - RLM 2-3 pts vs public
...

================================================================================
That's it. One process. Continuous. Automatic.
================================================================================

Questions? Check:
- Console logs for errors
- DraftKings scraper output
- ESPN API response data
- RLM calculations in real-time

To stop: Ctrl+C in the terminal
"""

print(setup_guide)

# Also create a quick start script
quick_start = """
#!/bin/bash
# Quick start script for autonomous engine

echo "Starting Autonomous Betting Engine v2..."
echo "This will run continuously and output picks in real-time"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python scripts/autonomous_engine_continuous.py
"""

with open("start_autonomous_engine.sh", "w") as f:
    f.write(quick_start)

print("\n\n" + "="*80)
print("QUICK START SCRIPT CREATED: start_autonomous_engine.sh")
print("="*80)
