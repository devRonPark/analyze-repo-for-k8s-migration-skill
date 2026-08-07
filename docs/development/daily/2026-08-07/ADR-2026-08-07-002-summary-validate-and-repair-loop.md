# ADR-2026-08-07-002: A bounded validate-and-repair loop for Summary JSON, scoped to named errors

- Status: Accepted
- Date: 2026-08-07
- Related: [ADR-2026-08-07-001](ADR-2026-08-07-001-summary-delivery-structured-output.md) (DEL-002/DEL-003), VS-020, VS-021
- Related (exp branch, not merged): `exp/opencode-sdk-summary-invocation`'s ADR-2026-08-07-002 (SDK structured-output spike, blocked on an upstream bug — filed as [anomalyco/opencode#40998](https://github.com/anomalyco/opencode/issues/40998))

## Context

`docs/development/current/status.md` has long flagged, for Detailed mode's
`DET-010`–`DET-014`: "Instruction-only fixes show diminishing returns; a
validate-and-repair loop needs an ADR first." Final rehearsal of the
JSON-first Summary pipeline (DEL-002/DEL-003 + VS-020/VS-021) against
`demo-repositories/jpetstore-6` reproduced the same underlying pattern for
Summary: two consecutive live runs each failed for a different,
well-localized reason —

1. A fabricated evidence citation: `evidence[].reference` cited
   `src/main/resources/database/jpetstore-hsqldb-dataload.sql:17-268`, but
   the file has 117 lines. `validate_report.py` correctly rejected it with
   an exact, named error.
2. A JSON syntax error (`Expecting property name enclosed in double quotes:
   line 1 column 2`) — the model's output was almost-valid JSON with one
   syntax mistake.

Both failures are narrow: the Agent's overall reasoning and evidence
gathering were sound (matching VS-020's finding that the underlying content
quality is good), but one field or one syntax detail was wrong. A full
re-run from scratch discards all of that correct work to fix one detail.

The SDK-based structured-output path (`exp/opencode-sdk-summary-invocation`)
would have solved this more robustly via OpenCode's own bounded retry, but
is blocked on a reproducible upstream bug (agent selection crashes the
message endpoint). This ADR implements the same *category* of fix —
bounded retry against a specific, named error — using only the CLI
invocation this project already has working.

## Decision

`scripts/run_opencode_acceptance.py` gains a targeted repair loop for
Summary cases only:

1. `run_case` now captures the session's `sessionID` from the first JSON
   event that has one, storing it as `trace["session_id"]`.
2. `retain_summary_markdown_with_repair` wraps `retain_summary_markdown`:
   on `ValueError` (invalid JSON, a rendering error, or a
   `validate_report.py` rejection), if a `session_id` is available and the
   repair budget (`max_repairs`, default 2) isn't exhausted, it sends a
   follow-up message in the *same session* via `continue_session`
   (`opencode run --session <id> ...`), quoting the exact validator error
   and asking for a corrected JSON object only — then retries validation
   against that new output.
3. A session with no captured `session_id`, or one that never produced
   parseable JSON at all (the "ignored the instruction, wrote free-form
   Markdown" failure mode), gets exactly one attempt — there's nothing
   coherent to continue.
4. `trace["repair_attempts"]` records every intermediate error message, so
   a passing report that needed a repair is distinguishable from one that
   passed on the first try, and a final failure shows the full history.

This is deliberately narrower than a general "keep retrying until it
passes" loop: it retries the *same* session with the *specific* error, not
a fresh generation. It does not address total format non-compliance (case
2 above's JSON syntax slip is repairable this way if the syntax break was
small and localized; if the model ignores the JSON-only instruction
entirely, this loop correctly gives up after one attempt rather than
looping pointlessly).

## Consequences

- Summary cases that fail on a narrow, nameable error get a bounded second
  (and third) chance without re-exploring the repository from scratch,
  which should reduce live-rehearsal flakiness without silently accepting
  a wrong report — the safety net (`validate_report.py`, VS-021's
  classification check) still runs identically on every attempt.
- Adds up to `max_repairs` extra `opencode run` invocations' worth of
  latency to a failing case; a case that already passes on the first try is
  unaffected.
- Does not use or depend on the blocked SDK path — pure CLI session
  continuation (`--session <id>`), already exposed by `opencode run --help`.
- `docs/development/current/status.md`'s DET-010–014 blocker note
  ("validate-and-repair loop needs an ADR first") can now point at this
  ADR's pattern if a Detailed-mode equivalent is scoped later; this ADR
  does not itself change Detailed mode.

## Verification

`python scripts/run_quality_gate.py` and a live re-run against
`demo-repositories/jpetstore-6` (`slash-default-summary`) — see the
completion report for pass/fail/repair-count evidence.
