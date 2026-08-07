# Current Focus

## Active priority (start here — 2026-08-07 evening handoff)

**Next session: live-verify [VS-023](../tickets/VS-023-migration-evidence-sensor-tools.md) Phase 1 (`locate_evidence`) against `demo-repositories/jpetstore-6`.**
This session (1) landed [SEC-002](../tickets/SEC-002-read-tool-symlink-escape.md)
(`18915ed`) — `read.ts`/`glob.ts` now resolve symlinks/junctions before
their worktree-boundary check, via new `runtime/lib/safe-path.ts`; (2)
completed VS-023's step-1 scoping pass and, per user confirmation, narrowed
it from the ticket's original five ecosystem-aware tools to one generic,
judgment-free `locate_evidence` tool — see
[ADR-2026-08-07-003](../daily/2026-08-07/ADR-2026-08-07-003-vs-023-sensor-tool-scoping.md);
(3) implemented and unit-tested it (`565a016`, `runtime/lib/locate-evidence.ts`
+ `runtime/tools/locate_evidence.ts`, 16/16 `bun test runtime/lib`, wired
into the agent's permission list and citation instructions).

**What's unverified and is the next session's actual work:** everything
above was checked with `bun test`/`bun build`/`python scripts/run_quality_gate.py`
only — no live OpenCode run happened this session (`opencode` CLI isn't
installed in this sandbox and a live run needs escalated per-command
permission, which wasn't requested). VS-023's acceptance criterion
("repeated live runs against `demo-repositories/jpetstore-6` show a
measurably lower citation-fabrication rate") is still open. Concretely:

1. Confirm `opencode` is installed and request escalated permission for
   `http://172.16.4.249:30000/v1` (see `memory/opencode-e2e.md`).
2. Run `python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root demo-repositories/jpetstore-6 --repeat 3-5 --output-dir <dir>` and check whether the model actually calls `locate_evidence` (it's only prompted to prefer it, not forced) and whether cited references are now consistently real.
3. Compare against the 58/100 baseline in `tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`'s "Evidence calibration and report discipline" dimension specifically — that's the dimension VS-023 targets.
4. If citations are still fabricated because the model picked a wrong `glob`/`content_pattern` (not a wrong line number) — a class of error `locate_evidence`'s design does not fix — that's the signal to revisit ADR-003's deferred Phase 2 (the five ecosystem-aware tools), not to add more instruction text.

**Read first, in this order:**
1. [ADR-2026-08-07-003](../daily/2026-08-07/ADR-2026-08-07-003-vs-023-sensor-tool-scoping.md) — the confirmed scoping decision and why it's narrower than the ticket's original proposal.
2. [VS-023](../tickets/VS-023-migration-evidence-sensor-tools.md)'s "Decision outcome (2026-08-07)" section — what was actually built and tested vs. not.
3. [ADR-2026-08-07-001](../daily/2026-08-07/ADR-2026-08-07-001-summary-delivery-structured-output.md) and [ADR-2026-08-07-002](../daily/2026-08-07/ADR-2026-08-07-002-summary-validate-and-repair-loop.md) — same-day context: the Summary Agent is JSON-only (DEL-002/DEL-003), and a bounded validate-and-repair loop exists for output-*format* failures. VS-023 targets a different axis (evidence *accuracy*), so don't re-solve what these two already cover.
4. [tests/evaluation/jpetstore-6-summary-json-first-scorecard.md](../../../tests/evaluation/jpetstore-6-summary-json-first-scorecard.md) — the 58/100 baseline this session's live-verification step should compare against.

**Do not start from `DET-010`–`DET-014` this session** (see "Deferred, still open" below) — finishing VS-023 Phase 1's live verification is the priority this handoff sets.

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
