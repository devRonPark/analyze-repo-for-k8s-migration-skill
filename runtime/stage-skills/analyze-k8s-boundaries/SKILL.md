---
name: analyze-k8s-boundaries
description: Use when accepted process and dependency facts need grounded workload boundaries.
---

# Boundaries

Use the incoming handoff only. Apply Workload Boundary, Grounding, and Quality Gate.

1. Read [the workload-boundary rules](references/workload-boundary.md) and
   [the payload contract](references/payload-contract.json) before evidence.
2. The incoming `stage_input` owns `mode`, `candidate_ids`, `process_ids`,
   `graph_edge_ids`, `discovery_fact_refs`, `execution_fact_refs`,
   `relationship_fact_refs`, and `unknown_ids`. Ground those inputs primarily
   from `stage_input.survey`.
3. Create only safe structured workload units. A deployable unit requires both
   a distinct start definition and an independent lifecycle; directories and
   ports alone never create a unit.
4. Submit one complete `submit_boundaries` attempt after this stage's decision
   is ready. Retry only after an explicit server rejection.

**Ground:** the incoming handoff's `stage_input.survey` already carries this
stage's bounded, redacted evidence (`observations[]`, each with an
`observation_ref`, status, and safe `path:line` reference). Read it before
calling any evidence tool; a missing category is a scoped absence
observation, not an error.

**Precision (optional, at most one call):** call `read_evidence`,
`locate_evidence`, or `list_target_paths` only if one current decision is
still blocked after grounding from the survey. `get_target_git_metadata` is
not counted against this budget. A `precision_budget_exhausted` response
means stop searching — the identical error repeats on any further call — and
submit with `unknown`/`inferred` status on the blocked field instead.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Every `payload.evidence[].observation_ref` must come from this
stage's `stage_input.survey.observations` or its one precision call.

**Checkpoint:** do not draft or send user-facing Markdown before
`submit_boundaries` returns. A rejected submission may be corrected and
resubmitted; after three rejections in this stage, further attempts are
marked non-retryable — resolve the specific issue named in the response or
submit with `unknown`/`inferred` status instead of resubmitting the same
payload.

Do not load another Skill, read another stage's references, or infer a later
procedure while this stage is open.

## Transition

Do not choose, predict, or infer the next stage.

If the submission is accepted:
1. Stop applying this Skill's procedure.
2. Read `handoff.next_skill` only from the accepted server response.
3. Load exactly that Skill.
4. Do not inspect or load any other stage or reference.

If the submission is rejected:
1. Remain in this Skill.
2. Correct only the issues returned by the server.
3. Resubmit within the allowed retry budget.

A response without `status: accepted` never authorizes a stage transition.
