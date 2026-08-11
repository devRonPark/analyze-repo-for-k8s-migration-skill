# D14 — Host-Activation Parity Correction

## 1. D13 defect and scope

D13 showed that D12 Variant B supplied `host_continuation.skill_content` and then let OpenCode return a native `skill(handoff.next_skill)` result for the same successor. B2 therefore had two successor contexts while A2 had one.

D14 changes only that B ownership seam. Variant A still has native Skill routing; it receives no host-activation state or guard. Stage Skill content, retry budget, validation, payload contracts, timeout, provider configuration, and `next_skill` are unchanged.

## 2. Corrected ownership seam and scope

After a trusted host-owned continuation, the MCP server atomically writes a private record containing `analysis_id`, `revision`, `transition_token`, and `next_skill`. Missing state storage or a write failure fails closed.

Only in Variant B, `scripts/host_owned_skill_guard.js` reads that exact pending record. Its `tool.definition` hook excludes only that successor name from native `skill`'s model-visible schema. Its `tool.execute.before` hook redirects an attempted exact duplicate to a non-existent sentinel before native Skill content can be returned. Other Skills remain available.

The first `analysis_*` action consumes the record. Thus an older consumed transition cannot suppress a later valid Skill operation. Missing or mismatched identity and unknown `next_skill` fail closed. The state is separate from `stage_input`, which is not duplicated.

## 3. Deterministic parity proof

Focused tests exercise the actual guard hooks and the host MCP seam, including attempted duplicate, different Skill, stale transition, rejected stage, unknown successor, and trace fields.

| Path | successor contexts | host activations | native same-successor activations | `stage_input` occurrences |
| --- | ---: | ---: | ---: | ---: |
| A: accepted handoff → native Skill | 1 | 0 | 1 | 1 |
| B: accepted handoff → host context | 1 | 1 | 0 | 1 |

## 4. Verification before provider execution

| Check | Result |
| --- | --- |
| D14 focused ownership/parity | 10 passed (9 host-MCP + 1 guard-hook) |
| D13 parity trace | 11 passed |
| D12 host-owned/static-MCP | 13 passed |
| D09/D10/D11 liveness | 20 passed |
| Timing instrumentation | 18 passed |
| Runtime suite | 211 passed, 1 skipped |
| General suite | 273 passed, 6 skipped |
| Static golden | validator PASS; 4 passed |
| Bundle | 1 passed |

`git diff --check` passed before B3.

## 5. Provider evidence

One B3 only was run: `jpetstore-6` at `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, Summary mode, OpenCode `1.18.14`, `upstage/solar-pro2`, `runtime/opencode.json`, and the same 300-second timeout. Artifacts are retained outside the target at `C:\\temp\\d14-host-parity-20260811\\jpetstore-6-summary\\trace.json` and `terminal.log`.

It timed out with no complete final Markdown report; the target was unchanged before and after. Its sole accepted Dispatcher → Discovery handoff recorded:

```text
transition_owner: host
next_skill: analyze-k8s-discovery
host_activation_observed: true
native_same_skill_invocation_observed: false
total_successor_context_occurrences: 1
stage_input_occurrences: 1
context_size_proxy: 7,293 serialized chars / 2 observable components
first_successor_action: none
```

No duplicate native successor Skill call was persisted. The model produced explanatory Discovery text, but made no `analysis_*` call: no evidence read, no `submit_discovery`, no validation result, and no later handoff.

## 6. A/B comparison

Retained clean A2 is the control because A and the pinned target/provider configuration were unchanged. A3 was unnecessary: B3 failed the required first-action rule.

| Metric | A2 model-routed | corrected B3 host-owned |
| --- | ---: | ---: |
| Accepted handoffs → useful actions | 3 / 4 | 0 / 1 |
| Zero-action stops | 1 | 1 |
| Highest accepted stage | relationships | none |
| Full completion | 0 | 0 |
| Persisted model turns | 13 | 2 |
| Validation rejections | 4 | 0 |
| Elapsed | 309,660 ms | 322,800 ms |
| Target unchanged | yes | yes |

The B3 turn/rejection reduction is not a reliability improvement: it stopped before a useful successor-stage action.

## 7. D12 regression check

```text
Previous B (D12 aggregate):
turns = 48
rejects = 39

Corrected B3:
turns = 2
rejects = 0
```

The D12 rejection/turn explosion did not recur. It changed form: B3 delivered exactly one context but then made no stage action and timed out. This does not prove that duplication caused D12's burst; it proves that its removal alone does not make host-owned continuation reliable.

## 8. Trust checks

Server validation remained authoritative; B3 issued no stage submission to bypass or filter. The target stayed read-only. No stage Skill prose, retry/validation behavior, provider configuration, or final migration architecture changed.

## 9. Outcome

```text
Outcome C — PARITY CORRECTED, HOST-OWNED STILL PATHOLOGICAL
```

Parity is correct, but the required useful successor-stage action was absent. Do not begin the one-public-Skill migration.

## 10. Next ticket

`D15 — RCA Host-Activated Post-Tool Continuation Liveness`

Investigate why Solar/OpenCode can describe the host-loaded successor yet does not issue an `analysis_*` action. Keep the parity guard and do not change stage Skill prose in that RCA.
