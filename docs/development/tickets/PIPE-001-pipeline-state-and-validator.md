# PIPE-001 — Define deterministic pipeline state and pure validator

## Outcome

Create the closed internal state schema and pure TypeScript validator for the
analysis pipeline. It must represent the six internal stages, state revisions,
claims, evidence registry, discovery/process/graph/boundary/contract data, and
the invariants in ADR-2026-08-08-004. No OpenCode tool binding, target read,
or provider invocation is included.

## Depends on

None.

## In scope

- Canonical JSON and SHA-256 helpers for state and deterministic IDs.
- Closed envelopes and stage-specific input/output schemas.
- Pure transition and `reopen` validation with atomic invalidation plans.
- Coverage, graph integrity, claim-status, evidence-ID, deployability, and
  runtime-contract invariants.
- TypeScript unit tests for every accepted and rejected transition.

## Out of scope

- Filesystem access, session storage, OpenCode permission changes, Agent
  prompt migration, Markdown rendering, and provider-backed E2E.

## Acceptance criteria

- Tests reject stage skips, duplicates, stale revisions, cross-binding state,
  premature finalization, dangling IDs, duplicate membership, and invalid
  unknown claims.
- Tests prove `reopen` invalidates all later state deterministically.
- The same valid state produces the same state hash and projected ID values.

## Commit boundary

Commit schema, pure library, and their focused tests together.
