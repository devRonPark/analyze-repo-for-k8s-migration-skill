# TICKET-LIST-2026-07-30-002: Summary Mode 품질 개선 — Vertical Slice Ticket List

- 작성일: **2026-07-30**
- 대상 저장소: `devRonPark/analyze-repo-for-kubernetes-skill`
- 기준 브랜치: `main`
- 기준 커밋: `8f8158e613b02e892d4456002e7668dd758355ab`
- 상태: **Planned**
- 선행 조건: 기존 긴급 P0 티켓 `TKT-001`~`TKT-005` 완료
- 구현 원칙: 각 티켓은 계약, 템플릿, 검증, 테스트를 함께 변경하여 독립적으로 사용자 가치를 제공한다.

## 1. 목표

현재 Summary mode는 구성 요소마다 실행 정보, 설정과 상태, Kubernetes 최소 입력을 모두 나열하여 Detailed mode와 체감 차이가 작다.

이번 작업의 목표는 사용자가 보고서를 열고 **30초 안에** 다음 질문에 답할 수 있게 만드는 것이다.

1. Kubernetes에 올릴 대상은 무엇인가?
2. 각 대상은 어떤 Workload 형태가 적절한가?
3. 주요 런타임 의존성과 운영 경계는 무엇인가?
4. 지금 설계를 실제로 막는 항목은 무엇인가?
5. 설계를 진행하면서 결정하거나 배포 시 입력하면 되는 값은 무엇인가?
6. 이 결과가 어떤 Repository와 Skill 버전에서 생성되고 검증되었는가?

## 2. 품질 기준

완료된 Summary mode는 다음 기준을 만족해야 한다.

- 최종 판정과 핵심 구성이 보고서 첫 화면에 나타난다.
- Summary는 구성 요소별 세부 속성을 반복하지 않는다.
- Repository에서 확인한 사실과 Kubernetes 해석을 구분한다.
- `미확인`을 모두 설계 차단 항목으로 취급하지 않는다.
- 각 핵심 주장에는 추적 가능한 Repository 근거가 있다.
- Detailed mode의 기존 정보량과 검증 계약은 유지한다.
- 동일한 입력과 계약에서는 구조적으로 일관된 결과가 생성된다.
- 고정 Fixture를 사용한 오프라인 회귀 검증이 가능하다.

## 3. 범위 제외

다음 작업은 이 Ticket List의 범위가 아니다.

- Repository 분석 탐색 알고리즘 전체 재작성
- Kubernetes Manifest, Helm Chart 또는 배포 명령 생성
- Detailed mode의 전면 개편
- 모든 자연어 문장의 스타일을 정규식으로 강제
- LLM 응답을 다른 LLM이 평가하는 품질 Gate
- 기존 긴급 P0 티켓과의 병합 구현
- 실제 `full-stack-fastapi-template`의 애플리케이션 코드 수정
- 새 `executive` 출력 모드 추가

---

# 구현 순서

## SUM-001 — 결론 우선 Summary v2를 끝까지 동작시킨다

### 사용자 가치

사용자가 보고서의 첫 화면만 읽어도 최종 판정, 배포 대상, 주요 의존성, 열린 항목을 파악할 수 있다.

### Vertical Slice 범위

Summary 전용 계약을 도입하고 다음 흐름을 템플릿 생성부터 검증까지 연결한다.

```text
제목
→ 한 줄 분석 식별 정보
→ 1. 결론
→ 2. 예상 Kubernetes 구성
→ 3. 관계와 운영 경계
→ 4. 열린 항목
→ 5. 핵심 근거
```

Detailed mode는 현재 구조를 유지한다.

### 구현 내용

- Summary와 Detailed가 동일한 필드 그룹을 강제로 공유하지 않도록 계약을 분리한다.
- Summary 계약에 다음 핵심 필드를 정의한다.
  - `verdict`
  - `deployable_candidates`
  - `runtime_dependencies`
  - `excluded_candidates`
  - `open_item_summary`
  - `reason`
- Summary 템플릿의 첫 번째 본문 섹션을 `결론`으로 변경한다.
- Validator가 Summary v2의 섹션 존재 여부와 순서를 검증한다.
- 기존 Summary v1은 명시적 Legacy 검증 경로에서만 한시적으로 허용한다.
- Detailed 계약과 Detailed Fixture는 변경 전과 동일하게 통과해야 한다.

### 예상 변경 파일

- P0 완료 후 확정된 Markdown Report Contract SSOT
- `skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md`
- `skills/analyze-repo-for-kubernetes/SKILL.md`
- `scripts/report_contract.py`
- `scripts/validate_report.py`
- `tests/test_validate_report.py`
- `tests/test_package.py`

### 테스트 우선 구현 순서

1. Summary v2 최소 유효 Fixture를 작성한다.
2. 첫 번째 H2 섹션이 `결론`이 아니면 실패하는 테스트를 추가한다.
3. Summary v2 필수 섹션 순서 테스트를 추가한다.
4. Detailed 기존 Fixture가 계속 통과하는 회귀 테스트를 추가한다.
5. 계약과 템플릿을 변경한다.
6. Validator를 변경한다.
7. 전체 Quality Gate를 실행한다.

### Acceptance Criteria

- Summary 제목 다음의 첫 번째 H2가 `## 1. 결론`이다.
- 첫 20개 비어 있지 않은 줄 안에 다음 값이 모두 존재한다.
  - 최종 판정
  - 배포 대상
  - 주요 런타임 의존성
  - 열린 항목 요약
- Summary v2에는 기존 구성 요소별 장문 카드가 없어도 된다.
- Detailed mode는 기존 필수 속성 검증을 그대로 유지한다.
- Summary v1과 v2를 자동으로 혼합 판정하지 않는다.
- 계약 버전을 감지하지 못하면 명확한 오류를 반환한다.

### 검증 명령

```bash
python3 -m unittest tests.test_validate_report
python3 -m unittest tests.test_package
python3 scripts/run_quality_gate.py
```

### 완료 정의

- 계약, 템플릿, Validator, Fixture가 함께 반영된다.
- Summary v2 유효 Fixture가 통과한다.
- 기존 Detailed 회귀 테스트가 통과한다.
- Summary v1 호환 정책이 문서에 기록된다.

### 의존성

- 기존 `TKT-002`, `TKT-003` 완료 후 시작한다.

### 범위 제외

- 구성 요소 표의 최종 열 설계
- 차단 항목 분류 체계 변경
- 분석 Provenance의 최종화 처리

---

## SUM-002 — 구성 요소 장문 카드를 한 줄 배포 표로 압축한다

### 사용자 가치

사용자가 backend, frontend, Job, Database 같은 전체 구성을 한눈에 비교할 수 있다.

### Vertical Slice 범위

Summary에서 구성 요소마다 반복되는 수십 개의 속성을 제거하고, 배포 대상별로 한 행만 사용하는 표를 계약, 템플릿, Validator, Fixture까지 적용한다.

### Summary 표 계약

| 열 | 의미 |
|---|---|
| 대상 | Repository에서 식별한 구성 요소 이름 |
| 역할 | API, 정적 Web, Worker, Migration 등 |
| Kubernetes 해석 | Deployment, Job, StatefulSet 후보 등 |
| 포트 | 확인된 수신 포트 또는 `없음` |
| 상태 | Stateless, Persistent, DB 쓰기 등 |
| 주요 의존성 | PostgreSQL, Redis, 외부 API 등 |
| 근거 | 핵심 판단을 지지하는 `file:line` |

### 구현 내용

- Summary의 `component_runtime`, `component_config_state`, `component_k8s_input` 장문 카드를 표 기반 `deployment_overview`로 교체한다.
- Summary에서는 다음 세부 필드를 필수 출력에서 제외한다.
  - 패키지 관리자
  - 설치 명령
  - 상세 빌드 명령
  - 종료와 복구
  - 관찰 가능성
  - 개별 `command`와 `args`
  - 구성 요소별 전체 설정 목록
- 제외된 정보는 Detailed mode에서 계속 제공한다.
- 근거는 각 셀마다 반복하지 않고 행 단위로 한 번 제공한다.
- 표의 각 행은 하나의 독립 실행 단위 또는 배포 후보를 나타낸다.
- 포트가 없거나 적용되지 않는 Job은 `없음`으로 명시한다.

### 예상 변경 파일

- P0 완료 후 확정된 Markdown Report Contract SSOT
- `skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md`
- `scripts/validate_report.py`
- `scripts/report_diagnostics.py`
- `tests/test_validate_report.py`
- `tests/test_package.py`

### 테스트 우선 구현 순서

1. 배포 대상 표가 없는 Summary v2가 실패하는 테스트를 작성한다.
2. 필수 열이 빠진 표가 실패하는 테스트를 작성한다.
3. 근거 열에 유효한 `file:line` 또는 검색 근거가 없으면 실패하는 테스트를 작성한다.
4. 기존 장문 카드 없이도 Summary가 통과하는 테스트를 작성한다.
5. Detailed 카드 필드 누락은 계속 실패하는 테스트를 유지한다.
6. 계약, 템플릿, Validator를 구현한다.

### Acceptance Criteria

- 구성 요소 하나당 Summary 본문에서 정확히 한 개의 대표 행을 사용한다.
- Summary Validator는 장문 카드의 28개 내외 속성을 요구하지 않는다.
- Detailed Validator는 기존 상세 속성을 계속 요구한다.
- 표의 모든 데이터 행에는 유효한 근거가 있다.
- `full-stack-fastapi-template` 대표 Fixture 기준 backend, frontend, prestart가 한 표에서 비교된다.
- 동일 근거 문자열을 한 구성 요소에서 불필요하게 반복하지 않는다.

### 검증 명령

```bash
python3 -m unittest tests.test_validate_report
python3 -m unittest tests.test_package
python3 scripts/run_quality_gate.py
```

### 완료 정의

- Summary가 구성 요소 표만으로 유효하게 검증된다.
- Detailed 카드 검증은 회귀하지 않는다.
- 표 누락과 근거 누락에 대해 구조화된 Diagnostic을 반환한다.

### 의존성

- `SUM-001`

### 범위 제외

- 차단 항목 의미 변경
- Runtime dependency의 분류 규칙 변경
- 표 행의 자연어 길이를 정규식으로 제한하는 작업

---

## SUM-003 — 미확인 항목을 네 종류로 분리하고 판정 의미를 바로잡는다

### 사용자 가치

사용자는 “지금 설계를 못 하는 이유”와 “나중에 결정하거나 값을 넣으면 되는 항목”을 구분할 수 있다.

### Vertical Slice 범위

Summary의 열린 항목을 다음 네 종류로 나누고, 이 분류가 최종 판정에 실제로 반영되도록 계약, 템플릿, Validator, 판정 규칙, 테스트를 함께 변경한다.

### 분류 계약

1. `hard_blocker`
   - 없으면 Workload 구조나 필수 연결 관계를 합리적으로 결정할 수 없는 정보
2. `open_design_decision`
   - 설계 과정에서 선택해야 하지만 현재 초안 작성을 막지는 않는 항목
3. `deployment_value`
   - Registry, Tag, Domain, Secret 값처럼 배포 시 주입할 값
4. `recommendation`
   - 운영 품질을 높이지만 Repository 기반 설계 입력 충분성과는 별개인 권장사항

### 판정 규칙

- `설계 입력 충분`
  - 배포 대상, 실행 형태, 핵심 포트 또는 통신 방식, 주요 의존 관계를 식별할 수 있다.
  - `open_design_decision` 또는 `deployment_value`가 존재해도 허용한다.
- `추가 정보 필요`
  - 하나 이상의 `hard_blocker` 때문에 기본 Workload 구조나 필수 관계를 결정할 수 없다.
- `분석 불가`
  - Repository 접근 실패, 근거 부족 또는 분석 범위 해석 실패로 사실 판단 자체가 불가능하다.

### 대표 분류 예시

| 항목 | 분류 |
|---|---|
| 이미지 Registry와 Tag | `deployment_value` |
| PostgreSQL 관리형 서비스 또는 StatefulSet 선택 | `open_design_decision` |
| Ingress Controller와 TLS 관리 방식 | `open_design_decision` |
| Secret의 실제 값 | `deployment_value` |
| 애플리케이션 시작 명령을 찾을 수 없음 | 상황에 따라 `hard_blocker` |
| 모니터링 추가 | `recommendation` |

### 예상 변경 파일

- P0 완료 후 확정된 Report Contract SSOT
- `skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md`
- `skills/analyze-repo-for-kubernetes/references/evidence-and-readiness.md`
- `skills/analyze-repo-for-kubernetes/references/workflow.md`
- `scripts/validate_report.py`
- `scripts/report_diagnostics.py`
- `tests/test_validate_report.py`
- `tests/test_package.py`

### 테스트 우선 구현 순서

1. Registry 미정만 존재하는 Fixture의 판정이 `설계 입력 충분`인지 검증한다.
2. DB 운영 모델 미정만 존재하는 Fixture의 판정이 `설계 입력 충분`인지 검증한다.
3. 시작 명령과 실행 형태가 모두 없는 Fixture가 `추가 정보 필요`인지 검증한다.
4. `hard_blocker` 없이 `추가 정보 필요`를 반환하면 실패하는 Validator 테스트를 작성한다.
5. `hard_blocker`가 있는데 `설계 입력 충분`이면 실패하는 테스트를 작성한다.
6. 계약, 문서, Validator를 구현한다.

### Acceptance Criteria

- 모든 열린 항목에는 네 분류 중 정확히 하나가 지정된다.
- `미확인` 상태라는 이유만으로 자동으로 `hard_blocker`가 되지 않는다.
- `추가 정보 필요` 판정에는 최소 한 개의 `hard_blocker`가 있어야 한다.
- `설계 입력 충분` 판정에는 `hard_blocker`가 없어야 한다.
- 판정과 열린 항목 분류가 상충하면 Validator가 실패한다.
- Summary의 열린 항목은 중요도 순으로 표시한다.
  - hard blocker
  - open design decision
  - deployment value
  - recommendation

### 검증 명령

```bash
python3 -m unittest tests.test_validate_report
python3 -m unittest tests.test_package
python3 scripts/run_quality_gate.py
```

### 완료 정의

- 판정 규칙이 참고 문서와 Validator에 동일하게 반영된다.
- 대표 분류 Fixture가 모두 통과한다.
- 기존 “미확인 = 차단” 동작을 방지하는 회귀 테스트가 존재한다.

### 의존성

- `SUM-001`
- `SUM-002`

### 범위 제외

- 실제 Secret 값 생성
- 플랫폼별 Ingress Controller 추천
- 관리형 Database 제품 선정

---

## SUM-004 — Repository 사실과 Kubernetes 해석을 분리하고 분류를 일관되게 만든다

### 사용자 가치

사용자는 “Repository에서 실제로 발견한 것”과 “Kubernetes로 옮길 때의 해석”을 혼동하지 않는다.

### Vertical Slice 범위

구성 요소와 의존성의 분류를 Repository 사실 기준으로 먼저 확정한 뒤, Kubernetes 해석을 별도 필드로 표현하도록 분석 지침, Summary 계약, Validator, 대표 Fixture를 함께 변경한다.

### Repository 사실 분류

분석 결과는 다음 네 분류 중 하나를 사용한다.

1. `배포 대상 후보`
2. `저장소에 정의된 런타임 의존성`
3. `외부 런타임 의존성`
4. `배포 대상 후보에서 제외한 항목`

### 분리 규칙

```text
Repository 사실
→ 구성 요소가 저장소의 실행 정의에 존재하는가?
→ 독립적인 런타임 동작이 있는가?
→ 다른 구성 요소가 실행 시 참조하는가?

Kubernetes 해석
→ Deployment, Job, StatefulSet 또는 외부 관리 후보인가?
→ 필수 또는 선택 구성인가?
→ 어떤 운영 경계를 결정해야 하는가?
```

### 대표 기대 동작

- Compose에 정의된 PostgreSQL은 우선 `저장소에 정의된 런타임 의존성`이다.
- PostgreSQL을 관리형 DB로 운영할지는 `Kubernetes 해석` 또는 `open_design_decision`이다.
- 독립 실행되는 migration/prestart는 `배포 대상 후보`이며 Kubernetes에서는 Job 후보가 될 수 있다.
- 독립 실행되는 Adminer는 선택적 `배포 대상 후보`로 분류할 수 있다.
- 로컬 개발 전용 Traefik은 `배포 대상 후보에서 제외한 항목`으로 분류하고 Ingress 대체 판단을 별도로 기록한다.
- 외부 SMTP 또는 Sentry는 Repository에 배포 정의가 없다면 `외부 런타임 의존성`이다.

### 예상 변경 파일

- `skills/analyze-repo-for-kubernetes/SKILL.md`
- `skills/analyze-repo-for-kubernetes/references/repository-analysis-checklist.md`
- `skills/analyze-repo-for-kubernetes/references/dependency-analysis.md`
- `skills/analyze-repo-for-kubernetes/references/evidence-and-readiness.md`
- P0 완료 후 확정된 Report Contract SSOT
- `skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md`
- `scripts/validate_report.py`
- `tests/test_validate_report.py`
- `tests/test_package.py`
- `tests/fixtures/summary-classification/`

### 테스트 우선 구현 순서

1. Compose-defined DB가 외부 의존성으로만 표시되면 실패하는 Fixture를 작성한다.
2. 동일 구성 요소가 상충하는 두 분류에 동시에 존재하면 실패하는 테스트를 작성한다.
3. Repository 분류와 Kubernetes 해석이 하나의 값으로 합쳐져 있으면 실패하는 구조 테스트를 작성한다.
4. prestart, Adminer, local-only proxy 대표 Fixture를 추가한다.
5. 분석 지침, 계약, 템플릿, Validator를 구현한다.

### Acceptance Criteria

- 동일한 구성 요소는 Repository 사실 분류에서 정확히 하나의 범주에만 속한다.
- Repository 분류와 Kubernetes 해석이 별도 필드 또는 별도 열로 표현된다.
- “운영에서는 외부 DB 권장”이라는 판단이 Repository의 DB 정의 존재를 지우지 않는다.
- 선택적 배포 대상과 제외 항목을 혼용하지 않는다.
- 분류 상충 시 Validator가 구조화된 오류를 반환한다.
- `full-stack-fastapi-template` 대표 Fixture에서 PostgreSQL, prestart, Adminer, Traefik의 분류가 기대값과 일치한다.

### 검증 명령

```bash
python3 -m unittest tests.test_validate_report
python3 -m unittest tests.test_package
python3 scripts/run_quality_gate.py
```

### 완료 정의

- 분류 규칙이 Skill 지침과 Validator에 모두 반영된다.
- 상충 분류를 차단하는 테스트가 존재한다.
- 대표 구성 요소 분류 Fixture가 통과한다.

### 의존성

- `SUM-002`
- `SUM-003`

### 범위 제외

- 특정 Cloud의 관리형 DB 제품 추천
- Adminer의 운영 배포 보안 승인
- 실제 Ingress Manifest 생성

---

## SUM-005 — 분석 대상, Skill, 계약과 검증 결과를 한 줄로 증명한다

### 사용자 가치

사용자는 보고서가 어떤 코드와 어떤 계약을 사용해 만들어졌는지 확인하고 동일 조건으로 재현할 수 있다.

### Vertical Slice 범위

준비 단계에서 Provenance를 수집하고, 검증 성공 후에만 Summary 상단에 검증 완료 Receipt를 기록하는 흐름을 구현한다.

### 표시 형식

```text
Target: <source> @ <resolved revision> | Skill: <version or commit> |
Contract: <contract version> | Validation: passed
```

로컬 Checkout이 Git 저장소인 경우 branch 이름만 쓰지 않고 resolved commit SHA를 포함한다.

### 구현 내용

- `target.json`에 다음 값을 기록한다.
  - Target resolved revision
  - 분석 subdirectory
  - Skill ID와 version
  - 가능하면 Skill source commit
  - Report contract version
- Summary 템플릿에는 `Validation: pending` 상태의 Placeholder를 둔다.
- `validate_target_report.py`가 본문 검증에 성공한 경우에만 Receipt를 `passed`로 원자적으로 최종화한다.
- 본문 검증 실패 시 `passed`를 기록하지 않는다.
- 최종화 이후 최소 구조 검증을 한 번 더 수행한다.
- Source archive는 commit 대신 archive SHA-256을 사용한다.
- Git 정보가 없는 Local directory는 `revision: unavailable`을 명시하며 임의 값을 생성하지 않는다.

### 예상 변경 파일

- `scripts/prepare_analysis_target.py`
- `scripts/source_intake.py`
- `scripts/plain_remote_git_clone.py`
- `scripts/validate_target_report.py`
- P0 완료 후 확정된 Project Metadata SSOT
- P0 완료 후 확정된 Report Contract SSOT
- `skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md`
- `scripts/validate_report.py`
- `tests/test_prepare_analysis_target.py`
- `tests/test_validate_target_report.py`
- `tests/test_validate_report.py`

### 테스트 우선 구현 순서

1. Local Git Checkout이 commit SHA를 기록하는 테스트를 작성한다.
2. Source archive가 archive SHA-256을 기록하는 테스트를 작성한다.
3. 검증 실패 시 Receipt가 `pending` 또는 실패 상태로 남는 테스트를 작성한다.
4. 검증 성공 시에만 `passed`로 원자적 전환되는 테스트를 작성한다.
5. Skill version과 contract version 누락 시 실패하는 Summary 테스트를 작성한다.
6. 준비, 최종화, 검증 코드를 구현한다.

### Acceptance Criteria

- `master (HEAD)` 또는 `main (HEAD)`만으로 분석 revision을 표시하지 않는다.
- Git Repository이면 최소 7자리 이상의 resolved commit SHA를 포함한다.
- Skill ID/version과 Report contract version을 표시한다.
- `Validation: passed`는 실제 Validator 성공 후에만 기록된다.
- Validation 실패 결과에는 성공 Receipt가 존재하지 않는다.
- Detailed mode의 기존 출력에는 Provenance를 강제하지 않거나, 별도 후속 결정 전까지 현재 동작을 유지한다.
- Provenance 값은 Secret을 포함하지 않는다.

### 검증 명령

```bash
python3 -m unittest tests.test_prepare_analysis_target
python3 -m unittest tests.test_validate_target_report
python3 -m unittest tests.test_validate_report
python3 scripts/run_quality_gate.py
```

### 완료 정의

- 준비 단계부터 최종 보고서까지 Provenance가 전달된다.
- 성공 Receipt의 거짓 양성을 방지하는 테스트가 존재한다.
- Local Git, Remote Git, Source archive 경로를 모두 검증한다.

### 의존성

- 기존 `TKT-001`
- 기존 `TKT-002`
- 기존 `TKT-003`
- `SUM-001`

### 범위 제외

- Git commit 서명 검증
- SBOM 또는 SLSA Provenance 구현
- Remote Repository의 현재 최신 commit과 재비교

---

## SUM-006 — `full-stack-fastapi-template` 고정 Fixture로 정확성과 가독성을 Release Gate에 넣는다

### 사용자 가치

실제에 가까운 Full-stack Repository를 분석해도 Summary가 다시 장문 보고서로 퇴행하거나 핵심 사실을 잘못 표시하는 일을 조기에 발견할 수 있다.

### Vertical Slice 범위

`full-stack-fastapi-template`의 특정 upstream commit을 기준으로 분석에 필요한 최소 파일만 포함한 오프라인 Fixture와 Golden Summary를 만들고, 이를 전체 Quality Gate에 연결한다.

### Fixture 원칙

- Upstream commit SHA를 고정한다.
- 필요한 파일만 최소 범위로 보관한다.
  - Compose 정의
  - backend Dockerfile과 package metadata
  - backend startup 또는 prestart script
  - frontend Dockerfile과 package metadata
  - nginx 설정
  - 주요 설정 스키마
- Fixture 출처와 License 정보를 기록한다.
- 테스트 중 네트워크에 접속하지 않는다.
- 기대 사실은 Fixture 파일에서 직접 도출할 수 있어야 한다.

### 검증 항목

#### 정확성

- backend runtime과 startup command
- frontend package manager와 build command
- backend와 frontend 수신 포트
- prestart의 일회성 실행 형태
- PostgreSQL의 Repository 사실 분류
- Adminer의 선택적 배포 대상 여부
- local-only proxy의 제외 여부
- 주요 외부 의존성
- 최종 판정과 열린 항목 분류

#### 가독성

- 첫 20개 비어 있지 않은 줄에 판정과 핵심 구성이 포함된다.
- 구성 요소당 장문 H4 카드가 생성되지 않는다.
- 배포 대상은 한 표에서 비교된다.
- 동일한 핵심 누락이 여러 섹션에 반복되지 않는다.
- Golden Summary는 Fixture 기준 최대 줄 수를 초과하지 않는다.
- 권장 Fixture 예산:
  - 기본 45줄
  - 배포 대상당 1줄
  - Runtime dependency당 1줄
  - 열린 항목당 1줄
  - Markdown 구분선과 제목을 포함해 **총 90줄 이하**

### 예상 변경 파일

- `tests/fixtures/full-stack-fastapi-template-summary/`
- `tests/golden/full-stack-fastapi-template-summary.md`
- `tests/test_summary_quality.py`
- `tests/test_package.py`
- `scripts/run_quality_gate.py`
- Fixture 출처와 License 문서

### 테스트 우선 구현 순서

1. 고정 upstream commit과 필요한 파일 목록을 확정한다.
2. Fixture에서 기대 사실을 읽는 테스트를 작성한다.
3. Golden Summary 구조 테스트를 작성한다.
4. 가독성 예산 테스트를 작성한다.
5. 잘못된 runtime, command, package manager를 넣었을 때 실패하는 Mutation 테스트를 작성한다.
6. Quality Gate에 신규 테스트를 연결한다.
7. Optional model smoke test는 별도 명령으로 제공한다.

### Acceptance Criteria

- 오프라인에서 Fixture와 Golden Summary 검증이 가능하다.
- Summary가 90줄을 초과하면 Fixture 품질 테스트가 실패한다.
- backend, frontend, prestart가 한 표에 존재한다.
- PostgreSQL이 Repository 사실과 Kubernetes 운영 선택으로 분리되어 나타난다.
- Registry/Tag 미정만으로 `추가 정보 필요` 판정을 내리지 않는다.
- 기대 runtime, startup command 또는 package manager가 달라지면 테스트가 실패한다.
- Detailed mode의 기존 Golden 또는 Fixture 테스트가 계속 통과한다.
- `python3 scripts/run_quality_gate.py`에 신규 품질 테스트가 포함된다.

### 검증 명령

```bash
python3 -m unittest tests.test_summary_quality
python3 -m unittest tests.test_package
python3 scripts/run_quality_gate.py
```

### 완료 정의

- 고정 Fixture와 Golden Summary가 Repository에 포함된다.
- 정확성, 구조, 가독성 회귀 테스트가 모두 통과한다.
- 네트워크 없이 Quality Gate를 실행할 수 있다.
- Fixture 갱신 절차가 문서화된다.

### 의존성

- `SUM-001`
- `SUM-002`
- `SUM-003`
- `SUM-004`
- `SUM-005`

### 범위 제외

- 모든 오픈소스 Repository를 Golden Fixture로 추가
- 실제 LLM 응답의 문장 미학 점수화
- 네트워크가 필요한 upstream 최신 버전 자동 추적

---

# 4. Release Gate

모든 티켓 구현 후 다음 조건을 만족해야 Summary mode v2를 기본값으로 전환한다.

1. 기존 P0 티켓 `TKT-001`~`TKT-005`가 완료되어 있다.
2. 전체 Unit Test와 Quality Gate가 통과한다.
3. Summary v2 Fixture가 90줄 이하이다.
4. 첫 화면에 판정, 배포 대상, 의존성, 열린 항목이 표시된다.
5. Summary에는 장문 구성 요소 카드가 없다.
6. Detailed mode의 기존 검증과 Fixture가 회귀하지 않는다.
7. 판정과 `hard_blocker` 분류가 논리적으로 일치한다.
8. 분류 상충이 없다.
9. Provenance와 Validation Receipt가 유효하다.
10. `full-stack-fastapi-template` 고정 Fixture의 정확성 기대값이 모두 일치한다.

## 최종 검증

```bash
python3 scripts/run_quality_gate.py
```

가능하면 실제 모델 환경에서 다음 Smoke Test를 별도로 수행한다.

```text
입력: 고정 full-stack-fastapi-template Fixture
모드: summary
확인:
- 첫 화면 의사결정 가능
- 90줄 이하
- 핵심 사실 일치
- 근거 추적 가능
- 최종 판정과 열린 항목 분류 일치
```

# 5. 작업 중단 조건

다음 상황에서는 후속 티켓을 진행하기 전에 현재 Slice를 수정한다.

- Summary 변경이 Detailed 검증을 깨뜨림
- v1과 v2 계약이 자동 감지 과정에서 혼합됨
- Validator를 통과하지만 필수 근거가 없음
- `hard_blocker`와 판정이 상충함
- 동일 구성 요소가 두 Repository 분류에 동시에 포함됨
- 검증 실패 보고서에 `Validation: passed`가 표시됨
- 고정 Fixture의 사실과 Golden Summary가 불일치함
- 사용자 가치를 확인할 수 없는 내부 리팩터링만 남음
