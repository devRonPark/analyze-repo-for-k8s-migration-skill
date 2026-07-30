# TICKET-LIST-2026-07-30-005: Detailed evidence-budget vertical slices

- Status: Planned; not active until `current/focus.md` selects this list.
- Governing decision: [ADR-2026-07-30-008-detailed-evidence-budget.md](ADR-2026-07-30-008-detailed-evidence-budget.md)
- Evaluation baseline: [JPetStore 6 Detailed golden set](../../../../tests/evaluation/jpetstore-6-detailed-golden.md)

## Goal

Make Detailed analysis finish a complete, evidence-disciplined eight-section
report within a bounded exploration budget. The change must retain factual
accuracy for both a single application and a multi-service repository.

## Scope boundary

These tickets change the existing Detailed agent instructions, checklist,
contracts, tests, fixtures, and evaluation material. They do not add
repository-specific allowlists, a separate planner/agent/validator, a new
output mode, a higher step limit, or Markdown tables in the final report.

## DET-001 — Evidence slots and completion-first Detailed contract

### User value

When exploration cannot resolve every question, the user still receives a
complete eight-section Detailed report with each evidence slot clearly
identified as confirmed, conflicting, or scoped unknown.

### Work

- Add shared evidence slots, terminal states, and skeleton-first sequencing to
  the Detailed agent instructions and checklist.
- Require the internal eight-section report skeleton immediately after
  candidate identification.
- Define how a slot becomes `confirmed`, `conflicting`, or scoped `unknown`,
  including the evidence or missing evidence that supports that state.
- Add contract tests that reject an unterminated slot and an incomplete
  eight-section Detailed report.
- Preserve the existing Detailed final-report title, Korean user-visible
  headings, and evidence-discipline rules.

### Acceptance criteria

- Every required evidence slot reaches exactly one terminal state.
- A Detailed report contains all eight required sections even when one or more
  slots remain scoped unknown.
- Conflicting evidence names both sides and does not silently select one as a
  fact.
- An unknown identifies its candidate or shared scope and what decision it
  prevents or leaves open.
- The JPetStore 6 Detailed interactive E2E ends in a complete final Markdown
  report and leaves the target Git status unchanged.

### Verification

- Run focused contract and report-validator tests.
- Run the applicable quality gate.
- Run the documented detached-`tmux` provider E2E for JPetStore 6 with
  approved network permission, an isolated runtime, and before/after target
  Git-status capture.
- Retain the final report as E2E diagnostic evidence only; score it through
  `DET-003` rather than treating tool reads as credit.

## DET-002 — Candidate-count, file-kind exploration budget

### User value

A single application completes quickly, while every service in an MSA receives
minimum execution and configuration/dependency evidence before the agent stops.

### Work

- Implement the Detailed budget `7 + candidate count × 4`, capped at 36
  files.
- Reserve six shared execution/deployment/operations slots, one context slot,
  two execution slots per candidate, and two configuration/dependency slots
  per candidate.
- Exclude lockfiles by default, allowing one only when it is the direct,
  material evidence for an unresolved slot.
- Add a low-signal stop rule: do not read an optional file that cannot
  materially resolve a candidate classification, report slot, conflict,
  blocker, or dependency.
- Add deterministic fixtures for one candidate and five MSA candidates.

### Acceptance criteria

- The one-candidate fixture calculates an 11-file budget.
- The five-candidate fixture calculates a 27-file budget and reserves four
  candidate-specific slots for every candidate.
- Any candidate count whose formula exceeds 36 is capped at 36.
- A candidate cannot complete without its minimum execution and
  configuration/dependency evidence, or an explicit scoped unknown for the
  unavailable evidence.
- Lockfiles do not consume a normal budget slot by default.

### Verification

- Add focused deterministic tests for budget calculation, slot allocation,
  lockfile exclusion, low-signal stopping, and candidate coverage.
- Run the affected unit/contract tests and the applicable quality gate.
- Run a Detailed E2E against the five-candidate food-delivery structure using
  the detached-`tmux` procedure and capture pre/post target Git status.

## DET-003 — Detailed final-report golden-set regression evaluation

### User value

The user can see that bounded exploration improves report completion without
silently reducing factual usefulness or overstating Kubernetes decisions.

### Work

- Prepare independent static-evidence golden sets and weighted scorecards for
  JPetStore 6 and the food-delivery structural target before loading the Skill
  or running either target.
- Record target path, immutable revision, evidence date, required findings,
  blockers, and unknowns in each golden set.
- Compare only the interactive E2E final report against its golden set; never
  award credit for transcript tool reads or assistant progress messages.
- Score report completion and contract structure, candidate coverage,
  execution/build/runtime/network facts, state/dependencies,
  configuration/security/compatibility risks, and evidence discipline/decision
  usefulness.

### Acceptance criteria

- Both targets have an independent golden set and scorecard stored under
  `tests/evaluation/`.
- Both final reports satisfy 100% of the required Detailed report structure.
- Each target scores at least 90/100 overall.
- Every deduction names the missing, conflicting, or unsupported finding and
  its repository evidence.
- Each E2E record includes unchanged pre/post target Git status; a changed
  target, tool error, incomplete final response, or invalid report fails the
  evaluation.

### Verification

- Review golden sets independently before each E2E run.
- Run both provider-backed Detached-`tmux` E2Es with approved network
  permission and isolated runtime directories.
- Validate the final Markdown reports directly, then retain their session
  capture only as diagnostic evidence.
- Run the applicable quality gate after evaluation fixtures and harness changes.

## Delivery order and commit boundary

Implement and commit each ticket independently in this order:

```text
DET-001 evidence-slot completion contract
  → DET-002 candidate-count exploration budget
  → DET-003 golden-set regression evaluation
```

Each commit contains that ticket's instructions or contract changes, tests,
fixtures, and the relevant E2E evidence. Provider E2E uses only the permission
needed for the specific local-LLM command and follows the repository's
detached-`tmux` procedure.
