# Component 계약과 도메인 규칙 복원 설계

## 상태

- 범위: Workflow 2단계(Repository Analysis Agent)가 생성하는 **구조화된 component
  계약**, 그 필드를 채우는 **Kubernetes 이관 도메인 규칙**, 규칙을 담는 **선언적 언어
  signal registry**, 그리고 이 셋을 판정하기 위한 **추가 계측**
- 제외: 3~7단계 상세 설계, public Tool 추가, provider별 business logic, OpenShell,
  Streamlit
- 구현 상태: 미구현, 설계 승인 대기
- 선행 완료: 관측 출처 계측(`3e0e014`, `migration_assistant/provenance.py`).
  다만 이것만으로는 부족하며 아래 「측정」 절이 남은 계측을 정의한다
- 열린 결정: 5단계 Manifest 생성 방식(결정론적 렌더러 vs LLM 생성 + Repair)은 보류.
  계약 필드는 Kubernetes object의 요구에서 역산하므로 어느 쪽에도 영향받지 않는다
- 개정: 2차 독립 검토와 자체 검토가 모두 REJECT였다. 두 검토가 겹쳐 지적한 네 가지와
  각각만 지적한 항목을 반영했다. 상세는 마지막 절에 남긴다

## 제품 목표 안에서의 위치

> 소스코드 Repository를 분석해 Kubernetes 이관에 필요한 정보를 추출하고, 근거가 충분한
> 항목을 바탕으로 실제 Kubernetes Manifest 초안을 자동 생성하는 온프레미스 개발자 도구

현재 저장소는 최종 제품이 아니라 **1단계 분석 엔진**이다.

```text
1. Target Resolution        코드      (구현됨)
2. Repository Analyzer      LLM       ← 본 문서
3. K8s Design Agent         LLM       (미구현, 계약의 소비자)
4. Decision Gate            코드      (미구현, 계약의 소비자)
5. Manifest Generator       미결정    (미구현, 계약의 소비자)
6. Manifest Validator       코드      (미구현)
7. Manifest Repair          LLM       (미구현)
```

`migration_assistant/schemas.py:30-33`의 `KubernetesMigrationPlan`은 필드가 없는 빈
경계이고, `migration_assistant/renderer.py:13-17`과
`migration_assistant/validator.py:10-14`는 Protocol 선언만 있다.

## 문제

### 지시문에 도메인이 없다

`migration_assistant/agent.py:57-90`의 지시문에서 Kubernetes 이관 도메인이라 부를 수
있는 것은 `migration_assistant/agent.py:69`의 "component boundary와 build/runtime
관계를 Repository 근거로 해석하고"가 거의 전부다. 나머지는 Tool 규약, Evidence 필드
채우는 법, 루프 제어, 안전 경계다.

### 측정이 이 진단을 뒷받침한다

Run 29(`docs/phase1-adk-experiment-log.md`)에서 계측을 켜고 3회 실행한 결과다.

| run | `read_file` | `read_file_lines` | `search_text` |
| --- | --- | --- | --- |
| 1 | 644 lines | 10 lines | 0 lines (호출 1회) |
| 2 | 767 lines | 0 lines (호출 0회) | 0 lines (호출 2회) |
| 3 | 0 lines | 4 lines | 0 lines (호출 0회) |

1. **관측이 whole-file read에 쏠려 있다.** 1,425줄 중 1,411줄이 `read_file`이다
2. **`search_text`가 3회 호출되어 hit 0건이다.** Tool 결함이 아니다. 같은 Repository에
   `java.version`, `<packaging>`, `port`, `jdbc`, `8080`을 직접 질의하면 각각 8, 1,
   32, 32, 4건이 나온다

지시문(`migration_assistant/agent.py:66`)은 "주장마다 먼저 search_text hit를 확보하라"고
요구하는데 **지시된 경로 자체가 성립하지 않는다.**

해석 한계: 세 run 모두 evidence 0건이라 이 수치는 모델이 **무엇을 열어봤는지**만 말한다.
n=3이다.

### 원인

`AGENTS.md:25-32`의 제약은 "언어별 고정 분석 흐름으로 Agent 판단을 대체하지 않는다.
일반 inventory와 안전한 parsing helper는 허용하지만, 낯선 Repository가 새 parser
없이는 분석 불가가 되는 구조는 금지한다"이다. 금지 대상은 **막다른 길**이다.

그러나 ADK 이식 과정에서 이 제약이 `migration_assistant/agent.py:89`의 "Repository
이름, 언어, 고정 파일 순서를 분석 규칙으로 사용하지 마세요"로 지시문에까지 적용되면서
도메인 안내가 함께 제거됐다. 복원 대상 규칙은 `origin/main:SKILL.md`,
`origin/main:references/workflow.md`,
`origin/main:references/language-discovery-rules.md`에 있다.

## 설계 원칙: 무엇이 2단계에 속하는가

두 검토가 함께 지적한 결함은 초안이 **저장소 사실과 운영 결정을 섞었다**는 것이다.
CPU/memory request와 limit, probe 지연, replica 수는 소스 저장소에 없다. 이를
`FieldValue`로 두면 항상 `unresolved`가 되고, 없는 것을 못 찾았다고 증명하는 절차만
남는다. 더 나쁘게는 근거 없는 값 authoring을 허용할 수 있다.

경계를 명시적으로 나눈다.

| 성격 | 항목 | 소속 |
| --- | --- | --- |
| 저장소 사실 | 기동 명령, 노출 포트, 이미지 참조와 그 생산 적합성, PID 1 신호 전달, 쓰기 경로, 내장 저장소, 환경변수 이름, 코드에 존재하는 health endpoint, 실행 사용자 요구 | 2단계 계약 |
| 운영 결정 | resources 값, probe 지연·주기, replica 수, namespace, registry 주소, 외부 노출 방식 | **4단계 Decision Gate** |

**2단계는 사실만 담는다.** 저장소에 resource 설정이 실제로 존재하면(예: Compose의
`mem_limit`) 그것은 사실이므로 기록하지만, 운영용 적정값을 제안하지 않는다.

## 설계 1: 선언적 언어 Signal Registry

### 형태

```text
LANGUAGE_SIGNALS[ecosystem]
  detect        이 생태계로 판정하는 파일
  manifests     우선 관측할 manifest/build 파일
  descriptors   web descriptor, application context 등
  extensions    소스 확장자
  patterns      high-signal 검색 패턴
  commands      슬롯별 알려진 명령 형태
```

`patterns`는 Run 29의 `search_text` hit 0건을 직접 겨냥한다.

### 명령 matcher 계약

독립 검토가 matcher를 "구현 가능한 계약으로는 부족하다"고 지적했다. 다음으로 확정한다.

- **형태**: 각 항목은 `(정규식, 슬롯)` 쌍이다. 정확 문자열이 아니라 정규식이며,
  registry 안에서만 컴파일한다
- **정규화**: 비교 전에 앞뒤 공백 제거, 연속 공백 축약, `sh -c "..."`와 `bash -c '...'`
  래퍼 한 겹 제거, `./mvnw`/`mvnw`/`mvn`과 `./gradlew`/`gradlew`/`gradle` 같은 wrapper
  별칭 통일을 적용한다. 그 이상은 하지 않는다
- **다중 매칭**: 한 명령이 여러 슬롯 정규식에 걸리면 **오배치로 판정하지 않는다.**
  모호한 명령을 단정하지 않기 위한 fail-open이다
- **미지 명령**: 어느 정규식에도 걸리지 않으면 판정하지 않고 "미지"로 집계한다
- **기록 위치**: 오배치는 Evidence도 Finding도 아니다. `validate_analysis` 응답의
  경고 목록과 측정 지표에만 기록하며 candidate를 거부하지 않는다. registry가 도메인
  값을 authoring하지 않기 위한 경계다

### 불변식

"언어 분기 금지"를 대체하는 다섯 가지이며 그대로 검증 기준이 된다.

1. registry에 없는 생태계도 generic 경로로 완주하고 부족한 값은 `미확인`으로 남는다
2. registry는 계약 값을 채우지 않는다. 모든 positive 값은 `evidence_ids`를 갖는다
3. 엔트리를 삭제해도 crash 없이 generic 경로로 떨어진다
4. 참조 지점이 한 모듈에 모인다
5. 탐지는 이름 추측이 아니라 실제 파일 관측 근거에 기반한다

`AGENTS.md:25-32`는 이 불변식을 반영해 **코드 변경 전에** 개정한다.

## 설계 2: Component 계약

### 근거 표현의 일관성

두 검토가 함께 지적한 대로, 초안은 "모든 필드는 `FieldValue`"라고 선언하고 `ports[]`,
`config[]`, `verdict`, `blockers[]`를 예외로 두었다. 예외를 없앤다.

```text
FieldValue
  status          confirmed | inferred | unresolved | conflicting
  value           확정 값. unresolved면 null
  evidence_ids    positive status일 때 필수
  absence_scope   unresolved일 때 필수
  absence_pattern unresolved일 때 필수
  result          unresolved일 때 필수

PortEntry
  name            FieldValue
  container_port  FieldValue
  protocol        FieldValue
  purpose         FieldValue   http | management | metrics | unknown

ConfigEntry
  key             FieldValue
  kind            FieldValue   config | secret
                  분류는 관측이 아니라 판정이므로 반드시 근거를 갖는다

Blocker
  id              고유 식별자
  category        FieldValue
  impact_scope    FieldValue   전체 | 특정 배포 대상 | production 경로
  reason          FieldValue   왜 막는가
  evidence_ids    최소 하나

verdict           FieldValue   설계 입력 충분 | 추가 정보 필요 | 분석 불가
```

`config[].kind`가 `FieldValue`인 이유는 ConfigMap과 Secret의 구분이 보안 판정이기
때문이다. 근거 없이 결정되면 안 된다.

### 필드와 필수성 매트릭스

독립 검토가 "top-level schema, component schema, complete 규칙 사이의 필수성 매트릭스가
없어 구현자가 서로 다른 계약을 만들 수 있다"고 지적했다. 명시한다.

| 필드 | wire schema | `complete` 요구 | 적용 대상 |
| --- | --- | --- | --- |
| `components` | 선택 | 필수, 최소 1개의 `배포 대상 후보` | — |
| `name` | 필수 | 필수 | 모든 component |
| `classification` | 필수 | 필수 | 모든 component |
| `commands.production_startup` | 선택 | **필수** | 배포 대상 후보 |
| `ports[]` | 선택 | **필수** | 배포 대상 후보 |
| `container_image.reference` | 선택 | **필수** | 배포 대상 후보 |
| `commands.{dependency_install, application_build, image_build}` | 선택 | 선택 | 배포 대상 후보 |
| `runtime` | 선택 | 선택 | 모든 component |
| `container_image.production_fit` | 선택 | 선택 | 배포 대상 후보 |
| `lifecycle.signal_propagation` | 선택 | 선택 | 배포 대상 후보 |
| `state.{writable_paths, embedded_store}` | 선택 | 선택 | 배포 대상 후보 |
| `config[]` | 선택 | 선택 | 배포 대상 후보 |
| `health.endpoints` | 선택 | 선택 | 배포 대상 후보 |
| `security.run_as_non_root` | 선택 | 선택 | 배포 대상 후보 |
| `verdict` | 선택 | 필수 | — |
| `blockers[]` | 선택 | 선택(있으면 검증) | — |

`partial`과 `failed`에서는 `components`, `verdict`, `blockers` 모두 생략 가능하다.
`배포 대상 후보`가 아닌 component는 `name`과 `classification`만 요구한다.

**"선택"은 없어도 candidate가 거부되지 않는다는 뜻이다.** 있으면 규칙대로 검증한다.

### 필드 수 증가의 위험과 완화

독립 검토가 "확장된 계약이 관측된 구조화 payload 실패를 악화시킬 가능성이 크다"고
지적했다. 이는 실재하는 위험이고 문서가 인정해야 한다. Run 26~29의 지배적 실패는
모델이 구조화 payload를 정확히 채우지 못하는 것이었다.

완화책은 다음과 같다.

1. **`complete`가 요구하는 필드는 다섯 개로 고정한다** — `components` 존재,
   `name`, `classification`, 그리고 배포 후보별 세 항목. 나머지는 전부 선택이다
2. **구현을 단계로 나눈다.** 계약 최소본(필수 다섯)을 먼저 넣고 성공률을 측정한 뒤에만
   선택 필드를 확장한다. 아래 「구현 분할」의 4단계는 3단계 측정 결과를 채택 조건으로 갖는다
3. **필수 필드 수와 성공률을 분리 측정한다.** 측정 항목 7번이 이를 담당한다
4. **누락 시 수정 규칙**: 선택 필드가 빠진 candidate는 거부하지 않는다. 오류로
   되돌리지 않으므로 recovery 예산을 소모하지 않는다

### DevOps 근거

`ports`가 복수인 것과 `production_fit`, `signal_propagation`, `state`, `config[].kind`,
`security`는 실무 실패에서 역산했다. 데모 대상 `jpetstore-6`이 사례다.

- Dockerfile이 `CMD ./mvnw cargo:run -P tomcat90`이다. shell form이라 PID 1이 `sh`가
  되고 SIGTERM이 JVM에 전달되지 않는다 → `lifecycle.signal_propagation`
- Dockerfile은 `FROM openjdk:25`인데 `pom.xml`은 `<java.version>17</java.version>`이다.
  `origin/main` 규칙이 이를 `상충됨`으로 규정한다 → `container_image.production_fit`
- 내장 HSQLDB는 로컬에 쓴다. PVC를 함부로 만들지 않는 것은 옳지만 쓰기 사실은 기록돼야
  replica 안전성을 판정할 수 있다 → `state`
- `DATABASE_URL`은 비밀번호를 포함한 연결 문자열이다 → `config[].kind`
- PSA restricted 클러스터에서는 securityContext 없는 Pod가 admit되지 않는다 → `security`

probe 지연과 resources 값은 여기 없다. 4단계 몫이다.

### verdict와 blockers

이관 분석의 산출물은 필드 목록이 아니라 "이 앱은 이대로 못 올린다, 막는 것은
이것들이다"이다. `origin/main:SKILL.md`의 판정 체계를 복원한다.

- `verdict`는 모델이 정한다. 코드가 계산하지 않는다
- `verdict`가 `설계 입력 충분`이려면 `blockers[]`가 비어 있고 `conflicting` 필드가
  없어야 한다. 이 규칙만 코드가 검증한다
- 각 `Blocker`는 `evidence_ids`를 최소 하나 가져야 한다

## 설계 3: 도메인 규칙 복원

규칙은 지시문 텍스트와 registry 데이터로만 존재하며 강제 routing이 아니라 **우선순위
힌트**다. registry가 제안한 순서를 따르지 않아도 진행할 수 있고, 미등록 언어는 generic
경로로 완주한다.

복원 대상:

1. **high-signal 탐색 순서**(`origin/main:references/workflow.md`): manifest/build →
   wrapper → Dockerfile → Compose → 환경·설정 → web descriptor → application context →
   entrypoint → DB/broker. README, CI, 테스트, 광범위 소스는 1차 발견에 근거가 더
   필요할 때만
2. **실행 단계 분리**: `npm install`은 빌드가 아니고, `npm run build`는 기동이 아니며,
   `docker build`는 애플리케이션 빌드가 아니고, dev server는 프로덕션 기동이 아니다
3. **분류 버킷 4개**: 마이그레이션·초기화 명령은 제외 전에 일회성 Job 후보로 평가
4. **언어별 신호**: registry의 `manifests`, `descriptors`, `patterns`
5. **도메인 함정**: Dockerfile 부재는 finding / 내장 startup 데이터로 PV·StatefulSet을
   추론하지 않음 / 빌드 대상과 base image 버전 불일치는 `상충됨` / 파일 이름으로 구현을
   추론하지 않음 / lockfile은 조건부 근거 / 저장소 실행 정의와 운영 환경 근거를 섞지
   않음 / credential 형태 seed는 위치와 위험만 기록

### 슬롯 분리의 실제 효과

슬롯 분리 자체는 **기록 위치 분리**에 그친다. registry `commands`가 그중 **알려진
형태에 한해** 검출 가능하게 한다. 미지 명령과 다중 매칭은 검출하지 않으며, 검출 결과는
candidate를 거부하지 않고 경고와 지표로만 남는다.

### 지시문 예산

현재 지시문의 상당 부분이 `migration_assistant/adk_tools.py:104`의 `TOOL_DESCRIPTIONS`와
중복된다. 중복을 제거하고 예산을 도메인에 쓴다. 구획은 역할·안전 / 이관 도메인 / 근거
규칙 / 계약 / 종료 조건으로 재구성한다. 길이 증가가 준수율을 떨어뜨릴 수 있으며 이는
측정 항목 6번이 담당한다.

## 구현 분할

두 검토가 함께 "항목별 롤백 조건이 단일 변경 단위와 맞지 않는다"고 지적했다. 독립
검토가 제안한 분할을 채택한다. **각 단계는 독립적으로 되돌릴 수 있어야 한다.**

| 단계 | 내용 | 채택 조건 |
| --- | --- | --- |
| 0 | `AGENTS.md:25-32` 제약 개정 | 문서 승인 |
| 1 | 계약 타입·검증·fixture (필수 다섯 필드만) | 결정론적 테스트 GREEN |
| 2 | registry와 generic fallback | 불변식 5개 테스트 GREEN |
| 3 | Agent 지시문 재구성과 슬롯 검증 | 측정 5·6번이 기준선 대비 개선 |
| 4 | 선택 필드 확장(verdict, blockers, 사실 필드) | **3단계 측정에서 `complete` 도달률이 하락하지 않았을 때만** |
| 5 | report/redaction 출력 | redaction 테스트 GREEN |
| 6 | 측정 지표와 harness 확장 | 1단계 착수 전에 필요한 부분은 선행 |
| 7 | 10회 이상 live 재측정과 채택 판단 | — |

6단계 중 측정 항목 1·4·5번에 필요한 계측은 **1단계보다 먼저** 들어가야 한다. 그렇지
않으면 1단계의 효과를 잴 수 없다.

## 변경 지점

독립 검토가 초안의 표를 "전수가 아니다"라고 지적했다. 보완한다.

| 경로 | 변경 |
| --- | --- |
| `migration_assistant/language_signals.py` | 신규. registry 데이터, 조회 helper, 명령 matcher |
| `migration_assistant/analysis.py:119-128` | `AnalysisResult`에 `components`, `verdict`, `blockers` 선택 필드 추가 |
| `migration_assistant/analysis.py:135-182` | `complete` 판정 규칙, `evidence_ids` 실재성, verdict 규칙 |
| `migration_assistant/analysis.py:214-235` | `render_report`에 component/verdict/blocker 출력과 redaction |
| `migration_assistant/adk_tools.py:94-101` | `ValidateAnalysisArgs`에 선택 인자와 중첩 입력 모델 |
| `migration_assistant/adk_tools.py:104` | `TOOL_DESCRIPTIONS`의 `validate_analysis` 설명 갱신 |
| `migration_assistant/adk_tools.py:409` | `_call`에 슬롯 오배치·search hit 계측 추가 |
| `migration_assistant/adk_tools.py:517` | `validate_analysis` 인자와 candidate 구성 |
| `migration_assistant/repository_tools.py:816-936` | component 필드 검증과 경고 반환 |
| `migration_assistant/adk_runner.py:219-233` | post-hoc fallback candidate |
| `migration_assistant/adk_runner.py:254-262` | 실패 fallback candidate |
| `migration_assistant/agent.py:57-90` | 지시문 재구성 |
| `migration_assistant/provenance.py` | 슬롯 오배치와 search hit 지표 추가 |
| `devtools/run_phase1_live_acceptance.py` | component 필드 채움률, 슬롯 오배치, search hit 0건 비율 집계 |
| `tests/test_phase1_adk_contract.py:854-870` | wire required 집합 assertion |
| `tests/test_phase1_adk_contract.py:935-946` | complete/partial fixture |
| `tests/test_analysis_vertical_slice.py:32-55` | `AnalysisResult` 계약 테스트 |
| `tests/test_adk_agent.py:106-136` | Agent 계약 테스트 |
| `AGENTS.md:25-32` | registry 불변식으로 제약 개정 (코드보다 먼저) |

**T2 wire contract가 바뀐다.** T1 Evidence 계약과 T3·T4 recovery 계층은 유지된다.
`components`, `verdict`, `blockers`를 선택 인자로 두므로 기존 fixture 다수는 살아남고,
`complete` 판정에서만 요구한다.

## 보존 경계

- public Agent Tool은 정확히 여덟 개(`migration_assistant/tool_contract.py:6-14`)
- 대상 Repository는 read-only이며 artifact는 output directory에만
- provider나 model 이름별 분기를 추가하지 않는다
- **코드는 component 도메인 값을 생성하지 않는다.** `status`, `claim`, 근거 연결,
  부재 근거, `verdict`, blocker 사유는 모델이 정한다. registry는 순서와 검출 힌트만
  제공하며 값을 쓰지 않는다
- Secret 비노출

경계 문구 정정: "코드가 status를 authoring하지 않는다"는 현재 코드와 상충한다.
`migration_assistant/adk_runner.py:219-233`은 terminal Tool 없이 제출된 `complete`를
`partial`로 바꾸고, `migration_assistant/analysis.py:262-282`는 planner fallback의
status를 코드가 정한다. 이는 의도된 안전장치이므로 유지하고, 경계는 **component 도메인
값**으로 한정한다.

### Secret 비노출 테스트 계획

독립 검토가 "선언만으로는 보안 경계를 검증할 수 없다"고 지적했다. 다음을 결정론적
테스트로 고정한다.

1. `FieldValue.value`에 secret 형태 문자열이 들어오면 저장·응답·artifact 어디에도
   원문이 나타나지 않는다
2. `config[].key`와 `kind`, 그리고 `value`에 동일하게 적용된다
3. `ports[]`의 모든 `FieldValue`에 적용된다
4. `blockers[].reason`에 적용된다
5. component를 포함한 `analysis-report.md`와 `analysis-result.json` 전체 출력에
   적용된다
6. `validate_analysis` 오류 응답과 슬롯 오배치 경고에 적용된다

## complete 판정 규칙

- `배포 대상 후보`가 하나도 없으면 `complete`가 아니다
- 각 `배포 대상 후보`는 `commands.production_startup`, `ports`,
  `container_image.reference`가 **모두 존재**해야 한다. 각각은 positive이거나 명시적
  `unresolved`여야 하며, 필드 자체가 누락되면 `complete`가 아니다
- 세 항목이 **전부 `unresolved`이면 `complete`가 아니다.** 최소 하나는 positive여야 한다
- `conflicting`은 "근거 있음"으로 인정한다. 다만 `conflicting`이 하나라도 있으면
  `verdict`는 `설계 입력 충분`이 될 수 없다
- Dockerfile이 없어 `container_image.reference`가 `unresolved`여도 나머지가 positive면
  `complete`가 가능하다(`origin/main:SKILL.md`의 "Dockerfile 부재는 분석 실패가
  아니다"와 일치). 이 경우 blocker로 기록한다
- `verdict`가 없으면 `complete`가 아니다

## 측정

### 이미 계산 가능한 것

`3e0e014`의 계측이 제공한다.

- Evidence별 관측 Tool 귀속 (`migration_assistant/provenance.py`)
- 미관측 인용 수 (`devtools/run_phase1_live_acceptance.py`)
- Tool별 관측 line 수

### 추가로 필요한 계측

독립 검토가 "선언한 측정 항목 1·4·5를 현재 계측으로 계산할 수 없다"고 지적했다. 사실이다.
다음을 **구현 1단계보다 먼저** 추가한다.

- **필드 채움률**: harness가 `components`를 읽어 필드별 상태를 집계한다. 현재
  `devtools/run_phase1_live_acceptance.py`에는 component 집계가 없다
- **슬롯 오배치**: registry matcher 판정 결과를 run 단위로 기록한다. 현재
  `migration_assistant/adk_tools.py:409`의 계측은 line 좌표만 남긴다
- **검색 유효성**: `search_text` 호출별 hit 수를 보존한다. 현재 `tool_calls`에는 호출
  이름만 있어 호출별 hit 여부를 구분할 수 없다

### 측정 항목

1. 필드 채움률 — 필수 다섯 필드 기준 positive / unresolved / 누락 비율
2. 필드별 근거 출처 — 좁은 관측 대 whole-file read 비율
3. 미관측 인용 수
4. 슬롯 오배치 — 검출 수와 미지 명령 수를 함께 기록
5. 검색 유효성 — `search_text` 호출 중 hit 0건 비율
6. 지시문 준수 — 첫 Tool이 `inspect_target`인지
7. **필수 필드 수 대 성공률** — 구현 1단계와 4단계 사이의 `complete` 도달률 변화

### 기준선

- **잠정 기준선**: Run 29. n=3이며 evidence가 0건이므로 항목 1·2·3은 값이 없다.
  유효한 것은 항목 5(hit 0건 비율 3/3)뿐이다
- **최종 기준선**: 추가 계측을 넣은 뒤 변경 전 코드로 10회 이상 실행해 항목 1~7의 값을
  확보한다. 이것이 채택·롤백 판단의 기준이다

### 롤백 조건 (사전 등록)

`complete` 도달률은 잠정 기준선이 0/3이므로 "기준선 이하" 조건이 발동할 수 없다.
최종 기준선 확보 후 다음을 적용한다.

| 단계 | 롤백 조건 |
| --- | --- |
| 2 (registry) | 항목 5의 hit 0건 비율이 최종 기준선보다 개선되지 않음 |
| 3 (지시문) | 항목 6의 준수율이 최종 기준선 대비 하락 |
| 4 (선택 필드 확장) | 항목 7에서 `complete` 도달률이 3단계 측정값 대비 하락 |
| 1 (계약 최소본) | 항목 7에서 `complete` 도달률이 최종 기준선 대비 하락 |

각 비교는 10회 이상 표본의 점추정으로 한다. 3-of-3 gate는 채택 판정 이후에만 실행한다.

## 검증 기준

1. `배포 대상 후보`가 없는 candidate는 `complete`가 아니다
2. 세 필수 항목이 전부 `unresolved`인 `배포 대상 후보`는 `complete`가 아니고, 하나라도
   positive면 가능하다
3. `container_image.reference`만 `unresolved`이고 나머지가 positive면 `complete`가
   가능하며 blocker가 기록된다
4. `conflicting`이 있으면 `verdict`가 `설계 입력 충분`이 될 수 없다
5. 선택 필드가 없는 candidate는 거부되지 않는다
6. component 필드의 `evidence_ids`가 실재하지 않는 Evidence id를 가리키면 거부된다
7. `unresolved` 필드에 `absence_scope`, `absence_pattern`, `result`가 없으면 거부된다
8. `ports[]`, `config[]`, `blockers[]`의 모든 값이 `FieldValue` 규칙을 따른다
9. registry에 없는 생태계의 Repository도 완주해 결과를 낸다
10. registry 엔트리를 삭제해도 crash 없이 generic 경로로 진행한다
11. registry는 어떤 계약 필드 값도 직접 채우지 않는다
12. registry `commands`에 있는 형태가 잘못된 슬롯에 들어오면 경고로 검출되고,
    미지 명령과 다중 매칭은 검출되지 않으며 그 사실이 지표에 기록된다
13. 슬롯 오배치 경고가 candidate를 거부하지 않는다
14. 「Secret 비노출 테스트 계획」의 여섯 항목이 모두 통과한다
15. `PUBLIC_AGENT_TOOL_NAMES`가 변하지 않는다
16. 대상 Repository가 변경되지 않는다
17. 위를 결정론적 테스트로 먼저 고정한 뒤 「측정」 절차를 수행한다

## 다른 문서와의 관계

- `docs/superpowers/specs/2026-08-02-observation-ledger-grounding-design.md`는 REJECT
  상태이고 Run 29 측정이 그 판단을 뒷받침한다. 좁은 관측에만 전사 면제를 주려 했는데
  실제 관측의 99%가 whole-file read다. **본 설계 이후로 미룬다.** 관측 분포가 좁은
  관측 쪽으로 이동한 뒤 재평가한다
- `docs/superpowers/plans/2026-08-02-agent-tool-protocol-reliability.md`의 T1, T3, T4는
  유지되고 T2의 `validate_analysis` declaration은 변경된다
- `AGENTS.md`와 `CONTEXT.md`는 제품 목표 재정의, 7단계 workflow, registry 불변식,
  OpenShell 범위를 반영해 갱신한다. registry 불변식 개정은 구현 **선행 조건**이고
  나머지는 별개 작업이다

## 필요성 판단

계약이 없으면 2단계의 완료 조건이 정의되지 않고 3단계 이후는 소비할 구조가 없다.
도메인 규칙이 없으면 Agent는 무엇을 찾아야 하는지 모른 채 탐색한다. Run 29가 그 결과를
직접 보여준다. 검색은 0건을 반환하고 관측은 whole-file read로 흐른다.

이 작업으로 live 신뢰성이 개선된다는 보장은 없다. 필드 확장은 오히려 실패를 늘릴 수
있으며, 그래서 구현을 단계로 나누고 4단계 착수를 3단계 측정 결과에 걸었다.

## 개정 이력

2차 독립 검토(REJECT)와 자체 검토(승인 불가)를 합쳐 반영했다. 두 검토가 함께 지적한
항목을 먼저 적는다.

**양쪽이 함께 지적**

- **저장소 사실과 운영 결정 혼동**: `resources` 값, probe 지연, replica 수를 계약에서
  제거하고 4단계 Decision Gate로 옮겼다. 「설계 원칙」 절을 신설해 경계를 표로 고정했다
- **필수/선택 미구분**: 필수성 매트릭스를 표로 추가했다. `complete`가 요구하는 것은
  다섯 개이고 나머지는 선택임을 명시했다
- **`FieldValue` 규칙 불일치**: `ports[]`, `config[]`, `blockers[]`, `verdict`를 모두
  `FieldValue` 규칙에 편입했다. `config[].kind`는 보안 판정이므로 근거를 요구한다
- **항목별 롤백과 단일 변경 단위 불일치**: 구현을 0~7단계로 분할하고 각 단계에 채택
  조건과 롤백 조건을 붙였다

**독립 검토만 지적**

- **C3 측정 항목 1·4·5 계산 불가**: 사실이다. 필드 채움률, 슬롯 오배치, search hit
  수를 추가 계측으로 정의하고 구현 1단계보다 먼저 넣도록 했다. 이전 판이 계측을
  "해소됨"으로 적은 것은 과장이었다
- **I2 필드 증가가 실패를 악화**: 위험을 명시하고 완화책 네 가지를 적었다. 4단계 착수를
  3단계 측정 결과에 걸었고 측정 항목 7번을 신설했다
- **I3 변경 지점 미완**: `tests/test_analysis_vertical_slice.py:32-55`,
  `tests/test_adk_agent.py:106-136` 등을 추가했다
- **I6 matcher 계약 부족**: 정규식 형태, 정규화 범위, 다중 매칭 fail-open, 미지 명령
  처리, 기록 위치를 확정했다
- **I7 redaction 테스트 부재**: 「Secret 비노출 테스트 계획」 여섯 항목을 신설했다
- **M1 지시문 line 인용 오류**: `agent.py:62`→`:66`, `:85`→`:89`로 정정했다. 원인은
  계측 커밋(`3e0e014`)이 지시문 위에 4줄을 추가해 인용이 밀린 것이다. 작성 시점에는
  맞았으나 갱신하지 않았다

**자체 검토만 지적**

- **기준선 자기모순**: Run 29를 잠정 기준선으로, 10회 재측정을 최종 기준선으로 구분했다.
  `complete` 도달률 롤백 조건은 잠정 기준선이 0/3이라 발동할 수 없으므로 최종 기준선
  확보 후 적용하도록 바꿨다
