# Current Status

| Work item | Status | Evidence | Blocker |
| --- | --- | --- | --- |
| INT-001 — help before analysis | DONE | Help and usage routing contract is covered by target safety tests and the Quality Gate. | None. |
| INT-002 — local target resolution | DONE | Worktree-bounded target contract is covered by target safety tests and the Quality Gate. | None. |
| INT-003 — report-only response | PARTIAL | Harness tests and Quality Gate pass; TTY run loaded the Skill and agent without mutating the target. | Final TTY Markdown report was not captured. |
| DET-001 — Detailed evidence slots | DONE | JPetStore 6 Detailed E2E returned a complete eight-section report in 2m 14s within the read budget and left the target Git status unchanged. | None. |
| DET-004 — verdict consistency | DONE | The validator accepts a repeated identical verdict, rejects differing ones, and runs keyed-blocker validation again. | None. |
| DET-005 — report line shapes | DONE | Detailed E2E rerun completed a 117-line report in 1m 56s; validator failures fell from 45 to 14 and keyed-blocker violations to 0, with the target unchanged. | None. |
| DET-006 — absence and conflict evidence | DONE | The DET-006 rerun completed a 124-line report in 2m 24s with no translated `검색` marker and no unparsable `상충됨` source; `미확인` evidence without `검색(...)` fell from 5 to 1. | None. |
| DET-007 — evidence references | DONE | The DET-007 rerun completed a 139-line report in 2m 1s with zero citations outside the repository; validator failures fell from 21 to 14. | None. |
| DET-008 — invented line ranges | DONE | The DET-008 rerun completed a 130-line report in 2m 28s with no out-of-range or reversed line span, no missing section, and validator failures down to 7. | None. |
| DET-003 — Detailed golden-set scoring | PARTIAL | The DET-008 report scores 63/100 against the independent JPetStore golden set; false absence evidence and missing dependency edges are the main deductions. | Below the 90-point threshold, and the five-candidate food-delivery target does not exist on this machine. |
| SEC-001 — safe evidence boundary | IN_PROGRESS | The trusted `read`, `glob`, and `git_metadata` tools loaded in the JPetStore E2E with no `grep`, `list`, or `bash` call and no credential literal in the report. | Adapter unit and canary E2E coverage are not implemented. |
| TKT-001 through TKT-005 | DEFERRED | Urgent-plan slices remain recorded in the prior ticket list. | Not the active queue. |
| Initial OpenCode-only milestone | INTERRUPTED | Original progress ledger is preserved in [`../archive/initial-opencode-milestone/status.md`](../archive/initial-opencode-milestone/status.md). | Superseded by the urgent priority. |

Allowed status values: `TODO`, `IN_PROGRESS`, `DONE`, `PARTIAL`, `BLOCKED`,
`DEFERRED`, `NEEDS_TICKET`, `INTERRUPTED`.
