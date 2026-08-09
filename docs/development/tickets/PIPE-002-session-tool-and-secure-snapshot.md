# PIPE-002 — Add Python MCP pipeline tool and secure evidence snapshot

## Static MCP Stage Skills amendment

This ticket is superseded by Ticket 2 of Static MCP Stage Skills. A stdio
Python server exposes a fixed twelve-tool catalog from its first tools/list
response, binds target_path relative to process-start command_directory, and
uses one active analysis per fresh server process. It has no dynamic catalog
refresh, host session identity, SDK dependency, or replay receipt.

## Outcome

Expose the explicit trusted analysis stage tools through a Python MCP stdio
server and bind PIPE-001 state to a verified target, deterministic content
snapshot, and one-process/one-analysis lifecycle boundary. Pipeline state
remains outside the target.

## Depends on

- PIPE-000 static API compatibility
- PIPE-001

## Read first

- ADR-2026-08-08-004
- the approved Python MCP design
- `scripts/run_opencode_acceptance.py`'s tool-copy and isolated-install paths

## In scope

- `start_analysis`, stage-specific `submit_*` tools, `reopen_analysis`, and
  `finalize_analysis` dispatch that delegates all
  validation to PIPE-001.
- Runtime-private state lifecycle and cleanup.
- Python MCP stdio server implementation, `initialize` handshake coverage, and
  stderr-only diagnostics. The delivered transport is a local stdio MCP server.
- A provider-free lifecycle gate: prove that each supported client launches a
  fresh server process per interactive analysis session, that one process
  accepts one active analysis only, rejects a second `start`, clears state on
  `finalize`, and leaves no state visible from a different server process.
- Safe file-handle access; deterministic target Merkle hashing; per-evidence
  hash checks; final snapshot revalidation.
- Rejection of symlinks/junctions/reparse points, target escape, state reuse,
  evidence forgery, and secret-bearing state or trace content.
- Pinned Python MCP dependency, lock/hashes, wheelhouse provenance, and an
  offline-reproducible clean-venv install path for supported clients.
- Minimal configuration templates and smoke tests for OpenCode, Claude Code,
  and Gemini CLI.

## Out of scope

- Stage instructions, Agent migration, public renderer implementation, and
  provider-backed correctness scenarios.

## Acceptance criteria

- Tests show state cannot be reused across processes, targets, snapshots, or
  manifest versions.
- The lifecycle gate proves actual process separation and cleanup for OpenCode,
  Claude Code, and Gemini CLI; no model-supplied substitute identifier is
  accepted.
- All target access is handle-verified and target changes fail finalization.
- State cleanup leaves no raw target content or secret literal on disk.
- Offline package installation, MCP launch, `initialize`, tool schema, and
  stderr-only diagnostics pass in provider-free smoke tests.

## Commit boundary

Commit the Python MCP server, secure runtime support, packaging changes, and
focused tests together.
