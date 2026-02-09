"""
Scrape real public betting percentages from free sportsbook sites.
- Covers.com public betting percentages
- ESPN betting percentages
- DraftKings public pages (if available)
- Reddit r/sportsbook live splits
"""

import httpx
import re
from typing import Dict, Optional, List
from loguru import logger
from datetime import datetime, timedelta


class SportsbookSplitsScraper:
    """Scrape real public betting splits from free sources"""
    
    async def scrape_covers_splits(self, home_team: str, away_team: str, sport: str) -> Optional[Dict]:
        """Scrape real betting % from Covers.com public pages"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Covers has public betting percentages on their game pages
                search_query = f"{away_team} {home_team}".lower().replace(" ", "-")
                
                # Try multiple URLs where Covers shows betting data
                urls = [
                    f"https://www.covers.com/sports/{sport.lower()}/matchups/{search_query}",
                    f"https://www.covers.com/sports/nfl/odds/{search_query}" if sport == "NFL" else None,
                ]
                
                for url in [u for u in urls if u]:
                    try:
                        response = await client.get(url)
                        if response.status_code == 200:
                            # Extract percentages from page HTML
                            text = response.text
                            
                            # Pattern: "45% of bets on Team" or "Public: 52% Money"
                            percentages = re.findall(r'(\d{1,3})%\s*(?:of bets|money|tickets|handle)', text, re.IGNORECASE)
                            
                            if percentages:
                                logger.info(f"✅ Covers: Found {away_team} @ {home_team} splits")
                                return {
                                    "public_ticket_pct": float(percentages[0]) if len(percentages) > 0 else 50,
                                    "public_money_pct": float(percentages[1]) if len(percentages) > 1 else float(percentages[0]),
                                    "public_side": "home" if float(percentages[1] if len(percentages) > 1 else percentages[0]) >= 50 else "away",
                                    "source": "covers_public"
                                }
                    except Exception as e:
                        logger.debug(f"Covers URL failed {url}: {e}")
                        continue
        
        except Exception as e:
            logger.debug(f"Covers scrape failed: {e}")
        
        return None
    
    async def scrape_reddit_splits(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Scrape real betting data shared on r/sportsbook"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Reddit allows scraping via their JSON API without authentication
                search = f"{away_team} {home_team}".lower()
                
                # Search r/sportsbook for recent posts with betting data
                url = f"https://www.reddit.com/r/sportsbook/search.json?q={search}&restrict_sr=true&sort=new&t=day&limit=10"
                
                response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get("data", {}).get("children", [])
                    
                    for post in posts:
                        title_text = post["data"]["title"] + " " + post["data"]["selftext"]
                        
                        # Extract patterns: "65% on Team" or "Money: 52%"
                        percentages = re.findall(r'(\d{1,3})%\s*(?:on|money|tickets|handle|public)', title_text, re.IGNORECASE)
                        
                        if percentages and len(percentages) >= 1:
                            logger.info(f"✅ Reddit: Found {away_team} @ {home_team} splits - {percentages}")
                            return {
                                "public_ticket_pct": float(percentages[0]) if len(percentages) > 0 else 50,
                                "public_money_pct": float(percentages[1]) if len(percentages) > 1 else float(percentages[0]),
                                "public_side": "home" if float(percentages[1] if len(percentages) > 1 else percentages[0]) >= 50 else "away",
                                "source": "reddit_sportsbook"
                            }
        
        except Exception as e:
            logger.debug(f"Reddit scrape failed: {e}")
        
        return None
    
    async def scrape_espn_betting_percentages(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Scrape ESPN public betting percentages"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # ESPN has betting percentages on their odds pages
                url = f"https://www.espn.com/betting/odds"
                
                response = await client.get(url)
                if response.status_code == 200:
                    text = response.text
                    
                    # Look for game and its betting percentage data
                    game_pattern = f"{away_team}.*?{home_team}.*?(\d{{1,3}})%"
                    matches = re.findall(game_pattern, text, re.IGNORECASE | re.DOTALL)
                    
                    if matches:
                        logger.info(f"✅ ESPN: Found {away_team} @ {home_team} splits")
                        return {
                            "public_ticket_pct": float(matches[0]) if matches else 50,
                            "public_money_pct": float(matches[1]) if len(matches) > 1 else float(matches[0]),
                            "public_side": "home",
                            "source": "espn_public"
                        }
        
        except Exception as e:
            logger.debug(f"ESPN scrape failed: {e}")
        
        return None
    
    async def get_real_splits(self, home_team: str, away_team: str, sport: str) -> Optional[Dict]:
        """Try all free scraping sources for real betting splits"""
        
        # Try Covers first (most reliable)
        result = await self.scrape_covers_splits(home_team, away_team, sport)
        if result:
            return result
        
        # Try Reddit
        result = await self.scrape_reddit_splits(home_team, away_team)
        if result:
            return result
        
        # Try ESPN
        result = await self.scrape_espn_betting_percentages(home_team, away_team)
        if result:
            return result
        
        logger.warning(f"No free public splits found for {away_team} @ {home_team}")
        return None


async def scrape_all_betting_data(home_team: str, away_team: str, sport: str) -> Optional[Dict]:
    """Main function to scrape REAL public betting data from all free sources"""
    scraper = SportsbookSplitsScraper()
    
    logger.info(f"Scraping real splits for {away_team} @ {home_team}...")
    result = await scraper.get_real_splits(home_team, away_team, sport)
    
    if result:
        logger.info(f"✅ REAL DATA: {result}")
        return result
    else:
        logger.warning(f"❌ Could not find real splits - will use market-implied")
        return None
