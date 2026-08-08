# PIPE-004 — Move final rendering into the runtime pipeline

## Outcome

Make `analysis_pipeline.finalize()` validate completed pipeline state, project
it to the existing public report contract, and return the sole deterministic
Markdown report plus a receipt. The acceptance adapter consumes this runtime
result rather than rendering raw Agent output after the session.

## Depends on

- PIPE-001
- PIPE-002
- PIPE-003

## In scope

- Pure TypeScript public-report projector, renderer, validator, and receipt
  generator equivalent to the existing supported Summary and Detailed
  contracts.
- Exact final-response/hash comparison in the runtime-aware acceptance path.
- Tests for deterministic output, invalid projection rejection, and the rule
  that finalization cannot discover or mutate analysis data.

## Out of scope

- New report fields or Korean template redesign.
- Provider retry policy beyond rejecting incomplete/unfinalized sessions.

## Acceptance criteria

- Identical finalized state yields byte-identical Markdown and receipt hash.
- No free-form Agent response can pass as a completed report without a valid
  `finalize` receipt.
- Summary and Detailed existing report-contract tests remain covered through
  the runtime implementation.

## Commit boundary

Commit the runtime projector/renderer, adapter migration, and focused tests
together.
