# PIPE-006 — Prune no-op Skill text after complete pipeline verification

## Static MCP Stage Skills amendment

This ticket is superseded by the terminal checks in Ticket 12 of Static MCP
Stage Skills. The scan includes bundled Skill roots, Python runtime, launcher,
client fragments, copy/install scripts, and acceptance harnesses. It rejects
any delivered .ts, .js, Node, or Bun analysis-runtime artifact.

## Outcome

Reduce `SKILL.md` and the public Agent/command text to the smallest behaviour-
preserving form. This is the final task of the trusted-pipeline milestone.

## Depends on

- PIPE-003's deletion inventory
- PIPE-005 complete
- VS-027 static and live evaluation complete

## In scope

- One-at-a-time deletion tests for public Skill and Agent/command passages.
- The deletion test procedure is fixed for every candidate: (1) select one
  suspicious instruction unit, (2) remove it completely in an isolated copy,
  (3) rerun the same agent scenario and inspect behaviour and output, and (4)
  compare the post-deletion result with the recorded baseline. Remove the unit
  permanently only when the comparison shows no behaviourally meaningful
  difference; otherwise restore it and retain it with the observed reason.
- A committed deletion record that maps each candidate passage to its claimed
  responsibility, deterministic checks, acceptance scenario, result, and
  retain/remove decision.
- Removal only for units proven not to change routing, stage coverage, grounded
  evidence, Workload Boundary result, report contract, or target immutability.
- Terminal artifact scans over the installed package, launchers, configuration,
  harnesses, and copied runtime files to prove that no supported path still
  references `.ts`, `.js`, Node, or Bun before legacy deletion.

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
- The terminal artifact scan passes and proves TypeScript artifact deletion is
  safe for every supported installation and acceptance path.

## Required deletion-test record

For each candidate, record before editing: immutable Skill revision, candidate
text location, exact baseline prompt/scenario, tool-read receipt, grounded
evidence IDs, Workload Boundary decision, rendered report, target Git status,
and the acceptance assertions used for comparison. The isolated post-deletion
run must use the same prompt, target revision, provider configuration, and
scenario. Compare routing, mandatory-reference grounding, evidence-to-decision
provenance, minimum deployable unit, Summary/Detailed contract, uncertainty,
and target immutability. A textually similar report is insufficient if any of
these behavioural fields differ.

## Execution order

1. Complete PIPE-005 and VS-027 static/live gates and freeze the baseline.
2. Build the candidate inventory from PIPE-003; do not preselect removal based
   on wording alone.
3. Run the four-step deletion test above one candidate at a time, committing
   only the final deletion record and proven removals at the ticket boundary.
4. Run the final provider-backed acceptance comparison and verify unchanged
   target Git status.
5. Only after all pipeline gates pass, run the terminal no-op deletion sweep on
   any remaining public-text candidates; no later feature work is allowed.

## Commit boundary

Commit the deletion record, final public-text removals, and their focused tests
together. Do not make subsequent feature changes in this milestone.
