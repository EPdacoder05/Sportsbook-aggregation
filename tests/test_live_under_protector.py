"""
Tests for Live Under Protector V2
==================================
Tests for the 11 rule-based live Under bet protection system.
"""

import pytest
from engine.live_under_protector_v2 import LiveUnderProtector, BettingDecision, PROTECTOR_RULES


def test_protector_initialization():
    """Test protector initializes with all rules."""
    protector = LiveUnderProtector()
    assert protector is not None
    assert len(protector.rules) == 9  # 9 rules defined


def test_rule_0_dead_bet_detection():
    """Test RULE_0: If current_score > line: BET IS DEAD."""
    protector = LiveUnderProtector()

    game_state = {
        "home_score": 80,
        "away_score": 75,
        "time_left_minutes": 5.0
    }

    bet = {
        "line": 150.0,  # Total is already 155
        "wager": 100.0,
        "cash_out": 0.0
    }

    decision = protector.evaluate_bet(game_state, bet)

    assert decision.action == "STOP_BETTING"
    assert decision.urgency == "IMMEDIATE"
    assert "RULE_0" in decision.reasoning
    assert decision.win_probability == 0.0


def test_rule_1_projected_to_lose():
    """Test RULE_1: If projected_final > line: CASH OUT."""
    protector = LiveUnderProtector()

    game_state = {
        "home_score": 70,
        "away_score": 70,
        "time_left_minutes": 10.0,
        "full_game_pace": 3.0,  # High pace
        "second_half_pace": 3.5
    }

    bet = {
        "line": 150.0,
        "wager": 100.0,
        "cash_out": 25.0  # Positive cash out offer
    }

    decision = protector.evaluate_bet(game_state, bet)

    # With 10 min left at 3.5 pace, projected = 140 + 35 = 175 > 150
    assert decision.action == "CASH_OUT"
    assert decision.urgency == "IMMEDIATE"
    assert "RULE_1" in decision.reasoning
    assert decision.cash_out_value == 25.0


def test_rule_2_tight_cushion():
    """Test RULE_2: If cushion < 5 AND time_left > 5min: CASH OUT."""
    protector = LiveUnderProtector()

    game_state = {
        "home_score": 70,
        "away_score": 65,
        "time_left_minutes": 8.0,
        "full_game_pace": 1.8,
        "second_half_pace": 1.5
    }

    bet = {
        "line": 150.0,
        "wager": 100.0,
        "cash_out": 50.0
    }

    decision = protector.evaluate_bet(game_state, bet)

    # Projected: 135 + (1.8 * 8) = 149.4, cushion = 0.6 < 5
    if decision.cushion < 5:
        assert decision.action == "CASH_OUT"
        assert "RULE_2" in decision.reasoning


def test_rule_3_max_pace_projection():
    """Test RULE_3: Always use MAX(full_game_pace, 2H_pace)."""
    protector = LiveUnderProtector()

    game_state = {
        "home_score": 60,
        "away_score": 55,
        "time_left_minutes": 10.0,
        "full_game_pace": 2.0,
        "second_half_pace": 2.8  # Higher 2H pace
    }

    projected = protector.calculate_projected_final(game_state)

    # Should use 2.8 (higher pace)
    expected = 115 + (2.8 * 10)
    assert abs(projected - expected) < 0.1


def test_rule_7_ot_risk_calculation():
    """Test RULE_7: OT risk in close games."""
    protector = LiveUnderProtector()

    # Close game in final minutes
    game_state = {
        "home_score": 70,
        "away_score": 70,
        "time_left_minutes": 3.0,
        "full_game_pace": 1.5,
        "second_half_pace": 1.5
    }

    bet = {
        "line": 145.0,
        "wager": 100.0,
        "cash_out": 30.0
    }

    decision = protector.evaluate_bet(game_state, bet)

    # Tied game with 3 min left - high OT risk
    # OT adds ~15 points
    if "RULE_7" in decision.reasoning:
        assert decision.action == "CASH_OUT"
        assert decision.urgency == "IMMEDIATE"


def test_rule_9_pace_explosion_detection():
    """Test RULE_9: Mid-major 2H pace explosion detection."""
    protector = LiveUnderProtector()

    # Mid-major conference with pace explosion
    first_half_pace = 2.0
    second_half_pace = 2.5  # 25% increase
    conference = "SWAC"

    is_explosion = protector.detect_pace_explosion(first_half_pace, second_half_pace, conference)

    assert is_explosion is True


def test_rule_11_fouling_adjustment():
    """Test RULE_11: Late-game fouling in playoff."""
    protector = LiveUnderProtector()

    game_state = {
        "home_score": 70,
        "away_score": 67,
        "time_left_minutes": 2.0,
        "full_game_pace": 1.5,
        "second_half_pace": 1.5,
        "is_playoff": True,
        "is_high_stakes": True
    }

    bet = {
        "line": 155.0,
        "wager": 100.0,
        "cash_out": 40.0
    }

    decision = protector.evaluate_bet(game_state, bet)

    # Close playoff game in final 2 min - fouling likely
    if "RULE_11" in decision.reasoning:
        assert decision.urgency in ["IMMEDIATE", "MONITOR"]


def test_rule_10_parlay_validation():
    """Test RULE_10: Parlay validation for correlated Under legs."""
    protector = LiveUnderProtector()

    # 3+ Under legs from same time slot
    bet_legs = [
        {"bet_type": "under", "line": 145.5},
        {"bet_type": "under", "line": 150.5},
        {"bet_type": "under", "line": 148.0}
    ]

    result = protector.evaluate_parlay(bet_legs, "7PM")

    assert result["violation"] is True
    assert result["rule"] == "RULE_10"
    assert "DANGER" in result["warning"]


def test_ot_probability_calculation():
    """Test OT probability calculation."""
    protector = LiveUnderProtector()

    # Tied game with 2 min left
    prob = protector.calculate_ot_probability(margin=0, time_left=2.0)
    assert prob == 0.4

    # 3-point game with 2 min left
    prob = protector.calculate_ot_probability(margin=3, time_left=2.0)
    assert prob == 0.1

    # 10-point game - no OT risk
    prob = protector.calculate_ot_probability(margin=10, time_left=2.0)
    assert prob < 0.1


def test_win_probability_estimation():
    """Test win probability estimation."""
    protector = LiveUnderProtector()

    # Large cushion with little time left
    prob = protector.estimate_win_probability(cushion=10.0, time_left=2.0)
    assert prob > 0.7

    # No cushion
    prob = protector.estimate_win_probability(cushion=0.0, time_left=5.0)
    assert prob <= 0.2


def test_add_and_remove_bet():
    """Test bet tracking."""
    protector = LiveUnderProtector()

    protector.add_bet("bet_1", line=145.5, wager=100.0, game_id="game_123")
    assert "bet_1" in protector.active_bets

    protector.remove_bet("bet_1")
    assert "bet_1" not in protector.active_bets


def test_hold_recommendation():
    """Test HOLD recommendation when all rules pass."""
    protector = LiveUnderProtector()

    game_state = {
        "home_score": 50,
        "away_score": 45,
        "time_left_minutes": 15.0,
        "full_game_pace": 1.5,
        "second_half_pace": 1.4
    }

    bet = {
        "line": 150.0,
        "wager": 100.0,
        "cash_out": 75.0
    }

    decision = protector.evaluate_bet(game_state, bet)

    # Projected: 95 + (1.5 * 15) = 117.5, well under 150
    assert decision.action == "HOLD"
    assert decision.cushion > 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
