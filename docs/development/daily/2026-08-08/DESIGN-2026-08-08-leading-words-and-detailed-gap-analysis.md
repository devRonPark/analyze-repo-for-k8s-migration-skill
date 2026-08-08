# Design: Leading Words and Detailed-only Kubernetes readiness gap analysis

- Status: Approved design; awaiting written-spec review before planning
- Date: 2026-08-08
- Related: `leading-words-research-2026-08-08.md`, VS-027, PIPE-001 through PIPE-005

## Goal

Make the Skill reliably turn mandatory-reference reads into repository-grounded
evidence that supports a minimum Workload Unit decision. Extend only Detailed
mode with evidence-backed Kubernetes migration readiness gaps and improvement
directions. Preserve Summary as a compact decision-input report without
recommendations.

## Non-goals

- Do not make reference loading mechanically reliable through prose alone; the
  trusted pipeline remains responsible for that runtime guarantee.
- Do not generate manifests, commands, default resource values, SecurityContext
  values, or organizational CNCF maturity scores.
- Do not turn missing platform policy into a repository defect or recommendation.
- Do not change Korean evidence statuses, target safety, or Summary's output
  shape other than wording needed to keep the established no-recommendation
  boundary clear.

## Leading-word flow

The primary-tier workflow in `SKILL.md` will use this compact sequence:

1. **Vertical Slice**: before broad exploration, complete one thin path from a
   required-reference rule and repository evidence to a Workload Unit outcome.
2. **Grounding**: every material conclusion from that slice has a repository
   reference, conflict, or scoped absence; a tool read alone is not grounding.
3. **Workload Boundary**: use the existing two-condition rule for every
   independently startable process; do not derive a candidate count from files,
   modules, images, ports, or Secret names.
4. **Gap Analysis**: in Detailed mode only, compare a grounded finding to one
   applicable migration-readiness lens and record a bounded improvement
   direction or an open design input.
5. **Quality Gate**: do not finish until all material runtime processes have
   a grounded boundary result and every readiness item is either grounded or
   scoped unknown.

The active Vertical Slice is context-isolated. At runtime the Agent receives
only its active contract and cannot inspect later-stage tasks, schemas, assets,
or a stage roadmap. A newly active contract is disclosed only after the prior
slice satisfies its Quality Gate. ADR-2026-08-08-008 defines this boundary.

`workflow.md` and `workload-boundary.md` remain the detailed authoritative
rules. `SKILL.md` retains only the ordered action and routing language. The
same leading word is not repeated merely for emphasis; each occurrence must
activate a different point in the sequence.

## Readiness lenses

Gap Analysis may use one of these lenses only when the repository exposes
relevant evidence:

| Lens | Examples of source evidence | Bounded improvement direction |
| --- | --- | --- |
| Portability | config timing, backing service endpoint, process state, listener, shutdown, logging | separate configuration from code, externalize state, or establish lifecycle evidence |
| Build hygiene | Dockerfile stages, base image, final user, build context, CI image job | separate build/runtime artifacts, reduce final image content, or add image verification |
| Operational readiness | health behaviour, ports, deployment descriptors, resource settings | provide probe/resource/service design input or verify the missing runtime behaviour |
| Workload protection | credential-shaped location, privilege/user settings, service-account/API use, network dependency | move confidential configuration to a protected delivery path or decide the required workload policy |
| Maturity signal | CI/CD, image packaging, infrastructure-as-code, recovery/scale evidence | identify a bounded automation or operational capability gap; never assign a CNCF maturity level |

The source standards are vocabulary and decision lenses, not hidden repository
requirements: 12-Factor App, Kubernetes workload/security documentation,
Docker build best practices, and the CNCF Cloud Native Maturity Model Technology
dimension. Any recommendation must cite repository evidence and must state its
lens; a recommendation may not be emitted from an absence alone.

## Output contract

### Summary

Summary remains fact, scoped unknown, relationship/boundary, minimum-input,
and verdict only. It continues to reject recommendations and remediation. A
readiness concern is represented as a cited fact or a keyed open input.

### Detailed

Detailed keeps its eight top-level sections and 70-line / 1,200-word budget.
Section 7 gains a short `Kubernetes migration readiness gap analysis` subsection
after design blockers. Each item has this conceptual shape:

`lens; grounded finding; impact scope; improvement direction or design input;
status; repository reference`

Only a grounded fact or conflict can yield an improvement direction. A scoped
unknown remains a missing input or design blocker and cannot be promoted to a
recommendation. The item must be action-oriented but implementation-neutral;
for example, it may request an external-state decision but may not invent a
particular manifest field or value.

The structured Detailed payload gains an optional `readiness_gaps` array with
`lens`, `finding`, `impact_scope`, `direction`, `status`, and `reference`.
When `readiness_gaps` is present, all fields are required; `status` is limited
to `확인됨` or `상충됨`. Summary rejects the field. The renderer and validator
enforce the same distinction.

## Failure handling

- A mandatory-reference read with no extracted source-linked result leaves the
  Vertical Slice incomplete; the Agent must continue, or record a scoped
  unknown when the target evidence is absent.
- Incomplete workload-boundary evidence yields `미확인`, not a split/merge
  guess.
- A missing probe, resource policy, or security policy is a Detailed design
  input only when the target evidence makes it material; it is not an automatic
  gap or recommendation.
- A malformed, uncited, Summary-mode, or unknown-status readiness-gap payload
  fails deterministic validation.

## Verification strategy

1. Add deterministic validator/schema tests: Summary rejects `readiness_gaps`;
   Detailed accepts a cited grounded item and rejects uncited, unknown-status,
   or invented-default items.
2. Add renderer/template tests for the Detailed subsection and preserve Summary
   byte/contract behaviour.
3. Extend VS-027 fixtures: the multi-process case proves one Vertical Slice per
   independent process; the single-process case proves modules/Secrets do not
   force a split.
4. Run the relevant static quality gate. Before calling the change complete,
   run the detached OpenCode E2E with an independent golden set and verify that
   the final Detailed report contains grounded boundary outcomes and only
   evidence-backed readiness gaps. Keep the analyzed target unchanged.

## Delivery slices

1. Leading-word routing and reference consolidation with characterization
   coverage; no output-contract change.
2. Detailed `readiness_gaps` schema, renderer, validator, and fixtures using
   test-first development.
3. Agent/command routing and acceptance harness integration.
4. Static and provider-backed evaluation, followed by prompt-pruning review.

Stage-context isolation is delivered with the Agent/command routing slice. It
must be in place before Leading Words are evaluated through a multi-stage E2E;
otherwise later-stage knowledge can confound the observed behaviour.

The two areas are intentionally separable: leading words improve process
selection, while the structured Detailed gap model keeps recommendations
grounded and reviewable.
