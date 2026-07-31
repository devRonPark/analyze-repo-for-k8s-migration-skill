# VS-003 — Build a minimal OpenCode runtime distribution and installer

## Outcome

A validated allowlist package can be installed to an OpenCode Skill directory without README, CI, tests, legacy installers, or unrelated platform configuration.

## Why this is a vertical slice

It delivers a working distribution path: source repository → deterministic `dist/` → temporary OpenCode home → discoverable Skill files, with tests for every boundary.

## Status and dependencies

- **Status:** Ready after VS-002
- **Depends on:** VS-001, VS-002
- **Blocks:** VS-009, VS-010, VS-013

## Read first

- `SKILL.md` direct links
- `scripts/install-codex.sh`
- `scripts/install-qwen.sh`
- `tests/test_repository_distribution.py`
- OpenCode Skill locations in official docs

## Scope

### In scope

- Create an allowlist-driven build script for `dist/analyze-repo-for-kubernetes/`.
- Include only `SKILL.md`, referenced `references/`, referenced `assets/`, runtime-called scripts, and later schemas.
- Generate a manifest containing Skill version/source revision and checksums.
- Add `scripts/install-opencode.sh` with global default `~/.config/opencode/skills/analyze-repo-for-kubernetes/` and optional project-local destination.
- Install by copying the built distribution, not by symlinking the whole source checkout.
- Detect duplicate installations in other OpenCode-compatible locations and fail with the conflicting paths unless an explicit override flag is used.

### Out of scope

- OpenCode process execution or model invocation.
- OpenShell sandbox policy.
- Deleting Qwen/Codex installers before usage is confirmed.

## Implementation steps

1. Define the runtime allowlist in one source-controlled file or constant.
2. Build into a temporary directory, validate all relative links there, then atomically replace `dist/`.
3. Write installer tests with a temporary `HOME` and a project-local directory.
4. Assert excluded files are absent: `README.md`, `CHANGELOG.md`, `.github/`, `tests/`, Qwen/Codex installers, and `agents/openai.yaml`.
5. Update distribution tests to treat OpenCode as the primary installation target.

## Acceptance criteria

- Two consecutive builds produce identical file content and manifest checksums for the same revision.
- The installed directory passes `validate_skill.py`.
- Every `SKILL.md` relative link resolves inside the distribution.
- Source checkout changes are not exposed through a symlink.
- Duplicate Skill IDs are reported before installation.

## Verification commands

```bash
python3 scripts/build_dist.py
python3 scripts/validate_skill.py dist/analyze-repo-for-kubernetes
HOME="$(mktemp -d)" bash scripts/install-opencode.sh
python3 -m unittest discover -s tests -p 'test_repository_distribution.py' -v
git diff --check
```

## Expected file changes

- `scripts/build_dist.py` (new)
- `scripts/install-opencode.sh` (new)
- `runtime-files.txt` or equivalent (new)
- `tests/test_repository_distribution.py`
- `dist/` generated locally; do not commit unless repository policy explicitly requires it

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `feat: add minimal OpenCode skill distribution`

## Codex execution instruction

```text
Implement only VS-003. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
