# VS-009 — Add OpenCode Skill loading and permission acceptance checks

## Outcome

The project can prove that OpenCode discovers the installed Skill, loads it for relevant requests, avoids it for unrelated requests, and enforces the analysis-only permission profile.

## Why this is a vertical slice

It validates the actual UI/agent-client boundary from installed distribution to trace and report output. OpenShell is not required yet; this isolates OpenCode integration failures.

## Status and dependencies

- **Status:** Implementation ready; integration verification requires OpenCode installed
- **Depends on:** VS-003, VS-005, VS-008
- **Blocks:** VS-010, VS-011

## Read first

- runtime distribution and installer from VS-003
- minimal-request scenarios from VS-005
- scenario evaluator from VS-008
- official OpenCode Skills and Agents/Permissions docs

## Scope

### In scope

- Add an analysis-only OpenCode agent definition and project test configuration.
- Allow only this Skill; deny edit; constrain bash and external-directory behavior using supported permission keys.
- Create three acceptance cases: minimal Kubernetes analysis, explicit Detailed analysis, unrelated request.
- Capture available Skill metadata, Skill load/tool calls, supporting file reads, final report, and command attempts in a normalized trace format.
- Skip integration tests with a clear reason when OpenCode is absent; never report them as passed.

### Out of scope

- OpenShell policy enforcement.
- Provider-specific quality comparisons.
- Allowing web search or package installation in local repository analysis.

## Implementation steps

1. Add `runtime/opencode.json` and an analysis-agent Markdown definition using the current OpenCode schema.
2. Implement `scripts/run_opencode_acceptance.py` as an adapter around the installed CLI; resolve the exact noninteractive flags from `opencode --help` at implementation time.
3. Normalize trace/output into the VS-008 evaluator input.
4. Assert Summary does not read the Detailed template and unrelated requests do not call the Skill.
5. Add a negative edit or forbidden-bash request and assert OpenCode permission denial.

## Acceptance criteria

- The installed Skill appears with the correct ID and description.
- Minimal request loads the Skill and produces Summary behavior.
- Detailed request reads the detailed template and required references only.
- Unrelated request does not load the Skill.
- Edit and forbidden command attempts are denied by OpenCode permissions.
- Missing OpenCode produces SKIP/UNAVAILABLE, not PASS.

## Verification commands

```bash
opencode --version
python3 scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --output-dir .artifacts/opencode
python3 scripts/evaluate_scenarios.py --cases tests/evaluation/opencode-cases.json --actual-dir .artifacts/opencode
python3 scripts/run_quality_gate.py
```

## Expected file changes

- `runtime/opencode.json` (new)
- `runtime/agents/kubernetes-migration-analyzer.md` (new)
- `scripts/run_opencode_acceptance.py` (new)
- `tests/evaluation/opencode-cases.json` (new)
- `tests/test_opencode_adapter.py` (new)
- `.gitignore` artifact entries

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `test: add OpenCode skill acceptance harness`

## Codex execution instruction

```text
Implement only VS-009. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
