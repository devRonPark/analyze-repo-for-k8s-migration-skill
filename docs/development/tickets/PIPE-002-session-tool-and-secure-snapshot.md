# PIPE-002 — Add session-scoped pipeline tool and secure evidence snapshot

## Outcome

Expose the single trusted `analysis_pipeline` tool and bind PIPE-001 state to a
non-forgeable OpenCode caller/session identity, a verified target, and a
deterministic content snapshot. Pipeline state remains outside the target.

## Depends on

- PIPE-000 (`SUPPORTED`)
- PIPE-001

## Read first

- ADR-2026-08-08-004
- `runtime/tools/read.ts`, `runtime/lib/safe-path.ts`, and
  `runtime/lib/locate-evidence.ts`
- `scripts/run_opencode_acceptance.py`'s tool-copy and isolated-install paths

## In scope

- `start`, `submit`, `reopen`, and `finalize` dispatch that delegates all
  validation to PIPE-001.
- Runtime-private state lifecycle and cleanup.
- Safe file-handle access; deterministic target Merkle hashing; per-evidence
  hash checks; final snapshot revalidation.
- Rejection of symlinks/junctions/reparse points, target escape, state reuse,
  evidence forgery, and secret-bearing state or trace content.
- Explicit runtime permission and isolated-adapter packaging changes.

## Out of scope

- Stage instructions, Agent migration, public renderer implementation, and
  provider-backed correctness scenarios.

## Acceptance criteria

- Tests show state cannot be reused across sessions, targets, snapshots, or
  manifest versions.
- All target access is handle-verified and target changes fail finalization.
- State cleanup leaves no raw target content or secret literal on disk.

## Commit boundary

Commit the binding, secure runtime support, packaging changes, and focused
tests together.
