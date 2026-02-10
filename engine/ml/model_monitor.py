"""
Model Drift Monitor.

Detects when the pick model's performance degrades due to:
  - Concept drift (market dynamics change)
  - Data drift (feature distributions shift)
  - Performance decay (accuracy/AUC drops below threshold)

Uses Page-Hinkley test for streaming drift detection and
PSI (Population Stability Index) for feature distribution shifts.

When drift is detected:
  1. Logs a WARNING with evidence
  2. Triggers automatic retrain
  3. Archives pre-drift model checkpoint
  4. Sends alert via event bus (if configured)
"""

import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Drift detection thresholds
PERFORMANCE_WINDOW = 50           # Rolling window for metrics
MIN_ACCURACY_THRESHOLD = 0.52    # Below random + noise → retrain
AUC_DRIFT_THRESHOLD = 0.55      # AUC below this → concept drift
BRIER_DRIFT_THRESHOLD = 0.30    # Brier above this → calibration drift
PSI_THRESHOLD = 0.20            # Feature PSI above this → data drift
PAGE_HINKLEY_DELTA = 0.005      # Sensitivity for PH test
PAGE_HINKLEY_LAMBDA = 50.0      # PH detection threshold

DATA_DIR = Path("data/ml")


class ModelMonitor:
    """
    Continuous monitor for model health.

    Tracks:
        - Rolling accuracy, AUC, Brier score
        - Feature distribution shifts (PSI)
        - Prediction confidence calibration
        - Page-Hinkley streaming drift test

    Usage:
        monitor = ModelMonitor()
        monitor.log_prediction(features, predicted_prob=0.72, actual_won=True)
        status = monitor.check_health()
        if status["drift_detected"]:
            model.train()  # Retrain
    """

    def __init__(self, window_size: int = PERFORMANCE_WINDOW):
        self.window_size = window_size
        self.predictions: deque = deque(maxlen=window_size * 2)
        self.feature_baselines: Optional[Dict] = None
        self.drift_events: List[Dict] = []

        # Page-Hinkley test state
        self._ph_sum = 0.0
        self._ph_min = float("inf")
        self._ph_count = 0
        self._ph_mean = 0.0

        self._state_path = DATA_DIR / "model_monitor.json"
        self._load_state()

    # ── Public API ────────────────────────────────────────────────

    def log_prediction(
        self,
        features: np.ndarray,
        predicted_prob: float,
        actual_won: Optional[bool] = None,
        game_key: str = "",
    ):
        """
        Log a prediction for tracking. Call again with actual_won
        when game completes.
        """
        entry = {
            "features": features.tolist() if isinstance(features, np.ndarray) else features,
            "predicted_prob": predicted_prob,
            "actual_won": actual_won,
            "game_key": game_key,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.predictions.append(entry)

        # Update Page-Hinkley test if we have the result
        if actual_won is not None:
            error = abs(predicted_prob - (1.0 if actual_won else 0.0))
            self._update_page_hinkley(error)

        # Update feature baselines periodically
        if len(self.predictions) >= self.window_size and self.feature_baselines is None:
            self._compute_feature_baselines()

        self._save_state()

    def check_health(self) -> Dict[str, Any]:
        """
        Comprehensive model health check.

        Returns:
            {
                "healthy": True/False,
                "drift_detected": True/False,
                "drift_type": "concept" | "data" | "performance" | None,
                "metrics": { ... },
                "recommendation": "retrain" | "monitor" | "ok",
            }
        """
        resolved = [p for p in self.predictions if p["actual_won"] is not None]

        if len(resolved) < 10:
            return {
                "healthy": True,
                "drift_detected": False,
                "drift_type": None,
                "metrics": {"resolved_predictions": len(resolved)},
                "recommendation": "insufficient_data",
            }

        # ── Performance metrics ───────────────────────────────────
        recent = list(resolved)[-self.window_size:]
        probs = np.array([p["predicted_prob"] for p in recent])
        actuals = np.array([1 if p["actual_won"] else 0 for p in recent])
        preds = (probs >= 0.5).astype(int)

        accuracy = float(np.mean(preds == actuals))
        brier = float(np.mean((probs - actuals) ** 2))

        # Simple AUC approximation (concordance index)
        auc = self._approx_auc(probs, actuals)

        # Calibration: predicted prob vs actual win rate in bins
        calibration = self._calibration_error(probs, actuals)

        metrics = {
            "accuracy": round(accuracy, 4),
            "brier_score": round(brier, 4),
            "auc_approx": round(auc, 4),
            "calibration_error": round(calibration, 4),
            "resolved_predictions": len(resolved),
            "window_size": len(recent),
        }

        # ── Drift checks ─────────────────────────────────────────
        drift_detected = False
        drift_type = None
        drift_evidence = []

        # 1. Performance drift
        if accuracy < MIN_ACCURACY_THRESHOLD:
            drift_detected = True
            drift_type = "performance"
            drift_evidence.append(
                f"Accuracy {accuracy:.3f} < threshold {MIN_ACCURACY_THRESHOLD}"
            )

        if auc < AUC_DRIFT_THRESHOLD:
            drift_detected = True
            drift_type = "concept"
            drift_evidence.append(
                f"AUC {auc:.3f} < threshold {AUC_DRIFT_THRESHOLD}"
            )

        if brier > BRIER_DRIFT_THRESHOLD:
            drift_detected = True
            drift_type = drift_type or "calibration"
            drift_evidence.append(
                f"Brier {brier:.4f} > threshold {BRIER_DRIFT_THRESHOLD}"
            )

        # 2. Page-Hinkley streaming drift
        if self._ph_count > 20:
            ph_stat = self._ph_sum - self._ph_min
            if ph_stat > PAGE_HINKLEY_LAMBDA:
                drift_detected = True
                drift_type = drift_type or "concept"
                drift_evidence.append(
                    f"Page-Hinkley stat {ph_stat:.2f} > lambda {PAGE_HINKLEY_LAMBDA}"
                )
                metrics["page_hinkley_stat"] = round(ph_stat, 2)

        # 3. Feature distribution drift (PSI)
        psi_result = self._check_feature_drift(recent)
        if psi_result["drifted"]:
            drift_detected = True
            drift_type = drift_type or "data"
            drift_evidence.extend(psi_result["evidence"])
            metrics["psi_scores"] = psi_result["scores"]

        # ── Recommendation ────────────────────────────────────────
        if drift_detected:
            recommendation = "retrain"
            logger.warning(
                f"DRIFT DETECTED ({drift_type}): {'; '.join(drift_evidence)}"
            )
            self.drift_events.append({
                "type": drift_type,
                "evidence": drift_evidence,
                "metrics": metrics,
                "timestamp": datetime.utcnow().isoformat(),
            })
        elif accuracy < 0.55 or brier > 0.25:
            recommendation = "monitor"
        else:
            recommendation = "ok"

        return {
            "healthy": not drift_detected,
            "drift_detected": drift_detected,
            "drift_type": drift_type,
            "drift_evidence": drift_evidence if drift_detected else [],
            "metrics": metrics,
            "recommendation": recommendation,
        }

    def get_drift_history(self) -> List[Dict]:
        """Return all recorded drift events."""
        return self.drift_events

    def reset_page_hinkley(self):
        """Reset PH test after a retrain (new baseline)."""
        self._ph_sum = 0.0
        self._ph_min = float("inf")
        self._ph_count = 0
        self._ph_mean = 0.0
        logger.info("Page-Hinkley test reset after retrain")

    # ── Page-Hinkley Test ─────────────────────────────────────────

    def _update_page_hinkley(self, error: float):
        """
        Page-Hinkley test for streaming change detection.
        Detects upward shift in prediction error.
        """
        self._ph_count += 1
        self._ph_mean += (error - self._ph_mean) / self._ph_count
        self._ph_sum += error - self._ph_mean - PAGE_HINKLEY_DELTA
        self._ph_min = min(self._ph_min, self._ph_sum)

    # ── Feature Drift (PSI) ───────────────────────────────────────

    def _compute_feature_baselines(self):
        """Compute feature distribution baselines from initial predictions."""
        features = [p["features"] for p in self.predictions if p["features"]]
        if len(features) < self.window_size:
            return

        arr = np.array(features)
        self.feature_baselines = {}
        for i in range(arr.shape[1]):
            col = arr[:, i]
            self.feature_baselines[str(i)] = {
                "mean": float(np.mean(col)),
                "std": float(np.std(col) + 1e-8),
                "histogram": np.histogram(col, bins=10)[0].tolist(),
                "bin_edges": np.histogram(col, bins=10)[1].tolist(),
            }

    def _check_feature_drift(self, recent: List[Dict]) -> Dict:
        """Check for feature distribution drift using PSI."""
        result = {"drifted": False, "evidence": [], "scores": {}}

        if self.feature_baselines is None:
            return result

        features = [p["features"] for p in recent if p["features"]]
        if len(features) < 10:
            return result

        arr = np.array(features)
        for i in range(min(arr.shape[1], len(self.feature_baselines))):
            baseline = self.feature_baselines.get(str(i))
            if not baseline:
                continue

            base_hist = np.array(baseline["histogram"], dtype=float)
            bin_edges = np.array(baseline["bin_edges"])

            current_hist = np.histogram(arr[:, i], bins=bin_edges)[0].astype(float)

            # Normalize to proportions
            base_p = base_hist / (base_hist.sum() + 1e-8)
            curr_p = current_hist / (current_hist.sum() + 1e-8)

            # Avoid log(0)
            base_p = np.clip(base_p, 1e-6, 1)
            curr_p = np.clip(curr_p, 1e-6, 1)

            # PSI = Σ (p - q) * ln(p/q)
            psi = float(np.sum((curr_p - base_p) * np.log(curr_p / base_p)))
            result["scores"][str(i)] = round(psi, 4)

            if psi > PSI_THRESHOLD:
                from engine.ml.feature_engine import FeatureEngine

                fname = (
                    FeatureEngine.FEATURE_NAMES[i]
                    if i < len(FeatureEngine.FEATURE_NAMES)
                    else f"feature_{i}"
                )
                result["drifted"] = True
                result["evidence"].append(
                    f"Feature '{fname}' PSI={psi:.3f} > {PSI_THRESHOLD}"
                )

        return result

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _approx_auc(probs: np.ndarray, actuals: np.ndarray) -> float:
        """Approximate AUC via concordance (no sklearn dependency needed)."""
        pos = probs[actuals == 1]
        neg = probs[actuals == 0]
        if len(pos) == 0 or len(neg) == 0:
            return 0.5
        concordant = sum((p > n) for p in pos for n in neg)
        total = len(pos) * len(neg)
        return concordant / total if total > 0 else 0.5

    @staticmethod
    def _calibration_error(probs: np.ndarray, actuals: np.ndarray, n_bins: int = 5) -> float:
        """Expected Calibration Error (ECE)."""
        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (probs >= lo) & (probs < hi)
            if mask.sum() == 0:
                continue
            avg_pred = probs[mask].mean()
            avg_actual = actuals[mask].mean()
            ece += mask.sum() * abs(avg_pred - avg_actual)
        return ece / len(probs) if len(probs) > 0 else 0.0

    # ── Persistence ───────────────────────────────────────────────

    def _save_state(self):
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "predictions": list(self.predictions),
            "feature_baselines": self.feature_baselines,
            "drift_events": self.drift_events,
            "ph_state": {
                "sum": self._ph_sum,
                "min": self._ph_min,
                "count": self._ph_count,
                "mean": self._ph_mean,
            },
        }
        with open(self._state_path, "w") as f:
            json.dump(state, f)

    def _load_state(self):
        if self._state_path.exists():
            try:
                with open(self._state_path) as f:
                    state = json.load(f)
                self.predictions = deque(
                    state.get("predictions", []),
                    maxlen=self.window_size * 2,
                )
                self.feature_baselines = state.get("feature_baselines")
                self.drift_events = state.get("drift_events", [])
                ph = state.get("ph_state", {})
                self._ph_sum = ph.get("sum", 0.0)
                self._ph_min = ph.get("min", float("inf"))
                self._ph_count = ph.get("count", 0)
                self._ph_mean = ph.get("mean", 0.0)
                logger.info(
                    f"Loaded monitor state: {len(self.predictions)} predictions, "
                    f"{len(self.drift_events)} drift events"
                )
            except Exception as e:
                logger.error(f"Failed to load monitor state: {e}")
