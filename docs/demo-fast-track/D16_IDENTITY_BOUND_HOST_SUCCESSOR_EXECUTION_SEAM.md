# D16 — Identity-Bound Host Successor Execution Scheduling Seam

## Outcome

~~~text
Outcome B — supported external session control surface, but no eligible
post-tool continuation operation for the current CLI/TUI architecture.
~~~

OpenCode 1.18.14 exposes a documented headless HTTP session API. A host can
create a session and receive an OpenCode-issued ses_* identity, and it can
observe session status through both an HTTP endpoint and event stream. The same
documented API does not expose an operation that resumes an existing session
after a completed tool result without creating a new message.

The only documented operation that starts model work is
POST /session/{sessionID}/message (session.prompt). Its OpenAPI summary is
"Create and send a new message to a session" and its body requires parts.
It is therefore not a native-equivalent continuation hook. Using it for D15
would create the synthetic follow-up user message that D15 explicitly rules
out.

No behavior change is made by this ticket.

## Scope

D15 required a supported mechanism for exactly one, identity-bound successor
execution step. This investigation is limited to installed OpenCode behavior;
it does not call a provider, start a repository analysis, alter a stage Skill,
or change the current CLI/PTY acceptance architecture.

## Local evidence

The following provider-free commands were run against the installed
OpenCode 1.18.14 executable.

| Probe | Result |
| --- | --- |
| opencode --version | 1.18.14 |
| opencode serve --help | supported headless server with loopback hostname/port |
| GET /doc on isolated opencode serve --pure | OpenAPI 3.1.0 document is served |
| POST /session | created a server-issued ses_* session ID |
| GET /session/{sessionID} | returned that same ID and server timestamps |
| GET /session/status | returned an empty status map for the new, inactive session |
| DELETE /session/{sessionID} | deleted the probe session |
| GET /event / OpenAPI schemas | documents session.status and session.idle events |

The temporary server was run with an isolated profile, then its exact child
process and temporary profile were removed. No configured provider was
contacted and no target repository was analyzed.

## Available API surface

The installed OpenAPI document contains these relevant operations:

~~~text
POST /session
  Create an OpenCode session; the server generates session ID ses_*.

POST /session/{sessionID}/message
  session.prompt; create and send a new message.
  Required body field: parts.

GET /session/status
GET /event
  Observe session state, including session.status and session.idle.

POST /api/session/{sessionID}/interrupt
  Interrupt active execution; idle interruption is a no-op.
~~~

The document does not expose any of the following:

~~~text
continue_after_tool_result
resume_tool_continuation
schedule_assistant_step
append_trusted_tool_result
execute_successor_without_message
~~~

The current PTY/CLI path also does not give the MCP server or plugin a
documented connection to a separately managed opencode serve session.

## D15 candidate assessment

| Candidate | Identity-bound | Schedules work | Native-equivalent | Decision |
| --- | --- | --- | --- | --- |
| Host context in MCP result | server handoff identity | only the ordinary current tool-result continuation | no extra post-Skill turn | insufficient, per D15 |
| Native skill() tool | current assistant/tool lifecycle | yes, after native tool completion | yes | current control |
| session.prompt HTTP endpoint | session ID can be host-owned | yes | no; creates a new message with required parts | rejected |
| session status/event APIs | session ID can be host-owned | no | no | observability only |
| interrupt API | session ID can be host-owned | stops work | no | not applicable |

## Architecture decision

The immediate model-loop boundary is not safely reproducible inside the current
CLI/TUI + stdio-MCP arrangement.

A future host-owned design has two mutually exclusive choices:

1. Keep the current interactive CLI architecture and retain native
   skill(next_skill) as the only supported successor-execution trigger.

2. Deliberately migrate to a serve-mode control-plane architecture. An external
   host would own session creation, prompt submission, event observation,
   identity binding, and final delivery. That is not a local successor-hook
   patch: it changes the product invocation boundary, the acceptance harness,
   permission model, session lifecycle, recovery model, and user-message
   semantics.

Option 2 cannot be introduced by calling session.prompt from the existing MCP
tool or plugin. It would bypass the current interactive client boundary and
manufacture a new session message. A full architecture decision must state
whether that message is a legitimate host command, how it is rendered or hidden
from users, how stage trust is bound, and how exactly one execution is enforced.

## Why no correction is implemented

D15 permits a bounded successor execution only when the host can reproduce an
existing native mechanism. The installed API proves that the available
scheduling operation is a new message, not a post-tool continuation. Treating
it as equivalent would violate all of these D15 constraints:

~~~text
no follow-up user message
no synthetic tool result
no retry loop
no duplicate context
no altered stage payload or host-selected stage
~~~

The correct implementation response is therefore to defer, not to wrap
session.prompt in a hidden retry or stronger prompt.

## Next ticket

D17 — Decide Serve-Mode Orchestrator Migration Boundary

It must be an ADR-scale decision. It should compare retaining native Skill
routing against an explicitly user-visible or otherwise approved serve-mode
orchestrator, and define the session ownership, trusted transition identity,
one-shot scheduling contract, permission boundary, event persistence, recovery,
and acceptance-harness migration before code is written.
