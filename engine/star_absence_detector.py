#!/usr/bin/env python3
"""
STAR ABSENCE DETECTOR — ESPN Injury Integration
=================================================
Tonight (Feb 9, 2026) SGA, Curry, Ja, Giannis, and Luka were ALL out.
This cratered our parlay legs that needed GS Over 218.5 and LAL ML.

Key insight: When a top-usage player (>25 USG%) is confirmed OUT within
2-4 hours of tip-off, it's not just a confirmation signal — it's a
PRIMARY signal that should auto-adjust totals confidence.

Star absences move lines 2-4 points. Without Curry, GS total drops ~5pts.
Without SGA, OKC's covering ability changes entirely.

Data source: ESPN injury API (FREE, no key needed)

Signal types:
  STAR_OUT:        Top-15 usage player confirmed OUT → primary signal
  STAR_GTD:        Star listed Game-Time Decision → confirmation signal
  MULTI_STAR_OUT:  2+ stars out in same game → nuclear-level signal

Impact rules:
  - Star OUT → total confidence for UNDER increases +10%, OVER decreases -15%
  - Star OUT on the dog → spread confidence for fav increases +5%
  - 2+ stars out → total likely 5-8pts below market → massive Under signal

Usage:
    from engine.star_absence_detector import StarAbsenceDetector
    detector = StarAbsenceDetector()
    injuries = detector.fetch_injuries()
    signals = detector.detect_impact(injuries, game_data)
"""

import json
import logging
import sys
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ESPN team IDs
ESPN_TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 17, "CHA": 30, "CHI": 4,
    "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GS": 9,
    "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MEM": 29,
    "MIA": 14, "MIL": 15, "MIN": 16, "NOP": 3, "NYK": 18,
    "OKC": 25, "ORL": 19, "PHI": 20, "PHX": 21, "POR": 22,
    "SAC": 23, "SAS": 24, "TOR": 28, "UTA": 26, "WAS": 27,
}

# Top-usage stars — players whose absence shifts lines 2-5 pts
# Approximate usage rate and typical impact on team total when OUT
# 🚨 FEB 2026 TRADE DEADLINE: Teams updated for mid-season trades
STAR_IMPACT = {
    # Format: "Player Name": {"team": "ABR", "usage": float, "total_impact": float, "spread_impact": float}
    "Luka Doncic":      {"team": "DAL", "usage": 33.2, "total_impact": -5.0, "spread_impact": 3.5},
    "Shai Gilgeous-Alexander": {"team": "OKC", "usage": 32.5, "total_impact": -4.5, "spread_impact": 3.0},
    "Giannis Antetokounmpo": {"team": "MIL", "usage": 32.0, "total_impact": -4.0, "spread_impact": 4.0},
    "Stephen Curry":    {"team": "GS",  "usage": 30.5, "total_impact": -5.0, "spread_impact": 2.5},
    "Ja Morant":        {"team": "MEM", "usage": 31.0, "total_impact": -4.5, "spread_impact": 3.5},
    "LeBron James":     {"team": "LAL", "usage": 30.0, "total_impact": -4.0, "spread_impact": 3.0},
    "Kevin Durant":     {"team": "PHX", "usage": 30.8, "total_impact": -4.5, "spread_impact": 3.0},
    "Joel Embiid":      {"team": "PHI", "usage": 33.5, "total_impact": -5.0, "spread_impact": 4.5},
    "Nikola Jokic":     {"team": "DEN", "usage": 29.5, "total_impact": -4.0, "spread_impact": 4.0},
    "Anthony Edwards":  {"team": "MIN", "usage": 30.0, "total_impact": -4.0, "spread_impact": 2.5},
    "Jayson Tatum":     {"team": "BOS", "usage": 29.8, "total_impact": -3.5, "spread_impact": 2.5},
    "Donovan Mitchell": {"team": "CLE", "usage": 29.0, "total_impact": -3.5, "spread_impact": 2.0},
    "James Harden":     {"team": "CLE", "usage": 27.5, "total_impact": -3.5, "spread_impact": 2.5},  # ✅ TRADED Feb 2026
    "Tyrese Haliburton": {"team": "IND", "usage": 27.5, "total_impact": -3.5, "spread_impact": 2.5},
    "De'Aaron Fox":     {"team": "SAC", "usage": 28.5, "total_impact": -3.5, "spread_impact": 2.5},
    "Damian Lillard":   {"team": "MIL", "usage": 28.0, "total_impact": -3.5, "spread_impact": 2.0},
    "Trae Young":       {"team": "ATL", "usage": 29.0, "total_impact": -3.5, "spread_impact": 2.5},
    "Devin Booker":     {"team": "PHX", "usage": 28.5, "total_impact": -3.0, "spread_impact": 2.0},
    "Kyrie Irving":     {"team": "DAL", "usage": 27.0, "total_impact": -3.0, "spread_impact": 2.0},
    "Jimmy Butler":     {"team": "MIA", "usage": 27.5, "total_impact": -3.0, "spread_impact": 2.5},
    "Zion Williamson":  {"team": "NOP", "usage": 28.0, "total_impact": -3.5, "spread_impact": 2.5},
}


class AbsenceSignal(Enum):
    STAR_OUT = "STAR_OUT"              # Confirmed OUT
    STAR_GTD = "STAR_GTD"              # Game-Time Decision
    MULTI_STAR_OUT = "MULTI_STAR_OUT"  # 2+ stars out in same game
    NONE = "NONE"


@dataclass
class InjuryInfo:
    """Parsed injury information for a player."""
    player_name: str
    team: str
    status: str           # "Out", "Day-To-Day", "Questionable", "Probable"
    reason: str           # "Ankle", "Rest", etc.
    is_star: bool
    total_impact: float   # Expected pts reduction to team total
    spread_impact: float  # Expected spread impact


@dataclass
class StarAbsenceResult:
    """Full analysis result for a game's injury situation."""
    game_key: str
    signal: AbsenceSignal
    injuries: List[InjuryInfo]
    star_injuries: List[InjuryInfo]
    total_impact: float          # Net total impact (negative = lower scoring expected)
    spread_impact: float         # Net spread impact (positive = favors healthy team)
    under_boost: float           # How much to boost Under confidence (0-20%)
    over_penalty: float          # How much to penalize Over confidence (0-20%)
    confidence_adjustment: float # Overall confidence delta for existing picks
    description: str
    recommendation: str

    def to_dict(self) -> Dict:
        return {
            "game_key": self.game_key,
            "signal": self.signal.value,
            "star_injuries": [
                {
                    "player": i.player_name,
                    "team": i.team,
                    "status": i.status,
                    "total_impact": i.total_impact,
                }
                for i in self.star_injuries
            ],
            "total_impact": round(self.total_impact, 1),
            "spread_impact": round(self.spread_impact, 1),
            "under_boost": round(self.under_boost, 1),
            "over_penalty": round(self.over_penalty, 1),
            "description": self.description,
            "recommendation": self.recommendation,
        }


class StarAbsenceDetector:
    """
    Fetches injuries from ESPN and detects star absences that
    should trigger signal adjustments.
    
    Now integrates with RosterUpdateTracker to handle trade deadline
    roster changes (e.g., James Harden → CLE).
    """

    def __init__(self, roster_tracker=None, auto_sync_rosters: bool = True):
        """
        Initialize detector with optional roster tracking.
        
        Args:
            roster_tracker: RosterUpdateTracker instance (optional)
            auto_sync_rosters: Auto-sync rosters during trade deadline period
        """
        self.roster_tracker = roster_tracker
        self.auto_sync = auto_sync_rosters
        self._star_impact_cache = None  # Cached STAR_IMPACT with updated teams
        
        # Auto-load roster tracker if in trade deadline period
        if auto_sync_rosters and roster_tracker is None:
            try:
                from engine.roster_update_tracker import RosterUpdateTracker
                self.roster_tracker = RosterUpdateTracker()
                if self.roster_tracker.is_trade_deadline_period():
                    logger.info("Trade deadline period detected — syncing rosters")
                    self.sync_rosters()
            except Exception as e:
                logger.warning(f"Could not auto-load roster tracker: {e}")
    
    def sync_rosters(self, force: bool = False) -> int:
        """
        Sync STAR_IMPACT teams with current NBA rosters.
        
        Returns:
            Number of roster changes detected
        """
        if not self.roster_tracker:
            logger.warning("No roster tracker configured — skipping sync")
            return 0
        
        changes = self.roster_tracker.sync_star_rosters(force=force)
        if changes:
            logger.info(f"Detected {len(changes)} roster changes:")
            for change in changes:
                logger.info(f"  {change.player_name}: {change.old_team} → {change.new_team}")
        
        # Update cached STAR_IMPACT
        self._star_impact_cache = self.roster_tracker.get_updated_star_impact()
        return len(changes)
    
    def get_star_impact(self) -> Dict:
        """
        Get STAR_IMPACT dictionary with current teams.
        
        Returns cached updated version if available, else returns original.
        """
        if self._star_impact_cache:
            return self._star_impact_cache
        return STAR_IMPACT
    
    def get_player_team(self, player_name: str) -> Optional[str]:
        """
        Get current team for a player, checking roster tracker if available.
        
        Args:
            player_name: Player's name
        
        Returns:
            Team abbreviation or None
        """
        # First check updated cache
        star_impact = self.get_star_impact()
        if player_name in star_impact:
            return star_impact[player_name].get("team")
        
        # Fallback to roster tracker if available
        if self.roster_tracker:
            return self.roster_tracker.get_current_team(player_name)
        
        return None

    def fetch_injuries_from_scoreboard(self, date_str: Optional[str] = None) -> List[Dict]:
        """
        Fetch today's games and extract injury reports from ESPN scoreboard.
        ESPN event data sometimes includes injury info in the "notes" or
        competitor status fields.

        Returns list of raw game dicts with any available injury data.
        """
        params = {}
        if date_str:
            params["dates"] = date_str

        try:
            resp = requests.get(ESPN_SCOREBOARD_URL, params=params,
                                headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"ESPN scoreboard fetch failed: {e}")
            return []

        games = []
        for event in data.get("events", []):
            comp = event.get("competitions", [{}])[0]
            teams = comp.get("competitors", [])
            if len(teams) < 2:
                continue

            home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])

            game = {
                "game_key": f"{away['team']['abbreviation']} @ {home['team']['abbreviation']}",
                "home_team": home["team"]["abbreviation"],
                "away_team": away["team"]["abbreviation"],
                "home_injuries": home.get("injuries", []),
                "away_injuries": away.get("injuries", []),
                "notes": [n.get("headline", "") for n in event.get("competitions", [{}])[0].get("notes", [])],
            }
            games.append(game)

        return games

    def detect_from_manual_report(
        self,
        game_key: str,
        players_out: List[str],
        players_gtd: Optional[List[str]] = None,
    ) -> StarAbsenceResult:
        """
        Detect star absence impact from manual injury reporting.

        This is the most reliable method since ESPN's injury API
        isn't always real-time. Use when you know who's OUT.

        Args:
            game_key: "OKC @ LAL" etc.
            players_out: ["Shai Gilgeous-Alexander", "Stephen Curry"]
            players_gtd: ["LeBron James"]  (optional)
        """
        injuries: List[InjuryInfo] = []
        star_injuries: List[InjuryInfo] = []

        # Process OUT players
        star_impact = self.get_star_impact()  # Use updated teams if available
        
        for player in players_out:
            impact = star_impact.get(player, {})
            is_star = player in star_impact
            
            # Get current team (handles trades)
            current_team = self.get_player_team(player) or impact.get("team", "?")
            
            injury = InjuryInfo(
                player_name=player,
                team=current_team,
                status="Out",
                reason="Reported OUT",
                is_star=is_star,
                total_impact=impact.get("total_impact", -1.0) if is_star else -1.0,
                spread_impact=impact.get("spread_impact", 0.5) if is_star else 0.5,
            )
            injuries.append(injury)
            if is_star:
                star_injuries.append(injury)

        # Process GTD players
        for player in (players_gtd or []):
            impact = star_impact.get(player, {})
            is_star = player in star_impact
            
            # Get current team (handles trades)
            current_team = self.get_player_team(player) or impact.get("team", "?")
            
            injury = InjuryInfo(
                player_name=player,
                team=current_team,
                status="Game-Time Decision",
                reason="GTD",
                is_star=is_star,
                total_impact=impact.get("total_impact", -0.5) * 0.5 if is_star else -0.5,
                spread_impact=impact.get("spread_impact", 0.25) * 0.5 if is_star else 0.25,
            )
            injuries.append(injury)
            if is_star:
                star_injuries.append(injury)

        return self._build_result(game_key, injuries, star_injuries)

    def _build_result(
        self,
        game_key: str,
        injuries: List[InjuryInfo],
        star_injuries: List[InjuryInfo],
    ) -> StarAbsenceResult:
        """Build the final result from parsed injuries."""
        if not star_injuries:
            return StarAbsenceResult(
                game_key=game_key,
                signal=AbsenceSignal.NONE,
                injuries=injuries,
                star_injuries=[],
                total_impact=0,
                spread_impact=0,
                under_boost=0,
                over_penalty=0,
                confidence_adjustment=0,
                description="No star absences detected.",
                recommendation="Proceed with standard analysis.",
            )

        # Calculate cumulative impact
        total_impact = sum(i.total_impact for i in star_injuries)
        spread_impact = sum(i.spread_impact for i in star_injuries)

        # Determine signal type
        out_stars = [i for i in star_injuries if i.status == "Out"]
        if len(out_stars) >= 2:
            signal = AbsenceSignal.MULTI_STAR_OUT
        elif out_stars:
            signal = AbsenceSignal.STAR_OUT
        else:
            signal = AbsenceSignal.STAR_GTD

        # Calculate confidence adjustments
        # Star OUT → Under gets boosted, Over gets penalized
        under_boost = min(20, abs(total_impact) * 3)  # Up to +20%
        over_penalty = min(20, abs(total_impact) * 3.5)  # Up to -20%

        # Build description
        star_names = [f"{i.player_name} ({i.team}, {i.status})" for i in star_injuries]
        names_str = ", ".join(star_names)

        description = (
            f"{signal.value}: {names_str}. "
            f"Expected total impact: {total_impact:+.1f}pts. "
            f"Spread impact: {spread_impact:+.1f}pts toward healthy side."
        )

        if signal == AbsenceSignal.MULTI_STAR_OUT:
            recommendation = (
                f"NUCLEAR: {len(out_stars)} stars OUT. "
                f"Under confidence +{under_boost:.0f}%, Over confidence {-over_penalty:.0f}%. "
                f"Total should be ~{abs(total_impact):.0f}pts lower than market."
            )
        elif signal == AbsenceSignal.STAR_OUT:
            recommendation = (
                f"Star OUT: {out_stars[0].player_name}. "
                f"Under gets +{under_boost:.0f}% confidence. "
                f"Over gets {-over_penalty:.0f}%. "
                f"Check if market has already adjusted."
            )
        else:
            recommendation = (
                f"Star GTD: monitoring. "
                f"If confirmed OUT, adjust Under +{under_boost:.0f}%."
            )

        return StarAbsenceResult(
            game_key=game_key,
            signal=signal,
            injuries=injuries,
            star_injuries=star_injuries,
            total_impact=total_impact,
            spread_impact=spread_impact,
            under_boost=under_boost,
            over_penalty=over_penalty,
            confidence_adjustment=under_boost,
            description=description,
            recommendation=recommendation,
        )

    def analyze_slate(
        self,
        players_out_by_game: Dict[str, List[str]],
    ) -> List[StarAbsenceResult]:
        """
        Analyze star absences for an entire slate.

        Args:
            players_out_by_game: {"OKC @ LAL": ["Shai Gilgeous-Alexander"], ...}
        """
        results = []
        for game_key, players in players_out_by_game.items():
            result = self.detect_from_manual_report(game_key, players)
            results.append(result)
        return results


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 70)
    print("  STAR ABSENCE DETECTOR — Demo")
    print("  (Based on Feb 9, 2026: SGA, Curry, Ja, Giannis, Luka all OUT)")
    print("═" * 70)

    detector = StarAbsenceDetector()

    # Tonight's actual injury situation
    tonight = {
        "MEM @ GS": ["Ja Morant", "Stephen Curry"],
        "OKC @ LAL": ["Shai Gilgeous-Alexander"],
        "MIL @ ORL": ["Giannis Antetokounmpo"],
    }

    for game_key, players_out in tonight.items():
        result = detector.detect_from_manual_report(game_key, players_out)
        print(f"\n  Game: {game_key}")
        print(f"  Signal: {result.signal.value}")
        print(f"  Total Impact: {result.total_impact:+.1f}pts")
        print(f"  Under Boost: +{result.under_boost:.0f}%")
        print(f"  Over Penalty: {-result.over_penalty:.0f}%")
        print(f"  {result.description}")
        print(f"  → {result.recommendation}")

    print()
