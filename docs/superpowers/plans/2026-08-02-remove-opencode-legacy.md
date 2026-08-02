# Remove OpenCode Legacy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove OpenCode Skill packaging and acceptance legacy from the isolated branch so only the current Kubernetes Migration Assistant ADK path remains.

**Architecture:** Keep `migration_assistant/` as the product package and keep only the ADK live harness in `devtools/`. Rewrite root guidance and CI to execute the Python ADK tests directly, then remove the old Skill/runtime/distribution/report-contract surface and its fixtures.

**Tech Stack:** Python 3.11+, Google ADK, Pydantic 2, unittest, GitHub Actions, PowerShell/Git worktree on Windows.

## Global Constraints

- The analyzed Repository remains read-only and generated artifacts stay outside it.
- The public ADK Agent Tool surface remains exactly eight tools.
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, and `LLM_MAX_TOKENS` remain the only model configuration variables.
- Current user changes in the original worktree are not reverted, staged, or overwritten.
- All subprocesses in retained Python tests/tools use `sys.executable`, never `python` or `python3` by PATH lookup.
- Windows verification starts Python with workspace-safe temp variables and UTF-8 output settings; Codex sandbox ACL failures are reported separately from product failures.

## File Map

### Keep

- `migration_assistant/` — active ADK package and deterministic guardrails
- `devtools/run_phase1_live_acceptance.py`, `devtools/env_file.py` — active live harness and development env loader
- Active ADK tests: `test_adk_agent.py`, `test_analysis_vertical_slice.py`, `test_cli_contract.py`, `test_exploration_loop.py`, `test_live_planner.py`, `test_migration_assistant_foundation.py`, `test_model_compatibility.py`, `test_phase1_adk_contract.py`, `test_phase1_live_acceptance_harness.py`, `test_repository_tools.py`, `test_target_safety.py`, `test_env_file_loader.py`
- `docs/phase1-adk-experiment-log.md`, `docs/agent-tool-design-best-practices.md`, and current 2026-08-02 ADK planning documents
- `pyproject.toml`, `uv.lock`, `.github/workflows/test.yml`, `.github/pull_request_template.md`, `LICENSE`

### Rewrite

- `README.md` — ADK product purpose, setup, CLI/live verification, and safety boundary
- `AGENTS.md`, `CONTEXT.md`, `CLAUDE.md` — current ADK architecture and collaboration rules without historical OpenCode migration instructions
- `CHANGELOG.md` — ADK migration history
- `.github/workflows/test.yml` — direct Python test command with `sys.executable`-compatible runner behavior

### Delete

- `SKILL.md`, `agents/`, `runtime/`, `runtime-files.txt`
- `assets/`, `contracts/`, `references/`, and all `scripts/`
- OpenCode/Skill-only tests: `test_context_measurement.py`, `test_discovery_contract.py`, `test_evidence_readiness_contract.py`, `test_opencode_adapter.py`, `test_package.py`, `test_project_metadata.py`, `test_quality_gate.py`, `test_report_contract.py`, `test_repository_distribution.py`, `test_scenario_evaluator.py`, `test_skill_validator.py`, `test_summary_quality.py`, `test_summary_renderer.py`, `test_target_and_safety_contract.py`, `test_validate_target_report.py`
- Old Skill fixtures and evaluations: `tests/evaluation/`, `tests/fixtures/discovery/`, `tests/fixtures/full-stack-fastapi-template-summary/`, `tests/fixtures/regression/`, `tests/fixtures/reports/`, `tests/fixtures/repos/`, `tests/golden/`, `tests/scenarios.md`
- Historical OpenCode material: `docs/development/`, `memory/`, `_review/`, `docs/baseline.md`, `docs/superpowers/specs/2026-07-30-det-001-evidence-slot-completion-design.md`

### Task 1: Rewrite current product guidance and CI

**Files:**
- Modify: `README.md`, `AGENTS.md`, `CONTEXT.md`, `CLAUDE.md`, `CHANGELOG.md`, `.github/workflows/test.yml`
- Create: `.github/pull_request_template.md`

- [x] Replace OpenCode installation and Skill instructions with the current Local Repository → ADK Runner → Migration Plan → manifest validation flow.
- [x] Remove historical legacy sections from `AGENTS.md`, `CONTEXT.md`, and `CLAUDE.md` while preserving safety, evidence, Korean UX, provider-neutral adapter, and worktree rules.
- [x] Change CI name and command from the legacy quality gate to the retained Python test suite; use the configured interpreter rather than a PATH `python3` assumption.
- [x] Add the requested PR template with What/Why/How to test/Risk-Rollback and the AI-agent changed-area checkbox.
- [x] Search the rewritten files for legacy runtime and installer paths before deleting those paths.

### Task 2: Delete legacy runtime and packaging surface

**Files:**
- Delete: `SKILL.md`, `agents/`, `runtime/`, `runtime-files.txt`, `assets/`, `contracts/`, `references/`, `scripts/`

- [x] Verify each path exists in the isolated worktree and is not imported by `migration_assistant/` or retained `devtools/` files.
- [x] Delete only the listed paths with Git-aware deletion in this isolated worktree.
- [x] Confirm no retained Python import or workflow command references a deleted path.

### Task 3: Delete legacy tests, fixtures, and historical artifacts

**Files:**
- Delete: the listed Skill-only test modules and all listed legacy fixture/evaluation/history directories/files.

- [x] Verify retained tests do not import `scripts`, `report_contract`, `runtime`, `agents`, or root Skill files.
- [x] Delete the legacy tests and fixtures.
- [x] Confirm the retained test inventory contains only ADK package, repository-tool, target-safety, live-harness, and env-loader coverage.

### Task 4: Verify Python executable and ADK-only boundaries

**Files:**
- Inspect: retained `migration_assistant/`, `devtools/`, tests, CI, and tracked documentation

- [x] Run `rg -n 'python3|\["python"|\["python3"'` over retained Python tests/tools and fix any remaining executable lookup.
- [x] Run `rg -n -i 'opencode|qwen|skill distribution|install-opencode|run_opencode|validate_skill|report_contract'` over tracked files and classify every remaining match as an intentional plan-history reference; no implementation match remains.
- [x] Run the retained ADK tests with the existing `.venv` interpreter from the isolated worktree; set `TEMP`, `TMP`, `TMPDIR`, and `PYTHONIOENCODING` before Python starts.
- [x] Tighten `TargetSafetyGate` to reject a nested directory of another Git repository and make the Windows subprocess decode explicit UTF-8.
- [x] Run `git diff --check`, inspect `git status --short`, and report any test blocked by the Codex Windows sandbox separately from code failures.

### Task 5: Review and handoff

- [x] Summarize exact deleted paths, rewritten files, retained ADK tests, and verification results.
- [x] Do not modify or commit the original worktree's user changes.
- [x] If a focused commit is requested or approved, stage only this isolated branch's cleanup changes.
