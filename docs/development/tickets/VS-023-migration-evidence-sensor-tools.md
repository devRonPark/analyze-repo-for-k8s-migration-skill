# VS-023 — Replace raw glob+read exploration with migration-evidence sensor tools

## Outcome

The Agent gathers evidence through a small set of Kubernetes-migration-scoped
"sensor" tools (e.g. `discover_deployment_candidates`,
`inspect_build_runtime`, `inspect_network_contract`, `inspect_configuration`,
`inspect_state_dependencies`) that return structured, tool-computed facts
with tool-computed `file:line` evidence — instead of the Agent doing its own
`glob`/`read` exploration and computing citations itself from raw file text
it read several steps earlier. Kubernetes-migration *judgment*
(classification, verdict, Kubernetes interpretation) stays entirely in
`SKILL.md`/the agent prompt; the sensor tools return facts only, never a
Kubernetes design recommendation.

## Why this is a vertical slice

`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md` and this
session's live rehearsals surfaced a specific, recurring failure mode: the
Agent's own evidence citations sometimes don't match reality (e.g. citing
`file:17-268` for a 117-line file) — a citation the Agent had to reconstruct
from memory of a `read` call several steps earlier, rather than a value a
tool handed it directly. Today's repair loop (ADR-2026-08-07-002) treats
this as a downstream, catch-after-the-fact problem; this ticket addresses
the same failure mode upstream, at the source of the citation.

This does **not** replace the repair loop, VS-021's classification
enforcement, or VS-022's blocked engine-level constraint — it targets a
different axis (evidence *accuracy*, not output *format* compliance). See
the discussion that produced this ticket: sensor tools would plausibly fix
citation/evidence fabrication, but would not by themselves fix a model
ignoring the JSON-only instruction, a JSON syntax slip, or a provider
timeout.

## Status and dependencies

- **Status:** Needs a scoping decision before implementation (see Scope) — the tool boundary and return shapes below are a proposal, not yet accepted. **2026-08-07: scoping pass done, see [ADR-2026-08-07-003](../daily/2026-08-07/ADR-2026-08-07-003-vs-023-sensor-tool-scoping.md).** That ADR recommends a narrower Phase 1 (one generic, judgment-free `locate_evidence` primitive) in place of the five ecosystem-aware tools proposed below, and is itself still pending user confirmation — no tool code has been written.
- **Depends on:** [SEC-002](SEC-002-read-tool-symlink-escape.md) — if sensor tools wrap the same underlying safe-file-access logic as `read.ts`, the symlink-boundary fix should land in the shared primitive, not be duplicated or skipped.
- **Blocks:** None

## Read first

- `runtime/tools/read.ts`, `runtime/tools/glob.ts`, `runtime/tools/git_metadata.ts` — the current safe primitives
- `runtime/agents/kubernetes-migration-analyzer.md` — the current prompt-driven discovery strategy ("Use a bounded high-signal pass...") this would partially replace
- `SKILL.md`, `references/workflow.md`, `references/repository-analysis-checklist.md` — the existing Kubernetes-migration judgment rules that must stay in the Skill layer, unchanged
- `tests/evaluation/jpetstore-6-summary-json-first-scorecard.md` — the citation-fabrication evidence motivating this ticket

## Scope

### In scope (proposed — confirm before implementing)

- Design the sensor tool set and their exact return schemas. Starting proposal:
  - `discover_deployment_candidates` — independently-executable component evidence
  - `inspect_build_runtime` — build/start/image/runtime command evidence
  - `inspect_network_contract` — port/protocol/context-path evidence
  - `inspect_configuration` — env/config/Secret-shaped input evidence (location only, never values — must preserve `read.ts`'s existing credential redaction)
  - `inspect_state_dependencies` — writable path/DB/cache/external-dependency evidence
  - Each returns facts + tool-computed `file:line` evidence in a shape close to `schemas/analysis-result.schema.json`'s `evidence`/`fields` shapes, e.g. `{"value": ..., "evidence": "path:line", "status": "confirmed"}` — never a Kubernetes-resource-shaped field (no `service_type`, `ingress_required`, `replicas`, etc.).
- Implement the chosen tools as new `runtime/tools/*.ts` OpenCode plugin tools, sharing (not duplicating) `read.ts`'s worktree-boundary and credential-redaction logic.
- Update `kubernetes-migration-analyzer.md`'s permission list and discovery instructions to use the new tools for the "bounded high-signal pass," while keeping `read`/`glob` available for cases the sensors don't cover (e.g. Detailed mode's broader inspection, or a finding the sensors didn't anticipate).
- Add tests that exercise each sensor tool against a fixture repository and assert its returned evidence strings are real, correct `file:line` references.

### Out of scope

- Any tool that outputs a Kubernetes design judgment (`recommend_deployment`, `generate_helm`, `choose_ingress`, `calculate_resources`, or similar) — this is an explicit non-goal; that judgment stays in the Skill/prompt layer.
- Removing `read`/`glob`/`git_metadata` entirely.
- Changing Detailed mode's contract or budget.
- The Agent Runtime migration discussion (goose/OpenHands) — this ticket is scoped to OpenCode's existing plugin-tool mechanism regardless of which runtime is used later.

## Implementation steps

1. Confirm the sensor tool set and return schemas with a short design pass (this is the "needs a scoping decision" item above) — in particular, decide how much file-pattern knowledge (e.g. "what counts as a Dockerfile") lives in tool code vs. stays prompt-driven, since over-encoding domain heuristics into tool code re-introduces the "Tool makes judgments" problem this ticket is trying to avoid for *design* judgments specifically (fact-finding heuristics like "check these filenames" are lower-risk than K8s-shape judgments, but the line should be drawn explicitly).
2. Implement the tools, sharing `read.ts`'s (post-SEC-002) boundary/redaction logic.
3. Update the agent prompt and permission list.
4. Add per-tool tests against fixture repositories with known-correct expected evidence.
5. Re-run the live jpetstore-6 scenario multiple times and compare the evidence-fabrication rate against `jpetstore-6-summary-json-first-scorecard.md`'s baseline.

## Acceptance criteria

- No sensor tool returns a Kubernetes-resource-shaped judgment field.
- Every sensor tool's evidence strings are verified correct (`file:line` points to real content) by its test.
- Repeated live runs against `demo-repositories/jpetstore-6` show a measurably lower citation-fabrication rate than the pre-change baseline.
- `python scripts/run_quality_gate.py` passes.

## Verification commands

```bash
python scripts/run_quality_gate.py
python scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --case slash-default-summary --repository-root demo-repositories/jpetstore-6 --repeat 5 --output-dir <dir>
```

## Expected file changes

- New `runtime/tools/*.ts` sensor tools
- `runtime/agents/kubernetes-migration-analyzer.md`
- `runtime/tools/read.ts` (shared boundary/redaction logic, coordinated with SEC-002)
- New tests under `tests/`

## Commit boundary

- Land the scoping decision (step 1) as its own small commit or ADR addendum before writing tool code, so the tool-boundary line is reviewable on its own.
- Commit tool implementation and prompt/permission changes together per tool or in one focused pass; do not bundle with unrelated Detailed-mode or DEL-00x changes.

## Codex execution instruction

```text
Implement only VS-023, and only after its Scope's step 1 design decision
is confirmed -- do not invent the sensor tool set unilaterally. Read
runtime/tools/read.ts and SEC-002 first; share the boundary/redaction
logic rather than duplicating it. Keep every sensor tool fact-only: no
Kubernetes-resource-shaped judgment field in any return value. Add tests
that verify returned evidence strings against real fixture file content,
not just schema shape. Run the quality gate and report the result.
```

## Decision outcome (2026-08-07)

User confirmed [ADR-2026-08-07-003](../daily/2026-08-07/ADR-2026-08-07-003-vs-023-sensor-tool-scoping.md)'s
narrower Phase 1: one generic, judgment-free `locate_evidence` tool instead
of the five proposed ecosystem-aware tools. `discover_deployment_candidates`
and the four `inspect_*` tools remain unimplemented, deferred to a possible
later phase.

Implemented as `runtime/lib/locate-evidence.ts` (`locateEvidence`,
`resolveRoot` — the pure, tested logic) plus a thin `runtime/tools/locate_evidence.ts`
wrapper (the `@opencode-ai/plugin` `tool()` binding, following the same
split SEC-002 used for `runtime/lib/safe-path.ts`). It globs for files under
a worktree-bounded root (reusing `isSafeWithin`), optionally matches a regex
against their lines, and returns `{status: "found", value, reference}` with
a `path:line` computed from that same read, or `{status: "not_found",
searched: {scope, glob, pattern}}` with the literal search performed —
either way, nothing for the agent to reconstruct from memory. Also
extracted the credential-redaction regexes `read.ts` already had into a new
shared `runtime/lib/redact.ts` (both `read.ts` and `locate-evidence.ts` now
import it, rather than duplicating a security-sensitive regex a second
time).

Wired into `runtime/opencode.json`'s and `kubernetes-migration-analyzer.md`'s
permission lists as `locate_evidence: allow`, and added two short prompt
sentences pointing the agent at it for computing a `근거:`/`검색(...)` citation
instead of recalling one — no change to `references/language-discovery-rules.md`
or any other discovery/classification instruction, per the confirmed
narrower scope.

**Tests:** `runtime/lib/locate-evidence.test.ts` (9 cases: found via glob
only, found via glob+pattern with the real matched line — not line 1,
redaction applied to a matched credential-shaped line, sorted-order
determinism across multiple candidates, worktree-relative reference from a
subdirectory root, not-found for no glob match, not-found for glob-match-but-no-pattern-match,
and two `resolveRoot` boundary cases) plus `runtime/lib/safe-path.test.ts`'s
existing 7 — 16/16 pass via `bun test runtime/lib`. `bun build` (targeting
Node, `@opencode-ai/plugin` external) compiles all four `runtime/tools/*.ts`
files without error. `python scripts/run_quality_gate.py`: 154/155 (same
pre-existing VS-019 Windows-junction failure, unrelated).

**Not done, and not claimed:** the acceptance criterion "repeated live runs
against `demo-repositories/jpetstore-6` show a measurably lower
citation-fabrication rate" needs a live OpenCode rerun, which needs the
`opencode` CLI (not installed in this sandbox) and escalated per-command
network permission (not requested this session). The tool's own logic is
unit-tested and verified against real fixture files, but whether the agent
actually calls `locate_evidence` instead of citing from memory, and whether
that measurably reduces the scored fabrication rate, is unverified.

## Live verification outcome (2026-08-07, follow-up session)

**Acceptance criterion met.** 3/3 live runs against a `jpetstore-6` clone
pinned to the golden set's revision (`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`),
all `PASS`, target unchanged before/after. `locate_evidence` was called 7,
10, and 13 times respectively; every citation in all three rendered reports
resolves to a real, correct `file:line` — no fabricated citation observed,
versus the pre-change baseline's documented `file:17-268` for a 117-line
file. Full detail, the evidence-calibration re-score (9/10, up from 8/10
post-VS-020), and one near-miss (a `locate_evidence` glob/pattern matching
an unrelated file, which did not leak into the final report) are recorded in
`tests/evaluation/jpetstore-6-summary-json-first-scorecard.md`'s "VS-023
Phase 1 live verification" section.

Getting this run to execute at all required first fixing an unrelated
harness bug: `scripts/install-opencode.sh` and `run_opencode_acceptance.py`
copied `runtime/tools/` but never `runtime/lib/`, so every tool importing
`"../lib/..."` (starting with SEC-002's `safe-path.ts`) failed to resolve in
every live run since SEC-002 landed. See the scorecard section and
`scripts/run_opencode_acceptance.py`'s `copy_tools()` for the fix, and
`tests/test_opencode_adapter.py::test_isolated_tool_copy_includes_sibling_lib_modules`
for the regression test.

Phase 2 (the five ecosystem-aware `inspect_*`/`discover_deployment_candidates`
tools) remains deferred, not needed: the one observed wrong-glob/pattern
near-miss did not produce a fabricated citation, which is the signal
`focus.md` set for revisiting that decision.
