# Current Focus

## Active priority (start here — 2026-08-07, VS-024 implementation landed, live verification still open)

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
architecture review (2026-08-07), prioritized:
- **P0 — [VS-025](../tickets/VS-025-summary-workload-boundary.md) — DONE
  (2026-08-07)**: Summary now conditionally loads
  `references/workload-boundary.md` on the same signal Detailed uses and
  routes an unresolved split/merge decision through `missing_inputs`
  (`open_design_decision`); no schema change. Live-verified 3/3 `PASS`
  against JPetStore 6 via the `upstage/solar-pro2` provider (the local
  `local-sglang` endpoint was unreachable this session) — see the ticket's
  "Decision outcome" for the full result.
- **P0 — [VS-028](../tickets/VS-028-prose-only-process-discovery.md) — NEW,
  rescoped 3x (2026-08-07), read before starting VS-027**: live-verifying
  VS-025 against a real must-split fixture
  (`github.com/miguelgrinberg/flask-celery-example` — Flask app + Celery
  worker, both defined in one `app.py`, distinct start commands) found the
  Celery worker never becomes a candidate at all, and `workload-boundary.md`
  was never loaded. Two earlier root-cause guesses were ruled out ("model
  ignores README prose"; "`SKILL.md` restricts evidence to declarative
  artifacts" — `script` was already in scope and `app.py` was read in full).
  Three independent fresh-session reviews (LLM-behavior, architecture/
  regression, project-scope) then found the third revision's *fix* — reword
  the conditional trigger a fourth time across `SKILL.md`/`workflow.md`/the
  agent prompt — would not have worked: it's the same "more prose" pattern
  that already failed 3x in this prompt, and critically, Detailed mode
  separately caps `components` at exactly one entry
  (`kubernetes-migration-analyzer.md:333-335`, a stale DET-001 artifact),
  which would have silently defeated the fix for Detailed regardless. This
  **fourth revision**'s fix is mechanical instead: move
  `workload-boundary.md` into both modes' *unconditional*-load lists (like
  `workflow.md` already is) rather than rewording the trigger again, plus
  remove Detailed's stale one-component cap. Confidence in the underlying
  diagnosis is also now explicitly caveated — the only supporting evidence
  is 2 repeats on the `upstage/solar-pro2` fallback provider, not this
  project's default, and the run artifacts were not preserved. See the
  ticket's "Independent review findings" section for full detail.
- **P1 — [VS-026](../tickets/VS-026-reconsider-descriptor-parser-phase2.md)**:
  re-open `ADR-2026-08-07-003`'s VS-023 Phase 2 deferral given two
  evidence-sourcing gaps since: the wrong-file `docker-compose.yaml`
  citation above, and `locate_evidence`'s documented first-match imprecision
  (`VS-023`'s "Citation-sourcing enforcement follow-up" section). A
  scoping/decision ticket, not a build-it ticket.
- **P1 — [VS-027](../tickets/VS-027-workload-boundary-golden-fixtures.md)**:
  `references/workload-boundary.md` has no fixture or golden-set coverage —
  JPetStore 6 never presents a multi-process split. Adds a must-split and a
  must-not-split fixture to verify the rule actually decides correctly.
  **Likely blocked by VS-028** in practice: a must-split fixture whose only
  evidence is prose will hit VS-028's gap before it ever exercises the
  boundary rule; either land VS-028 first or build Case B's second process
  with declarative (Dockerfile/Compose/Procfile) evidence to sidestep it.

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

## Deferred work

The urgent `TKT-*` plan and the `VS-*` ticket set remain available, but neither
is the active queue. Ticket IDs do not imply completion or current priority.
