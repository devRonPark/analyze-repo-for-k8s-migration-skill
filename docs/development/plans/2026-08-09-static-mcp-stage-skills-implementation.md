# Static MCP Stage Skills Implementation Plan

> **Execution:** Use superpowers:executing-plans and complete the tickets in
> order. Each ticket is one independently reviewable **Vertical Slice** and ends
> with its own focused commit. Do not start a later ticket until the predecessor
> verification passes.

**Goal:** Deliver the approved Python-only, static-MCP repository analysis
workflow as seven installed OpenCode Skills. The dispatcher loads a current
stage Skill only after the Python server accepts its predecessor. The target
repository may be an absolute local Git path or a path relative to the trusted
command directory.

**Architecture:** A process-private Python MCP server exposes a fixed 12-tool
catalog. It owns target binding, snapshots, observations, accepted facts,
transition state, redaction, and final report rendering. The Skill package
contains a user-invoked dispatcher and six model-invoked stage Skills. Skills
provide small current-step procedures and references; the server validates
progress and returns the exact next-Skill handoff. The final stage relays the
server-generated Markdown unchanged.

**Non-goals:** Dynamic tool catalog refresh, TypeScript/JavaScript/Node/Bun
runtime code, a Python-owned model loop, persistent session/audit/receipt
systems, target-repository writes, and model-backed Claude/Gemini E2E.

**Technology:** Python 3.13 and the existing deliberately stdlib-only JSON-RPC
MCP boundary. No MCP SDK, wheelhouse, or network dependency is introduced.
Use the existing report renderer/contracts, Python unittest, and detached tmux
only for the authorized OpenCode interactive E2E.

## Global implementation contracts

### Source and installed bundle topology

The source-of-truth dispatcher remains the repository-root SKILL.md. It is not
copied to another source location. Stage Skill source files live under
runtime/stage-skills/<skill-id>/; their immediate references live below the
same directory. Build output has exactly this layout:

~~~
bundle/
  bundle-manifest.json
  skills/
    analyze-repo-for-kubernetes/SKILL.md
    analyze-k8s-discovery/SKILL.md
    analyze-k8s-execution/SKILL.md
    analyze-k8s-relationships/SKILL.md
    analyze-k8s-boundaries/SKILL.md
    analyze-k8s-contracts/SKILL.md
    analyze-k8s-finalize/SKILL.md
  runtime/
  commands/
  agents/
~~~

The builder copies the root dispatcher to the first installed sibling, copies
each stage Skill to its sibling, and copies only allowlisted runtime assets.
bundle-manifest.json names every installed file, SHA-256, Skill ID, allowed MCP
tools, allowed installed-reference paths, and source revision. There is one
source dispatcher and one installed dispatcher; no divergent duplicate source
text exists.

The installed Skill IDs are fixed:

~~~
analyze-repo-for-kubernetes
analyze-k8s-discovery
analyze-k8s-execution
analyze-k8s-relationships
analyze-k8s-boundaries
analyze-k8s-contracts
analyze-k8s-finalize
~~~

The installer atomically installs all seven as sibling directories under an
OpenCode Skill discovery root. It never installs a nested Skill and rolls all
members back on a partial failure. The agent, command, OpenCode configuration,
and acceptance adapter whitelist exactly this inventory. OpenCode has one
static primary-agent permission set, so external_directory statically allows
the seven installed Skill roots. This is not filesystem isolation: progressive
disclosure is proved by Skill/reference load ordering, while stage validation
remains server-owned.

For an OpenCode configuration root ${OPENCODE_CONFIG_DIR}, the complete
installed topology is fixed:

~~~
${OPENCODE_CONFIG_DIR}/
  skills/<the seven Skill IDs>/SKILL.md
  agent/kubernetes-migration-analyzer.md
  command/analyze-repo-for-kubernetes.md
  analyze-repo-for-kubernetes/
    runtime/python/launch_mcp.py
    runtime/python/analysis_pipeline/
    contracts/mcp-static-catalog.json
    contracts/stage-payload-contracts.json
    assets/migration-summary-template.md
    assets/migration-assessment-template.md
    opencode-mcp.json
~~~

opencode-mcp.json is an installer-generated fragment whose command is the
absolute installed runtime/python/launch_mcp.py path. It contains no cwd.
At MCP process startup the launcher captures Path.cwd() once and constructs
Server(command_directory=Path.cwd()); that inherited OpenCode session cwd is
the trusted base for relative target_path. The installer never overwrites a
user's opencode.json; it emits the fragment for explicit merge. The isolated
E2E adapter owns composing the fragment into its temporary opencode.json. One
install transaction stages and either replaces or restores all seven Skill
directories, the runtime root, agent, command, and fragment. It has no partial
success state.

The following current rule assets have fixed planned owners. Ticket 1 records
the same mapping as evidence, and any change requires amending this plan before
implementation:

| Current asset | Canonical installed owner |
| --- | --- |
| references/workflow.md | discovery/references/workflow.md |
| references/language-discovery-rules.md | discovery/references/language-discovery-rules.md |
| references/dependency-analysis.md | relationships/references/dependency-analysis.md |
| references/workload-boundary.md | boundaries/references/workload-boundary.md |
| references/configuration-timing.md | contracts/references/configuration-timing.md |
| references/evidence-and-readiness.md | contracts/references/evidence-and-readiness.md |
| references/repository-analysis-checklist.md | contracts/references/repository-analysis-checklist.md |
| assets/migration-summary-template.md | installed runtime assets/migration-summary-template.md |
| assets/migration-assessment-template.md | installed runtime assets/migration-assessment-template.md |

### Fixed MCP wire catalog

contracts/mcp-static-catalog.json is the canonical, versioned wire artifact.
It contains every tool's final transport input schema, output schema,
annotations, bounded text fallback requirements, and error shape. The server's
initial and all later tools/list results must byte-match its tools list.

The 12 permanent tools and their public inputs are:

| Tool | Required public input |
| --- | --- |
| start_analysis | {target_path, mode} |
| read_evidence | {path} plus bounded offset, limit |
| list_target_paths | {pattern} plus optional relative path |
| locate_evidence | {glob} plus optional relative path, pattern |
| get_target_git_metadata | {} |
| submit_discovery | {analysis_id, revision, transition_token, payload} |
| submit_execution | {analysis_id, revision, transition_token, payload} |
| submit_relationships | {analysis_id, revision, transition_token, payload} |
| submit_boundaries | {analysis_id, revision, transition_token, payload} |
| submit_contracts | {analysis_id, revision, transition_token, payload} |
| reopen_analysis | {analysis_id, revision, transition_token, stage, reason} |
| finalize_analysis | {analysis_id, revision, transition_token} |

target_path accepts an absolute local path or a path relative to the trusted
command directory. mode is the closed enum summary | detailed. The dispatcher
supplies "." only when the user selected the command directory. The server
derives the command directory from the launcher process working directory and
receives it explicitly as Server(command_directory=...). It never derives it
from repository content, an MCP argument, or an environment value supplied by
the model.

The wire does not expose expected_hash or state_hash. Any state digest needed
for internal invariants stays private. Every submit tool exposes the same small
closed transport envelope: analysis_id, revision, transition_token, and a
payload object. The catalog deliberately does not expose future stage payload
fields. contracts/stage-payload-contracts.json is the sole schema source of
truth. analysis_pipeline.stage_contracts only loads, selects, and validates
that JSON; it contains no duplicated schema literals. The builder projects the
current fragment to the installed Skill path
skills/<skill-id>/references/payload-contract.json. A stage Skill loads that
generated file, while the server loads the installed runtime/contracts source.
Structural-equality tests compare each projection with its source fragment.
The server applies the fragment after envelope validation. A model cannot
submit arbitrary fact/evidence IDs.

Every success result has content and matching structuredContent; normal tool
results use a bounded text fallback. Business, validation, and state failures
return CallToolResult.isError: true with the stable closed shape
{code, retryable, issues} and no successor. Malformed JSON-RPC and unknown
methods remain protocol errors. Evidence-tool annotations are
readOnlyHint: true, destructiveHint: false, and openWorldHint: false.

Successful start and submit tools return this closed handoff:

~~~
{
  "status": "accepted",
  "analysis_id": "an_server_issued",
  "mode": "summary | detailed",
  "completed_stage": "null | discovery | execution | relationships | boundaries | contracts",
  "revision": 1,
  "transition_token": "tr_server_issued",
  "next_skill": "analyze-k8s-discovery | ... | analyze-k8s-finalize",
  "stage_input": { "only the allowlisted input fields of next_skill": true }
}
~~~

start_analysis returns completed_stage: null. stage_input is separately
schema-validated for each edge. It may contain only IDs/references from
accepted predecessors and needed scoped unknowns; it cannot contain target
paths, raw evidence, secret values, full state, an observation from another
stage, a future reference path, or procedure text. The finalizer returns
canonical Markdown in content, and only status, analysis ID, mode, and
revision in structuredContent.

The successor fact-ref field is exact and monotonic: discovery accepts no
predecessor fact refs; execution accepts discovery_fact_refs; relationships
accepts discovery_fact_refs and execution_fact_refs; boundaries additionally
accepts relationship_fact_refs; contracts additionally accepts
boundaries_fact_refs. The server compares each field with the preceding
handoff allowlist and rejects additions, substitutions, duplicates, or a
wrong-stage fact ref.

reopen_analysis has its own success schema. It returns status: reopened,
analysis_id, mode, reopened_stage, revision, transition_token, next_skill for
that stage, and that stage's redacted stage_input. It never returns a
completed-stage handoff or a future-stage identifier.

### State, fact, and report ownership

One server process supports one active analysis:

~~~
IDLE -> discovery -> execution -> relationships -> boundaries -> contracts
     -> READY_TO_FINALIZE -> IDLE
~~~

A state-changing call first checks analysis ID, snapshot, revision, transition
token, and exact stage. It then validates and normalizes the payload, promotes
accepted observations into immutable facts, writes state and fact registry as
one transaction, consumes the old token, issues a new token, and emits a
redacted handoff. Any failed validation rolls back all of those effects. A
repeated state-changing request is stale_transition; the server has no replay
ledger, receipt replay, resume, or retry protocol.

reopen_analysis permits only documented back-edges, invalidates its target and
later facts/observations, returns that target's current input, and never names
a future stage. Finalization keeps mode server-owned: an internal
AnalysisSession.finalize_and_render() verifies snapshot and state, invokes pure
project_and_render(state, mode), clears only after a successful response is
constructed, and leaves state intact on a render failure. A second finalizer
call fails; a second start succeeds after cleanup.

Report data uses closed dataclasses/JSON schemas, not free-form model report
text. Ownership is fixed: discovery owns candidate/exclusion facts; execution
owns build/runtime/start/image/port facts; relationships owns dependencies and
external services; boundaries owns deployable-unit and state/lifecycle
decisions; contracts owns configuration, credential exposure, missing inputs,
and final verdict slots. project_and_render maps these evidence-linked fields
to the existing mode-specific JSON and Markdown contracts. In-memory
validate_markdown(text, mode, target_metadata) and
finalize_markdown(text, mode, target_metadata) replace target-file and
subprocess finalization paths. The target directory is never used for a report
file.

### Skill procedure and progressive disclosure

The dispatcher is user-triggered. It owns only help/unrelated routing,
Korean/read-only policy, target/mode forwarding, start_analysis, loading
exactly handoff.next_skill, and unchanged final Markdown relay. It has no
stage procedure, report template, or full reference list.

Each stage Skill is model-triggered and contains only: its immediate goal,
incoming stage_input fields, current allowed MCP tools, named current
references, a leading-word procedure, and completion call. Descriptions and
procedure gates use Start, Read, List, Locate, Get, Submit, Reopen, Finalize,
plus Vertical Slice, Grounding, Workload Boundary, Gap Analysis, and Quality
Gate. A stage cannot choose a successor: predecessor acceptance supplies it.
Failure repairs only the current input. If the named Skill is unavailable it
stops.

This is progressive procedural disclosure, not secrecy. Tests validate declared
IDs and event ordering, never brittle exact prose: a future body/reference
canary must not load before predecessor acceptance; a current reference can
load only after its Skill; failed submission loads no successor; missing
successor stops; and reopen exposes only valid prior work.

## Ticket 1 — Reconcile normative documents and freeze rule ownership

**Files:** ADR-2026-08-08-004 through ADR-2026-08-08-009 under
docs/development/daily/2026-08-08, docs/development/tickets/PIPE-001 through
PIPE-006, docs/superpowers/specs/2026-08-08-python-mcp-analysis-pipeline-design.md,
the superseded Python-runner plan if present,
docs/development/specifications/static-stage-rule-ownership-2026-08-09.md,
and tests/test_development_contracts.py.

1. Amend the accepted ADR/tickets before code: replace TypeScript/OpenCode
   session and dynamic-catalog requirements with this Python static-MCP
   contract, process-instance state, target path binding, and no dynamic
   catalog. Mark the prior Python-owned runner plan superseded rather than
   deleting historical evidence.
2. Create the ownership matrix with exactly these columns: existing
   rule/reference or template, canonical new owner, validator owner, Skill
   stage, Summary/Detailed condition, report fields, characterization/golden
   test. Include workflow.md, workload-boundary.md, evidence-and-readiness.md,
   language-discovery-rules.md, configuration-timing.md,
   dependency-analysis.md, repository-analysis-checklist.md, both templates,
   and report contracts.
3. Record the fixed owner paths in the global mapping above exactly. If evidence
   requires a different owner, stop and amend this plan before implementation.
   Give every rule exactly one canonical retained/moved asset; do not make
   competing copies. Existing prose is removed only in its owning stage ticket
   after its characterization proof exists.
4. Add positive contract tests that the revised normative documents agree on
   static catalog, seven-Skill topology, process-private state, and Python-only
   runtime. Do not use a forbidden-word scan that rejects explanatory history.

**Verification:** python -m unittest tests.test_development_contracts

**Commit:** docs: reconcile static MCP stage-skill contracts

## Ticket 2 — Freeze the whole wire catalog and safe start vertical slice

**Files:** contracts/mcp-static-catalog.json,
contracts/stage-payload-contracts.json,
runtime/python/analysis_pipeline/protocol.py,
runtime/python/analysis_pipeline/mcp_server.py,
runtime/python/analysis_pipeline/state.py,
runtime/python/analysis_pipeline/observations.py,
runtime/python/analysis_pipeline/validation.py,
runtime/python/analysis_pipeline/transitions.py,
runtime/python/analysis_pipeline/session.py,
runtime/python/analysis_pipeline/stage_contracts.py,
runtime/python/analysis_pipeline/handoffs.py,
runtime/python/launch_mcp.py,
runtime/python/tests/test_mcp_server.py,
runtime/python/tests/test_pipeline_state.py,
runtime/python/tests/test_observations.py,
runtime/python/tests/test_tools.py, and scripts/mcp_smoke.py.

1. Introduce transport-neutral AnalysisSession. Move target binding, snapshot
   checks, observation/fact registry, transition token, stale-token rejection,
   and cleanup out of the JSON-RPC handler. Delete the replay ledger and all
   receipt-replay behavior. The handler is only stdio/protocol dispatch.
2. Implement the complete, final catalog artifact and serve all 12 transport
   schemas from it from the first tools/list. Keep submit payload transport
   opaque and locate the five closed stage contracts in stage_contracts.py.
   Add final success/error output schemas, including start-null and reopen
   handoffs, plus text fallbacks now; later tickets may implement semantics but
   may not change catalog bytes.
3. Implement start_analysis(target_path, mode) and its complete discovery
   handoff. Resolve relative paths against command_directory, bind both
   selected subdirectory and Git root/revision/snapshot, and reject a
   non-directory, non-Git path, Skill install path, unsafe root, link/reparse
   point, or path escaping the selected repository.
4. Preserve response stdout purity, protocol-version negotiation, and
   notifications/initialized; advertise no list-change capability and emit no
   list-change notification. Implement isError business results.
5. Use temporary external Git repositories to test absolute, relative,
   selected subdirectory, default ".", spaces, non-ASCII names, file,
   non-Git directory, install-root alias, link/junction escape, content
   mutation, and target-content injection. Start the same launcher from two
   distinct command directories and prove that "." and a relative target path
   resolve from that process-start cwd. Test failed start leaves IDLE.
6. Add byte-for-byte static-catalog regression, outputSchema,
   structuredContent/text fallback checks, annotation checks, malformed
   JSON-RPC protocol errors, repeated-call stale_transition rejection, and
   direct stdio initialize/list/start smoke.

**Verification:** python -m unittest runtime.python.tests.test_mcp_server runtime.python.tests.test_pipeline_state runtime.python.tests.test_observations runtime.python.tests.test_tools; python scripts/mcp_smoke.py --static-catalog

**Commit:** feat: add static MCP start and target binding

## Ticket 3 — Deliver seven-Skill bundle and dispatcher vertical slice

**Files:** SKILL.md,
runtime/stage-skills/analyze-k8s-discovery/SKILL.md,
runtime/stage-skills/analyze-k8s-execution/SKILL.md,
runtime/stage-skills/analyze-k8s-relationships/SKILL.md,
runtime/stage-skills/analyze-k8s-boundaries/SKILL.md,
runtime/stage-skills/analyze-k8s-contracts/SKILL.md,
runtime/stage-skills/analyze-k8s-finalize/SKILL.md,
contracts/skill-bundle-manifest.schema.json, runtime-files.txt,
scripts/build_dist.py, scripts/validate_skill.py,
scripts/install_distribution.py, scripts/install-opencode.sh,
scripts/install-codex.sh, scripts/install-qwen.sh,
scripts/run_opencode_acceptance.py, runtime/opencode.json,
runtime/agents/kubernetes-migration-analyzer.md,
runtime/commands/analyze-repo-for-kubernetes.md,
tests/test_package.py, tests/test_skill_validator.py,
tests/test_repository_distribution.py, tests/test_opencode_adapter.py,
tests/test_skill_bundle.py, and tests/test_bundle_installer.py.

1. Implement the declared source/bundle topology and bundle manifest. The
   builder reads the Ticket 2 schema SSOT and projects exactly one matching
   payload-contract.json into each staged Skill. Convert validators from one
   nested SKILL.md assumption to exact seven sibling installed Skills while
   retaining frontmatter, link, UTF-8, manifest, projection equality, and
   no-placeholder validation.
2. Rewrite only the root dispatcher into the minimal user-triggered router:
   help, target/mode argument parsing, one start call, handoff-directed Skill
   load, and canonical Markdown relay. It must call no evidence or submit tool.
3. Add six skeletal, model-triggered stage Skills whose only live behavior is
   receiving declared handoff input and stopping until their respective later
   vertical slices supply a completion contract. They are not full procedures.
4. Implement install_bundle(source_bundle, config_root) and
   render_opencode_mcp_fragment(runtime_root). The generated fragment contains
   only the installed absolute launcher command; launch_mcp.py captures the
   caller cwd. Install and discover the exact topology above: seven siblings,
   runtime, agent, singular command, and generated fragment in one rollback
   unit. Grant exact Skill permissions and one static external_directory
   allowlist for all seven roots, and reject missing/orphan/extra members. Do
   not claim runtime per-Skill filesystem permissions.
5. Extend copy_bundle(), discovery_audit_bundle(), and isolated_config_bundle()
   in the acceptance adapter. Test successful install and every injected
   partial failure restores the old skills, runtime, agent, command, and
   fragment. Add progressive-disclosure event tests: dispatcher start ->
   discovery load; no future canary read before accepted handoff; missing
   declared Skill stops; installed inventory and permissions match the manifest
   exactly. No test locks prose wording.

**Verification:** python -m unittest tests.test_package tests.test_skill_validator tests.test_repository_distribution tests.test_opencode_adapter tests.test_skill_bundle tests.test_bundle_installer; python scripts/build_dist.py --output .artifacts/plan-test-bundle

**Commit:** feat: package dispatcher and stage-skill bundle

## Ticket 4 — Discovery observation-to-handoff vertical slice

**Files:** runtime/stage-skills/analyze-k8s-discovery/SKILL.md and
runtime/stage-skills/analyze-k8s-discovery/references/workflow.md,
runtime/stage-skills/analyze-k8s-discovery/references/language-discovery-rules.md,
references/workflow.md, references/language-discovery-rules.md,
contracts/stage-payload-contracts.json,
runtime/python/analysis_pipeline/stage_contracts.py,
runtime/python/analysis_pipeline/handoffs.py,
runtime/python/analysis_pipeline/session.py,
runtime/python/tests/test_discovery_stage.py, and
tests/test_discovery_skill.py.

1. Give discovery its minimal Vertical Slice/Grounding procedure, only
   read_evidence, list_target_paths, locate_evidence, get_target_git_metadata,
   submit_discovery, and permitted reopen tools. It loads only its
   matrix-owned rules after the discovery Skill loads.
2. Implement validate_discovery_payload(payload, observations),
   promote_discovery_facts(state, registry, payload), and
   project_discovery_handoff(state). The transaction yields only candidate IDs,
   discovery_fact_refs, and scoped unknown IDs for execution.
3. Port the discovery-owned current behavior through the matrix and add
   characterization cases for candidate/exclusion findings in both modes.
   Remove old duplicate discovery prose only after these pass.
4. Test actual server tool calls: forged/cross-stage/stale observations,
   invalid payload rollback, token/revision rotation, redaction, no raw
   evidence in handoff, and event sequence discovery load/reference read ->
   accepted submit -> execution load.

**Verification:** python -m unittest runtime.python.tests.test_discovery_stage tests.test_discovery_skill runtime.python.tests.test_mcp_server

**Commit:** feat: complete discovery stage handoff

## Ticket 5 — Execution vertical slice

**Files:** runtime/stage-skills/analyze-k8s-execution/SKILL.md,
runtime/stage-skills/analyze-k8s-execution/references/execution-rules.md,
contracts/stage-payload-contracts.json,
runtime/python/analysis_pipeline/stage_contracts.py,
runtime/python/analysis_pipeline/handoffs.py,
runtime/python/analysis_pipeline/session.py,
runtime/python/tests/test_execution_stage.py, and tests/test_execution_skill.py.

1. Define the current-only execution Skill and payload that consumes discovery
   IDs, observes build/runtime/start/image/port evidence, and uses the
   Grounding/Quality Gate completion call submit_execution.
2. Implement validate_execution_payload(payload, observations,
   discovery_fact_refs), promote_execution_facts(state, registry, payload),
   and project_execution_handoff(state). The payload consumes only
   discovery_fact_refs and the handoff emits process IDs, execution_fact_refs,
   and scoped unknown IDs.
3. Migrate the matrix-owned language/discovery and runtime/build rules without
   duplicates; retain Summary/Detailed conditional loading and existing
   high-signal Summary boundary.
4. Test wrong-stage/foreign fact rejection, successful execution-to-
   relationships projection, mode-specific characterization, and no future
   reference load before acceptance.

**Verification:** python -m unittest runtime.python.tests.test_execution_stage tests.test_execution_skill runtime.python.tests.test_mcp_server tests.test_repository_distribution

**Commit:** feat: complete execution stage handoff

## Ticket 6 — Relationships vertical slice

**Files:** runtime/stage-skills/analyze-k8s-relationships/SKILL.md,
runtime/stage-skills/analyze-k8s-relationships/references/dependency-analysis.md,
references/dependency-analysis.md, contracts/stage-payload-contracts.json,
runtime/python/analysis_pipeline/stage_contracts.py,
runtime/python/analysis_pipeline/handoffs.py,
runtime/python/analysis_pipeline/session.py,
runtime/python/tests/test_relationships_stage.py, and
tests/test_relationships_skill.py.

1. Implement the current-only relationships Skill. It derives dependency edges,
   external runtime dependencies, and scoped unknowns solely from trusted
   current evidence and incoming fact refs.
2. Implement validate_relationships_payload(payload, observations,
   discovery_fact_refs, execution_fact_refs), promote_relationship_facts(state,
   registry, payload), and project_relationships_handoff(state). The handoff
   emits only graph-edge IDs, relationship_fact_refs, and scoped unknown IDs.
   Do not expose raw dependency files or future rules.
3. Migrate the matrix-owned dependency-analysis behavior with both Summary and
   Detailed characterization coverage.
4. Test dangling IDs, cycle/conflict/absence evidence, foreign observations,
   redaction, projection allowlist, failure immutability, and accepted
   relationships -> boundaries load ordering.

**Verification:** python -m unittest runtime.python.tests.test_relationships_stage tests.test_relationships_skill runtime.python.tests.test_mcp_server tests.test_skill_validator

**Commit:** feat: complete relationships stage handoff

## Ticket 7 — Workload-boundaries vertical slice

**Files:** runtime/stage-skills/analyze-k8s-boundaries/SKILL.md,
runtime/stage-skills/analyze-k8s-boundaries/references/workload-boundary.md,
references/workload-boundary.md, contracts/stage-payload-contracts.json,
runtime/python/analysis_pipeline/stage_contracts.py,
runtime/python/analysis_pipeline/handoffs.py,
runtime/python/analysis_pipeline/session.py,
runtime/python/tests/test_boundaries_stage.py, and tests/test_boundaries_skill.py.

1. Implement the current-only Workload Boundary Skill. It consumes accepted
   candidates/processes/edges and establishes independent execution/lifecycle
   units, deployment candidates, exclusions, and state decisions.
2. Implement validate_boundaries_payload(payload, observations,
   discovery_fact_refs, execution_fact_refs, relationship_fact_refs),
   promote_boundary_facts(state, registry, payload), and
   project_boundaries_handoff(state). The handoff emits only exact
   unit/deployable IDs, boundaries_fact_refs, and scoped unknown IDs.
3. Migrate workload-boundary/checklist rules assigned by the matrix and retain
   the two-condition boundary rule; do not split units by directory or port.
4. Test duplicate/dangling units, deployable-subset invariant, reopen from
   contracts/boundaries, later fact invalidation, no future-body/reference
   loading, and Summary/Detailed boundary characterizations.

**Verification:** python -m unittest runtime.python.tests.test_boundaries_stage tests.test_boundaries_skill runtime.python.tests.test_mcp_server tests.test_repository_distribution

**Commit:** feat: complete workload-boundaries stage handoff

## Ticket 8 — Contracts and report-slot closure vertical slice

**Files:** runtime/stage-skills/analyze-k8s-contracts/SKILL.md,
runtime/stage-skills/analyze-k8s-contracts/references/configuration-timing.md,
runtime/stage-skills/analyze-k8s-contracts/references/evidence-and-readiness.md,
runtime/stage-skills/analyze-k8s-contracts/references/repository-analysis-checklist.md,
references/configuration-timing.md, references/evidence-and-readiness.md,
references/repository-analysis-checklist.md,
assets/migration-summary-template.md, assets/migration-assessment-template.md,
runtime/report-assets/migration-summary-template.md,
runtime/report-assets/migration-assessment-template.md,
contracts/stage-payload-contracts.json,
contracts/accepted-report-state.schema.json,
runtime/python/analysis_pipeline/stage_contracts.py,
runtime/python/analysis_pipeline/handoffs.py,
runtime/python/analysis_pipeline/session.py,
runtime/python/tests/test_contracts_stage.py, and tests/test_contracts_skill.py.

1. Implement the current-only Gap Analysis/Quality Gate Skill. It closes every
   report-required slot with an accepted fact/evidence reference or a scoped
   unknown; it cannot create recommendation values.
2. Implement validate_contracts_payload(payload, observations,
   discovery_fact_refs, execution_fact_refs, relationship_fact_refs,
   boundaries_fact_refs), promote_contract_facts(state, registry, payload),
   and project_contracts_handoff(state). The last submit returns
   next_skill: analyze-k8s-finalize and a redacted report-slot projection only;
   no Markdown.
3. Migrate the configuration, evidence/readiness, templates, and detailed
   checklist rules assigned by the matrix. Maintain Summary's narrow contract
   and Detailed's broader conditionally evidenced fields.
4. Test an end-to-end synthetic analysis through all five real submit tools in
   both modes; missing/dangling required report slots fail before finalization.
   Test mode remains server-owned, no model-provided mode can drift, and
   failed contracts submit loads no final Skill.

**Verification:** python -m unittest runtime.python.tests.test_contracts_stage tests.test_contracts_skill runtime.python.tests.test_mcp_server tests.test_repository_distribution

**Commit:** feat: complete report contract stage

## Ticket 9 — Deterministic final report and cleanup vertical slice

**Files:** runtime/stage-skills/analyze-k8s-finalize/SKILL.md,
runtime/python/analysis_pipeline/report_projection.py,
runtime/python/analysis_pipeline/session.py,
scripts/validate_target_report.py, scripts/validate_report.py,
scripts/render_summary.py, scripts/render_detailed.py,
scripts/report_contract.py, scripts/markdown_contract.py,
runtime/python/tests/test_finalization_stage.py, and
tests/test_finalization_skill.py.

1. Extract the pure in-memory Markdown validation/finalization functions,
   preserving existing Summary and Detailed schema/Markdown contracts. Keep
   CLI file validation as a thin adapter; no target write or subprocess is
   permitted during MCP finalization.
2. Implement project_and_render(state, mode), validate_markdown(text, mode,
   target_metadata), finalize_markdown(text, mode, target_metadata), and
   AnalysisSession.finalize_and_render(analysis_id, revision, transition_token).
   It rechecks the snapshot, projects closed evidence-linked state, renders,
   redacts, validates final bytes, constructs the MCP result, then clears
   process-private state.
3. Implement the minimal final Skill: invoke the final tool from handoff and
   relay only canonical Markdown. It may not draft a report or reformat it.
4. Test actual five-stage state in both modes; server Markdown is byte-identical
   to deterministic integration output; final report validates; target Git
   status/files are unchanged; repeated finalization fails; render failure
   preserves active state; success enables a new start; clean installed launcher
   imports the projector.

**Verification:** python -m unittest runtime.python.tests.test_finalization_stage tests.test_finalization_skill tests.test_report_contract tests.test_validate_target_report; python scripts/build_dist.py --output .artifacts/finalizer-test-bundle

**Commit:** feat: finalize deterministic Kubernetes report

## Ticket 10 — Portable installed-bundle stdio smoke

**Files:** runtime/configs/opencode-mcp.json,
runtime/configs/claude-code-mcp.json, runtime/configs/gemini-cli-mcp.json,
runtime/opencode.json, runtime/python/launch_mcp.py,
runtime/python/requirements.lock,
docs/development/specifications/portable-installed-mcp-bundle.md,
scripts/mcp_smoke.py,
runtime/python/tests/test_client_configs.py, and tests/test_python_runtime_scan.py.

1. Define the common Python launcher and installed bundle artifact contract:
   Python 3.13, the committed stdlib-only requirements.lock, command-directory
   cwd, stderr-only diagnostics, and no secret in generated config. Do not add
   an SDK, package installation, lock hash, or wheelhouse.
2. Generate minimal OpenCode, Claude Code, and Gemini CLI config templates that
   start the same stdio server. OpenCode keeps the exact seven Skill
   permissions; Claude/Gemini are configuration/stdio smoke only.
3. In a clean Python 3.13 environment with network disabled, run the copied
   installed launcher directly and verify initialize, static tools/list
   schemas, start with an external fixture, error semantics, final cleanup,
   and stderr/stdout separation for each template. No dependency install runs.
4. Add tools/list repeat regression to prove later stage tickets cannot alter
   catalog bytes.

**Verification:** python -m unittest runtime.python.tests.test_client_configs tests.test_python_runtime_scan; python scripts/mcp_smoke.py --config-root .artifacts/portable-smoke --all-clients

**Commit:** test: verify portable static MCP bundle

## Ticket 11 — Freeze independent mode-specific E2E goldens

**Files:** tests/evaluation/static-mcp-jpetstore-6-summary-golden.md,
tests/evaluation/static-mcp-jpetstore-6-detailed-golden.md,
tests/evaluation/static-mcp-flask-celery-summary-golden.md,
tests/evaluation/static-mcp-flask-celery-detailed-golden.md,
tests/evaluation/static-mcp-fastapi-template-summary-golden.md,
tests/evaluation/static-mcp-fastapi-template-detailed-golden.md,
tests/evaluation/static-mcp-golden-manifest.json, and
tests/test_static_mcp_golden_manifest.py.

1. Before any provider-backed run, prepare each golden from independent static
   repository evidence without loading the Skill or E2E transcript. Record
   external target path, immutable revision, evidence date, required findings,
   blockers, unknowns, and weights for its named mode.
2. Write the SHA-256 manifest keyed by target and mode. The validator must
   reject a missing file, unknown case/mode, or changed hash.
3. Test tampering only against a temporary copied golden; do not mutate the
   committed evidence during validation.
4. Keep generated provider traces, logs, and scorecards out of this commit.

**Verification:** python -m unittest tests.test_static_mcp_golden_manifest

**Commit:** test: freeze mode-specific migration goldens

## Ticket 12 — Authorized OpenCode PTY E2E and scorecards

**Files:** scripts/run_opencode_acceptance.py,
tests/evaluation/static-mcp-opencode-cases.json,
tests/test_static_mcp_opencode_acceptance.py,
tests/evaluation/static-mcp-scorecards/jpetstore-6-summary-scorecard.md,
tests/evaluation/static-mcp-scorecards/jpetstore-6-detailed-scorecard.md,
tests/evaluation/static-mcp-scorecards/flask-celery-summary-scorecard.md,
tests/evaluation/static-mcp-scorecards/flask-celery-detailed-scorecard.md,
tests/evaluation/static-mcp-scorecards/fastapi-template-summary-scorecard.md,
and tests/evaluation/static-mcp-scorecards/fastapi-template-detailed-scorecard.md.
Do not commit raw isolated HOME, temporary bundles, credentials, or terminal
captures unless a purposely sanitized diagnostic asset is approved.

1. For each target/mode case, validate the committed golden hash first. Build
   a fresh temporary bundle, install seven sibling Skills, copy the configured
   agent, isolate HOME and OPENCODE_CONFIG_DIR, use runtime/opencode.json, and
   run an actual user request in a detached tmux PTY against a read-only
   external target. Use absolute target paths in at least one case and
   command-directory-relative paths in at least one case.
2. Bound each run to one dispatcher start, five accepted stage submissions, one
   finalization, a documented timeout, and guaranteed tmux/session cleanup.
   Capture pre/post target git status --short --branch.
3. Score the final assistant Markdown separately from tool activity using the
   matching frozen mode golden. Direct MCP integration owns static catalog and
   byte equality; E2E owns real Skill loads/reference reads, final Markdown
   contract/accuracy, no tool errors/secrets, and target immutability.
4. If a run fails, diagnose and fix the source in a new ticket/commit, then run
   the full case in a new isolated session. Never ask the same E2E conversation
   to repair a canonical report.

**Verification:** run exactly this provider-backed command with
sandbox_permissions: require_escalated:

~~~
python scripts/run_opencode_acceptance.py --mode isolated --config runtime/opencode.json --cases tests/evaluation/static-mcp-opencode-cases.json --output-dir .artifacts/static-mcp-acceptance --timeout 240 --debug-timeout 60 --repeat 1 --interactive
~~~

The case manifest has six case IDs, one for each Ticket 11 target/mode pair;
the harness accepts --case <case-id> for an isolated rerun. Preserve scorecard
evidence and report the exact unchanged Git statuses.

**Commit:** test: score OpenCode static MCP acceptance

## Delivery gates

- Every ticket stages only its enumerated files and commits after its named
  verification; no broad git add patterns.
- Ticket 2 creates the final static wire shape. Tickets 3–12 may add behavior
  behind it but must run its catalog regression unchanged.
- Ticket 1's ownership matrix controls all rule/template movement. No current
  rule is silently dropped.
- Ticket 11 commits goldens before Ticket 12 performs provider-backed E2E.
- Final completion requires the full test suite appropriate to changed files,
  Python/TypeScript distribution scan, offline packaging smoke, and authorized
  OpenCode results.
