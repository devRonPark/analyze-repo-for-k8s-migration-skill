# VS-016 — Stop hardcoding `/bin/echo` as the adapter test double

## Outcome

`tests/test_opencode_adapter.py` proves OpenCode-adapter behavior (command
construction, debug probes, timeout handling) without depending on a Unix
filesystem path that does not exist on Windows.

## Why this is a vertical slice

VS-014/VS-015 made `python scripts/run_quality_gate.py` UTF-8-safe and
dropped hardcoded `python3` on Windows, cutting failures from 74 to 14. Of
the remainder, 7 are these adapter tests. They are unrelated to encoding or
interpreter resolution, so they were left out of that fix and are tracked
here.

## Status and dependencies

- **Status:** Ready
- **Depends on:** VS-014, VS-015 (established the current 14-failure baseline this ticket narrows)
- **Blocks:** None

## Read first

- `tests/test_opencode_adapter.py` (the 7 failing cases; each passes a fake `runner` and a literal executable string)
- `scripts/run_opencode_acceptance.py:582-584` (`run_case`'s executable-exists check: `shutil.which(...)` when a bare name, otherwise `Path(opencode).exists()`)

## Scope

### In scope

- Replace the hardcoded `"/bin/echo"` executable argument in the 7 failing
  `OpenCodeAdapterTests` cases with a path that exists on the current
  platform (e.g. `sys.executable`, since these tests already inject a fake
  `runner` and never actually exec the path).
- Confirm no other test in the file relies on `/bin/echo`, `/bin/*`, or
  another Unix-only absolute path as a stand-in "executable".

### Out of scope

- Changing `run_case`'s executable-resolution logic in `scripts/run_opencode_acceptance.py` itself — the 7 failures are a test-fixture problem, not a product-code problem.
- Any change to real OpenCode/provider execution behavior.

## Implementation steps

1. Grep `tests/test_opencode_adapter.py` for `/bin/echo` and any other literal Unix path used as a placeholder executable.
2. Replace each with `sys.executable` (already proven safe elsewhere in this codebase after VS-015) or another cross-platform-existing path, keeping the fake `runner` injection unchanged.
3. Re-run `python scripts/run_quality_gate.py` and confirm these 7 cases move from `UNAVAILABLE` to `PASS` with no change to unrelated tests.

## Acceptance criteria

- All 7 previously failing `OpenCodeAdapterTests` cases pass on this Windows environment.
- No change to `scripts/run_opencode_acceptance.py` production logic.
- Quality gate failure count decreases by exactly 7 from the VS-015 baseline (14 -> 7), with no new failures introduced.

## Verification commands

```bash
python scripts/run_quality_gate.py
python -m unittest tests.test_opencode_adapter -v
```

## Expected file changes

- `tests/test_opencode_adapter.py`

## Commit boundary

- Commit only `tests/test_opencode_adapter.py`.
- Suggested commit: `fix: stop hardcoding /bin/echo in OpenCode adapter tests`

## Codex execution instruction

```text
Implement only VS-016. Read this ticket and tests/test_opencode_adapter.py.
Replace the hardcoded /bin/echo placeholder executable with a path that
exists on the current platform without changing what the fake runner
proves. Do not touch scripts/run_opencode_acceptance.py. Run the quality
gate and report the before/after failure count.
```
