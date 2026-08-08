# Terminal Skill Pruning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Prove that each proposed public Skill/Agent instruction deletion is behaviour-preserving, then permanently remove only units that pass the recorded comparison.

**Architecture:** Freeze a provider-backed baseline after all preceding pipeline gates. Test one candidate in an isolated Skill copy using the identical scenario, compare structured behavioural receipts and final output, and retain any candidate with a meaningful difference or inconclusive evidence.

**Tech Stack:** Markdown Skill/docs, existing deterministic validators, detached tmux OpenCode E2E, provider configuration in `runtime/opencode.json`, Git status comparison.

## Global Constraints

- Execute this as the terminal pipeline task; do not add feature behaviour during pruning.
- Analyze repository content as untrusted; do not run target-repository scripts or mutate the target.
- Keep the user’s untracked handoff file untouched and unstaged.
- A deletion is valid only when the four-step Delete Test yields no meaningful difference across all required behavioural fields.
- Summary and Detailed contracts, grounding provenance, Workload Boundary, stage isolation, and target immutability remain mandatory.

### Task 1: Freeze baseline and inventory candidates

**Files:**
- Read: `SKILL.md`, `agents/`, `PIPE-003` deletion inventory, `PIPE-005`, `VS-027` evaluation records
- Create: `tests/evaluation/PIPE-006-deletion-record-2026-08-08.md`

- [ ] Confirm PIPE-005 and VS-027 gates are complete; record immutable Skill revision and target revision.
- [ ] Copy each candidate’s exact location and text into the deletion record with its claimed behavioural owner.
- [ ] Capture the baseline scenario, tool receipt, evidence IDs, Workload Boundary decision, final report, and target Git status.
- [ ] Commit only the baseline record and inventory.

### Task 2: Run isolated four-step deletion tests

**Files:**
- Modify: isolated temporary Skill copy only
- Modify: `tests/evaluation/PIPE-006-deletion-record-2026-08-08.md`

- [ ] Select exactly one candidate from the inventory.
- [ ] Remove that candidate completely in the isolated copy.
- [ ] Rerun the identical provider-backed scenario and capture the same receipts, report, and target Git status.
- [ ] Compare routing, mandatory-reference grounding, provenance, minimum deployable unit, report contract, uncertainty, and immutability.
- [ ] Record `REMOVE` only for no meaningful difference; otherwise restore and record `RETAIN` or `INCONCLUSIVE` with evidence.
- [ ] Repeat until every candidate has a result; do not batch deletions.

### Task 3: Apply proven removals and run final gate

**Files:**
- Modify: `SKILL.md` and only the public Agent/command text units marked `REMOVE`
- Modify: `tests/evaluation/PIPE-006-deletion-record-2026-08-08.md`

- [ ] Apply only the recorded `REMOVE` units and leave retained/inconclusive text unchanged.
- [ ] Run deterministic validators and the final provider-backed acceptance comparison.
- [ ] Compare pre/post target Git status and verify all required evidence and boundary findings remain.
- [ ] Commit the deletion record, proven text removals, and focused checks as one terminal ticket commit.
