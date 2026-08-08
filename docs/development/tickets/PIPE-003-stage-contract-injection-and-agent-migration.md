# PIPE-003 — Inject canonical stage contracts and migrate the Agent

## Outcome

Move required analysis instructions from optional Markdown reads into
tool-provided stage contracts, then change the sole public Agent/command flow
to drive `analysis_pipeline` through its six stages.

## Depends on

- PIPE-001
- PIPE-002

## In scope

- Versioned, manifest-hashed stage instruction and closed-schema assets.
- Tool-owned installed Skill-bundle loading that supports the plural
  `config/skills` installation path.
- Agent and command instructions that start the pipeline, submit only the
  active stage, use restricted `reopen`, and relay only finalized output.
- Runtime stage-context isolation per ADR-2026-08-08-008: expose only the
  active contract and never a future-stage task, identifier, count, schema,
  asset, or roadmap.
- Each active contract declares only its applicable manifest-versioned
  `rule_id`s and requires a closed rule application to target evidence and its
  immediate phase decision input. It never discloses rules owned by later
  phases.
- Tests for stage instruction identity, path mismatch handling, stale
  submission rejection, no independent public stage command, and absence of
  future-stage leakage in `start`, failed `submit`, and `reopen` responses.
- Opaque-canary tests for future contracts/assets and rule-application tests
  that reject a read acknowledgement without target evidence usage.
- A deletion budget listing every public Skill or Agent-prompt requirement
  replaced by an injected, tested stage contract. Record every candidate for
  terminal PIPE-006; do not remove public text in this ticket.

## Out of scope

- Changing Kubernetes judgment rules without a separately approved decision.
- Public report Markdown layout and provider-backed scenario scoring.

## Acceptance criteria

- The model cannot complete a pipeline by voluntarily skipping an injected
  stage or an internal reference.
- The model cannot obtain a later-stage contract until the active contract's
  coverage and grounding invariants pass; errors and receipts do not disclose
  future-stage work.
- A new signal found late forces a bounded, validated reopen rather than a
  silently inconsistent report.
- The committed deletion inventory maps every duplicate normative rule to its
  tested runtime owner and PIPE-006 deletion test; it does not remove text
  before the complete pipeline baseline exists.

## Commit boundary

Commit stage assets, binding changes, Agent/command migration, and focused
tests together.
