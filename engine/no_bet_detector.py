#!/usr/bin/env python3
"""
NO-BET DETECTOR — Coin-Flip Filter
===================================
Identifies games with NO actionable edge and explicitly marks them as NO-BET.

The best bet is sometimes NO BET. This module filters out coin-flip games where:
  - Public action is balanced (no lopsided betting)
  - Line movement is minimal (no sharp action)
  - Books are in consensus (no disagreement)
  - No primary signals detected
  - Moneyline odds are tight across books

Detection Criteria:
  - All public %s within 45-55% (no lopsided action)
  - Line movement < 0.5 pts from open (no sharp action)
  - Book disagreement < 1.0 pts (market consensus)
  - No primary signals detected
  - ML odds within ±20 of each other across books

Usage:
    from engine.no_bet_detector import NoBetDetector
    detector = NoBetDetector()
    result = detector.detect(game_data)
    if result.is_no_bet:
        print(result.recommendation)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NoBetResult:
    """Result of no-bet detection for a game."""
    game_key: str
    is_no_bet: bool
    reasons: List[str] = field(default_factory=list)
    recommendation: str = ""
    confidence: float = 0.0  # How confident we are it's a coin flip (0-100)
    
    def to_dict(self) -> Dict:
        return {
            "game_key": self.game_key,
            "is_no_bet": self.is_no_bet,
            "reasons": self.reasons,
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 1),
        }


class NoBetDetector:
    """
    Detects games that are coin flips with no actionable edge.
    
    Philosophy: "The best bet is sometimes no bet."
    When the market is efficient and balanced, respect it.
    """
    
    # Thresholds for coin-flip detection
    PUBLIC_PCT_MIN = 45  # Public % must be between 45-55%
    PUBLIC_PCT_MAX = 55
    
    LINE_MOVEMENT_MAX = 0.5  # Line moved less than 0.5 pts from open
    
    BOOK_DISAGREEMENT_MAX = 1.0  # Books agree within 1.0 pt
    
    ML_ODDS_RANGE_MAX = 20  # Moneyline odds within ±20 across books
    
    def detect(
        self,
        game_key: str,
        spread_data: Optional[Dict] = None,
        total_data: Optional[Dict] = None,
        public_data: Optional[Dict] = None,
        book_data: Optional[Dict] = None,
        ml_data: Optional[Dict] = None,
        has_primary_signal: bool = False,
    ) -> NoBetResult:
        """
        Detect if a game is a no-bet coin flip.
        
        Args:
            game_key: "CHI @ BKN" etc.
            spread_data: {"open": -3, "current": -3.5, "public_pct": 52}
            total_data: {"open": 223.5, "current": 223.0, "over_pct": 48}
            public_data: {"spread_fav_pct": 52, "total_over_pct": 48}
            book_data: {"spread_range": 0.5, "total_range": 1.0}
            ml_data: {"home_best": -120, "home_worst": -135, "away_best": +110, "away_worst": +100}
            has_primary_signal: True if any primary signal was detected
        
        Returns:
            NoBetResult with is_no_bet flag and reasons
        """
        reasons = []
        coin_flip_score = 0  # Higher score = more coin-flippy
        
        # ── Check 1: Primary Signal Already Detected ──────────────
        if has_primary_signal:
            # If there's a primary signal, it's NOT a no-bet
            return NoBetResult(
                game_key=game_key,
                is_no_bet=False,
                reasons=["Primary signal detected — game has actionable edge"],
                recommendation="Proceed with signal-based analysis",
                confidence=0,
            )
        
        # ── Check 2: Public Action Balance ────────────────────────
        if public_data:
            spread_pct = public_data.get("spread_fav_pct", 50)
            total_over_pct = public_data.get("total_over_pct", 50)
            
            if self.PUBLIC_PCT_MIN <= spread_pct <= self.PUBLIC_PCT_MAX:
                reasons.append(f"Spread public balanced: {spread_pct:.0f}% (no lopsided action)")
                coin_flip_score += 25
            
            if self.PUBLIC_PCT_MIN <= total_over_pct <= self.PUBLIC_PCT_MAX:
                reasons.append(f"Total public balanced: {total_over_pct:.0f}% Over (no sharp lean)")
                coin_flip_score += 25
        
        # ── Check 3: Minimal Line Movement ────────────────────────
        if spread_data:
            open_spread = spread_data.get("open")
            current_spread = spread_data.get("current")
            
            if open_spread is not None and current_spread is not None:
                movement = abs(current_spread - open_spread)
                if movement < self.LINE_MOVEMENT_MAX:
                    reasons.append(f"Spread moved only {movement:.1f}pts from open (no sharp action)")
                    coin_flip_score += 20
        
        if total_data:
            open_total = total_data.get("open")
            current_total = total_data.get("current")
            
            if open_total is not None and current_total is not None:
                movement = abs(current_total - open_total)
                if movement < self.LINE_MOVEMENT_MAX:
                    reasons.append(f"Total moved only {movement:.1f}pts from open (no sharp action)")
                    coin_flip_score += 20
        
        # ── Check 4: Book Consensus ────────────────────────────────
        if book_data:
            spread_range = book_data.get("spread_range", 0)
            total_range = book_data.get("total_range", 0)
            
            if spread_range < self.BOOK_DISAGREEMENT_MAX:
                reasons.append(f"Books in consensus on spread: {spread_range:.1f}pt range")
                coin_flip_score += 15
            
            if total_range < self.BOOK_DISAGREEMENT_MAX:
                reasons.append(f"Books in consensus on total: {total_range:.1f}pt range")
                coin_flip_score += 15
        
        # ── Check 5: Tight Moneyline Odds ─────────────────────────
        if ml_data:
            home_best = ml_data.get("home_best", 0)
            home_worst = ml_data.get("home_worst", 0)
            away_best = ml_data.get("away_best", 0)
            away_worst = ml_data.get("away_worst", 0)
            
            home_range = abs(home_best - home_worst)
            away_range = abs(away_best - away_worst)
            
            if home_range <= self.ML_ODDS_RANGE_MAX and away_range <= self.ML_ODDS_RANGE_MAX:
                reasons.append(f"Tight ML odds: Home ±{home_range:.0f}, Away ±{away_range:.0f}")
                coin_flip_score += 15
        
        # ── Determine if it's a NO-BET ─────────────────────────────
        # Need at least 3 coin-flip indicators (score >= 60) to mark as NO-BET
        is_no_bet = coin_flip_score >= 60
        
        if is_no_bet:
            recommendation = (
                f"NO BET — This game is a coin flip with no edge. "
                f"Market is efficient and balanced. "
                f"Respect the consensus and sit this one out. "
                f"'No bet IS a bet.'"
            )
        else:
            recommendation = "Proceed with analysis — game may have actionable opportunities"
        
        return NoBetResult(
            game_key=game_key,
            is_no_bet=is_no_bet,
            reasons=reasons,
            recommendation=recommendation,
            confidence=coin_flip_score,
        )


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 70)
    print("  NO-BET DETECTOR — Coin-Flip Filter Demo")
    print("═" * 70)
    
    detector = NoBetDetector()
    
    # Demo 1: Clear coin flip — everything balanced
    print("\n  Demo 1: Textbook Coin Flip")
    result1 = detector.detect(
        game_key="LAL @ PHX",
        spread_data={"open": -3.0, "current": -3.0, "public_pct": 51},
        total_data={"open": 225.5, "current": 225.5, "over_pct": 49},
        public_data={"spread_fav_pct": 51, "total_over_pct": 49},
        book_data={"spread_range": 0.5, "total_range": 0.5},
        ml_data={"home_best": -150, "home_worst": -155, "away_best": +135, "away_worst": +130},
        has_primary_signal=False,
    )
    
    print(f"  Game: {result1.game_key}")
    print(f"  NO-BET: {result1.is_no_bet} (confidence: {result1.confidence:.0f}%)")
    print(f"  Reasons:")
    for r in result1.reasons:
        print(f"    • {r}")
    print(f"  Recommendation: {result1.recommendation}")
    
    # Demo 2: Clear edge — lopsided public + line movement
    print("\n  Demo 2: Game with Edge (NOT a No-Bet)")
    result2 = detector.detect(
        game_key="CHI @ BKN",
        spread_data={"open": -2.5, "current": -4.0, "public_pct": 72},
        total_data={"open": 223.5, "current": 218.5, "over_pct": 68},
        public_data={"spread_fav_pct": 72, "total_over_pct": 68},
        book_data={"spread_range": 2.0, "total_range": 2.5},
        ml_data={"home_best": -180, "home_worst": -220, "away_best": +170, "away_worst": +150},
        has_primary_signal=True,
    )
    
    print(f"  Game: {result2.game_key}")
    print(f"  NO-BET: {result2.is_no_bet} (confidence: {result2.confidence:.0f}%)")
    print(f"  Reasons:")
    for r in result2.reasons:
        print(f"    • {r}")
    print(f"  Recommendation: {result2.recommendation}")
    
    # Demo 3: Edge case — balanced but has movement
    print("\n  Demo 3: Balanced Public but Line Moved")
    result3 = detector.detect(
        game_key="MIL @ ORL",
        spread_data={"open": +10.5, "current": +12.0, "public_pct": 50},
        total_data={"open": 220.0, "current": 220.0, "over_pct": 52},
        public_data={"spread_fav_pct": 50, "total_over_pct": 52},
        book_data={"spread_range": 0.5, "total_range": 0.5},
        ml_data={"home_best": -450, "home_worst": -480, "away_best": +360, "away_worst": +340},
        has_primary_signal=False,
    )
    
    print(f"  Game: {result3.game_key}")
    print(f"  NO-BET: {result3.is_no_bet} (confidence: {result3.confidence:.0f}%)")
    print(f"  Reasons:")
    for r in result3.reasons:
        print(f"    • {r}")
    print(f"  Recommendation: {result3.recommendation}")
    
    print("\n" + "═" * 70)
