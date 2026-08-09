# Static MCP and Progressive Stage Skills Design

- Status: Approved
- Date: 2026-08-09
- Decision source: user-approved design discussion and GPT-5.6-sol high review
- Supersedes: the uncommitted Python-owned model-runner plan for this milestone
- Related: ADR-2026-08-08-004, ADR-2026-08-08-008, PIPE-001 through PIPE-006

## Goal

Deliver a Python-only, read-only repository-analysis workflow that is portable
across MCP clients without depending on dynamic MCP tool catalogs. The workflow
must keep procedural context small by loading only the current stage Skill and
its references, while the Python server remains the authority for target
binding, evidence, state transitions, validation, and deterministic reporting.

## Scope

The first milestone supports OpenCode 1.18.14 with detached-PTY interactive
E2E. Claude Code and Gemini CLI receive the same stdio server configuration and
provider-free initialize/schema/cleanup smoke tests.

The user invokes one dispatcher command, `/analyze-repo-for-kubernetes`.
The dispatcher accepts an explicit Local Git repository path or a path relative
to the current directory, plus Summary or Detailed mode. Users can analyze
repositories outside the Skill worktree.

## Non-goals

- Hiding every future tool or Skill identifier from the model.
- A Python-owned LLM loop, a separate agent runtime, or Google ADK.
- Dynamic `tools/list`, `notifications/tools/list_changed`, or host-specific
  tool refresh behavior.
- Persistent sessions, resume/replay support, multi-user coordination, an
  audit database, or cryptographic receipt infrastructure.
- Writing, building, installing dependencies, or otherwise changing the
  analyzed repository.

## Terminology and isolation guarantee

This design provides **progressive procedural disclosure**, not a secrecy or
security boundary. OpenCode may advertise permitted Skill IDs/descriptions and
the conversation retains earlier messages. The design guarantees only that a
stage Skill body and its reference contents are loaded after the preceding
server transition succeeds, not before.

The trusted boundary is the Python server. A model cannot use an out-of-order
tool call, a forged evidence reference, or an unvalidated report claim to
change accepted pipeline state.

## Architecture

```text
User
  -> /analyze-repo-for-kubernetes dispatcher Skill
  -> static Python stdio MCP server
  -> start_analysis(target_path, mode)
  -> success handoff
  -> current model-invoked stage Skill
  -> trusted evidence tools + submit_current-stage tool
  -> success handoff
  -> next stage Skill
  -> ...
  -> finalize_analysis
  -> deterministic Markdown
  -> dispatcher/Agent relays Markdown unchanged
```

The MCP catalog is fixed for the lifetime of each connection. Catalog
visibility and state validity are separate: a listed tool may be invalid in the
current state and then returns a tool-level structured error without changing
state.

## Static MCP contract

The server exposes these tools from its first `tools/list` response:

```text
start_analysis
read_evidence
list_target_paths
locate_evidence
get_target_git_metadata
submit_discovery
submit_execution
submit_relationships
submit_boundaries
submit_contracts
reopen_analysis
finalize_analysis
```

`tools.listChanged` is not advertised and the server never emits
`notifications/tools/list_changed`.

All tool results define `outputSchema`, return matching `structuredContent`,
and include a bounded text fallback. Invalid business/state calls use
`CallToolResult.isError=true` with stable `code`, `retryable`, and bounded
current-input `issues`. Unknown tools and malformed JSON-RPC remain protocol
errors.

### Start and target binding

`start_analysis` receives:

```json
{
  "target_path": "absolute path or path relative to the command directory",
  "mode": "summary | detailed"
}
```

The dispatcher forwards only a path selected in the user request. The server
resolves the path, requires a Local Git repository, rejects non-directories,
Skill-installation paths, repository-escaping links, and unsafe special roots,
then records the resolved realpath, selected subdirectory, Git revision, and
content snapshot. All subsequent evidence calls operate under that exact
binding. A changed snapshot rejects further state-changing calls.

### State machine

```text
IDLE
  -> discovery
  -> execution
  -> relationships
  -> boundaries
  -> contracts
  -> READY_TO_FINALIZE
  -> IDLE
```

The process retains only one active analysis. `start_analysis` is valid only
in `IDLE`; evidence tools require an active analysis; each `submit_*` is valid
only in its exact current stage; `reopen_analysis` accepts an earlier accepted
stage and invalidates that stage plus later outputs; and `finalize_analysis` is
valid only in `READY_TO_FINALIZE`.

State is in memory. Successful transitions rotate a server-issued transition
token and increment revision. Failed transitions preserve revision, token, and
state. After finalization, or after process exit, no recovery/resume exists; a
new analysis begins from `start_analysis`.

### Evidence and submission

Evidence tools issue server-owned `observation_ref` values. A stage submission
may cite only current, trusted observations. On acceptance, the server
normalizes stage facts and promotes reusable evidence to immutable `fact_ref`
values. A later stage receives fact references, not raw evidence or an earlier
stage's temporary observation handle.

Every `submit_*` accepts a small common envelope:

```json
{
  "analysis_id": "an_server_issued",
  "revision": 2,
  "transition_token": "tr_server_issued",
  "payload": {}
}
```

The server selects and applies the exact internal closed schema for the named
stage. The stage Skill carries the current payload contract; the global MCP
catalog does not repeat every future schema.

### Success handoff

A successful start or submit returns a server-generated, redacted projection:

```json
{
  "status": "accepted",
  "analysis_id": "an_server_issued",
  "completed_stage": "discovery",
  "revision": 2,
  "transition_token": "tr_server_issued",
  "next_skill": "analyze-k8s-execution",
  "stage_input": {
    "candidate_ids": ["candidate_web"],
    "accepted_fact_refs": ["fact_server_issued"],
    "unknown_ids": ["unknown_start_command"]
  }
}
```

`stage_input` contains only values required by the next stage. It excludes raw
evidence text, secret values, absolute target path, full state, the workflow,
future Skill bodies, and future reference lists. Failure results never name a
next Skill.

## Skill package

The package has one user-invoked dispatcher and six model-invoked Skills:

```text
analyze-repo-for-kubernetes
analyze-k8s-discovery
analyze-k8s-execution
analyze-k8s-relationships
analyze-k8s-boundaries
analyze-k8s-contracts
analyze-k8s-finalize
```

The dispatcher owns only:

- help and unrelated-request routing;
- user-selected target and mode forwarding;
- read-only and Korean-output policy;
- `start_analysis`;
- exact loading of the `next_skill` provided by a successful handoff; and
- unchanged relay of final Markdown.

It does not contain a stage procedure, a report template, or a complete
reference inventory.

Each stage Skill owns exactly:

1. its immediate objective;
2. its allowed MCP tools;
3. the incoming `stage_input` fields it may use;
4. its named reference files; and
5. its completion criteria and `submit_*` call.

Stage procedures and tool descriptions use leading words already established in
the repository: `Vertical Slice`, `Grounding`, `Workload Boundary`, `Gap
Analysis`, and `Quality Gate`. Tool descriptions begin with concrete actions:
`Start`, `Read`, `List`, `Locate`, `Get`, `Submit`, `Reopen`, and `Finalize`.

A Skill does not independently choose its successor. After a successful submit
it loads precisely `handoff.next_skill`; on a failure it repairs only current
input from fresh trusted evidence. If the named Skill cannot load, it reports
the error and stops.

References are separate files. Stage Skills reference only the rules/templates
needed by their immediate objective. Repository contents are read only through
MCP evidence tools; references are read from the installed Skill package.
Normative rules have one validator owner and are not duplicated as competing
prose in the Skill body.

## Deterministic finalization

`submit_contracts` closes every report-required slot with accepted facts,
evidence references, or scoped unknowns. The final Skill calls
`finalize_analysis` using the current analysis ID, revision, and token. It
does not draft a second report JSON or Markdown document.

The server finalizes in this order:

```text
recheck target snapshot
-> validate accepted state and fact references
-> project mode-specific report JSON
-> validate existing JSON schema
-> render with existing Summary/Detailed renderer
-> validate Markdown contract and redaction
-> return Markdown and small completion metadata
-> clear active state
```

The MCP `content` contains the canonical Markdown. `structuredContent`
contains status, analysis ID, mode, and revision. The Agent relays only the
Markdown content without a further model-authored report turn.

## Safety

The server rejects traversal, symlink/junction escape, stale token/revision,
cross-analysis or cross-stage observations, target mutation, malformed
payloads, secret-bearing state, and output-limit violations. It redacts
credential-shaped content before it reaches a tool response, stage state,
handoff, error, or final Markdown.

`get_target_git_metadata` is retained only if a stage requires it. It is a
delete-test candidate because finalization already owns target revision
metadata.

## Verification

Deterministic tests prove:

- a connection's tool names/schemas remain static and no list-change
  notification occurs;
- all legal and illegal state transitions, token rotation, failure
  immutability, and reopen invalidation;
- target path validation, snapshot mutation detection, traversal, and
  symlink/junction containment;
- trusted observation/fact lifetimes, forged/stale/cross-stage rejection,
  redaction, and output limits;
- handoff projections have required next-stage input and exclude raw evidence,
  secrets, full state, and future references;
- `outputSchema`, `structuredContent`, text fallback, stdout purity, and
  `isError` semantics;
- accepted state projects byte-identical Summary/Detailed Markdown that meets
  existing report contracts; and
- each stage Skill/reference exists, names only its allowed tools, does not
  embed another stage procedure, and matches the validator-owned rule IDs.

OpenCode acceptance uses a detached `tmux` PTY, an isolated temporary Skill
installation, isolated `HOME` and `OPENCODE_CONFIG_DIR`, `runtime/opencode.json`,
`tmux send-keys`, `tmux capture-pane`, and target Git status before/after.
It verifies the dispatcher-to-handoff Skill sequence, static initial catalog,
final Markdown equality with server output, absence of tool errors and secrets,
and target immutability. Summary and Detailed results are scored separately
against frozen mode-specific golden evidence for Flask/Celery, JPetStore-6, and
FastAPI.

Claude Code and Gemini CLI receive provider-free configuration/launch,
`initialize`, static catalog/schema, stderr-only, target-binding, and cleanup
smoke tests. They are not first-milestone model-backed E2E gates.

## Delete tests

Every procedural sentence and model-facing field is subject to a delete test.
Remove one candidate from an isolated package, rerun the targeted behavior
case, and retain it only when removal breaks a named invariant, reference
mapping, or report finding.

The package validator must fail for a removed declared stage Skill/reference,
an orphaned rule ID, or an allowed-tool mismatch. The distribution scan must
fail if it contains dynamic catalog behavior, Python-owned provider loop,
model-profile runtime, external audit sink, persistent store, duplicated report
template, or dispatcher-owned stage procedure. Surfaces with no failing
invariant after removal, including optional metadata tools, must be removed.

## Ticket-slicing rule

The implementation plan must use independently testable Vertical Slices.
Every ticket must include the smallest end-to-end behavior that a reviewer can
accept or reject, its deterministic test, its affected Skill/MCP/core boundary,
and its focused commit. Do not create tickets merely by file type or technical
layer. Documentation reconciliation is the prerequisite ticket; later slices
must leave the static tool contract and prior accepted behavior working.
