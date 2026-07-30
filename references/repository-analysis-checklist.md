# Detailed Analysis Checklist

Use this checklist only after Detailed mode is explicitly selected. Summary
does not require these fields.

## Required Component Fields

For every deployment candidate, record:

- name, execution form, role, and repository-relative path;
- language, framework, runtime, and version;
- dependency installation, application build, image build, and production
  startup commands as separate stages;
- protocol, listener port or non-listener behavior, and health behavior;
- configuration names and `적용 시점`;
- writable paths, persistence, session behavior, termination and recovery, and
  observability;
- inbound and outbound dependencies, execution location, and supply or
  management boundary;
- containerization classification and evidence.

For each dependency, use the direction `logical source workload -> target` and
record type, protocol/mechanism, endpoint/configuration, timing, execution
location, functional necessity, use in a confirmed launch definition, supply or
management boundary, state, and evidence. Keep the logical source separate from
the actual network caller.

## Completion gate

- immediately after candidate identification, create the internal eight-section
  Detailed skeleton and use it to complete the report before optional reads;
- every required evidence slot is terminal: `확인됨`, `상충됨`, or scoped
  `미확인`; `추정됨` does not close an evidence slot;
- an unknown minimum input names its candidate or shared `범위:` and the
  `결정:` it prevents or leaves open;
- all independently executable candidates and excluded items are represented;
- install, build, image, startup, launch, and operating-environment evidence are
  not conflated;
- the dependency matrix and text dependency graph agree;
- every material fact has valid evidence or a scoped unknown/conflict.
