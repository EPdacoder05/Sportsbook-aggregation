"""
Greed Index Engine
==================
Session tracker and withdrawal recommendation engine to prevent emotional losses.

Tracks session metrics and provides real-time greed scores with withdrawal recommendations.

Greed Thresholds:
- COLD (0-25): Keep playing disciplined
- WARM (26-50): One more bet max, withdraw 50%
- HOT (51-70): STOP and withdraw 60%
- BURNING (71-90): STOP NOW, withdraw 75%
- MELTDOWN (91-100): Walk away immediately
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Greed Threshold Definitions
GREED_THRESHOLDS = {
    "COLD": (0, 25),      # Keep playing disciplined
    "WARM": (26, 50),     # One more bet max, withdraw 50%
    "HOT": (51, 70),      # STOP and withdraw 60%
    "BURNING": (71, 90),  # STOP NOW, withdraw 75%
    "MELTDOWN": (91, 100)  # Walk away immediately
}


# Withdrawal Rules
WITHDRAWAL_RULES = {
    "W1": "Profit >= $200: Withdraw 50% before next bet",
    "W2": "Profit >= $500: Withdraw 60%",
    "W3": "Drawdown 30% from peak: STOP, withdraw 75%",
    "W4": "After 10 bets: EVALUATE before bet 11",
    "W5": "Prioritize DK withdrawals over FD (faster payout)",
    "W6": "NEVER re-deposit same day as withdrawal",
}


@dataclass
class BetRecord:
    """Record of a single bet in the session."""
    wager: float
    result: float  # Net result (win/loss amount)
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    book: str = ""


class GreedIndexEngine:
    """Track session progress and provide withdrawal recommendations."""

    def __init__(self):
        """Initialize session tracker."""
        self.session_bets: List[BetRecord] = []
        self.session_peak: float = 0.0
        self.total_wagered: float = 0.0
        self.session_start: datetime = datetime.now()

    def add_bet(self, wager: float, result: float, description: str, book: str = "") -> None:
        """
        Record a bet in the current session.

        Args:
            wager: Amount wagered
            result: Net result (positive for win, negative for loss)
            description: Bet description
            book: Sportsbook name (e.g., "DK", "FD")
        """
        bet = BetRecord(
            wager=wager,
            result=result,
            description=description,
            book=book
        )
        self.session_bets.append(bet)
        self.total_wagered += wager

        # Update peak
        current_profit = self.get_session_profit()
        if current_profit > self.session_peak:
            self.session_peak = current_profit

        logger.info(f"Bet recorded: {description} | Wager: ${wager} | Result: ${result:+.2f}")

    def get_session_profit(self) -> float:
        """Calculate total session profit/loss."""
        return sum(bet.result for bet in self.session_bets)

    def get_greed_score(self) -> int:
        """
        Calculate greed score (0-100) based on session metrics.

        Factors:
        - Win streak length
        - Profit vs peak drawdown
        - Number of bets in session
        - Recent bet sizing trends

        Returns:
            Integer from 0 to 100
        """
        if not self.session_bets:
            return 0

        score = 0

        # Factor 1: Profit level (max 30 points)
        profit = self.get_session_profit()
        if profit >= 500:
            score += 30
        elif profit >= 300:
            score += 25
        elif profit >= 200:
            score += 20
        elif profit >= 100:
            score += 15
        elif profit >= 50:
            score += 10

        # Factor 2: Win streak (max 25 points)
        win_streak = 0
        for bet in reversed(self.session_bets):
            if bet.result > 0:
                win_streak += 1
            else:
                break

        if win_streak >= 5:
            score += 25
        elif win_streak >= 4:
            score += 20
        elif win_streak >= 3:
            score += 15
        elif win_streak >= 2:
            score += 10

        # Factor 3: Drawdown from peak (max 20 points)
        drawdown_pct = 0
        if self.session_peak > 0:
            drawdown_pct = ((self.session_peak - profit) / self.session_peak) * 100

        if drawdown_pct >= 30:
            score += 20  # High risk - giving back gains
        elif drawdown_pct >= 20:
            score += 15
        elif drawdown_pct >= 10:
            score += 10

        # Factor 4: Number of bets (max 15 points)
        bet_count = len(self.session_bets)
        if bet_count >= 15:
            score += 15
        elif bet_count >= 12:
            score += 12
        elif bet_count >= 10:
            score += 10
        elif bet_count >= 8:
            score += 8

        # Factor 5: Recent bet sizing trends (max 10 points)
        if len(self.session_bets) >= 3:
            recent_wagers = [bet.wager for bet in self.session_bets[-3:]]
            first_wagers = [bet.wager for bet in self.session_bets[:3]]

            avg_recent = sum(recent_wagers) / len(recent_wagers)
            avg_first = sum(first_wagers) / len(first_wagers)

            if avg_recent > avg_first * 1.5:
                score += 10  # Bet sizes increasing - chasing or overconfident
            elif avg_recent > avg_first * 1.2:
                score += 5

        return min(score, 100)

    def get_greed_level(self) -> str:
        """
        Get greed level based on current score.

        Returns:
            One of: "COLD", "WARM", "HOT", "BURNING", "MELTDOWN"
        """
        score = self.get_greed_score()

        for level, (low, high) in GREED_THRESHOLDS.items():
            if low <= score <= high:
                return level

        return "COLD"

    def get_withdrawal_recommendation(self) -> Dict[str, Any]:
        """
        Get withdrawal recommendation based on current session state.

        Returns:
            Dictionary with recommendation, amount, reasoning
        """
        profit = self.get_session_profit()
        greed_level = self.get_greed_level()
        bet_count = len(self.session_bets)

        recommendation = {
            "should_withdraw": False,
            "withdraw_amount": 0.0,
            "withdraw_pct": 0.0,
            "reasoning": "",
            "urgency": "ROUTINE",
            "rules_triggered": []
        }

        # Rule W1: Profit >= $200
        if profit >= 200:
            recommendation["should_withdraw"] = True
            recommendation["withdraw_pct"] = 0.50
            recommendation["withdraw_amount"] = profit * 0.50
            recommendation["reasoning"] = "Profit >= $200. Lock in 50% of gains."
            recommendation["rules_triggered"].append("W1")

        # Rule W2: Profit >= $500
        if profit >= 500:
            recommendation["withdraw_pct"] = 0.60
            recommendation["withdraw_amount"] = profit * 0.60
            recommendation["reasoning"] = "Profit >= $500. Lock in 60% of gains."
            recommendation["rules_triggered"].append("W2")

        # Rule W3: Drawdown 30% from peak
        if self.session_peak > 0:
            drawdown_pct = ((self.session_peak - profit) / self.session_peak) * 100
            if drawdown_pct >= 30:
                recommendation["should_withdraw"] = True
                recommendation["withdraw_pct"] = 0.75
                recommendation["withdraw_amount"] = profit * 0.75 if profit > 0 else 0
                recommendation["reasoning"] = f"Drawdown {drawdown_pct:.0f}% from peak ${self.session_peak:.2f}. STOP and withdraw 75% of remaining profit."  # noqa: E501
                recommendation["urgency"] = "IMMEDIATE"
                recommendation["rules_triggered"].append("W3")

        # Rule W4: After 10 bets, evaluate
        if bet_count >= 10:
            recommendation["reasoning"] += " | You've placed 10+ bets. Take a break and evaluate."
            recommendation["rules_triggered"].append("W4")

        # Greed level warnings
        if greed_level == "HOT":
            recommendation["should_withdraw"] = True
            recommendation["urgency"] = "IMMEDIATE"
            recommendation["reasoning"] += f" | Greed level: {greed_level}. STOP betting now."

        elif greed_level == "BURNING":
            recommendation["should_withdraw"] = True
            recommendation["withdraw_pct"] = max(recommendation["withdraw_pct"], 0.75)
            recommendation["withdraw_amount"] = profit * 0.75 if profit > 0 else 0
            recommendation["urgency"] = "IMMEDIATE"
            recommendation["reasoning"] = f"Greed level: {greed_level}. STOP NOW and withdraw 75%."

        elif greed_level == "MELTDOWN":
            recommendation["should_withdraw"] = True
            recommendation["withdraw_pct"] = 1.0
            recommendation["withdraw_amount"] = profit if profit > 0 else 0
            recommendation["urgency"] = "CRITICAL"
            recommendation["reasoning"] = f"Greed level: {greed_level}. Walk away IMMEDIATELY. Withdraw ALL profit."

        # Rule W5: Book priority
        dk_balance = sum(bet.result for bet in self.session_bets if bet.book == "DK")
        if dk_balance > 0:
            recommendation["book_priority"] = "DK"
            recommendation["reasoning"] += " | Prioritize DK withdrawal (faster payout)."
            recommendation["rules_triggered"].append("W5")

        return recommendation

    def should_stop_betting(self) -> bool:
        """
        Determine if betting should stop based on greed level.

        Returns:
            True if should stop betting
        """
        greed_level = self.get_greed_level()
        return greed_level in ["HOT", "BURNING", "MELTDOWN"]

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive session summary.

        Returns:
            Dictionary with all session metrics
        """
        profit = self.get_session_profit()
        greed_score = self.get_greed_score()
        greed_level = self.get_greed_level()

        # Calculate win rate
        wins = sum(1 for bet in self.session_bets if bet.result > 0)
        losses = sum(1 for bet in self.session_bets if bet.result < 0)
        win_rate = (wins / len(self.session_bets)) * 100 if self.session_bets else 0

        # ROI
        roi = (profit / self.total_wagered) * 100 if self.total_wagered > 0 else 0

        # Book breakdown
        book_breakdown = {}
        for bet in self.session_bets:
            if bet.book:
                if bet.book not in book_breakdown:
                    book_breakdown[bet.book] = {"wagers": 0, "profit": 0.0}
                book_breakdown[bet.book]["wagers"] += bet.wager
                book_breakdown[bet.book]["profit"] += bet.result

        return {
            "session_duration": str(datetime.now() - self.session_start),
            "total_bets": len(self.session_bets),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_wagered": self.total_wagered,
            "profit": profit,
            "roi": roi,
            "session_peak": self.session_peak,
            "greed_score": greed_score,
            "greed_level": greed_level,
            "book_breakdown": book_breakdown,
            "should_stop": self.should_stop_betting()
        }

    def reset_session(self) -> None:
        """Reset session tracker for a new session."""
        summary = self.get_session_summary()
        logger.info(f"Session ended. Summary: {summary}")

        self.session_bets = []
        self.session_peak = 0.0
        self.total_wagered = 0.0
        self.session_start = datetime.now()
