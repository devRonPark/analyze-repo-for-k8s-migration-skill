# VS-030 — Close the Free-Text Escape Hatch on Mid-Stage Retry-Budget Exhaustion

## Outcome

When a non-final stage's submission retry budget is exhausted, the LLM agent
either (a) submits with `unknown`/`inferred` status through the normal
`submit_<stage>` tool as the stage's own instructions already say, or (b)
states the blocker in one sentence and stops. It never fabricates a free-text
Markdown analysis report outside the MCP pipeline. Every non-final Skill gets
the same "do not draft a fallback report" prohibition that VS-029
(commit `785af54`, not filed as a ticket doc — given directly and implemented
in the same session as this one) added to `analyze-k8s-finalize` only.
Separately, every Skill that constructs a `submit_<stage>` /
`finalize_analysis` / `reopen_analysis` envelope is told, in one explicit
sentence, to copy `analysis_id`, `revision`, and `transition_token` verbatim
from the most recently accepted response rather than retype or reconstruct
them.

## Why now

While live-verifying VS-029 against `upstage/solar-pro3` (2026-08-10, not a
regression test of VS-029 itself — this failure mode is orthogonal to what
VS-029 changed and reproduced on the *post*-VS-029 commit `785af54`), a run
against the pinned `jpetstore-6-summary` static-MCP case produced this
sequence, preserved at
`tests/evaluation/vs-030-mid-stage-retry-exhaustion/trace.json` and the
de-ANSI'd terminal transcript
`tests/evaluation/vs-030-mid-stage-retry-exhaustion/terminal-deansi.txt`
(line numbers below refer to this de-ANSI'd copy; see that directory's
`README.md`):

1. `analysis_start_analysis` succeeded and returned
   `analysis_id: "an_4vGykntgSlEitUjFiYoHtieS"`, with a Discovery survey that
   **confirmed** `pom.xml:1`, `Dockerfile:1`, `docker-compose.yaml:1`,
   `src/main/webapp/WEB-INF/web.xml:1`, and
   `src/main/webapp/WEB-INF/applicationContext.xml:1` (`terminal-deansi.txt:19-41`).
2. The model's very next call, `analysis_submit_discovery`, used a different,
   invented `analysis_id` (`an_Gxqvnf6wlt2g_1K`, `terminal-deansi.txt:45`) — not a
   near-miss typo of the real one. `runtime/python/analysis_pipeline/session.py:151-153`
   correctly rejects any `analysis_id` that doesn't match the active session
   with `ValueError("analysis_not_found")`.
3. It retried repeatedly with further invented IDs, then re-used one
   (`an_4vKyqFzH24NTZYN`) unchanged across at least 8 further calls
   (`terminal-deansi.txt:77-187`, spanning `submit_discovery`, a redundant
   `start_analysis`, `list_target_paths`, `reopen_analysis`, and
   `finalize_analysis` — all rejected `analysis_not_found`), each time
   receiving the server's own explicit instruction verbatim
   (`runtime/python/analysis_pipeline/mcp_server.py:91-101`):
   > `analysis_not_found - this is beyond the current discovery stage's
   > submission retry budget; resubmitting the same payload will not
   > succeed, resolve the specific issue above or submit with
   > unknown/inferred status on whatever it cannot ground`
4. One attempt (`terminal-deansi.txt:133-139`) sent a syntactically invalid
   payload (a JSON array of bare `"key": value` pairs instead of an object)
   and OpenCode reported `Model tried to call unavailable tool 'invalid'`.
5. The model never once called `submit_discovery` with `unknown`/`inferred`
   status as instructed, and never called `finalize_analysis` successfully.
   Instead it emitted a final free-text Korean response (`terminal-deansi.txt:191-243`)
   asserting the repository **has no** Dockerfile, no `pom.xml`, and is not a
   Git repository — the exact opposite of the evidence its own
   `start_analysis` call had confirmed two turns earlier — plus a "다음 단계
   제안" (next-steps) section, which the Summary template and `SKILL.md`'s
   Analysis contract both forbid.
6. The harness correctly marked this `status: FAIL` (`OpenCode PTY did not
   produce a complete final Markdown report before timeout`) because no
   `finalize_analysis` ever succeeded — but a live user driving this
   interactively would have received the fabricated report as the assistant's
   final answer, with no visible failure at all.

No Skill file anywhere (`SKILL.md`, any `runtime/stage-skills/*/SKILL.md`, or
`runtime/agents/kubernetes-migration-analyzer.md`) instructs the model on how
to construct the `analysis_id`/`revision`/`transition_token` envelope fields —
confirmed by `grep -rl analysis_id runtime/` returning only Python source and
tests, never a prompt file. The model is left to infer the mechanic from the
dynamically-discovered MCP tool schemas alone.

This is a live-run observation, not a bisected regression: the *before*
(`fe2d5b0`) arm of the same comparison never completed a run to compare
against (blocked first by a CRLF/golden-hash checkout artifact, then the
comparison was stopped by decision before a valid before-arm run happened).
Do not describe this ticket as "caused by VS-029" — treat it as a
pre-existing gap that VS-029's Finalize-only fix happened to make visible by
narrowing where a fallback report is explicitly forbidden.

## Read first

* This ticket's "Why now" section and the preserved artifacts under
  `tests/evaluation/vs-030-mid-stage-retry-exhaustion/`.
* `runtime/stage-skills/analyze-k8s-discovery/SKILL.md` and the four other
  non-final stage Skills — all share the `## Transition` accepted/rejected
  structure VS-029 just wrote; this ticket adds one more prohibition line to
  the same section rather than restructuring it again.
* `runtime/stage-skills/analyze-k8s-finalize/SKILL.md` — the existing
  `If \`finalize_analysis\` fails, do not draft a fallback report.` sentence
  (VS-029) is the pattern to generalize.
* `runtime/python/analysis_pipeline/mcp_server.py:87-101` — the retry-budget
  rejection wrapper and its exact message text.
* `runtime/python/analysis_pipeline/session.py:150-157` (`assert_envelope`) —
  envelope validation (`analysis_id`/`revision`/`transition_token` mismatch
  handling).
* `runtime/python/tests/test_submit_retry_budget.py` — existing Python
  coverage for the retry-budget mechanics themselves (unaffected; this ticket
  is prompt-only).
* `SKILL.md` (dispatcher) — confirm there is genuinely no existing
  envelope-copying instruction before adding one; check whether it belongs in
  the dispatcher (loaded once, before any stage) or must be repeated per stage
  Skill (each stage Skill is loaded fresh per VS-029's `## Transition`
  contract, so dispatcher-only placement may not survive the handoff — verify
  before choosing where to put it).

## In scope

* Add one sentence to every non-final stage Skill's Checkpoint/Transition
  area: on retry-budget exhaustion, submit `unknown`/`inferred` status through
  the normal tool call, or state the blocker and stop — never produce a report
  outside the pipeline. Reuse VS-029's Finalize wording as the template:
  `If <submit_stage> fails, do not draft a fallback report.` adapted for the
  fact that non-final stages *do* have a legitimate final fallback (submit
  unknown/inferred) that Finalize does not.
* Add one sentence (placement per the "Read first" investigation above)
  instructing the model to copy `analysis_id`, `revision`, and
  `transition_token` verbatim from the most recently accepted response, never
  retype or reconstruct them.
* A static contract test (extend `tests/test_stage_transition_contract.py` or
  sibling) asserting the new prohibition sentence is present in every
  non-final stage Skill, and the envelope-copying sentence is present
  somewhere the model reliably sees it before its first `submit_<stage>` call.

## Out of scope

* Any change to `runtime/python/analysis_pipeline/*` — the Python state
  machine already rejects the malformed envelope correctly; this is a
  prompt-only ticket, same posture as VS-029.
* Chasing the single malformed-JSON tool call (`terminal-deansi.txt:133-139`) — one
  occurrence is not enough evidence to diagnose, and it may be a
  model-capability limit rather than an instruction gap. Note it in a comment,
  do not design around it.
* A full before/after live comparison of VS-029 itself — deliberately stopped
  or the caller task; do not resume it as part of this ticket.
* Treating `tests/evaluation/vs-030-mid-stage-retry-exhaustion/` as a
  *passing* golden fixture or wiring it into
  `scripts/evaluate_scenarios.py` — it is preserved failure evidence, not a
  golden case. If a regression fixture is wanted, build it deliberately (e.g.
  inject a forced `analysis_not_found` the way `test_submit_retry_budget.py`'s
  `foreign_observation_ref` does) rather than replaying this exact transcript.

## Tests first

Static prompt-contract tests before any live run: assert the new
fallback-report prohibition text appears in all five non-final stage Skills,
and the envelope-copying sentence is present and not accidentally scoped to
only one stage.

## E2E verification

Reproduce the failure deliberately and cheaply first (no live model call
needed): call `runtime/python/analysis_pipeline/mcp_server.py`'s `Server`
directly with a fabricated wrong `analysis_id` on `submit_discovery`
(mirroring `test_submit_retry_budget.py`'s pattern) to confirm the server's
rejection message is unchanged, then re-run one live
`jpetstore-6-summary` case (`upstage/solar-pro3`, same harness/config as this
session — see this project's other memory for the exact invocation, the
CRLF/golden-hash gate must be worked around the same way this session did:
call `scripts.run_opencode_acceptance._run_static_mcp_case()` directly with a
freshly-computed `sha256` instead of going through
`load_static_mcp_golden_manifest()`) to check whether the model still ignores
the retry-budget exhaustion message after the new instruction is added. One
clean repeat is not proof; note honestly if budget/time only allows one.

## Acceptance Criteria

* Every non-final stage Skill explicitly forbids fabricating a report on
  retry-budget exhaustion, in wording distinct enough from Finalize's that a
  contract test can check for it independently.
* Every stage Skill (or a single point loaded before the first `submit_<stage>`
  call, verified to survive the VS-029 stage-transition handoff) instructs the
  model to copy the envelope fields verbatim.
* New static contract tests PASS.
* Existing Python/static tests and quality gate PASS unchanged.

## Commit boundary

```text
fix: forbid fallback reports and envelope guessing on mid-stage failure
```

**One commit for this ticket.**
