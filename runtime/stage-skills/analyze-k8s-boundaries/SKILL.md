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
   `relationship_fact_refs`, and `unknown_ids`. Use only `list_target_paths`,
   `read_evidence`, `locate_evidence`, and `get_target_git_metadata`.
3. Create only safe structured workload units. A deployable unit requires both
   a distinct start definition and an independent lifecycle; directories and
   ports alone never create a unit.
4. Submit `submit_boundaries` once with the incoming envelope.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Every `payload.evidence[].observation_ref` must be issued by an
evidence tool in this current stage.

**Checkpoint:** an `accepted` `submit_boundaries` response is this stage's only
completion. Do not draft or send user-facing Markdown before it returns.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
