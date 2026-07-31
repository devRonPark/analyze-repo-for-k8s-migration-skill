# VS-008 — Replace static JSON duplication with an executable scenario evaluator

## Outcome

Regression results come from actual report artifacts produced for repository fixtures, not from comparing two prewritten JSON objects inside the same file.

## Why this is a vertical slice

It creates a closed evaluation loop: scenario definition → actual output directory → report validation → behavior rubric → repository immutability check → machine-readable result.

## Status and dependencies

- **Status:** Ready after contract slices
- **Depends on:** VS-001, VS-004, VS-006, VS-007
- **Blocks:** VS-009, VS-011, VS-012

## Read first

- `scripts/validate_regression.py`
- `tests/fixtures/regression/expected.json`
- `tests/scenarios.md`
- report validators and fixtures from VS-004/VS-007

## Scope

### In scope

- Replace `first`/`second` static fields with `query`, `repository_fixture`, `report_mode`, `expected_behavior`, and `forbidden_behavior`.
- Add a runner that evaluates externally generated actual reports and optional trace/event files.
- Validate report structure, expected core facts, forbidden claims, readiness verdict, and repository Git/content immutability.
- Cover all four evidence states and all three readiness verdicts across the suite.
- Keep deterministic comparison as a secondary check across repeated real runs, not as self-comparison inside one fixture.

### Out of scope

- Invoking OpenCode directly; VS-009 supplies that adapter.
- Implementing OpenShell security event checks; VS-011 extends the evaluator.
- Exact natural-language equality of full reports.

## Implementation steps

1. Define a versioned scenario JSON schema.
2. Create at least eight small repository fixtures with known facts and explicit forbidden conclusions.
3. Implement `scripts/evaluate_scenarios.py --cases ... --actual-dir ...`.
4. Retire or repurpose `validate_regression.py`; do not leave both as competing truth sources.
5. Add one deliberately invalid report per major validation category.

## Acceptance criteria

- A missing actual report fails.
- A report with correct structure but wrong candidate/dependency facts fails.
- A report with repository changes fails.
- Repeated actual runs may differ in prose but must match stable core fields.
- The evaluator outputs a per-case JSON result usable by CI and later OpenShell checks.

## Verification commands

```bash
python3 scripts/evaluate_scenarios.py --cases tests/evaluation/cases.json --actual-dir tests/evaluation/golden-actual
python3 -m unittest discover -s tests -p 'test_scenario_evaluator.py' -v
python3 scripts/run_quality_gate.py
git diff --check
```

## Expected file changes

- `schemas/evaluation-case.schema.json` (new)
- `scripts/evaluate_scenarios.py` (new)
- `scripts/validate_regression.py` (remove or delegate)
- `tests/evaluation/cases.json` (new)
- `tests/evaluation/golden-actual/` (new)
- `tests/fixtures/repos/`
- `tests/test_scenario_evaluator.py` (new)
- `tests/fixtures/regression/expected.json` (remove after migration)

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `test: evaluate real report artifacts by scenario`

## Codex execution instruction

```text
Implement only VS-008. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
