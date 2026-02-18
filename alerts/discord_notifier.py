"""
Discord Notifier
================
Send rich embedded notifications for betting picks to Discord.

Features:
- Tier 1 picks with rich formatting
- Quota warnings
- Daily summaries
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

try:
    from discord_webhook import DiscordWebhook, DiscordEmbed
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    logging.warning("discord-webhook not installed. Discord notifications disabled.")

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """
    Send betting picks and alerts to Discord via webhook.
    """
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Args:
            webhook_url: Discord webhook URL (default: from DISCORD_WEBHOOK_URL env var)
        """
        if not DISCORD_AVAILABLE:
            logger.warning("Discord webhook library not available")
            self.enabled = False
            return
        
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        
        if not self.webhook_url:
            logger.warning("No Discord webhook URL configured. Notifications disabled.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Discord notifier initialized")
    
    def send_tier1_pick(self, pick: Dict[str, Any]) -> bool:
        """
        Send a Tier 1 pick notification with rich formatting.
        
        Args:
            pick: Pick dictionary with keys:
                - game: Game matchup (e.g., "CHI @ BKN")
                - pick: Pick description (e.g., "UNDER 218.5")
                - confidence: Confidence score (0.0 to 1.0)
                - signals: List of signal types
                - reasoning: Analysis reasoning
                - best_book: Best bookmaker and odds
                - tier: "TIER_1"
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            # Create rich embed
            embed = DiscordEmbed(
                title=f"🔥🔥🔥 TIER 1 PICK - {pick['game']}",
                description=f"**{pick['pick']}**",
                color=16729600  # Orange
            )
            
            # Add fields
            embed.add_embed_field(
                name="Confidence",
                value=f"{pick['confidence']*100:.0f}%",
                inline=True
            )
            
            embed.add_embed_field(
                name="Signals",
                value=f"{len(pick['signals'])} ({', '.join(pick['signals'])})",
                inline=True
            )
            
            embed.add_embed_field(
                name="Reasoning",
                value=pick['reasoning'][:1024],  # Discord limit
                inline=False
            )
            
            embed.add_embed_field(
                name="Best Book",
                value=pick['best_book'],
                inline=False
            )
            
            # Footer with timestamp
            timestamp = pick.get('timestamp', datetime.utcnow().isoformat())
            embed.set_footer(text=f"Generated at {timestamp}")
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code == 200 or response.status_code == 204:
                logger.info(f"Tier 1 pick sent to Discord: {pick['pick']}")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return False
    
    def send_tier2_pick(self, pick: Dict[str, Any]) -> bool:
        """
        Send a Tier 2 pick notification.
        
        Args:
            pick: Pick dictionary (same format as tier1)
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title=f"🔶 TIER 2 PICK - {pick['game']}",
                description=f"**{pick['pick']}**",
                color=16753920  # Yellow/Gold
            )
            
            embed.add_embed_field(
                name="Confidence",
                value=f"{pick['confidence']*100:.0f}%",
                inline=True
            )
            
            embed.add_embed_field(
                name="Signals",
                value=f"{len(pick['signals'])}",
                inline=True
            )
            
            embed.add_embed_field(
                name="Reasoning",
                value=pick['reasoning'][:1024],
                inline=False
            )
            
            embed.add_embed_field(
                name="Best Book",
                value=pick['best_book'],
                inline=False
            )
            
            timestamp = pick.get('timestamp', datetime.utcnow().isoformat())
            embed.set_footer(text=f"Generated at {timestamp}")
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code == 200 or response.status_code == 204:
                logger.info(f"Tier 2 pick sent to Discord: {pick['pick']}")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return False
    
    def send_quota_warning(self, used: int, total: int) -> bool:
        """
        Send API quota warning.
        
        Args:
            used: Credits used
            total: Total credits available
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            percent = (used / total) * 100 if total > 0 else 0
            
            # Choose color based on usage
            if percent >= 90:
                color = 16711680  # Red
                icon = "🚨"
            elif percent >= 75:
                color = 16776960  # Yellow
                icon = "⚠️"
            else:
                color = 16753920  # Orange
                icon = "ℹ️"
            
            embed = DiscordEmbed(
                title=f"{icon} API Quota Warning",
                description=f"Used **{used}/{total}** Odds API credits ({percent:.0f}%)",
                color=color
            )
            
            if percent >= 90:
                embed.add_embed_field(
                    name="Action Required",
                    value="Approaching monthly limit. Consider reducing fetch frequency.",
                    inline=False
                )
            
            embed.set_footer(text=f"Checked at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            return response.status_code in [200, 204]
        
        except Exception as e:
            logger.error(f"Error sending quota warning: {e}")
            return False
    
    def send_daily_summary(self, picks: List[Dict[str, Any]]) -> bool:
        """
        Send daily summary of all picks.
        
        Args:
            picks: List of pick dictionaries
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            # Count by tier
            tier1_count = sum(1 for p in picks if p['tier'] == 'TIER_1')
            tier2_count = sum(1 for p in picks if p['tier'] == 'TIER_2')
            lean_count = sum(1 for p in picks if p['tier'] == 'LEAN')
            
            embed = DiscordEmbed(
                title="📊 Daily Pick Summary",
                description=f"Generated {len(picks)} picks for today",
                color=3447003  # Blue
            )
            
            embed.add_embed_field(
                name="Tier 1",
                value=f"{tier1_count} picks",
                inline=True
            )
            
            embed.add_embed_field(
                name="Tier 2",
                value=f"{tier2_count} picks",
                inline=True
            )
            
            embed.add_embed_field(
                name="Leans",
                value=f"{lean_count} picks",
                inline=True
            )
            
            # List Tier 1 picks
            if tier1_count > 0:
                tier1_picks = [p for p in picks if p['tier'] == 'TIER_1']
                pick_lines = []
                for pick in tier1_picks[:5]:  # Max 5
                    pick_lines.append(f"• {pick['game']}: **{pick['pick']}** ({pick['confidence']*100:.0f}%)")
                
                embed.add_embed_field(
                    name="Top Tier 1 Picks",
                    value="\n".join(pick_lines),
                    inline=False
                )
            
            embed.set_footer(text=f"Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            return response.status_code in [200, 204]
        
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
            return False
    
    def send_pick(self, pick: Dict[str, Any]) -> bool:
        """
        Send a pick notification (auto-detects tier).
        
        Args:
            pick: Pick dictionary
        
        Returns:
            True if sent successfully
        """
        tier = pick.get('tier', 'PASS')
        
        if tier == 'TIER_1':
            return self.send_tier1_pick(pick)
        elif tier == 'TIER_2':
            return self.send_tier2_pick(pick)
        else:
            # Don't send leans or passes by default
            logger.debug(f"Skipping Discord notification for {tier} pick")
            return False
