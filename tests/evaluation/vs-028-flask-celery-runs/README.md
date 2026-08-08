# VS-028 reproduction evidence — `flask-celery-example`

Preserved run artifacts for [VS-028](../../../docs/development/tickets/VS-028-prose-only-process-discovery.md),
kept in the repository rather than a scratch directory per the ticket's
implementation step 1.

## Provenance

- Target: `github.com/miguelgrinberg/flask-celery-example`, cloned fresh,
  `master` at clone time, kept read-only. `git status --short --branch` was
  `## master...origin/master` before and after every run.
- Harness: `python scripts/run_opencode_acceptance.py --config runtime/opencode.json
  --cases tests/evaluation/opencode-cases.json --case <case> --repository-root <clone>
  --repeat 3 --skip-debug`.
- Provider/model: `upstage/solar-pro2`. The project's default local provider
  (`local-sglang`, `http://172.16.4.249:30000/v1`) was checked once this session
  and was unreachable (`curl` exit 28, timeout), consistent with
  `memory/opencode-e2e.md`. `solar-pro3` was not needed: no run hit a
  context-length error.
- `before-*` ran against the tree at `24fd979` (pre-change); `after-*` ran
  against this branch's working tree.
- `debug/` and `debug.json` are deliberately absent. OpenCode's debug probes
  dump the resolved provider config, including the literal `apiKey`, to disk;
  runs use `--skip-debug` and any such file is deleted immediately.

## Result

The Celery worker is **not** identified as its own deployment candidate, and no
explicitly evidenced open `미확인` boundary decision is recorded, in any repeat —
before or after the change.

| Set | Repeats | Harness status | `배포 대상 후보` entries | Worker candidate | Open boundary item |
| --- | ---: | --- | ---: | --- | --- |
| before-summary | 3 | 3 PASS | 1 in each | no | no (repeat-01 records a `workload-boundary` key, but its description asserts a single Flask application — a closed conclusion, not an open decision) |
| after-summary | 3 | 3 PASS | 1 in each | no | no |
| before-detailed | 3 | 3 PASS | 1 in each | no | no |
| after-detailed | 3 | 2 PASS, 1 FAIL (Detailed Markdown validation) | 1, 2, 1 | no | no |

In every run the deployment candidate's start command is `python app.py`; the
`celery ... worker` process documented in `README.md` is never counted.
`after-detailed/repeat-02` emits two `components` entries, but the second is
`redis`, not the Celery worker — it does show the removed one-entry cap no
longer suppresses a second card.

JPetStore 6 (`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`) was re-run for Summary
on this branch as the regression check. Each scored repeat produced exactly one
`배포 대상 후보` (`jpetstore-web-app` / `jpetstore`), port `8080`, verdict
`추가 정보 필요` — matching `jpetstore-6-golden.md`'s "one JPetStore WAR/web
workload" dimension, so the added Analysis-contract sentence did not cause
over-splitting. That is a check of the split/merge dimension only; the golden
set's 66/100 total is a human-scored rubric against an interactive `tmux` run
and was not recomputed here.

## Why the change did not move the number

`trace.json`'s `tool_calls` is the load-bearing evidence. In **every** run, in
both modes, before and after, the agent's only tool calls are:

    skill(analyze-repo-for-kubernetes) → glob/read of target files

No run reads `references/workflow.md`, `references/workload-boundary.md`,
`references/repository-analysis-checklist.md`, or
`assets/migration-assessment-template.md`. The `skill` tool returns
`<skill_content>` containing `SKILL.md` only; every other reference is a
separate file the model must choose to `read`, and it does not.

`workflow.md` was already an unconditional load *before* this ticket and is
likewise never read. So membership in an "unconditional load list" — the
mechanism this ticket changes — does not determine what reaches the model in
this runtime. Moving `workload-boundary.md` between the conditional and
unconditional lists is therefore inert at runtime, which is a different failure
from the three framings recorded in the ticket's revision history.

The parts of this change that *do* reach the model are `SKILL.md` (via the
`skill` tool) and the agent prompt in `runtime/agents/kubernetes-migration-analyzer.md`.
Both now state that a file or module boundary is not by itself evidence of a
single candidate. That was not sufficient to change the outcome in 3 Summary
repeats, consistent with `ADR-2026-08-07-002`'s finding that instruction-only
fixes show diminishing returns for this prompt.

Fact vs. inference:

- **Fact:** no reference file is read in any preserved run; the worker is not a
  candidate in any preserved run, before or after.
- **Evidence-backed inference:** the unconditional-load-list edit cannot change
  behaviour while no reference file is read at all.
- **Not established:** why the model never reads the references — whether the
  agent's step budget, the `read` tool's trusted-path rules, or the prompt's own
  "read only target files needed to support a required finding" instruction
  suppresses them. That needs its own investigation and is out of VS-028's scope.
