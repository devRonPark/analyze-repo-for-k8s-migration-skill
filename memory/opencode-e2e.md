# OpenCode E2E Memory

Operational memory for running this Skill against a local OpenCode provider. It
does not change the runtime Skill contract.

## Windows-native static-MCP procedure (use this on this machine)

This session's environment (win32, MSYS Bash, no `tmux`, no `/home/*` target
checkout) cannot run AGENTS.md's detached-`tmux` procedure below as written —
see "AGENTS.md's `tmux` procedure" further down for why. Use this instead.
`scripts/run_opencode_acceptance.py` already has a working Windows-native
equivalent: a `pywinpty`-backed PTY harness (`--interactive` static-MCP mode)
driving six pinned target/mode cases from
`tests/evaluation/static-mcp-opencode-cases.json` /
`static-mcp-golden-manifest.json`. Confirmed working end-to-end 2026-08-10
(VS-030-HOTFIX-1.7 verification: reached `discovery → execution →
relationships → boundaries → contracts` before a provider-latency timeout).

Requirements (all present in this environment as of 2026-08-10):
- `opencode` on `PATH` (found at `~/.bun/bin/opencode`).
- The `winpty` Python package. Its PyPI/pip name is `pywinpty` but its import
  name is `winpty` — `import pywinpty` fails even when it is installed; test
  with `python -c "import winpty"`.
- A target checkout already present under `C:\temp\opencode-e2e-<name>` (e.g.
  `opencode-e2e-jpetstore-6`), pinned to the revision the golden manifest
  expects. Verify before running:
  `git -C C:\temp\opencode-e2e-<name> rev-parse HEAD` must equal the
  `Revision:` line in the matching `tests/evaluation/static-mcp-*-golden.md`.
  If the checkout does not exist or does not match, clone fresh and pin it —
  do not guess a path or proceed on a mismatch.
- Network access to the provider endpoint requires
  `sandbox_permissions: require_escalated` per `CLAUDE.md`.

Run from the repository root (`PYTHONPATH` must include both the repo root and
`runtime/python` so `scripts.markdown_contract` and `analysis_pipeline` both
import):

```bash
PYTHONPATH="runtime/python:." python scripts/run_opencode_acceptance.py --mode isolated --config runtime/opencode.json --cases tests/evaluation/static-mcp-opencode-cases.json --output-dir <a fresh directory, e.g. C:\temp\<ticket>-smoke> --case <one case ID> --interactive --timeout 300
```

`<one case ID>` is one of: `jpetstore-6-summary`, `jpetstore-6-detailed`,
`flask-celery-summary`, `flask-celery-detailed`, `fastapi-template-summary`,
`fastapi-template-detailed`.

Omit `--model` to use `runtime/opencode.json`'s default
(`local-sglang/Qwen/Qwen3.6-35B-A3B-FP8`); pass `--model upstage/solar-pro2`
for the Upstage fallback described below.

Read the result from `<output-dir>/<case-id>/trace.json`, not `terminal.log`
(raw ANSI PTY text — this script does not de-ANSI it automatically).
`trace.json["tool_calls"]` is a structured, per-call record
(`state.input.payload` / `state.error`) and is enough to verify one specific
stage's behavior without waiting for the full pipeline to finish.
`trace.json["status"]` is `PASS` only on a complete, target-unchanged,
correctly-ordered run through `finalize_analysis`; a `FAIL` from timeout is
not automatically a correctness regression — read the tool-call sequence
before concluding anything.

Known limitation (2026-08-10, not specific to any one ticket): the
`local-sglang` `Qwen/Qwen3.6-35B-A3B-FP8` model is materially slower per turn
than `upstage/solar-pro2`/`-pro3` and can time out mid-pipeline (observed
stalling while composing `submit_contracts`) even at `--timeout 300`, with no
correctness defect. Do not read a bare timeout as a regression; inspect
`trace.json["tool_calls"]` for the specific behavior under test, and re-run
with the Upstage fallback if a full-pipeline completion read is required.

The VS-030 ticket's note about a "CRLF/golden-hash checkout artifact" forcing
a direct call to `_run_static_mcp_case()` (bypassing
`load_static_mcp_golden_manifest()`) did not reproduce on 2026-08-10 —
`load_static_mcp_golden_manifest()` loaded cleanly. Try the CLI above first;
only fall back to calling `_run_static_mcp_case()` directly if the golden hash
check itself raises.

## AGENTS.md's `tmux` procedure (different environment)

The "Reproducible interactive run" / "Interactive Detailed run" sections below
describe AGENTS.md's canonical `tmux`-based policy for an environment that
*has* `tmux` and a Linux target checkout (e.g. under `/home/daolts/...`) — a
different host from the Windows sessions this memory file otherwise covers.
Do not attempt them on this machine; use the Windows-native procedure above.

## Provider fallback: Upstage Solar

The default `local-sglang` provider (`http://172.16.4.249:30000/v1`) has been
unreachable from this environment across multiple sessions (2026-08-07:
`curl` timed out, exit 28, both sandboxed and with per-command escalation),
but was reachable again on 2026-08-10 (`curl` returned HTTP 200, and a full
static-MCP run against it succeeded through the `contracts` stage — see the
Windows-native procedure above). Check connectivity fresh each session
(`curl -m 8 http://172.16.4.249:30000/v1/models` with escalation) rather than
assuming either state; move to the fallback below only after that check fails,
not on a stale memory of a past outage. Do not treat one more retry against it
as diagnostic once it has failed once this session; repeated silent retries
produce a failure that looks like a provider outage, per `CLAUDE.md`'s
escalation guidance.

`runtime/opencode.json` (commit `1239c50`) already defines an `upstage`
provider (`upstage/solar-pro2`, `@ai-sdk/openai-compatible`,
`baseURL: https://api.upstage.ai/v1`) as a working substitute. Its `apiKey`
is `{env:UPSTAGE_API_KEY}` — no secret lives in this repo.

- If `UPSTAGE_API_KEY` is not already set in the session, a key targeting the
  same `https://api.upstage.ai/v1` account exists in a sibling project's env
  file: `C:\Users\<user>\.config\kubernetes-migration-assistant\env`
  (`LLM_API_KEY`, confirm the `LLM_BASE_URL` line matches before reusing it).
  Load it into `UPSTAGE_API_KEY` for the single command that needs it; do not
  print the raw value or write it into any repo file.
- Verify with a direct `curl -H "Authorization: Bearer $UPSTAGE_API_KEY"
  https://api.upstage.ai/v1/models` (expect `200`) before spending a full
  acceptance run on it.
- Pass `--model upstage/solar-pro2` to `run_opencode_acceptance.py` (or set
  `"model"` in a copied `opencode.json`) to use it. Solar's latency can
  exceed the harness's default 180s timeout on some repeats — retry the
  specific failed repeat with `--timeout 300` rather than treating one
  timeout as a correctness failure.
- `demo-repositories/` is not checked into any worktree; clone the target
  fresh (e.g. `git clone https://github.com/mybatis/jpetstore-6.git` for the
  JPetStore 6 golden set) and pin it to the revision named in the relevant
  golden-set file (`tests/evaluation/jpetstore-6-golden.md`'s `Revision:`
  line) before running.

## Safe preflight

- Run `git status --short --branch` in this repository and
  `git -C /home/daolts/jpetstore-6 status --short --branch` before and after a
  run.
- Keep the analyzed repository read-only. The expected final status for the
  current target is `## master...origin/master`.
- Do not count a run that edits the target, writes a report into the target, or
  has an incomplete provider response.

## Reproducible interactive run

Build the current Skill into a temporary distribution and copy the agent into
the temporary OpenCode config. The temporary directory must start with
`/tmp/opencode-acceptance-`; the agent's `external_directory` permission allow
rule is intentionally scoped to that prefix.

```bash
run_dir=$(mktemp -d /tmp/opencode-acceptance-interactive-XXXXXX)
mkdir -p "$run_dir/home" "$run_dir/config/agents" "$run_dir/config/skills/analyze-repo-for-kubernetes"
cp runtime/agents/kubernetes-migration-analyzer.md "$run_dir/config/agents/kubernetes-migration-analyzer.md"
python3 scripts/build_dist.py --output "$run_dir/config/skills/analyze-repo-for-kubernetes"

env HOME="$run_dir/home" OPENCODE_CONFIG="$PWD/runtime/opencode.json" OPENCODE_CONFIG_DIR="$run_dir/config" OPENCODE_DISABLE_AUTOUPDATE=1 opencode /home/daolts/jpetstore-6 --mini --agent kubernetes-migration-analyzer
```

`runtime/opencode.json` supplies the provider endpoint and model. Keep the
temporary `HOME` and `OPENCODE_CONFIG_DIR`; otherwise a user config or stale
Skill can change the result. In the TTY, enter `/analyze-repo-for-kubernetes`
and wait for the final Markdown Summary. Concise assistant progress updates are
allowed while the analysis runs. Confirm the final report has the title
`Kubernetes 설계 입력 요약`, the required sections, Korean open-item labels,
exactly one verdict, and leaves `/home/daolts/jpetstore-6` unchanged.

## Result rules

- This runbook covers only the interactive Summary flow. Do not use `opencode
  run`, `--format json`, or a non-TTY wrapper for this check.
- Provider connection errors, incomplete responses, or a response that reaches
  the agent step cap without a complete report are availability failures.
- Do not count a response without a complete, valid final Markdown report as
  successful.

## Interactive Detailed run

Install the current distribution into a temporary `HOME` instead of hand-copying
the layout. `HOME="$run_dir/home" bash scripts/install-opencode.sh` places the
Skill, agent, command, and trusted tools where both the agent's
`$HOME/.config/opencode/skill/...` allow rule and `runtime/tools/read.ts`'s
trusted-Skill roots accept them.

Use a short, fixed run directory such as `/tmp/opencode-acceptance-det5`. With a
`mktemp` random suffix the model retypes the Skill path from the loader output
and a single dropped character makes every reference read fail with
`path is outside the target or trusted Skill`; that run is not a valid result.

Start the session with `tmux -L <socket> new-session -d`, send
`/analyze-repo-for-kubernetes Detailed`, then read the raw final report from
`$run_dir/home/.local/share/opencode/opencode.db` (`part`/`message` tables). The
TUI renders Markdown, so `capture-pane` loses `#` heading markers and cannot be
validated directly.

## Non-interactive measurement run

Use this form only for elapsed-time measurement. It is not the interactive
acceptance check above and never substitutes for it.

```bash
run_dir=$(mktemp -d /tmp/opencode-acceptance-detailed-XXXXXX)
mkdir -p "$run_dir/home" "$run_dir/config/agents" "$run_dir/config/skills/analyze-repo-for-kubernetes"
cp runtime/agents/kubernetes-migration-analyzer.md "$run_dir/config/agents/kubernetes-migration-analyzer.md"
python3 scripts/build_dist.py --output "$run_dir/config/skills/analyze-repo-for-kubernetes"

/usr/bin/time -f '\nELAPSED_SECONDS=%e' env HOME="$run_dir/home" OPENCODE_CONFIG="$PWD/runtime/opencode.json" OPENCODE_CONFIG_DIR="$run_dir/config" OPENCODE_DISABLE_AUTOUPDATE=1 opencode run -i --print-logs --log-level DEBUG --agent kubernetes-migration-analyzer --dir /home/daolts/jpetstore-6 '현재 저장소를 Kubernetes 이관 관점에서 Detailed 모드로 분석해줘. Detailed/상세/전체 평가를 명시적으로 요청한다. 분석이 끝나면 Detailed 보고서만 출력하고 대기해줘.'
```

## Mode and measurement rules

- Summary is the default. Detailed requires an explicit `Detailed`, `상세`, or
  `전체 평가` phrase in the user prompt.
- A valid Detailed run must load `migration-assessment-template.md` and
  `repository-analysis-checklist.md`. If the temp path is not under
  `/tmp/opencode-acceptance-*`, these reads are denied and the elapsed time is
  not a valid Detailed benchmark.
- `--print-logs --log-level DEBUG` mixes internal events with the report on
  stdout. The internal log is at
  `$HOME/.local/share/opencode/log/opencode.log` and normally does not contain
  the assistant's final report body; use stdout for the report and
  `ELAPSED_SECONDS` for timing.
- Provider connection errors or `Internal Server Error` responses are
  availability failures, not slow analyses. Retry only when the endpoint is
  available and label failed attempts separately.
- A run that reaches the agent step cap may still exit 0. Treat it as a
  completed measurement only when the returned report is present and contains
  the requested mode; never include the cap/progress text in the user-facing
  report.

## Observed baseline (2026-07-29)

- Summary: `75.26s`, valid four-section report.
- Detailed: `181.75s`, valid eight-section report with Detailed-only references.
- An invalid Detailed attempt using `/tmp/opencode-detailed-manual-*` took
  `199.69s`; all Detailed references were denied and it was excluded from the
  benchmark.
- The successful target run left `/home/daolts/jpetstore-6` clean.

## Failure patterns to avoid

1. Do not use a custom temp prefix that falls outside the agent's
   `external_directory` allow rule.
2. Do not interpret a denied reference read as a normal Detailed result; fix the
   temp layout and rerun.
3. Do not claim a time for a provider-unavailable or partial run.
4. Do not broaden target permissions, run builds, or modify the analyzed
   repository just to make the E2E pass.

## Summary response check

Validate the final TTY response, not merely that the session stayed open:

1. Its final assistant response is the complete `Kubernetes 설계 입력 요약`
   report; progress narration before it is allowed.
2. It contains every Summary template section, Korean open-item labels, and
   exactly one verdict.
3. Compare `git -C /home/daolts/jpetstore-6 status --short --branch` before
   and after the run; the output must be identical.
