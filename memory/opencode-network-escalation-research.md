# OpenCode Local Endpoint and Sandboxed Execution Research

Research date: 2026-07-29

## Question

What is the usual resolution when a local OpenAI-compatible model responds to
`curl` from a user's terminal but an OpenCode run does not start, hangs, or
cannot reach the endpoint from a sandboxed execution environment?

## Executive finding

The failure must be separated into two layers:

1. The execution wrapper or sandbox may prevent the command from starting or
   may isolate its network namespace. This is the current observation: the
   restricted `curl` returned exit 7, while the latest `require_escalated`
   request returned no command output and never reached `opencode run`.
2. If OpenCode starts and reaches the provider, OpenCode-specific custom
   provider or streaming/tool-calling bugs become plausible. OpenCode issue
   [#12893](https://github.com/anomalyco/opencode/issues/12893) reports the
   closest application-level symptom: direct `/v1/models` and
   `/v1/chat/completions` calls worked, but `opencode run` and the TUI hung with
   no provider HTTP logs.

The practical first fix is therefore to run the exact reproduction from a host
terminal or from an execution context where the elevated command actually
starts. Changing `opencode.json` cannot grant network access to an outer
Codex-managed sandbox.

## Primary-source findings

### 1. Direct `curl` success does not prove OpenCode can complete a run

OpenCode issue [#12893](https://github.com/anomalyco/opencode/issues/12893)
records a healthy OpenAI-compatible endpoint, successful direct calls, visible
models, and an OpenCode CLI/TUI hang with no provider HTTP request logs. The
reported configuration used `@ai-sdk/openai-compatible` and a remote `baseURL`.
The issue page is marked closed, but it does not document a confirmed fix or a
maintainer resolution. It should be treated as a matching symptom report, not
as evidence that the current environment has the same root cause.

### 2. Verify provider identity, package, endpoint, and model ID

The official [OpenCode provider documentation](https://dev.opencode.ai/docs/providers/)
recommends checking all of the following for custom providers:

- the provider ID used during `/connect` matches the ID in `opencode.json`;
- `@ai-sdk/openai-compatible` is used for `/v1/chat/completions` APIs;
- `options.baseURL` is the correct API endpoint; and
- the configured model ID matches the provider's model ID.

The same documentation recommends using `/v1/models` to identify available
model IDs and checking `opencode auth list` for credential setup.

### 3. Use OpenCode's debug logs to distinguish startup from provider failure

The official [OpenCode troubleshooting guide](https://dev.opencode.ai/docs/troubleshooting/)
recommends `--log-level DEBUG` and identifies the Linux/macOS log directory as
`~/.local/share/opencode/log/`. A reproduction that has no provider request in
the debug log is different from one that records a provider HTTP error or an
empty response.

### 4. OpenCode permissions are not the same as the outer sandbox policy

The official [OpenCode permissions documentation](https://opencode.ai/v2/docs/permissions)
says its `shell` action uses the host user's filesystem, process, and network
authority, while `external_directory` is a separate path decision. This
describes OpenCode's own permission model; it does not grant a command access
through a parent Codex sandbox that has already isolated or denied networking.
This distinction explains why changing the OpenCode agent permission file alone
cannot repair the observed outer-network failure.

### 5. Older custom-provider configuration bugs are a separate branch

OpenCode issue [#5674](https://github.com/anomalyco/opencode/issues/5674)
describes an older case where `options.baseURL` and other options were not
forwarded, producing `NotFoundError` and logs with an empty `options` object.
That issue is marked closed as not planned. It is relevant only if OpenCode
actually starts, emits a request, and the logs show incorrect provider options;
it does not explain a command that never starts or produces no OpenCode output.

## Recommended diagnostic sequence

1. From the same host/network context that can reach the model, verify
   `/v1/models` and a minimal non-streaming `/v1/chat/completions` request using
   the exact configured model ID.
2. Run OpenCode with the exact config and model, first with a minimal prompt and
   `--print-logs --log-level DEBUG`; use `--agent none` when isolating provider
   startup from the analysis agent.
3. Confirm the OpenCode process actually starts. If the wrapper returns no
   stdout/stderr and no OpenCode log, investigate command approval, sandbox
   network namespace, or host/network execution before changing provider config.
4. If OpenCode starts but no provider HTTP request appears, compare the case to
   [#12893](https://github.com/anomalyco/opencode/issues/12893) and capture the
   OpenCode version, resolved config path, selected model, and debug log.
5. If a request appears, follow the concrete error: provider ID/model ID,
   `baseURL`, authentication, response schema, streaming, or tool-calling
   compatibility.

## Applicability to the current run

- `runtime/opencode.json` already selects `@ai-sdk/openai-compatible`, the
  configured `baseURL`, and `Qwen/Qwen3.6-35B-A3B-FP8`.
- The restricted sandbox produced `curl` exit 7 before an HTTP response.
- The latest elevated command produced no result before termination, so there
  is no evidence that `curl` or `opencode run` started in that attempt.
- Therefore the current failure is not yet attributable to OpenCode issue
  #12893 or #5674. The next meaningful test must run from the user's working
  host terminal or from an elevated execution channel that demonstrably starts
  the command, then collect OpenCode DEBUG logs.

## Local evidence

The repository's runbook records the known-good temporary distribution layout,
separate `HOME` and `OPENCODE_CONFIG_DIR`, and the historical successful
`jpetstore-6` timings in [memory/opencode-e2e.md](opencode-e2e.md).
