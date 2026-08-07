# VS-021 — Stop Summary output from carrying a `recommendation`-classified open item

## Outcome

A Summary JSON payload whose `missing_inputs` contains a
`classification: "recommendation"` entry either gets rejected before
rendering, or the Agent stops emitting one — Summary output never displays
`권장 사항`.

## Why this is a vertical slice

`runtime/agents/kubernetes-migration-analyzer.md` already states "Summary
must contain no `권장 사항`, remediation, alternative architecture, or
CI/site dependency." Both prior 2026-07-30 scorecards
(`jpetstore-6-golden.md`: 66/100, `jpetstore-6-summary-bullet-scorecard.md`:
69/100) deducted for this same violation in free-written Markdown. The
JSON-first pipeline (DEL-002/DEL-003, 2026-08-07) did not fix it: the live
run scored in
`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md` (58/100)
still emitted
`{"classification": "recommendation", "description": "내장 HSQLDB를 외부 데이터베이스로
전환할지, 내장 상태를 유지할지 결정 필요", ...}` in `payload.json`, which
`OPEN_ITEM_LABELS` renders as `분류: 권장 사항` in the final Markdown. The
rule is stated but nothing enforces it — a prompt-only instruction, exactly
the pattern `docs/development/current/status.md` already flagged as
unreliable for `DET-010`–`DET-014`.

## Status and dependencies

- **Status:** Completed — enforced at the JSON-payload validation layer (see Decision outcome).
- **Depends on:** DEL-002/DEL-003 (this ticket's evidence comes from that pipeline)
- **Blocks:** None

## Read first

- `runtime/agents/kubernetes-migration-analyzer.md` — the existing "no 권장 사항" instruction and the new `## Summary JSON contract` section this session added
- `scripts/report_contract.py` — `OPEN_ITEM_LABELS`, `validate_json_payload`
- `scripts/render_summary.py` — where `missing_inputs[].classification` is mapped and rendered
- `scripts/validate_report.py` — the Summary Markdown validator, for where a rendered `권장 사항` line could be rejected

## Scope

### In scope

- Add a validator check: reject Summary Markdown (or, earlier, reject the
  JSON payload before rendering) that contains a `recommendation`-classified
  / `권장 사항` open item, with a clear Korean error naming the offending
  item.
- Update the agent prompt's `## Summary JSON contract` section to state
  explicitly that `missing_inputs[].classification` must never be
  `recommendation` for Summary mode (Detailed mode is unaffected — check
  whether Detailed has the same constraint before changing anything there).

### Out of scope

- Removing `recommendation` from the schema's enum entirely — it may still
  be valid for Detailed mode or a future mode; confirm before touching
  `schemas/analysis-result.schema.json`.
- Any change to how Detailed mode handles recommendations.

## Implementation steps

1. Decide where the check belongs: JSON-payload validation
   (`validate_json_payload` in `report_contract.py`, mode-aware) versus
   post-render Markdown validation (`validate_report.py`). Payload-level is
   preferable — it fails fast before wasting a render/finalize cycle.
2. Add the check and a test fixture that exercises it (a Summary payload
   with a `recommendation` item must fail validation with a clear message).
3. Re-run the JSON-first pipeline against the same `jpetstore-6` scenario
   that surfaced this and confirm the new failure mode is a clear, named
   rejection rather than a silently-passing `권장 사항` line.

## Acceptance criteria

- A Summary JSON payload with a `recommendation`-classified `missing_inputs`
  entry fails validation with a message naming the field and value.
- Detailed mode's handling of `recommendation` is unchanged (confirm via a
  targeted test).
- `python scripts/run_quality_gate.py` passes with the new test included.

## Verification commands

```bash
python scripts/run_quality_gate.py
python -m unittest tests.test_report_contract tests.test_summary_renderer -v
```

## Expected file changes

- `scripts/report_contract.py` and/or `scripts/validate_report.py`
- `runtime/agents/kubernetes-migration-analyzer.md`
- new/updated test fixtures under `tests/`

## Commit boundary

- Commit only the validator/prompt change and its tests.
- Suggested commit: `fix: reject a recommendation-classified open item in Summary output`

## Decision outcome (2026-08-07)

Enforced at the JSON-payload layer, per the ticket's stated preference:
`scripts/report_contract.py`'s `validate_json_payload` now rejects any
`missing_inputs[]` entry with `classification == "recommendation"` when
`mode == "summary"`, with an error naming the index and description/key.
This runs before rendering (both `render_summary()` and
`_render_summary_v1()` call `validate_json_payload` first), so a
`recommendation` item now fails fast instead of silently rendering as
`권장 사항`. Detailed mode is untouched — the check is gated on
`mode == "summary"` and a dedicated test confirms Detailed accepts the same
payload shape unchanged.

Also updated `runtime/agents/kubernetes-migration-analyzer.md`'s
`## Summary JSON contract` section to state the three valid Summary
classifications explicitly (dropping `recommendation` from the list) and
added an explicit "the validator rejects it" line, so a compliant model has
one fewer classification to reach for by mistake — though the enforcement
is what actually guarantees this, not the instruction.

Added `test_summary_rejects_a_recommendation_classified_open_item` and
`test_detailed_recommendation_classification_is_unaffected` to
`tests/test_report_contract.py`. `python scripts/run_quality_gate.py`:
148/149 (unrelated VS-019), unchanged.

## Codex execution instruction

```text
Implement only VS-021. Read runtime/agents/kubernetes-migration-analyzer.md's
existing "no 권장 사항" Summary rule and scripts/report_contract.py first.
Add an enforced (not just instructed) rejection of a recommendation-
classified missing_inputs entry in Summary mode, confirm Detailed mode is
unaffected, and add a test. Run the quality gate and report the result.
```
