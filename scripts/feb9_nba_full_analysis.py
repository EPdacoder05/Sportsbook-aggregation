#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
 FEBRUARY 9, 2026 — FULL NBA SLATE ANALYSIS
 Data Sources: DraftKings splits, Covers consensus, ActionNetwork lines,
               The Odds API multi-book, opening line movement
═══════════════════════════════════════════════════════════════════════════

 Methodology (HOUSE EDGE):
 1. RLM (Reverse Line Movement) — line moves AGAINST the public side
 2. Sharp/Whale divergence — DK % of bets ≠ % of money
 3. Book disagreement — when books differ by 1.5+ pts, sharps are moving
 4. Opening-to-current line delta — tracks where sharp money pushed
 5. Cross-source consensus check — DK splits vs Covers vs line shape

 ⚠️ DISCLAIMER: Data analysis only. Not gambling advice. No bet is
 guaranteed. Practice smart bankroll management (1U = 1% bankroll).
═══════════════════════════════════════════════════════════════════════════
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
from datetime import datetime


# ─── Signal Strength ───────────────────────────────────────────────────
class Signal(Enum):
    TIER1  = "🔥🔥🔥 TIER 1 — STRONG SIGNAL"
    TIER2  = "🔥 TIER 2 — MODERATE SIGNAL"
    LEAN   = "👀 LEAN — WORTH WATCHING"
    TRAP   = "⚠️  TRAP — PUBLIC CONSENSUS (SKIP)"
    FLAT   = "➖ FLAT — NO EDGE DETECTED"


# ─── Data Container ────────────────────────────────────────────────────
@dataclass
class GameSlate:
    matchup: str
    time_et: str
    away: str
    home: str

    # Spread
    open_spread: float          # Opening home spread (negative = home fav)
    current_spread: float       # Current consensus home spread
    best_spread_away: float     # Best available line for away team
    best_spread_book: str

    # Totals
    open_total: float
    current_total: float
    best_over_total: Optional[float] = None
    best_over_book: Optional[str] = None
    best_under_total: Optional[float] = None
    best_under_book: Optional[str] = None

    # DraftKings public splits (% of BETS, not money)
    dk_ml_away_pct: float = 50
    dk_ml_home_pct: float = 50
    dk_spread_away_pct: float = 50
    dk_spread_home_pct: float = 50
    dk_over_pct: float = 50
    dk_under_pct: float = 50

    # Covers consensus (separate source — usually ticket-based)
    covers_away_pct: float = 50
    covers_home_pct: float = 50

    # ATS records
    away_ats: str = ""
    home_ats: str = ""
    away_last10: str = ""
    home_last10: str = ""

    # Book spread range (disagreement detector)
    spread_range: List[float] = field(default_factory=list)
    total_range: List[float] = field(default_factory=list)

    # Notes
    notes: str = ""


# ═══════════════════════════════════════════════════════════════════════
# TODAY'S DATA — EXTRACTED FROM SCREENSHOTS
# Sources: DraftKings, Covers.com, ActionNetwork/OddsAPI line movement
# ═══════════════════════════════════════════════════════════════════════

GAMES = [
    GameSlate(
        matchup="Detroit Pistons @ Charlotte Hornets",
        time_et="7:00 PM", away="DET", home="CHA",
        open_spread=2.5,    # CHA +2.5 open (DET favored)
        current_spread=2.5, # CHA +2.5 to +3.0 current
        best_spread_away=-2.5, best_spread_book="DraftKings/Caesars/bet365",
        open_total=223.0, current_total=222.5,
        best_over_total=223.5, best_over_book="BetMGM",
        best_under_total=222.5, best_under_book="FanDuel/DK",
        dk_ml_away_pct=62, dk_ml_home_pct=38,
        dk_spread_away_pct=68, dk_spread_home_pct=32,
        dk_over_pct=70, dk_under_pct=30,
        covers_away_pct=56, covers_home_pct=44,
        away_ats="27-23-1", home_ats="32-21-0",
        away_last10="7-3", home_last10="7-3 (0 ATS)",
        spread_range=[-2.5, -2.5, -2.5, -3.0, -2.5, -3.0],
        total_range=[223.5, 223.0, 223.0, 222.5, 222.5, 222.5],
        notes="CHA on insane win streak. Jalen Duren (DET) on injury report. Cade MVP candidate."
    ),
    GameSlate(
        matchup="Milwaukee Bucks @ Orlando Magic",
        time_et="7:30 PM", away="MIL", home="ORL",
        open_spread=-9.5,    # ORL -9.5 open
        current_spread=-10.5, # Moved to ORL -10.5 to -11.0
        best_spread_away=11.0, best_spread_book="bet365/BetOnline",
        open_total=218.5, current_total=220.0,
        best_over_total=220.5, best_over_book="BetMGM/Fanatics",
        best_under_total=219.5, best_under_book="FanDuel/DK",
        dk_ml_away_pct=16, dk_ml_home_pct=84,
        dk_spread_away_pct=64, dk_spread_home_pct=36,
        dk_over_pct=69, dk_under_pct=31,
        covers_away_pct=67, covers_home_pct=33,
        away_ats="22-28-0", home_ats="11-13-0",
        away_last10="4-6", home_last10="4-6",
        spread_range=[-10.5, -11.0, -11.0, -11.0, -10.5, -11.0],
        total_range=[220.5, 220.0, 220.0, 219.5, 219.5, 220.5],
        notes="MIL without roster. ORL 16-8 Home. 84% ML on ORL but 64% spread on MIL+10.5."
    ),
    GameSlate(
        matchup="Utah Jazz @ Miami Heat",
        time_et="7:30 PM", away="UTA", home="MIA",
        open_spread=-8.5,    # MIA -8.5 open
        current_spread=-7.5, # Moved to MIA -7.5 (line came DOWN)
        best_spread_away=7.5, best_spread_book="Multiple (consensus)",
        open_total=244.5, current_total=240.5,
        best_over_total=240.5, best_over_book="FanDuel/DK",
        best_under_total=240.0, best_under_book="Caesars/bet365",
        dk_ml_away_pct=21, dk_ml_home_pct=79,
        dk_spread_away_pct=54, dk_spread_home_pct=46,
        dk_over_pct=39, dk_under_pct=61,
        covers_away_pct=40, covers_home_pct=60,
        away_ats="14-12-0", home_ats="31-22-1",
        away_last10="2-8", home_last10="5-5 (6-4 ATS)",
        spread_range=[-7.5, -7.5, -7.5, -7.5, -7.5, -7.5],
        total_range=[240.5, 240.0, 240.0, 240.5, 240.5, 240.5],
        notes="Total dropped 4 FULL POINTS from 244.5 open. 79% ML on MIA but spread moved FROM MIA (RLM?)."
    ),
    GameSlate(
        matchup="Chicago Bulls @ Brooklyn Nets",
        time_et="7:30 PM", away="CHI", home="BKN",
        open_spread=-3.0,    # CHI -3.0 open (from Covers)
        current_spread=-4.0, # Moved to CHI -4.0 to -4.5
        best_spread_away=-3.5, best_spread_book="DraftKings",
        open_total=223.5, current_total=218.5,
        best_over_total=219.5, best_over_book="FanDuel",
        best_under_total=218.5, best_under_book="Multiple (consensus)",
        dk_ml_away_pct=77, dk_ml_home_pct=23,
        dk_spread_away_pct=68, dk_spread_home_pct=32,
        dk_over_pct=64, dk_under_pct=36,
        covers_away_pct=74, covers_home_pct=26,
        away_ats="11-15-0 Road", home_ats="24-28-1",
        away_last10="3-7", home_last10="2-8",
        spread_range=[-4.5, -4.0, -4.0, -4.0, -3.5, -4.5],
        total_range=[218.5, 218.5, 218.5, 219.5, 218.5, 218.5],
        notes="TOTAL DROPPED 5 FULL POINTS (223.5→218.5). 64% public on Over but sharps CRUSHED the Under."
    ),
    GameSlate(
        matchup="Sacramento Kings @ New Orleans Pelicans",
        time_et="8:00 PM", away="SAC", home="NO",
        open_spread=-6.0,    # NO -6.0 open
        current_spread=-7.5, # Moved to NO -7.5 to -8.0
        best_spread_away=7.5, best_spread_book="FanDuel (NOP -7.5 -112)",
        open_total=233.5, current_total=231.5,
        best_over_total=231.5, best_over_book="BetMGM (-102)",
        best_under_total=231.5, best_under_book="DraftKings (-115)",
        dk_ml_away_pct=28, dk_ml_home_pct=72,
        dk_spread_away_pct=53, dk_spread_home_pct=47,
        dk_over_pct=48, dk_under_pct=52,
        covers_away_pct=45, covers_home_pct=55,
        away_ats="20-32-2 (9-16 Road)", home_ats="29-25-0 (16-11 Home)",
        away_last10="0-10 ATS", home_last10="4-6",
        spread_range=[-7.5, -8.0, -8.0, -7.5, -7.5, -8.0],
        total_range=[231.5, 231.5, 231.5, 231.5, 231.5, 231.5],
        notes="SAC 0-10 ATS last 10! 3-23 Road record. NO 8-19 Home W/L but 16-11 Home ATS."
    ),
    GameSlate(
        matchup="Atlanta Hawks @ Minnesota Timberwolves",
        time_et="8:00 PM", away="ATL", home="MIN",
        open_spread=-6.5,    # MIN -6.5 open
        current_spread=-7.5, # Moved to MIN -7.5
        best_spread_away=7.5, best_spread_book="bet365/FanDuel",
        open_total=236.0, current_total=237.5,
        best_over_total=239.0, best_over_book="Fanatics",
        best_under_total=237.5, best_under_book="FanDuel",
        dk_ml_away_pct=18, dk_ml_home_pct=82,
        dk_spread_away_pct=49, dk_spread_home_pct=51,
        dk_over_pct=44, dk_under_pct=56,
        covers_away_pct=58, covers_home_pct=42,
        away_ats="26-28-0 (17-12 Road)", home_ats="23-31-0",
        away_last10="6-4", home_last10="5-5",
        spread_range=[-7.5, -7.5, -7.5, -7.5, -6.5, -7.5],
        total_range=[238.0, 237.5, 237.5, 237.5, 238.0, 239.0],
        notes="Covers has ATL 58% — public AGAINST the favorite. DK has MIN 82% ML. Divergence between sources."
    ),
    GameSlate(
        matchup="Cleveland Cavaliers @ Denver Nuggets",
        time_et="9:00 PM", away="CLE", home="DEN",
        open_spread=-1.0,    # DEN -1.0 open (CLE slight road dog)
        current_spread=-1.0, # Flat at DEN -1.0 to -1.5
        best_spread_away=1.5, best_spread_book="BetMGM/Caesars/FanDuel",
        open_total=234.0, current_total=239.5,
        best_over_total=239.5, best_over_book="Multiple",
        best_under_total=239.0, best_under_book="Fanatics",
        dk_ml_away_pct=45, dk_ml_home_pct=55,
        dk_spread_away_pct=47, dk_spread_home_pct=53,
        dk_over_pct=62, dk_under_pct=38,
        covers_away_pct=41, covers_home_pct=59,
        away_ats="21-32-0 (12-13 Road)", home_ats="31-22-0 (12-12 Home)",
        away_last10="8-2", home_last10="5-5 (6-4 ATS)",
        spread_range=[-1.5, -1.0, -1.0, -1.0, -1.5, -1.0],
        total_range=[239.5, 239.5, 239.5, 239.5, 239.5, 239.0],
        notes="Harden trade to CLE. CLE 8-2 L10. Jokic probable, Jamal Murray on injury report. Total UP 5.5 pts from 234→239.5."
    ),
    GameSlate(
        matchup="Oklahoma City Thunder @ Los Angeles Lakers",
        time_et="10:00 PM", away="OKC", home="LAL",
        open_spread=-4.0,    # OKC -4.0 open
        current_spread=-6.5, # Moved to OKC -6.5 to -7.5
        best_spread_away=-6.5, best_spread_book="FanDuel",
        open_total=220.0, current_total=223.0,
        best_over_total=223.5, best_over_book="BetMGM/DK/Fanatics",
        best_under_total=222.5, best_under_book="FanDuel",
        dk_ml_away_pct=61, dk_ml_home_pct=39,
        dk_spread_away_pct=43, dk_spread_home_pct=57,
        dk_over_pct=66, dk_under_pct=34,
        covers_away_pct=54, covers_home_pct=46,
        away_ats="25-27-1 (12-12 Road)", home_ats="28-22-1 (12-9 Home)",
        away_last10="5-5 (4-5 ATS)", home_last10="7-3 (7-3 ATS)",
        spread_range=[-6.5, -7.0, -7.0, -6.5, -7.5, -7.0],
        total_range=[223.5, 223.0, 223.0, 222.5, 223.5, 223.5],
        notes="LINE MOVED 2.5-3.5 PTS from -4 to -6.5/-7.5. 57% public on LAL spread but line moved AGAINST them. SHARP MONEY ON OKC."
    ),
    GameSlate(
        matchup="Memphis Grizzlies @ Golden State Warriors",
        time_et="10:00 PM", away="MEM", home="GS",
        open_spread=-7.5,    # GS -7.5 open
        current_spread=-9.5, # Moved to GS -9.0 to -9.5
        best_spread_away=9.5, best_spread_book="Caesars/bet365",
        open_total=226.0, current_total=220.5,
        best_over_total=220.5, best_over_book="BetMGM",
        best_under_total=220.5, best_under_book="Multiple",
        dk_ml_away_pct=17, dk_ml_home_pct=83,
        dk_spread_away_pct=48, dk_spread_home_pct=52,
        dk_over_pct=66, dk_under_pct=34,
        covers_away_pct=42, covers_home_pct=58,
        away_ats="22-28-1 (11-12 Road)", home_ats="24-28-1 (13-12 Home)",
        away_last10="2-8", home_last10="4-6 (4-6 ATS)",
        spread_range=[-9.5, -9.5, -9.5, -9.0, -9.5, -9.0],
        total_range=[220.5, 220.5, 220.5, 220.5, 220.5, 220.5],
        notes="TOTAL DROPPED 5.5 PTS (226→220.5). 66% public on Over but sharps DEMOLISHED the total. GS spread moved 2 pts WITH public."
    ),
    GameSlate(
        matchup="Philadelphia 76ers @ Portland Trail Blazers",
        time_et="10:00 PM", away="PHI", home="POR",
        open_spread=-2.0,    # PHI -2.0 open
        current_spread=-3.0, # Moved to PHI -3.0 to -3.5
        best_spread_away=-3.0, best_spread_book="FanDuel/bet365",
        open_total=230.5, current_total=228.5,
        best_over_total=228.5, best_over_book="BetMGM (-105)",
        best_under_total=228.0, best_under_book="Caesars/bet365",
        dk_ml_away_pct=80, dk_ml_home_pct=20,
        dk_spread_away_pct=73, dk_spread_home_pct=27,
        dk_over_pct=61, dk_under_pct=39,
        covers_away_pct=68, covers_home_pct=32,
        away_ats="17-6-1 Road (29-21-2 overall)", home_ats="28-25-0 (16-12 Home)",
        away_last10="7-3", home_last10="4-6 (4-6 ATS)",
        spread_range=[-3.5, -3.0, -3.0, -3.0, -3.5, -3.5],
        total_range=[228.5, 228.0, 228.0, 228.5, 228.5, 228.5],
        notes="PHI 80% ML + 73% spread = HEAVY public. Line moved WITH public from -2 to -3.5. Total dropped 2.5 pts against 61% Over public."
    ),
]


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════

def analyze_spread_rlm(g: GameSlate) -> Dict:
    """
    Analyze spread for RLM.
    RLM = line moves AGAINST the side receiving majority of bets.
    
    Key distinction: % of BETS ≠ % of MONEY.
    DK shows % of bets. When line moves against the bet majority,
    it means the MONEY (fewer but larger bets = whales/sharps)
    is on the other side.
    """
    # Spread movement: positive = moved toward home fav, negative = moved away
    spread_delta = g.current_spread - g.open_spread  # negative = home fav grew
    spread_delta_abs = abs(spread_delta)
    
    # Determine which side public bets are on (DK spread %)
    public_on_away = g.dk_spread_away_pct > 55
    public_on_home = g.dk_spread_home_pct > 55
    public_split_pct = max(g.dk_spread_away_pct, g.dk_spread_home_pct)
    
    # Determine line direction
    # If home was -6 and now -8, that's a 2pt move TOWARD home (they're more favored)
    # If home was -8 and now -6, that's a 2pt move AWAY from home (they're less favored)
    line_moved_toward_home = spread_delta < -0.5  # more negative = more home fav
    line_moved_toward_away = spread_delta > 0.5
    
    # RLM detection:
    # If public is on AWAY but line moved toward HOME = RLM (sharps on home)
    # If public is on HOME but line moved toward AWAY = RLM (sharps on away)
    rlm_detected = False
    rlm_side = None
    rlm_magnitude = spread_delta_abs
    
    if public_on_away and line_moved_toward_home:
        rlm_detected = True
        rlm_side = g.home
    elif public_on_home and line_moved_toward_away:
        rlm_detected = True
        rlm_side = g.away
    elif not public_on_away and not public_on_home:
        # Near 50/50 — look at Covers divergence
        if g.covers_away_pct >= 55 and line_moved_toward_home:
            rlm_detected = True
            rlm_side = g.home
        elif g.covers_home_pct >= 55 and line_moved_toward_away:
            rlm_detected = True
            rlm_side = g.away
    
    # Book disagreement
    spread_disagreement = max(g.spread_range) - min(g.spread_range) if g.spread_range else 0
    
    # Signal determination
    if rlm_detected and rlm_magnitude >= 2.5:
        signal = Signal.TIER1
    elif rlm_detected and rlm_magnitude >= 1.5:
        signal = Signal.TIER2
    elif rlm_detected and rlm_magnitude >= 0.5:
        signal = Signal.LEAN
    elif public_split_pct >= 70 and spread_delta_abs < 0.5:
        signal = Signal.TRAP  # Heavy public but line didn't move
    else:
        signal = Signal.FLAT
    
    return {
        "type": "SPREAD",
        "signal": signal,
        "rlm_detected": rlm_detected,
        "rlm_side": rlm_side,
        "rlm_magnitude": rlm_magnitude,
        "spread_delta": spread_delta,
        "public_split": public_split_pct,
        "public_dominant_side": g.away if g.dk_spread_away_pct > g.dk_spread_home_pct else g.home,
        "book_disagreement": spread_disagreement,
    }


def analyze_total_rlm(g: GameSlate) -> Dict:
    """
    Analyze total for RLM.
    If public is on Over but total DROPPED = sharps on Under (RLM).
    If public is on Under but total ROSE = sharps on Over (RLM).
    """
    total_delta = g.current_total - g.open_total  # positive = went up, negative = dropped
    total_delta_abs = abs(total_delta)
    
    public_on_over = g.dk_over_pct > 55
    public_on_under = g.dk_under_pct > 55
    public_total_pct = max(g.dk_over_pct, g.dk_under_pct)
    
    total_went_up = total_delta > 0.5
    total_went_down = total_delta < -0.5
    
    rlm_detected = False
    rlm_side = None
    
    if public_on_over and total_went_down:
        rlm_detected = True
        rlm_side = "UNDER"
    elif public_on_under and total_went_up:
        rlm_detected = True
        rlm_side = "OVER"
    
    # Signal determination
    if rlm_detected and total_delta_abs >= 4.0:
        signal = Signal.TIER1
    elif rlm_detected and total_delta_abs >= 2.5:
        signal = Signal.TIER2
    elif rlm_detected and total_delta_abs >= 1.5:
        signal = Signal.LEAN
    elif public_total_pct >= 65 and total_delta_abs < 1.0:
        signal = Signal.TRAP
    else:
        signal = Signal.FLAT
    
    # Book disagreement on total
    total_disagreement = max(g.total_range) - min(g.total_range) if g.total_range else 0
    
    return {
        "type": "TOTAL",
        "signal": signal,
        "rlm_detected": rlm_detected,
        "rlm_side": rlm_side,
        "rlm_magnitude": total_delta_abs,
        "total_delta": total_delta,
        "public_pct": public_total_pct,
        "public_side": "OVER" if public_on_over else ("UNDER" if public_on_under else "SPLIT"),
        "book_disagreement": total_disagreement,
    }


def cross_source_divergence(g: GameSlate) -> Dict:
    """
    Check if DK and Covers disagree — when they do, one source has
    retail bettors and the other has sharps. Significant divergence
    (15%+ difference) is a secondary signal.
    """
    # DK shows % of bets on spread; Covers shows their own consensus
    # Both should roughly agree if it's all retail
    dk_away = g.dk_spread_away_pct
    covers_away = g.covers_away_pct
    divergence = abs(dk_away - covers_away)
    
    # ML divergence (DK is more retail-heavy on ML)
    dk_ml_fav_pct = max(g.dk_ml_away_pct, g.dk_ml_home_pct)
    
    return {
        "dk_vs_covers_divergence": divergence,
        "significant": divergence >= 15,
        "dk_spread_away": dk_away,
        "covers_spread_away": covers_away,
        "dk_ml_heavy_fav_pct": dk_ml_fav_pct,
    }


def calculate_confidence(spread_result: Dict, total_result: Dict,
                         cross_src: Dict, game: GameSlate) -> float:
    """
    Composite confidence score 0.0 — 1.0
    Multiple confirming signals = higher confidence
    """
    conf = 0.50  # Base
    
    # Spread RLM
    if spread_result["rlm_detected"]:
        conf += min(0.15, spread_result["rlm_magnitude"] * 0.05)
    
    # Total RLM
    if total_result["rlm_detected"]:
        conf += min(0.15, total_result["rlm_magnitude"] * 0.03)
    
    # Heavy public (higher = more confidence in the fade)
    max_public = max(spread_result["public_split"], total_result["public_pct"])
    if max_public >= 75:
        conf += 0.05
    if max_public >= 80:
        conf += 0.05
    
    # Cross-source divergence
    if cross_src["significant"]:
        conf += 0.03
    
    # Book disagreement suggests sharp action
    if spread_result["book_disagreement"] >= 1.5:
        conf += 0.03
    
    # ATS record of underdog (if taking the dog)
    # Cap at 0.95
    return min(0.95, conf)


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════════

def run_analysis():
    print()
    print("═" * 85)
    print("  🏀 HOUSE EDGE — FULL NBA ANALYSIS — FEBRUARY 9, 2026")
    print(f"  Generated: {datetime.now().strftime('%I:%M %p ET')}")
    print("  Sources: DraftKings splits · Covers consensus · Odds API (6 books)")
    print("═" * 85)
    print()
    print("  Methodology:")
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │ 1. RLM: Line moves AGAINST side w/ most BETS              │")
    print("  │ 2. % bets ≠ % money — whales move lines, not ticket count │")
    print("  │ 3. Sharps bet early, public bets late                      │")
    print("  │ 4. Books set lines to maximize PROFIT, not predict winners │")
    print("  │ 5. Cross-source divergence (DK vs Covers) = hidden edge   │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    tier1_picks = []
    tier2_picks = []
    leans = []
    traps = []
    flat = []

    for g in GAMES:
        spread_res = analyze_spread_rlm(g)
        total_res = analyze_total_rlm(g)
        cross = cross_source_divergence(g)
        
        # Determine best signal from spread or total
        signals = []
        
        if spread_res["signal"] in (Signal.TIER1, Signal.TIER2, Signal.LEAN):
            conf = calculate_confidence(spread_res, total_res, cross, g)
            pick_line = f"{spread_res['rlm_side']} (sharp side)"
            signals.append((spread_res, conf, pick_line, "SPREAD"))
        
        if total_res["signal"] in (Signal.TIER1, Signal.TIER2, Signal.LEAN):
            conf = calculate_confidence(spread_res, total_res, cross, g)
            pick_line = f"{total_res['rlm_side']} {g.current_total}"
            signals.append((total_res, conf, pick_line, "TOTAL"))
        
        entry = {
            "game": g,
            "spread": spread_res,
            "total": total_res,
            "cross": cross,
            "signals": signals,
        }
        
        # Classify
        best_signal = Signal.FLAT
        for sig, _, _, _ in signals:
            if sig["signal"].value < best_signal.value:
                best_signal = sig["signal"]
        
        has_tier1 = any(s["signal"] == Signal.TIER1 for s, _, _, _ in signals)
        has_tier2 = any(s["signal"] == Signal.TIER2 for s, _, _, _ in signals)
        has_lean = any(s["signal"] == Signal.LEAN for s, _, _, _ in signals)
        is_trap = (spread_res["signal"] == Signal.TRAP or total_res["signal"] == Signal.TRAP)
        
        if has_tier1:
            tier1_picks.append(entry)
        elif has_tier2:
            tier2_picks.append(entry)
        elif has_lean:
            leans.append(entry)
        elif is_trap:
            traps.append(entry)
        else:
            flat.append(entry)

    # ── TIER 1 ──
    print("─" * 85)
    print(f"  🔥🔥🔥 TIER 1 — STRONG RLM SIGNALS ({len(tier1_picks)})")
    print("─" * 85)
    if not tier1_picks:
        print("  None identified.\n")
    for entry in tier1_picks:
        _print_pick(entry)

    # ── TIER 2 ──
    print("─" * 85)
    print(f"  🔥 TIER 2 — MODERATE RLM SIGNALS ({len(tier2_picks)})")
    print("─" * 85)
    if not tier2_picks:
        print("  None identified.\n")
    for entry in tier2_picks:
        _print_pick(entry)

    # ── LEANS ──
    print("─" * 85)
    print(f"  👀 LEANS — WORTH WATCHING ({len(leans)})")
    print("─" * 85)
    if not leans:
        print("  None identified.\n")
    for entry in leans:
        _print_pick(entry)

    # ── TRAPS ──
    print("─" * 85)
    print(f"  ⚠️  TRAPS — PUBLIC CONSENSUS, NO SHARP CONFIRMATION ({len(traps)})")
    print("─" * 85)
    if not traps:
        print("  None.\n")
    for entry in traps:
        _print_trap(entry)

    # ── FLAT ──
    print("─" * 85)
    print(f"  ➖ NO EDGE DETECTED ({len(flat)})")
    print("─" * 85)
    for entry in flat:
        g = entry["game"]
        print(f"  {g.away} @ {g.home} ({g.time_et}) — insufficient signal")
    print()

    # ── LINE SHOPPING GRID ──
    print("═" * 85)
    print("  🛒 LINE SHOPPING — BEST AVAILABLE NUMBERS")
    print("═" * 85)
    print(f"  {'Game':<35} {'Best Spread':<25} {'Best Total':<25}")
    print("  " + "─" * 83)
    for g in GAMES:
        spread_info = f"{g.away} {g.best_spread_away:+.1f} @ {g.best_spread_book}"
        total_info = ""
        if g.best_under_total:
            total_info = f"U {g.best_under_total} @ {g.best_under_book}"
        print(f"  {g.away + ' @ ' + g.home:<35} {spread_info[:24]:<25} {total_info[:24]:<25}")
    print()

    # ── BANKROLL MANAGEMENT ──
    print("═" * 85)
    print("  💰 BANKROLL GUIDELINES")
    print("═" * 85)
    print("  • 1U = 1% of your bankroll")
    print("  • Tier 1 signals:  max 2U")
    print("  • Tier 2 signals:  max 1U")
    print("  • Leans:           max 0.5U")
    print("  • Parlays:         max 0.1–0.3U per day")
    print("  • Never chase losses. The edge is in volume + discipline.")
    print()
    print("  ⚠️  DISCLAIMER: This is data analysis based on publicly")
    print("  available line movement and betting percentages. NOT gambling")
    print("  advice. No outcome is ever guaranteed. Bet responsibly.")
    print("═" * 85)
    print()


def _print_pick(entry: Dict):
    g = entry["game"]
    sp = entry["spread"]
    tot = entry["total"]
    cross = entry["cross"]
    
    print(f"\n  ┌── {g.matchup} ({g.time_et}) ──┐")
    print()
    
    for sig_res, conf, pick_line, sig_type in entry["signals"]:
        print(f"  {sig_res['signal'].value}")
        print(f"  ➤ {sig_type}: {pick_line}")
        print(f"  Confidence: {conf:.0%}")
        print()
    
    # Spread analysis
    print(f"  SPREAD: Open {g.open_spread:+.1f} → Current {g.current_spread:+.1f} "
          f"(Δ {sp['spread_delta']:+.1f}pts)")
    print(f"  DK Bets: {g.dk_spread_away_pct}% {g.away} / {g.dk_spread_home_pct}% {g.home}")
    print(f"  Covers:  {g.covers_away_pct}% {g.away} / {g.covers_home_pct}% {g.home}")
    if sp["rlm_detected"]:
        print(f"  ✅ RLM: {sp['rlm_magnitude']:.1f}pts AGAINST {sp['public_dominant_side']} public → Sharp $ on {sp['rlm_side']}")
    print(f"  Book disagreement: {sp['book_disagreement']:.1f}pts across books")
    print()
    
    # Total analysis
    print(f"  TOTAL: Open {g.open_total} → Current {g.current_total} "
          f"(Δ {tot['total_delta']:+.1f}pts)")
    print(f"  DK Bets: {g.dk_over_pct}% Over / {g.dk_under_pct}% Under")
    if tot["rlm_detected"]:
        print(f"  ✅ RLM: {tot['rlm_magnitude']:.1f}pts AGAINST {tot['public_side']} public → Sharp $ on {tot['rlm_side']}")
    print()
    
    # Cross-source
    if cross["significant"]:
        print(f"  📊 DK vs Covers divergence: {cross['dk_vs_covers_divergence']:.0f}%")
    
    # ATS records
    print(f"  ATS: {g.away} {g.away_ats} | {g.home} {g.home_ats}")
    print(f"  L10: {g.away} {g.away_last10} | {g.home} {g.home_last10}")
    
    # Notes
    if g.notes:
        print(f"  📌 {g.notes}")
    print()


def _print_trap(entry: Dict):
    g = entry["game"]
    sp = entry["spread"]
    tot = entry["total"]
    
    print(f"\n  ⚠️  {g.matchup} ({g.time_et})")
    max_pub = max(g.dk_spread_away_pct, g.dk_spread_home_pct)
    heavy_side = g.away if g.dk_spread_away_pct > g.dk_spread_home_pct else g.home
    print(f"  {max_pub}% of bets on {heavy_side} spread, "
          f"line Δ only {abs(sp['spread_delta']):.1f}pts")
    print(f"  → Books NOT moving against public = sharps may AGREE with public")
    print(f"  → Or books are confident in the number. Either way — NO EDGE to fade.")
    if g.notes:
        print(f"  📌 {g.notes}")
    print()


if __name__ == "__main__":
    run_analysis()
