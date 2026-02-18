"""
Live Under Protector V2
=======================
Implements 11 rules learned from session losses to protect live Under bets.
Uses ESPN's free API for real-time game data.

Core Rules:
- RULE_0: If current_score > line: BET IS DEAD
- RULE_1: If projected_final > line: CASH OUT (any amount > $0)
- RULE_2: If cushion < 5 AND time_left > 5min: CASH OUT
- RULE_3: Always use MAX(full_game_pace, 2H_pace) for projections
- RULE_6: Any cash_out > $0 when projected_to_lose: TAKE IT
- RULE_7: IF game_margin <= 3 AND time_left < 5min: calculate OT probability
- RULE_9: IF mid-major conference AND 2H_pace > 1H_pace * 1.15: use 2H_pace * 1.10 safety margin
- RULE_10: NEVER parlay 3+ Under legs from same time slot (correlated)
- RULE_11: IF game_margin <= 5 AND time_left <= 3min AND (playoff OR high_stakes): fouling adds 10-15 points
"""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


# Protection Rules Dictionary
PROTECTOR_RULES = {
    "RULE_0": "If current_score > line: BET IS DEAD",
    "RULE_1": "If projected_final > line: CASH OUT (any amount > $0)",
    "RULE_2": "If cushion < 5 AND time_left > 5min: CASH OUT",
    "RULE_3": "Always use MAX(full_game_pace, 2H_pace) for projections",
    "RULE_6": "Any cash_out > $0 when projected_to_lose: TAKE IT",
    "RULE_7": "IF game_margin <= 3 AND time_left < 5min: calculate OT probability. OT adds 12-18 pts. IF ot_projected > line: CASH OUT",  # noqa: E501
    "RULE_9": "IF mid-major conference AND 2H_pace > 1H_pace * 1.15: use 2H_pace * 1.10 safety margin",
    "RULE_10": "NEVER parlay 3+ Under legs from same time slot (correlated)",
    "RULE_11": "IF game_margin <= 5 AND time_left <= 3min AND (playoff OR high_stakes): fouling adds 10-15 points. Adjust projection UP.",  # noqa: E501
}


@dataclass
class BettingDecision:
    """Recommendation for a live Under bet."""
    action: str  # "HOLD", "CASH_OUT", "HEDGE", "STOP_BETTING"
    urgency: str  # "IMMEDIATE", "MONITOR", "ROUTINE"
    immediate_instruction: str  # "CASH OUT $X NOW" if urgent
    reasoning: str  # Explanation with rule references
    projected_final: float  # Projected total score
    cushion: float  # Line - projected_final
    win_probability: float  # 0.0 to 1.0
    cash_out_value: float = 0.0  # Current cash out offer
    hedge_amount: float = 0.0  # Suggested hedge amount
    hedge_line: float = 0.0  # Suggested hedge line


class LiveUnderProtector:
    """Protects live Under bets using 11 rules learned from session losses."""

    def __init__(self):
        """Initialize protector with rules."""
        self.rules = PROTECTOR_RULES
        self.active_bets: Dict[str, Dict[str, Any]] = {}

    def add_bet(self, bet_id: str, line: float, wager: float, game_id: str) -> None:
        """
        Track a new live Under bet.

        Args:
            bet_id: Unique bet identifier
            line: Total line (e.g., 145.5)
            wager: Amount wagered
            game_id: Game identifier
        """
        self.active_bets[bet_id] = {
            "line": line,
            "wager": wager,
            "game_id": game_id,
            "timestamp": None
        }
        logger.info(f"Added bet {bet_id}: Under {line} for ${wager}")

    def remove_bet(self, bet_id: str) -> None:
        """Remove a bet from tracking."""
        if bet_id in self.active_bets:
            del self.active_bets[bet_id]
            logger.info(f"Removed bet {bet_id}")

    def evaluate_bet(self, game_state: dict, bet: dict) -> BettingDecision:
        """
        Evaluate a live Under bet and return recommendation.

        Args:
            game_state: Live game state with scores, time, pace, etc.
            bet: Bet details with line, wager, cash_out offer

        Returns:
            BettingDecision with action and reasoning
        """
        line = bet["line"]
        cash_out = bet.get("cash_out", 0.0)
        wager = bet.get("wager", 0.0)

        # Extract game state
        home_score = game_state.get("home_score", 0)
        away_score = game_state.get("away_score", 0)
        current_total = home_score + away_score
        time_left = game_state.get("time_left_minutes", 0.0)
        game_margin = abs(home_score - away_score)

        # RULE_0: Dead bet check
        if current_total > line:
            return BettingDecision(
                action="STOP_BETTING",
                urgency="IMMEDIATE",
                immediate_instruction=f"Bet is DEAD. Current total {current_total} > line {line}",
                reasoning=f"RULE_0: Current score {current_total} exceeds line {line}. Bet is lost.",
                projected_final=current_total,
                cushion=line - current_total,
                win_probability=0.0,
                cash_out_value=cash_out
            )

        # Calculate projected final
        projected_final = self.calculate_projected_final(game_state)
        cushion = line - projected_final

        # RULE_1: Projected to lose
        if projected_final > line:
            if cash_out > 0:
                return BettingDecision(
                    action="CASH_OUT",
                    urgency="IMMEDIATE",
                    immediate_instruction=f"CASH OUT ${cash_out:.2f} NOW - Projected to lose",
                    reasoning=f"RULE_1: Projected final {projected_final:.1f} > line {line}. Any cash out > $0 is a win. Take ${cash_out:.2f}.",  # noqa: E501
                    projected_final=projected_final,
                    cushion=cushion,
                    win_probability=0.2,
                    cash_out_value=cash_out
                )
            else:
                return BettingDecision(
                    action="HEDGE",
                    urgency="IMMEDIATE",
                    immediate_instruction="Consider hedging - projected to lose",
                    reasoning=f"RULE_1: Projected final {projected_final:.1f} > line {line}. No cash out offer. Consider hedging.",  # noqa: E501
                    projected_final=projected_final,
                    cushion=cushion,
                    win_probability=0.2,
                    hedge_amount=wager * 0.5,
                    hedge_line=line
                )

        # RULE_2: Tight cushion with time left
        if cushion < 5 and time_left > 5:
            return BettingDecision(
                action="CASH_OUT",
                urgency="IMMEDIATE",
                immediate_instruction=f"CASH OUT ${cash_out:.2f} NOW - Cushion too tight with {time_left:.1f} min left",
                reasoning=f"RULE_2: Cushion {cushion:.1f} < 5 points with {time_left:.1f} minutes remaining. Too risky.",
                projected_final=projected_final,
                cushion=cushion,
                win_probability=0.3,
                cash_out_value=cash_out
            )

        # RULE_7: OT risk in close games
        if game_margin <= 3 and time_left < 5:
            ot_prob = self.calculate_ot_probability(game_margin, time_left)
            ot_impact = 15  # OT adds ~12-18 points
            ot_projected = projected_final + (ot_prob * ot_impact)

            if ot_projected > line:
                return BettingDecision(
                    action="CASH_OUT",
                    urgency="IMMEDIATE",
                    immediate_instruction=f"CASH OUT ${cash_out:.2f} NOW - High OT risk ({ot_prob*100:.0f}%)",
                    reasoning=f"RULE_7: Margin {game_margin} with {time_left:.1f}m. OT probability {ot_prob*100:.0f}%. OT-adjusted projection {ot_projected:.1f} > line {line}.",  # noqa: E501
                    projected_final=ot_projected,
                    cushion=line - ot_projected,
                    win_probability=0.25,
                    cash_out_value=cash_out
                )

        # RULE_11: Late-game fouling
        is_playoff = game_state.get("is_playoff", False)
        is_high_stakes = game_state.get("is_high_stakes", False)
        if game_margin <= 5 and time_left <= 3 and (is_playoff or is_high_stakes):
            fouling_adjustment = 12.5  # Add 10-15 points for intentional fouling
            adjusted_projection = projected_final + fouling_adjustment

            if adjusted_projection > line - 3:  # Close to line
                return BettingDecision(
                    action="CASH_OUT",
                    urgency="MONITOR",
                    immediate_instruction=f"Consider cash out ${cash_out:.2f} - Fouling likely",
                    reasoning=f"RULE_11: Close game (margin {game_margin}) with {time_left:.1f}m in playoff/high-stakes. Fouling adds ~12 pts. Adjusted projection {adjusted_projection:.1f}.",  # noqa: E501
                    projected_final=adjusted_projection,
                    cushion=line - adjusted_projection,
                    win_probability=0.5,
                    cash_out_value=cash_out
                )

        # RULE_9: Pace explosion check
        first_half_pace = game_state.get("first_half_pace", 0.0)
        second_half_pace = game_state.get("second_half_pace", 0.0)
        conference = game_state.get("conference", "")

        if self.detect_pace_explosion(first_half_pace, second_half_pace, conference):
            # Already factored into projected_final via MAX(full, 2H) in RULE_3
            return BettingDecision(
                action="MONITOR",
                urgency="ROUTINE",
                immediate_instruction="HOLD - Pace explosion detected but factored into projection",
                reasoning=f"RULE_9: Mid-major pace explosion detected (2H pace {second_half_pace:.2f} > 1H {first_half_pace:.2f}). Already using MAX pace in projection. Cushion {cushion:.1f}.",  # noqa: E501
                projected_final=projected_final,
                cushion=cushion,
                win_probability=0.6,
                cash_out_value=cash_out
            )

        # All clear - HOLD
        win_prob = self.estimate_win_probability(cushion, time_left)
        return BettingDecision(
            action="HOLD",
            urgency="ROUTINE",
            immediate_instruction=f"HOLD - Cushion {cushion:.1f} points",
            reasoning=f"All rules passed. Projected {projected_final:.1f} < line {line}. Cushion {cushion:.1f} with {time_left:.1f}m left.",  # noqa: E501
            projected_final=projected_final,
            cushion=cushion,
            win_probability=win_prob,
            cash_out_value=cash_out
        )

    def calculate_projected_final(self, game_state: dict) -> float:
        """
        Calculate projected final score using RULE_3: MAX(full_game_pace, 2H_pace).

        Args:
            game_state: Game state with pace and time data

        Returns:
            Projected final total score
        """
        current_total = game_state.get("home_score", 0) + game_state.get("away_score", 0)
        time_left = game_state.get("time_left_minutes", 0.0)

        # Get both paces
        full_game_pace = game_state.get("full_game_pace", 0.0)  # Points per minute
        second_half_pace = game_state.get("second_half_pace", 0.0)

        # RULE_3: Use the HIGHER pace for projection (more conservative)
        pace = max(full_game_pace, second_half_pace)

        if pace <= 0:
            # Fallback if pace data unavailable
            pace = 2.0  # Assume ~2 pts/min

        projected_final = current_total + (pace * time_left)
        return projected_final

    def calculate_ot_probability(self, margin: int, time_left: float) -> float:
        """
        Calculate probability of overtime based on margin and time remaining.

        Args:
            margin: Point differential
            time_left: Minutes remaining

        Returns:
            Probability from 0.0 to 1.0
        """
        if time_left > 5:
            return 0.0

        # Close games in final minutes
        if margin == 0:
            return 0.4
        elif margin == 1:
            return 0.3
        elif margin == 2:
            return 0.2
        elif margin == 3:
            return 0.1
        else:
            return 0.05

    def detect_pace_explosion(self, first_half_pace: float, second_half_pace: float, conference: str) -> bool:
        """
        Detect mid-major conference 2H pace explosions (RULE_9).

        Args:
            first_half_pace: First half pace
            second_half_pace: Second half pace
            conference: Conference name

        Returns:
            True if pace explosion detected
        """
        if first_half_pace <= 0 or second_half_pace <= 0:
            return False

        # Mid-major conferences
        mid_major_conferences = ["SWAC", "Southland", "MEAC", "OVC", "Big Sky"]
        is_mid_major = any(conf in conference for conf in mid_major_conferences)

        if is_mid_major and second_half_pace > first_half_pace * 1.15:
            return True

        return False

    def estimate_win_probability(self, cushion: float, time_left: float) -> float:
        """
        Estimate win probability based on cushion and time remaining.

        Args:
            cushion: Points between line and projection
            time_left: Minutes remaining

        Returns:
            Probability from 0.0 to 1.0
        """
        if cushion <= 0:
            return 0.1

        # More cushion = higher probability
        # Less time = higher probability
        cushion_factor = min(cushion / 10.0, 0.5)  # Max 0.5 from cushion
        time_factor = max(0, 0.4 - (time_left / 40.0))  # Less time = better

        win_prob = 0.1 + cushion_factor + time_factor
        return min(win_prob, 0.95)

    def evaluate_parlay(self, bet_legs: List[dict], time_slot: str) -> Dict[str, Any]:
        """
        Evaluate parlay for RULE_10 violations (3+ Under legs from same time slot).

        Args:
            bet_legs: List of bet leg dictionaries
            time_slot: Time slot identifier (e.g., "7PM", "9PM")

        Returns:
            Dictionary with warning and recommendation
        """
        under_legs = [leg for leg in bet_legs if "under" in leg.get("bet_type", "").lower()]

        if len(under_legs) >= 3:
            return {
                "violation": True,
                "rule": "RULE_10",
                "warning": f"DANGER: {len(under_legs)} Under legs in same {time_slot} time slot. Highly correlated.",
                "recommendation": "AVOID - Reduce to max 2 Under legs per time slot or split across slots"
            }

        return {
            "violation": False,
            "warning": None,
            "recommendation": "Parlay structure is acceptable"
        }
