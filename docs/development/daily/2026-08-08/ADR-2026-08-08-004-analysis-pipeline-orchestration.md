# ADR-2026-08-08-004: Make repository analysis a trusted staged pipeline

- Status: Accepted
- Date: 2026-08-08
- Supersedes: the implementation mechanism proposed by [VS-028](../../tickets/VS-028-prose-only-process-discovery.md)
- Related: [analysis pipeline handoff](../../current/analysis-pipeline-handoff-2026-08-08.md), ADR-2026-08-07-001, ADR-2026-08-07-002

## Context

VS-028's twelve Flask/Celery runs established that listing a Markdown
reference as always-read does not load it. The `skill()` tool returns only
`SKILL.md`; the Agent never read `references/workflow.md` or
`references/workload-boundary.md`. The acceptance adapter also installs the
Skill under `config/skills`, while `runtime/tools/read.ts` trusts the singular
`config/skill` path. Prompt wording cannot mechanically guarantee required
analysis stages, reference loading, or final report delivery.

The current Summary and Detailed renderers are deterministic, but they run in
the Python acceptance adapter after the Agent responds. The interactive
runtime has no equivalent finalizer. The public report schema is intentionally
permissive and cannot validate stage order, evidence ownership, boundary
coverage, or revision integrity.

## Decision

Keep one public command, `/analyze-repo-for-kubernetes`, and replace the
prompt-directed workflow with one trusted, session-scoped
`analysis_pipeline` runtime tool. Its only actions are `start`, `submit`,
`reopen`, and `finalize`. Internal stages are not public commands:

```text
discovery -> execution -> relationships -> boundaries -> contracts -> finalize
```

`start` returns the active stage's canonical instruction and closed submission
schema. The tool, not the model, loads those assets from a verified installed
Skill bundle. `submit` accepts only the current stage at the current server
revision. A justified `reopen` returns to the earliest affected prior stage
and atomically invalidates all later outputs and derived evidence. Only
`finalize` can project validated pipeline state into the existing public
report schema and produce Markdown.

The Agent may relay the Markdown returned by `finalize`, but a report is
accepted only when the final response matches that tool result's receipt and
content hash. Free-form Agent JSON or Markdown is not a completed analysis.

## State and deterministic identity

Pipeline state is private to the runtime and is stored outside the analyzed
repository. It has three internal groups:

```text
binding: session_id, target_realpath, target_snapshot_hash, skill_manifest_hash
control: current_stage, state_revision, state_hash, finalized
data: evidence_registry, rule_application_registry, stage_outputs
```

Except for `session_id`, all identity and control values are tool-computed.
`session_id` is a cryptographically random opaque identifier bound to the
runtime's actual caller/session identity; it is not model-provided and is not
part of report semantics. `target_realpath` is resolved once. The target
snapshot hash is a documented Merkle SHA-256 digest of normalized relative
paths, file kinds, executable bits, and regular-file contents, excluding the
VCS metadata directory. `skill_manifest_hash` is the corresponding digest of
the stage instructions, schemas, renderer, and manifest-version rules.
`state_revision` advances monotonically after each accepted transition.
`state_hash` is SHA-256 over the redacted state serialized with a defined
canonical JSON encoding. Evidence IDs are derived by the tool from the
snapshot identity, normalized location/range, claim status, and redacted
content fingerprint.

The implementation must not copy raw repository content into persistent
pipeline state. Each target read opens a verified regular-file handle beneath
the resolved target, rechecks that handle's identity before use, records its
content hash, and rejects reparse points or paths outside the target. Before
finalization the tool recomputes the target Merkle digest and verifies every
evidence-file hash. Any mismatch fails the session instead of emitting a
report. Evidence registry entries retain only IDs, relative locations, ranges,
content fingerprints, and redacted classifications; raw snippets, secret
literals, and unredacted error text are prohibited in state, traces, and
payloads.

## Pipeline contracts and invariants

The implementation uses a new internal closed schema rather than
`schemas/analysis-result.schema.json`. It models: discovery signals and their
dispositions; processes; runtime graph edges; operational units; and one
runtime contract per deployable unit. Every evidence-bearing claim has one of
`confirmed`, `inferred`, `unknown`, `conflicted`, or `not_applicable` status.
An `unknown` claim must name its search scope, absence evidence, and blocked
decision.

Every mandatory reference rule used by a stage has a manifest-versioned
`rule_id`. The rule-application registry links `rule_id` to the target evidence
IDs it governs, the process/candidate IDs affected, and the boundary or
readiness decision ID that consumes it. A required rule cannot be marked
complete merely because its file was read; it must have a valid application,
or a scoped target absence linked to the same rule and process.

The validator rejects skipped, duplicate, stale, cross-session, cross-target,
cross-snapshot, and cross-manifest submissions. It also rejects unresolved
signal/process coverage, dangling graph IDs, duplicate unit membership,
contracts for non-deployable units, missing or duplicate contracts for
deployable units, forged evidence IDs, secret-bearing state, and premature
finalization. It also rejects a mandatory rule with no application, dangling
rule/evidence/process/decision links, or a boundary decision not supported by
its required rule applications. Finalization is a pure projection: it cannot discover evidence
or change pipeline state other than marking the receipt final.

Execution duration (`continuous`, `one_shot`, `scheduled`) is distinct from
operational independence. Process existence, repository role, deployability,
and operational-management boundary are separate fields. This preserves an
unresolved boundary when evidence is insufficient instead of inventing a
merge or split.

## Runtime integration

The OpenCode binding is a thin `runtime/tools/analysis_pipeline.ts` wrapper;
pure state, validation, secure-read, instruction-bundle, and renderer modules
live under `runtime/lib/pipeline/`. The deployed tool bundle must include those
modules, have an explicit `analysis_pipeline` allow rule, and resolve the
plural `config/skills/analyze-repo-for-kubernetes` path after realpath and
manifest verification. It must not rely on the current `read.ts` trusted-root
logic.

Before PIPE-002 is implemented, verify that the OpenCode plugin/tool API
exposes a non-forgeable caller/session identity. If it does not, PIPE-002 is
blocked pending an appropriate session hook or plugin API; it must not emulate
session binding with a model-supplied ID. The existing Python adapter must use
the runtime finalizer path for acceptance, not render raw Agent output after
the fact.

## Consequences

- Required stages, instruction loading, state transitions, and report
  rendering become mechanically checked rather than voluntary Agent behavior.
- The implementation adds a stateful security boundary and must receive
  security-focused tests before provider-backed runs.
- More code and structured model/tool exchanges are acceptable: correctness
  and on-premise analysis quality take priority over token or latency savings.
- VS-028 remains evidence of the failed prose-only mechanism. Its prior
  always-load change is not a solution for this architecture and no additional
  wording-only iteration is authorized.

## Verification requirements

Unit and integration tests must prove transition, revision, coverage,
path/symlink, redaction, deterministic-rendering, and cleanup invariants.
Provider-backed verification must use the repository's detached `tmux`
procedure, retain ordered pipeline receipts, compare the final response with
the `finalize` receipt, and confirm the analyzed target's Git status is
unchanged. The work is divided into PIPE-001 through PIPE-005.
