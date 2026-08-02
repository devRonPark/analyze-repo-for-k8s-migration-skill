# Tool-Using Agent Design Principles and Best Practices

## Purpose

This document is a provider- and repository-neutral guide for designing
tool-using agents. Reuse it when creating a new agent or improving tool-call
accuracy, structured-output reliability, recovery behavior, and evaluation.

The central lesson is:

> Prompts guide model choices, schemas constrain representable inputs, the
> runtime controls execution, and validators judge results. None of these
> layers replaces the others.

Every public tool contract has two equally important audiences:

- **LLM-readable:** the natural-language specification must let the model choose
  the right tool, construct a valid call, interpret the result, and decide what
  to do next without reading implementation code.
- **Machine-validatable:** JSON Schema and runtime checks must enforce the name,
  types, required fields, bounds, permissions, and phase rules.

A strict schema with an unreadable description causes selection errors. A clear
description without runtime validation allows invalid calls to execute.

## Why a system prompt alone is insufficient

An explicit instruction such as “call only these eight tools” is necessary,
but it is behavioral guidance rather than an authorization boundary. A model
or an OpenAI-compatible provider can still alter a tool name, omit arguments,
produce malformed JSON, or terminate with prose.

The opposite approach is also incomplete. A runtime allowlist can block unsafe
calls, but short and vague tool descriptions will not improve correct tool
selection. Reliable designs layer the following controls:

```text
System instruction
  -> Tool definitions and JSON Schema
  -> Adapter protocol gate
  -> Runtime authorization and argument validation
  -> Tool-result contract
  -> Final structured-output validation
  -> Typed, bounded recovery
  -> Trajectory and final-result evaluation
```

## 1. Use system instructions for role, flow, and boundaries

An effective system instruction usually presents information in this order:

1. The agent's role and success criteria
2. The exact list of allowed tools
3. The step-by-step workflow and tools appropriate to each phase
4. Prohibited behavior and safety boundaries
5. Termination conditions and final-output contract
6. Recovery rules

Do not merely list tools. Explain when, why, and under which preconditions the
agent should call each one. Avoid accumulating every exception in one long
paragraph. Separate role, tool policy, workflow, evidence rules, and termination
contract under clear headings.

Project-specific example allowlist section (replace the names for other agents):

```text
TOOL POLICY
- The only callable tools are inspect_target, list_tree, find_files,
  search_text, read_file, read_file_lines, inspect_git_metadata, and
  validate_analysis.
- Never invent, infer, alias, abbreviate, or call any other tool name.
- If a needed capability is unavailable, do not invent a tool. Record the
  requirement as unresolved.
- Do not report success until the terminal validator returns an accepted,
  terminal result.
```

This policy must be backed by a runtime allowlist.

## 2. Treat every tool description as an operating manual

A tool description is not a one-line expansion of the function name. It should
explain at least:

- What the tool does
- When to call it
- When not to call it
- The meaning, format, and limits of every argument
- The important result fields and how to use them
- Side effects, limitations, and information it does not return
- The allowed next action after an error

Anthropic identifies detailed descriptions as the most important factor in tool
performance and recommends at least three to four sentences for non-trivial
tools. OpenAI and Google similarly recommend precise descriptions of purpose,
parameter formats, and invocation conditions.

Use this template:

```text
Purpose: The tool's single observable responsibility.
Use when: Concrete invocation conditions and required prior observations.
Do not use when: Commonly confused tools or prohibited situations.
Arguments: Format, units, boundaries, and examples for every argument.
Returns: Stable fields and what the result proves or does not prove.
On error: Whether retry is allowed and which next actions are valid.
```

Apply the “intern test”: if a human cannot call the tool correctly using only
its description and schema, a model is unlikely to call it reliably either.

## 3. Make invalid states difficult to represent in schemas

- Prefer enums over ambiguous combinations of booleans.
- Declare all expected object fields and use `additionalProperties: false`
  where supported.
- Mark mandatory fields as `required`.
- If a provider's strict schema requires every field, represent optional values
  with a supported nullable union rather than silently omitting constraints.
- Keep parameter names short, descriptive, case-consistent, and identical in
  the prompt, schema, and implementation.
- Reduce unnecessary nesting, large unions, and arguments the model does not
  need to supply.
- Inject IDs, paths, or state in application code when they are already known.

Use strict function calling or structured outputs when the provider officially
supports them. Do not assume that an OpenAI-compatible endpoint supports every
OpenAI strict-schema option. When support is unclear, use a broadly compatible
schema plus mandatory local validation. Enable strict features only after
capability testing.

## 4. Separate exploration calls from the final-result contract

Function calling is appropriate for observing external data or requesting an
action. A precise final response should use structured outputs or a terminal
validation tool. A prose instruction to “return JSON at the end” does not
guarantee schema adherence.

Give the agent an explicit terminal action:

```text
Observation tools -> build candidate -> call terminal validator
  accepted terminal result -> terminate successfully
  structured validation error -> repair only reported issues and retry within bounds
```

Tool-argument conformance and final-user-response conformance are different
problems. Validate both independently.

## 5. Keep the adapter a translation layer, not a reasoning layer

An adapter may translate protocol dialects, preserve call IDs, redact secrets,
convert supported JSON Schema subsets, and repair a known wire variation from a
closed alias table.

An adapter should not:

- Guess the nearest allowed tool for an unknown name
- Replace malformed JSON arguments with an empty object and execute the call
- Invent missing evidence status or semantic relationships
- Link findings to evidence by lexical similarity
- Add provider-name-specific business logic

Automatic correction is safe only when the original intent has exactly one
possible syntactic interpretation. Any correction should be observable. Errors
that require semantic judgment should become typed protocol errors.

## 6. Make the runtime the actual authorization boundary

Before executing a model-generated call, verify in order:

1. The tool name is in the exact allowlist.
2. The call ID and protocol sequence are valid.
3. Arguments parse as JSON.
4. Arguments conform to that tool's schema.
5. The call is allowed in the current agent phase.
6. Application guardrails such as path, budget, and authorization pass.

Do not execute the tool if any check fails. Prevent unknown names from reaching
application code and return a structured error such as `invalid_tool_name`.

Treat repository content, web content, database rows, and tool results as
untrusted observations rather than instructions. A tool result may inform the
next decision, but it must not override the system instruction, tool policy, or
runtime guardrails.

## 7. Return concise, structured, next-action-oriented tool results

Use stable envelopes for both success and failure. The following is a
repository-analysis-specific example; use domain-appropriate names elsewhere:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_line_range",
    "category": "validation",
    "path": "$.line_end",
    "message": "line_end exceeds the file length",
    "retryable": true,
    "allowed_next_actions": ["read_file_lines", "validate_analysis"]
  }
}
```

Do not combine validation failures into a long prose paragraph. Separate a
machine-readable code, JSON Pointer or field path, safe message, retryability,
and allowed next actions. Return only high-signal data needed for the next
decision; large internal payloads waste context and reduce accuracy.

`allowed_next_actions` must be computed from the runtime's current phase,
remaining budget, and blocked call signatures. Do not maintain a separate,
hard-coded list that can drift from the actual policy.

HTTP APIs provide a useful analogy, but local domain tools should not invent
HTTP status numbers. Preserve a real upstream HTTP status when it is relevant;
otherwise prefer stable domain codes such as `invalid_arguments`,
`forbidden_path`, `not_found`, `duplicate_call`, and `budget_exhausted`. The
model needs the error meaning and valid next action, not a decorative `400` or
`404`.

## 8. Design recovery as a state machine, not a generic reprompt

A generic “try again” prompt often reproduces the same failure. Define an
error-specific transition for each failure class.

| Error class | Recovery action |
| --- | --- |
| `invalid_tool_name` | Re-send the exact allowlist and permit one new call |
| `malformed_arguments` | Return the schema and failing fields; rewrite arguments |
| `tool_guardrail` | Forbid the same call; choose a safe observation or unresolved state |
| `candidate_schema` | Repair validation paths and resubmit the complete candidate |
| `evidence_grounding` | Apply exact verified corrections or mark the claim unresolved |
| `duplicate_call` | Block the signature; choose different arguments or terminal validation |
| `budget_exhausted` | Stop exploration and submit partial or failed from collected evidence |

Track total retries, retries by error class, tool-call signatures, and canonical
candidate fingerprints. An identical candidate or call is not progress and
should consume or terminate the retry budget.

## 9. Separate safe syntactic repair from unsafe semantic repair

Examples of safe repair:

- Map a known `search_records_args` wire variation to `search_records` through
  a closed alias table established from an observed provider defect.
- Apply an exact line or excerpt correction verified from repository content.
- Attach an `executed=false` result to a protocol call whose result is missing.

Examples of unsafe repair:

- Fill an empty top-level status with `complete` based on surrounding data.
- Generate missing evidence IDs and connect findings automatically.
- Guess evidence links from overlapping claim tokens.
- Invent default unresolved owners, sources, or reasons.

Unsafe repair can make a payload pass schema validation while reducing semantic
accuracy. A validator should judge the result, not author the result on the
model's behalf.

## 10. Distinguish protocol success from domain success

- Protocol success means the agent used only allowed tools, maintained valid
  call/result history, and produced schema-valid output.
- Domain success means the result satisfies the task with sufficient real
  evidence.

A valid `partial` result can be a protocol success without satisfying an
acceptance target that requires `complete`. Conversely, an auto-filled
`complete` result is not domain success.

LLMs are probabilistic, so no design can guarantee semantic success for every
future live run. Code can and should guarantee that unsafe calls are blocked,
invalid output is never reported as success, retries terminate, and failures are
structured. Define quality targets as repeated live-evaluation rates.

## 11. Evaluate both trajectory and final output

Agent evaluation needs two dimensions:

- Trajectory: allowed tool selection, correct ordering, no duplicate/no-progress
  loop, and error-appropriate recovery
- Final result: schema conformance, evidence grounding, internal consistency,
  redaction, and required terminal status

Inject malformed tool names, invalid JSON arguments, unknown fields, missing
required fields, invalid line ranges, duplicates, context truncation, prose-only
finals, and invalid candidates into deterministic tests. For live evaluation,
measure repeated success rates and failure distributions rather than citing one
successful run.

## Design checklist

### System instruction

- [ ] Does it include an exact tool allowlist and prohibit invented tools?
- [ ] Are role, flow, safety, and termination contracts separated?
- [ ] Does it explain when and why to use each tool?
- [ ] Are success, partial, and failed conditions distinct?

### Tool contract

- [ ] Does each description cover use, avoidance, arguments, returns, limits,
  and errors?
- [ ] Can the LLM decide when to call the tool and what to do with each result
  using only the public specification?
- [ ] Are parameters narrowed with strong types, enums, and required fields?
- [ ] Can a human call the tool correctly using only its public contract?
- [ ] Is the result concise, stable, and high-signal?

### Adapter and runtime

- [ ] Is the exact allowlist enforced before execution?
- [ ] Are malformed JSON arguments rejected rather than executed as `{}`?
- [ ] Are call IDs and corresponding tool results preserved?
- [ ] Is automatic repair limited to closed, syntactic transformations?
- [ ] Do unknown calls become structured, safe failures?
- [ ] Are tool results treated as untrusted observations rather than
  instructions?

### Recovery and evaluation

- [ ] Does each error code have a distinct recovery action?
- [ ] Are retries, iterations, and no-progress bounded?
- [ ] Are identical candidate fingerprints detected?
- [ ] Are both trajectory and final result evaluated?
- [ ] Does live acceptance use a repeated-run criterion?

## Official learning materials

The principles above were synthesized from the following primary sources:

- [Google ADK: LLM Agent instructions](https://adk.dev/agents/llm-agents/)
  explains that instructions should define the task, constraints, tool purpose,
  invocation circumstances, and output format.
- [Google ADK: Tool execution callbacks](https://adk.dev/callbacks/types-of-callbacks/)
  documents the execution-time interception point for inspecting arguments,
  enforcing authorization, modifying safe inputs, or skipping a call.
- [Google ADK: Agent evaluation](https://adk.dev/evaluate/) distinguishes tool-use
  trajectory evaluation from final-response evaluation and recommends automated
  evaluation beyond traditional deterministic tests.
- [Gemini API: Function calling](https://ai.google.dev/gemini-api/docs/function-calling)
  recommends clear descriptions, descriptive names, strong types, bounded active
  tool sets, validation before execution, and robust error handling.
- [Gemini Live API: Best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices)
  recommends ordered system instructions, distinct tool-call steps, precise tool
  definitions, explicit invocation conditions, and focused prompts.
- [OpenAI API: Function calling](https://developers.openai.com/api/docs/guides/function-calling)
  recommends explicit purpose and parameter descriptions, when/not-when guidance,
  enums that make invalid states unrepresentable, small active tool sets, and
  application-side handling of call IDs and results.
- [OpenAI API: Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
  distinguishes function calling from final structured responses and explains
  strict-schema requirements and JSON mode's limitations.
- [Claude Platform: Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
  emphasizes detailed descriptions covering what, when, parameters, limitations,
  and high-signal results, with examples for complex schemas.
- [Claude Platform: Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
  separates strict tool-input validation from schema-constrained final output and
  documents invalid-output edge cases.
