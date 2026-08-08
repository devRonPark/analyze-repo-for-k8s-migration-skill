# PIPE-006 — Prune no-op Skill text after complete pipeline verification

## Outcome

Reduce `SKILL.md` and the public Agent/command text to the smallest behaviour-
preserving form. This is the final task of the trusted-pipeline milestone.

## Depends on

- PIPE-003's deletion inventory
- PIPE-005 complete
- VS-027 static and live evaluation complete

## In scope

- One-at-a-time deletion tests for public Skill and Agent/command passages.
- A committed deletion record that maps each candidate passage to its claimed
  responsibility, deterministic checks, acceptance scenario, result, and
  retain/remove decision.
- Removal only for units proven not to change routing, stage coverage, grounded
  evidence, Workload Boundary result, report contract, or target immutability.

## Out of scope

- New pipeline behaviour, new report fields, reference-rule changes, or a
  rewrite for style.
- Removing target safety, active-stage routing, output routing, or any rule
  without a tested runtime owner.

## Acceptance criteria

- Each removed unit has a passing mapped deletion test and a recorded baseline
  comparison.
- Each retained unit has a documented behavioural reason or inconclusive test;
  it is not removed speculatively.
- Summary and Detailed contract checks remain unchanged except for intended
  text removals that have no observed behaviour impact.
- The final provider-backed acceptance comparison preserves target immutability
  and all required evidence and boundary findings.

## Commit boundary

Commit the deletion record, final public-text removals, and their focused tests
together. Do not make subsequent feature changes in this milestone.
