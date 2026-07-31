# VS-002 — Align Skill metadata and replace phrase-lock package validation

## Outcome

The Skill uses valid OpenCode-compatible metadata and package validation checks structure, links, names, and limits instead of requiring exact prose scattered across Markdown files.

## Why this is a vertical slice

The user-visible capability is reliable Skill discovery after wording changes. The slice covers metadata, validation, and tests end to end without yet rewriting the full Skill body.

## Status and dependencies

- **Status:** Ready after VS-001
- **Depends on:** VS-001
- **Blocks:** VS-003, VS-005, VS-006, VS-007

## Read first

- `SKILL.md` frontmatter
- `scripts/validate_skill.py`
- `tests/test_package.py`
- OpenCode Agent Skills documentation linked in `IMPLEMENTATION_PLAN.md`

## Scope

### In scope

- Rewrite `description` as a specific third-person capability and trigger description.
- Validate `name` against `^[a-z0-9]+(-[a-z0-9]+)*$`, 1–64 characters, and containing directory name.
- Validate `description` length as 1–1024 characters and reject XML tags.
- Parse YAML frontmatter safely without adding a dependency unless already available; a constrained parser is acceptable for recognized fields.
- Remove `Use when ` prefix enforcement and global `REQUIRED_TERMS` phrase scanning.
- Validate exactly one `SKILL.md`, direct relative links, broken paths, UTF-8 Markdown, and unfinished code fences.
- Make required runtime files explicit by role rather than forcing unused `agents/openai.yaml` or `interview-first-intake.md`.

### Out of scope

- Reducing or translating the main Skill instructions.
- Changing report validation rules.
- Deleting legacy files; later tickets decide their disposition.

## Implementation steps

1. Add focused validator tests first for valid metadata, invalid name, directory mismatch, 1,025-character description, XML tag, broken link, and unclosed fence.
2. Change the frontmatter description while preserving Kubernetes migration, Compose, GitOps, monorepo, and no-artifact-generation triggers.
3. Refactor `validate_skill.py` into small functions with actionable error locations.
4. Delete exact phrase assertions from package tests and replace them with structural contract tests.
5. Run the unified quality gate and document any intentionally changed test count.

## Acceptance criteria

- The Skill is discoverable under ID `analyze-repo-for-kubernetes`.
- Equivalent prose rewrites no longer fail package validation.
- Broken direct references and malformed frontmatter still fail.
- The validator does not require `Use when`, `agents/openai.yaml`, or an unreferenced intake file merely because they existed before.
- All existing functional report-validator tests remain green.

## Verification commands

```bash
python3 scripts/validate_skill.py .
python3 -m unittest discover -s tests -p 'test_skill_validator.py' -v
python3 scripts/run_quality_gate.py
git diff --check
```

## Expected file changes

- `SKILL.md` frontmatter
- `scripts/validate_skill.py`
- `tests/test_skill_validator.py` (new)
- `tests/test_package.py`

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `refactor: validate skill structure instead of prose`

## Codex execution instruction

```text
Implement only VS-002. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
