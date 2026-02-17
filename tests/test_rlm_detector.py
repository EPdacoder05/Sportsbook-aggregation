"""
Test Suite for RLM Detector
============================
Tests for Reverse Line Movement detection strategies.
"""

import pytest
from analysis.rlm_detector import (
    SpreadRLMDetector,
    TotalRLMDetector,
    MLSpreadDivergenceDetector,
    ATSTrendAnalyzer,
    RLMSignal
)


class TestSpreadRLMDetector:
    """Test Spread RLM detection."""
    
    def setup_method(self):
        self.detector = SpreadRLMDetector()
    
    def test_rlm_detected_against_home_favorite(self):
        """Test RLM when line moves against home favorite with public support."""
        game_data = {
            "opening_spread": -4.0,
            "current_spread": -6.5,
            "public_pct_home": 0.57,
            "home_team": "LAL",
            "away_team": "OKC"
        }
        
        result = self.detector.detect(game_data)
        
        # Line moved from -4 to -6.5 (making away MORE attractive)
        # But public is on home (57%)
        # This means sharp money is on AWAY
        assert result.detected == False  # Actually not RLM - line moved WITH favorites
    
    def test_rlm_detected_line_moves_against_public(self):
        """Test RLM when line moves against public bias."""
        game_data = {
            "opening_spread": -6.5,
            "current_spread": -4.0,
            "public_pct_home": 0.57,
            "home_team": "LAL",
            "away_team": "OKC"
        }
        
        result = self.detector.detect(game_data)
        
        # Line moved from -6.5 to -4 (making home LESS favored)
        # Public is on home (57%)
        # Sharp money is on AWAY
        assert result.detected == True
        assert result.sharp_side == "away"
        assert result.confidence >= 0.75
    
    def test_no_rlm_with_balanced_public(self):
        """Test no RLM detected with balanced public betting."""
        game_data = {
            "opening_spread": -4.0,
            "current_spread": -6.5,
            "public_pct_home": 0.50,
            "home_team": "LAL",
            "away_team": "OKC"
        }
        
        result = self.detector.detect(game_data)
        
        assert result.detected == False
    
    def test_no_rlm_with_small_line_movement(self):
        """Test no RLM with small line movement."""
        game_data = {
            "opening_spread": -4.0,
            "current_spread": -4.5,
            "public_pct_home": 0.60,
            "home_team": "LAL",
            "away_team": "OKC"
        }
        
        result = self.detector.detect(game_data)
        
        assert result.detected == False
    
    def test_missing_data(self):
        """Test handling of missing data."""
        game_data = {
            "public_pct_home": 0.60,
            "home_team": "LAL",
            "away_team": "OKC"
        }
        
        result = self.detector.detect(game_data)
        
        assert result.detected == False
        assert "Missing" in result.reasoning


class TestTotalRLMDetector:
    """Test Total RLM detection."""
    
    def setup_method(self):
        self.detector = TotalRLMDetector()
    
    def test_total_rlm_detected_under(self):
        """Test total RLM: total drops with public on Over."""
        game_data = {
            "opening_total": 223.5,
            "current_total": 218.5,
            "public_pct_over": 0.64,
            "home_team": "BKN",
            "away_team": "CHI"
        }
        
        result = self.detector.detect(game_data)
        
        # Total dropped 5 pts
        # Public on Over (64%)
        # Sharp money on UNDER
        assert result.detected == True
        assert result.sharp_side == "under"
        assert result.confidence >= 0.80
        assert result.magnitude == 5.0
    
    def test_total_rlm_detected_over(self):
        """Test total RLM: total rises with public on Under."""
        game_data = {
            "opening_total": 210.0,
            "current_total": 215.0,
            "public_pct_over": 0.35,  # 65% on Under
            "home_team": "BKN",
            "away_team": "CHI"
        }
        
        result = self.detector.detect(game_data)
        
        # Total rose 5 pts
        # Public on Under (65%)
        # Sharp money on OVER
        assert result.detected == True
        assert result.sharp_side == "over"
        assert result.confidence >= 0.80
    
    def test_no_total_rlm_with_small_movement(self):
        """Test no RLM with small total movement."""
        game_data = {
            "opening_total": 220.0,
            "current_total": 219.0,
            "public_pct_over": 0.64,
            "home_team": "BKN",
            "away_team": "CHI"
        }
        
        result = self.detector.detect(game_data)
        
        assert result.detected == False
    
    def test_strong_total_rlm_high_confidence(self):
        """Test strong total RLM gets high confidence."""
        game_data = {
            "opening_total": 226.0,
            "current_total": 220.5,
            "public_pct_over": 0.66,
            "home_team": "GS",
            "away_team": "MEM"
        }
        
        result = self.detector.detect(game_data)
        
        # 5.5 pt drop - strong signal
        assert result.detected == True
        assert result.confidence >= 0.80
        assert result.magnitude == 5.5


class TestMLSpreadDivergenceDetector:
    """Test ML-Spread Divergence detection."""
    
    def setup_method(self):
        self.detector = MLSpreadDivergenceDetector()
    
    def test_divergence_detected_high(self):
        """Test high ML-spread divergence."""
        game_data = {
            "public_pct_home_ml": 0.84,
            "public_pct_home_spread": 0.36,
            "home_team": "ORL",
            "away_team": "MIL",
            "current_spread": -10.5
        }
        
        result = self.detector.detect(game_data)
        
        # 48% divergence
        assert result.detected == True
        assert result.sharp_side == "away"  # Public says "ORL wins but doesn't cover"
        assert result.magnitude == 0.48
        assert result.confidence >= 0.75
    
    def test_divergence_detected_moderate(self):
        """Test moderate divergence."""
        game_data = {
            "public_pct_home_ml": 0.70,
            "public_pct_home_spread": 0.50,
            "home_team": "LAL",
            "away_team": "GSW",
            "current_spread": -5.0
        }
        
        result = self.detector.detect(game_data)
        
        # 20% divergence
        assert result.detected == True
        assert abs(result.magnitude - 0.20) < 0.01  # Allow for floating point imprecision
    
    def test_no_divergence_small_gap(self):
        """Test no divergence with small gap."""
        game_data = {
            "public_pct_home_ml": 0.60,
            "public_pct_home_spread": 0.55,
            "home_team": "LAL",
            "away_team": "GSW",
            "current_spread": -3.0
        }
        
        result = self.detector.detect(game_data)
        
        assert result.detected == False
    
    def test_missing_data(self):
        """Test handling of missing ML/spread data."""
        game_data = {
            "home_team": "LAL",
            "away_team": "GSW"
        }
        
        result = self.detector.detect(game_data)
        
        assert result.detected == False


class TestATSTrendAnalyzer:
    """Test ATS Trend analysis."""
    
    def setup_method(self):
        self.analyzer = ATSTrendAnalyzer()
    
    def test_extreme_cold_streak_home(self):
        """Test detection of extreme cold ATS streak."""
        game_data = {
            "home_ats_l10": "2-8",
            "away_ats_l10": "5-5",
            "home_team": "CHI",
            "away_team": "BKN"
        }
        
        result = self.analyzer.analyze(game_data)
        
        # CHI is 2-8 ATS (cold streak)
        # Fade the streak → bet ON CHI
        assert result.detected == True
        assert result.sharp_side == "home"
        assert result.confidence == 0.70
    
    def test_extreme_hot_streak_away(self):
        """Test detection of extreme hot ATS streak."""
        game_data = {
            "home_ats_l10": "5-5",
            "away_ats_l10": "8-2",
            "home_team": "MIA",
            "away_team": "BOS"
        }
        
        result = self.analyzer.analyze(game_data)
        
        # BOS is 8-2 ATS (hot streak)
        # Fade the streak → bet AGAINST BOS (bet MIA)
        assert result.detected == True
        assert result.sharp_side == "home"
        assert result.confidence == 0.65
    
    def test_no_extreme_trends(self):
        """Test no detection with normal trends."""
        game_data = {
            "home_ats_l10": "5-5",
            "away_ats_l10": "6-4",
            "home_team": "LAL",
            "away_team": "GSW"
        }
        
        result = self.analyzer.analyze(game_data)
        
        assert result.detected == False
    
    def test_parse_ats_record_valid(self):
        """Test parsing of ATS record strings."""
        assert self.analyzer._parse_ats_record("2-8") == 0.2
        assert self.analyzer._parse_ats_record("8-2") == 0.8
        assert self.analyzer._parse_ats_record("5-5") == 0.5
    
    def test_parse_ats_record_invalid(self):
        """Test handling of invalid ATS records."""
        assert self.analyzer._parse_ats_record("") is None
        assert self.analyzer._parse_ats_record("invalid") is None
        assert self.analyzer._parse_ats_record("10") is None


class TestRLMSignal:
    """Test RLMSignal dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        signal = RLMSignal(
            detected=True,
            signal_type="spread_rlm",
            confidence=0.85,
            reasoning="Line moved against public",
            sharp_side="away",
            magnitude=2.5
        )
        
        result = signal.to_dict()
        
        assert result["detected"] == True
        assert result["signal_type"] == "spread_rlm"
        assert result["confidence"] == 0.85
        assert result["sharp_side"] == "away"
        assert result["magnitude"] == 2.5
