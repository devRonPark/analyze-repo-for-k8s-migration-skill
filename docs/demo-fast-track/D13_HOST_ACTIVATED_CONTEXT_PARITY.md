# D13 Host-Activated Context Parity Trace

## 1. Motivation and scope

D12 compared model-routed and host-owned successor activation, but its B2
run had 47 persisted model turns and 39 rejected validations, compared with
13 turns and four rejected validations in A2.  This characterization asks the
prior question: did the two owners expose equivalent successor-stage context
before the first successor analysis action?

No orchestration, prompt, Skill, timeout, retry, stage-driver, validation, or
state behavior changed.  The server remains the owner of accepted state,
`next_skill`, transition tokens, validation, snapshot binding, and final
rendering.  D13 adds only a value-free trace projection and comparison.

## 2. Retained evidence and method

All retained D12 Windows PTY/static-MCP artifacts were inspected:

| Run | Owner | Retained transition evidence | Use |
| --- | --- | --- | --- |
| A1 | model | start → Discovery; native Skill call; no action | early no-action control |
| A2 | model | start → Discovery → Execution → Relationships → Boundaries | four comparable successor transitions |
| B1 | host | start → Discovery; host continuation; no action | early host no-action control |
| B2 | host | start → Discovery → Execution → Relationships → Boundaries | four comparable successor transitions and rejection burst |

The artifacts are under `C:\temp\d12-ablation-20260811`.  OpenCode version
is `1.18.14`.  The existing read-only SQLite extraction was used to recover
persisted assistant tool parts, their timing, message association, and tool
results.  The transient SQLite databases themselves were not retained by D12;
the retained normalized `trace.json` records are therefore the evidence
boundary for message-count, part-count, full tool-list, and predecessor prompt
retention claims.

The D13 projection records only structural fingerprints:

* a SHA-256 fingerprint and normalized size for persisted Skill-result text;
* a value-free shape fingerprint for `stage_input` (keys, types, list sizes,
  and string lengths, never target values);
* source/container, role, ordering, occurrence count, and serialized-size
  proxies.

It deliberately does not retain Skill prose, raw stage input, repository data,
assistant prose, or provider errors.

## 3. Observed transition anatomy

For the comparable B2 transitions, the intended host activation did occur in
the accepted server response.  However, OpenCode subsequently persisted a
native `skill(next_skill)` tool call before the first successor analysis action.
Both the host-loaded context and that native call named exactly the server's
`handoff.next_skill`.

```text
A2, Relationships → Boundaries
accepted submit_relationships tool result
→ native skill(analyze-k8s-boundaries) tool result
→ successor model turn completed with finish=stop
→ no Boundaries action

B2, Relationships → Boundaries
accepted submit_relationships tool result containing host_continuation
→ native skill(analyze-k8s-boundaries) tool result
→ successor model turn calls submit_boundaries
→ server rejects the submission
```

This same host-continuation-then-native-skill pattern is present in each B2
successor transition (Discovery, Execution, Relationships, and Boundaries).
B1 did not reach a persisted native Skill call or first action, so it cannot
establish a contrary context shape.

## 4. First divergence

```text
Last equivalent event:
the server accepted the start_analysis handoff and issued exactly
analyze-k8s-discovery with one server-owned stage_input.

First divergent event:
the accepted B2 response additionally contained host_continuation for that
same next_skill.  Before the first Discovery action, OpenCode also persisted
native skill(analyze-k8s-discovery); A2 contained only the native Skill result.

A representation:
accepted handoff tool result → one native Skill tool result.

B representation:
accepted handoff tool result with host_continuation → one native Skill tool
result.
```

The host and native sources use different serializations, so their byte hashes
are not presented as evidence that the serialized text is byte-identical.
The material observation is stronger and narrower: the host loaded the exact
server-selected installed Skill, and OpenCode then invoked that same named
Skill again before the first action.  B therefore has two observed
successor-Skill context components where A has one.

## 5. Parity table: Relationships → Boundaries

This is D12's decision boundary.  `stage_input` values legitimately differ
between independent stochastic runs after their earlier accepted facts differ;
that identity difference is not attributed to host injection.  Its observed
multiplicity is one in both runs.

| Dimension | A2 model-routed | B2 host-owned | Result |
| --- | --- | --- | --- |
| Skill identity | native Skill matches `analyze-k8s-boundaries` | host and native Skills both match | same |
| Skill occurrences | 1 native component | 2 components: host + native | different |
| Skill size | native result 3,718 chars | host 3,126 + native 3,718 chars | different |
| stage_input identity | value-free fingerprint A2 | distinct value-free fingerprint B2 | different (independent run facts) |
| stage_input occurrences | 1 | 1 | same |
| accepted handoff visibility | response, `next_skill`, `accepted_output`, `stage_input` present | same fields present; plus host continuation | same required fields / different extension |
| message role | one persisted tool-result component | two persisted tool-result components; both role `tool`, different containers | different |
| message ordering | handoff → native Skill | handoff → host continuation → native Skill | different |
| turn boundary | 1 persisted native Skill/model turn before action boundary | 1 persisted native Skill/model turn before action boundary | same |
| tool surface | not retained as a first-turn tool-list | not retained as a first-turn tool-list | unavailable |
| prior-stage retention | not observable from retained normalized trace | not observable from retained normalized trace | unavailable |
| context-size proxy | 5,509 serialized chars; 2 components | 12,188 serialized chars; 3 components | different |

At start → Discovery, where the server's one `stage_input` shape fingerprint
does match, the result is still non-parity: A2 is 1 Skill component / 4,953
serialized chars and B2 is 2 / 10,676.  Thus the first divergence does not
depend on later accepted fact differences.

## 6. Turn and rejection divergence

The immediate pre-action turn boundary is not an additional persisted model
turn in B2: both A2 and B2 show one native `skill(next_skill)` turn before the
first successor action.  The first shape difference instead precedes that
turn, inside B2's accepted handoff result, and remains present when OpenCode
then makes the native Skill call.

The D12 retained totals diverge at A2 13 versus B2 47 turns (D12 aggregate:
16 versus 48, including A1/B1).  The first high-volume rejection divergence
is the Relationships → Boundaries transition:

```text
First rejected stage in B2: Boundaries
A2 Boundaries rejects: 0 (no action was selected)
B2 Boundaries rejects: 18 observed submit_boundaries attempts before later
out-of-order Contracts/Finalize attempts
Context divergence already present: yes, from the accepted start handoff and
again at the Relationships → Boundaries handoff.
```

Earlier discovery rejection counts also differ (A2 has two rejected discovery
submissions; B2 has one), so this trace does not claim that the later
Boundaries burst is the first chronological rejection difference.  It is the
first transition at which B2's rejection volume expands while A2 has no
successor action.  Context divergence precedes it, but this observational
ordering is not causal proof.

## 7. Deterministic verification

`tests/test_transition_context_parity.py` covers:

* exact structural parity;
* duplicated successor Skill context;
* duplicated and missing `stage_input`;
* message-role and ordering differences;
* extra turn boundaries;
* quantitative-only context-size changes;
* unavailable artifacts; and
* compatibility with the existing transition trace.

Focused verification:

```text
PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python tests/test_transition_context_parity.py
10 passed

PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python tests/test_post_handoff_liveness.py
20 passed

PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python runtime/python/tests/test_host_owned_transition.py
8 passed
```

No new provider-backed execution was run: the retained artifacts already
contain the required first-divergence signal.

## 8. Outcome

```text
Outcome A — PARITY DEFECT IDENTIFIED
```

D12 was not an ownership-only comparison.  Before every B2 successor action,
the model-visible accepted handoff contains a host-provided successor Skill
component and OpenCode then persists a native result for the same successor
Skill.  This materially changes component multiplicity, tool-result
container/ordering, and context-size proxy before action.  It plausibly
invalidates D12's performance comparison; it does not establish causation for
the rejection burst.

## 9. Next ticket

`D14 — Correct Host-Activation Parity and Re-run Minimal A/B`
