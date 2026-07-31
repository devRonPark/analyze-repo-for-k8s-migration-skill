# JPetStore 6 independent Detailed golden set

This is an independent, static-evidence baseline for Detailed-mode scoring. It
was prepared without loading the Skill or its references and does not execute
the target repository.

- Target: `/home/daolts/jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-07-30

## Required Detailed findings

### Component card: `jpetstore`

- Classification: the sole deployable candidate; Maven WAR artifact
  `jpetstore.war` (`pom.xml:30-35`, `pom.xml:246-253`).
- Build: Maven wrapper runs `clean package` inside the Docker image
  (`Dockerfile:18-20`). Maven compilation target is Java 17
  (`pom.xml:60-64`).
- Runtime: Docker image is explicitly `openjdk:25` (`Dockerfile:17`), while
  Cargo's default profile is `tomcat9` (`pom.xml:334-363`). Docker and README
  use `-P tomcat90`, which has no matching profile in the POM. This is a
  blocking execution conflict, not a confirmed runtime command.
- Network: Compose maps `8080:8080`; documented application context path is
  `/jpetstore/` (`docker-compose.yaml:19-26`, `README.md:57-67`). Protocol is
  HTTP only to the extent of the local URL evidence; TLS and ingress are
  unknown.
- State: Spring creates and seeds an embedded HSQLDB at startup
  (`applicationContext.xml:31-39`). The data lifecycle is disposable only if
  that is an accepted product decision; no external database configuration or
  persistence-volume evidence exists.
- Configuration and security: no deployment configuration source is evidenced.
  Seed data includes demo credential values, which must be treated as sensitive
  source data and never copied into output (`jpetstore-hsqldb-dataload.sql:17-23`).
- Compatibility: Java EE 3.0 web descriptor and a deferred Jakarta upgrade
  require application-server compatibility verification (`web.xml:19-27`,
  `pom.xml:117-122`).

### Dependency matrix and graph

| Source | Target | Classification | Evidence |
| --- | --- | --- | --- |
| `jpetstore` | embedded HSQLDB | in-process runtime dependency | `applicationContext.xml:31-39` |
| `jpetstore` | application server | runtime dependency with unresolved selection | `pom.xml:334-363`, `Dockerfile:21` |
| `jpetstore` | Maven/Cargo downloads | build/start-time network dependency | `Dockerfile:20-21`, `pom.xml:282-292` |

```text
jpetstore -> embedded HSQLDB
jpetstore -> selected application server (Tomcat profile conflict unresolved)
jpetstore -> Maven/Cargo artifact downloads during image build and startup
```

### Required blockers and unknowns

1. Resolve the supported JDK and server combination: Java 17 build target,
   Java 25 Docker base, `tomcat9` profile, and `tomcat90` invocation conflict.
2. Decide whether embedded demo data is disposable or an external managed
   database is required; define migration, backup, recovery, and credentials.
3. Supply workload name/kind, registry and image tag policy, Service, Ingress
   host/TLS, probes, resource policy, security context, and autoscaling policy.
4. Verify Java EE/Jakarta compatibility for the selected runtime.

## Scorecard for the interactive Detailed E2E attempt

The `tmux` interactive run on 2026-07-30 loaded the Detailed template and
checklist, read target files, and then reached its maximum step count. It
returned a progress summary and restart suggestion rather than a completed
Detailed Markdown report.

| Criterion | Result |
| --- | --- |
| Detailed report completed | Fail — no final report was produced. |
| Required component card, dependency matrix, graph, and blockers | Fail — none were emitted as final report sections. |
| Target repository safety | Pass — Git status remained unchanged. |
| **Acceptance score** | **0 / 100** — an incomplete response cannot be scored as a Detailed analysis result. |

The discovery transcript is diagnostic evidence only; it is not partial credit
for a deliverable that the user cannot use as a detailed migration assessment.

## Scorecard for the `steps: 24` interactive Detailed E2E rerun

The rerun on 2026-07-30 returned a complete Detailed Markdown report. The
score below compares that final report with the static-evidence baseline above.
It does not award credit for tool reads that did not become correct report
findings.

| Criterion | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Detailed report completion and required structure | 25 | 25 | All required sections, component card, dependency matrix, graph, blockers, and a single final verdict were returned. |
| Component execution, runtime, and network facts | 25 | 13 | Correctly identifies the WAR, Java 17 build target, explicit `openjdk:25`, and Compose port mapping. It treats Tomcat 9.x as confirmed instead of reporting the `tomcat9`/`tomcat90` execution conflict, and omits the documented `/jpetstore/` context path. |
| State and dependency analysis | 20 | 10 | Identifies the embedded HSQLDB and Maven build dependency, but omits the unresolved application-server edge and includes CI/package publishing edges in the runtime dependency graph. Persistent Volume and external database are presented as required outcomes without repository evidence for that product decision. |
| Configuration, security, and compatibility risks | 20 | 6 | Correctly reports missing Kubernetes deployment configuration. It says that no password-related configuration exists, missing seeded demo credentials, and omits the Java EE 3.0/Jakarta compatibility risk. |
| Evidence discipline and decision usefulness | 10 | 5 | The final verdict and missing Kubernetes inputs are useful, but several claims use incorrect or overly strong certainty (notably the server selection and persistence requirement). |
| **Acceptance score** | **100** | **59** | **Complete Detailed report, but not yet reliable enough as a migration design input without correction of the identified findings.** |
