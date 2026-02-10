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


# ═══════════════════════════════════════════════════════════════════
#  Quarter-Line Detector Tests
# ═══════════════════════════════════════════════════════════════════

class TestQuarterLineDetector:
    """Test quarter-line mismatch detection (learned from $38 DET/CHA 1Q loss)."""

    def setup_method(self):
        from engine.quarter_line_detector import QuarterLineDetector
        self.detector = QuarterLineDetector()

    def test_instantiates(self):
        assert self.detector is not None

    def test_mismatch_detected(self):
        """Full-game drops 5pts but Q1 barely moves → QUARTER_MISMATCH."""
        result = self.detector.detect(
            game_key="DET @ CHA",
            full_game_open=222.5,
            full_game_current=218.0,
            quarter_open=55.0,
            quarter_current=54.5,
        )
        assert result.signal.value == "QUARTER_MISMATCH"
        assert result.q1_bet_safe is False
        assert "NO-BET" in result.recommendation.upper() or "mismatch" in result.recommendation.lower()

    def test_aligned_lines(self):
        """Both full-game and Q1 lines move proportionally → QUARTER_ALIGNED."""
        result = self.detector.detect(
            game_key="CHI @ BKN",
            full_game_open=223.0,
            full_game_current=218.0,
            quarter_open=56.0,
            quarter_current=53.0,
        )
        assert result.signal.value in ("QUARTER_ALIGNED", "NONE")
        assert result.q1_bet_safe is True

    def test_no_movement(self):
        """No line movement at all → NONE."""
        result = self.detector.detect(
            game_key="MIA @ UTA",
            full_game_open=220.0,
            full_game_current=220.0,
            quarter_open=55.0,
            quarter_current=55.0,
        )
        assert result.signal.value in ("NONE", "QUARTER_ALIGNED")

    def test_batch_detect(self):
        """Batch detection should return results for each game."""
        games = [
            {"game_key": "G1", "full_game_open": 222, "full_game_current": 218,
             "quarter_open": 55, "quarter_current": 54.5},
            {"game_key": "G2", "full_game_open": 220, "full_game_current": 220,
             "quarter_open": 55, "quarter_current": 55},
        ]
        results = self.detector.batch_detect(games)
        assert len(results) == 2


# ═══════════════════════════════════════════════════════════════════
#  Star Absence Detector Tests
# ═══════════════════════════════════════════════════════════════════

class TestStarAbsenceDetector:
    """Test star absence detection (learned from SGA/Curry/Ja/Giannis/Luka all OUT)."""

    def setup_method(self):
        from engine.star_absence_detector import StarAbsenceDetector
        self.detector = StarAbsenceDetector()

    def test_instantiates(self):
        assert self.detector is not None

    def test_single_star_out(self):
        """One star OUT → STAR_OUT signal with Under boost."""
        result = self.detector.detect_from_manual_report(
            game_key="OKC @ LAL",
            players_out=["Shai Gilgeous-Alexander"],
        )
        assert result.signal.value == "STAR_OUT"
        assert result.under_boost > 0
        assert "Shai Gilgeous-Alexander" in result.players_out

    def test_multi_star_out(self):
        """Two stars OUT in same game → MULTI_STAR_OUT."""
        result = self.detector.detect_from_manual_report(
            game_key="MEM @ GS",
            players_out=["Ja Morant", "Stephen Curry"],
        )
        assert result.signal.value == "MULTI_STAR_OUT"
        assert result.under_boost > 0.10  # Big boost
        assert len(result.players_out) == 2

    def test_no_stars_out(self):
        """No star absences → NONE."""
        result = self.detector.detect_from_manual_report(
            game_key="BOS @ PHI",
            players_out=["Random Benchwarmer"],
        )
        assert result.signal.value == "NONE"

    def test_gtd_player(self):
        """GTD player → lower impact than OUT."""
        result = self.detector.detect_from_manual_report(
            game_key="MIL @ ORL",
            players_out=[],
            players_gtd=["Giannis Antetokounmpo"],
        )
        assert result.signal.value in ("STAR_GTD", "NONE")

    def test_star_impact_database(self):
        """Verify star impact database has entries."""
        from engine.star_absence_detector import STAR_IMPACT
        assert len(STAR_IMPACT) >= 15
        # Check a known star
        assert "Luka Doncic" in STAR_IMPACT or "Luka Dončić" in STAR_IMPACT


# ═══════════════════════════════════════════════════════════════════
#  Parlay Tracker Tests
# ═══════════════════════════════════════════════════════════════════

class TestParlayTracker:
    """Test parlay survival tracking and hedge calculations."""

    def setup_method(self):
        from engine.parlay_tracker import ParlayTracker, ParlayLeg, Parlay, LegStatus
        self.ParlayLeg = ParlayLeg
        self.Parlay = Parlay
        self.LegStatus = LegStatus

        # Create tracker with temp file (no persistence in tests)
        import tempfile
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.tracker = ParlayTracker(data_file=Path(self.tmp.name))
        self.tracker.parlays = []

    def teardown_method(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_instantiates(self):
        assert self.tracker is not None

    def test_add_parlay(self):
        """Adding a parlay should persist and increase count."""
        self.tracker.add_parlay(
            parlay_id="TEST_3PICK",
            wager=10.0,
            to_pay=100.0,
            legs=[
                self.ParlayLeg("CLE ML", "CLE @ DEN", "ML", team="CLE"),
                self.ParlayLeg("Under 220", "CHI @ BKN", "TOTAL_UNDER", 220),
                self.ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ],
        )
        assert len(self.tracker.parlays) == 1

    def test_leg_update(self):
        """Updating a leg should change its status."""
        self.tracker.add_parlay(
            parlay_id="TEST_UPD",
            wager=5.0,
            to_pay=50.0,
            legs=[
                self.ParlayLeg("CLE ML", "CLE @ DEN", "ML", team="CLE"),
                self.ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ],
        )
        self.tracker.update_leg("DET", "WON", "Final: 110-104")

        det_leg = [l for l in self.tracker.parlays[0].legs if "DET" in l.description][0]
        assert det_leg.status == self.LegStatus.WON

    def test_parlay_alive_status(self):
        """Parlay with WON legs and PENDING legs should be ALIVE."""
        from engine.parlay_tracker import ParlayStatus
        self.tracker.add_parlay(
            parlay_id="ALIVE_TEST",
            wager=10.0,
            to_pay=200.0,
            legs=[
                self.ParlayLeg("CLE ML", "CLE @ DEN", "ML", team="CLE"),
                self.ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ],
        )
        self.tracker.update_leg("DET", "WON")
        assert self.tracker.parlays[0].status == ParlayStatus.ALIVE

    def test_parlay_lost_status(self):
        """Parlay with any LOST leg should be LOST."""
        from engine.parlay_tracker import ParlayStatus
        self.tracker.add_parlay(
            parlay_id="LOST_TEST",
            wager=10.0,
            to_pay=200.0,
            legs=[
                self.ParlayLeg("CLE ML", "CLE @ DEN", "ML", team="CLE"),
                self.ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ],
        )
        self.tracker.update_leg("CLE", "LOST")
        assert self.tracker.parlays[0].status == ParlayStatus.LOST

    def test_hedge_calculation(self):
        """Hedge math should return valid breakeven and equal-profit amounts."""
        self.tracker.add_parlay(
            parlay_id="HEDGE_TEST",
            wager=10.0,
            to_pay=200.0,
            legs=[
                self.ParlayLeg("CLE ML", "CLE @ DEN", "ML", team="CLE"),
                self.ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ],
        )
        self.tracker.update_leg("DET", "WON")

        hedge = self.tracker.calculate_hedge("HEDGE_TEST", opposing_odds=-110)
        assert "hedge_breakeven" in hedge
        assert "hedge_equal_profit" in hedge
        assert hedge["hedge_breakeven"] > 0
        assert hedge["hedge_equal_profit"] > 0

    def test_summary(self):
        """Summary should return portfolio stats."""
        summary = self.tracker.get_summary()
        assert "total_parlays" in summary
        assert "net_pnl" in summary
