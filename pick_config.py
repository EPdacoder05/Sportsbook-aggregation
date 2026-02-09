#!/usr/bin/env python
"""
Pick Configuration Manager
Load/save picks from JSON config file
"""

import json
import os
from datetime import datetime
from typing import Dict


class PickConfig:
    """Manage pick configuration"""
    
    def __init__(self, config_file: str = None):
        self.config_file = config_file or "picks_config.json"
        self.picks = self.load()
    
    def load(self) -> Dict:
        """Load picks from config file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"ERROR loading config: {e}")
                return self.default_picks()
        else:
            # Create default config
            self.save(self.default_picks())
            return self.default_picks()
    
    def save(self, picks: Dict = None):
        """Save picks to config file"""
        if picks is None:
            picks = self.picks
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(picks, f, indent=2)
            print(f"Saved picks to {self.config_file}")
        except Exception as e:
            print(f"ERROR saving config: {e}")
    
    def add_pick(self, pick_key: str, pick_data: Dict):
        """Add a new pick"""
        self.picks[pick_key] = pick_data
        self.save()
    
    def remove_pick(self, pick_key: str):
        """Remove a pick"""
        if pick_key in self.picks:
            del self.picks[pick_key]
            self.save()
    
    def update_pick(self, pick_key: str, updates: Dict):
        """Update pick details"""
        if pick_key in self.picks:
            self.picks[pick_key].update(updates)
            self.save()
    
    def get_active_picks(self):
        """Get only picks we're betting on (not just monitoring)"""
        return {k: v for k, v in self.picks.items() if v.get('bet') is not None}
    
    @staticmethod
    def default_picks() -> Dict:
        """Default configuration"""
        return {
            "cincinnati-ucf": {
                "away": "Cincinnati Bearcats",
                "home": "UCF Knights",
                "spread": 2.5,
                "bet": "Cincinnati",
                "status": "ACTIVE",
                "reason": "Line divergence: moved from -3.5 to +2.5 toward dog, public 88% UCF",
                "unit_size": 100,
                "added": datetime.now().isoformat()
            },
            "knicks-trail": {
                "away": "Knicks",
                "home": "Trail Blazers",
                "spread": -4.5,
                "bet": "Trail Blazers",
                "status": "ACTIVE",
                "reason": "Whale money: line moved -5.5, public 50-50 split",
                "unit_size": 100,
                "added": datetime.now().isoformat()
            },
            "raptors-76ers": {
                "away": "76ers",
                "home": "Raptors",
                "spread": 1.5,
                "bet": "Raptors",
                "status": "ACTIVE",
                "reason": "Line moved from -3.5 to -2 (toward dog), public 66% PHI",
                "unit_size": 100,
                "added": datetime.now().isoformat()
            },
            "ohio-state-washington": {
                "away": "Ohio State",
                "home": "Washington",
                "spread": -1.5,
                "bet": None,
                "status": "MONITORING",
                "reason": "Watching for divergence signals",
                "unit_size": 0,
                "added": datetime.now().isoformat()
            },
            "memphis-uab": {
                "away": "Memphis",
                "home": "UAB",
                "spread": None,
                "bet": None,
                "status": "MONITORING",
                "reason": "Monitoring live action",
                "unit_size": 0,
                "added": datetime.now().isoformat()
            }
        }


def main():
    """Test configuration"""
    
    config = PickConfig("picks_config.json")
    
    print("[PICK CONFIGURATION MANAGER]\n")
    
    print("Current picks:")
    print("-" * 80)
    
    for key, pick in config.picks.items():
        bet_str = f"{pick.get('bet')}" if pick.get('bet') else "(monitoring)"
        spread_str = f"{pick.get('spread'):+.1f}" if pick.get('spread') else "N/A"
        
        print(f"\n  {key}")
        print(f"    Bet: {bet_str:20s} Spread: {spread_str:>6s}")
        print(f"    Status: {pick.get('status', 'UNKNOWN')}")
        if pick.get('reason'):
            print(f"    Reason: {pick['reason'][:60]}")
    
    print("\n" + "-" * 80)
    print(f"Active bets: {len(config.get_active_picks())} / {len(config.picks)} total")


if __name__ == "__main__":
    main()
