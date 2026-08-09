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
4. Submit `submit_boundaries` once with the incoming envelope.

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

**Checkpoint:** an `accepted` `submit_boundaries` response is this stage's only
completion. Do not draft or send user-facing Markdown before it returns. A
rejected submission may be corrected and resubmitted; after three rejections
in this stage, further attempts are marked non-retryable — resolve the
specific issue named in the response or submit with `unknown`/`inferred`
status instead of resubmitting the same payload.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
