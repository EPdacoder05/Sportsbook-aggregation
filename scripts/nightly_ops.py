#!/usr/bin/env python3
"""
NIGHTLY OPS RUNNER
==================
Single-command pre-game checklist that runs every night before first tip.

This script systematizes the entire pre-game workflow:
  1. Fetch today's slate from ESPN (free — no credits)
  2. Fetch odds from The Odds API (budget-aware)
  3. Run RLM + fade analysis on all games
  4. Classify signals (primary vs confirmation)
  5. Apply confidence decay to any stale picks
  6. Detect line freezes from cached odds
  7. Evaluate available profit boosts
  8. Generate final pick card with tiers
  9. Send Discord notification with tonight's plays
  10. Log everything for post-game autopsy

Usage:
    python scripts/nightly_ops.py
    python scripts/nightly_ops.py --dry-run           # Skip Discord alerts
    python scripts/nightly_ops.py --sport basketball_nba
    python scripts/nightly_ops.py --boosts "MIL ML:-150:25" "CHI ML:+300:50"

Cron: Run at 5:00 PM ET (2 hours before first NBA tip-off)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.confidence_decay import ConfidenceDecayEngine
from engine.quarter_line_detector import QuarterLineDetector
from engine.star_absence_detector import StarAbsenceDetector
from engine.parlay_tracker import ParlayTracker


def load_env():
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass


def ensure_dirs():
    """Ensure required data directories exist."""
    (PROJECT_ROOT / "data").mkdir(exist_ok=True)
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)


def fetch_espn_slate(sport: str = "basketball_nba") -> list:
    """Fetch today's games from ESPN (free, no credits)."""
    import urllib.request

    sport_map = {
        "basketball_nba": ("basketball", "nba"),
    }
    category, league = sport_map.get(sport, ("basketball", "nba"))
    today = datetime.now().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}/scoreboard?dates={today}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SBagg/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        games = []
        for event in data.get("events", []):
            teams = event.get("competitions", [{}])[0].get("competitors", [])
            if len(teams) == 2:
                away = next((t for t in teams if t.get("homeAway") == "away"), teams[0])
                home = next((t for t in teams if t.get("homeAway") == "home"), teams[1])
                games.append({
                    "game_key": f"{away['team']['abbreviation']} @ {home['team']['abbreviation']}",
                    "away": away["team"]["abbreviation"],
                    "home": home["team"]["abbreviation"],
                    "away_full": away["team"]["displayName"],
                    "home_full": home["team"]["displayName"],
                    "start_time": event.get("date", ""),
                    "status": event.get("status", {}).get("type", {}).get("name", ""),
                })
        return games
    except Exception as e:
        print(f"  [!] ESPN fetch failed: {e}")
        return []


def fetch_odds(sport: str = "basketball_nba", api_key: str = "") -> list:
    """Fetch odds from The Odds API (credit-aware)."""
    import urllib.request

    if not api_key:
        print("  [!] No ODDS_API_KEY — skipping odds fetch")
        return []

    url = (
        f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
        f"?apiKey={api_key}&regions=us&markets=spreads,totals&oddsFormat=american"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SBagg/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            remaining = resp.headers.get("x-requests-remaining", "?")
            used = resp.headers.get("x-requests-used", "?")
            print(f"  [i] Odds API credits: {used} used / {remaining} remaining")
            return data
    except Exception as e:
        print(f"  [!] Odds API fetch failed: {e}")
        return []


def merge_slate_with_odds(games: list, odds_data: list) -> list:
    """Merge ESPN's slate with odds data."""
    # Build odds lookup
    odds_lookup = {}
    for event in odds_data:
        away = event.get("away_team", "")
        home = event.get("home_team", "")
        bookmakers = event.get("bookmakers", [])

        # Parse bookmaker consensus
        spreads = []
        totals = []
        for bm in bookmakers:
            for market in bm.get("markets", []):
                if market["key"] == "spreads":
                    for outcome in market.get("outcomes", []):
                        if outcome.get("name") == away:
                            spreads.append({
                                "book": bm["key"],
                                "spread": outcome.get("point", 0),
                                "price": outcome.get("price", -110),
                            })
                elif market["key"] == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome.get("name") == "Over":
                            totals.append({
                                "book": bm["key"],
                                "total": outcome.get("point", 0),
                                "over_price": outcome.get("price", -110),
                            })

        key = f"{away} @ {home}"
        odds_lookup[key] = {
            "spreads": spreads,
            "totals": totals,
            "num_books": len(bookmakers),
        }

    # Merge
    for game in games:
        # Try to match by team names
        matched = None
        for key, val in odds_lookup.items():
            if game["away"] in key or game["home"] in key:
                matched = val
                break

        if matched:
            game["odds"] = matched
        else:
            game["odds"] = {"spreads": [], "totals": [], "num_books": 0}

    return games


def analyze_game(game: dict) -> dict:
    """Run full analysis on a single game."""
    analysis = {
        "game": game["game_key"],
        "picks": [],
        "signals": [],
        "confidence": 0,
        "tier": "PASS",
    }

    odds = game.get("odds", {})
    spreads = odds.get("spreads", [])
    totals = odds.get("totals", [])

    if not spreads and not totals:
        analysis["notes"] = "No odds data available"
        return analysis

    # ── Spread Analysis ──
    if spreads:
        spread_vals = [s["spread"] for s in spreads]
        avg_spread = sum(spread_vals) / len(spread_vals)
        spread_range = max(spread_vals) - min(spread_vals)

        analysis["avg_spread"] = round(avg_spread, 1)
        analysis["spread_range"] = round(spread_range, 1)

        # Book disagreement signal
        if spread_range >= 2.0:
            analysis["signals"].append({
                "type": "BOOK_DISAGREEMENT",
                "category": "CONFIRMATION",
                "detail": f"Spread range {spread_range:.1f}pts across {len(spreads)} books",
            })

    # ── Totals Analysis ──
    if totals:
        total_vals = [t["total"] for t in totals]
        avg_total = sum(total_vals) / len(total_vals)
        total_range = max(total_vals) - min(total_vals)

        analysis["avg_total"] = round(avg_total, 1)
        analysis["total_range"] = round(total_range, 1)

        # Check for cross-source divergence on totals
        if total_range >= 2.0:
            analysis["signals"].append({
                "type": "CROSS_SOURCE_DIVERGENCE",
                "category": "CONFIRMATION",
                "detail": f"Total range {total_range:.1f}pts across {len(totals)} books",
            })

    # ── Signal Classification ──
    try:
        from engine.signals import SignalClassifier
        classifier = SignalClassifier()
        profile = classifier.classify(analysis.get("signals", []))
        analysis["signal_profile"] = {
            "has_primary": profile.has_primary,
            "confidence": profile.confidence,
            "tier": profile.tier,
            "primary_count": len(profile.primary_signals),
            "confirm_count": len(profile.confirmation_signals),
        }
        analysis["confidence"] = profile.confidence
        analysis["tier"] = profile.tier
    except ImportError:
        # If signal classifier not available, use simple logic
        if len(analysis["signals"]) >= 2:
            analysis["confidence"] = 70
            analysis["tier"] = "TIER2"
        elif len(analysis["signals"]) >= 1:
            analysis["confidence"] = 60
            analysis["tier"] = "LEAN"

    return analysis


def generate_pick_card(analyses: list) -> dict:
    """Generate the final pick card for tonight."""
    tier1 = [a for a in analyses if a.get("tier") == "TIER1"]
    tier2 = [a for a in analyses if a.get("tier") == "TIER2"]
    leans = [a for a in analyses if a.get("tier") == "LEAN"]
    passes = [a for a in analyses if a.get("tier") == "PASS"]

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_games": len(analyses),
            "tier1_plays": len(tier1),
            "tier2_plays": len(tier2),
            "leans": len(leans),
            "passes": len(passes),
        },
        "tier1": tier1,
        "tier2": tier2,
        "leans": leans,
        "passes": passes,
    }


def send_discord_alert(pick_card: dict, dry_run: bool = False):
    """Send pick card to Discord."""
    if dry_run:
        print("  [i] Dry run — skipping Discord notification")
        return

    try:
        from alerts.pick_notifier import PickNotifier
        notifier = PickNotifier()

        summary = pick_card["summary"]
        lines = [
            f"**Nightly Ops Report — {pick_card['date']}**",
            f"Games analyzed: {summary['total_games']}",
            f"TIER 1 plays: {summary['tier1_plays']}",
            f"TIER 2 plays: {summary['tier2_plays']}",
            f"Leans: {summary['leans']}",
            f"Passes: {summary['passes']}",
        ]

        for t1 in pick_card.get("tier1", []):
            lines.append(f"\n**TIER 1: {t1['game']}** (conf: {t1['confidence']}%)")
            for sig in t1.get("signals", []):
                lines.append(f"  Signal: {sig['type']} — {sig.get('detail', '')}")

        for t2 in pick_card.get("tier2", []):
            lines.append(f"\nTIER 2: {t2['game']} (conf: {t2['confidence']}%)")

        message = "\n".join(lines)
        notifier.send(message)
        print("  [✓] Discord notification sent")
    except Exception as e:
        print(f"  [!] Discord notification failed: {e}")


def save_pick_card(pick_card: dict):
    """Save pick card for post-game autopsy."""
    date_str = datetime.now().strftime("%Y%m%d")
    filepath = PROJECT_ROOT / "data" / f"picks_{date_str}.json"
    with open(filepath, "w") as f:
        json.dump(pick_card, f, indent=2, default=str)
    print(f"  [✓] Pick card saved: {filepath.name}")


def print_pick_card(pick_card: dict):
    """Print the pick card to console."""
    summary = pick_card["summary"]

    print("\n" + "═" * 60)
    print(f"  NIGHTLY OPS — {pick_card['date']}")
    print("═" * 60)
    print(f"  Games analyzed: {summary['total_games']}")
    print(f"  TIER 1: {summary['tier1_plays']}  |  TIER 2: {summary['tier2_plays']}  |  "
          f"Leans: {summary['leans']}  |  Pass: {summary['passes']}")
    print("─" * 60)

    for tier_name, tier_key in [("TIER 1", "tier1"), ("TIER 2", "tier2"), ("LEAN", "leans")]:
        games = pick_card.get(tier_key, [])
        if games:
            print(f"\n  {tier_name} PLAYS:")
            for g in games:
                print(f"    {g['game']}  —  Confidence: {g.get('confidence', '?')}%")
                if "avg_spread" in g:
                    print(f"      Spread: {g['avg_spread']:+.1f}  |  Total: {g.get('avg_total', '?')}")
                for sig in g.get("signals", []):
                    print(f"      [{sig.get('category', '?')}] {sig['type']}: {sig.get('detail', '')}")

    if summary["tier1_plays"] == 0 and summary["tier2_plays"] == 0:
        print("\n  No actionable plays tonight — sit this one out.")
        print("  'No bet IS a bet.' — Sharp thinking prevails.")

    print("\n" + "═" * 60)


def evaluate_boosts(boost_strings: list) -> list:
    """Parse and evaluate profit boosts from CLI."""
    if not boost_strings:
        return []

    try:
        from engine.boost_ev import BoostCalculator
        calc = BoostCalculator()
        boosts = []

        for bs in boost_strings:
            parts = bs.split(":")
            if len(parts) != 3:
                print(f"  [!] Invalid boost format '{bs}' — expected 'NAME:ODDS:BOOST%'")
                continue
            name, odds_str, boost_str = parts
            boosts.append({
                "name": name.strip(),
                "odds": int(odds_str),
                "boost_pct": int(boost_str),
            })

        results = calc.evaluate_all_boosts(boosts)
        print(f"\n  [i] Evaluated {len(results)} profit boosts:")
        for r in results:
            print(f"    {r.name}: {r.tier} (EV: {r.ev_pct:+.1f}%)")
        return results
    except Exception as e:
        print(f"  [!] Boost evaluation failed: {e}")
        return []


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Nightly Ops Runner")
    parser.add_argument("--dry-run", action="store_true", help="Skip Discord notifications")
    parser.add_argument("--sport", default="basketball_nba", help="Sport key")
    parser.add_argument("--boosts", nargs="*", default=[], help="Profit boosts: 'NAME:ODDS:BOOST%%'")
    parser.add_argument("--no-odds", action="store_true", help="Skip odds fetch (ESPN only)")
    args = parser.parse_args()

    load_env()
    ensure_dirs()

    print("═" * 60)
    print("  NIGHTLY OPS — Starting pre-game workflow")
    print("═" * 60)

    # ── Step 1: Fetch ESPN Slate ──
    print("\n[1/8] Fetching today's slate from ESPN...")
    games = fetch_espn_slate(args.sport)
    print(f"  Found {len(games)} games")

    if not games:
        print("  No games today — nothing to do")
        return

    for g in games:
        print(f"    {g['game_key']}  ({g.get('start_time', '?')})")

    # ── Step 2: Fetch Odds ──
    odds_data = []
    if not args.no_odds:
        print("\n[2/8] Fetching odds from The Odds API...")
        api_key = os.environ.get("ODDS_API_KEY", "")
        odds_data = fetch_odds(args.sport, api_key)
        print(f"  Got odds for {len(odds_data)} events")
    else:
        print("\n[2/8] Skipping odds fetch (--no-odds)")

    # ── Step 3: Merge ──
    print("\n[3/8] Merging slate with odds...")
    merged = merge_slate_with_odds(games, odds_data)
    games_with_odds = sum(1 for g in merged if g.get("odds", {}).get("num_books", 0) > 0)
    print(f"  Merged: {games_with_odds}/{len(merged)} games have odds")

    # ── Step 4: Analyze ──
    print("\n[4/8] Running analysis on all games...")
    analyses = [analyze_game(g) for g in merged]

    # ── Step 5: Generate Pick Card ──
    print("\n[5/8] Generating pick card...")
    pick_card = generate_pick_card(analyses)

    # ── Step 5.5: Apply Confidence Decay ──
    print("\n[5.5/8] Applying confidence decay...")
    decay_engine = ConfidenceDecayEngine()
    
    # Collect all picks with tier info
    all_picks = []
    for tier_key in ["tier1", "tier2", "leans"]:
        for pick in pick_card.get(tier_key, []):
            # Add timestamp if not present
            if "timestamp" not in pick:
                pick["timestamp"] = datetime.now().isoformat()
            all_picks.append(pick)
    
    # Apply decay
    if all_picks:
        decayed_picks = decay_engine.apply_decay_to_slate(all_picks)
        
        # Reorganize picks by updated tier
        pick_card["tier1"] = [p for p in decayed_picks if p.get("current_tier") == "TIER1"]
        pick_card["tier2"] = [p for p in decayed_picks if p.get("current_tier") == "TIER2"]
        pick_card["leans"] = [p for p in decayed_picks if p.get("current_tier") == "LEAN"]
        pick_card["passes"] = [p for p in decayed_picks if p.get("current_tier") == "PASS"]
        
        # Update summary
        pick_card["summary"]["tier1_plays"] = len(pick_card["tier1"])
        pick_card["summary"]["tier2_plays"] = len(pick_card["tier2"])
        pick_card["summary"]["leans"] = len(pick_card["leans"])
        pick_card["summary"]["passes"] = len(pick_card["passes"])
        
        # Log promotions/demotions
        for pick in decayed_picks:
            if "status_change" in pick:
                print(f"  {pick['status_change']}: {pick.get('game', '?')}")
    
    print(f"  Processed {len(all_picks)} picks through decay engine")

    # ── Step 6/10: Quarter-Line Sensitivity ──
    print("\n[6/10] Scanning for quarter-line mismatches...")
    quarter_detector = QuarterLineDetector()
    quarter_warnings = []
    for pick in all_picks:
        game = pick.get("game", "")
        if any(qt in pick.get("pick_type", "").upper() for qt in ["Q1", "1Q", "HALF", "1H", "2H"]):
            result = quarter_detector.detect(
                game_key=game,
                full_game_open=pick.get("total_open", 220),
                full_game_current=pick.get("total_current", 220),
                quarter_open=pick.get("quarter_open"),
                quarter_current=pick.get("quarter_current"),
            )
            if result.signal.value != "NONE":
                quarter_warnings.append({"game": game, "result": result})
                pick["quarter_warning"] = result.recommendation
                print(f"  ⚠ {game}: {result.recommendation}")
    if not quarter_warnings:
        print("  No quarter-line mismatches detected")

    # ── Step 7/10: Star Absence Detection ──
    print("\n[7/10] Scanning for star absences (ESPN injuries)...")
    star_detector = StarAbsenceDetector()
    star_results = star_detector.analyze_slate(games)
    star_warnings = [r for r in star_results if r.signal.value != "NONE"]
    for sw in star_warnings:
        out_names = ", ".join(sw.players_out)
        print(f"  ⚠ {sw.game_key}: {out_names} OUT → Under boost {sw.under_boost:+.0%}, Spread adj {sw.spread_adjustment:+.1f}")
    if not star_warnings:
        print("  No star absences detected")

    # ── Step 8/10: Evaluate Boosts ──
    if args.boosts:
        print("\n[8/10] Evaluating profit boosts...")
        evaluate_boosts(args.boosts)
    else:
        print("\n[8/10] No boosts to evaluate")

    # ── Step 9/10: Parlay Survival Status ──
    print("\n[9/10] Loading parlay tracker...")
    parlay_tracker = ParlayTracker()
    summary = parlay_tracker.get_summary()
    if summary["total_parlays"] > 0:
        parlay_tracker.print_survival_dashboard()
    else:
        print("  No active parlays tracked (add via parlay_tracker.add_parlay())")

    # ── Step 10/10: Output & Discord ──
    print("\n[10/10] Finalizing...")
    print_pick_card(pick_card)
    save_pick_card(pick_card)
    send_discord_alert(pick_card, dry_run=args.dry_run)

    print(f"\n  Nightly Ops complete at {datetime.now().strftime('%I:%M %p ET')}")
    print("  Run 'python scripts/analyze_results.py --today' tomorrow morning for autopsy.")


if __name__ == "__main__":
    main()
