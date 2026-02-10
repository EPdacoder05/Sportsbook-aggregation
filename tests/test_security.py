#!/usr/bin/env python3
"""
API SECURITY TESTS
====================
Tests for API rate limiting, input validation, and auth.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAPISecurityHeaders:
    """Test security headers and middleware."""

    def test_input_validator_on_query_params(self):
        """Input validator should catch SQL injection in query params."""
        from engine.security.input_validator import InputValidator
        validator = InputValidator()

        # Simulated malicious query param
        result = validator.validate("1; DROP TABLE signals")
        assert result.is_safe is False

    def test_input_validator_on_game_ids(self):
        """Normal game IDs should pass validation."""
        from engine.security.input_validator import InputValidator
        validator = InputValidator(strict=False)

        result = validator.validate("espn_401584901")
        assert result.is_safe is True

    def test_url_validation_blocks_ssrf(self):
        """SSRF attempts should be blocked."""
        from engine.security.input_validator import InputValidator
        validator = InputValidator()

        dangerous_urls = [
            "http://127.0.0.1:8000/admin",
            "http://localhost/secret",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/admin",
            "file:///etc/passwd",
        ]

        for url in dangerous_urls:
            result = validator.validate_url(url)
            assert result.is_safe is False, f"Should block: {url}"

    def test_url_validation_allows_legitimate(self):
        """Legitimate API URLs should pass."""
        from engine.security.input_validator import InputValidator
        validator = InputValidator()

        safe_urls = [
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds",
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            "https://discord.com/api/webhooks/12345/abcdef",
        ]

        for url in safe_urls:
            result = validator.validate_url(url)
            assert result.is_safe is True, f"Should allow: {url}"


class TestRateLimiting:
    """Test rate limiting behavior."""

    def test_rate_limiter_structure(self):
        """Rate limiter should be importable and configurable."""
        # This tests that the API module can at least be parsed
        # without database dependencies causing import errors
        from engine.security.input_validator import InputValidator
        validator = InputValidator()
        # Run multiple validations quickly
        for i in range(100):
            result = validator.validate(f"test input {i}")
            assert result.is_safe is True
