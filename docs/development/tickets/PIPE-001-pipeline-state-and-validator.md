# PIPE-001 — Define deterministic pipeline state and pure validator

## Static MCP Stage Skills amendment

This ticket's pure Python state work is superseded by Ticket 2 of the approved
Static MCP Stage Skills plan. The final contract uses process-private
AnalysisSession state, opaque server-issued analysis IDs and transition tokens,
static transport schemas, and no state-hash public field or replay ledger.

## Outcome

Create the closed internal state schema and pure Python validator for the
analysis pipeline under `runtime/python/`. It must represent the six internal
stages, state revisions, claims, evidence registry, mandatory-rule
applications, discovery/process/graph/boundary/contract data, and the
invariants in ADR-2026-08-08-004 and the approved Python MCP design. No MCP
transport, target read, or provider invocation is included.

## Depends on

- PIPE-000 must record `SUPPORTED` for the runtime-binding prerequisites, or
  an ADR must explicitly replace the blocked architecture before this ticket
  starts.

## In scope

- Canonical JSON and SHA-256 helpers for state and deterministic IDs.
- Closed envelopes and stage-specific input/output schemas.
- Pure transition and `reopen` validation with atomic invalidation plans.
- A closed transition table: legal forward stages, legal `reopen` targets,
  required structured reason, and the exact later outputs invalidated by each
  back-edge.
- Coverage, graph integrity, claim-status, evidence-ID, mandatory-reference
  provenance, deployability, and runtime-contract invariants.
- A closed rule-application relation:
  `rule_id -> evidence_ids -> process_or_candidate_ids -> decision_id`.
  A scoped target absence uses the same relation and cannot stand in for a
  missing rule application.
- Python unit tests for every accepted and rejected transition.
- A deterministic vertical proof over the pure API: create a bound state,
  submit minimal valid data for all six stages in order, finalize it, and
  verify that skipped, stale, forged, and unfinalized variants fail. This is
  not an MCP transport or provider invocation; PIPE-002 binds the same API to
  the stdio MCP server later.

## Out of scope

- Filesystem access, process lifecycle policy, client configuration, Agent
  prompt migration, Markdown rendering, and provider-backed E2E.

## Acceptance criteria

- Tests reject stage skips, duplicates, stale revisions, cross-binding state,
  premature finalization, dangling IDs, duplicate membership, and invalid
  unknown claims.
- Tests reject an unread/unapplied mandatory rule, a dangling or mismatched
  rule/evidence/process/decision relation, and a boundary outcome that does
  not consume its required rule application.
- Tests prove `reopen` invalidates all later state deterministically.
- The same valid state produces the same state hash and projected ID values.
- The vertical proof is the first consumer of the public pure state-machine
  API and proves that no valid path skips a stage or finalizes unvalidated
  data.
- The implementation and tests are provider-free and package under
  `runtime/python/` without requiring TypeScript, Node, or Bun.

## Commit boundary

Commit schema, pure Python library, and focused tests together.
