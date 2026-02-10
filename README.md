# Sportsbook Aggregation Engine

**Algorithmic Sports Betting Analysis | Signal Classification | Autonomous Nightly Ops**

---

## Overview

A Python-based autonomous sports betting analysis engine focused on NBA.
It merges free ESPN data with The Odds API odds, runs Reverse Line Movement (RLM) detection, classifies signals into PRIMARY vs CONFIRMATION tiers, applies confidence decay over time, and outputs tiered pick cards with Discord notifications.

**Key principle:** This is an *analysis* tool, not a gambling bot. It treats betting like algorithmic trading — edge-first, bankroll-managed, data-driven.

---

## Architecture

```
Data Ingestion (ESPN free + Odds API)
        │
        ▼
Signal Detection
  ├── RLM (spread & total)
  ├── Line Freeze Detection
  ├── Book Disagreement
  ├── ML/Spread Divergence
  └── Public Money Extremes
        │
        ▼
Signal Classification (engine/signals.py)
  ├── PRIMARY signals   → Trigger bets
  └── CONFIRMATION      → Boost confidence
        │
        ▼
Confidence Scoring + Decay (engine/confidence_decay.py)
  ├── Time decay (-1.5%/hr after 2hrs)
  ├── Line movement confirmation/erosion
  └── Injury & information leak penalties
        │
        ▼
Tier Classification
  ├── TIER 1 (≥80% confidence) → Full position
  ├── TIER 2 (≥70%)           → Partial position
  ├── LEAN   (≥60%)           → Small or watch
  └── PASS   (<60%)           → No bet
        │
        ▼
Output
  ├── Console pick card
  ├── data/picks_YYYYMMDD.json
  ├── Discord webhook notification
  └── CLV tracking for long-term P&L
```

---

## Modules

### Engine (`engine/`)

| Module | Purpose |
|--------|---------|
| `signals.py` | Classifies detected signals as PRIMARY (bet triggers) or CONFIRMATION (confidence boosters). 10 signal types with category-specific weights. |
| `confidence_decay.py` | Applies time-based and market-based decay to pick confidence. Auto-promotes/demotes picks as edge changes. |
| `clv_tracker.py` | Tracks Closing Line Value — the ground truth metric for proving long-term edge. Persists history to JSON. |
| `line_freeze_detector.py` | Detects when books refuse to move a line despite heavy public action (BOOK_TRAP, SHARP_HOLD, STEAM_FROZEN). |
| `boost_ev.py` | Calculates how DraftKings profit boosts change EV. Identifies when boosts turn PASS plays into +EV. |
| `smart_scheduler.py` | 4-phase autonomous pipeline: Discovery → Odds → Analysis → Picks. Credit-budget aware. |
| `credit_tracker.py` | Tracks Odds API credit usage (500/month budget). Prevents overspending. |
| `line_movement_tracker.py` | Monitors and records line movements over time for RLM detection. |
| `game_discovery.py` | Discovers today's games from ESPN (free, no API credits). |
| `autonomous_engine.py` | Original autonomous engine for whale tracking and fade detection. |

### Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `nightly_ops.py` | **Main entry point.** Single-command pre-game checklist: fetch slate, get odds, analyze, generate picks, notify Discord. |
| `analyze_results.py` | Post-game autopsy. Fetches final scores from ESPN and grades every pick. Run the morning after. |
| `run_daily_engine.py` | APScheduler service with cron jobs at 9 AM / 3 PM / 6 PM ET. |
| `todays_slate_runner.py` | ESPN + Odds API merger with RLM and fade analysis. |

### Config (`config/`)

| Module | Purpose |
|--------|---------|
| `api_registry.py` | Unified API credential management — loads from `.env`, never hardcoded. Singleton pattern. |
| `settings.py` | General project settings. |
| `sports_config.py` | Sport-specific configuration (leagues, markets). |

### Alerts (`alerts/`)

| Module | Purpose |
|--------|---------|
| `pick_notifier.py` | Sends pick cards and reports to Discord via webhook. |
| `discord_webhook.py` | Low-level Discord webhook sender. |
| `email_alert.py` | Email alert support. |

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/EPdacoder05/Sportsbook-aggregation.git
cd Sportsbook-aggregation
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and add your keys:
#   ODDS_API_KEY=your_key_here
#   DISCORD_WEBHOOK_URL=your_webhook_here
```

### 3. Run nightly ops

```bash
# Full run (fetches odds, costs API credits)
python scripts/nightly_ops.py

# Dry run (no Discord notification)
python scripts/nightly_ops.py --dry-run

# ESPN-only (no API credits used)
python scripts/nightly_ops.py --no-odds

# With profit boost evaluation
python scripts/nightly_ops.py --boosts "MIL ML:-150:25" "CHI ML:+300:50"
```

### 4. Morning after

```bash
# Grade last night's picks
python scripts/analyze_results.py --today
python scripts/analyze_results.py --date 2025-02-09
```

---

## API Credit Budget

The Odds API provides **500 free credits/month**. Each odds fetch costs credits based on markets requested.

The engine tracks usage via `engine/credit_tracker.py` and will skip fetches when the budget is exhausted. Use `--no-odds` for zero-credit runs that rely on cached or ESPN-only data.

---

## Signal Types

### Primary Signals (bet triggers — at least one required)

| Signal | Description | Threshold |
|--------|-------------|-----------|
| `RLM_SPREAD` | Reverse line movement on spread | ≥1.5pt move opposite public |
| `RLM_TOTAL` | Reverse line movement on total | ≥2pt move opposite public |
| `ML_SPREAD_DIVERGENCE` | Moneyline vs spread disagreement | ≥15% implied probability gap |
| `LINE_FREEZE` | Line frozen despite heavy public action | 70%+ public, 0 movement, 4+ hours |

### Confirmation Signals (boost confidence — cannot trigger alone)

| Signal | Description |
|--------|-------------|
| `ATS_EXTREME` | Team covers at extreme rate (>65% or <35%) |
| `BOOK_DISAGREEMENT` | Books disagree by ≥2 pts on spread |
| `CROSS_SOURCE_DIVERGENCE` | Different sources show divergent lines |
| `PACE_MISMATCH` | Pace differential suggesting total value |
| `REST_ADVANTAGE` | Significant rest day advantage |
| `HOME_ROAD_SPLIT` | Extreme home/road ATS differential |

---

## Confidence Decay

Picks are not static. Confidence decays based on:

- **Time**: -1.5% per hour after 2-hour freshness window (max -15%)
- **Line movement FOR you**: +2% per point (CLV confirmed)
- **Line movement AGAINST you**: -4% per point past 1pt threshold
- **Injury after pick**: -15% (game script changed)
- **Information leak** (sudden 2+ pt jump): -10%

A pick can be **promoted** (LEAN → TIER2) if the line moves in its favor, or **demoted** (TIER1 → TIER2 → PASS) if edge erodes.

---

## Profit Boost Calculator

The `engine/boost_ev.py` module evaluates DraftKings profit boosts:

- Boosts apply to **profit**, not payout (DK formula)
- Calculates true EV and Kelly criterion
- Classifies boosts: TIER1 (≥8% EV), TIER2 (3-8%), LEAN (0-3%), PASS (<0%)
- Can find the minimum boost % needed to make any bet +EV

---

## Post-Game Autopsy

`scripts/analyze_results.py` grades picks after games complete:

- Fetches final scores from ESPN (free)
- Grades each pick as WIN/LOSS/PUSH
- Reports by tier, pick type, and signal type
- Tracks margin of victory/defeat
- What-if analysis (would changing tiers improve results?)
- Feeds data to CLV tracker for long-term P&L

---

## Project Structure

```
├── engine/                    # Core analysis modules
│   ├── signals.py             # Signal classification (PRIMARY vs CONFIRMATION)
│   ├── confidence_decay.py    # Time/market decay engine
│   ├── clv_tracker.py         # Closing Line Value tracker
│   ├── line_freeze_detector.py# Book trap detection
│   ├── boost_ev.py            # Profit boost EV calculator
│   ├── smart_scheduler.py     # Credit-aware scheduler
│   ├── credit_tracker.py      # API credit budget tracker
│   └── ...
├── scripts/                   # Runnable scripts
│   ├── nightly_ops.py         # Main entry point
│   ├── analyze_results.py     # Post-game autopsy
│   ├── run_daily_engine.py    # Cron scheduler
│   └── ...
├── config/                    # Configuration
│   ├── api_registry.py        # API credential management
│   └── ...
├── alerts/                    # Notification senders
│   ├── pick_notifier.py       # Discord notifications
│   └── ...
├── scrapers/                  # Data scrapers
├── database/                  # DB models
├── api/                       # FastAPI backend
├── dashboard/                 # Streamlit dashboard
├── data/                      # Runtime data (gitignored)
├── logs/                      # Logs (gitignored)
├── .env                       # API keys (gitignored)
├── .env.example               # Template for .env
├── requirements.txt           # Python dependencies
└── README.md
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `ODDS_API_KEY` | Yes | The Odds API key (500 free credits/month) |
| `DISCORD_WEBHOOK_URL` | No | Discord webhook for pick notifications |
| `EMAIL_USER` | No | Email address for email alerts |
| `EMAIL_PASS` | No | Email password / app password |
| `DATABASE_URL` | No | PostgreSQL connection string |

---

## License

Private repository. Not for redistribution.
