# D08 Deterministic Degraded Recovery

## RCA input

This implementation is the narrow follow-up to
[D08_RETRY_ROOT_CAUSE.md](D08_RETRY_ROOT_CAUSE.md), Outcome C. It does not
re-open the RCA's corrected protocol defects and applies only to the
`Boundaries` stage.

## Recovery contract

Every Boundaries submission is still run through the normal deterministic
validator. A rejected model payload is never normalized into accepted state;
only compact server-owned loop metadata is retained.

The recovery threshold is four **consecutive actionable** Boundaries
rejections. A count alone cannot trigger recovery.

- **R1 — blind loop:** all four have the same server error code and relevant
  error path, and the canonical fingerprint of that path's projection is
  unchanged. The projection is path-local (`workload_units`,
  `candidate_exclusions`, claims, evidence, rules, or the declared Boundary
  shape), not full-payload bytes.
- **R2 — changing nonconvergence:** all four are actionable Boundary-decision
  errors (`workload_units` or `candidate_exclusions`) and each next submission
  has a different canonical Boundary decision projection. Ordering and
  non-decision envelope changes do not qualify as a correction.

An un-actionable rejection records a sequence boundary and prevents an older
attempt from being used to establish either class. The server also requires
the active stage to remain `Boundaries`, an unchanged snapshot, an unaccepted
Boundaries output, and the normal validation error that supplied the
actionable correction.

Recovery is fail-closed unless the server has exactly one accepted execution
process, the server-issued Boundaries survey has a start-definition
observation, and it has scoped-absence observations for lifecycle and
persistent-writable-location decisions. The single-process grouping rule is
the only grouping fact introduced by D08. A confirmed start survey observation
may set `start_definition_status=confirmed`; all unresolved Boundary,
lifecycle, state, deployability, and candidate-eligibility conclusions remain
`unknown` and carry their appropriate server-issued absence observation.

The server constructs a new payload from accepted predecessor identifiers and
those observations, validates it with the ordinary Boundaries validator, and
then applies the existing trusted transition. It never reads a rejected
payload except to fingerprint the bounded loop. If this construction cannot
validate, `boundaries_recovery_unavailable` leaves Boundaries open.

The accepted handoff carries a server-owned `recovery` marker with stage,
class, degradation reason, safe attempt metadata, trusted inputs, and unknown
categories. Contracts receives the ordinary Boundaries fact handoff; it needs
no client recovery flag or special authority.

## Deterministic tracer results

`runtime.python.tests.test_boundaries_recovery` covers these vertical cases:

| Case | Result |
| --- | --- |
| Normal valid Boundaries submission | normal acceptance; no recovery marker |
| One actionable rejection then valid correction | normal acceptance; no recovery marker |
| R1 unchanged invalid `workload_units` | four validated rejections, then degraded R1 acceptance |
| R2 changing invalid `workload_units` | four validated changing rejections, then degraded R2 acceptance |
| Missing trusted survey inputs | fail closed; no Boundaries output |
| Rejected unsupported assertion | absent from recovered accepted output |
| Snapshot change before recovery | `target_snapshot_changed` wins |
| Recovered Boundaries | ordinary Contracts handoff and Finalize completion |

The recovery tests also cover a confirmed server survey start observation, as
seen in the JPetStore Boundaries survey.

## RCA baseline and D08 provider trace

The RCA's latest standard-harness trace recorded Discovery accepted on its
first submission, Execution accepted on its first submission, Relationships
accepted after one correction, and four changing malformed Boundaries
submissions before timeout. Its earlier post-fix trace recorded 2/1/1/14/5
submissions for Discovery/Execution/Relationships/Boundaries/Contracts,
respectively, with Boundaries accepting on submission 14 and Contracts never
accepting. Finalize had no accepted submission in either trace.

| Stage | RCA baseline (latest standard trace) | D08 Solar run 1 | D08 Solar run 2 | D08 Solar run 3 |
| --- | --- | --- |
| Discovery | 1 accepted | 1 accepted | 1 accepted | no submission |
| Execution | 1 accepted | not submitted | 1 accepted | not reached |
| Relationships | 2 submissions, 1 rejection, accepted | not reached | 1 accepted | not reached |
| Boundaries | 4 changing malformed submissions, no acceptance | not reached | handoff reached; no submission | not reached |
| Contracts | not reached | not reached | not reached | not reached |
| Finalize | not reached | not reached | not reached | not reached |

Provider-backed run: `jpetstore-6-summary`, pinned revision
`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, `upstage/solar-pro2`, interactive
Windows PTY, 300-second timeout. The provider accepted Discovery, then made no
Execution submission and timed out after 309.685 seconds. Therefore no R1/R2
classification or recovery occurred in this run. The target Git status was
unchanged before and after (`## HEAD (no branch)`). This is a new explicit
provider non-submission failure, not evidence that validation or recovery
failed.

The equivalent second run accepted Discovery, Execution, and Relationships,
then made no Boundaries submission and timed out after 309.376 seconds. It
also supplied five accepted execution process identifiers, rather than the
single-process RCA path; D08 would correctly fail closed for that input even
after four eligible rejections because it cannot safely manufacture a
multi-process grouping. The target Git status again remained unchanged. This
is a second, distinct provider non-submission path; neither provider run
reproduced the RCA's Boundaries R2 sequence.

The third equivalent run reached only `start_analysis`, made no Discovery
submission, and timed out after 309.192 seconds. The Upstage models endpoint
returned HTTP 200 in the immediately preceding preflight, and the target Git
status again remained unchanged. Across all three D08 runs, the provider did
not reproduce the RCA's Boundaries R2 sequence; no further retries were made.

## Trust invariants

- Evidence comes only from the server-issued survey/registry and remains
  snapshot-bound and redacted.
- The recovery payload is separately constructed and fully validated before
  the ordinary state transition.
- Rejected model assertions, evidence aliases, identifiers, and values are
  never promoted.
- State, revision, catalog, stage ordering, and snapshot checks remain owned
  by the existing pipeline.
- There is no model-controlled degraded flag, no validator bypass, and no
  fabricated evidence or candidate/process identifier.

## Verification

```text
PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s runtime/python/tests
# 202 passed, 1 skipped

PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s tests
# 240 passed, 6 skipped

PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python scripts/validate_static_mcp_goldens.py
# Static MCP golden manifest: PASS

PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python tests/test_skill_bundle.py
# 1 passed
```

## Deferred architecture work

Dynamic tool catalogs, a generic recovery engine, a generic stage engine,
`AnalysisSession` decomposition, and validator consolidation remain deferred.
They are not required to recover the single-process Boundaries tracer bullet.

## Next ticket

Reproduce the new Solar non-submission between Discovery and Execution before
changing runtime behaviour. Do not broaden D08 recovery to another stage or
weaken its preconditions without a separate RCA and deterministic tracer.
