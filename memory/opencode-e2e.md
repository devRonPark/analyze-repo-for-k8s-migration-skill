# OpenCode E2E Memory

Operational memory for running this Skill against a local OpenCode provider. It
does not change the runtime Skill contract.

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
