# VS-020 — Decide and fix Summary v2's dropped field coverage

## Outcome

Either the Summary v2 Markdown surfaces the component fields the model
already gathers correctly (image, build/run commands, Secret location), or
the project explicitly accepts the current compactness trade-off and
updates the golden-set rubric so it stops scoring against information the
template was never meant to show.

## Why this is a vertical slice

Live-scoring the JSON-first pipeline
(`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`, 58/100)
against `tests/evaluation/jpetstore-6-golden.md` found that the model's raw
JSON (`payload.json`) correctly captured `image: openjdk:25`,
`빌드 명령: ./mvnw clean package`, `운영 기동 명령: ./mvnw cargo:run -P tomcat90`,
and `Secret: src/main/resources/database/jpetstore-hsqldb-dataload.sql:17-29`
— but none of it appears in the rendered `report.md`. `render_summary.py`'s
non-legacy (v2) path only prints `실행 형태`, `Kubernetes 해석`, `수신 포트`,
`쓰기 상태 또는 영속성`, and `런타임 의존성` per component
(`scripts/render_summary.py`, the `render_summary()` function's per-component
`lines.append(...)` call). This produced two of the golden set's lowest
dimension scores ("Build, image, and runtime precision": 12/20,
"Configuration, security, and compatibility risks": 5/20) even though the
underlying evidence was accurate.

## Status and dependencies

- **Status:** Completed — decided neither Option A nor B as written; see Decision outcome below.
- **Depends on:** DEL-002/DEL-003 (implemented 2026-08-07; this ticket found
  the gap through the JSON-first pipeline they introduced, not before)
- **Blocks:** None

## Read first

- `tests/evaluation/jpetstore-6-summary-json-first-scorecard.md` — the scoring evidence for this gap
- `scripts/render_summary.py` — compare `render_summary()` (v2, compact) against `_render_summary_v1()` (legacy, prints all 12 `CORE_FIELDS` per component under `#### 핵심 입력`)
- `assets/migration-summary-template.md` — the v2 template's `## 2. 예상 Kubernetes 구성` section, currently one bullet per component
- `docs/development/daily/2026-07-30/ADR-2026-07-30-002-summary-mode-v2.md` — the original decision to make Summary v2 more compact; read this before assuming the current shape is unintentional

## Scope

### In scope

Pick one:

- **Option A — surface more fields.** Extend the v2 per-component bullet (or
  add a short sub-list) to include image, build command, run command, and
  Secret location when present, without reverting to the legacy renderer's
  full per-field section structure. Update `assets/migration-summary-template.md`
  and the agent prompt's worked example if the shape changes.
- **Option B — accept the trade-off, revise the rubric.** If v2's
  compactness is intentional per ADR-2026-07-30-002 and re-litigating it
  is out of scope, update `tests/evaluation/jpetstore-6-golden.md`'s
  dimension weights/expectations (or add a v2-specific golden set) so they
  score what v2 actually promises, rather than scoring it against a
  legacy-shaped rubric it was never designed to satisfy.

### Out of scope

- Reverting to the legacy (v1) renderer as the default.
- Changing Detailed mode's output shape.

## Implementation steps

1. Re-read ADR-2026-07-30-002 and confirm which fields v2 was deliberately
   asked to drop versus which are an oversight.
2. Choose Option A or B above and record the choice with reasoning (a short
   ADR addendum or a note in this ticket's completion report is enough; a
   full new ADR is not required unless the reasoning is non-obvious).
3. Implement the chosen option and re-render the JSON-first pipeline's
   `payload.json` from the scorecard evidence to confirm the fix surfaces
   (Option A) or the rubric now matches (Option B).

## Acceptance criteria

- If Option A: a component's image, build command, run command, and Secret
  location (when present in JSON) appear in the rendered Summary Markdown,
  and `python scripts/run_quality_gate.py` still passes.
- If Option B: `tests/evaluation/jpetstore-6-golden.md` explicitly states it
  scores v2's compact shape, and re-scoring the same `payload.json` against
  the revised rubric no longer penalizes information v2 doesn't promise.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/render_summary.py tests/evaluation/.../payload.json
```

## Expected file changes

- `scripts/render_summary.py` and/or `assets/migration-summary-template.md` (Option A)
- `tests/evaluation/jpetstore-6-golden.md` (Option B)
- `runtime/agents/kubernetes-migration-analyzer.md` (worked example, if the JSON shape or Markdown shape changes)

## Commit boundary

- Commit only the files the chosen option touches.
- Suggested commit: `feat: surface image/build/Secret fields in Summary v2` (A) or `docs: rescope the JPetStore golden set to Summary v2's compact contract` (B)

## Decision outcome (2026-08-07)

Neither Option A nor B as originally written. Re-reading
ADR-2026-07-30-002 §2.3 showed adding component-table columns (Option A)
would directly contradict a deliberate decision ("상세 빌드 명령", "전체 설정
목록" are explicitly excluded from Summary output). But §2.5 of the same
ADR already defines a `missing_inputs` channel for exactly this kind of
information (`deployment_value` for Secret-shaped inputs,
`hard_blocker`/`open_design_decision` for execution mismatches), and the
v2 renderer already prints `missing_inputs` in full under `## 4. 열린 항목`
— the Agent prompt just never told the model to route build/image-alignment
risk and Secret exposure there instead of leaving them in unrendered
`fields.*`.

Fix: extended the prompt's `## Summary JSON contract` section with an
explicit rule (route these three finding types to `missing_inputs`) and a
worked-example `deployment_value` entry. No renderer, template, or schema
change. Re-scored the same live scenario:
`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`'s
"VS-020 re-score" section — 58/100 → 84/100, with the two lowest-scoring
dimensions (build/image precision, configuration/security risks) improving
the most (12→17, 5→15). `python scripts/run_quality_gate.py`: 148/149
(unrelated VS-019) both before and after.

## Codex execution instruction

```text
Implement only VS-020. Read ADR-2026-07-30-002 first to determine whether
the dropped fields are intentional. Choose Option A or B from this ticket's
Scope, state which and why, then implement it. Do not revert the legacy
renderer to default or touch Detailed mode. Run the quality gate and report
the result.
```
