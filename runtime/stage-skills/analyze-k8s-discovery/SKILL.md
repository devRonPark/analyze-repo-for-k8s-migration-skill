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
2. Ground high-signal candidates and exclusions primarily from
   `stage_input.survey`. Keep one-time commands distinct from deployable
   candidates.
3. Create identifiers and observation aliases that satisfy the payload
   contract. Keep raw evidence in MCP observations; do not copy it into claims.
4. Submit one complete `submit_discovery` attempt after this stage's decision
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
submit with `unknown`/`inferred` status on the blocked candidate instead.

**Checkpoint:** do not draft or send user-facing Markdown before
`submit_discovery` returns. A rejected submission may be corrected and
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
