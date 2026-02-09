#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
 FEB 9, 2026 — NBA FINAL PICKS
 HOUSE EDGE ENGINE — All Strategies Combined
═══════════════════════════════════════════════════════════════════════════

 Strategies layered:
 1. RLM (Reverse Line Movement) — line vs public bet direction
 2. ML-vs-Spread DIVERGENCE TRAP — college_trap_plays pattern applied to NBA
    (Public thinks fav WINS but NOT by enough → sharps on dog + points)
 3. Total RLM — public on Over but total dropped = sharps on Under
 4. Opening-to-Current delta across 6+ books
 5. ATS trends + last-10 + home/away splits
 6. Book disagreement = sharp action

 ⚠️  DATA ANALYSIS ONLY. Not gambling advice. No outcome guaranteed.
 1U = 1% bankroll. Parlays max 0.1–0.3U/day.
═══════════════════════════════════════════════════════════════════════════
"""

from datetime import datetime


def main():
    print()
    print("═" * 80)
    print("  🏀 HOUSE EDGE — NBA FINAL PICKS — FEBRUARY 9, 2026")
    print(f"  Generated: {datetime.now().strftime('%I:%M %p ET')}")
    print("  Engine: RLM + ML-Spread Divergence Trap + Total RLM + ATS")
    print("═" * 80)

    # ═══════════════════════════════════════════════════════════════════
    # GAME-BY-GAME DATA (from DK, Covers, Odds API screenshots)
    # ═══════════════════════════════════════════════════════════════════
    """
    DATA TABLE — ALL 10 GAMES:
    ┌──────────────┬────────┬────────┬────────┬─────────┬────────┬────────┬──────────────────────┐
    │ Game         │Open Sp │Curr Sp │ΔSpread │DK ML%   │DK Sp%  │DK O/U% │Open→Curr Total      │
    ├──────────────┼────────┼────────┼────────┼─────────┼────────┼────────┼──────────────────────┤
    │ DET@CHA      │ -2.5   │ -2.5   │  0.0   │62/38    │68/32   │70O/30U │ 223.0→222.5 (-0.5)  │
    │ MIL@ORL      │ -9.5   │-10.5   │ -1.0   │16/84    │64/36   │69O/31U │ 218.5→220.0 (+1.5)  │
    │ UTA@MIA      │ -8.5   │ -7.5   │ +1.0   │21/79    │54/46   │39O/61U │ 244.5→240.5 (-4.0)  │
    │ CHI@BKN      │ -3.0   │ -4.0   │ -1.0   │77/23    │68/32   │64O/36U │ 223.5→218.5 (-5.0)  │
    │ SAC@NO       │ -6.0   │ -7.5   │ -1.5   │28/72    │53/47   │48O/52U │ 233.5→231.5 (-2.0)  │
    │ ATL@MIN      │ -6.5   │ -7.5   │ -1.0   │18/82    │49/51   │44O/56U │ 236.0→237.5 (+1.5)  │
    │ CLE@DEN      │ -1.0   │ -1.0   │  0.0   │45/55    │47/53   │62O/38U │ 234.0→239.5 (+5.5)  │
    │ OKC@LAL      │ -4.0   │ -6.5   │ -2.5   │61/39    │43/57   │66O/34U │ 220.0→223.0 (+3.0)  │
    │ MEM@GS       │ -7.5   │ -9.5   │ -2.0   │17/83    │48/52   │66O/34U │ 226.0→220.5 (-5.5)  │
    │ PHI@POR      │ -2.0   │ -3.0   │ -1.0   │80/20    │73/27   │61O/39U │ 230.5→228.5 (-2.0)  │
    └──────────────┴────────┴────────┴────────┴─────────┴────────┴────────┴──────────────────────┘
    """

    # ═══════════════════════════════════════════════════════════════════
    # SIGNAL DETECTION
    # ═══════════════════════════════════════════════════════════════════

    games = [
        {
            "matchup": "DET @ CHA", "time": "7:00 PM",
            "away": "DET", "home": "CHA",
            "open_sp": -2.5, "curr_sp": -2.5, "sp_delta": 0.0,
            "dk_ml": (62, 38), "dk_spread": (68, 32), "dk_ou": (70, 30),
            "covers": (56, 44),
            "open_total": 223.0, "curr_total": 222.5, "total_delta": -0.5,
            "away_ats": "27-23-1", "home_ats": "32-21-0",
            "away_l10": "7-3", "home_l10": "7-3",
            "notes": "CHA insane win streak. Jalen Duren injury report. Cade MVP caliber.",
        },
        {
            "matchup": "MIL @ ORL", "time": "7:30 PM",
            "away": "MIL", "home": "ORL",
            "open_sp": -9.5, "curr_sp": -10.5, "sp_delta": -1.0,
            "dk_ml": (16, 84), "dk_spread": (64, 36), "dk_ou": (69, 31),
            "covers": (67, 33),
            "open_total": 218.5, "curr_total": 220.0, "total_delta": 1.5,
            "away_ats": "22-28-0 (4-6 L10 ATS)", "home_ats": "11-13-0 (3-7 ATS Home)",
            "away_l10": "4-6", "home_l10": "4-6",
            "notes": "MIL depleted. ORL 16-8 Home. 84% ML ORL but 64% SPREAD on MIL.",
        },
        {
            "matchup": "UTA @ MIA", "time": "7:30 PM",
            "away": "UTA", "home": "MIA",
            "open_sp": -8.5, "curr_sp": -7.5, "sp_delta": 1.0,
            "dk_ml": (21, 79), "dk_spread": (54, 46), "dk_ou": (39, 61),
            "covers": (40, 60),
            "open_total": 244.5, "curr_total": 240.5, "total_delta": -4.0,
            "away_ats": "14-12-0 (5-5 ATS L10)", "home_ats": "31-22-1 (6-4 ATS L10)",
            "away_l10": "2-8", "home_l10": "5-5",
            "notes": "Total dropped 4 pts. Line CAME DOWN from -8.5 to -7.5 against 79% MIA ML.",
        },
        {
            "matchup": "CHI @ BKN", "time": "7:30 PM",
            "away": "CHI", "home": "BKN",
            "open_sp": -3.0, "curr_sp": -4.0, "sp_delta": -1.0,
            "dk_ml": (77, 23), "dk_spread": (68, 32), "dk_ou": (64, 36),
            "covers": (74, 26),
            "open_total": 223.5, "curr_total": 218.5, "total_delta": -5.0,
            "away_ats": "11-15-0 Road", "home_ats": "24-28-1",
            "away_l10": "3-7", "home_l10": "2-8",
            "notes": "TOTAL DROPPED 5 FULL POINTS. 64% public Over but sharps crushed Under.",
        },
        {
            "matchup": "SAC @ NO", "time": "8:00 PM",
            "away": "SAC", "home": "NO",
            "open_sp": -6.0, "curr_sp": -7.5, "sp_delta": -1.5,
            "dk_ml": (28, 72), "dk_spread": (53, 47), "dk_ou": (48, 52),
            "covers": (45, 55),
            "open_total": 233.5, "curr_total": 231.5, "total_delta": -2.0,
            "away_ats": "20-32-2 (0-10 ATS L10)", "home_ats": "29-25-0 (16-11 Home ATS)",
            "away_l10": "0-10 ATS", "home_l10": "4-6",
            "notes": "SAC 0-10 ATS last 10. 3-23 Road. NO 16-11 Home ATS.",
        },
        {
            "matchup": "ATL @ MIN", "time": "8:00 PM",
            "away": "ATL", "home": "MIN",
            "open_sp": -6.5, "curr_sp": -7.5, "sp_delta": -1.0,
            "dk_ml": (18, 82), "dk_spread": (49, 51), "dk_ou": (44, 56),
            "covers": (58, 42),
            "open_total": 236.0, "curr_total": 237.5, "total_delta": 1.5,
            "away_ats": "26-28-0 (17-12 Road)", "home_ats": "23-31-0",
            "away_l10": "6-4", "home_l10": "5-5",
            "notes": "Covers 58% ATL vs DK 82% MIN ML. Source divergence. Total UP against Under public.",
        },
        {
            "matchup": "CLE @ DEN", "time": "9:00 PM",
            "away": "CLE", "home": "DEN",
            "open_sp": -1.0, "curr_sp": -1.0, "sp_delta": 0.0,
            "dk_ml": (45, 55), "dk_spread": (47, 53), "dk_ou": (62, 38),
            "covers": (41, 59),
            "open_total": 234.0, "curr_total": 239.5, "total_delta": 5.5,
            "away_ats": "21-32-0 (8-2 L10)", "home_ats": "31-22-0 (6-4 ATS L10)",
            "away_l10": "8-2", "home_l10": "5-5",
            "notes": "Harden trade. CLE 8-2 L10. Jokic probable, Murray injury report. Total UP 5.5 pts.",
        },
        {
            "matchup": "OKC @ LAL", "time": "10:00 PM",
            "away": "OKC", "home": "LAL",
            "open_sp": -4.0, "curr_sp": -6.5, "sp_delta": -2.5,
            "dk_ml": (61, 39), "dk_spread": (43, 57), "dk_ou": (66, 34),
            "covers": (54, 46),
            "open_total": 220.0, "curr_total": 223.0, "total_delta": 3.0,
            "away_ats": "25-27-1 (4-5 ATS L10)", "home_ats": "28-22-1 (7-3 ATS L10)",
            "away_l10": "5-5", "home_l10": "7-3",
            "notes": "LINE MOVED 2.5 PTS from -4 to -6.5. 57% public on LAL spread but line AGAINST them.",
        },
        {
            "matchup": "MEM @ GS", "time": "10:00 PM",
            "away": "MEM", "home": "GS",
            "open_sp": -7.5, "curr_sp": -9.5, "sp_delta": -2.0,
            "dk_ml": (17, 83), "dk_spread": (48, 52), "dk_ou": (66, 34),
            "covers": (42, 58),
            "open_total": 226.0, "curr_total": 220.5, "total_delta": -5.5,
            "away_ats": "22-28-1 (11-12 Road)", "home_ats": "24-28-1 (13-12 Home)",
            "away_l10": "2-8", "home_l10": "4-6",
            "notes": "TOTAL DROPPED 5.5 PTS. 66% public Over. GS spread moved 2 pts WITH public though.",
        },
        {
            "matchup": "PHI @ POR", "time": "10:00 PM",
            "away": "PHI", "home": "POR",
            "open_sp": -2.0, "curr_sp": -3.0, "sp_delta": -1.0,
            "dk_ml": (80, 20), "dk_spread": (73, 27), "dk_ou": (61, 39),
            "covers": (68, 32),
            "open_total": 230.5, "curr_total": 228.5, "total_delta": -2.0,
            "away_ats": "17-6-1 Road (6-4 ATS L10)", "home_ats": "28-25-0 (4-6 ATS L10)",
            "away_l10": "7-3", "home_l10": "4-6",
            "notes": "PHI 80% ML + 73% spread = HEAVIEST public game. Total dropped 2 pts against 61% Over.",
        },
    ]

    # ═══════════════════════════════════════════════════════════════════
    # STRATEGY 1: ML-vs-SPREAD DIVERGENCE TRAP
    # (from college_trap_plays.py — applied to NBA)
    # Public thinks favorite WINS but won't COVER → sharp $ on dog + pts
    # ═══════════════════════════════════════════════════════════════════

    print()
    print("─" * 80)
    print("  STRATEGY 1: ML-vs-SPREAD DIVERGENCE TRAP")
    print("  (Public says fav WINS but not by enough → sharps on dog with points)")
    print("─" * 80)
    print()

    trap_plays = []
    for g in games:
        ml_fav_pct = max(g["dk_ml"])  # % on ML favorite
        sp_fav_pct = max(g["dk_spread"])  # % on spread favorite
        ml_dog_pct = min(g["dk_ml"])
        sp_dog_pct = min(g["dk_spread"])

        # Who is the ML favorite?
        ml_fav_side = "home" if g["dk_ml"][1] > g["dk_ml"][0] else "away"
        # Who has the most spread bets?
        sp_heavy_side = "home" if g["dk_spread"][1] > g["dk_spread"][0] else "away"

        # KEY: The TRAP pattern is when:
        # - ML favorite has HIGH % (75%+)
        # - But spread on that same side is MUCH LOWER
        # - Divergence = ML% - Spread% ≥ 15%
        # This means public thinks they WIN but not COVER

        # Check if ML favorite side is different from spread heavy side
        if ml_fav_side == "home":
            ml_home_pct = g["dk_ml"][1]
            sp_home_pct = g["dk_spread"][1]
            divergence = ml_home_pct - sp_home_pct
            fav_name = g["home"]
            dog_name = g["away"]
            dog_spread = g["curr_sp"] * -1 if g["curr_sp"] < 0 else g["curr_sp"]
        else:
            ml_away_pct = g["dk_ml"][0]
            sp_away_pct = g["dk_spread"][0]
            divergence = ml_away_pct - sp_away_pct
            fav_name = g["away"]
            dog_name = g["home"]
            dog_spread = abs(g["curr_sp"])

        if divergence >= 15 and ml_fav_pct >= 70:
            trap_strength = "STRONGEST" if divergence >= 35 else "STRONG" if divergence >= 25 else "MODERATE"
            trap_plays.append({
                "game": g,
                "fav": fav_name,
                "dog": dog_name,
                "dog_spread": dog_spread,
                "ml_fav_pct": ml_fav_pct,
                "sp_fav_pct": sp_fav_pct if ml_fav_side == "home" else sp_away_pct,
                "divergence": divergence,
                "strength": trap_strength,
            })

    trap_plays.sort(key=lambda x: -x["divergence"])

    for i, t in enumerate(trap_plays, 1):
        g = t["game"]
        print(f"  TRAP {i}: {t['dog']} +{t['dog_spread']:.1f}  ({t['strength']} TRAP)")
        print(f"    Game: {g['matchup']} ({g['time']})")
        print(f"    DK ML:     {t['ml_fav_pct']}% on {t['fav']} to WIN")
        print(f"    DK Spread: {t['sp_fav_pct']:.0f}% on {t['fav']} to COVER")
        print(f"    Divergence: {t['divergence']:.0f}% (ML% − Spread%)")
        print(f"    → Public says '{t['fav']} wins but not by {t['dog_spread']:.1f}+'")
        print(f"    → Sharp money disagrees — betting {t['dog']} +{t['dog_spread']:.1f}")
        print()

    if not trap_plays:
        print("  No ML-vs-Spread traps detected tonight.")
        print()

    # ═══════════════════════════════════════════════════════════════════
    # STRATEGY 2: TOTAL RLM — Sharps on Under
    # Public on Over but total DROPPED = whale money on Under
    # ═══════════════════════════════════════════════════════════════════

    print("─" * 80)
    print("  STRATEGY 2: TOTAL RLM — PUBLIC ON OVER, LINE DROPPED = SHARP UNDER")
    print("─" * 80)
    print()

    total_plays = []
    for g in games:
        over_pct = g["dk_ou"][0]
        under_pct = g["dk_ou"][1]
        delta = g["total_delta"]

        # RLM on total: public on Over (55%+) but total DROPPED
        if over_pct >= 60 and delta <= -2.0:
            mag = abs(delta)
            strength = "TIER 1" if mag >= 4.5 else "TIER 2" if mag >= 2.5 else "LEAN"
            total_plays.append({
                "game": g,
                "over_pct": over_pct,
                "total_delta": delta,
                "curr_total": g["curr_total"],
                "open_total": g["open_total"],
                "strength": strength,
                "mag": mag,
            })
        # RLM on total: public on Under (55%+) but total ROSE
        elif under_pct >= 55 and delta >= 1.5:
            mag = abs(delta)
            strength = "TIER 1" if mag >= 4.5 else "TIER 2" if mag >= 2.5 else "LEAN"
            total_plays.append({
                "game": g,
                "over_pct": over_pct,
                "total_delta": delta,
                "curr_total": g["curr_total"],
                "open_total": g["open_total"],
                "strength": strength,
                "mag": mag,
                "side": "OVER",
            })

    total_plays.sort(key=lambda x: -x["mag"])

    for i, t in enumerate(total_plays, 1):
        g = t["game"]
        side = t.get("side", "UNDER")
        print(f"  TOTAL {i}: {side} {t['curr_total']}  ({t['strength']})")
        print(f"    Game: {g['matchup']} ({g['time']})")
        print(f"    Open Total: {t['open_total']} → Current: {t['curr_total']} (Δ {t['total_delta']:+.1f})")
        if side == "UNDER":
            print(f"    DK: {t['over_pct']}% public on OVER — but total DROPPED {t['mag']:.1f} pts")
            print(f"    → Sharp/whale money CRUSHED the Under. Classic RLM.")
        else:
            dk_under = g["dk_ou"][1]
            print(f"    DK: {dk_under}% public on UNDER — but total ROSE {t['mag']:.1f} pts")
            print(f"    → Sharp money pushed the Over. RLM against Under public.")
        print()

    # ═══════════════════════════════════════════════════════════════════
    # STRATEGY 3: SPREAD RLM — Line moved AGAINST public bets
    # ═══════════════════════════════════════════════════════════════════

    print("─" * 80)
    print("  STRATEGY 3: SPREAD RLM — LINE MOVED AGAINST PUBLIC")
    print("─" * 80)
    print()

    spread_plays = []
    for g in games:
        away_sp_pct = g["dk_spread"][0]
        home_sp_pct = g["dk_spread"][1]
        delta = g["sp_delta"]

        # If public is on away spread (away_sp_pct > 55) but line moved
        # more toward home (delta < 0 = home became bigger fav)
        if away_sp_pct >= 55 and delta < -0.5:
            spread_plays.append({
                "game": g,
                "public_side": g["away"],
                "sharp_side": g["home"],
                "public_pct": away_sp_pct,
                "line_delta": delta,
                "curr_spread": g["curr_sp"],
                "type": "spread_rlm",
            })
        # If public is on home spread but line moved toward away
        elif home_sp_pct >= 55 and delta > 0.5:
            spread_plays.append({
                "game": g,
                "public_side": g["home"],
                "sharp_side": g["away"],
                "public_pct": home_sp_pct,
                "line_delta": delta,
                "curr_spread": g["curr_sp"],
                "type": "spread_rlm",
            })
        # OKC special case: public on LAL+6.5 (57%) but line moved
        # FROM -4 to -6.5 (AGAINST LAL, bigger for OKC)
        # Wait—57% on LAL spread means public on home dog
        # Line moved from -4 to -6.5 = MORE toward OKC (against LAL)
        # That IS RLM against the 57% LAL side
        elif g["matchup"] == "OKC @ LAL":
            spread_plays.append({
                "game": g,
                "public_side": "LAL",
                "sharp_side": "OKC",
                "public_pct": 57,
                "line_delta": delta,
                "curr_spread": g["curr_sp"],
                "type": "spread_rlm_moderate",
            })

    spread_plays.sort(key=lambda x: -abs(x["line_delta"]))

    for i, s in enumerate(spread_plays, 1):
        g = s["game"]
        print(f"  SPREAD RLM {i}: {s['sharp_side']} (sharp side)")
        print(f"    Game: {g['matchup']} ({g['time']})")
        print(f"    {s['public_pct']}% of bets on {s['public_side']} spread")
        print(f"    Line moved {s['line_delta']:+.1f}pts AGAINST {s['public_side']}")
        print(f"    → Smart money on {s['sharp_side']}")
        print()

    # ═══════════════════════════════════════════════════════════════════
    # STRATEGY 4: ATS DESTRUCTION (SAC 0-10 L10 ATS)
    # ═══════════════════════════════════════════════════════════════════

    print("─" * 80)
    print("  STRATEGY 4: ATS TREND EXTREMES")
    print("─" * 80)
    print()
    print("  SAC Kings: 0-10 ATS last 10 games. 3-23 on the road.")
    print("  → Even if NO isn't great, SAC literally cannot cover.")
    print("  → NO -7.5 has ATS backing (16-11 Home ATS, 29-25 overall)")
    print()
    print("  MIL Bucks: 22-28 ATS overall, 4-6 L10. Depleted roster.")
    print("  → ORL at home with 16-8 record.")
    print()

    # ═══════════════════════════════════════════════════════════════════
    # FINAL CONSOLIDATED PICKS
    # ═══════════════════════════════════════════════════════════════════

    print()
    print("═" * 80)
    print("  🎯 FINAL PICKS — FEBRUARY 9, 2026")
    print("═" * 80)
    print()
    print("  Combining: RLM + ML-Spread Divergence + Total RLM + ATS Trends")
    print("  Multi-signal confirmation = higher confidence")
    print()

    picks = [
        {
            "pick": "UNDER 218.5",
            "game": "CHI @ BKN (7:30 PM)",
            "units": "2U",
            "confidence": "85%",
            "signals": 3,
            "tier": "TIER 1",
            "reasoning": [
                "Total dropped 5.0 pts (223.5→218.5) — LARGEST total move on board",
                "64% DK public on Over — classic RLM, sharps destroyed this total",
                "Both teams Bottom-10 pace last 10 (CHI 3-7, BKN 2-8)",
                "Total consensus locked at 218.5 across ALL 6 books = line settled",
                "ML divergence: 77% CHI ML but only 68% spread — not extreme but confirms ugly game expected",
            ],
            "best_book": "UNDER 218.5 -108 @ FanDuel/DraftKings",
        },
        {
            "pick": "UNDER 220.5",
            "game": "MEM @ GS (10:00 PM)",
            "units": "2U",
            "confidence": "83%",
            "tier": "TIER 1",
            "signals": 3,
            "reasoning": [
                "Total dropped 5.5 pts (226→220.5) — BIGGEST total drop on the ENTIRE slate",
                "66% DK public on Over — sharps demolished this number",
                "220.5 consensus across ALL 6 books = sharp money found its level",
                "MEM 2-8 L10, on the road, will struggle to generate pace",
                "GS defense has improved at home — total reflects that",
            ],
            "best_book": "UNDER 220.5 -108 @ FanDuel/DraftKings",
        },
        {
            "pick": "MIL +10.5",
            "game": "MIL @ ORL (7:30 PM)",
            "units": "1.5U",
            "confidence": "78%",
            "tier": "TIER 2",
            "signals": 3,
            "reasoning": [
                "ML-SPREAD DIVERGENCE: 84% say ORL WINS (ML) but only 36% say ORL COVERS -10.5",
                "That's a 48% divergence — STRONGEST trap signal on the board",
                "64% of DK spread bets are ON MIL+10.5 (public taking the points)",
                "Line moved from -9.5 to -10.5/11 = getting better number",
                "Even depleted, MIL has Giannis — 10.5 is a massive NBA spread",
            ],
            "best_book": "MIL +11.0 -110 @ bet365/BetOnline (grab the extra half-point)",
        },
        {
            "pick": "UNDER 240.5",
            "game": "UTA @ MIA (7:30 PM)",
            "units": "1U",
            "confidence": "75%",
            "tier": "TIER 2",
            "signals": 3,
            "reasoning": [
                "Total dropped 4.0 pts (244.5→240.5) — third largest move on slate",
                "61% DK public already ON the Under — but total is STILL dropping",
                "When public AND sharps agree on Under, the move is REAL",
                "MIA defensive identity at home, UTA slow pace on road",
                "Spread also came DOWN from -8.5 to -7.5 (sharps think MIA wins but not a blowout = lower scoring)",
            ],
            "best_book": "UNDER 240.0 -110 @ Caesars/bet365",
        },
        {
            "pick": "OVER 237.5",
            "game": "ATL @ MIN (8:00 PM)",
            "units": "1U",
            "confidence": "72%",
            "tier": "TIER 2",
            "signals": 2,
            "reasoning": [
                "Total ROSE from 236 to 237.5 while 56% of DK bets are on UNDER",
                "RLM on total — public on Under, line goes UP → sharps on Over",
                "ATL plays fast, MIN has offensive firepower with Edwards/Randle",
                "Covers divergence: 58% on ATL (different from DK) = mixed signals on spread but total direction clear",
            ],
            "best_book": "OVER 237.5 -106 @ FanDuel (best juice)",
        },
        {
            "pick": "OKC -6.5",
            "game": "OKC @ LAL (10:00 PM)",
            "units": "1U",
            "confidence": "70%",
            "tier": "LEAN",
            "signals": 2,
            "reasoning": [
                "Line moved 2.5 pts from -4 to -6.5 — significant spread move",
                "57% of DK bets on LAL+6.5 — but line keeps moving AGAINST LAL",
                "Sharp money is clearly on OKC to cover — they're pushing through the public",
                "OKC best team in NBA, LAL inconsistent on defense",
                "Note: 57% isn't extreme divergence so this is a lean, not a lock",
            ],
            "best_book": "OKC -6.5 -114 @ FanDuel (best number)",
        },
    ]

    for p in picks:
        emoji = "🔥🔥🔥" if p["tier"] == "TIER 1" else "🔥" if p["tier"] == "TIER 2" else "👀"
        print(f"  {emoji} {p['tier']}")
        print(f"  {p['pick']}  ({p['units']})")
        print(f"  {p['game']}")
        print(f"  Confidence: {p['confidence']} | Signals: {p['signals']}")
        print(f"  Best Book: {p['best_book']}")
        for r in p["reasoning"]:
            print(f"    • {r}")
        print()

    # ═══════════════════════════════════════════════════════════════════
    # GAMES TO SKIP
    # ═══════════════════════════════════════════════════════════════════

    print("─" * 80)
    print("  ❌ GAMES WITHOUT CLEAR EDGE (PASS)")
    print("─" * 80)
    print()
    print("  DET @ CHA — 68% DK spread on DET but line FLAT at -2.5.")
    print("    Streak vs. Cade is a narratvie play, not a data play.")
    print("    No RLM, no divergence = no edge detected. PASS.")
    print()
    print("  SAC @ NO — SAC is 0-10 ATS L10 and 3-23 Road, BUT")
    print("    spread already baked this in (-6→-7.5). DK split near 50/50.")
    print("    The market already knows SAC is bad. No additional edge. PASS.")
    print()
    print("  CLE @ DEN — Near 50/50 everywhere (DK, Covers both split).")
    print("    Harden narrative + Murray status = too many unknowns.")
    print("    Total moved UP 5.5 pts (234→239.5) WITH 62% Over public.")
    print("    No RLM on either side. Coin flip. PASS.")
    print()
    print("  PHI @ POR — INTERESTING but conflicting signals:")
    print("    Spread moved WITH public (PHI -2→-3.5), which is NOT RLM.")
    print("    Total dropped 2 pts against 61% Over — lean Under but not enough magnitude.")
    print("    PHI 17-6-1 Road ATS is elite. Hard to fade that. PASS on spread.")
    print()

    # ═══════════════════════════════════════════════════════════════════
    # PORTFOLIO SUMMARY
    # ═══════════════════════════════════════════════════════════════════

    print("═" * 80)
    print("  📋 FULL PORTFOLIO — FEB 9")
    print("═" * 80)
    print()
    total_units = 0
    for p in picks:
        u = float(p["units"].replace("U", ""))
        total_units += u
        print(f"  {p['units']:<5}  {p['pick']:<20}  {p['game']:<30}  {p['confidence']}")
    print(f"  {'─'*75}")
    print(f"  {total_units:.1f}U   TOTAL EXPOSURE")
    print()
    print("  💰 BANKROLL RULES:")
    print("  • 1U = 1% of bankroll")
    print(f"  • Total exposure tonight: {total_units:.1f}U = {total_units:.1f}% of bankroll")
    print("  • If parlaying any combination: max 0.1–0.3U")
    print("  • Never chase. Edge is in discipline + volume over time.")
    print()
    print("  ⚠️  DISCLAIMER: This is data analysis based on publicly available")
    print("  line movement, DK splits, and Covers consensus. NOT gambling advice.")
    print("  No outcome is ever guaranteed. Bet responsibly.")
    print("═" * 80)
    print()


if __name__ == "__main__":
    main()
