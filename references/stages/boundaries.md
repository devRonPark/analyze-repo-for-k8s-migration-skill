# Boundaries

Apply Workload Boundary, Grounding, and Quality Gate using only the accepted
server response.

1. Read [the workload-boundary rules](boundaries/workload-boundary.md) and
   [the payload contract](boundaries/payload-contract.json) before evidence.
2. Ground accepted candidates, processes, graph edges, fact references, and
   unknowns primarily from `stage_input.survey`.
3. Create only safe workload units. A deployable unit needs both a distinct
   start definition and an independent lifecycle; directories and ports alone
   never create a unit. For one accepted process, read the reference's
   "Single-process grouping" rule before searching for lifecycle evidence.
4. Submit one complete `submit_boundaries` attempt after the decision is ready.
   Retry only after an explicit server rejection.

**Evidence access:** use the current stage survey first. Call
`read_evidence`, `locate_evidence`, or `list_target_paths` as needed to ground
a current-stage decision. Keep each read targeted. When evidence remains
insufficient, submit the field as `unknown` or `inferred` under its payload
contract.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Each evidence observation must be issued in this stage.

**Checkpoint:** do not draft user-facing Markdown before `submit_boundaries`
returns. A rejection authorizes correction only for Boundaries. The server may
apply its independently justified degraded recovery; do not bypass it.
