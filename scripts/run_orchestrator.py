#!/usr/bin/env python3
"""
Orchestrator script for Phase 2 (MCP-first orchestration).

Supported goal modes (detected via keyword matching):
  mcp-smoke / validate connectivity
    - Lists files in the checked-out target repository via MCPClient
    - Reads mcp.json from the target repository via MCPClient
    - Emits PASS/FAIL for each operation

  mcp-integration
    - Exercises list + read + write via MCPClient
    - Writes a probe file to tests/generated/ in the target repository
    - Validates all emitted artifacts against their JSON schemas

Always emits required artifacts:
  - artifacts/test-plan.json
  - artifacts/test-changes.json
  - artifacts/execution-summary.json
  - artifacts/allure-summary.json
  - artifacts/maintenance-actions.json

Exits non-zero with explicit reason when:
  - Required env vars are missing
  - Smoke mode requested but MCP contract operations fail
  - Any required artifact cannot be written
  - Any emitted artifact fails schema validation

No secrets are printed. No auto-merge is performed.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Ensure the repository root (parent of scripts/) is on sys.path so that
# the ``agents`` package can be imported from any working directory.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.mcp_client import MCPClient  # noqa: E402
from agents.schema_validator import validate_all_artifacts  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

ARTIFACTS_DIR = "artifacts"
SMOKE_KEYWORDS = ("mcp-smoke", "validate connectivity", "validate mcp")
INTEGRATION_KEYWORDS = ("mcp-integration",)


def get_env(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def is_smoke_mode(goal: str) -> bool:
    """Return True if the goal indicates MCP smoke/connectivity validation."""
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in SMOKE_KEYWORDS)


def is_integration_mode(goal: str) -> bool:
    """Return True if the goal requests MCP integration (list + read + write)."""
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in INTEGRATION_KEYWORDS)


def run_mcp_smoke(target_path: str) -> tuple[bool, dict]:
    """
    Perform MCP smoke test operations against the checked-out target repository
    using the MCPClient wrapper (falls back to direct-FS when MCP server is absent).

    Returns: (success, results_dict)
    """
    client_label = "[MCP-CLIENT]"
    mcp_client = MCPClient(base_path=target_path)

    results: dict = {
        "list_files": {"status": "NOT_RUN", "file_count": 0, "files": []},
        "read_mcp_json": {"status": "NOT_RUN", "path": None, "content_valid": False},
    }

    # Step 1: list_files — list root of target repo
    print(f"{client_label} --- Step 1: list_files (MCP contract) ---", flush=True)
    print(f"{client_label} Target path: {target_path}", flush=True)

    if not os.path.isdir(target_path):
        print(
            f"[SMOKE] FAIL: Target path does not exist or is not a directory: {target_path}",
            flush=True,
        )
        results["list_files"]["status"] = "FAIL"
        results["list_files"]["error"] = f"Path not found: {target_path}"
        return False, results

    file_list = mcp_client.list_files(".")
    if file_list is not None:
        results["list_files"]["status"] = "PASS"
        results["list_files"]["file_count"] = len(file_list)
        results["list_files"]["files"] = file_list
        print(f"[SMOKE] PASS: list_files returned {len(file_list)} entries", flush=True)
        for entry in file_list:
            print(f"[SMOKE]   - {entry}", flush=True)
    else:
        print("[SMOKE] FAIL: list_files returned None", flush=True)
        results["list_files"]["status"] = "FAIL"
        results["list_files"]["error"] = "list_files returned None"
        return False, results

    # Step 2: read_file — read mcp.json from target repo
    print(f"{client_label} --- Step 2: read_file mcp.json (MCP contract) ---", flush=True)
    mcp_json_path = os.path.join(target_path, "mcp.json")
    results["read_mcp_json"]["path"] = mcp_json_path

    if not os.path.isfile(mcp_json_path):
        print(f"[SMOKE] FAIL: mcp.json not found at {mcp_json_path}", flush=True)
        results["read_mcp_json"]["status"] = "FAIL"
        results["read_mcp_json"]["error"] = "File not found"
        return False, results

    raw = mcp_client.read_file("mcp.json")
    if raw:
        try:
            parsed = json.loads(raw)
            results["read_mcp_json"]["status"] = "PASS"
            results["read_mcp_json"]["content_valid"] = True
            mcp_servers = list(parsed.get("mcpServers", {}).keys())
            print(
                f"[SMOKE] PASS: read_file mcp.json succeeded ({len(raw)} bytes)",
                flush=True,
            )
            print(f"[SMOKE]   MCP servers configured: {mcp_servers}", flush=True)
        except json.JSONDecodeError as exc:
            print(f"[SMOKE] FAIL: read_file mcp.json JSON parse error: {exc}", flush=True)
            results["read_mcp_json"]["status"] = "FAIL"
            results["read_mcp_json"]["error"] = str(exc)
            return False, results
    else:
        print(f"[SMOKE] FAIL: read_file mcp.json returned empty content", flush=True)
        results["read_mcp_json"]["status"] = "FAIL"
        results["read_mcp_json"]["error"] = "Empty content returned"
        return False, results

    smoke_passed = (
        results["list_files"]["status"] == "PASS"
        and results["read_mcp_json"]["status"] == "PASS"
    )
    return smoke_passed, results


def run_mcp_integration(target_path: str) -> tuple[bool, dict]:
    """
    Perform MCP integration test: list + read + write via MCPClient.

    Writes a probe file to tests/generated/ in the target repository to
    exercise the full write path with guardrails active.

    Returns: (success, results_dict)
    """
    client_label = "[MCP-CLIENT]"
    mcp_client = MCPClient(base_path=target_path)

    results: dict = {
        "list_files": {"status": "NOT_RUN"},
        "read_file": {"status": "NOT_RUN"},
        "write_file": {"status": "NOT_RUN"},
    }

    print(f"{client_label} === MCP Integration Mode ===", flush=True)

    # Step 1: list_files
    print(f"{client_label} --- Step 1: list_files ---", flush=True)
    file_list = mcp_client.list_files(".")
    if file_list is not None:
        results["list_files"]["status"] = "PASS"
        results["list_files"]["count"] = len(file_list)
        print(f"[INTEGRATION] PASS: list_files: {len(file_list)} entries", flush=True)
    else:
        results["list_files"]["status"] = "FAIL"
        print("[INTEGRATION] FAIL: list_files returned None", flush=True)
        return False, results

    # Step 2: read_file (attempt mcp.json; tolerate absence)
    print(f"{client_label} --- Step 2: read_file ---", flush=True)
    read_target = "mcp.json"
    raw = mcp_client.read_file(read_target)
    if raw:
        results["read_file"]["status"] = "PASS"
        results["read_file"]["bytes"] = len(raw)
        print(f"[INTEGRATION] PASS: read_file '{read_target}' ({len(raw)} bytes)", flush=True)
    else:
        results["read_file"]["status"] = "SKIP"
        results["read_file"]["reason"] = f"'{read_target}' not found or empty — skipped"
        print(
            f"[INTEGRATION] SKIP: read_file '{read_target}' not found — continuing",
            flush=True,
        )

    # Step 3: write_file probe to tests/generated/
    print(f"{client_label} --- Step 3: write_file (probe) ---", flush=True)
    probe_path = "tests/generated/.mcp_integration_probe"
    probe_content = (
        f"# MCP integration probe — generated at "
        f"{datetime.now(timezone.utc).isoformat()}\n"
    )
    write_ok = mcp_client.write_file(probe_path, probe_content)
    if write_ok:
        results["write_file"]["status"] = "PASS"
        results["write_file"]["path"] = probe_path
        print(f"[INTEGRATION] PASS: write_file '{probe_path}'", flush=True)
    else:
        results["write_file"]["status"] = "FAIL"
        results["write_file"]["path"] = probe_path
        print(f"[INTEGRATION] FAIL: write_file '{probe_path}'", flush=True)
        return False, results

    integration_passed = all(
        r["status"] in ("PASS", "SKIP") for r in results.values()
    )
    return integration_passed, results


def emit_artifacts(
    goal: str,
    target_repo: str,
    effective_branch: str,
    smoke_mode: bool,
    smoke_results: dict | None,
    overall_success: bool,
    integration_mode: bool = False,
    integration_results: dict | None = None,
) -> bool:
    """
    Write all required artifact JSON files to ARTIFACTS_DIR.
    Returns True if all artifacts were written successfully.
    """
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    if integration_mode:
        run_mode = "mcp-integration"
    elif smoke_mode:
        run_mode = "mcp-smoke"
    else:
        run_mode = "bootstrap"

    run_status = "success" if overall_success else "failure"

    combined_results = smoke_results or integration_results or {}

    writes_planned = integration_mode
    actions: list[str]
    if integration_mode:
        actions = ["list_files", "read_file", "write_file"]
    elif smoke_mode:
        actions = ["list_files", "read_file"]
    else:
        actions = ["bootstrap_validation"]

    artifacts = {
        "test-plan.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "goal": goal,
            "target_repo": target_repo,
            "target_branch": effective_branch,
            "actions": actions,
            "writes_planned": writes_planned,
            "auto_merge": False,
        },
        "test-changes.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "changes": [],
            "reason": "No writes performed in smoke/bootstrap mode" if not integration_mode else "",
        },
        "execution-summary.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "status": run_status,
            "goal": goal,
            "target_repo": target_repo,
            "target_branch": effective_branch,
            "smoke_results": combined_results,
            "secrets_redacted": True,
            "auto_merge_performed": False,
        },
        "allure-summary.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "reason": "No test execution in smoke/bootstrap/integration mode",
        },
        "maintenance-actions.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "actions": [],
            "reason": "No maintenance actions in smoke/bootstrap/integration mode",
        },
    }

    all_ok = True
    for filename, content in artifacts.items():
        artifact_path = os.path.join(ARTIFACTS_DIR, filename)
        try:
            with open(artifact_path, "w", encoding="utf-8") as fh:
                json.dump(content, fh, indent=2)
            print(f"[INFO] Artifact written: {artifact_path}", flush=True)
        except OSError as exc:
            print(f"[ERROR] Failed to write artifact {artifact_path}: {exc}", flush=True)
            all_ok = False

    return all_ok


def main() -> int:
    # --- Validate always-required configuration ---
    always_required = ["TARGET_REPO", "TARGET_PUSH_TOKEN"]
    missing = [v for v in always_required if not get_env(v)]
    if missing:
        for var in missing:
            print(f"[ERROR] Required environment variable not set: {var}", flush=True)
        print(
            "[ERROR] Orchestration aborted. Configure the missing secrets/variables "
            "in the control repository before re-running.",
            flush=True,
        )
        return 1

    # --- Parse workflow_dispatch inputs ---
    goal = get_env("ORCHESTRATOR_GOAL")
    branch_override = get_env("ORCHESTRATOR_BRANCH_OVERRIDE")

    if not goal:
        print("[ERROR] ORCHESTRATOR_GOAL is required but was not provided.", flush=True)
        return 1

    target_repo = get_env("TARGET_REPO")

    # TARGET_DEFAULT_BRANCH is required unless a branch override was provided via input
    target_default_branch = get_env("TARGET_DEFAULT_BRANCH")
    if not target_default_branch and not branch_override:
        print(
            "[ERROR] Required environment variable not set: TARGET_DEFAULT_BRANCH "
            "(required when no branch override is provided via workflow input)",
            flush=True,
        )
        print(
            "[ERROR] Orchestration aborted. Set TARGET_DEFAULT_BRANCH as a repository "
            "variable or provide a branch override input.",
            flush=True,
        )
        return 1

    effective_branch = branch_override or target_default_branch

    # --- Emit structured bootstrap log (no secrets) ---
    print("[INFO] === Orchestrator Bootstrap (Phase 2 / MCP-first) ===", flush=True)
    print(f"[INFO] Target repository : {target_repo}", flush=True)
    print(f"[INFO] Target branch     : {effective_branch}", flush=True)
    print(f"[INFO] Goal              : {goal}", flush=True)
    print(
        "[INFO] TARGET_PUSH_TOKEN : [REDACTED — present and non-empty]",
        flush=True,
    )
    if branch_override:
        print(f"[INFO] Branch override applied: {branch_override}", flush=True)
    print("[INFO] No auto-merge will be performed.", flush=True)

    # --- Determine run mode ---
    smoke_mode = is_smoke_mode(goal)
    integration_mode = is_integration_mode(goal)
    smoke_results: dict | None = None
    integration_results: dict | None = None
    overall_success = True

    target_path = get_env("TARGET_REPO_PATH") or os.path.join(
        get_env("GITHUB_WORKSPACE") or ".", "workspace", "target"
    )

    if smoke_mode:
        print("[INFO] === MCP Smoke Mode activated ===", flush=True)
        print(f"[INFO] Target repo path  : {target_path}", flush=True)

        smoke_passed, smoke_results = run_mcp_smoke(target_path)
        if smoke_passed:
            print("[INFO] === MCP Smoke: ALL STEPS PASSED ===", flush=True)
        else:
            print(
                "[ERROR] === MCP Smoke: FAILED — MCP list/read contract not fully executed ===",
                flush=True,
            )
            overall_success = False

    elif integration_mode:
        print("[INFO] === MCP Integration Mode activated ===", flush=True)
        print(f"[INFO] Target repo path  : {target_path}", flush=True)

        integration_passed, integration_results = run_mcp_integration(target_path)
        if integration_passed:
            print("[INFO] === MCP Integration: ALL STEPS PASSED ===", flush=True)
        else:
            print(
                "[ERROR] === MCP Integration: FAILED — see FAIL markers above ===",
                flush=True,
            )
            overall_success = False

    else:
        print(
            "[INFO] Orchestration plan: validate plumbing, emit bootstrap metadata. "
            "Full agent execution (checkout, test generation, PR creation) will be "
            "added in subsequent phases.",
            flush=True,
        )

    # --- Emit required artifacts (always) ---
    print("[INFO] Emitting required artifacts...", flush=True)
    artifacts_ok = emit_artifacts(
        goal=goal,
        target_repo=target_repo,
        effective_branch=effective_branch,
        smoke_mode=smoke_mode,
        smoke_results=smoke_results,
        overall_success=overall_success,
        integration_mode=integration_mode,
        integration_results=integration_results,
    )

    if not artifacts_ok:
        print("[ERROR] One or more required artifacts could not be written.", flush=True)
        return 1

    # --- Validate emitted artifacts against JSON schemas (Phase 2 / Step 2.3) ---
    print("[INFO] Validating emitted artifacts against schemas...", flush=True)
    validation_summary = validate_all_artifacts(ARTIFACTS_DIR)
    if validation_summary.get("all_valid"):
        print("[INFO] Schema validation: ALL artifacts are valid.", flush=True)
    else:
        for artifact_name, result in validation_summary.get("results", {}).items():
            if not result.get("valid"):
                for err in result.get("errors", []):
                    print(
                        f"[ERROR] Schema validation failed for '{artifact_name}': {err}",
                        flush=True,
                    )
        print(
            "[ERROR] One or more artifacts failed schema validation. "
            "See SCHEMA errors above.",
            flush=True,
        )
        return 1

    if not overall_success:
        print(
            "[ERROR] Orchestration completed with failures. "
            "See FAIL markers above for details.",
            flush=True,
        )
        return 1

    print("[INFO] === Orchestrator completed successfully ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
