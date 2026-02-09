#!/usr/bin/env python
"""
NEW PICK GENERATOR - Shows only UPCOMING opportunities
- Analyzes pre-game lines for NEW games only
- Skips games already started
- Quality over quantity approach
"""

import sys
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, r"c:\Users\epina\Devenvfoldher\Sportsbook-aggregation")
from live_score_service import LiveScoreService


class PickGenerator:
    """Generate picks for UPCOMING games only"""
    
    def __init__(self):
        self.service = LiveScoreService()
    
    def find_upcoming_games(self) -> Dict[str, List]:
        """Find games that haven't started yet"""
        
        all_games = self.service.fetch_all_games()
        upcoming = {}
        
        for sport, games in all_games.items():
            upcoming_in_sport = []
            for game in games:
                # Only include scheduled games (not live or final)
                if game.status in ['Scheduled', 'Pre-Game', 'Not Started']:
                    upcoming_in_sport.append(game)
            
            if upcoming_in_sport:
                upcoming[sport] = upcoming_in_sport
        
        return upcoming
    
    def generate_picks(self):
        """Generate picks for upcoming games"""
        
        print("\n" + "=" * 80)
        print("NEW PICK OPPORTUNITIES")
        print(f"Generated: {datetime.now().strftime('%I:%M %p')}")
        print("=" * 80)
        print()
        
        upcoming = self.find_upcoming_games()
        
        if not upcoming:
            print("⚠️  NO UPCOMING GAMES FOUND")
            print()
            print("All games are either:")
            print("  - Already live (too late to bet pre-game lines)")
            print("  - Already final")
            print("  - Not scheduled yet")
            print()
            print("RECOMMENDATIONS:")
            print("  1. Monitor LIVE games for hedge opportunities")
            print("  2. Wait for tomorrow's slate")
            print("  3. Check back in 30 minutes")
            return
        
        for sport, games in upcoming.items():
            print(f"[{sport}] UPCOMING GAMES:")
            print("-" * 80)
            
            for game in games:
                print(f"  {game.away_team} @ {game.home_team}")
                print(f"  Status: {game.status}")
                print()
                print("  TO ANALYZE THIS GAME:")
                print("    1. Get opening line + current line")
                print("    2. Check public % (Covers.com, Twitter)")
                print("    3. Look for 3+ point line movement")
                print("    4. Verify divergence (line moves away from public)")
                print()
        
        print("=" * 80)
        print("NEXT STEPS:")
        print("  1. Manually check lines for games above")
        print("  2. Use covers.com for public %")
        print("  3. Only bet if clear RLM (3+ pts, 70%+ public)")
        print("=" * 80)


if __name__ == "__main__":
    generator = PickGenerator()
    generator.generate_picks()
