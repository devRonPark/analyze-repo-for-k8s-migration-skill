# TICKET-LIST-2026-07-30-008: Detailed 정확도 후속 작업

- 상태: 전체 계획. 다음 세션의 시작 큐다.
- 선행 작업: [TICKET-LIST-2026-07-30-007](TICKET-LIST-2026-07-30-007-detailed-contract-defects.md)
  (`DET-004`~`DET-009` 완료)
- 채점 기준: [JPetStore 6 Detailed golden set](../../../../tests/evaluation/jpetstore-6-detailed-golden.md)
- 최신 점수와 감점 근거: [Detailed scorecards](../../../../tests/evaluation/jpetstore-6-detailed-scorecard.md)
- 최신 실행 산출물: [2026-07-30 Detailed E2E 보고서](../../../../tests/evaluation/jpetstore-6-detailed-e2e-2026-07-30.md)

## 현재 위치

`DET-009` 실행: 125줄 8개 섹션 보고서, 2분 5초, 대상 Git 상태 불변,
validator 실패 7건, golden-set 72/100.

| 실행 | validator 실패 | 점수 |
| --- | ---: | ---: |
| 최초 (step 한도) | 보고서 없음 | 0 |
| `steps: 24` | 미측정 | 59 |
| `DET-008` | 7 | 63 |
| `DET-009` | 7 | 72 |

`DET-003` 수용 기준(대상별 90점)은 아직 충족하지 않았다.

## DET-010 — published port가 있으면 문서화된 context path를 보고서에 담는다

- 감점: 실행·네트워크 -4 (2회 연속)
- 결함: `README.md:57`의 `http://localhost:8080/jpetstore/`를 읽고도 보고서에 context
  path를 쓰지 않는다. agent 지시에는 "README를 읽어라"만 있어 읽기만 하고 필드로
  남기지 않는다.
- 작업: published port를 기록할 때 문서화된 context path를 같은 카드의 필드로
  요구한다. 문서에 없으면 `미확인`과 `검색(...)` 부재 근거를 요구한다.
- 수용 기준: JPetStore 보고서가 `/jpetstore/`를 근거와 함께 포함한다.
- 검증: 계약 테스트(포트가 있고 context path가 없으면 실패), Quality Gate,
  Detailed E2E 재실행.

## DET-011 — 읽은 범위를 넘는 줄 범위 재발을 막는다

- 감점: 실행·네트워크 -3
- 결함: `docker-compose.yaml:20-27`, `:17-27`을 26줄 파일에 인용했다. `DET-008`에서
  같은 규칙을 넣었지만 범위 인용에서 다시 재발했다.
- 작업: 범위 인용 대신 단일 줄 인용을 기본으로 하고, 범위는 `read` 출력에서 시작과
  끝 줄 번호를 모두 본 경우에만 허용한다는 규칙으로 바꾼다.
- 수용 기준: E2E 보고서에 파일 범위를 벗어난 인용이 없다.
- 검증: 계약 테스트, Quality Gate, E2E 재실행.

## DET-012 — 빌드·기동 시점 네트워크 의존성 edge를 요구한다

- 감점: 상태·의존성 -3
- 결함: 이미지가 소스에서 빌드되고 기동 시 Cargo가 서버를 내려받는데
  (`Dockerfile:20-21`, `pom.xml:282-292`) dependency matrix에 해당 edge가 없다.
  golden set은 HSQLDB, application server, Maven/Cargo 세 edge를 요구한다.
- 작업: 컨테이너가 소스에서 빌드하거나 기동 시 artifact를 받는 경우 build/start-time
  네트워크 의존성 edge를 필수로 만든다.
- 수용 기준: matrix와 text graph가 세 edge를 모두 포함하고 서로 일치한다.
- 검증: 계약 테스트, Quality Gate, E2E 재실행.

## DET-013 — web 서술자 호환성을 사실대로 적고 keyed 검증 항목으로 남긴다

- 감점: 설정·보안·호환성 -5 (2회 연속)
- 결함: 활성 서술자는 `web-app_3_0.xsd` version 3.0
  (`src/main/webapp/WEB-INF/web.xml:24-27`)인데 보고서는 "Jakarta Servlet 4.0 API",
  이전 실행에서는 "Java EE 6/Java EE 5"로 적었다. 주석 처리된 4.0 블록
  (`web.xml:19-23`)과 활성 선언을 구분하지 못한다. 호환성 검증도 keyed 차단 항목이
  아니라 산문으로만 남는다.
- 작업: 서술자의 namespace와 version을 파일에서 그대로 인용하고, 주석 블록을 활성
  선언으로 읽지 않으며, 선택된 서버의 EE 호환성 검증을 keyed 항목으로 요구한다.
- 수용 기준: 보고서가 `version 3.0`과 그 근거를 적고, 호환성 검증이 차단 항목 또는
  범위·결정을 가진 `미확인`으로 남는다.
- 검증: 계약 테스트, Quality Gate, E2E 재실행.

## DET-014 — `미확인` 슬롯의 반복 형식 누락을 줄인다

- 감점: 완결성 -6, 근거 규율 -3
- 결함: `범위:`·`결정:` 누락 3건, `검색(...)` 누락 1건, `근거: glob(src...)` 1건.
  모두 `DET-005`~`DET-007`에서 이미 명시한 규칙의 반복 위반이다.
- 작업: 템플릿의 `#### 최소 입력 누락` 자리에 슬롯당 한 줄 예시를 넣어 복사할 수
  있게 하고, 도구 이름을 근거로 쓰지 못한다는 규칙을 근거 형식 블록에 함께 둔다.
- 수용 기준: E2E 보고서의 모든 `미확인` 슬롯이 `범위:`, `결정:`, `검색(...)`을
  갖는다.
- 검증: 계약 테스트, Quality Gate, E2E 재실행.

## 미결정 사항

1. **지시 강화의 수익 감소.** `DET-005`~`DET-009`는 매번 겨냥한 결함을 없앴지만 다른
   형식 실수가 새로 나타났다(45 → 14 → 21 → 14 → 7 → 7). 다음 단계로 보고서 확정
   전에 validator 결과를 agent에게 돌려주고 스스로 고치게 하는 방법이 있다. 이는
   런타임 흐름을 바꾸는 결정이므로 구현 전에 ADR이 필요하다.
2. **Detailed 출력 예산 강제 여부.** 보고서는 계속 70줄 예산을 넘는다(125~139줄).
   validator에 줄 수 제한을 넣으면 완결성과 충돌할 수 있어 판단이 필요하다.
3. **MSA 대상 확보.** `DET-003`이 요구하는 5개 후보 food-delivery 대상이 이 머신에
   없다. golden set·scorecard·E2E 모두 미실시이므로 대상 저장소를 먼저 정해야 한다.

## 실행 절차

E2E는 `memory/opencode-e2e.md`의 절차를 따른다: 짧은 고정 run directory
(`/tmp/opencode-acceptance-<ticket>`), `HOME` 격리 설치, detached `tmux`,
최종 보고서는 세션 데이터베이스에서 원문으로 추출, 대상 Git 상태 전후 비교.
