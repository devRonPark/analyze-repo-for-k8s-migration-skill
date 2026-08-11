# D12 Host-Owned Stage Transition / Continuation Ablation

## 1. Hypothesis and scope

This ablation tests whether moving only deterministic accepted-handoff
continuation from the model to the host makes an accepted handoff reach a
useful next-stage action more reliably.

It preserves the server as the authority for the active stage, accepted
state, `next_skill`, transition token, validation, and rendering. The model
continues to perform evidence interpretation and submit stage payloads. It
does not promote any model assertion or construct any host payload.

The default remains `model_routed`. `host_owned` is an explicit experiment
mode; it is not a production-default change.

## 2. Experimental seam

OpenCode 1.x exposes no host API that can invoke its internal `skill` tool in
an existing assistant turn. The narrow available seam is therefore the MCP
host response immediately after `start_analysis` or a `submit_<stage>` call
has already returned an accepted handoff and before OpenCode requests the
next model token.

In `host_owned` mode, `Server.tool_call()` calls the small continuation helper
only after a successful trusted response. The helper consumes exactly
`handoff.next_skill`, verifies it against the server's current stage,
`analysis_id`, revision, and transition token, reads only that installed
Skill's `SKILL.md`, and appends it as `host_continuation` in the same accepted
response. Its activation instruction tells the model that the host has already
loaded the Skill, so the model need not decide to call `skill(next_skill)`.

This is the smallest reversible intervention because it changes neither the
server state transition nor an OpenCode session mechanism. It only changes
which owner materializes the already-authoritative successor Skill context.
The stage Skill files themselves are byte-for-byte unchanged.

The host fails closed with `host_continuation_failed` for a non-accepted,
missing, unknown, stale, mismatched, or unreadable successor handoff. It does
not select an alternative stage or Skill.

## 3. A/B invariants

| Invariant | Variant A: model-routed | Variant B: host-owned |
| --- | --- | --- |
| Server-issued `next_skill` | Consumed by the model | Consumed exactly by the host |
| Stage order, token, revision, validation | Unchanged | Unchanged |
| Stage reasoning and payload construction | Model | Model |
| Evidence collection and target access | Existing trusted MCP tools | Existing trusted MCP tools |
| Skill source and content | Existing installed Skill | Exact same installed Skill content |
| Provider, model, mode, timeout, retries | `upstage/solar-pro2`, Summary, 300 s, existing policy | Identical |
| Default behavior | `model_routed` | Not selected unless explicit |

## 4. Deterministic verification

`host_owned` contract tests cover unchanged Variant A, exact accepted
`next_skill` consumption, rejected handoffs, missing/unknown Skills, stale
tokens, ordered multi-stage consumption, and unchanged validation behavior.
The existing D08 recovery and D09/D10/D11 observability suites remain active.

```text
D12 focused: 8 passed
D09/D10/D11: 20 passed
D08 recovery: 34 passed
timing: 18 passed
runtime: 210 passed, 1 skipped
general: 260 passed, 6 skipped
golden: 4 passed
bundle: 1 passed
```

The broader runtime and general suites were rerun with `PYTHONUTF8=1` after a
Windows child-process encoding mismatch; the passing rerun is the recorded
verification result.

## 5. Provider-backed runs

All runs used the Windows static-MCP PTY harness with the pinned
`jpetstore-6-summary` case, target revision
`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, `upstage/solar-pro2`, Summary
mode, `runtime/opencode.json`, and the same 300-second timeout. Artifacts are
preserved outside the target under `C:\temp\d12-ablation-20260811`.

| Run | Owner | Result | Accepted handoffs → actions | Zero-action stops | Accepted high-water stage | Validation rejections | Turns | Elapsed | Target unchanged |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| A1 | model | timeout | 0 / 1 | 1 | none | 0 | 3 | 309,772 ms | yes |
| B1 | host | timeout | 0 / 1 | 1 | none | 0 | 1 | 310,045 ms | yes |
| A2 | model | timeout | 3 / 4 | 1 | relationships | 4 | 13 | 309,660 ms | yes |
| B2 | host | timeout | 4 / 4 | 0 | relationships | 39 | 47 | 310,243 ms | yes |

No run reached canonical finalization. The high-water stage is the last
accepted completed stage, not merely a loaded or entered Skill.

## 6. Transition funnels

The useful boundary is an accepted handoff reaching the first next-stage
analysis action, not Skill-load rate.

| Accepted transition | A model-routed | B host-owned |
| --- | ---: | ---: |
| Dispatcher → Discovery | 1 / 2 | 1 / 2 |
| Discovery → Execution | 1 / 1 | 1 / 1 |
| Execution → Relationships | 1 / 1 | 1 / 1 |
| Relationships → Boundaries | 0 / 1 | 1 / 1 |
| Boundaries → Contracts | not reached | not accepted |
| Contracts → Finalize | not reached | not reached |

Aggregate handoff reach rate was 3 / 5 for A and 4 / 5 for B. That apparent
one-handoff difference is not sufficient evidence for promotion: B's only
further-progressing run also produced 39 server validation rejections, mainly
at Boundaries and then rejected out-of-order Contracts/Finalize attempts.
Those rejections were retained rather than being retried or filtered.

## 7. Comparison and trust check

| Metric | A model-routed | B host-owned |
| --- | ---: | ---: |
| Accepted handoffs | 5 | 5 |
| Handoffs reaching action | 3 | 4 |
| Zero-action stops | 2 | 1 |
| Highest accepted stage | relationships | relationships |
| Full completions | 0 | 0 |
| Model turns | 16 | 48 |
| Validation rejections | 4 | 39 |
| Elapsed time | 619,432 ms | 620,288 ms |
| Target unchanged | 2 / 2 | 2 / 2 |

```text
server validation unchanged: yes; deterministic and provider evidence retained rejections
stage order unchanged: yes; server rejected out-of-order calls
rejected assertions unchanged: yes; D08 recovery and validation tests passed
target mutation: none in all four provider attempts
final rendering unchanged: deterministic finalization coverage passed; no provider run reached rendering
```

## 8. Observed failure classes

* Both owners can complete a successor context activation and still produce no
  next-stage action.
* Both owners timed out before a complete final report.
* B2 reached the Boundaries action where A2 stopped at that boundary, but then
  entered a large server-rejected correction/ordering sequence. The host did
  not bypass validation; it also did not reduce model turns.

## 9. Decision

```text
Outcome D — INSUFFICIENT EVIDENCE
```

The two paired runs are stochastic and contradictory at the decision boundary:
B has a higher observed handoff-to-action count, but no higher accepted-stage
or completion result and a much larger validation-rejection/turn count. The
experiment therefore cannot establish that host-owned continuation materially
improves reliable pipeline progress without weakening the practical trusted
analysis contract.

## 10. Recommended next ticket

`D13 — Host-Activated Context Parity Trace`

Run one bounded, paired trace that stops immediately after the first
host-activated Boundaries action and records only the validated next model
turn and its first action, before any correction sequence can dominate the
metric. Keep the same server response, target, provider, timeout, stage Skills,
and validation policy; do not implement it as a retry mechanism.
