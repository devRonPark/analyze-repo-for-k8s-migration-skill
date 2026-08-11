# Discovery

Apply Vertical Slice and Grounding using only the accepted server response.

1. Read [the Discovery workflow](../workflow.md). Load
   [language rules](../language-discovery-rules.md) only for languages
   confirmed in the target. Read [the payload contract](discovery/payload-contract.json)
   before submission.
2. Ground high-signal candidates and exclusions primarily from
   `stage_input.survey`. Keep one-time commands distinct from deployable
   candidates.
3. Create identifiers and observation aliases that satisfy the payload
   contract. Keep raw evidence in MCP observations; do not copy it into claims.
4. Submit one complete `submit_discovery` attempt after this stage's decision
   is ready. Retry only after an explicit server rejection.

**Ground:** `stage_input.survey` carries this stage's bounded, redacted
evidence. A missing category is a scoped absence observation, not an error.

**Evidence access:** use the current stage survey first. Call
`read_evidence`, `locate_evidence`, or `list_target_paths` as needed to ground
a current-stage decision. Keep each read targeted; do not inspect future-stage
concerns. When evidence remains insufficient, submit the candidate as
`unknown` or `inferred` under its payload contract.

**Checkpoint:** do not draft or send user-facing Markdown before
`submit_discovery` returns. A rejection authorizes correction only for
Discovery; do not inspect another stage procedure.
