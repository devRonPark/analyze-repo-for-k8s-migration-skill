# Static MCP Golden — JPetStore 6 Summary

- Case: `jpetstore-6-summary`
- Target: `C:\temp\opencode-e2e-jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-08-09
- Evidence basis: independent static inspection of the pinned local repository.

## Required findings

- One deployable Java web application is packaged as a Maven WAR (`pom.xml:33`).
- The build declares Java 17 (`pom.xml:62`), while the Docker image is `openjdk:25` (`Dockerfile:16`); record the runtime compatibility decision as unverified rather than assuming incompatibility.
- Docker starts `./mvnw cargo:run -P tomcat90` (`Dockerfile:21`), but the checked-in active-by-default Cargo profile is `tomcat9` (`pom.xml:337-344`); report this direct start-profile discrepancy.
- The checked-in Compose service builds the repository and publishes `8080:8080` (`docker-compose.yaml:17-25`).
- HSQLDB is a declared dependency (`pom.xml:171-173`) and is configured as an embedded database loaded from repository SQL scripts (`src/main/webapp/WEB-INF/applicationContext.xml:31-34`).

## Required blockers and unknowns

- Durable production data handling, data lifecycle, backup/recovery, and Java/image compatibility are not established by the inspected evidence; record scoped design decisions.
- Do not invent an external database, persistent volume, Service, Ingress, probe, resource value, or security-context default.

## Scoring weights

- Report completion and Summary contract: 20
- Candidate, build, runtime, and reachable port facts: 35
- State and dependency facts: 20
- Configuration and security risk: 10
- Evidence discipline and decision usefulness: 15
