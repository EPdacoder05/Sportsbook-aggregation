"""Sport-specific configurations for modular support"""

from typing import Dict, List, Any


SPORTS_CONFIG: Dict[str, Dict[str, Any]] = {
    "NFL": {
        "name": "National Football League",
        "season_type": "fall_winter",
        "active_months": [9, 10, 11, 12, 1, 2],  # Sept - Feb
        "bet_types": [
            "spread",
            "moneyline",
            "totals",
            "player_props",
            "team_props",
            "game_props"
        ],
        "popular_props": [
            "passing_yards",
            "rushing_yards",
            "receiving_yards",
            "touchdowns",
            "receptions",
            "interceptions"
        ],
        "twitter_accounts": [
            "@br_betting",
            "@ActionNetworkHQ",
            "@BetMGM",
            "@DKSportsbook",
            "@FanDuel",
            "@PropJoeTV",
            "@drlocks_"
        ],
        "reddit_subreddits": [
            "sportsbook",
            "sportsbetting",
            "nfl",
            "fantasyfootball"
        ],
        "odds_api_sport": "americanfootball_nfl",
        "priority": 1,
        "min_whale_bet": 10000,
        "extreme_public_threshold": 85
    },
    
    "NBA": {
        "name": "National Basketball Association",
        "season_type": "fall_spring",
        "active_months": [10, 11, 12, 1, 2, 3, 4, 5, 6],  # Oct - June
        "bet_types": [
            "spread",
            "moneyline",
            "totals",
            "player_props",
            "team_props",
            "quarter_props"
        ],
        "popular_props": [
            "points",
            "rebounds",
            "assists",
            "three_pointers",
            "points_rebounds_assists",
            "double_double"
        ],
        "twitter_accounts": [
            "@br_betting",
            "@ActionNetworkHQ",
            "@BetMGM",
            "@DKSportsbook",
            "@FanDuel"
        ],
        "reddit_subreddits": [
            "sportsbook",
            "sportsbetting",
            "nba"
        ],
        "odds_api_sport": "basketball_nba",
        "priority": 2,
        "min_whale_bet": 10000,
        "extreme_public_threshold": 85
    },
    
    "NCAAB": {
        "name": "NCAA Men's Basketball",
        "season_type": "fall_spring",
        "active_months": [11, 12, 1, 2, 3, 4],  # Nov - April (March Madness)
        "bet_types": [
            "spread",
            "moneyline",
            "totals",
            "player_props",
            "team_props",
            "first_half",
            "second_half"
        ],
        "popular_props": [
            "points",
            "rebounds",
            "assists",
            "three_pointers"
        ],
        "twitter_accounts": [
            "@br_betting",
            "@ActionNetworkHQ",
            "@BetMGM",
            "@DKSportsbook",
            "@FanDuel",
            "@PropJoeTV"
        ],
        "reddit_subreddits": [
            "sportsbook",
            "sportsbetting",
            "CollegeBasketball"
        ],
        "odds_api_sport": "basketball_ncaab",
        "priority": 2,
        "min_whale_bet": 5000,
        "extreme_public_threshold": 80
    },

    "SOCCER": {
        "name": "Soccer / Football",
        "season_type": "year_round",
        "active_months": list(range(1, 13)),  # Year-round
        "bet_types": [
            "moneyline_3way",
            "spread",
            "totals",
            "both_teams_score",
            "correct_score",
            "player_props"
        ],
        "popular_props": [
            "goals",
            "assists",
            "shots_on_target",
            "cards",
            "anytime_goalscorer"
        ],
        "twitter_accounts": [
            "@br_betting",
            "@ActionNetworkHQ",
            "@BetMGM",
            "@DKSportsbook"
        ],
        "reddit_subreddits": [
            "sportsbook",
            "sportsbetting",
            "soccer"
        ],
        "odds_api_sport": "soccer_epl",  # Premier League
        "leagues": [
            "soccer_epl",  # English Premier League
            "soccer_spain_la_liga",
            "soccer_germany_bundesliga",
            "soccer_italy_serie_a",
            "soccer_uefa_champs_league"
        ],
        "priority": 3,
        "min_whale_bet": 10000,
        "extreme_public_threshold": 85
    },
    
    "MLB": {
        "name": "Major League Baseball",
        "season_type": "spring_fall",
        "active_months": [3, 4, 5, 6, 7, 8, 9, 10],  # March - Oct
        "bet_types": [
            "moneyline",
            "run_line",
            "totals",
            "player_props",
            "team_props",
            "inning_props"
        ],
        "popular_props": [
            "hits",
            "runs",
            "rbis",
            "strikeouts",
            "total_bases",
            "home_runs"
        ],
        "twitter_accounts": [
            "@br_betting",
            "@ActionNetworkHQ",
            "@BetMGM"
        ],
        "reddit_subreddits": [
            "sportsbook",
            "sportsbetting",
            "baseball"
        ],
        "odds_api_sport": "baseball_mlb",
        "priority": 4,
        "min_whale_bet": 10000,
        "extreme_public_threshold": 85
    },
    
    "NHL": {
        "name": "National Hockey League",
        "season_type": "fall_spring",
        "active_months": [10, 11, 12, 1, 2, 3, 4, 5, 6],  # Oct - June
        "bet_types": [
            "moneyline",
            "puck_line",
            "totals",
            "player_props",
            "period_props"
        ],
        "popular_props": [
            "goals",
            "assists",
            "points",
            "shots_on_goal",
            "saves"
        ],
        "twitter_accounts": [
            "@br_betting",
            "@ActionNetworkHQ"
        ],
        "reddit_subreddits": [
            "sportsbook",
            "sportsbetting",
            "hockey"
        ],
        "odds_api_sport": "icehockey_nhl",
        "priority": 5,
        "min_whale_bet": 10000,
        "extreme_public_threshold": 85
    }
}


def get_active_sports(current_month: int) -> List[str]:
    """Get list of sports currently in season"""
    active = []
    for sport_key, config in SPORTS_CONFIG.items():
        if current_month in config["active_months"]:
            active.append(sport_key)
    return sorted(active, key=lambda x: SPORTS_CONFIG[x]["priority"])


def get_sport_config(sport: str) -> Dict[str, Any]:
    """Get configuration for specific sport"""
    return SPORTS_CONFIG.get(sport.upper(), {})


def get_all_twitter_accounts() -> List[str]:
    """Get all Twitter accounts to monitor across all sports"""
    accounts = set()
    for config in SPORTS_CONFIG.values():
        accounts.update(config.get("twitter_accounts", []))
    return sorted(list(accounts))


def get_all_reddit_subreddits() -> List[str]:
    """Get all Reddit subreddits to monitor"""
    subreddits = set()
    for config in SPORTS_CONFIG.values():
        subreddits.update(config.get("reddit_subreddits", []))
    return sorted(list(subreddits))
