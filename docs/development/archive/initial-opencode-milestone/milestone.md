# Current Milestone — OpenCode-Only Local Acceptance

## Goal

Reach the first usable checkpoint where a user can enter a locally cloned repository, start OpenCode, invoke the Skill with a minimal request, and receive a validated Kubernetes migration analysis report without OpenShell.

## Included tickets

Implement in dependency order:

```text
VS-001 -> VS-002 -> VS-003
       -> VS-004 -> VS-005 -> VS-006 -> VS-007 -> VS-008
       -> VS-009
```

Parallel implementation is allowed only when ticket dependencies are already complete, but completion and commits remain one ticket at a time.

## Stop condition

Stop after `VS-009` passes.

Do not implement:

- `VS-010` OpenShell secure runtime;
- `VS-011` full-stack E2E security;
- `VS-012` final context measurement based on OpenShell traces;
- `VS-013` final legacy cleanup and release.

## Milestone acceptance

The milestone is accepted when all of the following are demonstrated with executed commands:

- the Skill package and unified quality gate pass;
- a minimal OpenCode runtime distribution is built and installed;
- OpenCode discovers the Skill;
- a relevant request activates it;
- a non-relevant request does not activate it;
- the minimum Korean request produces a Summary report;
- an explicit Detailed request produces a Detailed report;
- generated reports pass structural and behavioral evaluation;
- repository mutation and prohibited-command cases are denied;
- the analyzed repository has no changes after the run.

## Implementation loop

For each ticket:

1. Set the ticket to `IN_PROGRESS` in the milestone status ledger.
2. Read the ticket's `Read first` files.
3. Run the relevant baseline or targeted test.
4. Implement only the ticket scope.
5. Run targeted verification.
6. Run the unified quality gate once.
7. Run `git diff --check`.
8. Record command output and blockers in the milestone status ledger.
9. Commit the ticket separately.

## Testing boundary

- Strict TDD is required only for deterministic executable contracts.
- Markdown refactors use characterization and acceptance checks.
- Do not add phrase-lock, exact-log, trivial-branch, or coverage-only tests.
