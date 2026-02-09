"""Database models for HOUSE EDGE system"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, JSON, Text, Enum as SQLEnum, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum


Base = declarative_base()


class BetType(str, enum.Enum):
    """Bet type enumeration"""
    SPREAD = "spread"
    MONEYLINE = "moneyline"
    TOTALS = "totals"
    PLAYER_PROP = "player_prop"
    TEAM_PROP = "team_prop"
    GAME_PROP = "game_prop"


class SignalType(str, enum.Enum):
    """Signal type enumeration"""
    FADE = "fade"
    FOLLOW = "follow"
    HOLD = "hold"


class Sport(str, enum.Enum):
    """Supported sports"""
    NFL = "NFL"
    NBA = "NBA"
    SOCCER = "SOCCER"
    MLB = "MLB"
    NHL = "NHL"


class Game(Base):
    """Game/Match model"""
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True)
    sport = Column(SQLEnum(Sport), nullable=False, index=True)
    league = Column(String(50), nullable=False)
    
    # Teams
    home_team = Column(String(100), nullable=False)
    away_team = Column(String(100), nullable=False)
    
    # Game info
    game_time = Column(DateTime, nullable=False, index=True)
    venue = Column(String(200))
    
    # ESPN tracking
    espn_id = Column(String(50), unique=True, index=True)  # ESPN's unique game ID
    espn_status = Column(String(50))  # ESPN's raw status (STATUS_SCHEDULED, STATUS_IN_PROGRESS, STATUS_FINAL, etc)
    
    # Status: scheduled (future) | live (in_progress) | completed (final)
    status = Column(String(20), default="scheduled", index=True)
    status_last_checked = Column(DateTime)  # When we last checked ESPN for status
    
    # Live scores (from ESPN API)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    odds = relationship("OddsSnapshot", back_populates="game", cascade="all, delete-orphan")
    odds_history = relationship("OddsHistory", back_populates="game", cascade="all, delete-orphan")
    betting_splits = relationship("BettingSplit", back_populates="game", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="game", cascade="all, delete-orphan")
    whale_bets = relationship("WhaleBet", back_populates="game", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_game_time_sport", "game_time", "sport"),
    )
    
    def __repr__(self):
        return f"<Game {self.away_team} @ {self.home_team} ({self.game_time})>"


class OddsSnapshot(Base):
    """Odds snapshot at a point in time"""
    __tablename__ = "odds_snapshots"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    # Sportsbook
    sportsbook = Column(String(50), nullable=False)
    
    # Odds
    home_spread = Column(Float)
    home_spread_odds = Column(Integer)
    away_spread = Column(Float)
    away_spread_odds = Column(Integer)
    
    home_ml = Column(Integer)
    away_ml = Column(Integer)
    
    total = Column(Float)
    over_odds = Column(Integer)
    under_odds = Column(Integer)
    
    # Metadata
    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    game = relationship("Game", back_populates="odds")
    
    __table_args__ = (
        Index("idx_odds_game_time", "game_id", "snapshot_time"),
    )
    
    def __repr__(self):
        return f"<OddsSnapshot {self.sportsbook} - Game {self.game_id}>"


class OddsHistory(Base):
    """Full odds history to preserve 5-minute snapshots for RLM/divergence detection"""
    __tablename__ = "odds_history"

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)

    sportsbook = Column(String(50), nullable=False)

    home_spread = Column(Float)
    home_spread_odds = Column(Integer)
    away_spread = Column(Float)
    away_spread_odds = Column(Integer)

    home_ml = Column(Integer)
    away_ml = Column(Integer)

    total = Column(Float)
    over_odds = Column(Integer)
    under_odds = Column(Integer)

    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)

    game = relationship("Game", back_populates="odds_history")

    __table_args__ = (
        Index("idx_odds_history_game_time", "game_id", "snapshot_time"),
    )

    def __repr__(self):
        return f"<OddsHistory {self.sportsbook} - Game {self.game_id}>"


class BettingSplit(Base):
    """Betting split data (public vs sharp)"""
    __tablename__ = "betting_splits"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    bet_type = Column(SQLEnum(BetType), nullable=False)
    
    # Ticket percentages (number of bets)
    home_ticket_pct = Column(Float)
    away_ticket_pct = Column(Float)
    over_ticket_pct = Column(Float)
    under_ticket_pct = Column(Float)
    
    # Money percentages (dollar amount)
    home_money_pct = Column(Float)
    away_money_pct = Column(Float)
    over_money_pct = Column(Float)
    under_money_pct = Column(Float)
    
    # Source
    source = Column(String(100))  # "action_network", "covers", "br_betting"
    
    # Metadata
    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    game = relationship("Game", back_populates="betting_splits")
    
    __table_args__ = (
        Index("idx_split_game_time", "game_id", "snapshot_time"),
    )
    
    def __repr__(self):
        return f"<BettingSplit Game {self.game_id} - {self.bet_type}>"


class LineMovement(Base):
    """Track line movement to detect RLM (Reverse Line Movement) and sharp money"""
    __tablename__ = "line_movements"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    # Opening vs current line
    opening_spread = Column(Float)
    current_spread = Column(Float)
    spread_movement = Column(Float)  # current - opening (positive = moved toward away, negative = toward home)
    
    opening_ml_home = Column(Integer)
    current_ml_home = Column(Integer)
    
    opening_ml_away = Column(Integer)
    current_ml_away = Column(Integer)
    
    # RLM Detection (Line Moved Opposite to Public)
    public_favored_side = Column(String(20))  # "home" or "away" (where consensus bets)
    line_moved_to = Column(String(20))  # "home" or "away" (which direction line moved)
    is_rlm = Column(Boolean, default=False)  # True if line moved opposite to public
    rlm_strength = Column(Float)  # How many points against public (higher = stronger signal)
    
    # Timestamps
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    game = relationship("Game")
    
    __table_args__ = (
        Index("idx_line_movement_game", "game_id", "detected_at"),
    )
    
    def __repr__(self):
        return f"<LineMovement Game {self.game_id} RLM={self.is_rlm} strength={self.rlm_strength}>"


class WhaleBet(Base):
    """Large bet (whale) tracking"""
    __tablename__ = "whale_bets"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True, index=True)
    
    # Bet details
    amount = Column(Float, nullable=False, index=True)
    bet_type = Column(SQLEnum(BetType), nullable=False)
    selection = Column(String(200), nullable=False)  # "Cardinals ML", "Over 45.5"
    odds = Column(Integer)
    potential_payout = Column(Float)
    
    # Source
    source = Column(String(100))  # "twitter", "instagram", "blockchain"
    source_url = Column(Text)
    source_post_id = Column(String(100))
    
    # Verification
    verified = Column(Boolean, default=False)
    fake_slip_score = Column(Float)  # 0-1 probability of being fake
    
    # Metadata
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    bet_timestamp = Column(DateTime)
    
    # Relationships
    game = relationship("Game", back_populates="whale_bets")
    
    __table_args__ = (
        Index("idx_whale_amount_time", "amount", "detected_at"),
    )
    
    def __repr__(self):
        return f"<WhaleBet ${self.amount:,.0f} on {self.selection}>"


class Signal(Base):
    """Generated betting signals"""
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    # Signal details
    signal_type = Column(SQLEnum(SignalType), nullable=False)
    fade_score = Column(Float, nullable=False, index=True)
    confidence = Column(Float)  # 0-1
    
    # Recommendation
    recommendation = Column(Text, nullable=False)
    reasoning = Column(Text)
    
    # Contributing factors (JSON)
    factors = Column(JSON)  # {"extreme_public": true, "whale_confirmation": true, ...}
    
    # Alert status
    alert_sent = Column(Boolean, default=False)
    alert_channels = Column(JSON)  # ["discord", "sms", "email"]
    
    # Metadata
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime)
    
    # Relationships
    game = relationship("Game", back_populates="signals")
    
    __table_args__ = (
        Index("idx_signal_score_time", "fade_score", "generated_at"),
    )
    
    def __repr__(self):
        return f"<Signal {self.signal_type} - Score {self.fade_score}>"


class SocialSentiment(Base):
    """Social media sentiment tracking"""
    __tablename__ = "social_sentiment"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True, index=True)
    
    # Platform
    platform = Column(String(50), nullable=False)  # "twitter", "instagram", "reddit"
    
    # Sentiment
    public_side = Column(String(100))  # "home", "away", "over", "under"
    sentiment_score = Column(Float)  # 0-100
    hype_level = Column(Float)  # 0-100
    
    # Metrics
    mention_count = Column(Integer)
    positive_mentions = Column(Integer)
    negative_mentions = Column(Integer)
    
    # Notable posts
    top_posts = Column(JSON)  # List of influential posts
    
    # Metadata
    analyzed_at = Column(DateTime, default=datetime.utcnow, index=True)
    analysis_window_start = Column(DateTime)
    analysis_window_end = Column(DateTime)
    
    __table_args__ = (
        Index("idx_sentiment_game_time", "game_id", "analyzed_at"),
    )
    
    def __repr__(self):
        return f"<SocialSentiment {self.platform} - Game {self.game_id}>"


class BookLiability(Base):
    """Sportsbook liability/exposure tracking"""
    __tablename__ = "book_liabilities"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True, index=True)
    
    # Book
    sportsbook = Column(String(50), nullable=False)
    
    # Exposure
    exposed_side = Column(String(100), nullable=False)
    exposure_amount = Column(Float)  # Dollar amount at risk
    
    # Source
    source = Column(String(100))
    source_url = Column(Text)
    
    # Metadata
    reported_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<BookLiability {self.sportsbook} - ${self.exposure_amount:,.0f}>"
