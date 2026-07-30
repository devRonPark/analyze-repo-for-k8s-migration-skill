# ADR-2026-07-30-001: Limit the urgent work to contract SSOTs and safe filesystem replacement

- Status: Accepted
- Date: 2026-07-30
- Related plan: [urgent improvement ticket list](TICKET-LIST-2026-07-30-001-urgent-improvements.md)

## Context

The repository has two verified operational risks:

1. Project identity and report contracts are defined in more than one consumer.
   A change can make the builder, validator, acceptance harness, templates, and
   installer disagree.
2. The builder and installer delete existing directories before a replacement
   has fully succeeded. A failure can lose a good distribution or leave
   installation paths at different versions.

Broad object-oriented refactoring, replacing every literal, and splitting the
acceptance runner do not address either risk.

## Decision

Implement these ordered slices only:

| Slice | Authoritative source or operation | Consumers / guarantee |
| --- | --- | --- |
| TKT-001 | `contracts/project-metadata.json` | Builder, validator, acceptance harness, and installer share identity values. |
| TKT-002 | `schemas/analysis-result.schema.json` | JSON validator and acceptance extraction share version, enums, and mode requirements. |
| TKT-003 | `contracts/markdown-report-contract.json` | Markdown validator and templates share report structure; legacy support remains. |
| TKT-004 | backup, swap, rollback | A failed distribution replacement restores the prior output. |
| TKT-005 | prepare, commit, reverse rollback | A failed multi-path install restores every committed path. |

Each source owns one responsibility. Do not create one combined contract file.
Use Python's standard library for metadata and the current schema subset; a
third-party JSON Schema engine requires a new ADR.

## Filesystem guarantees and limits

Create staging and backup directories in the destination's parent filesystem.
Validate staging before moving an existing directory to a unique backup, then
rename staging into place. On failure, restore backups and retain any backup
that cannot be restored, with its path and a manual recovery command.

The installer prepares and validates every target before committing any target.
If a commit fails, it restores committed targets in reverse order. `EXIT`,
`INT`, and `TERM` should attempt the same cleanup.

This is not a distributed transaction. Power loss, `kill -9`, filesystem
corruption, remote filesystems, and a rollback failure can still require manual
recovery; none may be reported as success.

## Non-goals

- Whole-codebase OO redesign or acceptance-runner modularization
- New report fields, a schema-version change, or legacy Markdown removal
- Release history, symlink releases, remote artifacts, signing, or multi-host
  installation

## Verification and revisit

Every slice needs a focused parity or failure-injection test plus relevant
regressions. After the final slice, run:

```bash
python3 scripts/run_quality_gate.py
```

Create a follow-up ADR if a breaking contract change, external schema library,
different rename semantics, legacy removal, multi-machine installation, or a
repeated rollback failure requires a different design.
