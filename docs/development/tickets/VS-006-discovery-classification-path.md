# VS-006 — Consolidate repository discovery and component classification

## Outcome

The Skill consistently distinguishes executable candidates, repository-defined runtime dependencies, external dependencies, and excluded items across monorepos and Dockerfile-free repositories without repeated language rules.

## Why this is a vertical slice

It covers inventory through component classification and command discovery, including dedicated tests for Node.js and Java conflict cases. The result is directly visible in the component list a user receives.

## Status and dependencies

- **Status:** Ready after VS-002
- **Depends on:** VS-001, VS-002
- **Blocks:** VS-008, VS-012

## Read first

- `SKILL.md` Discovery Classification and analysis-result sections
- `references/repository-analysis-checklist.md`
- `references/language-discovery-rules.md`
- `references/workflow.md` inventory steps
- related string-lock tests in `tests/test_package.py`

## Scope

### In scope

- Make `workflow.md` the owner of inventory phases and classification flow.
- Make `repository-analysis-checklist.md` the owner of required component fields and completion questions.
- Make `language-discovery-rules.md` contain only language-specific file signals, precedence, and exceptions.
- Define build, image build, and production startup once.
- Consolidate Node.js precedence: `packageManager`, workspace ownership, nearest component manifest, matching lockfile, conflict preservation.
- Consolidate Java/Kotlin wrapper and Maven/Gradle coexistence rules.
- Keep missing Dockerfile as a finding, not failure.
- Translate internal rules to concise English.

### Out of scope

- Final evidence-status and readiness logic.
- Adding a repository inventory helper before the benchmark in VS-012.
- Executing build, test, server, migration, or container commands.

## Implementation steps

1. Create small static repository fixtures for a Dockerfile-free Node monorepo, nested package manager conflict, Maven/Gradle coexistence, shared library, migration utility, and external SaaS reference.
2. Write expected classification and command-discovery assertions independent of exact prose.
3. Build a before/after rule ownership map and remove duplicated definitions.
4. Rewrite the three reference files with one instruction per sentence.
5. Confirm all excluded items require reason and evidence.

## Acceptance criteria

- Each discovered item has exactly one classification.
- Package manifests alone do not create deployable candidates.
- Build, image build, and production startup remain distinct.
- Node and Java conflicts remain `상충됨` or `미확인` rather than being forced into one command.
- Dockerfile-free candidates are still analyzed.
- No language rule is defined in more than one owner file.

## Verification commands

```bash
python3 -m unittest discover -s tests -p 'test_discovery_contract.py' -v
python3 scripts/validate_skill.py .
python3 scripts/run_quality_gate.py
git diff --check
```

## Expected file changes

- `SKILL.md`
- `references/workflow.md`
- `references/repository-analysis-checklist.md`
- `references/language-discovery-rules.md`
- `tests/test_discovery_contract.py` (new)
- `tests/fixtures/repos/` additions

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `refactor: consolidate discovery and classification rules`

## Codex execution instruction

```text
Implement only VS-006. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
