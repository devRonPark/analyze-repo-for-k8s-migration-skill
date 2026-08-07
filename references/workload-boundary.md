# Workload Boundary Decision

A Workload Unit is an application process that should be operated
independently. Decide this before classifying candidates; it is what
`배포 대상 후보` boundaries are actually asking for.

## Primary rule

Treat two runtime processes as separate Workload Units only when both hold:

1. distinct production start commands or entrypoints;
2. an independent operational lifecycle -- started, stopped, restarted,
   scaled, or scheduled apart from the other process.

Both conditions are required. Evidence for only one is not a separation.

## Supporting rule

State, security, resource, or network differences strengthen a separation
already supported by the primary rule. They never create a separate
Workload Unit by themselves.

## Do not separate on these alone

- directory or package boundaries;
- source modules (`controller/`, `service/`, `repository/` are code layers
  inside one process, not workloads);
- listener ports;
- dependencies;
- configuration or Secret names.

## Unknown

When runtime-process or lifecycle evidence is insufficient, record the
boundary as `미확인` with its `검색(...)` scope rather than inferring one
from names or directory structure.

## Contrastive examples

- Distinct start commands with independent scaling (`node server.js` /
  `node worker.js`, or `uvicorn app:api` / `celery -A app worker` in the
  same directory) -> separate Workload Units, even sharing one directory.
- `controller/`, `service/`, `repository/` under a single
  `java -jar app.jar` start command -> one Workload Unit; these are code
  layers, not independently operated processes.
- A one-time `python migrate.py` distinct from the continuously running
  main process -> separate Workload Units: the two have different
  execution lifecycles (run-once vs. continuous), not one candidate with
  two commands.
- A documented recurring schedule (e.g. a daily `02:00` cleanup command)
  for an otherwise idle entrypoint -> a distinct Workload Unit with a
  scheduled lifecycle, not folded into the main process.
- One process exposing two ports (application and metrics), or one
  process reading several differently named Secrets -> one Workload Unit;
  ports and Secret names are supporting evidence at most, never sufficient
  alone.
- Two directories (`api/`, `worker/`) with no discovered start command,
  process-manager entry, Dockerfile `CMD`, Compose command, or deployment
  descriptor -> `미확인`, not a guess from directory names.
