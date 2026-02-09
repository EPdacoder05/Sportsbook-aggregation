#!/usr/bin/env python3
"""
LINE FREEZE DETECTOR
=====================
Detects when books REFUSE to move a line despite heavy public action.

A Line Freeze occurs when:
  - Public betting % is heavily skewed (>65% on one side)
  - But the line hasn't moved (or barely moved) over multiple hours
  - This means the book is COMFORTABLE with their exposure
  - Translation: the book KNOWS the public side is wrong

Signal types:
  BOOK_TRAP:    >70% public, 0 movement for 4+ hours → books want that money
  SHARP_HOLD:   60-70% public, <0.5pt movement → sharps holding the line
  STEAM_FROZEN: Line moved once then froze despite continued public money

Usage:
    from engine.line_freeze_detector import LineFreezeDetector
    detector = LineFreezeDetector()
    signal = detector.detect(game_key, snapshots, public_pct)
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "data"


class FreezeSignal(Enum):
    BOOK_TRAP = "BOOK_TRAP"          # >70% public, zero movement — books want that money
    SHARP_HOLD = "SHARP_HOLD"        # 60-70% public, minimal movement — sharps holding
    STEAM_FROZEN = "STEAM_FROZEN"    # Line moved then froze — steam absorbed
    NONE = "NONE"                    # No freeze detected


@dataclass
class LineSnapshot:
    """A single point-in-time snapshot of a line."""
    timestamp: str          # ISO format
    spread: Optional[float] = None
    total: Optional[float] = None
    source: str = ""        # which book/API

    @property
    def dt(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)


@dataclass
class FreezeResult:
    """Result of freeze detection for one game/market."""
    game_key: str
    market: str             # "spread" or "total"
    signal: FreezeSignal
    public_pct: float       # % on the public side
    line_value: float       # current line
    movement: float         # total movement in observation window
    hours_frozen: float     # hours with <0.5pt movement
    confidence: float       # 0-100
    description: str

    def to_dict(self) -> Dict:
        return {
            "game_key": self.game_key,
            "market": self.market,
            "signal": self.signal.value,
            "public_pct": self.public_pct,
            "line_value": self.line_value,
            "movement": self.movement,
            "hours_frozen": round(self.hours_frozen, 1),
            "confidence": self.confidence,
            "description": self.description,
        }


class LineFreezeDetector:
    """
    Detects line freezes by analyzing snapshots of odds over time.

    The key insight: when 70%+ of bets are on one side but the line
    doesn't move, the book is telling you they WANT that money.
    The public is wrong.
    """

    # Thresholds
    BOOK_TRAP_PUBLIC_PCT = 70       # % of bets on one side
    SHARP_HOLD_PUBLIC_PCT = 60      # lower threshold for sharp hold
    MIN_FREEZE_HOURS = 2.0          # minimum hours for a freeze
    STRONG_FREEZE_HOURS = 4.0       # strong freeze
    MAX_MOVEMENT_FOR_FREEZE = 0.5   # line moved less than this = frozen

    def detect_spread_freeze(
        self,
        game_key: str,
        snapshots: List[LineSnapshot],
        public_pct_favorite: float,
    ) -> FreezeResult:
        """
        Detect freeze on the spread.

        Args:
            game_key: "CHI@BKN" etc.
            snapshots: list of LineSnapshot with .spread populated
            public_pct_favorite: % of bets on the favorite side
        """
        spreads = [(s.dt, s.spread) for s in snapshots if s.spread is not None]
        if len(spreads) < 2:
            return FreezeResult(
                game_key=game_key, market="spread",
                signal=FreezeSignal.NONE,
                public_pct=public_pct_favorite, line_value=0,
                movement=0, hours_frozen=0, confidence=0,
                description="Insufficient snapshots for freeze detection",
            )

        return self._analyze_freeze(
            game_key=game_key,
            market="spread",
            data_points=spreads,
            public_pct=public_pct_favorite,
        )

    def detect_total_freeze(
        self,
        game_key: str,
        snapshots: List[LineSnapshot],
        public_pct_over: float,
    ) -> FreezeResult:
        """
        Detect freeze on the total.

        Args:
            game_key: "CHI@BKN" etc.
            snapshots: list of LineSnapshot with .total populated
            public_pct_over: % of bets on the Over
        """
        totals = [(s.dt, s.total) for s in snapshots if s.total is not None]
        if len(totals) < 2:
            return FreezeResult(
                game_key=game_key, market="total",
                signal=FreezeSignal.NONE,
                public_pct=public_pct_over, line_value=0,
                movement=0, hours_frozen=0, confidence=0,
                description="Insufficient snapshots for freeze detection",
            )

        return self._analyze_freeze(
            game_key=game_key,
            market="total",
            data_points=totals,
            public_pct=public_pct_over,
        )

    def _analyze_freeze(
        self,
        game_key: str,
        market: str,
        data_points: List[Tuple[datetime, float]],
        public_pct: float,
    ) -> FreezeResult:
        """Core freeze detection logic."""
        # Sort by time
        data_points.sort(key=lambda x: x[0])

        first_time, first_val = data_points[0]
        last_time, last_val = data_points[-1]

        # Total movement
        total_movement = abs(last_val - first_val)

        # Time span
        time_span = (last_time - first_time).total_seconds() / 3600  # hours

        # Find the longest freeze window (consecutive points with <0.5pt change)
        max_freeze_hours = 0.0
        freeze_start = data_points[0][0]
        freeze_val = data_points[0][1]

        for i in range(1, len(data_points)):
            t, v = data_points[i]
            if abs(v - freeze_val) <= self.MAX_MOVEMENT_FOR_FREEZE:
                # Still frozen
                current_freeze = (t - freeze_start).total_seconds() / 3600
                max_freeze_hours = max(max_freeze_hours, current_freeze)
            else:
                # Line moved — reset freeze window
                freeze_start = t
                freeze_val = v

        # Check for steam-then-freeze pattern
        steam_frozen = False
        if len(data_points) >= 3:
            # Did the line move early then stop?
            early_movement = abs(data_points[1][1] - data_points[0][1])
            late_movement = abs(data_points[-1][1] - data_points[1][1])
            if early_movement >= 1.0 and late_movement <= 0.5:
                steam_frozen = True

        # Classify signal
        signal = FreezeSignal.NONE
        confidence = 0.0
        description = ""

        if public_pct >= self.BOOK_TRAP_PUBLIC_PCT and total_movement <= self.MAX_MOVEMENT_FOR_FREEZE:
            if max_freeze_hours >= self.STRONG_FREEZE_HOURS:
                signal = FreezeSignal.BOOK_TRAP
                confidence = min(95, 70 + (public_pct - 70) * 1.5 + max_freeze_hours * 2)
                description = (
                    f"BOOK TRAP: {public_pct:.0f}% public on one side, "
                    f"line frozen for {max_freeze_hours:.1f}hrs. "
                    f"Books WANT this money — public is wrong."
                )
            elif max_freeze_hours >= self.MIN_FREEZE_HOURS:
                signal = FreezeSignal.BOOK_TRAP
                confidence = min(85, 60 + (public_pct - 70) + max_freeze_hours * 3)
                description = (
                    f"BOOK TRAP: {public_pct:.0f}% public, "
                    f"frozen {max_freeze_hours:.1f}hrs. Developing trap signal."
                )

        elif public_pct >= self.SHARP_HOLD_PUBLIC_PCT and total_movement <= self.MAX_MOVEMENT_FOR_FREEZE:
            if max_freeze_hours >= self.MIN_FREEZE_HOURS:
                signal = FreezeSignal.SHARP_HOLD
                confidence = min(75, 50 + (public_pct - 60) * 1.5 + max_freeze_hours * 2)
                description = (
                    f"SHARP HOLD: {public_pct:.0f}% public, "
                    f"line barely moved ({total_movement:.1f}pts) over {max_freeze_hours:.1f}hrs. "
                    f"Sharps holding the line from the other side."
                )

        elif steam_frozen and public_pct >= self.SHARP_HOLD_PUBLIC_PCT:
            signal = FreezeSignal.STEAM_FROZEN
            confidence = min(80, 55 + (public_pct - 60) + max_freeze_hours * 2)
            description = (
                f"STEAM FROZEN: Line moved early then froze despite "
                f"{public_pct:.0f}% continuing to bet one side. "
                f"Initial move was absorbed by sharps."
            )

        if signal == FreezeSignal.NONE:
            description = (
                f"No freeze: {public_pct:.0f}% public, "
                f"{total_movement:.1f}pts movement over {time_span:.1f}hrs."
            )

        return FreezeResult(
            game_key=game_key,
            market=market,
            signal=signal,
            public_pct=public_pct,
            line_value=last_val,
            movement=total_movement,
            hours_frozen=max_freeze_hours,
            confidence=round(confidence),
            description=description,
        )

    def detect_from_cached_odds(self, game_key: str, public_pct: float,
                                market: str = "spread") -> Optional[FreezeResult]:
        """
        Run freeze detection using cached odds files in data/.

        Scans analysis_window_*.json for the game and builds snapshots.
        """
        snapshots = []
        for f in sorted(DATA_DIR.glob("analysis_window_*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                if game_key in data:
                    game_data = data[game_key]
                    # Try to extract timestamp from filename
                    parts = f.stem.split("_")
                    ts = f.stat().st_mtime
                    ts_str = datetime.fromtimestamp(ts).isoformat()

                    if market == "spread":
                        spread_data = game_data.get("spreads", {})
                        line = spread_data.get("consensus_line")
                        if line is not None:
                            snapshots.append(LineSnapshot(
                                timestamp=ts_str, spread=line, source=f.name
                            ))
                    elif market == "total":
                        total_data = game_data.get("totals", {})
                        line = total_data.get("consensus_line")
                        if line is not None:
                            snapshots.append(LineSnapshot(
                                timestamp=ts_str, total=line, source=f.name
                            ))
            except Exception:
                continue

        if not snapshots:
            return None

        if market == "spread":
            return self.detect_spread_freeze(game_key, snapshots, public_pct)
        else:
            return self.detect_total_freeze(game_key, snapshots, public_pct)


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    detector = LineFreezeDetector()

    # Demo with synthetic data
    print("═" * 60)
    print("  LINE FREEZE DETECTOR — Demo")
    print("═" * 60)

    # Simulate a book trap: 72% public on DET, line flat at -2.5 for 6 hours
    now = datetime.now()
    demo_snapshots = [
        LineSnapshot(timestamp=(now - timedelta(hours=6)).isoformat(), spread=-2.5),
        LineSnapshot(timestamp=(now - timedelta(hours=4)).isoformat(), spread=-2.5),
        LineSnapshot(timestamp=(now - timedelta(hours=2)).isoformat(), spread=-2.5),
        LineSnapshot(timestamp=(now - timedelta(hours=1)).isoformat(), spread=-2.5),
        LineSnapshot(timestamp=now.isoformat(), spread=-2.5),
    ]

    result = detector.detect_spread_freeze("DET@CHA", demo_snapshots, 68.0)
    print(f"\n  Game: DET @ CHA")
    print(f"  Signal: {result.signal.value}")
    print(f"  Confidence: {result.confidence}%")
    print(f"  {result.description}")
    print()
