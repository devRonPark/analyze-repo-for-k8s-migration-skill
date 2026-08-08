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
- Tests for stage instruction identity, path mismatch handling, stale
  submission rejection, and no independent public stage command.
- A deletion budget listing every public Skill or Agent-prompt requirement
  replaced by an injected, tested stage contract. Remove only entries on that
  list; retain invocation, target-safety, and final-output routing that the
  pipeline does not yet own.

## Out of scope

- Changing Kubernetes judgment rules without a separately approved decision.
- Public report Markdown layout and provider-backed scenario scoring.

## Acceptance criteria

- The model cannot complete a pipeline by voluntarily skipping an injected
  stage or an internal reference.
- A new signal found late forces a bounded, validated reopen rather than a
  silently inconsistent report.
- The committed deletion budget has no duplicate normative rule remaining in
  both an enforced stage contract and the public Skill/Agent prompt.

## Commit boundary

Commit stage assets, binding changes, Agent/command migration, and focused
tests together.
