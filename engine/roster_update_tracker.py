#!/usr/bin/env python3
"""
ROSTER UPDATE TRACKER — Trade Deadline & Roster Changes
=========================================================
Feb 12, 2026: James Harden traded to CLE. Your STAR_IMPACT database is outdated.

Problem:
  - STAR_IMPACT has hardcoded teams from start of season
  - Trade deadline (Feb 6) moved multiple stars
  - Star absence detector checks wrong teams
  - System doesn't know Harden is on CLE now

Solution:
  - Fetch live rosters from ESPN API (free, no credits)
  - Build player_name -> current_team mapping
  - Compare against STAR_IMPACT teams
  - Auto-update during trade deadline period (Feb 1-15)
  - Log all roster changes for audit trail

Usage:
    from engine.roster_update_tracker import RosterUpdateTracker
    
    tracker = RosterUpdateTracker()
    
    # Fetch current rosters and update STAR_IMPACT
    changes = tracker.sync_star_rosters()
    
    # Check if we're in trade deadline period
    if tracker.is_trade_deadline_period():
        tracker.sync_star_rosters()
    
    # Get current team for any player
    team = tracker.get_current_team("James Harden")  # Returns "CLE"
"""

import json
import logging
import requests
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
ROSTER_CACHE_FILE = DATA_DIR / "nba_rosters.json"

# ESPN Team IDs (same as star_absence_detector.py)
ESPN_TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 17, "CHA": 30, "CHI": 4, "CLE": 5,
    "DAL": 6, "DEN": 7, "DET": 8, "GS": 9, "HOU": 10, "IND": 11,
    "LAC": 12, "LAL": 13, "MEM": 29, "MIA": 14, "MIL": 15, "MIN": 16,
    "NO": 3, "NY": 18, "OKC": 25, "ORL": 19, "PHI": 20, "PHX": 21,
    "POR": 22, "SAC": 23, "SA": 24, "TOR": 28, "UTA": 26, "WAS": 27,
}

# Reverse mapping
TEAM_ID_TO_ABBR = {v: k for k, v in ESPN_TEAM_IDS.items()}


@dataclass
class RosterChange:
    """A single roster change (trade, signing, etc.)"""
    player_name: str
    old_team: Optional[str]
    new_team: str
    detected_at: str
    change_type: str = "TRADE"  # TRADE, SIGNING, WAIVE


class RosterUpdateTracker:
    """
    Tracks NBA roster changes and syncs with STAR_IMPACT database.
    
    Automatically updates during trade deadline period (Feb 1-15).
    """

    def __init__(self, cache_file: Optional[Path] = None):
        self.cache_file = cache_file or ROSTER_CACHE_FILE
        self.player_to_team: Dict[str, str] = {}
        self.last_sync: Optional[datetime] = None
        self.roster_changes: List[RosterChange] = []
        self._load_cache()

    def _load_cache(self):
        """Load cached roster data from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    data = json.load(f)
                self.player_to_team = data.get("player_to_team", {})
                self.last_sync = datetime.fromisoformat(data["last_sync"]) if data.get("last_sync") else None
                logger.info(f"Loaded roster cache from {self.last_sync}")
            except Exception as e:
                logger.error(f"Failed to load roster cache: {e}")

    def _save_cache(self):
        """Save roster data to disk."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "player_to_team": self.player_to_team,
            "last_sync": datetime.now().isoformat(),
            "total_players": len(self.player_to_team),
        }
        with open(self.cache_file, "w") as f:
            json.dump(data, f, indent=2)

    def is_trade_deadline_period(self, today: Optional[date] = None) -> bool:
        """
        Check if we're in NBA trade deadline period.
        
        NBA trade deadline is typically first Thursday in February.
        We monitor Feb 1-15 to catch all trades around deadline day.
        """
        today = today or date.today()
        return today.month == 2 and 1 <= today.day <= 15

    def fetch_team_roster(self, team_abbr: str) -> List[Dict]:
        """
        Fetch roster for a single team from ESPN API.
        
        Args:
            team_abbr: "CLE", "LAL", etc.
        
        Returns:
            List of player dicts with name, position, jersey
        """
        team_id = ESPN_TEAM_IDS.get(team_abbr.upper())
        if not team_id:
            logger.warning(f"Unknown team abbreviation: {team_abbr}")
            return []

        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
        
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            players = []
            for athlete in data.get("athletes", []):
                full_name = athlete.get("fullName", "")
                display_name = athlete.get("displayName", "")
                name = display_name or full_name
                
                if name:
                    players.append({
                        "name": name,
                        "full_name": full_name,
                        "position": athlete.get("position", {}).get("abbreviation", ""),
                        "jersey": athlete.get("jersey", ""),
                    })
            
            return players
        
        except Exception as e:
            logger.error(f"Failed to fetch roster for {team_abbr}: {e}")
            return []

    def fetch_all_rosters(self) -> Dict[str, List[str]]:
        """
        Fetch rosters for all 30 NBA teams.
        
        Returns:
            Dict mapping team_abbr -> list of player names
        """
        all_rosters = {}
        
        for team_abbr in ESPN_TEAM_IDS.keys():
            players = self.fetch_team_roster(team_abbr)
            all_rosters[team_abbr] = [p["name"] for p in players]
            logger.info(f"Fetched {len(players)} players for {team_abbr}")
        
        return all_rosters

    def build_player_team_mapping(self, rosters: Dict[str, List[str]]) -> Dict[str, str]:
        """
        Build player_name -> team_abbr mapping from roster data.
        
        Args:
            rosters: Dict of team -> [player_names]
        
        Returns:
            Dict of player_name -> team_abbr
        """
        mapping = {}
        
        for team, players in rosters.items():
            for player_name in players:
                # Normalize name (remove suffixes like Jr., III)
                normalized = player_name.replace(" Jr.", "").replace(" III", "").replace(" II", "")
                mapping[normalized] = team
                mapping[player_name] = team  # Also store original
        
        return mapping

    def sync_star_rosters(self, force: bool = False) -> List[RosterChange]:
        """
        Sync STAR_IMPACT database with current NBA rosters.
        
        Fetches live rosters, compares with cached data, and detects changes.
        
        Args:
            force: Force sync even if not in trade deadline period
        
        Returns:
            List of RosterChange objects for detected changes
        """
        # Only auto-sync during trade deadline unless forced
        if not force and not self.is_trade_deadline_period():
            logger.info("Not in trade deadline period — skipping roster sync (use force=True to override)")
            return []

        logger.info("Syncing star rosters from ESPN...")
        
        # Fetch current rosters
        rosters = self.fetch_all_rosters()
        new_mapping = self.build_player_team_mapping(rosters)
        
        # Detect changes from cached data
        changes = []
        from engine.star_absence_detector import STAR_IMPACT
        
        for player_name, star_data in STAR_IMPACT.items():
            cached_team = star_data["team"]
            
            # Check if player is on a different team now
            current_team = self._find_player_team(player_name, new_mapping)
            
            if current_team and current_team != cached_team:
                change = RosterChange(
                    player_name=player_name,
                    old_team=cached_team,
                    new_team=current_team,
                    detected_at=datetime.now().isoformat(),
                    change_type="TRADE",
                )
                changes.append(change)
                logger.warning(f"ROSTER CHANGE: {player_name} {cached_team} → {current_team}")
        
        # Update cache
        self.player_to_team = new_mapping
        self.last_sync = datetime.now()
        self.roster_changes.extend(changes)
        self._save_cache()
        
        return changes

    def _find_player_team(self, player_name: str, mapping: Dict[str, str]) -> Optional[str]:
        """
        Find current team for a player, handling name variations.
        
        Args:
            player_name: "Shai Gilgeous-Alexander", "Luka Doncic", etc.
            mapping: Current player -> team mapping
        
        Returns:
            Team abbreviation or None if not found
        """
        # Direct match
        if player_name in mapping:
            return mapping[player_name]
        
        # Try without suffixes
        normalized = player_name.replace(" Jr.", "").replace(" III", "").replace(" II", "")
        if normalized in mapping:
            return mapping[normalized]
        
        # Try fuzzy match (last name only)
        last_name = player_name.split()[-1]
        for roster_name, team in mapping.items():
            if last_name.lower() in roster_name.lower():
                return team
        
        return None

    def get_current_team(self, player_name: str) -> Optional[str]:
        """
        Get current team for a player.
        
        Args:
            player_name: Player's name
        
        Returns:
            Team abbreviation or None if not found
        """
        return self._find_player_team(player_name, self.player_to_team)

    def get_updated_star_impact(self) -> Dict:
        """
        Get STAR_IMPACT dictionary with updated team assignments.
        
        Returns:
            Updated STAR_IMPACT dict with current teams
        """
        from engine.star_absence_detector import STAR_IMPACT
        
        updated = {}
        for player_name, star_data in STAR_IMPACT.items():
            current_team = self.get_current_team(player_name)
            
            updated[player_name] = {
                **star_data,
                "team": current_team or star_data["team"],  # Fallback to original if not found
                "team_updated": current_team is not None and current_team != star_data["team"],
            }
        
        return updated

    def print_roster_report(self):
        """Print a summary of detected roster changes."""
        if not self.roster_changes:
            print("  No roster changes detected")
            return
        
        print("\n" + "═" * 72)
        print("  🔄 ROSTER CHANGES DETECTED")
        print("═" * 72)
        
        for change in self.roster_changes:
            print(f"  {change.player_name}: {change.old_team} → {change.new_team}")
            print(f"    Detected: {change.detected_at}")
            print(f"    Type: {change.change_type}")
        
        print("═" * 72)

    def get_trade_deadline_date(self, year: int = 2026) -> date:
        """
        Get the NBA trade deadline date for a given year.
        
        NBA trade deadline is typically the first Thursday in February.
        """
        # Simplified: assume Feb 6, 2026 for this season
        return date(year, 2, 6)


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 72)
    print("  ROSTER UPDATE TRACKER — Testing")
    print("═" * 72)

    tracker = RosterUpdateTracker()
    
    print(f"\n  Trade deadline period: {tracker.is_trade_deadline_period()}")
    print(f"  Last sync: {tracker.last_sync or 'Never'}")
    
    # Test: Find James Harden's current team
    print("\n  Testing player lookups:")
    test_players = [
        "James Harden",
        "Shai Gilgeous-Alexander",
        "Giannis Antetokounmpo",
        "Stephen Curry",
        "Luka Doncic",
    ]
    
    for player in test_players:
        team = tracker.get_current_team(player)
        print(f"    {player}: {team or 'NOT FOUND'}")
    
    # Force sync
    print("\n  Force syncing rosters from ESPN...")
    changes = tracker.sync_star_rosters(force=True)
    
    if changes:
        print(f"\n  Detected {len(changes)} roster changes:")
        for change in changes:
            print(f"    {change.player_name}: {change.old_team} → {change.new_team}")
    else:
        print("\n  No roster changes detected")
    
    print("\n  Updated STAR_IMPACT teams:")
    updated = tracker.get_updated_star_impact()
    for player, data in list(updated.items())[:5]:
        status = "✅ UPDATED" if data.get("team_updated") else "   (no change)"
        print(f"    {player}: {data['team']} {status}")
    
    print()
