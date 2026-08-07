# Current Focus

## Active priority (start here — 2026-08-07 late-evening handoff)

**VS-023 Phase 1 (`locate_evidence`) is now live-verified and DONE.** This
session cloned `jpetstore-6` (pinned to the golden set's revision
`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`) and ran
`scripts/run_opencode_acceptance.py --case slash-default-summary --repeat 3`
against it three times, all `PASS`, target unchanged. Full detail in
`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`'s "VS-023
Phase 1 live verification" section and [VS-023](../tickets/VS-023-migration-evidence-sensor-tools.md)'s
"Live verification outcome" section — short version: 0 fabricated citations
across 30 checked, evidence-calibration dimension re-scored 9/10, Phase 2
(the deferred five ecosystem-aware tools) still not needed.

Getting the live run to execute at all required fixing an unrelated,
previously-undetected harness bug first: `scripts/install-opencode.sh` and
`run_opencode_acceptance.py` copied `runtime/tools/` but never
`runtime/lib/`, so every tool importing `"../lib/..."` (starting with
SEC-002's `safe-path.ts`) failed to resolve — meaning every live run since
SEC-002 landed (`18915ed`) would have failed the same way. Fixed via a new
`copy_tools()` helper and a regression test
(`test_isolated_tool_copy_includes_sibling_lib_modules`); see the scorecard
section for why this was in-scope to fix rather than just flag.

One unfixed, low-priority finding from this session, not blocking anything:
`read.ts`'s `trustedSkillRoots` hardcodes a singular `skill/` path segment,
but the actual installed/observed directory is plural `skills/`. The model
never actually needs this path (it reads skill content via the `skill` tool,
which inlines everything), so this went unnoticed across all three live
runs. Worth a follow-up ticket only if a future workflow needs direct `read`
access to skill-internal files.

**Next session has no forced starting point.** Reasonable candidates, in no
particular priority order:
- `DET-010`–`DET-014` (see "Deferred, still open" below) — the longest-
  standing open item, previously deferred only because VS-023 took priority.
- A follow-up on the `skill/`-vs-`skills/` mismatch noted above, if it turns
  out to matter for some workflow.
- Confirming SEC-002's symlink-escape fix with a dedicated live attempt
  (status.md notes it was only incidentally exercised, not deliberately
  attacked, during VS-023's live runs).

**Read first, in this order, if picking up VS-023-adjacent work:**
1. [tests/evaluation/jpetstore-6-summary-json-first-scorecard.md](../../../tests/evaluation/jpetstore-6-summary-json-first-scorecard.md)'s "VS-023 Phase 1 live verification" section — the actual result.
2. [VS-023](../tickets/VS-023-migration-evidence-sensor-tools.md)'s "Live verification outcome" section.
3. [ADR-2026-08-07-003](../daily/2026-08-07/ADR-2026-08-07-003-vs-023-sensor-tool-scoping.md) — why Phase 1 is narrower than the ticket's original proposal, and what would justify Phase 2.

## Deferred, still open (unrelated to VS-023, not this session's target)

[`../daily/2026-07-30/TICKET-LIST-2026-07-30-008-detailed-accuracy-followups.md`](../daily/2026-07-30/TICKET-LIST-2026-07-30-008-detailed-accuracy-followups.md):
`DET-010` through `DET-014` carry the remaining golden-set deductions, and three
open decisions are recorded there. The completed contract-defect work is in
[`../daily/2026-07-30/TICKET-LIST-2026-07-30-007-detailed-contract-defects.md`](../daily/2026-07-30/TICKET-LIST-2026-07-30-007-detailed-contract-defects.md).
The secret-safe evidence boundary plan remains open in
[`../daily/2026-07-30/TICKET-LIST-2026-07-30-006-secret-safe-evidence-boundary.md`](../daily/2026-07-30/TICKET-LIST-2026-07-30-006-secret-safe-evidence-boundary.md).
This queue's own "validate-and-repair loop needs an ADR first" blocker is
now resolved in principle by ADR-2026-08-07-002 (written for Summary) —
whoever picks up `DET-010`–`DET-014` should read that ADR before deciding
whether to reuse or adapt its pattern for Detailed mode.

## Also open, not scheduled

- [VS-019](../tickets/VS-019-qwen-symlink-windows-junction.md) — `ln -s` produces a Windows junction, not a symlink `test_install_script_creates_qwen_skill_symlink` recognizes. Low priority, cosmetic test failure, not a real functionality gap.
- Agent Runtime portability (OpenCode vs. goose/OpenHands/Codex) was discussed and explicitly **deferred, not rejected** on 2026-08-07 — see that day's conversation if revisiting; no ticket exists for it yet because the current OpenCode CLI-subprocess path (not the blocked HTTP/SDK path) is not actually broken.

| Ticket | Status | Outcome |
| --- | --- | --- |
| `DET-004` | DONE | A Detailed report that repeats one verdict passes validation; conflicting verdicts fail. |
| `DET-005` | DONE | Detailed report lines keep the property, minimum-input, and keyed-blocker shapes. |
| `DET-006` | DONE | Absence and conflict evidence keep the Korean `검색(...)` form and two parseable sources. |
| `DET-007` | DONE | Every evidence reference is a repository-relative `path:line` with no trailing prose. |
| `DET-008` | DONE | Cited line ranges exist in the read file and all eight sections are present. |
| `DET-009` | DONE | No `result=없음` claim contradicts a file the run read. |
| `DET-003` | PARTIAL | JPetStore Detailed report scores 72/100; the MSA target and the 90-point threshold remain open. |
| `DET-010` — `DET-014` | TODO | Context path, cited line ranges, build-time dependency edge, descriptor compatibility, and repeated `미확인` slot slips. |
| `SEC-001` | IN_PROGRESS | Target evidence is redacted before the model can read it. |

Read [the Detailed verdict-consistency ADR](../daily/2026-07-30/ADR-2026-07-30-010-detailed-verdict-consistency.md)
and [the secret-safe evidence boundary ADR](../daily/2026-07-30/ADR-2026-07-30-009-secret-safe-evidence-boundary.md)
before implementation.

## Deferred work

The urgent `TKT-*` plan and the `VS-*` ticket set remain available, but neither
is the active queue. Ticket IDs do not imply completion or current priority.
