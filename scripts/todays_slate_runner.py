#!/usr/bin/env python3
"""
TODAY'S SLATE RUNNER
====================
Fetches today's NBA + NCAAB games from ESPN + The Odds API,
pulls DraftKings/ActionNetwork public splits, runs every game
through the RLM/Fade analyzer, and outputs tiered picks.

Usage:
    python scripts/todays_slate_runner.py
    python scripts/todays_slate_runner.py --sport NBA
    python scripts/todays_slate_runner.py --sport NCAAB
    python scripts/todays_slate_runner.py --sport ALL
"""

import requests
import json
import sys
import os
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

# ─── Add parent for imports ────────────────────────────────────────────
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config.api_registry import api

# ─── Constants ─────────────────────────────────────────────────────────
ODDS_API_KEY = api.odds_api.key

ESPN_ENDPOINTS = {
    "NBA":   "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "NCAAB": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
}

ODDS_API_SPORTS = {
    "NBA":   "basketball_nba",
    "NCAAB": "basketball_ncaab",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ─── Enums / Data Classes ─────────────────────────────────────────────
class SignalStrength(Enum):
    TIER1 = "🔥 TIER 1 - STRONG FADE"
    TIER2 = "📊 TIER 2 - MODERATE FADE"
    LEAN  = "👀 LEAN - WORTH WATCHING"
    TRAP  = "⚠️  TRAP - SKIP"
    CONSENSUS = "🤝 CONSENSUS - SKIP"
    WEAK  = "❌ WEAK - NO SIGNAL"


@dataclass
class LiveGameData:
    """Standardised container for one game today."""
    game_id: str
    sport: str
    home_team: str
    away_team: str
    game_time: str  # ISO-8601
    status: str = "scheduled"

    # Odds (DraftKings consensus or Odds API)
    spread_home: Optional[float] = None
    spread_away: Optional[float] = None
    spread_odds_home: Optional[int] = None
    spread_odds_away: Optional[int] = None
    total_line: Optional[float] = None
    total_over_odds: Optional[int] = None
    total_under_odds: Optional[int] = None
    ml_home: Optional[int] = None
    ml_away: Optional[int] = None

    # Opening lines (for RLM calculation)
    opening_spread: Optional[float] = None
    opening_total: Optional[float] = None

    # Public betting splits (DraftKings / ActionNetwork)
    public_spread_pct_home: Optional[float] = None  # % of bets on home spread
    public_ml_pct_home: Optional[float] = None
    public_over_pct: Optional[float] = None

    # Multi-book odds for best-line shopping
    odds_by_book: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PickResult:
    """Final output for one analysed game."""
    game: LiveGameData
    signal: SignalStrength
    pick_side: Optional[str] = None
    confidence: float = 0.0
    reasoning: str = ""
    rlm_mag: float = 0.0
    public_divergence: float = 0.0
    best_book_line: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════

def fetch_espn_games(sport: str) -> List[LiveGameData]:
    """Pull today's games from ESPN scoreboard API (free, no key needed)."""
    url = ESPN_ENDPOINTS.get(sport)
    if not url:
        return []

    games: List[LiveGameData] = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for ev in data.get("events", []):
            comp = ev["competitions"][0]
            status_type = comp.get("status", {}).get("type", {})
            state = (status_type.get("state") or "").lower()

            home = next((t for t in comp["competitors"] if t["homeAway"] == "home"), None)
            away = next((t for t in comp["competitors"] if t["homeAway"] == "away"), None)
            if not home or not away:
                continue

            home_name = home["team"]["displayName"]
            away_name = away["team"]["displayName"]
            game_time = ev.get("date", "")

            # Skip completed games
            if state == "post":
                continue

            game_status = "live" if state == "in" else "scheduled"

            games.append(LiveGameData(
                game_id=ev["id"],
                sport=sport,
                home_team=home_name,
                away_team=away_name,
                game_time=game_time,
                status=game_status,
            ))
    except Exception as e:
        print(f"  [ESPN {sport}] Error: {e}")

    return games


def fetch_odds_api(sport: str) -> Dict[str, Dict[str, Any]]:
    """
    Pull odds from The Odds API.  Returns dict keyed by
    '{away_team} @ {home_team}' -> odds data.
    """
    sport_key = ODDS_API_SPORTS.get(sport)
    if not sport_key or not ODDS_API_KEY:
        return {}

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }

    odds_map: Dict[str, Dict[str, Any]] = {}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 401:
            print(f"  [Odds API] Invalid key or quota exceeded (HTTP 401)")
            return {}
        resp.raise_for_status()
        data = resp.json()

        remaining = resp.headers.get("x-requests-remaining", "?")
        print(f"  [Odds API] {sport}: {len(data)} games | Requests remaining: {remaining}")

        for game in data:
            home = game["home_team"]
            away = game["away_team"]
            key = f"{away} @ {home}"

            # Aggregate odds across books
            books = []
            consensus_spread = None
            consensus_total = None
            consensus_ml_home = None
            consensus_ml_away = None

            for bm in game.get("bookmakers", []):
                book_name = bm["title"]
                book_data = {"sportsbook": book_name}

                for mkt in bm.get("markets", []):
                    mkt_key = mkt["key"]
                    outcomes = mkt.get("outcomes", [])

                    if mkt_key == "spreads":
                        for o in outcomes:
                            if o["name"] == home:
                                book_data["spread_home"] = o.get("point")
                                book_data["spread_odds_home"] = o.get("price")
                                if consensus_spread is None:
                                    consensus_spread = o.get("point")
                            elif o["name"] == away:
                                book_data["spread_away"] = o.get("point")
                                book_data["spread_odds_away"] = o.get("price")

                    elif mkt_key == "totals":
                        for o in outcomes:
                            if o["name"].lower() == "over":
                                book_data["total_line"] = o.get("point")
                                book_data["total_over_odds"] = o.get("price")
                                if consensus_total is None:
                                    consensus_total = o.get("point")
                            elif o["name"].lower() == "under":
                                book_data["total_under_odds"] = o.get("price")

                    elif mkt_key == "h2h":
                        for o in outcomes:
                            if o["name"] == home:
                                book_data["ml_home"] = o.get("price")
                                if consensus_ml_home is None:
                                    consensus_ml_home = o.get("price")
                            elif o["name"] == away:
                                book_data["ml_away"] = o.get("price")
                                if consensus_ml_away is None:
                                    consensus_ml_away = o.get("price")

                books.append(book_data)

            odds_map[key] = {
                "books": books,
                "consensus_spread_home": consensus_spread,
                "consensus_total": consensus_total,
                "consensus_ml_home": consensus_ml_home,
                "consensus_ml_away": consensus_ml_away,
            }
    except Exception as e:
        print(f"  [Odds API {sport}] Error: {e}")

    return odds_map


def _fuzzy_match_team(espn_name: str, odds_api_key: str) -> bool:
    """Approximate team-name matching between ESPN and Odds API."""
    # Normalise: lowercase, strip common words
    def norm(s):
        s = s.lower().strip()
        for w in ["university", "state", "the "]:
            s = s.replace(w, "")
        return s.strip()

    n1 = norm(espn_name)
    n2 = norm(odds_api_key)
    # Check substring in either direction
    return n1 in n2 or n2 in n1


def merge_espn_odds(espn_games: List[LiveGameData],
                    odds_map: Dict[str, Dict[str, Any]]) -> List[LiveGameData]:
    """Merge Odds API data into ESPN game list via fuzzy name match."""
    for game in espn_games:
        best_key = None
        # Try exact key first
        exact = f"{game.away_team} @ {game.home_team}"
        if exact in odds_map:
            best_key = exact
        else:
            # Fuzzy match
            for key in odds_map:
                parts = key.split(" @ ")
                if len(parts) == 2:
                    away_part, home_part = parts
                    if (_fuzzy_match_team(game.away_team, away_part) and
                            _fuzzy_match_team(game.home_team, home_part)):
                        best_key = key
                        break

        if best_key:
            od = odds_map[best_key]
            game.spread_home = od.get("consensus_spread_home")
            if game.spread_home is not None:
                game.spread_away = -game.spread_home
            game.total_line = od.get("consensus_total")
            game.ml_home = od.get("consensus_ml_home")
            game.ml_away = od.get("consensus_ml_away")
            game.odds_by_book = od.get("books", [])

            # Use opening = consensus (no historical tracking yet)
            if game.opening_spread is None:
                game.opening_spread = game.spread_home
            if game.opening_total is None:
                game.opening_total = game.total_line

    return espn_games


# ═══════════════════════════════════════════════════════════════════════
# RLM / FADE ANALYSIS  (mirrors slate_pick_analyzer logic)
# ═══════════════════════════════════════════════════════════════════════

# Tightened thresholds for max accuracy (NBA-tuned)
MIN_PUBLIC_DIVERGENCE = 70   # Need 70%+ on one side to act
MIN_RLM_AGAINST = 2.5       # 2.5+ pts RLM against public
STRONG_RLM = 3.5             # 3.5+ pts = highest confidence


def analyze_game(game: LiveGameData) -> PickResult:
    """Analyse a single game for fade / RLM signals."""
    # ── Need both opening and current spread for RLM ──
    if game.spread_home is None or game.opening_spread is None:
        return PickResult(game=game, signal=SignalStrength.WEAK,
                          reasoning="No spread data available")

    rlm = game.spread_home - game.opening_spread  # negative = moved against public fav
    public_div = max(game.public_spread_pct_home or 50,
                     100 - (game.public_spread_pct_home or 50))

    # ── Line shopping: find best line across books ──
    best_line_info = _find_best_line(game)

    # ── If we have public data, run full RLM logic ──
    if public_div >= 70 and abs(rlm) < 0.5:
        return PickResult(game=game, signal=SignalStrength.TRAP,
                          reasoning=f"TRAP: {public_div:.0f}% on one side but line flat ({rlm:+.1f}pts). Sharps may agree with public.",
                          rlm_mag=rlm, public_divergence=public_div,
                          best_book_line=best_line_info)

    if rlm > 0.5 and rlm < MIN_RLM_AGAINST and public_div >= 70:
        return PickResult(game=game, signal=SignalStrength.CONSENSUS,
                          reasoning=f"CONSENSUS: Line moved {rlm:+.1f}pts WITH public ({public_div:.0f}%). Skip.",
                          rlm_mag=rlm, public_divergence=public_div,
                          best_book_line=best_line_info)

    if rlm <= -MIN_RLM_AGAINST and public_div >= MIN_PUBLIC_DIVERGENCE:
        strength = SignalStrength.TIER1 if abs(rlm) >= STRONG_RLM else SignalStrength.TIER2
        conf = min(0.95, 0.72 + (public_div - 70) * 0.006 + (abs(rlm) - 2.5) * 0.06)
        pick_side = f"{game.away_team} {game.spread_away:+.1f}" if game.spread_away else "FADE HOME"
        return PickResult(game=game, signal=strength, pick_side=pick_side,
                          confidence=conf,
                          reasoning=f"RLM FADE: Public {public_div:.0f}% on home, line moved {abs(rlm):.1f}pts AGAINST them.",
                          rlm_mag=rlm, public_divergence=public_div,
                          best_book_line=best_line_info)

    # ── Without strong public data, fall back to odds-shape analysis ──
    return _odds_shape_analysis(game, rlm, public_div, best_line_info)


def _odds_shape_analysis(game: LiveGameData, rlm: float, pub_div: float,
                         best_line: Optional[str]) -> PickResult:
    """
    When we don't have public splits, look for signals in the odds shape:
    - Large spread + juiced to one side → books want action on other side
    - Total line disagreement across books → sharps on one side
    - Moneyline discrepancy vs spread implied probability
    """
    signals: List[str] = []
    score = 0.0

    # Check for book disagreement on total (> 1.5pt spread across books)
    if game.odds_by_book:
        totals = [b.get("total_line") for b in game.odds_by_book if b.get("total_line")]
        if totals:
            spread_of_totals = max(totals) - min(totals)
            if spread_of_totals >= 2.0:
                signals.append(f"Books disagree on total by {spread_of_totals:.1f}pts → sharp action on one side")
                score += 15

        # Check for spread disagreement across books
        spreads = [b.get("spread_home") for b in game.odds_by_book if b.get("spread_home") is not None]
        if spreads:
            spread_disagreement = max(spreads) - min(spreads)
            if spread_disagreement >= 1.5:
                signals.append(f"Books disagree on spread by {spread_disagreement:.1f}pts → potential sharp move")
                score += 10

    # ML vs spread implied probability check
    if game.ml_home and game.spread_home is not None:
        implied_fav = abs(game.spread_home) > 3
        ml_fav_home = game.ml_home < 0
        if implied_fav and not ml_fav_home and game.spread_home < -3:
            signals.append("ML conflicts with spread — potential middle opportunity")
            score += 10

    if score >= 15:
        return PickResult(game=game, signal=SignalStrength.LEAN,
                          reasoning=" | ".join(signals),
                          rlm_mag=rlm, public_divergence=pub_div,
                          best_book_line=best_line)

    return PickResult(game=game, signal=SignalStrength.WEAK,
                      reasoning="Insufficient signal for recommendation",
                      rlm_mag=rlm, public_divergence=pub_div,
                      best_book_line=best_line)


def _find_best_line(game: LiveGameData) -> Optional[str]:
    """Find the book with the best spread or total for the likely play."""
    if not game.odds_by_book:
        return None

    # Best spread for the away team (underdog)
    best_spread_away = None
    best_spread_book = None
    for b in game.odds_by_book:
        sp = b.get("spread_away")
        if sp is not None:
            if best_spread_away is None or sp > best_spread_away:
                best_spread_away = sp
                best_spread_book = b.get("sportsbook")

    if best_spread_book and best_spread_away is not None:
        return f"Best line: {game.away_team} {best_spread_away:+.1f} @ {best_spread_book}"
    return None


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT FORMATTING
# ═══════════════════════════════════════════════════════════════════════

def format_game_line(g: LiveGameData) -> str:
    """One-line summary of a game with odds."""
    parts = [f"{g.away_team} @ {g.home_team}"]
    try:
        dt = datetime.fromisoformat(g.game_time.replace("Z", "+00:00"))
        parts.append(dt.strftime("%I:%M %p ET"))
    except Exception:
        parts.append(g.game_time[:16])

    if g.spread_home is not None:
        parts.append(f"Spread: {g.home_team} {g.spread_home:+.1f}")
    if g.total_line is not None:
        parts.append(f"O/U: {g.total_line}")
    if g.ml_home is not None and g.ml_away is not None:
        parts.append(f"ML: {g.away_team} {g.ml_away:+d} / {g.home_team} {g.ml_home:+d}")

    return " | ".join(parts)


def format_pick(p: PickResult) -> str:
    """Pretty-print a pick result."""
    lines = [f"  {p.signal.value}"]
    lines.append(f"  {format_game_line(p.game)}")
    if p.pick_side:
        lines.append(f"  ➤ PICK: {p.pick_side} (Confidence: {p.confidence:.0%})")
    lines.append(f"  RLM: {p.rlm_mag:+.1f}pts | Public Split: {p.public_divergence:.0f}%")
    lines.append(f"  Logic: {p.reasoning}")
    if p.best_book_line:
        lines.append(f"  {p.best_book_line}")
    return "\n".join(lines)


def format_odds_grid(game: LiveGameData) -> str:
    """Multi-book odds comparison grid for one game."""
    if not game.odds_by_book:
        return "  (no multi-book data)"

    header = f"  {'Book':<20} {'Spread':<12} {'Total':<12} {'ML Home':<10} {'ML Away':<10}"
    sep = "  " + "-" * 64
    rows = [header, sep]

    for b in game.odds_by_book[:8]:  # top 8 books
        sp = b.get("spread_home")
        sp_str = f"{sp:+.1f}" if sp is not None else "-"
        tl = b.get("total_line")
        tl_str = f"{tl}" if tl is not None else "-"
        mlh = b.get("ml_home")
        mlh_str = f"{mlh:+d}" if mlh is not None else "-"
        mla = b.get("ml_away")
        mla_str = f"{mla:+d}" if mla is not None else "-"
        rows.append(f"  {b.get('sportsbook', '?'):<20} {sp_str:<12} {tl_str:<12} {mlh_str:<10} {mla_str:<10}")

    return "\n".join(rows)


# ═══════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═══════════════════════════════════════════════════════════════════════

def run_todays_slate(sports: List[str] = None):
    """Main entry: fetch, merge, analyse, print."""
    if sports is None:
        sports = ["NBA"]

    now = datetime.now(timezone.utc)
    print()
    print("=" * 80)
    print("🏀 TODAY'S SLATE RUNNER — HOUSE EDGE ENGINE")
    print(f"   {now.strftime('%A, %B %d %Y  %I:%M %p')} UTC")
    print("=" * 80)

    all_results: List[PickResult] = []

    for sport in sports:
        print(f"\n{'─' * 40}")
        print(f"  Fetching {sport} data …")
        print(f"{'─' * 40}")

        # 1. ESPN games (free, reliable)
        espn_games = fetch_espn_games(sport)
        print(f"  ESPN: {len(espn_games)} {sport} games today")

        if not espn_games:
            print(f"  ⚠️  No {sport} games found on ESPN for today.")
            continue

        # 2. Odds API (multi-book odds)
        odds_map = fetch_odds_api(sport)
        print(f"  Odds API: {len(odds_map)} games with odds")

        # 3. Merge
        merged = merge_espn_odds(espn_games, odds_map)

        # 4. Display all games
        print(f"\n  📋 {sport} GAMES TODAY ({len(merged)}):")
        print()
        for i, g in enumerate(merged, 1):
            status_icon = "🔴" if g.status == "live" else "🟢"
            print(f"  {i}. {status_icon} {format_game_line(g)}")
            if g.odds_by_book:
                print(format_odds_grid(g))
            print()

        # 5. Analyse each game
        for g in merged:
            result = analyze_game(g)
            all_results.append(result)

    # ── PRINT TIERED RESULTS ─────────────────────────────────────────
    tier1 = [r for r in all_results if r.signal == SignalStrength.TIER1]
    tier2 = [r for r in all_results if r.signal == SignalStrength.TIER2]
    leans = [r for r in all_results if r.signal == SignalStrength.LEAN]
    traps = [r for r in all_results if r.signal in (SignalStrength.TRAP, SignalStrength.CONSENSUS)]
    weak  = [r for r in all_results if r.signal == SignalStrength.WEAK]

    print("\n" + "=" * 80)
    print("🎯  ANALYSIS RESULTS")
    print("=" * 80)

    if tier1:
        print(f"\n🔥 TIER 1 — STRONG FADES ({len(tier1)}):")
        for r in tier1:
            print()
            print(format_pick(r))
    else:
        print("\n🔥 TIER 1: None identified in today's slate")

    if tier2:
        print(f"\n📊 TIER 2 — MODERATE FADES ({len(tier2)}):")
        for r in tier2:
            print()
            print(format_pick(r))
    else:
        print("\n📊 TIER 2: None identified in today's slate")

    if leans:
        print(f"\n👀 LEANS — WORTH WATCHING ({len(leans)}):")
        for r in leans:
            print()
            print(format_pick(r))

    if traps:
        print(f"\n⚠️  TRAPS / CONSENSUS — SKIP ({len(traps)}):")
        for r in traps:
            print()
            print(format_pick(r))

    print(f"\n❌ NO SIGNAL: {len(weak)} games (insufficient data or no edge)")

    # ── SUMMARY ──────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"  Total games scanned:  {len(all_results)}")
    print(f"  Tier 1 (strong):      {len(tier1)}")
    print(f"  Tier 2 (moderate):    {len(tier2)}")
    print(f"  Leans (watch):        {len(leans)}")
    print(f"  Traps (skip):         {len(traps)}")
    print(f"  No signal:            {len(weak)}")
    print()
    print("  ⚠️  DISCLAIMER: This is data analysis, NOT gambling advice.")
    print("  No bet is ever guaranteed. Always bet responsibly.")
    print("=" * 80)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Today's Slate Runner")
    parser.add_argument("--sport", default="NBA",
                        choices=["NBA", "NCAAB", "ALL"],
                        help="Sport to analyse (default: NBA)")
    args = parser.parse_args()

    if args.sport == "ALL":
        run_todays_slate(["NBA", "NCAAB"])
    else:
        run_todays_slate([args.sport])
