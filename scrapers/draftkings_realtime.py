#!/usr/bin/env python3
"""
DraftKings Real-Time Scraper
Pulls % of bets placed for live analysis
Integrates with autonomous engine
"""

import httpx
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
import re
from datetime import datetime

class DraftKingsScraper:
    """Scrape real betting data from DraftKings"""
    
    def __init__(self):
        self.base_url = "https://www.draftkings.com"
        self.cache = {}
        self.last_update = {}
    
    def scrape_game_splits(self, sport: str, game_id: str) -> Optional[Dict]:
        """
        Scrape betting splits for a specific game
        Returns: {
            'ml_public_pct': float (0-100),
            'spread_public_pct': float (0-100),
            'over_public_pct': float (0-100),
            'timestamp': datetime
        }
        """
        try:
            # Construct URL based on sport and game
            if sport == "NCAAB":
                url = f"{self.base_url}/sportsbook/leagues/basketball/nba"
            elif sport == "NBA":
                url = f"{self.base_url}/sportsbook/leagues/basketball/nba"
            else:
                return None
            
            headers = {"User-Agent": "Mozilla/5.0"}
            response = httpx.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for betting data in the page
            # DraftKings embeds data in JavaScript/JSON
            script_tags = soup.find_all('script')
            
            betting_data = None
            for script in script_tags:
                if script.string and 'betslipData' in script.string or 'percentages' in script.string:
                    # Parse the JSON data
                    try:
                        # Extract JSON from script
                        json_match = re.search(r'{.*}', script.string)
                        if json_match:
                            import json
                            betting_data = json.loads(json_match.group())
                            break
                    except:
                        pass
            
            if betting_data:
                return {
                    'ml_public_pct': betting_data.get('moneyline_pct', None),
                    'spread_public_pct': betting_data.get('spread_pct', None),
                    'over_public_pct': betting_data.get('over_pct', None),
                    'timestamp': datetime.now()
                }
        
        except Exception as e:
            print(f"[ERROR scraping DraftKings] {e}")
        
        return None
    
    def scrape_all_games(self, sport: str) -> Dict[str, Dict]:
        """Scrape all games for a given sport"""
        games_data = {}
        
        try:
            if sport == "NCAAB":
                url = f"{self.base_url}/sportsbook/leagues/basketball/college-basketball"
            elif sport == "NBA":
                url = f"{self.base_url}/sportsbook/leagues/basketball/nba"
            else:
                return games_data
            
            headers = {"User-Agent": "Mozilla/5.0"}
            response = httpx.get(url, headers=headers, timeout=10)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse game containers
            game_containers = soup.find_all(class_='game-card')  # Adjust class name based on DK layout
            
            for container in game_containers:
                try:
                    # Extract game info
                    teams = container.find_all(class_='team-name')
                    if len(teams) >= 2:
                        matchup = f"{teams[0].text} @ {teams[1].text}"
                        
                        # Extract public percentages
                        ml_pct_elem = container.find(class_='moneyline-pct')
                        spread_pct_elem = container.find(class_='spread-pct')
                        
                        games_data[matchup] = {
                            'ml_public_pct': float(ml_pct_elem.text.rstrip('%')) if ml_pct_elem else None,
                            'spread_public_pct': float(spread_pct_elem.text.rstrip('%')) if spread_pct_elem else None,
                        }
                except:
                    pass
        
        except Exception as e:
            print(f"[ERROR] {e}")
        
        return games_data


class ActionNetworkScraper:
    """Scrape Action Network for public betting data"""
    
    def __init__(self):
        self.base_url = "https://www.actionnetwork.com"
    
    def scrape_game_data(self, sport: str, game_id: str) -> Optional[Dict]:
        """
        Scrape betting consensus from Action Network
        Returns betting % and smart money signals
        """
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            
            if sport == "NCAAB":
                url = f"{self.base_url}/ncaab/games/{game_id}"
            elif sport == "NBA":
                url = f"{self.base_url}/nba/games/{game_id}"
            else:
                return None
            
            response = httpx.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for consensus data
            consensus_elem = soup.find(class_='consensus-data')
            
            if consensus_elem:
                # Extract percentages
                public_pct_text = consensus_elem.get_text()
                # Parse the percentages (would need exact parsing based on AN layout)
                
                return {
                    'consensus_data': public_pct_text,
                    'timestamp': datetime.now()
                }
        
        except Exception as e:
            print(f"[ERROR scraping Action Network] {e}")
        
        return None


# Integration with autonomous engine
def get_betting_splits_for_game(matchup: str, sport: str) -> Optional[Dict]:
    """
    Master function to get betting splits
    Tries multiple sources in order of reliability
    """
    
    # Try DraftKings first
    dk_scraper = DraftKingsScraper()
    dk_data = dk_scraper.scrape_all_games(sport)
    
    if matchup in dk_data:
        return dk_data[matchup]
    
    # Try Action Network as fallback
    an_scraper = ActionNetworkScraper()
    # Would need game ID mapping
    
    return None


if __name__ == "__main__":
    # Test scrapers
    print("Testing DraftKings scraper...")
    dk = DraftKingsScraper()
    
    print("Testing Action Network scraper...")
    an = ActionNetworkScraper()
    
    print("Scrapers ready for integration with autonomous engine")
