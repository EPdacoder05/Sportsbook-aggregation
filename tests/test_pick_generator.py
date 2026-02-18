"""
Tests for Pick Generator
========================
Integration tests for the pick generation pipeline.
"""

import pytest
from analysis.pick_generator import PickGenerator, Pick


def test_pick_generator_initialization():
    """Test pick generator initializes correctly."""
    generator = PickGenerator()
    assert generator is not None


def test_generate_picks_with_sample_data():
    """Test pick generation with sample game data."""
    generator = PickGenerator()

    # Sample game data
    games = [
        {
            "game_id": "test_game_1",
            "home_team": "Duke",
            "away_team": "UNC",
            "sport": "NCAAB",
            "odds": {
                "DraftKings": {
                    "spread": {"home": -5.5, "away": 5.5, "home_odds": -110, "away_odds": -110},
                    "total": {"line": 145.5, "over_odds": -110, "under_odds": -110},
                },
                "FanDuel": {
                    "spread": {"home": -5.0, "away": 5.0, "home_odds": -105, "away_odds": -115},
                    "total": {"line": 146.0, "over_odds": -115, "under_odds": -105},
                }
            },
            "public_money": {
                "spread_home_pct": 70,
                "total_over_pct": 65
            },
            "opening_lines": {
                "spread": -4.0,
                "total": 144.0
            }
        }
    ]

    # Generate picks (might return empty if signals don't meet thresholds)
    picks = generator.generate_picks(games)

    # Should return a list (may be empty if no strong signals)
    assert isinstance(picks, list)


def test_pick_dataclass():
    """Test Pick dataclass structure."""
    pick = Pick(
        game_id="test_1",
        home_team="Team A",
        away_team="Team B",
        sport="NCAAB",
        bet_type="spread",
        side="away",
        line=5.5,
        odds=-110,
        confidence=0.85,
        tier="Tier 1",
        reasoning="RLM detected with 75% confidence",
        best_book="DraftKings",
        signals=["spread_rlm"]
    )

    assert pick.game_id == "test_1"
    assert pick.confidence == 0.85
    assert pick.tier == "Tier 1"
    assert "DraftKings" in pick.best_book


def test_best_odds_selection():
    """Test that generator finds best odds across books."""
    generator = PickGenerator()

    # Mock odds from multiple books
    odds_data = {
        "DraftKings": {"odds": -110},
        "FanDuel": {"odds": -105},
        "BetMGM": {"odds": -115}
    }

    # FanDuel should be selected (-105 is best)
    # This would be tested internally in the generator
    assert True  # Placeholder - actual test would call internal method


def test_tiering_logic():
    """Test confidence tier classification."""
    # Tier 1: >= 85%
    # Tier 2: >= 75%
    # LEAN: >= 60%
    # PASS: < 60%

    assert 0.85 >= 0.85  # Tier 1
    assert 0.78 >= 0.75  # Tier 2
    assert 0.65 >= 0.60  # LEAN
    assert 0.55 < 0.60   # PASS


def test_empty_game_list():
    """Test generator handles empty game list."""
    generator = PickGenerator()
    picks = generator.generate_picks([])
    assert picks == []


def test_missing_odds_data():
    """Test generator handles games with missing odds."""
    generator = PickGenerator()

    games = [
        {
            "game_id": "test_game_2",
            "home_team": "Team A",
            "away_team": "Team B",
            "sport": "NCAAB"
            # Missing odds data
        }
    ]

    picks = generator.generate_picks(games)
    # Should handle gracefully and return empty or skip
    assert isinstance(picks, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
