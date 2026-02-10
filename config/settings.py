"""Configuration settings for HOUSE EDGE system"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Optional, Union
from functools import lru_cache
import os
from pathlib import Path


class Settings(BaseSettings):
    """Main application settings"""
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/house_edge"
    
    # Twitter/X API
    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_ACCESS_TOKEN: str = ""
    TWITTER_ACCESS_SECRET: str = ""
    TWITTER_BEARER_TOKEN: str = ""
    
    # Grok API (xAI)
    GROK_API_KEY: str = ""
    GROK_API_BASE: str = "https://api.x.ai/v1"
    
    # The Odds API
    ODDS_API_KEY: str = ""
    ODDS_API_BASE: str = "https://api.the-odds-api.com/v4"

    @property
    def odds_api_key(self) -> str:
        """Alias for ODDS_API_KEY to match lower-case access attempts."""
        return self.ODDS_API_KEY
    
    # Instagram
    INSTAGRAM_USERNAME: Optional[str] = None
    INSTAGRAM_PASSWORD: Optional[str] = None
    
    # Reddit API
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "house-edge-bot/1.0"
    
    # Google Cloud Vision (OCR)
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    
    # Discord
    DISCORD_WEBHOOK_URL: str = ""
    DISCORD_HIGH_ALERT_WEBHOOK: str = ""
    
    # SendGrid (Email)
    SENDGRID_API_KEY: str = ""
    ALERT_EMAIL_FROM: str = "alerts@houseedge.ai"
    ALERT_EMAIL_TO: str = ""
    
    # Application Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    
    # Scraping Settings
    SCRAPE_INTERVAL_MINUTES: int = 5
    WHALE_BET_THRESHOLD: int = 10000  # $10,000 minimum
    EXTREME_PUBLIC_THRESHOLD: int = 85  # 85%+ triggers nuclear fade
    
    # Alert Thresholds
    MIN_FADE_SCORE: int = 65  # Minimum to trigger alert
    HIGH_PRIORITY_FADE_SCORE: int = 80  # High priority threshold
    
    # Sports Priority
    PRIORITY_SPORTS: List[str] = ["NFL", "NBA", "SOCCER"]
    
    # User Agents for scraping
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
