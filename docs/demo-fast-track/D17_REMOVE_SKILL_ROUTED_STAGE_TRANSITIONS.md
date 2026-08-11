# D17 — Remove Skill-Routed Stage Transitions

## Context

The former implementation had two transition layers. The trusted layer was
`PipelineState.current_stage`, `ANALYSIS_STAGES`, validation, fact promotion,
revision/state-hash protection, and finalization. A second, runtime-specific
layer emitted `handoff.next_skill` and required native or host-managed loading
of a successor `SKILL.md`.

D12 through D16 established that host-injected successor content cannot
reproduce OpenCode's native Skill lifecycle without a different control plane.
Those experimental records remain historical evidence and are not rewritten.

## Decision

Remove successor-Skill routing. There is one public Skill. On each accepted
server response it reads only `references/stages/<current_stage>.md`, where
`current_stage` is supplied by the trusted server. This is progressive
disclosure of the already-authoritative state, not a request to activate a
successor Skill or select a stage.

## What remains authoritative

The server remains the sole authority for stage progression:

```text
start_analysis -> current_stage
execute current-stage procedure -> submit_<current_stage>
accepted -> server advances current_stage
rejected -> current_stage is unchanged
```

`PipelineState`, legal ordering, stage-specific payload validation, evidence
binding, fact promotion, revision/state hash integrity, snapshot protection,
retry budgets, Boundaries recovery, and deterministic rendering remain in the
trusted pipeline.

## What was removed

- `handoff.next_skill` and `SKILL_BY_STAGE`.
- Seven-Skill bundle topology and successor-Skill permissions.
- Host/model transition ownership, host continuation, activation state, and
  the OpenCode duplicate-Skill guard.
- Stage `## Transition` choreography and its prompt-prose tests.
- D12–D16 runtime-routing characterization tests.

`transition_token` remains because it is part of existing server integrity
state, not because it activates a Skill.

## Why stages remain

Discovery, Execution, Relationships, Boundaries, Contracts, and Finalize are
still separate procedure documents. The public Skill directs the model to read
only the document named by the server's current state. No all-stage prompt or
replacement router is introduced.

## Serve mode

Serve-mode orchestration is not pursued. D16 showed that it would be a new
control-plane architecture, while this decision removes the unnecessary
successor-activation mechanism instead.

## Behavioral invariants

- A wrong-stage submit returns deterministic `stage_order` and leaves state
  unchanged.
- An accepted submit advances exactly one legal stage.
- A rejected submit preserves the current stage, revision, and state binding.
- Finalization remains valid only after Contracts acceptance.
- The target remains read-only.

## Ablation results

Deterministic verification covers the public response seam and stage-document
progressive disclosure. One Windows-native static-MCP run was completed against
the pinned `jpetstore-6-summary` target at
`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, using the configured local
provider. It timed out at 309,697 ms without a final report, but the preserved
trace recorded five accepted responses (`start_analysis` through
`submit_boundaries`), current-stage progression through `contracts`, zero
validation rejections, 27 tool calls/turns, and an unchanged target. No
successor Skill activation appeared in that path. One comparable run is not a
completion-rate ablation; three comparable runs and a completed-report result
remain required before making a provider-level success claim.

## Superseded runtime-specific mechanisms

D12–D16's host-owned/model-routed experiments, continuation state, and native
successor-Skill lifecycle comparison are superseded as implementation paths,
not as historical evidence. Their conclusion supports deletion: the trusted
state machine does not require a second routing state machine.

The acceptance adapter retains an unreachable D12–D16 trace-decoding helper
only for old captured artifacts. It is stale development telemetry: the active
runner no longer invokes it and it must not be used as a runtime route.
