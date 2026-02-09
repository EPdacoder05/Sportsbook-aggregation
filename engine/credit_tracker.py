"""
Odds API Credit Tracker
========================
Tracks Odds API credit usage to stay within the 500/month free tier.
Persists usage to a JSON file so it survives restarts.

Credit costs:
  /sports           = FREE
  /events           = FREE
  /odds (per call)  = markets × regions  (e.g. spreads+totals, us = 2)
  /scores           = 1 (live+upcoming) or 2 (with daysFrom)
  historical        = 10 × markets × regions  (TOO EXPENSIVE for free tier)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

TRACKER_FILE = Path(__file__).parent.parent / "data" / "credit_usage.json"
MONTHLY_LIMIT = 500  # Free tier
SAFETY_BUFFER = 20   # Reserve 20 credits as safety margin


class CreditTracker:
    """Tracks and enforces Odds API credit budget."""

    def __init__(self, tracker_file: Optional[Path] = None):
        self.tracker_file = tracker_file or TRACKER_FILE
        self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        """Load usage data from disk."""
        if self.tracker_file.exists():
            with open(self.tracker_file, "r") as f:
                self.data = json.load(f)
        else:
            self.data = self._empty_month()

        # Reset if we're in a new month
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if self.data.get("month") != current_month:
            logger.info(f"New month detected ({current_month}). Resetting credit tracker.")
            self.data = self._empty_month()
            self._save()

    def _empty_month(self) -> Dict:
        return {
            "month": datetime.now(timezone.utc).strftime("%Y-%m"),
            "credits_used": 0,
            "credits_remaining": MONTHLY_LIMIT,
            "calls": [],
            "daily_breakdown": {},
        }

    def _save(self):
        """Persist to disk."""
        with open(self.tracker_file, "w") as f:
            json.dump(self.data, f, indent=2, default=str)

    @property
    def used(self) -> int:
        return self.data["credits_used"]

    @property
    def remaining(self) -> int:
        return max(0, MONTHLY_LIMIT - self.data["credits_used"])

    @property
    def effective_remaining(self) -> int:
        """Remaining minus safety buffer."""
        return max(0, self.remaining - SAFETY_BUFFER)

    def can_afford(self, cost: int) -> bool:
        """Check if we can afford a call of this cost."""
        return self.effective_remaining >= cost

    def record_call(self, endpoint: str, cost: int, details: str = ""):
        """Record an API call and its credit cost."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        self.data["credits_used"] += cost
        self.data["credits_remaining"] = max(0, MONTHLY_LIMIT - self.data["credits_used"])

        call_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "cost": cost,
            "details": details,
            "running_total": self.data["credits_used"],
        }
        self.data["calls"].append(call_record)

        # Daily breakdown
        if today not in self.data["daily_breakdown"]:
            self.data["daily_breakdown"][today] = {"calls": 0, "credits": 0}
        self.data["daily_breakdown"][today]["calls"] += 1
        self.data["daily_breakdown"][today]["credits"] += cost

        self._save()

        logger.info(
            f"💳 API Credit: {cost} used | "
            f"Today: {self.data['daily_breakdown'][today]['credits']} | "
            f"Month: {self.used}/{MONTHLY_LIMIT} | "
            f"Remaining: {self.remaining}"
        )

    def update_from_headers(self, headers: Dict):
        """
        Update tracker from Odds API response headers.
        Headers: x-requests-remaining, x-requests-used, x-requests-last
        """
        if "x-requests-used" in headers:
            api_used = int(headers["x-requests-used"])
            api_remaining = int(headers.get("x-requests-remaining", 0))
            last_cost = int(headers.get("x-requests-last", 0))

            # Sync with API's own tracking (authoritative)
            if api_used > self.data["credits_used"]:
                logger.warning(
                    f"Credit sync: local={self.data['credits_used']}, "
                    f"API={api_used}. Updating to API value."
                )
                self.data["credits_used"] = api_used
                self.data["credits_remaining"] = api_remaining
                self._save()

    def get_budget_for_today(self) -> int:
        """
        Calculate how many credits we can spend today.
        Distributes remaining credits evenly across remaining days in month.
        """
        now = datetime.now(timezone.utc)
        days_in_month = 30  # approximate
        day_of_month = now.day
        days_left = max(1, days_in_month - day_of_month + 1)

        daily_budget = self.effective_remaining // days_left
        return max(3, daily_budget)  # Minimum 3 credits (1 odds call with spreads+totals)

    def get_optimal_markets(self) -> str:
        """
        Decide which markets to request based on remaining budget.
        - Flush budget: h2h,spreads,totals (3 credits)
        - Tight budget: spreads,totals (2 credits)
        - Critical: spreads only (1 credit)
        """
        budget = self.get_budget_for_today()

        if budget >= 15:
            return "h2h,spreads,totals"  # 3 credits per call
        elif budget >= 6:
            return "spreads,totals"  # 2 credits per call
        else:
            return "spreads"  # 1 credit per call

    def get_market_cost(self, markets: str, regions: str = "us") -> int:
        """Calculate the credit cost for a given markets+regions combo."""
        n_markets = len(markets.split(","))
        n_regions = len(regions.split(","))
        return n_markets * n_regions

    def summary(self) -> str:
        """Human-readable summary."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_usage = self.data["daily_breakdown"].get(today, {"calls": 0, "credits": 0})

        return (
            f"📊 ODDS API CREDIT STATUS\n"
            f"   Month: {self.data['month']}\n"
            f"   Used: {self.used}/{MONTHLY_LIMIT}\n"
            f"   Remaining: {self.remaining} (effective: {self.effective_remaining})\n"
            f"   Today: {today_usage['credits']} credits in {today_usage['calls']} calls\n"
            f"   Daily budget: {self.get_budget_for_today()} credits\n"
            f"   Optimal markets: {self.get_optimal_markets()}"
        )
