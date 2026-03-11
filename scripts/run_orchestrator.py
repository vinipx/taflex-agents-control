#!/usr/bin/env python3
"""
Bootstrap orchestrator script for Phase 1 (Option 1).

Validates required environment variables and emits structured logs indicating
what would be orchestrated against the target repository. Exits non-zero with
an explicit reason when required configuration is missing.

No secrets are printed. No auto-merge is performed.
"""

import os
import sys


def get_env(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def main() -> int:
    # --- Validate required configuration ---
    required_vars = ["TARGET_REPO", "TARGET_DEFAULT_BRANCH", "TARGET_PUSH_TOKEN"]
    missing = [v for v in required_vars if not get_env(v)]
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
    effective_branch = branch_override or get_env("TARGET_DEFAULT_BRANCH")

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
    print(
        "[INFO] Orchestration plan: validate plumbing, emit bootstrap metadata. "
        "Full agent execution (checkout, test generation, PR creation) will be "
        "added in subsequent phases.",
        flush=True,
    )
    print("[INFO] No auto-merge will be performed.", flush=True)
    print("[INFO] === Orchestrator bootstrap completed successfully ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
