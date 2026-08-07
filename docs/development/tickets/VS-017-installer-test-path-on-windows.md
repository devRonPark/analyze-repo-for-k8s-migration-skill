# VS-017 — Give installer tests a `python3` the sandboxed PATH can find

## Outcome

`tests/test_repository_distribution.py`'s `install-opencode.sh` /
`install-qwen.sh` subprocess tests pass on a Windows/Git Bash environment,
not only on a Unix CI runner.

## Why this is a vertical slice

VS-014/VS-015 fixed encoding and interpreter-resolution failures across the
suite (74 -> 14 failures). 5 of the remaining 14 are these installer tests,
and they fail for a third, distinct reason: the tests intentionally set
`env={"HOME": str(home), "PATH": "/usr/bin:/bin"}` to sandbox the install
script, but `scripts/install-opencode.sh:35` and `install-qwen.sh` call
`python3`, which does not exist under `/usr/bin` or `/bin` on this machine
(confirmed failure: `install-opencode.sh: line 35: python3: command not
found`, exit 127). This is a test-environment gap, not a product defect —
`install-opencode.sh` correctly requires `python3` on the installing user's
PATH, same as documented in `README.md`.

## Status and dependencies

- **Status:** Ready
- **Depends on:** VS-014, VS-015 (established the current 14-failure baseline this ticket narrows)
- **Blocks:** None

## Read first

- `tests/test_repository_distribution.py` (5 failing cases: `test_install_script_creates_qwen_skill_symlink`, `test_opencode_installer_copies_global_distribution`, `test_opencode_installer_does_not_replace_source_checkout`, `test_opencode_installer_refreshes_duplicate_locations`, `test_opencode_installer_supports_project_local_destination`)
- `scripts/install-opencode.sh`, `scripts/install-qwen.sh` (both call `python3` directly, not `$PYTHON` or similar)

## Scope

### In scope

- Compute, in the test setup, a PATH value that (a) keeps the sandboxing
  intent — only whatever directories are actually needed, not the full host
  PATH — and (b) includes a directory containing a working `python3` in the
  Git Bash / MSYS path syntax the subprocess's `bash` expects (e.g. derived
  from `sys.executable`'s directory, converted to `/c/...` form).
- Confirm `bash` itself is still resolvable under the sandboxed PATH on this
  platform (it currently is, since only `python3` resolution fails).

### Out of scope

- Changing `install-opencode.sh` / `install-qwen.sh` to use `python3` via
  some other resolution mechanism — the scripts' contract with real user
  environments should not change for a test-only workaround.
- Any change to `README.md`'s documented user-facing install commands.

## Implementation steps

1. Add a small helper in `tests/test_repository_distribution.py` that
   resolves the directory containing a working `python3`/`python` on the
   current platform and formats it for the subprocess `PATH` the same way
   the existing `"/usr/bin:/bin"` value is formatted.
2. Merge that directory into each installer subprocess call's `env["PATH"]`
   without widening the sandbox further than necessary.
3. Re-run the 5 failing cases and confirm they pass; confirm no other test
   in the file regresses (the file also has 3 currently-passing bash
   subprocess cases that must stay unaffected).

## Acceptance criteria

- All 5 previously failing installer tests pass on this Windows/Git Bash environment.
- The sandboxed `PATH` still excludes the full host PATH — only the directories the install script actually needs are added.
- No change to `scripts/install-opencode.sh` or `scripts/install-qwen.sh`.

## Verification commands

```bash
python scripts/run_quality_gate.py
python -m unittest tests.test_repository_distribution -v
```

## Expected file changes

- `tests/test_repository_distribution.py`

## Commit boundary

- Commit only `tests/test_repository_distribution.py`.
- Suggested commit: `fix: give installer tests a resolvable python3 on Windows`

## Codex execution instruction

```text
Implement only VS-017. Read this ticket and tests/test_repository_distribution.py.
Fix the 5 failing installer subprocess tests by extending their sandboxed
env PATH to include a working python3, without widening the sandbox beyond
what install-opencode.sh/install-qwen.sh actually need and without changing
the install scripts themselves. Run the quality gate and report the
before/after failure count.
```
