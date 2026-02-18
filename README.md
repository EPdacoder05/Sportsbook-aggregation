# Sportsbook Aggregation Engine

**Algorithmic Sports Betting Analysis | RLM Detection | Autonomous Nightly Ops**

---

## Overview

A Python-based autonomous sports betting analysis engine focused on NBA.
It merges free ESPN data with The Odds API odds, runs Reverse Line Movement (RLM) detection, ML-vs-Spread divergence analysis, classifies signals into PRIMARY vs CONFIRMATION tiers, applies confidence decay over time, and outputs tiered pick cards with Discord notifications.

**Key principle:** This is an *analysis* tool, not a gambling bot. It treats betting like algorithmic trading — edge-first, bankroll-managed, data-driven.

---

## Architecture

```
Data Ingestion (ESPN free + Odds API)
        │
        ▼
RLM Analysis Engine (analysis/)
  ├── Spread RLM: Line moves against public
  ├── Total RLM: Total drops/rises against public  
  ├── ML/Spread Divergence: Public trap detection
  └── ATS Trend Analysis: Fade extreme streaks
        │
        ▼
Confidence Scoring (multi-signal)
  ├── Primary signals: Trigger bets
  └── Confirmation signals: Boost confidence
        │
        ▼
Tier Classification
  ├── TIER 1 (≥85% confidence) → Full position
  ├── TIER 2 (≥75%)           → Partial position
  ├── LEAN   (≥60%)           → Small or watch
  └── PASS   (<60%)           → No bet
        │
        ▼
Output
  ├── Console pick card
  ├── data/picks_YYYYMMDD.json
  ├── Discord webhook notification (Tier 1/2)
  └── CLV tracking for long-term P&L
```

---

## Modules

### Analysis (`analysis/`) — NEW Intelligence Layer

| Module | Purpose |
|--------|---------|
| `rlm_detector.py` | Reverse Line Movement detection (4 strategies: Spread RLM, Total RLM, ML-Spread Divergence, ATS Trends) |
| `confidence.py` | Multi-signal confidence scorer with tier classification |
| `data_loader.py` | Unified data loading from odds/opening lines/public splits |
| `pick_generator.py` | Complete pick generation pipeline |

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
| `betting_engine.py` | **Unified orchestrator.** Wires signals + decay + freeze + ML into a single `analyze_game()` pipeline. |
| `no_bet_detector.py` | Coin-flip filter. Identifies games with zero edge via weighted scoring. Primary signal gate overrides. |
| `autonomous_engine.py` | Original autonomous engine for whale tracking and fade detection. |

### ML/AI Layer (`engine/ml/`)

| Module | Purpose |
|--------|---------|
| `feature_engine.py` | Transforms raw odds/signals/context into 32-dimension feature vectors for ML models. |
| `pick_model.py` | Gradient-Boosted supervised classifier. Learns WIN/LOSS from historical picks. Auto-retrains every 25 results. |
| `anomaly_detector.py` | Isolation Forest unsupervised detector. Flags games with unusual line/book/public profiles. |
| `model_monitor.py` | Drift detection (Page-Hinkley + PSI). Auto-triggers retrain when performance degrades. |

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
| `discord_notifier.py` | **NEW** Rich Discord embeds for Tier 1/2 picks with confidence scores. |
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

## Docker Security

The application uses a **hardened Docker setup** with multi-layered security:

### Security Features

#### 1. Multi-Stage Build
The Dockerfile uses a two-stage build process:
- **Builder stage**: Compiles dependencies with build tools (gcc, etc.)
- **Runtime stage**: Contains only runtime dependencies, reducing attack surface by ~40%

#### 2. Non-Root User
All containers run as the `appuser` (non-root) user with:
- No shell access (`/sbin/nologin`)
- Restricted home directory (`/app`)
- Minimal system privileges

#### 3. Security Options
All services in `docker-compose.yml` enforce:
- `no-new-privileges`: Prevents privilege escalation attacks
- Pinned image versions (no `latest` tags)
- Healthchecks for automatic recovery

#### 4. Minimal Base Image
Uses `python:3.12-slim-bookworm`:
- Debian-based minimal image
- Regular security patches
- ~5x smaller than full Python image

#### 5. Image Metadata
OCI-compliant labels for:
- Source repository tracking
- Maintainer information
- Security scanning integration

### Running with Docker

```bash
# Build the image
docker compose build

# Start all services
docker compose up -d

# Check service health
docker compose ps

# View logs
docker compose logs -f api

# Stop all services
docker compose down
```

### Docker Deployment Best Practices

1. **Always set strong passwords**: Update `DB_PASSWORD` in `.env`
2. **Keep images updated**: Rebuild weekly for security patches
3. **Monitor logs**: Use `docker compose logs` to track suspicious activity
4. **Limit network exposure**: Only expose necessary ports (8000, 8501)
5. **Use secrets management**: For production, use Docker secrets instead of environment variables

### Security Scanning

```bash
# Scan the image for vulnerabilities
docker scan sportsbook-aggregation:latest

# Or use Trivy
trivy image sportsbook-aggregation:latest
```

---

## API Credit Budget

The Odds API provides **500 free credits/month**. Each odds fetch costs credits based on markets requested.

The engine tracks usage via `engine/credit_tracker.py` and will skip fetches when the budget is exhausted. Use `--no-odds` for zero-credit runs that rely on cached or ESPN-only data.

---

## RLM Detection Strategies

The analysis engine implements 4 core RLM (Reverse Line Movement) strategies:

### 1. Spread RLM
**Strategy:** Line moves AGAINST the side with 60%+ public money.

**Example:**
- Opening: OKC @ LAL, Lakers -4.0
- Public: 57% on Lakers
- Current: Lakers -6.5 (line moved AGAINST Lakers)
- **Detection:** Sharp money is on OKC -6.5

**Thresholds:**
- Minimum line movement: 1.5 points
- Minimum public bias: 55%
- Confidence: 75-90% based on magnitude

### 2. Total RLM
**Strategy:** Total drops/rises 4+ points against public Over/Under bias.

**Example:**
- Opening: CHI @ BKN, Total 223.5
- Public: 64% on Over
- Current: Total 218.5 (dropped 5.0 points)
- **Detection:** Sharp money on UNDER 218.5 (Tier 1, 85% confidence)

**Thresholds:**
- Minimum total movement: 2.0 points
- Strong signal: 4.0+ points
- Minimum public bias: 60%

### 3. ML-Spread Divergence
**Strategy:** When Moneyline % - Spread % > 25%, public says "team wins but doesn't cover."

**Example:**
- MIL @ ORL
- Public: 84% ML on Orlando, 36% spread on Orlando
- Divergence: 48% (HIGHEST)
- **Interpretation:** Public thinks Orlando wins but doesn't cover
- **Pick:** MIL +10.5 (sharp side with points)

**Thresholds:**
- Minimum divergence: 15%
- Strong signal: 30%+
- Confidence: 70-85%

### 4. ATS Trend Extremes
**Strategy:** Fade extreme ATS streaks (regression to mean).

**Example:**
- CHI is 2-8 ATS L10 → Bet ON Chicago (fade cold streak)
- BOS is 8-2 ATS L10 → Bet AGAINST Boston (fade hot streak)

**Thresholds:**
- Extreme: ≥70% win/loss rate (7-3 or worse)
- Confidence: 65-70% (confirmation signal)

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
├── analysis/                  # NEW - Core intelligence layer
│   ├── rlm_detector.py        # RLM detection strategies
│   ├── confidence.py          # Multi-signal confidence scoring
│   ├── data_loader.py         # Unified data loading
│   └── pick_generator.py      # Pick generation pipeline
├── engine/                    # Core analysis modules
│   ├── signals.py             # Signal classification (PRIMARY vs CONFIRMATION)
│   ├── confidence_decay.py    # Time/market decay engine
│   ├── clv_tracker.py         # Closing Line Value tracker
│   ├── line_freeze_detector.py# Book trap detection
│   ├── line_tracker.py        # NEW - Opening line tracking
│   ├── boost_ev.py            # Profit boost EV calculator
│   ├── betting_engine.py      # Unified orchestrator (wires everything)
│   ├── no_bet_detector.py     # Coin-flip filter
│   ├── smart_scheduler.py     # Credit-aware scheduler
│   ├── credit_tracker.py      # API credit budget tracker
│   ├── ml/                    # ML/AI layer
│   │   ├── feature_engine.py  # 32-dim feature extraction
│   │   ├── pick_model.py      # Supervised GradientBoosting
│   │   ├── anomaly_detector.py# Unsupervised Isolation Forest
│   │   └── model_monitor.py   # Drift detection & auto-retrain
│   └── ...
├── scripts/                   # Runnable scripts
│   ├── nightly_ops.py         # Main entry point
│   ├── test_pick_generator.py # NEW - Test pick generation
│   ├── analyze_results.py     # Post-game autopsy
│   ├── run_daily_engine.py    # Cron scheduler
│   └── ...
├── config/                    # Configuration
│   ├── api_registry.py        # API credential management
│   └── ...
├── alerts/                    # Notification senders
│   ├── pick_notifier.py       # Discord notifications
│   ├── discord_notifier.py    # NEW - Rich Discord embeds
│   └── ...
├── tests/                     # Test suite
│   ├── test_rlm_detector.py   # NEW - RLM detection tests
│   ├── test_confidence.py     # NEW - Confidence scoring tests
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

## ML/AI Architecture

The engine uses a **closed-loop learning system**: predictions → results → retrain → better predictions.

```
Game Data → FeatureEngine (32-dim vector)
                │
                ├── PickModel (Supervised)
                │     └── GradientBoosting → Win probability
                │     └── Calibrated probabilities (Platt scaling)
                │     └── Anti-overfitting: early stopping, 5-fold CV,
                │         min 50 samples, holdout validation
                │
                ├── AnomalyDetector (Unsupervised)
                │     └── Isolation Forest → "Is this game unusual?"
                │     └── Z-score per feature → "Which features are off?"
                │
                └── ModelMonitor (Drift Detection)
                      └── Page-Hinkley test → streaming concept drift
                      └── PSI (Population Stability Index) → feature drift
                      └── Rolling accuracy/AUC/Brier → performance decay
                      └── Auto-retrain when drift detected
```

**Key Anti-Overfitting Guards:**
- Minimum 50-game sample before predictions activate
- Early stopping (patience=20) on validation loss
- Max tree depth=4, min samples per leaf=5
- Feature bagging (sqrt features per split)
- Calibrated probabilities via Platt scaling
- Separate holdout set (10%) never used for training
- Model drift monitor triggers retrain, not manual tuning

---

## Roadmap

### Phase 1: Core Engine ✅ SHIPPED
- Signal classification (10 signal types, PRIMARY vs CONFIRMATION)
- Confidence decay (time + market based)
- CLV tracking, line freeze detection, boost EV calculator
- Credit-aware scheduler, game discovery, nightly ops pipeline
- Discord notifications, post-game autopsy

### Phase 2: Unified Pipeline ✅ SHIPPED (PR #1)
- BettingEngine unified orchestrator
- NoBetDetector coin-flip filter
- Signal wiring into smart_scheduler
- Confidence decay integration into nightly_ops

### Phase 3: ML/AI Layer ✅ SHIPPED
- 32-feature engineering pipeline
- Supervised GradientBoosting pick model with auto-retrain
- Unsupervised Isolation Forest anomaly detector
- Model drift monitoring (Page-Hinkley + PSI)
- Closed-loop learning: predict → result → retrain

### Phase 4: Daemon Microservice (NEXT)
- [ ] Dockerized headless daemon (no human interaction needed)
- [ ] Health check endpoints (/health/live, /health/ready, /health/metrics)
- [ ] Prometheus metrics export (pick accuracy, model drift, API credits)
- [ ] Graceful shutdown with state persistence
- [ ] Watchdog auto-restart on crash

### Phase 5: Data Enrichment
- [ ] Player injury real-time feed integration
- [ ] Weather data for outdoor sports expansion
- [ ] Historical matchup data pipeline
- [ ] Opening line capture (currently unavailable at scheduler runtime)
- [ ] Public money % from Action Network or similar

### Phase 6: Multi-Sport Expansion
- [ ] NFL, MLB, NHL signal classification
- [ ] Sport-specific feature engineering
- [ ] League-specific thresholds and model weights

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
