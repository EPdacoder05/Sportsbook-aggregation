#!/usr/bin/env python3
"""
Test Pick Generator
===================
Test script to validate the pick generation pipeline with sample data.
"""

import sys
import os
import json
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.pick_generator import PickGenerator
from alerts.discord_notifier import DiscordNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def main():
    """Test pick generation with sample data."""
    
    logger.info("=" * 80)
    logger.info("Testing Pick Generator with Sample Data")
    logger.info("=" * 80)
    
    # Initialize generator
    generator = PickGenerator(data_dir="data")
    
    # Load sample odds data
    with open("data/sample_odds.json", 'r') as f:
        odds_data = json.load(f)
    
    # Load opening lines
    with open("data/opening_lines_20260209.json", 'r') as f:
        opening_lines = json.load(f)
    
    # Load public splits
    with open("data/public_splits.json", 'r') as f:
        public_splits = json.load(f)
    
    # Merge data
    games = generator.data_loader.merge_game_data(odds_data, opening_lines, public_splits)
    
    logger.info(f"\nMerged data for {len(games)} games")
    
    # Analyze each game
    all_picks = []
    
    for i, game_data in enumerate(games, 1):
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Game {i}: {game_data['away_team']} @ {game_data['home_team']}")
        logger.info(f"{'=' * 80}")
        
        # Show line movement
        opening_spread = game_data.get('opening_spread')
        current_spread = game_data.get('current_spread')
        opening_total = game_data.get('opening_total')
        current_total = game_data.get('current_total')
        
        if opening_spread and current_spread:
            spread_move = current_spread - opening_spread
            logger.info(f"Spread: {opening_spread:+.1f} → {current_spread:+.1f} (Δ {spread_move:+.1f})")
        
        if opening_total and current_total:
            total_move = current_total - opening_total
            logger.info(f"Total: {opening_total} → {current_total} (Δ {total_move:+.1f})")
        
        # Show public splits
        logger.info(f"Public: {game_data['public_pct_home']*100:.0f}% on {game_data['home_team']} (spread)")
        logger.info(f"Public: {game_data['public_pct_over']*100:.0f}% on Over (total)")
        
        # Analyze game
        picks = generator._analyze_game(game_data)
        
        if picks:
            logger.info(f"\n🎯 Generated {len(picks)} pick(s):")
            for pick in picks:
                logger.info("")
                # Select emoji based on tier
                tier_emojis = {
                    "TIER_1": "🔥🔥🔥",
                    "TIER_2": "🔶",
                    "LEAN": "📌"
                }
                emoji = tier_emojis.get(pick.tier, "📌")
                logger.info(f"{emoji} {pick.tier}: {pick.pick}")
                logger.info(f"   Confidence: {pick.confidence*100:.0f}%")
                logger.info(f"   Signals: {', '.join(pick.signals)}")
                logger.info(f"   Reasoning: {pick.reasoning}")
                logger.info(f"   Best Book: {pick.best_book}")
                all_picks.append(pick)
        else:
            logger.info("\n❌ No picks generated (PASS)")
    
    # Summary
    logger.info(f"\n{'=' * 80}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 80}")
    
    tier1 = [p for p in all_picks if p.tier == 'TIER_1']
    tier2 = [p for p in all_picks if p.tier == 'TIER_2']
    leans = [p for p in all_picks if p.tier == 'LEAN']
    
    logger.info(f"Total picks: {len(all_picks)}")
    logger.info(f"  TIER 1: {len(tier1)}")
    logger.info(f"  TIER 2: {len(tier2)}")
    logger.info(f"  LEAN:   {len(leans)}")
    
    if tier1:
        logger.info("\n🔥 TIER 1 PICKS:")
        for pick in tier1:
            logger.info(f"  • {pick.game}: {pick.pick} ({pick.confidence*100:.0f}%)")
    
    # Save picks
    if all_picks:
        generator.save_picks(all_picks, "20260209")
        logger.info("\n✅ Picks saved to data/picks_20260209.json")
    
    # Test Discord notifier (without actually sending)
    logger.info("\n" + "=" * 80)
    logger.info("Discord Notification Test")
    logger.info("=" * 80)
    
    notifier = DiscordNotifier()  # Will be disabled without webhook URL
    
    if notifier.enabled:
        logger.info("Discord notifier is ENABLED")
        logger.info("Would send notifications for Tier 1 and Tier 2 picks")
    else:
        logger.info("Discord notifier is DISABLED (no webhook URL configured)")
        logger.info("Set DISCORD_WEBHOOK_URL environment variable to enable")
    
    logger.info("\n" + "=" * 80)
    logger.info("Test Complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
