# VS-025 — Wire the Workload Unit boundary decision into Summary mode

## Outcome

Summary mode's `components` array reflects the same Workload Unit boundary
judgment `references/workload-boundary.md` already defines for Detailed mode
(distinct start command AND independent lifecycle both required to split one
process into two candidates) — instead of the model splitting or merging
deployment candidates by its own unstated judgment.

## Why this is a vertical slice

`references/workload-boundary.md` (added 2026-08-07, commit `5cd7d3a`) is
loaded only for an explicit Detailed request:
`runtime/agents/kubernetes-migration-analyzer.md:161` — `"For an explicit
Detailed request, load ... references/workload-boundary.md (when more than
one runtime process or start command is plausible)."` Summary's own contract
section never mentions it (`runtime/agents/kubernetes-migration-analyzer.md`'s
`## Summary JSON contract`, immediately above).

But Summary's `components` array makes exactly the judgment this reference
exists to constrain: how many `배포 대상 후보` entries a repository with more
than one runtime process produces
(`runtime/agents/kubernetes-migration-analyzer.md`'s `components` field
description). Today that count is decided by the model's unaided judgment in
Summary, the same failure mode the reference was written to close for
Detailed. This is the concrete gap between the ADK-repo review's "Deployment
Unit Modeling" critique and this project's actual Summary contract, not a
speculative one.

## Status and dependencies

- **Status:** Proposed — not yet scoped in detail or implemented.
- **Depends on:** `references/workload-boundary.md` (already landed).
- **Blocks:** [VS-027](VS-027-workload-boundary-golden-fixtures.md) — its
  fixtures need something in Summary mode to measure against.

## Read first

- `references/workload-boundary.md` — the rule itself.
- `runtime/agents/kubernetes-migration-analyzer.md`'s `## Summary JSON
  contract` section and its Detailed-mode reference-loading sentence (line
  ~161) — where the wiring gap is.
- `docs/development/tickets/VS-020-summary-v2-field-coverage.md`'s "Decision
  outcome" — the precedent for routing a Summary finding through the existing
  `missing_inputs` channel instead of a schema/renderer change; read before
  assuming this ticket needs a schema change.
- `schemas/analysis-result.schema.json:148` (`component` def) and `:17`
  (`missing_inputs`) — confirm there is no field today for "why N components
  instead of N-1" reasoning.

## Scope

### In scope

- Decide when Summary should load `references/workload-boundary.md`: always,
  or conditionally on the same "more than one runtime process or start
  command is plausible" signal Detailed already uses. Prefer the conditional
  form if it can reuse the same signal cheaply — Summary's budget is tighter
  than Detailed's.
- Decide where the boundary reasoning surfaces in Summary's output. Follow
  the VS-020 precedent: check whether the existing `missing_inputs`
  (`open_design_decision` classification) or a component's `evidence` array
  can carry "split because X has its own start command and lifecycle" or
  "not split — 미확인, no independent start command found" before proposing
  a schema change. Only add a schema field if neither existing channel can
  express it.
- Update the agent prompt's Summary section and worked example accordingly.

### Out of scope

- Changing Detailed mode's existing wiring or the reference file's rules.
- A new `boundary_decision` object with `reason_codes` (the ADK-repo
  report's proposed shape) unless the VS-020-style existing-channel routing
  is tried first and found insufficient.
- VS-026 and VS-027 (separate tickets).

## Implementation steps

1. Confirm the conditional-load signal and whether Summary's existing
   `missing_inputs`/`evidence` channels can carry the reasoning (the VS-020
   read-first item above).
2. Update `runtime/agents/kubernetes-migration-analyzer.md`'s Summary
   contract section and worked example.
3. Re-run the JPetStore 6 Summary scenario and compare `components` count
   and any component split/merge decisions against the pre-change baseline
   (`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`).
4. If a repository with a genuine multi-process split is available (a
   fixture close to VS-027's Case B), verify the boundary decision is
   evidenced rather than assumed.

## Acceptance criteria

- Summary mode's component count/split decision is evidenced by a start
  command and lifecycle signal (or explicitly `미확인`), not asserted without
  a `근거:`/`reference`.
- No regression in the JPetStore 6 Summary golden-set score
  (`tests/evaluation/jpetstore-6-golden.md`).
- `python scripts/run_quality_gate.py` passes.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root demo-repositories/jpetstore-6 --repeat 3 --output-dir <dir>
```

## Expected file changes

- `runtime/agents/kubernetes-migration-analyzer.md`
- `schemas/analysis-result.schema.json` (only if step 1 finds existing
  channels insufficient)
- `tests/` (prompt/contract regression coverage)

## Commit boundary

- Land the scoping decision (step 1) as a short note in this ticket before
  changing the prompt, per the VS-020/VS-023 precedent of separating the
  decision from the implementation.
- Commit the prompt/schema change and its tests together; do not bundle with
  VS-026 or VS-027.

## Decision outcome (2026-08-07)

Step 1 (scoping) resolved before touching the prompt, per the commit-boundary
note above.

**Conditional-load signal:** reuse the same signal Detailed already uses —
"more than one runtime process or start command is plausible" — rather than
always loading the reference. `references/workflow.md:47-51` already states
this policy in general terms for both modes; the gap is narrower than the
ticket's "Why this is a vertical slice" section implies: only the operative
`runtime/agents/kubernetes-migration-analyzer.md` prompt's explicit
Detailed-only load sentence (line ~155-161) needed extending to Summary.

**Routing:** the existing `missing_inputs` channel is sufficient; no schema
change. `schemas/analysis-result.schema.json:17`'s top-level `missing_inputs`
is already `{"type": "array", "items": {"type": "object"}}` — untyped, so it
accepts a new `classification: "open_design_decision"` entry describing an
unresolved boundary today, with zero schema edits. This is the same
VS-020-style routing: extend the prompt's instructions, not the contract.

- When the primary rule (distinct start command AND independent lifecycle)
  resolves a split or a merge, no new channel is needed: each resulting
  component's own `fields.운영 기동 명령` entry (and its `evidence`) already
  carries the start-command citation the Summary contract requires per
  component. The count of `components` entries *is* the evidenced decision.
- When runtime-process or lifecycle evidence is insufficient to decide split
  vs. merge, route it through `missing_inputs` as `classification:
  open_design_decision`, `status: 미확인`, with a `검색(...)` reference
  scoped to where a distinct start command or lifecycle signal was checked
  for and not found. This mirrors how `references/workload-boundary.md`
  itself defines the `미확인` case.

No `boundary_decision`/`reason_codes` object (the out-of-scope ADK-repo shape)
is needed; the existing-channel routing above expresses both the resolved and
unresolved cases.

## Codex execution instruction

```text
Implement only VS-025. Read references/workload-boundary.md and
runtime/agents/kubernetes-migration-analyzer.md's Summary contract section
first. Before touching the schema, check whether Summary's existing
missing_inputs or component evidence channel can carry the boundary
reasoning (see VS-020's decision outcome for the pattern) -- only add a new
schema field if neither can express it. Re-run the JPetStore 6 Summary
scenario and compare against the existing golden-set score. Run the quality
gate and report the result.
```
