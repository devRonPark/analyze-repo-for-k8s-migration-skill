# Bounded Stage Surveys Design

## Problem

The static MCP workflow keeps each analysis stage isolated, but its generic
evidence tools leave the evidence-search budget entirely to the model.  A
Windows OpenCode acceptance run against the pinned JPetStore target issued 91
successful `locate_evidence` calls in Discovery and never submitted that
stage.  Increasing the agent step limit does not make this bounded, reliable,
or compatible with the five-minute acceptance objective.

## Goal

Keep the seven-Skill, accepted-handoff workflow while making every analysis
stage reach a submit decision from a bounded server-produced evidence set.

## Non-goals

- Do not execute target code, builds, containers, or migrations.
- Do not merge stages, reveal a future stage to the current Skill, or make the
  server write a final report without the Finalize Skill.
- Do not add a JavaScript or TypeScript runtime.
- Do not infer unobserved target facts or return unredacted target content.

## Architecture

The static catalog gains five current-stage-only read-only tools:

| Current stage | Tool | Server-selected evidence categories |
| --- | --- | --- |
| Discovery | `survey_discovery_evidence` | build/package manifests, container and orchestration declarations, startup descriptors, runtime configuration |
| Execution | `survey_execution_evidence` | build commands, image definitions, entrypoints, listening ports, runtime launch configuration |
| Relationships | `survey_relationship_evidence` | declared dependencies, connection settings, brokers, queues, caches, identity and external service configuration |
| Boundaries | `survey_boundaries_evidence` | independent start definitions, worker or schedule declarations, lifecycle signals, persistent writable locations |
| Contracts | `survey_contract_evidence` | configuration timing, credentials markers, health or readiness signals, observability configuration and report-slot gaps |

Each survey accepts no model-selected target path.  The active
`AnalysisSession` supplies the target root, current stage, mode, and accepted
predecessor facts.  The server walks a fixed high-signal path and pattern
allowlist in stable order, reads only bounded redacted lines, and issues at
most twelve current-stage observation references.  A missing category produces
a scoped absence observation rather than a tool error.  The response contains
only the stage, a `surveyed` status, bounded category coverage, and redacted
observations with their `observation_ref`, status, and safe `path:line`
reference.

The generic evidence tools remain available only as a single optional
precision check after that stage's survey.  The session records a survey flag
and a combined `read_evidence` / `locate_evidence` / `list_target_paths` /
`get_target_git_metadata` precision count for each stage.  Before a survey,
those tools return the
retryable `survey_required` result.  After one precision check, another call
returns the retryable `precision_budget_exhausted` result.  These responses
name the current Stage tool but never name a future stage.  Git metadata is
included in the relevant survey response, so it needs no separate stage call.

## Skill Flow

Each non-final Stage Skill uses the same short, current-only sequence:

1. **Survey:** call its own `survey_*_evidence` tool once and retain only its
   returned observation references.
2. **Precision:** make at most one generic evidence call only if one current
   decision remains blocked by the survey response.
3. **Checkpoint:** construct the transparent `submit_*` payload and submit it.
   An accepted response is the only completion; no user-facing report is
   drafted first.

`*_fact_refs` from the incoming handoff remain accepted facts, not observation
references.  Every `payload.evidence[].observation_ref` is issued in the
current stage by its survey or precision call.

The Finalize Skill remains unchanged: it only calls `finalize_analysis` and
relays canonical Markdown.

## Public Contract and Safety

- The MCP catalog exposes every survey as a separate named tool with a
  leading verb and a description that states when it should be called.
- Survey response schemas are transparent and bounded.  Submit schemas remain
  fully transparent, including nested relationship, boundary, and report-slot
  structures.
- The server computes observations, target binding, revisions, tokens, and
  handoffs.  The model never supplies raw evidence, paths outside the target,
  or server-owned evidence identifiers.
- Existing safe-path, reparse-point, redaction, snapshot, and process-private
  session rules apply to survey collection unchanged.
- A survey cannot be called out of stage order, repeated in a stage, or used
  after finalization.

## Verification

Deterministic tests must prove:

1. all five survey tools are present in the static catalog with read-only
   annotations and transparent output schemas;
2. every survey rejects the wrong current stage and a repeat without changing
   session state;
3. every survey returns no more than twelve current-stage, redacted
   observations and represents absent categories safely;
4. generic evidence tools reject pre-survey calls and a second precision call;
5. survey observations can be submitted by their matching stage but cannot be
   reused by another stage;
6. sealed bundles, installed tool policies, Skill references, and the
   Python-only artifact scan include the new tool names and no unrelated
   runtime files.

Windows-native OpenCode acceptance keeps the pinned JPetStore, Flask-Celery,
and FastAPI targets read-only.  Each Summary and Detailed case must produce
the canonical Markdown report, complete every required submit transition and
finalization exactly once, and leave Git status unchanged.  A provider-backed
case has a five-minute limit; its trace must include at most five survey calls
and at most five generic precision calls.  A timeout, incomplete final report,
invalid transition, or target change fails the case.

## Delivery Boundary

This is a focused continuation of the static MCP milestone.  It supersedes
the unbounded generic-evidence loop but preserves the seven installed Skill
IDs, user-invoked custom command, Python 3.13 runtime, Windows-native E2E
path, sealed bundle verification, and one-process-per-analysis session model.
