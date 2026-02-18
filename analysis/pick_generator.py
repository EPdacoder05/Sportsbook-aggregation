"""
Pick Generator
==============
Combines all analysis components to generate final pick recommendations.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from analysis.rlm_detector import (
    SpreadRLMDetector,
    TotalRLMDetector,
    MLSpreadDivergenceDetector,
    ATSTrendAnalyzer,
    RLMSignal
)
from analysis.confidence import ConfidenceScorer, ConfidenceScore
from analysis.data_loader import DataLoader

logger = logging.getLogger(__name__)


class Pick:
    """A betting pick recommendation."""
    
    def __init__(
        self,
        game_id: str,
        game: str,
        pick: str,
        tier: str,
        confidence: float,
        signals: List[str],
        reasoning: str,
        best_book: Optional[str] = None,
        timestamp: Optional[str] = None
    ):
        self.game_id = game_id
        self.game = game
        self.pick = pick
        self.tier = tier
        self.confidence = confidence
        self.signals = signals
        self.reasoning = reasoning
        self.best_book = best_book or "N/A"
        self.timestamp = timestamp or datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "game": self.game,
            "pick": self.pick,
            "tier": self.tier,
            "confidence": self.confidence,
            "signals": self.signals,
            "reasoning": self.reasoning,
            "best_book": self.best_book,
            "timestamp": self.timestamp
        }


class PickGenerator:
    """
    Generate betting picks from unified game data.
    
    Pipeline:
    1. Load and merge data (odds + opening lines + public splits)
    2. Run all RLM detectors on each game
    3. Score confidence and determine tier
    4. Find best lines across bookmakers
    5. Generate pick recommendations
    """
    
    def __init__(self, data_dir: str = "data"):
        """
        Args:
            data_dir: Directory containing data files (default: "data")
        """
        self.data_dir = Path(data_dir)
        self.data_loader = DataLoader(str(self.data_dir))
        
        # Initialize detectors
        self.spread_rlm = SpreadRLMDetector()
        self.total_rlm = TotalRLMDetector()
        self.ml_divergence = MLSpreadDivergenceDetector()
        self.ats_analyzer = ATSTrendAnalyzer()
        
        # Initialize scorer
        self.confidence_scorer = ConfidenceScorer()
    
    def generate_picks(
        self,
        odds_file: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> List[Pick]:
        """
        Generate picks from odds data.
        
        Args:
            odds_file: Optional odds window file (e.g., "odds_window_7pm_20260209.json")
            date_str: Optional date string for opening lines (e.g., "20260209")
        
        Returns:
            List of Pick objects (only TIER_1, TIER_2, and strong LEANs)
        """
        # Auto-detect files if not provided
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
        
        # Load data
        if odds_file:
            odds_data = self.data_loader.load_odds_window(odds_file)
        else:
            # Try to find most recent odds file
            odds_data = self._find_latest_odds_file()
        
        if not odds_data:
            logger.warning("No odds data found")
            return []
        
        opening_lines = self.data_loader.load_opening_lines(date_str)
        public_splits = self.data_loader.load_public_splits()
        
        # Merge data
        games = self.data_loader.merge_game_data(odds_data, opening_lines, public_splits)
        
        if not games:
            logger.warning("No games found after merging data")
            return []
        
        # Analyze each game
        picks = []
        
        for game_data in games:
            game_picks = self._analyze_game(game_data)
            picks.extend(game_picks)
        
        # Sort by confidence (highest first)
        picks.sort(key=lambda p: p.confidence, reverse=True)
        
        logger.info(f"Generated {len(picks)} picks")
        return picks
    
    def _analyze_game(self, game_data: Dict[str, Any]) -> List[Pick]:
        """
        Analyze a single game and generate picks.
        
        Args:
            game_data: Unified game data
        
        Returns:
            List of Pick objects (0-2 picks per game: spread and/or total)
        """
        picks = []
        
        game_id = game_data.get("game_id", "")
        home_team = game_data.get("home_team", "")
        away_team = game_data.get("away_team", "")
        game_str = f"{away_team} @ {home_team}"
        
        # Run all detectors
        spread_rlm_signal = self.spread_rlm.detect(game_data)
        total_rlm_signal = self.total_rlm.detect(game_data)
        ml_divergence_signal = self.ml_divergence.detect(game_data)
        ats_signal = self.ats_analyzer.analyze(game_data)
        
        # Separate primary and confirmation signals
        primary_signals = [spread_rlm_signal, total_rlm_signal, ml_divergence_signal]
        confirmation_signals = [ats_signal]
        
        # Check for spread pick
        spread_primary = [s for s in [spread_rlm_signal, ml_divergence_signal] if s.detected]
        if spread_primary:
            confidence = self.confidence_scorer.score_with_boost(
                spread_primary,
                confirmation_signals
            )
            
            if confidence.tier != "PASS":
                # Determine which side to pick
                sharp_side = self._determine_sharp_side(spread_primary)
                
                if sharp_side:
                    # Find best line
                    best_line_data = self.data_loader.find_best_line(
                        game_data, "spreads", sharp_side
                    )
                    
                    if best_line_data:
                        team = home_team if sharp_side == "home" else away_team
                        line = best_line_data["line"]
                        odds = best_line_data["american_odds"]
                        book = best_line_data["bookmaker"]
                        
                        pick_str = f"{team} {line:+.1f}"
                        best_book_str = f"{book} {team} {line:+.1f} {odds:+d}"
                        
                        # Combine reasoning from all signals
                        reasoning_parts = [s.reasoning for s in spread_primary if s.detected]
                        if ats_signal.detected:
                            reasoning_parts.append(ats_signal.reasoning)
                        reasoning = " | ".join(reasoning_parts)
                        
                        pick = Pick(
                            game_id=game_id,
                            game=game_str,
                            pick=pick_str,
                            tier=confidence.tier,
                            confidence=confidence.confidence,
                            signals=confidence.signals,
                            reasoning=reasoning,
                            best_book=best_book_str
                        )
                        
                        picks.append(pick)
                        logger.info(f"{confidence.tier}: {pick_str} ({confidence.confidence:.0%})")
        
        # Check for total pick
        if total_rlm_signal.detected:
            confidence = self.confidence_scorer.score_with_boost(
                [total_rlm_signal],
                confirmation_signals
            )
            
            if confidence.tier != "PASS":
                sharp_side = total_rlm_signal.sharp_side
                
                if sharp_side:
                    # Find best line
                    best_line_data = self.data_loader.find_best_line(
                        game_data, "totals", sharp_side
                    )
                    
                    if best_line_data:
                        line = best_line_data["line"]
                        odds = best_line_data["american_odds"]
                        book = best_line_data["bookmaker"]
                        
                        pick_str = f"{sharp_side.upper()} {line}"
                        best_book_str = f"{book} {pick_str} {odds:+d}"
                        
                        reasoning_parts = [total_rlm_signal.reasoning]
                        if ats_signal.detected:
                            reasoning_parts.append(ats_signal.reasoning)
                        reasoning = " | ".join(reasoning_parts)
                        
                        pick = Pick(
                            game_id=game_id,
                            game=game_str,
                            pick=pick_str,
                            tier=confidence.tier,
                            confidence=confidence.confidence,
                            signals=confidence.signals,
                            reasoning=reasoning,
                            best_book=best_book_str
                        )
                        
                        picks.append(pick)
                        logger.info(f"{confidence.tier}: {pick_str} ({confidence.confidence:.0%})")
        
        return picks
    
    def _determine_sharp_side(self, signals: List[RLMSignal]) -> Optional[str]:
        """
        Determine the consensus sharp side from multiple signals.
        
        Args:
            signals: List of detected RLMSignal objects
        
        Returns:
            "home", "away", or None
        """
        if not signals:
            return None
        
        # Count votes for each side
        votes = {"home": 0, "away": 0}
        
        for signal in signals:
            if signal.sharp_side in votes:
                # Weight by confidence
                votes[signal.sharp_side] += signal.confidence
        
        # Return side with most votes
        if votes["home"] > votes["away"]:
            return "home"
        elif votes["away"] > votes["home"]:
            return "away"
        else:
            # Tie - use strongest signal
            strongest = max(signals, key=lambda s: s.confidence)
            return strongest.sharp_side
    
    def _find_latest_odds_file(self) -> Optional[Dict[str, Any]]:
        """
        Find the most recent odds window file.
        
        Returns:
            Odds data dict or None
        """
        odds_files = list(self.data_dir.glob("odds_window_*.json"))
        
        if not odds_files:
            return None
        
        # Sort by modification time
        latest_file = max(odds_files, key=lambda f: f.stat().st_mtime)
        
        logger.info(f"Using latest odds file: {latest_file.name}")
        
        try:
            with open(latest_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {latest_file}: {e}")
            return None
    
    def save_picks(self, picks: List[Pick], date_str: Optional[str] = None) -> bool:
        """
        Save picks to JSON file.
        
        Args:
            picks: List of Pick objects
            date_str: Optional date string (default: today)
        
        Returns:
            True if saved successfully
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
        
        file_path = self.data_dir / f"picks_{date_str}.json"
        
        picks_data = {
            "date": date_str,
            "generated_at": datetime.utcnow().isoformat(),
            "picks": [p.to_dict() for p in picks]
        }
        
        try:
            with open(file_path, 'w') as f:
                json.dump(picks_data, f, indent=2)
            logger.info(f"Saved {len(picks)} picks to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving picks: {e}")
            return False
