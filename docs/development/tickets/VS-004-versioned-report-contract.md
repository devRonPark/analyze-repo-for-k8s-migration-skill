# VS-004 — Version and enforce the current report contract

## Outcome

Summary, detailed Markdown, and optional JSON outputs share one current contract, while legacy headings and verdicts cannot silently pass as current output.

## Why this is a vertical slice

It protects the report a user receives from template through validation. The slice includes contract constants/schema, validators, positive fixtures, and negative fixtures.

## Status and dependencies

- **Status:** Ready after VS-001
- **Depends on:** VS-001
- **Blocks:** VS-007, VS-008, VS-011

## Read first

- `scripts/validate_report.py`
- `assets/migration-summary-template.md`
- `assets/migration-assessment-template.md`
- report fixtures in `tests/test_package.py`
- `tests/fixtures/regression/invalid-actual-output.md`

## Scope

### In scope

- Define current evidence enums, readiness enums, containerization enums, and configuration timing values in one machine-readable source.
- Add `schema_version` for JSON output and a clear current Markdown contract version marker only if it does not pollute the user report.
- Restrict current verdicts to `설계 입력 충분`, `추가 정보 필요`, and `분석 불가`.
- Move `준비됨` and `진행 불가` support to an explicit legacy mode or remove it after a repository-wide usage search.
- Keep Summary and Detailed templates separate while sharing the same enum source.
- Improve validation errors with section, component, field, and expected format.

### Out of scope

- Changing the meaning of the three current readiness verdicts.
- Adding Kubernetes manifests or next-action plans.
- Rewriting all Skill references.

## Implementation steps

1. Create `schemas/analysis-result.schema.json` for JSON handoff and `scripts/report_contract.py` for shared constants if needed.
2. Add tests proving current output rejects legacy verdicts by default.
3. Add an explicit `--legacy` compatibility path only when an actual consumer is documented.
4. Align both Markdown templates with validator expectations.
5. Ensure file-line evidence and absence-search evidence continue to work.

## Acceptance criteria

- Current Summary and Detailed fixtures pass.
- A current report containing `준비됨` or `진행 불가` fails.
- Exactly one current readiness verdict is required.
- JSON examples validate against the schema and include `schema_version`.
- Markdown and JSON enum sets cannot drift without a failing test.

## Verification commands

```bash
python3 -m unittest discover -s tests -p 'test_report_contract.py' -v
python3 scripts/validate_report.py tests/fixtures/reports/valid-summary.md --mode summary --repo-root tests/fixtures/repos/sample
python3 scripts/validate_report.py tests/fixtures/reports/valid-detailed.md --mode detailed --repo-root tests/fixtures/repos/sample
python3 scripts/run_quality_gate.py
git diff --check
```

## Expected file changes

- `schemas/analysis-result.schema.json` (new)
- `scripts/report_contract.py` (new, if useful)
- `scripts/validate_report.py`
- `assets/migration-summary-template.md`
- `assets/migration-assessment-template.md`
- `tests/test_report_contract.py` (new)
- `tests/fixtures/reports/` (new)

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `feat: version the current analysis report contract`

## Codex execution instruction

```text
Implement only VS-004. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
