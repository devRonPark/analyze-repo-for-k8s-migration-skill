# JPetStore 6 independent golden set

This is an independent, static-evidence baseline for scoring an interactive
Skill response. It was prepared without loading the Skill or its references.
It does not execute the target repository.

- Target: `/home/daolts/jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-07-30

## Required factual findings

| Area | Golden finding | Direct evidence |
| --- | --- | --- |
| Deployable unit | One deployable web application, packaged as `jpetstore.war`. | `pom.xml:30-35`, `pom.xml:246-253` |
| Build/runtime versions | Maven compilation target is Java 17, while the Docker base image is `openjdk:25`; this is a version-alignment risk, not an unknown image tag. | `pom.xml:60-64`, `Dockerfile:17` |
| Container build/start | The Docker image copies the entire source tree, builds with Maven inside the image, then starts Maven/Cargo at runtime. It is not a multi-stage runtime image. | `Dockerfile:18-21` |
| Server selection | The active Maven profile is `tomcat9`, but the Dockerfile and README invoke `-P tomcat90`; the supplied evidence is internally inconsistent and must be called out rather than asserted as a confirmed Tomcat 9 runtime. | `pom.xml:334-363`, `Dockerfile:21`, `README.md:36-57` |
| Reachability | Docker Compose publishes host/container port `8080`; the documented application URL is `/jpetstore/`. | `docker-compose.yaml:19-26`, `README.md:57-67` |
| Data state | Spring creates an embedded HSQLDB and runs schema and data-load scripts at startup. It is a stateful application concern; no external database configuration is evidenced. | `applicationContext.xml:31-39`, `pom.xml:170-174` |
| Credential exposure | The seed SQL includes demo usernames and passwords; those literals must not be copied into Kubernetes manifests or reported as secret values. | `jpetstore-hsqldb-dataload.sql:17-23` |
| Compatibility risk | The web descriptor uses the Java EE 3.0 namespace and the POM explicitly defers a Jakarta upgrade. Application-server compatibility must be verified. | `web.xml:19-27`, `pom.xml:117-122`, `pom.xml:365-566` |
| Existing orchestration | Compose exists with one service and `restart: always`; no Kubernetes resource, image registry/tag policy, probes, resource limits, Service, Ingress, Secret, ConfigMap, or external database endpoint is defined in the inspected static configuration. | `docker-compose.yaml:17-26`; absence search over repository configuration |

## Required uncertainty and design inputs

The analysis must preserve these as unknown or decisions, not invent values:

- Kubernetes workload kind, metadata name, image registry/tag policy, Service
  type, Ingress/host/TLS, resource requests/limits, probes, security context,
  and autoscaling policy.
- Whether the demo embedded database is intentionally disposable in the target
  environment or must be replaced by a managed external database.
- The intended supported JDK and application server after resolving the Java
  17/25 and `tomcat9`/`tomcat90` inconsistencies.

## Scorecard for the interactive E2E Summary

The scored response is the `tmux` interactive run on 2026-07-30 for the target
and revision above. Progress messages are permitted; this assesses the final
report content, not its pre-report narration.

| Dimension | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Scope, revision, and deployable-unit identification | 10 | 10 | Correct target, revision, and one JPetStore WAR/web workload. |
| Build, image, and runtime precision | 20 | 11 | Correctly found the in-image Maven build and Maven/Cargo startup, but incorrectly called the explicit `openjdk:25` tag unknown and treated Tomcat 9 as confirmed despite the profile mismatch. |
| Network and state dependencies | 15 | 12 | Correctly found port 8080, Compose, and embedded HSQLDB. It did not identify the documented `/jpetstore/` context path and overextended the state conclusion to a possible StatefulSet without persistence evidence. |
| Configuration, security, and compatibility risks | 20 | 7 | Correctly identifies missing Kubernetes configuration, but omits seed credentials and the Java EE/Jakarta compatibility risk. |
| Kubernetes design-input gaps | 20 | 15 | Covers image, Service, Ingress, database decision, Secret/ConfigMap, and broad design gaps. It should also call out probes, resources, security context, and the version/profile conflicts explicitly. |
| Evidence calibration and report discipline | 10 | 6 | Many claims cite files, but the image-tag assertion is false and the report includes recommendations despite a Summary-only boundary. |
| Interactive completion and target safety | 5 | 5 | Final report was completed after progress updates; target Git status was unchanged. |
| **Total** | **100** | **66** | **Useful first-pass migration inventory, but not yet reliable enough to be the sole Kubernetes design input.** |

## Correction priorities

1. Parse image references exactly: `openjdk:25` has an explicit tag; registry
   policy is the unknown.
2. Detect and report internal execution conflicts (`tomcat9` versus `tomcat90`,
   Java 17 versus Docker Java 25) as blockers.
3. Detect credential-like seed data and report only its location and exposure
   risk, never its values.
4. Distinguish embedded in-memory startup data from persistent-volume evidence.
5. Include web-platform compatibility, probes, resource policy, and security
   context among scoped unknowns.
