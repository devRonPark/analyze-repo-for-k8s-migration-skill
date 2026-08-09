# ADR-2026-08-08-009: Make no-op Skill pruning the terminal pipeline task

- Status: Accepted
- Date: 2026-08-08
- Related: ADR-2026-08-08-005, ADR-2026-08-08-008, PIPE-003, PIPE-005, PIPE-006

## Static MCP Stage Skills amendment

The Static MCP Stage Skills terminal sweep applies to the installed bundle,
runtime launcher, copied contracts, client fragments, and acceptance adapter.
It verifies the delivered analysis runtime contains no TypeScript, JavaScript,
Node, or Bun artifact and that canonical rule ownership remains singular.

## Context

`SKILL.md` is always-loaded context. A sentence that does not change an
Agent's routing, tool use, grounded evidence, Workload Unit decision, report
contract, or safety behaviour consumes context without owning a behavioural
contract. It can dilute the terms that do carry such a contract and leave
duplicated sources of truth after stage contracts move into the runtime.

Matt Pocock's skill-writing guidance explicitly treats every description word
as context cost and recommends a no-op deletion test: remove a passage and
observe whether agent behaviour changes. This repository's trusted pipeline
adds a stronger prerequisite: deterministic contracts and provider-backed E2E
must first establish the behavioural baseline that makes a deletion result
meaningful.

## Decision

Perform no-op Skill pruning only as the final pipeline task, `PIPE-006`, after
PIPE-005 and VS-027 live evaluation are complete. Do not remove instructional
prose merely because a runtime contract was introduced; retain it until the
full pipeline is measured end-to-end.

For every candidate sentence or paragraph, use a deletion test:

1. identify its claimed unique behavioural responsibility;
2. remove only that unit in an isolated change;
3. run its mapped deterministic checks and the relevant acceptance scenario;
4. compare routing, stage coverage, source-linked evidence, Workload Boundary
   outcome, report contract, and target immutability with the baseline; and
5. keep the deletion only when all mapped behaviour is unchanged.

If a deletion changes any required behaviour or the evidence is inconclusive,
restore the text and record it as retained. The final compact Skill preserves
only invocation, target safety, active-stage routing, output routing, and any
rule not yet owned by a tested runtime contract.

## Consequences

- PIPE-003 records the deletion inventory but performs no text removal.
- PIPE-006 is last in the milestone queue; no feature work follows it in the
  same milestone.
- The deletion record names every removed and retained unit with its mapped
  test evidence, so pruning is a measured refactor rather than aesthetic
  editing.
