# VS-031 — Measure Per-Stage Model Latency and Payload Cost

## Outcome

`scripts/run_opencode_acceptance.py`'s Windows-PTY static-MCP runner
(`_run_static_mcp_case`) emits a stage-attributed timing breakdown in every
case's `trace.json`, on a timeout/stopped exit exactly as much as on a
completed one. Each entry ("turn") records which pipeline stage it belongs
to, the wall-clock interval the harness spent waiting on the model
(`elapsed_ms`), the MCP tool's own execution time where OpenCode exposes it,
and character-count size metrics for the tool payload. No token counts are
invented. This is a characterization ticket only: no default timeout,
payload shape, prompt text, retry budget, or pipeline behavior changes.

## Why now

The previous ticket (VS-030, commit `c74687e` "fix: keep active analysis
context server-owned") closed the `analysis_not_found` identity-corruption
failure. Three follow-up live `jpetstore-6-summary` runs against
`local-sglang`/`Qwen3.6-35B` (preserved at
`tests/evaluation/vs030-followup-e2e/`) confirm the fix — zero
`analysis_not_found` occurrences — but all three now time out mid-pipeline
instead, per that directory's `README.md`: attempt-1 reached
`relationships`, attempts 2 and 3 reached `boundaries`/`contracts` before the
240s timeout. The working hypothesis is that per-turn model
reasoning/generation time in the local Qwen model, not MCP execution, is the
dominant cost, and a secondary hypothesis is that later stages
(`boundaries`, `contracts`) cost more because their context/payload is
structurally larger. Neither is proven: **on the timeout path, the current
harness never calls `_static_tool_calls`, so `trace.json` for every one of
these three preserved failures has no `tool_calls` key at all** — the
`completed · Nms` figures in this ticket's originating description were read
by hand off the raw terminal transcript, not off any structured artifact.
There is no committed code that parses `completed · Nms`, and the raw PTY
terminal text carries no absolute timestamp to anchor those durations to
wall-clock time or to each other (`grep` of
`tests/evaluation/vs-030-mid-stage-retry-exhaustion/terminal-deansi.txt`
finds zero ISO-8601 or other absolute timestamps). This ticket exists to
measure the question before optimizing anything.

## Read first

* `scripts/run_opencode_acceptance.py`:
  * `_run_static_mcp_case` (~line 1736) — the Windows-PTY runner used for
    every `jpetstore-6-summary` static-MCP case. Its mid-pipeline timeout
    branch (`"OpenCode PTY did not produce a complete final Markdown report
    before timeout"`, ~line 1844) and its `static_mcp_terminal_stop_reason`
    branch (~line 1834) both `return trace` **before** the success-only call
    to `_static_tool_calls` (~line 1848–1852) — this is the gap to close.
  * `_static_tool_calls` (~line 1606) — already preserves each tool part's
    entire `state` dict verbatim (`{"name": ..., "state": payload.get("state",
    payload)}`), which is exactly OpenCode's own persisted `Part` schema. If
    OpenCode populates `state.time.{start,end}` (epoch ms) for a PTY/SQLite
    session the same way it does for the NDJSON `run_case` path (confirmed
    present there — see `collect_tool_calls`, ~line 767, which currently
    discards `state.time`), that duration is already being captured and
    only needs to be read, not invented.
  * `_static_db_records` (~line 1524) — returns each SQLite row's raw
    `columns` dict, which includes non-JSON columns. Schema inspection
    (`.artifacts/*/home*/.local/share/opencode/opencode.db`, empty of rows
    but present in schema) shows the `part` table carries `time_created` /
    `time_updated` INTEGER columns independent of anything inside the JSON
    blob — a coarser fallback wall-clock anchor if `state.time` turns out
    absent for some part type. `_static_tool_calls` currently discards
    `record["columns"]` entirely; it only keeps `name` and `state`.
  * `STATIC_MCP_TOOL_SEQUENCE` (~line 592) and `_tool_name` (~line 701) —
    the existing accepted-tool-name list and the `analysis_` prefix
    stripper; reuse both rather than re-deriving stage names.
* `runtime/python/analysis_pipeline/protocol.py`: `STAGES` (line 16, the
  five submit-stage names, `finalize` handled separately),
  `STAGE_TOOL_BY_STAGE` (line 17, `submit_<stage>` naming), `HANDOFF_SCHEMA`
  (line 81) — every accepted response carries `completed_stage`,
  `next_skill`, and `stage_input.survey.stage`, i.e. reliable server-owned
  stage identity if a machine-parseable response is available for a call.
* `runtime/python/analysis_pipeline/mcp_server.py` lines 14, 27 —
  `PRECISION_BUDGET_TOOLS = ("read_evidence", "locate_evidence",
  "list_target_paths")` and `RETRY_BUDGET_TOOLS` — the non-stage-defining
  tool names that must inherit the *current* stage context rather than get
  attributed `unknown`.
* `tests/test_static_mcp_opencode_acceptance.py` — the existing pure-function
  test style (synthetic `tool_calls` lists, `StubPty`, no live OpenCode) is
  the pattern to follow; `test_transition_audit_reads_real_opencode_state_output`
  (line 63) shows the realistic `state.output` JSON-string shape to build
  fixtures from.
* `tests/evaluation/vs030-followup-e2e/README.md` — the exact prior
  three-attempt evidence and its "Next failure to hand off" section, which
  this ticket answers.

## In scope

* Extend `_static_tool_calls` to also carry each part's row-level
  `time_created` / `time_updated` (from `record["columns"]`) alongside the
  existing `name` / `state` fields, without dropping anything currently
  returned.
* Add a pure stage-attribution/turn-building function
  (`attribute_stage_timeline` or similar) that, given the `tool_calls` list
  `_static_tool_calls` already produces, returns one "turn" record per tool
  call:
  * `stage` — one of `dispatcher/start`, `discovery`, `execution`,
    `relationships`, `boundaries`, `contracts`, `finalize`, `unknown`,
    attributed primarily by tool name (`submit_<stage>` → `<stage>`,
    `start_analysis` → `dispatcher/start`, `finalize_analysis` →
    `finalize`), with non-stage-defining tools (`read_evidence`,
    `locate_evidence`, `list_target_paths`, `reopen_analysis`) inheriting
    whichever stage was most recently entered by an *accepted* `submit_*` /
    `start_analysis` call, defaulting to `unknown` only before the first
    such call.
  * `started_at` / `completed_at` / `elapsed_ms` — the model-turn wall-clock
    interval, taken as the gap between the previous tool call's end
    timestamp (or session start, for the first turn) and this call's start
    timestamp, using `state.time.{start,end}` when present and falling back
    to the row `time_created`/`time_updated` pair otherwise; `None` (not
    `0`, not fabricated) when no timestamp source is available at all.
    Clamp any negative gap to `0` and do not raise — this is measurement
    code observing an external process's clock, not a correctness check.
  * `tool_calls: [{tool, elapsed_ms}]` — the MCP execution time, from the
    same source, kept as a distinct field from the surrounding model-turn
    `elapsed_ms`.
  * `input_chars` / `output_chars` — character length of the tool call's own
    `input` payload (`output_chars`, i.e. what the model produced this turn)
    and of the *previous* tool call's `output`/`structuredContent` payload
    (`input_chars`, i.e. what was added to context immediately before this
    turn began — a documented lower bound on total context size, not the
    full prompt). `None` for the first turn (no prior tool response, and the
    initial Skill/prompt text is not captured by this instrumentation).
* A pure per-attempt aggregator (`summarize_stage_timeline` or similar)
  reducing a `turns` list to per-stage totals/means/max for `elapsed_ms` and
  tool `elapsed_ms` — needed to produce the required stage-level summary
  without hand-reconstructing it from raw JSON three times.
* Call the tool-call/turn extraction from **every** return path of
  `_run_static_mcp_case` that has a live `home` directory to read from
  (success, mid-pipeline timeout, terminal-stop-reason), not only the
  success path. Persist `trace["turns"]` and `trace["total_elapsed_ms"]`
  (harness-side `time.monotonic()` wall time for the attempt, always
  available regardless of outcome) into the existing `trace.json`.
* Document the exact "model-turn latency" definition (harness-observed
  wall-clock wait, not isolated neural-network inference; OpenCode's own
  orchestration inside that interval is included and not claimed otherwise)
  in code and in this ticket.

## Out of scope

Everything the ticket's originating instructions list under "Explicitly out
of scope" — no default-timeout change, no payload/schema/prompt change, no
stage merging, no survey/budget change, no provider/model/runtime-parameter
change, no caching, no report-structure or domain-rule change, no Python
server performance work. Also out of scope for this ticket specifically:

* Parsing the terminal's `completed · Nms` text. `state.time` (or the row
  timestamp fallback) is a structured, already-parsed source for the same
  number; adding a second, text-scraping timing path would be the
  "redundant timing system" the originating instructions explicitly reject.
  If live verification shows OpenCode's PTY/SQLite persistence never
  populates `state.time` or the row timestamp columns for tool parts, note
  that as an instrumentation limitation in the deliverables report rather
  than adding terminal-text parsing to compensate.
* Capturing the initial prompt/Skill-load size as `input_chars` for the very
  first turn. Not available from the tool-call stream this ticket reads;
  document as a known gap.
* Any change to the NDJSON (`run_case`) path's `collect_tool_calls`. It
  already receives `state.time` but discards it — leave it alone; the
  Windows-PTY path is what every `jpetstore-6-summary` case in scope here
  actually uses.

## Tests first

New file `tests/test_stage_timing_instrumentation.py`, pure-function only
(no live OpenCode, following `test_static_mcp_opencode_acceptance.py`'s
existing style):

1. A turn record built from a synthetic `submit_discovery` tool call with
   `state.time = {"start": T0, "end": T1}` contains `stage`, `started_at`,
   `completed_at`, and `elapsed_ms`.
2. `elapsed_ms` is always `>= 0` and equals `completed_at - started_at`; a
   deliberately out-of-order pair clamps to `0` instead of going negative.
3. Each name in `STATIC_MCP_TOOL_SEQUENCE` attributes to its documented
   stage (`submit_discovery → discovery`, ..., `finalize_analysis →
   finalize`); a `read_evidence` call between `submit_discovery` and
   `submit_execution` attributes to `discovery` (the last-entered stage),
   not `unknown`; a `read_evidence` call before any accepted `submit_*`/
   `start_analysis` attributes to `unknown`.
4. A turn's `tool_calls[0]["elapsed_ms"]` (tool execution) and the turn's own
   `elapsed_ms` (model-turn wait) are independent fields that can differ.
5. When `state` has no `time` key and the row carries no `time_created`/
   `time_updated`, the turn's `elapsed_ms` is `None` — never a fabricated
   number — while `input_chars`/`output_chars` (derived from `state.input`/
   `state.output`, unrelated to timestamps) are still populated.
6. Loading one of the preserved pre-instrumentation traces
   (`tests/evaluation/vs030-followup-e2e/attempt-2/jpetstore-6-summary/trace.json`,
   which has no `tool_calls`/`turns` key) through the new summarizer does not
   raise and returns an empty/degenerate summary rather than crashing.
7. `summarize_stage_timeline` on a multi-turn, multi-stage synthetic list
   correctly sums `elapsed_ms` per stage and reports the per-stage turn
   count and max.

Then: the full existing `tests/test_static_mcp_opencode_acceptance.py` suite
must continue to pass unchanged, demonstrating no regression from extending
`_static_tool_calls`'s return shape (additive fields only) or from the new
extraction call on the timeout paths.

## E2E verification

After focused and full tests pass, run `jpetstore-6-summary` against
`local-sglang` for **3 repeats** through the existing
`_run_static_mcp_acceptance` / `--interactive` Windows-PTY path (the same
invocation this ticket's evidence and `tests/evaluation/vs030-followup-e2e/`
used). Use an explicit experiment-only timeout of `480`–`600` seconds via
the existing `--timeout` flag so later stages have a chance to be observed;
record the timeout used and do not change the project's default. Preserve
all three attempts' `trace.json` / `terminal.log` under
`tests/evaluation/` (a new `vs-031-*` directory, mirroring
`vs030-followup-e2e`'s layout). Confirm the target repository is unchanged
before and after each attempt (`git status --short --branch`).

## Acceptance Criteria

* `tests/test_stage_timing_instrumentation.py` PASSes (all 7 cases above).
* `tests/test_static_mcp_opencode_acceptance.py` PASSes unchanged.
* The full `python -m unittest discover -s tests -p 'test_*.py'` suite
  PASSes, with any pre-existing baseline failure (if one exists) explicitly
  distinguished from a new regression.
* `python scripts/run_quality_gate.py` PASSes (or its pre-existing failures,
  if any, are named and shown to be unrelated to this change).
* `trace.json` for all three live `jpetstore-6-summary` / `local-sglang`
  repeats contains a non-empty `turns` list and a `total_elapsed_ms` value,
  regardless of whether that repeat completed or timed out.
* No `analysis_id`/`revision`/`transition_token` round-tripping, timeout
  default, payload shape, prompt text, or pipeline behavior changes.
* The target repository is unchanged before/after every live repeat.
* A stage-level timing table (per-repeat and aggregated) and a
  measurement-limitations note are produced in the ticket's closing report,
  with an evidence-backed Outcome A/B/C classification per the originating
  instructions — no causal claim beyond what the three repeats support.

## Commit boundary

```text
test: measure per-stage model latency
```

**One commit for this ticket.**
