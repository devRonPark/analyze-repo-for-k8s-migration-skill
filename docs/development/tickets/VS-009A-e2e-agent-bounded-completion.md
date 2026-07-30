# VS-009A — Bound OpenCode E2E agent completion

## Outcome

The OpenCode-only E2E agent has a bounded read-only analysis profile: it accepts
the Git command forms emitted by the model, prioritizes high-signal repository
evidence, and is forced to synthesize text after a finite number of agentic
iterations.

## Status and dependencies

- **Status:** Partial; deterministic configuration checks pass, but the provider
  acceptance suite remains unavailable after its timeout
- **Depends on:** VS-009
- **Blocks:** None; VS-010 and all OpenShell work remain out of scope

## Why this is a separate ticket

VS-009 established Skill discovery, permission tracing, and the OpenCode
adapter. Its interactive trace showed that the model could remain in discovery
for an unbounded session. This ticket records the E2E-specific completion
guardrails without changing the normal Skill instructions or starting the next
platform slice.

## Scope

### In scope

- Allow only read-only `git -C` forms needed for target status and revision
  resolution.
- Set the OpenCode agent `steps` limit to 20. OpenCode uses this limit to force
  a text response after the configured number of agentic iterations.
- Add an E2E-agent prompt rule for a bounded high-signal inventory and immediate
  Summary synthesis once required fields have evidence or scoped unknowns.
- Add deterministic configuration contract tests and record the provider result.

### Out of scope

- Broad `bash` permission, shell wrappers, write commands, or `--auto` approval.
- Changes to the normal user-invoked Skill workflow.
- OpenShell, gateway, provider tuning beyond the E2E agent guardrails, or VS-010.

## Acceptance criteria

- Resolved OpenCode agent configuration reports `steps: 20`.
- Resolved permissions allow `git -C * status`, `git -C * status *`,
  `git -C * rev-parse *`, and `git -C * symbolic-ref *`, while the general
  `bash` rule remains denied.
- The agent prompt contains bounded high-signal discovery and Summary synthesis
  instructions.
- Targeted adapter tests pass.
- The acceptance run records `UNAVAILABLE` rather than `PASS` when the provider
  does not return a final report before timeout, and the analyzed Repository
  remains unchanged.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_opencode_adapter -v
debug_home=$(mktemp -d /tmp/opencode-debug-XXXXXX)
HOME="$debug_home" OPENCODE_CONFIG=runtime/opencode.json OPENCODE_CONFIG_DIR=runtime opencode debug agent kubernetes-migration-analyzer --pure
python3 scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --repository-root /home/daolts/jpetstore-6 --model local-sglang/Qwen/Qwen3.6-35B-A3B-FP8 --timeout 180 --output-dir .artifacts/opencode-vs009a
python3 scripts/run_quality_gate.py
git diff --check
```

## Expected file changes

- `runtime/opencode.json`
- `runtime/agents/kubernetes-migration-analyzer.md`
- `tests/test_opencode_adapter.py`
- `docs/development/plans/initial-skill-diet-roadmap.md`
- `docs/development/archive/initial-opencode-milestone/status.md`

## Commit boundary

- Commit the verified Ticket changes immediately; do not push without explicit authorization.
