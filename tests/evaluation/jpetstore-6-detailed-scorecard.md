# JPetStore 6 Detailed scorecards

Scores the interactive Detailed E2E **final report only** against
[the independent Detailed golden set](jpetstore-6-detailed-golden.md). Tool reads
and assistant progress messages earn no credit.

## Run record — DET-008 report

- Target: `/home/daolts/jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-07-30
- Procedure: detached `tmux`, isolated `HOME` at `/tmp/opencode-acceptance-det8`,
  distribution installed by `scripts/install-opencode.sh`, provider
  `local-sglang/Qwen/Qwen3.6-35B-A3B-FP8`, request
  `/analyze-repo-for-kubernetes Detailed`
- Result: complete eight-section Markdown report, 130 lines, 2m 28s
- Target Git status before and after: `## master...origin/master` (unchanged)
- `scripts/validate_report.py --mode detailed --repo-root /home/daolts/jpetstore-6`:
  7 failures

## Score — DET-008 report

| Criterion | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Report completion and contract structure | 20 | 14 | All eight sections, `### 핵심 요약`, the keyed blocker, and one verdict are present, and every `미확인` minimum input carries `범위:` and `결정:`. Deductions: the validator still rejects four property references without `:line` (`근거: pom.xml`, `근거: mvnw, pom.xml`), two `web.xml:24-27`/`web.xml:61-63` citations that are not repository-relative (`src/main/webapp/WEB-INF/web.xml`), and one `추정됨` without `/ 판단:`. A non-contract appendix after section 8 repeats 핵심 요약 content and pushes the report to 130 lines against the 70-line budget. |
| Candidate coverage | 10 | 10 | `jpetstore` is identified as the sole deployable WAR with `finalName` evidence (`pom.xml:33`, `pom.xml:247`), the embedded database stays a dependency rather than a candidate, and MyBatis mappers and `beans.xml` are excluded with evidence. |
| Execution, build, runtime, and network facts | 25 | 13 | Correct: WAR artifact, Java 17 build target (`pom.xml:62`), `./mvnw clean package` (`Dockerfile:20`), `CMD ./mvnw cargo:run -P tomcat90` (`Dockerfile:21`), published port 8080 (`docker-compose.yaml:24`), `FROM openjdk:25` in section 6, and the profile conflict reported as `상충됨` with both references and an accurate profile list (`pom.xml:337` … `resin`). Deductions: the documented context path `http://localhost:8080/jpetstore/` (`README.md:57`) is missing (-4); the `image` minimum input is `미확인` with `검색(scope=., pattern=Dockerfile, result=없음)` although `Dockerfile:17` carries an explicit tag (-4); `command`, `args`, and `containerPort` repeat that false absence while `Dockerfile:21` and `docker-compose.yaml:24` are evidenced (-4). |
| State and dependency analysis | 15 | 9 | The embedded HSQLDB edge records JDBC, startup timing, in-process location, and disposable state (`applicationContext.xml:31-34`), and no PersistentVolume or external database is asserted as required. Deductions: the dependency matrix and graph carry only that one edge, omitting the unresolved application-server edge (`pom.xml:334-363`, `Dockerfile:21`) and the Maven/Cargo build- and start-time network dependency (`Dockerfile:20-21`) required by the golden set (-6). |
| Configuration, security, and compatibility risks | 20 | 11 | Seed credentials are reported by path and class only, with no values (`jpetstore-hsqldb-dataload.sql:19-20`), and the absence of Kubernetes deployment configuration is stated with absence evidence. Deductions: the Java EE/Jakarta compatibility risk is not a keyed verification need and the report contradicts itself on the level — section 6 reads the active descriptor correctly as `web-app_3_0.xsd` while the appendix calls it "Java EE 6/Java EE 5" (-5); the embedded-data lifecycle decision and the Jakarta verification exist only as appendix prose instead of keyed blockers or scoped unknowns (-4). |
| Evidence discipline and decision usefulness | 10 | 6 | The verdict, its reason, and its references are usable, and unknowns name their scope and blocked decision. Deductions: four `result=없음` claims are false for files the run actually read (-3), and one `추정됨` states no judgement reason (-1). |
| **Acceptance score** | **100** | **63** | **Below the 90-point DET-003 threshold. The report is structurally usable as a migration design input, but false absence evidence and the missing dependency edges still require correction before it can be trusted unreviewed.** |

## Score after DET-009 (false-absence fix)

Same procedure, run directory `/tmp/opencode-acceptance-det9`: complete
eight-section report, 125 lines, 2m 5s, target Git status unchanged, 7 validator
failures and zero false absence claims.

| Criterion | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Report completion and contract structure | 20 | 14 | Eight sections, `### 핵심 요약`, one verdict, and three keyed blockers. Deductions: `근거: glob(src…)` uses a tool name, three `미확인` minimum inputs drop `범위:`/`결정:`, one drops the `검색(...)` form, and the report is 125 lines against the 70-line budget. |
| Candidate coverage | 10 | 10 | The sole WAR candidate is correct, and CI, test-only dependencies, and the site-deploy profiles are excluded with evidence (`pom.xml:48-58`, `pom.xml:184-243`). |
| Execution, build, runtime, and network facts | 25 | 16 | `image` is now the fact `openjdk:25` (`Dockerfile:17`) instead of a false unknown, the profile conflict keeps both references, and build, start, and port facts hold. Deductions: the documented `/jpetstore/` context path (`README.md:57`) is still missing (-4); `docker-compose.yaml:20-27` and `:17-27` exceed the 26-line file (-3); the active `web-app_3_0.xsd` descriptor is labelled "Jakarta Servlet 4.0 API … JSP 3.0" (-2). |
| State and dependency analysis | 15 | 10 | The dependency matrix now carries the embedded HSQLDB edge and the application-server edge with unresolved selection, and the graph matches. Deductions: the Maven/Cargo build- and start-time network dependency required by the golden set is still absent (-3), and the `persistence` unknown lacks both `범위:`/`결정:` and absence evidence (-2). |
| Configuration, security, and compatibility risks | 20 | 15 | Seed credentials are a keyed blocker named by path and class with no values, the missing Kubernetes configuration is a keyed blocker, and the embedded-data lifecycle is raised as a decision. Deduction: Java EE/Jakarta compatibility is still not a keyed verification need and its level is mislabelled (-5). |
| Evidence discipline and decision usefulness | 10 | 7 | No `result=없음` claim contradicts a read file, and the verdict, reason, and references are usable. Deductions: one tool-name evidence value and three unscoped unknowns (-3). |
| **Acceptance score** | **100** | **72** | **Still below the 90-point threshold, but the false-absence class is gone and the dependency picture is materially more complete.** |

## Comparison with earlier attempts

| Attempt | Report | Validator failures | Score |
| --- | --- | ---: | ---: |
| First interactive run (step limit) | none | n/a | 0 |
| `steps: 24` rerun | complete | not measured | 59 |
| DET-008 rerun | complete | 7 | 63 |
| DET-009 rerun | complete | 7 | 72 |

The gain from 59 to 63 was factual: the profile conflict is now reported
as `상충됨` instead of a confirmed server, the seed credentials are named without
values, and no PersistentVolume requirement is invented. The remaining gap is no
longer report structure but false absence evidence and incomplete dependency
edges.

## Not covered

The DET-003 five-candidate food-delivery target does not exist on this machine,
so its golden set, scorecard, and E2E run remain outstanding. DET-003 acceptance
is therefore not met for either target: the latest JPetStore run scores 72/100
and the MSA target has no evidence at all.
