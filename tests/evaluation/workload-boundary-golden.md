# Workload Unit boundary golden set (Case A / Case B)

This is an independent, static-evidence baseline for scoring the Workload
Unit boundary decision (`references/workload-boundary.md`) against two
purpose-built fixtures. It was prepared without loading the Skill or its
references and does not execute either target repository. Both fixtures are
in-repo and read-only; there is no external checkout to pin a revision
against, so each entry below cites the fixture path directly.

This golden set exists because `tests/evaluation/jpetstore-6-golden.md` is a
single deployable Java web application with an embedded database -- it never
presents a candidate second process, so it has never exercised the Primary
rule's split-or-merge judgment end to end (see
`docs/development/tickets/VS-027-workload-boundary-golden-fixtures.md`).

## Case A -- must NOT split

- Target: `tests/fixtures/workload-boundary/case-a-single-process`
- Fixture type: static, in-repo, read-only (no build, install, or execution
  required or permitted)
- Instantiates: `references/workload-boundary.md`'s second contrastive
  example (`controller/`, `service/`, `repository/` under a single
  `java -jar app.jar` start command).

### Expected component count

**1 Workload Unit** (`배포 대상 후보` count = 1). `controller/`, `service/`,
and `repository/` must be reported as code layers inside that one component,
never as separate candidates or separate Workload Units.

### Required factual findings

| Area | Golden finding | Direct evidence |
| --- | --- | --- |
| Deployable unit | One deployable process, `petstore-app`, packaged as a single jar. | `pom.xml:4` (`<artifactId>petstore-app</artifactId>`), `pom.xml:6` (`<packaging>jar</packaging>`) |
| Start command | Exactly one production start command exists: `java -jar app.jar`. | `Dockerfile:4` |
| Internal layering | `controller/`, `service/`, `repository/` are Java packages under one `Application` entrypoint, not separate processes. | `src/main/java/com/example/petstore/Application.java`, `.../controller/PetController.java`, `.../service/PetService.java`, `.../repository/PetRepository.java` |
| Second-process search | No second entrypoint, process-manager entry, Dockerfile `CMD`, Compose service, or deployment descriptor exists anywhere in the fixture. | absence search over the fixture tree |

### Expected boundary evidence and reasoning

Applying the Primary rule: only one distinct production start command exists
(`java -jar app.jar`) and only one operational lifecycle is evidenced (one
process, one `Dockerfile` `CMD`). Condition 1 (distinct start commands) is
not met for any second candidate, so the Primary rule's two-condition test
fails at the first condition -- the analysis must not reach for a second
condition using package names alone. Per "Do not separate on these alone,"
`controller/`, `service/`, `repository/` are source modules / code layers,
not evidence of a second Workload Unit. Correct output: one component,
zero split, and package directory names must not be cited as boundary
evidence.

## Case B -- must split

- Target: `tests/fixtures/workload-boundary/case-b-two-processes`
- Fixture type: static, in-repo, read-only (no build, install, or execution
  required or permitted)
- Instantiates: `references/workload-boundary.md`'s first contrastive
  example (distinct start commands with independent scaling, in one source
  root).

### Expected component count

**2 Workload Units** (`배포 대상 후보` count = 2): `api` and `worker`. They
must be reported as separate components even though they share one source
root and one `docker-compose.yaml`.

### Required factual findings

| Area | Golden finding | Direct evidence |
| --- | --- | --- |
| Process 1 (`api`) | A Flask process started by `python app.py`, in its own file and directory. | `api/app.py:16-17`, `docker-compose.yaml:4` |
| Process 2 (`worker`) | A queue-processing loop started by `python worker.py`, in its own file and directory, sharing no file with `api/app.py`. | `worker/worker.py:15-16`, `docker-compose.yaml:11` |
| Distinct start commands | `docker-compose.yaml` declares `command: python app.py` for `api` and `command: python worker.py` for `worker` -- two distinct commands. | `docker-compose.yaml:4`, `docker-compose.yaml:11` |
| Independent lifecycle | `api` and `worker` declare different `restart` policies (`always` vs `on-failure`) and only `worker` declares `deploy.replicas: 3` -- independent scaling. | `docker-compose.yaml:7`, `docker-compose.yaml:12-14` |
| No shared lifecycle | Each service has its own `Dockerfile` and build context (`./api`, `./worker`); neither process imports, starts, or supervises the other. | `docker-compose.yaml:3`, `docker-compose.yaml:10`, `api/Dockerfile`, `worker/Dockerfile` |

### Expected boundary evidence and reasoning

Applying the Primary rule: condition 1 (distinct start commands) is met --
`python app.py` versus `python worker.py`. Condition 2 (independent
operational lifecycle) is also met -- distinct `restart` policies and
`worker`-only `replicas: 3` in `docker-compose.yaml` show they are started,
restarted, and scaled apart from each other. Both conditions hold, so the two
processes must be reported as separate Workload Units even though they sit
in one source root and one Compose file -- sharing a directory or a Compose
file is not, by itself, a reason to merge them (mirrors the reference's own
"even sharing one directory" clause). The Supporting rule evidence (separate
`Dockerfile`s, separate build contexts, separate `requirements.txt`) may be
cited as reinforcing, but must not be presented as the reason for the split
by itself -- the Primary rule's two conditions are the reason.

## Scoring: Workload Unit boundary precision/recall

Score this dimension per live run, independent of every other scored
dimension in a run's scorecard:

- Treat Case A as a negative instance (the correct decision is "do not
  split"). A run that reports 1 component = a true negative. A run that
  reports 2+ components for Case A, or cites `controller/`/`service/`/
  `repository/` as boundary evidence = a false positive.
- Treat Case B as a positive instance (the correct decision is "split"). A
  run that reports 2 components (`api`, `worker`) = a true positive. A run
  that reports 1 merged component for Case B = a false negative.
- Precision = true positives / (true positives + false positives) across all
  scored repeats of both cases.
- Recall = true positives / (true positives + false negatives) across all
  scored repeats of both cases.
- A run that reports the correct component count but for the wrong reason
  (e.g. splits Case B because of "two directories" rather than distinct
  start commands and independent lifecycle, or merges Case A but also
  mislabels a code layer as `미확인`) is scored correct on count but flagged
  separately as a reasoning defect in the scorecard's assessment column --
  it does not change the precision/recall tally, which is decision-only.
