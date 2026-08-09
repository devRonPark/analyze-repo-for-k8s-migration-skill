# Bounded Stage Surveys Design

Revised 2026-08-09, three times, after two independent three-perspective
review passes (MCP server design, agent-orchestration design, Skill
authoring) plus implementation. The first revision replaced the original
draft's five new `survey_*_evidence` tools with evidence pushed into the
existing handoff/start response. The second revision closed gaps the
follow-up review found in that fix: the "terminal" response wasn't actually
enforced, the submit-retry mechanism required an uncounted extra call,
several new pieces of session state were implied but never named, and two
deferred items (`question: deny`, the observation-cap measurement) were
silently unlisted rather than deferred on the record. This third revision
records what implementation actually found safe to build: auto-degrading a
rejected payload's offending fields and accepting it on the fourth attempt
turned out to require the server to safely interpret dozens of distinct
validation-failure shapes (`validation.py`) well enough to silently rewrite
client-submitted content — a risk to the evidence-integrity invariant this
whole system exists to hold. The implemented mechanism instead strips the
"try again" framing after three rejections (non-retryable, explicit
budget-exhausted message) without ever mutating or auto-accepting a payload
the server did not itself validate. See Architecture ("Submit retries") and
Skill Flow for what changed.

## Problem

The static MCP workflow keeps each analysis stage isolated, but its generic
evidence tools leave the evidence-search budget entirely to the model.  A
Windows OpenCode acceptance run against the pinned JPetStore target issued 91
successful `locate_evidence` calls in Discovery and never submitted that
stage.  Increasing the agent step limit does not make this bounded, reliable,
or compatible with the five-minute acceptance objective.

Review also found a second, currently-unbounded copy of the same shape:
nothing caps repeated `submit_<stage>` rejections. A stage stuck re-submitting
a malformed payload can consume the entire step budget the same way the
evidence-search loop did, just later in the stage. Any fix must close both
paths, not just the one that already failed once — and must actually block
or exhaust the loop, not just relabel it as instructional text, or the same
91-call shape reproduces against whichever response a weaker or noncompliant
model treats as retryable.

## Goal

Keep the seven-Skill, accepted-handoff workflow while making every analysis
stage reach a submit decision from a bounded, server-computed evidence set —
without adding a new tool-catalog surface, and with every bound enforced as
an actual error response with no new information on repeat, not an
instructional success message a model can choose to ignore.

## Non-goals

- Do not execute target code, builds, containers, or migrations.
- Do not merge stages, reveal a future stage to the current Skill, or make the
  server write a final report without the Finalize Skill.
- Do not add a JavaScript or TypeScript runtime.
- Do not infer unobserved target facts or return unredacted target content.
- Do not grow the MCP tool catalog Ticket 2 froze. The bounded evidence set is
  delivered inside payload fields the wire shape already carries, not new
  tools — no new entry in `TOOL_ORDER` is needed. `HANDOFF_SCHEMA` and the
  `submit_*` payload schemas do change shape (adding `survey`/`budget`
  fields), the same way the already-landed stage-payload-transparency commit
  changed `submit_*` payload schemas from opaque to fully typed without
  touching `TOOL_ORDER` or the tool-count regression. Ticket 2's frozen
  invariant is the tool list, not payload shape; this design stays inside
  that boundary but is a schema change and should say so plainly rather than
  imply nothing about the wire shape moves.
- Do not change the primary agent's step budget policy, permission model, or
  `task: deny` / `question: deny`. The agent-orchestration review found both
  denials relevant — `task: deny` prevents per-stage subagent isolation
  (a real contributing factor to how 91 calls accumulated in one continuous
  context), and `question: deny` removes the one channel the agent could use
  to signal "I'm stuck" instead of silently spinning. Both are runtime/
  permission-layer concerns above this MCP-server ticket; track them together
  in the follow-up ADR named in Delivery Boundary, not silently.

## Architecture

Instead of five new `survey_*_evidence` tools, the server computes each
stage's bounded evidence set and attaches it to the response that already
hands that stage its work: `start_analysis`'s response for Discovery, and
each `submit_<stage>`'s accepted response (`stage_input`) for Execution
through Contracts. This adds zero new tools — the model never has to decide
whether to call a survey tool, because the evidence is already in the context
that told the stage to begin. It also removes an entire enforcement surface
the original draft needed: there is no "was survey called yet" state to gate,
because there is no separate survey call.

Server-selected evidence categories per stage (unchanged from the original
draft):

| Stage | Evidence categories |
| --- | --- |
| Discovery | build/package manifests, container and orchestration declarations, startup descriptors, runtime configuration |
| Execution | build commands, image definitions, entrypoints, listening ports, runtime launch configuration |
| Relationships | declared dependencies, connection settings, brokers, queues, caches, identity and external service configuration |
| Boundaries | independent start definitions, worker or schedule declarations, lifecycle signals, persistent writable locations |
| Contracts | configuration timing, credentials markers, health or readiness signals, observability configuration and report-slot gaps |

The response gains a `survey` object: the stage name, a `surveyed: true`
marker, bounded category coverage, and a server-chosen number of redacted
observations, each with its `observation_ref`, status, and safe `path:line`
reference. The server walks a fixed high-signal path and pattern allowlist in
stable order and issues at most that many current-stage observation
references; a missing category produces a scoped absence observation rather
than a tool error.

**The observation cap is a starting point, not a frozen constant.** Twelve is
carried forward from the original draft, but no measurement backs it. Ticket
implementation must run the three pinned acceptance targets (JPetStore,
Flask-Celery, FastAPI template) in both Summary and Detailed mode, check
whether any required report slot is chronically starved of grounding
evidence at that cap, and raise it if so. This measurement is a Verification
gate below, not an optional note — the cap may not be finalized without it.

### Precision escape valve

If the pushed evidence leaves exactly one current-stage decision blocked, the
stage may make **one** call to `read_evidence`, `locate_evidence`, or
`list_target_paths` (combined budget of one call per stage across these
three). `get_target_git_metadata` is carved out of this budget and stays
freely callable: it is a narrow, cheap, single-purpose lookup (current commit
metadata), not an open-ended content search, and folding it into the same
budget as the search tools only crowds out the search that actually needs
bounding.

Exhausting the one-call content-search budget must not look like a normal
successful result. The server returns an MCP tool **error** (`isError: true`,
not a plain successful `structuredContent`) with a stable code
(`precision_budget_exhausted`) and static message text identifying the
current stage. Calling the same tool again while exhausted returns the exact
same error, with no new content — categorically different from the original
incident, where every one of the 91 calls returned a distinct, plausible-
looking result that could appear to justify one more call. This is not a
literal call-blocking mechanism: an MCP server cannot prevent a model from
issuing another tool call. What it can do, and what this design commits to,
is make repeating the call strictly unproductive — the same static error,
forever, carrying no information a model could rationally act on. The actual
hard backstop against a model that repeats it anyway is the agent's step
budget, which this design does not change (see Non-goals) and which the
follow-up ADR should address directly rather than this ticket papering over
it with stronger wording.

### Submit retries

A rejected `submit_<stage>` call (schema violation, forged observation ref,
stage mismatch, etc.) may be corrected and resubmitted; the first three
payload-content rejections in a stage are normal `isError: true` responses
identifying the specific violated field, same as today, and stay
`retryable: true` wherever they already were. Envelope-level failures (stale
revision or transition token, wrong stage, malformed call) never count
against this — they mean the caller reused a stale handoff, not that it is
stuck iterating on payload content.

The **fourth and later** payload-content rejection in a stage is not
auto-accepted. An earlier draft of this design had the server degrade the
offending fields to `unknown`/`conflicted` and accept the payload outright,
but implementation found no safe, general way to do that: `validation.py`
raises dozens of distinct, differently-shaped rejections (duplicate alias,
forged evidence, dangling report-slot fact, invalid claim status, and more),
and letting the server guess how to silently rewrite a client-submitted
claim into something acceptable risks the evidence-integrity invariant this
whole system exists to hold — accepting content the server itself never
validated is a materially different (and worse) failure than a bounded
retry loop.

Instead, the fourth-and-later response keeps the same specific validation
issue but is marked `retryable: false` with an appended note that the
stage's retry budget is exhausted and resubmitting unchanged will not
succeed. This is the same honesty the precision budget above already
commits to: the server cannot literally prevent another call, only make
repeating it unambiguously unproductive. The actual hard backstop is still
the agent's step budget (see Non-goals and the follow-up ADR).

### Budget visibility

Every survey-bearing handoff and every precision/submit response carries a
`budget` object: content-search calls remaining this stage (0 or 1), and
submit rejections remaining before further attempts stop being framed as
retryable (counting down from 3). This gives a stage an in-context signal of
how much room is left,
distinct from the enforcement above — visibility is a courtesy for a
well-behaved model, not the mechanism that bounds a noncompliant one.

### New session state

Two per-stage counters must be added to `AnalysisSession`: precision calls
used (0 or 1) and submit rejections (uncapped internally; the fourth and
later payload-content rejection just stops being marked retryable). Both
reset to zero on
entry to a new stage. `reopen_analysis` is a stub today
(`mcp_server.py`); until it does something, these counters have no defined
reset-on-reopen behavior beyond "reopening starts a stage over," which is
out of scope for this ticket to specify further — implementers should treat
any concrete `reopen_analysis` behavior as its own ticket and leave these
counters following whatever stage-reset semantics `reopen_analysis` already
defines for other per-stage state.

Existing safe-path, reparse-point, redaction, snapshot, and process-private
session rules apply to evidence collection at handoff-computation time,
unchanged. A stage's evidence and precision budget cannot be reused by
another stage or replayed after finalization.

## Skill Flow

Each non-final Stage Skill uses the same short, current-only sequence:

1. **Ground:** read the bounded evidence already present in the incoming
   handoff (`stage_input.survey`). No tool call is needed to obtain it.
2. **Precision (optional, at most one call):** call `read_evidence`,
   `locate_evidence`, or `list_target_paths` only if one current decision
   remains blocked after grounding; `get_target_git_metadata` is unbudgeted
   and may be called freely. An error response means stop searching and
   submit with `unknown`/`inferred` status on the blocked field — it is not a
   signal to try a different generic tool.
3. **Checkpoint:** construct the transparent `submit_*` payload and submit
   it. A rejected submission may be corrected and resubmitted; after three
   rejections, further attempts are marked non-retryable with an explicit
   note that the stage's retry budget is exhausted — resubmitting the same
   payload will not succeed, so resolve the specific issue or submit with
   `unknown`/`inferred` status on whatever cannot be validated. An accepted
   response is the only completion; no user-facing report is drafted first.

`*_fact_refs` from the incoming handoff remain accepted facts, not
observation references. Every `payload.evidence[].observation_ref` is either
part of the pushed survey or issued by the one precision call, both in the
current stage. Discovery has no incoming `*_fact_refs` (it is the first
stage) — its Skill text omits that clause entirely rather than including it
vacuously.

**This procedure is documentation of server-enforced behavior, not the
enforcement itself, and it should say so in the Skill text.** The Skill
review found the withdrawn "Minimal Slice" paragraph — prose telling the
model to stop searching, with nothing behind it — was exactly this mistake:
a prompt-only stopgap for a bound that only the server can actually hold.

Write this procedure once, in a shared reference (e.g.
`references/stage-protocol.md`) loaded by the four stages that already carry
near-identical "Boundary"/"Checkpoint" paragraphs (Execution, Relationships,
Boundaries, Contracts), plus Discovery with its `*_fact_refs` clause omitted.
**Be precise about what this buys:** stages run in one continuous agent
context today (`task: deny` means no per-stage isolation — see Non-goals), so
a shared file does not reduce how much of this text ends up in the model's
context over a full run; the same content still loads five times. What it
does buy is authoring consistency — one file to edit instead of five
near-identical hand-copies drifting apart over time. State the benefit as
that, not as context reduction.

The shared reference supplements each stage's existing numbered steps (which
cover stage-specific evidence categories and grounding rules); it does not
replace them. Concretely: each stage SKILL.md keeps its own steps 1-3 (load
references, ground category-specific evidence, build identifiers), and the
shared reference supplies the common Ground/Precision/Checkpoint wrapper
around them.

The Finalize Skill remains unchanged: it only calls `finalize_analysis` and
relays canonical Markdown.

## Step budget

Well-behaved case, per stage, under this design: 1 precision call + up to 3
corrected-and-resubmitted submit attempts + 1 accepted submit attempt = 5
calls. Across five stages: 25. Plus fixed overhead: `start_analysis` (1),
five Skill loads for the stages plus one for the dispatcher plus one for
Finalize (7), `finalize_analysis` (1) = 9. Total well-behaved-case: 34 of the
current `steps: 48` budget — comfortable headroom (14).

This is not a hard ceiling: since the fourth-and-later submit rejection is
no longer auto-accepted (see "Submit retries"), a model that keeps
resubmitting an unfixed payload can still keep calling `submit_<stage>`
beyond four times — each call gets the same non-retryable, budget-exhausted
message, but nothing server-side stops the calls themselves. The true
backstop for that case is the agent's step budget, unchanged by this design.
Ticket implementation must still record the actual measured step count from
a real, well-behaved run in Verification below; 34 is an upper-bound
estimate for that case, not a substitute for measurement, and not a
guarantee against a non-compliant model.

## Public Contract and Safety

- The MCP catalog's tool list is unchanged by this design — no tool is added,
  removed, or renamed, and `TOOL_ORDER` needs no new entry.
- `HANDOFF_SCHEMA` and every `submit_<stage>` response schema gain the
  `survey` and `budget` fields described above. This is a payload-shape
  change, consistent with how the already-landed stage-payload-transparency
  work changed `submit_*` payload schemas without touching the tool-count or
  `TOOL_ORDER` regressions.
- Precision-budget exhaustion is returned as a genuine tool error
  (`isError: true`), not a successful result with instructional text.
  Submit rejections remain genuine tool errors at every attempt; the server
  never mutates or auto-accepts a payload it did not itself validate. Only
  the `retryable` flag and issue text change once a stage's rejection count
  passes three.
- The server computes observations, target binding, revisions, tokens,
  budgets, and handoffs. The model never supplies raw evidence, paths outside
  the target, or server-owned evidence identifiers.
- A stage's survey observations and precision budget cannot be called out of
  stage order, recomputed mid-stage, or reused after finalization.

## Verification

Deterministic tests must prove:

1. `start_analysis`'s response and every accepted `submit_<stage>` response
   carry a `survey` field with bounded category coverage and no more than the
   ticket-measured cap of redacted, current-stage observations; a missing
   category is a scoped absence, not an error.
2. No tool is added to the static catalog; the existing tool-count and
   `TOOL_ORDER` regressions pass byte-for-byte unchanged.
3. **The observation cap is set from measurement, not asserted.** The three
   pinned targets, both modes, are run against the implementation and the
   cap is confirmed sufficient (or raised) before this Ticket's commit; the
   measurement and resulting number are recorded in the commit message.
4. The one-call content-search precision budget (`read_evidence`,
   `locate_evidence`, `list_target_paths` combined; `get_target_git_metadata`
   excluded) is enforced per stage; a call past the budget returns
   `isError: true` with static, repeated content — not a relabeled success —
   confirmed by asserting two consecutive over-budget calls return
   byte-identical error bodies.
5. Submit rejections stop being marked `retryable` after three per stage;
   the fourth-and-later rejection keeps the same underlying validation
   issue but adds an explicit retry-budget-exhausted note, and envelope-
   level failures (stale revision/token, wrong stage) are confirmed not to
   count toward this per-stage count.
6. Every survey-bearing handoff and every precision/submit response carries
   the calls/attempts-remaining `budget` field.
7. Survey observations can be submitted only by their matching stage and
   cannot be reused by another stage.
8. Sealed bundles, installed tool policies, Skill references, and the
   Python-only artifact scan show zero tool-catalog delta from this change.
9. A real run's total tool-call count is measured against the step-budget
   estimate in "Step budget" above and recorded; the estimate is revised if
   actual usage differs materially.

Windows-native OpenCode acceptance keeps the pinned JPetStore, Flask-Celery,
and FastAPI targets read-only. Each Summary and Detailed case must produce
the canonical Markdown report, complete every required submit transition and
finalization exactly once, and leave Git status unchanged. A provider-backed
case has a five-minute limit; its trace must show at most one content-search
precision call per stage and, for a well-behaved run, no stage issuing more
than four `submit_<stage>` calls — a run that exceeds this is not
automatically a fixture failure (nothing server-side forces a hard stop),
but it must still finish inside the five-minute limit or the case fails on
timeout regardless. A timeout, incomplete final report, invalid transition,
or target change fails the case.

## Delivery Boundary

This is a focused continuation of the static MCP milestone. It supersedes
the unbounded generic-evidence loop but preserves the seven installed Skill
IDs, user-invoked custom command, Python 3.13 runtime, Windows-native E2E
path, sealed bundle verification, and one-process-per-analysis session model.

This change touches the `start_analysis` / `submit_<stage>` payload shape
inside the already-evolving `protocol.py` schema. It adds no tool, so
`TOOL_ORDER` needs no new entry — but `HANDOFF_SCHEMA`'s `additionalProperties:
false` object does change shape, the same category of change the stage-
payload-transparency commit already made to `submit_*` payloads. Name this
plainly in the implementation Ticket rather than asserting no wire change is
involved.

**Out of scope, tracked together in one follow-up ADR:** `task: deny`
prevents per-stage context/step isolation; `question: deny` removes the
agent's only channel to signal it is stuck instead of silently spinning; and
the primary agent has no in-context signal of its own *global* step budget
(only the stage-local `budget` field this design adds). All three are
runtime/permission-layer concerns above this MCP-server ticket.

**Interim risk, resolved by explicit action, not a warning:** until this
design ships, Discovery's SKILL.md has no bound on evidence-tool call count
— the earlier prompt-only "Minimal Slice" mitigation was reverted once the
team decided a server-enforced fix was required, and that fix is not yet
built. A design doc that names its own unmitigated hazard should not leave
the choice to whoever reads it next: restore a minimal interim bound in
Discovery's SKILL.md now, as a separate, immediate action outside this
design's implementation Ticket, and remove it once this design's server-side
enforcement ships. Do not attempt a provider-backed acceptance run against
Discovery in between.
