# ADR-2026-07-30-005: Defer client-side analysis routing and external target handoff

- Status: Deferred
- Date: 2026-07-30

## Context

The supported interactive path is intentionally small: a user starts OpenCode
in the local Git repository to analyze and invokes
`/analyze-repo-for-kubernetes`. The installed custom command selects the
analysis agent without requiring `--mini` or `--agent` flags on every launch.

Natural-language intent routing and `@repository` selection were considered
as convenience features. Making either deterministic would require a client or
plugin that observes user input, creates an isolated analysis session, and
applies a single-target read permission before the agent starts. The current
Skill and agent cannot safely change their own filesystem permissions.

## Decision

Exclude the following from the current implementation agreement:

- mandatory routing of natural-language requests to the analysis agent;
- `@repository` selection from an already-open OpenCode session;
- automatic creation of an external-target analysis session;
- host-side launcher and per-session external-directory allowlists.

Natural-language analysis requests remain best-effort. The supported,
documented path is the installed slash command in the target repository.
Existing OpenCode default agent, model, and global permissions must not be
overwritten by Skill installation.

## Reconsideration criteria

Revisit this decision only when a concrete OpenCode client/plugin integration
can prove all of the following:

1. It can recognize an analysis request and switch to a new isolated session.
2. It can validate a single local Git root and apply only that root as a
   session-scoped read permission before the agent starts.
3. It keeps prior session history, attachments, and permissions out of the new
   session.
4. It exposes handoff and failure state through client UI, not assistant prose.
5. It has an end-to-end test covering invalid targets, session-creation
   failure, unchanged repositories, and no broadened filesystem access.
