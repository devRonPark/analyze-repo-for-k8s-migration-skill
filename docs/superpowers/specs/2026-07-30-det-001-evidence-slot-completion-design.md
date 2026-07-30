# DET-001 Evidence-slot completion contract design

## Scope

Implement DET-001 from the Detailed evidence-budget ticket list. The work
changes the existing Detailed analysis instructions, checklist, report
template, report validator, fixture, and focused contract tests. It does not
implement DET-002's candidate-count budget or DET-003's golden-set evaluation.

## Design

Detailed analysis treats the existing eight report sections as its report
skeleton. Immediately after deployable candidates are identified, the agent
creates that skeleton and fills every required finding before optional further
exploration. A required finding ends as `확인됨`, `상충됨`, or a scoped
`미확인`; `추정됨` remains available only for an evidence-backed inference and
does not replace an unresolved required finding.

The Detailed checklist defines the required evidence groups: candidate
classification, per-candidate execution, per-candidate configuration and
state, dependency relationships, operating-environment evidence, exclusions
and blockers, and final design-input readiness. For missing evidence, the
report names the candidate or shared scope and the decision left open.

The existing Markdown contract remains the sole structural source. The
validator continues to require its eight sections and gains Detailed-specific
checks that required candidate-card evidence groups have a terminal status,
that conflicts preserve both sources, and that unknowns describe the affected
scope and decision. No `evidence slots` section, new runtime process, or new
dependency is added.

## Verification

Focused contract tests cover a complete Detailed fixture plus rejection of an
incomplete eight-section report, an unterminated required candidate evidence
group, an unscoped unknown, and a conflict without both sources. Run the
affected unit tests and the repository quality gate. The provider-backed
JPetStore E2E is then run through the documented detached-tmux procedure with
approved network permission and unchanged target Git status.

## Non-goals

- Candidate-count budgeting, slot allocation, lockfile budgeting, and
  low-signal stopping belong to DET-002.
- Golden-set preparation, scoring, and the food-delivery E2E belong to DET-003.
- The final Detailed report adds no Markdown table or new top-level section.
