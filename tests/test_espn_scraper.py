"""
Tests for ESPN Schedule Scraper
================================
Tests for ESPN API schedule fetching.
"""

import pytest
from scrapers.espn_schedule_scraper import ESPNScheduleScraper


def test_scraper_initialization():
    """Test scraper initializes correctly."""
    scraper = ESPNScheduleScraper()
    assert scraper is not None
    assert "NCAAB" in scraper.ENDPOINTS
    assert "NCAAW" in scraper.ENDPOINTS


def test_endpoints_defined():
    """Test that endpoints are properly defined."""
    scraper = ESPNScheduleScraper()

    assert "basketball/mens-college-basketball" in scraper.ENDPOINTS["NCAAB"]
    assert "basketball/womens-college-basketball" in scraper.ENDPOINTS["NCAAW"]


def test_parse_event_basic():
    """Test parsing a basic event structure."""
    scraper = ESPNScheduleScraper()

    # Mock event data structure
    mock_event = {
        "id": "401234567",
        "date": "2026-02-18T19:00Z",
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": "Duke Blue Devils"},
                        "score": 0
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": "UNC Tar Heels"},
                        "score": 0
                    }
                ],
                "status": {
                    "type": {
                        "description": "Scheduled",
                        "state": "pre"
                    }
                },
                "venue": {"fullName": "Cameron Indoor Stadium"},
                "broadcasts": [{"names": ["ESPN"]}]
            }
        ]
    }

    game = scraper._parse_event(mock_event, "NCAAB")

    assert game["game_id"] == "401234567"
    assert game["home_team"] == "Duke Blue Devils"
    assert game["away_team"] == "UNC Tar Heels"
    assert game["status"] == "Scheduled"
    assert game["network"] == "ESPN"
    assert game["sport"] == "NCAAB"


def test_parse_event_with_rankings():
    """Test parsing event with team rankings."""
    scraper = ESPNScheduleScraper()

    mock_event = {
        "id": "401234568",
        "date": "2026-02-18T19:00Z",
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": "Duke Blue Devils"},
                        "curatedRank": {"current": 1},
                        "score": 0
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": "UNC Tar Heels"},
                        "curatedRank": {"current": 5},
                        "score": 0
                    }
                ],
                "status": {
                    "type": {
                        "description": "Scheduled",
                        "state": "pre"
                    }
                },
                "venue": {"fullName": "Cameron Indoor Stadium"}
            }
        ]
    }

    game = scraper._parse_event(mock_event, "NCAAB")

    assert game["home_rank"] == 1
    assert game["away_rank"] == 5


def test_parse_live_game():
    """Test parsing live game data."""
    scraper = ESPNScheduleScraper()

    mock_event = {
        "id": "401234569",
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": "Duke Blue Devils"},
                        "score": 45
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": "UNC Tar Heels"},
                        "score": 42
                    }
                ],
                "status": {
                    "type": {
                        "description": "In Progress",
                        "state": "in"
                    }
                }
            }
        ]
    }

    game = scraper._parse_live_game(mock_event, "NCAAB")

    assert game["game_id"] == "401234569"
    assert game["home_score"] == 45
    assert game["away_score"] == 42
    assert game["status"] == "In Progress"


def test_format_schedule_table():
    """Test schedule formatting to markdown table."""
    scraper = ESPNScheduleScraper()

    games = [
        {
            "home_team": "Duke Blue Devils",
            "away_team": "UNC Tar Heels",
            "start_time_est": "07:00 PM ET",
            "network": "ESPN",
            "venue": "Cameron Indoor Stadium",
            "home_rank": 1,
            "away_rank": 5
        },
        {
            "home_team": "Kansas Jayhawks",
            "away_team": "Kentucky Wildcats",
            "start_time_est": "09:00 PM ET",
            "network": "ESPN2",
            "venue": "Allen Fieldhouse",
            "home_rank": None,
            "away_rank": 10
        }
    ]

    table = scraper.format_schedule_table(games)

    assert "## Schedule" in table
    assert "07:00 PM ET" in table
    assert "09:00 PM ET" in table
    assert "#1 Duke Blue Devils" in table
    assert "#5 UNC Tar Heels" in table
    assert "#10 Kentucky Wildcats" in table
    assert "ESPN" in table


def test_format_schedule_table_empty():
    """Test formatting empty game list."""
    scraper = ESPNScheduleScraper()

    table = scraper.format_schedule_table([])
    assert table == "No games found."


def test_parse_event_missing_data():
    """Test parsing event with missing data."""
    scraper = ESPNScheduleScraper()

    # Event with minimal data
    mock_event = {
        "id": "401234570",
        "competitions": []
    }

    game = scraper._parse_event(mock_event, "NCAAB")
    assert game == {}


def test_parse_event_insufficient_competitors():
    """Test parsing event with insufficient competitors."""
    scraper = ESPNScheduleScraper()

    mock_event = {
        "id": "401234571",
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Team A"}}
                    # Missing away team
                ]
            }
        ]
    }

    game = scraper._parse_event(mock_event, "NCAAB")
    assert game == {}


@pytest.mark.asyncio
async def test_get_todays_games_invalid_sport():
    """Test handling invalid sport parameter."""
    scraper = ESPNScheduleScraper()

    games = await scraper.get_todays_games(sport="INVALID")
    assert games == []


@pytest.mark.asyncio
async def test_get_live_scores_invalid_sport():
    """Test handling invalid sport in live scores."""
    scraper = ESPNScheduleScraper()

    games = await scraper.get_live_scores(sport="INVALID")
    assert games == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
