# Portable Installed MCP Bundle

## Runtime contract

The analysis runtime is a Python 3.13 stdio process. `requirements.lock` is a
committed declaration that the runtime has no third-party dependencies; the
bundle neither installs a package nor contacts a package index. The launcher
captures its inherited working directory once as the trusted command directory
for relative target paths.

The launcher is usable from both source and installed layouts. It emits MCP
responses only on stdout. A successful run emits no stderr diagnostics. It
does not accept a model-provided working directory, target-root override, or
configuration path.

## Bundle and installation contract

The sealed bundle contains the three client templates under `configs/`, the
runtime launcher and Python modules under `runtime/python/`, and the report
schema needed by the in-memory finalizer. `install_bundle()` atomically installs
the runtime below `${OPENCODE_CONFIG_DIR}/analyze-repo-for-kubernetes/` and
creates an OpenCode MCP fragment with an absolute launcher path. The fragment
contains only the local MCP server configuration; it never contains credentials
or an API key value.

The templates use two explicit environment values:

- `ANALYSIS_PIPELINE_PYTHON`: an absolute Python 3.13 executable.
- `ANALYSIS_PIPELINE_LAUNCHER`: the absolute installed `launch_mcp.py` path.

OpenCode uses its local `mcp.analysis` array-command form. Claude Code and
Gemini CLI use their `mcpServers.analysis` command-plus-args form. All three
resolve to the same two-token Python launcher command and omit `cwd`.

## Offline smoke contract

`python scripts/mcp_smoke.py --config-root <path> --all-clients` builds and
validates a fresh bundle, installs it, then executes each template's installed
launcher directly with Python's `-I -S` isolated interpreter flags. Its child
environment preserves only operating-system process essentials, excludes
Python/package/proxy settings, disables package-index access, and installs an
audit/socket guard before the launcher so network operations fail locally. It
uses a temporary external Git fixture and neither installs dependencies nor
invokes a network client. It verifies initialization, the fixed 12-tool catalog
and its repeat byte equality, a start request, a closed business error, five
accepted submissions, final Markdown cleanup, restart after cleanup,
stdout/stderr separation, and unchanged target Git status.
