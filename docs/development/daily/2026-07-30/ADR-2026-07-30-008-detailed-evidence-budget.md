# ADR-2026-07-30-008: Bound Detailed exploration by evidence slots and candidate count

- Status: Accepted
- Date: 2026-07-30
- Related work: [Detailed evidence-budget ticket list](TICKET-LIST-2026-07-30-005-detailed-evidence-budget.md)
- Evidence baseline: [JPetStore 6 Detailed golden set](../../../../tests/evaluation/jpetstore-6-detailed-golden.md)

## Context

Detailed analysis must produce a usable, complete report without treating an
unbounded repository walk as evidence quality. In the JPetStore 6 interactive
E2E, the agent gathered relevant repository evidence but exhausted its step
budget before returning a Detailed report. Its progress summary and tool reads
could not be used as a migration-design deliverable. A later 24-step rerun
returned a complete report, but scored 59/100 against an independent golden
set: it missed or overstated execution, state, security, compatibility, and
dependency findings.

The existing global cap of 16 files gives no representation guarantee for a
multi-service repository. It can spend too much of the budget on common files
or low-signal files and leave a deployable candidate without its execution or
configuration evidence. Conversely, a fixed cap makes a single-candidate
repository needlessly expensive when its essential evidence is already known.

The failure is not solved by allowing arbitrary exploration. The agent needs a
bounded way to preserve the evidence needed by every candidate and to finish
the report when additional reads are unlikely to change a decision.

## Decision

1. Detailed-mode exploration uses a candidate-count budget of `7 + candidate
   count × 4` files, capped at 36 files. The budget is calculated after
   deployable candidates are identified.
2. The slots are allocated as follows:
   - six shared execution, deployment, or operations configuration files;
   - one repository-context file, such as a README;
   - two execution-evidence files per candidate; and
   - two configuration or dependency-evidence files per candidate.
3. Immediately after candidate identification, the agent creates the internal
   eight-section Detailed-report skeleton. Each evidence slot must conclude as
   `confirmed`, `conflicting`, or a scoped `unknown`; report completion takes
   priority over low-signal additional exploration.
4. Lockfiles are excluded by default. The agent stops optional exploration when
   the available file is low signal and cannot materially resolve a report
   slot, blocker, conflict, dependency, or candidate classification.
5. The budget is a selection and stopping rule, not permission to invent
   evidence. Facts remain repository-supported; inferences and unknowns remain
   labelled according to the Skill's evidence policy.

## Consequences

### Positive

- A single candidate receives a compact 11-file target budget, while a
  five-candidate repository receives 27 slots with four reserved for each
  candidate. The 36-file cap remains a hard upper bound for larger systems.
- Every candidate has a minimum path to execution and dependency/configuration
  evidence, reducing accidental omission in MSA analysis.
- The eight-section skeleton makes a complete final report possible even when
  an evidence item is unresolved, provided the uncertainty is scoped and
  explained.
- Completion and accuracy can be evaluated separately against independent
  golden sets.

### Costs and limits

- A candidate may still need a scoped unknown when the repository does not
  contain enough evidence; the budget does not make the deployment decision
  known.
- A large repository may have more plausible files than the cap permits. The
  agent must choose files that directly discharge evidence slots and report
  what remains unresolved.
- The agent instructions, Detailed checklist, contract tests, fixtures, and
  acceptance evaluation need coordinated changes.

## Rejected alternatives

- **Keep the global 16-file limit.** It has no per-candidate representation
  guarantee and is insufficient for the observed MSA shape.
- **Use repository-specific allowlists.** They would not generalize and would
  turn a reusable Skill into a collection of target-specific policies.
- **Add a separate planner, agent, or validator.** The problem is a bounded
  evidence-selection contract inside the existing Detailed flow; another
  runtime role would add context and coordination cost without improving the
  evidence itself.
- **Permit unlimited exploration before reporting.** This repeats the
  JPetStore low-signal exploration failure and makes completion depend on
  repository size rather than decision-relevant evidence.

## Guardrails

- Do not use Markdown tables in the Detailed final-report contract introduced
  by this work; retain the established compact Markdown form.
- Keep the existing step limit. This ADR changes how steps choose evidence, not
  the maximum number of tool actions.
- Do not introduce repository-specific allowlists or separate planner, agent,
  or validator processes.
- Provider-backed E2E remains subject to the detached `tmux`, isolated runtime,
  and before/after target Git-status procedure.

## Follow-up

Implement the decision through `DET-001` through `DET-003` in the related
ticket list. Do not claim the budget improves correctness until the independent
golden-set scorecards record both completion and fact-accuracy results.
