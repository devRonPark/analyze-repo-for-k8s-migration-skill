# SEC-002 — `read.ts`'s worktree boundary check does not resolve symlinks

## Outcome

The trusted `read` tool rejects a read that traverses a symlink planted
inside the analyzed repository whose target resolves outside the current
worktree, the same way the target-resolution gate already rejects a
symlink-outside-worktree *target argument*.

## Why this is a vertical slice

`runtime/tools/read.ts`'s `safePath()` computes `resolve(worktree, path)`
and checks the *string* result with `isWithin()` (a `relative()`-based
prefix check). `resolve()` only normalizes `.`/`..` segments lexically — it
does not call `fs.realpath`, so it never dereferences symlinks. Node's
`readFile`/`readdir`/`stat`, however, transparently follow symlinks at the
OS level.

Confirmed by code inspection (not yet exploited live): if an analyzed
repository — untrusted input per `AGENTS.md`'s Safety section — contains a
symlink such as `evidence -> /etc/passwd` or `evidence -> ../../outside-secret`,
then `glob` finds `evidence`, `safePath(worktree, "evidence")` computes a
path string that is lexically inside `worktree` (passing `isWithin`), and
`read("evidence")` follows the symlink and returns the *external* file's
content (only credential-shaped literals get redacted from whatever that
external content is — the escape itself is not caught).

This is a different boundary from the one `tests/evaluation/opencode-cases.json`'s
`symlink-escape-rejected` case already covers: that case sends the literal
string `"symlink-outside-worktree"` as the user's target argument and
verifies the target-resolution gate never calls a tool at all. It does not
construct a real on-disk symlink inside an *accepted* target and exercise
`read.ts`'s own boundary check — so this specific gap has no test coverage
today.

## Status and dependencies

- **Status:** Ready
- **Depends on:** None
- **Blocks:** None (SEC-001 covers the broader safe-evidence-boundary; this is a specific, newly identified gap within it)

## Read first

- `runtime/tools/read.ts` — `safePath()`, `isWithin()`
- `runtime/tools/glob.ts` — confirm whether it has the same lexical-only boundary issue for path listing (lower severity: listing a symlink's name doesn't read its target's content, but worth checking for consistency)
- `tests/evaluation/opencode-cases.json`'s `symlink-escape-rejected` case, for the existing (different) boundary it covers

## Scope

### In scope

- Change `safePath()` to resolve symlinks before the boundary check —
  Node's `fs.realpath`/`fs.promises.realpath` on the computed path (and,
  since the target itself may not exist yet in some call patterns, consider
  resolving each existing path segment or using `fs.realpath.native` with a
  clear error for a target that doesn't exist rather than silently passing).
- Add a test that plants a real symlink inside a temporary fixture
  repository pointing outside the worktree and asserts `read` rejects it
  with the existing `"path is outside the target or trusted Skill"` error.
- Check `glob.ts` for the same class of issue and fix if present.

### Out of scope

- Changing the target-resolution gate's existing (different) symlink-argument rejection.
- Any change to `git_metadata.ts`.

## Implementation steps

1. Reproduce: in a temp directory, create `target/evidence -> <somewhere outside target>`, call the current `safePath(target, "evidence")`, confirm it does not throw.
2. Fix `safePath()` to resolve symlinks (e.g. `await realpath(value).catch(() => value)` before the `isWithin` check, applied to both `worktree` and the candidate path so the comparison is realpath-to-realpath).
3. Re-run the reproduction; confirm it now throws `"path is outside the target or trusted Skill"`.
4. Add the regression test; run the full acceptance suite.

## Acceptance criteria

- A symlink inside the target repository pointing outside the worktree is rejected by `read`, with the existing error message.
- Existing valid reads (no symlinks, or symlinks that stay within the worktree) are unaffected.
- `python scripts/run_quality_gate.py` and the OpenCode acceptance suite both pass.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --repository-root <target> --output-dir <dir>
```

## Expected file changes

- `runtime/tools/read.ts` (and `runtime/tools/glob.ts` if the same issue is found there)
- new test fixture/case exercising a real on-disk symlink

## Commit boundary

- Commit only the tool fix and its test.
- Suggested commit: `fix: resolve symlinks before the read tool's worktree boundary check`

## Codex execution instruction

```text
Implement only SEC-002. Reproduce the gap first (a real on-disk symlink
inside a temp target pointing outside it, read via the current safePath),
confirm it isn't caught, then fix by resolving symlinks before the
boundary comparison. Check glob.ts for the same issue. Add a regression
test using a real symlink, not a string argument. Do not touch the
existing symlink-argument target-resolution gate.
```
