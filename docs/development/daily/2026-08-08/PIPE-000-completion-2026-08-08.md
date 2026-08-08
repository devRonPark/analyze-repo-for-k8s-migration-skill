# PIPE-000 completion: runtime binding compatibility

- Date: 2026-08-08
- Outcome: SUPPORTED
- Provider calls: none

## Commands and evidence

| Command or source | Exit / result | Finding |
| --- | --- | --- |
| `opencode --version` | 0 | Installed OpenCode is `1.18.14`. |
| `opencode --help` | 0 | The public CLI accepts `--session <id>` and exposes `opencode export <sessionID>` and `opencode session delete <sessionID>`. These are caller-supplied session references, not evidence of a non-forgeable tool caller identity. |
| `OPENCODE_CONFIG=runtime/opencode.json OPENCODE_CONFIG_DIR=runtime opencode debug config --pure` | 0 | The resolved configuration contains no plugin, session hook, final-response hook, or `analysis_pipeline` tool. It resolves the current Agent prompt and existing trusted tools only. |
| `runtime/tools/read.ts`, `glob.ts`, `git_metadata.ts` | repository read | Existing custom tools implement `execute(args, context)` and use only `context.worktree`. No repository evidence documents a caller/session identity supplied by the host to custom tools. |
| `runtime/agents/kubernetes-migration-analyzer.md` and `scripts/run_opencode_acceptance.py` | repository read | The Agent is instructed to emit JSON; the Python acceptance adapter extracts the text after the session, renders Markdown, validates it, and writes the receipt. No equivalent interactive-runtime finalizer is present. |
| `runtime/node_modules/@opencode-ai/plugin/package.json` | installed-package read | The plugin package used by this runtime is `@opencode-ai/plugin` `1.18.14`, matching the installed OpenCode version. |
| `runtime/node_modules/@opencode-ai/plugin/dist/tool.d.ts` | installed-package read | `ToolContext` declares `sessionID: string`, separately from model-call `args`; `tool()` invokes `execute(args, context)`. |

The first local diagnostic combined configuration, agent, and broad install-tree
inspection and exceeded its 30-second limit. The two decisive local probes above
were rerun separately and completed. The timeout is not used as capability
evidence.

## Prerequisite conclusions

### Host-issued caller/session identity: SUPPORTED

The installed 1.18.14 plugin declaration delivers `context.sessionID` as part
of `ToolContext`, not as a field of the model-supplied `args` value. Binding
pipeline state only to that context field meets PIPE-000's API requirement:
the tool implementation does not accept a caller/session identifier from the
model, CLI argument, or generated value.

This is a static installed-package compatibility result, not a provider-backed
interactive invocation. PIPE-002 must preserve the boundary by accepting the
identity exclusively from `context.sessionID`; its unit tests must reject any
attempt to provide a session identifier through submitted payload data.

### Final-response receipt binding: not required

The current renderer and receipt finalizer remain post-response acceptance
harness code. ADR-2026-08-08-007 records the user decision that content
integrity is material whereas a direct-TUI presentation-format deviation is
not. Therefore this observation does not block the trusted pipeline.

## Safety result

No configured provider endpoint, external model, target repository, build, or
interactive E2E session was invoked. The evidence came from local CLI help,
resolved configuration, and checked-in runtime source.

## Required next decision

PIPE-000 is complete. PIPE-001 may begin with its deterministic pure state
machine and vertical proof. PIPE-002 may begin only after PIPE-001 passes; it
must use `context.sessionID` exclusively and must not accept a model-provided
or process-global substitute.
