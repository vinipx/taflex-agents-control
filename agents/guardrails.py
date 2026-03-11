"""
guardrails.py — Path allowlist/blocklist enforcement and modification counter.

Enforces the security rules defined in Section 4.2 of
AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md:
  - Allow writes only to tests/generated/** and tests/maintained/**
  - Block edits to sensitive paths: .github/workflows/**, pyproject.toml,
    requirements*.txt, security/auth config files
  - Max file modifications per run (default: 20)
"""

from __future__ import annotations

import fnmatch
import logging
import os

logger = logging.getLogger(__name__)

# Paths where write operations are permitted (relative glob patterns)
WRITE_ALLOWLIST: tuple[str, ...] = (
    "tests/generated/*",
    "tests/generated/**",
    "tests/maintained/*",
    "tests/maintained/**",
)

# Paths that must never be modified regardless of allowlist
WRITE_BLOCKLIST: tuple[str, ...] = (
    ".github/workflows/*",
    ".github/workflows/**",
    "pyproject.toml",
    "requirements*.txt",
    "requirements-*.txt",
    "setup.py",
    "setup.cfg",
    "*.env",
    ".env*",
    "secrets*",
    "auth*",
    "security*",
    "config/auth*",
    "config/security*",
)

MAX_MODIFICATIONS_PER_RUN: int = 20


class Guardrails:
    """Enforces write-path allowlist/blocklist and a per-run modification cap."""

    def __init__(self, max_modifications: int = MAX_MODIFICATIONS_PER_RUN) -> None:
        self._max_modifications = max_modifications
        self._modification_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def modification_count(self) -> int:
        """Number of write operations approved so far this run."""
        return self._modification_count

    def check_write(self, path: str) -> tuple[bool, str]:
        """
        Validate whether a write to *path* is permitted.

        Returns:
            (allowed: bool, reason: str) — reason is empty when allowed.
        """
        normalised = _normalise(path)

        # Blocklist takes precedence over allowlist
        if _matches_any(normalised, WRITE_BLOCKLIST):
            reason = f"[GUARDRAILS] BLOCKED: '{path}' matches sensitive blocklist."
            logger.warning(reason)
            return False, reason

        # Must match at least one allowlist pattern
        if not _matches_any(normalised, WRITE_ALLOWLIST):
            reason = (
                f"[GUARDRAILS] BLOCKED: '{path}' is not in the write allowlist "
                f"(tests/generated/** or tests/maintained/**)."
            )
            logger.warning(reason)
            return False, reason

        # Enforce per-run cap
        if self._modification_count >= self._max_modifications:
            reason = (
                f"[GUARDRAILS] BLOCKED: max modifications per run "
                f"({self._max_modifications}) reached."
            )
            logger.warning(reason)
            return False, reason

        return True, ""

    def record_write(self, path: str) -> None:
        """Increment the modification counter after a successful write."""
        self._modification_count += 1
        logger.info(
            "[GUARDRAILS] Write recorded for '%s'. Total modifications this run: %d",
            path,
            self._modification_count,
        )

    def reset(self) -> None:
        """Reset the modification counter (useful between test runs)."""
        self._modification_count = 0


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _normalise(path: str) -> str:
    """Normalise path separators and strip leading slashes/dots."""
    return os.path.normpath(path).replace("\\", "/").lstrip("/").lstrip("./")


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    """Return True if *path* matches any of the given glob patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Also test against the last N path components to handle both
        # relative and absolute-looking paths.
        parts = path.split("/")
        for depth in range(1, len(parts)):
            sub = "/".join(parts[depth:])
            if fnmatch.fnmatch(sub, pattern):
                return True
    return False
