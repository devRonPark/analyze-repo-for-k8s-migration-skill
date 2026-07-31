# VS-010 — Add OpenShell policy, preflight, and launch wrapper

## Outcome

OpenCode can be launched in an OpenShell sandbox where the target and Skill are read-only, output is separately writable, the process is non-root, and network access is deny-by-default with explicit agent/inference allowances.

## Why this is a vertical slice

It delivers the complete runtime boundary from parameter validation through sandbox creation and observable policy decisions. It can be tested independently of report quality.

## Status and dependencies

- **Status:** Implementation ready; full verification requires a reachable OpenShell gateway
- **Depends on:** VS-003, VS-009
- **Blocks:** VS-011

## Read first

- `runtime/opencode.json` from VS-009
- official OpenShell Supported Agents, Policy Schema, Policies, Security Best Practices, and Logging docs
- installed `openshell --help` output

## Scope

### In scope

- Add a version-1 OpenShell policy template with absolute path substitution.
- Use `filesystem_policy.include_workdir: false`; target and Skill paths read-only; dedicated output path read-write.
- Use Landlock `hard_requirement` for production acceptance and an explicitly named development variant only if needed.
- Run as non-root `sandbox` user/group.
- Declare only observed OpenCode binary paths and required endpoints; start from default deny.
- Route inference through configured OpenShell provider/inference path without placing raw provider credentials in the repository or report.
- Add preflight for path existence, read/write expectations, `python3`, `git`, `rg` fallback, validator, templates, OpenCode, and OpenShell versions.
- Launch with `openshell sandbox create --policy <file> -- opencode` after resolving current CLI details.

### Out of scope

- Broad internet access, package registries, curl-based installers, or writable target mounts.
- Hardcoding secrets or machine-specific absolute paths in committed files.
- Automatically weakening a denied policy based on agent requests.

## Implementation steps

1. Create a policy template and a renderer that rejects relative paths and target/output overlap.
2. Create `runtime/launch-opencode.sh` with preflight, rendered-policy output, sandbox name, and artifact directory.
3. Add static policy tests for schema version, non-root identity, `include_workdir: false`, and path separation.
4. When OpenShell is available, create a smoke sandbox, collect `openshell logs <name> --source sandbox`, and verify expected CONFIG events.
5. Document environment variables and teardown without embedding credentials.

## Acceptance criteria

- Preflight fails before sandbox creation for missing paths, writable target, overlapping mounts, or missing binaries.
- Policy contains no root process identity and no broad `/` read-write path.
- Target write fails while output write succeeds.
- Unapproved egress is denied and visible in logs.
- OpenCode required traffic is added only from observed denied-request evidence.
- Missing gateway is reported as an environment blocker, not a code failure or pass.

## Verification commands

```bash
openshell --version
python3 runtime/render_policy.py --target /abs/repo --skill /abs/skill --output /abs/output --out .artifacts/policy.yaml
python3 -m unittest discover -s tests -p 'test_openshell_policy.py' -v
bash runtime/launch-opencode.sh --dry-run --target /abs/repo --output /abs/output
# Integration environment only:
openshell sandbox create --policy .artifacts/policy.yaml -- opencode
```

## Expected file changes

- `runtime/openshell-policy.template.yaml` (new)
- `runtime/render_policy.py` (new)
- `runtime/launch-opencode.sh` (new)
- `runtime/README.md` (new)
- `tests/test_openshell_policy.py` (new)

## Commit boundary

- Commit only the files needed by this ticket.
- Do not include opportunistic refactors from later tickets.
- Suggested commit: `feat: add secure OpenShell runtime for OpenCode`

## Codex execution instruction

```text
Implement only VS-010. Read this ticket and the files listed under “Read first”.
Preserve all behavior outside this ticket. Run the baseline and ticket-specific checks.
Do not implement later tickets, weaken tests, or claim OpenCode/OpenShell integration
without executing the required acceptance checks. Report facts, evidence-backed
inferences, and unresolved environment dependencies separately.
```
