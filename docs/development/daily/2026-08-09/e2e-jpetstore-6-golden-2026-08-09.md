# JPetStore 6 Summary golden set

- Target: `C:\temp\opencode-e2e-jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-08-09

Required grounded findings:

- one Java web deployment candidate packaged as a Maven WAR (`pom.xml`);
- `pom.xml` declares Java 17 while `Dockerfile` uses `openjdk:25`, which is a material build/runtime compatibility conflict;
- the image build runs `./mvnw clean package` and startup uses `./mvnw cargo:run -P tomcat90` (`Dockerfile`);
- Compose publishes `8080:8080` (`docker-compose.yaml`);
- HSQLDB is a repository dependency (`pom.xml`), but durable production state is not established by the inspected evidence.

Required uncertainty/blocker:

- persistence/data-lifecycle and target runtime compatibility need a scoped design decision; do not invent an external database, PV, Service, or Ingress.

Scoring weights: report contract 20, candidate/build/runtime/network 35, state/dependencies 20, security/configuration 10, evidence discipline/decision usefulness 15.
