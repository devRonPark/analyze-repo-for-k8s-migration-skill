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
   `discovery_fact_refs`, `execution_fact_refs`, and `unknown_ids`. Use only
   `list_target_paths`, `read_evidence`, `locate_evidence`, and
   `get_target_git_metadata` to ground dependency edges, external runtime
   dependencies, or scoped unknowns for those inputs.
3. Keep incoming fact references unchanged. Create only safe structured graph
   edges and observation aliases; never copy raw evidence into claims.
4. Submit `submit_relationships` once with the incoming envelope.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Every `payload.evidence[].observation_ref` must be issued by an
evidence tool in this current stage.

**Checkpoint:** an `accepted` `submit_relationships` response is this stage's
only completion. Do not draft or send user-facing Markdown before it returns.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
