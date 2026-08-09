---
name: analyze-k8s-relationships
description: Use when accepted discovery and execution facts need grounded dependency relationships.
---

# Relationships

Use the incoming handoff only. Apply Vertical Slice, Grounding, and Quality Gate.

1. Read [the dependency analysis rules](references/dependency-analysis.md) and
   [the payload contract](references/payload-contract.json) before collecting
   evidence.
2. The incoming `stage_input` owns `mode`, `process_ids`,
   `discovery_fact_refs`, `execution_fact_refs`, and `unknown_ids`. Ground
   dependency edges, external runtime dependencies, or scoped unknowns for
   those inputs primarily from `stage_input.survey`.
3. Keep incoming fact references unchanged. Create only safe structured graph
   edges and observation aliases; never copy raw evidence into claims.
4. Submit `submit_relationships` once with the incoming envelope.

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

**Checkpoint:** an `accepted` `submit_relationships` response is this stage's
only completion. Do not draft or send user-facing Markdown before it
returns. A rejected submission may be corrected and resubmitted; after three
rejections in this stage, further attempts are marked non-retryable —
resolve the specific issue named in the response or submit with
`unknown`/`inferred` status instead of resubmitting the same payload.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
