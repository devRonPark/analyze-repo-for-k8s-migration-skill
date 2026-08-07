# ADR-2026-08-07-003: VS-023 sensor tool scoping decision (Implementation step 1)

- Status: Proposed — needs user confirmation before any tool code is written
- Date: 2026-08-07
- Related: [VS-023](../../tickets/VS-023-migration-evidence-sensor-tools.md), [SEC-002](../../tickets/SEC-002-read-tool-symlink-escape.md) (landed today, `18915ed`), [ADR-2026-08-07-002](ADR-2026-08-07-002-summary-validate-and-repair-loop.md)

## Context

VS-023 targets the citation-fabrication failure mode `tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`
and ADR-2026-08-07-002 both recorded: the Agent read a file, then several
steps later reconstructed a `file:line` citation from memory rather than
from the read output, producing an invented range (`17-268` against a
117-line file) that `validate_report.py` correctly rejected. VS-023's
ticket proposes fixing this by moving evidence-gathering into five
Kubernetes-migration-scoped "sensor" tools
(`discover_deployment_candidates`, `inspect_build_runtime`,
`inspect_network_contract`, `inspect_configuration`,
`inspect_state_dependencies`) that return tool-computed facts with
tool-computed citations, explicitly marking that proposal as unconfirmed
and requiring a scoping pass before implementation (ticket Implementation
step 1).

This ADR is that scoping pass. It reads `runtime/agents/kubernetes-migration-analyzer.md`'s
current Summary JSON contract and discovery instructions, and
`references/language-discovery-rules.md`, `references/dependency-analysis.md`,
`references/configuration-timing.md` — the prompt-layer rules the proposed
tools would partially replace.

## The core mechanism that actually fixes the bug

The fabrication bug has two forms, both a symptom of the model reconstructing
a citation from memory instead of copying it at the moment of discovery:

1. A `확인됨`/`추정됨` finding gets an invented `path:line` or a `path:start-end`
   that doesn't match the file's real length.
2. A `미확인` finding gets a `검색(scope=..., pattern=..., result=없음)` string
   with an invented or approximate `scope=`/`pattern=` that doesn't reflect
   what was actually searched.

A sensor tool fixes both only if its return shape captures the reference
*at the point of the tool's own file access*, for both outcomes:

```ts
type Fact =
  | { status: "found"; value: string; reference: string }   // reference = "path:line" or "path:start-end", computed from the tool's own read
  | { status: "not_found"; searched: { scope: string; pattern: string } }  // the literal scope/pattern the tool searched, for a verbatim 검색(...) string
```

The agent copies `reference` or `searched` verbatim into the final JSON's
`reference` field — it never recomputes a line number or a search
description from memory. This is the actual fix; everything else below is
about how much repository-understanding logic sits behind that return
shape.

## Re-scoping the proposed five tools

`references/language-discovery-rules.md` documents materially more
per-ecosystem judgment than the ticket's "fact-finding heuristics are
lower-risk than K8s-shape judgments" framing accounted for. Examples
already in that file: Node package-manager precedence across four
tiebreak levels including workspace ownership ("a workspace declaration
applies only to components it owns"); "if equally applicable signals
conflict, preserve the conflict as `상충됨`"; Java "when Maven and Gradle
coexist, keep both scopes and evidence visible, do not select a single
toolchain." Encoding this precedence and conflict-preservation logic into
`inspect_build_runtime`'s tool code would not be filename-pattern
fact-finding — it would be re-implementing judgment calls the ticket's own
"out of scope" section says must stay in the Skill/prompt layer, just
re-labeled as "discovery" instead of "design."

Building all five ecosystem-aware tools as proposed is also a large surface
for a first pass: each would need to encode enough of
`language-discovery-rules.md`, `dependency-analysis.md`, and
`configuration-timing.md` to be useful, across Node/TS, Python, Go,
Java/Kotlin, .NET, and Rust, before any of it is live-tested.

**Recommendation: narrow Phase 1 to one generic, judgment-free primitive
instead of five ecosystem-aware tools.**

- One tool, e.g. `locate_evidence(root, glob, content_pattern?)`: scans
  `glob` under `root` (reusing `runtime/lib/safe-path.ts`'s boundary check
  and `read.ts`'s redaction), and for each matching file either returns the
  first line matching `content_pattern` (or the whole file's first line if
  `content_pattern` is omitted) as a `found` Fact, or — if no file matches
  `glob` at all, or none match `content_pattern` — a `not_found` Fact
  carrying the literal `glob`/`content_pattern` searched.
- The agent keeps deciding *which* `glob`/`content_pattern` to use for a
  given language and field, exactly as `language-discovery-rules.md`
  already instructs it to today — no discovery judgment moves into tool
  code. What moves is only the mechanical step of turning "I looked at this
  file" into a citation, which is exactly where the fabrication happens
  today.
- This is a strict subset of the proposed design's value: it eliminates the
  citation-fabrication bug (the demonstrated, scored failure) without also
  re-implementing per-ecosystem precedence rules, so it is testable against
  a fixture repository per language with much less new code, and the
  five named tools remain available as a later phase — each would become a
  thin, curated table of `(glob, content_pattern)` pairs calling this same
  primitive, at whatever point that curation is itself judged low-risk
  enough to move server-side.

This is a real fork from the ticket's proposal, not a detail within it —
it trades the ticket's broader "sensor tools replace prompt-driven
discovery" framing for a narrower "sensor tool makes citation mechanically
correct, discovery logic stays exactly where it is" framing. Flagging this
for confirmation rather than deciding it unilaterally, per the ticket's own
Codex instruction ("do not invent the sensor tool set unilaterally") and
this project's change-scope rule.

## Tool/prompt boundary, stated explicitly (ticket step 1's second question)

- **In tool code:** the `Fact`/`locate_evidence` mechanism itself (glob
  scanning, safe-boundary + redaction reuse, line-locating, verbatim
  reference/search-description construction). No per-language filename
  tables live in tool code under this recommendation — see above.
- **Never in tool code:** any classification of a component
  (`repository_classification`), any `missing_inputs` classification
  (`hard_blocker` / `open_design_decision` / `deployment_value`), any
  `design_input_verdict`, any comparison between two Facts that concludes
  `상충됨` (the agent constructs a `상충됨` reference by concatenating two
  already tool-sourced references — see ADR context above — but the
  judgment that they conflict stays in the prompt), any Kubernetes-resource
  vocabulary, any `kubernetes_interpretation` text.
- **`추정됨` stays prompt-only:** a tool never emits `추정됨`; the agent may
  build a `추정됨` finding from a tool-returned `found` Fact's `reference`
  plus its own `reason` text, unchanged from today.

## Consequences if the narrower Phase 1 is confirmed

- Smaller, single-tool implementation (`runtime/tools/locate_evidence.ts` or
  similar name, sharing `runtime/lib/safe-path.ts`), testable the same way
  SEC-002's fix was — fixture-based `bun test`, no live provider required
  for the tool logic itself, though the acceptance criterion ("measurably
  lower citation-fabrication rate") still needs a live jpetstore-6 rerun to
  confirm the *agent* actually adopts the tool consistently.
- Every `read`/`glob`-based discovery instruction in
  `runtime/agents/kubernetes-migration-analyzer.md` and the `references/*`
  files stays as-is; only the final "write down what I found" step changes,
  which limits the size of the prompt diff and the retest surface compared
  to the ticket's original five-tool proposal.
- Does not close VS-023's acceptance criterion about "no sensor tool
  returns a Kubernetes-resource-shaped judgment field" any differently —
  still true, and easier to keep true with one narrow tool than five.
- Leaves the five named tools' ecosystem-aware curation as explicit future
  work if the narrower primitive's live rehearsal still shows fabrication
  (e.g. because the agent picks a wrong `glob`/`content_pattern`, which this
  design does not fix — it only fixes citation computation once a
  correct search is chosen).

## Open question for confirmation

Proceed with the narrower `locate_evidence` primitive (Phase 1 above) in
place of the five proposed ecosystem-aware tools, deferring
`discover_deployment_candidates`/`inspect_*` to a later phase? Or implement
the five tools as originally proposed in the ticket? No tool code has been
written under either option yet.
