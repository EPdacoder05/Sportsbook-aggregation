"""
RLM (Reverse Line Movement) Detector
=====================================
Detects sharp money signals by analyzing line movements against public betting percentages.

Strategies:
1. Spread RLM: Line moves AGAINST the side with 60%+ public money
2. Total RLM: Total drops/rises against public Over/Under bias
3. ML-Spread Divergence: Public says "team wins but doesn't cover"
4. ATS Trend Extremes: Fade extreme streaks (0-10 ATS → bet on them)
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class RLMSignal:
    """Result of RLM detection."""
    detected: bool
    signal_type: str  # "spread_rlm", "total_rlm", "ml_divergence", "ats_extreme"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    sharp_side: Optional[str] = None  # "home", "away", "over", "under"
    magnitude: float = 0.0  # How strong the signal is
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "signal_type": self.signal_type,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "sharp_side": self.sharp_side,
            "magnitude": self.magnitude,
        }


class SpreadRLMDetector:
    """
    Detect Reverse Line Movement on spreads.
    
    Strategy:
    - If line moves AGAINST side with 60%+ public bets → RLM detected
    - Example: 57% public on LAL, but line moves from -4 to -6.5 AGAINST LAL
    - Interpretation: Sharp money is on the opposite side (OKC)
    """
    
    def __init__(self, min_public_threshold: float = 0.55, min_line_move: float = 1.5):
        """
        Args:
            min_public_threshold: Minimum public % to consider (default 55%)
            min_line_move: Minimum line movement in points (default 1.5)
        """
        self.min_public_threshold = min_public_threshold
        self.min_line_move = min_line_move
    
    def detect(self, game_data: Dict[str, Any]) -> RLMSignal:
        """
        Detect spread RLM for a game.
        
        Args:
            game_data: Dictionary containing:
                - opening_spread: Opening spread (negative = home favored)
                - current_spread: Current spread
                - public_pct_home: % of public bets on home team
                - home_team: Home team name
                - away_team: Away team name
        
        Returns:
            RLMSignal with detection result
        """
        opening_spread = game_data.get("opening_spread")
        current_spread = game_data.get("current_spread")
        public_pct_home = game_data.get("public_pct_home", 0.5)
        home_team = game_data.get("home_team", "Home")
        away_team = game_data.get("away_team", "Away")
        
        # Validate required data
        if opening_spread is None or current_spread is None:
            return RLMSignal(
                detected=False,
                signal_type="spread_rlm",
                confidence=0.0,
                reasoning="Missing opening or current spread data"
            )
        
        # Calculate line movement and public bias
        line_movement = current_spread - opening_spread
        public_on_away = 1.0 - public_pct_home
        
        # Check if public is heavily on one side
        public_on_home_strong = public_pct_home >= self.min_public_threshold
        public_on_away_strong = public_on_away >= self.min_public_threshold
        
        # Check for RLM
        # If public is on home, but line moved making home MORE favored (more negative)
        # That means sharp money is ALSO on home (NOT RLM)
        # RLM = line moves AGAINST public
        
        detected = False
        sharp_side = None
        reasoning = ""
        magnitude = abs(line_movement)
        confidence = 0.0
        
        if public_on_home_strong and line_movement > self.min_line_move:
            # Public on home, but line moved making home LESS favored (toward away)
            # Sharp money is on AWAY
            detected = True
            sharp_side = "away"
            reasoning = f"Line moved {line_movement:+.1f} pts AGAINST {home_team} despite {public_pct_home*100:.0f}% public on {home_team}. Sharp money on {away_team}."
            confidence = min(0.90, 0.75 + (magnitude - self.min_line_move) * 0.05)
            
        elif public_on_away_strong and line_movement < -self.min_line_move:
            # Public on away, but line moved making away LESS favored (home more favored)
            # Sharp money is on HOME
            detected = True
            sharp_side = "home"
            reasoning = f"Line moved {line_movement:+.1f} pts AGAINST {away_team} despite {public_on_away*100:.0f}% public on {away_team}. Sharp money on {home_team}."
            confidence = min(0.90, 0.75 + (magnitude - self.min_line_move) * 0.05)
        
        else:
            reasoning = f"No RLM detected. Line movement: {line_movement:+.1f}, Public: {public_pct_home*100:.0f}% {home_team}"
        
        return RLMSignal(
            detected=detected,
            signal_type="spread_rlm",
            confidence=confidence,
            reasoning=reasoning,
            sharp_side=sharp_side,
            magnitude=magnitude
        )


class TotalRLMDetector:
    """
    Detect Reverse Line Movement on totals (Over/Under).
    
    Strategy:
    - If total drops 4+ points with 65%+ public on Over → Sharp money hammering Under
    - If total rises 4+ points with 65%+ public on Under → Sharp money on Over
    
    Example from user data:
    - CHI @ BKN: Total opened 223.5 → current 218.5 (Δ -5.0)
    - Public: 64% Over
    - Pick: UNDER 218.5 (Tier 1, 85% confidence)
    """
    
    def __init__(self, min_total_move: float = 2.0, strong_total_move: float = 4.0, min_public_threshold: float = 0.60):
        """
        Args:
            min_total_move: Minimum total movement to consider (default 2.0)
            strong_total_move: Strong total movement threshold (default 4.0)
            min_public_threshold: Minimum public % to consider (default 60%)
        """
        self.min_total_move = min_total_move
        self.strong_total_move = strong_total_move
        self.min_public_threshold = min_public_threshold
    
    def detect(self, game_data: Dict[str, Any]) -> RLMSignal:
        """
        Detect total RLM for a game.
        
        Args:
            game_data: Dictionary containing:
                - opening_total: Opening total
                - current_total: Current total
                - public_pct_over: % of public bets on Over
                - home_team: Home team name
                - away_team: Away team name
        
        Returns:
            RLMSignal with detection result
        """
        opening_total = game_data.get("opening_total")
        current_total = game_data.get("current_total")
        public_pct_over = game_data.get("public_pct_over", 0.5)
        home_team = game_data.get("home_team", "Home")
        away_team = game_data.get("away_team", "Away")
        
        # Validate required data
        if opening_total is None or current_total is None:
            return RLMSignal(
                detected=False,
                signal_type="total_rlm",
                confidence=0.0,
                reasoning="Missing opening or current total data"
            )
        
        # Calculate total movement
        total_movement = current_total - opening_total
        magnitude = abs(total_movement)
        public_pct_under = 1.0 - public_pct_over
        
        # Check for RLM
        detected = False
        sharp_side = None
        reasoning = ""
        confidence = 0.0
        
        # Total dropped (moved down) + public on Over = Sharp money on Under
        if total_movement <= -self.min_total_move and public_pct_over >= self.min_public_threshold:
            detected = True
            sharp_side = "under"
            reasoning = f"Total dropped {abs(total_movement):.1f} pts ({opening_total} → {current_total}) AGAINST {public_pct_over*100:.0f}% public on Over. Sharp money on UNDER."
            
            # Strong signal if magnitude >= strong_total_move
            if magnitude >= self.strong_total_move:
                confidence = min(0.90, 0.80 + (magnitude - self.strong_total_move) * 0.02)
            else:
                confidence = 0.70 + (magnitude - self.min_total_move) * 0.05
        
        # Total rose (moved up) + public on Under = Sharp money on Over
        elif total_movement >= self.min_total_move and public_pct_under >= self.min_public_threshold:
            detected = True
            sharp_side = "over"
            reasoning = f"Total rose {total_movement:.1f} pts ({opening_total} → {current_total}) AGAINST {public_pct_under*100:.0f}% public on Under. Sharp money on OVER."
            
            if magnitude >= self.strong_total_move:
                confidence = min(0.90, 0.80 + (magnitude - self.strong_total_move) * 0.02)
            else:
                confidence = 0.70 + (magnitude - self.min_total_move) * 0.05
        
        else:
            reasoning = f"No total RLM detected. Total movement: {total_movement:+.1f}, Public: {public_pct_over*100:.0f}% Over"
        
        return RLMSignal(
            detected=detected,
            signal_type="total_rlm",
            confidence=confidence,
            reasoning=reasoning,
            sharp_side=sharp_side,
            magnitude=magnitude
        )


class MLSpreadDivergenceDetector:
    """
    Detect ML-vs-Spread Divergence.
    
    Strategy:
    - If (Moneyline % - Spread %) > 25% → Public trap
    - Public says "team WINS but doesn't COVER" → Sharp money on dog with points
    
    Example from user data:
    - MIL @ ORL: 84% ML on ORL, 36% spread on ORL
    - Divergence: 48% (HIGHEST)
    - Pick: MIL +10.5 (sharp side)
    """
    
    def __init__(self, min_divergence: float = 0.15, strong_divergence: float = 0.30):
        """
        Args:
            min_divergence: Minimum divergence to consider (default 15%)
            strong_divergence: Strong divergence threshold (default 30%)
        """
        self.min_divergence = min_divergence
        self.strong_divergence = strong_divergence
    
    def detect(self, game_data: Dict[str, Any]) -> RLMSignal:
        """
        Detect ML-Spread divergence for a game.
        
        Args:
            game_data: Dictionary containing:
                - public_pct_home_ml: % of public ML bets on home team
                - public_pct_home_spread: % of public spread bets on home team
                - home_team: Home team name
                - away_team: Away team name
                - current_spread: Current spread (for context)
        
        Returns:
            RLMSignal with detection result
        """
        ml_pct_home = game_data.get("public_pct_home_ml")
        spread_pct_home = game_data.get("public_pct_home_spread")
        home_team = game_data.get("home_team", "Home")
        away_team = game_data.get("away_team", "Away")
        current_spread = game_data.get("current_spread", 0.0)
        
        # Validate required data
        if ml_pct_home is None or spread_pct_home is None:
            return RLMSignal(
                detected=False,
                signal_type="ml_divergence",
                confidence=0.0,
                reasoning="Missing ML or spread public betting data"
            )
        
        # Calculate divergence
        divergence = abs(ml_pct_home - spread_pct_home)
        
        detected = False
        sharp_side = None
        reasoning = ""
        confidence = 0.0
        
        if divergence >= self.min_divergence:
            detected = True
            
            # Determine which side is the trap
            if ml_pct_home > spread_pct_home:
                # More ML money on home than spread money
                # Public: "Home will WIN but won't COVER"
                # Sharp side: AWAY with points
                sharp_side = "away"
                reasoning = f"ML/Spread divergence: {divergence*100:.0f}% ({ml_pct_home*100:.0f}% ML vs {spread_pct_home*100:.0f}% spread on {home_team}). Public says '{home_team} wins but doesn't cover'. Sharp side: {away_team} {current_spread:+.1f}"
            else:
                # More spread money on home than ML money
                # Public: "Home will COVER but might not WIN"
                # Sharp side: HOME with points
                sharp_side = "home"
                reasoning = f"ML/Spread divergence: {divergence*100:.0f}% ({spread_pct_home*100:.0f}% spread vs {ml_pct_home*100:.0f}% ML on {home_team}). Public says '{home_team} covers but might not win'. Sharp side: {home_team} {current_spread:+.1f}"
            
            # Confidence based on divergence magnitude
            if divergence >= self.strong_divergence:
                confidence = min(0.85, 0.75 + (divergence - self.strong_divergence) * 0.5)
            else:
                confidence = 0.70 + (divergence - self.min_divergence) * 0.3
        
        else:
            reasoning = f"No ML/Spread divergence detected. Gap: {divergence*100:.0f}%"
        
        return RLMSignal(
            detected=detected,
            signal_type="ml_divergence",
            confidence=confidence,
            reasoning=reasoning,
            sharp_side=sharp_side,
            magnitude=divergence
        )


class ATSTrendAnalyzer:
    """
    Analyze ATS (Against The Spread) trend extremes.
    
    Strategy:
    - If team is 0-10 ATS last 10 games → Fade the streak (bet on them)
    - If team is 10-0 ATS last 10 games → Fade the streak (bet against them)
    - Regression to the mean
    
    This is a CONFIRMATION signal, not a primary trigger.
    """
    
    def __init__(self, extreme_threshold: float = 0.70):
        """
        Args:
            extreme_threshold: Win/loss rate to be considered extreme (default 70%)
        """
        self.extreme_threshold = extreme_threshold
    
    def analyze(self, game_data: Dict[str, Any]) -> RLMSignal:
        """
        Analyze ATS trends for a game.
        
        Args:
            game_data: Dictionary containing:
                - home_ats_l10: Home team ATS record last 10 (e.g., "2-8")
                - away_ats_l10: Away team ATS record last 10 (e.g., "8-2")
                - home_team: Home team name
                - away_team: Away team name
        
        Returns:
            RLMSignal with analysis result
        """
        home_ats = game_data.get("home_ats_l10", "")
        away_ats = game_data.get("away_ats_l10", "")
        home_team = game_data.get("home_team", "Home")
        away_team = game_data.get("away_team", "Away")
        
        detected = False
        sharp_side = None
        reasoning = ""
        confidence = 0.0
        
        # Parse ATS records (e.g., "2-8" → 0.2 win rate)
        home_rate = self._parse_ats_record(home_ats)
        away_rate = self._parse_ats_record(away_ats)
        
        if home_rate is None or away_rate is None:
            return RLMSignal(
                detected=False,
                signal_type="ats_extreme",
                confidence=0.0,
                reasoning="Missing or invalid ATS data"
            )
        
        # Check for extreme trends
        home_extreme_bad = home_rate <= (1.0 - self.extreme_threshold)  # <= 30% (0-3 in L10)
        away_extreme_bad = away_rate <= (1.0 - self.extreme_threshold)
        home_extreme_good = home_rate >= self.extreme_threshold  # >= 70% (7+ in L10)
        away_extreme_good = away_rate >= self.extreme_threshold
        
        if home_extreme_bad and not away_extreme_bad:
            # Home team is in a bad ATS streak → Fade the streak, bet ON them
            detected = True
            sharp_side = "home"
            reasoning = f"{home_team} is {home_ats} ATS L10 (extreme cold streak). Fade the streak → bet {home_team}."
            confidence = 0.70
            
        elif away_extreme_bad and not home_extreme_bad:
            detected = True
            sharp_side = "away"
            reasoning = f"{away_team} is {away_ats} ATS L10 (extreme cold streak). Fade the streak → bet {away_team}."
            confidence = 0.70
            
        elif home_extreme_good and not away_extreme_good:
            # Home team is on a hot ATS streak → Fade the streak, bet AGAINST them
            detected = True
            sharp_side = "away"
            reasoning = f"{home_team} is {home_ats} ATS L10 (extreme hot streak). Fade the streak → bet {away_team}."
            confidence = 0.65  # Slightly lower confidence for fading hot streaks
            
        elif away_extreme_good and not home_extreme_good:
            detected = True
            sharp_side = "home"
            reasoning = f"{away_team} is {away_ats} ATS L10 (extreme hot streak). Fade the streak → bet {home_team}."
            confidence = 0.65
        
        else:
            reasoning = f"No extreme ATS trends. {home_team}: {home_ats}, {away_team}: {away_ats}"
        
        magnitude = max(abs(home_rate - 0.5), abs(away_rate - 0.5)) * 2.0  # 0 to 1 scale
        
        return RLMSignal(
            detected=detected,
            signal_type="ats_extreme",
            confidence=confidence,
            reasoning=reasoning,
            sharp_side=sharp_side,
            magnitude=magnitude
        )
    
    def _parse_ats_record(self, ats_string: str) -> Optional[float]:
        """
        Parse ATS record string like "2-8" or "8-2" into win rate.
        
        Args:
            ats_string: ATS record like "2-8"
        
        Returns:
            Win rate (0.0 to 1.0) or None if invalid
        """
        if not ats_string or "-" not in ats_string:
            return None
        
        try:
            parts = ats_string.split("-")
            wins = int(parts[0])
            losses = int(parts[1])
            total = wins + losses
            
            if total == 0:
                return None
            
            return wins / total
        except (ValueError, IndexError):
            return None
