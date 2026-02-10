"""
HOUSE EDGE - FastAPI Application

Main entry point for the API
"""

from fastapi import FastAPI, Depends, HTTPException, status, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from loguru import logger
import time
import os
from collections import defaultdict

from database import get_db, init_db, Game, Signal, WhaleBet, Sport
from scheduler.jobs import start_scheduler
from events.bus import bus
from fastapi.responses import StreamingResponse
import asyncio
import json
from config import get_settings

# Initialize settings
settings = get_settings()

# ── API Key Auth ──────────────────────────────────────────────────────
API_KEY = os.getenv("HOUSE_EDGE_API_KEY", "")  # Set in .env for production

# ── Rate Limiting ─────────────────────────────────────────────────────
RATE_LIMIT_WINDOW = 60   # seconds
RATE_LIMIT_MAX = 60      # requests per window
_rate_store: dict = defaultdict(list)  # ip -> [timestamps]

# Create FastAPI app
app = FastAPI(
    title="HOUSE EDGE API",
    description="Anti-Public Sports Betting Intelligence System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware — locked to known origins
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ── Security Middleware ───────────────────────────────────────────────

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Rate limiting + API key enforcement on write endpoints."""
    client_ip = request.client.host if request.client else "unknown"

    # 1. Rate limiting
    now = time.time()
    _rate_store[client_ip] = [
        t for t in _rate_store[client_ip] if t > now - RATE_LIMIT_WINDOW
    ]
    if len(_rate_store[client_ip]) >= RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )
    _rate_store[client_ip].append(now)

    # 2. API key enforcement on mutation endpoints
    if request.method == "POST" and API_KEY:
        api_key = request.headers.get("X-API-Key", "")
        if api_key != API_KEY:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing API key."},
            )

    # 3. Security headers
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("Starting HOUSE EDGE API...")
    
    # Initialize database
    try:
        init_db()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")

    # Set event loop for sync publishing
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        bus.set_loop(loop)
        logger.info("✓ Event bus configured")
    except Exception as e:
        logger.error(f"✗ Event bus configuration failed: {e}")

    # Start background scheduler (ESPN sync, odds collection, RLM)
    try:
        start_scheduler()
        logger.info("✓ Background scheduler started (ESPN sync every 1m)")
    except Exception as e:
        logger.error(f"✗ Scheduler start failed: {e}")


@app.get("/events/games")
async def sse_games_events():
    """Server-Sent Events stream for game status updates."""
    async def event_generator():
        q = await bus.subscribe()
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await bus.unsubscribe(q)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/events/test-publish")
async def test_publish_event(payload: dict = Body(default={})):
    """Publish a test event into the SSE bus (for diagnostics)."""
    event = {
        "type": "diagnostic",
        "message": payload.get("message", "hello"),
        "timestamp": datetime.utcnow().isoformat()
    }
    logger.info(f"test-publish: Publishing event={event}")
    await bus.publish(event)
    logger.info(f"test-publish: Event published successfully")
    return {"ok": True, "published": event}


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down HOUSE EDGE API...")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "HOUSE EDGE API",
        "version": "1.0.0",
        "status": "running",
        "message": "The House Always Wins"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/games/live")
async def get_live_games(db: Session = Depends(get_db)):
    """
    Get LIVE and TODAY's games with real-time status
    Returns: scheduled, in_progress, and final games
    """
    try:
        now = datetime.utcnow()
        today = now.date()
        
        # Get all games from today
        games = db.query(Game).filter(
            Game.game_time >= datetime.combine(today, datetime.min.time()),
            Game.game_time <= datetime.combine(today + timedelta(days=1), datetime.max.time())
        ).order_by(Game.game_time.asc()).all()
        
        result = {
            "total": len(games),
            "scheduled": [],
            "live": [],
            "final": []
        }
        
        for game in games:
            game_dict = {
                "id": game.id,
                "sport": game.sport.value if hasattr(game.sport, 'value') else str(game.sport),
                "away_team": game.away_team,
                "home_team": game.home_team,
                "game_time": game.game_time.isoformat() if game.game_time else None,
                "status": game.status or "scheduled",
                "espn_id": game.espn_id,
                "venue": game.venue
            }
            
            status = (game.status or "scheduled").lower()
            if status in ["in_progress", "live"]:
                result["live"].append(game_dict)
            elif status in ["final", "completed"]:
                result["final"].append(game_dict)
            else:
                result["scheduled"].append(game_dict)
        
        logger.info(f"🔴 LIVE: {len(result['live'])} | 🟢 SCHEDULED: {len(result['scheduled'])} | ✅ FINAL: {len(result['final'])}")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching live games: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/games/upcoming")
async def get_upcoming_games(
    sport: Sport = None,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """
    Get upcoming games
    
    Args:
        sport: Filter by sport
        hours: Hours ahead to look
        db: Database session
    """
    try:
        query = db.query(Game).filter(
            Game.game_time >= datetime.utcnow(),
            Game.game_time <= datetime.utcnow() + timedelta(hours=hours),
            Game.status == "scheduled"
        )
        
        if sport:
            query = query.filter(Game.sport == sport)
        
        games = query.order_by(Game.game_time).all()
        
        return {
            "count": len(games),
            "games": [
                {
                    "id": game.id,
                    "sport": game.sport.value,
                    "away_team": game.away_team,
                    "home_team": game.home_team,
                    "game_time": game.game_time.isoformat(),
                    "venue": game.venue
                }
                for game in games
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching upcoming games: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/games/all")
async def get_all_games(
    days_ahead: int = 7,
    db: Session = Depends(get_db)
):
    """
    Get TODAY's games and upcoming games (refreshes daily automatically)
    
    Args:
        days_ahead: Number of days ahead to fetch (default 7)
        db: Database session
    """
    try:
        # Get games from today onwards (next X days)
        today = datetime.utcnow().date()
        end_date = today + timedelta(days=days_ahead)
        
        games = db.query(Game).filter(
            Game.game_time >= today,
            Game.game_time <= end_date
        ).order_by(Game.game_time.asc()).all()
        
        logger.info(f"Fetching games from {today} to {end_date}: Found {len(games)} games")
        
        return [
            {
                "id": game.id,
                "sport": game.sport if hasattr(game, 'sport') else 'NFL',
                "away_team": game.away_team,
                "home_team": game.home_team,
                "game_date": game.game_time.isoformat() if game.game_time else None,
                "spread": game.spread if hasattr(game, 'spread') else None,
                "status": game.status if hasattr(game, 'status') else 'scheduled'
            }
            for game in games
        ]
    except Exception as e:
        logger.error(f"Error fetching all games: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signals/active")
async def get_active_signals(
    min_score: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get active fade signals (ONLY scheduled games)
    
    Args:
        min_score: Minimum fade score
        db: Database session
    """
    try:
        signals = db.query(Signal).join(Game).filter(
            Signal.fade_score >= min_score,
            Signal.expires_at >= datetime.utcnow(),
            Game.status == "scheduled"
        ).order_by(Signal.fade_score.desc()).all()
        
        return {
            "count": len(signals),
            "signals": [
                {
                    "id": signal.id,
                    "game_id": signal.game_id,
                    "game": {
                        "away_team": signal.game.away_team,
                        "home_team": signal.game.home_team,
                        "sport": signal.game.sport.value,
                        "game_time": signal.game.game_time.isoformat()
                    },
                    "fade_score": signal.fade_score,
                    "signal_type": signal.signal_type.value,
                    "confidence": signal.confidence,
                    "recommendation": signal.recommendation,
                    "factors": signal.factors,
                    "generated_at": signal.generated_at.isoformat()
                }
                for signal in signals
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signals/{game_id}")
async def get_signals_for_game(
    game_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all signals for a specific game
    
    Args:
        game_id: Game ID
        db: Database session
    """
    try:
        signals = db.query(Signal).filter(Signal.game_id == game_id).all()
        
        return [
            {
                "id": signal.id,
                "game_id": signal.game_id,
                "signal_type": signal.signal_type,
                "fade_score": signal.fade_score,
                "confidence": signal.confidence,
                "public_money_pct": signal.public_money_pct if hasattr(signal, 'public_money_pct') else 50,
                "reasoning": signal.reasoning if hasattr(signal, 'reasoning') else None
            }
            for signal in signals
        ]
    except Exception as e:
        logger.error(f"Error fetching signals for game {game_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signals-top")
async def get_top_signals(
    limit: int = 10,
    min_score: float = 0,
    db: Session = Depends(get_db)
):
    """
    Get top fade signals by score
    
    Args:
        limit: Maximum number of signals
        min_score: Minimum fade score filter (e.g., 60 for TIER 1)
        db: Database session
    """
    try:
        query = db.query(Signal).join(Game).filter(
            Signal.expires_at >= datetime.utcnow(),
            Game.status == "scheduled",
            Game.game_time > datetime.utcnow()  # Only future games
        )
        
        if min_score > 0:
            query = query.filter(Signal.fade_score >= min_score)
        
        signals = query.order_by(Signal.fade_score.desc()).limit(limit).all()
        
        return [
            {
                "id": signal.id,
                "game_id": signal.game_id,
                "game": {
                    "away_team": signal.game.away_team,
                    "home_team": signal.game.home_team,
                    "sport": signal.game.sport.value,
                    "game_time": signal.game.game_time.isoformat(),
                    "status": signal.game.status
                },
                "fade_score": signal.fade_score,
                "confidence": signal.confidence,
                "signal_type": signal.signal_type.value,
                "recommendation": signal.recommendation,
                "reasoning": signal.reasoning,
                "public_money_pct": float(signal.reasoning.split("Public Money: ")[1].split("%")[0]) if signal.reasoning and "Public Money: " in signal.reasoning else 50,
                "generated_at": signal.generated_at.isoformat()
            }
            for signal in signals
        ]
    except Exception as e:
        logger.error(f"Error fetching top signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/whales/recent")
async def get_recent_whales(
    min_amount: int = 10000,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """
    Get recent whale bets
    
    Args:
        min_amount: Minimum bet amount
        hours: Hours to look back
        db: Database session
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        whales = db.query(WhaleBet).filter(
            WhaleBet.amount >= min_amount,
            WhaleBet.detected_at >= cutoff_time
        ).order_by(WhaleBet.amount.desc()).all()
        
        return {
            "count": len(whales),
            "total_amount": sum(w.amount for w in whales),
            "whales": [
                {
                    "id": whale.id,
                    "amount": whale.amount,
                    "selection": whale.selection,
                    "odds": whale.odds,
                    "potential_payout": whale.potential_payout,
                    "source": whale.source,
                    "verified": whale.verified,
                    "detected_at": whale.detected_at.isoformat()
                }
                for whale in whales
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching whales: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get system statistics"""
    try:
        total_games = db.query(Game).count()
        active_signals = db.query(Signal).filter(
            Signal.expires_at >= datetime.utcnow()
        ).count()
        total_whales = db.query(WhaleBet).count()
        
        strong_signals = db.query(Signal).filter(
            Signal.fade_score >= 80,
            Signal.expires_at >= datetime.utcnow()
        ).count()
        
        return {
            "total_games": total_games,
            "active_signals": active_signals,
            "strong_signals": strong_signals,
            "total_whales": total_whales,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# RLM (Reverse Line Movement) Detection Endpoints
@app.post("/rlm/detect")
async def detect_rlm(db: Session = Depends(get_db)):
    """
    Detect reverse line movement for all active games
    """
    try:
        from logic.line_movement_detector import detect_rlm_for_game
        
        # Get all scheduled games
        games = db.query(Game).filter(Game.status == "SCHEDULED").all()
        
        rlm_detections = []
        for game in games:
            rlm = detect_rlm_for_game(game.id)
            if rlm and rlm.is_rlm:
                rlm_detections.append({
                    "game_id": game.id,
                    "home_team": game.home_team,
                    "away_team": game.away_team,
                    "opening_spread": rlm.opening_spread,
                    "current_spread": rlm.current_spread,
                    "spread_movement": rlm.spread_movement,
                    "rlm_strength": rlm.rlm_strength,
                    "is_rlm": rlm.is_rlm
                })
        
        return {
            "total_games_checked": len(games),
            "rlm_detected": len(rlm_detections),
            "detections": rlm_detections,
            "detected_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error detecting RLM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rlm/generate-signals")
async def generate_rlm_signals(db: Session = Depends(get_db)):
    """
    Generate fade signals based on detected RLM
    """
    try:
        from logic.line_movement_detector import generate_rlm_signals
        
        signals_created = generate_rlm_signals()
        
        return {
            "signals_created": signals_created,
            "generated_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error generating RLM signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rlm/stats")
async def get_rlm_stats(db: Session = Depends(get_db)):
    """
    Get RLM detection statistics
    """
    try:
        from logic.line_movement_detector import get_rlm_stats
        
        stats = get_rlm_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting RLM stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD
    )
