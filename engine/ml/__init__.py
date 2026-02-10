"""
ML/AI layer for the Sportsbook Aggregation Engine.

Provides supervised learning, unsupervised anomaly detection,
feature engineering, and model drift monitoring for autonomous
pick generation.
"""

from engine.ml.feature_engine import FeatureEngine
from engine.ml.pick_model import PickModel
from engine.ml.anomaly_detector import AnomalyDetector
from engine.ml.model_monitor import ModelMonitor

__all__ = [
    "FeatureEngine",
    "PickModel",
    "AnomalyDetector",
    "ModelMonitor",
]
