# ADR-2026-08-08-006: Hold the pipeline until a host-owned session and final-response boundary exists

- Status: Accepted
- Date: 2026-08-08
- Related: ADR-2026-08-08-004, ADR-2026-08-08-005, PIPE-000 completion

## Context

PIPE-000 found no local evidence that OpenCode 1.18.14 exposes a non-forgeable
caller/session identity to a custom tool, or that the interactive runtime owns
the final response through a receipt and content-hash check. The current
renderer and receipt finalizer are acceptance-harness code that runs after the
Agent response, and the existing tool examples use only `context.worktree`.

The trusted pipeline cannot replace either missing capability with a
model-provided identifier, a generated process-global ID, or a prompt rule.
Those substitutes would weaken the security boundary that ADR-2026-08-08-004
introduced it to provide.

## Decision

Hold PIPE-001 through PIPE-004 implementation. Preserve their ticket designs
as a conditional plan, but do not implement the pure state machine or runtime
binding until a host boundary is selected and independently verified.

The required boundary must provide both:

1. an opaque caller/session identity issued by the host and delivered directly
   to the pipeline implementation; and
2. a host-owned final-response path that can return only the pipeline
   finalizer's Markdown, receipt, and content hash to the user.

An OpenCode plugin API, a supported OpenCode host hook, or a separately
approved host-side invocation architecture may satisfy this decision. Any
candidate must document its API, lifecycle, cleanup behavior, and testable
non-forgeability before PIPE-001 is unblocked. It must not place state or
reports in the analyzed repository.

## Consequences

- No substitute binding is implemented in this repository.
- PIPE-005 provider E2E remains blocked because it depends on PIPE-001 through
  PIPE-004.
- VS-027's static fixtures remain useful future test data but do not remove the
  host-boundary blocker.
- Resuming the pipeline requires a new ADR selecting the concrete host API and
  a revised PIPE-000 completion record with `SUPPORTED` results for both
  prerequisites.
