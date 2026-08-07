# JPetStore 6 Detailed-mode timing and citation-accuracy measurement (2026-08-07)

Scope: Detailed mode only. Summary-mode timing/citation work for this date is
recorded separately in `jpetstore-6-summary-json-first-scorecard.md`'s
"VS-023 Phase 1 live verification" section; that work did not touch Detailed
mode, which is what this file measures.

## Run record

- Target: `C:\ktmp\jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807` (matches
  `tests/evaluation/jpetstore-6-detailed-golden.md`'s pinned revision)
- Verified clean and at the pinned revision before the run
  (`git status --short --branch` → `## HEAD (no branch)`, `git rev-parse HEAD`
  → `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`) and re-verified identical after
  all three repeats completed. No dependency install, build, test, or execution
  was performed against the target at any point.
- Command:
  `python scripts/run_opencode_acceptance.py --config runtime/opencode.json
  --cases tests/evaluation/opencode-cases.json --case slash-detailed
  --repository-root C:\ktmp\jpetstore-6 --repeat 3 --timeout 900
  --output-dir <session scratchpad>/detailed-run`
- Model/provider (from `run-metadata.json`): `local-sglang/Qwen/Qwen3.6-35B-A3B-FP8`,
  same as the `jpetstore-6-detailed-scorecard.md` DET-008/DET-009 baseline.
  `steps: 64` (the doubled budget from this session's earlier Summary-mode
  work) and the `locate_evidence`-only citation rule in
  `runtime/agents/kubernetes-migration-analyzer.md` both applied to this run.
- Harness: the `--pure` isolated acceptance harness (batch `opencode run
  --format json`), not the interactive `tmux` procedure DET-008/DET-009 used.
  This is a real methodological difference from the DET-008/009 baseline,
  noted wherever it may matter, but it uses the same model/provider and the
  same target/revision.

## Timing

| Repeat | Status | `elapsed_seconds` | Target unchanged (before→after) |
| --- | --- | ---: | --- |
| 1 | PASS (returncode 0) | 212.48 | Yes (`e1dd9a3…` → `e1dd9a3…`) |
| 2 | PASS (returncode 0) | 311.10 | Yes |
| 3 | PASS (returncode 0) | 209.05 | Yes |

Mean 244.2s, range 209.1–311.1s. All three completed well inside the 900s
timeout with no retries needed. For comparison, this session's Summary-mode
measurement saw one run take 426s, so Detailed here was faster in wall-clock
terms than that Summary outlier despite doing more work per run — plausibly
because Detailed's `opencode run --format json` path has no repair loop
(Summary's `retain_summary_markdown_with_repair` can add follow-up turns;
Detailed has no analogous post-hoc validator/repair step in the harness).

## Structural result: all three reports deviate from the Detailed contract

This is the headline finding, and it was not something this task's setup
predicted. None of the three reports matches the required
`assets/migration-assessment-template.md` structure:

- **No report starts cleanly with the title.** Each `final_output` opens with
  61–92 lines of the model's own tool-call narration ("Now let me check the
  web.xml...", "이제 모든 증거를 수집했습니다...") before the `# Kubernetes
  설계 입력 상세 평가` title appears. This is not present in the archived
  DET-008/DET-009 transcripts in `jpetstore-6-detailed-e2e-2026-07-30.md`. It
  may be a harness/procedure artifact (batch `--format json` capturing
  intermediate assistant turns as part of `final_output`, vs. the interactive
  `tmux` procedure's likely cleaner final message) rather than the same
  regression as the section drift below — I did not verify which because
  distinguishing the two would require re-running DET-008/009 with today's
  harness, and this file is one dated snapshot with a 900s budget, not a
  root-cause investigation.
- **None of the eight required `##` headings appear verbatim in any of the
  three repeats.** All three invented their own section names and counts
  (7–8 headings, all differently worded/ordered from the template and from
  each other). None used the required `### 배포 대상: <이름>` component-card
  heading with its `#### 실행 정보` / `#### 설정과 상태` / `#### Kubernetes
  최소 설계 입력` / `#### 최소 입력 누락` subsections; none used the required
  `### Dependency matrix` / `### Text dependency graph` headings (repeat 3 has
  a fenced ```text``` block, but it is a compile-time library dependency tree,
  not the runtime/infrastructure graph the template specifies — see the
  State-and-dependency dimension below); none used `### 설계 차단 항목`
  verbatim.
- **`scripts/validate_report.py --mode detailed --repo-root
  C:\ktmp\jpetstore-6`** (run against each report with its preamble stripped,
  i.e. the best case for the model) failed with:

  | Repeat | Validator failures | Report lines (post-title) | Word count (space-split) | Line budget (≤70) | Word budget (≤1200) |
  | --- | ---: | ---: | ---: | --- | --- |
  | 1 | 32 | 68 | 737 | met | met |
  | 2 | 18 | 180 | 1348 | exceeded (2.6×) | exceeded |
  | 3 | 20 | 137 | 1092 | exceeded (2×) | met |

  This is far worse than the DET-008 (7 failures) and DET-009 (7 failures)
  baseline runs recorded in `jpetstore-6-detailed-scorecard.md`. Two of
  repeat 1's failures are the same "citation path is not repository-relative"
  class DET-008 had (`applicationContext.xml:31` instead of
  `src/main/webapp/WEB-INF/applicationContext.xml:31`) — content-correct, but
  machine-unverifiable and against the template's explicit
  repository-relative-path instruction.
- **No repeat emits a machine-checkable verdict line.** The template requires
  `- 판정: 설계 입력 충분 | 추가 정보 필요 | 분석 불가`. Repeats 1 and 2 never
  contain the token `판정:` at all (the conclusion is asserted only in prose).
  Repeat 3 has `### 판정: 추가 정보 필요` as a heading, which is closer in
  spirit but still not the required `- 판정: <value>` bullet form, so the
  validator's regex still does not match it.

This means: whatever this session's earlier Summary-mode work did (steps
budget doubling, `locate_evidence`-only citation rule), it did not carry over
to reliable Detailed-mode template compliance in this 3-run sample. Given the
small sample (n=3, one date, one harness) this is a measurement, not a
diagnosis — but 3/3 failing this hard, compared to a 7-failure baseline, is a
large enough gap that it is worth a dedicated follow-up before trusting
Detailed mode's contract compliance.

## Rubric

Because the task explicitly flagged citation accuracy as the highest-risk
axis, this rubric keeps `jpetstore-6-detailed-scorecard.md`'s general
weighted-dimension shape but pulls citation verification out into its own
scored dimension with a written, reproducible procedure, instead of folding
it into a general "evidence discipline" catch-all.

| # | Dimension | Weight | What it measures |
| --- | --- | ---: | --- |
| 1 | Report completion and contract structure | 20 | 8 required `##` headings present verbatim; component-card and dependency-matrix/graph headings present; single machine-checkable `- 판정:` line; line/word budget; `validate_report.py` failure count. |
| 2 | Candidate coverage | 10 | Correct deployable candidate(s) identified; correct exclusions with evidence; no invented candidates. |
| 3 | Execution/build/runtime/network facts | 20 | Scored against the 9 required findings in `jpetstore-6-detailed-golden.md`: deployable unit, Java 17/`openjdk:25` version risk, in-image build behavior, `tomcat9`/`tomcat90` conflict, port 8080 + `/jpetstore/` context path, embedded HSQLDB, credential exposure (location only), Java EE/Jakarta compatibility risk, absence of K8s orchestration. |
| 4 | State and dependency analysis | 15 | Dependency matrix/graph coverage against the golden set's 3-edge table (embedded HSQLDB, application server with unresolved selection, Maven/Cargo build/start-time network dependency). |
| 5 | Configuration, security, and compatibility risks | 15 | Secret handled by location only (no literal values); compatibility risk raised as a decision, not just a fact. |
| 6 | **Citation accuracy spot-check** | 10 | See procedure below. |
| 7 | Evidence discipline / form compliance | 10 | `추정됨` carries `/ 판단:`; `미확인` carries a real `검색(...)` absence marker and (per candidate) `범위:`/`결정:`; `상충됨` carries two references; no false-absence claims (a `result=없음` for a file that was actually read or that exists in the tree); no credential literals leaked. |

**Total: 100.**

### Citation-accuracy procedure (dimension 6)

1. Extract every `path:line` / `path:start-end` token that appears after a
   `근거:` marker in each report (regex on the stripped report text).
2. Deduplicate by normalizing path separators; this run produced 59 raw
   tokens across the three reports, collapsing to well under that once
   bare-filename (`web.xml:24`) and repository-relative
   (`src/main/webapp/WEB-INF/web.xml:24`) citations of the same real location
   are merged.
3. For each unique location, `Read` the real file in `C:\ktmp\jpetstore-6` at
   that line/range and judge: **match** (line content directly supports the
   claim), **partial** (right file and general area, ≤2 lines off from the
   most precise supporting line, or the claim is a reasonable but not literal
   paraphrase), or **mismatch** (wrong file, out-of-range line, or a quoted
   string that does not appear on the cited line).
4. Also directly search the repository tree for every `검색(..., result=없음)`
   absence claim's pattern, to catch false-absence claims independent of
   `validate_report.py`'s own (narrower) check.
5. Score = `10 × (matches + 0.5×partials) / total_checked`, applied
   per-report. This run checked essentially the full unique-citation set (not
   a sample) because the corpus was small enough (~40 unique locations) to
   verify exhaustively within the task's time budget; a larger target would
   need to fall back to a stratified sample (e.g. first citation per section
   plus every Nth remaining one) — future reruns should say explicitly which
   they did.

## Citation spot-check evidence

Every unique `pom.xml`, `Dockerfile`, `docker-compose.yaml`, `README.md`,
`web.xml`, `applicationContext.xml`, seed-SQL, and `beans.xml` citation
across all three reports was opened and compared. Representative results:

**Matches (high confidence, exact):**

- Claim (repeat 1/2/3, all three): `./mvnw cargo:run -P tomcat90` (Dockerfile
  CMD) conflicts with the only defined Cargo profile. Real file:
  `Dockerfile:21` → `CMD ./mvnw cargo:run -P tomcat90`; `pom.xml:337` →
  `<id>tomcat9</id>`. **Match** — this is the single most consistently
  reproduced, correctly cited finding across all three runs, matching the
  golden set's #1 correction priority.
- Claim (repeat 1): `Dockerfile:17` → `openjdk:25`. Real file: `FROM
  openjdk:25`. **Match.**
- Claim (all three): embedded HSQLDB created via Spring.
  `src/main/webapp/WEB-INF/applicationContext.xml:31` → `<jdbc:embedded-database
  id="dataSource">`. **Match.**
- Claim (repeat 1): seed credentials at
  `src/main/resources/database/jpetstore-hsqldb-dataload.sql:19-20`. Real
  file, lines 19–20: `INSERT INTO signon VALUES('j2ee','j2ee');` /
  `INSERT INTO signon VALUES('ACID','ACID');`. **Match** — and the report
  correctly did not print the literal values (`validate_report.py`'s
  credential-literal check also passed on all three reports).
- Claim (repeat 2): same finding, different file —
  `src/main/resources/database/jpetstore-hsqldb-data.sql:170`. Real file,
  line 170: `INSERT INTO SIGNON VALUES('j2ee','j2ee');`. **Match** — confirms
  the repo genuinely has two near-duplicate seed files and repeat 2 cited the
  other one correctly, at the correct line.
- Claim (all three): documented context path `/jpetstore/`.
  `README.md:57` → `Run application in browser
  http://localhost:8080/jpetstore/`. **Match** in all three repeats — notably
  better than the DET-008 baseline, which missed this citation entirely
  (a -4 deduction there).
- Claim (repeat 2): `pom.xml:119`/`pom.xml:121`, "Spring 6.2.19와 분리된
  spring-web 5.3.39". Real file: line 119 `<artifactId>spring-web</artifactId>`,
  line 120 `<!-- Keep spring-web at 5.3.39 until jakarta upgrade occurs -->`,
  line 121 `<version>5.3.39</version>`. **Match**, and a genuinely precise
  catch — the report's claim is directly backed by the pinning comment.
- Absence claims (all three; e.g. `검색(scope=., pattern={**/*deployment*,
  **/kustomization*,**/helm*}, result=없음)`): independently verified with a
  direct filesystem search (`find ... -iname "*deployment*" -o -iname
  "*kustomization*" -o -iname "*helm*" -o -iname "*ingress*" ...` and a
  second pass for `*health*`/`*probe*`/`*actuator*`/`*prometheus*`) — no
  matches in either search. **No false-absence claims found in any of the
  three reports**, in contrast to DET-008's four false `result=없음` claims.

**Mismatch found (repeat 3, section 7 "설계 차단 항목"):**

- Claim: `` `pom.xml:121`의 `Keep disabled until jakarta upgrade occurs` ``
  (presented in backticks as a verbatim quote).
- Real file, `pom.xml:120`: `<!-- Keep spring-web at 5.3.39 until jakarta
  upgrade occurs -->` (line 121 is `<version>5.3.39</version>`, not a
  comment at all).
- **Mismatch.** The line pointer is in the right neighborhood and the
  underlying finding (deferred Jakarta upgrade) is real and correctly
  sourced elsewhere in the same report, but the quoted string does not
  appear anywhere in `pom.xml`. This is a distinct failure mode from a wrong
  `file:line` — the tool-computed location is close, but the model's prose
  fabricated an exact quotation around it. This is the one clear citation
  fabrication found in this session's entire spot-check.

**Minor imprecision (repeat 3):**

- Claim: `저장소: https://github.com/mybatis/jpetstore-6.git ... 근거:
  pom.xml:39`. Real file, line 39: `<connection>scm:git:ssh://git@github.com
  /mybatis/jpetstore-6.git</connection>` (ssh, not https). The https form
  is real but on line 42 (`<url>https://github.com/mybatis/jpetstore-6/</url>`),
  three lines away, same `<scm>` block. **Partial** — right block, wrong
  exact line/protocol for the value as quoted.

Aside from these two items, no fabricated file, no out-of-range line, and no
other misquote was found across the ~40 unique locations checked. This
extends VS-023 Phase 1's Summary-mode finding ("no fabricated citation
observed in 3/3 runs") to Detailed mode: citation *content* accuracy remains
very high even though report *structure* compliance collapsed. These are
different failure surfaces and should be tracked separately — a future
session should not read "citations are accurate" as "the report is usable
unreviewed," given the structural findings above.

## Scores

| Dimension (weight) | Repeat 1 | Repeat 2 | Repeat 3 |
| --- | ---: | ---: | ---: |
| 1. Structure (20) | 4 | 3 | 5 |
| 2. Candidate coverage (10) | 9 | 8 | 10 |
| 3. Execution/build/runtime facts (20) | 16 | 17 | 14 |
| 4. State/dependency analysis (15) | 5 | 12 | 6 |
| 5. Config/security/compat (15) | 11 | 9 | 10 |
| 6. Citation accuracy (10) | 8 | 10 | 7 |
| 7. Evidence discipline (10) | 5 | 6 | 7 |
| **Total (100)** | **58** | **65** | **59** |

Mean **60.7/100**, range 58–65. Notable per-repeat detail behind these
numbers:

- **Repeat 1** loses the most on structure (no dependency graph artifact at
  all, only one dependency edge instead of the golden set's three, no
  `범위:`/`결정:` on any missing-input line) despite being the only repeat
  within the 70-line budget.
- **Repeat 2** has the best golden-set fact coverage and the cleanest,
  most extensive citations of the three (10/10 on the citation dimension,
  zero issues found), but is 2.6× over the line budget and, like repeat 1,
  never emits a `판정:` line.
- **Repeat 3** has the best structural gestures (only repeat with a fenced
  dependency-graph block, an explicit exclusions section, and a
  `판정:`-labeled heading) but has two real content problems: it never flags
  the Java 17/`openjdk:25` version mismatch at all (a golden-set required
  finding that repeats 1 and 2 both caught), and it contains this session's
  one confirmed citation fabrication (the misquoted `pom.xml` comment).

All three scores are below both the DET-008 (63) and DET-009 (72) baselines
recorded in `jpetstore-6-detailed-scorecard.md`, and the structural gap (18–32
validator failures vs. 7) is much larger than the score gap alone suggests,
because this rubric — unlike a pass/fail contract check — gives substantial
credit for factually accurate content even when it is not in the required
shape. A strict pass/fail against `validate_report.py` would score all three
repeats as **FAIL**.

## What this does and does not show

- **Timing**: Detailed mode completed reliably in 209–311s across 3/3 runs,
  well under the 900s budget, using the same model as the July 30 baseline.
- **Citation content accuracy**: very high — effectively the same clean
  result VS-023 Phase 1 found for Summary mode, now with direct evidence for
  Detailed mode too, across a near-exhaustive check of every distinct
  citation in the corpus rather than a small sample.
- **Contract/structural compliance**: markedly worse than the July 30
  interactive baseline in this 3-run sample. This session cannot attribute a
  cause (different harness, different date, small n) — it can only report
  that 3/3 runs missed the required template shape by a wide and consistent
  margin, which is a large enough, clean enough signal to warrant a dedicated
  follow-up rather than being dismissed as noise.
- **Not covered**: no comparison run was made with the pre-VS-023 agent
  file or with the interactive `tmux` harness under today's conditions, so
  this file cannot separate "harness effect" from "prompt/steps-budget
  effect" on the structural regression. A follow-up that reruns one Detailed
  case through the interactive `tmux` procedure on the same date would
  isolate that variable. **Update: see the follow-up run below — it isolates
  the batch-vs-interactive variable, though not with `tmux` itself.**

## Follow-up: one true `--interactive` Detailed run (same date, same machine)

`memory/opencode-e2e.md`'s documented procedure requires `tmux` (to run a
detached session) and the `sqlite3` CLI (to read `opencode.db` directly).
**Neither is installed on this Windows machine** (`which tmux` /
`which sqlite3` both fail; this is Git Bash / MSYS2, not the Linux machine
the runbook assumes, and there is no `pacman` available to install them).
Rather than fabricate a result or silently substitute something and call it
the same procedure, this section documents the actual substitute used: a
direct `opencode run --interactive` invocation (a real interactive-mode
invocation, as opposed to the `--format json` batch mode all three earlier
runs used), built with the same isolated `HOME`/config/skill-install
machinery `run_opencode_acceptance.py` already uses and tests (so the run
is still a validly-scoped Skill install, not an ad hoc one). This is **not**
a byte-for-byte reproduction of the DET-008/DET-009 `tmux` procedure — it
does not allocate a real pty and was not captured via `capture-pane`/the
session's sqlite db — but it does answer the specific open question above:
does the structural failure only show up in batch `--format json` mode?

- Query sent: `Detailed` (matching the `slash-detailed` case), via
  `opencode run --interactive --pure --agent kubernetes-migration-analyzer
  --command analyze-repo-for-kubernetes --dir C:\ktmp\jpetstore-6`.
- Result: **PASS**, `elapsed_seconds = 271.1`, target unchanged
  (`git status`/`rev-parse` identical before and after:
  `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`).
- Preamble before the title: 35 lines (vs. 61–92 for the batch runs) — a bit
  shorter, and reads more like the runbook's allowed "concise progress
  narration" than the batch runs' more repetitive tool-by-tool commentary,
  but the preamble is not absent either way.

### Structural result: still fails, and by more than any batch run

`validate_report.py --mode detailed --repo-root C:\ktmp\jpetstore-6` on the
stripped report: **36 failures** — worse than all three batch repeats
(32/18/20). None of the 8 required headings appear verbatim; one heading is
in **English** (`## 1. Target Scope`, not `## 1. 분석 범위` — a template
heading translated, which `CLAUDE.md` calls out explicitly as something
`validate_report.py` matches literally and fails silently on if translated).
Sections 3 and 7 use **Markdown tables**, which the template explicitly
forbids for Detailed reports (`Detailed report must not use Markdown
tables.`) — and the table in section 3 is malformed (a whole
key/value/status/evidence row crammed into one cell). The final verdict
appears only as bold prose after a bare `---` separator
(`**판정: 추가 정보 필요**`), not as a `- 판정: <value>` bullet inside a
`## 8. Kubernetes 설계 입력 상태` heading, so — same as batch repeats 1 and
2 — the validator's verdict regex does not match it.

**This answers the open question from the first measurement**: the
structural collapse is not primarily a batch-JSON-harness artifact. It
reproduces, and is if anything worse, under a genuine `--interactive`
invocation. Given this and the earlier 3-run batch result, the structural
non-compliance looks like a property of the current Detailed prompt/template
interaction under this model, not an artifact of one harness.

### Citation-accuracy result: a new, more serious failure mode

The three batch runs' citations were checked almost exhaustively and were
very clean (one misquote across ~40 locations). This interactive run's
citations were spot-checked the same way and surfaced a **worse, repeated**
problem — not imprecise lines, but the **wrong file** cited for the same
claim, reused several times:

- The report correctly cites `Dockerfile:21` once (section 3's table row,
  `운영 기동`) for the `-P tomcat90` CMD that conflicts with the `tomcat9`
  Maven profile. But the *same* claim is then cited as `docker-compose.yaml:21`
  in four other places (section 2's "최상단 블록", section 4.1, section 5,
  and blocker 1 in section 8). Real file, `docker-compose.yaml:21`:
  `container_name: jpetstore` — completely unrelated to the profile
  conflict. **Mismatch**, repeated 4×.
- Similarly, `Dockerfile:17` (`FROM openjdk:25`) is the file that actually
  supports the "Java 17 build vs. Java 25 base image" conflict, but the
  report cites `docker-compose.yaml:17` for it three times (section 4's
  "빌드 도구" line, section 4.3's "JVM 아키텍처" line, and blocker 2 in
  section 8). Real file, `docker-compose.yaml:17`: `version: "3.9"` (the
  Compose schema version) — again unrelated. **Mismatch**, repeated 3×.
- One content-level error, not just a wrong file: section 4.3 labels
  `pom.xml:157` as `javax.servlet-api 4.0.4`. Real file, `pom.xml:155-157`:
  `<groupId>jakarta.servlet</groupId>` / `<artifactId>jakarta.servlet-api</artifactId>`
  / `<version>4.0.4</version>` — the dependency is under the **jakarta**
  namespace, the opposite of what the report says, which undermines the
  exact javax/jakarta split the report is trying to document there.
  **Mismatch** (wrong claim, not just wrong citation).
- Everything else checked (the `tomcat9`/`tomcat90` core finding via its
  correctly-cited `Dockerfile:21`/`pom.xml:337` instances, embedded HSQLDB
  at `applicationContext.xml:31`, seed credentials at
  `jpetstore-hsqldb-dataload.sql:19` with no literal values printed, port
  8080 and `/jpetstore/` context path, `pom.xml:77`/`:150` build-timestamp
  and jsp-api citations) matched the real file content, same as the batch
  runs.

This is a materially different and more concerning failure mode than
anything found in the three batch runs: a citation that points to a real,
existing `file:line` but is the **wrong file for the claim**, repeated for a
"top blocker" item — exactly the kind of error a reviewer skimming
`file:line` references without opening them would not catch, and worse than
DET-008's non-repository-relative-path defect or repeat 3's misquote from
the batch measurement above. **This tempers the earlier conclusion** ("no
fabricated citation observed... extends VS-023 Phase 1's clean-citation
result to Detailed mode") — that conclusion holds for the batch `--format
json` harness in this sample, but does not hold for this one interactive
run. With n=1 for the interactive path, this is one data point, not a
trend, but it is concrete enough (4+3 repeated wrong-file citations for two
different blocker-level claims in a single report) to flag as a real risk
rather than dismiss as noise.

### Updated verdict

Across all four Detailed runs measured today (3 batch + 1 interactive):
structural template compliance failed in all four (18–36 validator
failures, none matching the required headings/verdict format), and citation
accuracy — while excellent in the batch harness — showed a new, repeated
wrong-file failure mode in the one interactive run. Both problems point the
same direction: **do not trust an unreviewed Detailed report from the
current agent/template combination**, regardless of which invocation mode
produced it. A larger interactive sample (ideally with real `tmux` on a
Linux machine, matching the original DET-008/DET-009 conditions exactly)
would be needed to know whether this run's wrong-file citation pattern is
typical or a one-off.
