# VS-027 — Golden-set fixtures for the Workload Unit boundary rule

## Outcome

`references/workload-boundary.md`'s Primary/Supporting rule is measured
against at least two purpose-built fixture repositories — one that should
merge into a single Workload Unit, one that should split into two — instead
of remaining unverified against anything but the single-service JPetStore 6
golden set, which never exercises a genuine multi-process split.

## Why this is a vertical slice

`references/workload-boundary.md` (commit `5cd7d3a`, 2026-08-07) is new and,
as of this ticket, has no golden-set or fixture coverage: JPetStore 6
(`tests/evaluation/jpetstore-6-golden.md`) is a single Java web application
with an embedded database — it never presents a candidate second process, so
no existing golden run has ever exercised the Primary rule's split-or-merge
judgment end to end. The ADK-repo review this project's Summary/Detailed
architecture was compared against proposed exactly this style of fixture
(Case A: API + shared library that must not split; Case B: API + worker in
one source root that must split) as the way to turn "the rule reads
correctly" into "the rule decides correctly." Without it, `VS-025`'s Summary
wiring and the existing Detailed wiring both rest on an unverified rule.

## Status and dependencies

- **Status:** Proposed.
- **Depends on:** `references/workload-boundary.md` (landed). Benefits from
  VS-025 landing first so both Summary and Detailed can be scored against
  the same fixtures, but does not strictly require it — Detailed alone can
  be scored first.
- **Blocks:** PIPE-005's provider-backed acceptance runs after the static
  fixtures and golden rubrics are committed. The live repetitions and
  scorecard remain a final VS-027 completion step after PIPE-005 exposes the
  trusted runtime path.

## Read first

- `references/workload-boundary.md` — the rule and its six contrastive
  examples, which already suggest fixture shapes.
- `tests/evaluation/jpetstore-6-golden.md` — the existing golden-set rubric
  format to match.
- The ADK-repo review's Case A/B/C fixture descriptions (conversation
  context, not a repository file) for the fixture shapes this ticket adapts:
  API + shared library (must not split), API + worker sharing one source
  root (must split), and a one-shot migration script (must not be modeled as
  a long-running Workload Unit).

## Scope

### In scope

- Build two minimal fixture repositories (or reuse/extend an existing
  `demo-repositories/*` fixture if one already fits) under
  `demo-repositories/` or `tests/fixtures/`, following whatever convention
  `demo-repositories/jpetstore-6` already established for golden-set targets:
  - **Case A (must not split):** one process with `controller/`, `service/`,
    `repository/`-style internal layering under a single start command —
    the reference's own second contrastive example, made concrete as a real
    fixture.
  - **Case B (must split):** two runtime processes in one source root or
    directory (e.g. `node server.js` / `node worker.js`, or a Python
    `app.py` / `worker.py` pair) with distinct start commands and no shared
    lifecycle — the reference's first contrastive example, made concrete.
- Write a golden-set rubric entry for each (matching
  `jpetstore-6-golden.md`'s format) stating the expected component count and
  the expected boundary evidence/reasoning.
- Run Detailed mode (and Summary mode, if VS-025 has landed) against both and
  score the actual output against the expected boundary decision.
- Record Workload Unit boundary precision/recall as an explicit scored
  dimension, not folded into an unrelated existing dimension.

### Out of scope

- A third fixture for the one-shot-Job case (`migrate.py`) or the
  external-dependency case (Case C/D from the ADK-repo review) — worth a
  follow-up ticket once Cases A/B establish the pattern, not required to
  ship this one.
- Any change to `references/workload-boundary.md` itself unless a fixture
  run reveals the rule gives a wrong answer, in which case fixing the rule
  becomes its own follow-up, not silently folded into this ticket.

## Implementation steps

1. Build Case A and Case B fixture repositories.
2. Write their golden-set rubric entries.
3. Commit the fixtures and golden rubrics before PIPE-005 begins.
4. Run Detailed (and Summary, if available) against both, at least 3 repeats
   each per this project's existing live-verification convention after PIPE-005.
5. Score and record results; file a follow-up ticket immediately if either
   case's boundary decision is wrong, rather than adjusting the rule inline.

## Acceptance criteria

- Both fixtures exist and are read-only-safe (no scripts, builds, or
  installs required to analyze them, matching this project's target-safety
  rules).
- Both golden-set rubric entries exist with an explicit expected component
  count and expected boundary evidence.
- Before PIPE-005: the static fixtures and golden rubrics are committed.
- At ticket completion: at least 3 live repeats per case per mode tested,
  `PASS`, target unchanged.
- `python scripts/run_quality_gate.py` passes.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-detailed --repository-root <case-a-fixture> --repeat 3 --output-dir <dir>
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-detailed --repository-root <case-b-fixture> --repeat 3 --output-dir <dir>
```

## Expected file changes

- New fixture repositories under `demo-repositories/` or `tests/fixtures/`
- New or extended golden-set rubric file(s) under `tests/evaluation/`
- A new scorecard file recording the live results, following
  `jpetstore-6-summary-json-first-scorecard.md`'s format

## Commit boundary

- Commit fixtures and their golden-set rubric together.
- Commit the live-run scorecard as a separate follow-up commit once results
  are in, matching this project's "measure, then record" pattern elsewhere
  in `docs/development/daily/2026-08-07/`.

## Codex execution instruction

```text
Implement only VS-027. Read references/workload-boundary.md's contrastive
examples and tests/evaluation/jpetstore-6-golden.md's rubric format first.
Build exactly two fixtures (Case A: must-not-split, Case B: must-split) as
scoped above -- do not add the deferred Case C/D fixtures. Score at least 3
live repeats per case. If either case's boundary decision is wrong, file a
follow-up ticket rather than editing references/workload-boundary.md in this
pass. Run the quality gate and report the result.
```
