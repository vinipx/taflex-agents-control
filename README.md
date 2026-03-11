# taflex-agents-control

Control-plane repository for autonomous test orchestration against [`vinipx/taflex-python-modular`](https://github.com/vinipx/taflex-python-modular).

---

## Control-Plane → Target-Repo Orchestration

This repository acts as the **orchestrator** that drives automated test generation and maintenance in the target repository via a pull model:

1. The control workflow runs in this repo.
2. It invokes `scripts/run_orchestrator.py` which validates configuration and emits bootstrap metadata.
3. In later phases the orchestrator will checkout the target repo, generate/maintain tests, open a PR in the target — **no auto-merge, PR-only delivery**.

### Architecture overview

```
taflex-agents-control (this repo)
  └── .github/workflows/orchestrate-target.yml   ← manual trigger
  └── scripts/run_orchestrator.py                 ← orchestrator entry point

        │  pulls/pushes via TARGET_PUSH_TOKEN
        ▼

vinipx/taflex-python-modular (target repo)
  └── tests/generated/   ← agent-created tests (future phases)
  └── tests/maintained/  ← agent-maintained tests (future phases)
```

---

## Required Secrets and Variables

Configure the following in **this repository's** Settings → Secrets and Variables:

| Name | Type | Value / Description |
|---|---|---|
| `TARGET_PUSH_TOKEN` | Secret | PAT or GitHub App token with `contents: read/write` and `pull-requests: read/write` on the target repo |
| `TARGET_DEFAULT_BRANCH` | Variable | Default branch of the target repo (e.g. `main`) |

The `TARGET_REPO` value (`vinipx/taflex-python-modular`) is hardcoded in the workflow and does not require a secret.

---

## Workflow: `orchestrate-target.yml`

**Trigger**: `workflow_dispatch` (manual)

### Inputs

| Input | Required | Description | Example |
|---|---|---|---|
| `goal` | ✅ Yes | Task or goal to orchestrate | `generate tests for module payments` |
| `target_branch` | No | Override target branch (defaults to `TARGET_DEFAULT_BRANCH`) | `feature/new-tests` |

### Running the workflow

1. Navigate to **Actions → Orchestrate Target Repository**.
2. Click **Run workflow**.
3. Fill in the `goal` input (and optionally `target_branch`).
4. Click **Run workflow**.

---

## Validation Steps

To verify the bootstrap is correctly configured:

1. Confirm `TARGET_PUSH_TOKEN` and `TARGET_DEFAULT_BRANCH` are set in repository secrets/variables.
2. Trigger the workflow via **Actions → Orchestrate Target Repository → Run workflow** with:
   - `goal`: `validate bootstrap configuration`
3. Inspect the workflow run logs. Expected output:
   ```
   [INFO] === Orchestrator Bootstrap (Phase 1 / Option 1) ===
   [INFO] Target repository : vinipx/taflex-python-modular
   [INFO] Target branch     : main
   [INFO] Goal              : validate bootstrap configuration
   [INFO] TARGET_PUSH_TOKEN : [REDACTED — present and non-empty]
   [INFO] No auto-merge will be performed.
   [INFO] === Orchestrator bootstrap completed successfully ===
   ```
4. If any required variable is missing, the script exits non-zero with an explicit error message identifying the missing variable.

---

## Operational Policies

- Changes to the target repository are delivered **via PR only** — no auto-merge.
- Agent writes are restricted to `tests/generated/**` and `tests/maintained/**` in the target repo.
- Secrets are never printed in logs.
- See [`AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md`](./AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md) for the full architecture roadmap.
