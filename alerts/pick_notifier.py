"""
Pick Notifier
==============
Sends analysis results / picks to configured notification channels.
Currently supports Discord. SMS/email can be added by wiring AlertManager.

Usage:
    from alerts.pick_notifier import PickNotifier
    
    notifier = PickNotifier()
    notifier.send_window_analysis(window_id, results)  # from smart_scheduler
    notifier.send_daily_summary(all_picks)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

try:
    from discord_webhook import DiscordWebhook, DiscordEmbed
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False
    logger.debug("discord-webhook not installed — Discord notifications disabled")

from config.api_registry import api


class PickNotifier:
    """Sends analysis results to Discord (and optionally SMS/email)."""

    def __init__(self):
        self.webhook_url = api.discord.key  # actually the webhook URL
        self.high_webhook = _env("DISCORD_HIGH_ALERT_WEBHOOK", self.webhook_url)
        self.enabled = bool(self.webhook_url) and HAS_DISCORD
        if self.enabled:
            logger.info("Discord notifications ENABLED")
        else:
            logger.info("Discord notifications DISABLED (no webhook URL or missing package)")

    # ── public API ───────────────────────────────────────────────────

    def send_window_analysis(self, window_id: str, results: Dict[str, Any]):
        """Send analysis for a single game-time window."""
        if not self.enabled or not results:
            return

        # Build one embed per game with a signal
        embeds = []
        for game_key, data in results.items():
            embed = self._build_game_embed(game_key, data)
            if embed:
                embeds.append(embed)

        if not embeds:
            return  # Nothing exciting to report

        try:
            webhook = DiscordWebhook(
                url=self.webhook_url,
                content=f"**⏰ WINDOW: {window_id}** — {len(results)} games analyzed",
            )
            for embed in embeds[:10]:  # Discord max 10 embeds per message
                webhook.add_embed(embed)
            resp = webhook.execute()
            if resp and getattr(resp, "status_code", 0) in (200, 204):
                logger.info(f"Discord: sent {len(embeds)} game(s) for {window_id}")
            else:
                logger.warning(f"Discord: unexpected status {getattr(resp, 'status_code', '?')}")
        except Exception as e:
            logger.error(f"Discord send failed: {e}")

    def send_daily_summary(self, picks: List[Dict[str, Any]]):
        """Send end-of-day pick summary."""
        if not self.enabled:
            return

        if not picks:
            return

        lines = [f"**HOUSE EDGE — Daily Picks ({datetime.now().strftime('%b %d')})**\n"]
        total_units = 0.0

        for p in picks:
            tier = p.get("tier", "LEAN")
            game = p.get("game", "?")
            pick = p.get("pick", "?")
            units = p.get("units", 1.0)
            conf = p.get("confidence", 0)
            total_units += units
            lines.append(f"{'🔴' if tier == 'TIER1' else '🟠' if tier == 'TIER2' else '🟡'} **{tier}** {game} → {pick} ({units}U, {conf}%)")

        lines.append(f"\n**Total exposure: {total_units:.1f}U**")

        try:
            webhook = DiscordWebhook(url=self.webhook_url, content="\n".join(lines))
            webhook.execute()
            logger.info(f"Discord: daily summary sent ({len(picks)} picks)")
        except Exception as e:
            logger.error(f"Discord daily summary failed: {e}")

    def send_credit_warning(self, remaining: int, monthly_limit: int):
        """Alert when credits are running low."""
        if not self.enabled:
            return

        pct = remaining / monthly_limit * 100 if monthly_limit else 0
        if pct > 30:
            return  # Not low enough to warn

        try:
            webhook = DiscordWebhook(
                url=self.high_webhook or self.webhook_url,
                content=(
                    f"⚠️ **CREDIT WARNING**: {remaining}/{monthly_limit} remaining ({pct:.0f}%)\n"
                    f"Daily budget reduced. Consider limiting calls."
                ),
            )
            webhook.execute()
        except Exception as e:
            logger.error(f"Discord credit warning failed: {e}")

    # ── private helpers ──────────────────────────────────────────────

    def _build_game_embed(self, game_key: str, data: Dict) -> Optional["DiscordEmbed"]:
        """Build a Discord embed for a game, only if it has signals."""
        sp = data.get("spreads") or {}
        tot = data.get("totals") or {}
        ml = data.get("moneylines") or {}

        has_signal = sp.get("disagreement") or tot.get("disagreement")
        if not has_signal:
            return None  # Skip boring games

        embed = DiscordEmbed(
            title=f"📊 {game_key}",
            description=f"Books: {data.get('books_count', 0)} | {data.get('commence_time', '')[:16]}",
            color="ff8800" if (sp.get("spread_range", 0) >= 2 or tot.get("total_range", 0) >= 2) else "ffff00",
        )

        if sp:
            spread_text = f"Consensus: **{sp.get('consensus_line', 0):+.1f}**"
            if sp.get("disagreement"):
                spread_text += f"\n⚠️ {sp['spread_range']:.1f}pt range ({sp['min_line']:+.1f} → {sp['max_line']:+.1f})"
            if sp.get("best_away"):
                ba = sp["best_away"]
                spread_text += f"\nBest dog: +{ba['line']} @ {ba['book']}"
            embed.add_embed_field(name="Spread", value=spread_text, inline=True)

        if tot:
            total_text = f"Consensus: **{tot.get('consensus_line', 0):.1f}**"
            if tot.get("disagreement"):
                total_text += f"\n⚠️ {tot['total_range']:.1f}pt range ({tot['min_line']:.1f} → {tot['max_line']:.1f})"
            embed.add_embed_field(name="Total", value=total_text, inline=True)

        if ml:
            embed.add_embed_field(
                name="Moneyline",
                value=f"Home: {ml.get('home_consensus', 0):+d} / Away: {ml.get('away_consensus', 0):+d}",
                inline=False,
            )

        embed.set_footer(text=f"HOUSE EDGE • {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
        return embed


def _env(key: str, default: str = "") -> str:
    import os
    return os.getenv(key, default)
