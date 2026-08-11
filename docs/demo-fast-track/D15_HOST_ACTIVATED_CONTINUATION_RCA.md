# D15 — Host-Activated Post-Tool Continuation Liveness RCA

## 1. Scope and D14 baseline

D14 established deterministic successor-context parity for host-owned transitions:

```text
successor contexts = 1
host activations = 1
native same-successor Skill calls = 0
stage_input occurrences = 1
```

Its B3 provider trace still stopped after Dispatcher → Discovery. The retained
B3 normalized trace contained an assistant-text observation but did not retain
the assistant lifecycle or any session-status record, so it could not answer
whether OpenCode had scheduled and completed a continuation turn. This ticket
does not alter the agent, stage Skills, provider settings, timeouts, server
state, validation, or the D14 guard. It adds only a safe lifecycle projection
to the existing D09–D14 `stage_transitions` extraction.

OpenCode was verified as `1.18.14` from the installed executable.

## 2. Evidence boundary and instrumentation

The existing SQLite extractor already reads persisted `message` and `part`
records. D15 retains only categorical assistant lifecycle fields, message and
session identities, timestamps, part-type presence, and a persisted session
status when one exists. It never retains assistant prose, raw provider
responses, provider errors, or raw session metadata.

Each accepted handoff now adds `continuation_trace` with:

```text
context source and message/session identity
native tool lifecycle/result availability
successor continuation turn creation/completion and finish
first follow-up analysis tool
whether the next model step is observed
persisted session status after the turn, otherwise unavailable
```

For a native context, the causally bounded successor turn begins strictly
after the persisted Skill-result completion. For a host context, it begins
strictly after the accepted handoff result containing `host_continuation`.
Both bounds end before the next accepted handoff. Ambiguous or absent message
association remains `lifecycle_unavailable`.

`session.status` is not assumed from an assistant `finish`. A status is
reported only when a persisted session row for the same session has a timestamp
at or after the bounded assistant completion.

## 3. Native continuation anatomy (retained A2)

The retained D12 A2 `Dispatcher → Discovery` transition is the successful
native control. It is the same pinned target and provider configuration as B4.

```text
accepted start_analysis handoff completed: 1786424421828
native skill(analyze-k8s-discovery) tool part created: 1786424422752
native Skill result completed: 1786424422826
continuation assistant message created: 1786424422845
continuation assistant message completed: 1786424431814
normalized assistant finish: tool-calls
first follow-up analysis action: submit_discovery at 1786424430226
accepted Discovery submission: 1786424447094
```

The normalized A2 trace proves a completed native Skill tool lifecycle and a
separate successor assistant message with `tool`, `step-start`, and
`step-finish` parts. The follow-up action is in that assistant message. The
retained A2 trace has no persisted session-status projection, so its state
after the turn is unavailable. It does not retain the raw provider finish
reason; `message.data.finish = tool-calls` is the available OpenCode-normalized
finish.

## 4. Corrected host continuation anatomy (B4)

B4 was a single new host-owned run because the necessary assistant lifecycle
fields were unavailable in B3. It used the pinned `jpetstore-6-summary` target
at `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, Summary mode,
`upstage/solar-pro2`, `runtime/opencode.json`, and the Windows PTY/static-MCP
procedure. Artifacts are retained outside the target under
`C:\temp\d15-continuation-20260811\jpetstore-6-summary`.

```text
accepted start_analysis handoff plus host successor context completed: 1786428818840
host activation: observed
successor context count: 1
native same-successor Skill call: not observed
successor assistant message created: 1786428818901
successor assistant message completed: 1786428822030
normalized assistant finish: stop
text part: observed
tool part / analysis action: not observed
next model step after host context: observed (the completed successor message)
next scheduled model step after stop: not observed
persisted session status after turn: unavailable
```

The B4 assistant message shares the accepted handoff's OpenCode session and
starts after its completion. It has `step-start`, `text`, and `step-finish`
parts, no `tool` part, no error, and no abort. The harness waited for a complete
final report until its 300-second deadline; this is not evidence of a provider
timeout during the already-completed stop turn. The persisted database has no
session status row, so D15 cannot state that the session was idle after that
turn. It also cannot state that another model step was scheduled after `stop`.

## 5. First continuation-semantic divergence

```text
Last equivalent event:
the accepted start_analysis tool result is complete and the model has exactly
one server-selected Discovery successor context plus one stage_input.

First divergent event:
in A, the continuation model turn invokes native skill(analyze-k8s-discovery).
OpenCode persists that completed tool result and automatically creates one more
assistant turn, which finishes with tool-calls and invokes submit_discovery.
In B, the host places the same successor context inside the already-completed
start_analysis result. OpenCode creates the immediate successor assistant turn,
but there is no native Skill tool lifecycle and therefore no subsequent
tool-result-triggered assistant turn; that immediate turn finishes stop.
```

This matters because host activation is not an additional OpenCode tool
lifecycle. It is model-visible content in the preceding analysis tool result.
The native path has one extra model-loop boundary: assistant `skill` call →
completed native tool result → automatically scheduled assistant step. The
host path demonstrably receives an ordinary continuation after `start_analysis`,
but it does not reproduce that additional boundary.

## 6. Provider and normalized finish evidence

| Path | Provider-native finish | OpenCode-normalized finish | Tool lifecycle | Next assistant step | First action |
| --- | --- | --- | --- | --- | --- |
| A2 native | unavailable in retained artifacts | `tool-calls` | completed native Skill result | observed | `submit_discovery` |
| B4 host | unavailable in retained artifacts | `stop` | host context only; no native Skill result | immediate continuation observed; no later step observed | none |

The absent raw provider finish is intentional: neither retained trace stores
raw provider payloads. No claim about a provider-specific stop reason is made.

## 7. Hypotheses

### H1 — Host context was informational, not an active tool continuation

```text
Discriminator: after the accepted host context, no bounded assistant continuation is created.
Evidence: B4 has one causally bounded successor assistant message, created after the accepted handoff and completed normally.
Decision: Rejected in its strong form. Host context is delivered in a completed tool result that does trigger the ordinary next assistant turn.
```

### H2 — Native Skill tool result carries additional continuation semantics

```text
Discriminator: a completed native Skill result is followed by another assistant step that is absent from the host injection path.
Evidence: A2 persists native Skill completion followed by a distinct assistant message with finish=tool-calls and submit_discovery. B4 has no native same-successor Skill lifecycle; its immediate successor message ends stop and no later model step is observed.
Decision: Accepted. The native tool lifecycle is an observable additional model-loop boundary, not merely visible Skill text.
```

### H3 — Solar independently chose prose/stop

```text
Discriminator: A and B must expose equivalent successor context at the same model-loop boundary.
Evidence: B4 proves an immediate host continuation, but A reaches its action only after the additional native Skill lifecycle. The boundaries are not equivalent.
Decision: Inconclusive. Solar selected stop in B4, but the available A/B evidence cannot isolate that choice from the extra native lifecycle boundary.
```

### H4 — Another host/runtime difference exists

```text
Discriminator: persisted error, abort, active generation, duplicate Skill context, or target mutation.
Evidence: B4 has no error/abort, a completed assistant message, one successor context, no native duplicate, and unchanged target status.
Decision: Rejected for these observable alternatives. Session idle/active after completion remains unavailable.
```

## 8. Deterministic verification

`tests/test_post_handoff_liveness.py` now covers native completed tool result
→ successor model step → analysis action; host context → completed `stop` → no
action; host context followed by action; persisted `idle`; active generation;
unavailable native tool lifecycle; and legacy trace compatibility. D13/D14
parity coverage remains unchanged.

Focused and broader verification was run after the D15 changes:

| Check | Result |
| --- | --- |
| D15 focused | 25 passed |
| D14 ownership/parity | 10 passed (9 host-owned transition + 1 guard hook) |
| D13 context parity | 11 passed |
| D12 static-MCP harness | 13 passed |
| D09/D10/D11 liveness | 25 passed (current consolidated suite) |
| timing | 18 passed |
| runtime | 211 passed, 1 skipped |
| general | 278 passed, 6 skipped |
| golden | Static MCP golden manifest: PASS |
| bundle | 1 passed |
| diff | `git diff --check` passed |

## 9. Provider result

```text
Run: B4 host-owned, one new provider run
accepted handoffs: 1
host activations: 1
successor context count: 1
continuation turns after successor context: 1
handoffs reaching action: 0
zero-action stops: 1
validation rejects: 0
highest accepted stage: none
target unchanged: yes
elapsed: 324489 ms
```

## 10. Correction

No behavior change made.

The observable native mechanism is a separate OpenCode-generated assistant
step after native Skill completion. Reproducing it from host activation would
need a supported, identity-bound host scheduling seam. The current host MCP
response can expose context but cannot invoke OpenCode's internal Skill tool or
schedule an assistant step. Sending a user message, fabricating a tool result,
or retrying after `stop` would not reproduce the native mechanism safely and is
outside this RCA.

## 11. Outcome and next ticket

```text
Outcome B — CONTINUATION DIFFERENCE IDENTIFIED, CORRECTION DEFERRED
```

Next ticket: `D16 — Design an Identity-Bound Host Successor Execution Scheduling Seam`.

That ticket should identify a supported OpenCode host/runtime mechanism that
schedules exactly one successor execution step bound to the accepted
`analysis_id`, `revision`, `transition_token`, and `next_skill`; it must not
send a synthetic user message, synthesize a Skill result, alter stage payloads,
or introduce retries.
