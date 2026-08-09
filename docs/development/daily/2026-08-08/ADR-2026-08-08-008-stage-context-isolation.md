# ADR-2026-08-08-008: Isolate future-stage work from the Agent's active context

- Status: Accepted
- Date: 2026-08-08
- Related: ADR-2026-08-08-004, PIPE-001, PIPE-003, Leading Words design

## Static MCP Stage Skills amendment

Static MCP Stage Skills narrows this ADR's guarantee to progressive procedural
disclosure. The fixed MCP catalog may reveal tool names, and OpenCode has a
static allowlist for the seven installed Skill roots. The invariant is that a
future Skill body or reference is not loaded before predecessor acceptance;
the server rejects out-of-order calls even though every tool is listed.

## Context

An Agent that can see a complete multi-stage roadmap while performing an early
stage can optimize for apparent progress toward later work. In this Skill that
causes a harmful shortcut: it may open a required reference, collect only a
shallow signal, and rush to the Workload Unit decision or report before the
current evidence work is complete.

Progressive disclosure is required here as a quality control, not merely as a
context-saving technique. The Agent needs the active stage's purpose, allowed
tools, authoritative references, closed submission schema, and completion
criteria. It does not need a preview of the next stage's task, assets,
acceptance criteria, or outputs.

## Decision

The runtime `analysis_pipeline` is the sole disclosure boundary for stage
contracts.

- `start` returns only the initial active contract. It does not return the
  stage graph, later-stage identifiers, a remaining-stage count, or future
  assets.
- A successful `submit` verifies and closes the active contract before it
  returns the newly active contract. The returned next contract is the first
  time the Agent may learn that work; at that point the prior stage is closed.
- `reopen` returns only the reopened contract and its structured reason. It
  invalidates later outputs without exposing their instructions or data.
- The runtime has no `list_stages`, `preview_stage`, or equivalent action.
  Stage assets are loaded internally and may not be read through a general
  repository-reading tool.
- Public Skill, command, and Agent text name only the currently active
  pipeline action. They do not enumerate the internal stage roadmap or tell
  the Agent what it will do next.

A **Vertical Slice** is the end-to-end, runtime-owned trace for one Workload
candidate across the necessary internal phases. It is not synonymous with one
active contract. An active contract is the slice's current phase: it exposes
only that phase's evidence, Grounding rule, immediate decision input, and
Quality Gate. A Workload Boundary or readiness conclusion is required only in
the phase that owns that conclusion; an early phase must not predict it or
describe later work as motivation to hurry its own completion.

## Consequences

- Development documents may retain the full pipeline plan; the restriction
  applies to runtime Agent context, not maintainers.
- Tool responses and traces contain only accepted receipts and the active
  contract; they must not leak future instructions through names, errors, or
  metadata.
- A valid current submission is necessary but not sufficient to receive a
  later contract: the tool must also pass the current stage's coverage and
  grounding checks.
- This does not make the model unable to reason generally about a Kubernetes
  migration. It prevents this Skill from supplying a future-task roadmap that
  competes with the active evidence task.

## Verification requirements

- Unit tests give every future contract, schema, and asset a distinct opaque
  canary and assert that `start`, failed `submit`, and `reopen` responses do
  not contain any future canary, identifier, asset content, count, or schema.
- Transition tests assert that a next contract appears only after the current
  submission satisfies its full coverage and grounding invariants.
- Integration tests ensure general read/glob tools cannot read the internal
  stage-contract bundle.
- Interactive E2E traces and model-input snapshots are checked for a completed
  grounded current-stage result before each later contract is observed, and
  for absence of every future canary from prompts, tool responses, errors, and
  receipts.
