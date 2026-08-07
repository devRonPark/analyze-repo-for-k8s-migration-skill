# VS-019 — `ln -s` on Windows produces a junction, not a symlink the test recognizes

## Outcome

`tests/test_repository_distribution.py::test_install_script_creates_qwen_skill_symlink`
either passes on Windows without requiring elevated privileges / Developer
Mode, or the test's expectation is corrected to match what
`install-qwen.sh` can actually produce on this platform.

## Why this is a vertical slice

Discovered while implementing VS-017: once the test's sandboxed PATH could
find `python3` (VS-017's fix), `scripts/install-qwen.sh` ran to completion
(exit 0, `ln -s "$SKILL_ROOT" "$TARGET"` reported success), but
`Path(installed).is_symlink()` is `False` and `Path(installed).is_dir()` is
`True`. This is a separate, unrelated root cause from VS-017 and was never
reached before VS-017's fix, so it is tracked as its own ticket rather than
folded in.

## Status and dependencies

- **Status:** Ready
- **Depends on:** VS-017 (its PATH fix is what let this test reach the symlink assertion at all)
- **Blocks:** None

## Read first

- `tests/test_repository_distribution.py` — `test_install_script_creates_qwen_skill_symlink`
- `scripts/install-qwen.sh:19` — `ln -s "$SKILL_ROOT" "$TARGET"`, no fallback or error handling

## Suspected root cause (not yet confirmed against Windows symlink privilege APIs)

Git for Windows' `ln -s`, when the current user lacks
`SeCreateSymbolicLinkPrivilege` (not Administrator, not in Developer Mode),
is known to fall back to creating an NTFS directory junction
(`IO_REPARSE_TAG_MOUNT_POINT`) instead of a true symlink reparse point
(`IO_REPARSE_TAG_SYMLINK`) for directory targets. Python's
`Path.is_symlink()` does not treat a junction as a symlink, and
`Path.is_dir()` reports `True` because junctions resolve transparently.
This needs to be confirmed (e.g. by checking whether Developer Mode is
enabled on the target machine, and whether `ln -s` behaves differently with
it on) before deciding the fix.

## Scope

### In scope

- Confirm the junction-vs-symlink theory above on the actual demo machine.
- Decide and implement one of:
  a. If Developer Mode / elevated privilege is an acceptable demo-machine
     prerequisite, document it and leave `install-qwen.sh` unchanged — the
     test failure would then only affect environments without that
     privilege, which should be called out in `README.md`.
  b. If not, change the test's assertion to accept a junction as
     equivalent to a symlink on Windows (e.g. check `installed.is_dir()`
     and that it does not contain a real copy of `SKILL.md`'s content
     independently — i.e. that it still points at `SKILL_ROOT` rather than
     being a physical copy), without changing `install-qwen.sh`'s behavior
     for platforms where `ln -s` produces a real symlink.

### Out of scope

- Changing `install-opencode.sh`'s installer (it does not use `ln -s`; the equivalent OpenCode installer tests already pass after VS-017).
- Requiring end users to run as Administrator for a normal `qwen` install — that would be a regression in usability, not just a test fix.

## Implementation steps

1. On the demo machine, check `fsutil reparsepoint query <path>` (or
   equivalent) on the directory `install-qwen.sh` creates, to confirm
   whether it is a junction or a symlink, and check the machine's Developer
   Mode setting.
2. Based on that finding, implement option (a) or (b) from Scope above.
3. Re-run `test_install_script_creates_qwen_skill_symlink` and confirm it passes without weakening what it actually proves (that the installed skill still resolves to the source checkout, not a stale copy).

## Acceptance criteria

- The test passes on this Windows environment without requiring the CI/demo machine to run as Administrator, unless that is explicitly documented as a prerequisite.
- `install-qwen.sh`'s behavior for real-symlink-capable platforms (Linux/macOS, or Windows with Developer Mode) is unchanged.

## Verification commands

```bash
python scripts/run_quality_gate.py
python -m unittest tests.test_repository_distribution.RepositoryDistributionTests.test_install_script_creates_qwen_skill_symlink -v
```

## Expected file changes

- `tests/test_repository_distribution.py` (assertion) and/or `README.md` (documented prerequisite), depending on which option is chosen in step 2.

## Commit boundary

- Commit only the files the chosen option actually touches.
- Suggested commit: `fix: recognize Windows junctions as valid qwen skill links` (option b) or `docs: document Developer Mode as a Windows install prerequisite` (option a).

## Codex execution instruction

```text
Implement only VS-019. Read this ticket's Suspected root cause section
first, then confirm it on the target machine before writing code — the
theory is not yet verified. Choose option (a) or (b) from Scope based on
what you find, and say which you chose and why. Do not modify
scripts/install-qwen.sh's ln -s behavior for platforms with real symlink
support. Run the quality gate and report the before/after state of this
one test.
```
