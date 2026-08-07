# VS-028 — Recognize a second runtime-process candidate from README prose alone

## Outcome

The agent creates a `components` (Summary) or Detailed candidate entry for a
second runtime process whose only evidence is prose in a README documenting a
distinct start command (e.g. "open a third terminal and run `celery -A
app.celery worker`") — instead of folding it silently into the first
component's dependency/runtime-dependency fields without ever surfacing it as
a candidate to evaluate.

## Why this is a vertical slice

Live-verifying [VS-025](VS-025-summary-workload-boundary.md) (2026-08-07)
against a purpose-built fixture — `github.com/mybatis/jpetstore-6`'s sibling
test, `github.com/miguelgrinberg/flask-celery-example` pinned to
`76f785ebe6a049e873a8c28b4f25686b64c4fa55` — surfaced a gap upstream of
`references/workload-boundary.md` entirely. That reference governs how to
decide the boundary *between two already-identified process candidates*; this
fixture never got that far.

Two live Summary runs (`upstage/solar-pro2`, `run_opencode_acceptance.py
--case slash-default-summary`) against the fixture both:

- read `README.md` in full — the raw tool output in the run trace includes
  line 21 verbatim: `` 4. Open a third terminal window. ... Then start a
  Celery worker: `venv/bin/celery -A app.celery worker --loglevel=info`. ``
- produced exactly two `components` entries: the Flask app (`배포 대상
  후보`) and Redis (`저장소에 정의된 런타임 의존성`) — the Celery worker
  never appeared as a candidate, an exclusion, or any other entry.
- never read `references/workload-boundary.md`'s content — the only two
  trace occurrences of the string `workload-boundary` are the Skill's sampled
  file listing, not a read call. The "more than one runtime process or start
  command is plausible" trigger [VS-025](VS-025-summary-workload-boundary.md)
  wired never fired, because the model did not model the Celery worker as a
  second process candidate to begin with.

So VS-025's fix is correctly wired for the case it targets (routing an
*already-recognized* ambiguity through `missing_inputs`/component evidence),
but this fixture shows the trigger condition itself is unreliable when the
only evidence is prose in a README rather than a declarative multi-service
artifact (`docker-compose.yaml`, `Procfile`, Kubernetes manifests). Both
Detailed's existing wiring and VS-025's new Summary wiring share this same
upstream blind spot. [VS-027](VS-027-workload-boundary-golden-fixtures.md)'s
planned Case B fixture ("two runtime processes in one source root ... with
distinct start commands") is exactly this scenario — attempting VS-027
without addressing this first will very likely score a hard fail on Case B
for a different reason than the boundary rule being wrong.

## Status and dependencies

- **Status:** Proposed — not yet scoped in detail or implemented.
- **Depends on:** None strictly, but informs how VS-027's Case B fixture
  should be built and scored.
- **Blocks:** Makes [VS-027](VS-027-workload-boundary-golden-fixtures.md)'s
  Case B likely to fail for a candidate-discovery reason, not a boundary-rule
  reason, unless read together with this ticket's outcome.

## Read first

- This ticket's "Why this is a vertical slice" section — the only record of
  the live reproduction; the run artifacts themselves were written to a
  scratch directory outside this repo and were not preserved.
- `runtime/agents/kubernetes-migration-analyzer.md`'s Summary bounded-pass
  paragraph (the "read only target files needed to support a required
  finding" instruction) and its `## Analysis contract` equivalent in
  `SKILL.md` — where candidate identification actually happens, upstream of
  `workload-boundary.md`.
- `references/workload-boundary.md` — confirm its primary rule assumes a
  candidate has already been identified; it has no instruction for *finding*
  candidates in the first place.
- [VS-025](VS-025-summary-workload-boundary.md)'s "Decision outcome" section
  — what it did and did not fix, for the boundary between these two tickets.

## Scope

### In scope

- Reproduce this finding once more (a fresh clone of
  `github.com/miguelgrinberg/flask-celery-example`, or an equivalent minimal
  fixture) to confirm it is not a one-off model sampling artifact before
  changing any prompt text.
- Decide where "a distinct start command documented only in prose (README,
  CONTRIBUTING, comments) is itself candidate evidence" belongs: most likely
  the `## Analysis contract` / candidate-identification instructions in
  `SKILL.md` or the agent prompt's bounded-pass paragraph, not
  `workload-boundary.md` itself (that reference already correctly assumes a
  candidate list exists).
- Update the relevant instruction so a second explicit start command found in
  README/docs text is treated as candidate evidence with the same weight as
  a Dockerfile `CMD`/Compose service, triggering the same "more than one
  runtime process is plausible" signal VS-025 and Detailed both already key
  off of.

### Out of scope

- Changing `references/workload-boundary.md`'s primary/supporting rule text
  — the fixture never reached that rule, so there is no evidence it is
  wrong.
- Building VS-027's fixtures or golden-set rubric — this ticket only removes
  a confound from that measurement.
- Re-litigating VS-025's routing decision.

## Implementation steps

1. Reproduce the finding on a fresh clone; capture the trace evidence this
   time (do not let it live only in a scratch directory).
2. Identify the exact instruction gap (likely: candidate identification only
   keys off declarative artifacts, not documented commands in prose).
3. Update the instruction and worked example accordingly.
4. Re-run the same fixture 3x and confirm the Celery worker now appears as a
   candidate (split or explicitly `미확인`, evidenced either way).
5. Re-run the JPetStore 6 golden scenario to confirm no regression.

## Acceptance criteria

- The `flask-celery-example` fixture (or an equivalent) produces a second
  candidate entry for the Celery worker, evidenced by the README start
  command, in at least 3 live repeats.
- No regression in the JPetStore 6 golden-set score.
- `python scripts/run_quality_gate.py` passes.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root <flask-celery-example clone> --repeat 3 --model upstage/solar-pro2 --output-dir <dir>
```

## Expected file changes

- `SKILL.md` and/or `runtime/agents/kubernetes-migration-analyzer.md`
- `tests/` (prompt/contract regression coverage)

## Commit boundary

- Land the reproduction-and-scoping note as a short commit before changing
  any prompt text, per this project's VS-020/VS-023/VS-025 precedent of
  separating the decision from the implementation.

## Codex execution instruction

```text
Implement only VS-028. Reproduce the finding first: clone
github.com/miguelgrinberg/flask-celery-example, run slash-default-summary
against it 3x, and confirm the Celery worker (README.md's `celery -A
app.celery worker` line) is missing from components. Do not touch
references/workload-boundary.md -- the gap is upstream, in candidate
identification. Find and fix the instruction that limits candidate evidence
to declarative artifacts (Dockerfile/Compose/manifests) instead of also
counting an explicit start command documented in README/docs prose. Re-run
the fixture and the JPetStore 6 golden scenario, run the quality gate, and
report the result.
```
