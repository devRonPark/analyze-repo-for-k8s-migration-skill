# ADR-2026-08-08-006: Hold the pipeline until a host-owned session and final-response boundary exists

- Status: Superseded by ADR-2026-08-08-007
- Date: 2026-08-08
- Related: ADR-2026-08-08-004, ADR-2026-08-08-005, PIPE-000 completion

## Static MCP Stage Skills amendment

This ADR remains superseded. Static MCP Stage Skills does not select a host
session API: one fresh server process owns one active analysis. Server-issued
analysis IDs, revisions, transition tokens, target snapshots, and trusted
observations replace any proposed host identity. No model-supplied identifier
is accepted as state authority.

## Context

PIPE-000's local inspection found no session-identity use in this repository's
tool examples and no interactive final-response transformation hook. Subsequent
official API research showed that custom-tool context documents a host-provided
`sessionID`; installed-runtime compatibility still needs proof. The current
renderer and receipt finalizer are acceptance-harness code that runs after the
Agent response.

The trusted pipeline cannot replace the required session identity with a
model-provided identifier, a generated process-global ID, or a prompt rule.
Those substitutes would weaken the security boundary that ADR-2026-08-08-004
introduced it to provide.

## Decision

Hold PIPE-001 through PIPE-004 implementation. Preserve their ticket designs
as a conditional plan, but do not implement the pure state machine or runtime
binding until a host boundary is selected and independently verified.

The required boundary was originally specified as both an opaque caller/session
identity and a host-owned final-response path. ADR-2026-08-08-007 narrows that
requirement to the identity boundary because content integrity, rather than
strict interactive response formatting, is the material safety objective.

An OpenCode plugin API, a supported OpenCode host hook, or a separately
approved host-side invocation architecture may satisfy this decision. Any
candidate must document its API, lifecycle, cleanup behavior, and testable
non-forgeability before PIPE-001 is unblocked. It must not place state or
reports in the analyzed repository.

## Consequences

- No substitute session binding is implemented in this repository.
- PIPE-005 provider E2E remains blocked because it depends on PIPE-001 through
  PIPE-004.
- VS-027's static fixtures remain useful future test data but do not remove the
  host-boundary blocker.
- Resuming the pipeline requires a new ADR selecting the concrete host API and
  a revised PIPE-000 completion record with `SUPPORTED` results for both
  prerequisites.
