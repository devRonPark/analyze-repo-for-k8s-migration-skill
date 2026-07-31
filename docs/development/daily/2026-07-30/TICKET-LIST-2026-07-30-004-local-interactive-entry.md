# TICKET-LIST-2026-07-30-004: Local interactive analysis entry

- Status: Planned; not active until `current/focus.md` selects this list.
- Governing decision: [ADR-2026-07-30-006-local-interactive-entry.md](ADR-2026-07-30-006-local-interactive-entry.md)
- Deferred client routing: [ADR-2026-07-30-005-deferred-client-routing.md](ADR-2026-07-30-005-deferred-client-routing.md)

## Goal

Make the supported `opencode` → `/analyze-repo-for-kubernetes` experience
predictable without changing a user's global OpenCode defaults.

## Scope boundary

These tickets support only local Git worktrees. They do not add automatic
natural-language routing, Repository URL cloning, `@repository` handoff,
plugins, launchers, or external-directory permissions.

## INT-001 — Provide help without repository analysis

### User value

A user can discover the supported command, default Summary mode, Detailed
request, and local-target rules before any repository is read.

### Work

- Route `--help`, `도움말`, and `사용법` before target resolution.
- Return a compact Korean usage guide with slash-command examples.
- State that the documented path is to start `opencode` in the target Git
  repository and invoke the custom command.

### Acceptance

- Help performs no target discovery or repository reads.
- Help never starts an analysis or emits a report.
- The guide distinguishes default Summary from explicit Detailed mode.

### Verification

- Add one focused routing test for every recognized help pattern.
- Run the relevant unit tests and `python3 scripts/run_quality_gate.py`.

## INT-002 — Resolve local targets predictably

### User value

The same command chooses the intended scope for the current repository and
for an explicit `.` without silently expanding filesystem access.

### Work

- Make no-argument command requests resolve to the current Git root.
- Treat `.` as an explicit current-directory subdirectory scope.
- Accept only paths within the current Git worktree; reject non-Git paths,
  repository-escaping symlinks, and URL-only input.
- Return one Korean reason-and-path-request sentence on resolution failure.

### Acceptance

- A current-repository request uses the Git root even when OpenCode starts in
  a subdirectory.
- A `.` request preserves that subdirectory as the analysis scope.
- Invalid input never triggers repository discovery outside the permitted
  worktree.

### Verification

- Add deterministic target-resolution contract tests for root, subdirectory,
  invalid path, symlink escape, and URL-only input.
- Run the relevant unit tests and `python3 scripts/run_quality_gate.py`.

## INT-003 — Require a complete final report

### User value

An interactive user sees OpenCode activity and optional concise progress while
the final assistant response remains a clean, copyable Markdown report.

### Work

- Align the command, Skill, and agent contract: successful Summary and
  Detailed responses end with a complete Markdown report.
- Keep target, revision, and subdirectory in the final report.
- Have the acceptance harness retain the final Summary Markdown and validate
  it directly.

### Acceptance

- The final Summary is a complete `# Kubernetes 설계 입력 요약` report.
- It passes the report validator, uses Korean open-item labels, and has one
  verdict.
- Interactive client tool events and concise assistant progress are not treated
  as final report text.

### Verification

- Add adapter tests for final-report extraction and direct Markdown validation.
- Run `python3 scripts/run_quality_gate.py`.
- Run the documented TTY E2E against a read-only target; compare target Git
  status before and after.

## Delivery order

Implement and commit each ticket independently in this order:

```text
INT-001 help → INT-002 local target resolution → INT-003 final report response
```
