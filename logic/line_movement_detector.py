"""
Line Movement (RLM) Detector
Detects reverse line movement = when line moves opposite to public betting expectations
This is a real money signal - sharp money pushes line against the public
"""

from datetime import datetime, timedelta
from sqlalchemy import and_
from database.models import Game, OddsSnapshot, OddsHistory, LineMovement, Signal, SignalType, BetType
from database.db import SessionLocal
import logging

logger = logging.getLogger(__name__)


def get_opening_line(game_id):
    """Get the earliest odds snapshot for a game (opening line)"""
    db = SessionLocal()
    try:
        opening = db.query(OddsHistory).filter(
            OddsHistory.game_id == game_id
        ).order_by(
            OddsHistory.snapshot_time.asc()
        ).first()

        # Fallback to OddsSnapshot if history not available
        if not opening:
            opening = db.query(OddsSnapshot).filter(
                OddsSnapshot.game_id == game_id
            ).order_by(
                OddsSnapshot.snapshot_time.asc()
            ).first()
        
        if opening:
            return {
                "home_spread": opening.home_spread,
                "away_spread": opening.away_spread,
                "home_ml": opening.home_ml,
                "away_ml": opening.away_ml,
                "snapshot_time": opening.snapshot_time
            }
        return None
    finally:
        db.close()


def get_current_line(game_id):
    """Get the most recent odds snapshot for a game (current line)"""
    db = SessionLocal()
    try:
        current = db.query(OddsHistory).filter(
            OddsHistory.game_id == game_id
        ).order_by(
            OddsHistory.snapshot_time.desc()
        ).first()

        # Fallback to OddsSnapshot if history not available
        if not current:
            current = db.query(OddsSnapshot).filter(
                OddsSnapshot.game_id == game_id
            ).order_by(
                OddsSnapshot.snapshot_time.desc()
            ).first()
        
        if current:
            return {
                "home_spread": current.home_spread,
                "away_spread": current.away_spread,
                "home_ml": current.home_ml,
                "away_ml": current.away_ml,
                "snapshot_time": current.snapshot_time
            }
        return None
    finally:
        db.close()


def detect_rlm_for_game(game_id):
    """
    Detect reverse line movement for a game
    RLM = Line moves opposite to where public consensus expects
    
    Example:
    - Opening: Ravens -2.5 (public consensus is "take Ravens")
    - Current: Ravens -3.5 (line moved AWAY from Ravens, meaning sharp money on Steelers)
    - Result: RLM detected (line supports Steelers, public wants Ravens)
    
    Returns: LineMovement object with RLM detection or None
    """
    
    opening = get_opening_line(game_id)
    current = get_current_line(game_id)
    
    if not opening or not current or opening == current:
        return None
    
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            return None
        
        # Calculate spread movement
        # Positive = line moved toward away team (home got worse)
        # Negative = line moved toward home team (away got worse)
        spread_movement = current["home_spread"] - opening["home_spread"]
        
        # Determine public consensus (where the money is expected)
        # In most cases, public bets favorites and overs
        # So consensus would be on lower number team (favorite)
        if opening["home_spread"] < 0:  # Home is favorite
            public_favored = "home"
        else:  # Away is favorite
            public_favored = "away"
        
        # Determine where line moved
        if spread_movement > 0:
            line_moved_to = "away"  # Line moved toward away team
        elif spread_movement < 0:
            line_moved_to = "home"  # Line moved toward home team
        else:
            return None  # No movement
        
        # RLM = line moved opposite to public consensus
        is_rlm = public_favored != line_moved_to
        
        # RLM strength = absolute value of spread movement
        rlm_strength = abs(spread_movement)
        
        logger.info(f"🎯 RLM Detection Game {game_id} ({game.home_team} vs {game.away_team})")
        logger.info(f"   Opening: {opening['home_spread']} | Current: {current['home_spread']}")
        logger.info(f"   Public favors: {public_favored} | Line moved to: {line_moved_to}")
        logger.info(f"   RLM: {is_rlm} (Strength: {rlm_strength} pts)")
        
        # Create or update LineMovement record
        existing = db.query(LineMovement).filter(
            LineMovement.game_id == game_id
        ).first()
        
        if existing:
            existing.current_spread = current["home_spread"]
            existing.current_ml_home = current["home_ml"]
            existing.current_ml_away = current["away_ml"]
            existing.spread_movement = spread_movement
            existing.is_rlm = is_rlm
            existing.rlm_strength = rlm_strength
            existing.line_moved_to = line_moved_to
            existing.updated_at = datetime.utcnow()
            line_mov = existing
        else:
            line_mov = LineMovement(
                game_id=game_id,
                opening_spread=opening["home_spread"],
                current_spread=current["home_spread"],
                spread_movement=spread_movement,
                opening_ml_home=opening["home_ml"],
                current_ml_home=current["home_ml"],
                opening_ml_away=opening["away_ml"],
                current_ml_away=current["away_ml"],
                public_favored_side=public_favored,
                line_moved_to=line_moved_to,
                is_rlm=is_rlm,
                rlm_strength=rlm_strength
            )
        
        db.add(line_mov)
        db.commit()
        return line_mov
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error detecting RLM for game {game_id}: {str(e)}")
        return None
    finally:
        db.close()


def generate_rlm_signals():
    """
    Generate fade signals based on reverse line movement
    RLM = money coming in opposite to public consensus = sharp signal
    """
    
    db = SessionLocal()
    try:
        # Get all scheduled games (accept both enum-like and lowercase statuses)
        scheduled_games = db.query(Game).filter(
            Game.status.in_(["SCHEDULED", "scheduled", "IN_PROGRESS", "in_progress"])
        ).all()
        
        signals_created = 0
        
        for game in scheduled_games:
            # Detect RLM
            line_mov = detect_rlm_for_game(game.id)
            
            if not line_mov or not line_mov.is_rlm:
                continue
            
            # Only create signal if RLM strength > 1 point
            if line_mov.rlm_strength <= 1.0:
                continue
            
            # Determine the fade target
            # If line moved to away = away got better = public was on home = FADE home, TAKE away
            # If line moved to home = home got better = public was on away = FADE away, TAKE home
            
            if line_mov.line_moved_to == "away":
                fade_team = game.home_team
                take_team = game.away_team
                fade_side = "home"
                take_side = "away"
            else:
                fade_team = game.away_team
                take_team = game.home_team
                fade_side = "away"
                take_side = "home"
            
            # Check if signal already exists
            existing_signal = db.query(Signal).filter(
                and_(
                    Signal.game_id == game.id,
                    Signal.signal_type == SignalType.RLM
                )
            ).first()
            
            if existing_signal:
                # Update existing signal
                existing_signal.confidence = min(100, 50 + (line_mov.rlm_strength * 10))
                existing_signal.details = f"Line moved {line_mov.rlm_strength}pts vs public consensus. Sharp money on {take_team}. FADE {fade_team}."
                existing_signal.updated_at = datetime.utcnow()
                db.add(existing_signal)
                logger.info(f"✅ Updated RLM signal for {game.home_team} vs {game.away_team} (strength: {line_mov.rlm_strength})")
            else:
                # Create new signal
                new_signal = Signal(
                    game_id=game.id,
                    signal_type=SignalType.RLM,
                    recommended_bet=f"{take_team} (FADE {fade_team})",
                    confidence=min(100, 50 + (line_mov.rlm_strength * 10)),
                    public_money_pct=None,  # RLM doesn't use public %, uses line movement
                    sharp_money_pct=None,
                    generated_at=datetime.utcnow(),
                    details=f"Line moved {line_mov.rlm_strength}pts vs public consensus. Sharp money on {take_team}. FADE {fade_team}.",
                    data_source="line_movement_rlm"
                )
                db.add(new_signal)
                signals_created += 1
                logger.info(f"✅ Created RLM signal for {game.home_team} vs {game.away_team} (confidence: {new_signal.confidence}%)")
        
        db.commit()
        logger.info(f"🎯 RLM Signal Generation: Created {signals_created} new signals")
        return signals_created
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error generating RLM signals: {str(e)}")
        return 0
    finally:
        db.close()


def get_rlm_stats():
    """Get RLM detection statistics"""
    db = SessionLocal()
    try:
        total_games = db.query(Game).count()
        rlm_games = db.query(LineMovement).filter(LineMovement.is_rlm == True).count()
        avg_rlm_strength = db.query(LineMovement).filter(
            LineMovement.is_rlm == True
        ).all()
        
        if avg_rlm_strength:
            avg_strength = sum(m.rlm_strength for m in avg_rlm_strength) / len(avg_rlm_strength)
        else:
            avg_strength = 0
        
        return {
            "total_games": total_games,
            "rlm_games": rlm_games,
            "rlm_percentage": (rlm_games / total_games * 100) if total_games > 0 else 0,
            "avg_rlm_strength": round(avg_strength, 2)
        }
    finally:
        db.close()
