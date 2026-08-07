# VS-018 — Fix CRLF byte-count drift in the context-measurement test fixture

## Outcome

`tests/test_context_measurement.py::test_measurement_counts_loaded_files_and_preserves_missing_usage`
passes on Windows, and the fixture's expected byte count matches what a
checked-in LF file actually measures.

## Why this is a vertical slice

VS-014/VS-015 narrowed `python scripts/run_quality_gate.py` from 74 to 14
failures. This is the last of the 3 residual categories and the only one
with a single, confirmed root cause (the other two, VS-016 and VS-017, are
test-fixture Unix-path assumptions).

## Status and dependencies

- **Status:** Ready
- **Depends on:** VS-014, VS-015 (established the current 14-failure baseline this ticket narrows)
- **Blocks:** None

## Read first

- `tests/test_context_measurement.py:16` — `loaded.write_text("one\ntwo\n", encoding="utf-8")`
- `tests/test_context_measurement.py:41` — `self.assertEqual(measurement["loaded_files"]["bytes"], len(b"one\ntwo\n"))`
- `scripts/measure_context.py:107` — `content = selected.read_bytes()` (raw byte read, no newline translation)

## Root cause (confirmed, not speculative)

`Path.write_text` defaults to `newline=None`, which applies platform
universal-newline translation on write. On Windows this rewrites each `\n`
to `\r\n`, turning the intended 8-byte fixture (`"one\ntwo\n"`) into 10
bytes on disk. `measure_context.measure()` reads the file with
`read_bytes()` (no translation), correctly reports 10, and the test's
hardcoded expectation of `len(b"one\ntwo\n")` (8) fails. The bug is in the
test fixture's write, not in `measure_context.py`'s read/count logic.

## Scope

### In scope

- Change the fixture write in `tests/test_context_measurement.py:16` to
  avoid newline translation — either `loaded.write_bytes(b"one\ntwo\n")` or
  `loaded.write_text("one\ntwo\n", encoding="utf-8", newline="")` — so the
  on-disk byte count matches the LF-only literal the assertion expects.
- Grep the rest of the file (and sibling fixture-writing tests, if any
  share this pattern) for the same `write_text` default-newline exposure.

### Out of scope

- Changing `scripts/measure_context.py` — it already measures the true
  on-disk byte count, which is the contractually correct behavior (context
  measurement must reflect actual loaded bytes, not a platform-normalized
  count).
- Any change to how real OpenCode traces or `SKILL.md` are counted.

## Implementation steps

1. Fix the write call at `tests/test_context_measurement.py:16` to produce
   exactly 8 bytes on disk regardless of platform.
2. Search the test suite for other `write_text(...)` calls whose output is
   later compared against a hardcoded `len(b"...")` or byte count, and
   apply the same fix if found.
3. Re-run the test on this Windows environment and confirm it passes.

## Acceptance criteria

- `test_measurement_counts_loaded_files_and_preserves_missing_usage` passes on Windows.
- The fixture's on-disk byte count is platform-independent (same result on Windows and Unix).
- No change to `scripts/measure_context.py`.

## Verification commands

```bash
python scripts/run_quality_gate.py
python -m unittest tests.test_context_measurement -v
```

## Expected file changes

- `tests/test_context_measurement.py`

## Commit boundary

- Commit only `tests/test_context_measurement.py`.
- Suggested commit: `fix: avoid CRLF drift in context-measurement byte-count fixture`

## Codex execution instruction

```text
Implement only VS-018. Read this ticket's Root cause section first — it is
already confirmed, not something to re-derive. Fix the write_text call at
tests/test_context_measurement.py:16 so the on-disk byte count is
platform-independent, without changing scripts/measure_context.py. Run the
quality gate and report the before/after failure count.
```
