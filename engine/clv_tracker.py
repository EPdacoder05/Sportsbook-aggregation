#!/usr/bin/env python3
"""
CLV TRACKER — Closing Line Value
==================================
The single most important metric for proving long-term edge.

CLV = Your Line - Closing Line (at tip-off)
  Positive CLV = you beat the market = provably profitable long-term
  Negative CLV = market corrected against you = edge is illusory

Workflow:
  1. When a pick is generated → log_pick() records your line
  2. Right before tip-off → capture_closing_line() snapshots the final number
  3. After game ends → record_result() logs W/L + final score
  4. analyze_clv() computes rolling CLV stats across all picks

Usage:
    from engine.clv_tracker import CLVTracker
    tracker = CLVTracker()
    tracker.log_pick("CHI@BKN", "UNDER", 218.5, confidence=85, tier="TIER1")
    tracker.capture_closing_line("CHI@BKN", "UNDER", 217.0)
    tracker.record_result("CHI@BKN", "UNDER", won=True, final_total=210)
    report = tracker.analyze_clv()
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "data"
CLV_FILE = DATA_DIR / "clv_history.json"


class CLVRecord:
    """Single pick with CLV tracking."""

    def __init__(self, game_key: str, pick_type: str, your_line: float,
                 confidence: float = 0.0, tier: str = "", units: float = 1.0,
                 timestamp: str = ""):
        self.game_key = game_key          # e.g. "CHI@BKN"
        self.pick_type = pick_type        # "UNDER", "OVER", "SPREAD_AWAY", etc.
        self.your_line = your_line        # line you got (e.g. 218.5)
        self.closing_line = None          # line at tip-off
        self.clv = None                   # your_line - closing_line (adjusted for direction)
        self.won = None                   # True/False after game
        self.final_score = None           # actual result
        self.confidence = confidence
        self.tier = tier
        self.units = units
        self.timestamp = timestamp or datetime.now().isoformat()
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.signal_types = []            # which signals triggered this pick

    def to_dict(self) -> Dict:
        return {
            "game_key": self.game_key,
            "pick_type": self.pick_type,
            "your_line": self.your_line,
            "closing_line": self.closing_line,
            "clv": self.clv,
            "won": self.won,
            "final_score": self.final_score,
            "confidence": self.confidence,
            "tier": self.tier,
            "units": self.units,
            "timestamp": self.timestamp,
            "date": self.date,
            "signal_types": self.signal_types,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "CLVRecord":
        rec = cls(
            game_key=d["game_key"],
            pick_type=d["pick_type"],
            your_line=d["your_line"],
            confidence=d.get("confidence", 0),
            tier=d.get("tier", ""),
            units=d.get("units", 1.0),
            timestamp=d.get("timestamp", ""),
        )
        rec.closing_line = d.get("closing_line")
        rec.clv = d.get("clv")
        rec.won = d.get("won")
        rec.final_score = d.get("final_score")
        rec.date = d.get("date", "")
        rec.signal_types = d.get("signal_types", [])
        return rec


class CLVTracker:
    """Tracks CLV across all picks."""

    def __init__(self, clv_file: Path = CLV_FILE):
        self.clv_file = clv_file
        self.records: List[CLVRecord] = []
        self._load()

    def _load(self):
        """Load existing CLV history."""
        if self.clv_file.exists():
            try:
                with open(self.clv_file) as f:
                    data = json.load(f)
                self.records = [CLVRecord.from_dict(d) for d in data]
            except (json.JSONDecodeError, KeyError):
                self.records = []

    def _save(self):
        """Persist CLV history to disk."""
        self.clv_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.clv_file, "w") as f:
            json.dump([r.to_dict() for r in self.records], f, indent=2)

    # ── Recording Methods ─────────────────────────────────────────

    def log_pick(self, game_key: str, pick_type: str, your_line: float,
                 confidence: float = 0.0, tier: str = "", units: float = 1.0,
                 signal_types: Optional[List[str]] = None) -> CLVRecord:
        """
        Log a new pick when it's generated.

        Args:
            game_key:  "CHI@BKN" or "Chicago Bulls @ Brooklyn Nets"
            pick_type: "UNDER", "OVER", "SPREAD_AWAY", "SPREAD_HOME", "ML_AWAY", "ML_HOME"
            your_line: The number you're betting (e.g., 218.5 for Under 218.5)
            confidence: 0-100
            tier: "TIER1", "TIER2", "LEAN"
            units: bet size
            signal_types: ["RLM_TOTAL", "ML_SPREAD_DIVERGENCE", ...]
        """
        rec = CLVRecord(
            game_key=game_key,
            pick_type=pick_type,
            your_line=your_line,
            confidence=confidence,
            tier=tier,
            units=units,
        )
        rec.signal_types = signal_types or []
        self.records.append(rec)
        self._save()
        return rec

    def capture_closing_line(self, game_key: str, pick_type: str,
                             closing_line: float) -> Optional[CLVRecord]:
        """
        Record the closing line at tip-off.
        Call this ~1 min before game starts using a scheduled job.
        """
        rec = self._find_record(game_key, pick_type)
        if rec is None:
            return None

        rec.closing_line = closing_line
        rec.clv = self._compute_clv(rec)
        self._save()
        return rec

    def record_result(self, game_key: str, pick_type: str,
                      won: bool, final_score: Optional[float] = None) -> Optional[CLVRecord]:
        """Record whether the bet won or lost after the game."""
        rec = self._find_record(game_key, pick_type)
        if rec is None:
            return None

        rec.won = won
        rec.final_score = final_score
        self._save()
        return rec

    # ── CLV Calculation ───────────────────────────────────────────

    @staticmethod
    def _compute_clv(rec: CLVRecord) -> Optional[float]:
        """
        Compute CLV based on pick type.

        For UNDER: CLV = closing_line - your_line
            (if total dropped further, you got a BETTER number)
        For OVER:  CLV = your_line - closing_line
            (if total rose further, you got a BETTER number)
        For SPREAD (taking dog): CLV = your_line - closing_line
            (if spread grew, you got MORE points = better)
        """
        if rec.closing_line is None:
            return None

        if rec.pick_type in ("UNDER",):
            # Under: you want the number HIGH. If it dropped, you got better value.
            return rec.your_line - rec.closing_line
        elif rec.pick_type in ("OVER",):
            # Over: you want the number LOW. If it rose, you got better value.
            return rec.closing_line - rec.your_line
        elif rec.pick_type in ("SPREAD_AWAY", "SPREAD_HOME"):
            # Spread (taking points): you want MORE points.
            return rec.your_line - rec.closing_line
        else:
            # ML or unknown — just return raw difference
            return rec.your_line - rec.closing_line

    # ── Analysis ──────────────────────────────────────────────────

    def analyze_clv(self, days: int = 0) -> Dict:
        """
        Compute CLV statistics.

        Args:
            days: only include records from the last N days (0 = all)

        Returns:
            Dict with avg_clv, win_rate, clv_by_tier, clv_by_signal, etc.
        """
        records = self.records
        if days > 0:
            cutoff = datetime.now().strftime("%Y-%m-%d")
            # Simple: filter by date string comparison
            records = [r for r in records if r.date >= cutoff]

        if not records:
            return {"total_picks": 0, "message": "No picks recorded yet."}

        # Overall CLV
        clv_values = [r.clv for r in records if r.clv is not None]
        avg_clv = sum(clv_values) / len(clv_values) if clv_values else 0

        # Win rate
        resolved = [r for r in records if r.won is not None]
        wins = sum(1 for r in resolved if r.won)
        win_rate = wins / len(resolved) if resolved else 0

        # CLV by tier
        clv_by_tier = {}
        for tier in ("TIER1", "TIER2", "LEAN"):
            tier_recs = [r for r in records if r.tier == tier and r.clv is not None]
            if tier_recs:
                tier_clvs = [r.clv for r in tier_recs]
                tier_wins = [r for r in tier_recs if r.won is True]
                tier_losses = [r for r in tier_recs if r.won is False]
                clv_by_tier[tier] = {
                    "count": len(tier_recs),
                    "avg_clv": sum(tier_clvs) / len(tier_clvs),
                    "wins": len(tier_wins),
                    "losses": len(tier_losses),
                    "win_rate": len(tier_wins) / (len(tier_wins) + len(tier_losses))
                    if (len(tier_wins) + len(tier_losses)) > 0 else 0,
                }

        # CLV by signal type
        clv_by_signal = {}
        all_signals = set()
        for r in records:
            all_signals.update(r.signal_types)
        for sig in all_signals:
            sig_recs = [r for r in records if sig in r.signal_types and r.clv is not None]
            if sig_recs:
                sig_clvs = [r.clv for r in sig_recs]
                sig_wins = [r for r in sig_recs if r.won is True]
                sig_losses = [r for r in sig_recs if r.won is False]
                clv_by_signal[sig] = {
                    "count": len(sig_recs),
                    "avg_clv": sum(sig_clvs) / len(sig_clvs),
                    "wins": len(sig_wins),
                    "losses": len(sig_losses),
                    "hit_rate": len(sig_wins) / (len(sig_wins) + len(sig_losses))
                    if (len(sig_wins) + len(sig_losses)) > 0 else 0,
                }

        # Units P&L
        total_units_won = sum(r.units for r in resolved if r.won)
        total_units_lost = sum(r.units for r in resolved if not r.won)
        net_units = total_units_won - total_units_lost

        return {
            "total_picks": len(records),
            "resolved": len(resolved),
            "wins": wins,
            "losses": len(resolved) - wins,
            "win_rate": round(win_rate, 3),
            "avg_clv": round(avg_clv, 2),
            "positive_clv_pct": round(
                sum(1 for c in clv_values if c > 0) / len(clv_values), 3
            ) if clv_values else 0,
            "clv_by_tier": clv_by_tier,
            "clv_by_signal": clv_by_signal,
            "net_units": round(net_units, 1),
            "total_units_risked": round(sum(r.units for r in resolved), 1),
        }

    def print_report(self, days: int = 0):
        """Pretty-print CLV analysis."""
        stats = self.analyze_clv(days)

        if stats["total_picks"] == 0:
            print("  No picks recorded yet.")
            return

        print()
        print("═" * 70)
        print("  📊 CLV PERFORMANCE REPORT")
        print("═" * 70)
        print(f"  Total Picks:       {stats['total_picks']}")
        print(f"  Resolved:          {stats['resolved']}")
        print(f"  Record:            {stats['wins']}-{stats['losses']} "
              f"({stats['win_rate']:.1%})")
        print(f"  Avg CLV:           {stats['avg_clv']:+.2f} pts")
        print(f"  Positive CLV %:    {stats['positive_clv_pct']:.1%}")
        print(f"  Net Units:         {stats['net_units']:+.1f}U")
        print(f"  Total Risked:      {stats['total_units_risked']:.1f}U")

        if stats["clv_by_tier"]:
            print()
            print("  ── BY TIER ────────────────────────────────────────")
            for tier, data in stats["clv_by_tier"].items():
                print(f"  {tier}: {data['count']} picks | "
                      f"CLV {data['avg_clv']:+.2f} | "
                      f"{data['wins']}-{data['losses']} "
                      f"({data['win_rate']:.0%})")

        if stats["clv_by_signal"]:
            print()
            print("  ── BY SIGNAL TYPE ─────────────────────────────────")
            for sig, data in stats["clv_by_signal"].items():
                print(f"  {sig}: {data['count']} picks | "
                      f"CLV {data['avg_clv']:+.2f} | "
                      f"Hit Rate {data['hit_rate']:.0%}")

        print("═" * 70)

    # ── Helpers ───────────────────────────────────────────────────

    def _find_record(self, game_key: str, pick_type: str) -> Optional[CLVRecord]:
        """Find the most recent matching record."""
        today = datetime.now().strftime("%Y-%m-%d")
        for rec in reversed(self.records):
            if rec.game_key == game_key and rec.pick_type == pick_type and rec.date == today:
                return rec
        return None

    def get_todays_picks(self) -> List[CLVRecord]:
        """Get all picks from today."""
        today = datetime.now().strftime("%Y-%m-%d")
        return [r for r in self.records if r.date == today]


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tracker = CLVTracker()

    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        tracker.print_report()
    else:
        print(f"CLV Tracker: {len(tracker.records)} records loaded from {CLV_FILE}")
        print("Usage: python engine/clv_tracker.py --report")
