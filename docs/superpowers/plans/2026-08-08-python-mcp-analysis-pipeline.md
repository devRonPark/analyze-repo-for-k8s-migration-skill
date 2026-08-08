# Python MCP Analysis Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the TypeScript/OpenCode-specific trusted analysis path with a Python MCP implementation usable by OpenCode, Claude Code, and Gemini CLI.

**Architecture:** A Python package owns the pure six-stage state machine, evidence validation, secure repository tools, and a stdio MCP server. One MCP server process owns one active analysis and clears process-private state immediately after finalization; no model-supplied session identifier or persistent cross-process state is accepted.

**Tech Stack:** Python 3.13, pinned Python MCP SDK with hash-locked offline installation, `unittest`, JSON-RPC over MCP stdio, existing Python acceptance harness.

## Global Constraints

- The delivered analysis path contains no TypeScript, JavaScript, Node, or Bun runtime dependency.
- The public command remains `/analyze-repo-for-kubernetes`.
- MCP server stdout contains only valid MCP messages; diagnostics go to stderr.
- A server process accepts exactly one active analysis and never persists state across process exit.
- Python replacement tools preserve root boundaries, reparse-point rejection, redaction, output limits, and failure semantics.
- A client is supported for stateful analysis only after a provider-free fresh-process, cross-process isolation, cleanup, initialize, and tool-schema smoke test passes.
- Existing TypeScript drafts and runtime files are preserved until their Python replacements pass parity and the terminal deletion gate.

---

### Task 1: Amend the accepted architecture and ticket contracts

**Files:**
- Modify: `docs/development/daily/2026-08-08/ADR-2026-08-08-004-analysis-pipeline-orchestration.md`
- Modify: `docs/development/tickets/PIPE-001-pipeline-state-and-validator.md`
- Modify: `docs/development/tickets/PIPE-002-session-tool-and-secure-snapshot.md`
- Modify: `docs/development/tickets/PIPE-003-stage-contract-injection-and-agent-migration.md`
- Modify: `docs/development/tickets/PIPE-004-runtime-finalizer-and-deterministic-renderer.md`
- Modify: `docs/development/tickets/PIPE-005-pipeline-acceptance-and-interactive-e2e.md`
- Modify: `docs/development/tickets/PIPE-006-terminal-skill-pruning.md`
- Test: `tests/test_development_contracts.py` (new focused assertions if the repository contract suite has no existing ticket-link checks)

**Interfaces:**
- Produces: consistent Python/MCP language, lifecycle, packaging, parity, and TypeScript-removal requirements for every later task.

- [ ] **Step 1: Write the failing documentation-contract test**

Assert that the active PIPE documents name Python MCP, the one-process/one-analysis boundary, and the TypeScript artifact deletion gate, and do not retain `context.sessionID` or `runtime/tools/analysis_pipeline.ts` as an acceptance requirement.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest tests.test_development_contracts -v`

Expected: FAIL because the accepted ADR and PIPE tickets still contain TypeScript and OpenCode custom-tool requirements.

- [ ] **Step 3: Amend the ADR and tickets**

Replace the runtime integration, session lifecycle, verification, and commit-boundary language with the approved Python MCP design. Add explicit cross-client smoke tests, offline package checks, parity inventory, and final artifact scans.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest tests.test_development_contracts -v`

Expected: PASS with no stale TypeScript or `context.sessionID` acceptance wording in PIPE-001 through PIPE-006.

- [ ] **Step 5: Commit the contract amendment**

```powershell
git add docs/development/daily/2026-08-08/ADR-2026-08-08-004-analysis-pipeline-orchestration.md docs/development/tickets/PIPE-001-pipeline-state-and-validator.md docs/development/tickets/PIPE-002-session-tool-and-secure-snapshot.md docs/development/tickets/PIPE-003-stage-contract-injection-and-agent-migration.md docs/development/tickets/PIPE-004-runtime-finalizer-and-deterministic-renderer.md docs/development/tickets/PIPE-005-pipeline-acceptance-and-interactive-e2e.md docs/development/tickets/PIPE-006-terminal-skill-pruning.md tests/test_development_contracts.py
git commit -m "docs: reframe pipeline contracts around Python MCP"
```

### Task 2: Implement the pure Python state model and validator

**Files:**
- Create: `runtime/python/analysis_pipeline/__init__.py`
- Create: `runtime/python/analysis_pipeline/state.py`
- Create: `runtime/python/analysis_pipeline/validation.py`
- Create: `runtime/python/analysis_pipeline/transitions.py`
- Create: `runtime/python/tests/__init__.py`
- Create: `runtime/python/tests/test_pipeline_state.py`

**Interfaces:**
- Produces: `create_state(binding)`, `submit(state, stage, payload, expected_revision, expected_hash)`, `reopen(state, target_stage, reason, expected_revision, expected_hash)`, `finalize(state, expected_revision, expected_hash)`, `canonical_json(value)`, and `derive_evidence_id(input)`.

- [ ] **Step 1: Write failing tests for canonical identity and six-stage transitions**

Cover stable canonical JSON/hash output, ordered six-stage submission, skipped and duplicate stages, stale revision/hash, cross-binding data, forged/unredacted evidence, malformed nested fields, unknown-claim absence data, mandatory-rule provenance, dangling graph/process/candidate/decision relations, duplicate membership, deployability/contract cardinality, premature finalization, and duplicate finalization.

- [ ] **Step 2: Run the focused Python tests to verify failure**

Run: `python -m unittest discover -s runtime/python/tests -p 'test_*.py' -v`

Expected: FAIL because the package and public functions do not exist.

- [ ] **Step 3: Implement the minimal immutable state and validator**

Use dataclasses or typed mappings with explicit stage payloads. Compute sorted-key canonical JSON and SHA-256 IDs. Return new state values for transitions; never mutate caller state or retain module-global state.

- [ ] **Step 4: Implement closed reopen invalidation and finalization**

Use an explicit permitted back-edge table. Reopening a stage removes that stage and all later outputs/evidence/catalog entries atomically, records the bounded reason, and increments the revision. Finalization requires all six outputs and all required rule applications, then clears only the process-private runtime state in the later MCP layer.

- [ ] **Step 5: Run the focused tests to verify green**

Run: `python -m unittest discover -s runtime/python/tests -p 'test_*.py' -v`

Expected: PASS for the complete vertical proof and every rejection contract.

- [ ] **Step 6: Commit the pure core**

```powershell
git add runtime/python/analysis_pipeline runtime/python/tests
git commit -m "feat: add Python pipeline state validator"
```

### Task 3: Package and expose the Python stdio MCP server

**Files:**
- Create: `runtime/python/analysis_pipeline/mcp_server.py`
- Create: `runtime/python/analysis_pipeline/protocol.py`
- Create: `runtime/python/pyproject.toml`
- Create: `runtime/python/requirements.lock`
- Create: `runtime/python/tests/test_mcp_server.py`
- Modify: `runtime/opencode.json`

**Interfaces:**
- Produces: explicit leading-word MCP tools (`start_analysis`, stage-specific
  `submit_*`, `reopen_analysis`, `finalize_analysis`, and grounded trusted
  evidence tools); one process-private active state; valid `initialize`,
  state-aware `tools/list`, and `tools/call` responses.

- [ ] **Step 1: Write failing protocol and lifecycle tests**

Feed newline-delimited MCP initialize and tool-call messages to the server entry point. Assert the advertised schema, stderr-only diagnostics, one active `start`, rejection of a second `start`, revision-bound submissions, finalization cleanup, and process exit with no state file.

- [ ] **Step 2: Run the focused server tests to verify failure**

Run: `python -m unittest runtime.python.tests.test_mcp_server -v`

Expected: FAIL because the MCP server and package metadata do not exist.

- [ ] **Step 3: Add the pinned offline package contract**

Declare Python 3.13, resolve the official Python MCP SDK, record exact versions and hashes in `requirements.lock`, record wheelhouse provenance, and add a clean virtual-environment install test using `--no-index` against that wheelhouse.

- [ ] **Step 4: Implement the stdio server and process lifecycle**

Use the pinned MCP SDK. Route all protocol output through the SDK, send logs to stderr, dispatch only the four pipeline actions, reject a second active analysis, clear state after finalization, and never serialize raw target content or secrets.

- [ ] **Step 5: Configure an isolated local server launch**

Add the Python launcher and MCP server entry to `runtime/opencode.json` without adding a TypeScript custom tool. Keep the existing public command and permission intent while routing analysis calls through the MCP server.

- [ ] **Step 6: Run server and offline-install tests**

Run: `python -m unittest runtime.python.tests.test_mcp_server -v`

Expected: PASS, including initialize/schema, one-process lifecycle, stderr-only output, cleanup, and offline installation checks.

- [ ] **Step 7: Commit the MCP boundary**

```powershell
git add runtime/python runtime/opencode.json
git commit -m "feat: expose pipeline through Python MCP"
```

### Task 4: Migrate trusted repository tools with security parity

**Files:**
- Create: `runtime/python/analysis_pipeline/tools/read.py`
- Create: `runtime/python/analysis_pipeline/tools/glob.py`
- Create: `runtime/python/analysis_pipeline/tools/git_metadata.py`
- Create: `runtime/python/analysis_pipeline/tools/locate_evidence.py`
- Create: `runtime/python/analysis_pipeline/tools/safe_paths.py`
- Create: `runtime/python/tests/test_tool_parity.py`
- Modify: `runtime/python/analysis_pipeline/mcp_server.py`

**Interfaces:**
- Produces: MCP tools with the existing trusted tool names and equivalent input/output schemas, redaction, root-boundary enforcement, output limits, and failure semantics.

- [ ] **Step 1: Inventory existing contracts and write golden parity tests**

Extract the current TypeScript tool schemas and behavior into literal Python fixtures. Test normal reads, glob scope, Git metadata failures, unique evidence location, credential-shaped content redaction, output limits, traversal, symlink/junction, and Windows reparse-point rejection.

- [ ] **Step 2: Run parity tests to verify failure**

Run: `python -m unittest runtime.python.tests.test_tool_parity -v`

Expected: FAIL because the Python tools do not exist.

- [ ] **Step 3: Implement safe path and redaction primitives**

Resolve the trusted root and candidate, reject escapes and reparse points, open only verified regular files, redact credential-shaped values before returning content, and enforce deterministic output limits.

- [ ] **Step 4: Implement each Python tool and register it with MCP**

Port behavior one tool at a time; keep raw repository content out of persistent pipeline state and send operational errors to stderr while returning structured tool errors.

- [ ] **Step 5: Run parity and security tests**

Run: `python -m unittest runtime.python.tests.test_tool_parity -v`

Expected: PASS for golden behavior and malicious-path/secret cases.

- [ ] **Step 6: Commit the trusted-tool migration**

```powershell
git add runtime/python/analysis_pipeline/tools runtime/python/tests/test_tool_parity.py runtime/python/analysis_pipeline/mcp_server.py
git commit -m "feat: migrate trusted repository tools to Python MCP"
```

### Task 5: Migrate client configuration, agent routing, packaging, and acceptance

**Files:**
- Modify: `runtime/opencode.json`
- Modify: `runtime/agents/kubernetes-migration-analyzer.md`
- Modify: `scripts/build_dist.py`
- Modify: `scripts/install-opencode.sh`
- Modify: `scripts/run_opencode_acceptance.py`
- Create: `runtime/config/claude-code.mcp.json`
- Create: `runtime/config/gemini-cli.mcp.json`
- Create: `tests/test_python_mcp_distribution.py`
- Create: `tests/test_client_mcp_smoke.py`

**Interfaces:**
- Produces: installed Python MCP artifacts and OpenCode, Claude Code, and Gemini CLI configuration templates with matching tool names, paths, permissions, and environment handling.

- [ ] **Step 1: Write failing distribution and client smoke tests**

Assert the built artifact contains the Python package, lock file, launcher, and config templates; contains no TypeScript analysis tool; and each client can launch a provider-free server, complete initialize/tools-list, return stderr-only diagnostics, and clean up after finalize.

- [ ] **Step 2: Run distribution and smoke tests to verify failure**

Run: `python -m unittest tests.test_python_mcp_distribution tests.test_client_mcp_smoke -v`

Expected: FAIL because build/install paths still copy TypeScript runtime tools and no Python client templates exist.

- [ ] **Step 3: Update distribution and acceptance harness**

Copy the Python package and locked dependencies into isolated acceptance homes, launch the server with platform-correct absolute paths, preserve target read-only boundaries, and capture MCP receipts alongside existing report artifacts.

- [ ] **Step 4: Update Agent and permission routing**

Route the public command to MCP tools, remove direct TypeScript tool names and `context.sessionID` instructions, and keep Korean user-facing report requirements unchanged.

- [ ] **Step 5: Run all provider-free gates**

Run: `python -m unittest tests.test_python_mcp_distribution tests.test_client_mcp_smoke -v`

Expected: PASS for artifact composition, all three client templates, absolute-path handling, tool schemas, cleanup, and unchanged target status.

- [ ] **Step 6: Commit client and packaging migration**

```powershell
git add runtime scripts tests/test_python_mcp_distribution.py tests/test_client_mcp_smoke.py
git commit -m "feat: route agent clients through Python MCP"
```

### Task 6: Remove legacy TypeScript runtime and prove the terminal boundary

**Files:**
- Delete: `runtime/tools/read.ts`
- Delete: `runtime/tools/glob.ts`
- Delete: `runtime/tools/git_metadata.ts`
- Delete: `runtime/tools/locate_evidence.ts`
- Delete: `runtime/lib/safe-path.ts`
- Delete: `runtime/lib/locate-evidence.ts`
- Modify: `scripts/build_dist.py`
- Modify: `scripts/install-opencode.sh`
- Modify: `scripts/run_opencode_acceptance.py`
- Create: `tests/test_no_legacy_typescript_runtime.py`
- Modify: `docs/development/tickets/PIPE-006-terminal-skill-pruning.md`

**Interfaces:**
- Produces: a distribution and source tree with no supported analysis path that references TypeScript, JavaScript, Node, or Bun runtime artifacts.

- [ ] **Step 1: Write the failing terminal deletion test**

Scan source, distribution allowlists, launchers, client templates, config, imports, and acceptance copy rules for `.ts`, `.js`, Node, and Bun references in the delivered analysis path. Assert that each migrated tool remains registered through Python MCP.

- [ ] **Step 2: Run the terminal test to verify failure**

Run: `python -m unittest tests.test_no_legacy_typescript_runtime -v`

Expected: FAIL while the legacy TypeScript tools and references remain.

- [ ] **Step 3: Delete only proven-redundant TypeScript runtime artifacts**

Remove the listed files after Tasks 4 and 5 pass parity and client smoke gates. Keep unrelated historical documentation until its deletion-test record proves it is safe to remove.

- [ ] **Step 4: Run the terminal test and full quality gate**

Run: `python -m unittest tests.test_no_legacy_typescript_runtime -v`

Expected: PASS with zero delivered runtime references to TypeScript, JavaScript, Node, or Bun.

Run: `python scripts/run_quality_gate.py`

Expected: PASS with the Python MCP package and all existing report-contract tests green.

- [ ] **Step 5: Commit the terminal removal**

```powershell
git add runtime scripts tests/test_no_legacy_typescript_runtime.py docs/development/tickets/PIPE-006-terminal-skill-pruning.md
git commit -m "chore: remove legacy TypeScript analysis runtime"
```
