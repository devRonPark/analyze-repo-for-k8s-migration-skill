# VS-030 evidence: mid-stage retry exhaustion → fabricated report

Preserved from a live run (2026-08-10, commit `785af54`, `upstage/solar-pro3`,
`jpetstore-6-summary` static-MCP case) made while live-verifying VS-029. This
is failure evidence for VS-030, not a passing golden fixture — do not wire it
into `scripts/evaluate_scenarios.py` or the golden manifest as-is.

- `trace.json` — the acceptance harness's own trace record (`status: FAIL`,
  `reason: "OpenCode PTY did not produce a complete final Markdown report
  before timeout"`).
- `direct-result.json` — identical content to `trace.json`, written by the
  ad hoc script that called `_run_static_mcp_case()` directly to bypass an
  unrelated CRLF/golden-hash checkout artifact (see VS-030's ticket, "Why
  now").
- `terminal-deansi.txt` — the PTY terminal transcript with ANSI escape codes
  stripped, showing the actual tool-call sequence and model text. Key lines:
  the confirmed Discovery survey (19-41), the first invented `analysis_id`
  (45), the repeated `analysis_not_found` rejections carrying the server's own
  "submit unknown/inferred instead" instruction (83-187), and the fabricated
  final report contradicting that survey (191-243).

See `docs/development/tickets/VS-030-mid-stage-retry-exhaustion-pipeline-exit.md`
for the full analysis.
