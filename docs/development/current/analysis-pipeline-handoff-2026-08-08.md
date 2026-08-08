# Analysis Pipeline Redesign Handoff — 2026-08-08

## Purpose

Resume the Kubernetes-migration Skill redesign from an evidence-backed pivot.
The user wants one public `/analyze-repo-for-kubernetes` command. Its internals
must be a mechanically validated, composable analysis pipeline; users do not
invoke individual stages.

No implementation has started for this redesign. This document records the
confirmed runtime failure, the design direction, independent reviews, and the
next-session starting point.

## Working context

- Implementation worktree:
  `C:\Users\박병찬\Desktop\analyze-repo-for-k8s-migration-skill-worktrees\pipe-001-state-model`
- Branch: `ticket/pipe-001-state-model`
- Historical VS-028 worktree:
  `C:\Users\박병찬\Desktop\analyze-repo-for-k8s-migration-skill-worktrees\vs-028-history`
- Completed VS-028 implementation commit: `524657e` (`fix: load workload-boundary unconditionally and drop Detailed's one-entry cap`)
- Worktree status when this handoff was written: clean.
- Write PIPE-001 changes only in the dedicated PIPE-001 worktree.

Read first on resume:

1. `docs/development/tickets/VS-028-prose-only-process-discovery.md`
2. `tests/evaluation/vs-028-flask-celery-runs/README.md`
3. This handoff
4. `runtime/agents/kubernetes-migration-analyzer.md`
5. `runtime/tools/read.ts` and `scripts/run_opencode_acceptance.py`

## Confirmed failure and its impact

### Fact: Markdown references are not automatically loaded

`skill()` returns `SKILL.md` content, not its linked reference files. In the
VS-028 Flask/Celery before/after experiment, Summary and Detailed each ran
three times (12 runs total). Every trace recorded only `SKILL.md` as a
supporting Skill read; none recorded `references/workflow.md` or
`references/workload-boundary.md`.

Therefore, adding a reference to an always-read list in `SKILL.md` or an
agent prompt does not mechanically load that file. It is only a model
instruction to make a later read call.

### Fact: the current adapter has a Skill-root path mismatch

The isolated acceptance adapter installs the Skill at
`config/skills/analyze-repo-for-kubernetes`, while `runtime/tools/read.ts`
recognizes `OPENCODE_CONFIG_DIR/skill/analyze-repo-for-kubernetes` as its
trusted configuration-root path. The plural/singular mismatch means that a
direct reference read may be rejected even if the model tries it.

This must be fixed or bypassed by the redesigned orchestrator. Do not treat
the absence of a read attempt as proof that this mismatch did not matter.

### Fact: VS-028 did not demonstrate its intended effect

In all 12 Flask/Celery runs, the Celery worker was not emitted as a separate
candidate. The original theory that making `workload-boundary.md` always read
would solve the failure is therefore disproven as an implementation mechanism,
not as a statement that workload-boundary reasoning is valuable.

JPetStore Summary after-runs were 2/3 complete without an observed splitting
regression. The remaining Summary repeat and Detailed verification were not
completed. At least one after Detailed run failed Markdown validation; the
cause remains uninvestigated.

## User-approved architectural direction

The user approved this direction in principle:

- Keep exactly one public command: `/analyze-repo-for-kubernetes`.
- Split the internal workflow into composable stages with explicit input and
  output interfaces.
- Put stage contracts and validation in code/schema, not only in Markdown
  instructions.
- Keep supporting documents separated for maintainability, but do not depend
  on the model voluntarily loading them.

The initial stage names are:

```text
01 discovery
02 execution
03 relationships
04 boundaries
05 runtime contracts
06 finalize/report rendering
```

The refined design below supersedes the earlier idea of a strictly linear
six-stage prompt workflow.

## Independent high-reasoning design reviews

Two independent `gpt-5.6-sol` reviewers were run read-only at high reasoning
effort. Both returned conditional approval. Their convergent conclusions are
binding design inputs for the next design pass.

### P0: use a trusted session-scoped orchestration tool/plugin

Commands and Skills alone are prompts. A model can skip a stage, omit a tool
call, or reach its step limit and emit arbitrary text. Implement one trusted
`analysis_pipeline` tool/plugin with stage methods rather than six
independent public commands or model-selected reference reads.

Proposed public interaction:

```text
/analyze-repo-for-kubernetes
  -> analysis_pipeline.start(target, mode)
  -> analysis_pipeline.submit(discovery, payload)
  -> analysis_pipeline.submit(execution, payload)
  -> analysis_pipeline.submit(relationships, payload)
  -> analysis_pipeline.submit(boundaries, payload)
  -> analysis_pipeline.submit(contracts, payload)
  -> analysis_pipeline.reopen(stage, reason)       # restricted back-edge
  -> analysis_pipeline.finalize()
```

Only `finalize()` may create the final report payload. A free-form model
Markdown or JSON response is not a successful analysis.

### P0: separate execution form from operational independence

`continuous`, `one-shot`, and `scheduled` describe a process's execution
duration. They do not prove that two processes can be started, stopped,
restarted, scaled, or scheduled independently. The latter is a relationship
used for workload-boundary judgment. Do not represent both ideas with one
`lifecycle` field.

### P0: separate process existence, repository role, and deployability

One enum cannot safely represent an application worker, a repository-defined
Redis dependency, an external SaaS, and a migration command. In particular,
do not collapse these axes:

- process/discovery disposition;
- repository role;
- deployability (`deployable_unit`, runtime dependency, external dependency,
  excluded);
- operational management boundary.

### P0: allow controlled revisiting of earlier stages

Relationship or contract exploration can reveal a new worker or scheduler
entrypoint. A strictly forward-only pipeline would lose it. Use state
revisions and a limited `reopen()` transition back to the earliest affected
stage; reject stale submissions after reopening.

### P0: the orchestrator owns reference loading and final rendering

The orchestrator must load the canonical internal stage instructions from the
installed Skill root and return the current stage's instruction/schema to the
model. The model must not reconstruct an installed absolute path or be asked
to optionally read a Markdown reference.

The final renderer must also be part of the interactive runtime path. The
current prompt says an external finalizer renders JSON, but the renderer is
currently wired in the acceptance harness rather than guaranteed in the
interactive runtime. This is a plausible contributor to the known Detailed
Markdown validation failure and must be verified before claiming causation.

### P1: use a distinct internal state schema

Do not reuse `schemas/analysis-result.schema.json` as the pipeline schema.
It is a permissive report schema and does not prove stage order, signal
coverage, ID integrity, or runtime-contract coverage.

All stage envelopes should be closed schemas (`additionalProperties: false`)
and contain at least:

```text
session_id
target_realpath
target_revision
skill_manifest_hash
current_stage
input_state_revision
output_state_revision
state_hash
evidence_registry
stage_outputs
```

Use a common typed claim representation for evidence-bearing values. It must
distinguish confirmed, inferred, unknown, conflicted, and not-applicable
states; an `unknown` claim requires scoped absence evidence and the blocked
decision.

## Proposed internal interfaces to refine next

```text
DiscoveryInventory
  signals[]
    id, type, evidence_ids

SignalDisposition
  Every signal is resolved as supports_process, dependency_only, duplicate,
  non_runtime, or unresolved, with evidence.

ProcessInventory
  processes[]
    process_id, origin_signal_ids, start_command, entrypoint,
    execution_context, duration, artifact_or_image, command_aliases,
    direct_runtime_dependencies, evidence

RuntimeGraph
  edges[]
    source_id, target_id, mechanism, timing, evidence_ids

BoundaryResult
  operational_units[]
    unit_id, member_process_ids, unit_kind, deployability,
    repository_role, management_boundary, evidence
  process_dispositions[]
  unresolved_boundaries[]

RuntimeContracts
  One contract per deployable unit: image, command, args, port, env,
  config, secret, health, storage, resource claims.
```

Required invariants:

- Every discovery signal has a disposition.
- Every process has a disposition and boundary coverage; uncertainty is
  preserved rather than silently merged into another process.
- Graph endpoints reference existing process/dependency IDs.
- A deployable unit has exactly one runtime contract, and a runtime contract
  cannot reference a non-deployable unit.
- No dangling IDs, duplicate unit membership, stale state revision, or
  cross-session/target/revision state reuse.
- `finalize()` is a pure projection: it may not discover new evidence.

## Security and safety requirements

The orchestrator is a new security boundary because custom tool code can read
and write independently of the agent's normal `edit` permission. It must:

- keep all state outside the analyzed repository;
- bind state to session, resolved target realpath, immutable revision, Skill
  manifest hash, and state hash;
- prevent symlink escape and cross-session state reuse;
- persist redacted evidence only, never secret literals;
- reject stage skipping, duplicate/stale submission, and premature finalization;
- clean up state when the session ends;
- leave the target repository unchanged.

## Required tests before implementation can be declared complete

### Deterministic

1. Stage order, duplicate submit, stale revision, cross-session/target/revision
   reuse, and premature finalization are rejected.
2. Validation failure leaves the state unchanged and permits resubmission only
   to the same stage.
3. Every discovery signal/process/unit is covered; dangling IDs, duplicate
   membership, and missing contracts fail validation.
4. Unknown is allowed only with evidence scope and blocked decision.
5. Reference root handling covers the singular/plural Skill path mismatch.
6. Symlink escape, evidence-ID forgery, and secret-literal state storage fail.
7. Final Markdown is deterministic for the same finalized state.
8. The analyzed target's Git status/tree remains unchanged.

### Acceptance and interactive E2E

1. Flask/Celery, Summary and Detailed, three repetitions each: web and worker
   are distinct units even when they share a source file/image; no worker port
   is required for the worker to remain a candidate.
2. JPetStore, Summary and Detailed: the web workload remains one unit and the
   embedded database is not split into a workload.
3. Command aliases across Dockerfile/Compose/README merge into one process.
4. Separate role arguments with independent operations split correctly.
5. Missing command or operational-independence evidence yields an unresolved
   boundary, not an invented merge or split.
6. Trace records stage submissions, injected stage instruction identity, state
   revisions, and finalization in order.
7. Provider interruption or step limit is not accepted as a complete report.
8. Detached `tmux` interactive run yields the required final Markdown and
   identical target Git status before/after.

## Recommended next-session sequence

1. Treat VS-028 as an evidence-producing partial implementation. Do not claim
   its always-load mechanism works.
2. Decide whether this redesign receives a new ticket/ADR or formally
   supersedes VS-028. The scope is materially larger than VS-028 and should
   not be appended to that ticket without an explicit decision.
3. Write and approve the detailed design before code changes:
   - pipeline state schema and IDs;
   - legal state transitions and `reopen()` policy;
   - internal stage-document loading API;
   - finalizer integration point;
   - security lifecycle and cleanup;
   - renderer/report projection boundary.
4. Split implementation into focused tickets. Suggested dependency order:
   - `PIPE-001`: stage state model and pure validator;
   - `PIPE-002`: trusted session-scoped `analysis_pipeline` tool/plugin and
     state lifecycle;
   - `PIPE-003`: stage contracts/instruction injection and agent migration;
   - `PIPE-004`: runtime finalizer plus deterministic renderer integration;
   - `PIPE-005`: deterministic and provider-backed acceptance coverage.
5. Run deterministic tests first. Run the provider-backed interactive E2E only
   with the required network escalation and the repository's `tmux` procedure.

## Do not do on resume

- Do not try another prose-only wording change to force reference reads.
- Do not make `workflow.md` or `workload-boundary.md` the only owner of a
  required runtime decision.
- Do not expose individual internal stages as user-facing commands.
- Do not place state or generated reports in the analyzed target repository.
- Do not regard a report-shaped model response as valid without successful
  pipeline finalization.
- Do not re-run provider tests until the pipeline contract and expected trace
  assertions are defined.
