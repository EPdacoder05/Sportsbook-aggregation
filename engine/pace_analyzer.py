"""
Pace Analyzer
=============
Analyzes game pace with focus on 2H pace isolation and projections.
Uses ESPN live data for real-time calculations.

Key Features:
- 2H pace isolation from full-game pace
- Conference-specific pace inflation factors (NCAAB 2H runs 15-35% faster)
- OT risk calculation
- Late-game fouling adjustments
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class PaceAnalyzer:
    """Analyzes game pace and projects final scores."""

    # Conference 2H pace inflation factors based on historical data
    # NCAAB 2H typically runs faster due to shorter shot clock, fatigue, desperation
    CONFERENCE_2H_INFLATION = {
        "Power 5": 1.15,      # Power 5 conferences (ACC, Big Ten, etc.)
        "Mid-Major": 1.25,    # Mid-major conferences
        "SWAC": 1.35,         # SWAC (Historically highest pace increases)
        "Southland": 1.30,    # Southland conference
        "MEAC": 1.30,         # MEAC
        "OVC": 1.25,          # Ohio Valley
        "Big Sky": 1.25,      # Big Sky
        "default": 1.20       # Default for unknown conferences
    }

    def __init__(self):
        """Initialize pace analyzer."""
        pass

    def calculate_pace(self, score: int, elapsed_minutes: float) -> float:
        """
        Calculate pace (points per minute).

        Args:
            score: Total points scored
            elapsed_minutes: Minutes elapsed

        Returns:
            Points per minute (float)
        """
        if elapsed_minutes <= 0:
            return 0.0

        return score / elapsed_minutes

    def get_2h_pace(self, game_state: dict) -> float:
        """
        Isolate 2H-only pace from game state.

        Args:
            game_state: Game state with scores and period info

        Returns:
            2H pace in points per minute
        """
        # Extract scores
        current_total = game_state.get("home_score", 0) + game_state.get("away_score", 0)
        halftime_total = game_state.get("halftime_total", 0)

        # If we don't have halftime total, can't calculate 2H pace
        if halftime_total == 0:
            return 0.0

        # Calculate 2H points
        second_half_points = current_total - halftime_total

        # Get elapsed time in second half
        period = game_state.get("period", 1)
        clock_minutes = game_state.get("clock_minutes", 20.0)

        if period == 1:
            # Still in first half
            return 0.0
        elif period == 2:
            # In second half - calculate elapsed 2H time
            second_half_length = 20.0  # 20 minutes for college basketball
            elapsed_2h = second_half_length - clock_minutes
        else:
            # OT or post-game - use full 2H
            elapsed_2h = 20.0

        if elapsed_2h <= 0:
            return 0.0

        second_half_pace = second_half_points / elapsed_2h
        return second_half_pace

    def project_final_score(self, game_state: dict) -> float:
        """
        Project final score using MAX(full_game_pace, 2H_pace) * remaining_time + current_score.

        Args:
            game_state: Game state with scores, time, and pace

        Returns:
            Projected final total score
        """
        current_total = game_state.get("home_score", 0) + game_state.get("away_score", 0)
        time_left = game_state.get("time_left_minutes", 0.0)

        # Get full game pace
        game_minutes = game_state.get("game_minutes", 40.0)
        elapsed_minutes = game_minutes - time_left
        full_game_pace = self.calculate_pace(current_total, elapsed_minutes) if elapsed_minutes > 0 else 0.0

        # Get 2H pace
        second_half_pace = self.get_2h_pace(game_state)

        # Use MAX pace (RULE_3 from live_under_protector)
        pace = max(full_game_pace, second_half_pace)

        # If no pace data, use default
        if pace <= 0:
            pace = 2.0  # Default ~2 pts/min

        # Apply conference inflation if in 2H
        period = game_state.get("period", 1)
        if period >= 2 and second_half_pace > full_game_pace:
            conference = game_state.get("conference", "")
            inflation = self._get_conference_inflation(conference)
            pace = pace * inflation

        projected_final = current_total + (pace * time_left)
        return projected_final

    def _get_conference_inflation(self, conference: str) -> float:
        """
        Get pace inflation factor for conference.

        Args:
            conference: Conference name

        Returns:
            Inflation multiplier
        """
        # Check for known conferences
        for conf_name, multiplier in self.CONFERENCE_2H_INFLATION.items():
            if conf_name.lower() in conference.lower():
                return multiplier

        return self.CONFERENCE_2H_INFLATION["default"]

    def calculate_ot_risk(self, home_score: int, away_score: int, time_left: float) -> Dict[str, Any]:
        """
        Calculate overtime risk and projected OT points.

        Args:
            home_score: Home team score
            away_score: Away team score
            time_left: Minutes remaining

        Returns:
            Dictionary with probability and projected_ot_points
        """
        margin = abs(home_score - away_score)

        # OT risk only relevant in final 5 minutes
        if time_left > 5:
            return {
                "probability": 0.0,
                "projected_ot_points": 0,
                "reasoning": "Too much time remaining to calculate OT risk"
            }

        # Calculate OT probability based on margin and time
        ot_probability = 0.0
        if margin == 0:
            ot_probability = 0.4
        elif margin == 1:
            ot_probability = 0.3 if time_left < 2 else 0.2
        elif margin == 2:
            ot_probability = 0.2 if time_left < 2 else 0.1
        elif margin == 3:
            ot_probability = 0.1 if time_left < 1 else 0.05
        else:
            ot_probability = 0.02

        # OT adds 12-18 points on average (5 min period, fast pace)
        projected_ot_points = 15  # Use middle of range

        return {
            "probability": ot_probability,
            "projected_ot_points": projected_ot_points,
            "reasoning": f"Margin {margin} with {time_left:.1f}m: {ot_probability*100:.0f}% OT probability. OT adds ~{projected_ot_points} pts."  # noqa: E501
        }

    def calculate_fouling_adjustment(self, margin: int, time_left: float, is_playoff: bool = False) -> float:
        """
        Calculate late-game fouling adjustment (RULE_11).

        Args:
            margin: Point differential
            time_left: Minutes remaining
            is_playoff: Whether it's a playoff/tournament game

        Returns:
            Points to add to projection
        """
        # Intentional fouling only happens in close games at end
        if time_left > 3 or margin > 5:
            return 0.0

        # Playoff games have more aggressive fouling
        if is_playoff:
            if margin <= 3 and time_left <= 2:
                return 15.0  # Aggressive fouling adds 15 pts
            elif margin <= 5 and time_left <= 3:
                return 12.0
        else:
            if margin <= 3 and time_left <= 2:
                return 12.0  # Regular season fouling
            elif margin <= 5 and time_left <= 3:
                return 10.0

        return 0.0

    def analyze_pace_trend(self, game_state: dict) -> Dict[str, Any]:
        """
        Analyze pace trends throughout the game.

        Args:
            game_state: Game state with scores and timing

        Returns:
            Dictionary with pace analysis
        """
        full_game_pace = game_state.get("full_game_pace", 0.0)
        second_half_pace = self.get_2h_pace(game_state)
        first_half_pace = game_state.get("first_half_pace", 0.0)

        pace_change = 0.0
        pace_direction = "stable"

        if first_half_pace > 0 and second_half_pace > 0:
            pace_change = ((second_half_pace - first_half_pace) / first_half_pace) * 100
            if pace_change > 15:
                pace_direction = "accelerating"
            elif pace_change < -15:
                pace_direction = "decelerating"

        return {
            "full_game_pace": full_game_pace,
            "first_half_pace": first_half_pace,
            "second_half_pace": second_half_pace,
            "pace_change_pct": pace_change,
            "pace_direction": pace_direction,
            "using_2h_pace": second_half_pace > full_game_pace,
            "reasoning": self._get_pace_reasoning(pace_direction, pace_change)
        }

    def _get_pace_reasoning(self, direction: str, change_pct: float) -> str:
        """Generate reasoning for pace trend."""
        if direction == "accelerating":
            return f"2H pace accelerating by {change_pct:.1f}%. Teams playing faster - expect higher scoring."
        elif direction == "decelerating":
            return f"2H pace slowing by {abs(change_pct):.1f}%. Teams slowing down - expect lower scoring."
        else:
            return "Pace is stable. No significant trend change."

    def get_projection_breakdown(self, game_state: dict) -> Dict[str, Any]:
        """
        Get detailed projection breakdown with all factors.

        Args:
            game_state: Complete game state

        Returns:
            Dictionary with all projection components
        """
        current_total = game_state.get("home_score", 0) + game_state.get("away_score", 0)
        time_left = game_state.get("time_left_minutes", 0.0)

        # Base projection
        base_projection = self.project_final_score(game_state)

        # OT risk
        home_score = game_state.get("home_score", 0)
        away_score = game_state.get("away_score", 0)
        ot_risk = self.calculate_ot_risk(home_score, away_score, time_left)
        ot_adjusted_projection = base_projection + (ot_risk["probability"] * ot_risk["projected_ot_points"])

        # Fouling adjustment
        margin = abs(home_score - away_score)
        is_playoff = game_state.get("is_playoff", False)
        fouling_adj = self.calculate_fouling_adjustment(margin, time_left, is_playoff)
        fouling_adjusted_projection = base_projection + fouling_adj

        # Full projection
        full_projection = base_projection + (ot_risk["probability"] * ot_risk["projected_ot_points"]) + fouling_adj

        # Pace analysis
        pace_trend = self.analyze_pace_trend(game_state)

        return {
            "current_total": current_total,
            "time_left": time_left,
            "base_projection": base_projection,
            "ot_risk": ot_risk,
            "ot_adjusted_projection": ot_adjusted_projection,
            "fouling_adjustment": fouling_adj,
            "fouling_adjusted_projection": fouling_adjusted_projection,
            "full_projection": full_projection,
            "pace_trend": pace_trend,
            "recommendation": self._get_recommendation(game_state, full_projection)
        }

    def _get_recommendation(self, game_state: dict, projection: float) -> str:
        """Generate recommendation based on projection."""
        line = game_state.get("line", 0.0)
        if line == 0:
            return "No line available for comparison"

        cushion = line - projection

        if cushion > 10:
            return f"Strong cushion of {cushion:.1f} points. Under looks safe."
        elif cushion > 5:
            return f"Comfortable cushion of {cushion:.1f} points. Under is favored."
        elif cushion > 0:
            return f"Tight cushion of {cushion:.1f} points. Under is risky."
        else:
            return f"Projected over by {abs(cushion):.1f} points. Under is losing."
