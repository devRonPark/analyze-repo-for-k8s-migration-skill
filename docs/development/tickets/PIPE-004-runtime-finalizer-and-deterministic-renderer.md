# PIPE-004 — Move final rendering into the runtime pipeline

## Outcome

Make `analysis_pipeline.finalize()` validate completed pipeline state, project
it to the existing public report contract, and return canonical deterministic
Markdown plus a receipt. The acceptance adapter uses that result to assess
content integrity. A direct-TUI response may differ in presentation without
being a pipeline-security failure, as recorded in ADR-2026-08-08-007.

## Depends on

- PIPE-001
- PIPE-002
- PIPE-003

## In scope

- Pure TypeScript public-report projector, renderer, validator, and receipt
  generator equivalent to the existing supported Summary and Detailed
  contracts.
- Canonical report/receipt comparison in the runtime-aware acceptance path.
- Tests for deterministic output, invalid projection rejection, and the rule
  that finalization cannot discover or mutate analysis data.

## Out of scope

- New report fields or Korean template redesign.
- Provider retry policy beyond rejecting incomplete/unfinalized sessions.

## Acceptance criteria

- Identical finalized state yields byte-identical Markdown and receipt hash.
- No report can pass content-oriented pipeline acceptance without a valid
  `finalize` receipt.
- Summary and Detailed existing report-contract tests remain covered through
  the runtime implementation.

## Commit boundary

Commit the runtime projector/renderer, adapter migration, and focused tests
together.
