---
name: analyze-k8s-discovery
description: Discover grounded Kubernetes migration candidates only after a trusted start handoff.
---

# Discovery

Use the incoming handoff only. Apply Vertical Slice and Grounding.

1. Read [the Discovery workflow](references/workflow.md). Load
   [language rules](references/language-discovery-rules.md) only for languages
   confirmed in the target. Read [the payload contract](references/payload-contract.json)
   before submission.
2. Use only `list_target_paths`, `read_evidence`, `locate_evidence`, and
   `get_target_git_metadata` to ground high-signal candidates and exclusions.
   Keep one-time commands distinct from deployable candidates.
3. Create identifiers and observation aliases that satisfy the payload
   contract. Keep raw evidence in MCP observations; do not copy it into claims.
4. Submit `submit_discovery` once with the incoming envelope.

**Checkpoint:** an `accepted` `submit_discovery` response is this stage's only
completion. Do not draft or send user-facing Markdown before it returns.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
