# D10 Post-Skill Model-Turn Lifecycle Tracing

## Status

Outcome A — the observed failure is now narrow enough for one subsequent runtime/control-plane investigation ticket. This ticket is diagnostic only; it changes neither model-turn behaviour nor accepted pipeline state.

## Host evidence inventory

The Windows PTY acceptance path used local OpenCode `1.18.14`. Its persisted SQLite records show the following relevant fields:

| Evidence | Persisted shape | D10 use |
| --- | --- | --- |
| Assistant turn creation/completion | `message.data.time.created` and `.completed` | associate and terminal-state evidence |
| Finish reason | `message.data.finish` | safe terminal category |
| Error/abort | `message.data.error.name` | preserve a safe category; `MessageAbortedError` is distinct from other errors |
| Parts | `part.message_id`, `part.session_id`, and `part.data.type` | presence-only `reasoning`, `text`, `tool`, `step-start`, and `step-finish` observations |
| Tool lifecycle | `part.data.state.status/time` | existing tool and timing extraction |

No `reasoning` part was present in the inspected local database. D10 therefore uses `not_observed`, never a claim that the model did not reason. It also does not retain assistant prose or raw error messages.

## Association and limitations

A post-Skill turn is projected only when a persisted assistant message shares the Skill tool call's session and has a creation time strictly after that Skill load and strictly before the next accepted handoff, when one exists. If several messages fit without the observed first analysis action identifying one, the lifecycle is unavailable. The harness timeout alone never establishes a model turn state.

## D09 correction

The previous D09 Outcome B was too strong for historical D08 traces, which did not have equivalent liveness instrumentation. The safe D09 conclusion is Outcome C: Skill loading became observable, but post-Skill model-turn lifecycle remained unobservable. Reaching different stages in historical runs does not, on its own, establish different root causes.

## Provider-backed runs

Both runs used the pinned JPetStore revision `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, `upstage/solar-pro2`, the Windows PTY/static-MCP procedure, and a 300-second per-run timeout. The target Git status was `## HEAD (no branch)` before and after each run.

| Attempt | Accepted handoffs | Post-Skill gap | Classification | Target unchanged |
| --- | --- | --- | --- | --- |
| 1 | Discovery, Execution, Relationships | Boundaries Skill loaded; bounded assistant turn completed with `finish=stop`; no analysis tool, text, error, abort, or Boundaries submission | `model_turn_completed_no_stage_action` | yes |
| 2 | Discovery, Execution, Relationships | Same bounded Boundaries turn state and no Boundaries submission | `model_turn_completed_no_stage_action` | yes |

Both harnesses timed out without a final report after approximately 309 seconds. The timeout is recorded separately and is not attributed to the provider.

## Decision

The repeated, structured host evidence is a completed post-Boundaries-Skill model turn that selected no next-stage action. It is not evidence to alter timeouts, provider configuration, retry budgets, or server-owned acceptance.

Recommended next ticket: **D11 — investigate and minimally correct the post-Boundaries-Skill completed-without-action control-plane path**, using this persisted lifecycle evidence and without changing any pipeline behaviour in advance of that investigation.
