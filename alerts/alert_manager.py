"""
Unified Alert Manager

Sends alerts via:
- Discord Webhook
- Email (SendGrid)
"""

from typing import Dict, Any, List, Optional
from loguru import logger
from config.settings import get_settings
from alerts.discord_webhook import DiscordAlerter
from alerts.email_alert import EmailAlert


class AlertManager:
    """Unified alert management"""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = logger
        
        # Initialize alerters
        self.discord: Optional[DiscordAlerter] = None
        self.email: Optional[EmailAlert] = None
        
        self._init_discord()
        self._init_email()
    
    def _init_discord(self):
        """Initialize Discord alerter"""
        webhook_url = getattr(self.settings, 'DISCORD_WEBHOOK_URL', None)
        if webhook_url:
            try:
                high_alert_webhook = getattr(self.settings, 'DISCORD_HIGH_ALERT_WEBHOOK', webhook_url)
                self.discord = DiscordAlerter(
                    webhook_url=webhook_url,
                    high_alert_webhook=high_alert_webhook
                )
                logger.info("OK Discord alerter initialized")
            except Exception as e:
                logger.error(f"FAIL Discord initialization: {e}")
    
    def _init_email(self):
        """Initialize email alerter"""
        if getattr(self.settings, 'SENDGRID_API_KEY', None):
            try:
                self.email = EmailAlert(settings=self.settings)
                logger.info("OK Email alerter initialized")
            except Exception as e:
                logger.error(f"FAIL Email initialization: {e}")
    
    async def send_fade_alert(
        self,
        game_data: Dict[str, Any],
        signal_data: Dict[str, Any],
        channels: List[str] = None
    ) -> Dict[str, bool]:
        """
        Send fade signal alert across channels
        
        Args:
            game_data: Game information
            signal_data: Fade signal data
            channels: Specific channels to use (default: all)
            
        Returns:
            Dict of channel: success status
        """
        fade_score = signal_data.get("fade_score", 0)
        
        # Only send alerts for meaningful signals
        min_score = getattr(self.settings, 'min_fade_score_alert', 70)
        if fade_score < min_score:
            logger.debug(f"Fade score {fade_score} below threshold, skipping alert")
            return {}
        
        results = {}
        channels = channels or ["discord"]
        
        # Discord alert
        if "discord" in channels and self.discord:
            try:
                await self.discord.send(f"Fade Alert - Score: {fade_score}")
                results["discord"] = True
                logger.info(f"✓ Discord fade alert sent (score: {fade_score})")
            except Exception as e:
                logger.error(f"❌ Discord alert failed: {e}")
                results["discord"] = False
        
        return results
    
    async def send_whale_alert(
        self,
        whale_data: Dict[str, Any],
        channels: List[str] = None
    ) -> Dict[str, bool]:
        """
        Send whale bet alert across channels
        
        Args:
            whale_data: Whale bet information
            channels: Specific channels to use (default: all)
            
        Returns:
            Dict of channel: success status
        """
        amount = whale_data.get("amount", 0)
        threshold = getattr(self.settings, 'min_whale_bet_amount', 10000)
        
        # Only send for significant whales
        if amount < threshold:
            return {}
        
        results = {}
        channels = channels or ["discord"]
        
        # Discord alert
        if "discord" in channels and self.discord:
            try:
                team = whale_data.get('team', 'Unknown')
                await self.discord.send(f"🐋 WHALE BET: ${amount:,.0f} on {team}")
                results["discord"] = True
                logger.info(f"✓ Discord whale alert sent (${amount:,.0f})")
            except Exception as e:
                logger.error(f"❌ Discord whale alert failed: {e}")
                results["discord"] = False
        
        return results
    
    async def send_test_alert(self) -> Dict[str, bool]:
        """
        Send test alerts to verify configuration
        
        Returns:
            Dict of channel: success status
        """
        test_message = "🧪 HOUSE EDGE TEST ALERT - If you see this, alerts are working!"
        
        logger.info("📨 Sending test alerts...")
        results = {}
        
        if self.discord:
            try:
                await self.discord.send(test_message)
                results["discord"] = True
                logger.info("✓ Discord test alert sent successfully")
            except Exception as e:
                logger.error(f"❌ Discord test failed: {e}")
                results["discord"] = False
        
        if self.email:
            try:
                await self.email.send("Test Alert", test_message)
                results["email"] = True
                logger.info("✓ Email test alert sent successfully")
            except Exception as e:
                logger.error(f"❌ Email test failed: {e}")
                results["email"] = False
        
        return results
    
    def get_status(self) -> Dict[str, bool]:
        """
        Get status of all alert channels
        
        Returns:
            Dict of channel: configured status
        """
        return {
            "discord": self.discord is not None,
            "email": self.email is not None
        }
