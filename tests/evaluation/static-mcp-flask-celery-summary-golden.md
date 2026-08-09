# Static MCP Golden — Flask-Celery Summary

- Case: `flask-celery-summary`
- Target: `C:\temp\opencode-e2e-flask-celery`
- Revision: `76f785ebe6a049e873a8c28b4f25686b64c4fa55`
- Evidence date: 2026-08-09
- Evidence basis: independent static inspection of the pinned local repository.

## Required findings

- The Flask web process starts with `python app.py`, enables debug mode, and is documented at `localhost:5000` (`app.py:129`; `README.md:21-23`).
- A Celery worker is independently started from the web process (`README.md:21-22`), so web and worker workload boundary evidence must be retained.
- Redis is the configured broker and result backend at `redis://localhost:6379/0` (`app.py:22-30`); it is an external runtime dependency, not a repository deployment candidate.
- SMTP credentials are environment-backed and `SECRET_KEY` is hard-coded (`app.py:11-18`). Report only location/risk and never reproduce secret values.

## Required blockers and unknowns

- Redis ownership, production SMTP configuration, secret provisioning, and the separate web/worker workload boundary require scoped Kubernetes design input.
- Do not invent a Redis StatefulSet, secret values, resource defaults, or a production debug setting.

## Scoring weights

- Report completion and Summary contract: 20
- Candidate, build, runtime, and reachable port facts: 30
- State and dependency facts: 25
- Configuration and security risk: 15
- Evidence discipline and decision usefulness: 10
