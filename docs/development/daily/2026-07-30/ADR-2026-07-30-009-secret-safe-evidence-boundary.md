# ADR-2026-07-30-009: Redact repository evidence before the model sees it

- Status: Accepted
- Date: 2026-07-30
- Related work: [Secret-safe evidence boundary ticket list](TICKET-LIST-2026-07-30-006-secret-safe-evidence-boundary.md)

## Context

The Detailed OpenCode E2E for JPetStore 6 read seed SQL containing demo
credentials. Although the Skill instructs the model not to emit values, the
final report later reproduced them. Prompt rules and post-hoc report validation
can detect a leak but cannot prevent a direct assistant response from reaching
the user.

Static OpenCode permissions can deny an unsafe tool but cannot enforce a
stateful rule such as "read this file only after redaction." Repository content
is untrusted evidence, so a model must not receive secret literals merely to
report their location and exposure risk.

## Decision

1. Repository text reaches the analysis model only through one `safe_read`
   boundary that detects and replaces credential literals before returning
   content.
2. The boundary preserves repository-relative path, line numbers, and a
   `credential-shaped demo seed data` classification, but never returns the
   literal value or a reversible prefix, suffix, hash, or encoded form.
3. The analysis agent loses native file-read, grep, and shell access to target
   repository content. Its permitted discovery and evidence tools must route
   through the same boundary.
4. Final reports are written through one report egress that runs the same
   literal detector before delivery. The existing report validator remains a
   diagnostic and regression check, not the primary safety control.
5. The safety contract is verified with planted canary values across direct
   reads, chunked reads, searches, encoded forms, tool transcripts, and final
   reports. A canary appearing anywhere is a failure.

## Consequences

### Positive

- A model cannot reproduce a credential value it never receives.
- Reports retain actionable exposure locations without copying sensitive data.
- The guarantee is enforced at an I/O trust boundary rather than relying on
  model instruction following.

### Costs and limits

- The model cannot assess credential strength or compare secret values. Those
  are outside Kubernetes migration analysis.
- Existing native discovery paths need replacement or removal, and all target
  evidence reads must be covered before the native permissions are revoked.
- This is a security boundary, not a new planner, agent, or repository-specific
  allowlist.

## Rejected alternatives

- **Prompt-only redaction.** E2E already demonstrated that it is not reliable.
- **Post-hoc validator only.** It detects a leak after the user-facing response
  has already been generated.
- **Credential hashes or partial values.** They can leak short demo values and
  are not required for the migration decision.
- **Allow native reads for selected file types.** Secret literals can occur in
  any repository text and file names are not sufficient evidence of safety.

## Follow-up

Implement `SEC-001` from the related ticket list before treating direct
OpenCode reports as safe for repositories containing secret-shaped data.
