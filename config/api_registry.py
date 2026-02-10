"""
Unified API Registry
======================
Single source of truth for ALL external API credentials, rate limits,
and credit budgets. Every module pulls from here — no more hardcoded keys.

Usage:
    from config.api_registry import api
    
    key = api.odds_api.key          # str — empty if not set
    api.odds_api.require_key()      # raises if missing
    cost = api.odds_api.credits     # CreditTracker instance
    
    key = api.espn.base_url         # "https://site.api.espn.com/..."
    key = api.discord.webhook_url   # str
"""

import os
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure project root is on sys.path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────
#  Credit / Rate-Limit Tracker  (generalised from CreditTracker v1)
# ──────────────────────────────────────────────────────────────────────

class UsageMeter:
    """
    Tracks usage for any metered API (credits, requests, tokens).
    Persists to JSON so it survives restarts.
    """

    def __init__(
        self,
        name: str,
        monthly_limit: int,
        safety_buffer: int = 0,
        tracker_dir: Optional[Path] = None,
    ):
        self.name = name
        self.monthly_limit = monthly_limit
        self.safety_buffer = safety_buffer
        self._file = (tracker_dir or DATA_DIR) / f"usage_{name}.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # ── persistence ──────────────────────────────────────────────────

    def _load(self):
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if self._file.exists():
            with open(self._file, "r") as f:
                self._data = json.load(f)
            if self._data.get("month") != current_month:
                logger.info(f"[{self.name}] New month — resetting usage.")
                self._data = self._blank(current_month)
                self._save()
        else:
            self._data = self._blank(current_month)
            self._save()

    def _blank(self, month: str) -> Dict:
        return {
            "month": month,
            "used": 0,
            "calls": [],
            "daily": {},
        }

    def _save(self):
        with open(self._file, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    # ── public interface ─────────────────────────────────────────────

    @property
    def used(self) -> int:
        return self._data["used"]

    @property
    def remaining(self) -> int:
        return max(0, self.monthly_limit - self.used)

    @property
    def effective_remaining(self) -> int:
        return max(0, self.remaining - self.safety_buffer)

    def can_afford(self, cost: int) -> bool:
        return self.effective_remaining >= cost

    def record(self, endpoint: str, cost: int = 1, details: str = ""):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._data["used"] += cost
        self._data["calls"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "cost": cost,
            "details": details,
            "running": self._data["used"],
        })
        day = self._data["daily"].setdefault(today, {"calls": 0, "credits": 0})
        day["calls"] += 1
        day["credits"] += cost
        self._save()
        logger.info(
            f"[{self.name}] +{cost} | today={day['credits']} | "
            f"month={self.used}/{self.monthly_limit} | left={self.remaining}"
        )

    def sync_from_headers(self, headers: Dict[str, str]):
        """Sync with API-reported usage (e.g. Odds API x-requests-used)."""
        used_h = headers.get("x-requests-used")
        if used_h and int(used_h) > self.used:
            logger.warning(f"[{self.name}] syncing local={self.used} → API={used_h}")
            self._data["used"] = int(used_h)
            self._save()

    def daily_budget(self) -> int:
        day = datetime.now(timezone.utc).day
        days_left = max(1, 30 - day + 1)
        return max(1, self.effective_remaining // days_left)

    def summary(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        td = self._data["daily"].get(today, {"calls": 0, "credits": 0})
        return (
            f"[{self.name}] {self.used}/{self.monthly_limit} used | "
            f"remaining={self.remaining} (eff={self.effective_remaining}) | "
            f"today={td['credits']} in {td['calls']} calls | "
            f"daily_budget={self.daily_budget()}"
        )


# ──────────────────────────────────────────────────────────────────────
#  Individual API configs
# ──────────────────────────────────────────────────────────────────────

@dataclass
class APIService:
    """Base for any external API."""
    name: str
    key_env_var: str          # env-var name to read the key from
    base_url: str = ""
    _key_cache: Optional[str] = field(default=None, repr=False)

    @property
    def key(self) -> str:
        if self._key_cache is None:
            self._key_cache = os.getenv(self.key_env_var, "")
        return self._key_cache

    @property
    def is_configured(self) -> bool:
        return bool(self.key)

    def require_key(self) -> str:
        """Return key or raise."""
        if not self.is_configured:
            raise EnvironmentError(
                f"[{self.name}] Missing API key. "
                f"Set {self.key_env_var} in your .env file."
            )
        return self.key

    def status(self) -> str:
        return f"{'OK' if self.is_configured else 'MISSING'} {self.name} ({self.key_env_var})"


@dataclass
class MeteredAPIService(APIService):
    """API with a metered usage budget (credits, tokens, etc.)."""
    monthly_limit: int = 0
    safety_buffer: int = 0
    _meter: Optional[UsageMeter] = field(default=None, repr=False)

    @property
    def credits(self) -> UsageMeter:
        if self._meter is None:
            self._meter = UsageMeter(
                name=self.name,
                monthly_limit=self.monthly_limit,
                safety_buffer=self.safety_buffer,
            )
        return self._meter


@dataclass
class FreeAPIService:
    """Unmetered / no-key API (e.g. ESPN public endpoints)."""
    name: str
    base_url: str = ""

    @property
    def is_configured(self) -> bool:
        return True

    def status(self) -> str:
        return f"OK {self.name} (free / no key)"


# ──────────────────────────────────────────────────────────────────────
#  The Registry  — one instance, import `api` from here
# ──────────────────────────────────────────────────────────────────────

class APIRegistry:
    """
    Central registry of every external API this system touches.
    All keys come from env vars (loaded by python-dotenv / pydantic).
    """

    def __init__(self):
        # ── Odds & Scores ──────────────────────────────────
        self.odds_api = MeteredAPIService(
            name="odds_api",
            key_env_var="ODDS_API_KEY",
            base_url="https://api.the-odds-api.com/v4",
            monthly_limit=500,
            safety_buffer=20,
        )

        self.espn = FreeAPIService(
            name="espn",
            base_url="https://site.api.espn.com/apis/site/v2/sports",
        )

        # ── Social / Scraping ──────────────────────────────
        self.twitter = APIService(
            name="twitter",
            key_env_var="TWITTER_BEARER_TOKEN",
            base_url="https://api.twitter.com/2",
        )

        self.reddit = APIService(
            name="reddit",
            key_env_var="REDDIT_CLIENT_ID",
            base_url="https://oauth.reddit.com",
        )

        # ── AI / ML ────────────────────────────────────────
        self.grok = MeteredAPIService(
            name="grok",
            key_env_var="GROK_API_KEY",
            base_url="https://api.x.ai/v1",
            monthly_limit=0,  # set when you know the tier
            safety_buffer=0,
        )

        self.openai = MeteredAPIService(
            name="openai",
            key_env_var="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            monthly_limit=0,
            safety_buffer=0,
        )

        # ── Betting Data Sources ───────────────────────────
        self.action_network = APIService(
            name="action_network",
            key_env_var="ACTION_NETWORK_API_KEY",
            base_url="https://api.actionnetwork.com/web/v1",
        )

        self.draftkings = FreeAPIService(
            name="draftkings",
            base_url="https://sportsbook.draftkings.com",
        )

        self.covers = FreeAPIService(
            name="covers",
            base_url="https://www.covers.com",
        )

        # ── Notifications ─────────────────────────────────
        self.discord = APIService(
            name="discord",
            key_env_var="DISCORD_WEBHOOK_URL",  # not a key, but same pattern
        )

        self.sendgrid = APIService(
            name="sendgrid",
            key_env_var="SENDGRID_API_KEY",
        )

        # ── keep a list for iteration ────────────────────
        self._all: list = [
            self.odds_api, self.espn, self.twitter, self.reddit,
            self.grok, self.openai, self.action_network,
            self.draftkings, self.covers,
            self.discord, self.sendgrid,
        ]

    # ── helpers ──────────────────────────────────────────

    def health_check(self) -> str:
        """Print status of every registered API."""
        lines = ["═══ API HEALTH CHECK ═══"]
        for svc in self._all:
            lines.append(f"  {svc.status()}")

        # credit summaries for metered APIs
        metered = [s for s in self._all if isinstance(s, MeteredAPIService) and s.monthly_limit > 0]
        if metered:
            lines.append("\n═══ CREDIT BUDGETS ═══")
            for s in metered:
                lines.append(f"  {s.credits.summary()}")

        return "\n".join(lines)

    def configured_services(self) -> list:
        return [s for s in self._all if s.is_configured]

    def missing_services(self) -> list:
        return [s for s in self._all if not s.is_configured]


# ──────────────────────────────────────────────────────────────────────
#  Singleton — import this
# ──────────────────────────────────────────────────────────────────────
api = APIRegistry()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(api.health_check())
