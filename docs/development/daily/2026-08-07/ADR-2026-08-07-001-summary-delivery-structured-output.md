# ADR-2026-08-07-001: Reconfirm deterministic Summary delivery and add provider-level JSON-schema constraint

> **Superseded for interactive Python-MCP delivery (2026-08-09).** The
> accepted Python MCP pipeline owns in-session completion. Its interactive
> OpenCode boundary is the assistant-authored Markdown report, not a
> model-authored JSON payload rendered or finalized outside the session. The
> final assistant response is emitted only after `finalize_analysis` succeeds
> and begins `# Kubernetes 설계 입력 요약` for Summary (or
> `# Kubernetes 설계 입력 상세 평가` for Detailed). The acceptance harness
> preserves and validates that Markdown directly; it does not invoke an
> external renderer or finalizer as a completion dependency. This amendment
> supersedes the JSON-only and external-finalizer decisions below only for the
> Python-MCP interactive flow. JSON schemas and renderers remain available for
> explicitly requested offline structured-output workflows.

- Status: Accepted
- Date: 2026-08-07
- Related tickets: [TICKET-LIST-2026-07-30-003-deterministic-summary-delivery.md](../2026-07-30/TICKET-LIST-2026-07-30-003-deterministic-summary-delivery.md) (DEL-002, DEL-003, DEL-004 — specified 2026-07-30, not yet implemented)
- Extends: [ADR-2026-07-30-004-deterministic-summary-delivery.md](../2026-07-30/ADR-2026-07-30-004-deterministic-summary-delivery.md)

## Context

Live-rehearsed the Summary flow twice against `demo-repositories/jpetstore-6`
through `scripts/run_opencode_acceptance.py --case slash-default-summary`,
using the real provider (`172.16.4.249:30000`, `Qwen/Qwen3.6-35B-A3B-FP8`,
`reasoningEffort: "none"`) now that it is reachable. Both runs produced a
factually sound, well-evidenced report (correct `pom.xml`/`Dockerfile`
citations, correctly flagged the `tomcat90`/`tomcat9` profile mismatch as
`상충됨`) but both failed `scripts/validate_report.py --mode summary`:

- Run 1 used headings `## Target`, `## 배포 대상 후보`, `## 실행 형태`, ...
- Run 2 used a different set: `## Target: jpetstore-6 / master (...)`,
  `## 배포 대상 후보 및 주요 제외 항목`, `## 후보 실행 형태 / 런타임 / 빌드 / 이미지 / 컨테이너화`, ...
- Neither matches `assets/migration-summary-template.md`'s `report-contract=2.0`
  five-section structure, and neither matches the other.
- Run 2 additionally contains token-level language drift: `確認됨` (Han
  characters, not the required `확인됨`) and `профили` (Cyrillic).

This reproduces, for Summary mode, the exact failure mode
`docs/development/current/status.md` already recorded for Detailed mode
(`DET-010`–`DET-014`: "Instruction-only fixes show diminishing returns; a
validate-and-repair loop needs an ADR first").

### Why this happened despite ADR-004 already deciding the fix

[ADR-2026-07-30-004](../2026-07-30/ADR-2026-07-30-004-deterministic-summary-delivery.md)
decided, on 2026-07-30, that the Summary Agent should emit one JSON payload
and that `render_summary.py` should be the sole Markdown producer, finalized
by the acceptance harness. `TICKET-LIST-2026-07-30-003` broke this into
DEL-001 (renderer/validator JSON↔Korean-label mapping) through DEL-004 (E2E
gate). Checking the current code:

- DEL-001 is implemented: `render_summary.py` imports `EVIDENCE_STATUSES`,
  `MARKDOWN_VERSION_MARKER`, `OPEN_ITEM_LABELS`, `validate_json_payload` from
  `report_contract.py`, and the Quality Gate's renderer/validator tests pass.
- DEL-002/DEL-003/DEL-004 are **not** implemented. `runtime/agents/kubernetes-migration-analyzer.md`
  still instructs the model to author the final Markdown report directly
  ("the final assistant response must be the completed Markdown report...
  Do not emit JSON"). `scripts/run_opencode_acceptance.py:518`
  (`retain_summary_markdown`) takes the model's raw text, slices from the
  `# Kubernetes 설계 입력 요약` marker, and validates *that* directly — it never
  calls `render_summary.py` or expects JSON. `runtime/opencode.json` has no
  `response_format`/JSON-schema constraint on the provider.

So the decision was made but never carried out for Summary; the live path is
still "the model free-writes the final Markdown," which is exactly the
non-deterministic path this ADR's evidence reproduces.

### Research: local-LLM output-format idempotency, general practice

- Prompt-only formatting instructions do not reliably force a small/local
  model's exact output shape, especially with `reasoningEffort: "none"` and a
  long, rule-dense system prompt; this matches the observed run-to-run drift
  and cross-script token leakage. ([Deepchecks: LLM Output Consistency](https://deepchecks.com/glossary/llm-output-consistency/), [Ensuring Consistent Outputs Across Different LLMs](https://dayanand-shah.medium.com/ensuring-consistent-outputs-across-different-llms-a-deep-dive-176edff5517d))
- The reliable mitigation used in production systems is schema-first
  generation: have the model emit structured data validated against a schema
  (Pydantic/JSON Schema), then render presentation deterministically outside
  the model; retry against validator feedback when generation still drifts. ([Structured Outputs for Consistent LLM Responses](https://technofile.substack.com/p/structured-outputs-for-consistent), [How to Ensure Reliability in LLM Applications](https://towardsdatascience.com/how-to-ensure-reliability-in-llm-applications/))
- `sglang` (this project's provider engine) natively supports grammar/JSON-schema-constrained
  decoding (XGrammar-backed), which *guarantees* schema-valid output at the
  token level rather than relying on the model choosing to comply — a
  stronger guarantee than prompt instructions alone. ([SGLang: Structured Outputs](https://sgl-project-sglang-93.mintlify.app/advanced/structured-outputs), [SGLang and the Rise of Engine-Level Structured Output](https://builderai.tools/blog/sglang-and-the-structured-output-renaissance))

This means DEL-002 as originally scoped ("update the Summary Agent and
command instructions to require exactly one JSON object") is necessary but,
on its own, is still an instruction-only fix of the same kind
`status.md` already flagged as showing diminishing returns for Detailed
mode. It should be paired with an engine-level constraint.

## Decision

1. Implement DEL-002 and DEL-003 from `TICKET-LIST-2026-07-30-003` as
   specified (JSON-only Summary Agent; harness finalizer that calls
   `render_summary.py` and `validate_report.py`/`validate_target_report.py`
   and only ever exposes the rendered, validated Markdown).
2. Add a provider-level constraint beyond DEL-002's prompt instruction: set
   `response_format` (JSON-schema mode) on the `local-sglang` provider
   options in `runtime/opencode.json` for the Summary command, using
   `schemas/analysis-result.schema.json` (or a Summary-scoped subset) as the
   schema, so malformed JSON is structurally impossible rather than merely
   discouraged. If OpenCode 1.18's provider options do not expose
   `response_format` passthrough to the underlying OpenAI-compatible call,
   record that as a discovered constraint and fall back to DEL-002 alone
   plus the DEL-003 finalizer's existing validate/reject behavior.
3. Defer DEL-004's full E2E gate extension (retaining JSON + rendered
   Markdown + diagnostics as permanent artifacts, gating CI on it) to a
   follow-up ticket; today's scope is making one live Summary run
   deterministically pass end to end.

## Implementation note (same day, after Decision)

Implemented decision item 1 (DEL-002 + DEL-003) in full. Decision item 2
(provider-level `response_format` JSON-schema constraint) was **not**
attempted this session — after implementing the prompt-only JSON contract
and live-verifying it worked, the remaining risk (schema-constrained
decoding wiring, unknown OpenCode 1.18 passthrough support) was judged not
worth taking on immediately before a demo. It remains open, tracked below.

- `runtime/agents/kubernetes-migration-analyzer.md`: the Summary instruction
  now requires exactly one JSON object (no Markdown/fence/prose), with a
  `## Summary JSON contract` section giving the full field shape and one
  worked example. Detailed mode instructions are unchanged.
- `scripts/run_opencode_acceptance.py`: added `extract_json_object` (tolerant
  of a stray code fence or surrounding prose) and rewrote
  `retain_summary_markdown` to parse JSON, call `render_summary()`, validate
  with `validate_report.py --repo-root`, and finalize the `Validation:
  pending` → `passed` receipt via `validate_target_report.finalize()`.
- `tests/test_opencode_adapter.py`: replaced the three tests that exercised
  the old raw-Markdown contract with JSON-payload equivalents (including a
  stray-code-fence case) and updated the prompt-contract test to assert the
  new instruction text.
- **Live verification**: ran `slash-default-summary` against
  `demo-repositories/jpetstore-6` with the real provider
  (`172.16.4.249:30000`) twice.
  - Run 1 (this pipeline): `PASS` — `Validation: passed`, correct five-section
    v2 structure, target repository git status unchanged before/after.
  - Both earlier pre-fix live runs (recorded above in Context) had failed
    Markdown validation with two different, mutually inconsistent heading
    structures; this run's Markdown structure is byte-for-byte the
    renderer's deterministic output regardless of what the model wrote, so
    the class of failure this ADR targets is closed for this run.
- `python scripts/run_quality_gate.py`: 148/149 pass; the one remaining
  failure is the pre-existing, unrelated VS-019 (Windows `ln -s` junction
  issue), confirmed present before this change too.

## Consequences

- Summary delivery converges on the pipeline ADR-004 already decided:
  `Agent JSON -> render_summary.py -> validate_report.py -> validate_target_report.py -> Markdown`.
- If the provider-level JSON-schema constraint is available, format failures
  become structurally impossible for Summary instead of probabilistically
  reduced.
- This does not fix Detailed mode (`DET-010`–`DET-014`); that queue's own
  "validate-and-repair loop needs an ADR first" blocker should reference this
  ADR's pattern once Summary delivery is confirmed working live.
- `docs/development/current/status.md` has a new `DEL-002 — DEL-003` row
  recording this outcome.
- Residual risk: JSON emission is still prompt-only, not schema-constrained
  at the engine level. A local model can still fail to emit parseable JSON
  on a given run; `retain_summary_markdown` reports that as a clear `FAIL
  (Summary output is not valid JSON: ...)` rather than silently accepting
  malformed Markdown, but it does not guarantee every run succeeds. Decision
  item 2 (sglang `response_format`) remains the way to close that gap and is
  left for a follow-up ticket.
