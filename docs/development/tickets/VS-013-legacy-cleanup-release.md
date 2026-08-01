# VS-013 — Remove obsolete platform assets and cut a verified release

> **Status: Superseded**
>
> **Superseded by: Google ADK migration MVP**
>
> This ticket's OpenCode release objective is not current execution authority.
> `scripts/run_opencode_acceptance.py` and `scripts/build_dist.py` are legacy
> validation material, not completion gates for the new ADK path. Preserve this
> document as historical context; do not execute its release scope for the ADK
> MVP.

## Outcome

The repository clearly supports OpenCode on OpenShell, contains no unowned legacy platform files in the runtime path, and publishes a release with measured behavior, security, and context results.

## Why this is a vertical slice

It completes the product transition from source tree to documented, installable, tested runtime package. Cleanup is performed only after usage and compatibility evidence exists.

## Status and dependencies

- **Status:** Final slice
- **Depends on:** VS-003, VS-011, VS-012
- **Blocks:** None

## Read first

- all completed ticket reports
- `README.md`
- `CHANGELOG.md`
- legacy installers and `agents/openai.yaml`
- distribution manifest and E2E report

## Scope

### In scope

- Search repository history, CI, docs, and known deployment environments for usage of Qwen/Codex installers and `agents/openai.yaml`.
- Delete unused files or move genuinely supported compatibility files to `legacy/` outside the runtime allowlist with an explicit owner and deprecation note.
- Rewrite README for OpenCode installation, OpenShell runtime, one-line request, validation, and troubleshooting.
- Update CHANGELOG with factual before/after behavior and measured context values.
- Generate and validate the final distribution, checksums, and release notes.
- Run the complete local and environment-dependent acceptance suites; mark unresolved external blockers explicitly.

### Out of scope

- Deleting a compatibility path with an identified active consumer.
- Publishing exact context savings that were not measured.
- Calling the release production-ready while required E2E cases are BLOCKED.

## Implementation steps

1. Create a legacy-usage evidence table and disposition decision for each file.
2. Remove legacy requirements from tests and package validator.
3. Update README and CHANGELOG in English; preserve Korean report examples and user-visible fixed messages.
4. Build a clean checkout distribution and install it into a temporary OpenCode home.
5. Run all quality, OpenCode, OpenShell, E2E, and context checks.
6. Prepare a release checklist and tag recommendation; do not push or tag unless explicitly requested.

## Acceptance criteria

- Runtime distribution contains only allowlisted files.
- README describes OpenCode as UI/agent client and OpenShell as runtime/security boundary.
- No test requires obsolete Qwen/Codex files.
- Release report separates verified facts, evidence-backed inference, and unresolved environment blockers.
- All required gates pass, or the release is explicitly marked blocked.

## Verification commands

```bash
python3 scripts/run_quality_gate.py
python3 scripts/build_dist.py
python3 scripts/validate_skill.py dist/analyze-repo-for-kubernetes
python3 scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --output-dir .artifacts/release-opencode
python3 scripts/run_e2e.py --cases tests/evaluation/e2e-cases.json --artifacts .artifacts/release-e2e
git diff --check
git status --short
```

## Expected file changes

- `README.md`
- `CHANGELOG.md`
- legacy files removed or moved with evidence
- tests and distribution allowlist
- `docs/release-readiness.md` (new)
- final generated distribution artifacts

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `chore: prepare OpenCode OpenShell skill release`

## Codex execution instruction

```text
Implement only VS-013. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
