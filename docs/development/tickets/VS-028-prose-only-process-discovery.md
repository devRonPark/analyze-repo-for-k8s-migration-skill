# VS-028 — Anchor candidate identification to start commands, not files, and make workload-boundary consultation unconditional

## Outcome

Candidate identification treats each distinct start command/entrypoint as a
separate candidate to evaluate — even when two such commands are defined in
the same file or module — and `references/workload-boundary.md` is consulted
against the full candidate list before `components` is finalized, in both
Summary and Detailed, instead of being gated behind the model's own,
already-falsified, sense that "more than one runtime process is plausible."

## Why this is a vertical slice

This ticket has been rescoped twice as the live reproduction was traced back
further. The first framing ("teach the model to weight prose evidence") and
the second ("`SKILL.md`'s Analysis contract restricts evidence to declarative
artifacts") are both **wrong** and superseded by this section — recorded here
so the mistake isn't silently repeated in a future pass.

**What actually happened, checked against the fixture's source directly**
(`flask-celery-example`'s `app.py`, pinned to
`76f785ebe6a049e873a8c28b4f25686b64c4fa55`):

```
app.py:10:  app = Flask(__name__)
app.py:30:  celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
app.py:34:  @celery.task
app.py:45:  @celery.task(bind=True)
app.py:128: if __name__ == '__main__':
```

`SKILL.md:97-98`'s `## Analysis contract` already lists `script` as evidence
("A manifest, dependency, **script**, Dockerfile, Compose service, or CI job
is evidence") — source code was never excluded. And the live trace confirms
the model *did* read `app.py` in full (cited at `app.py:22` for the Redis
broker URL, and named "Celery 작업 큐" in its own internal summary). So the
evidence-type restriction claimed in this ticket's prior revision does not
hold: the model had the Celery instantiation, both `@celery.task` decorators,
and Flask's own separate `if __name__` runner directly in front of it.

**The actual defect: candidate identification defaults to file/module-level
granularity, not start-command-level granularity.** Everything inside
`app.py` — the Flask routes and the Celery task definitions alike — got
treated as attributes of one candidate ("this is all one script") instead of
being recognized as evidence for two independently-invokable entities that
happen to share a file. This is precisely the mistake
`references/workload-boundary.md`'s own first contrastive example exists to
correct: "`uvicorn app:api` / `celery -A app worker` ... in the same
directory -> separate Workload Units, **even sharing one directory**." Had
that file been read before the candidate list was finalized, its own example
almost exactly matches this fixture's shape. It was not read.

Why it was not read: `references/workflow.md:47-51` gates it — "Route to ...
[workload-boundary] references only after the corresponding finding exists
-- workload-boundary applies when more than one runtime process or start
command is plausible." This makes consultation reactive to an ambiguity the
model must already have noticed on its own. But surfacing that exact
ambiguity (two start commands sharing one file) is part of what the
reference itself is for — gating it behind the thing it's supposed to help
recognize is circular. Nothing forces a read of the file before the model
has already (silently, by omission) resolved the grouping question in favor
of "one file, one candidate."

`runtime/agents/kubernetes-migration-analyzer.md` mirrors this circular gate
twice: [VS-025](VS-025-summary-workload-boundary.md)'s new Summary-mode
sentences ("When more than one runtime process or start command is
plausible, ...") and Detailed's pre-existing sentence at the same location
("... or `references/workload-boundary.md` (when more than one runtime
process or start command is plausible)") both inherit it — VS-025 copied the
phrasing from Detailed rather than introducing it. **Detailed mode has
carried this exact gap, untested, since before this session**; it is not a
Summary-specific defect and belongs in this ticket's scope, not out of it.

(A secondary, smaller observation, worth keeping but not leading with:
`references/workflow.md:34` still treats README/docs reads as confirmatory-
only — "only when a first-pass finding needs evidence" — which would matter
in a repository where source code alone doesn't evidence the second start
command and only a README documents it. That was not the deciding factor
here, since `app.py` alone already had sufficient evidence, but it is a real,
independent instance of the same "evidence exists but isn't promoted to
inventory status" pattern and can stay in scope as a smaller companion fix.)

Live evidence (2026-08-07, `upstage/solar-pro2`, 2 completed repeats):
`references/workload-boundary.md` was never read in either trace (only named
in the Skill's sampled file listing). The run artifacts themselves live in a
scratch directory outside this repository and were not preserved; this
section and the `app.py` line numbers above are the only durable record.

## Status and dependencies

- **Status:** Proposed — root cause corrected 2026-08-07 after checking the
  fixture's source directly (see above); not yet implemented.
- **Depends on:** None. Does not depend on or block on VS-025 landing (it
  already has), but changes text VS-025 just added.
- **Blocks:** [VS-027](VS-027-workload-boundary-golden-fixtures.md)'s
  planned must-split Case B fixture will very likely fail on this gap before
  it ever exercises `workload-boundary.md`'s actual rule, unless Case B's
  fixture is built so its two start commands can't be read as one file/one
  candidate, or this ticket lands first.

## Read first

- This ticket's "Why this is a vertical slice" section — the only surviving
  record of the live reproduction, including the corrected diagnosis and the
  two prior, wrong framings (kept intentionally as a record of what was
  ruled out and why).
- `SKILL.md`'s `## Analysis contract` (~line 95-126) and `## Completion gate`
  (~line 145-150).
- `references/workflow.md`'s `## 1. High-signal inventory` and
  `## 2. Analyze in one pass`.
- `runtime/agents/kubernetes-migration-analyzer.md` — both the Summary
  sentences [VS-025](VS-025-summary-workload-boundary.md) added and
  Detailed's pre-existing conditional-load sentence.
- `references/workload-boundary.md` — confirm its own text needs no change;
  the fixture never reached its rule, so there is no evidence the rule
  itself is wrong. This ticket only changes when it gets consulted and what
  counts as a candidate to run it against.

## Scope

### In scope

- `SKILL.md`'s `## Analysis contract`: state explicitly that a distinct
  start command/entrypoint is its own candidate even when it shares a file
  or module with another — file/module boundaries are not a merge signal,
  mirroring `workload-boundary.md`'s own "do not separate on directory or
  package boundaries alone" in the opposite direction (don't *merge* on
  file-sharing alone, either).
- `SKILL.md`'s `## Completion gate`: name `references/workload-boundary.md`
  explicitly as something to check the full candidate list against before
  returning a report, rather than the current unanchored "confirm ... all
  independent runtime components."
- `references/workflow.md` §2: remove the "only after the corresponding
  finding exists" gating for workload-boundary specifically (language-
  discovery/configuration-timing/dependency-analysis's existing conditional
  gating is out of scope and stays as-is — their trigger conditions are
  externally observable, not self-referential the way this one is).
- `references/workflow.md` §1: as a smaller companion fix, stop treating
  README as confirmatory-only when no declarative container/process artifact
  exists and source code alone doesn't evidence a second start command.
- `runtime/agents/kubernetes-migration-analyzer.md`: update VS-025's Summary
  sentences and Detailed's pre-existing sentence to the same "always consult
  before finalizing components, regardless of perceived ambiguity, and
  regardless of whether the candidates share a file" framing; update both
  worked examples if the shape of an example needs to change.
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
  hardcoding "celery" anywhere) — the fix must be evidence-general.

## Implementation steps

1. Reproduce the finding once more on a fresh clone, this time saving the
   run's `trace.json`/`payload.json` under `tests/evaluation/` or similar so
   the evidence survives past the session.
2. Edit `SKILL.md`'s `## Analysis contract` and `## Completion gate` per
   scope above.
3. Edit `references/workflow.md` §2 (primary) and §1 (companion) per scope
   above.
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
section first, including the two superseded framings recorded there --
the defect is NOT "README isn't evidence" or "SKILL.md restricts evidence
to declarative artifacts" (both were checked and ruled out; source code
was already in scope and was read). The actual defect: candidate
identification defaults to file/module-level granularity, so two distinct
start commands sharing one file (a Flask app object and a separately
invoked Celery worker object, both in app.py) get merged into one
candidate instead of being recognized as two. Fix SKILL.md's Analysis
contract to say file/module boundaries don't imply one candidate, and fix
workflow.md/the agent prompt so workload-boundary.md is consulted against
the full candidate list before finalizing components, not gated behind an
already-perceived finding. Fix both modes (Summary and Detailed both
inherit the circular gate). Do not touch workload-boundary.md's own rule
text. Reproduce against github.com/miguelgrinberg/flask-celery-example
before and after the fix, 3 repeats per mode, and preserve the run
artifacts under tests/ instead of a scratch directory. Re-run the
JPetStore 6 golden scenario for both modes to confirm no regression. Run
the quality gate and report the result.
```
