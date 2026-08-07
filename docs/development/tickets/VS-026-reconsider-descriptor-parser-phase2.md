# VS-026 — Re-open the VS-023 Phase 2 scoping decision

## Outcome

A confirmed decision — not a default carry-over — on whether VS-023's
deferred Phase 2 (ecosystem-aware `discover_deployment_candidates` /
`inspect_*` sensor tools) should now be built, given two evidence-sourcing
gaps observed since `ADR-2026-08-07-003` deferred it: a wrong-file citation
in Detailed mode and a first-match imprecision in `locate_evidence`.

## Why this is a vertical slice

`ADR-2026-08-07-003` deferred Phase 2 because Phase 1's one observed
near-miss (a `locate_evidence` glob/pattern matching an unrelated file) "did
not produce a fabricated citation" — the signal `focus.md` set for
revisiting the decision. Two things have happened since that are closer to
that signal than the ADR anticipated:

1. `docs/development/current/focus.md`'s active-priority section (2026-08-07)
   records a live interactive Detailed run citing `docker-compose.yaml:17`
   and `docker-compose.yaml:21` (a Compose schema-version string and a
   `container_name` line — real content, wrong file) for two blocker-level
   claims actually sourced from `Dockerfile:17`/`Dockerfile:21`, repeated 3x
   and 4x in the same report. `focus.md` explicitly flags this as "the same
   risk class VS-023's `locate_evidence` targets" and notes it is unconfirmed
   whether it was `locate_evidence`-sourced or hand-written.
2. `VS-023-migration-evidence-sensor-tools.md`'s "Citation-sourcing
   enforcement follow-up" section separately documents `locate_evidence`
   returning the *first* line matching an under-specific `pattern` (e.g.
   `INSERT INTO` matching a non-credential `sequence` row before the real
   `signon`/`account` credential rows) — real content, imprecise match, the
   same failure shape as the wrong-file case above, just narrower.

Both are exactly the class of problem the ADK-repo review's "Descriptor
Parser" recommendation (structural, ecosystem-aware fact extraction instead
of pattern-matching raw text) targets. `locate_evidence` is judgment-free but
still text-pattern-based; a `Dockerfile`-shaped or `docker-compose.yaml`-shaped
parser could not confuse the two files by construction. This ticket does not
pre-decide Phase 2 should be built — it re-runs the ADR-003 scoping decision
against the new evidence and records the outcome either way.

## Status and dependencies

- **Status:** Proposed — a scoping/decision ticket, not an implementation
  ticket, following the VS-023 Phase 1 precedent (scope first, implement
  only after the decision is confirmed).
- **Depends on:** VS-023 Phase 1 (`locate_evidence`, done) and its
  `ADR-2026-08-07-003`; VS-024 (Detailed JSON-first pipeline) for isolating
  whether the wrong-file citation was a format problem (VS-024 fixes that)
  or a sourcing problem (this ticket's concern) — VS-024's own ticket already
  states it does not fix wrong-file citation.
- **Blocks:** None. Does not block VS-025 or VS-027.

## Read first

- `ADR-2026-08-07-003-vs-023-sensor-tool-scoping.md` — the original
  deferral reasoning and the signal it set for revisiting.
- `docs/development/current/focus.md`'s active-priority section — the
  wrong-file citation finding.
- `VS-023-migration-evidence-sensor-tools.md`'s "Citation-sourcing
  enforcement follow-up" section — the first-match imprecision finding.
- `tests/evaluation/jpetstore-6-detailed-timing-and-citation-2026-08-07.md` —
  full detail on the wrong-file citation run.

## Scope

### In scope

- Determine, from the interactive run's transcript or a reproduction, whether
  the `docker-compose.yaml`/`Dockerfile` wrong-file citation was
  `locate_evidence`-sourced or hand-written (the specific open question
  `focus.md` leaves unresolved). This alone may resolve the question without
  new tooling: if it was hand-written, the existing "every citation must come
  from `locate_evidence`" enforcement already covers it and the finding is
  process (n=1, not yet a trend), not a Phase 2 case.
- If it was `locate_evidence`-sourced, re-evaluate `ADR-2026-08-07-003`'s
  Phase 2 proposal (the five ecosystem-aware tools) against this and the
  `INSERT INTO` finding together, and record a decision: build a narrow
  subset (e.g. a Dockerfile/Compose-only disambiguator, short of the full
  five-tool proposal), build the original Phase 2 set, or hold given
  insufficient sample size (n=2 across two different failure shapes).

### Out of scope

- Implementing any Phase 2 tool before this ticket's decision is recorded —
  same discipline VS-023 itself followed.
- Re-opening VS-023 Phase 1 or its enforcement rules.

## Implementation steps

1. Reproduce or inspect the interactive Detailed run's tool-call trace to
   settle the `locate_evidence`-sourced-vs-hand-written question.
2. If needed, run a few more live Detailed/Summary repeats against
   repositories with a Dockerfile *and* a docker-compose file to see whether
   the confusion recurs (build a small sample before deciding, not a single
   anecdote).
3. Write the decision as an addendum to this ticket or a new ADR, following
   `ADR-2026-08-07-003`'s format, referencing both this ticket's evidence and
   the original Phase 2 proposal in `VS-023-migration-evidence-sensor-tools.md`.

## Acceptance criteria

- A recorded decision (build subset / build full Phase 2 / hold) with
  reasoning tied to the specific evidence in this ticket, not a restatement
  of `ADR-2026-08-07-003`.
- If "hold" is chosen, the specific signal that would trigger revisiting
  again is stated (as `ADR-2026-08-07-003` did).

## Verification commands

```bash
python scripts/run_quality_gate.py
```

(No implementation verification until a decision selects one — this ticket's
own acceptance criterion is the decision record itself.)

## Expected file changes

- This ticket file (decision outcome section)
- A new `ADR-2026-08-07-*` or `ADR-2026-08-08-*` file if the decision
  warrants one (recommended — matches the existing pattern for scoping
  reversals)

## Commit boundary

- A single docs-only commit recording the decision. No code changes unless
  the decision is "build," in which case implementation is a separate,
  later ticket/commit.

## Codex execution instruction

```text
Implement only VS-026. This is a scoping/decision ticket -- do not write any
new sensor-tool code. First determine whether the docker-compose.yaml
wrong-file citation described in focus.md was locate_evidence-sourced or
hand-written. Read ADR-2026-08-07-003 and VS-023's citation-sourcing
follow-up section before concluding. Record the decision (build subset /
build full Phase 2 / hold, with the revisit signal if holding) as an
addendum to this ticket or a new ADR. Do not implement Phase 2 tools in this
pass even if the decision favors building them.
```
