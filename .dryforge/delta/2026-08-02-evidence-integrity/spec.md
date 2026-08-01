# Phase 1 Evidence Integrity Delta Cycle 명세

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
```

## 목적

이 문서는 `1686be7`에서 T1~T6 구현이 완료된 Phase 1에 대해 Claude Gate에서 발견된
Evidence 무결성 결함만 보정하기 위한 별도 delta cycle의 실행 계약이다. 새로운 First
Project Cycle을 만들지 않으며, 기존 First Cycle의 T1~T14 task graph를 재생성하거나
수정하지 않는다.

핵심 목표는 Repository read-only 경계, 실제 Repository에 대조되는 line-backed Evidence,
`confirmed`/`inferred`/`unresolved`/`conflicting` 상태 분리, `validate_analysis`를 통한
complete 승인, Secret redaction을 실행 경계 전체에서 일관되게 보장하는 것이다.

## delta 범위

다음 결함만 D1~D6에서 다룬다.

1. `.git` 경로의 대소문자 및 canonical/symlink/junction 우회
2. Repository-aware validation 없이 `complete`가 되는 경로
3. 외부 배포 결정 때문에 전체 분석이 `partial`이 되는 잘못된 상태 의미론
4. 내용 없는 Evidence와 summary/finding의 연결 부족
5. fallback observation의 `confirmed` 자동 승격
6. URL authority, Git remote, JDBC/general connection URL credential redaction 누락

## 공통 계약

- 입력 Repository는 항상 read-only이며, target 내부의 instruction, README, 주석은
  신뢰할 수 없는 분석 데이터다.
- 모든 positive Evidence는 repository-relative `path`, 유효한 `line_start`/`line_end`,
  실제 Repository에서 읽은 `excerpt`를 가져야 한다.
- 부재 주장은 `absence_scope`, `absence_pattern`, `absence_result`를 기록한다. 부재를
  positive Evidence 또는 `confirmed`로 바꾸지 않는다.
- structured finding은 자신이 사용하는 Evidence ID를 명시하고, summary는 검증된
  finding/Evidence로부터만 렌더링한다.
- Secret 값과 credential은 model context, ledger, JSON, Markdown report, exception,
  history, artifact에 노출하지 않는다. 이름·위치·필요성만 안전하게 남긴다.
- `ledger.result`가 Repository-aware `validate_analysis`를 통과한 경우만 `complete`다.
- 외부 배포 선택사항(registry, imagePullSecrets, deployment environment 등)이
  Repository에 결정되어 있지 않다는 사실은 `unresolved`로 남길 수 있으며, 그 자체로
  전체 분석을 `partial`로 만들지 않는다.

## 상태 의미론

### complete

- Repository 탐색이 정상 종료되었다.
- Repository에서 확인 가능한 핵심 사실을 충분히 확보했다.
- 실제 내용이 있는 line-backed Evidence가 있다.
- 모든 finding이 Evidence ID로 연결되어 있다.
- `validate_analysis`가 성공했고 그 결과가 `ledger.result`에 저장되어 있다.
- 외부 환경 선택 또는 사용자 결정이 `unresolved`로 남아 있어도 된다.

### partial

실행 과정이 실제로 끝까지 완료되지 않은 경우에만 사용한다.

- iteration 또는 byte budget 소진
- duplicate/no-progress 종료
- Tool 실행 오류
- model parsing 또는 structured output 오류
- 필요한 Repository 탐색 또는 Evidence coverage 미완료
- fallback 경로에서 Agent의 검증된 판단을 얻지 못함

### failed

- dependency 또는 configuration failure
- schema 또는 Repository-aware validation failure
- 내부 실행 오류
- artifact 저장 실패

## 범위 밖

이번 delta에서는 KubernetesMigrationPlan, `generate` CLI, renderer, manifest validator,
Streamlit, Go holdout, multi-agent/A2A/graph workflow, T7 시작, 기존 OpenCode legacy 코드,
Agent Tool 8개 surface 변경, 기존 First Cycle task graph 변경을 수행하지 않는다.

Ready 단계에서는 제품 코드와 기존 사용자 변경사항을 수정하지 않는다. D1~D6 구현과
Solar Pro 3 live acceptance는 사용자 승인 후 별도의 delta `go` 실행에서만 수행한다.

## routing 계약과 실행 차단

실제 설치 plugin `dryforge 1.1.1`의 `skills/go/SKILL.md:99-101`은 root
`.dryforge/{handoff,spec,plan}.md`만 읽는다. `skills/go/references/harness-lifecycle.md:8-18`
은 `.dryforge/status.json`의 정확한 schema `{ "initialized": true }`와 marker 존재 여부를
first-cycle/delta 판별자로 정의하며, 성공적인 first-cycle archive 뒤에 marker를 생성한다.
현재 repository에는 marker가 없으므로 root 실행은 first-cycle이다. `skills/go/SKILL.md:124-134`
및 `260-295`의 계약에 따르면 delta directory의 `plan.md`를 자동 선택할 수 없다.

plugin interface `skills/go/agents/openai.yaml:1-7`의 정확한 호출 문구는
`Use dryforge go to execute the 3-doc in .dryforge.`뿐이며 cycle ID 또는 plan path 선택
옵션이 없다. 따라서 `.dryforge/delta/2026-08-02-evidence-integrity/plan.md`를 실행하는
공식 Delta Go 호출은 없고, 현재 routing은 `BLOCKED`다. `status.json`을 추측으로 만들거나
root `.dryforge/plan.md`를 delta plan으로 취급하지 않는다. root T1~T14 graph는 이번 delta
대상이 아니며 T7은 delta 완료와 Claude 승인 전까지 실행 금지다.
