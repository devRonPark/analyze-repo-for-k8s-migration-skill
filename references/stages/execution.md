# Execution

Apply Vertical Slice, Grounding, and Quality Gate using only the accepted
server response.

1. Read [the Execution rules](../execution-rules.md) and [the payload
   contract](execution/payload-contract.json) before collecting evidence.
2. Ground build, image, startup, runtime, and port facts for the accepted
   `candidate_ids` and `discovery_fact_refs` primarily from `stage_input.survey`.
3. Keep incoming discovery fact references unchanged. Create only safe process
   identifiers and observation aliases; never copy raw evidence into claims.
4. Submit one complete `submit_execution` attempt after the decision is ready.
   Retry only after an explicit server rejection.

**Evidence access:** use the current stage survey first. Call
`read_evidence`, `locate_evidence`, or `list_target_paths` as needed to ground
a current-stage decision. Keep each read targeted. When evidence remains
insufficient, submit the field as `unknown` or `inferred` under its payload
contract.

**Boundary:** incoming `discovery_fact_refs` are accepted facts, not
observation references. Each evidence observation must be issued in this
stage. If no trusted rule or decision identifiers are supplied, submit
`"rule_applications": []`; never infer them.

**Checkpoint:** do not draft user-facing Markdown before `submit_execution`
returns. A rejection authorizes correction only for Execution.
