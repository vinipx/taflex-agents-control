"""
mcp_client.py — Standardised MCP client wrapper for agent-to-MCP communication.

Implements the interface defined in Phase 2 / Step 2.1 of
AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md.

All operations include structured logging with an [MCP] prefix.
When the MCP server is not available the client falls back to direct
filesystem operations (labelled [DIRECT-FS]).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import subprocess
import sys
from typing import Optional
from xml.etree import ElementTree

from agents.guardrails import Guardrails

logger = logging.getLogger(__name__)

_MCP_PREFIX = "[MCP]"
_FS_PREFIX = "[DIRECT-FS]"


class MCPClient:
    """
    High-level interface for file and test-execution operations against
    a checked-out target repository.

    Parameters
    ----------
    base_path:
        Absolute (or relative) path to the root of the checked-out target
        repository.  All path arguments to the public methods are resolved
        relative to this base.
    mcp_server_available:
        Set to True when a real MCP server is reachable.  When False (the
        default) every operation falls back to direct filesystem calls.
    max_modifications:
        Maximum number of write operations allowed in a single run.
    """

    def __init__(
        self,
        base_path: str,
        mcp_server_available: bool = False,
        max_modifications: int = 20,
    ) -> None:
        self.base_path = os.path.abspath(base_path)
        self._mcp_available = mcp_server_available
        self._guardrails = Guardrails(max_modifications=max_modifications)

    # ------------------------------------------------------------------
    # list_files
    # ------------------------------------------------------------------

    def list_files(
        self,
        path: str,
        glob_pattern: Optional[str] = None,
    ) -> Optional[list[str]]:
        """
        List files/directories at *path*, optionally filtered by *glob_pattern*.

        Parameters
        ----------
        path:
            Directory path to list.  Resolved relative to ``base_path``.
        glob_pattern:
            Optional fnmatch-style pattern (e.g. ``"*.py"``).

        Returns
        -------
        Optional[list[str]]
            Sorted list of entry names found at *path*, or None on error.
        """
        mode = _MCP_PREFIX if self._mcp_available else _FS_PREFIX
        abs_path = self._resolve(path)
        logger.info("%s list_files('%s', glob=%s)", mode, abs_path, glob_pattern)
        print(f"{mode} list_files: {abs_path}  glob={glob_pattern!r}", flush=True)

        if not os.path.isdir(abs_path):
            logger.warning("%s list_files: path not found: %s", mode, abs_path)
            print(f"{mode} list_files WARN: path not found: {abs_path}", flush=True)
            return None

        try:
            entries = sorted(os.listdir(abs_path))
        except OSError as exc:
            logger.error("%s list_files error: %s", mode, exc)
            print(f"{mode} list_files ERROR: {exc}", flush=True)
            return None

        if glob_pattern:
            entries = [e for e in entries if fnmatch.fnmatch(e, glob_pattern)]

        logger.info("%s list_files returned %d entries", mode, len(entries))
        print(f"{mode} list_files: {len(entries)} entries returned", flush=True)
        return entries

    # ------------------------------------------------------------------
    # read_file
    # ------------------------------------------------------------------

    def read_file(self, path: str) -> Optional[str]:
        """
        Read and return the contents of *path* as a string.

        Parameters
        ----------
        path:
            File path, resolved relative to ``base_path``.

        Returns
        -------
        Optional[str]
            File contents, or None on error (distinguishes from a legitimately empty file).
        """
        mode = _MCP_PREFIX if self._mcp_available else _FS_PREFIX
        abs_path = self._resolve(path)
        logger.info("%s read_file('%s')", mode, abs_path)
        print(f"{mode} read_file: {abs_path}", flush=True)

        try:
            with open(abs_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            logger.info("%s read_file: %d bytes", mode, len(content))
            print(f"{mode} read_file: {len(content)} bytes read", flush=True)
            return content
        except OSError as exc:
            logger.error("%s read_file error: %s", mode, exc)
            print(f"{mode} read_file ERROR: {exc}", flush=True)
            return None

    # ------------------------------------------------------------------
    # write_file
    # ------------------------------------------------------------------

    def write_file(self, path: str, content: str) -> bool:
        """
        Write *content* to *path*.

        Guardrails are enforced before any write is attempted:
        - Only ``tests/generated/**`` and ``tests/maintained/**`` are allowed.
        - Sensitive paths are always blocked.
        - Per-run modification cap is enforced.

        Parameters
        ----------
        path:
            File path relative to ``base_path``.
        content:
            String content to write.

        Returns
        -------
        bool
            True on success, False when blocked by guardrails or on I/O error.
        """
        mode = _MCP_PREFIX if self._mcp_available else _FS_PREFIX

        allowed, reason = self._guardrails.check_write(path)
        if not allowed:
            print(f"{mode} write_file BLOCKED: {reason}", flush=True)
            return False

        abs_path = self._resolve(path)
        logger.info("%s write_file('%s', %d bytes)", mode, abs_path, len(content))
        print(f"{mode} write_file: {abs_path}", flush=True)

        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._guardrails.record_write(path)
            logger.info("%s write_file: success", mode)
            print(f"{mode} write_file: success ({len(content)} bytes written)", flush=True)
            return True
        except OSError as exc:
            logger.error("%s write_file error: %s", mode, exc)
            print(f"{mode} write_file ERROR: {exc}", flush=True)
            return False

    # ------------------------------------------------------------------
    # execute_tests
    # ------------------------------------------------------------------

    # Allowlist of command prefixes permitted in execute_tests
    _ALLOWED_TEST_COMMANDS: tuple[str, ...] = ("pytest", "python -m pytest", "python3 -m pytest")

    def execute_tests(self, command: str) -> dict:
        """
        Execute a test command and return structured results.

        Only commands starting with an allowed prefix (``pytest``,
        ``python -m pytest``) are permitted to prevent shell injection.

        Parameters
        ----------
        command:
            Test command string to execute (e.g. ``"pytest tests/ --tb=short"``).

        Returns
        -------
        dict
            ``{"return_code": int, "stdout": str, "stderr": str}``
        """
        mode = _MCP_PREFIX if self._mcp_available else _FS_PREFIX

        # Guard: only allow known safe test-runner commands
        stripped = command.strip()
        if not any(stripped.startswith(prefix) for prefix in self._ALLOWED_TEST_COMMANDS):
            reason = (
                f"Command '{stripped}' is not in the allowed test-command list: "
                f"{self._ALLOWED_TEST_COMMANDS}"
            )
            logger.error("%s execute_tests BLOCKED: %s", mode, reason)
            print(f"{mode} execute_tests BLOCKED: {reason}", flush=True)
            return {"return_code": -1, "stdout": "", "stderr": reason}

        logger.info("%s execute_tests: %s", mode, command)
        print(f"{mode} execute_tests: {command}", flush=True)

        # Split into a list of tokens so shell=False can be used safely
        import shlex
        try:
            args = shlex.split(stripped)
        except ValueError as exc:
            logger.error("%s execute_tests: could not parse command: %s", mode, exc)
            return {"return_code": -1, "stdout": "", "stderr": str(exc)}

        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                cwd=self.base_path,
            )
            summary = {
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            logger.info(
                "%s execute_tests: return_code=%d", mode, result.returncode
            )
            print(
                f"{mode} execute_tests: return_code={result.returncode}", flush=True
            )
            return summary
        except Exception as exc:  # noqa: BLE001
            logger.error("%s execute_tests error: %s", mode, exc)
            print(f"{mode} execute_tests ERROR: {exc}", flush=True)
            return {"return_code": -1, "stdout": "", "stderr": str(exc)}

    # ------------------------------------------------------------------
    # get_allure_summary
    # ------------------------------------------------------------------

    def get_allure_summary(self, results_path: str) -> dict:
        """
        Parse an Allure results directory and return a summary.

        Supports both Allure JSON result files (``*-result.json``) and
        JUnit-style XML files as a fallback.

        Parameters
        ----------
        results_path:
            Path to the Allure results directory, relative to ``base_path``.

        Returns
        -------
        dict
            ``{"total": int, "passed": int, "failed": int, "skipped": int}``
        """
        mode = _MCP_PREFIX if self._mcp_available else _FS_PREFIX
        abs_results = self._resolve(results_path)
        logger.info("%s get_allure_summary('%s')", mode, abs_results)
        print(f"{mode} get_allure_summary: {abs_results}", flush=True)

        summary: dict = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        if not os.path.isdir(abs_results):
            logger.warning(
                "%s get_allure_summary: results path not found: %s",
                mode,
                abs_results,
            )
            print(
                f"{mode} get_allure_summary WARN: path not found: {abs_results}",
                flush=True,
            )
            return summary

        # Try Allure JSON result files first
        json_files = [
            f for f in os.listdir(abs_results) if f.endswith("-result.json")
        ]
        if json_files:
            for fname in json_files:
                fpath = os.path.join(abs_results, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    status = str(data.get("status", "")).lower()
                    summary["total"] += 1
                    if status == "passed":
                        summary["passed"] += 1
                    elif status in ("failed", "broken"):
                        summary["failed"] += 1
                    elif status == "skipped":
                        summary["skipped"] += 1
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "%s get_allure_summary: error reading %s: %s",
                        mode,
                        fpath,
                        exc,
                    )
        else:
            # Fallback: JUnit XML files
            xml_files = [
                f for f in os.listdir(abs_results) if f.endswith(".xml")
            ]
            for fname in xml_files:
                fpath = os.path.join(abs_results, fname)
                try:
                    tree = ElementTree.parse(fpath)
                    root = tree.getroot()
                    suites = (
                        [root]
                        if root.tag == "testsuite"
                        else root.findall("testsuite")
                    )
                    for suite in suites:
                        summary["total"] += int(suite.get("tests", 0))
                        summary["failed"] += int(suite.get("failures", 0)) + int(
                            suite.get("errors", 0)
                        )
                        summary["skipped"] += int(suite.get("skipped", 0))
                    summary["passed"] = (
                        summary["total"]
                        - summary["failed"]
                        - summary["skipped"]
                    )
                except (OSError, ElementTree.ParseError) as exc:
                    logger.warning(
                        "%s get_allure_summary: error reading %s: %s",
                        mode,
                        fpath,
                        exc,
                    )

        logger.info("%s get_allure_summary: %s", mode, summary)
        print(f"{mode} get_allure_summary: {summary}", flush=True)
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, path: str) -> str:
        """Resolve *path* relative to ``base_path``.  Absolute paths are returned as-is."""
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_path, path)
