#!/usr/bin/env python3
"""
Orchestrator script for Phase 1 (Option 1).

In smoke mode (goal contains 'mcp-smoke' or 'validate connectivity'):
  - Lists files in the checked-out target repository (MCP list_files equivalent)
  - Reads mcp.json from the target repository (MCP read_file equivalent)
  - Emits PASS/FAIL for each operation

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

No secrets are printed. No auto-merge is performed.
"""

import json
import os
import sys
from datetime import datetime, timezone

ARTIFACTS_DIR = "artifacts"
SMOKE_KEYWORDS = ("mcp-smoke", "validate connectivity", "validate mcp")


def get_env(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def is_smoke_mode(goal: str) -> bool:
    """Return True if the goal indicates MCP smoke/connectivity validation."""
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in SMOKE_KEYWORDS)


def run_mcp_smoke(target_path: str) -> tuple[bool, dict]:
    """
    Perform MCP smoke test operations against the checked-out target repository.

    Simulates MCP list_files and read_file using local filesystem operations
    on the checked-out target repo path.

    Returns: (success, results_dict)
    """
    results: dict = {
        "list_files": {"status": "NOT_RUN", "file_count": 0, "files": []},
        "read_mcp_json": {"status": "NOT_RUN", "path": None, "content_valid": False},
    }

    # Step 1: list_files — list root of target repo
    print("[SMOKE] --- Step 1: list_files (MCP contract) ---", flush=True)
    print(f"[SMOKE] Target path: {target_path}", flush=True)

    if not os.path.isdir(target_path):
        print(
            f"[SMOKE] FAIL: Target path does not exist or is not a directory: {target_path}",
            flush=True,
        )
        results["list_files"]["status"] = "FAIL"
        results["list_files"]["error"] = f"Path not found: {target_path}"
        return False, results

    try:
        file_list = sorted(os.listdir(target_path))
        results["list_files"]["status"] = "PASS"
        results["list_files"]["file_count"] = len(file_list)
        results["list_files"]["files"] = file_list
        print(f"[SMOKE] PASS: list_files returned {len(file_list)} entries", flush=True)
        for entry in file_list:
            print(f"[SMOKE]   - {entry}", flush=True)
    except OSError as exc:
        print(f"[SMOKE] FAIL: list_files raised an error: {exc}", flush=True)
        results["list_files"]["status"] = "FAIL"
        results["list_files"]["error"] = str(exc)
        return False, results

    # Step 2: read_file — read mcp.json from target repo
    print("[SMOKE] --- Step 2: read_file mcp.json (MCP contract) ---", flush=True)
    mcp_json_path = os.path.join(target_path, "mcp.json")
    results["read_mcp_json"]["path"] = mcp_json_path

    if not os.path.isfile(mcp_json_path):
        print(f"[SMOKE] FAIL: mcp.json not found at {mcp_json_path}", flush=True)
        results["read_mcp_json"]["status"] = "FAIL"
        results["read_mcp_json"]["error"] = "File not found"
        return False, results

    try:
        with open(mcp_json_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        parsed = json.loads(raw)
        results["read_mcp_json"]["status"] = "PASS"
        results["read_mcp_json"]["content_valid"] = True
        mcp_servers = list(parsed.get("mcpServers", {}).keys())
        print(
            f"[SMOKE] PASS: read_file mcp.json succeeded ({len(raw)} bytes)",
            flush=True,
        )
        print(f"[SMOKE]   MCP servers configured: {mcp_servers}", flush=True)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[SMOKE] FAIL: read_file mcp.json error: {exc}", flush=True)
        results["read_mcp_json"]["status"] = "FAIL"
        results["read_mcp_json"]["error"] = str(exc)
        return False, results

    smoke_passed = (
        results["list_files"]["status"] == "PASS"
        and results["read_mcp_json"]["status"] == "PASS"
    )
    return smoke_passed, results


def emit_artifacts(
    goal: str,
    target_repo: str,
    effective_branch: str,
    smoke_mode: bool,
    smoke_results: dict | None,
    overall_success: bool,
) -> bool:
    """
    Write all required artifact JSON files to ARTIFACTS_DIR.
    Returns True if all artifacts were written successfully.
    """
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    run_mode = "mcp-smoke" if smoke_mode else "bootstrap"
    run_status = "success" if overall_success else "failure"

    artifacts = {
        "test-plan.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "goal": goal,
            "target_repo": target_repo,
            "target_branch": effective_branch,
            "actions": ["list_files", "read_file"] if smoke_mode else ["bootstrap_validation"],
            "writes_planned": False,
            "auto_merge": False,
        },
        "test-changes.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "changes": [],
            "reason": "No writes performed in smoke/bootstrap mode",
        },
        "execution-summary.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "status": run_status,
            "goal": goal,
            "target_repo": target_repo,
            "target_branch": effective_branch,
            "smoke_results": smoke_results or {},
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
            "reason": "No test execution in smoke/bootstrap mode",
        },
        "maintenance-actions.json": {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "mode": run_mode,
            "actions": [],
            "reason": "No maintenance actions in smoke/bootstrap mode",
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
    print("[INFO] === Orchestrator Bootstrap (Phase 1 / Option 1) ===", flush=True)
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

    # --- MCP smoke mode ---
    smoke_mode = is_smoke_mode(goal)
    smoke_results: dict | None = None
    overall_success = True

    if smoke_mode:
        print("[INFO] === MCP Smoke Mode activated ===", flush=True)
        target_path = get_env("TARGET_REPO_PATH") or os.path.join(
            get_env("GITHUB_WORKSPACE") or ".", "workspace", "target"
        )
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
    )

    if not artifacts_ok:
        print("[ERROR] One or more required artifacts could not be written.", flush=True)
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
