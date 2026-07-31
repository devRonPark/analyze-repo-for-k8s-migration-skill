# VS-007 — Consolidate evidence, dependency, configuration, and readiness rules

## Outcome

Every important conclusion has valid positive or absence evidence, dependencies are directional, conflicts remain visible, and the report ends with exactly one defensible readiness verdict.

## Why this is a vertical slice

This slice spans evidence collection through the final readiness decision and validated report. It produces a complete quality improvement users can observe without requiring OpenCode/OpenShell integration.

## Status and dependencies

- **Status:** Ready after VS-004
- **Depends on:** VS-001, VS-004, preferably VS-006
- **Blocks:** VS-008, VS-011

## Read first

- `SKILL.md` evidence, configuration, dependency, minimum-input, and readiness sections
- `references/evidence-and-readiness.md`
- `references/dependency-analysis.md`
- `references/configuration-timing.md`
- `scripts/validate_report.py`
- both report templates

## Scope

### In scope

- Remove duplicate absence-evidence rules and fix the unclosed Markdown fence.
- Keep four evidence states and three readiness verdicts exactly.
- Keep `file:line` for existing facts and structured `검색(scope=..., pattern=..., result=없음)` for absence.
- Make dependencies directional and separate logical source from actual network caller.
- Keep configuration timing values in one owner file.
- Keep minimum-design-input gaps keyed, evidenced, and scoped by impact.
- Translate internal references to concise English while preserving Korean output enums and templates.

### Out of scope

- Changing component discovery semantics.
- Adding deployment recommendations, priorities, owners, or Kubernetes artifacts.
- Treating every unknown as a blocker.

## Implementation steps

1. Create a rule ownership map for evidence, dependency, timing, minimum inputs, and readiness.
2. Add positive and negative report fixtures for all four evidence states and all three verdicts.
3. Rewrite the three references, then remove duplicated paragraphs from `SKILL.md`.
4. Update validator tests to assert behavior and structured fields rather than source phrases.
5. Validate that Summary and Detailed outputs preserve the same facts.

## Acceptance criteria

- Fabricated file lines fail validation when `--repo-root` is provided.
- Unstructured absence claims fail; structured search evidence passes.
- `추정됨` requires reasoning, `상충됨` preserves both sources, and `미확인` records checked scope and missing information.
- An unknown that does not block design does not automatically force `추가 정보 필요`.
- Exactly one readiness verdict is emitted and its blockers are scoped.

## Verification commands

```bash
python3 -m unittest discover -s tests -p 'test_evidence_readiness_contract.py' -v
python3 scripts/run_quality_gate.py
python3 scripts/validate_skill.py .
git diff --check
```

## Expected file changes

- `SKILL.md`
- `references/evidence-and-readiness.md`
- `references/dependency-analysis.md`
- `references/configuration-timing.md`
- `scripts/validate_report.py`
- `tests/test_evidence_readiness_contract.py` (new)
- report fixtures

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `refactor: unify evidence and readiness contracts`

## Codex execution instruction

```text
Implement only VS-007. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
