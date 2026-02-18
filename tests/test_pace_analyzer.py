"""
Tests for Pace Analyzer
========================
Tests for 2H pace isolation and projection calculations.
"""

import pytest
from engine.pace_analyzer import PaceAnalyzer


def test_pace_analyzer_initialization():
    """Test pace analyzer initializes correctly."""
    analyzer = PaceAnalyzer()
    assert analyzer is not None
    assert len(analyzer.CONFERENCE_2H_INFLATION) > 0


def test_calculate_pace():
    """Test pace calculation (points per minute)."""
    analyzer = PaceAnalyzer()

    # 100 points in 20 minutes = 5.0 pts/min
    pace = analyzer.calculate_pace(score=100, elapsed_minutes=20.0)
    assert pace == 5.0

    # 80 points in 40 minutes = 2.0 pts/min
    pace = analyzer.calculate_pace(score=80, elapsed_minutes=40.0)
    assert pace == 2.0


def test_calculate_pace_zero_time():
    """Test pace calculation with zero elapsed time."""
    analyzer = PaceAnalyzer()

    pace = analyzer.calculate_pace(score=50, elapsed_minutes=0.0)
    assert pace == 0.0


def test_get_2h_pace():
    """Test 2H pace isolation."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 75,
        "away_score": 70,
        "halftime_total": 70,  # 70 at half
        "period": 2,
        "clock_minutes": 10.0  # 10 min left in 2H
    }

    second_half_pace = analyzer.get_2h_pace(game_state)

    # 2H points: 145 - 70 = 75
    # 2H elapsed: 20 - 10 = 10 minutes
    # Pace: 75 / 10 = 7.5 pts/min
    assert second_half_pace == pytest.approx(7.5, rel=0.01)


def test_get_2h_pace_first_half():
    """Test 2H pace returns 0 if still in first half."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 40,
        "away_score": 35,
        "halftime_total": 0,
        "period": 1,
        "clock_minutes": 5.0
    }

    second_half_pace = analyzer.get_2h_pace(game_state)
    assert second_half_pace == 0.0


def test_project_final_score_rule3():
    """Test projection uses MAX(full_game_pace, 2H_pace) per RULE_3."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 70,
        "away_score": 65,
        "time_left_minutes": 10.0,
        "full_game_pace": 2.0,
        "second_half_pace": 3.0,  # Higher
        "game_minutes": 40.0,
        "halftime_total": 60
    }

    projected = analyzer.project_final_score(game_state)

    # Should use 3.0 (higher pace)
    # Current: 135, Remaining: 10 min * 3.0 = 30
    # Projected: 135 + 30 = 165
    assert projected == pytest.approx(165.0, rel=0.1)


def test_calculate_ot_risk_tied_game():
    """Test OT risk calculation for tied game."""
    analyzer = PaceAnalyzer()

    ot_risk = analyzer.calculate_ot_risk(home_score=70, away_score=70, time_left=2.0)

    assert ot_risk["probability"] == 0.4
    assert ot_risk["projected_ot_points"] == 15


def test_calculate_ot_risk_blowout():
    """Test OT risk for blowout game."""
    analyzer = PaceAnalyzer()

    ot_risk = analyzer.calculate_ot_risk(home_score=90, away_score=70, time_left=2.0)

    # 20-point game - no OT risk
    assert ot_risk["probability"] < 0.1


def test_calculate_ot_risk_too_much_time():
    """Test OT risk returns 0 with too much time left."""
    analyzer = PaceAnalyzer()

    ot_risk = analyzer.calculate_ot_risk(home_score=70, away_score=70, time_left=10.0)

    assert ot_risk["probability"] == 0.0


def test_calculate_fouling_adjustment_playoff():
    """Test fouling adjustment in playoff game."""
    analyzer = PaceAnalyzer()

    # Close playoff game in final 2 minutes
    adjustment = analyzer.calculate_fouling_adjustment(margin=3, time_left=2.0, is_playoff=True)

    assert adjustment == 15.0


def test_calculate_fouling_adjustment_regular_season():
    """Test fouling adjustment in regular season."""
    analyzer = PaceAnalyzer()

    # Close regular season game
    adjustment = analyzer.calculate_fouling_adjustment(margin=3, time_left=2.0, is_playoff=False)

    assert adjustment == 12.0


def test_calculate_fouling_adjustment_no_fouling():
    """Test no fouling adjustment for comfortable lead or too much time."""
    analyzer = PaceAnalyzer()

    # Too much time
    adjustment = analyzer.calculate_fouling_adjustment(margin=3, time_left=5.0, is_playoff=True)
    assert adjustment == 0.0

    # Too large margin
    adjustment = analyzer.calculate_fouling_adjustment(margin=10, time_left=2.0, is_playoff=True)
    assert adjustment == 0.0


def test_analyze_pace_trend_accelerating():
    """Test pace trend analysis - accelerating."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 80,
        "away_score": 75,
        "full_game_pace": 2.5,
        "first_half_pace": 2.0,
        "second_half_pace": 3.0,  # 50% increase
        "halftime_total": 70,  # For get_2h_pace calculation
        "period": 2,
        "clock_minutes": 5.0
    }

    trend = analyzer.analyze_pace_trend(game_state)

    assert trend["pace_direction"] == "accelerating"
    assert trend["pace_change_pct"] > 15
    assert trend["using_2h_pace"] is True


def test_analyze_pace_trend_decelerating():
    """Test pace trend analysis - decelerating."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 60,
        "away_score": 55,
        "full_game_pace": 2.0,
        "first_half_pace": 4.0,  # Higher first half
        "second_half_pace": 2.5,  # Lower second half
        "halftime_total": 90,  # High halftime score
        "period": 2,
        "clock_minutes": 10.0
    }

    trend = analyzer.analyze_pace_trend(game_state)

    # 2H will calculate: (115 - 90) / (20 - 10) = 25 / 10 = 2.5
    # Change: (2.5 - 4.0) / 4.0 = -37.5%
    assert trend["pace_direction"] == "decelerating"
    assert trend["pace_change_pct"] < -15


def test_analyze_pace_trend_stable():
    """Test pace trend analysis - stable."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 70,
        "away_score": 65,
        "full_game_pace": 2.5,
        "first_half_pace": 2.5,
        "second_half_pace": 2.6  # Only 4% change
    }

    trend = analyzer.analyze_pace_trend(game_state)

    assert trend["pace_direction"] == "stable"


def test_conference_inflation_swac():
    """Test SWAC conference gets higher inflation."""
    analyzer = PaceAnalyzer()

    inflation = analyzer._get_conference_inflation("SWAC")
    assert inflation == 1.35


def test_conference_inflation_power5():
    """Test Power 5 conference inflation."""
    analyzer = PaceAnalyzer()

    inflation = analyzer._get_conference_inflation("Power 5")
    assert inflation == 1.15


def test_conference_inflation_default():
    """Test default inflation for unknown conference."""
    analyzer = PaceAnalyzer()

    inflation = analyzer._get_conference_inflation("Unknown Conference")
    assert inflation == 1.20


def test_projection_breakdown():
    """Test full projection breakdown."""
    analyzer = PaceAnalyzer()

    game_state = {
        "home_score": 70,
        "away_score": 70,
        "time_left_minutes": 5.0,
        "full_game_pace": 2.0,
        "second_half_pace": 2.5,
        "game_minutes": 40.0,
        "halftime_total": 65,
        "is_playoff": True,
        "line": 150.0
    }

    breakdown = analyzer.get_projection_breakdown(game_state)

    assert "base_projection" in breakdown
    assert "ot_risk" in breakdown
    assert "fouling_adjustment" in breakdown
    assert "full_projection" in breakdown
    assert "pace_trend" in breakdown
    assert "recommendation" in breakdown


def test_projection_with_default_pace():
    """Test projection falls back to default pace if no pace data."""
    analyzer = PaceAnalyzer()

    # Ensure both full_game_pace and 2H_pace calculation return 0
    # by making it look like start of game (no elapsed time)
    game_state = {
        "home_score": 50,
        "away_score": 45,
        "time_left_minutes": 40.0,  # Full game remaining
        "full_game_pace": 0.0,  # No pace data provided
        "second_half_pace": 0.0,  # No pace data provided
        "game_minutes": 40.0,
        "halftime_total": 0,  # No halftime data
        "period": 1,  # Still in first half
        "clock_minutes": 40.0
    }

    projected = analyzer.project_final_score(game_state)

    # Should use default 2.0 pts/min
    # 95 + (2.0 * 40) = 175
    assert projected == pytest.approx(175.0, rel=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
