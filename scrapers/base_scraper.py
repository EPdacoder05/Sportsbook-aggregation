"""Base scraper class with common functionality"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings


class BaseScraper(ABC):
    """Abstract base class for all scrapers"""
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": self.settings.USER_AGENT},
            follow_redirects=True
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def fetch(self, url: str, **kwargs) -> httpx.Response:
        """
        Fetch URL with retry logic
        
        Args:
            url: URL to fetch
            **kwargs: Additional httpx request parameters
            
        Returns:
            httpx.Response object
        """
        if not self.client:
            raise RuntimeError("Scraper must be used as async context manager")
            
        try:
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """
        POST request with retry logic
        
        Args:
            url: URL to post to
            **kwargs: Additional httpx request parameters
            
        Returns:
            httpx.Response object
        """
        if not self.client:
            raise RuntimeError("Scraper must be used as async context manager")
            
        try:
            response = await self.client.post(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(f"Error posting to {url}: {e}")
            raise
    
    @abstractmethod
    async def scrape(self) -> List[Dict[str, Any]]:
        """
        Main scraping method - must be implemented by subclasses
        
        Returns:
            List of scraped data dictionaries
        """
        pass
    
    def validate_data(self, data: Dict[str, Any], required_fields: List[str]) -> bool:
        """
        Validate that data contains required fields
        
        Args:
            data: Data dictionary to validate
            required_fields: List of required field names
            
        Returns:
            True if valid, False otherwise
        """
        for field in required_fields:
            if field not in data or data[field] is None:
                logger.warning(f"Missing required field: {field}")
                return False
        return True
    
    async def scrape_with_error_handling(self) -> List[Dict[str, Any]]:
        """
        Scrape with comprehensive error handling
        
        Returns:
            List of scraped data, empty list on error
        """
        try:
            async with self:
                data = await self.scrape()
                logger.info(f"{self.__class__.__name__} scraped {len(data)} items")
                return data
        except Exception as e:
            logger.error(f"{self.__class__.__name__} failed: {e}")
            return []
