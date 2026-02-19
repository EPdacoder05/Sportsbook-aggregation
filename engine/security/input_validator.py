#!/usr/bin/env python3
"""
32-PATTERN INPUT VALIDATOR
============================
Comprehensive input sanitization covering:
  - SQL injection (26 patterns)
  - XSS (10 patterns)
  - LDAP injection
  - Path traversal
  - Command injection
  - SSRF prevention
  - XXE prevention
  - ReDoS protection

Usage:
    from engine.security.input_validator import InputValidator

    validator = InputValidator()
    result = validator.validate("user input here")
    if not result.is_safe:
        print(f"Blocked: {result.threat_type} — {result.detail}")
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of input validation."""
    is_safe: bool
    threat_type: Optional[str] = None
    detail: Optional[str] = None
    pattern_matched: Optional[str] = None
    sanitized: Optional[str] = None


# ── SQL Injection Patterns (26) ──────────────────────────────────────

SQL_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b\s)",
    r"(\b(UNION\s+(ALL\s+)?SELECT)\b)",
    r"(--\s)",
    r"(/\*.*?\*/)",
    r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)",
    r"(\b(OR|AND)\b\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+['\"]?)",
    r"('\s*(OR|AND)\s+')",
    r"(\bEXEC(UTE)?\b\s)",
    r"(\bxp_\w+)",
    r"(\bsp_\w+)",
    r"(\bWAITFOR\s+DELAY\b)",
    r"(\bBENCHMARK\s*\()",
    r"(\bSLEEP\s*\()",
    r"(\bLOAD_FILE\s*\()",
    r"(\bINTO\s+(OUT|DUMP)FILE\b)",
    r"(\bINFORMATION_SCHEMA\b)",
    r"(\bHAVING\s+\d+\s*[<>=])",
    r"(\bGROUP\s+BY\s+\d+)",
    r"(\bORDER\s+BY\s+\d+\s*(--|#))",
    r"(;\s*(DROP|DELETE|INSERT|UPDATE|ALTER)\b)",
    r"(\bCAST\s*\(.*\bAS\b)",
    r"(\bCONVERT\s*\()",
    r"(\bCHAR\s*\(\d+\))",
    r"(\bCONCAT\s*\()",
    r"(0x[0-9a-fA-F]+)",
    r"(\b(CHAR|NCHAR|VARCHAR|NVARCHAR)\s*\()",
]

# ── XSS Patterns (10) ───────────────────────────────────────────────

XSS_PATTERNS = [
    r"(<\s*script\b[^>]*>)",
    r"(\bon\w+\s*=)",
    r"(javascript\s*:)",
    r"(vbscript\s*:)",
    r"(data\s*:\s*text/html)",
    r"(<\s*iframe\b)",
    r"(<\s*object\b)",
    r"(<\s*embed\b)",
    r"(<\s*img\b[^>]+\bonerror\b)",
    r"(document\s*\.\s*(cookie|write|location))",
]

# ── LDAP Injection ───────────────────────────────────────────────────

LDAP_PATTERNS = [
    r"([)(|*\\])",
    r"(\x00)",
    r"(\bnull\b\s*[)(])",
]

# ── Path Traversal ───────────────────────────────────────────────────

PATH_TRAVERSAL_PATTERNS = [
    r"(\.\./)",
    r"(\.\.\\)",
    r"(%2e%2e[/\\%])",
    r"(%252e%252e)",
    r"(\.\./\.\./)",
    r"(/etc/(passwd|shadow|hosts))",
    r"(C:\\Windows\\)",
    r"(/proc/self/)",
]

# ── Command Injection ───────────────────────────────────────────────

CMD_INJECTION_PATTERNS = [
    r"([;&|`$])",
    r"(\$\(.*\))",
    r"(`.*`)",
    r"(\|\s*\w+)",
    r"(>\s*/)",
    r"(\b(cat|ls|rm|chmod|chown|wget|curl|nc|ncat)\b\s)",
]

# ── SSRF Patterns ────────────────────────────────────────────────────

SSRF_BLOCKED_HOSTS = [
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",  # GCP metadata
    "100.100.100.200",  # Azure metadata
]

# ── XXE Patterns ─────────────────────────────────────────────────────

XXE_PATTERNS = [
    r"(<!DOCTYPE[^>]*\[)",
    r"(<!ENTITY\s)",
    r"(&\w+;)",
    r"(SYSTEM\s+[\"'])",
    r"(PUBLIC\s+[\"'])",
]


class InputValidator:
    """
    Validates input strings against 32+ attack patterns.
    Designed for API endpoints and user-facing inputs.
    """

    def __init__(self, strict: bool = True):
        self.strict = strict
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile all regex patterns for performance."""
        self._sql = [re.compile(p, re.IGNORECASE) for p in SQL_PATTERNS]
        self._xss = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]
        self._ldap = [re.compile(p, re.IGNORECASE) for p in LDAP_PATTERNS]
        self._path = [re.compile(p, re.IGNORECASE) for p in PATH_TRAVERSAL_PATTERNS]
        self._cmd = [re.compile(p, re.IGNORECASE) for p in CMD_INJECTION_PATTERNS]
        self._xxe = [re.compile(p, re.IGNORECASE) for p in XXE_PATTERNS]

    def validate(self, input_str: str) -> ValidationResult:
        """
        Validate a single input string against all patterns.
        Returns ValidationResult with safety assessment.
        """
        if not isinstance(input_str, str):
            return ValidationResult(is_safe=True)

        if len(input_str) == 0:
            return ValidationResult(is_safe=True)

        # Length check (ReDoS protection)
        if len(input_str) > 10000:
            return ValidationResult(
                is_safe=False,
                threat_type="REDOS_LENGTH",
                detail=f"Input too long ({len(input_str)} chars, max 10000)",
            )

        # SQL injection
        for i, pattern in enumerate(self._sql):
            if pattern.search(input_str):
                logger.warning(f"SQL injection attempt blocked: pattern {i}")
                return ValidationResult(
                    is_safe=False,
                    threat_type="SQL_INJECTION",
                    detail=f"Matched SQL pattern #{i}",
                    pattern_matched=SQL_PATTERNS[i],
                )

        # XSS
        for i, pattern in enumerate(self._xss):
            if pattern.search(input_str):
                logger.warning(f"XSS attempt blocked: pattern {i}")
                return ValidationResult(
                    is_safe=False,
                    threat_type="XSS",
                    detail=f"Matched XSS pattern #{i}",
                    pattern_matched=XSS_PATTERNS[i],
                )

        # LDAP injection
        for i, pattern in enumerate(self._ldap):
            if pattern.search(input_str):
                return ValidationResult(
                    is_safe=False,
                    threat_type="LDAP_INJECTION",
                    detail=f"Matched LDAP pattern #{i}",
                )

        # Path traversal
        for i, pattern in enumerate(self._path):
            if pattern.search(input_str):
                return ValidationResult(
                    is_safe=False,
                    threat_type="PATH_TRAVERSAL",
                    detail=f"Matched path traversal pattern #{i}",
                )

        # Command injection (only in strict mode — sports data has legit & | chars)
        if self.strict:
            for i, pattern in enumerate(self._cmd):
                if pattern.search(input_str):
                    return ValidationResult(
                        is_safe=False,
                        threat_type="COMMAND_INJECTION",
                        detail=f"Matched command injection pattern #{i}",
                    )

        # XXE
        for i, pattern in enumerate(self._xxe):
            if pattern.search(input_str):
                return ValidationResult(
                    is_safe=False,
                    threat_type="XXE",
                    detail=f"Matched XXE pattern #{i}",
                )

        return ValidationResult(is_safe=True, sanitized=input_str)

    def validate_url(self, url: str) -> ValidationResult:
        """Validate a URL for SSRF prevention."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""

            # Block internal hosts
            if hostname in SSRF_BLOCKED_HOSTS:
                return ValidationResult(
                    is_safe=False,
                    threat_type="SSRF",
                    detail=f"Blocked internal host: {hostname}",
                )

            # Block private IP ranges
            if hostname.startswith("10.") or hostname.startswith("192.168."):
                return ValidationResult(
                    is_safe=False,
                    threat_type="SSRF",
                    detail=f"Blocked private IP: {hostname}",
                )

            # Block file:// and other dangerous schemes
            if parsed.scheme not in ("http", "https", ""):
                return ValidationResult(
                    is_safe=False,
                    threat_type="SSRF",
                    detail=f"Blocked scheme: {parsed.scheme}",
                )

            return ValidationResult(is_safe=True, sanitized=url)

        except Exception as e:
            return ValidationResult(
                is_safe=False,
                threat_type="URL_PARSE_ERROR",
                detail=str(e),
            )

    def validate_batch(self, inputs: dict) -> List[ValidationResult]:
        """Validate a dict of inputs. Returns list of any failures."""
        failures = []
        for key, value in inputs.items():
            if isinstance(value, str):
                result = self.validate(value)
                if not result.is_safe:
                    result.detail = f"Field '{key}': {result.detail}"
                    failures.append(result)
        return failures

    def sanitize(self, input_str: str) -> str:
        """Strip dangerous characters while preserving safe content."""
        if not isinstance(input_str, str):
            return str(input_str)

        # Remove null bytes
        cleaned = input_str.replace("\x00", "")
        # Remove script tags (including malformed closing tags like </script foo="bar">)
        cleaned = re.sub(r"<\s*script\b[^>]*>.*?</\s*script[^>]*>", "", cleaned, flags=re.I | re.S)
        # Remove event handlers
        cleaned = re.sub(r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", "", cleaned, flags=re.I)
        # Escape HTML entities
        cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
        return cleaned
