# Relationships

Apply Vertical Slice, Grounding, and Quality Gate using only the accepted
server response.

1. Read [the dependency analysis rules](../dependency-analysis.md)
   and [the payload contract](relationships/payload-contract.json) before
   collecting evidence.
2. Ground dependency edges, external runtime dependencies, or scoped unknowns
   for the accepted process and fact references from `stage_input.survey`.
3. Keep incoming fact references unchanged. Create only safe graph edges and
   observation aliases; never copy raw evidence into claims.
4. Submit one complete `submit_relationships` attempt after the decision is
   ready. Retry only after an explicit server rejection.

**Ground and precision:** use the current stage survey first. At most one
`read_evidence`, `locate_evidence`, or `list_target_paths` call is allowed;
on budget exhaustion, submit `unknown`/`inferred` for the blocked field.

**Boundary:** incoming `*_fact_refs` are accepted facts, not observation
references. Each evidence observation must be issued in this stage.

**Checkpoint:** do not draft user-facing Markdown before
`submit_relationships` returns. A rejection authorizes correction only for
Relationships.
