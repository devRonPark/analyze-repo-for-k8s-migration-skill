# JPetStore 6 Summary bullet-variant scorecard

- Target: `/home/daolts/jpetstore-6`
- Revision: `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`
- Evidence date: 2026-07-30
- Variant: all Summary sections use bullets rather than Markdown tables

The interactive E2E returned all five Summary sections in 1 minute 11 seconds.
The target Git status was unchanged: `## master...origin/master`.

| Dimension | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Scope, revision, and deployable-unit identification | 10 | 10 | Correct target, revision, and single WAR candidate. |
| Build, image, and runtime precision | 20 | 15 | Correctly records WAR packaging, in-image Maven build, explicit `openjdk:25`, and the `tomcat90`/`tomcat9` conflict. It does not clearly state that the image is non-multistage or consistently present the Java 17/25 alignment risk. |
| Network and state dependencies | 15 | 11 | Correctly identifies Compose port 8080, `/jpetstore/`, and embedded HSQLDB. It overstates the absence of an external database as an open problem and adds unsupported internal-filesystem wording. |
| Configuration, security, and compatibility risks | 20 | 15 | Correctly redacts credential-shaped seed data and identifies Java EE/Jakarta compatibility. It does not clearly distinguish missing deployment configuration from required Secret/ConfigMap input. |
| Kubernetes design-input gaps | 20 | 8 | Captures profile, data-lifecycle, compatibility, and registry decisions. It omits or fails to scope Service, Ingress host/TLS, probes, resource policy, security context, and autoscaling. |
| Evidence discipline and decision usefulness | 10 | 5 | The profile conflict and explicit image tag are calibrated, but the report introduces unsupported `ExternalSecret`/`InitContainer` discussion and treats an external database as a missing requirement. |
| Interactive completion and target safety | 5 | 5 | Complete report and unchanged target. |
| **Total** | **100** | **69** | Completion improved substantially, but the report remains below the 90-point migration-design-input threshold. |

## Deductions to fix next

1. Make the Summary emit every required Kubernetes input gap as scoped `미확인`.
2. For embedded HSQLDB, request a lifecycle decision without presuming an external database, PersistentVolume, ExternalSecret, or InitContainer.
3. Keep Java 17 build target and `openjdk:25` image tag together as an alignment risk, and state that the Docker image builds and starts through Maven/Cargo rather than a multistage runtime image.
