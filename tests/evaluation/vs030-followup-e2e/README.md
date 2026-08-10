# Follow-up E2E evidence: server-owned control plane, jpetstore-6-summary

Preserved from three live runs (2026-08-10, `local-sglang/Qwen/Qwen3.6-35B-A3B-FP8`,
static-MCP `jpetstore-6-summary` case, `C:\temp\opencode-e2e-jpetstore-6`) made
after implementing the server-owned analysis control plane described in the
handoff for VS-030
(`docs/development/tickets/VS-030-mid-stage-retry-exhaustion-pipeline-exit.md`).
This is not a passing golden fixture — do not wire it into
`scripts/evaluate_scenarios.py` or the golden manifest.

## What changed since VS-030's evidence

`submit_<stage>`, `finalize_analysis`, and `reopen_analysis` no longer accept
or require `analysis_id` / `revision` / `transition_token` from the caller;
the trusted server uses its own active-session state instead. VS-030's
evidence run (`tests/evaluation/vs-030-mid-stage-retry-exhaustion/`) showed
the model invent a wrong `analysis_id` on its very next call after
`start_analysis` and never recover.

## Result across three attempts

None of the three attempts reached `finalize_analysis`; all three timed out
(240s) mid-pipeline. **None of the three shows an invented or corrupted
`analysis_id`** (`grep -c analysis_not_found` on every `terminal-deansi.txt`
is `0`) — the exact failure this change targets did not recur.

- `attempt-1`: reached `relationships`, hit a legitimate payload rejection
  (`relationship target process dangling` — a real domain validation, not an
  identifier bug), asked the user for clarification, then ran out of time.
- `attempt-2`: progressed cleanly through `discovery` → `execution` →
  `relationships` → `boundaries` (revision 4), loaded `analyze-k8s-contracts`,
  and was reasoning about the report-slot survey when the timeout hit.
- `attempt-3`: same shape as attempt 2 — reached `boundaries` → `contracts`
  survey reasoning before timing out.

The target repository (`C:\temp\opencode-e2e-jpetstore-6`) was unchanged
before and after all three attempts (`git status --short --branch` reported
`## HEAD (no branch)` both times).

## Next failure to hand off

All three attempts are consistent with one cause: `local-sglang`'s
`Qwen/Qwen3.6-35B-A3B-FP8` model is materially slower per turn than the
`upstage/solar-pro3` model used in VS-030's own evidence run, so the fixed
240s per-case timeout is not enough for this model to reach
`finalize_analysis` on this case. This is a availability/latency issue, not a
correctness regression — do not expand this ticket to address it. A
follow-up should either raise the timeout for this provider or re-run with
`upstage/solar-pro2` (see `memory/opencode-e2e.md`) to get a clean
pass/fail read on the full pipeline.

- `attempt-N/jpetstore-6-summary/trace.json` — the harness's own trace
  record for each attempt (`status: FAIL`, timeout reason).
- `attempt-N/jpetstore-6-summary/terminal-deansi.txt` — the PTY terminal
  transcript with ANSI escape codes stripped.
- `summary.json` — the three traces combined, as printed by the ad hoc
  runner (mirrors `static-mcp-results.json`'s shape).
