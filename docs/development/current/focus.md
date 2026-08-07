# Current Focus

## Active priority (start here — 2026-08-07 handoff)

**Next session: [VS-023](../tickets/VS-023-migration-evidence-sensor-tools.md) — migration-evidence sensor tools.**
Read it in full before starting; it is intentionally marked "needs a
scoping decision before implementation" — the proposed tool set
(`discover_deployment_candidates`, `inspect_build_runtime`,
`inspect_network_contract`, `inspect_configuration`,
`inspect_state_dependencies`) and their exact return shapes are a
*proposal*, not yet accepted. Do the scoping pass (VS-023's Implementation
step 1) before writing any tool code.

**Read first, in this order:**
1. [ADR-2026-08-07-001](../daily/2026-08-07/ADR-2026-08-07-001-summary-delivery-structured-output.md) and [ADR-2026-08-07-002](../daily/2026-08-07/ADR-2026-08-07-002-summary-validate-and-repair-loop.md) — same-day context: the Summary Agent is now JSON-only (DEL-002/DEL-003), and a bounded validate-and-repair loop already exists for output-*format* failures. VS-023 targets a different axis (evidence *accuracy* — citation fabrication), so don't re-solve what these two already cover.
2. [tests/evaluation/jpetstore-6-summary-json-first-scorecard.md](../../../tests/evaluation/jpetstore-6-summary-json-first-scorecard.md) — the live evidence motivating VS-023 (a citation `file:17-268` against a 117-line file), and the 58→84/100 score history from VS-020/VS-021.
3. [SEC-002](../tickets/SEC-002-read-tool-symlink-escape.md) — **VS-023 depends on this.** `read.ts`'s worktree-boundary check doesn't resolve symlinks; if sensor tools share that boundary logic (they should, per VS-023's scope), decide whether to land SEC-002 first or in the same pass.
4. `runtime/agents/kubernetes-migration-analyzer.md`'s current `## Summary JSON contract` section (added 2026-08-07) — sensor tools would feed evidence into this same JSON contract, not change it.

**Do not start from `DET-010`–`DET-014` this session** (see "Deferred, still open" below) — VS-023 is the priority the previous session ended on, per this handoff.

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
