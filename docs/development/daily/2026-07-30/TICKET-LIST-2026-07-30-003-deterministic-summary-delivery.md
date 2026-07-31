# TICKET-LIST-2026-07-30-003: Deterministic Summary delivery

- Date: 2026-07-30
- Decision: [ADR-2026-07-30-004](ADR-2026-07-30-004-deterministic-summary-delivery.md)
- Scope: make the existing OpenCode Summary command return only validated
  Summary v2 Markdown without requiring a separate user CLI.

## Order

```text
DEL-001 JSON/display contract -> DEL-002 JSON-only Agent -> DEL-003 harness finalizer -> DEL-004 E2E gate
```

## DEL-001 — Preserve internal enums and render Korean open-item labels

- Depends on: Summary v2 renderer and validator
- Result: JSON uses stable internal enums; users see Korean labels only.

### Work

Add one renderer mapping for the four open-item enums and make the Summary
Markdown validator validate the mapped Korean labels and verdict consistency.
Update the template, valid fixtures, and Golden Summary. Do not rename JSON
enums or alter Detailed output.

### Acceptance and verification

- Each enum renders as its specified Korean label.
- Unknown enums and English display labels fail Summary validation.
- `hard_blocker` and verdict consistency remain enforced.
- Run targeted renderer/validator tests and `python3 scripts/run_quality_gate.py`.

## DEL-002 — Make the Summary Agent a JSON-only producer

- Depends on: DEL-001
- Result: a Summary request produces one contract-valid JSON payload rather
  than user-facing Markdown.

### Work

Update the Summary Agent and command instructions to require exactly one JSON
object, forbid progress text in the final payload, and require evidence,
classification, provenance, and verdict fields needed by the existing
renderer. Keep Detailed mode and unrelated-request routing unchanged.

### Acceptance and verification

- A Summary JSON payload is accepted by `validate_json_payload` and the
  renderer.
- A final response containing prose plus JSON is rejected by acceptance
  extraction.
- Detailed and permission acceptance cases remain unchanged.

## DEL-003 — Finalize Summary responses in the acceptance harness

- Depends on: DEL-002
- Result: the harness exposes validated Markdown without a separate user CLI.

### Work

The harness consumes the final Summary JSON, calls the existing renderer and
validators, finalizes the receipt only after success, and replaces its visible
result with that Markdown. On failure it presents a short failure message and
keeps raw JSON plus diagnostics in the run artifact. Do not add a plugin:
OpenCode 1.18 cannot replace a completed response through its plugin API.

### Acceptance and verification

- A valid JSON response produces one Markdown report with `Validation: passed`.
- Render/validation failure cannot display a successful receipt or raw JSON.
- Installer and distribution tests assert plugin placement and loading.

## DEL-004 — Gate the user-visible E2E result

- Depends on: DEL-003
- Result: E2E passes only when the rendered report, not raw Agent prose,
  satisfies Summary v2.

### Work

Extend the acceptance harness to retain JSON, rendered Markdown, diagnostics,
and target repository status. Validate the rendered report with the target as
`--repo-root`; treat JSON extraction, rendering, validation, receipt, or target
mutation failures as E2E failures.

### Acceptance and verification

- E2E final output begins with `# Kubernetes 설계 입력 요약` and has no progress
  text before it.
- It includes the v2 marker, five required sections, Korean open-item labels,
  valid evidence, and `Validation: passed`.
- The analyzed repository remains unchanged.
- Run the 6-minute OpenCode Summary E2E and `python3 scripts/run_quality_gate.py`.
