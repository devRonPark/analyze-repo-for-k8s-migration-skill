# Qwen3.6 Structured-output Research

Research date: 2026-07-30

## Question

Does official evidence show that `Qwen/Qwen3.6-35B-A3B-FP8` is unsuitable for
Markdown tables, and should the Summary contract avoid Markdown altogether?

## Finding

No. The official Qwen3.6 model card documents OpenAI-compatible serving with
SGLang and vLLM, but does not identify a Markdown-table limitation. It also
uses Markdown tables for its published benchmark results. The observed
incomplete Summary is therefore not evidence that the model cannot generate
tables.

The model card says Qwen3.6 thinks by default and provides a non-thinking API
setting. That is a plausible completion-budget factor, but not a table-specific
finding. Its recommended SGLang command includes `--reasoning-parser qwen3`.

## Structured-output option

The official vLLM documentation supports OpenAI-compatible structured outputs:
`json` follows a JSON Schema; `choice`, `regex`, and `grammar` constrain their
respective formats. It also recommends repeating the schema and field-population
instructions in the prompt for better results. Qwen's official Qwen3 deployment
documentation likewise documents `guided_json` with an explicit output-format
instruction. These are serving features, so support must be verified against
the deployed SGLang version and the OpenCode provider path before relying on
them.

## Decision guidance

Keep Markdown as the final user-facing format while the acceptance contract
requires it. If structured decoding is available, the smallest robust design is
schema-constrained JSON extraction followed by deterministic Markdown rendering.
This does not require the model to author Markdown tables.

Do not replace tables based on this research alone. Run the same `jpetstore-6`
scenario with fixed timeout/output budget in table and bullet variants, then
compare final-report completion, contract validity, and golden-set score. Adopt
bullets only if that measurement improves the result; otherwise investigate
reasoning-token budget and the actual stop condition.

## Sources

- [Qwen3.6-35B-A3B-FP8 official model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B-FP8)
  — model/API/serving instructions, default thinking behavior, and benchmark
  tables.
- [Qwen vLLM deployment guide](https://qwen.readthedocs.io/en/stable/deployment/vllm.html)
  — Qwen's `guided_json` structured-output guidance.
- [Qwen SGLang deployment guide](https://qwen.readthedocs.io/en/v3.0/deployment/sglang.html)
  — Qwen structured JSON-output guidance for SGLang.
- [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
  — OpenAI-compatible JSON Schema, choice, regex, grammar, and reasoning-mode
  support.
