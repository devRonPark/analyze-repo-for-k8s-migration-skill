# Project-Scoped Code Review Graph Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `code-review-graph` enabled for this repository in both Codex and Claude while preventing the user-scoped `cwd` misrouting and PostToolUse failures or blocking delays.

**Architecture:** Codex will use the trusted repository's `.codex/config.toml` to override the global MCP entry with the repository root and a direct CRG executable. The project-local hook runner will drain hook stdin, coalesce concurrent updates with an atomic lock, launch `update --skip-flows` in the background, and return success even when the optional refresh cannot run. Claude will use the same runner through its project settings.

**Tech Stack:** Codex TOML project configuration, Claude JSON hook configuration, Python standard library, `code-review-graph` CLI.

## Global Constraints

- Do not modify or discard unrelated existing user changes.
- Keep the repository read/write behavior unchanged; only `.code-review-graph` is used for CRG data and logs.
- The PostToolUse hook must drain stdin, return exit code `0`, and never block the originating tool on graph refresh.
- Only this trusted project opts into CRG; the user-scoped CRG MCP entry must not force a fixed repository elsewhere.
- Use one Codex hook representation in the project layer; do not create both `.codex/hooks.json` and inline `[hooks]`.

---

### Task 1: Add the tested project-local hook runner

**Files:**
- Create: `.codex/code_review_graph_hook.py`
- Create: `tests/test_code_review_graph_hook.py`

**Interfaces:**
- Consumes: hook JSON on stdin, optional `--worker` mode, `CRG_EXECUTABLE` environment override.
- Produces: immediate process exit `0`; background worker log under `.code-review-graph/hook.log`; at most one active update per repository.

- [ ] **Step 1: Write failing tests** for stdin draining, missing graph fail-open behavior, lock coalescing, and worker failure exit behavior.
- [ ] **Step 2: Run the focused tests and confirm they fail for the missing runner.**
- [ ] **Step 3: Implement the standard-library runner with atomic lock creation, stale-lock cleanup, detached worker launch, timeout, and unconditional success for hook mode.**
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 2: Add Codex project configuration

**Files:**
- Create: `.codex/config.toml`

**Interfaces:**
- Consumes: project root and `.codex/code_review_graph_hook.py`.
- Produces: project-scoped `code-review-graph` MCP server with explicit `cwd`/`--repo` and project `PostToolUse` hook.

- [ ] **Step 1: Define the project MCP server with the direct executable, `PYTHONUTF8=1`, bounded startup/tool timeouts, and repository-root `cwd`/`--repo`.**
- [ ] **Step 2: Define only inline `[[hooks.PostToolUse]]` entries for `Write|Edit|Bash` using the project runner and a short hook timeout.**
- [ ] **Step 3: Parse the TOML and assert the MCP `cwd`, `--repo`, and hook fields.**

### Task 3: Add Claude project hook and MCP configuration

**Files:**
- Modify: `.claude/settings.json`
- Create: `.mcp.json`

**Interfaces:**
- Consumes: the same project-local runner and CRG executable.
- Produces: Claude project-scoped MCP server and valid nested PostToolUse hook schema.

- [ ] **Step 1: Add the nested `matcher` + `hooks` Claude hook entry for `Write|Edit|Bash` with a short timeout.**
- [ ] **Step 2: Add a project `.mcp.json` entry with explicit repository `cwd`, `--repo`, direct executable, and `PYTHONUTF8=1`.**
- [ ] **Step 3: Parse both JSON files and validate the required fields.**

### Task 4: Stop forcing the incorrect global Codex server

**Files:**
- Modify: `%USERPROFILE%/.codex/config.toml` outside the repository.

**Interfaces:**
- Consumes: existing global Codex configuration.
- Produces: global CRG entry disabled so only trusted project config enables it.

- [ ] **Step 1: Preserve a read-only snapshot of the existing global block.**
- [ ] **Step 2: Set only `mcp_servers.code-review-graph.enabled = false` in the user config.**
- [ ] **Step 3: Verify the project config re-enables the server and the user config no longer starts it by default.

### Task 5: Verify end-to-end behavior

**Files:**
- Verify: `.codex/config.toml`, `.codex/code_review_graph_hook.py`, `.claude/settings.json`, `.mcp.json`, user Codex config.

- [ ] **Step 1: Run Python unit tests and JSON/TOML validation.**
- [ ] **Step 2: Invoke the hook with representative PostToolUse payloads and assert exit code `0` and no foreground wait.**
- [ ] **Step 3: Run `code-review-graph status` and inspect hook log/lock behavior without starting a second concurrent updater.**
- [ ] **Step 4: Confirm no CRG process remains tied to `self-learning-agent` and report any verification requiring a full Claude/Codex restart.**
