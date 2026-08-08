# Case A fixture -- single process, layered internals

Golden-set fixture for `references/workload-boundary.md`'s second
contrastive example. It must NOT be split into multiple Workload Units.

One deployable process, started only by `java -jar app.jar`
(`Dockerfile:4`). `controller/`, `service/`, and `repository/` are Java
packages inside that one process (`src/main/java/com/example/petstore/**`),
not independently started, stopped, restarted, or scaled processes. There is
exactly one build artifact: `pom.xml` declares `<packaging>jar</packaging>`
with `finalName: app`, and no second entrypoint, process-manager entry, or
Compose/Dockerfile `CMD` exists anywhere in this fixture.

This fixture is read-only: it is not intended to be built, compiled, tested,
or run. It exists as static evidence for scoring the Workload Unit boundary
rule (see `tests/evaluation/workload-boundary-golden.md`).
