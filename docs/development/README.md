# Development Documentation

Use this directory to find the current development boundary first, then the
day on which a decision or ticket change was recorded. Development documents
are not part of the runtime Skill distribution.

## Start here

- [Current focus](current/focus.md) — the work that may be started now.
- [Current status](current/status.md) — a compact, current-state ledger.
- [Latest priority log](daily/2026-07-30/) — the urgent work's decision and
  ticket plan.

Do not select work from a historical plan or a ticket's filename. A ticket is
active only when it is listed in `current/focus.md`.

## Directory roles

| Path | Role | Update rule |
| --- | --- | --- |
| `current/` | Small, authoritative view of the active priority and current status. | Replace entries as priorities change; do not append command transcripts. |
| `daily/YYYY-MM-DD/ADR-YYYY-MM-DD-NNN-slug.md` | A durable decision made that day, including its context and consequences. | Allocate the next zero-padded sequence for that date; do not rewrite historical decisions. |
| `daily/YYYY-MM-DD/TICKET-LIST-YYYY-MM-DD-NNN-slug.md` | A coherent ticket plan or ticket-event record created that day. | Allocate the next zero-padded sequence for that date; link to ticket source files rather than duplicating their specifications. |
| `tickets/` | Executable ticket specifications, including incomplete backlog tickets. | One source file per ticket; retain its stable ID. |
| `plans/` | Long-lived specifications and roadmaps. | Revise only when their plan is still current. |
| `archive/` | Superseded milestone snapshots and their evidence. | Read-only historical record. |

## Daily workflow

1. Create `daily/YYYY-MM-DD/` when work begins on a new day.
2. Allocate the next `NNN` sequence for that date, then record each durable
   decision in `ADR-YYYY-MM-DD-NNN-slug.md`.
3. Allocate the next `NNN` sequence for that date, then record each coherent
   ticket plan or ticket-event record in `TICKET-LIST-YYYY-MM-DD-NNN-slug.md`.
4. Link related ADRs and ticket lists by their full filenames. Never use a
   duplicate-name suffix such as `(1)`, and do not imply that one document is
   the day's default when several exist.
5. Update `current/focus.md` and `current/status.md` with only the resulting
   current state.
6. Keep ticket acceptance criteria and verification evidence in the ticket or
   its linked completion record, not in a daily index.

## Historical initial milestone

The initial OpenCode-only milestone was interrupted before every planned
vertical slice was implemented. Its original boundary, status evidence, and
roadmap remain preserved under
[`archive/initial-opencode-milestone/`](archive/initial-opencode-milestone/)
and [`plans/`](plans/). The `VS-*` documents in `tickets/` remain backlog or
partial-work specifications unless `current/status.md` says otherwise.
