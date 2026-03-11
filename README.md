# taflex-agents-control

Control-plane repository for autonomous test orchestration against [`vinipx/taflex-python-modular`](https://github.com/vinipx/taflex-python-modular).

---

## Control-Plane → Target-Repo Orchestration

This repository acts as the **orchestrator** that drives automated test generation and maintenance in the target repository via a pull model:

1. The control workflow runs in this repo.
2. It checks out the target repo into `workspace/target` and invokes `scripts/run_orchestrator.py`.
3. In smoke mode the orchestrator validates MCP connectivity (list/read only, no writes).
4. In later phases the orchestrator will generate/maintain tests and open a PR in the target — **no auto-merge, PR-only delivery**.

### Architecture overview

```
taflex-agents-control (this repo)
  └── .github/workflows/orchestrate-target.yml   ← manual trigger
  └── scripts/run_orchestrator.py                 ← orchestrator entry point

        │  pulls/pushes via TARGET_PUSH_TOKEN
        ▼

vinipx/taflex-python-modular (target repo)
  └── mcp.json              ← MCP server configuration (validated in smoke mode)
  └── tests/generated/      ← agent-created tests (future phases)
  └── tests/maintained/     ← agent-maintained tests (future phases)
```

---

## Required Secrets and Variables

Configure the following in **this repository's** Settings → Secrets and Variables:

| Name | Type | Value / Description |
|---|---|---|
| `TARGET_PUSH_TOKEN` | Secret | PAT or GitHub App token with `contents: read/write` and `pull-requests: read/write` on the target repo |
| `TARGET_DEFAULT_BRANCH` | Variable | Default branch of the target repo (e.g. `main`). Optional if `target_branch` input is always supplied. |

The `TARGET_REPO` value (`vinipx/taflex-python-modular`) is hardcoded in the workflow and does not require a secret.

---

## Workflow: `orchestrate-target.yml`

**Trigger**: `workflow_dispatch` (manual)

### Inputs

| Input | Required | Description | Example |
|---|---|---|---|
| `goal` | ✅ Yes | Task or goal to orchestrate | `generate tests for module payments` |
| `target_branch` | No | Override target branch (defaults to `TARGET_DEFAULT_BRANCH`) | `main` |

### Running the workflow

1. Navigate to **Actions → Orchestrate Target Repository**.
2. Click **Run workflow**.
3. Fill in the `goal` input (and optionally `target_branch`).
4. Click **Run workflow**.

---

## MCP Smoke Validation

Use this mode to validate MCP connectivity (list/read only) before enabling write operations.

### Trigger

Run **Actions → Orchestrate Target Repository → Run workflow** with:

| Input | Value |
|---|---|
| `goal` | `mcp-smoke: validate MCP connectivity by listing files and reading mcp.json in target repo; no writes, no PR` |
| `target_branch` | `main` (or your branch; also satisfies `TARGET_DEFAULT_BRANCH` requirement if variable is unset) |

### Expected log evidence (PASS)

```
[INFO] === Orchestrator Bootstrap (Phase 1 / Option 1) ===
[INFO] Target repository : vinipx/taflex-python-modular
[INFO] Target branch     : main
[INFO] Goal              : mcp-smoke: validate MCP connectivity ...
[INFO] TARGET_PUSH_TOKEN : [REDACTED — present and non-empty]
[INFO] === MCP Smoke Mode activated ===
[INFO] Target repo path  : /home/runner/work/.../workspace/target
[SMOKE] --- Step 1: list_files (MCP contract) ---
[SMOKE] PASS: list_files returned N entries
[SMOKE]   - mcp.json
[SMOKE]   - ...
[SMOKE] --- Step 2: read_file mcp.json (MCP contract) ---
[SMOKE] PASS: read_file mcp.json succeeded (N bytes)
[SMOKE]   MCP servers configured: ['taflex-py']
[INFO] === MCP Smoke: ALL STEPS PASSED ===
[INFO] Artifact written: artifacts/test-plan.json
[INFO] Artifact written: artifacts/test-changes.json
[INFO] Artifact written: artifacts/execution-summary.json
[INFO] Artifact written: artifacts/allure-summary.json
[INFO] Artifact written: artifacts/maintenance-actions.json
[INFO] === Orchestrator completed successfully ===
```

### Failure behaviour

- If `list_files` or `read_file mcp.json` fails, each step logs `[SMOKE] FAIL: ...` and the run exits non-zero with:
  ```
  [ERROR] === MCP Smoke: FAILED — MCP list/read contract not fully executed ===
  ```
- If any artifact cannot be written, the run exits non-zero with an explicit error.

### Required artifacts (uploaded on every run)

All runs upload `orchestration-artifacts` containing:

| File | Description |
|---|---|
| `artifacts/test-plan.json` | Run mode, goal, target, planned actions |
| `artifacts/test-changes.json` | List of file changes (empty in smoke/bootstrap mode) |
| `artifacts/execution-summary.json` | Overall status and per-step smoke results |
| `artifacts/allure-summary.json` | Test counts (zero in smoke/bootstrap mode) |
| `artifacts/maintenance-actions.json` | Maintenance actions taken (empty in smoke/bootstrap mode) |

---

## Validation Steps

To verify the bootstrap is correctly configured:

1. Confirm `TARGET_PUSH_TOKEN` is set in repository secrets.
2. Confirm `TARGET_DEFAULT_BRANCH` is set as a repository variable **or** always supply `target_branch` in the workflow input.
3. Trigger the workflow via **Actions → Orchestrate Target Repository → Run workflow** with:
   - `goal`: `validate bootstrap configuration`
   - `target_branch`: `main`
4. Inspect the workflow run logs. Expected output:
   ```
   [INFO] === Orchestrator Bootstrap (Phase 1 / Option 1) ===
   [INFO] Target repository : vinipx/taflex-python-modular
   [INFO] Target branch     : main
   [INFO] Goal              : validate bootstrap configuration
   [INFO] TARGET_PUSH_TOKEN : [REDACTED — present and non-empty]
   [INFO] No auto-merge will be performed.
   [INFO] === Orchestrator completed successfully ===
   ```
5. If any required variable is missing, the script exits non-zero with an explicit error message identifying the missing variable.

---

## Operational Policies

- Changes to the target repository are delivered **via PR only** — no auto-merge.
- Agent writes are restricted to `tests/generated/**` and `tests/maintained/**` in the target repo.
- Secrets are never printed in logs.
- See [`AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md`](./AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md) for the full architecture roadmap.
