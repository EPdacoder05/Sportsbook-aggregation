#!/usr/bin/env python3
"""
QUARTER-LINE SENSITIVITY DETECTOR
===================================
Tonight (Feb 9, 2026) we lost $38 on DET/CHA 1Q Under 53.5 because the
full-game total dropped 5 pts but the 1Q total barely moved.

Lesson: sharp money on the full-game total does NOT automatically justify
a 1Q bet. Quarter totals have their own pace dynamics, especially in Q1
where teams play at full intensity before fatigue kicks in.

Detection logic:
  1. Compare full-game total movement vs Q1 opening total
  2. If full-game dropped ≥3 pts but Q1 dropped <1 pt → QUARTER_MISMATCH
  3. If pace data shows both teams start fast → Q1_PACE_OVERRIDE
  4. Score: Only recommend quarter bets when BOTH game AND quarter lines agree

Signal types:
  QUARTER_MISMATCH:    Full-game total moved hard but 1Q barely moved → NO-BET on 1Q
  QUARTER_ALIGNED:     Both full and 1Q totals moved in same direction → 1Q bet OK
  Q1_PACE_OVERRIDE:    Pace data shows Q1 is typically faster → avoid 1Q Under

Usage:
    from engine.quarter_line_detector import QuarterLineDetector
    detector = QuarterLineDetector()
    result = detector.detect(
        game_key="DET@CHA",
        full_game_total_open=222.5,
        full_game_total_current=218.0,
        q1_total_open=55.0,
        q1_total_current=54.5,
    )
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class QuarterSignal(Enum):
    QUARTER_MISMATCH = "QUARTER_MISMATCH"    # Full-game moved but quarter didn't
    QUARTER_ALIGNED = "QUARTER_ALIGNED"      # Both moved together — safe
    Q1_PACE_OVERRIDE = "Q1_PACE_OVERRIDE"    # Pace data says Q1 is fast
    NONE = "NONE"


@dataclass
class QuarterLineResult:
    """Result of quarter-line sensitivity analysis."""
    game_key: str
    signal: QuarterSignal
    full_game_movement: float       # How much the full-game total moved
    quarter_movement: float         # How much the quarter total moved
    movement_ratio: float           # quarter_move / full_game_move (0=none, 1=proportional)
    q1_bet_safe: bool               # Is a Q1 bet supported by the data?
    confidence: float               # 0-100
    description: str
    recommendation: str

    def to_dict(self) -> Dict:
        return {
            "game_key": self.game_key,
            "signal": self.signal.value,
            "full_game_movement": round(self.full_game_movement, 1),
            "quarter_movement": round(self.quarter_movement, 1),
            "movement_ratio": round(self.movement_ratio, 2),
            "q1_bet_safe": self.q1_bet_safe,
            "confidence": round(self.confidence),
            "description": self.description,
            "recommendation": self.recommendation,
        }


class QuarterLineDetector:
    """
    Detects mismatches between full-game and quarter-level line movement.

    Core insight: Full-game Under bets are driven by fatigue/pace/game-script.
    1Q bets are driven by opening intensity, which is often HIGH even in
    low-total games.

    The $38 DET/CHA 1Q Under loss teaches: do NOT assume quarter lines track
    full-game lines proportionally.
    """

    # Thresholds
    FULL_GAME_MIN_MOVE = 2.0           # Full-game needs ≥2pt move to matter
    QUARTER_PROPORTIONAL_MIN = 0.40    # Quarter should move ≥40% of full-game
    MISMATCH_THRESHOLD = 0.25          # Quarter moved <25% of full-game → mismatch
    Q1_PACE_FAST_THRESHOLD = 56.0      # Q1 totals ≥56 are "fast starts"

    # Average NBA Q1 total (roughly 53-55 points)
    NBA_AVG_Q1_TOTAL = 54.0

    def detect(
        self,
        game_key: str,
        full_game_total_open: float,
        full_game_total_current: float,
        q1_total_open: Optional[float] = None,
        q1_total_current: Optional[float] = None,
        q1_pace_estimate: Optional[float] = None,
        direction: str = "UNDER",
    ) -> QuarterLineResult:
        """
        Analyze whether a Q1 bet is supported by the full-game line movement.

        Args:
            game_key: "DET@CHA" etc.
            full_game_total_open: Opening full-game total (e.g., 223.5)
            full_game_total_current: Current full-game total (e.g., 218.0)
            q1_total_open: Opening Q1 total (e.g., 55.0). None if unavailable.
            q1_total_current: Current Q1 total (e.g., 54.5). None if unavailable.
            q1_pace_estimate: Estimated Q1 pace (e.g., 56.0). None if unavailable.
            direction: "UNDER" or "OVER" — the direction of the full-game bet

        Returns:
            QuarterLineResult with safety assessment
        """
        full_game_move = abs(full_game_total_current - full_game_total_open)

        # If we have quarter data, compute proportionality
        if q1_total_open is not None and q1_total_current is not None:
            quarter_move = abs(q1_total_current - q1_total_open)

            # Direction check: did they move in the same direction?
            fg_direction = full_game_total_current - full_game_total_open  # negative = dropped
            q1_direction = q1_total_current - q1_total_open

            same_direction = (fg_direction < 0 and q1_direction < 0) or \
                             (fg_direction > 0 and q1_direction > 0)

            # Compute ratio
            if full_game_move > 0:
                ratio = quarter_move / full_game_move
            else:
                ratio = 1.0  # No full-game movement, quarter is fine

            # Check for mismatch
            if full_game_move >= self.FULL_GAME_MIN_MOVE and ratio < self.MISMATCH_THRESHOLD:
                return QuarterLineResult(
                    game_key=game_key,
                    signal=QuarterSignal.QUARTER_MISMATCH,
                    full_game_movement=full_game_move,
                    quarter_movement=quarter_move,
                    movement_ratio=ratio,
                    q1_bet_safe=False,
                    confidence=85,
                    description=(
                        f"QUARTER MISMATCH: Full-game total moved {full_game_move:.1f}pts "
                        f"but Q1 only moved {quarter_move:.1f}pts "
                        f"(ratio: {ratio:.0%}). "
                        f"Sharps hit the FULL GAME, not the quarter. "
                        f"Q1 pace dynamics are independent."
                    ),
                    recommendation=(
                        f"NO-BET on Q1 {direction}. The sharp money signal is "
                        f"on the full game — Q1 didn't follow. "
                        f"Learned the hard way: DET/CHA $38 loss on Feb 9."
                    ),
                )

            # Both moved proportionally — aligned
            if full_game_move >= self.FULL_GAME_MIN_MOVE and ratio >= self.QUARTER_PROPORTIONAL_MIN:
                if same_direction:
                    return QuarterLineResult(
                        game_key=game_key,
                        signal=QuarterSignal.QUARTER_ALIGNED,
                        full_game_movement=full_game_move,
                        quarter_movement=quarter_move,
                        movement_ratio=ratio,
                        q1_bet_safe=True,
                        confidence=75,
                        description=(
                            f"ALIGNED: Full-game moved {full_game_move:.1f}pts and "
                            f"Q1 tracked with {quarter_move:.1f}pts ({ratio:.0%}). "
                            f"Both moving same direction."
                        ),
                        recommendation=(
                            f"Q1 {direction} is SUPPORTED by the data. "
                            f"Both full-game and quarter lines confirm."
                        ),
                    )

        # Check pace override: if Q1 pace is typically fast, avoid 1Q Under
        if q1_pace_estimate is not None and direction == "UNDER":
            if q1_pace_estimate >= self.Q1_PACE_FAST_THRESHOLD:
                return QuarterLineResult(
                    game_key=game_key,
                    signal=QuarterSignal.Q1_PACE_OVERRIDE,
                    full_game_movement=full_game_move,
                    quarter_movement=0,
                    movement_ratio=0,
                    q1_bet_safe=False,
                    confidence=70,
                    description=(
                        f"Q1 PACE OVERRIDE: Expected Q1 pace is {q1_pace_estimate:.0f}pts "
                        f"(above {self.Q1_PACE_FAST_THRESHOLD:.0f} fast threshold). "
                        f"Teams typically come out hot in Q1."
                    ),
                    recommendation=(
                        f"AVOID Q1 Under. Even in low-total games, "
                        f"Q1 pace tends to run high."
                    ),
                )

        # Default: insufficient data for quarter analysis
        quarter_move = 0.0
        if q1_total_open is not None and q1_total_current is not None:
            quarter_move = abs(q1_total_current - q1_total_open)

        return QuarterLineResult(
            game_key=game_key,
            signal=QuarterSignal.NONE,
            full_game_movement=full_game_move,
            quarter_movement=quarter_move,
            movement_ratio=0,
            q1_bet_safe=True,  # No data to disqualify
            confidence=50,
            description="Insufficient quarter-level data for analysis.",
            recommendation="Proceed with caution — no quarter-line data available.",
        )

    def batch_detect(
        self,
        games: list,
        direction: str = "UNDER",
    ) -> list:
        """
        Run detection on a batch of games.

        Each game dict should have:
            game_key, full_open, full_current, q1_open (opt), q1_current (opt)
        """
        results = []
        for game in games:
            result = self.detect(
                game_key=game.get("game_key", "?"),
                full_game_total_open=game.get("full_open", 0),
                full_game_total_current=game.get("full_current", 0),
                q1_total_open=game.get("q1_open"),
                q1_total_current=game.get("q1_current"),
                q1_pace_estimate=game.get("q1_pace"),
                direction=direction,
            )
            results.append(result)
        return results


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 70)
    print("  QUARTER-LINE SENSITIVITY DETECTOR — Demo")
    print("  (Based on Feb 9, 2026 DET/CHA $38 1Q Under loss)")
    print("═" * 70)

    detector = QuarterLineDetector()

    # Recreate tonight's DET/CHA 1Q Under loss
    result = detector.detect(
        game_key="DET@CHA",
        full_game_total_open=222.5,
        full_game_total_current=218.0,
        q1_total_open=55.0,
        q1_total_current=54.5,  # Barely moved
        direction="UNDER",
    )
    print(f"\n  Game: DET @ CHA")
    print(f"  Signal: {result.signal.value}")
    print(f"  Q1 Bet Safe: {result.q1_bet_safe}")
    print(f"  {result.description}")
    print(f"  → {result.recommendation}")

    # Counter-example: CHI/BKN where everything aligned
    result2 = detector.detect(
        game_key="CHI@BKN",
        full_game_total_open=223.5,
        full_game_total_current=218.5,
        q1_total_open=55.5,
        q1_total_current=53.0,  # Also dropped proportionally
        direction="UNDER",
    )
    print(f"\n  Game: CHI @ BKN")
    print(f"  Signal: {result2.signal.value}")
    print(f"  Q1 Bet Safe: {result2.q1_bet_safe}")
    print(f"  {result2.description}")
    print(f"  → {result2.recommendation}")

    print()
