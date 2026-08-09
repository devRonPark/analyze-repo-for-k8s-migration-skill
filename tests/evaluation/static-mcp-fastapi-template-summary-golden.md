# Static MCP Golden — FastAPI Template Summary

- Case: `fastapi-template-summary`
- Target: `C:\temp\opencode-e2e-fastapi`
- Revision: `d506ea4883c0f7bfcf5280921cfc407c46808711`
- Evidence date: 2026-08-09
- Evidence basis: independent static inspection of the pinned local repository.

## Required findings

- The repository defines a FastAPI backend and a React frontend built into and served from the backend image (`README.md:9-14`).
- Compose defines a PostgreSQL service with durable `app-db-data`, a backend health endpoint on port 8000, and a `prestart` job that waits for PostgreSQL health (`compose.yml:3-19`; `compose.yml:44-56`; `compose.yml:88-112`; `compose.yml:138-141`).
- Backend and prestart use environment-backed database, application-secret, SMTP, and Sentry settings (`compose.yml:60-76`; `compose.yml:93-109`); no values may be exposed.
- Traefik labels and the external `traefik-public` network are existing deployment-environment evidence (`compose.yml:25-34`; `compose.yml:115-141`), not proof that an Ingress choice is complete.

## Required blockers and unknowns

- PostgreSQL ownership, secret provisioning, prestart/migration job semantics, and external Traefik/TLS/network integration require scoped design decisions.
- Do not invent Kubernetes resource defaults, an Ingress resource, database ownership, or secret values.

## Scoring weights

- Report completion and Summary contract: 20
- Candidate, build, runtime, and reachable port facts: 30
- State and dependency facts: 25
- Configuration and security risk: 15
- Evidence discipline and decision usefulness: 10
