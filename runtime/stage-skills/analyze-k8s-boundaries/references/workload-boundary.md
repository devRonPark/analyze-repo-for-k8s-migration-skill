# Workload Boundary Decision

A Workload Unit is an application process operated independently. Treat two
runtime processes as separate units only when both have distinct production
start definitions and independent lifecycle operations. State, security,
resource, network, directory, package, port, dependency, or Secret differences
alone never establish a boundary. Record insufficient evidence as `미확인` with
its `검색(...)` scope rather than inferring a boundary from names.

Keep boundary, lifecycle, and state claims independent: a confirmed boundary
may have an unknown state decision. Summary records only the unit, deployable
status, state decision, and scoped unknowns. Detailed additionally records the
two boundary conditions, lifecycle, candidate inclusion or exclusion, and
supporting evidence.

## Payload consistency rules

Every `workload_units[]` entry is checked against these exact rules, on top of
the field types and enums in the payload contract:

- `boundary_claim_ids` claims must each have `status` equal to the unit's own
  `boundary_status` -- not merely `confirmed`, the same value.
- `deployability_claim_ids` claims must each have `status` equal to
  `deployability_status`.
- `lifecycle_claim_ids` claims must be `unknown` when `lifecycle` is
  `unknown`, otherwise `confirmed` or `inferred`.
- `state_claim_ids` claims must match `state_decision`: `unknown` needs
  `unknown`, `conflicted` needs `conflicted`, anything else needs `confirmed`
  or `inferred`.
- `boundary_status: confirmed` requires `start_definition_status` confirmed,
  and `independent_lifecycle_status` confirmed too -- except for a
  single-process unit (see "Single-process grouping" below), where
  `independent_lifecycle_status` may stay `unknown`.
- `deployable: true` requires `boundary_status` and `start_definition_status`
  confirmed (`independent_lifecycle_status` confirmed too, under the same
  single-process exception), and `deployability_status` `confirmed` or
  `inferred`.
- Every `process_ids` entry from the incoming handoff must end up assigned to
  exactly one workload unit -- none left out, none assigned twice.

A fully grounded, deployable unit looks like this (each `*_claim_ids` array
names a claim from `claims[]` whose own `status` matches the rule above):

```json
{
  "id": "unit-web",
  "process_ids": ["process-web"],
  "candidate_ids": ["candidate-web"],
  "start_definition_status": "confirmed",
  "independent_lifecycle_status": "confirmed",
  "boundary_status": "confirmed",
  "lifecycle": "continuous",
  "state_decision": "externalized",
  "deployable": true,
  "deployability_status": "confirmed",
  "boundary_claim_ids": ["claim-web-boundary"],
  "lifecycle_claim_ids": ["claim-web-lifecycle"],
  "state_claim_ids": ["claim-web-state"],
  "deployability_claim_ids": ["claim-web-deployability"]
}
```

with a matching claim for each `*_claim_ids` entry, e.g.
`{"id": "claim-web-boundary", "status": "confirmed", "evidence_aliases": [...]}`.
When a condition is not grounded, set that status field to `unknown` and give
its linked claim `status: "unknown"` too, rather than guessing `confirmed`.

## Single-process grouping

When the incoming handoff's accepted `process_ids` has exactly one member,
Workload Grouping is deterministic: that one process is necessarily its own
Workload Unit, because there is no second process to compare an independent
lifecycle against. Do not search for healthcheck, volume, restart-policy,
state, or listening-port signals to ground `independent_lifecycle_status` in
this case, and do not cite them if the survey already surfaced them --
strengthening evidence needs something to strengthen, and a single process has
no comparison to strengthen. Leave `independent_lifecycle_status: "unknown"`;
it does not block `boundary_status: confirmed` or `deployable: true` here.
`start_definition_status` still needs its own grounding regardless of process
count.

This exception is about grouping only. Once a unit's process is grouped, its
`lifecycle`, `state_decision`, and `deployability_status` still need their
own evidence exactly as before.
