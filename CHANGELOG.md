# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added

- Google ADK repository analysis agent with a fixed eight-tool public surface:
  `inspect_target`, `list_tree`, `find_files`, `search_text`, `read_file`,
  `read_file_lines`, `inspect_git_metadata`, `validate_analysis`.
- Read-only target boundary: path escape and symlink blocking, file size and
  iteration budgets, and secret redaction across tool results and artifacts.
- Provider-neutral OpenAI-compatible adapter configured only through
  `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, and
  `LLM_MAX_TOKENS`.
- Typed tool protocol with stable error envelopes, dispatch validation before
  ADK dispatch, and bounded typed recovery.
- Evidence-grounded `AnalysisResult`: `complete` and `partial` both require
  positive line-backed evidence, and only an accepted `validate_analysis` call
  can complete an analysis.
- Korean `analyze` CLI writing `analysis-result.json` and `analysis-report.md`
  to a separate output directory.
- Development-only live acceptance harness in `devtools/` with a 3-of-3 gate and
  a `KEY=VALUE` env file loader.

### Removed

- The OpenCode Agent Skill package: `SKILL.md`, `runtime/`, `agents/`,
  `assets/`, `contracts/`, `references/`, `schemas/`, and `runtime-files.txt`.
- OpenCode, Qwen, and Codex install, update, and distribution scripts, the
  legacy report/skill validators, the scenario evaluator, the quality gate, and
  the OpenCode acceptance harness under `scripts/`.
- Legacy report-contract, packaging, distribution, scenario, and summary tests
  with their fixtures, golden files, and evaluation data.
- Legacy development documents under `docs/development/`, OpenCode and Qwen
  research notes, and stale review artifacts.

### Changed

- CI runs the Python test suite instead of the legacy quality gate.
- README, `AGENTS.md`, `CONTEXT.md`, and `CLAUDE.md` describe the ADK product
  boundary only.

## 0.1.0 - 2026-07-23

Initial OpenCode Agent Skill release. Superseded by the ADK product above; the
skill packaging described in this release no longer exists in the repository.
