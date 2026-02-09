"""
HOUSE EDGE - Core Fade Score Algorithm

Philosophy: The house always wins. We bet WITH the house by:
1. Fading extreme public action
2. Following whale/sharp money
3. Detecting reverse line movement
4. Tracking book liability

Fade Score: 0-100
- 80+: 🔴 STRONG FADE (High confidence contrarian play)
- 65-79: 🟠 FADE (Solid fade signal)
- 50-64: 🟡 MONITOR (Weak signal, need confirmation)
- <50: ⚪ NO SIGNAL (Balanced or insufficient data)
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger


@dataclass
class GameData:
    """Data structure for game analysis"""
    game_id: int
    home_team: str
    away_team: str
    sport: str
    
    # Betting splits
    public_ticket_pct: Optional[float] = None  # % of tickets
    public_money_pct: Optional[float] = None   # % of money
    public_side: Optional[str] = None          # "home" or "away"
    
    # Line movement
    opening_line: Optional[float] = None
    current_line: Optional[float] = None
    line_movement_direction: Optional[str] = None
    
    # Sentiment
    social_hype_score: Optional[float] = None  # 0-100
    sentiment_side: Optional[str] = None
    
    # Whale activity
    whale_bets: List[Dict[str, Any]] = None
    
    # Book exposure
    book_liability: Optional[Dict[str, Any]] = None
    

@dataclass
class FadeSignal:
    """Fade signal output"""
    fade_score: float
    signal_type: str  # "STRONG FADE", "FADE", "MONITOR", "NO SIGNAL"
    recommendation: str
    reasoning: List[str]
    factors: Dict[str, Any]
    confidence: float


class FadeScoreCalculator:
    """Calculate fade score for games"""
    
    # Score weights (boosted for better variance)
    WEIGHTS = {
        "extreme_public": 50,      # 95%+ public money
        "reverse_line_movement": 40,
        "whale_confirmation": 35,
        "book_liability": 30,
        "sharp_divergence": 25,    # Tickets vs Money gap
        "prop_overload": 20,
        "signal_multiplier": 1.15  # Boost when multiple signals align
    }
    
    # Thresholds
    EXTREME_PUBLIC_THRESHOLD = 90   # 90%+ = extreme
    HIGH_PUBLIC_THRESHOLD = 85      # 85%+ = high
    MODERATE_PUBLIC_THRESHOLD = 75  # 75%+ = moderate
    
    SHARP_DIVERGENCE_THRESHOLD = 15  # 15%+ gap between tickets and money
    WHALE_MIN_AMOUNT = 10000        # $10K minimum
    
    def calculate_fade_score(self, game: GameData) -> FadeSignal:
        """
        Calculate comprehensive fade score
        
        Args:
            game: Game data to analyze
            
        Returns:
            FadeSignal with score and recommendation
        """
        score = 0
        reasoning = []
        factors = {}
        signal_count = 0
        
        # Signal 1: Extreme Public Load
        if game.public_money_pct:
            public_signal = self._analyze_public_load(game.public_money_pct)
            score += public_signal["score"]
            if public_signal["score"] > 0:
                signal_count += 1
                reasoning.append(public_signal["reason"])
                factors["extreme_public"] = True
                factors["public_money_pct"] = game.public_money_pct
        
        # Signal 2: Sharp Divergence (Tickets vs Money)
        if game.public_ticket_pct and game.public_money_pct:
            divergence_signal = self._analyze_divergence(
                game.public_ticket_pct,
                game.public_money_pct
            )
            score += divergence_signal["score"]
            if divergence_signal["score"] > 0:
                signal_count += 1
                reasoning.append(divergence_signal["reason"])
                factors["sharp_divergence"] = divergence_signal["divergence"]
        
        # Signal 3: Reverse Line Movement
        if game.opening_line and game.current_line and game.public_side:
            rlm_signal = self._analyze_line_movement(
                game.opening_line,
                game.current_line,
                game.public_side,
                game.public_ticket_pct or 0
            )
            score += rlm_signal["score"]
            if rlm_signal["score"] > 0:
                signal_count += 1
                reasoning.append(rlm_signal["reason"])
                factors["reverse_line_movement"] = True
        
        # Signal 4: Whale Confirmation
        if game.whale_bets and game.public_side:
            whale_signal = self._analyze_whale_activity(
                game.whale_bets,
                game.public_side
            )
            score += whale_signal["score"]
            if whale_signal["score"] > 0:
                signal_count += 1
                reasoning.append(whale_signal["reason"])
                factors["whale_confirmation"] = whale_signal["details"]
        
        # Signal 5: Book Liability
        if game.book_liability and game.public_side:
            liability_signal = self._analyze_book_liability(
                game.book_liability,
                game.public_side
            )
            score += liability_signal["score"]
            if liability_signal["score"] > 0:
                signal_count += 1
                reasoning.append(liability_signal["reason"])
                factors["book_liability"] = True
        
        # Signal 6: Social Hype vs Reality
        if game.social_hype_score and game.public_money_pct:
            hype_signal = self._analyze_hype_divergence(
                game.social_hype_score,
                game.public_money_pct
            )
            score += hype_signal["score"]
            if hype_signal["score"] > 0:
                signal_count += 1
                reasoning.append(hype_signal["reason"])
                factors["hype_divergence"] = True
        
        # SIGNAL MULTIPLIER: Multiple signals = exponential confidence boost
        # 2 signals: +15%, 3 signals: +30%, 4+ signals: +45%
        if signal_count >= 4:
            multiplier = 1.45
            factors["signal_convergence"] = "STRONG (4+ signals)"
        elif signal_count >= 3:
            multiplier = 1.30
            factors["signal_convergence"] = "SOLID (3 signals)"
        elif signal_count >= 2:
            multiplier = 1.15
            factors["signal_convergence"] = "MODERATE (2 signals)"
        else:
            multiplier = 1.0
        
        final_score = min(score * multiplier, 100)
        
        # Determine signal type and recommendation
        signal_type, recommendation = self._generate_recommendation(
            final_score,
            game,
            reasoning,
            signal_count
        )
        
        # Calculate confidence (based on number of signals)
        confidence = min((signal_count + 1) / 5, 1.0)  # Max confidence with 4+ signals
        
        return FadeSignal(
            fade_score=final_score,
            signal_type=signal_type,
            recommendation=recommendation,
            reasoning=reasoning,
            factors=factors,
            confidence=confidence
        )
    
    def _analyze_public_load(self, public_money_pct: float) -> Dict[str, Any]:
        """Analyze public money percentage"""
        if public_money_pct >= 95:
            return {
                "score": self.WEIGHTS["extreme_public"],
                "reason": f"🔴 NUCLEAR: {public_money_pct:.0f}% of money on public side"
            }
        elif public_money_pct >= self.EXTREME_PUBLIC_THRESHOLD:
            return {
                "score": self.WEIGHTS["extreme_public"] * 0.75,
                "reason": f"🟠 EXTREME: {public_money_pct:.0f}% of money on public side"
            }
        elif public_money_pct >= self.HIGH_PUBLIC_THRESHOLD:
            return {
                "score": self.WEIGHTS["extreme_public"] * 0.5,
                "reason": f"🟡 HIGH PUBLIC: {public_money_pct:.0f}% of money on public side"
            }
        else:
            return {"score": 0, "reason": ""}
    
    def _analyze_divergence(
        self,
        ticket_pct: float,
        money_pct: float
    ) -> Dict[str, Any]:
        """Analyze ticket vs money divergence"""
        divergence = ticket_pct - money_pct
        
        if divergence >= 20:
            return {
                "score": self.WEIGHTS["sharp_divergence"],
                "reason": f"📊 SHARP DIVERGENCE: {divergence:.0f}% gap (more tickets than money)",
                "divergence": divergence
            }
        elif divergence >= self.SHARP_DIVERGENCE_THRESHOLD:
            return {
                "score": self.WEIGHTS["sharp_divergence"] * 0.6,
                "reason": f"📊 Divergence: {divergence:.0f}% gap indicates sharp action opposite side",
                "divergence": divergence
            }
        else:
            return {"score": 0, "reason": "", "divergence": divergence}
    
    def _analyze_line_movement(
        self,
        opening_line: float,
        current_line: float,
        public_side: str,
        public_pct: float
    ) -> Dict[str, Any]:
        """Analyze reverse line movement"""
        # Determine expected direction based on public
        if public_pct > 60:  # Clear public side
            if public_side == "home":
                expected_direction = "down"  # Line should move toward favorite
            else:
                expected_direction = "up"
        else:
            return {"score": 0, "reason": ""}
        
        # Actual direction
        line_change = current_line - opening_line
        if line_change > 0.5:
            actual_direction = "up"
        elif line_change < -0.5:
            actual_direction = "down"
        else:
            return {"score": 0, "reason": ""}
        
        # Detect reverse movement
        if expected_direction != actual_direction:
            return {
                "score": self.WEIGHTS["reverse_line_movement"],
                "reason": f"📈 RLM DETECTED: Line moved {actual_direction} despite {public_pct:.0f}% public action"
            }
        
        return {"score": 0, "reason": ""}
    
    def _analyze_whale_activity(
        self,
        whale_bets: List[Dict[str, Any]],
        public_side: str
    ) -> Dict[str, Any]:
        """Analyze whale bet activity"""
        if not whale_bets:
            return {"score": 0, "reason": "", "details": []}
        
        # Check for whales betting opposite of public
        contrarian_whales = []
        total_contrarian_amount = 0
        
        for whale in whale_bets:
            whale_side = whale.get("side", "")
            if whale_side and whale_side != public_side:
                contrarian_whales.append(whale)
                total_contrarian_amount += whale.get("amount", 0)
        
        if contrarian_whales:
            max_whale = max(contrarian_whales, key=lambda x: x.get("amount", 0))
            amount = max_whale.get("amount", 0)
            
            if amount >= 100000:  # $100K+ mega whale
                score = self.WEIGHTS["whale_confirmation"]
                reason = f"🐋 MEGA WHALE: ${amount:,.0f} bet AGAINST public"
            elif amount >= 50000:  # $50K+ large whale
                score = self.WEIGHTS["whale_confirmation"] * 0.8
                reason = f"🐋 WHALE FADE: ${amount:,.0f} against public"
            else:
                score = self.WEIGHTS["whale_confirmation"] * 0.6
                reason = f"🐋 Whale activity: ${total_contrarian_amount:,.0f} against public"
            
            return {
                "score": score,
                "reason": reason,
                "details": contrarian_whales
            }
        
        return {"score": 0, "reason": "", "details": []}
    
    def _analyze_book_liability(
        self,
        liability: Dict[str, Any],
        public_side: str
    ) -> Dict[str, Any]:
        """Analyze sportsbook liability"""
        exposed_side = liability.get("exposed_side", "")
        amount = liability.get("exposure_amount", 0)
        
        if exposed_side == public_side and amount > 0:
            return {
                "score": self.WEIGHTS["book_liability"],
                "reason": f"🏦 BOOK EXPOSED: Sportsbook at risk on public side"
            }
        
        return {"score": 0, "reason": ""}
    
    def _analyze_hype_divergence(
        self,
        hype_score: float,
        money_pct: float
    ) -> Dict[str, Any]:
        """Analyze social hype vs actual money"""
        # If high social hype but money isn't following
        if hype_score > 80 and money_pct < 70:
            return {
                "score": 10,
                "reason": f"📱 HYPE vs REALITY: High social hype ({hype_score:.0f}) but only {money_pct:.0f}% of money"
            }
        
        return {"score": 0, "reason": ""}
    
    def _generate_recommendation(
        self,
        score: float,
        game: GameData,
        reasoning: List[str],
        signal_count: int = 1
    ) -> tuple[str, str]:
        """Generate recommendation based on score"""
        if score >= 80:
            signal_type = "STRONG FADE"
            fade_side = "away" if game.public_side == "home" else "home"
            fade_team = game.away_team if game.public_side == "home" else game.home_team
            confidence_msg = f"({signal_count} confirming signals)" if signal_count >= 3 else "(Multiple signal confirms)"
            recommendation = (
                f"🔴 STRONG FADE SIGNAL {confidence_msg}\n\n"
                f"Public: {game.public_side.upper()} ({game.public_money_pct:.0f}% of money)\n"
                f"Recommendation: BET {fade_team.upper()} ({fade_side.upper()})\n\n"
                f"High-confidence contrarian opportunity - Multiple market signals align."
            )
        elif score >= 65:
            signal_type = "FADE"
            fade_side = "away" if game.public_side == "home" else "home"
            fade_team = game.away_team if game.public_side == "home" else game.home_team
            confidence_msg = f"({signal_count} signals)" if signal_count >= 2 else "(Confirmed)"
            recommendation = (
                f"🟠 FADE SIGNAL {confidence_msg}\n\n"
                f"Public: {game.public_side.upper()}\n"
                f"Consider: BET {fade_team.upper()}\n\n"
                f"Solid fade opportunity with confirming signals."
            )
        elif score >= 50:
            signal_type = "MONITOR"
            recommendation = (
                f"🟡 MONITOR\n\n"
                f"Weak fade signal ({signal_count} signal detected). Need additional confirmation.\n"
                f"Watch for: Line movement, whale activity, or sharper divergence."
            )
        else:
            signal_type = "NO SIGNAL"
            recommendation = (
                f"⚪ NO SIGNAL\n\n"
                f"Balanced or insufficient data. No clear contrarian opportunity."
            )
        
        return signal_type, recommendation
