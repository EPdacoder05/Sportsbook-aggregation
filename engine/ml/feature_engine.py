"""
Feature Engineering Pipeline for Sports Betting ML.

Transforms raw game/odds/signal data into ML-ready feature vectors.
Handles missing data, normalization, and temporal feature extraction.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class FeatureEngine:
    """
    Converts raw game analysis into fixed-dimension feature vectors for
    supervised and unsupervised models.

    Feature Groups (32 total features):
        - Spread features (6)
        - Total features (6)
        - Moneyline features (4)
        - Book consensus features (4)
        - Signal features (6)
        - Contextual features (6)
    """

    FEATURE_NAMES: List[str] = [
        # Spread (6)
        "spread_open",
        "spread_current",
        "spread_movement",
        "spread_public_pct",
        "spread_rlm_flag",       # 1 if line moved opposite public
        "spread_range_across_books",
        # Total (6)
        "total_open",
        "total_current",
        "total_movement",
        "total_over_pct",
        "total_rlm_flag",
        "total_range_across_books",
        # Moneyline (4)
        "home_ml_odds",
        "away_ml_odds",
        "ml_implied_prob_home",
        "ml_spread_divergence",  # gap between ML implied and spread implied
        # Book consensus (4)
        "book_count",
        "spread_stdev",
        "total_stdev",
        "max_line_diff",
        # Signal profile (6)
        "primary_signal_count",
        "confirmation_signal_count",
        "total_confidence_add",
        "has_rlm",
        "has_line_freeze",
        "has_book_disagreement",
        # Context (6)
        "hours_to_tipoff",
        "home_rest_days",
        "away_rest_days",
        "home_ats_pct",
        "away_ats_pct",
        "is_national_tv",
    ]

    NUM_FEATURES = len(FEATURE_NAMES)

    # ── Public API ────────────────────────────────────────────────

    def extract(
        self,
        odds_data: Optional[Dict] = None,
        signal_profile: Optional[Any] = None,
        context: Optional[Dict] = None,
    ) -> np.ndarray:
        """
        Build a 32-element feature vector from raw analysis data.

        Missing data → 0.0 (safe default; models trained with this convention).
        """
        vec = np.zeros(self.NUM_FEATURES, dtype=np.float64)
        odds = odds_data or {}
        ctx = context or {}

        # ── Spread features ───────────────────────────────────────
        spread = odds.get("spread", {})
        s_open = self._safe(spread.get("open"))
        s_curr = self._safe(spread.get("current"))
        s_pub = self._safe(spread.get("public_pct"))

        vec[0] = s_open
        vec[1] = s_curr
        vec[2] = s_curr - s_open if (s_open and s_curr) else 0.0
        vec[3] = s_pub
        vec[4] = self._rlm_flag(s_open, s_curr, s_pub)
        vec[5] = self._safe(odds.get("books", {}).get("spread_range"))

        # ── Total features ────────────────────────────────────────
        total = odds.get("total", {})
        t_open = self._safe(total.get("open"))
        t_curr = self._safe(total.get("current"))
        t_over = self._safe(total.get("over_pct"))

        vec[6] = t_open
        vec[7] = t_curr
        vec[8] = t_curr - t_open if (t_open and t_curr) else 0.0
        vec[9] = t_over
        vec[10] = self._rlm_flag(t_open, t_curr, t_over)
        vec[11] = self._safe(odds.get("books", {}).get("total_range"))

        # ── Moneyline features ────────────────────────────────────
        ml = odds.get("ml", {})
        home_ml = self._safe(ml.get("home_ml"))
        away_ml = self._safe(ml.get("away_ml"))
        vec[12] = home_ml
        vec[13] = away_ml
        vec[14] = self._ml_to_prob(home_ml)
        vec[15] = self._ml_spread_divergence(home_ml, s_curr)

        # ── Book consensus ────────────────────────────────────────
        books = odds.get("books", {})
        vec[16] = self._safe(books.get("book_count"))
        vec[17] = self._safe(books.get("spread_stdev"))
        vec[18] = self._safe(books.get("total_stdev"))
        vec[19] = self._safe(books.get("max_line_diff"))

        # ── Signal profile ────────────────────────────────────────
        if signal_profile and hasattr(signal_profile, "signals"):
            primary = [
                s for s in signal_profile.signals
                if hasattr(s, "category") and str(s.category) == "PRIMARY"
            ]
            confirmation = [
                s for s in signal_profile.signals
                if hasattr(s, "category") and str(s.category) == "CONFIRMATION"
            ]
            vec[20] = len(primary)
            vec[21] = len(confirmation)
            vec[22] = sum(
                getattr(s, "confidence_add", 0) for s in signal_profile.signals
            )
            vec[23] = 1.0 if any(
                "RLM" in str(getattr(s, "signal_type", "")) for s in signal_profile.signals
            ) else 0.0
            vec[24] = 1.0 if any(
                "LINE_FREEZE" in str(getattr(s, "signal_type", "")) for s in signal_profile.signals
            ) else 0.0
            vec[25] = 1.0 if any(
                "BOOK_DISAGREEMENT" in str(getattr(s, "signal_type", "")) for s in signal_profile.signals
            ) else 0.0

        # ── Context ───────────────────────────────────────────────
        vec[26] = self._safe(ctx.get("hours_to_tipoff"))
        vec[27] = self._safe(ctx.get("home_rest_days"))
        vec[28] = self._safe(ctx.get("away_rest_days"))
        vec[29] = self._safe(ctx.get("home_ats_pct"))
        vec[30] = self._safe(ctx.get("away_ats_pct"))
        vec[31] = 1.0 if ctx.get("is_national_tv") else 0.0

        return vec

    def extract_batch(
        self,
        games: List[Dict],
    ) -> np.ndarray:
        """Extract features for a list of games → (N, 32) array."""
        rows = []
        for g in games:
            row = self.extract(
                odds_data=g.get("odds_data"),
                signal_profile=g.get("signal_profile"),
                context=g.get("context"),
            )
            rows.append(row)
        return np.vstack(rows) if rows else np.empty((0, self.NUM_FEATURES))

    # ── Internals ─────────────────────────────────────────────────

    @staticmethod
    def _safe(val, default: float = 0.0) -> float:
        """Safely cast to float, returning default on None/error."""
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _rlm_flag(
        open_line: float,
        current_line: float,
        public_pct: float,
    ) -> float:
        """
        1.0 if line moved OPPOSITE to public money direction, else 0.0.
        Requires all three values to be non-zero.
        """
        if not (open_line and current_line and public_pct):
            return 0.0
        movement = current_line - open_line
        # Public on favorite side → public_pct > 50 → line should move more negative
        # If line moved positive (less negative) → reverse movement → RLM
        if public_pct > 55 and movement > 0.5:
            return 1.0
        if public_pct < 45 and movement < -0.5:
            return 1.0
        return 0.0

    @staticmethod
    def _ml_to_prob(ml_odds: float) -> float:
        """American odds → implied probability."""
        if ml_odds == 0:
            return 0.0
        if ml_odds > 0:
            return 100.0 / (ml_odds + 100.0)
        return abs(ml_odds) / (abs(ml_odds) + 100.0)

    @staticmethod
    def _ml_spread_divergence(home_ml: float, spread: float) -> float:
        """
        Measures gap between ML implied probability and spread-implied
        probability. Larger gaps indicate potential mispricing.
        """
        if home_ml == 0 or spread == 0:
            return 0.0
        ml_prob = (
            abs(home_ml) / (abs(home_ml) + 100.0)
            if home_ml < 0
            else 100.0 / (home_ml + 100.0)
        )
        # Rough spread→prob conversion: each point ≈ 3% probability
        spread_prob = 0.5 + (abs(spread) * 0.03) * (1 if spread < 0 else -1)
        spread_prob = max(0.05, min(0.95, spread_prob))
        return abs(ml_prob - spread_prob) * 100  # Return as percentage points
