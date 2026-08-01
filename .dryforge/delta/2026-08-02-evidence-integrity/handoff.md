# Phase 1 Evidence Integrity Delta Cycle handoff

```yaml
cycle_type: delta
cycle_marker: phase1-evidence-integrity-2026-08-02
parent_cycle: first-project-cycle
baseline_commit: 1686be7
ready_status: awaiting-user-approval
first_cycle_status: phase1-t1-t6-implemented
next_delta_task: D1
```

## 이 Ready의 의미

이번 Ready는 새로운 First Project Cycle이 아니다. `1686be7`의 Phase 1 구현에 대해 Claude
Gate에서 발견된 Evidence 무결성 결함을 보정하는 별도 delta cycle을 정의한다.

현재 실행은 문서 생성으로 끝난다. 제품 코드, 테스트 코드, 기존 First Cycle 문서, 기존
T1~T14 graph, T7 또는 live acceptance를 이 Ready에서 수정·실행하지 않는다. 사용자 승인
전에는 기존 First Cycle을 재개하지 않는다.

## 산출물

- `spec.md`: delta 동작 계약과 상태 의미론
- `plan.md`: D1~D6 작업 정의와 Execution Graph
- `handoff.md`: cycle marker, baseline, 승인 및 실행 경계

세 문서는 모두 이 delta directory에만 있으며 First Cycle의 `.dryforge/spec.md`,
`.dryforge/plan.md`, `.dryforge/handoff.md`를 덮어쓰지 않는다.

## 실행 순서와 dependency

```text
D1 → D2 → D3 → D4 → D5 → D6
             ↘       ↗
              (D3는 D1·D2, D5는 D1~D4 필요)
```

정규 graph의 dependency는 다음과 같다.

- D1: []
- D2: [D1]
- D3: [D1, D2]
- D4: [D3]
- D5: [D1, D2, D3, D4]
- D6: [D5]

따라서 첫 delta `go`의 시작 task는 D1이며, D6은 D5의 테스트와 검증 증거가 있을 때만
실행된다.

## 기존 First Cycle 영향

- 기존 T1~T14 graph: 변경 없음
- T1~T6 구현: baseline으로 취급하며 delta에서 필요한 경계만 보정 대상으로 표시
- T7: 미시작, delta 완료 후에도 자동 시작하지 않음
- First Cycle 상태: 완료 처리하지 않음
- 기존 사용자 작업 트리 변경: 보존하고 delta 문서 commit에 포함하지 않음

## 승인 후 `dryforge go` 경계

승인 후에만 `plan.md`의 D1~D6를 실행한다. D5는 회귀 테스트를 먼저 실패 상태로 작성한
뒤 구현을 진행한다. D6에서만 실제 Google ADK Runner, Upstage Solar Pro 3, acceptance
Repository와 credential을 사용한다. Go holdout은 이번 delta 범위가 아니므로 자동 호출하지
않는다.

실행 중에도 다음은 금지한다.

- KubernetesMigrationPlan, generate CLI, renderer, manifest validator, Streamlit 구현
- Agent Tool 8개 surface 변경, multi-agent, A2A, graph workflow
- legacy OpenCode 코드 수정
- target Repository 수정, clone, build, test, server, container 실행
- registry/imagePullSecrets/Repository 이름을 business rule로 하드코딩

## Ready 검증 기준

- delta marker와 baseline `1686be7`이 세 문서에 일치한다.
- D1~D6가 plan과 handoff에 동일하게 존재한다.
- 모든 dependency가 D1~D6 중 하나를 가리키며 cycle/dangling dependency가 없다.
- 기존 First Cycle graph와 T7은 변경·시작되지 않았다.
- 제품 구현 파일은 변경하지 않았다.
- `git diff --check`가 통과한다.
- 사용자가 승인하면 D1부터 delta `go`를 실행할 수 있다.

## 현재 상태

`awaiting-user-approval`. 이 handoff 이후에는 사용자 승인을 기다린다. 승인 전에는 First
Cycle 재개, T7 이동, D1~D6 구현 및 D6 live acceptance를 수행하지 않는다.
