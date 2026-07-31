# TICKET-LIST-2026-07-30-001: Required improvement tickets

- Date: 2026-07-30
- Decision: [ADR-2026-07-30-001](ADR-2026-07-30-001-urgent-contract-ssots.md)
- Scope: eliminate only contract drift and filesystem partial-failure risks.

Do not include wholesale conditional-to-object refactoring, literal cleanup,
acceptance-runner splitting, enum conversion, immediate legacy removal, or
transactional acceptance-result files. Those are not prerequisites for the
risks in scope.

## Order

```text
TKT-001 identity SSOT → TKT-002 JSON contract SSOT → TKT-003 Markdown contract SSOT
                                                       ↓
                         TKT-004 atomic distribution replacement → TKT-005 atomic installation
```

## TKT-001 — Project identity SSOT

- Priority: P0
- Depends on: none
- Result: every runtime consumer reads `skill_id`, `agent_id`, `skill_version`,
  and `manifest_name` from `contracts/project-metadata.json`.

### Work

Add a validating Python loader and a small standard-library Python query CLI
for the shell installer. Replace direct identity definitions in the builder,
validator, acceptance harness, and installer without changing IDs, paths, or
manifest format.

### Acceptance and verification

- A changed test metadata file is reflected by every consumer without consumer
  source changes.
- Missing or mistyped metadata fails before an installation or distribution is
  changed.
- Add consumer-parity tests; run affected builder, validator, and acceptance
  tests plus `python3 scripts/run_quality_gate.py`.
- Repository search leaves direct production identity definitions only in the
  metadata source.

## TKT-002 — JSON report contract SSOT

- Priority: P0
- Depends on: TKT-001
- Result: JSON validation and acceptance extraction obtain the report version,
  enums, and mode requirements from `schemas/analysis-result.schema.json`.

### Work

Add a shared schema access API. Make `report_contract.py` and the acceptance
harness use it; remove their duplicated values, including the harness's direct
`"1.0"` comparison. Preserve current valid and invalid fixture outcomes and
do not introduce a dependency or change the schema version.

### Acceptance and verification

- Changing a schema-fixture version or enum changes the API and validator
  behavior without editing Python constants.
- Missing summary fields and detailed `dependencies` remain validation errors.
- Add schema-to-validator parity and acceptance-extraction tests; run JSON
  regressions and `python3 scripts/run_quality_gate.py`.

## TKT-003 — Markdown report contract SSOT

- Priority: P0
- Depends on: TKT-002
- Result: the report validator and both templates use
  `contracts/markdown-report-contract.json` for headings, sections, cards,
  categories, properties, Kubernetes inputs, and legacy identifiers.

### Work

Load that contract in `validate_report.py`. Add package validation that catches
template drift before distribution generation. Keep current Summary, Detailed,
and legacy formats; do not rewrite the Markdown parser or report UX.

### Acceptance and verification

- A mismatched required template section fails package validation.
- Unknown detailed categories and missing required properties identify the card
  and missing item.
- Add contract-to-template parity tests; run report/package regressions and
  `python3 scripts/run_quality_gate.py`.

## TKT-004 — Atomic distribution replacement

- Priority: P0
- Depends on: TKT-001–TKT-003
- Result: a failed replacement preserves the previous distribution.

### Work

Keep staging on the output's filesystem. Validate it, rename an existing output
to a unique backup, rename staging into place, then delete the backup. If the
swap fails, restore the backup; if restoration fails, retain recovery paths and
fail clearly. Never delete the existing output before a backup exists.

### Acceptance and verification

- Successful replacement leaves only the new output.
- Injecting a staging-to-output failure restores the old output at its original
  path; a failed staging validation leaves it untouched.
- A rollback failure is not success and preserves recovery data.
- Add replacement and rollback fault-injection tests, including old-output hash
  checks; run package regressions and `python3 scripts/run_quality_gate.py`.

## TKT-005 — Atomic multi-path installation

- Priority: P0
- Depends on: TKT-004
- Result: all compatibility paths receive the new distribution or all return
  to their pre-install state.

### Work

Preflight deduplicated targets, source conflicts, parent access, metadata, and
the distribution. Prepare and validate a same-filesystem staging copy for every
target before committing any target. Commit via backup-and-rename; on failure,
restore committed paths in reverse order, clean unused staging, and retain
unrestored backups with recovery instructions. Attempt cleanup on `EXIT`,
`INT`, and `TERM`.

### Acceptance and verification

- Three successful targets have the same new manifest and file hash.
- Failure during the second or final commit restores every target's prior hash.
- Prepare failures change no installed target; rollback failures show affected
  paths, backup locations, and manual recovery commands.
- Preserve global, `--project-local`, and compatibility-path behavior.
- Add temporary-home integration and fault-injection tests; run
  `python3 scripts/run_quality_gate.py`.

## Release gate

All five slices are complete only when their parity/fault-injection tests and
existing Summary, Detailed, JSON, package, and scenario regressions pass; the
quality gate passes; and the analyzed-repository read-only and external-report
rules remain intact.

Stop and create a new ADR if preserving the public CLI or report contract
requires a breaking change, an external schema library, or unsupported
filesystem rename semantics.
