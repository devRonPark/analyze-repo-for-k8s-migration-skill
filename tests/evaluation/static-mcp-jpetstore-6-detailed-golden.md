# Static MCP Golden — JPetStore 6 Detailed

- Case: `jpetstore-6-detailed`
- Target: `C:\temp\opencode-e2e-jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-08-09
- Evidence basis: independent static inspection of the pinned local repository.

## Required findings

- The single repository deployment candidate is a Maven WAR (`pom.xml:33`) with Java 17 (`pom.xml:62`).
- The Docker build uses `openjdk:25` and packages with Maven Wrapper (`Dockerfile:16-20`), while the build declares Java 17 (`pom.xml:62`); retain compatibility as an unverified decision rather than a proven conflict.
- Docker starts Cargo's `tomcat90` profile (`Dockerfile:21`), but the active-by-default POM profile is `tomcat9` (`pom.xml:337-344`); retain this direct start-profile discrepancy.
- Compose provides one `jpetstore` service with port `8080:8080` (`docker-compose.yaml:17-25`).
- HSQLDB dependency and Spring embedded data source/scripts are repository-local runtime evidence (`pom.xml:171-173`; `src/main/webapp/WEB-INF/applicationContext.xml:31-34`).

## Required blockers and unknowns

- The evidence does not establish production persistence, backup, restore, or data migration ownership. Keep the state/lifecycle decision scoped to the application data path.
- Treat Java/image compatibility as an unresolved decision and retain the evidenced `tomcat90` versus active `tomcat9` start-profile discrepancy.
- Do not infer a Kubernetes database topology, persistent volume, ingress, resource limits, or probe policy.

## Scoring weights

- Report completion and Detailed contract: 20
- Candidate, build, runtime, and network facts: 25
- State, lifecycle, and dependency analysis: 25
- Configuration, security, and compatibility risks: 20
- Evidence discipline and decision usefulness: 10
