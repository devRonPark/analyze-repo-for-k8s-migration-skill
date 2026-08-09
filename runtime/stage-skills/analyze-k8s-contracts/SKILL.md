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
   `fact_statuses`, `required_report_slot_ids`, and `unknown_ids`. Use only `list_target_paths`,
   `read_evidence`, `locate_evidence`, and `get_target_git_metadata`.
3. Close every server-selected `report_slots` entry with a matching-status,
   allowed-stage fact reference or a scoped evidence claim. Record facts and gaps only; do not
   create recommendation values.
4. Submit `submit_contracts` once with the incoming envelope.

Do not load another Skill, read another stage's references, or infer a later
procedure. End this stage after the server response.
