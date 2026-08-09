# Flask-Celery Summary golden set

- Target: `C:\temp\opencode-e2e-flask-celery`
- Revision: `76f785ebe6a049e873a8c28b4f25686b64c4fa55`
- Evidence date: 2026-08-09

Required grounded findings:

- the Flask web process starts with `python app.py`, runs in debug mode, and serves `localhost:5000` (`app.py`, `README.md`);
- a Celery worker is an independently started runtime process (`README.md`);
- Redis is the broker/result backend at `redis://localhost:6379/0` (`app.py`) and is an external runtime dependency, not a deployment candidate from this repository;
- SMTP configuration and mail credentials are environment-backed, while `SECRET_KEY` is hard-coded in `app.py` and must be reported only as a location/risk, never reproduced.

Required uncertainty/blocker:

- Redis ownership, mail/SMTP production configuration, and the separate web/worker workload boundary require Kubernetes design input; do not invent a Redis StatefulSet, secret values, or resource defaults.

Scoring weights: report contract 20, candidate/build/runtime/network 30, state/dependencies 25, security/configuration 15, evidence discipline/decision usefulness 10.
