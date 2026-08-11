# Contracts

Apply Gap Analysis and Quality Gate using only the accepted server response.

1. Read [configuration timing](../configuration-timing.md), [evidence
   and readiness](../evidence-and-readiness.md), [the server-selected
   report slots](contracts/report-slots.json), and [the payload
   contract](contracts/payload-contract.json). Read [the Detailed checklist](../repository-analysis-checklist.md)
   only when `mode` is `detailed`.
2. Ground accepted units, predecessor facts, fact statuses, report slots, and
   unknowns primarily from `stage_input.survey`.
3. Close every server-selected report slot with an allowed-stage fact reference
   or scoped evidence claim. Record facts and gaps only; do not recommend
   values.
4. Submit one complete `submit_contracts` attempt after the decision is ready.
   Retry only after an explicit server rejection.

**Evidence access:** use the current stage survey first. Call
`read_evidence`, `locate_evidence`, or `list_target_paths` as needed to ground
a current-stage decision. Keep each read targeted. When evidence remains
insufficient, submit the field as `unknown` or `inferred` under its payload
contract.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Each evidence observation must be issued in this stage.

**Checkpoint:** do not draft user-facing Markdown before `submit_contracts`
returns. A rejection authorizes correction only for Contracts.
