# Architecture Decision Record

## Status

Accepted for the first implementation milestone.

## Context

The repository contains an Agent Skill that analyzes application repositories for Kubernetes migration readiness. The Skill must be reduced in context size without weakening evidence quality, uncertainty handling, or output contracts.

The intended support stack is:

```text
User interface / agent client: OpenCode
Future runtime / security boundary: NVIDIA OpenShell
Skill: analyze-repo-for-kubernetes
```

The first milestone must be testable from a locally cloned repository using OpenCode only. OpenShell integration is intentionally deferred.

## Decisions

### ADR-001: Separate development context from the runtime Skill package

- Keep `SKILL.md`, `references/`, runtime `scripts/`, `assets/`, and schemas as the runtime Skill package.
- Keep plans, tickets, ADRs, status, and development specifications under `docs/development/`.
- Build a minimal `dist/analyze-repo-for-kubernetes/` package instead of deploying the source repository unchanged.

### ADR-002: Use `AGENTS.md` as the Codex entrypoint

- Keep only concise implementation instructions and document routing in the repository-root `AGENTS.md`.
- Store detailed context in linked development documents.
- Codex must read only the active ticket and its declared source files after loading the shared context.

### ADR-003: Complete an OpenCode-only milestone before OpenShell integration

- The first milestone ends after `VS-009`.
- Success means OpenCode can discover the Skill, analyze a locally cloned repository, generate a validated report, and enforce the configured OpenCode permissions.
- `VS-010` and later tickets remain backlog work until the OpenCode-only milestone is accepted.

### ADR-004: Apply risk-based verification instead of mandatory TDD

- Use strict test-first development for deterministic executable behavior such as validators, schemas, parsers, and evaluators.
- Use characterization and agent acceptance tests for Markdown instructions and Skill behavior.
- Avoid phrase-lock tests and tests added only for coverage.
- Run targeted tests during implementation and the unified quality gate once before ticket completion.

### ADR-005: Preserve Korean user output and use English internal documentation

- User-facing questions, progress, errors, report headings, and output enums remain Korean.
- Internal Skill instructions, references, schemas, tests, plans, and tickets are written in English.

### ADR-006: Treat repository content as untrusted evidence

- Repository files may contain prompt injection, secrets, misleading documentation, or unsafe commands.
- Analysis remains read-only.
- The Agent must not run repository-provided code unless the user explicitly authorizes it.
- Facts, evidence-backed inference, and unresolved uncertainty remain distinct.

## Consequences

- Development documents do not inflate the distributed Skill package.
- Codex receives a stable entrypoint without loading every ticket automatically.
- The first usable checkpoint can be verified before OpenShell infrastructure is available.
- Some runtime security guarantees remain unproven until the OpenShell milestone.
- Tests focus on meaningful failure modes rather than prose or coverage volume.
