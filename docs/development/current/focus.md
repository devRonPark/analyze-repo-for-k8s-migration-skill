# Current Focus

## Active priority

The active priority is the three-day Google ADK migration MVP. The next step is
`dryforge ready`: write the MVP specification and implementation plan before
any ADK code is started. The migration has established product direction and
permanent constraints; an absence of ADK implementation code is normal at this
stage.

Keep the MVP to one tool-using Agent, deterministic guardrails, a separate
output directory, and the Korean Streamlit work dashboard. Do not reactivate
OpenCode runtime work, multi-agent work, Helm, Cluster apply, or other deferred
scope while preparing the specification and plan.

## Superseded legacy OpenCode work

The following tickets and their linked ADRs remain historical reference only.
They are not prerequisites for the ADK MVP. `DET-010` through `DET-014` and
`SEC-001` are deferred legacy work; their OpenCode/Qwen evidence must not be
reported as ADK completion evidence.

| Ticket | Status | Outcome |
| --- | --- | --- |
| `DET-004` | DONE | A Detailed report that repeats one verdict passes validation; conflicting verdicts fail. |
| `DET-005` | DONE | Detailed report lines keep the property, minimum-input, and keyed-blocker shapes. |
| `DET-006` | DONE | Absence and conflict evidence keep the Korean `검색(...)` form and two parseable sources. |
| `DET-007` | DONE | Every evidence reference is a repository-relative `path:line` with no trailing prose. |
| `DET-008` | DONE | Cited line ranges exist in the read file and all eight sections are present. |
| `DET-009` | DONE | No `result=없음` claim contradicts a file the run read. |
| `DET-003` | PARTIAL | Historical JPetStore Detailed baseline; the 90-point threshold is not an ADK MVP gate. |
| `DET-010` — `DET-014` | DEFERRED | Legacy OpenCode detailed-report follow-ups; superseded for the current MVP. |
| `SEC-001` | DEFERRED | Legacy OpenCode safe-evidence-boundary work; superseded for the current MVP. |

The Detailed verdict-consistency and secret-safe evidence ADRs remain available
as historical reference, not as required reading before ADK implementation.

## Deferred work

The urgent `TKT-*` plan and the `VS-*` ticket set are deferred legacy work.
Ticket IDs do not imply current priority.
