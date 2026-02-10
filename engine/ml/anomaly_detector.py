"""
Unsupervised Anomaly Detector for Sports Betting.

Uses Isolation Forest + statistical outlier detection to identify:
  - Unusual line movements (potential sharp/insider action)
  - Abnormal book disagreements
  - Suspicious public money patterns
  - Games with feature profiles unlike anything seen before

These anomalies are surfaced as additional signals to the betting engine
WITHOUT requiring labeled data — pure unsupervised learning.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path("data/ml")

# Minimum games to fit the anomaly detector
MIN_FIT_SAMPLES = 30
# Contamination: expected proportion of anomalies
CONTAMINATION = 0.10
# Z-score threshold for statistical outlier features
Z_SCORE_THRESHOLD = 2.5


class AnomalyDetector:
    """
    Unsupervised anomaly detection on game feature vectors.

    Two-layer approach:
        1. Isolation Forest — learns "normal" game profiles, flags outliers
        2. Z-score per feature — identifies WHICH features are anomalous

    Usage:
        detector = AnomalyDetector()
        detector.fit(historical_features)  # (N, 32) array
        result = detector.detect(new_game_features)  # (32,) vector
        # result = {
        #     "is_anomaly": True,
        #     "anomaly_score": -0.42,  # More negative = more anomalous
        #     "anomalous_features": ["spread_movement", "ml_spread_divergence"],
        #     "z_scores": {...},
        # }
    """

    def __init__(self):
        self.model = None
        self.is_fitted = False
        self.baseline_mean: Optional[np.ndarray] = None
        self.baseline_std: Optional[np.ndarray] = None
        self.fit_count = 0
        self.historical_data: List[List[float]] = []
        self.detected_anomalies: List[Dict] = []

        self._state_path = DATA_DIR / "anomaly_detector.json"
        self._load_state()

    # ── Public API ────────────────────────────────────────────────

    def ingest(self, features: np.ndarray, game_key: str = ""):
        """
        Add a game's features to the historical pool.
        Auto-fits when enough data accumulates.
        """
        self.historical_data.append(features.tolist())

        total = len(self.historical_data)
        if total >= MIN_FIT_SAMPLES and (
            not self.is_fitted or total % MIN_FIT_SAMPLES == 0
        ):
            self.fit()

        self._save_state()

    def fit(self, X: Optional[np.ndarray] = None):
        """
        Fit the Isolation Forest on historical data.

        Args:
            X: Optional explicit training array. If None, uses accumulated data.
        """
        if X is None:
            if len(self.historical_data) < MIN_FIT_SAMPLES:
                logger.warning(
                    f"Only {len(self.historical_data)} samples, "
                    f"need {MIN_FIT_SAMPLES} to fit"
                )
                return
            X = np.array(self.historical_data)

        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            logger.error("scikit-learn not installed. Run: pip install scikit-learn")
            return

        self.model = IsolationForest(
            n_estimators=100,
            contamination=CONTAMINATION,
            max_features=0.8,     # Feature subsampling
            bootstrap=True,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X)

        # Compute baseline statistics for z-score detection
        self.baseline_mean = np.mean(X, axis=0)
        self.baseline_std = np.std(X, axis=0) + 1e-8  # Avoid div/0

        self.is_fitted = True
        self.fit_count += 1
        logger.info(
            f"Anomaly detector fitted on {len(X)} samples "
            f"(fit #{self.fit_count})"
        )

        self._save_state()

    def detect(
        self,
        features: np.ndarray,
        game_key: str = "",
    ) -> Dict[str, Any]:
        """
        Detect if a game's feature vector is anomalous.

        Returns:
            {
                "is_anomaly": bool,
                "anomaly_score": float,     # Isolation Forest score
                "anomalous_features": [],   # Feature names with extreme z-scores
                "z_scores": {},             # All feature z-scores
                "top_anomalies": [],        # Top 3 most anomalous features
            }
        """
        if not self.is_fitted:
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "anomalous_features": [],
                "z_scores": {},
                "top_anomalies": [],
                "reason": "Detector not yet fitted",
            }

        X = features.reshape(1, -1)

        # ── Isolation Forest score ────────────────────────────────
        # Negative = anomaly, positive = normal
        iso_score = float(self.model.decision_function(X)[0])
        iso_pred = int(self.model.predict(X)[0])  # -1=anomaly, 1=normal
        is_anomaly = iso_pred == -1

        # ── Z-score per feature ───────────────────────────────────
        from engine.ml.feature_engine import FeatureEngine

        z_scores_raw = (features - self.baseline_mean) / self.baseline_std
        z_scores = {}
        anomalous_features = []

        for i, z in enumerate(z_scores_raw):
            name = (
                FeatureEngine.FEATURE_NAMES[i]
                if i < len(FeatureEngine.FEATURE_NAMES)
                else f"feature_{i}"
            )
            z_val = float(z)
            z_scores[name] = round(z_val, 3)

            if abs(z_val) > Z_SCORE_THRESHOLD:
                anomalous_features.append(name)

        # Top 3 most extreme features
        sorted_features = sorted(
            z_scores.items(), key=lambda x: abs(x[1]), reverse=True
        )
        top_anomalies = [
            {"feature": name, "z_score": z, "severity": self._severity(z)}
            for name, z in sorted_features[:3]
        ]

        result = {
            "is_anomaly": is_anomaly or len(anomalous_features) >= 3,
            "anomaly_score": round(iso_score, 4),
            "anomalous_features": anomalous_features,
            "z_scores": z_scores,
            "top_anomalies": top_anomalies,
            "game_key": game_key,
        }

        if result["is_anomaly"]:
            result["timestamp"] = datetime.utcnow().isoformat()
            self.detected_anomalies.append(result)
            logger.warning(
                f"ANOMALY DETECTED for {game_key}: "
                f"score={iso_score:.3f}, "
                f"anomalous_features={anomalous_features}"
            )

        return result

    def detect_batch(
        self,
        features: np.ndarray,
        game_keys: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Detect anomalies across a slate of games."""
        results = []
        keys = game_keys or ["" for _ in range(len(features))]
        for i, row in enumerate(features):
            results.append(self.detect(row, game_key=keys[i]))
        return results

    def get_status(self) -> Dict[str, Any]:
        """Return detector status."""
        return {
            "is_fitted": self.is_fitted,
            "fit_count": self.fit_count,
            "historical_samples": len(self.historical_data),
            "detected_anomalies": len(self.detected_anomalies),
            "min_samples_required": MIN_FIT_SAMPLES,
            "contamination": CONTAMINATION,
        }

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _severity(z_score: float) -> str:
        """Classify z-score severity."""
        z = abs(z_score)
        if z >= 4.0:
            return "EXTREME"
        if z >= 3.0:
            return "HIGH"
        if z >= 2.5:
            return "MODERATE"
        return "LOW"

    # ── Persistence ───────────────────────────────────────────────

    def _save_state(self):
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "is_fitted": self.is_fitted,
            "fit_count": self.fit_count,
            "historical_data": self.historical_data[-500:],  # Keep last 500
            "detected_anomalies": self.detected_anomalies[-100:],
            "baseline_mean": (
                self.baseline_mean.tolist() if self.baseline_mean is not None else None
            ),
            "baseline_std": (
                self.baseline_std.tolist() if self.baseline_std is not None else None
            ),
        }
        with open(self._state_path, "w") as f:
            json.dump(state, f)

    def _load_state(self):
        if self._state_path.exists():
            try:
                with open(self._state_path) as f:
                    state = json.load(f)
                self.is_fitted = state.get("is_fitted", False)
                self.fit_count = state.get("fit_count", 0)
                self.historical_data = state.get("historical_data", [])
                self.detected_anomalies = state.get("detected_anomalies", [])
                bm = state.get("baseline_mean")
                bs = state.get("baseline_std")
                if bm is not None:
                    self.baseline_mean = np.array(bm)
                if bs is not None:
                    self.baseline_std = np.array(bs)

                # Re-fit if we had a fitted model
                if self.is_fitted and len(self.historical_data) >= MIN_FIT_SAMPLES:
                    self.fit()

                logger.info(
                    f"Loaded anomaly detector: {len(self.historical_data)} samples, "
                    f"{len(self.detected_anomalies)} anomalies"
                )
            except Exception as e:
                logger.error(f"Failed to load anomaly state: {e}")
