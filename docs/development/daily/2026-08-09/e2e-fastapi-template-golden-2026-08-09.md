# FastAPI template Summary golden set

- Target: `C:\temp\opencode-e2e-fastapi`
- Revision: `d506ea4883c0f7bfcf5280921cfc407c46808711`
- Evidence date: 2026-08-09

Required grounded findings:

- the repository defines a FastAPI backend and a React frontend built into and served from the backend image (`README.md`);
- Compose defines backend port 8000, health endpoint `/api/v1/utils/health-check/`, and a `prestart` one-shot command dependent on PostgreSQL health (`compose.yml`);
- PostgreSQL persists to `app-db-data` (`compose.yml`), so durable data and migration/prestart handling are material design inputs;
- the deployment uses environment-backed database, JWT/secret, SMTP, and Sentry settings; values must not be exposed;
- Traefik routing/HTTPS labels and an external `traefik-public` network are existing deployment-environment evidence, not a claim that an Ingress has been chosen.

Required uncertainty/blocker:

- platform ownership for PostgreSQL, external ingress/TLS/network integration, secret provisioning, and prestart job semantics remain scoped design decisions; do not invent Kubernetes resource defaults.

Scoring weights: report contract 20, candidate/build/runtime/network 30, state/dependencies 25, security/configuration 15, evidence discipline/decision usefulness 10.
