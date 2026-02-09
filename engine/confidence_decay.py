#!/usr/bin/env python3
"""
CONFIDENCE DECAY ENGINE
========================
Confidence scores should NOT be static. Edge decays over time as:
  1. Lines move (your CLV erodes)
  2. New information arrives (injuries, rest, scratches)
  3. Stale analysis becomes less reliable

This module applies time-based and market-based decay to picks,
enabling auto-promotion and auto-demotion in real-time.

Rules:
  - Pick generated 4+ hours ago with no line change? Confidence -5%
  - Line moved IN your direction since pick? Confidence +3% (CLV confirmed)
  - Line moved AGAINST you 1.5+ pts? Confidence -10% (edge eroding)
  - Star player injury after pick? Confidence -15% (game script changed)

Usage:
    from engine.confidence_decay import ConfidenceDecayEngine
    engine = ConfidenceDecayEngine()
    updated = engine.apply_decay(pick, current_line, current_time)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class DecayFactor:
    """A single factor affecting confidence."""
    name: str
    delta: float          # positive = boost, negative = decay
    reason: str

    def __repr__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.name}: {sign}{self.delta:.1f}% ({self.reason})"


@dataclass
class DecayResult:
    """Result of applying decay to a pick."""
    original_confidence: float
    current_confidence: float
    factors: List[DecayFactor]
    original_tier: str
    current_tier: str
    promoted: bool
    demoted: bool

    def to_dict(self) -> Dict:
        return {
            "original_confidence": self.original_confidence,
            "current_confidence": round(self.current_confidence, 1),
            "delta": round(self.current_confidence - self.original_confidence, 1),
            "factors": [{"name": f.name, "delta": f.delta, "reason": f.reason}
                        for f in self.factors],
            "original_tier": self.original_tier,
            "current_tier": self.current_tier,
            "promoted": self.promoted,
            "demoted": self.demoted,
        }


class ConfidenceDecayEngine:
    """Applies time-based and market-based decay to pick confidence."""

    # Tier thresholds (must match signals.py)
    TIER_THRESHOLDS = {
        "TIER1": 80,
        "TIER2": 70,
        "LEAN": 60,
        "PASS": 0,
    }

    # Decay parameters
    TIME_DECAY_RATE = -1.5       # % per hour after 2 hours
    TIME_DECAY_START_HOURS = 2   # Start decaying after 2 hours
    TIME_DECAY_MAX = -15         # Max time decay

    LINE_MOVE_WITH_BONUS = 2.0   # % bonus per pt line moves in your favor
    LINE_MOVE_AGAINST_PENALTY = -4.0  # % per pt line moves against you
    LINE_MOVE_AGAINST_THRESHOLD = 1.0  # only penalize if 1+ pt against

    INJURY_PENALTY = -15         # Major injury after pick
    INFO_LEAK_PENALTY = -10      # Sudden 2+ pt line jump (information leak)

    def classify_tier(self, confidence: float) -> str:
        """Classify confidence into a tier."""
        if confidence >= self.TIER_THRESHOLDS["TIER1"]:
            return "TIER1"
        elif confidence >= self.TIER_THRESHOLDS["TIER2"]:
            return "TIER2"
        elif confidence >= self.TIER_THRESHOLDS["LEAN"]:
            return "LEAN"
        return "PASS"

    def apply_decay(
        self,
        pick: Dict,
        current_time: Optional[datetime] = None,
        current_line: Optional[float] = None,
        injury_flag: bool = False,
        info_leak_flag: bool = False,
    ) -> DecayResult:
        """
        Apply all decay factors to a pick.

        Args:
            pick: Dict with keys: confidence, timestamp, line, pick_type
            current_time: Now (defaults to datetime.now())
            current_line: Current market line (to detect movement)
            injury_flag: True if a significant injury occurred after pick
            info_leak_flag: True if line jumped 2+ pts in 10 min

        Returns:
            DecayResult with updated confidence and all factors
        """
        if current_time is None:
            current_time = datetime.now()

        original_conf = pick.get("confidence", 70)
        original_tier = self.classify_tier(original_conf)
        factors: List[DecayFactor] = []

        # ── Factor 1: Time Decay ──────────────────────────────────
        pick_time = pick.get("timestamp")
        if pick_time:
            if isinstance(pick_time, str):
                try:
                    pick_time = datetime.fromisoformat(pick_time)
                except ValueError:
                    pick_time = None

            if pick_time:
                hours_elapsed = (current_time - pick_time).total_seconds() / 3600

                if hours_elapsed > self.TIME_DECAY_START_HOURS:
                    decay_hours = hours_elapsed - self.TIME_DECAY_START_HOURS
                    time_decay = max(self.TIME_DECAY_MAX, decay_hours * self.TIME_DECAY_RATE)
                    factors.append(DecayFactor(
                        name="TIME_DECAY",
                        delta=time_decay,
                        reason=f"Pick is {hours_elapsed:.1f}hrs old "
                               f"({decay_hours:.1f}hrs past freshness window)",
                    ))

        # ── Factor 2: Line Movement ──────────────────────────────
        if current_line is not None:
            pick_line = pick.get("line")
            pick_type = pick.get("pick_type", "").upper()

            if pick_line is not None:
                line_diff = current_line - pick_line

                # Determine direction
                if pick_type in ("UNDER",):
                    # Under: line going down = moving in your favor
                    movement_for_you = -line_diff  # negative diff = good for Under
                elif pick_type in ("OVER",):
                    # Over: line going up = moving in your favor
                    movement_for_you = line_diff
                elif pick_type in ("SPREAD_AWAY", "SPREAD"):
                    # Taking dog: line going up (more points) = in your favor
                    movement_for_you = line_diff
                else:
                    movement_for_you = 0

                if movement_for_you > 0:
                    # Line moved in your favor — CLV confirmed
                    bonus = min(10, movement_for_you * self.LINE_MOVE_WITH_BONUS)
                    factors.append(DecayFactor(
                        name="LINE_CONFIRMATION",
                        delta=bonus,
                        reason=f"Line moved {abs(line_diff):.1f}pts in your favor "
                               f"(CLV: +{movement_for_you:.1f}pts)",
                    ))
                elif movement_for_you < -self.LINE_MOVE_AGAINST_THRESHOLD:
                    # Line moved against you
                    penalty = max(-20, movement_for_you * abs(self.LINE_MOVE_AGAINST_PENALTY))
                    factors.append(DecayFactor(
                        name="LINE_EROSION",
                        delta=penalty,
                        reason=f"Line moved {abs(line_diff):.1f}pts AGAINST you "
                               f"(edge eroding: {movement_for_you:+.1f}pts)",
                    ))

        # ── Factor 3: Injury ─────────────────────────────────────
        if injury_flag:
            factors.append(DecayFactor(
                name="INJURY",
                delta=self.INJURY_PENALTY,
                reason="Significant injury reported after pick was generated",
            ))

        # ── Factor 4: Information Leak ────────────────────────────
        if info_leak_flag:
            factors.append(DecayFactor(
                name="INFO_LEAK",
                delta=self.INFO_LEAK_PENALTY,
                reason="Line jumped 2+ pts suddenly — possible information leak",
            ))

        # ── Apply all factors ─────────────────────────────────────
        current_conf = original_conf
        for f in factors:
            current_conf += f.delta

        # Clamp to 0-95
        current_conf = max(0, min(95, current_conf))
        current_tier = self.classify_tier(current_conf)

        return DecayResult(
            original_confidence=original_conf,
            current_confidence=current_conf,
            factors=factors,
            original_tier=original_tier,
            current_tier=current_tier,
            promoted=(self._tier_rank(current_tier) < self._tier_rank(original_tier)),
            demoted=(self._tier_rank(current_tier) > self._tier_rank(original_tier)),
        )

    @staticmethod
    def _tier_rank(tier: str) -> int:
        """Lower = better tier."""
        return {"TIER1": 0, "TIER2": 1, "LEAN": 2, "PASS": 3}.get(tier, 4)

    def apply_decay_to_slate(
        self,
        picks: List[Dict],
        current_lines: Optional[Dict[str, float]] = None,
    ) -> List[Dict]:
        """
        Apply decay to an entire slate of picks.

        Args:
            picks: List of pick dicts
            current_lines: {game_key: current_line, ...}

        Returns:
            Enriched list with decay results
        """
        results = []
        now = datetime.now()

        for pick in picks:
            game_key = pick.get("game", pick.get("game_key", ""))
            current_line = (current_lines or {}).get(game_key)

            decay = self.apply_decay(pick, current_time=now, current_line=current_line)

            enriched = {
                **pick,
                "decay": decay.to_dict(),
                "current_confidence": decay.current_confidence,
                "current_tier": decay.current_tier,
            }

            if decay.promoted:
                enriched["status_change"] = f"PROMOTED: {decay.original_tier} → {decay.current_tier}"
            elif decay.demoted:
                enriched["status_change"] = f"DEMOTED: {decay.original_tier} → {decay.current_tier}"

            results.append(enriched)

        return results


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 60)
    print("  CONFIDENCE DECAY ENGINE — Demo")
    print("═" * 60)

    engine = ConfidenceDecayEngine()

    # Demo: a pick from 3 hours ago where the line moved in our favor
    demo_pick = {
        "game": "CHI @ BKN",
        "pick": "UNDER 218.5",
        "pick_type": "UNDER",
        "line": 218.5,
        "confidence": 85,
        "tier": "TIER1",
        "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
    }

    # Line dropped further (Under got better)
    result = engine.apply_decay(demo_pick, current_line=217.0)
    print(f"\n  Pick: UNDER 218.5 (generated 3hrs ago)")
    print(f"  Current line: 217.0 (moved in our favor)")
    print(f"  Confidence: {result.original_confidence}% → {result.current_confidence:.0f}%")
    print(f"  Tier: {result.original_tier} → {result.current_tier}")

    for f in result.factors:
        print(f"    {f}")

    # Demo: a pick where the line moved against us
    demo_pick2 = {
        "game": "MIL @ ORL",
        "pick": "MIL +10.5",
        "pick_type": "SPREAD_AWAY",
        "line": 10.5,
        "confidence": 78,
        "tier": "TIER2",
        "timestamp": (datetime.now() - timedelta(hours=5)).isoformat(),
    }

    result2 = engine.apply_decay(demo_pick2, current_line=8.5)
    print(f"\n  Pick: MIL +10.5 (generated 5hrs ago)")
    print(f"  Current line: +8.5 (moved AGAINST us — less points)")
    print(f"  Confidence: {result2.original_confidence}% → {result2.current_confidence:.0f}%")
    print(f"  Tier: {result2.original_tier} → {result2.current_tier}")

    for f in result2.factors:
        print(f"    {f}")

    print()
