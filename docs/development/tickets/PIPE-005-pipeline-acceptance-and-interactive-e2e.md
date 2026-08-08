# PIPE-005 — Verify pipeline invariants and interactive behavior

## Outcome

Prove that the complete pipeline produces useful, evidence-disciplined reports
without modifying analyzed repositories, and that its ordered receipts expose
all required stage activity.

## Depends on

- PIPE-001
- PIPE-002
- PIPE-003
- PIPE-004
- VS-027's committed static fixtures and golden rubrics

## Read first

- `memory/opencode-e2e.md`
- ADR-2026-08-08-004
- `tests/evaluation/vs-028-flask-celery-runs/README.md`

## In scope

- Deterministic integration coverage for all PIPE invariants and runtime
  packaging paths.
- Golden sets and scorecards created from static target evidence before any
  provider run.
- Provider-free smoke tests for OpenCode, Claude Code, and Gemini CLI covering
  Python MCP launch, `initialize`, tool schema, one active analysis only,
  post-finalize cleanup, and stderr-only diagnostics.
- Detached `tmux` OpenCode E2E: Flask/Celery Summary and Detailed three times
  each; JPetStore Summary and Detailed; command aliases; independent role
  arguments; and unresolved-boundary cases.
- Trace assertions for ordered submissions, injected instruction identity,
  state revisions, finalization receipt, canonical report hash, rule
  application provenance, and future-stage opaque-canary absence across model
  inputs, tool responses, errors, receipts, and trace snapshots.
- Contrastive fixtures or rule-mutation tests where surface process signals are
  held constant but correct Workload Boundary outcome changes only when the
  applicable mandatory rule is consumed.
- Detailed readiness-gap acceptance cases and Summary rejection cases.
- Target Git status/tree comparison before and after every interactive run.

## Out of scope

- Treating an `opencode run` wrapper or a report-shaped Agent message as an
  interactive acceptance substitute.

## Acceptance criteria

- Flask web and Celery worker are distinct deployable candidates even when
  they share source or image; lack of a worker port does not remove it.
- JPetStore web remains one workload and its embedded database is not split.
- Every mandatory rule used in a final boundary outcome has a
  `rule_id -> evidence -> process/candidate -> decision` trace; a read-only or
  unused rule cannot pass coverage.
- Detailed gap items are grounded and implementation-neutral; Summary contains
  no readiness-gap recommendation.
- Interrupted, step-limited, unfinalized, or canonically hash-mismatched
  sessions fail content-oriented acceptance.
- Every recorded interactive run preserves the target repository unchanged.
- Cross-client smoke tests confirm the same Python MCP tool schema and cleanup
  behavior for OpenCode, Claude Code, and Gemini CLI before those clients are
  considered supported.

## Commit boundary

Commit golden evidence, scorecards, deterministic tests, and E2E harness
changes as reviewable focused commits; keep provider artifacts redacted.
