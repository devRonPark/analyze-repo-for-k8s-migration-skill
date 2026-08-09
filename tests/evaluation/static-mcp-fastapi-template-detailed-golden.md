# Static MCP Golden — FastAPI Template Detailed

- Case: `fastapi-template-detailed`
- Target: `C:\temp\opencode-e2e-fastapi`
- Revision: `d506ea4883c0f7bfcf5280921cfc407c46808711`
- Evidence date: 2026-08-09
- Evidence basis: independent static inspection of the pinned local repository.

## Required findings

- FastAPI backend and React frontend are one backend-image delivery unit according to the README (`README.md:9-14`).
- Compose declares PostgreSQL with an `app-db-data` volume and health check (`compose.yml:3-19`), a prestart command dependent on database health (`compose.yml:44-56`), and backend completion ordering plus health endpoint `/api/v1/utils/health-check/` on 8000 (`compose.yml:88-125`).
- Backend and prestart require environment-backed application, database, SMTP, and observability configuration (`compose.yml:60-76`; `compose.yml:93-109`), with values redacted.
- Traefik router/TLS labels and external `traefik-public` network are Compose deployment evidence (`compose.yml:25-34`; `compose.yml:115-141`).

## Required blockers and unknowns

- Preserve design decisions for PostgreSQL persistence/ownership, secret injection, migration/prestart completion semantics, external ingress/TLS/network integration, and operational ownership.
- Do not claim that Compose labels select a Kubernetes Ingress implementation or manufacture Kubernetes resource limits, probes beyond the evidenced health endpoint, or credentials.

## Scoring weights

- Report completion and Detailed contract: 20
- Candidate, build, runtime, and network facts: 25
- State, lifecycle, and dependency analysis: 25
- Configuration, security, and compatibility risks: 20
- Evidence discipline and decision usefulness: 10
