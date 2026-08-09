---
name: analyze-k8s-execution
description: Ground execution, build, startup, image, and port facts for accepted candidates.
---

# Execution

Use the incoming handoff only. Apply Vertical Slice, Grounding, and Quality Gate.

1. Read [the Execution rules](references/execution-rules.md) and [the payload
   contract](references/payload-contract.json) before collecting evidence.
2. The incoming `stage_input` owns `mode`, `candidate_ids`,
   `discovery_fact_refs`, and `unknown_ids`. Use only
   `list_target_paths`, `read_evidence`, `locate_evidence`, and
   `get_target_git_metadata` to ground build, image, startup, runtime, and
   port facts for those inputs.
3. Keep the incoming discovery fact references unchanged. Create only safe
   execution process identifiers and observation aliases; never copy raw
   evidence into claims.
4. Submit `submit_execution` once with the incoming envelope.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
