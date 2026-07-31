# Architecture Decision Record — 2026-07-29

## ADR-2026-07-29-001: Organize development context by day and separate it from current priority

### Status

Accepted.

### Context

Development produces decisions and ticket changes every day. A single ADR
document and a cumulative status table make the context of a particular day
hard to recover. The repository also contains planned `VS-*` tickets that are
not all implemented. The active priority is maintained separately so a future
priority change does not rewrite the historical plan.

### Decision

- Keep the active queue and compact state only in `current/`.
- Record daily decisions in `daily/YYYY-MM-DD/ADR.md` and daily ticket events
  in `daily/YYYY-MM-DD/TICKET_LIST.md`.
- Keep each ticket specification in `tickets/` as its sole detailed source.
- Treat ticket IDs and historical plans as backlog context, not evidence of
  completion or current priority.
- Preserve the initial OpenCode-only milestone's milestone and status files
  under `archive/initial-opencode-milestone/`.

### Consequences

- Current work can be found without reading historical command evidence.
- A future reader can reconstruct why a priority or decision changed on a
  given day.
- New work must receive a ticket before implementation; this prevents a
  priority change from silently bypassing acceptance criteria and verification.
