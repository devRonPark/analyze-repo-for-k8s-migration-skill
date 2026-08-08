# Trusted Observation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace model-authored evidence IDs with server-issued, stage-scoped observation references that can be submitted safely through the Python MCP pipeline.

**Architecture:** Trusted evidence tools issue opaque observations after safe-path resolution and redaction. The MCP server owns observations, transition tokens, snapshot checks, retry receipts, and payload normalization; the pure pipeline accepts only normalized canonical evidence. Each active `submit_*` tool exposes a closed stage-specific schema and never reveals a future stage.

**Tech Stack:** Python 3.13, standard library `unittest`, local stdio MCP JSON-RPC, existing Python trusted tools and detached OpenCode PTY acceptance procedure.

## Global Constraints

- The model must never supply canonical evidence IDs, source fingerprints, redaction flags, or evidence locations in a stage submission.
- A server process owns exactly one analysis, all observation references, transition tokens, and retry receipts; none survive process exit.
- Observation issuance, submission, reopen, and finalize revalidate target snapshot and safe source identity before accepting state.
- Stage contracts are closed JSON Schemas and use leading-word descriptions; a current-stage tool must not disclose a future-stage contract.
- `content` is always present; `structuredContent` is an object only. Diagnostics remain stderr-only.
- The analyzed target stays read-only. No TypeScript, JavaScript, Node, or Bun may enter the delivered runtime.

---

### Task 1: Define pure observation and normalized-submission values

**Files:**
- Modify: `runtime/python/analysis_pipeline/state.py`
- Modify: `runtime/python/analysis_pipeline/validation.py`
- Modify: `runtime/python/analysis_pipeline/transitions.py`
- Test: `runtime/python/tests/test_pipeline_state.py`

**Interfaces:**
- Produces: `Observation`, `normalize_submission_payload(payload, observations, binding)`, and a `submit()` input containing canonical evidence only after server normalization.
- Consumes: server-owned observations keyed by opaque reference and the existing immutable `PipelineState` transition API.

- [ ] **Step 1: Write failing normalization tests**

```python
def test_normalizes_local_aliases_to_server_derived_evidence_ids():
    normalized, evidence = normalize_submission_payload(
        discovery_payload_with_alias("docker", "obs_issued"),
        {"obs_issued": observation("Dockerfile", "17-21")},
        BINDING,
    )
    assert normalized["claims"][0]["evidence_ids"] == [next(iter(evidence))]
    assert "evidence_inputs" not in discovery_payload_with_alias("docker", "obs_issued")

def test_rejects_client_owned_evidence_fields():
    with self.assertRaisesRegex(ValueError, "client evidence"):
        normalize_submission_payload(payload_with("content_fingerprint"), OBSERVATIONS, BINDING)
```

- [ ] **Step 2: Run the focused test to verify failure**

Run: `python -m unittest runtime.python.tests.test_pipeline_state.PipelineStateTests.test_normalizes_local_aliases_to_server_derived_evidence_ids -v`

Expected: FAIL because the normalization API does not exist.

- [ ] **Step 3: Add closed client payload validation and atomic normalization**

Accept `schema_version`, `stage`, local `evidence` alias/reference pairs, claims with `evidence_aliases`, rules with `evidence_aliases`, and the current stage's identifiers. Restrict aliases and IDs to a documented ASCII pattern and bounded length. Resolve every alias from an immutable observation map, derive canonical evidence IDs from server-owned fields, rewrite aliases, then run existing canonical validation on a copy.

- [ ] **Step 4: Preserve accepted-state invariants**

Keep `PipelineState.outputs` and `PipelineState.evidence` in canonical form only. Reject duplicate aliases, duplicate observation use, undeclared aliases, unreferenced observations, and unknown claims without a server-issued scoped-absence observation. Ensure validation exceptions return before state replacement.

- [ ] **Step 5: Run the pure-core suite**

Run: `python -m unittest discover -s runtime/python/tests -p 'test_pipeline_state.py' -v`

Expected: PASS for current transition checks plus alias normalization and no-mutation failures.

- [ ] **Step 6: Commit the pure contract**

```powershell
git add runtime/python/analysis_pipeline/state.py runtime/python/analysis_pipeline/validation.py runtime/python/analysis_pipeline/transitions.py runtime/python/tests/test_pipeline_state.py
git commit -m "feat: normalize trusted observation submissions"
```

### Task 2: Add server-owned snapshots and observation registry

**Files:**
- Create: `runtime/python/analysis_pipeline/observations.py`
- Modify: `runtime/python/analysis_pipeline/mcp_server.py`
- Modify: `runtime/python/analysis_pipeline/tools/read.py`
- Modify: `runtime/python/analysis_pipeline/tools/locate_evidence.py`
- Test: `runtime/python/tests/test_observations.py`

**Interfaces:**
- Produces: `TargetSnapshot.capture(root)`, `ObservationRegistry.issue_present(...)`, `ObservationRegistry.issue_absence(...)`, `ObservationRegistry.resolve(ref, stage, snapshot)`, and `ObservationRegistry.invalidate_from(stage)`.
- Consumes: redacted safe-tool results and the server's process-private target root.

- [ ] **Step 1: Write failing registry tests**

```python
def test_tool_issued_observation_is_stage_bound_and_redacted():
    issued = registry.issue_present("discovery", safe_file, 17, 21, "token=[REDACTED]")
    assert issued["ref"].startswith("obs_")
    assert "token=" not in repr(registry.resolve(issued["ref"], "discovery", snapshot))

def test_changed_file_and_wrong_stage_invalidate_observation():
    ref = registry.issue_present("discovery", safe_file, 1, 1, "safe")
    mutate_file_for_test(safe_file)
    with self.assertRaisesRegex(ValueError, "snapshot|source changed"):
        registry.resolve(ref, "discovery", snapshot)
    with self.assertRaisesRegex(ValueError, "stage"):
        registry.resolve(ref, "execution", refreshed_snapshot)
```

- [ ] **Step 2: Run the registry test to verify failure**

Run: `python -m unittest runtime.python.tests.test_observations -v`

Expected: FAIL because observation registry and target snapshot classes do not exist.

- [ ] **Step 3: Implement target and file identity verification**

For Git targets record `HEAD` plus deterministic `git status --porcelain=v1` content; for non-Git targets record a sorted, bounded content manifest. Record each issued regular file's resolved safe path, stat identity, SHA-256 content hash, and redacted canonical text hash. Re-run safe-path resolution and identity checks before resolve, submit, reopen, and finalize.

- [ ] **Step 4: Issue observations only through trusted tools**

Make `read_evidence` return redacted text plus one present observation covering the returned line range. Make `locate_evidence` return a present observation for a match or an absence observation containing only server-owned scoped query metadata. Do not put secret literals in an observation, error, or receipt.

- [ ] **Step 5: Implement lifecycle invalidation**

Bind each reference to process binding, snapshot, and active stage. Invalidate observations from a reopened stage onward; clear all on successful finalization and process cleanup. Reject forged, expired, cross-stage, cross-server, and stale references.

- [ ] **Step 6: Run registry and tool regression tests**

Run: `python -m unittest runtime.python.tests.test_observations runtime.python.tests.test_mcp_server -v`

Expected: PASS, including redaction, source-change, symlink/reparse, absence, and invalidation cases.

- [ ] **Step 7: Commit the trusted evidence issuer**

```powershell
git add runtime/python/analysis_pipeline/observations.py runtime/python/analysis_pipeline/mcp_server.py runtime/python/analysis_pipeline/tools/read.py runtime/python/analysis_pipeline/tools/locate_evidence.py runtime/python/tests/test_observations.py
git commit -m "feat: issue trusted MCP observations"
```

### Task 3: Add transition tokens, receipts, and replay protection

**Files:**
- Modify: `runtime/python/analysis_pipeline/mcp_server.py`
- Modify: `runtime/python/analysis_pipeline/protocol.py`
- Test: `runtime/python/tests/test_mcp_server.py`

**Interfaces:**
- Produces: start and submit receipts with `transition_token`, `input_revision`, `output_revision`, `state_hash`, `canonical_evidence`, and `next_stage`.
- Consumes: normalized submission data and the active server registry.

- [ ] **Step 1: Write failing replay tests**

```python
def test_identical_submit_retry_returns_original_receipt():
    first = call_submit(server, token, payload)
    retry = call_submit(server, token, payload)
    self.assertEqual(retry, first)

def test_same_transition_token_with_other_payload_is_replay_conflict():
    call_submit(server, token, payload)
    self.assert_tool_error(call_submit(server, token, changed_payload), "replay conflict")
```

- [ ] **Step 2: Run the focused replay test to verify failure**

Run: `python -m unittest runtime.python.tests.test_mcp_server.MCPTests.test_identical_submit_retry_returns_original_receipt -v`

Expected: FAIL because receipts and token replay cache do not exist.

- [ ] **Step 3: Implement server-issued token handling**

Issue an opaque token at start and after each accepted transition. Hash a canonical normalized request for the active token. Cache only successful submit/finalize receipts in process memory. Return the cached receipt for an identical request and return a structured replay conflict for a different request. Do not cache rejected validation attempts.

- [ ] **Step 4: Implement finalization retry and cleanup**

Retain an in-memory completion tombstone only for one identical finalize retry. Invalidate state, observations, and normal transition tokens before returning the final receipt. A new start never observes the tombstone as active analysis state.

- [ ] **Step 5: Run MCP server tests**

Run: `python -m unittest runtime.python.tests.test_mcp_server -v`

Expected: PASS for token rotation, idempotent retry, replay conflict, rejected retry, finalization cleanup, and current catalog tests.

- [ ] **Step 6: Commit receipts and retry safety**

```powershell
git add runtime/python/analysis_pipeline/mcp_server.py runtime/python/analysis_pipeline/protocol.py runtime/python/tests/test_mcp_server.py
git commit -m "feat: add MCP transition receipts and retries"
```

### Task 4: Publish closed active-stage MCP schemas and agent routing

**Files:**
- Modify: `runtime/python/analysis_pipeline/protocol.py`
- Modify: `runtime/python/analysis_pipeline/mcp_server.py`
- Modify: `runtime/agents/kubernetes-migration-analyzer.md`
- Test: `runtime/python/tests/test_mcp_server.py`
- Test: `tests/test_opencode_adapter.py`

**Interfaces:**
- Produces: one `submit_<stage>` JSON schema with `additionalProperties: false` at every nested object, the current transition token requirement, and a leading-word usage description.
- Consumes: the active stage from process-private state.

- [ ] **Step 1: Write failing catalog/schema tests**

```python
def test_discovery_schema_exposes_observation_aliases_but_not_execution():
    start(server)
    discovery = tool_by_name(tools_list(server), "submit_discovery")
    self.assertTrue(discovery["inputSchema"]["additionalProperties"] is False)
    self.assertIn("observation_ref", json.dumps(discovery))
    self.assertNotIn("submit_execution", tool_names(tools_list(server)))
```

- [ ] **Step 2: Run focused schema tests to verify failure**

Run: `python -m unittest runtime.python.tests.test_mcp_server.MCPTests.test_discovery_schema_exposes_observation_aliases_but_not_execution -v`

Expected: FAIL because the payload schema is currently an unrestricted object.

- [ ] **Step 3: Implement stage-specific schema factories**

Generate only the active stage tool with closed outer and nested schemas. Include `transition_token` and the exact current stage payload fields. Use descriptions beginning `Submit ...` and state when an issued observation is required. Never expose evidence IDs, fingerprints, redaction flags, future schemas, or future stage names.

- [ ] **Step 4: Replace contradictory agent instructions**

Make the agent call `start_analysis` with `{}`, use only active MCP tools, preserve tool-issued references, and refuse a final answer before successful `finalize_analysis`. Remove superseded direct-tool and JSON-finalizer instructions. Require the final assistant response to be Markdown headed `Kubernetes 설계 입력 요약`.

- [ ] **Step 5: Run schema and adapter checks**

Run: `python -m unittest runtime.python.tests.test_mcp_server tests.test_opencode_adapter -v`

Expected: PASS with active-only schemas and no legacy direct-tool or conflicting final-output instruction.

- [ ] **Step 6: Commit active-stage interface routing**

```powershell
git add runtime/python/analysis_pipeline/protocol.py runtime/python/analysis_pipeline/mcp_server.py runtime/agents/kubernetes-migration-analyzer.md runtime/python/tests/test_mcp_server.py tests/test_opencode_adapter.py
git commit -m "feat: publish closed observation stage schemas"
```

### Task 5: Provider-free integration and interactive acceptance

**Files:**
- Modify: `scripts/mcp_smoke.py`
- Modify: `scripts/run_opencode_acceptance.py` only if required for final-report capture
- Create: `tests/test_observation_mcp_integration.py`
- Modify: `memory/opencode-e2e.md` with the corrected Windows forward-slash and OpenCode 1.x configuration notes if they are still absent

**Interfaces:**
- Produces: a reproducible provider-free observation/submit/retry lifecycle proof and an interactive E2E procedure that checks final report contract and target cleanliness.

- [ ] **Step 1: Write failing end-to-end protocol test**

```python
def test_server_accepts_tool_issued_observation_through_discovery():
    session = launch_mcp_at(git_fixture)
    receipt = session.start()
    observation = session.read("Dockerfile")["observation"]
    next_receipt = session.submit_discovery(receipt["transition_token"], payload_using(observation))
    self.assertEqual(next_receipt["next_stage"], "execution")
```

- [ ] **Step 2: Run the integration test to verify failure**

Run: `python -m unittest tests.test_observation_mcp_integration -v`

Expected: FAIL until all server-bound observations, schemas, and receipts are connected.

- [ ] **Step 3: Extend the provider-free smoke script**

Exercise initialize, current catalog, start, issued observation, alias submission, receipt retry, replay conflict, next-stage catalog, and finalize cleanup. Assert stdout contains only JSON-RPC and stderr is empty.

- [ ] **Step 4: Run all deterministic gates**

Run: `python -m unittest discover -s runtime/python/tests -p 'test_*.py'`

Expected: PASS.

Run: `python -m unittest tests.test_observation_mcp_integration tests.test_opencode_adapter -v`

Expected: PASS.

Run: `python scripts/mcp_smoke.py; python scripts/verify_python_runtime.py; git diff --check`

Expected: all commands PASS with no diff whitespace errors.

- [ ] **Step 5: Run detached OpenCode E2E after deterministic green**

Build the Skill into an ASCII-path isolated acceptance directory, configure forward-slash Python and launcher paths, use OpenCode 1.x `mcp.analysis.enabled: true`, start a detached tmux-compatible PTY in the read-only target, and send `/analyze-repo-for-kubernetes`. Capture the final response and require the exact Markdown heading `Kubernetes 설계 입력 요약`, no tool errors, successful finalization, and identical pre/post target Git status. Run JPetStore 6 first, then two additional pinned repositories only after JPetStore passes.

- [ ] **Step 6: Commit integration coverage**

```powershell
git add scripts/mcp_smoke.py scripts/run_opencode_acceptance.py tests/test_observation_mcp_integration.py memory/opencode-e2e.md
git commit -m "test: verify trusted observation MCP lifecycle"
```

## Plan Self-Review

- Spec coverage: Tasks 1-5 cover aliases, trusted issuance, snapshots, redaction, stage isolation, replay safety, closed schemas, agent conflict removal, deterministic tests, and interactive OpenCode E2E.
- Placeholder scan: no deferred implementation markers are present; every task names files, interfaces, assertions, commands, and a focused commit.
- Type consistency: observations and tokens are created only at the server boundary; pure state receives normalized canonical evidence, and later tasks consume the same receipt names.

## Review Amendment — Mandatory Before Implementation

This amendment supersedes conflicting steps above and records the independent
high-reasoning plan review. The following changes are implementation gates.

### Task 0: Repair terminal state and report-delivery boundary

Before Task 1, write RED tests proving that five submitted stages
(`discovery`, `execution`, `relationships`, `boundaries`, `contracts`) move the
state to terminal `finalize`, and that `finalize_analysis` succeeds without a
nonexistent `submit_finalize` tool. Refactor `state.py` to define
`ANALYSIS_STAGES` separately from `FINAL_STAGE`; make terminal validation
require exactly the five submitted outputs. Keep `tools/list` after contracts
limited to `finalize_analysis`, `reopen_analysis`, and trusted evidence tools.

Direct interactive Markdown is required by the repository E2E policy but
conflicts with the current JSON-first ADR and tests. In this same task, amend
the JSON-first ADR, agent, renderer/harness, adapter tests, and report-contract
tests together. The final OpenCode assistant response must be validated
Markdown headed `Kubernetes 설계 입력 요약` only after finalization; no external
uninvoked finalizer may be an acceptance dependency. Commit this boundary
before the observation work.

### Strengthened Task 2: fail-closed snapshot and atomic evidence read

Replace the earlier `HEAD + git status` proposal. A Git snapshot records HEAD,
index blob identity, and the normalized type/content hash of every dirty or
untracked entry. Disable untrusted fsmonitor and hooks for all Git queries. A
manifest larger than its declared bound fails start rather than omitting an
entry. A non-Git target uses the same complete fail-closed manifest rule.

For evidence files, use one verified open handle: verify every path component
has not become a symlink or reparse point, `fstat`, read bytes, `fstat` again,
redact, and issue both displayed content and the observation from those exact
bytes. Revalidate target and file identity on resolve, submit, reopen, and
finalize. Add separate tests for an already-dirty file whose content changes,
symlink/junction replacement, and source change between observation and
submission.

Task 2 must also modify `runtime-files.txt` for `observations.py` and add a
built-distribution launcher/import test. Source-only tests do not satisfy this
gate.

### Strengthened Task 3: universal replay ledger

Apply transition tokens and idempotent receipts to submit, reopen, and
finalize. Check the replay ledger before active-stage visibility so an
identical retry works after catalog advancement. A rejected request changes
neither state, revision, token, nor observation-consumed status. One alias may
support many claims or rules; duplicate aliases and duplicate declaration of a
single observation fail, while exploratory unsubmitted observations remain
allowed.

### Strengthened Task 4: complete client contract

Each active tool schema must recursively set `additionalProperties: false` and
declare every required/optional field, enum, pattern, and length/cardinality
bound. Empty process, edge, unit, or contract results are valid only with a
server-issued scoped-absence observation; never require fabricated IDs.
`structuredContent`, when present, is an object. Return domain validation and
replay failures as MCP tool errors with structured code/path; reserve JSON-RPC
errors for malformed protocol requests. Test that start receipts do not expose
future rule catalogs and that static SKILL/agent text does not describe future
stages.

### Strengthened Task 5: required three-repository evidence protocol

For JPetStore 6, `miguelgrinberg/flask-celery-example`, and
`tiangolo/full-stack-fastapi-template`, make a static independent golden set
before loading the Skill or starting OpenCode. Each records target path,
immutable revision, evidence date, required Summary findings, blockers,
unknowns, and weighted scorecard. Preserve pre/post Git status, final assistant
response, finalization receipt, and catalog-refresh trace. Score only the
captured final response. A tool error, absent finalization, invalid heading, or
target change fails that target. Run JPetStore first and proceed only after it
passes.

### Revised completion gate

Run all pure and MCP tests, `tests/test_repository_distribution.py`, adapter
and report-contract suites, `scripts/mcp_smoke.py`,
`scripts/verify_python_runtime.py`, `scripts/run_quality_gate.py`, and a built
distribution launcher smoke before any provider-backed run. The detached PTY
E2E must then prove all active catalog transitions and a clean final report for
all three golden-scored repositories.

### Final review amendment: dependency, rules, and full stdio proof

Before Task 0, amend the approved design contract to state: "The stdlib-only
MCP protocol boundary supersedes the pinned-SDK and handwritten-JSON-RPC
prohibition in the approved design. Protocol conformance is enforced by
initialize, tools/list, tools/call, list-changed notification, tool-error,
stdout purity, and OpenCode 1.18 integration tests." Do not introduce an MCP
SDK or a Node/Bun bridge.

Task 4 must add manifest-hashed stage contract and rule assets to the installed
Skill, `runtime-files.txt`, and built-distribution tests. The server holds the
full catalog privately; its start receipt and all static Skill/agent text omit
future stages and rules. The active tool's closed schema and leading-word
description expose only the current instruction and applicable `rule_id`s.
Missing required current-stage rule applications reject submission, and
finalization checks the full internal rule provenance. Add canary tests proving
that start, failure, reopen, static Skill/agent, and distribution files contain
no future rule or stage leakage.

Replace Task 5's first protocol example with a complete provider-free stdio
proof: issue fresh stage-scoped observations and submit all five stages,
exercise one permitted reopen and resubmission, finalize, retry finalization,
assert the active-only catalog after every transition, then launch a fresh MCP
process and prove cleanup. Add a credential-shaped client `glob` or `pattern`
input test proving it is bounded, redacted before any persisted absence record,
and never echoed in state, output, error, or diagnostics.
