# ADR-2026-08-08-004: Make repository analysis a trusted staged pipeline

- Status: Superseded in implementation detail by the approved Python MCP design
- Date: 2026-08-08
- Supersedes: the implementation mechanism proposed by [VS-028](../../tickets/VS-028-prose-only-process-discovery.md)
- Related: [analysis pipeline handoff](../../current/analysis-pipeline-handoff-2026-08-08.md), ADR-2026-08-07-001, ADR-2026-08-07-002

## Context

VS-028's repeated Flask/Celery runs showed that prompt-only staging does not
mechanically load required references, preserve ordered evidence, or guarantee
a final report. The public report schema is intentionally permissive and cannot
by itself validate stage order, evidence ownership, boundary coverage, or
revision integrity.

The accepted milestone design replaces the previously discussed TypeScript and
custom-tool path with a Python MCP server. That revision keeps the trusted
staged pipeline decision while changing the runtime packaging, lifecycle, and
client-compatibility requirements.

## Decision

Keep one public command, `/analyze-repo-for-kubernetes`, and replace the
prompt-directed workflow with one trusted `analysis_pipeline` tool exposed by a
local Python MCP stdio server. Its only actions remain `start`, `submit`,
`reopen`, and `finalize`. Internal stages are not public commands:

```text
discovery -> execution -> relationships -> boundaries -> contracts -> finalize
```

`start` returns the active stage's canonical instruction and closed submission
schema. The server, not the model, loads those assets from a verified installed
Skill bundle. `submit` accepts only the current stage at the current state
revision. A justified `reopen` returns to the earliest affected prior stage and
atomically invalidates all later outputs and derived evidence. Only `finalize`
can project validated pipeline state into the existing public report schema and
produce canonical deterministic Markdown plus a receipt.

The Agent may relay the Markdown returned by `finalize`, but a report is
accepted only when the final response matches that receipt and content hash.
Free-form Agent JSON or Markdown is not a completed analysis.

## State and deterministic identity

Pipeline state is private to one MCP server-process instance and is stored
outside the analyzed repository. It has three internal groups:

```text
binding: target_realpath, target_snapshot_hash, skill_manifest_hash
control: current_stage, state_revision, state_hash, finalized
data: evidence_registry, rule_application_registry, stage_outputs
```

All identity and control values are server-computed. A server accepts exactly
one active analysis. The binding is the target real path, target snapshot hash,
and installed-skill manifest hash; no model-supplied identifier participates in
state identity. `state_revision` advances monotonically after each accepted
transition. `state_hash` is SHA-256 over the redacted state serialized with a
defined canonical JSON encoding. Evidence IDs are derived from snapshot
identity, normalized location/range, claim status, and redacted content
fingerprint.

The implementation must not copy raw repository content into persistent
pipeline state. Each target read opens a verified regular-file handle beneath
the resolved target, rechecks that handle's identity before use, records its
content hash, and rejects reparse points or paths outside the target. Before
finalization the server recomputes the target Merkle digest and verifies every
evidence-file hash. Any mismatch fails the analysis instead of emitting a
report. Evidence registry entries retain only IDs, relative locations, ranges,
content fingerprints, and redacted classifications; raw snippets, secret
literals, and unredacted error text are prohibited in state, traces, and
payloads.

## Pipeline contracts and invariants

The implementation uses a new internal closed schema rather than
`schemas/analysis-result.schema.json`. It models discovery signals and their
dispositions, processes, runtime graph edges, operational units, and one
runtime contract per deployable unit. Every evidence-bearing claim has one of
`confirmed`, `inferred`, `unknown`, `conflicted`, or `not_applicable` status.
An `unknown` claim must name its search scope, absence evidence, and blocked
decision.

Every mandatory reference rule used by a stage has a manifest-versioned
`rule_id`. The rule-application registry links `rule_id` to the target evidence
IDs it governs, the process or candidate IDs affected, and the boundary or
readiness decision ID that consumes it. A required rule cannot be marked
complete merely because its file was read; it must have a valid application, or
a scoped target absence linked to the same rule and process.

The validator rejects skipped, duplicate, stale, cross-binding,
cross-snapshot, and cross-manifest submissions. It also rejects unresolved
signal or process coverage, dangling graph IDs, duplicate unit membership,
contracts for non-deployable units, missing or duplicate contracts for
deployable units, forged evidence IDs, secret-bearing state, and premature or
repeated finalization. Finalization is a pure projection: it cannot discover
evidence or change pipeline state other than marking the receipt final.

Execution duration (`continuous`, `one_shot`, `scheduled`) is distinct from
operational independence. Process existence, repository role, deployability,
and operational-management boundary are separate fields. This preserves an
unresolved boundary when evidence is insufficient instead of inventing a merge
or split.

## Runtime integration

The runtime package lives under `runtime/python/` and owns state, validation,
transitions, rendering, and MCP exposure in one language. `mcp_server.py` is
the only transport boundary and must speak valid stdio MCP JSON-RPC: requests
from stdin, responses to stdout, diagnostics to stderr only. The server uses a
pinned Python MCP dependency with an offline-reproducible installation path for
supported clients.

MCP does not guarantee a trustworthy host session token for all clients, so the
supported lifecycle boundary is one fresh MCP process per interactive analysis
session and one active analysis per process. `finalize` must clear state before
returning control; process exit must leave no analysis state to reuse. No
client may substitute a model-supplied identifier for this lifecycle boundary.

The legacy TypeScript runtime remains only until Python replacements pass parity
and security checks. Terminal deletion work must prove that no supported
installation, launcher, configuration, acceptance harness, or artifact still
references `.ts`, `.js`, Node, or Bun runtime dependencies before removal.

## Consequences

- Required stages, instruction loading, state transitions, and report
  rendering become mechanically checked rather than voluntary Agent behavior.
- The implementation adds a stateful security boundary and therefore requires
  parity, offline-package, and cross-client smoke tests before provider-backed
  runs.
- More code and structured model or tool exchanges are acceptable: correctness
  and on-premise analysis quality take priority over token or latency savings.
- VS-028 remains evidence of the failed prose-only mechanism. Its prior
  always-load wording is not a solution for this architecture.

## Verification requirements

PIPE-001 runs only provider-free Python tests over state, validation, and
transitions. PIPE-002 adds Python MCP launch, initialize, tool-schema,
stderr-only diagnostics, offline package installation, and one-process/one-
analysis lifecycle checks. PIPE-003 proves parity and migration of trusted
tools plus client configuration templates for OpenCode, Claude Code, and Gemini
CLI. PIPE-004 proves deterministic rendering and receipt integrity. PIPE-005
proves ordered submissions, canonical report hashes, golden-set scoring,
cross-client smoke tests, and target immutability in detached `tmux`
interactive E2E runs. PIPE-006 removes legacy TypeScript artifacts only after a
terminal artifact scan proves they are no longer referenced.
