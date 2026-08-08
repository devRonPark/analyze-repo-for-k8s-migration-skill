# Current Focus

## Active priority (start here — updated 2026-08-08, explicit user directive)

**The active queue is the PIPE analysis-pipeline milestone,
[VS-027](../tickets/VS-027-workload-boundary-golden-fixtures.md), and
[VS-026](../tickets/VS-026-reconsider-descriptor-parser-phase2.md), in that
order.** The PIPE milestone supersedes VS-028's prose-only mechanism under
[ADR-2026-08-08-004](../daily/2026-08-08/ADR-2026-08-08-004-analysis-pipeline-orchestration.md).
The approved review-driven reordering is recorded in
[ADR-2026-08-08-005](../daily/2026-08-08/ADR-2026-08-08-005-pipeline-resequencing-and-skill-load.md):
PIPE-000 first, an early deterministic vertical proof after PIPE-001, and
VS-027 static fixtures before PIPE-005.
Suggested order and why:

1. **PIPE milestone: blocked at PIPE-000** —
   [PIPE-000 completion](../daily/2026-08-08/PIPE-000-completion-2026-08-08.md)
   found no verified host-issued identity or interactive final-response hook.
   [ADR-2026-08-08-006](../daily/2026-08-08/ADR-2026-08-08-006-host-boundary-required-for-pipeline.md)
   prohibits substitute IDs and holds PIPE-001 through PIPE-004 until a
   supported host boundary is selected. Do not make another prose-only change
   intended to force a reference read.
2. **VS-027** — golden-set fixtures (must-split Case B, must-not-split
   Case A) for `references/workload-boundary.md`. Build Case B with its two
   processes in genuinely separate files/directories (not sharing one file
   like the `flask-celery-example` fixture that exposed the prior gap).
3. **VS-026** — a scoping/decision ticket only (re-open `ADR-2026-08-07-003`'s
   VS-023 Phase 2 deferral): decide whether the wrong-file `docker-compose.yaml`
   citation finding and `locate_evidence`'s first-match imprecision justify
   building the deferred five ecosystem-aware sensor tools. No implementation
   expected from this one, just a decision recorded in the ticket.

**Everything below this point (VS-024, VS-023-adjacent handoff notes,
`DET-010`–`DET-014`, `SEC-001`, VS-019, etc.) is deprioritized as of this
directive — kept for context and to resume later, not for the next session
to pick up.**

<details>
<summary>Deprioritized context (click to expand — not the active queue)</summary>

### VS-024 (deprioritized)

**[VS-024](../tickets/VS-024-detailed-json-first-pipeline.md) (port Detailed
mode to the JSON-first render/validate/repair pipeline) has both commits
landed on `worktree-review-main` (schema/renderer/tests, then
prompt/harness wiring) — TDD throughout, 178 tests passing (1 pre-existing
unrelated VS-019 failure). Live verification (3+ `slash-detailed` repeats
against `jpetstore-6`, before/after validator counts and rubric score) is
deferred: the local OpenCode provider was not reachable this session. Read
the ticket's "Decision outcome (partial)" section before resuming — pick
this up next once the provider is reachable, or continue with other work
in the meantime.** The same-day Detailed-mode measurement that motivated
this ticket:
(`tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md`)
ran the current free-written-Markdown Detailed path 4 times (3 batch, 1
interactive `--interactive`) against `jpetstore-6` pinned to the golden
set's revision. Timing was fine (209–311s) and citation content was mostly
accurate in the 3 batch runs, but **structural contract compliance was
bad in all four**: `validate_report.py --mode detailed` failure counts of
32/18/20/36, none matching the required literal section headings or
`- 판정:` verdict line, one run even emitting an English heading and
Markdown tables the template forbids. This is the exact failure class
Summary mode already solved via DEL-002/DEL-003/ADR-2026-08-07-001 (JSON +
a deterministic renderer instead of free-written Markdown); Detailed never
got the same treatment. VS-024 is that port, fully scoped with a schema gap
analysis, an implementation-step list, and explicit out-of-scope boundaries
(it does **not** attempt to fix the wrong-file citation problem the
interactive run also found — see below).

**Read first, in this order, if picking up VS-024:**
1. [VS-024](../tickets/VS-024-detailed-json-first-pipeline.md) in full — it
   is self-contained and lists its own "Read first" set
   (`assets/migration-assessment-template.md`, `scripts/render_summary.py`,
   `schemas/analysis-result.schema.json`, `scripts/report_contract.py`,
   `scripts/validate_report.py`, the agent prompt, and
   `run_opencode_acceptance.py`'s repair-loop functions).
2. [tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md](../../../tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md) —
   the measurement that motivated the ticket, including the exact validator
   failure lists and the wrong-file-citation evidence.

**A second, separate, more concerning finding from the same measurement,
explicitly out of VS-024's scope:** the one interactive (`--interactive`,
not batch) run cited `docker-compose.yaml:17`/`docker-compose.yaml:21` (a
Compose schema-version string and a `container_name` line — real content,
wrong file) for two different blocker-level claims that were actually
sourced from `Dockerfile:17`/`Dockerfile:21`, repeated 3× and 4× in the same
report. This is a content/evidence-sourcing problem, not a format problem —
a JSON-first renderer (VS-024) cannot catch it. It is the same risk class
VS-023's `locate_evidence` targets; worth checking whether these specific
wrong-file citations were `locate_evidence`-sourced or hand-written before
deciding whether new work is needed, or whether VS-023's existing
"every citation must come from `locate_evidence`" enforcement already
covers it and just wasn't followed this one time (n=1, not yet a trend).

### Prior handoff, still valid context (2026-08-07 late-evening, VS-023 Phase 1)

**VS-023 Phase 1 (`locate_evidence`) is live-verified and DONE for Summary
mode.** This session cloned `jpetstore-6` (pinned to the golden set's
revision `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`) and ran
`scripts/run_opencode_acceptance.py --case slash-default-summary --repeat 3`
against it three times, all `PASS`, target unchanged. Full detail in
`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`'s "VS-023
Phase 1 live verification" section and [VS-023](../tickets/VS-023-migration-evidence-sensor-tools.md)'s
"Live verification outcome" section — short version: 0 fabricated citations
across 30 checked, evidence-calibration dimension re-scored 9/10, Phase 2
(the deferred five ecosystem-aware tools) still not needed. **Not yet
confirmed for Detailed mode** — see the wrong-file-citation finding above.

Getting the live run to execute at all required fixing an unrelated,
previously-undetected harness bug first: `scripts/install-opencode.sh` and
`run_opencode_acceptance.py` copied `runtime/tools/` but never
`runtime/lib/`, so every tool importing `"../lib/..."` (starting with
SEC-002's `safe-path.ts`) failed to resolve — meaning every live run since
SEC-002 landed (`18915ed`) would have failed the same way. Fixed via a new
`copy_tools()` helper and a regression test
(`test_isolated_tool_copy_includes_sibling_lib_modules`); see the scorecard
section for why this was in-scope to fix rather than just flag.

One unfixed, low-priority finding from that session, not blocking anything:
`read.ts`'s `trustedSkillRoots` hardcodes a singular `skill/` path segment,
but the actual installed/observed directory is plural `skills/`. The model
never actually needs this path (it reads skill content via the `skill` tool,
which inlines everything), so this went unnoticed across all three live
runs. Worth a follow-up ticket only if a future workflow needs direct `read`
access to skill-internal files.

New candidates from comparing this project against a sibling repo's
architecture review (2026-08-07):
- **[VS-025](../tickets/VS-025-summary-workload-boundary.md) — DONE
  (2026-08-07)**: Summary now conditionally loads
  `references/workload-boundary.md` on the same signal Detailed uses and
  routes an unresolved split/merge decision through `missing_inputs`
  (`open_design_decision`); no schema change. Live-verified 3/3 `PASS`
  against JPetStore 6 via the `upstage/solar-pro2` provider (the local
  `local-sglang` endpoint was unreachable this session) — see the ticket's
  "Decision outcome" for the full result.
- VS-026, VS-027, VS-028 (found via VS-025's live verification) are now the
  sole active priority — see the top of this file, not this list.

Other reasonable candidates if none of the above is picked up next, in no
particular priority order:
- `DET-010`–`DET-014` (see "Deferred, still open" below) — re-triage against
  VS-024 first if VS-024 has landed by the time these are picked up; they
  target the free-written Detailed path VS-024 may make moot.
- A follow-up on the `skill/`-vs-`skills/` mismatch noted above, if it turns
  out to matter for some workflow.
- Confirming SEC-002's symlink-escape fix with a dedicated live attempt
  (status.md notes it was only incidentally exercised, not deliberately
  attacked, during VS-023's live runs).

**Read first, in this order, if picking up VS-023-adjacent work instead:**
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

</details>

## Deferred work

The urgent `TKT-*` plan and the `VS-*` ticket set remain available, but neither
is the active queue. Ticket IDs do not imply completion or current priority.
