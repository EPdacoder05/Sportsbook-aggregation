#!/usr/bin/env python3
"""
SIGNAL CLASSIFICATION ENGINE
==============================
Separates PRIMARY signals (triggers that justify a bet) from
CONFIRMATION signals (supporting evidence that boosts confidence).

Problem this solves:
  Old system mixed "RLM 5pts against public" (primary trigger) with
  "team is 2-8 ATS L10" (supporting trend) and weighted them equally.
  This inflated confidence on weak plays.

New system:
  PRIMARY SIGNALS → These TRIGGER a bet. Without one, it's a PASS.
    - RLM_SPREAD:         Line moved 1.5+ pts against majority public bets
    - RLM_TOTAL:          Total moved 4+ pts against public over/under bets
    - ML_SPREAD_DIVERGE:  40%+ gap between ML% and spread%
    - LINE_FREEZE:        75%+ public but zero line movement (BOOK_TRAP)

  CONFIRMATION SIGNALS → These BOOST confidence on an existing primary signal.
    - ATS_EXTREME:        Team ATS record is extreme (0-10 or 8-2 L10)
    - BOOK_DISAGREEMENT:  1.5+ pt spread across books
    - CROSS_SOURCE_DIV:   DK vs Covers disagree by 15%+
    - PACE_MISMATCH:      Pace mismatches (fast vs slow team totals)
    - REST_ADVANTAGE:     B2B vs rested team
    - HOME_ROAD_SPLIT:    Extreme home/road performance split

Confidence Calculation:
    base = 50%
    + primary signal magnitude → +10-25%
    + each confirmation signal → +3-8%
    capped at 95%

Usage:
    from engine.signals import SignalClassifier, classify_game
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class SignalCategory(Enum):
    PRIMARY = "PRIMARY"
    CONFIRMATION = "CONFIRMATION"


class SignalType(Enum):
    # Primary signals
    RLM_SPREAD = "RLM_SPREAD"
    RLM_TOTAL = "RLM_TOTAL"
    ML_SPREAD_DIVERGENCE = "ML_SPREAD_DIVERGENCE"
    LINE_FREEZE = "LINE_FREEZE"

    # Confirmation signals
    ATS_EXTREME = "ATS_EXTREME"
    BOOK_DISAGREEMENT = "BOOK_DISAGREEMENT"
    CROSS_SOURCE_DIVERGENCE = "CROSS_SOURCE_DIVERGENCE"
    PACE_MISMATCH = "PACE_MISMATCH"
    REST_ADVANTAGE = "REST_ADVANTAGE"
    HOME_ROAD_SPLIT = "HOME_ROAD_SPLIT"


# Map each signal to its category
SIGNAL_CATEGORIES = {
    SignalType.RLM_SPREAD: SignalCategory.PRIMARY,
    SignalType.RLM_TOTAL: SignalCategory.PRIMARY,
    SignalType.ML_SPREAD_DIVERGENCE: SignalCategory.PRIMARY,
    SignalType.LINE_FREEZE: SignalCategory.PRIMARY,
    SignalType.ATS_EXTREME: SignalCategory.CONFIRMATION,
    SignalType.BOOK_DISAGREEMENT: SignalCategory.CONFIRMATION,
    SignalType.CROSS_SOURCE_DIVERGENCE: SignalCategory.CONFIRMATION,
    SignalType.PACE_MISMATCH: SignalCategory.CONFIRMATION,
    SignalType.REST_ADVANTAGE: SignalCategory.CONFIRMATION,
    SignalType.HOME_ROAD_SPLIT: SignalCategory.CONFIRMATION,
}

# Thresholds for primary signals
PRIMARY_THRESHOLDS = {
    SignalType.RLM_SPREAD: {
        "min_magnitude": 1.5,      # pts moved against public
        "strong_magnitude": 2.5,   # strong RLM
        "elite_magnitude": 3.5,    # elite RLM = Tier 1 territory
        "min_public_pct": 55,      # need 55%+ on one side
    },
    SignalType.RLM_TOTAL: {
        "min_drop": 2.0,           # total moved 2+ pts
        "strong_drop": 4.0,        # strong total move
        "elite_drop": 5.0,         # elite (like CHI/BKN 5.0pt drop)
        "min_public_pct": 55,
    },
    SignalType.ML_SPREAD_DIVERGENCE: {
        "min_gap": 15,             # 15%+ gap is meaningful
        "strong_gap": 30,          # 30%+ is strong
        "elite_gap": 40,           # 40%+ is a trap (like MIL/ORL 48%)
        "min_ml_pct": 70,          # ML fav needs 70%+ for the trap to matter
    },
    SignalType.LINE_FREEZE: {
        "min_public_pct": 65,      # 65%+ public
        "strong_public_pct": 70,   # 70%+ for strong freeze
        "min_hours": 2.0,          # frozen 2+ hours
        "strong_hours": 4.0,       # frozen 4+ hours
    },
}

# Confidence contributions
CONFIDENCE_CONTRIBUTIONS = {
    # Primary signals: base contribution
    SignalType.RLM_SPREAD: {"base": 15, "per_pt": 5, "max": 25},
    SignalType.RLM_TOTAL: {"base": 12, "per_pt": 3, "max": 22},
    SignalType.ML_SPREAD_DIVERGENCE: {"base": 10, "per_pct": 0.3, "max": 20},
    SignalType.LINE_FREEZE: {"base": 10, "per_hour": 2, "max": 18},
    # Confirmation signals: smaller boost
    SignalType.ATS_EXTREME: {"base": 5, "max": 8},
    SignalType.BOOK_DISAGREEMENT: {"base": 3, "max": 6},
    SignalType.CROSS_SOURCE_DIVERGENCE: {"base": 3, "max": 5},
    SignalType.PACE_MISMATCH: {"base": 3, "max": 5},
    SignalType.REST_ADVANTAGE: {"base": 4, "max": 7},
    SignalType.HOME_ROAD_SPLIT: {"base": 3, "max": 5},
}


@dataclass
class DetectedSignal:
    """A single detected signal with its metadata."""
    signal_type: SignalType
    category: SignalCategory
    magnitude: float          # How strong is this signal (varies by type)
    confidence_add: float     # How much confidence does this add
    description: str
    raw_data: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "type": self.signal_type.value,
            "category": self.category.value,
            "magnitude": round(self.magnitude, 2),
            "confidence_add": round(self.confidence_add, 1),
            "description": self.description,
        }


@dataclass
class GameSignalProfile:
    """Complete signal profile for a game."""
    game_key: str
    primary_signals: List[DetectedSignal] = field(default_factory=list)
    confirmation_signals: List[DetectedSignal] = field(default_factory=list)
    total_confidence: float = 50.0    # base 50%
    has_primary: bool = False
    tier: str = "PASS"
    recommended_units: float = 0.0
    pick_side: str = ""

    def add_signal(self, signal: DetectedSignal):
        if signal.category == SignalCategory.PRIMARY:
            self.primary_signals.append(signal)
            self.has_primary = True
        else:
            self.confirmation_signals.append(signal)

        self.total_confidence = min(95, self.total_confidence + signal.confidence_add)
        self._update_tier()

    def _update_tier(self):
        """Update tier based on confidence and primary signal presence."""
        if not self.has_primary:
            self.tier = "PASS"
            self.recommended_units = 0
            return

        if self.total_confidence >= 80:
            self.tier = "TIER1"
            self.recommended_units = 2.0
        elif self.total_confidence >= 70:
            self.tier = "TIER2"
            self.recommended_units = 1.5
        elif self.total_confidence >= 60:
            self.tier = "LEAN"
            self.recommended_units = 1.0
        else:
            self.tier = "PASS"
            self.recommended_units = 0

    def to_dict(self) -> Dict:
        return {
            "game_key": self.game_key,
            "has_primary": self.has_primary,
            "tier": self.tier,
            "confidence": round(self.total_confidence, 1),
            "recommended_units": self.recommended_units,
            "pick_side": self.pick_side,
            "primary_signals": [s.to_dict() for s in self.primary_signals],
            "confirmation_signals": [s.to_dict() for s in self.confirmation_signals],
        }

    def print_summary(self):
        """Pretty-print signal profile."""
        emoji = {"TIER1": "🔥🔥🔥", "TIER2": "🔥", "LEAN": "👀", "PASS": "❌"}
        print(f"\n  {emoji.get(self.tier, '')} {self.game_key} — {self.tier} "
              f"({self.total_confidence:.0f}% confidence)")

        if self.pick_side:
            print(f"  ➤ {self.pick_side} ({self.recommended_units}U)")

        if self.primary_signals:
            print("  PRIMARY:")
            for s in self.primary_signals:
                print(f"    ★ {s.description}")

        if self.confirmation_signals:
            print("  CONFIRMATION:")
            for s in self.confirmation_signals:
                print(f"    ✓ {s.description}")

        if not self.has_primary:
            print("  ⚠ No primary signal — PASS regardless of confirmation count")


class SignalClassifier:
    """Classifies signals for a game and produces a GameSignalProfile."""

    def classify(
        self,
        game_key: str,
        spread_data: Optional[Dict] = None,
        total_data: Optional[Dict] = None,
        ml_data: Optional[Dict] = None,
        public_data: Optional[Dict] = None,
        ats_data: Optional[Dict] = None,
        freeze_data: Optional[Dict] = None,
        book_data: Optional[Dict] = None,
    ) -> GameSignalProfile:
        """
        Run all signal detection and return a classified profile.

        Args:
            spread_data: {"open": -3, "current": -4, "public_pct": 68, ...}
            total_data:  {"open": 223.5, "current": 218.5, "over_pct": 64, ...}
            ml_data:     {"away_ml_pct": 77, "home_ml_pct": 23, ...}
            public_data: {"spread_fav_pct": 68, "total_over_pct": 64, ...}
            ats_data:    {"away_l10_ats": "3-7", "home_l10_ats": "2-8", ...}
            freeze_data: {"signal": "BOOK_TRAP", "hours_frozen": 6, ...}
            book_data:   {"spread_range": 1.5, "total_range": 2.0, ...}
        """
        profile = GameSignalProfile(game_key=game_key)

        # ── Primary Signal Detection ─────────────────────────────

        # 1. Spread RLM
        if spread_data:
            sig = self._detect_spread_rlm(spread_data)
            if sig:
                profile.add_signal(sig)

        # 2. Total RLM
        if total_data:
            sig = self._detect_total_rlm(total_data)
            if sig:
                profile.add_signal(sig)

        # 3. ML-Spread Divergence
        if ml_data and public_data:
            sig = self._detect_ml_spread_divergence(ml_data, public_data)
            if sig:
                profile.add_signal(sig)

        # 4. Line Freeze
        if freeze_data:
            sig = self._detect_line_freeze(freeze_data)
            if sig:
                profile.add_signal(sig)

        # ── Confirmation Signal Detection ─────────────────────────

        # 5. ATS Extremes
        if ats_data:
            sig = self._detect_ats_extreme(ats_data)
            if sig:
                profile.add_signal(sig)

        # 6. Book Disagreement
        if book_data:
            sig = self._detect_book_disagreement(book_data)
            if sig:
                profile.add_signal(sig)

        return profile

    # ── Primary Detectors ─────────────────────────────────────────

    def _detect_spread_rlm(self, data: Dict) -> Optional[DetectedSignal]:
        """Detect Reverse Line Movement on spread."""
        thresholds = PRIMARY_THRESHOLDS[SignalType.RLM_SPREAD]
        open_s = data.get("open", 0)
        curr_s = data.get("current", 0)
        public_pct = data.get("public_pct", 50)

        magnitude = abs(curr_s - open_s)

        if magnitude < thresholds["min_magnitude"] or public_pct < thresholds["min_public_pct"]:
            return None

        # Calculate confidence contribution
        conf = CONFIDENCE_CONTRIBUTIONS[SignalType.RLM_SPREAD]
        contrib = min(conf["max"], conf["base"] + (magnitude - 1.5) * conf["per_pt"])

        level = "ELITE" if magnitude >= thresholds["elite_magnitude"] else \
                "STRONG" if magnitude >= thresholds["strong_magnitude"] else "MODERATE"

        return DetectedSignal(
            signal_type=SignalType.RLM_SPREAD,
            category=SignalCategory.PRIMARY,
            magnitude=magnitude,
            confidence_add=contrib,
            description=f"{level} RLM: {magnitude:.1f}pts against {public_pct:.0f}% public "
                        f"(open {open_s:+.1f} → curr {curr_s:+.1f})",
            raw_data=data,
        )

    def _detect_total_rlm(self, data: Dict) -> Optional[DetectedSignal]:
        """Detect RLM on totals."""
        thresholds = PRIMARY_THRESHOLDS[SignalType.RLM_TOTAL]
        open_t = data.get("open", 0)
        curr_t = data.get("current", 0)
        over_pct = data.get("over_pct", 50)

        drop = abs(curr_t - open_t)
        total_went_down = curr_t < open_t

        # RLM: public on Over but total dropped (or public Under but total rose)
        is_rlm = (over_pct >= thresholds["min_public_pct"] and total_went_down) or \
                 ((100 - over_pct) >= thresholds["min_public_pct"] and not total_went_down)

        if not is_rlm or drop < thresholds["min_drop"]:
            return None

        conf = CONFIDENCE_CONTRIBUTIONS[SignalType.RLM_TOTAL]
        contrib = min(conf["max"], conf["base"] + (drop - 2.0) * conf["per_pt"])

        side = "UNDER" if total_went_down else "OVER"
        level = "ELITE" if drop >= thresholds["elite_drop"] else \
                "STRONG" if drop >= thresholds["strong_drop"] else "MODERATE"

        return DetectedSignal(
            signal_type=SignalType.RLM_TOTAL,
            category=SignalCategory.PRIMARY,
            magnitude=drop,
            confidence_add=contrib,
            description=f"{level} TOTAL RLM → {side} {curr_t}: {drop:.1f}pts moved against "
                        f"{over_pct:.0f}% {'Over' if total_went_down else 'Under'} public "
                        f"(open {open_t} → {curr_t})",
            raw_data=data,
        )

    def _detect_ml_spread_divergence(self, ml_data: Dict,
                                     public_data: Dict) -> Optional[DetectedSignal]:
        """Detect ML vs Spread divergence trap."""
        thresholds = PRIMARY_THRESHOLDS[SignalType.ML_SPREAD_DIVERGENCE]

        ml_fav_pct = max(ml_data.get("away_ml_pct", 50), ml_data.get("home_ml_pct", 50))
        spread_fav_pct = public_data.get("spread_fav_pct", 50)
        gap = abs(ml_fav_pct - spread_fav_pct)

        if gap < thresholds["min_gap"] or ml_fav_pct < thresholds["min_ml_pct"]:
            return None

        conf = CONFIDENCE_CONTRIBUTIONS[SignalType.ML_SPREAD_DIVERGENCE]
        contrib = min(conf["max"], conf["base"] + gap * conf["per_pct"])

        level = "ELITE" if gap >= thresholds["elite_gap"] else \
                "STRONG" if gap >= thresholds["strong_gap"] else "MODERATE"

        return DetectedSignal(
            signal_type=SignalType.ML_SPREAD_DIVERGENCE,
            category=SignalCategory.PRIMARY,
            magnitude=gap,
            confidence_add=contrib,
            description=f"{level} DIVERGENCE TRAP: {ml_fav_pct:.0f}% ML but only "
                        f"{spread_fav_pct:.0f}% spread = {gap:.0f}% gap. "
                        f"Public says 'win but not cover' → sharp on dog + points.",
            raw_data={**ml_data, **public_data},
        )

    def _detect_line_freeze(self, data: Dict) -> Optional[DetectedSignal]:
        """Detect line freeze from LineFreezeDetector output."""
        thresholds = PRIMARY_THRESHOLDS[SignalType.LINE_FREEZE]

        signal = data.get("signal", "NONE")
        public_pct = data.get("public_pct", 50)
        hours = data.get("hours_frozen", 0)

        if signal == "NONE" or public_pct < thresholds["min_public_pct"]:
            return None

        conf = CONFIDENCE_CONTRIBUTIONS[SignalType.LINE_FREEZE]
        contrib = min(conf["max"], conf["base"] + hours * conf["per_hour"])

        return DetectedSignal(
            signal_type=SignalType.LINE_FREEZE,
            category=SignalCategory.PRIMARY,
            magnitude=hours,
            confidence_add=contrib,
            description=f"LINE FREEZE ({signal}): {public_pct:.0f}% public, "
                        f"line frozen {hours:.1f}hrs. Books want this money.",
            raw_data=data,
        )

    # ── Confirmation Detectors ────────────────────────────────────

    def _detect_ats_extreme(self, data: Dict) -> Optional[DetectedSignal]:
        """Detect extreme ATS records."""
        for side in ["away", "home"]:
            l10 = data.get(f"{side}_l10_ats", "")
            if not l10 or "-" not in l10:
                continue
            try:
                wins = int(l10.split("-")[0])
                losses = int(l10.split("-")[1])
            except (ValueError, IndexError):
                continue

            if wins <= 2 and (wins + losses) >= 8:
                return DetectedSignal(
                    signal_type=SignalType.ATS_EXTREME,
                    category=SignalCategory.CONFIRMATION,
                    magnitude=wins,
                    confidence_add=CONFIDENCE_CONTRIBUTIONS[SignalType.ATS_EXTREME]["base"],
                    description=f"ATS EXTREME: {side.upper()} team is {l10} ATS L10 — fade territory",
                    raw_data=data,
                )
            elif wins >= 7 and (wins + losses) >= 8:
                return DetectedSignal(
                    signal_type=SignalType.ATS_EXTREME,
                    category=SignalCategory.CONFIRMATION,
                    magnitude=wins,
                    confidence_add=CONFIDENCE_CONTRIBUTIONS[SignalType.ATS_EXTREME]["base"],
                    description=f"ATS HOT: {side.upper()} team is {l10} ATS L10 — ride streak",
                    raw_data=data,
                )

        return None

    def _detect_book_disagreement(self, data: Dict) -> Optional[DetectedSignal]:
        """Detect when books disagree on the number."""
        spread_range = data.get("spread_range", 0)
        if spread_range >= 1.5:
            return DetectedSignal(
                signal_type=SignalType.BOOK_DISAGREEMENT,
                category=SignalCategory.CONFIRMATION,
                magnitude=spread_range,
                confidence_add=CONFIDENCE_CONTRIBUTIONS[SignalType.BOOK_DISAGREEMENT]["base"],
                description=f"BOOK DISAGREEMENT: {spread_range:.1f}pt spread range across books — shop the best line",
                raw_data=data,
            )
        return None
