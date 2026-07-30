# TICKET-LIST-2026-07-30-006: Secret-safe evidence boundary

- Status: Active
- Governing decision: [ADR-2026-07-30-009-secret-safe-evidence-boundary.md](ADR-2026-07-30-009-secret-safe-evidence-boundary.md)

## Goal

Prevent repository credential literals from reaching the analysis model or a
user-facing Kubernetes migration report while preserving actionable evidence
locations and classifications.

## SEC-001 — Safe repository evidence ingress and report egress

### Work

- Add one safe evidence adapter that redacts credential literals before any
  model-visible read, search, or file chunk is returned.
- Route every permitted target-repository discovery and evidence operation
  through that adapter; revoke native target-content read, grep, and shell
  permissions from the analysis agent.
- Add one report-delivery egress that rejects any remaining credential literal.
- Preserve path, line range, and the `credential-shaped demo seed data`
  classification without values, hashes, prefixes, suffixes, or encoded forms.
- Add canary-based unit, transcript, and detached-`tmux` E2E coverage.

### Acceptance criteria

- A planted canary is absent from every model-visible tool result, transcript,
  final report, and retained diagnostic artifact.
- Safe evidence still reports the source path, line range, and finding class.
- Chunked reads, searches, one-level encoded forms, and tool-returned text do
  not bypass redaction.
- The analysis agent has no native target-content read, grep, or shell path.
- JPetStore Detailed E2E leaves the target Git status unchanged and emits no
  credential literal.

### Verification

- Run focused adapter, report-validator, and permission-contract tests.
- Run the applicable Quality Gate.
- Run the documented isolated detached-`tmux` JPetStore Detailed E2E with
  approved network permission and compare target Git status before and after.

## Delivery order and commit boundary

Implement and commit `SEC-001` as one focused security-boundary change. Do not
include unrelated Detailed evidence-budget or Summary contract cleanup.
