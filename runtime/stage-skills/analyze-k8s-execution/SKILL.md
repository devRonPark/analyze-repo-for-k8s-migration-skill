---
name: analyze-k8s-execution
description: Ground execution, build, startup, image, and port facts for accepted candidates.
---

# Execution

Use the incoming handoff only. Apply Vertical Slice, Grounding, and Quality Gate.

1. Read [the Execution rules](references/execution-rules.md) and [the payload
   contract](references/payload-contract.json) before collecting evidence.
2. The incoming `stage_input` owns `mode`, `candidate_ids`,
   `discovery_fact_refs`, and `unknown_ids`. Ground build, image, startup,
   runtime, and port facts for those inputs primarily from
   `stage_input.survey`.
3. Keep the incoming discovery fact references unchanged. Create only safe
   execution process identifiers and observation aliases; never copy raw
   evidence into claims.
4. Submit one complete `submit_execution` attempt after this stage's decision
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

**Boundary:** `discovery_fact_refs` are accepted facts, not observation
references. Every `payload.evidence[].observation_ref` must come from this
stage's `stage_input.survey.observations` or its one precision call.

**Rule applications:** the incoming `stage_input` does not provide
`decision_ids` or `required_rule_ids` for this stage. If it does not
explicitly provide trusted rule or decision identifiers to apply, submit
`"rule_applications": []`. Do not create or infer a `rule_id` or `decision_id`
from claim ids, execution concerns, build/startup facts, process ids,
filenames, or observation aliases. `rule_applications` being a required
payload field does not mean the list must contain an item — an empty list is
valid when no rule context is supplied.

**Checkpoint:** do not draft or send user-facing Markdown before
`submit_execution` returns. A rejected submission may be corrected and
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
