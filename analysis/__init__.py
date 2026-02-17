"""
Analysis Package
================
Core intelligence layer for sports betting analysis.

Modules:
    - rlm_detector: Reverse Line Movement detection
    - data_loader: Load and merge odds/public data
    - confidence: Multi-signal confidence scoring
    - pick_generator: Generate final pick recommendations
"""

from analysis.rlm_detector import (
    SpreadRLMDetector,
    TotalRLMDetector,
    MLSpreadDivergenceDetector,
    ATSTrendAnalyzer,
    RLMSignal
)
from analysis.confidence import ConfidenceScorer, ConfidenceScore
from analysis.data_loader import DataLoader
from analysis.pick_generator import PickGenerator, Pick

__all__ = [
    "SpreadRLMDetector",
    "TotalRLMDetector",
    "MLSpreadDivergenceDetector",
    "ATSTrendAnalyzer",
    "RLMSignal",
    "ConfidenceScorer",
    "ConfidenceScore",
    "DataLoader",
    "PickGenerator",
    "Pick",
]
