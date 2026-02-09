#!/usr/bin/env python3
"""
POST-GAME AUTOPSY
==================
Runs the morning after a slate to evaluate:
  1. Win/Loss record by tier
  2. CLV accuracy (did you beat the closing line?)
  3. Signal accuracy (which signals actually worked?)
  4. Unit P&L
  5. What would have happened with different thresholds

Input:  picks JSON from data/ + final scores from ESPN (free)
Output: Detailed report + updated CLV history

Usage:
    python scripts/analyze_results.py                    # Last night
    python scripts/analyze_results.py --date 2026-02-09  # Specific date
    python scripts/analyze_results.py --all              # Full history
"""

import json
import sys
import os
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "data"

# Team name normalization for matching ESPN ↔ picks
TEAM_ABBR_MAP = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GS", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def fetch_final_scores(date_str: str) -> Dict[str, Dict]:
    """
    Fetch final scores from ESPN for a given date.
    Free API, no key needed.
    """
    # ESPN expects YYYYMMDD
    espn_date = date_str.replace("-", "")
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
        f"?dates={espn_date}"
    )

    games = {}
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for event in data.get("events", []):
            comp = event["competitions"][0]
            teams = comp.get("competitors", [])
            status = event.get("status", {}).get("type", {}).get("name", "")

            if len(teams) < 2:
                continue

            home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])

            home_name = home["team"]["displayName"]
            away_name = away["team"]["displayName"]
            home_score = int(home.get("score", 0))
            away_score = int(away.get("score", 0))

            game_key = f"{away_name} @ {home_name}"
            games[game_key] = {
                "home_team": home_name,
                "away_team": away_name,
                "home_score": home_score,
                "away_score": away_score,
                "total_score": home_score + away_score,
                "spread_result": home_score - away_score,  # positive = home won by X
                "status": status,
                "completed": status in ("STATUS_FINAL", "STATUS_FINAL_OT"),
            }

    except Exception as e:
        print(f"  ESPN fetch error: {e}")

    return games


def load_picks_for_date(date_str: str) -> List[Dict]:
    """Load picks JSON files for a given date."""
    date_compact = date_str.replace("-", "")
    all_picks = []

    for f in sorted(DATA_DIR.glob(f"picks_{date_compact}*.json")):
        try:
            with open(f) as fh:
                picks = json.load(fh)
                if isinstance(picks, list):
                    all_picks.extend(picks)
                print(f"  Loaded {f.name}: {len(picks)} picks")
        except Exception as e:
            print(f"  Failed to load {f.name}: {e}")

    return all_picks


def match_pick_to_game(pick: Dict, scores: Dict[str, Dict]) -> Optional[Dict]:
    """Match a pick to its final score using fuzzy matching."""
    pick_game = pick.get("game", "")

    # Direct match
    if pick_game in scores:
        return scores[pick_game]

    # Fuzzy match on team abbreviations
    for game_key, game_data in scores.items():
        if (any(abbr in pick_game.upper() for abbr in
                [TEAM_ABBR_MAP.get(game_data["home_team"], ""),
                 TEAM_ABBR_MAP.get(game_data["away_team"], "")]
                if abbr)):
            return game_data

    return None


def grade_pick(pick: Dict, score: Dict) -> Dict:
    """
    Grade a single pick against the final score.

    Returns enriched pick dict with grading info.
    """
    pick_str = pick.get("pick", "").upper()
    result = {**pick, "graded": True, "won": None, "margin": None,
              "final_total": score["total_score"],
              "final_spread": score["spread_result"]}

    if "UNDER" in pick_str:
        # Extract the number from "UNDER 218.5"
        try:
            line = float(pick_str.split("UNDER")[1].strip())
            result["won"] = score["total_score"] < line
            result["margin"] = line - score["total_score"]
            result["pick_type"] = "UNDER"
            result["line"] = line
        except (ValueError, IndexError):
            result["graded"] = False

    elif "OVER" in pick_str:
        try:
            line = float(pick_str.split("OVER")[1].strip())
            result["won"] = score["total_score"] > line
            result["margin"] = score["total_score"] - line
            result["pick_type"] = "OVER"
            result["line"] = line
        except (ValueError, IndexError):
            result["graded"] = False

    elif "+" in pick_str:
        # Spread pick on underdog: e.g., "MIL +10.5"
        try:
            parts = pick_str.split("+")
            team_abbr = parts[0].strip()
            spread = float(parts[1].strip())
            # Determine if the team is home or away
            if team_abbr in score.get("away_team", "").upper() or \
               TEAM_ABBR_MAP.get(score["away_team"], "").upper() == team_abbr:
                # Away team getting points
                adjusted = score["away_score"] + spread
                result["won"] = adjusted > score["home_score"]
                result["margin"] = adjusted - score["home_score"]
            else:
                # Home team getting points
                adjusted = score["home_score"] + spread
                result["won"] = adjusted > score["away_score"]
                result["margin"] = adjusted - score["away_score"]
            result["pick_type"] = "SPREAD"
            result["line"] = spread
        except (ValueError, IndexError):
            result["graded"] = False

    elif "-" in pick_str and any(c.isalpha() for c in pick_str):
        # Spread pick on favorite: e.g., "OKC -6.5"
        try:
            parts = pick_str.split("-")
            team_abbr = parts[0].strip()
            spread = float(parts[1].strip())
            if team_abbr in score.get("away_team", "").upper() or \
               TEAM_ABBR_MAP.get(score["away_team"], "").upper() == team_abbr:
                adjusted = score["away_score"] - spread
                result["won"] = adjusted > score["home_score"]
                result["margin"] = adjusted - score["home_score"]
            else:
                adjusted = score["home_score"] - spread
                result["won"] = adjusted > score["away_score"]
                result["margin"] = adjusted - score["away_score"]
            result["pick_type"] = "SPREAD"
            result["line"] = -spread
        except (ValueError, IndexError):
            result["graded"] = False

    else:
        result["graded"] = False

    return result


def generate_autopsy_report(graded_picks: List[Dict], date_str: str):
    """Generate the full autopsy report."""
    print()
    print("═" * 75)
    print(f"  📋 POST-GAME AUTOPSY — {date_str}")
    print(f"  Generated: {datetime.now().strftime('%I:%M %p ET')}")
    print("═" * 75)

    # Filter to graded picks
    graded = [p for p in graded_picks if p.get("graded") and p.get("won") is not None]
    ungraded = [p for p in graded_picks if not p.get("graded") or p.get("won") is None]

    if not graded:
        print("\n  No picks could be graded. Check if games are completed.")
        return

    # Overall record
    wins = sum(1 for p in graded if p["won"])
    losses = len(graded) - wins
    total_units_won = sum(p.get("units", 1.0) for p in graded if p["won"])
    total_units_lost = sum(p.get("units", 1.0) for p in graded if not p["won"])
    net_units = total_units_won - total_units_lost

    print(f"\n  RECORD: {wins}-{losses} ({wins/(wins+losses):.0%})")
    print(f"  UNITS:  +{total_units_won:.1f}U won / -{total_units_lost:.1f}U lost = {net_units:+.1f}U net")

    # By tier
    print(f"\n  ── BY TIER ────────────────────────────────────────────")
    tier_order = ["TIER1", "TIER2", "LEAN"]
    for tier in tier_order:
        tier_picks = [p for p in graded if p.get("tier", "").upper().replace(" ", "") == tier]
        if not tier_picks:
            continue
        tw = sum(1 for p in tier_picks if p["won"])
        tl = len(tier_picks) - tw
        tu = sum(p.get("units", 1.0) for p in tier_picks if p["won"]) - \
             sum(p.get("units", 1.0) for p in tier_picks if not p["won"])
        emoji = "🔥" if tier == "TIER1" else "📊" if tier == "TIER2" else "👀"
        print(f"  {emoji} {tier}: {tw}-{tl} ({tw/(tw+tl):.0%}) | {tu:+.1f}U")

    # By pick type
    print(f"\n  ── BY PICK TYPE ───────────────────────────────────────")
    type_groups = defaultdict(list)
    for p in graded:
        type_groups[p.get("pick_type", "UNKNOWN")].append(p)

    for ptype, picks in sorted(type_groups.items()):
        tw = sum(1 for p in picks if p["won"])
        tl = len(picks) - tw
        print(f"  {ptype}: {tw}-{tl} ({tw/(tw+tl):.0%})")

    # By signal type
    print(f"\n  ── BY SIGNAL ──────────────────────────────────────────")
    signal_stats = defaultdict(lambda: {"wins": 0, "losses": 0})
    for p in graded:
        signals = p.get("signals", p.get("signal_types", []))
        if isinstance(signals, list):
            for sig in signals:
                if isinstance(sig, str):
                    # Extract signal type from the description
                    sig_type = sig.split(":")[0].strip() if ":" in sig else sig[:20]
                    if p["won"]:
                        signal_stats[sig_type]["wins"] += 1
                    else:
                        signal_stats[sig_type]["losses"] += 1

    for sig, stats in sorted(signal_stats.items(), key=lambda x: -(x[1]["wins"] + x[1]["losses"])):
        total = stats["wins"] + stats["losses"]
        rate = stats["wins"] / total if total > 0 else 0
        bar = "█" * int(rate * 10) + "░" * (10 - int(rate * 10))
        print(f"  {sig[:30]:<30} {stats['wins']}-{stats['losses']} "
              f"{bar} {rate:.0%}")

    # Individual pick results
    print(f"\n  ── PICK-BY-PICK RESULTS ────────────────────────────────")
    for p in graded:
        icon = "✅" if p["won"] else "❌"
        units = p.get("units", 1.0)
        margin = p.get("margin", 0)
        confidence = p.get("confidence", "?")
        game = p.get("game", "?")[:35]
        pick = p.get("pick", "?")
        print(f"  {icon} {pick:<20} {game:<35} "
              f"{units:.1f}U | margin: {margin:+.1f} | conf: {confidence}%")

    # Margin analysis
    print(f"\n  ── MARGIN ANALYSIS ────────────────────────────────────")
    margins = [p["margin"] for p in graded if p.get("margin") is not None]
    if margins:
        avg_margin = sum(margins) / len(margins)
        close_calls = sum(1 for m in margins if abs(m) <= 2.0)
        blowouts = sum(1 for m in margins if abs(m) >= 10.0)
        print(f"  Average margin:    {avg_margin:+.1f} pts")
        print(f"  Close calls (±2):  {close_calls}")
        print(f"  Blowouts (10+):    {blowouts}")

    # Ungraded picks
    if ungraded:
        print(f"\n  ── UNGRADED ({len(ungraded)}) ──────────────────────────")
        for p in ungraded:
            print(f"  ⚪ {p.get('pick', '?')} — {p.get('game', '?')}")

    # What-If analysis
    print(f"\n  ── WHAT-IF ANALYSIS ───────────────────────────────────")
    tier1_only = [p for p in graded if "TIER1" in p.get("tier", "").upper().replace(" ", "")]
    if tier1_only:
        t1w = sum(1 for p in tier1_only if p["won"])
        t1l = len(tier1_only) - t1w
        t1u = sum(2.0 for p in tier1_only if p["won"]) - sum(2.0 for p in tier1_only if not p["won"])
        print(f"  If TIER1 only (2U each): {t1w}-{t1l} = {t1u:+.1f}U")

    all_at_1u = sum(1.0 for p in graded if p["won"]) - sum(1.0 for p in graded if not p["won"])
    print(f"  If all flat 1U:          {wins}-{losses} = {all_at_1u:+.1f}U")

    print("\n" + "═" * 75)

    # Save report
    report = {
        "date": date_str,
        "generated": datetime.now().isoformat(),
        "record": f"{wins}-{losses}",
        "win_rate": round(wins / (wins + losses), 3),
        "net_units": round(net_units, 1),
        "picks": graded_picks,
    }

    report_file = DATA_DIR / f"autopsy_{date_str.replace('-', '')}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Report saved: {report_file.name}")


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Post-Game Autopsy Report")
    parser.add_argument("--date", type=str, default=None,
                        help="Date to analyze (YYYY-MM-DD). Default: yesterday.")
    parser.add_argument("--today", action="store_true",
                        help="Analyze today's completed games.")
    args = parser.parse_args()

    if args.today:
        date_str = datetime.now().strftime("%Y-%m-%d")
    elif args.date:
        date_str = args.date
    else:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\n  📋 Loading data for {date_str}...")

    # Load picks
    picks = load_picks_for_date(date_str)
    if not picks:
        print(f"  No picks found for {date_str} in {DATA_DIR}")
        print(f"  Looking for: picks_{date_str.replace('-', '')}*.json")
        return

    # Fetch final scores
    print(f"  Fetching final scores from ESPN (free)...")
    scores = fetch_final_scores(date_str)
    if not scores:
        print(f"  No scores found for {date_str}. Games may not be completed yet.")
        return

    print(f"  Found {len(scores)} completed games.")

    # Grade each pick
    graded = []
    for pick in picks:
        score = match_pick_to_game(pick, scores)
        if score and score.get("completed"):
            graded.append(grade_pick(pick, score))
        else:
            graded.append({**pick, "graded": False, "won": None})

    # Generate report
    generate_autopsy_report(graded, date_str)


if __name__ == "__main__":
    main()
