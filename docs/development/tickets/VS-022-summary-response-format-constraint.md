# VS-022 — Constrain Summary JSON emission at the provider level

## Outcome

The Summary Agent's JSON output is schema-valid by construction (engine-level
constrained decoding), not merely by prompt instruction, so a run cannot
fail the way live attempt 3 did today (see Context).

## Why this is a vertical slice

ADR-2026-08-07-001 decided this as item 2 alongside DEL-002/DEL-003, but
explicitly deferred it: "the remaining risk (schema-constrained decoding
wiring, unknown OpenCode 1.18 passthrough support) was judged not worth
taking on immediately before a demo." That deferral is now costed: of three
live `slash-default-summary` runs against `demo-repositories/jpetstore-6`
today (after DEL-002/DEL-003 shipped), one passed, one timed out
(`UNAVAILABLE`), and one **ignored the JSON-only instruction entirely** and
free-wrote Markdown analysis (with a `Recommendation`-style section and a
Markdown table), so `extract_json_object` had nothing to parse
(`Summary output is not valid JSON: Expecting value: line 1 column 1 (char
0)`). That run also showed token-level language drift (Han characters
mid-Korean sentence). This is exactly the residual risk the ADR recorded,
now reproduced.

## Status and dependencies

- **Status:** Closed — investigated, not implemented; see Decision outcome below.
- **Depends on:** DEL-002/DEL-003 (`d6a5fba`)
- **Blocks:** None

## Read first

- `docs/development/daily/2026-08-07/ADR-2026-08-07-001-summary-delivery-structured-output.md` — full context and the sglang research citations
- `runtime/opencode.json` — the `local-sglang` provider block (`options.baseURL`, `models.*.options`)
- `scripts/run_opencode_acceptance.py`'s `retain_summary_markdown` / `extract_json_object` — current tolerant-but-unenforced JSON extraction

## Scope

### In scope

- Investigate whether OpenCode 1.18's provider `options` (or per-model
  `options`) passes an OpenAI-compatible `response_format` (or equivalent)
  through to the underlying `@ai-sdk/openai-compatible` call, and whether
  `sglang`'s OpenAI-compatible server at `172.16.4.249:30000` honors it for
  this exact model (`Qwen/Qwen3.6-35B-A3B-FP8`).
- If supported: add a `response_format` JSON-schema constraint (derived from
  `schemas/analysis-result.schema.json`, Summary-scoped) to the
  `local-sglang` provider's Summary-relevant model options in
  `runtime/opencode.json`, and re-run the live scenario enough times to
  characterize whether attempt-3-style failures stop occurring.
- If not supported: record the specific blocker (missing passthrough,
  provider rejects the param, etc.) in this ticket or a follow-up ADR, and
  leave DEL-002/DEL-003's prompt-only approach as the accepted interim
  state.

### Out of scope

- Detailed mode (out of scope for the whole DEL-00x line so far).
- Investigating the `UNAVAILABLE` timeout separately — that's a latency/
  availability question, not a format-constraint one; note it if observed
  again but don't chase it here.

## Implementation steps

1. Check OpenCode 1.18's config schema/docs for `response_format` or
   `structuredOutputs` passthrough support at the provider or model level.
2. If present, add it for the `Qwen/Qwen3.6-35B-A3B-FP8` model entry, scoped
   so it only applies to the Summary command (confirm it doesn't also
   constrain Detailed's free-form Markdown output — if OpenCode applies
   provider-level settings to every request from that model, this may
   require a second model/provider entry used only by Summary).
3. Re-run `slash-default-summary` against `demo-repositories/jpetstore-6`
   several times and record how many produce valid JSON versus the
   attempt-3 failure mode, to characterize whether this closes the gap.

## Acceptance criteria

- Either: a documented, working `response_format` constraint is in
  `runtime/opencode.json` and repeated live Summary runs stop producing
  non-JSON final output, with Detailed mode unaffected.
- Or: the investigation concludes it isn't supported, with the specific
  reason recorded, and the interim prompt-only approach is explicitly kept
  as the accepted state (no silent abandonment).

## Verification commands

```bash
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --skip-debug --repository-root <target> --timeout 180 --output-dir <dir> --repeat 5
```

## Expected file changes

- `runtime/opencode.json`
- `docs/development/daily/<date>/ADR-*.md` if the investigation's outcome is non-obvious enough to warrant recording

## Commit boundary

- Commit only `runtime/opencode.json` and any new investigation notes.
- Suggested commit: `feat: constrain Summary JSON output via sglang response_format` or `docs: record why sglang response_format isn't wired up yet`

## Decision outcome (2026-08-07)

Investigated; not implemented, per the ticket's own fallback path ("if not
supported, record the specific blocker and leave DEL-002/DEL-003's
prompt-only approach as the accepted interim state").

**Finding**: OpenCode 1.18 does have engine-enforced structured output —
`session.prompt({ path, body: { format: { type: "json_schema", schema },
retryCount } })`, backed by an internal `StructuredOutput` tool with
validate-and-retry and a `StructuredOutputError` on exhaustion. Confirmed
against both `https://opencode.ai/docs/sdk/` and
`https://opencode.ai/docs/config` (the config schema at
`https://opencode.ai/config.json` has no `response_format`/structured-output
property anywhere under provider or model options).

**The blocker is OpenCode's invocation path, not the inference engine.**
`format: json_schema` is only reachable through the SDK's `session.prompt()`
API — an external program driving a session over HTTP. It is not
configurable from `opencode.json`, not from an agent `.md` definition, and
not reachable from the CLI paths this project uses (`opencode run`, the
`/analyze-repo-for-kubernetes` custom command, or the acceptance harness's
subprocess invocation). **Switching the underlying LLM runtime (e.g.
sglang → vLLM) would not close this gap** — both engines already support
schema-constrained decoding at the inference layer; the missing piece is
that OpenCode's CLI/agent-config surface never forwards a schema constraint
down to whichever engine is behind it.

Closing the gap for real would mean migrating `scripts/run_opencode_acceptance.py`
(and eventually the documented user workflow) from CLI-subprocess
invocation to SDK-driven `session.prompt()` calls — a change to this
project's core invocation architecture, not a config tweak. That is out of
scope for this ticket and would need its own ADR if pursued.

**Interim state kept**: DEL-002/DEL-003's prompt-only JSON contract, plus
VS-021's payload-level rejection of disallowed content, remain the accepted
approach. `retain_summary_markdown`'s clear `FAIL` on invalid JSON (rather
than silently accepting free-form Markdown) is the safety net for the
failure mode this ticket can't yet prevent at the source.

## Codex execution instruction

```text
Implement only VS-022. This starts as an investigation, not a known
implementation — read ADR-2026-08-07-001 first, then determine whether
OpenCode 1.18 can pass response_format through to this sglang endpoint for
this model before writing any config. Report what you found either way;
do not claim the constraint works without a live run showing it.
```
