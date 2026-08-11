# D08 Retry Root Cause Analysis

## Status

Outcome C — proceed to deterministic degraded recovery, explicitly targeting
the remaining provider/model failure class. The reproduced protocol defects
were corrected; Solar still repeats invalid payloads after complete,
deterministic correction information.

## Observed symptom and reproduction

The Windows-native static-MCP PTY procedure was run against the pinned
JPetStore 6 revision `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, with
`upstage/solar-pro2`, Summary mode, a 300-second timeout, and an unchanged
target Git status before/after each run. The normal CLI entry was blocked
before model invocation by the known golden-manifest hash mismatch; the same
`_run_static_mcp_case()` PTY implementation was then used directly, as the
Windows runbook permits for that condition.

Safe compact traces (stored outside the target):

```text
Before: C:\tmp\d08-rca-baseline-direct-20260811090456\jpetstore-6-summary\trace.json
  Discovery: accepted on submission 1
  Execution: accepted on submission 1
  Relationships:
    1: unknown claim requires a scoped-absence observation
    2: invalid relationship mechanism
    3+: identical invalid relationship mechanism despite no relevant correction
    control: reopen_analysis -> reopen_not_ready
  Result: timeout; no final report

After: C:\tmp\d08-rca-after-20260811092010\jpetstore-6-summary\trace.json
  Discovery:
    1: undeclared decision referenced by a rule
    2: accepted
  Execution: accepted on submission 1
  Relationships:
    1: invalid relationship endpoint_name
    2: accepted
  Boundaries:
    1-4: invalid workload boundary status
    5-13: further distinct/partially corrected workload errors
    14: accepted
  Contracts:
    1: claim evidence aliases required
    2-4: invalid_report_state_contract
    5: same invalid_report_state_contract with an unchanged payload
  Finalize:
    17 calls while Contracts remained open -> stage_order
  Result: timeout; no final report
```

The second run is not a reliable performance comparison: provider output
varied in the earlier stages. It nevertheless supplies current, executable
evidence that a protocol-induced loop remains.

## Submission counts

`accepted` counts only accepted stage submissions. `rejected` excludes invalid
control actions.

| Stage | Before submissions | Before rejected | Before accepted | After submissions | After rejected | After accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Discovery | 1 | 0 | 1 | 2 | 1 | 1 |
| Execution | 1 | 0 | 1 | 1 | 0 | 1 |
| Relationships | 39 | 39 | 0 | 2 | 1 | 1 |
| Boundaries | unavailable (not reached) | unavailable | unavailable | 14 | 13 | 1 |
| Contracts | unavailable (not reached) | unavailable | unavailable | 5 | 5 | 0 |
| Finalize | unavailable (not reached) | unavailable | unavailable | 0 | 0 | 0 |

Invalid control actions: before had one `reopen_analysis` call; after had 17
`finalize_analysis` calls. The after trace therefore fails the no-blind-loop
acceptance criterion.

## Rejection taxonomy and conclusions

| Category | Evidence | Conclusion |
| --- | --- | --- |
| P1 missing/inaccessible contract | The sealed-bundle test verifies each stage's generated `references/payload-contract.json` projection is present and equals the source contract. | Rejected for the current runtime. |
| P2 vocabulary mismatch | Current source has no `client_payload_submission_template`, `submission_template`, or `survey_reference`; the executable contract, survey, MCP schema, and skills use `observation_ref`. | Rejected for this branch; historical reports do not establish a current defect. |
| P3 alias/reference identity confusion | The model successfully formed aliases from server-issued observations in Discovery and Execution. The before Relationships attempt initially omitted aliases for unknown claims, then supplied scoped-absence aliases. | Dual identity is cognitively costly but not confirmed as the live loop's cause. |
| P4/P5 payload and referential errors | Discovery rule/decision mismatch and Contracts claim evidence alias rejection were deterministic, but their errors did not always identify all safe corrective fields. | Confirmed correction-information gap. |
| P6 semantic/domain validation | Relationships `mechanism` rejected prose despite the wire schema's identifier rule; Boundaries and Contracts then exposed multiple opaque domain errors. | Confirmed. The mechanism error was a repeated identical loop before the change. |
| P7 invalid stage/control action | The catalog exposed an undelivered `reopen_analysis`, which was called in the before trace; the static catalog also exposes finalization while Contracts is still open, and it was called 17 times after. | Confirmed invalid-affordance contribution. |
| P8 repeated identical correction | Before: repeated `invalid relationship mechanism`; after: repeated `invalid_report_state_contract` with the fifth Contracts payload unchanged, and 17 identical `stage_order` finalize failures. | Confirmed; D08-RCA is not complete. |
| P9 provider/model reasoning | The model made invalid values even when a JSON schema was available. But opaque/serial corrections and invalid tools were also exposed, so this cannot yet be classified primarily as provider behavior. | Not established. |

## Confirmed root causes

1. An undelivered `reopen_analysis` action was advertised as callable. Its only
   response was a permanent failure, yet the provider selected it after a
   submission loop.
2. The Relationships validator reported `invalid relationship mechanism`
   without the executable field path, identifier grammar, or corrective
   representation. The provider repeatedly resubmitted the same relevant
   field.
3. Other stage validators still expose similarly opaque correction surfaces;
   the current Contracts `invalid_report_state_contract` loop and premature
   finalization demonstrate that the two minimal fixes do not remove all
   protocol-induced retries.

## Minimal fixes made

1. Removed `reopen_analysis` from the MCP tool catalog, static catalog, and
   acceptance trace allowlist. This removes the reproduced invalid affordance;
   it does not change state ownership or stage ordering.
2. Mapped the reproduced Relationships mechanism failure to the retryable
   `invalid_relationship_mechanism` code with
   `payload.graph_edges[].mechanism`, its wire identifier pattern, and safe
   examples (`jdbc`, `spring_boot`). This does not repair client input or
   relax validation.
3. Expanded the sealed-bundle regression check from Discovery only to all five
   stage-owned payload-contract projections.

## Explicitly deferred architectural observations

- Dynamic stage-specific tool catalogs could prevent premature finalization,
  but the current evidence does not justify building dynamic MCP tool
  infrastructure inside this ticket.
- Validator ownership and `AnalysisSession` decomposition remain broader
  cleanup opportunities, not demonstrated causes of the individual loops.
- A generic error taxonomy or generic stage engine is deferred. The next ticket
  must first reproduce and correct the specific Boundaries/Contracts error
  surfaces listed above.

## Trust-boundary assessment

The fixes preserve server-issued observations, server-derived evidence
identity, snapshot binding, immutable accepted state, deterministic validation,
stage order, accepted-fact handoff, and redaction. No client assertion was
accepted or repaired by the server.

## Verification

```text
PYTHONPATH='runtime/python;.' python -m unittest runtime.python.tests.test_server_owned_control_plane runtime.python.tests.test_submit_retry_budget
# 10 tests passed (executed with Windows temporary-fixture access)

PYTHONPATH='runtime/python;.' python tests/test_skill_bundle.py
# 1 test passed

PYTHONPATH='runtime/python;.' python -m unittest runtime.python.tests.test_retry_protocol_corrections
# 2 tests passed
```

The complete broader suite was not run because the provider-backed acceptance
run remained materially failing; it would not establish D08 readiness.

## Recommended next ticket

`D08: deterministic degraded recovery for explicit provider correction
nonconvergence`.

The recovery ticket must consume the observable condition only after the server
has returned an actionable correction and the provider repeats the same
`(stage, error_code, path)` without a relevant payload change. It must not
weaken evidence, validation, or accepted-state ownership.

## Continued reproduction after minimal corrections

Two additional identical Solar/JPetStore PTY runs narrowed the remaining
behavior without introducing recovery logic:

```text
C:\tmp\d08-rca-after-edge-aggregate-20260811094716\jpetstore-6-summary\trace.json
  Discovery: 1 accepted
  Execution: 1 accepted
  Relationships: 1 target-process correction, then accepted
  Boundaries:
    attempt 1: missing boundaries payload field(s): candidate_exclusions,
               claims, discovery_fact_refs, evidence, execution_fact_refs,
               relationship_fact_refs, rule_applications, schema_version,
               stage, workload_units
    attempt 2: identical error with an unchanged empty payload
```

The first rejection supplied every missing wire field in one deterministic,
safe response. The second attempt did not change the relevant cause. This is
the required P8 observation, but it is explained as P9: provider/model
nonconvergence after adequate deterministic guidance, not a remaining hidden
protocol ambiguity. Later Boundaries attempts changed payloads but remained
invalid; they are provider reasoning failures rather than blind retries.

Additional minimal corrections made during this continued RCA:

- report-slot set mismatches now distinguish unexpected and missing
  server-selected IDs instead of returning `invalid_report_state_contract`;
- missing and extra stage payload fields are returned together;
- independent Relationships edge identifier/enum failures are returned
  together; and
- Boundaries condition fields name all invalid fields, allowed values, and the
  exact conditions for confirmed/deployable status.

Focused verification after these additions:

```text
PYTHONPATH='runtime/python;.' python -m unittest runtime.python.tests.test_contracts_correction_protocol runtime.python.tests.test_relationships_stage runtime.python.tests.test_boundaries_stage runtime.python.tests.test_retry_protocol_corrections runtime.python.tests.test_server_owned_control_plane runtime.python.tests.test_submit_retry_budget
# 59 tests passed
```

## Standard harness and full verification

The stale `static-mcp-golden-manifest.json` digests were resealed against the
unchanged six golden files. This restores the standard CLI path; it does not
alter golden evidence. `scripts/mcp_smoke.py` was updated from 12 to 11 tools
to match removal of the undelivered reopen affordance.

```text
PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s runtime/python/tests
# 168 passed, 1 skipped

PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s tests
# 240 passed, 6 skipped

PYTHONPATH='runtime/python;.' python scripts/validate_static_mcp_goldens.py
# Static MCP golden manifest: PASS
```

The standard interactive command, rather than the direct harness fallback,
then ran successfully through its golden preflight:

```text
C:\tmp\d08-rca-standard-20260811095848\jpetstore-6-summary\trace.json
  Discovery: accepted on submission 1
  Execution: accepted on submission 1
  Relationships: invalid_relationship_edge_fields, then accepted on submission 2
  Boundaries: four changing malformed submissions; no repeated identical
              `(stage, error_code, path)` with an unchanged relevant payload
  Final result: provider timeout before a report; target Git status unchanged
```

The remaining Boundaries behavior is not a blind correction loop: each attempt
changed the payload and received a different deterministic error. It is the
explicit nonconvergence target for D08 recovery, not evidence to relax or
expand the trusted pipeline protocol.
