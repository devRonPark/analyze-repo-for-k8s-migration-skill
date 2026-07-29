# Evidence and Readiness

## Evidence status

Use exactly one status for every material repository fact:

- `확인됨`: directly supported by executable source or configuration;
- `추정됨`: strongly indicated by multiple repository signals but not directly
  confirmed;
- `미확인`: the checked evidence cannot determine the value;
- `상충됨`: reliable evidence gives different values.

Preserve conflicts. Do not select the value that is most convenient for a
Kubernetes design.

## Evidence references

For an existing fact, cite a repository-relative `path/to/file:line` or
`path/to/file:start-end`.

For a verified absence, use exactly:

```text
검색(scope=<repository-relative scope>, pattern=<glob 또는 검색식>, result=없음)
```

An `추정됨` finding includes `/ 판단: <reason>`. An `미확인` finding records
the checked scope and missing information. An `상충됨` finding includes both
sources. Do not invent a file line for an absence or attach metadata evidence
to the repository itself.

Prefer executable source and runtime configuration over development examples.
Separate repository launch definitions from operating-environment deployment
evidence.

## Directional relationships

Represent each dependency as `logical source workload -> target`. Record the
dependency type, protocol or mechanism, endpoint or configuration name, timing,
execution location, `기능 실행에 필요`, `확인된 실행 정의에서 사용 여부`,
`공급 또는 관리 경계`, state, and evidence. Distinguish the logical source
from the actual network caller.

## Kubernetes design-input readiness

End with exactly one verdict:

- `설계 입력 충분`: no repository fact or required input blocks the next design;
- `추가 정보 필요`: analysis is complete but a verified blocker needs a user or
  operator decision;
- `분석 불가`: target access failed or the core runtime could not be identified.

Do not turn every `미확인` value into a blocker. For `추가 정보 필요`, record
each blocker with a category, impact scope (`전체`, `특정 배포 대상`, or
`production 경로`), status, and valid evidence. This verdict is not a
production, security, or SLO approval.
