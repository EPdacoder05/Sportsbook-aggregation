#!/usr/bin/env python3
"""
PARLAY SURVIVAL TRACKER
========================
Tonight (Feb 9, 2026) you manually tracked 11 DK parlays via screenshots.
That's insane. Your system should do this.

What this module does:
  1. Log parlay legs at placement time (from picks JSON or manual entry)
  2. At each game completion, mark legs WON / LOST / PENDING
  3. Auto-calculate "surviving parlay value" and hedge math
  4. Recommend optimal boost deployment based on which parlays are alive
  5. Feed into boost_ev.py for boost × hedge calculations

Key metrics:
  - Survival rate: % of parlays with all completed legs winning
  - Hedge value: How much to bet on the opposite outcome to lock profit
  - Dead weight: Parlays that can no longer hit (one leg lost)

Usage:
    from engine.parlay_tracker import ParlayTracker, ParlayLeg
    tracker = ParlayTracker()
    tracker.add_parlay("SGP7", wager=10, to_pay=895.50, legs=[...])
    tracker.update_from_scores(live_scores)
    tracker.print_survival_dashboard()
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


class LegStatus(Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    PUSH = "PUSH"
    LIVE = "LIVE"     # Game in progress


class ParlayStatus(Enum):
    ALIVE = "ALIVE"       # All completed legs WON, some still PENDING/LIVE
    WON = "WON"           # All legs WON
    LOST = "LOST"         # At least one leg LOST
    PENDING = "PENDING"   # No legs completed yet


@dataclass
class ParlayLeg:
    """A single leg of a parlay."""
    description: str          # "CLE Cavaliers ML", "Under 218.5"
    game_key: str             # "CLE @ DEN"
    pick_type: str            # "ML", "SPREAD", "TOTAL_UNDER", "TOTAL_OVER", "PROP"
    line: Optional[float] = None  # 218.5, -1.5, etc.
    team: Optional[str] = None    # "CLE" if applicable
    status: LegStatus = LegStatus.PENDING
    result_detail: str = ""   # "Final: 115-123" etc.

    def to_dict(self) -> Dict:
        return {
            "description": self.description,
            "game_key": self.game_key,
            "pick_type": self.pick_type,
            "line": self.line,
            "team": self.team,
            "status": self.status.value,
            "result_detail": self.result_detail,
        }


@dataclass
class Parlay:
    """A complete parlay bet."""
    parlay_id: str            # "SGP7_895", "8_PICK_207"
    wager: float              # $ wagered
    to_pay: float             # $ potential payout
    legs: List[ParlayLeg]     # All legs
    boost_pct: float = 0      # 0.25 = 25% boost
    boost_name: str = ""      # "25% CLE/DEN Boost"
    placed_at: str = ""       # ISO timestamp
    dk_bet_id: str = ""       # DK reference ID

    @property
    def status(self) -> ParlayStatus:
        """Calculate current parlay status from legs."""
        statuses = [leg.status for leg in self.legs]
        if LegStatus.LOST in statuses:
            return ParlayStatus.LOST
        if all(s == LegStatus.WON for s in statuses):
            return ParlayStatus.WON
        if any(s in (LegStatus.PENDING, LegStatus.LIVE) for s in statuses):
            if any(s == LegStatus.WON for s in statuses):
                return ParlayStatus.ALIVE
            return ParlayStatus.PENDING
        return ParlayStatus.PENDING

    @property
    def legs_won(self) -> int:
        return sum(1 for l in self.legs if l.status == LegStatus.WON)

    @property
    def legs_lost(self) -> int:
        return sum(1 for l in self.legs if l.status == LegStatus.LOST)

    @property
    def legs_pending(self) -> int:
        return sum(1 for l in self.legs if l.status in (LegStatus.PENDING, LegStatus.LIVE))

    @property
    def survival_pct(self) -> float:
        """% of completed legs that won."""
        completed = self.legs_won + self.legs_lost
        return (self.legs_won / completed * 100) if completed > 0 else 100.0

    @property
    def needs_teams(self) -> List[str]:
        """List of teams/outcomes still needed for this parlay."""
        return [
            leg.description
            for leg in self.legs
            if leg.status in (LegStatus.PENDING, LegStatus.LIVE)
        ]

    def to_dict(self) -> Dict:
        return {
            "parlay_id": self.parlay_id,
            "wager": self.wager,
            "to_pay": self.to_pay,
            "status": self.status.value,
            "legs_won": self.legs_won,
            "legs_lost": self.legs_lost,
            "legs_pending": self.legs_pending,
            "survival_pct": round(self.survival_pct, 1),
            "boost_pct": self.boost_pct,
            "legs": [l.to_dict() for l in self.legs],
            "needs": self.needs_teams,
        }


class ParlayTracker:
    """
    Tracks all active parlays and calculates survival/hedge math.
    """

    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or DATA_DIR / "parlay_tracker.json"
        self.parlays: List[Parlay] = []
        self._load()

    def _load(self):
        """Load parlays from disk."""
        if self.data_file.exists():
            try:
                with open(self.data_file) as f:
                    data = json.load(f)
                for p in data.get("parlays", []):
                    legs = [
                        ParlayLeg(
                            description=l["description"],
                            game_key=l["game_key"],
                            pick_type=l["pick_type"],
                            line=l.get("line"),
                            team=l.get("team"),
                            status=LegStatus(l.get("status", "PENDING")),
                            result_detail=l.get("result_detail", ""),
                        )
                        for l in p.get("legs", [])
                    ]
                    self.parlays.append(Parlay(
                        parlay_id=p["parlay_id"],
                        wager=p["wager"],
                        to_pay=p["to_pay"],
                        legs=legs,
                        boost_pct=p.get("boost_pct", 0),
                        boost_name=p.get("boost_name", ""),
                        placed_at=p.get("placed_at", ""),
                        dk_bet_id=p.get("dk_bet_id", ""),
                    ))
            except Exception as e:
                logger.error(f"Failed to load parlay tracker: {e}")

    def save(self):
        """Save parlays to disk."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": datetime.now().isoformat(),
            "parlays": [p.to_dict() for p in self.parlays],
        }
        with open(self.data_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def add_parlay(
        self,
        parlay_id: str,
        wager: float,
        to_pay: float,
        legs: List[ParlayLeg],
        boost_pct: float = 0,
        boost_name: str = "",
        dk_bet_id: str = "",
    ):
        """Add a new parlay to track."""
        parlay = Parlay(
            parlay_id=parlay_id,
            wager=wager,
            to_pay=to_pay,
            legs=legs,
            boost_pct=boost_pct,
            boost_name=boost_name,
            placed_at=datetime.now().isoformat(),
            dk_bet_id=dk_bet_id,
        )
        self.parlays.append(parlay)
        self.save()
        logger.info(f"Added parlay: {parlay_id} (${wager} → ${to_pay})")

    def update_leg(self, game_key: str, result: str, detail: str = ""):
        """
        Update all parlay legs that match a game_key.

        Args:
            game_key: "CLE @ DEN" or team abbreviation
            result: "WON", "LOST", "PUSH", "LIVE"
            detail: "Final: 115-110" etc.
        """
        status = LegStatus(result.upper())
        updated = 0

        for parlay in self.parlays:
            for leg in parlay.legs:
                if (game_key.upper() in leg.game_key.upper() or
                    game_key.upper() in leg.description.upper() or
                    (leg.team and game_key.upper() in leg.team.upper())):
                    if leg.status in (LegStatus.PENDING, LegStatus.LIVE):
                        leg.status = status
                        leg.result_detail = detail
                        updated += 1

        if updated:
            self.save()
            logger.info(f"Updated {updated} legs for {game_key}: {result}")

    def update_from_scores(self, final_scores: Dict[str, Dict]):
        """
        Bulk-update legs from a dict of final scores.

        Args:
            final_scores: {
                "DET @ CHA": {"home_score": 98, "away_score": 110, "completed": True},
                ...
            }
        """
        for game_key, score in final_scores.items():
            if not score.get("completed"):
                continue

            for parlay in self.parlays:
                for leg in parlay.legs:
                    if leg.status not in (LegStatus.PENDING, LegStatus.LIVE):
                        continue

                    # Check if this leg matches the game
                    if (game_key.upper() not in leg.game_key.upper() and
                        not any(part.upper() in leg.description.upper()
                                for part in game_key.split())):
                        continue

                    # Grade the leg
                    total = score.get("home_score", 0) + score.get("away_score", 0)
                    spread = score.get("home_score", 0) - score.get("away_score", 0)
                    detail = f"Final: {score.get('away_score', '?')}-{score.get('home_score', '?')}"

                    won = self._grade_leg(leg, score)
                    if won is True:
                        leg.status = LegStatus.WON
                    elif won is False:
                        leg.status = LegStatus.LOST
                    else:
                        continue  # Can't grade this leg type
                    leg.result_detail = detail

        self.save()

    def _grade_leg(self, leg: ParlayLeg, score: Dict) -> Optional[bool]:
        """Grade a single leg against final score. Returns True/False/None."""
        total = score.get("home_score", 0) + score.get("away_score", 0)
        spread = score.get("home_score", 0) - score.get("away_score", 0)

        pick_type = leg.pick_type.upper()

        if pick_type == "TOTAL_UNDER" and leg.line is not None:
            return total < leg.line
        elif pick_type == "TOTAL_OVER" and leg.line is not None:
            return total > leg.line
        elif pick_type == "ML" and leg.team:
            home_team = score.get("home_team", "")
            away_team = score.get("away_team", "")
            home_won = score.get("home_score", 0) > score.get("away_score", 0)
            if leg.team.upper() in home_team.upper():
                return home_won
            elif leg.team.upper() in away_team.upper():
                return not home_won
        elif pick_type == "SPREAD" and leg.line is not None and leg.team:
            home_team = score.get("home_team", "")
            if leg.team.upper() in home_team.upper():
                adjusted = spread + leg.line
            else:
                adjusted = -spread + leg.line
            return adjusted > 0

        return None  # Can't grade

    # ── Hedge Math ────────────────────────────────────────────────

    def calculate_hedge(
        self,
        parlay_id: str,
        opposing_odds: int = 110,
    ) -> Dict:
        """
        Calculate optimal hedge bet for a surviving parlay.

        Args:
            parlay_id: Which parlay to hedge
            opposing_odds: American odds of the opposing bet
        """
        parlay = next((p for p in self.parlays if p.parlay_id == parlay_id), None)
        if not parlay:
            return {"error": f"Parlay {parlay_id} not found"}

        if parlay.status != ParlayStatus.ALIVE:
            return {"error": f"Parlay is {parlay.status.value}, not ALIVE"}

        remaining_legs = parlay.legs_pending

        # Simple hedge: bet enough on the opposite to guarantee profit
        potential_payout = parlay.to_pay
        total_invested = parlay.wager

        # Convert opposing odds to decimal
        if opposing_odds > 0:
            decimal_odds = 1 + (opposing_odds / 100)
        else:
            decimal_odds = 1 + (100 / abs(opposing_odds))

        # Hedge to guarantee breakeven:
        # hedge_amount * decimal_odds = total_invested
        hedge_breakeven = total_invested / decimal_odds

        # Hedge to guarantee equal profit either way:
        # If parlay wins: profit = to_pay - wager - hedge_amount
        # If hedge wins: profit = hedge_amount * (decimal_odds - 1) - wager
        # Set equal: to_pay - wager - hedge = hedge * (decimal - 1) - wager
        # to_pay = hedge + hedge * (decimal - 1) = hedge * decimal
        hedge_equal_profit = potential_payout / (1 + decimal_odds)

        return {
            "parlay_id": parlay_id,
            "parlay_payout": potential_payout,
            "parlay_wager": total_invested,
            "legs_remaining": remaining_legs,
            "opposing_odds": opposing_odds,
            "hedge_breakeven": round(hedge_breakeven, 2),
            "hedge_equal_profit": round(hedge_equal_profit, 2),
            "if_parlay_hits": round(potential_payout - total_invested - hedge_equal_profit, 2),
            "if_hedge_hits": round(hedge_equal_profit * (decimal_odds - 1) - total_invested, 2),
        }

    # ── Dashboard ────────────────────────────────────────────────

    def print_survival_dashboard(self):
        """Print a live survival dashboard."""
        alive = [p for p in self.parlays if p.status == ParlayStatus.ALIVE]
        won = [p for p in self.parlays if p.status == ParlayStatus.WON]
        lost = [p for p in self.parlays if p.status == ParlayStatus.LOST]
        pending = [p for p in self.parlays if p.status == ParlayStatus.PENDING]

        total_wagered = sum(p.wager for p in self.parlays)
        total_won = sum(p.to_pay for p in won)
        total_alive_value = sum(p.to_pay for p in alive)

        print()
        print("═" * 72)
        print(f"  📋 PARLAY SURVIVAL DASHBOARD — {datetime.now().strftime('%I:%M %p ET')}")
        print("═" * 72)
        print(f"  Total wagered: ${total_wagered:.2f}")
        print(f"  Won: {len(won)} (${total_won:.2f})")
        print(f"  Lost: {len(lost)}")
        print(f"  Alive: {len(alive)} (${total_alive_value:.2f} potential)")
        print(f"  Pending: {len(pending)}")

        if alive:
            print(f"\n  🟢 ALIVE PARLAYS:")
            for p in alive:
                print(f"    {p.parlay_id}: ${p.wager} → ${p.to_pay}")
                print(f"      {p.legs_won}W / {p.legs_lost}L / {p.legs_pending} remaining")
                if p.boost_name:
                    print(f"      Boost: {p.boost_name} ({p.boost_pct:.0%})")
                for need in p.needs_teams:
                    print(f"      ⏳ Needs: {need}")

        if won:
            print(f"\n  ✅ WON:")
            for p in won:
                print(f"    {p.parlay_id}: ${p.wager} → ${p.to_pay} CASHED")

        if lost:
            print(f"\n  ❌ LOST:")
            for p in lost:
                losing_legs = [l for l in p.legs if l.status == LegStatus.LOST]
                failed = ", ".join(l.description for l in losing_legs[:2])
                print(f"    {p.parlay_id}: ${p.wager} (failed: {failed})")

        print("\n" + "═" * 72)

    # ── Summary ──────────────────────────────────────────────────

    def get_summary(self) -> Dict:
        """Get portfolio summary."""
        alive = [p for p in self.parlays if p.status == ParlayStatus.ALIVE]
        won = [p for p in self.parlays if p.status == ParlayStatus.WON]
        lost = [p for p in self.parlays if p.status == ParlayStatus.LOST]

        return {
            "total_parlays": len(self.parlays),
            "alive": len(alive),
            "won": len(won),
            "lost": len(lost),
            "total_wagered": sum(p.wager for p in self.parlays),
            "total_won": sum(p.to_pay for p in won),
            "alive_value": sum(p.to_pay for p in alive),
            "dead_weight": sum(p.wager for p in lost),
            "net_pnl": sum(p.to_pay for p in won) - sum(p.wager for p in self.parlays),
        }


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 72)
    print("  PARLAY SURVIVAL TRACKER — Demo (Feb 9, 2026)")
    print("═" * 72)

    tracker = ParlayTracker(data_file=Path("/dev/null"))  # Don't persist demo
    tracker.parlays = []  # Fresh

    # Add tonight's parlays
    tracker.parlays.append(Parlay(
        parlay_id="SGP7_895",
        wager=10.0,
        to_pay=895.50,
        legs=[
            ParlayLeg("Under 218.5 CHI/BKN", "CHI @ BKN", "TOTAL_UNDER", 218.5),
            ParlayLeg("Under 239.5 UTA/MIA", "UTA @ MIA", "TOTAL_UNDER", 239.5),
            ParlayLeg("CLE -1.5", "CLE @ DEN", "SPREAD", -1.5, "CLE"),
            ParlayLeg("Over 218.5 MEM/GS", "MEM @ GS", "TOTAL_OVER", 218.5),
            ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ParlayLeg("Under 220.5 MIL/ORL", "MIL @ ORL", "TOTAL_UNDER", 220.5),
            ParlayLeg("MIL +10.5", "MIL @ ORL", "SPREAD", 10.5, "MIL"),
        ],
    ))

    tracker.parlays.append(Parlay(
        parlay_id="8_PICK_207",
        wager=10.0,
        to_pay=207.0,
        boost_pct=0.20,
        boost_name="20% Parlay Boost",
        legs=[
            ParlayLeg("DET ML", "DET @ CHA", "ML", team="DET"),
            ParlayLeg("MIA ML", "UTA @ MIA", "ML", team="MIA"),
            ParlayLeg("CHI ML", "CHI @ BKN", "ML", team="CHI"),
            ParlayLeg("ORL ML", "MIL @ ORL", "ML", team="ORL"),
            ParlayLeg("MIN ML", "ATL @ MIN", "ML", team="MIN"),
            ParlayLeg("NOP ML", "SAC @ NOP", "ML", team="NOP"),
            ParlayLeg("CLE ML", "CLE @ DEN", "ML", team="CLE"),
            ParlayLeg("GS ML", "MEM @ GS", "ML", team="GS"),
        ],
    ))

    # Simulate some results
    tracker.update_leg("DET", "WON", "Final: 110-104")
    tracker.update_leg("MIA", "WON", "Final: 111-115")
    tracker.update_leg("CHI", "WON", "Final: 115-123")
    tracker.update_leg("ORL", "WON", "Final: 99-118")
    tracker.update_leg("MIN", "WON", "Final: 116-138")
    tracker.update_leg("NOP", "WON", "Final: 94-120")

    tracker.print_survival_dashboard()

    # Calculate hedge for surviving parlay
    hedge = tracker.calculate_hedge("8_PICK_207", opposing_odds=110)
    print(f"\n  Hedge math for 8_PICK_207:")
    for k, v in hedge.items():
        print(f"    {k}: {v}")
    print()
