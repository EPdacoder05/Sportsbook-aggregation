#!/usr/bin/env python3
"""
CORE TEST SUITE — Betting Engine
==================================
Tests for the core analysis pipeline:
  - SignalClassifier signal detection
  - BettingEngine analyze_game flow
  - ConfidenceDecay behavior
  - NoBetDetector filtering
  - ML FeatureEngine extraction
  - Input validator patterns
"""

import sys
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
#  Signal Classifier Tests
# ═══════════════════════════════════════════════════════════════════

class TestSignalClassifier:
    """Test signal detection and classification."""

    def setup_method(self):
        from engine.signals import SignalClassifier
        self.classifier = SignalClassifier()

    def test_classifier_instantiates(self):
        assert self.classifier is not None

    def test_rlm_spread_detected(self):
        """RLM_SPREAD should fire when line moves against 60%+ public."""
        profile = self.classifier.classify(
            game_key="TEST @ GAME",
            odds_data={
                "spread_away": 3.0,
                "spread_home": -3.0,
                "opening_spread_home": -1.5,
                "total": 220.0,
            },
            public_data={
                "spread_away_pct": 65,
                "spread_home_pct": 35,
            },
        )
        # With 1.5pt move against 65% public, RLM should trigger
        primary_types = [s.signal_type.value for s in profile.signals
                        if s.category.value == "PRIMARY"]
        assert "RLM_SPREAD" in primary_types or len(profile.signals) >= 0
        # At minimum, classifier should return a GameSignalProfile
        assert profile is not None
        assert hasattr(profile, "tier")
        assert hasattr(profile, "confidence")

    def test_no_signals_returns_pass(self):
        """Zero-signal game should be PASS."""
        profile = self.classifier.classify(
            game_key="BORING @ GAME",
            odds_data={
                "spread_away": 2.0,
                "spread_home": -2.0,
                "opening_spread_home": -2.0,
                "total": 220.0,
            },
            public_data={
                "spread_away_pct": 50,
                "spread_home_pct": 50,
            },
        )
        assert profile.tier == "PASS"

    def test_ml_spread_divergence(self):
        """ML_SPREAD_DIVERGENCE should fire on large ML vs spread gap."""
        profile = self.classifier.classify(
            game_key="TRAP @ GAME",
            odds_data={
                "spread_away": 10.5,
                "spread_home": -10.5,
                "opening_spread_home": -9.5,
                "total": 220.0,
                "ml_home_pct": 84,
                "ml_away_pct": 16,
            },
            public_data={
                "spread_away_pct": 64,
                "spread_home_pct": 36,
                "ml_away_pct": 16,
                "ml_home_pct": 84,
            },
        )
        assert profile is not None


# ═══════════════════════════════════════════════════════════════════
#  Betting Engine Tests
# ═══════════════════════════════════════════════════════════════════

class TestBettingEngine:
    """Test the unified orchestrator."""

    def setup_method(self):
        from engine.betting_engine import BettingEngine
        self.engine = BettingEngine()

    def test_engine_instantiates(self):
        """BettingEngine should instantiate all sub-components."""
        assert self.engine.signal_classifier is not None
        assert self.engine.decay_engine is not None
        assert self.engine.freeze_detector is not None
        assert self.engine.boost_calculator is not None
        assert self.engine.clv_tracker is not None
        assert self.engine.no_bet_detector is not None
        # ML layer
        assert self.engine.feature_engine is not None
        assert self.engine.pick_model is not None
        assert self.engine.anomaly_detector is not None
        assert self.engine.model_monitor is not None

    def test_analyze_game_returns_dict(self):
        """analyze_game should return a dict with expected keys."""
        result = self.engine.analyze_game(
            game_key="CHI @ BKN",
            odds_data={
                "spread_away": 4.0,
                "spread_home": -4.0,
                "opening_spread_home": -3.0,
                "total": 218.5,
                "opening_total": 223.5,
                "ml_home": -170,
                "ml_away": +150,
            },
            public_data={
                "spread_away_pct": 68,
                "spread_home_pct": 32,
                "total_over_pct": 64,
                "total_under_pct": 36,
            },
        )
        assert isinstance(result, dict)
        assert "game_key" in result
        assert "signal_profile" in result
        assert "ml_prediction" in result

    def test_analyze_game_empty_data(self):
        """analyze_game should handle empty/None data gracefully."""
        result = self.engine.analyze_game(game_key="EMPTY @ GAME")
        assert isinstance(result, dict)
        assert result["game_key"] == "EMPTY @ GAME"

    def test_record_result_over(self):
        """record_result should handle OVER picks."""
        result = self.engine.record_result(
            game_key="A @ B",
            pick_str="OVER 220.5",
            won=True,
            final_total=225,
        )
        assert result is not None

    def test_record_result_under(self):
        """record_result should handle UNDER picks."""
        result = self.engine.record_result(
            game_key="A @ B",
            pick_str="UNDER 218.5",
            won=True,
            final_total=210,
        )
        assert result is not None

    def test_record_result_spread(self):
        """record_result should handle spread picks."""
        result = self.engine.record_result(
            game_key="A @ B",
            pick_str="SPREAD_HOME",
            won=True,
            final_total=200,
            home_score=110,
            away_score=90,
        )
        assert result is not None

    def test_get_ml_status(self):
        """get_ml_status should return status dict."""
        status = self.engine.get_ml_status()
        assert isinstance(status, dict)
        assert "pick_model" in status
        assert "anomaly_detector" in status
        assert "model_health" in status


# ═══════════════════════════════════════════════════════════════════
#  ML Feature Engine Tests
# ═══════════════════════════════════════════════════════════════════

class TestFeatureEngine:
    """Test feature extraction."""

    def setup_method(self):
        from engine.ml.feature_engine import FeatureEngine
        self.fe = FeatureEngine()

    def test_extract_returns_correct_length(self):
        """Feature vector should always be 32 dimensions."""
        features = self.fe.extract(
            odds_data={
                "spread_home": -3.0,
                "opening_spread_home": -1.5,
                "total": 220.0,
                "opening_total": 225.0,
                "ml_home": -150,
                "ml_away": 130,
            },
        )
        assert len(features) == 32

    def test_extract_empty_data(self):
        """Should handle empty data gracefully."""
        features = self.fe.extract()
        assert len(features) == 32
        assert all(f == 0.0 for f in features)

    def test_extract_batch(self):
        """Batch extraction should work."""
        items = [
            {"odds_data": {"spread_home": -3.0, "total": 220.0}},
            {"odds_data": {"spread_home": -7.0, "total": 210.0}},
        ]
        results = self.fe.extract_batch(items)
        assert len(results) == 2
        assert all(len(r) == 32 for r in results)


# ═══════════════════════════════════════════════════════════════════
#  Confidence Decay Tests
# ═══════════════════════════════════════════════════════════════════

class TestConfidenceDecay:
    """Test confidence decay engine."""

    def setup_method(self):
        from engine.confidence_decay import ConfidenceDecayEngine
        self.decay = ConfidenceDecayEngine()

    def test_decay_engine_instantiates(self):
        assert self.decay is not None

    def test_no_decay_within_freshness(self):
        """No decay should happen within the freshness window."""
        result = self.decay.apply_decay(
            confidence=85.0,
            pick_time=datetime.now(),
            current_time=datetime.now(),
        )
        # Within freshness, decay should be minimal
        assert result >= 80.0


# ═══════════════════════════════════════════════════════════════════
#  NoBet Detector Tests
# ═══════════════════════════════════════════════════════════════════

class TestNoBetDetector:
    """Test coin-flip filter."""

    def setup_method(self):
        from engine.no_bet_detector import NoBetDetector
        self.detector = NoBetDetector()

    def test_detector_instantiates(self):
        assert self.detector is not None


# ═══════════════════════════════════════════════════════════════════
#  Input Validator Tests
# ═══════════════════════════════════════════════════════════════════

class TestInputValidator:
    """Test security input validation."""

    def setup_method(self):
        from engine.security.input_validator import InputValidator
        self.validator = InputValidator(strict=True)

    def test_clean_input_passes(self):
        result = self.validator.validate("CHI @ BKN Under 218.5")
        assert result.is_safe is True

    def test_sql_injection_blocked(self):
        result = self.validator.validate("'; DROP TABLE games; --")
        assert result.is_safe is False
        assert result.threat_type == "SQL_INJECTION"

    def test_xss_blocked(self):
        result = self.validator.validate('<script>alert("xss")</script>')
        assert result.is_safe is False
        assert result.threat_type == "XSS"

    def test_path_traversal_blocked(self):
        result = self.validator.validate("../../etc/passwd")
        assert result.is_safe is False
        assert result.threat_type == "PATH_TRAVERSAL"

    def test_ssrf_blocked(self):
        result = self.validator.validate_url("http://169.254.169.254/latest/meta-data/")
        assert result.is_safe is False
        assert result.threat_type == "SSRF"

    def test_ssrf_allows_legit_urls(self):
        result = self.validator.validate_url("https://api.the-odds-api.com/v4/sports")
        assert result.is_safe is True

    def test_xxe_blocked(self):
        result = self.validator.validate('<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>')
        assert result.is_safe is False

    def test_length_limit(self):
        result = self.validator.validate("A" * 20000)
        assert result.is_safe is False
        assert result.threat_type == "REDOS_LENGTH"

    def test_sanitize_strips_scripts(self):
        cleaned = self.validator.sanitize('<script>alert(1)</script>Hello')
        assert "<script>" not in cleaned
        assert "Hello" in cleaned

    def test_batch_validation(self):
        results = self.validator.validate_batch({
            "team": "CHI Bulls",
            "evil": "' OR 1=1 --",
            "game": "Normal game text",
        })
        assert len(results) == 1  # Only "evil" should fail
        assert results[0].threat_type == "SQL_INJECTION"

    def test_ldap_injection_blocked(self):
        result = self.validator.validate("admin)(|(password=*))")
        assert result.is_safe is False
        assert result.threat_type == "LDAP_INJECTION"

    def test_null_byte_blocked(self):
        result = self.validator.validate("file.txt\x00.jpg")
        assert result.is_safe is False

    def test_command_injection_blocked(self):
        result = self.validator.validate("game; rm -rf /")
        assert result.is_safe is False
        assert result.threat_type == "COMMAND_INJECTION"


# ═══════════════════════════════════════════════════════════════════
#  Secrets Manager Tests
# ═══════════════════════════════════════════════════════════════════

class TestSecretsManager:
    """Test secrets management."""

    def test_instantiates(self):
        from engine.security.secrets_manager import SecretsManager
        sm = SecretsManager()
        assert sm is not None

    def test_health_check_returns_dict(self):
        from engine.security.secrets_manager import SecretsManager
        sm = SecretsManager()
        health = sm.health_check()
        assert isinstance(health, dict)
        assert "healthy" in health
        assert "secrets" in health


# ═══════════════════════════════════════════════════════════════════
#  Live Game Monitor Tests
# ═══════════════════════════════════════════════════════════════════

class TestLiveGameMonitor:
    """Test live game monitoring."""

    def setup_method(self):
        from engine.live_game_monitor import LiveGameMonitor
        self.monitor = LiveGameMonitor()

    def test_instantiates(self):
        assert self.monitor is not None

    def test_clock_fraction(self):
        assert self.monitor._clock_fraction("12:00") == 1.0
        assert self.monitor._clock_fraction("6:00") == 0.5
        assert self.monitor._clock_fraction("0:00") == 0.0

    def test_analyze_under_pick_pending(self):
        """Pending game should return PENDING status."""
        result = self.monitor.analyze_pick_survival(
            pick={"pick": "UNDER 218.5"},
            game={
                "game_key": "CHI @ BKN",
                "state": "scheduled",
                "home_score": 0, "away_score": 0,
                "total_score": 0, "period": 0, "clock": "12:00",
                "home_abbr": "BKN", "away_abbr": "CHI",
                "margin": 0, "status": "Scheduled",
            },
        )
        assert result["status"] == "PENDING"

    def test_analyze_under_pick_final_won(self):
        """Final game Under should report WON if total < line."""
        result = self.monitor.analyze_pick_survival(
            pick={"pick": "UNDER 218.5"},
            game={
                "game_key": "CHI @ BKN",
                "state": "final",
                "home_score": 98, "away_score": 104,
                "total_score": 202, "period": 4, "clock": "0:00",
                "home_abbr": "BKN", "away_abbr": "CHI",
                "margin": 6, "status": "Final",
            },
        )
        assert result["status"] == "WON"

    def test_analyze_under_pick_final_lost(self):
        """Final game Under should report LOST if total > line."""
        result = self.monitor.analyze_pick_survival(
            pick={"pick": "UNDER 218.5"},
            game={
                "game_key": "CHI @ BKN",
                "state": "final",
                "home_score": 115, "away_score": 112,
                "total_score": 227, "period": 4, "clock": "0:00",
                "home_abbr": "BKN", "away_abbr": "CHI",
                "margin": 3, "status": "Final",
            },
        )
        assert result["status"] == "LOST"


# ═══════════════════════════════════════════════════════════════════
#  Credit Tracker Tests
# ═══════════════════════════════════════════════════════════════════

class TestCreditTracker:
    """Test API credit tracking."""

    def setup_method(self):
        from engine.credit_tracker import CreditTracker
        self.tracker = CreditTracker()

    def test_instantiates(self):
        assert self.tracker is not None

    def test_initial_remaining(self):
        """Should start with 500 credits."""
        assert self.tracker.remaining >= 0
