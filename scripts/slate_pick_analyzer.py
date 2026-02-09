#!/usr/bin/env python3
"""
SLATE PICK ANALYZER - Using All Lessons Learned
Applies the correct fade detection methodology:
1. High public % on one side
2. Line moved AGAINST public direction = sharp money fade signal
3. NO RLM movement = potential TRAP or consensus (skip)
4. Multi-signal verification before recommending

Key lessons from failures:
- Baylor, Wisconsin, LSU failed because we used public % alone
- Cavs Under failed because we didn't track scoring pace
- MUST verify line movement against public before fading
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime
from enum import Enum

class SignalStrength(Enum):
    TIER1 = "TIER 1 - STRONG FADE"
    TIER2 = "TIER 2 - MODERATE FADE"
    TRAP = "TRAP - SKIP"
    CONSENSUS = "CONSENSUS - SKIP"
    WEAK = "WEAK SIGNAL - SKIP"

@dataclass
class GameData:
    """Game information with lines and betting data"""
    game_id: str
    matchup: str
    away_team: str
    home_team: str
    opening_spread: float
    current_spread: float
    opening_total: float
    current_total: float
    public_pct_favorite: float  # % on favorite (vs spread)
    public_pct_total: Optional[float]  # % on over (if available)
    sport: str = "NCAAB"

@dataclass
class PickAnalysis:
    """Analysis result for a game"""
    game: GameData
    signal_strength: SignalStrength
    pick_side: Optional[str]  # e.g., "Away +15.5" or "Over 138.5"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    rlm_magnitude: float  # How far line moved against public
    public_divergence: float  # How heavy public is on one side
    
    def __str__(self) -> str:
        matchup = self.game.matchup
        if self.pick_side is None:
            return f"❌ {matchup} - {self.signal_strength.value}\n   Reason: {self.reasoning}"
        
        emoji = "🔥" if self.signal_strength == SignalStrength.TIER1 else "📊"
        return f"{emoji} {matchup}\n   Pick: {self.pick_side}\n   Confidence: {self.confidence:.1%}\n   Signal: {self.signal_strength.value}\n   RLM: {self.rlm_magnitude:+.1f}pts | Public: {self.public_divergence:.0f}% on fave\n   Logic: {self.reasoning}"

class PickAnalyzer:
    """Analyzes games using proper RLM + public divergence methodology"""
    
    # Thresholds - learned from failures
    MIN_PUBLIC_DIVERGENCE = 65  # Need at least 65% on one side to matter
    MIN_RLM_AGAINST_PUBLIC = 2.0  # Line must move 2+ pts AGAINST public
    STRONG_RLM = 3.0  # 3+ pts = very strong signal
    
    def analyze_game(self, game: GameData) -> PickAnalysis:
        """Analyze a single game for fade opportunities"""
        
        # Calculate key metrics
        rlm = self._calculate_rlm(game)
        public_divergence = self._calculate_public_divergence(game)
        is_line_heavy_on_public = self._is_line_heavy_on_public_side(game)
        
        # Determine if public is on favorite or underdog
        public_on_favorite = public_divergence >= 50
        favorite_spread = -abs(game.current_spread)
        underdog_spread = +abs(game.current_spread)
        
        # Decision tree using lessons learned
        
        # LESSON 1: High public % + NO line movement = TRAP or CONSENSUS
        # (Sharp money agrees with public, or books don't want to move)
        if abs(rlm) < 0.5 and public_divergence >= 70:
            return PickAnalysis(
                game=game,
                signal_strength=SignalStrength.TRAP,
                pick_side=None,
                confidence=0.0,
                reasoning=f"TRAP SIGNAL: {public_divergence:.0f}% on side but line didn't move. Sharp money likely agrees with public or books confident in line.",
                rlm_magnitude=rlm,
                public_divergence=public_divergence
            )
        
        # LESSON 2: Line moved slightly in public direction = CONSENSUS
        # (Books are managing liability, not a sharp money signal)
        if rlm > 0.5 and rlm < self.MIN_RLM_AGAINST_PUBLIC and public_divergence >= 70:
            return PickAnalysis(
                game=game,
                signal_strength=SignalStrength.CONSENSUS,
                pick_side=None,
                confidence=0.0,
                reasoning=f"CONSENSUS: Line moved {rlm:+.1f}pts WITH public ({public_divergence:.0f}% on side). Books managing liability, not a sharp signal.",
                rlm_magnitude=rlm,
                public_divergence=public_divergence
            )
        
        # LESSON 3: Strong RLM AGAINST public = REAL FADE (sharp money moving line)
        # This is the Baylor/Wisconsin lesson: need to verify line actually moved against public
        if rlm <= -self.MIN_RLM_AGAINST_PUBLIC and public_divergence >= self.MIN_PUBLIC_DIVERGENCE:
            # Determine which side to fade
            if public_on_favorite:
                # Public heavy on favorite, line moved down (favor underdog)
                pick_side = f"{game.away_team} {underdog_spread:+.1f}" if game.current_spread > 0 else f"{game.home_team} {underdog_spread:+.1f}"
                signal_strength = SignalStrength.TIER1 if abs(rlm) >= self.STRONG_RLM else SignalStrength.TIER2
            else:
                # Public heavy on underdog, line moved up (favor favorite)
                pick_side = f"{game.away_team} {favorite_spread:+.1f}" if game.current_spread < 0 else f"{game.home_team} {favorite_spread:+.1f}"
                signal_strength = SignalStrength.TIER1 if abs(rlm) >= self.STRONG_RLM else SignalStrength.TIER2
            
            confidence = min(0.95, 0.70 + (public_divergence - 65) * 0.005 + (abs(rlm) - 2.0) * 0.05)
            
            return PickAnalysis(
                game=game,
                signal_strength=signal_strength,
                pick_side=pick_side,
                confidence=confidence,
                reasoning=f"RLM FADE: Public {public_divergence:.0f}% on side, but line moved {abs(rlm):.1f}pts AGAINST them. Sharp money detected.",
                rlm_magnitude=rlm,
                public_divergence=public_divergence
            )
        
        # LESSON 4: Moderate divergence but no RLM = weak/skip
        # (Not enough signal strength to warrant action)
        if public_divergence >= 60 and abs(rlm) < self.MIN_RLM_AGAINST_PUBLIC:
            return PickAnalysis(
                game=game,
                signal_strength=SignalStrength.WEAK,
                pick_side=None,
                confidence=0.0,
                reasoning=f"WEAK SIGNAL: {public_divergence:.0f}% divergence but only {rlm:+.1f}pts RLM. Need stronger signals.",
                rlm_magnitude=rlm,
                public_divergence=public_divergence
            )
        
        # No signal detected
        return PickAnalysis(
            game=game,
            signal_strength=SignalStrength.WEAK,
            pick_side=None,
            confidence=0.0,
            reasoning=f"No actionable signal: {public_divergence:.0f}% divergence, {rlm:+.1f}pts RLM. Insufficient for recommendation.",
            rlm_magnitude=rlm,
            public_divergence=public_divergence
        )
    
    def _calculate_rlm(self, game: GameData) -> float:
        """
        Calculate Reverse Line Movement (RLM)
        Positive = line moved in public's favor
        Negative = line moved against public
        
        If opening was -7 and current is -8, line moved 1pt toward favorite
        """
        return game.current_spread - game.opening_spread
    
    def _calculate_public_divergence(self, game: GameData) -> float:
        """
        Calculate how heavy public is on one side (0-100%)
        65%+ is meaningful divergence
        75%+ is very strong divergence
        """
        return max(game.public_pct_favorite, 100 - game.public_pct_favorite)
    
    def _is_line_heavy_on_public_side(self, game: GameData) -> bool:
        """Check if line moved in public's favor"""
        return self._calculate_rlm(game) > 0


def analyze_slate(games: list[GameData]) -> list[PickAnalysis]:
    """Analyze entire slate and return sorted picks"""
    analyzer = PickAnalyzer()
    analyses = [analyzer.analyze_game(game) for game in games]
    
    # Sort: Tier 1 first, then by confidence
    def sort_key(analysis):
        priority = {
            SignalStrength.TIER1: 0,
            SignalStrength.TIER2: 1,
            SignalStrength.WEAK: 2,
            SignalStrength.TRAP: 3,
            SignalStrength.CONSENSUS: 4,
        }
        return (priority[analysis.signal_strength], -analysis.confidence)
    
    return sorted(analyses, key=sort_key)


# ============================================================================
# 5 PM SLATE ANALYSIS - From User Screenshots
# ============================================================================

def analyze_5pm_slate():
    """Analyze the 5 PM slate from user's DraftKings screenshots"""
    
    games = [
        GameData(
            game_id="wsu_sm_1",
            matchup="Washington State @ Saint Marys",
            away_team="Washington State",
            home_team="Saint Marys",
            opening_spread=15.5,  # WSU +15.5 opening
            current_spread=15.5,  # WSU +15.5 current (per screenshot)
            opening_total=143.5,
            current_total=143.5,
            public_pct_favorite=27,  # 27% on WSU +15.5, so 73% on SM -15.5
            public_pct_total=None,
            sport="NCAAB"
        ),
        GameData(
            game_id="tulane_utsa_1",
            matchup="Tulane @ UTSA",
            away_team="Tulane",
            home_team="UTSA",
            opening_spread=-7.5,  # Tulane -7.5 opening
            current_spread=-7.5,  # Tulane -7.5 current
            opening_total=147.5,
            current_total=147.5,
            public_pct_favorite=76,  # 76% on Tulane -7.5
            public_pct_total=24,  # 24% on Over
            sport="NCAAB"
        ),
        GameData(
            game_id="se_mcneese_1",
            matchup="SE Louisiana @ McNeese",
            away_team="SE Louisiana",
            home_team="McNeese",
            opening_spread=16.5,  # SE LA +16.5 opening
            current_spread=16.5,  # SE LA +16.5 current
            opening_total=138.5,
            current_total=138.5,
            public_pct_favorite=25,  # 25% on SE LA +16.5, so 75% on McNeese -16.5
            public_pct_total=28,  # 28% on Under
            sport="NCAAB"
        ),
        GameData(
            game_id="apb_ts_1",
            matchup="Arkansas-Pine Bluff @ Texas Southern",
            away_team="Arkansas-Pine Bluff",
            home_team="Texas Southern",
            opening_spread=1.5,  # APB +1.5 opening
            current_spread=1.5,  # APB +1.5 current
            opening_total=162.5,
            current_total=162.5,
            public_pct_favorite=40,  # 40% on APB +1.5, so 60% on TS -1.5
            public_pct_total=31,  # 31% on Over
            sport="NCAAB"
        ),
    ]
    
    print("\n" + "="*80)
    print("🎯 5 PM SLATE ANALYSIS - APPLYING ALL LESSONS LEARNED")
    print("="*80)
    print("\nMethodology:")
    print("✓ High public % alone = NOT a signal (Baylor/Wisconsin failure)")
    print("✓ Line moved AGAINST public = Real fade signal (sharp money)")
    print("✓ No RLM movement = TRAP (public consensus, skip)")
    print("✓ RLM 3+ pts against public = TIER 1 confidence")
    print("✓ RLM 2-3 pts against public = TIER 2 moderate confidence")
    print("\n" + "="*80)
    
    analyses = analyze_slate(games)
    
    # Print actionable picks
    print("\n🔥 TIER 1 PICKS (Strong Fades - RLM 3+ pts against public):")
    tier1_picks = [a for a in analyses if a.signal_strength == SignalStrength.TIER1]
    if tier1_picks:
        for pick in tier1_picks:
            print(f"\n{pick}")
    else:
        print("   None identified - no strong fades in this slate")
    
    print("\n\n📊 TIER 2 PICKS (Moderate Fades - RLM 2-3 pts against public):")
    tier2_picks = [a for a in analyses if a.signal_strength == SignalStrength.TIER2]
    if tier2_picks:
        for pick in tier2_picks:
            print(f"\n{pick}")
    else:
        print("   None identified - no moderate fades in this slate")
    
    print("\n\n⚠️  GAMES TO SKIP (Traps/Consensus/Weak Signals):")
    skip_picks = [a for a in analyses if a.signal_strength in [
        SignalStrength.TRAP, SignalStrength.CONSENSUS, SignalStrength.WEAK
    ]]
    for pick in skip_picks:
        print(f"\n❌ {pick}")
    
    print("\n\n" + "="*80)
    print("SUMMARY OF SIGNALS:")
    print("="*80)
    for analysis in analyses:
        print(f"{analysis.game.matchup}")
        print(f"  • Opening: {analysis.game.away_team} {analysis.game.opening_spread:+.1f}")
        print(f"  • Current:  {analysis.game.away_team} {analysis.game.current_spread:+.1f}")
        print(f"  • Public: {analysis.public_divergence:.0f}% on one side")
        print(f"  • RLM: {analysis.rlm_magnitude:+.1f}pts (negative = against public)")
        print(f"  • Recommendation: {analysis.signal_strength.value}")
        if analysis.pick_side:
            print(f"  • PICK: {analysis.pick_side} at {analysis.confidence:.0%} confidence")
        print()


if __name__ == "__main__":
    analyze_5pm_slate()
