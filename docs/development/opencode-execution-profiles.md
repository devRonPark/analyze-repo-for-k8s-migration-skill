# OpenCode Execution Profiles

`scripts/run_opencode_acceptance.py` supports two profiles. Both profiles set
the application repository as the OpenCode `--dir` value and as the child
process working directory. The runner rejects an output directory located
inside the application repository.

## `user`

`user` inherits the caller's `HOME`, `OPENCODE_CONFIG`,
`OPENCODE_CONFIG_DIR`, global config, Agent, Skill, and log settings. It never
installs or copies `.opencode`, an Agent, or a Skill. The runner records the
discovery paths and reports missing or stale global Skill copies without
repairing them.

Use this profile to characterize a real user installation. A missing global
Agent or Skill, or a user HOME that cannot write OpenCode logs, is an observed
environment blocker rather than a reason to fall back to the isolated profile.

## `isolated`

`isolated` creates a temporary root containing:

- `runtime/opencode.json`, copied from the requested source config;
- one Agent at `config/agents/kubernetes-migration-analyzer.md`;
- the allowlisted runtime Skill at `config/skills/analyze-repo-for-kubernetes`;
- temporary HOME and XDG config/data/state/cache directories.

The temporary config and rendered Agent allow only the exact temporary Skill
path through `external_directory`. Global HOME Skill exceptions are removed
from the rendered Agent. The application repository is not an allowed external
directory because it is the current OpenCode project selected by `--dir`.

The isolated profile sets `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, and
`OPENCODE_DISABLE_AUTOUPDATE=1`; it does not consult or modify the caller's
global Skill installation.

## Evidence and measurement

Each run writes debug output for `config`, `startup`, `skill`, and
`agent kubernetes-migration-analyzer`, plus stdout/stderr logs with
`--print-logs --log-level DEBUG`. Traces include the profile paths, command to
Agent mapping, merged permission input, loaded Skill/tool calls, provider and
model, target `.opencode` preflight, Git probes, and a filesystem hash
comparison.

Pass `--interactive` to execute one representative interactive command for the
profile and store its independent result under `interactive.json`. Interactive
timeouts and provider failures remain non-success statuses.

`scripts/measure_context.py` consumes these traces. It reports loaded file
bytes and lines only when the path resolves under a recorded Skill or target
root, along with tool calls, explicit step events, elapsed time, and provider
usage. It leaves usage as `null` when the provider did not emit usage fields;
it never estimates tokens from bytes or model names.

The project-local installer remains supported for normal development, but it
is intentionally not used by acceptance/debug runs because it changes the
application repository.
