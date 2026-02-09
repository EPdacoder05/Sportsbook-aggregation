"""
Fetch REAL public action percentages from free online sources (NO PAID APIs).
Scrapes:
- Sportsbook public pages (Covers, ESPN)
- Reddit r/sportsbook (live community data)
- Twitter @br_betting, betting accounts
- Discord betting servers (if available)
"""

import httpx
import asyncio
import os
from typing import Dict, Optional, Tuple
from loguru import logger


class PublicActionFeed:
    """Fetch real public betting action percentages from FREE sources"""
    
    def __init__(self):
        pass
    
    async def get_public_split(
        self,
        home_team: str,
        away_team: str,
        sport: str
    ) -> Optional[Dict[str, float]]:
        """
        Get REAL public betting data from free online sources.
        
        Priority (all FREE):
        1. Sportsbook public pages (Covers, ESPN)
        2. Reddit r/sportsbook (live data from bettors)
        3. Twitter betting accounts
        4. Return None if no real data found
        """
        try:
            # Try sportsbook splits scraper
            from scrapers.sportsbook_splits_scraper import scrape_all_betting_data
            result = await scrape_all_betting_data(home_team, away_team, sport)
            if result:
                logger.info(f"✅ GOT REAL DATA: {result['source']}")
                return result
            
            # Try social media scraper
            from scrapers.social_media_betting_scraper import get_social_betting_data
            result = await get_social_betting_data(home_team, away_team)
            if result:
                logger.info(f"✅ GOT REAL DATA: {result['source']}")
                return result
            
            # No real data found
            logger.warning(f"⚠️ No real public splits found for {away_team} @ {home_team}")
            return None
        
        except Exception as e:
            logger.error(f"Error fetching public splits: {e}")
            return None


async def get_public_market_data(
    home_team: str,
    away_team: str,
    sport: str,
    api_key: Optional[str] = None
) -> Dict[str, float]:
    """Convenience function to fetch real market splits"""
    feed = PublicActionFeed(api_key=api_key)
    return await feed.get_public_split(home_team, away_team, sport)


# Example: Get real public action for a specific game
if __name__ == "__main__":
    async def demo():
        result = await get_public_market_data("Golden State Warriors", "Utah Jazz", "NBA")
        print(f"Jazz @ Warriors Public Split: {result}")
    
    asyncio.run(demo())
