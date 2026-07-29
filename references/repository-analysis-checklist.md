# Repository Analysis Checklist

## Classification

Classify every discovered item in exactly one outcome:

- `배포 대상 후보`
- `저장소에 정의된 런타임 의존성`
- `외부 런타임 의존성`
- `배포 대상 후보에서 제외한 항목`

Use independently executable runtime behavior as the candidate threshold. A
manifest, dependency declaration, build script, CI job, Dockerfile, or Compose
service is evidence, not a deployment conclusion. Evaluate a migration or
initialization command as a one-time job candidate before excluding it.

For an excluded item, record its reason and evidence. Common exclusions are
shared libraries, generated clients, build-only packages, documentation, test
fixtures, and development-only utilities.

## Required Component Fields

For every deployment candidate, record:

- name, execution form, and repository-relative path;
- candidate reason and evidence;
- language, framework, runtime, and version;
- dependency installation, application build, image build, and production startup
  commands as separate stages;
- protocol, listener port or non-listener behavior, and health behavior;
- configuration names and `적용 시점`;
- writable paths, persistence, session behavior, termination and recovery;
- inbound and outbound dependencies, execution location, and supply or management
  boundary;
- containerization classification;
- evidence status and `file:line` or `검색(...)` evidence.

For each dependency, record the direction `logical source workload -> target`,
dependency type, protocol or mechanism, endpoint or configuration name, timing,
`기능 실행에 필요`, `확인된 실행 정의에서 사용 여부`, `공급 또는 관리 경계`,
state, and evidence. Keep the logical source separate from the actual network
caller.

## Containerization Classification

Use exactly one value:

- `기존 컨테이너 정의 있음`
- `대체 이미지 빌드 방식`
- `컨테이너화 필요`
- `컨테이너화 불필요`
- `미확인`

A missing Dockerfile is a finding, not an analysis failure.

## Completion Questions

- Are all independently executable candidates represented?
- Are repository-defined runtime dependencies, external runtime dependencies, and
  excluded items separated?
- Are dependency installation, application build, image build, and production
  startup distinct?
- Are repository launch definitions separate from operating-environment evidence?
- Are ports and health behavior supported by source or runtime configuration?
- Are unknown and conflicting facts preserved?
- Does every material fact have valid positive or absence evidence?
- Does every candidate have Kubernetes minimum inputs or keyed minimum-input gaps?
