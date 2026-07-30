# VS-001 — Lock the executable baseline and one-command quality gate

## Outcome

A contributor can run one command to reproduce the current package validation, 31 unit tests, and regression-fixture check, with the result recorded as the comparison baseline for all later slices.

## Why this is a vertical slice

It delivers a complete developer workflow from checkout to an auditable pass/fail result. Later refactors can be compared against the same gate instead of relying on memory or prose.

## Status and dependencies

- **Status:** Ready now
- **Depends on:** None
- **Blocks:** VS-002 through VS-013

## Read first

- `scripts/validate_skill.py`
- `scripts/validate_report.py`
- `scripts/validate_regression.py`
- `tests/test_package.py`
- `tests/test_repository_distribution.py`
- `.github/workflows/test.yml`

## Scope

### In scope

- Add one repository-local quality-gate entrypoint using Python standard library or a small shell wrapper.
- Run package validation, unit-test discovery, and regression-fixture validation in a fixed order.
- Fail fast with the failed command and exit code; print a concise final summary.
- Record the current baseline: package validator passes, 31 tests pass, and 8 static regression cases pass.
- Make CI call the same entrypoint so local and CI behavior cannot drift.

### Out of scope

- Changing Skill instructions, validators, fixtures, or output contracts.
- Adding OpenCode or OpenShell integration.
- Claiming the current static regression fixture proves real agent behavior.

## Implementation steps

1. Create `scripts/run_quality_gate.py` or `scripts/run-quality-gate.sh`; prefer Python for Windows/WSL portability.
2. Execute the three existing commands with inherited stdout/stderr and deterministic working directory.
3. Add a unit test that proves a failing child command makes the gate fail.
4. Update `.github/workflows/test.yml` to invoke only the unified gate.
5. Add `docs/baseline.md` with the exact date, commands, observed counts, and the limitation of the static regression fixture.

## Acceptance criteria

- `python3 scripts/run_quality_gate.py` exits 0 on the untouched repository.
- The output reports 31 unit tests and 8 static regression cases without presenting them as agent E2E coverage.
- A simulated command failure returns non-zero.
- CI and local validation use the same entrypoint.
- No production Skill behavior changes.

## Verification commands

```bash
python3 scripts/run_quality_gate.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

## Expected file changes

- `scripts/run_quality_gate.py` (new)
- `tests/test_quality_gate.py` (new)
- `.github/workflows/test.yml`
- `docs/baseline.md` (new)

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `test: add unified skill quality gate`

## Codex execution instruction

```text
Implement only VS-001. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
