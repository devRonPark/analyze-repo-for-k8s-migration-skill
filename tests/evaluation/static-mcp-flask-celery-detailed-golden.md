# Static MCP Golden — Flask-Celery Detailed

- Case: `flask-celery-detailed`
- Target: `C:\temp\opencode-e2e-flask-celery`
- Revision: `76f785ebe6a049e873a8c28b4f25686b64c4fa55`
- Evidence date: 2026-08-09
- Evidence basis: independent static inspection of the pinned local repository.

## Required findings

- The Flask process is a debug-mode Python web process on port 5000 (`app.py:129`; `README.md:21-23`).
- Celery worker startup is a separate command and therefore a distinct execution/lifecycle boundary (`README.md:21-22`).
- Redis is a runtime broker/result backend configured by application code (`app.py:22-30`), with no repository evidence that it is managed by this deployment.
- Mail server settings, environment-backed mail credentials, and a hard-coded `SECRET_KEY` are configuration/security facts (`app.py:11-19`); values must remain redacted.

## Required blockers and unknowns

- Decide web/worker workload ownership, Redis service ownership, secret injection, production SMTP, and debug-mode posture from scoped evidence.
- The inspected files do not establish a container image, durable writable-state design, health probe, ingress, or resource policy.
- Do not manufacture Redis, Secret, Service, Ingress, or resource manifests.

## Scoring weights

- Report completion and Detailed contract: 20
- Candidate, build, runtime, and network facts: 25
- State, lifecycle, and dependency analysis: 25
- Configuration, security, and compatibility risks: 20
- Evidence discipline and decision usefulness: 10
