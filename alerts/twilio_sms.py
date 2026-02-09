"""Twilio SMS integration for high-priority alerts"""

from twilio.rest import Client
from loguru import logger
from typing import List, Dict, Any


class TwilioSMSAlerter:
    """Send SMS alerts via Twilio"""
    
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_numbers: List[str]
    ):
        self.from_number = from_number
        self.to_numbers = to_numbers
        
        try:
            self.client = Client(account_sid, auth_token)
            logger.info("Twilio SMS client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio: {e}")
            self.client = None
    
    def send_fade_alert(
        self,
        game_data: Dict[str, Any],
        signal_data: Dict[str, Any]
    ) -> bool:
        """
        Send fade signal SMS alert
        
        Only sends for high-priority signals (score >= 80)
        
        Args:
            game_data: Game information
            signal_data: Fade signal data
            
        Returns:
            True if successful
        """
        fade_score = signal_data.get("fade_score", 0)
        
        # Only send SMS for strong signals
        if fade_score < 80:
            return False
        
        if not self.client:
            logger.warning("Twilio client not initialized")
            return False
        
        try:
            message_body = self._format_fade_message(game_data, signal_data)
            
            success_count = 0
            for to_number in self.to_numbers:
                try:
                    message = self.client.messages.create(
                        body=message_body,
                        from_=self.from_number,
                        to=to_number
                    )
                    logger.info(f"SMS sent to {to_number}: {message.sid}")
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send SMS to {to_number}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error sending SMS alerts: {e}")
            return False
    
    def send_whale_alert(self, whale_data: Dict[str, Any]) -> bool:
        """
        Send whale bet SMS alert
        
        Only sends for mega whales ($100K+)
        
        Args:
            whale_data: Whale bet information
            
        Returns:
            True if successful
        """
        amount = whale_data.get("amount", 0)
        
        # Only send for mega whales
        if amount < 100000:
            return False
        
        if not self.client:
            return False
        
        try:
            message_body = self._format_whale_message(whale_data)
            
            success_count = 0
            for to_number in self.to_numbers:
                try:
                    message = self.client.messages.create(
                        body=message_body,
                        from_=self.from_number,
                        to=to_number
                    )
                    logger.info(f"Whale SMS sent to {to_number}: {message.sid}")
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send whale SMS to {to_number}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error sending whale SMS: {e}")
            return False
    
    def _format_fade_message(
        self,
        game_data: Dict[str, Any],
        signal_data: Dict[str, Any]
    ) -> str:
        """Format fade alert SMS message"""
        away = game_data.get("away_team", "")
        home = game_data.get("home_team", "")
        fade_score = signal_data.get("fade_score", 0)
        
        public_side = game_data.get("public_side", "")
        public_pct = game_data.get("public_money_pct", 0)
        
        fade_team = away if public_side == "home" else home
        
        message = (
            f"🔴 HOUSE EDGE ALERT\n\n"
            f"{away} @ {home}\n\n"
            f"Fade Score: {fade_score:.0f}/100\n"
            f"Public: {public_pct:.0f}% on {public_side.upper()}\n"
            f"RECOMMENDATION: BET {fade_team.upper()}\n\n"
            f"Multiple strong signals detected."
        )
        
        return message[:160]  # SMS character limit
    
    def _format_whale_message(self, whale_data: Dict[str, Any]) -> str:
        """Format whale alert SMS message"""
        amount = whale_data.get("amount", 0)
        selection = whale_data.get("selection", "Unknown")
        odds = whale_data.get("odds", "")
        
        message = (
            f"🐋 WHALE ALERT\n\n"
            f"${amount:,.0f} on {selection}"
        )
        
        if odds:
            message += f" ({odds:+d})"
        
        return message[:160]
