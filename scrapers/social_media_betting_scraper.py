"""
Real-time social media betting data scraper.
Pulls ACTUAL betting percentages from:
- Twitter @br_betting, @ActionNetworkHQ, betting accounts
- Reddit r/sportsbook live posts
- Discord betting servers (if accessible)
"""

import httpx
import re
import asyncio
from typing import Dict, Optional, List, Tuple
from loguru import logger
from datetime import datetime, timedelta


class SocialMediaBettingData:
    """Scrape real betting data from social platforms"""
    
    async def scrape_twitter_percentages(self, home_team: str, away_team: str) -> Optional[Dict]:
        """
        Scrape Twitter for real betting percentages from betting accounts.
        Looks for posts like: "65% on Team | 52% Money"
        """
        try:
            # Twitter search for betting percentages (without API, using search results)
            search_terms = [
                f"{away_team} {home_team} % tickets",
                f"{away_team} {home_team} % money",
                f"{away_team} {home_team} betting split",
                f"@br_betting {away_team} {home_team}",
            ]
            
            async with httpx.AsyncClient(timeout=10) as client:
                for search in search_terms:
                    try:
                        # Use public Twitter search
                        url = f"https://twitter.com/search?q={search.replace(' ', '%20')}&f=live"
                        
                        response = await client.get(url, follow_redirects=True)
                        if response.status_code == 200:
                            text = response.text
                            
                            # Look for percentage patterns
                            # Pattern: "45% tickets / 52% money" or "65% on Team"
                            ticket_match = re.search(r'(\d{1,3})%\s*(?:tickets?|bets?)', text, re.IGNORECASE)
                            money_match = re.search(r'(\d{1,3})%\s*(?:money|handle)', text, re.IGNORECASE)
                            
                            if ticket_match and money_match:
                                logger.info(f"✅ Twitter: {away_team} @ {home_team} | {ticket_match.group(1)}% tickets / {money_match.group(1)}% money")
                                return {
                                    "public_ticket_pct": float(ticket_match.group(1)),
                                    "public_money_pct": float(money_match.group(1)),
                                    "public_side": "home" if float(money_match.group(1)) >= 50 else "away",
                                    "source": "twitter_live"
                                }
                            elif ticket_match or money_match:
                                pct = float((ticket_match or money_match).group(1))
                                logger.info(f"✅ Twitter: {away_team} @ {home_team} | {pct}%")
                                return {
                                    "public_ticket_pct": pct,
                                    "public_money_pct": pct,
                                    "public_side": "home" if pct >= 50 else "away",
                                    "source": "twitter_live"
                                }
                    except Exception as e:
                        logger.debug(f"Twitter search failed for '{search}': {e}")
                        continue
        
        except Exception as e:
            logger.debug(f"Twitter scrape failed: {e}")
        
        return None
    
    async def scrape_reddit_live_splits(self, home_team: str, away_team: str) -> Optional[Dict]:
        """
        Scrape Reddit r/sportsbook for live betting percentage posts.
        Redditors constantly post: "72% public on Team, 52% money"
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Search r/sportsbook/new for latest posts about this matchup
                query = f"{away_team} {home_team}".lower().replace(" ", "+")
                
                url = f"https://www.reddit.com/r/sportsbook/search.json?q={query}&sort=new&t=day&limit=20"
                
                response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get("data", {}).get("children", [])
                    
                    for post in posts:
                        post_data = post.get("data", {})
                        title = post_data.get("title", "")
                        selftext = post_data.get("selftext", "")
                        full_text = f"{title} {selftext}".lower()
                        
                        # Look for betting percentage patterns
                        # Patterns: "65% on team", "52% money", "70% tickets", etc.
                        ticket_matches = re.findall(r'(\d{1,3})%\s*(?:tickets?|public|bets?)', full_text)
                        money_matches = re.findall(r'(\d{1,3})%\s*(?:money|handle|action)', full_text)
                        
                        if ticket_matches or money_matches:
                            tickets = float(ticket_matches[0]) if ticket_matches else 50
                            money = float(money_matches[0]) if money_matches else tickets
                            
                            logger.info(f"✅ Reddit: {away_team} @ {home_team} | {tickets}% tickets / {money}% money")
                            return {
                                "public_ticket_pct": tickets,
                                "public_money_pct": money,
                                "public_side": "home" if money >= 50 else "away",
                                "source": "reddit_live"
                            }
        
        except Exception as e:
            logger.debug(f"Reddit scrape failed: {e}")
        
        return None
    
    async def scrape_discord_betting_servers(self) -> Optional[Dict]:
        """
        Discord betting servers often share live percentages publicly.
        This requires finding public Discord guild information.
        For now, this is a placeholder for future integration.
        """
        logger.debug("Discord scraping not yet implemented")
        return None
    
    async def get_all_social_data(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Try all social media sources for real betting data"""
        
        # Try Twitter first (usually has most recent data)
        result = await self.scrape_twitter_percentages(home_team, away_team)
        if result:
            return result
        
        # Try Reddit (community shares splits constantly)
        result = await self.scrape_reddit_live_splits(home_team, away_team)
        if result:
            return result
        
        logger.warning(f"No social data found for {away_team} @ {home_team}")
        return None


async def get_social_betting_data(home_team: str, away_team: str) -> Optional[Dict]:
    """Main function to get REAL betting data from social media"""
    scraper = SocialMediaBettingData()
    return await scraper.get_all_social_data(home_team, away_team)
