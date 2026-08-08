# PIPE-000 completion: runtime binding compatibility

- Date: 2026-08-08
- Outcome: BLOCKED
- Provider calls: none

## Commands and evidence

| Command or source | Exit / result | Finding |
| --- | --- | --- |
| `opencode --version` | 0 | Installed OpenCode is `1.18.14`. |
| `opencode --help` | 0 | The public CLI accepts `--session <id>` and exposes `opencode export <sessionID>` and `opencode session delete <sessionID>`. These are caller-supplied session references, not evidence of a non-forgeable tool caller identity. |
| `OPENCODE_CONFIG=runtime/opencode.json OPENCODE_CONFIG_DIR=runtime opencode debug config --pure` | 0 | The resolved configuration contains no plugin, session hook, final-response hook, or `analysis_pipeline` tool. It resolves the current Agent prompt and existing trusted tools only. |
| `runtime/tools/read.ts`, `glob.ts`, `git_metadata.ts` | repository read | Existing custom tools implement `execute(args, context)` and use only `context.worktree`. No repository evidence documents a caller/session identity supplied by the host to custom tools. |
| `runtime/agents/kubernetes-migration-analyzer.md` and `scripts/run_opencode_acceptance.py` | repository read | The Agent is instructed to emit JSON; the Python acceptance adapter extracts the text after the session, renders Markdown, validates it, and writes the receipt. No equivalent interactive-runtime finalizer is present. |

The first local diagnostic combined configuration, agent, and broad install-tree
inspection and exceeded its 30-second limit. The two decisive local probes above
were rerun separately and completed. The timeout is not used as capability
evidence.

## Prerequisite conclusions

### Non-forgeable caller/session identity: BLOCKED

There is no confirmed local API by which a custom tool receives a host-issued,
caller-bound identity. The observed public session values are CLI arguments or
output events; accepting either as a tool binding would let a model or caller
select the identifier. Absence of a documented local API is a security blocker,
not permission to generate a UUID or accept a submitted `session_id`.

### Final-response receipt binding: BLOCKED

The only observed renderer and receipt finalizer run in the Python acceptance
adapter after OpenCode returns. The resolved interactive configuration has no
runtime output hook that can require the final assistant response to equal a
`finalize()` receipt and content hash. Prompt text is therefore not a
mechanical final-response binding.

## Safety result

No configured provider endpoint, external model, target repository, build, or
interactive E2E session was invoked. The evidence came from local CLI help,
resolved configuration, and checked-in runtime source.

## Required next decision

PIPE-001 and PIPE-002 must not start under the current ticket dependencies.
ADR-2026-08-08-006 records the required host capability: an OpenCode-supported
extension point that supplies a non-forgeable caller identity and owns the
final-response boundary. Until that capability is selected and verified, no
model-provided or process-global substitute is allowed.
