# ADR-2026-07-30-006: Use a slash-first local interactive entry

- Status: Accepted
- Date: 2026-07-30
- Related deferred work: [ADR-2026-07-30-005-deferred-client-routing.md](ADR-2026-07-30-005-deferred-client-routing.md)

## Context

The primary user flow is to change into a local Git repository, run `opencode`,
and ask for Kubernetes migration analysis. Requiring users to remember
`--mini --agent kubernetes-migration-analyzer` exposes runtime implementation
details. Conversely, making the installed Skill replace OpenCode's global
default agent, model, or permissions would affect unrelated user workflows.

## Decision

The supported, deterministic entry is:

```text
<target Git repository> $ opencode
OpenCode > /analyze-repo-for-kubernetes [optional arguments]
```

The installed custom command selects `kubernetes-migration-analyzer`; users do
not supply agent flags. The command's default target is the current Git root.
An explicit `.` preserves the current directory as an analysis subdirectory.
All local targets must remain within the current Git worktree.

Help requests (`--help`, `도움말`, and `사용법`) are resolved before target
resolution and do not inspect a repository. A missing, invalid, or unsafe
target returns one Korean sentence with the reason and a Local path request.

For a successful analysis, the final assistant response is the completed
Markdown report. OpenCode client tool events, spinners, and concise
model-authored progress updates may remain visible during an interactive run.

Natural-language routing is best-effort, not a supported guarantee. Do not
support Repository URLs, in-session `@repository` selection, external target
handoff, or session-scoped external permissions in this decision.

## Consequences

- The existing installer continues to register the Skill, command, and agent
  without overwriting global OpenCode defaults.
- Documentation can teach one reliable invocation path.
- Future client-side routing remains isolated under ADR-005 instead of leaking
  into Skill target-resolution rules.
