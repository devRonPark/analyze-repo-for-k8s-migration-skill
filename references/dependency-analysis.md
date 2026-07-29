# Dependency Analysis

## Direction and fields

Write every relationship as `logical source workload -> target component or
external system`. Include:

- source and target;
- dependency type;
- protocol or mechanism;
- endpoint or configuration name when known;
- `기능 실행에 필요한지`;
- `확인된 저장소 기동 정의에서 사용되는지`;
- `공급 또는 관리 경계` (`저장소에 배포 정의 있음`, `외부 관리로 참조`, or
  `미확인`);
- build-time or runtime timing;
- `실행 위치`;
- evidence status and evidence.

The logical source and network caller can differ. A static frontend can depend
logically on an API while the browser is the actual caller.

## Execution location

Use one of these values when applicable:

- `브라우저`;
- `서버 프로세스`;
- `worker 프로세스`;
- `scheduled/job 프로세스`;
- `빌드 파이프라인`;
- `배포 controller`;
- `사람/관리자`;
- `외부 시스템`;
- `미확인`.

## Evidence

A dependency declaration does not prove runtime communication. Use
`path/to/file:line` for existing relationships and the structured Korean search
form for verified absence. Preserve conflicting endpoints, ports, protocols,
and management boundaries.

## Output by mode

Summary uses one concise runtime-dependency field per candidate; it does not
require a dependency matrix or text dependency graph. Detailed output uses both
and the two representations must agree and distinguish build-time from runtime
edges.
