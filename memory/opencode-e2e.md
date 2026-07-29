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

## Reproducible local run

Build the current Skill into a temporary distribution and copy the agent into
the temporary OpenCode config. The temporary directory must start with
`/tmp/opencode-acceptance-`; the agent's `external_directory` permission allow
rule is intentionally scoped to that prefix.

```bash
run_dir=$(mktemp -d /tmp/opencode-acceptance-detailed-XXXXXX)
mkdir -p "$run_dir/home" "$run_dir/config/agents" "$run_dir/config/skills/analyze-repo-for-kubernetes"
cp runtime/agents/kubernetes-migration-analyzer.md "$run_dir/config/agents/kubernetes-migration-analyzer.md"
python3 scripts/build_dist.py --output "$run_dir/config/skills/analyze-repo-for-kubernetes"

/usr/bin/time -f '\nELAPSED_SECONDS=%e' env HOME="$run_dir/home" OPENCODE_CONFIG="$PWD/runtime/opencode.json" OPENCODE_CONFIG_DIR="$run_dir/config" OPENCODE_DISABLE_AUTOUPDATE=1 opencode run -i --print-logs --log-level DEBUG --agent kubernetes-migration-analyzer --dir /home/daolts/jpetstore-6 '현재 저장소를 Kubernetes 이관 관점에서 Detailed 모드로 분석해줘. Detailed/상세/전체 평가를 명시적으로 요청한다. 분석이 끝나면 Detailed 보고서만 출력하고 대기해줘.'
```

`runtime/opencode.json` supplies the provider endpoint and model. Keep the
temporary `HOME` and `OPENCODE_CONFIG_DIR`; otherwise a user config or stale
Skill can change the result.

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
