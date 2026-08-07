# VS-028 — Make component inventory and workload-boundary consultation unconditional

## Outcome

Candidate identification (`SKILL.md`'s `## Analysis contract`) treats a start
command documented only in README/docs prose as inventory evidence on equal
footing with a Dockerfile/Compose/CI artifact whenever no declarative
container or process config exists, and `references/workload-boundary.md` is
consulted against the full candidate list before `components` is finalized —
in both Summary and Detailed — instead of being gated behind the model's own,
already-falsified, sense that "more than one runtime process is plausible."

## Why this is a vertical slice

This supersedes this ticket's original, narrower framing ("teach the model to
weight prose evidence"). Tracing the `flask-celery-example` failure back
through the actual prompt/reference chain shows the defect sits in two
authoritative places, not in a missing weighting rule:

1. **`SKILL.md:97-98` (`## Analysis contract`, the section `workflow.md:3-4`
   names as the single owner of evidence semantics):** "A manifest,
   dependency, script, Dockerfile, Compose service, or CI job is evidence,
   not a deployment conclusion." README/docs prose is not in this list.
   `references/workflow.md:34` compounds this: "Use README, CI, logs,
   migrations, tests, and broad source-tree reads **only when a first-pass
   finding needs evidence**" — i.e. confirmatory, never a primary inventory
   source. In a repository with no Dockerfile/Compose/Procfile/k8s manifest
   (exactly `flask-celery-example`'s shape), README is not "only" a
   confirmatory source — it is the *sole* source, and the current wording
   never promotes it.
2. **`references/workflow.md:47-51`:** "Route to ... [workload-boundary]
   references only after the corresponding finding exists -- workload-
   boundary applies when more than one runtime process or start command is
   plausible." This treats the boundary decision as a reactive sub-step of
   classification, contingent on the model already having noticed two
   candidates. But the boundary rule's own job is partly to *decide whether
   there are two candidates in the first place* (its contrastive examples —
   `uvicorn app:api` / `celery -A app worker` sharing one directory — are
   about surfacing a split, not just adjudicating one already surfaced). Its
   consultation being gated on the very ambiguity it exists to resolve is
   circular: nothing forces the file to be read before the model has already
   (silently, by omission) resolved the split question in favor of "one
   component."

`runtime/agents/kubernetes-migration-analyzer.md` mirrors both flaws twice:
[VS-025](VS-025-summary-workload-boundary.md)'s new Summary-mode sentences
("When more than one runtime process or start command is plausible, ...")
and Detailed's pre-existing sentence at the same location ("... or
`references/workload-boundary.md` (when more than one runtime process or
start command is plausible)") both inherit the same circular trigger — VS-025
copied it from Detailed rather than introducing it. **This means Detailed
mode has carried this exact gap, untested, since before this session**; it is
not a Summary-specific defect and belongs in this ticket's scope rather than
staying out of it.

Live evidence (2026-08-07, `upstage/solar-pro2`, 2 completed repeats,
`flask-celery-example` pinned to `76f785ebe6a049e873a8c28b4f25686b64c4fa55`):
the model read `README.md` in full, including line 21's explicit Celery
worker start command, and both times folded it into the Flask component's
`fields`/internal-summary text rather than surfacing it as a second
candidate. `references/workload-boundary.md` was never read in either trace
(only named in the Skill's sampled file listing). The run artifacts
themselves live in a scratch directory outside this repository and were not
preserved; this section is the only durable record.

## Status and dependencies

- **Status:** Proposed — scope revised 2026-08-07 after live reproduction;
  not yet implemented.
- **Depends on:** None. Does not depend on or block on VS-025 landing (it
  already has), but changes text VS-025 just added.
- **Blocks:** [VS-027](VS-027-workload-boundary-golden-fixtures.md)'s
  planned must-split Case B fixture will very likely fail on this gap before
  it ever exercises `workload-boundary.md`'s actual rule, unless Case B's
  fixture uses only declarative (Dockerfile/Compose) evidence to sidestep
  it, or this ticket lands first.

## Read first

- `SKILL.md`'s `## Analysis contract` (~line 95-126) and `## Completion gate`
  (~line 145-150) — the two sections this ticket edits at the root.
- `references/workflow.md`'s `## 1. High-signal inventory` and
  `## 2. Analyze in one pass` — the same defect, restated for the workflow
  layer `SKILL.md` delegates to.
- `runtime/agents/kubernetes-migration-analyzer.md` — both the Summary
  sentences [VS-025](VS-025-summary-workload-boundary.md) added and
  Detailed's pre-existing conditional-load sentence (originally around line
  155-161 before VS-025's edits shifted line numbers).
- `references/workload-boundary.md` — confirm its own text needs no change;
  the fixture never reached its rule, so there is no evidence the rule
  itself is wrong. This ticket only changes when/what feeds into it.
- This ticket's "Why this is a vertical slice" section — the only surviving
  record of the live reproduction.

## Scope

### In scope

- `SKILL.md`'s `## Analysis contract`: add prose-documented start commands
  (README, docs) as evidence on par with Dockerfile/Compose/CI, scoped to
  "when no declarative container or process artifact exists" so it doesn't
  encourage over-reading README in the common case where a Dockerfile/Compose
  already answers the question.
- `SKILL.md`'s `## Completion gate`: name `references/workload-boundary.md`
  explicitly as something to check the full candidate list against before
  returning a report, rather than the current unanchored "confirm ... all
  independent runtime components."
- `references/workflow.md` §1: stop treating README as confirmatory-only;
  promote it to first-pass inventory evidence under the same "no declarative
  artifact exists" condition as the `SKILL.md` change.
- `references/workflow.md` §2: remove the "only after the corresponding
  finding exists" gating for workload-boundary specifically (language-
  discovery/configuration-timing/dependency-analysis's existing conditional
  gating is out of scope and stays as-is — their trigger conditions are
  externally observable, not self-referential the way this one is).
- `runtime/agents/kubernetes-migration-analyzer.md`: update VS-025's Summary
  sentences and Detailed's pre-existing sentence to the same
  "always consult before finalizing components, regardless of perceived
  ambiguity" framing; update both worked examples if the shape of an example
  needs to change.
- Explicitly bringing Detailed's existing wiring into scope (a deliberate,
  reasoned expansion past VS-025's "Out of scope: Changing Detailed mode's
  existing wiring" boundary, justified above, not silent scope creep).

### Out of scope

- `references/workload-boundary.md`'s own primary/supporting rule text.
- The other conditional references' (language-discovery-rules,
  configuration-timing, dependency-analysis) gating — their trigger
  conditions are not self-referential like this one.
- Building VS-027's fixtures/golden-set rubric.
- Any change motivated only by this one fixture's specific repo shape (e.g.
  hardcoding "celery" anywhere) — the fix must be evidence-type-general.

## Implementation steps

1. Reproduce the finding once more on a fresh clone, this time saving the
   run's `trace.json`/`payload.json` under `tests/evaluation/` or similar so
   the evidence survives past the session.
2. Edit `SKILL.md`'s `## Analysis contract` and `## Completion gate` per
   scope above.
3. Edit `references/workflow.md` §1 and §2 per scope above.
4. Edit `runtime/agents/kubernetes-migration-analyzer.md`'s Summary sentences
   (from VS-025) and Detailed's conditional sentence; adjust worked examples
   if needed.
5. Re-run `slash-default-summary` and `slash-detailed` against the fixture,
   3 repeats each, and confirm the Celery worker now appears as a component
   (split, or an explicitly evidenced `미확인` boundary via `missing_inputs`
   / `범위`+`결정` per mode) rather than silently disappearing.
6. Re-run the JPetStore 6 golden scenario for both modes to confirm no
   regression from the broadened evidence-type and unconditional-consultation
   changes.
7. Run the quality gate.

## Acceptance criteria

- The `flask-celery-example` fixture produces a second candidate entry (or an
  explicitly evidenced open boundary decision) for the Celery worker, in at
  least 3 live repeats, for both Summary and Detailed.
- No regression in the JPetStore 6 golden-set score for either mode.
- `python scripts/run_quality_gate.py` passes.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root <flask-celery-example clone> --repeat 3 --model upstage/solar-pro2 --output-dir <dir>
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-detailed --repository-root <flask-celery-example clone> --repeat 3 --model upstage/solar-pro2 --output-dir <dir>
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root <jpetstore-6 clone, pinned per tests/evaluation/jpetstore-6-golden.md> --repeat 3 --model upstage/solar-pro2 --output-dir <dir>
```

## Expected file changes

- `SKILL.md`
- `references/workflow.md`
- `runtime/agents/kubernetes-migration-analyzer.md`
- `tests/` (prompt/contract regression coverage, and ideally the preserved
  fixture-run evidence from implementation step 1)

## Commit boundary

- Land this scoping/decision note (already done, this revision) separately
  from the implementation, per the VS-020/VS-023/VS-025 precedent.
- Commit the `SKILL.md`/`workflow.md`/agent-prompt changes and their tests
  together as one focused commit; do not bundle with VS-026 or VS-027.

## Codex execution instruction

```text
Implement only VS-028. Read this ticket's "Why this is a vertical slice"
section first -- it cites exact line numbers in SKILL.md and
references/workflow.md for the two root-cause sections. Do not touch
references/workload-boundary.md's own rule text; the defect is upstream, in
(a) SKILL.md's Analysis contract restricting inventory evidence to
declarative artifacts, and (b) workflow.md/the agent prompt gating
workload-boundary consultation behind an already-perceived finding instead
of running it unconditionally before finalizing components. Fix both mode's
wiring (Summary and Detailed both inherit this). Reproduce against
github.com/miguelgrinberg/flask-celery-example (Flask app + Celery worker,
distinct start commands, README-only evidence, no Dockerfile/Compose) before
and after the fix, 3 repeats per mode, and preserve the run artifacts under
tests/ this time instead of a scratch directory. Re-run the JPetStore 6
golden scenario for both modes to confirm no regression. Run the quality
gate and report the result.
```
