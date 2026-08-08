# TICKET-LIST-2026-08-08-001: Trusted pipeline resequencing

- Status: PIPE-000 supported; PIPE-001 is the next ticket
- Decision: ADR-2026-08-08-005

## Queue

Implement and commit each ticket independently in this order:

1. [PIPE-000](../../tickets/PIPE-000-runtime-binding-compatibility.md) —
   verify the OpenCode capability assumptions without a provider call.
2. [PIPE-001](../../tickets/PIPE-001-pipeline-state-and-validator.md) —
   define the closed pure state machine and prove the minimal ordered path.
3. [PIPE-002](../../tickets/PIPE-002-session-tool-and-secure-snapshot.md) —
   bind that state machine to the supported runtime identity and verified
   target snapshot.
4. [PIPE-003](../../tickets/PIPE-003-stage-contract-injection-and-agent-migration.md)
   — inject canonical contracts and record the deletion inventory without
   removing public text.
5. [PIPE-004](../../tickets/PIPE-004-runtime-finalizer-and-deterministic-renderer.md)
   — produce a canonical report and receipt for content-oriented acceptance.
6. [VS-027](../../tickets/VS-027-workload-boundary-golden-fixtures.md), static
   fixture and rubric portion only — prepare the boundary test data before
   provider runs.
7. [PIPE-005](../../tickets/PIPE-005-pipeline-acceptance-and-interactive-e2e.md)
   — run deterministic integration and provider-backed interactive acceptance.
8. [VS-027](../../tickets/VS-027-workload-boundary-golden-fixtures.md), live
   repetitions and scorecard — finish the ticket using PIPE-005's verified
   runtime path.
9. [PIPE-006](../../tickets/PIPE-006-terminal-skill-pruning.md) — run measured
   no-op deletion tests and remove only behaviour-preserving public text. This
   is the final milestone task.

## Gates

- A `BLOCKED` PIPE-000 result stops PIPE-002 and requires an ADR before any
  substitute identity is proposed.
- PIPE-001's deterministic vertical proof is required before PIPE-002 starts.
- PIPE-005 may not begin provider-backed runs until VS-027's static fixtures
  and golden rubrics are committed.
- The existing Markdown-directed workflow remains intact until PIPE-003 has
  a tool-owned replacement and PIPE-006 has completed the mapped deletion test
  for each removed requirement.

## Commit discipline

Each completed ticket receives one focused commit after its stated verification.
This list is the queue index only; ticket files remain the sole source of
acceptance criteria and verification evidence.
