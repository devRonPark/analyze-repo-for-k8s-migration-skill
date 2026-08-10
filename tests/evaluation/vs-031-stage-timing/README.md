# Per-stage model latency evidence: jpetstore-6-summary, local-sglang

Three live runs (2026-08-10, `local-sglang/Qwen/Qwen3.6-35B-A3B-FP8`,
static-MCP `jpetstore-6-summary` case, target `C:\temp\opencode-e2e-jpetstore-6`
pinned at `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`), produced by the VS-031
timing instrumentation
(`docs/development/tickets/VS-031-per-stage-model-latency-measurement.md`)
added to `_run_static_mcp_case`. Not a passing golden fixture — do not wire
into `scripts/evaluate_scenarios.py` or the golden manifest.

Timeout used: **600s** (experiment-only override via `--timeout 600`; the
harness's own default of 180s is unchanged). Target repository confirmed
unchanged before and after all three attempts
(`git -C C:\temp\opencode-e2e-jpetstore-6 status --short --branch` ==
`## HEAD (no branch)` throughout).

## Result across three attempts

All three attempts timed out at 600s without reaching a complete final
report. None show `analysis_not_found` (the VS-030 failure mode remains
fixed). Each attempt got permanently stuck retrying a single stage:

| Attempt | Highest stage reached | Stuck in           | Retries in stuck stage | Status |
|---------|------------------------|---------------------|------------------------|--------|
| 1       | contracts               | `contracts`         | 10 consecutive `submit_contracts` rejections | FAIL (timeout) |
| 2       | boundaries               | `boundaries`         | 22 consecutive `submit_boundaries` rejections | FAIL (timeout) |
| 3       | boundaries (attempted `finalize_analysis` and `reopen_analysis` mid-loop, both rejected) | `boundaries` | 15+ `submit_boundaries` rejections, 2 `reopen_analysis` attempts | FAIL (timeout) |

## Per-attempt stage timing (model-turn wall-clock vs. tool execution)

`elapsed_ms` = harness-observed wait between the previous tool call's end and
this call's start (see VS-031 for the exact definition); `tool ms` = the MCP
tool's own execution time, read from OpenCode's `state.time.{start,end}`.

### Attempt 1

| Stage | Turns | Model-turn total (ms) | Model-turn mean (ms) | Tool mean (ms) |
|---|---|---|---|---|
| dispatcher/start | 1 | – | – | 616 |
| discovery | 2 | 42,900 | 21,450 | 214.5 |
| execution | 1 | 17,623 | 17,623 | 223.0 |
| relationships | 2 | 27,027 | 13,513.5 | 207.0 |
| boundaries | 1 | 19,301 | 19,301 | 214.0 |
| contracts | 14 | 356,013 | 25,429.5 | 139.3 |

### Attempt 2

| Stage | Turns | Model-turn total (ms) | Model-turn mean (ms) | Tool mean (ms) |
|---|---|---|---|---|
| dispatcher/start | 1 | – | – | 548 |
| discovery | 8 | 78,082 | 9,760.3 | 96.6 |
| execution | 3 | 61,832 | 20,610.7 | 112.7 |
| relationships | 2 | 46,484 | 23,242.0 | 130.5 |
| boundaries | 23 | 393,175 | 17,094.6 | 76.3 |

### Attempt 3

| Stage | Turns | Model-turn total (ms) | Model-turn mean (ms) | Tool mean (ms) |
|---|---|---|---|---|
| dispatcher/start | 1 | – | – | 600 |
| discovery | 10 | 107,554 | 10,755.4 | 118.4 |
| execution | 1 | 25,322 | 25,322 | 215.0 |
| relationships | 2 | 34,700 | 17,350.0 | 156.0 |
| boundaries | 16 | 231,066 | 14,441.6 | 73.1 |
| finalize | 1 | 7,037 | 7,037 | 61.0 |

## Aggregate across all three attempts

| Stage | Turns (n) | Model-turn mean (ms) | Model-turn max (ms) | Tool mean (ms) | Output payload mean (chars) |
|---|---|---|---|---|---|
| dispatcher/start | 3 | – | – | 588 | 72 |
| discovery | 20 | 11,426.8 | 26,239 | 119.3 | 685.2 |
| execution | 5 | 20,955.4 | 28,234 | 155.2 | 1,383.0 |
| relationships | 6 | 18,035.2 | 23,763 | 164.5 | 1,452.2 |
| boundaries | 40 | 16,088.5 | 30,789 | 78.5 | 1,398.5 |
| contracts | 14 | 25,429.5 | 32,528 | 139.3 | 2,428.2 |
| finalize | 1 | 7,037 | 7,037 | 61.0 | 2 |

## Findings

1. **MCP/tool execution time is never the bottleneck.** Mean tool execution
   across every stage stays under ~220ms; total tool time across all three
   full 600s attempts sums to a few seconds. This confirms the ticket's
   originating hypothesis.
2. **Model-turn latency is the dominant cost, and it is not flat across
   stages** (contradicts a clean Outcome B): discovery averages ~11.4s/turn,
   boundaries ~16.1s/turn, contracts ~25.4s/turn (highest mean and highest
   max of any stage). Output payload size also grows from discovery
   (~685 chars) toward contracts (~2,428 chars) — an **observed
   correlation**, not proven causation (contracts appears in only one of the
   three attempts, so this specific stage's numbers rest on n=14 turns from
   a single attempt).
3. **The dominant cause of full-attempt timeout is not per-turn latency
   growth — it is retry-loop count in one specific stage per attempt**
   (Outcome C, but the anomaly is turn *count*, not turn *duration*).
   boundaries alone accounts for 40 of the 89 total measured turns across all
   three attempts, at a per-turn latency (~16s mean) that is not higher than
   execution's or relationships'. Terminal transcript inspection (see
   `attempt-2/jpetstore-6-summary/terminal-deansi.txt`) shows the model
   correctly diagnosing a genuine evidence gap for this repository
   (`independent_lifecycle_status` has no supporting evidence in the
   boundaries-stage survey — every observation for "lifecycle signals" is
   `unknown`) but, rather than following its own stage Skill's written
   instruction to submit `unknown`/`inferred` once retry budget is exhausted
   and stop, it kept constructing new payload variants for the remainder of
   the 600s window, each tripping a different validation error
   (`workload claim dangling`, `workload claim duplicate`,
   `observation_stage_mismatch`, `claim evidence aliases required`,
   `boundaries requires trusted evidence and claims`). Attempt 3 additionally
   shows a premature `finalize_analysis` attempt (rejected: `stage_order`)
   and two `reopen_analysis` attempts (rejected: `reopen_not_ready`) inside
   this same loop.
4. **This is a related but distinct failure mode from VS-030's.** VS-030 was
   about the model resubmitting an *identical* payload past its retry
   budget. Here the model resubmits *different* payloads past budget, each
   satisfying the previously-named issue while tripping a new one — the
   existing "do not draft a fallback report" / "submit unknown/inferred and
   stop" instruction is present in the Skill but was not followed in any of
   the three attempts once genuinely blocked.

## Recommended next ticket (evidence-backed, not implemented here)

Two independent, narrowly-scoped candidates, in order of expected impact:

1. **Boundaries/contracts retry-loop containment**: strengthen the
   already-written "submit unknown/inferred and stop" instruction so it is
   followed once the submission retry budget is exhausted, specifically for
   the case where the stage's own survey shows a structural evidence gap
   (all observations for one required condition are `unknown`). This is a
   prompt-only change in the same family as VS-029/VS-030, not a payload or
   validation-rule change.
2. **Contracts-stage payload/latency profiling**: contracts shows both the
   highest per-turn model latency and the largest output payload of any
   stage in this data, but rests on a single attempt (n=14 turns). A
   dedicated repeat set that reaches contracts consistently (e.g. after (1)
   reduces boundaries' retry count) would be needed before treating this as
   more than a single-attempt observation.

Do not implement either here; this ticket is characterization only.

## Instrumentation limitations

* `input_chars` is `None` for every stage's first turn in each attempt (no
  prior tool response to measure) and undercounts total model context in
  general — it only measures the immediately preceding tool response, not
  the full accumulated conversation.
* `elapsed_ms` for the very first turn in every attempt (`start_analysis`)
  is `None` — there is no harness-observed anchor before the first tool
  call; the initial Skill-load/prompt-submission time is not captured.
* `terminal-deansi.txt` (ANSI-stripped from the harness's own `terminal.log`,
  which `.gitignore`'s `*.log` rule keeps out of the repository, matching
  `tests/evaluation/vs030-followup-e2e`'s convention) is capped at the last
  1,000,000 characters of PTY output
  (`_run_static_mcp_case`'s existing rolling buffer, unchanged by this
  ticket); the discovery/execution/relationships portions of the raw
  transcript were already evicted by the time a 600s attempt ended, though
  the structured `trace.json` timing for those stages is unaffected (it
  reads OpenCode's SQLite database, not the terminal buffer).
* Token counts are not reported anywhere; only character counts, per the
  ticket's explicit instruction not to add a tokenizer dependency.

## Files

* `attempt-N/jpetstore-6-summary/trace.json` — the harness's trace record for
  each attempt, including `turns` (this ticket's new field), `tool_calls`
  (raw, with `state.time` where OpenCode provides it), and
  `total_elapsed_ms`.
* `attempt-N/jpetstore-6-summary/terminal-deansi.txt` — the PTY terminal
  transcript with ANSI escape codes stripped (last 1,000,000 characters of
  the raw capture only).
* `attempt-N/static-mcp-results.json` — the single-case result wrapper the
  CLI writes per invocation.
