# ADR-2026-07-30-004: Deliver Summary v2 through a deterministic finalizer

- Status: Proposed
- Date: 2026-07-30
- Related tickets: [TICKET-LIST-2026-07-30-003-deterministic-summary-delivery.md](TICKET-LIST-2026-07-30-003-deterministic-summary-delivery.md)
- Supersedes: no decision; extends [ADR-2026-07-30-002-summary-mode-v2.md](ADR-2026-07-30-002-summary-mode-v2.md)

## Context

The OpenCode E2E run produced useful repository analysis but failed the Summary
v2 Markdown contract. The model emitted progress text before the report,
omitted the contract marker, changed required Markdown syntax, and appended
natural-language explanations to evidence cells. Prompt wording cannot make
these formatting rules deterministic.

Requiring users to run a separate CLI wrapper would make the existing
`/analyze-repo-for-kubernetes` experience worse. The user must continue to
invoke the same OpenCode command and receive one final Markdown report.

## Decision

Summary delivery has one internal pipeline:

```text
OpenCode Agent JSON -> acceptance harness -> render_summary.py
                       -> validate_report.py -> validate_target_report.py
                       -> visible Markdown
```

1. The Summary Agent returns one JSON payload conforming to the Summary JSON
   contract. It does not generate user-facing Markdown.
2. `render_summary.py` is the only producer of Summary v2 Markdown. No
   Markdown repair, tolerant parsing, or regex cleanup layer is introduced.
3. The finalizer validates rendered Markdown before replacing `Validation:
   pending` with `Validation: passed`. A failed render or validation never
   exposes a passed receipt.
4. The acceptance harness owns finalization and replaces its visible Summary
   result with the validated renderer output. OpenCode 1.18 plugins expose
   event observation but no completed-response replacement hook, so no local
   plugin is bundled.
5. Raw Agent JSON, progress messages, and diagnostics remain E2E artifacts;
   they are not the user-facing report.

## Open item display contract

The JSON enum remains stable while Markdown uses Korean labels:

| Internal enum | Markdown label | Verdict effect |
|---|---|---|
| `hard_blocker` | 설계 차단 | requires `추가 정보 필요` |
| `open_design_decision` | 설계 결정 | does not block initial design |
| `deployment_value` | 배포 입력 | does not block initial design |
| `recommendation` | 권장 사항 | does not block design or deployment |

The renderer owns this mapping. The validator accepts only the Korean display
labels in Summary Markdown and checks verdict consistency through the mapped
classification.

## Consequences

- Repeated runs may differ in repository interpretation, but valid JSON always
  renders into the same Summary v2 structure.
- The user does not learn or run an additional command.
- Harness finalization is part of the supported acceptance runtime.
- Detailed mode and explicit legacy Markdown validation remain unchanged.
