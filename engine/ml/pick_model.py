"""
Supervised Learning Pick Model.

Gradient-Boosted classifier that learns from historical pick outcomes
to predict WIN/LOSS probability. Uses the 32-feature vectors from
FeatureEngine and trains incrementally as results accumulate.

Anti-overfitting measures:
  - Early stopping on validation loss
  - 5-fold cross-validation for hyperparameter tuning
  - Minimum 50-game sample before making predictions
  - Calibrated probabilities via Platt scaling
  - Train/val/holdout split enforcement
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Minimum games needed before the model starts making predictions
MIN_TRAINING_SAMPLES = 50
# Retrain trigger: every N new results
RETRAIN_INTERVAL = 25
# Maximum depth to prevent overfitting
MAX_DEPTH = 4
# Learning rate — low for generalization
LEARNING_RATE = 0.05
# Number of estimators
N_ESTIMATORS = 200
# Validation split
VAL_SPLIT = 0.2
# Holdout split (never trained on — only for drift detection)
HOLDOUT_SPLIT = 0.1

DATA_DIR = Path("data/ml")


class PickModel:
    """
    Supervised learning model for pick win probability.

    Lifecycle:
        1. FeatureEngine.extract() → 32-dim vector
        2. PickModel.predict(vector) → win probability + confidence
        3. After game: PickModel.record(vector, won=True/False)
        4. Auto-retrains every RETRAIN_INTERVAL results if enough data
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.calibrator = None
        self.is_trained = False
        self.training_data: List[Dict] = []
        self.model_version = 0
        self.last_trained_at: Optional[str] = None
        self.results_since_train = 0

        self._model_path = Path(model_path) if model_path else DATA_DIR / "pick_model.json"
        self._model_pkl = self._model_path.with_suffix(".pkl")

        # Load existing training data + model if available
        self._load_state()

    # ── Public API ────────────────────────────────────────────────

    def predict(self, features: np.ndarray) -> Dict[str, Any]:
        """
        Predict win probability for a single feature vector.

        Returns:
            {
                "win_probability": 0.65,
                "confidence": "HIGH" | "MEDIUM" | "LOW",
                "model_version": 3,
                "sample_size": 150,
                "is_trained": True,
            }
        """
        sample_size = len(self.training_data)

        if not self.is_trained or sample_size < MIN_TRAINING_SAMPLES:
            return {
                "win_probability": 0.5,  # No edge without training
                "confidence": "UNTRAINED",
                "model_version": self.model_version,
                "sample_size": sample_size,
                "is_trained": False,
                "reason": f"Need {MIN_TRAINING_SAMPLES} samples, have {sample_size}",
            }

        try:
            X = features.reshape(1, -1)

            # Get calibrated probability
            if self.calibrator:
                prob = self.calibrator.predict_proba(X)[0][1]
            else:
                prob = self.model.predict_proba(X)[0][1]

            # Confidence based on distance from 0.5
            edge = abs(prob - 0.5)
            if edge >= 0.15:
                confidence = "HIGH"
            elif edge >= 0.08:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            return {
                "win_probability": round(float(prob), 4),
                "confidence": confidence,
                "model_version": self.model_version,
                "sample_size": sample_size,
                "is_trained": True,
            }

        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return {
                "win_probability": 0.5,
                "confidence": "ERROR",
                "model_version": self.model_version,
                "sample_size": sample_size,
                "is_trained": self.is_trained,
                "error": str(e),
            }

    def record(
        self,
        features: np.ndarray,
        won: bool,
        game_key: str = "",
        pick_type: str = "",
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Record a result for future training.
        Auto-retrains if enough new results have accumulated.

        Returns status dict with retrain info if applicable.
        """
        record = {
            "features": features.tolist(),
            "won": won,
            "game_key": game_key,
            "pick_type": pick_type,
            "recorded_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self.training_data.append(record)
        self.results_since_train += 1
        self._save_state()

        result = {
            "recorded": True,
            "total_samples": len(self.training_data),
            "results_since_train": self.results_since_train,
        }

        # Auto-retrain check
        total = len(self.training_data)
        if total >= MIN_TRAINING_SAMPLES and self.results_since_train >= RETRAIN_INTERVAL:
            logger.info(
                f"Auto-retrain triggered: {total} samples, "
                f"{self.results_since_train} new since last train"
            )
            train_result = self.train()
            result["retrained"] = True
            result["train_result"] = train_result
        else:
            needed = max(0, MIN_TRAINING_SAMPLES - total)
            result["retrained"] = False
            if needed > 0:
                result["samples_needed"] = needed
            else:
                result["next_retrain_in"] = RETRAIN_INTERVAL - self.results_since_train

        return result

    def train(self) -> Dict[str, Any]:
        """
        Train the model on accumulated data with anti-overfitting guards.

        Pipeline:
            1. Split: train / val / holdout
            2. Train GradientBoosting with early stopping on val
            3. Calibrate probabilities (Platt scaling)
            4. Evaluate on holdout (never-seen data)
            5. Persist model + metadata
        """
        total = len(self.training_data)
        if total < MIN_TRAINING_SAMPLES:
            return {
                "status": "insufficient_data",
                "total": total,
                "needed": MIN_TRAINING_SAMPLES,
            }

        try:
            from sklearn.calibration import CalibratedClassifierCV
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.metrics import (
                accuracy_score,
                brier_score_loss,
                log_loss,
                roc_auc_score,
            )
            from sklearn.model_selection import cross_val_score
        except ImportError:
            return {
                "status": "error",
                "error": "scikit-learn not installed. Run: pip install scikit-learn",
            }

        # ── Prepare data ──────────────────────────────────────────
        X = np.array([r["features"] for r in self.training_data])
        y = np.array([1 if r["won"] else 0 for r in self.training_data])

        # Check class balance
        win_rate = y.mean()
        if win_rate < 0.1 or win_rate > 0.9:
            logger.warning(
                f"Extreme class imbalance: {win_rate:.1%} win rate. "
                "Model may not generalize well."
            )

        # ── Split: train / val / holdout ──────────────────────────
        np.random.seed(42)
        indices = np.random.permutation(total)

        holdout_n = max(5, int(total * HOLDOUT_SPLIT))
        val_n = max(5, int(total * VAL_SPLIT))
        train_n = total - holdout_n - val_n

        train_idx = indices[:train_n]
        val_idx = indices[train_n : train_n + val_n]
        holdout_idx = indices[train_n + val_n :]

        X_train, y_train = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]
        X_holdout, y_holdout = X[holdout_idx], y[holdout_idx]

        logger.info(
            f"Training split: train={len(X_train)}, val={len(X_val)}, "
            f"holdout={len(X_holdout)}"
        )

        # ── Train with early stopping ─────────────────────────────
        base_model = GradientBoostingClassifier(
            n_estimators=N_ESTIMATORS,
            max_depth=MAX_DEPTH,
            learning_rate=LEARNING_RATE,
            subsample=0.8,          # Stochastic gradient boosting
            min_samples_leaf=5,     # Prevent leaf overfitting
            min_samples_split=10,   # Prevent split overfitting
            max_features="sqrt",    # Feature bagging
            validation_fraction=0.15,
            n_iter_no_change=20,    # Early stopping patience
            tol=1e-4,
            random_state=42,
        )
        base_model.fit(X_train, y_train)

        actual_estimators = base_model.n_estimators_
        logger.info(
            f"Early stopping: used {actual_estimators}/{N_ESTIMATORS} estimators"
        )

        # ── 5-fold cross-validation on train set ──────────────────
        cv_scores = cross_val_score(
            base_model, X_train, y_train, cv=5, scoring="accuracy"
        )
        cv_mean = cv_scores.mean()
        cv_std = cv_scores.std()
        logger.info(f"5-fold CV accuracy: {cv_mean:.3f} +/- {cv_std:.3f}")

        # ── Overfitting check ─────────────────────────────────────
        train_acc = accuracy_score(y_train, base_model.predict(X_train))
        val_acc = accuracy_score(y_val, base_model.predict(X_val))
        overfit_gap = train_acc - val_acc

        if overfit_gap > 0.15:
            logger.warning(
                f"OVERFITTING DETECTED: train_acc={train_acc:.3f}, "
                f"val_acc={val_acc:.3f}, gap={overfit_gap:.3f}"
            )

        # ── Calibration (Platt scaling) ───────────────────────────
        calibrator = CalibratedClassifierCV(
            base_model, method="sigmoid", cv="prefit"
        )
        calibrator.fit(X_val, y_val)

        # ── Holdout evaluation ────────────────────────────────────
        holdout_probs = calibrator.predict_proba(X_holdout)[:, 1]
        holdout_preds = (holdout_probs >= 0.5).astype(int)
        holdout_acc = accuracy_score(y_holdout, holdout_preds)
        holdout_brier = brier_score_loss(y_holdout, holdout_probs)

        try:
            holdout_auc = roc_auc_score(y_holdout, holdout_probs)
        except ValueError:
            holdout_auc = 0.5  # Only one class present

        try:
            holdout_logloss = log_loss(y_holdout, holdout_probs)
        except ValueError:
            holdout_logloss = 999.0

        logger.info(
            f"Holdout: acc={holdout_acc:.3f}, AUC={holdout_auc:.3f}, "
            f"Brier={holdout_brier:.4f}, LogLoss={holdout_logloss:.4f}"
        )

        # ── Feature importance ────────────────────────────────────
        from engine.ml.feature_engine import FeatureEngine

        importances = base_model.feature_importances_
        feature_importance = {
            name: round(float(imp), 4)
            for name, imp in sorted(
                zip(FeatureEngine.FEATURE_NAMES, importances),
                key=lambda x: -x[1],
            )
        }

        # ── Persist ───────────────────────────────────────────────
        self.model = base_model
        self.calibrator = calibrator
        self.is_trained = True
        self.model_version += 1
        self.results_since_train = 0
        self.last_trained_at = datetime.utcnow().isoformat()

        self._save_model()
        self._save_state()

        metrics = {
            "status": "trained",
            "model_version": self.model_version,
            "total_samples": total,
            "train_size": len(X_train),
            "val_size": len(X_val),
            "holdout_size": len(X_holdout),
            "estimators_used": int(actual_estimators),
            "cv_accuracy": round(cv_mean, 4),
            "cv_std": round(cv_std, 4),
            "train_accuracy": round(train_acc, 4),
            "val_accuracy": round(val_acc, 4),
            "overfit_gap": round(overfit_gap, 4),
            "holdout_accuracy": round(holdout_acc, 4),
            "holdout_auc": round(holdout_auc, 4),
            "holdout_brier": round(holdout_brier, 4),
            "holdout_logloss": round(holdout_logloss, 4),
            "win_rate": round(float(win_rate), 4),
            "feature_importance_top5": dict(list(feature_importance.items())[:5]),
            "trained_at": self.last_trained_at,
        }

        logger.info(f"Model v{self.model_version} trained successfully")
        return metrics

    def get_status(self) -> Dict[str, Any]:
        """Return model status for dashboard/monitoring."""
        return {
            "is_trained": self.is_trained,
            "model_version": self.model_version,
            "total_samples": len(self.training_data),
            "results_since_train": self.results_since_train,
            "last_trained_at": self.last_trained_at,
            "min_samples_required": MIN_TRAINING_SAMPLES,
            "retrain_interval": RETRAIN_INTERVAL,
        }

    # ── Persistence ───────────────────────────────────────────────

    def _save_state(self):
        """Persist training data and metadata (not the model weights)."""
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "model_version": self.model_version,
            "is_trained": self.is_trained,
            "last_trained_at": self.last_trained_at,
            "results_since_train": self.results_since_train,
            "training_data": self.training_data,
        }
        with open(self._model_path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        """Load training data and metadata from disk."""
        if self._model_path.exists():
            try:
                with open(self._model_path) as f:
                    state = json.load(f)
                self.model_version = state.get("model_version", 0)
                self.is_trained = state.get("is_trained", False)
                self.last_trained_at = state.get("last_trained_at")
                self.results_since_train = state.get("results_since_train", 0)
                self.training_data = state.get("training_data", [])
                logger.info(
                    f"Loaded {len(self.training_data)} training records "
                    f"(model v{self.model_version})"
                )
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

        if self._model_pkl.exists() and self.is_trained:
            self._load_model()

    def _save_model(self):
        """Persist sklearn model to pickle."""
        try:
            import joblib

            self._model_pkl.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(
                {"model": self.model, "calibrator": self.calibrator},
                self._model_pkl,
            )
            logger.info(f"Model saved to {self._model_pkl}")
        except ImportError:
            logger.warning("joblib not installed — model not persisted to disk")

    def _load_model(self):
        """Load sklearn model from pickle."""
        try:
            import joblib

            data = joblib.load(self._model_pkl)
            self.model = data["model"]
            self.calibrator = data["calibrator"]
            logger.info(f"Model loaded from {self._model_pkl}")
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
            self.is_trained = False
