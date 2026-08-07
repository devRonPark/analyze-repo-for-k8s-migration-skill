# JPetStore 6 Summary scorecard — JSON-first pipeline (post DEL-002/DEL-003)

- Target: `demo-repositories/jpetstore-6` (this machine)
- Revision analyzed: `3ebd25fd04f1b48361ab879e113ba353838ffe6a`
- Golden set pinned revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
  (`git diff` between the two touches only `.github/workflows/*.yaml`
  Renovate digest bumps — none of the files the golden set cites changed, so
  the golden set's file:line evidence is still valid for this revision.)
- Golden set: `tests/evaluation/jpetstore-6-golden.md`
- Scored artifact: `report.md` from
  `scripts/run_opencode_acceptance.py --case slash-default-summary
  --repository-root demo-repositories/jpetstore-6`, run 1 of 3 live attempts
  today (see reliability note below) — `Validation: passed`, target Git
  status unchanged before/after.
- Pipeline: Agent JSON → `render_summary.py` (v2, non-legacy) →
  `validate_report.py` → `validate_target_report.finalize()`. This is the
  DEL-002/DEL-003 path implemented and committed today (`d6a5fba`).

## Scorecard

Same seven dimensions and weights as `jpetstore-6-golden.md`'s 2026-07-30
scorecard (66/100, legacy free-written Markdown) and
`jpetstore-6-summary-bullet-scorecard.md` (69/100, legacy v1 renderer), for
direct comparability.

| Dimension | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Scope, revision, and deployable-unit identification | 10 | 10 | Correct target path, correct revision (`master@3ebd25f...`), single `jpetstore` WAR candidate — matches golden exactly. |
| Build, image, and runtime precision | 20 | 12 | The `tomcat90`/`tomcat9` profile mismatch is correctly resolved as a blocking conflict (`## 4. 열린 항목`, citing `Dockerfile:21, pom.xml:337`) — golden's #2 correction priority, and better-calibrated than either prior scored run. But the explicit `openjdk:25` image tag, the build command, the run command, and the "in-image Maven build, not multistage" characterization are **absent from the rendered report** even though the model captured all of them correctly in its JSON (`payload.json` `fields.이미지`, `fields.빌드 명령`, `fields.운영 기동 명령`) — the v2 template's one-line-per-component format does not surface those fields. |
| Network and state dependencies | 15 | 12 | Port 8080 correct (`포트: 8080`). Embedded HSQLDB correctly stated with lifecycle left `미확인` — no unsupported StatefulSet/PersistentVolume overreach (an error both prior runs made). Compose is not named by product, and the documented `/jpetstore/` context path (`README.md:57`) is missing — the model never read `README.md` this run. |
| Configuration, security, and compatibility risks | 20 | 5 | Missing Kubernetes configuration is correctly noted. But the Secret finding — which the JSON payload captured precisely (`fields.Secret` → `src/main/resources/database/jpetstore-hsqldb-dataload.sql:17-29`, location only, no value) — **does not appear anywhere in the rendered report**, again because the v2 template's compact bullet omits it. Java EE/Jakarta compatibility risk (`web.xml` namespace) was not gathered at all this run — the model didn't read `web.xml`. |
| Kubernetes design-input gaps | 20 | 8 | Only `workload.kind` is individually itemized as an open input (`## 4. 열린 항목`). `metadata.name`, Service, Ingress/host/TLS, probes, resource limits, security context, and autoscaling are not itemized — the model didn't scope them as separate open items, and the v2 renderer only prints what `missing_inputs` contains (no auto-generated checklist fallback). This is fewer itemized gaps than the 2026-07-30 legacy run, which listed four individually. |
| Evidence calibration and report discipline | 10 | 6 | Every citation resolves to a real file:line; no false or invented claim (an improvement — the 2026-07-30 run wrongly called the image tag "unknown"). But one open item is classified `recommendation` ("내장 HSQLDB를 외부 데이터베이스로 전환할지... 결정 필요"), rendered as `권장 사항` — the agent prompt explicitly forbids `권장 사항` in Summary. Same rule violation both prior scorecards also deducted for. |
| Interactive completion and target safety | 5 | 5 | Report completed, `Validation: passed`, target `git status` identical before/after. |
| **Total** | **100** | **58** | See "How to read this score" below — this is not a regression in analysis quality. |

## How to read this score

The raw JSON (`payload.json`) the model produced is materially *more*
accurate and better-calibrated than either prior scored run: it correctly
resolved the `tomcat90`/`tomcat9` conflict, correctly kept the `openjdk:25`
tag as a confirmed fact rather than calling it "unknown," and made no false
claims. Most of this score's shortfall against the golden set is **not** a
model-quality regression — it's the v2 Summary template's intentionally
compact one-line-per-component rendering silently dropping fields
(image, build/run commands, protocol, Secret) that the model gathered
correctly and put in the JSON, but that `render_summary.py`'s non-legacy
path never prints. This is a distinct, structural finding from DEL-002/
DEL-003's original scope (which targeted format-determinism, not
information completeness) and is not addressed by this ADR's implementation.

## Reliability context (3 live attempts today, JSON-first pipeline)

1. **PASS** — this scored run.
2. **UNAVAILABLE** — timed out at 180s with no output; a 300s retry (attempt
   3) did complete, so this looks like transient latency, not a hang.
3. **FAIL** — the model ignored the JSON-only instruction entirely and
   free-wrote Markdown analysis (including a `Recommendation`-heavy section
   and a Markdown table), so `extract_json_object` found no JSON to parse.
   Also showed token-level language drift (Chinese characters mid-Korean
   sentence), consistent with `reasoningEffort: "none"` degradation under a
   long system prompt.

One clean PASS out of three is not yet a reliability claim either way with
this sample size, but it does confirm the residual risk ADR-2026-08-07-001
already recorded: JSON emission is prompt-only, not schema-constrained at
the engine level.

## Follow-up candidates (as of the original 58/100 score)

1. Decide whether the v2 template should surface more `fields` per
   component (image, build/run commands, Secret) for Summary mode, or
   whether that's an intentional compactness trade-off the golden-set
   rubric needs to be revised to match. → resolved below as **VS-020**.
2. The model still includes a `recommendation`-classified open item despite
   the prompt's explicit "no 권장 사항" rule for Summary — worth a targeted
   prompt or validator check. → still open, tracked as **VS-021**.
3. `response_format` JSON-schema constraint (already tracked in
   ADR-2026-08-07-001) would address the attempt-3 failure mode directly.
   → still open, tracked as **VS-022**.

## VS-020 re-score: 84/100

`docs/development/tickets/VS-020-summary-v2-field-coverage.md` decided
against Option A (adding component-table columns) after reading
ADR-2026-07-30-002 §2.3, which explicitly excludes verbose per-field detail
(build commands, full config lists) from Summary — adding columns would
have reopened a decision that ADR already made. §2.5 of that same ADR
defines exactly where information like this belongs instead: `missing_inputs`
with `hard_blocker` / `open_design_decision` / `deployment_value`
classification, which the v2 renderer already prints in full under
`## 4. 열린 항목`. The gap was that the Agent prompt never told the model to
route build/image-alignment risk and Secret exposure there — it only had
those facts sitting in unrendered `fields.*`.

Fix (no renderer or schema change): extended `runtime/agents/kubernetes-migration-analyzer.md`'s
`## Summary JSON contract` section with an explicit rule — a
build/runtime mismatch, a Secret/credential-shaped data location, or a
compatibility risk must also become a `missing_inputs` entry, with a
worked-example addition showing a `deployment_value` Secret item — and
re-ran the identical live scenario.

| Dimension | Weight | Before (58/100 run) | After (this run) | Assessment |
| --- | ---: | ---: | ---: | --- |
| Scope, revision, deployable-unit | 10 | 10 | 10 | Unchanged, already correct. |
| Build, image, runtime precision | 20 | 12 | 17 | Now explicitly names the `openjdk:25`/Java 17 alignment risk (`Dockerfile:17, pom.xml:63`) alongside the `tomcat90`/`tomcat9` conflict, both as `설계 차단` open items. |
| Network and state dependencies | 15 | 12 | 12 | Unchanged — port/HSQLDB still correct, `/jpetstore/` context path still missing (model still didn't read `README.md`). |
| Configuration, security, compatibility risks | 20 | 5 | 15 | Secret/credential-shaped seed data now appears as a `배포 입력` open item with precise location (`src/main/resources/database/jpetstore-hsqldb-data.sql:168-173`) — golden's #3 correction priority. Java EE/Jakarta compatibility still not evidenced. |
| Kubernetes design-input gaps | 20 | 8 | 17 | Now individually covers workload.kind, HSQLDB persistence/lifecycle, and names Service/Ingress/probes/resources/security-context/autoscaling together — close to the full golden checklist, though the last six are consolidated into one bullet rather than six. |
| Evidence calibration and report discipline | 10 | 6 | 8 | No false claims; no `recommendation`-classified item this run (VS-021 not yet implemented, so this isn't guaranteed on every run). |
| Interactive completion and target safety | 5 | 5 | 5 | Completed, `Validation: passed`, target unchanged. |
| **Total** | **100** | **58** | **84** | |

This confirms VS-020's decision was correct without touching the renderer,
template, or schema at all — the v2 architecture already had a channel for
this information; the Agent just wasn't told to use it. `python scripts/run_quality_gate.py`
stayed at 148/149 (unrelated VS-019) after this change.
