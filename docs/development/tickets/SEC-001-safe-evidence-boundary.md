# SEC-001 — Safe repository evidence ingress and report egress

## User value

Kubernetes migration reports identify credential exposure by location without
ever showing the credential value to the model or user.

## Scope

Implement ADR-2026-07-30-009's single safe evidence boundary and report egress
for the OpenCode analysis runtime. Preserve read-only target analysis,
repository-relative evidence paths, line ranges, and the existing Korean report
contract.

## Non-goals

- Credential-quality or value-comparison analysis.
- Repository-specific credential allowlists.
- A new planner, agent, output mode, or deployment artifact.
- Unrelated Summary or Detailed contract cleanup.

## Acceptance criteria

- The model can receive only redacted target evidence.
- The agent cannot bypass redaction with native reads, grep, shell, chunking,
  search output, encoded text, subtool output, or report writing.
- A report states `credential-shaped demo seed data` plus source location, not
  any literal or derivative.
- Canary tests prove absence from model-visible evidence, transcript, report,
  and retained diagnostics while retaining the expected path and line range.
- The JPetStore Detailed detached-`tmux` E2E is credential-literal-free and
  leaves target Git status unchanged.

## Required verification

- Focused safe-boundary, report-validator, runtime-permission, and canary
  transcript tests.
- Applicable Quality Gate.
- Approved-network detached-`tmux` JPetStore Detailed E2E using an isolated
  runtime, captured final response, and before/after target Git status.
