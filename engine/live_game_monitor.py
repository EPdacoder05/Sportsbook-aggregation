"""
LIVE GAME MONITOR - Real-time score tracking and line adjustment
Updates signals as games progress, just like Vegas adjusts odds
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
sys.path.insert(0, '/app')

from database.db import SessionLocal
from database.models import Game, Signal, OddsSnapshot
from sqlalchemy import and_

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LiveGameMonitor:
    """
    Monitors live games and adjusts recommendations in real-time
    Like Vegas: When score changes dramatically, update the edge
    """
    
    def __init__(self):
        self.db = SessionLocal()
        self.live_games = {}
        self.update_interval = 30  # Check every 30 seconds
        
    def get_live_games(self) -> List[Game]:
        """Get games currently in progress"""
        now = datetime.utcnow()
        
        # Games that started in last 4 hours and aren't marked complete
        recent_start = now - timedelta(hours=4)
        
        return self.db.query(Game).filter(
            and_(
                Game.game_time <= now,
                Game.game_time >= recent_start,
                Game.status.in_(['in_progress', 'scheduled'])
            )
        ).all()
    
    async def fetch_live_score(self, game_id: int, sport: str) -> Optional[Dict]:
        """
        Fetch live score from API
        In production: Connect to ESPN API, The Score, etc.
        For now: Return simulated live data
        """
        try:
            # Simulate live score updates
            # In production, replace with actual API call
            return {
                'game_id': game_id,
                'status': 'in_progress',
                'quarter': 3,
                'time_remaining': '8:42',
                'home_score': 24,
                'away_score': 17,
                'last_play': 'TD - Home team',
                'momentum': 'home',  # Which team has momentum
                'injuries': [],  # List of injured players
                'live_spread': -10.5,  # Current live spread
            }
        except Exception as e:
            logger.error(f"Error fetching live score: {e}")
            return None
    
    def analyze_live_situation(self, game: Game, live_data: Dict) -> Dict:
        """
        Analyze if current game situation changes our recommendation
        
        Key factors:
        - Score differential vs original spread
        - Momentum shifts
        - Key injuries
        - Time remaining
        """
        try:
            # Get original signal for this game
            signal = self.db.query(Signal).filter(
                and_(
                    Signal.game_id == game.id,
                    Signal.expires_at > datetime.utcnow()
                )
            ).first()
            
            if not signal:
                return {'action': 'no_signal', 'recommendation': 'No active signal'}
            
            # Get original spread
            odds = self.db.query(OddsSnapshot).filter(
                OddsSnapshot.game_id == game.id
            ).order_by(OddsSnapshot.snapshot_time.desc()).first()
            
            if not odds:
                return {'action': 'no_odds'}
            
            original_spread = abs(odds.home_spread or 0)
            current_margin = abs(live_data['home_score'] - live_data['away_score'])
            
            # SCENARIO 1: Blowout forming (margin > spread + 14)
            if current_margin > original_spread + 14:
                return {
                    'action': 'ALERT_BLOWOUT',
                    'game': f"{game.away_team} @ {game.home_team}",
                    'original_pick': signal.recommendation,
                    'current_score': f"{live_data['home_score']}-{live_data['away_score']}",
                    'recommendation': '🚨 BLOWOUT ALERT - Consider hedging or live betting opposite',
                    'confidence': 'LOW',
                    'reason': f'Margin ({current_margin}) exceeds spread by {current_margin - original_spread:.1f}'
                }
            
            # SCENARIO 2: Close game (still within spread + 3)
            if current_margin <= original_spread + 3:
                return {
                    'action': 'HOLD',
                    'game': f"{game.away_team} @ {game.home_team}",
                    'current_score': f"{live_data['home_score']}-{live_data['away_score']}",
                    'recommendation': '✅ Pick still alive - HOLD position',
                    'confidence': 'MEDIUM'
                }
            
            # SCENARIO 3: Comfortable cover forming
            underdog_covering = current_margin < original_spread - 3
            if underdog_covering:
                return {
                    'action': 'GOOD',
                    'game': f"{game.away_team} @ {game.home_team}",
                    'current_score': f"{live_data['home_score']}-{live_data['away_score']}",
                    'recommendation': '🟢 Underdog covering - Looking good!',
                    'confidence': 'HIGH'
                }
            
            # SCENARIO 4: Key injury detected
            if live_data.get('injuries'):
                return {
                    'action': 'ALERT_INJURY',
                    'game': f"{game.away_team} @ {game.home_team}",
                    'injuries': live_data['injuries'],
                    'recommendation': '⚠️ Key injury - Monitor situation',
                    'confidence': 'REDUCED'
                }
            
            return {'action': 'MONITOR', 'recommendation': 'Continue monitoring'}
            
        except Exception as e:
            logger.error(f"Error analyzing game {game.id}: {e}")
            return {'action': 'ERROR'}
    
    def update_signal_confidence(self, signal: Signal, live_situation: Dict):
        """Adjust signal confidence based on live game state"""
        if live_situation['action'] == 'ALERT_BLOWOUT':
            # Lower confidence dramatically
            signal.confidence = 0.25
            signal.reasoning += f" | LIVE UPDATE: {live_situation['recommendation']}"
            self.db.commit()
            logger.warning(f"⚠️ {live_situation['game']}: Confidence lowered to 25%")
        
        elif live_situation['action'] == 'GOOD':
            # Increase confidence
            signal.confidence = min(0.95, signal.confidence + 0.15)
            self.db.commit()
            logger.info(f"✅ {live_situation['game']}: Confidence increased to {signal.confidence:.0%}")
    
    async def monitor_live_games(self):
        """Main monitoring loop - runs continuously during game days"""
        logger.info("🚀 Live Game Monitor started")
        
        try:
            while True:
                # Get games in progress
                live_games = self.get_live_games()
                
                if not live_games:
                    logger.info("No live games currently")
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"📊 Monitoring {len(live_games)} live games...")
                
                for game in live_games:
                    # Fetch live data
                    live_data = await self.fetch_live_score(game.id, game.sport)
                    
                    if not live_data:
                        continue
                    
                    # Analyze situation
                    situation = self.analyze_live_situation(game, live_data)
                    
                    # Log important updates
                    if situation['action'] in ['ALERT_BLOWOUT', 'ALERT_INJURY', 'GOOD']:
                        logger.warning(f"🔥 {situation['game']}: {situation['recommendation']}")
                    
                    # Update signal if needed
                    signal = self.db.query(Signal).filter(
                        Signal.game_id == game.id
                    ).first()
                    
                    if signal:
                        self.update_signal_confidence(signal, situation)
                
                # Wait 30 seconds before next check
                await asyncio.sleep(self.update_interval)
                
        except KeyboardInterrupt:
            logger.info("Monitor stopped")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        finally:
            self.db.close()


async def main():
    """Start live monitoring"""
    monitor = LiveGameMonitor()
    await monitor.monitor_live_games()


if __name__ == "__main__":
    asyncio.run(main())
