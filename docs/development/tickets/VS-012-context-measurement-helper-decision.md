# VS-012 — Measure actual context loading and decide whether a discovery helper is justified

## Outcome

The project has measured metadata, Skill body, Summary, Detailed, and language-reference load costs, plus an evidence-based decision to add or reject a deterministic repository-discovery helper.

## Why this is a vertical slice

It delivers a complete optimization decision rather than speculative code: baseline measurement → bottleneck identification → optional helper implementation → repeated quality/cost comparison.

## Status and dependencies

- **Status:** Ready for static measurement; full decision requires VS-011 traces
- **Depends on:** VS-005, VS-006, VS-008, VS-011 for full data
- **Blocks:** VS-013

## Read first

- OpenCode traces from VS-009/VS-011
- current `SKILL.md` and references
- repository fixtures and evaluator results
- v4 work plan section 4.9 and 4.14

## Scope

### In scope

- Measure bytes, lines, loaded file list, model usage metric when available, tool-call count, and elapsed steps for metadata-only, Skill activation, Summary, Detailed, and language-specific paths.
- Compare native `read`/`glob`/`grep`/`rg` discovery across at least eight fixtures.
- Define thresholds before implementing a helper: repeated high-signal omissions, excessive duplicate reads/tool calls, or unstable inventory.
- Only if thresholds are crossed, implement `scripts/discover_repository.py` for deterministic collection, not semantic classification.
- If implemented, include root/revision metadata, high-signal file list, line index, excluded paths, search patterns, and redacted secret-key locations.
- Evaluate same-session inventory reuse only for identical target, revision, subdirectory, helper version, and exclusion rules.

### Out of scope

- Adding a helper because scripts are generally preferred.
- Letting the helper decide deployability, production command, dependencies, or readiness.
- Reporting a precise context-reduction percentage without measured comparable runs.

## Implementation steps

1. Implement `scripts/measure_context.py` that consumes normalized traces and source files.
2. Commit a decision rubric and thresholds before collecting final measurements.
3. Run native discovery baselines and record omissions/tool calls.
4. Choose `NO_HELPER` or `ADD_HELPER` with evidence.
5. For `ADD_HELPER`, implement and rerun the same cases; retain it only if quality is equal or higher and cost improves materially.

## Acceptance criteria

- Measurements distinguish total package size from files actually loaded.
- The report names model/provider and unavailable metrics instead of guessing.
- The helper decision is reproducible from committed thresholds and results.
- Any helper is read-only, deterministic, secret-safe, and writes outside the repository.
- Cache invalidates on every declared identity field change.

## Verification commands

```bash
python3 scripts/measure_context.py --traces .artifacts/e2e --output docs/context-measurement.json
python3 -m unittest discover -s tests -p 'test_context_measurement.py' -v
# Only when the committed threshold selects ADD_HELPER:
python3 scripts/discover_repository.py --root tests/fixtures/repos/node-monorepo --output .artifacts/inventory.json
python3 scripts/run_quality_gate.py
```

## Expected file changes

- `scripts/measure_context.py` (new)
- `docs/context-measurement.md` (new)
- `docs/context-measurement.json` (new)
- `docs/discovery-helper-decision.md` (new)
- `scripts/discover_repository.py` (conditional)
- `tests/test_context_measurement.py` (new)
- `tests/test_discover_repository.py` (conditional)

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `perf: measure skill loading and discovery cost`

## Codex execution instruction

```text
Implement only VS-012. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
