# VS-024 — Port Detailed mode to the JSON-first render/validate/repair pipeline

## Outcome

Detailed mode stops having the Agent free-write the entire ~70–130 line
Markdown report by hand. Instead, the Agent emits structured JSON (like
Summary already does per ADR-2026-08-07-001), a new deterministic
`render_detailed.py` turns that JSON into the exact required
`assets/migration-assessment-template.md` shape (all eight `##` headings
verbatim, the `### 배포 대상: <이름>` component-card format with its four
`####` subsections, `### Dependency matrix` / `### Text dependency graph`,
`### 설계 차단 항목`, and a single machine-checkable `- 판정:` line — never a
Markdown table, which the template explicitly forbids), and the existing
`retain_summary_markdown_with_repair`-style repair loop (ADR-2026-08-07-002)
retries a named validation failure in the same session instead of the whole
run being scored as non-compliant.

## Why this is a vertical slice

`tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md`
(today's measurement) ran the current free-written-Markdown Detailed path
four times (3 batch `--format json`, 1 interactive `--interactive`) against
`jpetstore-6` pinned to the golden set's revision. All four were content-wise
substantially correct (the `tomcat9`/`tomcat90` conflict, the Java 17/`openjdk:25`
mismatch, embedded HSQLDB, and redacted Secret-shaped seed data were found in
most runs) but **none matched the required template structure**:
`scripts/validate_report.py --mode detailed` failure counts were 32, 18, 20,
and 36 — none produced the required literal section headings, the component
card format, or a `- 판정: <value>` bullet the validator's regex can match;
one run even emitted a heading in English (`## 1. Target Scope`) and used
Markdown tables the template forbids.

This is exactly the failure mode Summary mode already solved. Per
`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`'s VS-020
section, moving Summary from free-written Markdown to JSON + a deterministic
renderer (DEL-002/DEL-003, ADR-2026-08-07-001) is what made Summary's report
*shape* reliable — the renderer, not the prompt, now guarantees headings,
bullet format, and verdict placement. Detailed mode never received the same
treatment; `DET-004`–`DET-009` (see `status.md`) improved the free-written
path's compliance through iterated *instructions* alone and plateaued around
7 validator failures on a good run (`jpetstore-6-detailed-scorecard.md`'s
DET-008/DET-009) — still nonzero, and today's measurement shows the
free-written path can regress far below that (18–36 failures) without any
Detailed-specific prompt change having been made. A deterministic renderer
removes the entire class of error the instruction-only approach could not:
the Agent no longer decides what the headings/table-vs-bullet/verdict-line
text looks like.

**This does not fix everything found today.** The interactive run in the
same evaluation file found a *different*, more serious problem: two
blocker-level claims cited `docker-compose.yaml:17`/`docker-compose.yaml:21`
(a Compose version string and a `container_name` line) where
`Dockerfile:17`/`Dockerfile:21` was actually intended — a real `file:line`,
just the wrong file, repeated 4× and 3× for two different claims in one
report. A deterministic renderer faithfully reproduces whatever the JSON
says; it cannot detect that the *content* of a field is a wrong citation.
That is the same evidence-sourcing risk VS-023 targets (`locate_evidence`),
not this ticket's scope — see "Out of scope" below and the note in
`focus.md` this ticket should add a pointer to.

## Status and dependencies

- **Status:** Scoped, not started. No code written. This is a handoff for a
  separate implementation session.
- **Depends on:**
  - [ADR-2026-08-07-001](../daily/2026-08-07/ADR-2026-08-07-001-summary-delivery-structured-output.md) — the JSON-only delivery decision this ticket extends to Detailed mode.
  - [ADR-2026-08-07-002](../daily/2026-08-07/ADR-2026-08-07-002-summary-validate-and-repair-loop.md) — the repair-loop pattern this ticket reuses.
  - [VS-020](VS-020-summary-v2-field-coverage.md) — precedent for how much a renderer change alone can move a golden-set score (58→84) without touching the schema; read before assuming a schema extension is the only lever.
- **Blocks:** None directly, but `DET-010`–`DET-014` (`focus.md`'s "Deferred, still open") target the free-written Detailed path's remaining golden-set deductions — if this ticket lands first, re-triage whether those tickets still apply to a JSON-first Detailed report or should be closed/rewritten against the new path.
- **Related, not a dependency:** [VS-023](VS-023-migration-evidence-sensor-tools.md) — the wrong-file-citation finding above is the same evidence-sourcing risk class VS-023's `locate_evidence` targets. Worth checking whether the interactive run's wrong-file citations were `locate_evidence`-sourced or hand-written before assuming this needs new work; if they were hand-written, VS-023's existing "every citation must come from `locate_evidence`" prompt rule may already be the fix, just not yet verified for Detailed mode specifically.

## Read first

- `tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md` — today's failure evidence (validator counts, the English heading, the forbidden tables, the wrong-file citations) that motivates this ticket.
- `assets/migration-assessment-template.md` — the exact Markdown shape a `render_detailed.py` must produce. Note the "no Markdown tables," "one candidate card per repeated `###` block," and single-line keyed-field formats (`- 키: 값 — 상태: ... / 근거: ...`) — these are exactly what free-written output keeps getting wrong.
- `scripts/render_summary.py` — the precedent renderer. Detailed's renderer should follow the same shape (pure function, JSON in, contract Markdown out) but will be materially larger: Detailed has repeated per-candidate cards, a dependency matrix *and* a text graph that must agree, and keyed blocker/minimum-input formats Summary doesn't have.
- `schemas/analysis-result.schema.json` — **already has a `mode: detailed` variant** (`oneOf` requires `dependencies` in addition to Summary's fields), but its `component`/`dependency` `$defs` are still Summary-shaped (a `component` is just `name`/`evidence`/`containerization`/`configuration_timing`; a `dependency` is just `source`/`target`/`evidence`). Neither captures Detailed's actual required structure: per-candidate `실행 정보` (13 fields)/`설정과 상태` (6 fields)/`Kubernetes 최소 설계 입력` (8 fields)/`최소 입력 누락` (keyed, with `범위:`/`결정:` for each `미확인` entry), the dependency matrix's ~11 keyed fields per edge, or blockers' `범주:`/`영향 범위:` fields. **This schema needs real extension, not just a renderer.**
- `scripts/report_contract.py` — `validate_json_payload` already branches on `mode == "detailed"` for the summary/detailed `oneOf`, but has no Detailed-specific field-level checks analogous to what `summary_v2_errors`/`evidence_semantic_errors` do for Summary Markdown today.
- `scripts/validate_report.py` — the current Markdown-contract validator Detailed reports are scored against (`detailed_evidence_slot_errors`, `design_blocker_format_errors`, `mode_specific_errors`, etc.); a JSON-first Detailed path still needs the rendered Markdown to pass this, same as Summary does today.
- `runtime/agents/kubernetes-migration-analyzer.md` — currently instructs Detailed mode to write Markdown directly; needs the same "JSON only, no fence, no prose" instruction Summary already has, adapted to the new/extended schema.
- `scripts/run_opencode_acceptance.py`'s `retain_summary_markdown_with_repair` / `retain_summary_markdown` — the repair-loop and render/validate/finalize pipeline to generalize (or parallel) for Detailed's `report_mode: "detailed"` cases (`slash-detailed`, `explicit-detailed` in `tests/evaluation/opencode-cases.json`).

## Scope

### In scope

1. Extend `schemas/analysis-result.schema.json`'s Detailed `component`/
   `dependency` `$defs` (or add Detailed-specific `$defs`) to cover every
   field `assets/migration-assessment-template.md` requires per candidate
   card, dependency-matrix edge, minimum-input slot, and blocker — including
   the keyed `범위:`/`결정:` requirement on `미확인` minimum inputs and
   `범주:`/`영향 범위:` on blockers.
2. Write `scripts/render_detailed.py` (pure function, JSON payload in,
   contract Markdown out — no side effects, same shape as `render_summary.py`),
   producing exactly the template's eight `##` headings, repeated `###
   배포 대상: <이름>` cards with all four `####` subsections, `###
   Dependency matrix` / `### Text dependency graph` (kept in sync from the
   same JSON data — no separate free-text graph the Agent could get out of
   sync with the matrix), `### 설계 차단 항목`, and a single `- 판정: <value>`
   line. No Markdown tables anywhere in the output.
3. Extend `scripts/report_contract.py`'s `validate_json_payload` with
   Detailed-specific field checks mirroring what `summary_v2_errors` /
   `evidence_semantic_errors` do for Summary today (every `evidence` has a
   real `status`/`reference`; `미확인` minimum-input entries carry scope/decision;
   blockers carry category/impact).
4. Update `runtime/agents/kubernetes-migration-analyzer.md`'s Detailed
   instructions to emit JSON only against the extended schema, the same way
   its Summary instructions already do.
5. Generalize `run_opencode_acceptance.py`'s `retain_summary_markdown` /
   `retain_summary_markdown_with_repair` (or add parallel
   `retain_detailed_markdown[_with_repair]` functions) so `report_mode:
   "detailed"` cases go through render → `validate_report.py --mode detailed`
   → repair-on-named-failure → finalize, the same as Summary.
6. Add unit tests for `render_detailed.py` (fixture JSON in, expected
   contract-compliant Markdown out, including a case with multiple candidate
   cards and a case with a `상충됨` dependency) and for the new schema/
   `validate_json_payload` checks.
7. Re-run `tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md`'s
   same measurement procedure (3 batch repeats minimum) against the new
   JSON-first Detailed path and record a comparable before/after table,
   the same way VS-020's section does for Summary.

### Out of scope

- Fixing the wrong-file citation problem found in the interactive run
  (`docker-compose.yaml:17`/`:21` cited for Dockerfile-sourced claims). That
  is a content-accuracy problem a renderer cannot fix; it belongs with
  VS-023 evidence-sourcing work, not this ticket. Do not attempt a citation-
  correctness fix as part of this ticket — file it separately if the
  `locate_evidence`-sourced-or-hand-written question above turns up a real
  gap.
- Retriaging or closing `DET-010`–`DET-014` — note in this ticket's outcome
  whether they still apply, but let a human decide whether to close/rewrite
  them; don't do it unilaterally as a side effect.
- Changing the Detailed line/word budget (70 lines / 1,200 Korean words) or
  any other content policy in `assets/migration-assessment-template.md` —
  the renderer must fit the existing template, not redesign it.
- The interactive-vs-batch harness gap noted in today's evaluation file
  (no real `tmux` available on this Windows machine). Not this ticket's
  problem to solve; re-run whatever measurement this ticket needs through
  whichever harness is available at implementation time.

## Implementation steps

1. Read the "Read first" list above in full, especially
   `assets/migration-assessment-template.md` and today's evaluation file's
   exact failure list, before touching the schema — the schema extension
   should be driven by the template's real required fields, not guessed.
2. Extend `schemas/analysis-result.schema.json`'s Detailed `$defs`.
3. Write `render_detailed.py` and its unit tests against the extended schema.
4. Extend `report_contract.py`'s `validate_json_payload` and its tests.
5. Update the agent prompt's Detailed instructions.
6. Wire the harness's render/validate/repair path for `report_mode:
   "detailed"` cases.
7. Run `python scripts/run_quality_gate.py`.
8. Live-verify: re-run the acceptance harness against `jpetstore-6` (pinned
   revision `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, matching the golden
   set) for the `slash-detailed` case, at least 3 repeats, and record
   `validate_report.py` failure counts and the rubric score from today's
   evaluation file's procedure, before/after, in this ticket's "Decision
   outcome" section (append, following the VS-023 ticket's pattern — do not
   overwrite today's evaluation file, add a new dated one or a new section).

## Acceptance criteria

- `render_detailed.py` output passes `scripts/validate_report.py --mode
  detailed --repo-root <target>` with **zero** failures on well-formed input
  JSON (a renderer bug, not a model content problem, if this fails).
- A live `slash-detailed` run's rendered report also passes
  `validate_report.py` with zero or near-zero failures (allow for the model
  still occasionally emitting invalid JSON the repair loop has to fix, same
  tolerance Summary has today) across at least 3 repeats against the pinned
  `jpetstore-6` revision.
- The golden-set rubric score (`tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md`'s
  method, or `jpetstore-6-detailed-scorecard.md`'s six-dimension method) is
  measurably higher than today's 58–65/100 range on the structure/contract
  dimension specifically — content-accuracy dimensions may not move, since
  this ticket doesn't touch content generation.
- `python scripts/run_quality_gate.py` passes.
- No Markdown table appears in any rendered Detailed output.

## Verification commands

```bash
python scripts/run_quality_gate.py
python -m pytest tests/ -k render_detailed
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-detailed --repository-root <jpetstore-6 clone @ e1dd9a31d1cef68793cd0933ae06898e6fcfa807> --repeat 3 --timeout 900 --output-dir <scratch dir>
python scripts/validate_report.py <rendered report.md> --mode detailed --repo-root <jpetstore-6 clone>
```

## Expected file changes

- `schemas/analysis-result.schema.json`
- New `scripts/render_detailed.py` + tests
- `scripts/report_contract.py` + tests
- `runtime/agents/kubernetes-migration-analyzer.md`
- `scripts/run_opencode_acceptance.py` (render/validate/repair wiring for `report_mode: "detailed"`)
- New dated `tests/evaluation/jpetstore-6-detailed-*.md` recording the before/after measurement

## Commit boundary

- Schema + renderer + renderer tests can land as one commit (the pure,
  independently-testable layer).
- Prompt change + harness wiring + live verification should be a separate
  commit, since the live-verification step depends on the first commit
  being correct and may need iteration.
- Do not bundle with `DET-010`–`DET-014` retriage or any VS-023 follow-up;
  those are separate decisions per "Out of scope" above.

## Codex execution instruction

```text
Implement VS-024: port Detailed mode to the same JSON-first render/
validate/repair pipeline Summary mode already uses (ADR-2026-08-07-001,
ADR-2026-08-07-002, render_summary.py as precedent). Read
assets/migration-assessment-template.md and
tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md
first. Extend schemas/analysis-result.schema.json's Detailed $defs to
actually cover the template's per-candidate card, dependency-matrix,
minimum-input, and blocker fields (they are currently Summary-shaped
placeholders). Write render_detailed.py as a pure function with unit
tests, extend report_contract.py's Detailed validation, update the agent
prompt to emit Detailed JSON only, and wire run_opencode_acceptance.py's
render/validate/repair path for report_mode: "detailed" cases. Do not
attempt to fix the wrong-file-citation content problem noted in the ticket
(out of scope, belongs with VS-023). Run the quality gate and at least 3
live repeats against jpetstore-6 pinned to
e1dd9a31d1cef68793cd0933ae06898e6fcfa807, and record validator failure
counts and a rubric score before/after in a new dated evaluation file.
Append a "Decision outcome" section to this ticket with the result.
```
