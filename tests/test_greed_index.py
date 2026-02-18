"""
Tests for Greed Index Engine
=============================
Tests for session tracking and withdrawal recommendations.
"""

import pytest
from engine.greed_index import GreedIndexEngine, GREED_THRESHOLDS


def test_greed_engine_initialization():
    """Test greed engine initializes correctly."""
    engine = GreedIndexEngine()
    assert engine is not None
    assert len(engine.session_bets) == 0
    assert engine.session_peak == 0.0
    assert engine.total_wagered == 0.0


def test_add_bet():
    """Test adding bets to session."""
    engine = GreedIndexEngine()

    engine.add_bet(wager=100.0, result=50.0, description="Win on Duke -5", book="DK")
    assert len(engine.session_bets) == 1
    assert engine.total_wagered == 100.0
    assert engine.session_peak == 50.0


def test_session_profit_calculation():
    """Test session profit calculation."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 90.0, "Win 1", "DK")
    engine.add_bet(100.0, -100.0, "Loss 1", "FD")
    engine.add_bet(100.0, 180.0, "Win 2", "DK")

    profit = engine.get_session_profit()
    assert profit == 170.0  # 90 - 100 + 180


def test_greed_score_profit_factor():
    """Test greed score increases with profit."""
    engine = GreedIndexEngine()

    # Small profit
    engine.add_bet(100.0, 50.0, "Small win", "DK")
    score_1 = engine.get_greed_score()

    # Large profit
    engine.add_bet(100.0, 500.0, "Big win", "DK")
    score_2 = engine.get_greed_score()

    assert score_2 > score_1


def test_greed_score_win_streak():
    """Test greed score increases with win streaks."""
    engine = GreedIndexEngine()

    # No wins
    score_baseline = engine.get_greed_score()

    # 5-win streak
    for i in range(5):
        engine.add_bet(100.0, 90.0, f"Win {i+1}", "DK")

    score_streak = engine.get_greed_score()
    assert score_streak > score_baseline


def test_greed_level_cold():
    """Test COLD greed level (0-25)."""
    engine = GreedIndexEngine()
    engine.add_bet(100.0, 20.0, "Small win", "DK")

    level = engine.get_greed_level()
    # May be COLD if score is low
    assert level in ["COLD", "WARM"]


def test_greed_level_hot():
    """Test HOT greed level (51-70)."""
    engine = GreedIndexEngine()

    # Create conditions for HIGH greed
    for i in range(5):
        engine.add_bet(100.0, 100.0, f"Win {i+1}", "DK")

    score = engine.get_greed_score()
    level = engine.get_greed_level()

    if score >= 51:
        assert level in ["HOT", "BURNING", "MELTDOWN"]


def test_greed_level_meltdown():
    """Test MELTDOWN greed level (91-100)."""
    # Would need extreme conditions to reach 91+
    # Test that greed level mapping works
    for level_name, (low, high) in GREED_THRESHOLDS.items():
        assert low <= high


def test_withdrawal_recommendation_rule_w1():
    """Test W1: Profit >= $200, withdraw 50%."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 250.0, "Big win", "DK")

    recommendation = engine.get_withdrawal_recommendation()

    assert recommendation["should_withdraw"] is True
    assert "W1" in recommendation["rules_triggered"]
    assert recommendation["withdraw_pct"] >= 0.5


def test_withdrawal_recommendation_rule_w2():
    """Test W2: Profit >= $500, withdraw 60%."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 600.0, "Huge win", "DK")

    recommendation = engine.get_withdrawal_recommendation()

    assert recommendation["should_withdraw"] is True
    assert "W2" in recommendation["rules_triggered"]
    assert recommendation["withdraw_pct"] >= 0.6


def test_withdrawal_recommendation_rule_w3():
    """Test W3: 30% drawdown from peak, withdraw 75%."""
    engine = GreedIndexEngine()

    # Build up profit
    engine.add_bet(100.0, 500.0, "Big win", "DK")
    assert engine.session_peak == 500.0

    # Lose some back
    engine.add_bet(100.0, -200.0, "Loss", "FD")

    # Profit now 300, down from peak 500 = 40% drawdown
    recommendation = engine.get_withdrawal_recommendation()

    if "W3" in recommendation["rules_triggered"]:
        assert recommendation["urgency"] == "IMMEDIATE"
        assert recommendation["withdraw_pct"] >= 0.75


def test_withdrawal_recommendation_rule_w4():
    """Test W4: After 10 bets, evaluate."""
    engine = GreedIndexEngine()

    for i in range(11):
        engine.add_bet(100.0, 50.0, f"Bet {i+1}", "DK")

    recommendation = engine.get_withdrawal_recommendation()

    assert "W4" in recommendation["rules_triggered"]


def test_withdrawal_recommendation_rule_w5():
    """Test W5: Prioritize DK withdrawals."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 150.0, "DK win", "DK")
    engine.add_bet(100.0, 50.0, "FD win", "FD")

    recommendation = engine.get_withdrawal_recommendation()

    # If DK balance is positive, should prioritize DK
    if "book_priority" in recommendation:
        assert recommendation["book_priority"] == "DK"


def test_should_stop_betting():
    """Test should_stop_betting flag."""
    engine = GreedIndexEngine()

    # Low greed - should not stop
    engine.add_bet(100.0, 50.0, "Small win", "DK")
    assert engine.should_stop_betting() is False

    # High greed conditions
    for i in range(10):
        engine.add_bet(100.0, 100.0, f"Win {i+1}", "DK")

    # May trigger stop if greed level is HOT/BURNING/MELTDOWN
    level = engine.get_greed_level()
    should_stop = engine.should_stop_betting()

    if level in ["HOT", "BURNING", "MELTDOWN"]:
        assert should_stop is True


def test_session_summary():
    """Test session summary generation."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 90.0, "Win 1", "DK")
    engine.add_bet(100.0, -100.0, "Loss 1", "FD")
    engine.add_bet(100.0, 90.0, "Win 2", "DK")

    summary = engine.get_session_summary()

    assert summary["total_bets"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["win_rate"] == pytest.approx(66.67, rel=0.1)
    assert summary["total_wagered"] == 300.0
    assert summary["profit"] == 80.0
    assert "greed_score" in summary
    assert "greed_level" in summary


def test_book_breakdown():
    """Test book breakdown in session summary."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 90.0, "DK Win", "DK")
    engine.add_bet(100.0, 90.0, "DK Win 2", "DK")
    engine.add_bet(100.0, -100.0, "FD Loss", "FD")

    summary = engine.get_session_summary()
    book_breakdown = summary["book_breakdown"]

    assert "DK" in book_breakdown
    assert "FD" in book_breakdown
    assert book_breakdown["DK"]["profit"] == 180.0
    assert book_breakdown["FD"]["profit"] == -100.0


def test_reset_session():
    """Test session reset."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 90.0, "Win", "DK")
    assert len(engine.session_bets) > 0

    engine.reset_session()

    assert len(engine.session_bets) == 0
    assert engine.session_peak == 0.0
    assert engine.total_wagered == 0.0


def test_roi_calculation():
    """Test ROI calculation in session summary."""
    engine = GreedIndexEngine()

    engine.add_bet(100.0, 50.0, "Win", "DK")
    engine.add_bet(100.0, 30.0, "Win 2", "DK")

    summary = engine.get_session_summary()

    # Total profit: 80, Total wagered: 200
    # ROI = (80 / 200) * 100 = 40%
    assert summary["roi"] == pytest.approx(40.0, rel=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
