# ADR-2026-08-08-007: Prioritize content integrity over final-response enforcement

- Status: Accepted
- Date: 2026-08-08
- Related: ADR-2026-08-08-004, ADR-2026-08-08-005, ADR-2026-08-08-006, PIPE-000

## Context

The review-driven PIPE-000 gate originally required two host-owned runtime
properties: an opaque session identity and a path that could force every
interactive final response to be the exact `analysis_pipeline.finalize()`
receipt. That conflated two different risks.

OpenCode's documented custom-tool context includes the host-provided
`sessionID` field, subject to compatibility verification against the installed
1.18.14 runtime. The existing Python acceptance harness already renders,
validates, and finalizes the report after an Agent response. It does not
rewrite a direct-TUI response, but it detects a report-contract failure.

The user has clarified that a formatting deviation is not a material failure
when the analysis content remains correct. Incorrect or unsupported content,
on the other hand, is a material risk. Requiring a server-wrapper-only entry
point would change the established direct-TUI experience in exchange for a
guarantee that is not required for this milestone.

## Decision

Keep the direct-TUI `/analyze-repo-for-kubernetes` workflow. Do not introduce
a local server wrapper as a prerequisite for the trusted analysis pipeline.

PIPE-000 now verifies only that the installed runtime delivers a host-issued
`sessionID` to a custom tool. PIPE-001 through PIPE-004 may use that identity
only after the compatibility test demonstrates it. A model-provided,
CLI-provided, generated, or process-global substitute remains prohibited.

Use the existing deterministic renderer, report validator, receipt finalizer,
static golden fixtures, and provider-backed E2E scoring to protect content
integrity. The acceptance boundary must reject unsupported evidence,
transition errors, incomplete required analysis stages, and content that
contradicts the golden rubric. It may report a presentation-format deviation
without treating it as a pipeline-security failure when the content contract
still passes.

## Consequences

- The final-response receipt is a post-response acceptance artifact, not an
  interactive-response interception mechanism.
- PIPE-000 is no longer blocked by the absence of a documented direct-TUI
  final-response transformation hook.
- ADR-2026-08-08-006 is superseded. Its prohibition on substitute session IDs
  remains in force; its mandatory host-owned final-response requirement does
  not.
- A future server wrapper remains an optional delivery feature, not a trusted
  pipeline prerequisite. It requires a separate UX decision and ADR.
