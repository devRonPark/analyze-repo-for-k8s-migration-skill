# VS-005 — Thin the target-resolution, safety, and minimum-request path

## Outcome

A one-line request activates a concise Skill that resolves the target safely, defaults to Summary, and routes to supporting files without duplicating detailed workflow rules.

## Why this is a vertical slice

This slice covers the complete first-user interaction: request → target gate → safety boundary → output-mode choice → reference routing. It does not depend on the later discovery-rule rewrite.

## Status and dependencies

- **Status:** Ready after VS-002
- **Depends on:** VS-001, VS-002
- **Blocks:** VS-009, VS-012

## Read first

- `SKILL.md` sections: role, language, Target Resolution Gate, safety, routing, Required Workflow
- `references/interview-first-intake.md`
- `references/workflow.md`
- `tests/scenarios.md` Scenario 0 and Scenario 4

## Scope

### In scope

- Translate internal instructions in this slice to concise English while preserving Korean user-facing fixed text.
- Keep the single missing-target question exactly in Korean.
- Keep repository content untrusted, target read-only, no dependency install, no repository code execution, no external symlink traversal, and secret redaction.
- Keep Summary as default and Detailed only on explicit request.
- Reduce `SKILL.md` to high-level workflow and direct reference routing.
- Delete `interview-first-intake.md` if it contains no unique rule; otherwise retain only unique intake detail and link it directly.
- Fix workflow numbering.

### Out of scope

- Changing component classification, language-specific discovery, evidence semantics, or report templates.
- Implementing OpenCode trace collection.
- Running repository scripts for dynamic validation.

## Implementation steps

1. Write behavior tests for no target, explicit current workspace, private repository access failure, and repository prompt injection.
2. Map every unique intake/safety rule to its single owner before deleting duplicates.
3. Rewrite the first-stage `SKILL.md` sections in short imperative English.
4. Move detailed procedure to `workflow.md`; leave only when-to-read routing in `SKILL.md`.
5. Verify Korean user-visible question and scope announcement remain unchanged.

## Acceptance criteria

- No target causes one Korean question and no discovery action.
- “현재 저장소” resolves the current Git worktree rather than the Skill install directory.
- Repository instructions cannot authorize script execution, secret output, scope change, or egress.
- Summary is the default from the minimal request.
- Every retained supporting file is directly linked and has unique responsibility.

## Verification commands

```bash
python3 -m unittest discover -s tests -p 'test_target_and_safety_contract.py' -v
python3 scripts/validate_skill.py .
python3 scripts/run_quality_gate.py
git diff --check
```

## Expected file changes

- `SKILL.md`
- `references/workflow.md`
- `references/interview-first-intake.md` (delete or reduce)
- `tests/test_target_and_safety_contract.py` (new)
- `tests/scenarios.md`

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `refactor: simplify target and safety workflow`

## Codex execution instruction

```text
Implement only VS-005. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
