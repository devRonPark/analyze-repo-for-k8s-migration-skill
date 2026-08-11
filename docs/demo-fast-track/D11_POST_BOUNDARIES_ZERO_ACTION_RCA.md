# D11 Post-Boundaries Zero-Action Stop RCA

## Scope and evidence boundary

This ticket investigates the exact D10 boundary on OpenCode `1.18.14`:
after an accepted Relationships handoff loaded `analyze-k8s-boundaries`, one
causally bounded assistant turn completed normally with `finish=stop` and did
not select an analysis action. It does not attribute the later PTY timeout to
that completed turn and does not change pipeline behaviour.

The two D10 Solar/JPetStore runs used pinned target revision
`e1dd9a31d1cef68793cd0933ae06898e6fcfa807`, `upstage/solar-pro2`, Summary
mode, and the Windows PTY/static-MCP procedure. D11's comparison run used the
same model, target revision, case, and procedure. The target status was
`## HEAD (no branch)` before and after each provider run.

## 1. Baseline

```text
stage: relationships
next_skill: analyze-k8s-boundaries
Skill load: observed
post-Skill turn: completed normally
finish: stop
first action: none
submit: submit_boundaries not observed
classification: model_turn_completed_no_stage_action
```

This exact state occurred in both D10 attempts. The bounded turn had no
observed reasoning, text, or tool part; those are presence-only observations,
not claims about unobserved model reasoning.

## 2. Successful-vs-failing comparison

The first D10 trace supplies the natural within-session comparison. Every
stage had the same static catalog of 11 analysis tools. Skill `content_bytes`
is the persisted Skill tool result; `stage_input_bytes` is compact UTF-8 JSON
for the server handoff. A missing first action has no delay value.

| Stage | Skill result bytes | Stage input bytes | Post-Skill turn / finish | First analysis action | Skill completion to action | Result |
| --- | ---: | ---: | --- | --- | ---: | --- |
| Discovery | 3,383 | 1,240 | completed / `tool-calls` | `submit_discovery` | 7,586 ms | accepted handoff |
| Execution | 4,019 | 1,475 | completed / `tool-calls` | `submit_execution` | 4,145 ms | accepted handoff |
| Relationships | 3,534 | 1,370 | completed / `tool-calls` | `submit_relationships` | 3,184 ms | accepted handoff |
| Boundaries | 3,718 | 1,645 | completed / `stop` | none | unavailable | no submission |

The Boundaries Skill result was smaller than Execution's. Its 1,645-byte input
was only 275 bytes above Relationships' 1,370-byte input and was not the
largest observed successful context component. Its stage-specific rule
reference is longer (4,209 source bytes) than the Execution (2,104) and
Relationships (1,523) references, but the failed bounded turn had no tool
part. It therefore did not load a reference or payload contract after the
Skill returned. Reference size is not evidence for the stop.

Skill-content comparison found no Boundaries-only completion instruction. All
four Skills share the same Ground, precision, checkpoint, and transition
structure. Boundaries uniquely names its larger accepted-fact set and the
workload-unit/lifecycle decision rule; those are required stage decisions,
not duplicated transition text that can safely be removed.

## 3. Smallest provider-backed comparison

The D11 current-baseline run is the smallest existing acceptance seam: it uses
the pinned `jpetstore-6-summary` case with no provider, timeout, server-state,
or Skill-behaviour modification. It reached the same transition, but differed
only in model-selected action:

```text
Baseline D10:
Boundaries Skill load: observed
post-Skill completion: finish=stop
first action: none
submit_boundaries: none

D11 current baseline:
Boundaries Skill load: observed
post-Skill completion: finish=tool-calls
first action: submit_boundaries (5,413 ms after Skill completion)
submit_boundaries: observed; not accepted
classification: stage_action_observed_no_submission
```

The D11 Boundaries Skill result was 3,742 bytes and its stage input was 1,331
bytes. Earlier Discovery, Execution, and Relationships transitions also
progressed normally. The later rejected Boundaries submissions and timeout are
not substituted for the D10 zero-action failure.

## 4. Tested hypotheses

### H1 — Boundaries-specific context or instruction effect

```text
Discriminator: the same Boundaries transition must consistently stop before an action.
Experiment: compare both D10 stops with an unchanged current Solar/JPetStore baseline.
Result: D11 selected submit_boundaries after the same Skill load.
Decision: Rejected as a consistent Boundaries-Skill cause.
```

### H2 — context-size threshold effect

```text
Discriminator: the failed handoff must cross a size boundary not present in successful transitions.
Experiment: compare persisted Skill-result and serialized stage-input sizes.
Result: Execution progressed with a larger Skill result; D11 Boundaries progressed with a nearby stage-input size. No threshold boundary was observed.
Decision: Rejected.
```

### H3 — general Skill-return continuation defect

```text
Discriminator: a normal post-Skill completion must generally fail to select an action.
Experiment: compare Discovery, Execution, and Relationships post-Skill turns in the same traces.
Result: all selected an analysis tool and completed with finish=tool-calls.
Decision: Rejected as a general defect in the observed static-MCP continuation path.
```

### H4 — specific Boundaries stage-input interaction

```text
Discriminator: varying only a valid Boundaries stage_input must change the zero-action result.
Experiment: compare the valid D10 and D11 server-owned handoffs without manufacturing or weakening accepted state.
Result: action selection varied, but the accepted facts also varied. Isolating the input alone would require a new host-owned transition seam or synthetic accepted state.
Decision: Inconclusive.
```

### H5 — unrelated general provider nonconvergence

```text
Discriminator: failures must occur independently of the Boundaries handoff.
Experiment: retain the D11 provider trace after the first Boundaries action.
Result: D11 made rejected Boundaries submissions after action selection, which is a separate validation/nonconvergence path.
Decision: Inconclusive for the D10 zero-action boundary; not used as its cause.
```

## 5. Root cause and change

No Boundaries-specific root cause is proven. The narrow proven conclusion is
that model-routed continuation is not reliable as the ownership boundary for
this transition: two equivalent runs stopped immediately after the Boundaries
Skill, while an unchanged current run selected `submit_boundaries`. The
evidence does not isolate a valid one-variable Skill or stage-input correction.

No runtime, Skill-behaviour, validation, retry, timeout, or server-state
change was made. D11 adds only safe trace characterization: Skill completion
time, content byte size, serialized handoff size, and a timestamp-proven delay
to the first action. It does not retain Skill content, assistant prose, or
provider error text.

## 6. Verification

```text
Focused D11/D09/D10 liveness tests:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python tests/test_post_handoff_liveness.py
  19 passed
Stage timing tests:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python tests/test_stage_timing_instrumentation.py
  18 passed
D08 Boundaries recovery tests:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s runtime/python/tests -p test_boundaries_recovery.py
  34 passed
Runtime suite:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s runtime/python/tests
  202 passed, 1 skipped
General suite:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python -m unittest discover -s tests
  259 passed, 6 skipped
Static golden:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python scripts/validate_static_mcp_goldens.py
  Static MCP golden manifest: PASS
Bundle:
  PYTHONUTF8=1 PYTHONPATH='runtime/python;.' python tests/test_skill_bundle.py
  1 passed
Provider baseline:
  jpetstore-6-summary, upstage/solar-pro2, 300 seconds, Windows PTY/static MCP
  incomplete final report at 309.550 seconds; Boundaries action observed; target unchanged
```

The provider trace is preserved outside the target at
`C:\temp\d11-baseline-20260811\jpetstore-6-summary\trace.json`.

## 7. Decision

```text
Outcome C
```

## 8. Next ticket

`D12 — Host-Owned Stage Transition / Continuation Ablation`

It should test one bounded host-owned continuation after a detected completed
post-Skill zero-action turn, preserving the same server-owned session and
accepted state, and explicitly terminating on a repeated zero-action turn.
It must not redesign all stage orchestration.
