# Autonomous Implementation Guide: Agentic Test Automation Control Plane + MCP Integration

## Context

This guide defines how to implement an autonomous POC using:

- **Control Plane Repository**: `vinipx/taflex-agents-control`
- **Target Framework Repository**: `vinipx/taflex-python-modular`

Goal: enable GitHub workflow agents to interact with MCP support in the target repository to:

1. Read files
2. List files
3. Write new test cases
4. Maintain existing test cases
5. Execute tests
6. Analyze Allure reports

---

## 1) Architecture Options (Evolution Path)

This implementation should evolve in phases from Option 1 to Option 3.

---

### Option 1 — Single Orchestrator Agent (Fastest POC)

#### What it is
A single workflow in `taflex-agents-control` executes one orchestrator agent that performs all tasks end-to-end.

#### Responsibilities
- Checkout target repo
- Read/list files (via MCP)
- Generate/maintain tests
- Execute pytest
- Capture and summarize Allure output
- Commit changes and open PR to target repo

#### Why use first
- Lowest complexity
- Quick validation of integration plumbing
- Fastest demo

---

### Option 2 — Multi-Agent Pipeline (Scalable Mid-Step)

#### What it is
Split agent responsibilities into specialized roles chained in a pipeline.

#### Agent roles
- **Planner Agent**: creates test plan from repo/module context
- **Author Agent**: creates/updates test files
- **Executor Agent**: runs tests and stores execution output
- **Analyst Agent**: reads Allure output and recommends fixes

#### Data contracts (artifacts between stages)
- `artifacts/test-plan.json`
- `artifacts/test-changes.json`
- `artifacts/execution-summary.json`
- `artifacts/allure-summary.json`
- `artifacts/maintenance-actions.json`

#### Why evolve here
- Better maintainability
- Easier debugging
- Independent optimization per agent stage

---

### Option 3 — Event-Driven Agent Mesh (Advanced)

#### What it is
Autonomous event-driven architecture using GitHub events and schedules.

#### Event triggers
- PR opened/updated → impact analysis + targeted test generation
- Label `ai-generate-tests` → authoring pipeline
- Issue comment `/ai-maintain-tests` → maintenance flow
- Nightly schedule → regression + flaky detection

#### Why evolve here
- Continuous autonomy
- Production-like behavior
- Better long-term quality maintenance

---

## 2) Repository Topology and Boundaries

## 2.1 Repositories

- **Control Plane (orchestrator)**: `vinipx/taflex-agents-control`
- **Target (framework + MCP implementation)**: `vinipx/taflex-python-modular`

## 2.2 Responsibility split

### `taflex-agents-control`
- Workflows
- Agent orchestration code
- Prompt templates
- Governance/rules
- Pipeline artifacts and summaries

### `taflex-python-modular`
- MCP server/interface implementation
- Test framework code
- Test directories and fixtures
- Allure configuration and raw results

## 2.3 Orchestration model (initial)

Use **Pull Model**:
- Control workflow clones target repo into workspace
- Control workflow runs orchestration against target files
- Control workflow pushes branch to target
- Control workflow opens PR in target

---

## 3) Target End-State Folder Structures

## 3.1 Control repository (`vinipx/taflex-agents-control`)

```text
.github/workflows/
  orchestrate-target.yml
  plan.yml
  author.yml
  execute.yml
  analyze.yml
  nightly-regression.yml

agents/
  orchestrator/main.py
  planner/main.py
  author/main.py
  executor/main.py
  analyst/main.py
  mcp_client.py
  guardrails.py

prompts/
  generate_test.prompt.md
  maintain_test.prompt.md
  analyze_failure.prompt.md

scripts/
  run_orchestrator.py

configs/
  targets.yaml
  policy.yaml

artifacts/               # generated at runtime in CI
```

## 3.2 Target repository (`vinipx/taflex-python-modular`)

```text
tests/
  generated/
  maintained/
  manual/

reports/
  allure-results/
  allure-report/

mcp/
  # existing MCP support lives here (or equivalent location)
```

---

## 4) Security, Auth, and Governance

## 4.1 Required secrets in control repo

Configure in `vinipx/taflex-agents-control`:

- `TARGET_REPO` = `vinipx/taflex-python-modular`
- `TARGET_DEFAULT_BRANCH` = `main` (or actual default branch)
- `TARGET_PUSH_TOKEN` = PAT or GitHub App token with least privilege:
  - Contents: Read/Write
  - Pull requests: Read/Write
  - Metadata: Read

## 4.2 Guardrails (must enforce)

- Allow writes only to:
  - `tests/generated/**`
  - `tests/maintained/**`
- Block edits to sensitive paths by default:
  - `.github/workflows/**`
  - `pyproject.toml`
  - `requirements*.txt`
  - security/auth config files
- Max file modifications per run (e.g., 20)
- Fail if MCP output schema invalid

---

## 5) Step-by-Step Implementation Plan (Autonomous Execution)

## Phase 0 — Planning and baseline

### Step 0.1 — Create baseline docs
**What**: Add architecture README section in control repo.  
**Why**: Align humans and agents on boundaries and flow.  
**How**: Document control vs target responsibilities, auth, branching, PR model.

### Step 0.2 — Define acceptance criteria
**What**: Add measurable POC criteria.  
**Why**: Agents need objective completion conditions.  
**How**: Add checklist in README (see Section 9).

---

## Phase 1 — Option 1 bootstrap (single orchestrator)

### Step 1.1 — Add workflow `orchestrate-target.yml`
**What**: Manual `workflow_dispatch` pipeline in control repo.  
**Why**: Deterministic first end-to-end run.  
**How**:
1. Checkout control repo
2. Checkout target repo into `workspace/target`
3. Setup Python
4. Install deps
5. Run `scripts/run_orchestrator.py`
6. Run pytest with Allure output
7. Upload artifacts
8. Commit/push branch to target
9. Open PR in target

### Step 1.2 — Add script `scripts/run_orchestrator.py`
**What**: Initial deterministic orchestrator script.  
**Why**: Validate plumbing before LLM complexity.  
**How**:
- parse args (`--repo-path`, `--action`, `--target-module`)
- create/update at least one test file in `tests/generated/`
- print trace logs
- exit non-zero on invalid action

### Step 1.3 — Validate first run
**What**: Execute manual workflow with action `generate`.  
**Why**: Prove end-to-end integration.  
**How**: confirm:
- PR created in target repo
- file added in `tests/generated/`
- pytest executed
- `allure-results` artifact uploaded

---

## Phase 2 — MCP-first orchestration

### Step 2.1 — Implement MCP client wrapper
**What**: Add `agents/mcp_client.py`.  
**Why**: Standardize agent-to-MCP communication.  
**How**: expose methods:
- `list_files(path, glob_pattern=None)`
- `read_file(path)`
- `write_file(path, content)`
- `execute_tests(command)`
- `get_allure_summary(results_path)`

### Step 2.2 — Replace direct FS operations with MCP calls
**What**: Update orchestrator to use MCP wrapper.  
**Why**: Core requirement is MCP-driven operation.  
**How**:
- list existing tests via MCP
- read reference tests via MCP
- write generated/maintained tests via MCP
- run tests via MCP (if available) or fallback shell
- parse Allure summary via MCP-enabled helper

### Step 2.3 — Add schema validations
**What**: Validate all MCP I/O payloads with JSON schema.  
**Why**: Avoid malformed actions and brittle runs.  
**How**: add schema files and strict validators before executing writes/actions.

---

## Phase 3 — Option 2 evolution (multi-agent pipeline)

### Step 3.1 — Split into role-specific agents
**What**: Create planner/author/executor/analyst modules.  
**Why**: Improve modularity and independent testing.  
**How**:
- `agents/planner/main.py`
- `agents/author/main.py`
- `agents/executor/main.py`
- `agents/analyst/main.py`

### Step 3.2 — Introduce artifact contracts
**What**: Use JSON artifacts as stage handoff contracts.  
**Why**: Ensure deterministic inter-agent communication.  
**How**:
- planner emits `test-plan.json`
- author emits `test-changes.json`
- executor emits `execution-summary.json`
- analyst emits `allure-summary.json` and `maintenance-actions.json`

### Step 3.3 — Create split workflows
**What**: Add `plan.yml`, `author.yml`, `execute.yml`, `analyze.yml`.  
**Why**: Clear CI observability and rerunnable stages.  
**How**: each workflow uploads/downloads relevant artifacts and logs stage metrics.

---

## Phase 4 — Option 3 evolution (event-driven mesh)

### Step 4.1 — Add event triggers
**What**: trigger autonomous flows on PR, labels, comments, schedule.  
**Why**: move from manual to continuous autonomous operations.  
**How**:
- `on: pull_request`
- `on: issue_comment`
- `on: schedule`
- `on: workflow_dispatch`

### Step 4.2 — Add command grammar for comments
**What**: parse commands like `/ai-generate-tests module=...`.  
**Why**: controlled human-in-the-loop autonomy.  
**How**: command parser with strict allowlist and validation.

### Step 4.3 — Add flaky and trend intelligence
**What**: nightly analysis of historical Allure summaries.  
**Why**: prioritize maintenance actions and reduce noise.  
**How**: aggregate results into trend artifacts and open maintenance PRs/issues.

---

## 6) Branching and PR strategy

- Branch naming:
  - `agent/generate-<run_id>`
  - `agent/maintain-<run_id>`
  - `agent/fix-<failure_signature>-<run_id>`
- Commit format:
  - `chore(agent): generate tests for <module>`
  - `chore(agent): maintain tests based on allure analysis`
- PR template should include:
  - scope/module
  - files created/updated count
  - test execution summary
  - allure artifact reference

---

## 7) Operational Policies for Autonomous Agent

1. Never write outside approved directories.
2. Never force-push protected branches.
3. Never merge PRs automatically in early POC stage.
4. Always attach execution and allure artifacts.
5. If no changes required, skip PR creation and publish summary only.
6. If test run fails catastrophically (infrastructure error), mark as infra-failure and stop write operations.

---

## 8) Suggested Milestone Timeline

## Milestone 1 (Day 1–2)
- Option 1 workflow + orchestrator script
- First PR generated in target repo

## Milestone 2 (Day 3–5)
- MCP wrapper integration
- schema validations
- guardrails active

## Milestone 3 (Week 2)
- Option 2 multi-agent split
- artifacts contracts and separate workflows

## Milestone 4 (Week 3+)
- Option 3 event-driven triggers
- nightly flaky analysis and autonomous maintenance loop

---

## 9) Definition of Done (POC Acceptance Criteria)

POC is complete when all are true:

1. Control repo workflow can operate against target repo end-to-end.
2. Agent performs file list/read/write through MCP.
3. Agent creates or updates valid pytest tests in allowed directories.
4. Tests are executed and Allure raw results are produced.
5. Workflow uploads artifacts: execution summary + allure summary.
6. PR is created in target repo with clear agent-generated description.
7. Guardrails prevent unauthorized writes.
8. Re-run can maintain/update tests based on prior failures.

---

## 10) Handoff Prompt Template for GitHub Coding Agent

Use this as the exact implementation brief for autonomous execution:

```md
Implement the autonomous POC control plane in repository `vinipx/taflex-agents-control` to orchestrate test generation and maintenance in `vinipx/taflex-python-modular`.

Requirements:
1. Add Option 1 bootstrap:
   - `.github/workflows/orchestrate-target.yml`
   - `scripts/run_orchestrator.py`
2. Integrate MCP-first operations:
   - `agents/mcp_client.py`
   - Replace direct filesystem operations with MCP wrapper calls
3. Add guardrails and schemas:
   - Write allowlist for `tests/generated/**`, `tests/maintained/**`
   - JSON schema validation for stage artifacts
4. Emit and upload artifacts:
   - `test-plan.json`, `execution-summary.json`, `allure-summary.json`
5. Prepare Option 2 evolution:
   - scaffold role agents in `agents/planner`, `agents/author`, `agents/executor`, `agents/analyst`
6. Document architecture and runbook in README.

Do not implement auto-merge. Use PR-only change delivery to target repository.
```

---

## 11) Final Recommendation

- Start with **Option 1 immediately** for fast proof.
- Move to **Option 2** once first PR loop is stable.
- Introduce **Option 3** only after guardrails + observability are mature.

This creates a reliable progression from simple orchestration to autonomous agentic operations without losing control.
