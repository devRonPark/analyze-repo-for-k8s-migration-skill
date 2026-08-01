# Phase 1 Evidence Integrity Delta Cycle handoff

```yaml
cycle_type: delta
delta_id: 2026-08-02-evidence-integrity
cycle_marker: 2026-08-02-evidence-integrity
parent_cycle: first-project-cycle
baseline_commit: 1686be7
product_baseline: 1686be7
control_plane_parent_commit: b761676
control_plane_commit: HEAD after this documentation-only routing commit (parent b761676)
executable_plan_path: .dryforge/delta/2026-08-02-evidence-integrity/plan.md
first_task: D1
last_task: D6
root_plan_execution: forbidden in this delta
t7_execution: forbidden until this delta is complete and Claude approves it
routing_status: BLOCKED
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

## 공식 Dryforge routing과 승인 후 실행 경계

설치된 `dryforge 1.1.1` 계약을 실제 skill/interface 정의에서 확인했다.

- `...\skills\go\SKILL.md:99-101`의 공식 입력은 root `.dryforge/{handoff,spec,plan}.md`다.
- `...\skills\go\references\harness-lifecycle.md:8-18`의 first-cycle/delta 판별자는
  `.dryforge/status.json`이며, 정확한 marker schema는 `{ "initialized": true }`다.
- `...\skills\go\SKILL.md:124-134,260-295`에 따라 marker가 없으면 first-cycle이고,
  marker는 first-cycle 성공적인 user approval/archive 뒤에 plugin이 쓴다. 현재 marker는
  존재하지 않으므로 이를 수동 생성하지 않는다.
- `...\skills\go\agents\openai.yaml:1-7`의 정확한 공식 prompt는
  `Use dryforge go to execute the 3-doc in .dryforge.`이며 plan path/cycle ID를 지정하는
  별도 option은 없다.

따라서 `.dryforge/delta/2026-08-02-evidence-integrity/plan.md`를 직접 선택하는 공식
Delta Go 호출 문구는 없다. root 호출 문구를 실행하면 root `.dryforge/plan.md`의 T1부터
first-cycle 경로가 선택될 수 있으므로 안전하다고 주장하지 않는다. 이 handoff에서 승인된
정확한 실행 문구는 `없음 — BLOCKED`이고, 공식 plan 선택 방법이 제공될 때까지 `dryforge go`
자체를 실행하지 않는다. root `.dryforge/plan.md`와 T1~T14 graph는 변경하지 않았으며,
이번 delta의 실행 대상에서 명시적으로 제외한다. T7은 delta 완료와 Claude 승인 전까지
실행 금지다.

공식 선택 방법이 추가되어 사용자가 승인한 뒤에만 D1부터 D6를 실행한다. D5는 회귀 테스트를
먼저 실패 상태로 작성한 뒤 구현을 진행한다. D6에서만 실제 Google ADK Runner, Upstage Solar
Pro 3, acceptance Repository와 credential을 사용한다. Go holdout은 이번 delta 범위가 아니므로
자동 호출하지 않는다.

실행 중에도 다음은 금지한다.

- KubernetesMigrationPlan, generate CLI, renderer, manifest validator, Streamlit 구현
- Agent Tool 8개 surface 변경, multi-agent, A2A, graph workflow
- legacy OpenCode 코드 수정
- target Repository 수정, clone, build, test, server, container 실행
- registry/imagePullSecrets/Repository 이름을 business rule로 하드코딩

## Ready 검증 기준

- delta marker와 baseline `1686be7`이 세 문서에 일치한다.
- delta ID가 `2026-08-02-evidence-integrity`이고 executable plan path가
  `.dryforge/delta/2026-08-02-evidence-integrity/plan.md` 하나로 고정된다.
- `cycle_type=delta`, first task `D1`, last task `D6`, root T1~T14 plan 제외, T7 실행 금지,
  routing `BLOCKED`가 세 문서에 일치한다.
- D1~D6가 plan과 handoff에 동일하게 존재한다.
- 모든 dependency가 D1~D6 중 하나를 가리키며 cycle/dangling dependency가 없다.
- 기존 First Cycle graph와 T7은 변경·시작되지 않았다.
- 제품 구현 파일은 변경하지 않았다.
- `git diff --check`가 통과한다.
- 공식 delta plan 선택 방법이 확인되기 전에는 실행할 수 없다. 현재 상태는 `BLOCKED`다.

## 현재 상태

`BLOCKED; awaiting-user-approval`. 이 handoff 이후에는 공식 delta plan 선택 방법이 확인될
때까지 실행을 기다린다. 그 전에는 First Cycle 재개, root T1 실행, T7 이동, D1~D6 구현 및
D6 live acceptance를 수행하지 않는다.
