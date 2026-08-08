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
- Detached `tmux` OpenCode E2E: Flask/Celery Summary and Detailed three times
  each; JPetStore Summary and Detailed; command aliases; independent role
  arguments; and unresolved-boundary cases.
- Trace assertions for ordered submissions, injected instruction identity,
  state revisions, finalization receipt, and final-response hash.
- Target Git status/tree comparison before and after every interactive run.

## Out of scope

- Treating an `opencode run` wrapper or a report-shaped Agent message as an
  interactive acceptance substitute.

## Acceptance criteria

- Flask web and Celery worker are distinct deployable candidates even when
  they share source or image; lack of a worker port does not remove it.
- JPetStore web remains one workload and its embedded database is not split.
- Interrupted, step-limited, unfinalized, or hash-mismatched sessions fail.
- Every recorded interactive run preserves the target repository unchanged.

## Commit boundary

Commit golden evidence, scorecards, deterministic tests, and E2E harness
changes as reviewable focused commits; keep provider artifacts redacted.
