#!/usr/bin/env python3
"""
BOOST EV CALCULATOR
====================
Calculates how DraftKings profit boosts change the EV of a bet.

A 25% boost turns -110 into ~-88 effective odds.
A 50% boost turns -110 into ~-73.
A 100% boost turns -110 into ~-10 (nearly even money on the PROFIT).

This module answers: "Does this boost turn a PASS/LEAN into a TIER 1 play?"

Usage:
    from engine.boost_ev import BoostCalculator, evaluate_boost_play
    calc = BoostCalculator()

    # Check if a 25% boost makes OKC -6.5 worth it
    result = calc.evaluate(-110, 0.25, win_probability=0.52)
    print(result)
    # → {'boosted_odds': -88, 'base_ev': -3.6%, 'boosted_ev': +8.4%, 'verdict': 'TIER2→TIER1'}
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
import math


@dataclass
class BoostResult:
    """Result of boost EV evaluation."""
    base_odds: int              # Original American odds (e.g., -110)
    boost_pct: float            # Boost as decimal (0.25 = 25%)
    boosted_odds: int           # Effective American odds after boost
    base_decimal: float         # Original decimal odds
    boosted_decimal: float      # Boosted decimal odds
    implied_prob: float         # Market implied probability (no-vig)
    win_probability: float      # Your estimated win probability
    base_ev: float              # EV% without boost
    boosted_ev: float           # EV% with boost
    ev_gain: float              # How much EV the boost adds
    base_tier: str              # Tier without boost
    boosted_tier: str           # Tier with boost
    promoted: bool              # Did the boost promote the tier?
    verdict: str                # Human-readable verdict
    kelly_fraction: float       # Kelly criterion bet fraction (boosted)

    def to_dict(self) -> Dict:
        return {
            "base_odds": self.base_odds,
            "boost_pct": f"{self.boost_pct:.0%}",
            "boosted_odds": self.boosted_odds,
            "implied_prob": f"{self.implied_prob:.1%}",
            "win_probability": f"{self.win_probability:.1%}",
            "base_ev": f"{self.base_ev:+.1%}",
            "boosted_ev": f"{self.boosted_ev:+.1%}",
            "ev_gain": f"{self.ev_gain:+.1%}",
            "tier_change": f"{self.base_tier} → {self.boosted_tier}",
            "promoted": self.promoted,
            "verdict": self.verdict,
            "kelly": f"{self.kelly_fraction:.1%}",
        }


class BoostCalculator:
    """Calculate the impact of DraftKings profit boosts on EV."""

    # EV thresholds for tier classification
    TIER1_EV = 0.08      # 8%+ EV = strong play
    TIER2_EV = 0.03      # 3-8% EV = moderate play
    LEAN_EV = 0.00       # 0-3% EV = lean
    # Below 0% = negative EV = PASS

    @staticmethod
    def american_to_decimal(american: int) -> float:
        """Convert American odds to decimal odds."""
        if american > 0:
            return 1 + (american / 100)
        else:
            return 1 + (100 / abs(american))

    @staticmethod
    def decimal_to_american(decimal_odds: float) -> int:
        """Convert decimal odds to American odds."""
        if decimal_odds >= 2.0:
            return round((decimal_odds - 1) * 100)
        else:
            return round(-100 / (decimal_odds - 1))

    @staticmethod
    def implied_probability(american: int) -> float:
        """Get no-vig implied probability from American odds."""
        if american < 0:
            return abs(american) / (abs(american) + 100)
        else:
            return 100 / (american + 100)

    def apply_boost(self, base_odds: int, boost_pct: float) -> tuple:
        """
        Apply a DraftKings profit boost to American odds.

        DK boosts work on PROFIT, not total payout:
        - If you bet $100 at -110, your profit if you win = $90.91
        - A 25% boost means profit = $90.91 * 1.25 = $113.64
        - Total payout = $100 + $113.64 = $213.64
        - Effective decimal odds = 2.1364
        - Effective American odds = +114

        Args:
            base_odds: American odds (e.g., -110, +150)
            boost_pct: boost as decimal (0.25 for 25%, 0.50 for 50%)

        Returns:
            (boosted_decimal, boosted_american)
        """
        base_decimal = self.american_to_decimal(base_odds)

        # DK boost applies to PROFIT (decimal - 1)
        base_profit = base_decimal - 1
        boosted_profit = base_profit * (1 + boost_pct)
        boosted_decimal = 1 + boosted_profit

        boosted_american = self.decimal_to_american(boosted_decimal)
        return boosted_decimal, boosted_american

    def calculate_ev(self, decimal_odds: float, win_prob: float) -> float:
        """
        Calculate expected value.

        EV = (win_prob * profit) - (lose_prob * stake)
           = (win_prob * (decimal - 1)) - ((1 - win_prob) * 1)
        """
        return (win_prob * (decimal_odds - 1)) - ((1 - win_prob) * 1)

    def kelly_criterion(self, decimal_odds: float, win_prob: float) -> float:
        """
        Kelly criterion for optimal bet sizing.

        f* = (bp - q) / b
        where b = decimal - 1, p = win_prob, q = 1 - win_prob
        """
        b = decimal_odds - 1
        p = win_prob
        q = 1 - p
        if b <= 0:
            return 0
        kelly = (b * p - q) / b
        return max(0, kelly)  # Never bet negative

    def classify_tier(self, ev: float) -> str:
        """Classify EV into tiers."""
        if ev >= self.TIER1_EV:
            return "TIER1"
        elif ev >= self.TIER2_EV:
            return "TIER2"
        elif ev >= self.LEAN_EV:
            return "LEAN"
        else:
            return "PASS"

    def evaluate(self, base_odds: int, boost_pct: float,
                 win_probability: Optional[float] = None) -> BoostResult:
        """
        Full evaluation of a boosted bet.

        Args:
            base_odds:       American odds (e.g., -110)
            boost_pct:       Boost as decimal (0.25 = 25%)
            win_probability: Your estimated probability of winning (0-1).
                             If None, uses implied probability (assumes fair line).

        Returns:
            BoostResult with all calculated metrics
        """
        base_decimal = self.american_to_decimal(base_odds)
        implied_prob = self.implied_probability(base_odds)

        # Use provided win probability or implied
        win_prob = win_probability if win_probability is not None else implied_prob

        # Apply boost
        boosted_decimal, boosted_american = self.apply_boost(base_odds, boost_pct)

        # Calculate EVs
        base_ev = self.calculate_ev(base_decimal, win_prob)
        boosted_ev = self.calculate_ev(boosted_decimal, win_prob)
        ev_gain = boosted_ev - base_ev

        # Classify tiers
        base_tier = self.classify_tier(base_ev)
        boosted_tier = self.classify_tier(boosted_ev)
        promoted = base_tier != boosted_tier and boosted_ev > base_ev

        # Kelly
        kelly = self.kelly_criterion(boosted_decimal, win_prob)

        # Verdict
        if promoted:
            verdict = f"PROMOTED: {base_tier} → {boosted_tier} (boost adds {ev_gain:+.1%} EV)"
        elif boosted_ev > 0:
            verdict = f"POSITIVE EV: {boosted_ev:+.1%} with boost ({base_tier} tier)"
        elif boosted_ev > -0.02:
            verdict = f"MARGINAL: {boosted_ev:+.1%} — barely worth it with boost"
        else:
            verdict = f"STILL NEGATIVE: {boosted_ev:+.1%} — boost not enough to save this"

        return BoostResult(
            base_odds=base_odds,
            boost_pct=boost_pct,
            boosted_odds=boosted_american,
            base_decimal=round(base_decimal, 4),
            boosted_decimal=round(boosted_decimal, 4),
            implied_prob=round(implied_prob, 4),
            win_probability=round(win_prob, 4),
            base_ev=round(base_ev, 4),
            boosted_ev=round(boosted_ev, 4),
            ev_gain=round(ev_gain, 4),
            base_tier=base_tier,
            boosted_tier=boosted_tier,
            promoted=promoted,
            verdict=verdict,
            kelly_fraction=round(kelly, 4),
        )

    def evaluate_all_boosts(self, base_odds: int,
                            win_probability: float,
                            boosts: Optional[List[float]] = None) -> List[BoostResult]:
        """
        Evaluate a bet across multiple boost levels.

        Default boosts: 25%, 50%, 100% (standard DK boost tiers).
        """
        if boosts is None:
            boosts = [0.25, 0.50, 1.00]

        return [self.evaluate(base_odds, b, win_probability) for b in boosts]

    def find_breakeven_boost(self, base_odds: int,
                             win_probability: float) -> Optional[float]:
        """
        Find the minimum boost % needed to make a bet +EV.

        Returns None if the bet is already +EV without a boost.
        """
        base_decimal = self.american_to_decimal(base_odds)
        base_ev = self.calculate_ev(base_decimal, win_probability)

        if base_ev >= 0:
            return None  # Already +EV

        # EV = p * (1 + profit*(1+boost)) - 1 = 0
        # Solve for boost: profit*(1+boost) = (1/p - 1)
        # 1+boost = (1/p - 1) / profit
        # boost = (1/p - 1) / profit - 1
        profit = base_decimal - 1
        if profit <= 0:
            return None

        needed = ((1 / win_probability - 1) / profit) - 1
        return max(0, needed)


def print_boost_analysis(base_odds: int, win_prob: float, boost_pct: float):
    """Pretty-print a boost evaluation."""
    calc = BoostCalculator()
    result = calc.evaluate(base_odds, boost_pct, win_prob)
    d = result.to_dict()

    print(f"\n  Bet: {base_odds:+d} odds | Your edge: {win_prob:.0%} win")
    print(f"  Boost: {d['boost_pct']} → Effective odds: {result.boosted_odds:+d}")
    print(f"  Base EV: {d['base_ev']} | Boosted EV: {d['boosted_ev']} (gain: {d['ev_gain']})")
    print(f"  Tier: {d['tier_change']}")
    print(f"  Kelly: {d['kelly']} of bankroll")
    print(f"  Verdict: {result.verdict}")


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 65)
    print("  BOOST EV CALCULATOR — DraftKings Profit Boost Analysis")
    print("═" * 65)

    calc = BoostCalculator()

    # Tonight's examples
    examples = [
        ("OKC -6.5", -110, 0.54, 0.25),
        ("CHI/BKN Under 218.9", -108, 0.57, 0.25),
        ("MIL +11.0", -110, 0.52, 0.50),
        ("CLE ML vs DEN", +105, 0.50, 0.25),
        ("MEM/GS Under 220.5", -110, 0.55, 0.50),
    ]

    for label, odds, win_prob, boost in examples:
        print(f"\n  {'─' * 55}")
        print(f"  {label}")
        print_boost_analysis(odds, win_prob, boost)

    # Breakeven boost finder
    print(f"\n  {'═' * 55}")
    print("  BREAKEVEN BOOST FINDER")
    print(f"  {'═' * 55}")

    test_cases = [
        ("OKC -6.5 @ -110, 48% win", -110, 0.48),
        ("MIL +11 @ -110, 50% win", -110, 0.50),
        ("CLE ML @ +105, 47% win", 105, 0.47),
    ]

    for label, odds, wp in test_cases:
        be = calc.find_breakeven_boost(odds, wp)
        if be is not None:
            print(f"  {label} → Need {be:.0%} boost to break even")
        else:
            print(f"  {label} → Already +EV without boost!")

    print()
