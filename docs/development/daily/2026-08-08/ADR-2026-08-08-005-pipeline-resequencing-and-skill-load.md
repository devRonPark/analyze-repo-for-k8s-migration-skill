# ADR-2026-08-08-005: Resequence the trusted analysis pipeline around an early vertical proof

- Status: Accepted
- Date: 2026-08-08
- Related: ADR-2026-08-08-004, PIPE-001 through PIPE-005, VS-027

## Context

The VS-028 experiment proved that a Markdown reference named by a Skill or
Agent prompt is not mechanically loaded. ADR-2026-08-08-004 correctly moved
required analysis stages, instruction loading, state transitions, and final
rendering into one trusted, session-scoped `analysis_pipeline` tool.

An external review of that direction used the Skill-design principles described
by Matt Pocock: predictable process over repeated prose, progressive
disclosure, one authoritative owner for each rule, and removal of no-op or
duplicated instructions. The review accepted the trusted-pipeline direction,
but found two execution-order risks:

1. The planned `PIPE-001` through `PIPE-005` sequence delays proof of the
   critical runtime assumptions until the final ticket.
2. The existing Skill and Agent text could remain as duplicated sediment after
   stage contracts move into the tool.

The architecture also depends on two runtime properties that are not yet
verified: a non-forgeable OpenCode caller/session identity, and a path by
which only a `finalize()` result can be accepted as the final response.

## Decision

Keep the single public `/analyze-repo-for-kubernetes` command and the
`analysis_pipeline` deep module. Do not return to prose-only attempts to make
the model load linked Markdown files.

Resequence the work as follows:

1. Add `PIPE-000` as a read-only compatibility gate. It verifies the required
   OpenCode session-identity and final-response capabilities before any
   stateful runtime implementation begins. A missing non-forgeable identity
   blocks PIPE-002 rather than being emulated with a model-provided value.
2. Retain PIPE-001 as the pure closed state model and validator, but require a
   deterministic vertical proof immediately after it. That proof exercises a
   minimal valid six-stage state through `start`, ordered submissions, and
   `finalize`, and rejects a forged, skipped, stale, or unfinalized path.
   Later PIPE tickets extend this path instead of waiting for PIPE-005 to
   first exercise it.
3. Make the internal state schema and transition table the single source of
   truth for invariants. ADRs explain why, tickets define change scope, and
   handoffs record status; none may duplicate normative validation rules.
4. Treat the static fixture and golden-rubric portion of VS-027 as an input to
   the pipeline milestone. It is prepared before PIPE-005; only provider-backed
   repetitions remain in PIPE-005.
5. Add an explicit PIPE-003 deletion budget. Once an injected stage contract
   is enforced by the tool and covered by tests, its duplicate requirements
   are removed from the public Skill and Agent prompt. The public Skill keeps
   only invocation, target-safety, and final-output routing needed before the
   pipeline starts.
6. Specify `reopen()` with a closed transition matrix, structured reason, and
   deterministic invalidation of all derived later state. It must reject an
   illegal back-edge or stale submission; it must not become an open-ended
   exploration loop.

## Consequences

- The first implementation work is a compatibility decision and a small
  vertical proof, not a broad rewrite of the existing Skill text.
- PIPE-005 remains the provider-backed and interactive acceptance boundary;
  it is not the first place where tool integration is exercised.
- Current linked Markdown references remain documented repository knowledge
  until PIPE-003 replaces their runtime ownership. No behavior is removed
  before a tool-owned contract and its tests exist.
- The implementation may not begin until PIPE-000 is recorded as supported
  or blocked. A blocked result requires a revised ADR before PIPE-002.

## Initial execution order

1. Create and commit the focused PIPE-000 ticket and the PIPE/VS-027 ticket
   amendments that implement this decision.
2. Perform and record the PIPE-000 compatibility gate without invoking an
   external model provider.
3. Implement PIPE-001 with test-first deterministic contracts and the early
   vertical proof.
4. Continue PIPE-002 through PIPE-004 as independently reviewable vertical
   increments, then run PIPE-005 using the detached interactive E2E procedure.
