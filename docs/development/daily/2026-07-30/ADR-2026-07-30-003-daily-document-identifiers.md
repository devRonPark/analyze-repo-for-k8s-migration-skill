# ADR-2026-07-30-003: Identify daily documents by sequence and subject

- Status: Accepted
- Date: 2026-07-30

## Context

A date directory can contain more than one decision or coherent ticket plan.
Fixed filenames such as `ADR.md` and `TICKET_LIST.md` force duplicate-name
suffixes such as `(1)`, which are not stable identifiers and obscure links.

## Decision

Keep the date directory as a grouping boundary, not as a single-document
container. Name daily documents using their type, date, zero-padded sequence,
and a concise subject slug:

```text
ADR-YYYY-MM-DD-NNN-slug.md
TICKET-LIST-YYYY-MM-DD-NNN-slug.md
```

Allocate each sequence independently by document type and date. Documents
that refer to a related ADR or ticket list must link to its complete filename.
`current/` must link to the exact document governing the active work.

## Consequences

- Multiple decisions and ticket plans can be created on the same day without
  ambiguous filenames.
- Historical links remain meaningful when later documents are added.
- A daily directory has no implicit default ADR or ticket list.
