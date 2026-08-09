---
name: analyze-k8s-contracts
description: Close evidence-linked configuration, readiness, and report input gaps only.
---

# Contracts

Use the incoming handoff only. Apply Gap Analysis and Quality Gate.

1. Read [configuration timing](references/configuration-timing.md),
   [evidence and readiness](references/evidence-and-readiness.md),
   [the server-selected report slots](references/report-slots.json), and
   [the payload contract](references/payload-contract.json) before evidence.
   Read [the Detailed checklist](references/repository-analysis-checklist.md)
   only when `mode` is `detailed`.
2. The incoming `stage_input` owns `mode`, `unit_ids`,
   `included_candidate_ids`, `excluded_candidate_ids`, `discovery_fact_refs`,
   `execution_fact_refs`, `relationship_fact_refs`, `boundaries_fact_refs`,
   `fact_statuses`, `required_report_slot_ids`, and `unknown_ids`. Ground
   those inputs primarily from `stage_input.survey`.
3. Close every server-selected `report_slots` entry with a matching-status,
   allowed-stage fact reference or a scoped evidence claim. Record facts and gaps only; do not
   create recommendation values.
4. Submit `submit_contracts` once with the incoming envelope.

**Ground:** the incoming handoff's `stage_input.survey` already carries this
stage's bounded, redacted evidence (`observations[]`, each with an
`observation_ref`, status, and safe `path:line` reference). Read it before
calling any evidence tool; a missing category is a scoped absence
observation, not an error. For a report slot with no eligible predecessor
fact, `survey.observations` includes one dedicated observation tagged
`category: "report_slot:<slot_id>"` — ground that slot's claim from it
directly rather than searching for one.

**Precision (optional, at most one call):** call `read_evidence`,
`locate_evidence`, or `list_target_paths` only if one current decision is
still blocked after grounding from the survey. `get_target_git_metadata` is
not counted against this budget. A `precision_budget_exhausted` response
means stop searching — the identical error repeats on any further call — and
submit with `unknown`/`inferred` status on the blocked field instead.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Every `payload.evidence[].observation_ref` must come from this
stage's `stage_input.survey.observations` or its one precision call.

**Checkpoint:** an `accepted` `submit_contracts` response is this stage's only
completion. Do not draft or send user-facing Markdown before it returns. A
rejected submission may be corrected and resubmitted; after three rejections
in this stage, further attempts are marked non-retryable — resolve the
specific issue named in the response or submit with `unknown`/`inferred`
status instead of resubmitting the same payload.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
