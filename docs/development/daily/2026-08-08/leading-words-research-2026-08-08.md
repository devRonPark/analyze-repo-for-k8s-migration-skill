# Leading-words research for evidence-to-workload analysis

- Status: Research complete; application to `SKILL.md` is not yet designed
- Date: 2026-08-08
- Scope: Prevent required-reference reads that produce no usable evidence, and
  make evidence collection precede minimum deployable-unit judgment.

## Problem statement

The current Skill names mandatory references and tells the Agent to inspect
them. A tool read alone is not an analysis result: it can leave no cited fact,
no scoped unknown, and no input to the Workload Unit decision. The failure is
especially damaging when `references/workload-boundary.md` is read but the
final candidate count is still inferred from files, directories, or container
names rather than independently executable processes and their lifecycle.

The desired behaviour is this closed sequence:

`required file read -> extract repository evidence -> enumerate runtime
processes -> decide the Workload Unit boundary -> report fact, conflict, or
scoped unknown`.

## Research evidence

### Skill-writing vocabulary

Matt Pocock's `writing-great-skills` guide defines a leading word as a compact,
pretrained concept that anchors a repeatable region of agent behaviour. The
same term can link invocation and execution while replacing repeated prose.
It also recommends retaining steps only when they affect the process and
keeping detailed material in lower-tier references.

- Source: <https://github.com/mattpocock/skills/blob/main/skills/productivity/writing-great-skills/SKILL.md>

### Kubernetes boundary vocabulary

Kubernetes defines a workload as an application running in Pods. A Pod may
contain multiple containers, but those containers share networking and are
co-located and co-scheduled; Kubernetes guidance says containers should be
scheduled together only when they are tightly coupled and need to share
resources. Therefore a source-file, directory, image, port, or Secret name is
not by itself the boundary of a minimum deployable unit.

- Sources: <https://kubernetes.io/docs/concepts/workloads/>,
  <https://kubernetes.io/docs/tutorials/kubernetes-basics/explore/explore-intro/>,
  <https://kubernetes.io/docs/concepts/services-networking/>

The repository's `references/workload-boundary.md` makes the resulting local
contract precise: separate Workload Units require both independent execution
and an independent lifecycle/operational boundary; evidence for only one is
not a separation.

## Candidate leading words

| Leading word | Existing prior it recruits | Required agent behaviour | Why it addresses the observed failure |
| --- | --- | --- | --- |
| **Evidence chain** | Traceable claim-to-source provenance | Turn every material required-file read into a `path:line` fact, conflict, or scoped absence before using it in a conclusion. | It distinguishes opening a file from collecting an analysable fact. |
| **Runtime census** | An inventory completed before judgment | Enumerate each independently startable process and its command, owning scope, and lifecycle evidence before counting candidates. | It prevents file/module/container names from becoming implicit deployment units. |
| **Workload boundary** | The established Kubernetes operational boundary | Apply the repository's two-condition rule to each census item; preserve `미확인` when either condition lacks evidence. | It connects collected process evidence to the minimum deployable-unit decision. |
| **Decision gate** | A closed prerequisite check | Do not emit candidate count, exclusion, or verdict until each runtime-census item has an evidence-chain entry and a boundary outcome. | It prevents a report from completing after references were read but not used. |

`Workload boundary` is already an established local term and should remain
unchanged. `Evidence chain`, `runtime census`, and `decision gate` are compact
operational concepts rather than new output categories; they must not replace
the required Korean evidence statuses or report headings.

## Readiness vocabulary from migration standards

The requested industry standards support a fifth candidate term,
**readiness gap**: a repository-supported difference between observed behaviour
and a Kubernetes migration expectation. It is not a presumed Kubernetes
manifest value and it is not a diagnosis when repository evidence is absent.
It turns a completed evidence chain into either a confirmed readiness finding,
a scoped design input, or an explicitly unknown item.

| Readiness lens | External vocabulary | Repository evidence to seek | Permitted conclusion |
| --- | --- | --- | --- |
| **Portability** | 12-Factor config, backing services, build/release/run, stateless processes, port binding, disposability, event-stream logs | Configuration source and timing, attached services, start command, writable state, listener, termination, and logging configuration | Confirmed portability behaviour, a conflict, or a scoped design input; never assume statelessness from a container. |
| **Build hygiene** | Docker multi-stage build, small trusted base image, ephemeral containers, CI image test | Dockerfile stages, final-image contents, base-image reference, `USER`, build context, and CI definition | Containerization fact or improvement candidate with source evidence; a missing Dockerfile remains a finding, not a failure. |
| **Operational readiness** | Kubernetes workload, probes, resources, Service/Ingress, configuration | Runtime process, protocol/port, health endpoint or behaviour, state, configuration, and existing deployment descriptors | Existing evidence or a minimum design input. Missing platform policy is not automatically a repository defect in Summary mode. |
| **Workload protection** | Secret protection, Pod security standards, network policy, access control | Credential-shaped locations, image/user configuration, privilege/security settings, service-account/API use, and network dependencies | A security fact/risk or scoped unknown; do not disclose secret values or invent a required `SecurityContext`. |
| **Maturity signal** | CNCF Technology maturity: automation, packaging, security baseline, availability and scaling capabilities | CI/CD, image packaging, infrastructure-as-code, deployment descriptors, recovery and scaling evidence | A bounded readiness observation. This is not a CNCF maturity score or organizational assessment. |

Sources:

- <https://12factor.net/> defines configuration, backing services,
  build/release/run, stateless processes, port binding, disposability, and
  event-stream logging as its application-operability vocabulary.
- <https://kubernetes.io/docs/concepts/workloads/> and
  <https://kubernetes.io/docs/tutorials/kubernetes-basics/explore/explore-intro/>
  define workload/Pod lifecycle and tight container coupling.
- <https://kubernetes.io/docs/concepts/security/> identifies Secrets, Pod
  security standards, and network policies as workload-protection concerns.
- <https://docs.docker.com/build/building/best-practices/> covers multi-stage
  builds, trusted base images, ephemeral containers, and image testing in CI.
- <https://maturitymodel.cncf.io/> uses Technology as one maturity dimension;
  this Skill may use it only as a vocabulary source, not as a maturity score.

## Revised leading-word set

The recommended compact set is now:

1. **Runtime census** — enumerate possible runtime processes before any count.
2. **Evidence chain** — convert required reads into source-linked facts,
   conflicts, or scoped absences.
3. **Workload boundary** — use the local two-condition rule to decide the
   minimum deployable unit from the census evidence.
4. **Readiness gap** — compare only a completed evidence chain against the
   relevant portability, build, operational, or protection lens.
5. **Decision gate** — prohibit candidate counts, readiness conclusions, and
   improvement items until the preceding entries are complete or scoped
   unknowns.

The terms form an analysis sequence, not five checklists. They are intentionally
fewer than the five source frameworks: a leading word must compress behaviour,
not reproduce an external standard in the prompt.

## Terms not to use as anchors

- `read` or `inspect`: these describe a tool action but not the required
  extraction and judgment.
- `candidate`: it is an output classification and is too late to ensure a
  runtime process was enumerated.
- `Pod` or `deployment unit`: Kubernetes uses Pod for an atomic compute object,
  while this Skill needs an evidence-led design decision about its local
  `Workload Unit`; using them interchangeably would create ambiguity.

## Proposed application hypothesis

Use the five leading words in the primary-tier ordered workflow, not as a new
prose layer:

1. Build a **runtime census** from repository start definitions.
2. For every material census entry and required reference, record an
   **evidence chain** before using it.
3. Apply the **workload boundary** rule to every census entry.
4. Derive a **readiness gap** only from those boundary outcomes and their
   evidence chains.
5. Close the **decision gate** only when all entries have a boundary outcome
   and all material claims and readiness gaps have evidence, conflict, or
   scoped absence.

The detailed explanations stay in `workflow.md` and `workload-boundary.md`.
The `SKILL.md` change should delete superseded instruction prose rather than
add a duplicate checklist.

## Validation hypothesis

Before accepting the refactor, use focused static fixtures and interactive
golden-set cases to distinguish a tool read from a usable result:

- a multiple-process repository must show an evidence-chain entry for each
  runtime command and derive the split/merge result through the workload
  boundary;
- a single-process repository with several modules or Secrets must not split
  without both boundary conditions;
- a missing lifecycle signal must produce a scoped `미확인`, not a guessed
  candidate count; and
- the final report must cite the evidence-chain result, not merely show that a
  reference file was opened.

This research does not claim that the vocabulary alone supplies mechanical
reference loading. The trusted pipeline work remains responsible for that
runtime guarantee; leading words make the required behaviour more predictable
once the relevant context is available.

It also does not yet change the output contract. Current Summary mode explicitly
forbids recommendations, while the requested direction contemplates
improvement recommendations. That product-scope choice must be made before
editing `SKILL.md`, report templates, schemas, or validators.
