#!/usr/bin/env python3
"""
SECRETS MANAGER
=================
Unified secrets management with .env fallback.
Validates that required keys are present at startup.

Future: Azure Key Vault / AWS Secrets Manager integration.

Usage:
    from engine.security.secrets_manager import SecretsManager

    sm = SecretsManager()
    sm.validate_required()  # Raises if critical keys missing
    key = sm.get("ODDS_API_KEY")
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Define required vs optional secrets
REQUIRED_SECRETS = [
    "ODDS_API_KEY",
]

OPTIONAL_SECRETS = [
    "DISCORD_WEBHOOK_URL",
    "TWITTER_BEARER_TOKEN",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "GROK_API_KEY",
    "OPENAI_API_KEY",
    "ACTION_NETWORK_API_KEY",
    "EMAIL_USER",
    "EMAIL_PASS",
    "DATABASE_URL",
    "SENDGRID_API_KEY",
    "REDIS_URL",
]


class SecretsManager:
    """
    Centralized secrets access with startup validation.
    Loads from .env via python-dotenv, validates required keys.
    """

    def __init__(self, env_path: Optional[str] = None):
        self._secrets: Dict[str, str] = {}
        self._loaded = False
        self._env_path = env_path or str(
            Path(__file__).parent.parent.parent / ".env"
        )
        self._load()

    def _load(self):
        """Load secrets from .env file and environment."""
        try:
            from dotenv import dotenv_values

            file_values = dotenv_values(self._env_path)
            self._secrets.update(file_values)
        except ImportError:
            logger.warning("python-dotenv not installed; using env vars only")
        except Exception as e:
            logger.warning(f"Failed to load .env: {e}")

        # Environment variables override .env file
        for key in REQUIRED_SECRETS + OPTIONAL_SECRETS:
            env_val = os.environ.get(key)
            if env_val:
                self._secrets[key] = env_val

        self._loaded = True

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value."""
        return self._secrets.get(key, default)

    def validate_required(self) -> List[str]:
        """
        Validate that all required secrets are present.
        Returns list of missing keys. Raises ValueError if any missing.
        """
        missing = [
            key for key in REQUIRED_SECRETS
            if not self._secrets.get(key)
        ]

        if missing:
            logger.error(
                "One or more required secrets are missing; check configuration."
            )
            raise ValueError(
                f"Missing required secrets: {', '.join(missing)}. "
                f"Add them to .env or set as environment variables."
            )

        # Log aggregate status without exposing individual secret names or values
        required_present = sum(
            1 for key in REQUIRED_SECRETS if self._secrets.get(key)
        )
        optional_present = sum(
            1 for key in OPTIONAL_SECRETS if self._secrets.get(key)
        )
        logger.info(
            "Secrets validation passed: %d/%d required and %d/%d optional secrets present.",
            required_present,
            len(REQUIRED_SECRETS),
            optional_present,
            len(OPTIONAL_SECRETS),
        )

        return missing

    def health_check(self) -> Dict:
        """Return health status of all secrets."""
        status = {}
        for key in REQUIRED_SECRETS:
            status[key] = {
                "required": True,
                "present": bool(self._secrets.get(key)),
            }
        for key in OPTIONAL_SECRETS:
            status[key] = {
                "required": False,
                "present": bool(self._secrets.get(key)),
            }

        all_required_present = all(
            status[k]["present"] for k in REQUIRED_SECRETS
        )

        return {
            "healthy": all_required_present,
            "secrets": status,
            "required_count": len(REQUIRED_SECRETS),
            "optional_count": len(OPTIONAL_SECRETS),
            "missing_required": [
                k for k in REQUIRED_SECRETS if not status[k]["present"]
            ],
        }
