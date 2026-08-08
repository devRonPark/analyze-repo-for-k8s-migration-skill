# PIPE-000 — Verify runtime binding and final-response compatibility

## Outcome

Determine, without invoking a model provider or changing a target repository,
whether the installed OpenCode plugin/tool API can expose both prerequisites of
ADR-2026-08-08-004:

1. a runtime-issued caller/session identity that a model cannot supply or
   choose; and
2. a final-response path that can bind an accepted result to the exact
   `analysis_pipeline.finalize()` receipt and content hash.

The outcome is `SUPPORTED` or `BLOCKED`; this ticket does not implement an
alternative architecture.

## Depends on

None.

## Read first

- ADR-2026-08-08-004 and ADR-2026-08-08-005
- `memory/opencode-e2e.md`
- `runtime/opencode.json`
- the installed OpenCode plugin/tool API documentation and local `opencode`
  help output

## In scope

- Inspect local OpenCode version, command help, agent-debug output, and the
  installed plugin/tool API without calling a configured provider.
- Record the exact capability evidence, API surface, and limitation in a
  completion record under `docs/development/daily/2026-08-08/`.
- State the next action precisely:
  - `SUPPORTED`: PIPE-002 may bind state to the documented runtime identity
    and receipt path.
  - `BLOCKED`: PIPE-002 must not start; write a follow-up ADR describing the
    required host hook or plugin API instead of accepting a model-supplied ID.

## Out of scope

- Provider-backed OpenCode sessions, target analysis, an `analysis_pipeline`
  implementation, schema changes, or permission changes.
- Emulating caller identity with a CLI argument, model field, generated UUID,
  or process-global value.

## Acceptance criteria

- The completion record identifies the OpenCode version and the inspected API
  surface with repository or installed-package evidence.
- It gives a single `SUPPORTED` or `BLOCKED` conclusion for each prerequisite.
- It demonstrates that the conclusion does not depend on a model-provided
  identifier or a provider request.
- The checked-out target is unchanged and no external model provider is called.

## Verification commands

Run only local, read-only discovery commands. Do not use a configured provider
endpoint or an interactive E2E session. Record each executed command and its
exit status in the completion record.

## Commit boundary

Commit this ticket, its completion record, and any focused static test only if
an executable contract was added. Do not bundle PIPE-001 implementation.
