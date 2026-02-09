"""Discord webhook integration"""

from discord_webhook import DiscordWebhook, DiscordEmbed
from loguru import logger
from typing import Dict, Any
from datetime import datetime


class DiscordAlerter:
    """Send alerts to Discord via webhook"""
    
    def __init__(self, webhook_url: str, high_alert_webhook: str = None):
        self.webhook_url = webhook_url
        self.high_alert_webhook = high_alert_webhook or webhook_url
    
    def send_fade_alert(
        self,
        game_data: Dict[str, Any],
        signal_data: Dict[str, Any]
    ) -> bool:
        """
        Send fade signal alert to Discord
        
        Args:
            game_data: Game information
            signal_data: Fade signal data
            
        Returns:
            True if successful
        """
        try:
            fade_score = signal_data.get("fade_score", 0)
            signal_type = signal_data.get("signal_type", "NO SIGNAL")
            
            # Use high priority webhook for strong signals
            webhook_url = (
                self.high_alert_webhook
                if fade_score >= 80
                else self.webhook_url
            )
            
            webhook = DiscordWebhook(url=webhook_url)
            
            # Create embed
            embed = DiscordEmbed(
                title=self._get_alert_title(signal_type, fade_score),
                description=self._format_game_description(game_data),
                color=self._get_alert_color(fade_score)
            )
            
            # Add game details
            embed.add_embed_field(
                name="Game",
                value=f"{game_data.get('away_team')} @ {game_data.get('home_team')}",
                inline=False
            )
            
            # Add fade score
            embed.add_embed_field(
                name="Fade Score",
                value=f"**{fade_score:.0f}/100**",
                inline=True
            )
            
            # Add confidence
            confidence = signal_data.get("confidence", 0)
            embed.add_embed_field(
                name="Confidence",
                value=f"{confidence:.0%}",
                inline=True
            )
            
            # Add recommendation
            recommendation = signal_data.get("recommendation", "")
            if recommendation:
                embed.add_embed_field(
                    name="Recommendation",
                    value=recommendation[:1024],  # Discord limit
                    inline=False
                )
            
            # Add reasoning
            reasoning = signal_data.get("reasoning", [])
            if reasoning:
                embed.add_embed_field(
                    name="Signals Detected",
                    value="\n".join(f"• {r}" for r in reasoning[:5]),  # Top 5
                    inline=False
                )
            
            # Add factors
            factors = signal_data.get("factors", {})
            if factors:
                factor_text = self._format_factors(factors)
                embed.add_embed_field(
                    name="Key Factors",
                    value=factor_text,
                    inline=False
                )
            
            # Footer
            embed.set_footer(
                text=f"HOUSE EDGE • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
            )
            
            # Add embed to webhook
            webhook.add_embed(embed)
            
            # Execute
            response = webhook.execute()
            
            if response.status_code == 200:
                logger.info(f"Discord alert sent for {game_data.get('away_team')} @ {game_data.get('home_team')}")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
            return False
    
    def send_whale_alert(self, whale_data: Dict[str, Any]) -> bool:
        """
        Send whale bet alert to Discord
        
        Args:
            whale_data: Whale bet information
            
        Returns:
            True if successful
        """
        try:
            webhook = DiscordWebhook(url=self.high_alert_webhook)
            
            amount = whale_data.get("amount", 0)
            
            embed = DiscordEmbed(
                title="🐋 WHALE BET ALERT",
                description=f"**${amount:,.0f}** bet detected",
                color="03b2f8"
            )
            
            # Bet details
            selection = whale_data.get("selection", "Unknown")
            odds = whale_data.get("odds")
            payout = whale_data.get("potential_payout")
            
            embed.add_embed_field(
                name="Selection",
                value=selection,
                inline=False
            )
            
            if odds:
                embed.add_embed_field(
                    name="Odds",
                    value=f"{odds:+d}",
                    inline=True
                )
            
            if payout:
                embed.add_embed_field(
                    name="Potential Payout",
                    value=f"${payout:,.0f}",
                    inline=True
                )
            
            # Source
            source = whale_data.get("source", "Unknown")
            embed.add_embed_field(
                name="Source",
                value=source,
                inline=True
            )
            
            embed.set_footer(text="HOUSE EDGE Whale Tracker")
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error sending whale alert: {e}")
            return False
    
    def _get_alert_title(self, signal_type: str, score: float) -> str:
        """Get alert title based on signal"""
        if score >= 80:
            return "🔴 STRONG FADE SIGNAL"
        elif score >= 65:
            return "🟠 FADE SIGNAL"
        elif score >= 50:
            return "🟡 MONITOR SIGNAL"
        else:
            return "⚪ INFORMATIONAL"
    
    def _get_alert_color(self, score: float) -> str:
        """Get embed color based on score"""
        if score >= 80:
            return "ff0000"  # Red
        elif score >= 65:
            return "ff8800"  # Orange
        elif score >= 50:
            return "ffff00"  # Yellow
        else:
            return "ffffff"  # White
    
    def _format_game_description(self, game_data: Dict[str, Any]) -> str:
        """Format game description"""
        sport = game_data.get("sport", "")
        game_time = game_data.get("game_time", "")
        
        if isinstance(game_time, datetime):
            time_str = game_time.strftime("%a, %b %d @ %I:%M %p")
        else:
            time_str = str(game_time)
        
        return f"{sport} • {time_str}"
    
    def _format_factors(self, factors: Dict[str, Any]) -> str:
        """Format factors into readable text"""
        lines = []
        
        if factors.get("extreme_public"):
            pct = factors.get("public_money_pct", 0)
            lines.append(f"✓ Extreme Public: {pct:.0f}%")
        
        if factors.get("sharp_divergence"):
            div = factors.get("sharp_divergence", 0)
            lines.append(f"✓ Sharp Divergence: {div:.0f}% gap")
        
        if factors.get("reverse_line_movement"):
            lines.append("✓ Reverse Line Movement")
        
        if factors.get("whale_confirmation"):
            lines.append("✓ Whale Activity Confirmed")
        
        if factors.get("book_liability"):
            lines.append("✓ Book Exposed")
        
        return "\n".join(lines) if lines else "No key factors"
