#!/usr/bin/env python3
"""
BETTING ENGINE — Unified Orchestrator
======================================
Single entry point that ties all modules together into a cohesive pipeline.

This module orchestrates:
  - SignalClassifier: Detects primary and confirmation signals
  - ConfidenceDecayEngine: Applies time-based and market-based decay
  - LineFreezeDetector: Identifies book traps and sharp holds
  - BoostEVCalculator: Evaluates profit boost opportunities
  - CLVTracker: Tracks closing line value for post-game grading
  - NoBetDetector: Filters out coin-flip games with no edge

Architecture:
  Input:  Game data (odds, public %, ATS, pace, rest, etc.)
  Output: Full GameSignalProfile with tier, confidence, picks
  
Usage:
    from engine.betting_engine import BettingEngine
    
    engine = BettingEngine()
    
    # Analyze a single game
    profile = engine.analyze_game(
        game_key="CHI @ BKN",
        odds_data={...},
        public_data={...},
        ats_data={...},
    )
    
    # Analyze an entire slate
    results = engine.analyze_slate([game1, game2, game3])
    
    # Evaluate a boost
    boost_result = engine.evaluate_boost(pick, boost_pct=0.25)
    
    # Record result after game
    engine.record_result("CHI @ BKN", "UNDER 218.5", won=True, final_total=210)
"""

from typing import Dict, List, Optional
from datetime import datetime
import sys
import os
from pathlib import Path

# Add project root to path for standalone execution
if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.signals import SignalClassifier, GameSignalProfile
from engine.confidence_decay import ConfidenceDecayEngine
from engine.line_freeze_detector import LineFreezeDetector, LineSnapshot
from engine.boost_ev import BoostCalculator
from engine.clv_tracker import CLVTracker
from engine.no_bet_detector import NoBetDetector
from engine.ml.feature_engine import FeatureEngine
from engine.ml.pick_model import PickModel
from engine.ml.anomaly_detector import AnomalyDetector
from engine.ml.model_monitor import ModelMonitor

import logging

logger = logging.getLogger(__name__)


class BettingEngine:
    """
    Unified orchestrator for the entire betting pipeline.
    
    This class wires together all modular components into a single
    cohesive system for analyzing games, generating picks, and
    tracking performance.
    """
    
    def __init__(self):
        self.signal_classifier = SignalClassifier()
        self.decay_engine = ConfidenceDecayEngine()
        self.freeze_detector = LineFreezeDetector()
        self.boost_calculator = BoostCalculator()
        self.clv_tracker = CLVTracker()
        self.no_bet_detector = NoBetDetector()
        
        # ML/AI layer
        self.feature_engine = FeatureEngine()
        self.pick_model = PickModel()
        self.anomaly_detector = AnomalyDetector()
        self.model_monitor = ModelMonitor()
    
    def analyze_game(
        self,
        game_key: str,
        odds_data: Optional[Dict] = None,
        public_data: Optional[Dict] = None,
        ats_data: Optional[Dict] = None,
        pace_data: Optional[Dict] = None,
        rest_data: Optional[Dict] = None,
        home_road_data: Optional[Dict] = None,
        cross_source_data: Optional[Dict] = None,
        freeze_snapshots: Optional[List[LineSnapshot]] = None,
        apply_decay: bool = True,
    ) -> Dict:
        """
        Analyze a single game and return full profile with tier and confidence.
        
        Args:
            game_key: "CHI @ BKN" format
            odds_data: {
                "spread": {"open": -3, "current": -4, "public_pct": 68},
                "total": {"open": 223.5, "current": 218.5, "over_pct": 64},
                "ml": {"away_ml_pct": 77, "home_ml_pct": 23},
                "books": {"spread_range": 1.5, "total_range": 2.0}
            }
            public_data: {"spread_fav_pct": 68, "total_over_pct": 64}
            ats_data: {"away_l10_ats": "3-7", "home_l10_ats": "2-8"}
            pace_data: {"away_pace_rank": 5, "home_pace_rank": 25, "league_avg_pace": 100}
            rest_data: {"away_rest_days": 0, "home_rest_days": 2}
            home_road_data: {"away_road_ats": "3-7", "home_home_ats": "8-2"}
            cross_source_data: {"dk_pct": 64, "covers_pct": 48, "side": "over"}
            freeze_snapshots: List of LineSnapshot for freeze detection
            apply_decay: Whether to apply confidence decay
        
        Returns:
            Dict with full game profile including:
            - signal_profile: GameSignalProfile with tier/confidence
            - no_bet_result: NoBetResult if game is a coin flip
            - decay_result: DecayResult if apply_decay=True
            - freeze_result: FreezeResult if snapshots provided
        """
        # Extract sub-dicts from odds_data if provided
        spread_data = odds_data.get("spread") if odds_data else None
        total_data = odds_data.get("total") if odds_data else None
        ml_data = odds_data.get("ml") if odds_data else None
        book_data = odds_data.get("books") if odds_data else None
        
        # ── Step 1: Signal Classification ────────────────────────
        signal_profile = self.signal_classifier.classify(
            game_key=game_key,
            spread_data=spread_data,
            total_data=total_data,
            ml_data=ml_data,
            public_data=public_data,
            ats_data=ats_data,
            book_data=book_data,
            cross_source_data=cross_source_data,
            pace_data=pace_data,
            rest_data=rest_data,
            home_road_data=home_road_data,
        )
        
        # ── Step 2: Line Freeze Detection ────────────────────────
        freeze_result = None
        if freeze_snapshots and public_data:
            spread_pct = public_data.get("spread_fav_pct", 50)
            freeze_result = self.freeze_detector.detect_spread_freeze(
                game_key, freeze_snapshots, spread_pct
            )
            
            # Add freeze signal if detected
            if freeze_result.signal.value != "NONE":
                freeze_data = {
                    "signal": freeze_result.signal.value,
                    "public_pct": freeze_result.public_pct,
                    "hours_frozen": freeze_result.hours_frozen,
                }
                freeze_sig = self.signal_classifier._detect_line_freeze(freeze_data)
                if freeze_sig:
                    signal_profile.add_signal(freeze_sig)
        
        # ── Step 3: No-Bet Detection ──────────────────────────────
        no_bet_result = self.no_bet_detector.detect(
            game_key=game_key,
            spread_data=spread_data,
            total_data=total_data,
            public_data=public_data,
            book_data=book_data,
            ml_data=ml_data,
            has_primary_signal=signal_profile.has_primary,
        )
        
        # If it's a no-bet, override tier to PASS
        if no_bet_result.is_no_bet:
            signal_profile.tier = "PASS"
            signal_profile.recommended_units = 0
            signal_profile.pick_side = "NO BET"
        
        # ── Step 4: Confidence Decay ──────────────────────────────
        decay_result = None
        if apply_decay and signal_profile.tier != "PASS":
            # Create a pick dict for decay analysis
            pick = {
                "game": game_key,
                "confidence": signal_profile.total_confidence,
                "tier": signal_profile.tier,
                "timestamp": datetime.now().isoformat(),
                "line": spread_data.get("current") if spread_data else None,
                "pick_type": "SPREAD",
            }
            
            current_line = spread_data.get("current") if spread_data else None
            decay_result = self.decay_engine.apply_decay(pick, current_line=current_line)
            
            # Update profile with decay-adjusted values
            signal_profile.total_confidence = decay_result.current_confidence
            signal_profile.tier = decay_result.current_tier
            signal_profile._update_tier()
        
        return {
            "game_key": game_key,
            "signal_profile": signal_profile.to_dict(),
            "no_bet_result": no_bet_result.to_dict() if no_bet_result else None,
            "decay_result": decay_result.to_dict() if decay_result else None,
            "freeze_result": freeze_result.to_dict() if freeze_result else None,
            "ml_prediction": self._ml_analyze(game_key, odds_data, signal_profile, rest_data),
            "timestamp": datetime.now().isoformat(),
        }
    
    def analyze_slate(
        self,
        games: List[Dict],
        apply_decay: bool = True,
    ) -> Dict:
        """
        Analyze an entire slate of games.
        
        Args:
            games: List of game dicts, each with:
                {
                    "game_key": "CHI @ BKN",
                    "odds_data": {...},
                    "public_data": {...},
                    "ats_data": {...},
                    ...
                }
            apply_decay: Whether to apply confidence decay
        
        Returns:
            Dict with:
            - games: List of analyzed game profiles
            - summary: Aggregate stats (tier1_count, tier2_count, etc.)
            - sorted_by_tier: Games sorted by tier/confidence
        """
        analyzed_games = []
        
        for game in games:
            result = self.analyze_game(
                game_key=game.get("game_key", ""),
                odds_data=game.get("odds_data"),
                public_data=game.get("public_data"),
                ats_data=game.get("ats_data"),
                pace_data=game.get("pace_data"),
                rest_data=game.get("rest_data"),
                home_road_data=game.get("home_road_data"),
                cross_source_data=game.get("cross_source_data"),
                freeze_snapshots=game.get("freeze_snapshots"),
                apply_decay=apply_decay,
            )
            analyzed_games.append(result)
        
        # Sort by tier (TIER1 > TIER2 > LEAN > PASS) then confidence
        tier_order = {"TIER1": 0, "TIER2": 1, "LEAN": 2, "PASS": 3}
        sorted_games = sorted(
            analyzed_games,
            key=lambda g: (
                tier_order.get(g["signal_profile"]["tier"], 4),
                -g["signal_profile"]["confidence"],
            )
        )
        
        # Generate summary
        tier_counts = {"TIER1": 0, "TIER2": 0, "LEAN": 0, "PASS": 0}
        no_bet_count = 0
        
        for game in analyzed_games:
            tier = game["signal_profile"]["tier"]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            
            if game.get("no_bet_result", {}).get("is_no_bet"):
                no_bet_count += 1
        
        return {
            "games": analyzed_games,
            "sorted_by_tier": sorted_games,
            "summary": {
                "total_games": len(games),
                "tier1": tier_counts["TIER1"],
                "tier2": tier_counts["TIER2"],
                "leans": tier_counts["LEAN"],
                "passes": tier_counts["PASS"],
                "no_bets": no_bet_count,
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    def evaluate_boost(
        self,
        pick: Dict,
        boost_pct: float,
    ) -> Dict:
        """
        Evaluate if a profit boost makes a pick worthwhile.
        
        Args:
            pick: {
                "odds": -110,
                "win_probability": 0.52,
                "tier": "LEAN",
            }
            boost_pct: Boost as decimal (0.25 = 25%)
        
        Returns:
            Dict with boost evaluation and tier change
        """
        odds = pick.get("odds", -110)
        win_prob = pick.get("win_probability", 0.52)
        
        result = self.boost_calculator.evaluate(odds, boost_pct, win_prob)
        
        return {
            "pick": pick.get("name", "Unknown"),
            "base_tier": result.base_tier,
            "boosted_tier": result.boosted_tier,
            "promoted": result.promoted,
            "base_ev": f"{result.base_ev:+.1%}",
            "boosted_ev": f"{result.boosted_ev:+.1%}",
            "verdict": result.verdict,
            "kelly_fraction": f"{result.kelly_fraction:.1%}",
        }
    
    def record_result(
        self,
        game_key: str,
        pick: Dict,
        final_score: Dict,
    ) -> Dict:
        """
        Record post-game result and compute CLV.
        
        Args:
            game_key: "CHI @ BKN"
            pick: {
                "type": "UNDER",
                "line": 218.5,
                "confidence": 85,
                "tier": "TIER1",
                "units": 2.0,
            }
            final_score: {
                "away_score": 105,
                "home_score": 103,
                "total": 208,
                "closing_line": 217.0,
            }
        
        Returns:
            Dict with CLV analysis
        """
        pick_type = pick.get("type", "UNDER")
        your_line = pick.get("line", 0)
        closing_line = final_score.get("closing_line", your_line)
        
        # Determine if bet won
        actual_total = final_score.get("total", 0)
        away_score = final_score.get("away_score", 0)
        home_score = final_score.get("home_score", 0)
        
        if pick_type == "UNDER":
            won = actual_total < your_line
        elif pick_type == "OVER":
            won = actual_total > your_line
        elif pick_type in ("SPREAD_AWAY", "ATS_AWAY"):
            # Away team covers: away_score + spread > home_score
            won = (away_score + your_line) > home_score
        elif pick_type in ("SPREAD_HOME", "ATS_HOME"):
            # Home team covers: home_score + spread > away_score
            won = (home_score + your_line) > away_score
        elif pick_type == "ML_AWAY":
            won = away_score > home_score
        elif pick_type == "ML_HOME":
            won = home_score > away_score
        else:
            logger.warning(f"Unknown pick_type '{pick_type}' — defaulting to LOSS")
            won = False
        
        # Log to CLV tracker
        rec = self.clv_tracker.log_pick(
            game_key=game_key,
            pick_type=pick_type,
            your_line=your_line,
            confidence=pick.get("confidence", 0),
            tier=pick.get("tier", ""),
            units=pick.get("units", 1.0),
        )
        
        self.clv_tracker.capture_closing_line(game_key, pick_type, closing_line)
        self.clv_tracker.record_result(game_key, pick_type, won, actual_total)
        
        return {
            "game_key": game_key,
            "pick": f"{pick_type} {your_line}",
            "result": "WIN" if won else "LOSS",
            "your_line": your_line,
            "closing_line": closing_line,
            "clv": rec.clv if rec.clv else 0,
            "final_score": final_score,
        }

    # ── ML/AI Layer ───────────────────────────────────────────────

    def _ml_analyze(
        self,
        game_key: str,
        odds_data: Optional[Dict],
        signal_profile,
        rest_data: Optional[Dict] = None,
    ) -> Dict:
        """
        Run ML prediction + anomaly detection on a game.
        Returns structured dict that gets merged into analyze_game output.
        """
        try:
            # Build feature vector
            context = {}
            if rest_data:
                context["home_rest_days"] = rest_data.get("home_rest_days", 0)
                context["away_rest_days"] = rest_data.get("away_rest_days", 0)

            features = self.feature_engine.extract(
                odds_data=odds_data,
                signal_profile=signal_profile,
                context=context,
            )

            # 1. Supervised prediction
            prediction = self.pick_model.predict(features)

            # 2. Unsupervised anomaly detection
            anomaly = self.anomaly_detector.detect(features, game_key=game_key)

            # 3. Ingest for future training
            self.anomaly_detector.ingest(features, game_key=game_key)

            # 4. Log prediction for drift monitoring
            self.model_monitor.log_prediction(
                features=features,
                predicted_prob=prediction["win_probability"],
                game_key=game_key,
            )

            return {
                "prediction": prediction,
                "anomaly": anomaly,
                "features_extracted": True,
            }
        except Exception as e:
            logger.error(f"ML analysis failed for {game_key}: {e}")
            return {
                "prediction": {"win_probability": 0.5, "confidence": "ERROR"},
                "anomaly": {"is_anomaly": False},
                "features_extracted": False,
                "error": str(e),
            }

    def ml_record_result(
        self,
        game_key: str,
        odds_data: Optional[Dict],
        signal_profile,
        won: bool,
        pick_type: str = "",
        rest_data: Optional[Dict] = None,
    ) -> Dict:
        """
        Feed game result back to the ML model for learning.
        Called after record_result() to close the feedback loop.
        """
        try:
            context = {}
            if rest_data:
                context["home_rest_days"] = rest_data.get("home_rest_days", 0)
                context["away_rest_days"] = rest_data.get("away_rest_days", 0)

            features = self.feature_engine.extract(
                odds_data=odds_data,
                signal_profile=signal_profile,
                context=context,
            )

            # Record for supervised learning (auto-retrains when threshold met)
            record_result = self.pick_model.record(
                features=features,
                won=won,
                game_key=game_key,
                pick_type=pick_type,
            )

            # Update drift monitor with actual result
            self.model_monitor.log_prediction(
                features=features,
                predicted_prob=self.pick_model.predict(features)["win_probability"],
                actual_won=won,
                game_key=game_key,
            )

            # Check model health
            health = self.model_monitor.check_health()
            if health["drift_detected"]:
                logger.warning(
                    f"Model drift detected ({health['drift_type']}), "
                    f"triggering retrain..."
                )
                self.pick_model.train()
                self.model_monitor.reset_page_hinkley()

            return {
                "recorded": True,
                "model_status": record_result,
                "health": health,
            }
        except Exception as e:
            logger.error(f"ML record failed for {game_key}: {e}")
            return {"recorded": False, "error": str(e)}

    def get_ml_status(self) -> Dict:
        """Get status of all ML components."""
        return {
            "pick_model": self.pick_model.get_status(),
            "anomaly_detector": self.anomaly_detector.get_status(),
            "model_health": self.model_monitor.check_health(),
            "drift_history": self.model_monitor.get_drift_history()[-5:],
        }


# ── CLI Demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 70)
    print("  BETTING ENGINE — Unified Orchestrator Demo")
    print("═" * 70)
    
    engine = BettingEngine()
    
    # ── Demo 1: Analyze a single game with strong signals ────────
    print("\n  Demo 1: Strong RLM + Multiple Confirmation Signals")
    
    game1 = engine.analyze_game(
        game_key="CHI @ BKN",
        odds_data={
            "spread": {"open": -2.5, "current": -4.0, "public_pct": 72},
            "total": {"open": 223.5, "current": 218.5, "over_pct": 68},
            "ml": {"away_ml_pct": 77, "home_ml_pct": 23},
            "books": {"spread_range": 2.0, "total_range": 2.5},
        },
        public_data={"spread_fav_pct": 72, "total_over_pct": 68},
        ats_data={"away_l10_ats": "2-8", "home_l10_ats": "7-3"},
        pace_data={"away_pace_rank": 5, "home_pace_rank": 28, "league_avg_pace": 100},
        rest_data={"away_rest_days": 0, "home_rest_days": 3},
        apply_decay=False,  # Skip decay for demo
    )
    
    profile = game1["signal_profile"]
    print(f"  Game: {game1['game_key']}")
    print(f"  Tier: {profile['tier']} ({profile['confidence']:.0f}% confidence)")
    print(f"  Primary Signals: {len(profile['primary_signals'])}")
    print(f"  Confirmation Signals: {len(profile['confirmation_signals'])}")
    print(f"  Recommended Units: {profile['recommended_units']}")
    
    if game1.get("no_bet_result"):
        print(f"  No-Bet: {game1['no_bet_result']['is_no_bet']}")
    
    # ── Demo 2: Analyze a coin-flip game (no-bet) ────────────────
    print("\n  Demo 2: Coin-Flip Game (No Edge)")
    
    game2 = engine.analyze_game(
        game_key="LAL @ PHX",
        odds_data={
            "spread": {"open": -3.0, "current": -3.0, "public_pct": 51},
            "total": {"open": 225.5, "current": 225.5, "over_pct": 49},
            "ml": {},
            "books": {"spread_range": 0.5, "total_range": 0.5},
        },
        public_data={"spread_fav_pct": 51, "total_over_pct": 49},
        apply_decay=False,
    )
    
    profile2 = game2["signal_profile"]
    no_bet = game2["no_bet_result"]
    print(f"  Game: {game2['game_key']}")
    print(f"  Tier: {profile2['tier']}")
    print(f"  No-Bet Detected: {no_bet['is_no_bet']}")
    print(f"  Confidence: {no_bet['confidence']:.0f}%")
    print(f"  Recommendation: {no_bet['recommendation'][:80]}...")
    
    # ── Demo 3: Analyze a slate ───────────────────────────────────
    print("\n  Demo 3: Analyzing Full Slate")
    
    slate = [
        {
            "game_key": "CHI @ BKN",
            "odds_data": {
                "spread": {"open": -2.5, "current": -4.0, "public_pct": 72},
                "total": {"open": 223.5, "current": 218.5, "over_pct": 68},
                "books": {"spread_range": 2.0},
            },
            "public_data": {"spread_fav_pct": 72},
        },
        {
            "game_key": "LAL @ PHX",
            "odds_data": {
                "spread": {"open": -3.0, "current": -3.0, "public_pct": 51},
                "total": {"open": 225.5, "current": 225.5},
                "books": {"spread_range": 0.5},
            },
            "public_data": {"spread_fav_pct": 51},
        },
        {
            "game_key": "MIL @ ORL",
            "odds_data": {
                "spread": {"open": -10.5, "current": -11.5, "public_pct": 65},
                "total": {"open": 220.0, "current": 218.0},
                "books": {"spread_range": 1.0},
            },
            "public_data": {"spread_fav_pct": 65},
        },
    ]
    
    results = engine.analyze_slate(slate, apply_decay=False)
    
    print(f"  Total Games: {results['summary']['total_games']}")
    print(f"  TIER 1: {results['summary']['tier1']}")
    print(f"  TIER 2: {results['summary']['tier2']}")
    print(f"  Leans: {results['summary']['leans']}")
    print(f"  Passes: {results['summary']['passes']}")
    print(f"  No-Bets: {results['summary']['no_bets']}")
    
    print("\n  Top Picks (sorted by tier/confidence):")
    for game in results["sorted_by_tier"][:3]:
        prof = game["signal_profile"]
        print(f"    {game['game_key']}: {prof['tier']} ({prof['confidence']:.0f}%)")
    
    # ── Demo 4: Evaluate a boost ──────────────────────────────────
    print("\n  Demo 4: Profit Boost Evaluation")
    
    pick = {
        "name": "CHI/BKN Under 218.5",
        "odds": -110,
        "win_probability": 0.57,
        "tier": "LEAN",
    }
    
    boost_result = engine.evaluate_boost(pick, boost_pct=0.25)
    print(f"  Pick: {boost_result['pick']}")
    print(f"  Base: {boost_result['base_tier']} (EV: {boost_result['base_ev']})")
    print(f"  Boosted: {boost_result['boosted_tier']} (EV: {boost_result['boosted_ev']})")
    print(f"  Promoted: {boost_result['promoted']}")
    print(f"  Verdict: {boost_result['verdict']}")
    
    print("\n" + "═" * 70)
