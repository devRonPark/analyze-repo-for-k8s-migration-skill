# Python MCP Analysis Pipeline Design

## Status

Approved for planning on 2026-08-08. This design supersedes the TypeScript
implementation choice in PIPE-001 and later PIPE tickets. It does not change
the public `/analyze-repo-for-kubernetes` command.

Before implementation, a new ADR must supersede ADR-2026-08-08-004's runtime
integration decision and PIPE-001 through PIPE-006 must be revised. The
historical ADR remains unchanged; its current TypeScript, OpenCode custom-tool,
and `context.sessionID` requirements are incompatible with this design.

## Goal

Implement the trusted analysis pipeline and every current trusted-analysis
tool as Python MCP servers so one language owns pipeline state, validation,
evidence handling, rendering, and MCP exposure. The server must be usable by
OpenCode, Claude Code, and Gemini CLI through the standard local stdio MCP
transport.

## Non-goals

- No TypeScript or JavaScript source, bridge, plugin, custom-tool wrapper, or
  runtime dependency in the delivered analysis path.
- No OpenCode-specific custom-tool API or `context.sessionID` dependency.
- No provider-backed run, target mutation, or public-command migration in
  PIPE-001.
- No long-lived network listener; the server uses stdio only.

## Architecture

The runtime package is a Python package under `runtime/python/`:

```text
runtime/python/
  analysis_pipeline/
    state.py          # immutable state values and deterministic identifiers
    validation.py     # closed schemas and invariant checks
    transitions.py    # start, submit, reopen, finalize state transitions
    mcp_server.py     # stdio MCP process and tool registrations
    protocol.py       # JSON/MCP request and response boundary
  tests/
    test_state.py
    test_transitions.py
```

`state.py`, `validation.py`, and `transitions.py` are pure and provider-free.
They accept explicit state and bindings, return a new state or a typed
validation failure, and never read files, spawn processes, access the network,
or retain module-global session state.

`mcp_server.py` is the only transport boundary. It reads MCP JSON-RPC from
stdin and writes valid MCP responses to stdout. Diagnostics go only to stderr.
It exposes explicit stage tools (`analysis_start`, `analysis_discovery`,
`analysis_execution`, `analysis_relationships`, `analysis_boundaries`,
`analysis_contracts`, and `analysis_finalize`) plus lifecycle `analysis_reopen`
and Python replacements for the existing trusted `read`, `glob`,
`git_metadata`, and `locate_evidence` tools. Each tool has a closed schema and
documents its reference inputs, receipt output, and rejection conditions.
The server still owns process-private state; stage tools cannot expose future
stage contracts or accept out-of-order submissions. `tools/list` is state-aware:
before start it exposes only `analysis_start`; after start it exposes only the
active stage tool and generic `analysis_reopen`; after all stages it exposes
only `analysis_finalize` and `analysis_reopen`. Future stage names, schemas,
rules, goals, and output shapes are not disclosed to the active-stage agent.

The implementation uses a pinned Python MCP dependency. PIPE-002 must add an
offline-reproducible installation path before a client configuration can launch
the server. The supported runtime is Python 3.13; the package declaration,
locked dependency hashes, wheelhouse provenance, and offline clean-venv install
test are mandatory. Hand-written JSON-RPC or a Node/Bun subprocess is out of
scope.

## State and validation contract

The six internal stages remain ordered:

```text
discovery -> execution -> relationships -> boundaries -> contracts -> finalize
```

State is bound to one MCP server-process instance, target real path, target
snapshot hash, and installed-skill manifest hash. A server accepts exactly one
active analysis. `start` creates state only when no analysis is active; all
later actions operate on that process-private state, and `finalize` writes its
response before immediately clearing that state. Process termination remains a
client lifecycle policy and cannot preserve analysis state. No model-supplied
session identifier, process-global state shared across server instances, or
persistent session store is allowed.
State records the revision, canonical state hash, current stage, redacted
evidence registry, rule applications, stage outputs, and a derived ID catalog.

The validator rejects skipped, duplicate, stale, cross-binding, and post-final
transitions. It also rejects forged or unredacted evidence; invalid claim
status or unknown-claim absence data; dangling graph, process, candidate,
decision, unit, and contract references; duplicate membership; invalid
deployable-unit contract cardinality; incomplete required-rule provenance; and
premature or repeated finalization.

`reopen` uses a closed back-edge table. A valid reopen removes the target
stage and every later stage, their evidence, and derived catalog entries in
one transition. It retains only earlier state and appends a structured reason.

## Portability and security gate

All supported clients configure the Python executable as a local stdio MCP
server. Client-specific configuration files may differ, but the server's tool
schema and JSON-RPC behaviour are identical.

MCP does not establish that every client supplies a non-forgeable host session
identifier to a Python server. A supported client must therefore launch one
fresh server process per interactive analysis session. PIPE-002 must run a
provider-free, per-client isolation proof that demonstrates a fresh process,
one active analysis only, rejection of a second start, no state after
finalization or process exit, and no state visibility from a different server
process. A client that cannot meet this proof is unsupported for stateful
pipeline execution; it may not receive a model-supplied substitute identifier.

The legacy TypeScript implementations remain only until their Python
equivalents pass parity and security tests. PIPE-003 migrates the command,
agent permissions, distribution manifest, and acceptance harness to the Python
MCP server. PIPE-006 removes every legacy TypeScript runtime file only after
the terminal deletion test proves that no supported installation, command, or
acceptance path still references it.

Parity is defined by a checked inventory of each legacy tool's input schema,
output schema, permission name, root-boundary semantics, symlink/junction and
reparse-point handling, secret redaction, output limits, and failure behaviour.
Python replacements require golden contract tests and malicious-path,
symlink/junction, and credential-shaped-content tests before the TypeScript
counterpart can be removed.

## Delivery sequence

1. Replace PIPE-001's TypeScript wording with this Python pure-core contract.
2. Write failing Python tests for each accepted and rejected transition.
3. Implement the pure state, validation, and transition modules until the
   focused tests pass.
4. Review the Python core against the contract before its focused commit.
5. In PIPE-002, add the Python MCP server, the pinned offline-reproducible
   Python dependency path, one-analysis process lifecycle, and the
   client session-isolation gate. Add provider-free launch, `initialize`,
   tool-schema, stderr-only diagnostics, and cleanup smoke tests for OpenCode,
   Claude Code, and Gemini CLI before claiming support.
6. In PIPE-003, migrate and parity-test every trusted TypeScript tool and its
   OpenCode-only configuration before modifying the public command and Agent.
   Add client-specific minimal configuration templates and verify the installed
   Python launcher, absolute-path handling, and permission mapping for each
   supported CLI.
7. In PIPE-006, run the terminal deletion test and remove the legacy
   TypeScript runtime only when no supported path references it. The terminal
   test scans the installed artifact, launchers, configuration, copy scripts,
   harnesses, and imports for `.ts`, `.js`, Node, and Bun runtime dependencies.

## Verification

PIPE-001 runs only provider-free checks:

```text
python -m unittest discover -s runtime/python/tests -p 'test_*.py' -v
python scripts/run_quality_gate.py
git diff --check
```

The MCP process and any client configuration are verified in PIPE-002, not in
PIPE-001. Provider-backed and interactive acceptance remain PIPE-005 work.
