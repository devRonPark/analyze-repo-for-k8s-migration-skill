# VS-028 — Always-load `workload-boundary.md` and remove Detailed's stale one-component cap

## Outcome

`references/workload-boundary.md` is an unconditionally loaded reference in
both Summary and Detailed — the same tier as `workflow.md` and the mode
templates — instead of a conditionally loaded one gated behind the model's
own, weakly-evidenced sense that "more than one runtime process is
plausible." Separately, `runtime/agents/kubernetes-migration-analyzer.md`'s
stale Detailed-mode instruction capping `components` at exactly one entry is
corrected, since that cap would silently defeat this fix for Detailed even
if the loading change works perfectly.

## Revision history and why this version is narrower

This ticket has been rescoped three times. Recorded here so the same ground
isn't re-covered:

1. **First framing** ("teach the model to weight README prose as evidence"):
   ruled out — the model read the README fully; the failure wasn't about
   which files got read.
2. **Second framing** ("`SKILL.md`'s Analysis contract restricts inventory
   evidence to declarative artifacts"): ruled out by checking the fixture's
   `app.py` directly — `script` was already listed as evidence and the model
   read `app.py` in full, including the `celery = Celery(...)` instantiation
   and both `@celery.task` decorators.
3. **Third framing** ("candidate identification defaults to file/module
   granularity; fix by making `workload-boundary.md` consultation
   unconditional via more prose in `SKILL.md`/`workflow.md`/the agent
   prompt"): this diagnosis's *mechanism* survives independent review (see
   below), but its proposed *fix* does not, for two convergent reasons: (a)
   the conditional-load trigger this ticket wanted to reword already appears
   three times in the agent prompt and still didn't fire — a fourth,
   differently-worded copy is the same failure category, not a different
   one; (b) it never checked whether Detailed's output contract would even
   let the fix show up, and it didn't (see "Independent review findings"
   below — this was a real, separate, verified bug in the third revision's
   scope).

**This (fourth) revision's fix is mechanical rather than persuasive:** stop
asking the model to remember to consult the file, and instead put it in the
always-loaded set the same way `workflow.md` already is. This is smaller in
blast radius than the third revision (no `SKILL.md` Completion-gate change,
no `workflow.md` §1 README-reweighting change — both dropped, see Scope) and
does not add a fourth competing instruction to an already-dense prompt.

## Independent review findings (2026-08-07)

Before implementing the third revision, it was reviewed by three fresh,
independent sub-agent sessions (no shared context with each other or with
the session that wrote the diagnosis), each instructed to verify every cited
file:line claim against the actual repository rather than trust the ticket.
Findings that changed this revision:

- **LLM-behavior review:** the diagnosis's citations check out (`SKILL.md:97-98`,
  `references/workflow.md:47-51`, and the same conditional phrase duplicated
  three times in `kubernetes-migration-analyzer.md`), but the ticket's
  confidence was overstated: the only supporting evidence (2 repeats against
  `flask-celery-example`) ran on `upstage/solar-pro2`, a documented fallback
  provider (`memory/opencode-e2e.md`), not this project's intended default,
  and the raw run artifacts were not preserved — so alternative contributing
  causes (agent step-budget pressure; Summary's explicitly-designed early
  stopping) were never ruled out, only not observed. It also found this
  project already recorded, in `ADR-2026-08-07-002`, that "instruction-only
  fixes show diminishing returns" for this exact prompt — directly relevant
  and unaddressed by the third revision. Its recommended alternative
  (always-load the reference, mechanically, rather than reword the trigger)
  is what this revision adopts.
- **Architecture/regression review:** found that
  `kubernetes-migration-analyzer.md:333-335` currently instructs Detailed
  mode that it has "a hard output budget... **one** `components` entry" —
  verified against `scripts/render_detailed.py` (no such limit in the
  renderer) and `tests/test_render_detailed.py`'s
  `test_renders_multiple_candidate_cards` (already proves N>1 Detailed
  components render and validate correctly). This line is a stale artifact
  from `2984bd5` (DET-001, 2026-07-30, written when JPetStore 6 was the only
  target). The third revision's scope never touched this line, so even a
  perfect boundary-consultation fix would sit next to an unmodified,
  unambiguous "emit only one component" instruction for Detailed — almost
  certainly a self-defeating no-op. Also found `docs/development/current/focus.md`
  records VS-024's Detailed/JPetStore live baseline as still deferred/never
  run, so a "no regression vs. the Detailed baseline" acceptance criterion
  has no actual baseline to diff against yet.
- **Project-scope/priority review:** found the third revision's blast radius
  (editing `SKILL.md`'s core Analysis contract and Completion gate — shared
  by every run regardless of repo shape) was larger than this project's
  established VS-020/VS-023/VS-025 pattern of a minimal, existing-channel
  fix touching one file for one mode. It also found the third revision
  itself already names the cheaper unblock for
  [VS-027](VS-027-workload-boundary-golden-fixtures.md): build Case B's
  fixture with its two processes in genuinely separate files/directories,
  which sidesteps this specific shared-file failure mode entirely and does
  not need to wait on this ticket.

## Status and dependencies

- **Status:** Proposed — fourth revision, narrowed after independent review;
  not yet implemented.
- **Depends on:** None.
- **Blocks:** Nothing, if [VS-027](VS-027-workload-boundary-golden-fixtures.md)
  builds Case B with its two processes in separate files (recommended — see
  above) rather than waiting on this ticket.

## Read first

- This ticket's "Revision history" and "Independent review findings"
  sections — the durable record of two ruled-out diagnoses and the review
  findings that narrowed this version.
- `runtime/agents/kubernetes-migration-analyzer.md` lines ~333-335 (the
  stale Detailed one-component cap) and its Summary/Detailed
  `workload-boundary.md` load sentences.
- `references/workflow.md` §1-2 and `SKILL.md`'s `## Analysis contract` —
  read for context; most of what the third revision proposed changing here
  is now out of scope (see below).
- `references/workload-boundary.md` — still unchanged; still no evidence its
  rule text itself is wrong, only that it wasn't being read.
- `scripts/render_detailed.py` and `tests/test_render_detailed.py`'s
  `test_renders_multiple_candidate_cards` — confirms the renderer already
  supports N>1 Detailed components; this ticket only needs to stop telling
  the model not to use that support.

## Scope

### In scope

- `SKILL.md`'s Mode routing (~line 64-68, where `workflow.md` and the
  Summary template are already named as always-read): add
  `references/workload-boundary.md` to the always-read set for Summary.
- `runtime/agents/kubernetes-migration-analyzer.md`'s Detailed reference list
  (~line 172): move `workload-boundary.md` out of the conditional
  "(when more than one runtime process or start command is plausible)"
  clause into Detailed's unconditional load list, alongside the checklist
  and assessment template.
- `runtime/agents/kubernetes-migration-analyzer.md`'s Summary sentences added
  by [VS-025](VS-025-summary-workload-boundary.md) (the bounded-pass
  paragraph and the `components` field description): remove the conditional
  framing now that the file is always loaded; keep the instruction to apply
  its primary rule when deciding candidate boundaries.
- **`kubernetes-migration-analyzer.md:333-335`: remove or correct the "hard
  output budget... one `components` entry" cap for Detailed.** This is
  required, not optional — without it, the loading fix cannot produce a
  visible behavior change in Detailed mode. Confirm with
  `render_detailed.py`/`test_renders_multiple_candidate_cards` what the
  renderer actually supports before rewording, and update the Detailed
  worked example if its shape needs to change.
- One added sentence in `SKILL.md`'s `## Analysis contract`: file/module
  boundaries do not by themselves imply one candidate (cheap, directly
  targeted, reinforces the always-loaded reference's own point at the
  moment evidence is being classified).
- A static prompt-contract test asserting Detailed's text does not cap
  `components` at one entry, and that `workload-boundary.md` appears in both
  modes' unconditional-load lists (extend
  `tests/test_target_and_safety_contract.py`).

### Out of scope (moved from the third revision, not adopted this time)

- `SKILL.md`'s `## Completion gate` change — redundant once the reference is
  always loaded before finalizing; dropped to keep blast radius smaller per
  the project-scope review.
- `references/workflow.md` §1's README-confirmatory-only wording — a
  different mechanism (evidence-promotion timing, not boundary-consultation
  gating) bundled in by convenience in the third revision; worth its own,
  smaller follow-up ticket if a future case shows source code alone isn't
  sufficient evidence (this fixture didn't need it — `app.py` alone had
  enough).
- `references/workload-boundary.md`'s own rule text — still unchanged.
- Building VS-027's fixtures/golden-set rubric — recommend VS-027 proceeds
  independently with Case B fixture using separate files, not blocked on
  this ticket.

## Implementation steps

1. **Reproduce with preserved evidence before changing anything.** Clone
   `github.com/miguelgrinberg/flask-celery-example` again, and this time
   save `trace.json`/`payload.json` under `tests/evaluation/` (or equivalent)
   instead of a scratch directory. If the project's default local provider
   (`local-sglang`/Qwen) is reachable this session, prefer it over the
   `upstage/solar-pro2` fallback used previously, or run both, to address the
   LLM-behavior review's point that the only supporting evidence so far used
   a non-default provider.
2. Add `workload-boundary.md` to Summary's and Detailed's unconditional-load
   lists per Scope above.
3. Remove/correct the Detailed one-component cap at line ~333-335; verify
   against `render_detailed.py` what the renderer actually supports.
4. Add the one-sentence `SKILL.md` Analysis-contract clarification.
5. Add the static test(s) for the no-cap assertion and the always-load
   lists — cheap, run before any live model call.
6. Re-run `slash-default-summary` and `slash-detailed` against the fixture,
   3 repeats each, confirm the Celery worker now appears as its own
   candidate (split, or an explicitly evidenced `미확인` boundary) in both
   modes.
7. Re-run the JPetStore 6 golden scenario for Summary (has an existing
   baseline) to confirm no regression. For Detailed, note honestly in the
   result that no prior live JPetStore baseline exists (VS-024's is still
   deferred per `focus.md`) — this run establishes a first baseline, it is
   not a before/after diff; do not claim "no regression" for Detailed
   without that caveat.
8. Run the quality gate.

## Acceptance criteria

- The `flask-celery-example` fixture produces a second candidate entry (or
  an explicitly evidenced open boundary decision) for the Celery worker, in
  at least 3 live repeats, for both Summary and Detailed.
- A static test confirms Detailed's prompt text no longer caps `components`
  at one entry, and that `workload-boundary.md` is in both modes'
  unconditional-load lists.
- No regression in the JPetStore 6 Summary golden-set score. Detailed's
  JPetStore result is recorded as a first baseline, honestly labeled as
  such, not a regression claim.
- `python scripts/run_quality_gate.py` passes.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root <flask-celery-example clone> --repeat 3 --output-dir <dir>
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-detailed --repository-root <flask-celery-example clone> --repeat 3 --output-dir <dir>
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root <jpetstore-6 clone, pinned per tests/evaluation/jpetstore-6-golden.md> --repeat 3 --output-dir <dir>
```

## Expected file changes

- `SKILL.md`
- `runtime/agents/kubernetes-migration-analyzer.md`
- `tests/test_target_and_safety_contract.py` (or equivalent) and
  `tests/evaluation/` (preserved fixture-run evidence from step 1)

## Commit boundary

- Land this scoping/decision note (already done, this revision) separately
  from the implementation, per the VS-020/VS-023/VS-025 precedent.
- Commit the `SKILL.md`/agent-prompt changes and their tests together as one
  focused commit; do not bundle with VS-026 or VS-027.

## Codex execution instruction

```text
Implement only VS-028 (fourth revision). Read this ticket's "Revision
history" and "Independent review findings" sections first -- two earlier
diagnoses were checked and ruled out, and three independent reviews already
found the third revision's fix would not have worked. The fix is now
mechanical: move references/workload-boundary.md into Summary's and
Detailed's unconditional-load lists (like workflow.md and the templates
already are) instead of rewording the conditional trigger again. Critically,
also remove or correct kubernetes-migration-analyzer.md's ~line 333-335
"one components entry" cap for Detailed -- verify against
scripts/render_detailed.py and test_renders_multiple_candidate_cards that
the renderer already supports more than one component; without this fix the
loading change is a no-op for Detailed. Add one sentence to SKILL.md's
Analysis contract: file/module boundaries do not by themselves imply one
candidate. Add a static test locking both changes. Reproduce against
github.com/miguelgrinberg/flask-celery-example before and after, 3 repeats
per mode, save the run artifacts under tests/ instead of a scratch
directory, and use the project's default local provider if reachable this
session rather than only the upstage/solar-pro2 fallback. Re-run the
JPetStore 6 golden scenario for Summary to confirm no regression; for
Detailed, record the result as a first baseline, not a regression claim,
since no prior live Detailed/JPetStore baseline exists. Run the quality
gate and report the result.
```
