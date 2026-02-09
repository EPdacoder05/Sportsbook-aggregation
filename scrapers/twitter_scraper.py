"""
Twitter/X Scraper for betting sentiment and whale alerts

Targets:
- @br_betting: Bet percentages, whale alerts, props
- @DKSportsbook: Big bet alerts, liability news
- @ActionNetworkHQ: Sharp money reports
- @PropJoeTV, @drlocks_: Professional bettor insights
"""

from typing import List, Dict, Any, Optional
import tweepy
from datetime import datetime, timedelta
from loguru import logger
from .base_scraper import BaseScraper


class TwitterScraper(BaseScraper):
    """Scrape Twitter/X for betting intelligence"""
    
    def __init__(self, accounts: Optional[List[str]] = None):
        super().__init__()
        
        # Default accounts to monitor
        self.accounts = accounts or [
            "br_betting",
            "ActionNetworkHQ",
            "DKSportsbook",
            "BetMGM",
            "FanDuel",
            "PropJoeTV",
            "drlocks_"
        ]
        
        # Initialize Tweepy client
        self.client = None
        if self.settings.TWITTER_BEARER_TOKEN:
            try:
                self.client = tweepy.Client(
                    bearer_token=self.settings.TWITTER_BEARER_TOKEN,
                    wait_on_rate_limit=True
                )
                logger.info("Twitter API client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Twitter client: {e}")
    
    async def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape recent tweets from betting accounts
        
        Returns:
            List of tweet data with betting information
        """
        if not self.client:
            logger.warning("Twitter client not initialized - check API keys")
            return []
        
        all_tweets = []
        
        for account in self.accounts:
            try:
                tweets = await self.scrape_account(account)
                all_tweets.extend(tweets)
            except Exception as e:
                logger.error(f"Error scraping @{account}: {e}")
                continue
        
        return all_tweets
    
    async def scrape_account(self, username: str) -> List[Dict[str, Any]]:
        """
        Scrape tweets from a specific account
        
        Args:
            username: Twitter username (without @)
            
        Returns:
            List of processed tweet data
        """
        try:
            # Get user ID
            user = self.client.get_user(username=username)
            if not user.data:
                logger.warning(f"User @{username} not found")
                return []
            
            user_id = user.data.id
            
            # Get recent tweets (last 24 hours)
            start_time = datetime.utcnow() - timedelta(days=1)
            
            tweets = self.client.get_users_tweets(
                id=user_id,
                max_results=100,
                start_time=start_time,
                tweet_fields=["created_at", "public_metrics", "entities"],
                exclude=["retweets", "replies"]
            )
            
            if not tweets.data:
                return []
            
            processed_tweets = []
            for tweet in tweets.data:
                processed = self.process_tweet(tweet, username)
                if processed:
                    processed_tweets.append(processed)
            
            logger.info(f"Scraped {len(processed_tweets)} tweets from @{username}")
            return processed_tweets
            
        except Exception as e:
            logger.error(f"Error scraping @{username}: {e}")
            return []
    
    def process_tweet(self, tweet, username: str) -> Optional[Dict[str, Any]]:
        """
        Process tweet to extract betting information
        
        Args:
            tweet: Tweepy tweet object
            username: Account username
            
        Returns:
            Processed tweet data or None if not relevant
        """
        text = tweet.text.lower()
        
        # Check if tweet contains betting-relevant keywords
        keywords = [
            "bet", "odds", "spread", "moneyline", "over", "under",
            "alert", "whale", "sharp", "public", "lock", "pick",
            "$", "money", "handle", "tickets", "%"
        ]
        
        if not any(keyword in text for keyword in keywords):
            return None
        
        return {
            "source": "twitter",
            "account": username,
            "tweet_id": tweet.id,
            "text": tweet.text,
            "created_at": tweet.created_at,
            "likes": tweet.public_metrics.get("like_count", 0),
            "retweets": tweet.public_metrics.get("retweet_count", 0),
            "url": f"https://twitter.com/{username}/status/{tweet.id}",
            # Flags for further processing
            "is_whale_alert": self.is_whale_alert(tweet.text),
            "is_betting_split": self.is_betting_split(tweet.text),
            "is_liability_news": self.is_liability_news(tweet.text),
        }
    
    def is_whale_alert(self, text: str) -> bool:
        """Check if tweet is a whale bet alert"""
        indicators = [
            "big bet alert",
            "whale",
            "bettor placed",
            "$10",
            "$20",
            "$35",
            "$50",
            "$100",
            "k bet",
            "000 on"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in indicators)
    
    def is_betting_split(self, text: str) -> bool:
        """Check if tweet contains betting split data"""
        indicators = [
            "% of bets",
            "% of money",
            "% of tickets",
            "% of handle",
            "ticket%",
            "money%",
            "public betting"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in indicators)
    
    def is_liability_news(self, text: str) -> bool:
        """Check if tweet contains book liability information"""
        indicators = [
            "sportsbook",
            "draftkings lose",
            "fanduel lose",
            "book exposure",
            "liability",
            "million loss",
            "worst case"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in indicators)
    
    async def search_tweets(self, query: str, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Search for tweets matching a query
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of matching tweets
        """
        if not self.client:
            return []
        
        try:
            start_time = datetime.utcnow() - timedelta(hours=24)
            
            tweets = self.client.search_recent_tweets(
                query=query,
                max_results=max_results,
                start_time=start_time,
                tweet_fields=["created_at", "public_metrics", "author_id"]
            )
            
            if not tweets.data:
                return []
            
            results = []
            for tweet in tweets.data:
                results.append({
                    "tweet_id": tweet.id,
                    "text": tweet.text,
                    "created_at": tweet.created_at,
                    "author_id": tweet.author_id,
                    "likes": tweet.public_metrics.get("like_count", 0),
                    "retweets": tweet.public_metrics.get("retweet_count", 0),
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
            return []
