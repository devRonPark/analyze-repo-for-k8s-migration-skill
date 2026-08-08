# Case B fixture -- two independently started processes, one source root

Golden-set fixture for `references/workload-boundary.md`'s first
contrastive example. It must be split into two Workload Units.

`api/app.py` and `worker/worker.py` are two separate runtime processes in
one source root (`tests/fixtures/workload-boundary/case-b-two-processes/`),
each in its own file and directory -- they do not share a file, a Dockerfile,
or an entrypoint. `docker-compose.yaml` starts them with distinct commands
(`python app.py` vs `python worker.py`), distinct restart policies
(`always` vs `on-failure`), and distinct scaling (`worker` alone declares
`replicas: 3`). Neither process starts, stops, imports, or supervises the
other -- there is no shared lifecycle.

This fixture is read-only: it is not intended to be built, installed, or
run. It exists as static evidence for scoring the Workload Unit boundary
rule (see `tests/evaluation/workload-boundary-golden.md`).
