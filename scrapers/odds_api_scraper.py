"""
The Odds API Scraper

Provides:
- Live odds from 40+ sportsbooks
- Line movement tracking
- Historical odds data
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
from .base_scraper import BaseScraper


class OddsAPIScraper(BaseScraper):
    """Scrape odds data from The Odds API"""
    
    def __init__(self, sport: str = "americanfootball_nfl"):
        super().__init__()
        self.sport = sport
        self.base_url = self.settings.ODDS_API_BASE
        self.api_key = self.settings.ODDS_API_KEY
        
    async def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape current odds for sport
        
        Returns:
            List of game odds
        """
        if not self.api_key:
            logger.warning("Odds API key not configured")
            return []
        
        url = f"{self.base_url}/sports/{self.sport}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american"
        }
        
        try:
            response = await self.fetch(url, params=params)
            games = response.json()
            
            processed_games = []
            for game in games:
                processed = self.process_game(game)
                if processed:
                    processed_games.append(processed)
            
            logger.info(f"Scraped odds for {len(processed_games)} games")
            return processed_games
            
        except Exception as e:
            logger.error(f"Error scraping odds: {e}")
            return []
    
    def process_game(self, game_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process game odds data
        
        Args:
            game_data: Raw game data from API
            
        Returns:
            Processed game data
        """
        try:
            # Extract basic info
            home_team = game_data.get("home_team")
            away_team = game_data.get("away_team")
            commence_time = datetime.fromisoformat(
                game_data["commence_time"].replace("Z", "+00:00")
            )
            
            # Extract bookmaker odds
            bookmakers = game_data.get("bookmakers", [])
            
            odds_by_book = []
            for bookmaker in bookmakers:
                book_odds = self.extract_bookmaker_odds(bookmaker)
                if book_odds:
                    odds_by_book.append(book_odds)
            
            return {
                "sport": self.sport,
                "home_team": home_team,
                "away_team": away_team,
                "game_time": commence_time,
                "odds_by_bookmaker": odds_by_book,
                "scraped_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error processing game: {e}")
            return None
    
    def extract_bookmaker_odds(self, bookmaker: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract odds from bookmaker data
        
        Args:
            bookmaker: Bookmaker data
            
        Returns:
            Processed odds data
        """
        try:
            book_name = bookmaker.get("title")
            markets = bookmaker.get("markets", [])
            
            odds = {
                "sportsbook": book_name,
                "moneyline": {},
                "spread": {},
                "totals": {}
            }
            
            for market in markets:
                market_key = market.get("key")
                outcomes = market.get("outcomes", [])
                
                if market_key == "h2h":  # Moneyline
                    for outcome in outcomes:
                        team = outcome.get("name")
                        price = outcome.get("price")
                        odds["moneyline"][team] = price
                        
                elif market_key == "spreads":  # Spread
                    for outcome in outcomes:
                        team = outcome.get("name")
                        point = outcome.get("point")
                        price = outcome.get("price")
                        odds["spread"][team] = {
                            "line": point,
                            "odds": price
                        }
                        
                elif market_key == "totals":  # Over/Under
                    for outcome in outcomes:
                        name = outcome.get("name")  # "Over" or "Under"
                        point = outcome.get("point")
                        price = outcome.get("price")
                        odds["totals"][name.lower()] = {
                            "line": point,
                            "odds": price
                        }
            
            return odds
            
        except Exception as e:
            logger.error(f"Error extracting bookmaker odds: {e}")
            return None
    
    async def get_sports_list(self) -> List[Dict[str, Any]]:
        """
        Get list of available sports
        
        Returns:
            List of sports
        """
        url = f"{self.base_url}/sports"
        params = {"apiKey": self.api_key}
        
        try:
            response = await self.fetch(url, params=params)
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching sports list: {e}")
            return []
    
    async def get_historical_odds(
        self,
        sport: str,
        event_id: str,
        date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get historical odds for specific event
        
        Args:
            sport: Sport key
            event_id: Event ID
            date: ISO date string
            
        Returns:
            Historical odds data
        """
        url = f"{self.base_url}/sports/{sport}/odds-history"
        params = {
            "apiKey": self.api_key,
            "eventIds": event_id,
            "date": date,
            "regions": "us",
            "markets": "h2h,spreads,totals"
        }
        
        try:
            response = await self.fetch(url, params=params)
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching historical odds: {e}")
            return None
