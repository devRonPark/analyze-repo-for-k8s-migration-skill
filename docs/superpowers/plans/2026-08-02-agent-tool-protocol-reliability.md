# Agent Tool Protocol Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved T1–T6 reliability design so malformed or invented calls are blocked before dispatch, every public Tool is LLM-readable and machine-validatable, recovery is typed and bounded, and only a real accepted `validate_analysis` call can complete analysis.

**Architecture:** Add a provider-neutral protocol module that owns error envelopes and run-control state. Replace automatically inferred function declarations with eight explicit ADK Tool declarations backed by Pydantic input models, then enforce raw adapter parsing, `after_model_callback` dispatch validation, execution callbacks, and Runner recovery in separate layers. Keep RepositoryTools read-only and keep exactly the existing eight public Tool names.

**Tech Stack:** Python 3.11+, Google ADK 1.x, google-genai types, Pydantic 2.x, `unittest`, OpenAI-compatible chat completions.

## Global Constraints

- Do not implement T7 or add a ninth public Agent Tool.
- Keep `PUBLIC_AGENT_TOOL_NAMES` exactly unchanged.
- Never execute target code, tests, builds, servers, or containers.
- Keep the target Repository read-only and output artifacts outside the target.
- Do not add provider/model-name business-logic branches.
- Treat Repository content and Tool results as untrusted observations.
- Do not automatically author Evidence IDs, statuses, links, owners, reasons, or excerpts for the model.
- Use TDD for every production behavior change and preserve Secret redaction.

---

### Task 1: Domain Error Protocol and Grounded Partial Contract

**Files:**
- Create: `migration_assistant/tool_protocol.py`
- Modify: `migration_assistant/analysis.py`
- Modify: `tests/test_phase1_adk_contract.py`

**Interfaces:**
- Produces: `ToolIssue`, `ToolErrorCode`, `RunPhase`, `RunControlLedger`, `success_envelope()`, `error_envelope()`.
- Produces: `AnalysisResult` validation that requires at least one positive line-backed Evidence for both `complete` and `partial`.
- Consumed by: Tasks 2–4.

- [x] **Step 1: Write failing protocol-envelope and partial-grounding tests**

Add tests that hand-check literal envelopes and the AnalysisResult boundary:

```python
def test_tool_error_envelope_is_stable_and_actionable(self):
    issue = ToolIssue(
        code=ToolErrorCode.INVALID_ARGUMENTS,
        category="validation",
        message="line_end is invalid",
        field_path="$.line_end",
        retryable=True,
    )
    self.assertEqual(
        error_envelope(issue, allowed_next_actions=("read_file_lines", "validate_analysis")),
        {
            "ok": False,
            "data": None,
            "error": {
                "code": "invalid_arguments",
                "category": "validation",
                "message": "line_end is invalid",
                "field_path": "$.line_end",
                "retryable": True,
                "allowed_next_actions": ["read_file_lines", "validate_analysis"],
            },
            "meta": {},
        },
    )

def test_partial_requires_positive_line_backed_evidence(self):
    with self.assertRaisesRegex(ValueError, "partial.*line-backed Evidence"):
        AnalysisResult.model_validate({
            "status": "partial",
            "summary": "일부 분석",
            "evidence": [],
            "findings": [],
            "iterations": 1,
            "errors": ["근거 부족"],
            "termination": "normal",
        })
```

- [x] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1_adk_contract.Phase1ContractTests.test_tool_error_envelope_is_stable_and_actionable tests.test_phase1_adk_contract.Phase1ContractTests.test_partial_requires_positive_line_backed_evidence -v
```

Expected: import failure for `tool_protocol` and the old evidence-free partial behavior.

- [x] **Step 3: Implement the minimal protocol types and partial validator**

Implement immutable issue data and one envelope shape:

```python
class ToolErrorCode(StrEnum):
    INVALID_TOOL_NAME = "invalid_tool_name"
    MALFORMED_ARGUMENTS = "malformed_arguments"
    INVALID_ARGUMENTS = "invalid_arguments"
    FORBIDDEN_PATH = "forbidden_path"
    NOT_FOUND = "not_found"
    DUPLICATE_CALL = "duplicate_call"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANDIDATE_SCHEMA = "candidate_schema"
    EVIDENCE_GROUNDING = "evidence_grounding"

@dataclass(frozen=True, slots=True)
class ToolIssue:
    code: ToolErrorCode
    category: str
    message: str
    field_path: str | None = None
    retryable: bool = False
```

`RunControlLedger` must own `phase`, `protocol_issue`, retry counts, blocked signatures, and `last_candidate_hash`. In `AnalysisResult.validate_status`, require non-unresolved Evidence with path, line range, claim, and excerpt for `partial` as well as `complete`.

- [x] **Step 4: Run Task 1 tests and focused schema regressions**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1_adk_contract tests.test_analysis_vertical_slice -v
```

Expected: Task 1 tests pass; existing tests that intentionally encode the old evidence-free partial behavior may now fail and must be updated only when their asserted contract conflicts with the approved design.

- [x] **Step 5: Commit Task 1**

```powershell
git add migration_assistant/tool_protocol.py migration_assistant/analysis.py tests/test_phase1_adk_contract.py tests/test_analysis_vertical_slice.py
git commit -m "feat: add typed agent tool protocol"
```

---

### Task 2: Explicit LLM-Readable Tool Declarations and Uniform Results

**Files:**
- Create: `migration_assistant/adk_function_tool.py`
- Modify: `migration_assistant/adk_tools.py`
- Modify: `migration_assistant/repository_tools.py`
- Modify: `migration_assistant/analysis.py`
- Modify: `tests/test_phase1_adk_contract.py`
- Modify: `tests/test_adk_agent.py`

**Interfaces:**
- Consumes: Task 1 envelopes and issue types.
- Produces: `RepositoryFunctionTool(BaseTool)` with explicit `FunctionDeclaration`, Pydantic argument validation, and a raw handler.
- Produces: eight Tool declarations with exact names, descriptions, and nested `ValidateAnalysisArgs` schema.

- [x] **Step 1: Write failing declaration and Tool-result tests**

Add behavior tests that inspect the actual wire declaration generated through `OpenAICompatibleAdkLlm._tools` and execute a real Tool object:

```python
def test_public_tool_descriptions_are_llm_readable(self):
    tools = self.make_toolset().functions()
    by_name = {tool.name: tool for tool in tools}
    self.assertIn("Use when", by_name["search_text"].description)
    self.assertIn("Do not use when", by_name["search_text"].description)
    self.assertIn("Python regular expression", by_name["search_text"].description)
    self.assertIn("glob", by_name["find_files"].description)
    self.assertIn("On error", by_name["read_file_lines"].description)

def test_validate_analysis_wire_schema_has_typed_items(self):
    wire = self.wire_tools(self.make_toolset())
    validate = next(item for item in wire if item["function"]["name"] == "validate_analysis")
    parameters = validate["function"]["parameters"]
    evidence_items = parameters["properties"]["evidence"]["items"]
    evidence_schema = parameters["$defs"][evidence_items["$ref"].removeprefix("#/$defs/")]
    self.assertIn("properties", evidence_schema)
    self.assertEqual(
        evidence_schema["properties"]["status"]["enum"],
        ["confirmed", "inferred", "unresolved", "conflicting"],
    )
```

Add an async execution test asserting invalid arguments return `ok=false`, `code=invalid_arguments`, and no Repository operation is performed.

- [x] **Step 2: Run the declaration tests and verify RED**

Run the named tests with `unittest -v`.

Expected: current short docstrings lack the required usage sections; `validate_analysis` exposes `list[dict]` without item properties; current Tool methods do not use the uniform envelope.

- [x] **Step 3: Implement explicit input models and `RepositoryFunctionTool`**

Define Pydantic argument models for all eight Tools. Use `ConfigDict(extra="forbid")`, descriptive `Field` metadata, and exact nested models `ValidateEvidenceInput` and `ValidateFindingInput`. Their `status` fields must use `Literal["confirmed", "inferred", "unresolved", "conflicting"]`; `ValidateAnalysisArgs.evidence` and `.findings` must be `list[ValidateEvidenceInput]` and `list[ValidateFindingInput]`, not `list[dict]`. Reuse these types for runtime validation, then convert their `model_dump(mode="json")` values into `AnalysisResult`. `RepositoryFunctionTool._get_declaration()` must return:

```python
types.FunctionDeclaration(
    name=self.name,
    description=self.description,
    parameters_json_schema=self.input_model.model_json_schema(),
)
```

`run_async()` must validate `args` before invoking the handler and return `error_envelope()` on `ValidationError`. The first Pydantic error location becomes a JSONPath-like `field_path` such as `$.line_end`; messages must be Secret-redacted. It must wrap successful raw observations with `success_envelope(data)` and set `meta.terminal=true` only for an accepted `validate_analysis` result.

Replace substring-based `_recovery_action()` with typed `RepositoryToolError` fields. Assign concrete codes at each raise site: excluded/path escape → `forbidden_path`, missing file/line → `not_found`, malformed regex/range → `invalid_arguments`, and budget exceptions → `budget_exhausted`.

- [x] **Step 4: Run declaration, Tool, and Agent registration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1_adk_contract tests.test_adk_agent tests.test_model_compatibility -v
```

Expected: exactly eight Tools remain registered; wire schemas contain nested item constraints; invalid calls return one envelope shape.

- [x] **Step 5: Commit Task 2**

```powershell
git add migration_assistant/adk_function_tool.py migration_assistant/adk_tools.py migration_assistant/repository_tools.py migration_assistant/analysis.py tests/test_phase1_adk_contract.py tests/test_adk_agent.py
git commit -m "feat: publish llm-readable repository tools"
```

---

### Task 3: Raw Adapter Parsing and Model-Independent Dispatch Gate

**Files:**
- Modify: `migration_assistant/adk_model.py`
- Modify: `migration_assistant/agent.py`
- Modify: `migration_assistant/adk_tools.py`
- Modify: `tests/test_phase1_adk_contract.py`

**Interfaces:**
- Consumes: Task 1 `RunControlLedger` and Task 2 Tool registry/input models.
- Produces: adapter protocol issues in `LlmResponse.custom_metadata`.
- Produces: `AdkRepositoryToolset.after_model_callback(callback_context, llm_response)`.

- [x] **Step 1: Write failing malformed-response and callback tests**

Cover three real boundary behaviors:

```python
def test_malformed_raw_arguments_are_not_replaced_with_empty_object(self):
    response = OpenAICompatibleAdkLlm._response(self.raw_call("read_file", '{"relative":"broken'))
    self.assertEqual(response.content.parts[0].text, "Tool protocol validation failed.")
    self.assertEqual(response.custom_metadata["protocol_issue"]["code"], "malformed_arguments")
    self.assertFalse(any(part.function_call for part in response.content.parts))

def test_after_model_callback_blocks_unknown_name_before_adk_dispatch(self):
    response = self.llm_response_call("shell", {})
    replaced = self.make_toolset().after_model_callback(self.callback_context(), response)
    self.assertEqual(self.control.protocol_issue.code, ToolErrorCode.INVALID_TOOL_NAME)
    self.assertFalse(any(part.function_call for part in replaced.content.parts))

def test_closed_alias_is_canonicalized_but_embedded_json_suffix_is_rejected(self):
    accepted = self.callback(self.llm_response_call("read_filearg", {"relative": "pom.xml"}))
    self.assertEqual(accepted.content.parts[0].function_call.name, "read_file")
    rejected = self.callback(self.llm_response_call('read_fileargs{"relative":"pom.xml"}', {}))
    self.assertEqual(self.control.protocol_issue.code, ToolErrorCode.INVALID_TOOL_NAME)
```

- [x] **Step 2: Run the callback tests and verify RED**

Expected: malformed JSON currently becomes `{}`, unknown names pass to ADK, and embedded JSON suffixes are currently accepted.

- [x] **Step 3: Implement raw parsing and `after_model_callback`**

Remove fuzzy/prefix normalization from `_response`. Raw JSON parse failure or non-object arguments must produce a text-only `LlmResponse` with redacted `custom_metadata.protocol_issue`. Preserve an exact raw name in otherwise valid FunctionCalls.

In `after_model_callback`, first consume adapter metadata, then inspect every FunctionCall. Permit exact names and only these closed canonicalizations:

1. Removing underscores yields exactly one public name.
2. An exact or compact public name is followed only by `arg`, `args`, `argument`, or `arguments`, while the separate args object is valid.

Validate args with the registered input model. On any issue, store it in `RunControlLedger` and replace the response with a text-only protocol-error response. Register this callback on `Agent(...)` so it also covers `model_override`.

- [x] **Step 4: Run callback and real Agent lifecycle tests**

Run the relevant named tests, then:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1_adk_contract tests.test_adk_agent -v
```

Expected: unknown and malformed calls never reach ADK dispatch; exact eight-tool registration remains intact.

- [x] **Step 5: Commit Task 3**

```powershell
git add migration_assistant/adk_model.py migration_assistant/agent.py migration_assistant/adk_tools.py tests/test_phase1_adk_contract.py
git commit -m "fix: gate model tool calls before dispatch"
```

---

### Task 4: Typed Runtime Recovery and Validator Non-Authorship

**Files:**
- Modify: `migration_assistant/adk_tools.py`
- Modify: `migration_assistant/adk_runner.py`
- Modify: `migration_assistant/agent.py`
- Modify: `tests/test_phase1_adk_contract.py`
- Modify: `tests/test_adk_agent.py`

**Interfaces:**
- Consumes: `RunControlLedger`, Tool envelopes, explicit Tool registry.
- Produces: `before_tool_callback`, `on_tool_error_callback`, phase transitions, candidate fingerprints, and error-specific Runner recovery.

- [x] **Step 1: Reverse old semantic-repair and zero-tool tests before production edits**

Change tests so they require:

- Wrong excerpt returns `ok=false`, `code=evidence_grounding`, and suggested corrections without committing the candidate.
- Missing status, IDs, evidence links, unresolved metadata are not generated by code.
- A repository-aware zero-tool JSON final cannot become `complete`.
- A protocol-error replacement is not stored as `run.final_text` and starts one bounded recovery turn.
- Repeating the same candidate fingerprint ends no-progress.

- [x] **Step 2: Run reversed tests and verify RED**

Expected: old `_normalize_verified_candidate()` makes several tests fail because it authors semantics; zero-tool parsing still completes a valid candidate.

- [x] **Step 3: Remove semantic auto-repair and implement runtime callbacks**

Delete `_normalize_verified_candidate()`. `validate_analysis` must return typed issues with JSON paths and optional exact repository corrections but leave `ledger.result` unset until the model resubmits a valid candidate.

`before_tool_callback` must enforce phase, blocked signature, and remaining budget before execution. `on_tool_error_callback` must convert argument binding and unexpected Tool exceptions into the same error envelope without exposing Secrets.

- [x] **Step 4: Implement Runner state and error-specific recovery**

In `consume`, check `control.protocol_issue` before writing model text to `run.final_text`; close that stream and transition to `REPAIR`. Generate recovery content from `ToolIssue.code`, field path, schema summary, and runtime-derived allowed actions. Keep two total recovery attempts and reject identical `(error_code, action fingerprint)` or candidate hash.

Post-hoc JSON parsing may produce at most `partial`, only when `control.protocol_issue is None`; a result without positive line-backed Evidence becomes `failed`. Only `ledger.result` accepted through the terminal Tool may become `complete`.

- [x] **Step 5: Run all focused ADK contract tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1_adk_contract tests.test_adk_agent tests.test_model_compatibility tests.test_live_planner -v
```

Expected: all focused tests pass and no test retains the old semantic-repair or zero-tool-complete contract.

- [x] **Step 6: Commit Task 4**

```powershell
git add migration_assistant/adk_tools.py migration_assistant/adk_runner.py migration_assistant/agent.py tests/test_phase1_adk_contract.py tests/test_adk_agent.py
git commit -m "fix: make agent recovery typed and bounded"
```

---

### Task 5: Development-Only Live Acceptance Harness

**Files:**
- Create: `devtools/run_phase1_live_acceptance.py`
- Create: `tests/test_phase1_live_acceptance_harness.py`
- Modify: `docs/phase1-adk-experiment-log.md`

**Interfaces:**
- Produces: CLI arguments `--repository`, `--output-parent`, `--runs` with `--runs` fixed to `3` for gate mode.
- Produces: non-secret JSON summary with commit, budget values, per-run exit/status/trajectory/evidence counts, and aggregate `passed`.
- Extends: `AdkRun` with `terminal: bool = False` and `protocol_issues: list[dict[str, object]]`; only accepted `validate_analysis` sets `terminal=True`.

- [x] **Step 1: Write failing harness tests with a real fake runner function**

Test aggregation behavior without calling a live model:

```python
def test_gate_requires_three_of_three_complete_terminal_runs(self):
    summary = evaluate_runs([
        run(0, "complete", terminal=True),
        run(0, "complete", terminal=True),
        run(2, "partial", terminal=True),
    ])
    self.assertFalse(summary["passed"])
    self.assertEqual(summary["successes"], 2)
    self.assertEqual(summary["required"], 3)
```

Test that output directories are distinct and outside the target, Secret values are absent, and a zero-tool complete-shaped response fails the gate.

- [x] **Step 2: Run harness tests and verify RED**

Expected: `devtools.run_phase1_live_acceptance` does not exist.

- [x] **Step 3: Implement the minimal harness**

The harness must call the existing `analyze()` application boundary without target mutation and capture each run in a separate output directory. Extend `AdkRun` and the application result handoff so the harness receives `terminal` and Secret-safe `protocol_issues` generated by the Runner; do not infer terminal acceptance merely from a `complete`-shaped artifact. Emit one JSON summary containing only repository-relative or output paths, commit, non-secret model settings, budget values, per-run exit/status/terminal/tool-call names/evidence counts/protocol error codes, and aggregate `passed`. It must not contain repository-name branches; the path comes only from `--repository`.

- [x] **Step 4: Run harness unit tests and focused regression suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1_live_acceptance_harness tests.test_phase1_adk_contract -v
```

Expected: all tests pass without network access.

- [x] **Step 5: Commit Task 5**

```powershell
git add devtools/run_phase1_live_acceptance.py tests/test_phase1_live_acceptance_harness.py docs/phase1-adk-experiment-log.md
git commit -m "test: add phase1 live reliability gate"
```

---

### Task 6: Live jpetstore-6 Validation and Regression

**Files:**
- Modify only if evidence requires a design-conformant fix: files from Tasks 1–5 and their tests
- Modify: `docs/phase1-adk-experiment-log.md`

**Interfaces:**
- Consumes: live LLM environment variables and the user-provided local checkout.
- Produces: three isolated run outputs and a Secret-safe acceptance summary.

- [ ] **Step 1: Verify live configuration without printing the key**

Check that `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, and `LLM_MAX_TOKENS` are present; report only presence and non-secret values.

- [ ] **Step 2: Run one diagnostic jpetstore-6 acceptance execution**

Run the harness against `C:\Users\박병찬\Desktop\demo-repositories\jpetstore-6` with a separate output parent. Preserve Tool trajectory and typed error codes.

Expected: either a complete terminal result or a precise typed failure suitable for one TDD correction cycle.

- [ ] **Step 3: For each observed defect, perform a strict TDD fix cycle**

Add one deterministic failing test reproducing the observed protocol/schema/recovery defect, verify RED, implement the minimal provider-neutral fix, and verify GREEN. Do not add repository-name, language, or provider branches.

- [ ] **Step 4: Run the 3/3 gate**

Run exactly three executions with identical commit, budget defaults, and non-secret model settings.

Expected: `passed=true`, `successes=3`, each run has exit 0, `status=complete`, `terminal=true`, a real `validate_analysis` call, and positive line-backed Evidence linked to a Finding.

- [ ] **Step 5: Run cross-repository regressions**

Run one validation each for `spring-petclinic`, `full-stack-fastapi-template`, and the configured Go holdout. A valid Go `partial` is acceptable only when backed by positive line Evidence and genuine unresolved deployment ambiguity.

- [ ] **Step 6: Run final deterministic verification**

Run the focused 36-test command plus the new harness tests, then `git diff --check` and `git status --short`.

- [ ] **Step 7: Commit evidence-backed live fixes and log**

```powershell
git add migration_assistant tests devtools docs/phase1-adk-experiment-log.md
git commit -m "fix: complete live agent protocol recovery"
```
