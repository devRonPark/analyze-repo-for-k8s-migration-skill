# ADR-2026-07-30-002: Summary mode를 결론 우선의 독립 계약으로 재설계한다

- 상태: **Accepted for implementation after P0 tickets**
- 결정일: **2026-07-30**
- 대상 저장소: `devRonPark/analyze-repo-for-kubernetes-skill`
- 기준 브랜치: `main`
- 기준 커밋: `8f8158e613b02e892d4456002e7668dd758355ab`
- 관련 문서: [TICKET-LIST-2026-07-30-002-summary-mode-v2.md](TICKET-LIST-2026-07-30-002-summary-mode-v2.md)
- 선행 결정: 기존 긴급 P0 티켓 `TKT-001`~`TKT-005`

## 1. Context

현재 Summary mode는 이름과 달리 구성 요소마다 다음 정보를 반복한다.

- 실행 형태와 경로
- 언어, 프레임워크, 런타임
- 패키지 관리자와 설치·빌드·기동 명령
- 프로토콜, 포트, 상태 확인
- 설정, Secret, 영속성, 적용 시점
- 종료와 복구, 관찰 가능성
- Kubernetes Workload, image, command, args, Service, Ingress
- 최소 입력 누락과 개별 근거

현재 Validator도 Summary 구성 요소마다 이 세부 속성을 필수로 요구한다. 그 결과 Summary는 Detailed 보고서보다 짧은 의사결정 문서가 아니라, Detailed 정보의 다른 배열에 가깝다.

`full-stack-fastapi-template` 분석 결과에서는 다음 문제가 함께 확인되었다.

1. 최종 판정이 보고서 끝에 있어 핵심 결론을 늦게 확인한다.
2. 모든 속성에 동일한 `상태 / 근거` 형식을 반복하여 중요한 차단 항목이 묻힌다.
3. Repository 사실, Kubernetes 해석, 후속 설계 선택이 섞인다.
4. Registry, Tag, DB 운영 모델, Ingress 방식 같은 서로 다른 성격의 미정 항목이 모두 설계 차단 항목으로 취급된다.
5. branch 이름만 표시하고 resolved commit SHA나 Skill·계약 버전을 충분히 증명하지 못할 수 있다.
6. 실제에 가까운 고정 Repository Fixture가 없어 정확성과 가독성 퇴행을 동시에 막기 어렵다.

이 문제는 Prompt 문장을 조금 줄이는 방식으로 해결할 수 없다. 현재 계약과 Validator가 장문 필드 출력을 요구하기 때문이다.

## 2. Decision

Summary mode를 Detailed mode와 다른 목적을 가진 **결론 우선의 독립 Report Contract**로 재설계한다.

### 2.1 Summary의 제품 목적

Summary는 사용자가 30초 안에 다음을 판단하도록 돕는다.

- 어떤 구성 요소를 배포해야 하는가?
- 예상 Kubernetes 형태는 무엇인가?
- 주요 의존성과 운영 경계는 무엇인가?
- 지금 설계를 실제로 막는 항목은 무엇인가?
- 설계 중 결정하거나 배포 시 입력하면 되는 것은 무엇인가?
- 분석 결과를 재현할 수 있는 대상·Skill·계약 정보는 무엇인가?

Summary는 Repository의 모든 세부 정보를 보여주는 문서가 아니다. 세부 실행 정보는 Detailed mode의 책임으로 유지한다.

### 2.2 Summary 출력 순서

Summary v2는 다음 순서를 사용한다.

```text
# Kubernetes 설계 입력 요약

Target / Skill / Contract / Validation Receipt

## 1. 결론
## 2. 예상 Kubernetes 구성
## 3. 관계와 운영 경계
## 4. 열린 항목
## 5. 핵심 근거
```

최종 판정은 첫 번째 본문 섹션에 위치한다.

### 2.3 구성 요소 표현

Summary는 구성 요소별 장문 카드를 사용하지 않는다.

대신 구성 요소 하나당 한 행을 사용하는 배포 개요 표를 사용한다.

| 대상 | 역할 | Kubernetes 해석 | 포트 | 상태 | 주요 의존성 | 근거 |
|---|---|---|---|---|---|---|

다음 세부 정보는 Summary 필수 출력에서 제외하고 Detailed mode에 유지한다.

- 패키지 관리자
- 설치 명령
- 상세 빌드 명령
- 종료와 복구
- 관찰 가능성 상세
- 전체 설정 목록
- 개별 command와 args
- Service와 Ingress의 세부 초안

Summary에 포함할 가치가 있는 예외적인 세부 사항은 결론이나 열린 항목에 압축해서 기록한다.

### 2.4 근거 표현

Summary에서도 근거 추적 가능성을 유지한다.

다만 각 속성마다 근거를 반복하지 않고 다음 단위로 묶는다.

- 배포 개요 표의 행 단위 근거
- 관계 또는 운영 경계 행 단위 근거
- 열린 항목 행 단위 근거
- 판정을 지지하는 핵심 근거 목록

Detailed mode는 기존의 세부 속성별 근거 방식을 유지할 수 있다.

### 2.5 열린 항목 분류

모든 미확인 항목을 차단 요인으로 취급하지 않는다.

Summary v2는 다음 네 분류를 사용한다.

- `hard_blocker`
- `open_design_decision`
- `deployment_value`
- `recommendation`

각 분류의 의미는 다음과 같다.

#### hard_blocker

Workload 구조나 필수 연결 관계를 합리적으로 결정할 수 없게 만드는 누락이다.

#### open_design_decision

초기 설계는 가능하지만 설계 과정에서 선택해야 하는 항목이다.

#### deployment_value

배포 시 제공할 Registry, Tag, Domain, Secret 값 같은 입력이다.

#### recommendation

Repository 기반 설계 입력의 충분성과 별개인 운영 권장사항이다.

### 2.6 최종 판정 의미

판정은 다음 의미로 제한한다.

#### 설계 입력 충분

배포 대상, 실행 형태, 핵심 통신 방식과 주요 의존 관계를 식별할 수 있다.

`open_design_decision`, `deployment_value`, `recommendation`이 존재할 수 있다.

#### 추가 정보 필요

하나 이상의 `hard_blocker` 때문에 기본 Workload 구조나 필수 관계를 결정할 수 없다.

#### 분석 불가

Repository 접근 또는 근거 확보 실패로 분석 자체를 신뢰할 수 없다.

Validator는 판정과 `hard_blocker`의 논리적 일관성을 검사한다.

### 2.7 Repository 사실과 Kubernetes 해석

Summary는 다음 두 층을 분리한다.

#### Repository 사실

구성 요소를 다음 네 범주 중 하나로 분류한다.

1. 배포 대상 후보
2. 저장소에 정의된 런타임 의존성
3. 외부 런타임 의존성
4. 배포 대상 후보에서 제외한 항목

#### Kubernetes 해석

Repository 사실을 바꾸지 않고 다음을 별도로 기록한다.

- Deployment, Job, StatefulSet 또는 외부 관리 후보
- 필수 또는 선택 구성
- 운영 경계
- 열린 설계 결정

예를 들어 Compose에 PostgreSQL이 정의되어 있으면 Repository 사실은 `저장소에 정의된 런타임 의존성`이다. Kubernetes에서 관리형 DB를 사용할지는 별도의 해석과 설계 결정이다.

### 2.8 Provenance와 Validation Receipt

Summary 상단에는 다음 정보를 표시한다.

- Target source
- Resolved target revision
- 분석 subdirectory
- Skill ID와 version
- 가능한 경우 Skill source commit
- Report contract version
- Validation result

`Validation: passed`는 실제 본문 검증 성공 후에만 기록한다.

Git commit을 확인할 수 없는 Source archive는 archive SHA-256을 사용한다. Git 정보가 없는 Local directory는 값을 추정하지 않고 `unavailable`로 표시한다.

### 2.9 고정 Repository Fixture

`full-stack-fastapi-template`의 특정 commit을 기준으로 분석에 필요한 최소 파일을 보관한 오프라인 Fixture와 Golden Summary를 Release Gate에 포함한다.

Fixture는 다음을 검증한다.

- 사실 정확성
- 구성 요소 분류
- 열린 항목 분류
- 최종 판정
- 결론 우선 구조
- 구성 요소 표
- 근거 존재
- 최대 90줄의 Fixture별 가독성 예산
- Detailed mode 회귀 방지

### 2.10 계약 호환성

Summary v2는 계약 버전을 명시적으로 올린다.

- v2 Summary를 기본 생성 계약으로 전환한다.
- 기존 v1 Summary는 한시적으로 명시적 Legacy 검증만 허용한다.
- v1과 v2를 하나의 보고서에서 혼합하지 않는다.
- Detailed mode는 이번 결정에서 구조를 전면 변경하지 않는다.
- Legacy 제거 시점은 실제 사용 현황을 확인한 별도 결정으로 다룬다.

## 3. Information Budget

Summary의 분량은 단순 단어 수가 아니라 정보 반복을 제한하는 방식으로 관리한다.

### 필수 규칙

- 구성 요소 하나당 대표 행 하나
- Runtime dependency 하나당 대표 행 하나
- 열린 항목 하나당 대표 행 하나
- 동일 누락을 여러 섹션에서 반복하지 않음
- 세부 실행 필드는 Detailed로 이동
- 핵심 근거만 별도 목록으로 제공

### 고정 Fixture Release Budget

`full-stack-fastapi-template` Summary Golden은 Markdown 제목, 표 구분선, 공백을 포함하여 **90줄 이하**여야 한다.

90줄은 모든 Repository에 적용하는 절대 제한이 아니다. 대규모 Monorepo는 식별된 구성 요소 수에 따라 비례해서 늘어날 수 있다. 다만 구성 요소별 장문 카드로 되돌아가는 것은 허용하지 않는다.

## 4. Consequences

### 긍정적 결과

- 최종 판정과 핵심 구성을 빠르게 이해할 수 있다.
- Summary와 Detailed의 제품 목적이 명확히 구분된다.
- 불필요한 근거 반복이 줄어든다.
- 미확인 항목의 성격을 구분해 과도한 `추가 정보 필요` 판정을 줄인다.
- Repository 사실과 Kubernetes 권장 방향의 혼동을 줄인다.
- 분석 결과의 재현성과 신뢰성이 높아진다.
- 실제 Full-stack Fixture로 정확성과 가독성을 함께 회귀 검증할 수 있다.

### 비용과 단점

- Summary와 Detailed의 Validator 경로가 더 분리된다.
- 계약 버전과 Legacy 호환 정책을 관리해야 한다.
- Table 구조 검증과 판정 일관성 검증이 추가된다.
- Provenance Receipt 최종화 단계가 생긴다.
- Golden Fixture 유지 비용이 발생한다.
- v1 Summary를 소비하던 외부 자동화가 있다면 전환 작업이 필요하다.

## 5. Alternatives Considered

### 5.1 Prompt에 “짧게 작성하라”만 추가

기각한다.

현재 계약과 Validator가 Summary 구성 요소마다 상세 필드를 요구하므로 Prompt만 줄여도 검증을 통과하기 어렵다.

### 5.2 기존 필드의 `required`를 일부 `false`로 변경

기각한다.

Summary와 Detailed의 목적 차이를 계약에 명확히 표현하지 못하며, 모델마다 임의의 필드 조합이 생성될 가능성이 높다.

### 5.3 기존 Summary를 유지하고 `executive` 모드를 새로 추가

기각한다.

사용자가 기본으로 기대하는 Summary의 의미를 바로잡지 못하고 출력 모드만 늘린다. 기본 모드는 계속 장황한 상태로 남는다.

### 5.4 근거를 모두 별도 Appendix로 이동

부분 채택한다.

핵심 근거 목록은 별도 섹션으로 묶지만, 배포 표와 열린 항목의 각 행에도 최소 한 개의 직접 근거를 유지한다.

### 5.5 Summary에서도 구성 요소별 모든 필드를 유지하되 접기 UI를 사용

기각한다.

Markdown과 다양한 Agent 환경에서 접기 UI의 동작을 보장하기 어렵고, 정보 구조 자체의 중복을 해결하지 못한다.

### 5.6 LLM Judge로 가독성을 점수화

Release Gate로는 기각한다.

결과가 비결정적이며 폐쇄망과 로컬 모델 환경에서 재현성이 떨어진다. 구조, 줄 수, 필드 중복, 판정 일관성 같은 결정적 검증을 우선한다.

### 5.7 실제 upstream Repository를 CI에서 매번 Clone

기각한다.

네트워크 상태와 upstream 변경에 따라 결과가 달라진다. 고정된 최소 Fixture를 기본 Gate로 사용하고 실제 모델 Smoke Test는 별도로 수행한다.

## 6. Implementation Order

기존 긴급 P0 티켓을 먼저 완료한 뒤 다음 순서로 구현한다.

1. `SUM-001` 결론 우선 Summary v2
2. `SUM-002` 구성 요소 표와 근거 압축
3. `SUM-003` 열린 항목 분류와 판정 규칙
4. `SUM-004` Repository 사실과 Kubernetes 해석 분리
5. `SUM-005` Provenance와 Validation Receipt
6. `SUM-006` 고정 Fixture와 Release Gate

각 단계는 계약, 템플릿, Validator, 테스트가 함께 완료되어야 한다.

## 7. Rollout

1. Summary v2를 새 계약 버전으로 구현한다.
2. 내부 Fixture와 Quality Gate를 통과시킨다.
3. 실제 로컬 모델 환경에서 고정 Fixture Smoke Test를 수행한다.
4. Summary v2를 기본 생성 계약으로 전환한다.
5. v1 Summary는 한시적으로 명시적 Legacy 검증만 허용한다.
6. 실제 소비자가 없음을 확인한 뒤 Legacy 제거를 별도 결정한다.

## 8. Non-Goals

이번 결정은 다음을 포함하지 않는다.

- Kubernetes Manifest나 Helm Chart 생성
- Detailed mode 전체 재설계
- 애플리케이션 코드 또는 Dockerfile 수정
- Cloud 제품 추천
- Secret 값 생성 또는 저장
- 모든 문장의 어투를 강제하는 Style Linter
- 모든 Repository에서 무조건 90줄을 강제하는 제한
- 실시간 upstream 변경 추적
- 기존 P0 Ticket 범위의 재정의

## 9. Revisit Conditions

다음 조건이 발생하면 이 결정을 재검토한다.

- Summary를 기계적으로 소비하는 외부 도구가 v1 필드 전체를 요구함
- 대규모 Monorepo에서 한 행당 한 구성 요소 방식이 충분하지 않음
- Markdown 표가 주요 실행 환경에서 안정적으로 렌더링되지 않음
- Provenance Receipt 최종화가 보고서 생성 흐름을 불안정하게 만듦
- `hard_blocker` 판정 규칙이 반복적으로 오판을 유발함
- Summary v2가 다시 Detailed와 유사한 분량으로 증가함
- 고정 Fixture가 실제 분석 오류를 충분히 포착하지 못함

## 10. Decision Outcome

Summary mode는 더 이상 “모든 분석 필드를 짧게 나열하는 보고서”가 아니다.

Summary mode는 다음을 우선하는 의사결정 문서다.

1. 결론
2. 예상 배포 구성
3. 관계와 운영 경계
4. 실제 차단 항목과 열린 결정
5. 핵심 근거
6. 재현 가능한 분석 식별 정보

세부 실행 정보는 Detailed mode에서 제공한다.
