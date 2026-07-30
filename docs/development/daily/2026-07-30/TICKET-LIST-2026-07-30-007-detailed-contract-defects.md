# TICKET-LIST-2026-07-30-007: Detailed E2E에서 드러난 계약 결함

- 상태: `DET-004` 활성. `DET-005`~`DET-007`은 계획.
- 결정: [ADR-2026-07-30-010](ADR-2026-07-30-010-detailed-verdict-consistency.md),
  [ADR-2026-07-30-008](ADR-2026-07-30-008-detailed-evidence-budget.md)
- 평가 기준: [JPetStore 6 Detailed golden set](../../../../tests/evaluation/jpetstore-6-detailed-golden.md)

## E2E 실행 기록

- 절차: detached `tmux`(소켓 `k8se2e`), 격리 HOME
  `/tmp/opencode-acceptance-interactive-*`, `scripts/install-opencode.sh`로
  설치한 배포본, provider `local-sglang/Qwen/Qwen3.6-35B-A3B-FP8`.
- 요청: TTY에서 `/analyze-repo-for-kubernetes Detailed`.
- 대상: `/home/daolts/jpetstore-6` @ `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`.
- 결과: 8개 섹션 144줄 최종 Markdown 보고서를 2분 14초에 완성. 대상 Git 상태는
  실행 전후 모두 `## master...origin/master`로 동일.
- 검증: `python3 scripts/validate_report.py <report> --mode detailed --repo-root
  /home/daolts/jpetstore-6` → 실패 45건.

`DET-001`의 완성 우선 계약은 목표를 달성했다. step 한도 소진 없이 보고서가
완결되었고, 대상 `read`는 10회로 12회 예산 안에 있었다. `SEC-001`의 신뢰 도구
(`read`, `glob`, `git_metadata`)가 로드되어 사용되었고 `grep`, `list`, `bash`
호출은 없었으며 자격증명 값 누출도 없었다. 남은 문제는 출력 형식 계약이다.

## DET-004 — 판정 검증을 일치성으로 바꾼다

- 상태: 활성
- 결함: 템플릿은 `### 핵심 요약`과 8절에서 `- 판정:`을 요구하는데 validator는
  판정이 하나가 아니면 실패시킨다. 템플릿을 따른 보고서가 항상 실패한다.
- 근거: `assets/migration-assessment-template.md:29`,
  `assets/migration-assessment-template.md:134`,
  `scripts/validate_report.py`의 `최종 판정은 정확히 하나여야 합니다`,
  `tests/fixtures/reports/valid-detailed.md`에 `### 핵심 요약` 없음.

### 작업

- validator가 판정 개수 대신 값 일치를 검사한다: 판정이 최소 하나 존재하고 모든
  판정 값이 동일해야 한다.
- 반복된 동일 판정 때문에 `추가 정보 필요` keyed blocker 검사가 건너뛰어지지
  않게 한다.
- `valid-detailed.md` fixture에 `### 핵심 요약`을 추가해 실제 템플릿 형태를
  대표하게 한다.
- Summary 판정 동작은 바꾸지 않는다.

### 수용 기준과 검증

- `핵심 요약`과 8절에 같은 판정을 적은 Detailed 보고서가 통과한다.
- 두 판정이 다른 보고서는 실패하고, 그 이유를 판정 불일치로 보고한다.
- 판정이 없는 보고서는 계속 실패한다.
- `추가 정보 필요` 보고서의 keyed blocker 요구는 판정이 반복돼도 유지된다.
- 계약 테스트를 먼저 추가한 뒤 `python3 scripts/run_quality_gate.py`를 실행한다.

### 결과

판정 반복은 `readiness_blocker_errors`의 `verdicts != ["추가 정보 필요"]` 비교도
무력화하고 있었다. 일치성 검증으로 바꾼 뒤 이 검사가 다시 동작하면서 E2E 보고서의
keyed blocker 형식 위반이 새로 드러났다. 이 형식 위반은 `DET-005`에서 처리한다.

## DET-005 — 구성 요소 카드 속성 라인 형식을 지시로 고정한다

- 상태: 완료
- 결함: 실행 정보, 설정과 상태, 최소 설계 입력 속성 약 40줄이
  `- 키: 값 — 상태: <상태> / 근거: <근거>` 형식을 지키지 않았다. 값 뒤에 설명을
  붙이거나 `범위:`, `결정:` 뒤로 `상태:`를 밀어 썼다. 설계 차단 항목도
  `- 차단 항목: <내용> — 범주: <범주> / 영향 범위: ...` 대신 자유 서술로 적어
  `범주:` 키와 `차단 항목:` 키가 없었다.
- 작업: agent 지시와 Detailed 템플릿에 형식 예시를 고정하고, `범위:`와 `결정:`이
  들어가는 `최소 입력 누락` 항목의 필드 순서를 한 줄 예시로 못 박는다. 형식
  위반을 잡는 계약 테스트를 추가한다.
- 검증: 계약 테스트, Quality Gate, Detailed E2E 재실행.

### 구현

agent 지시에 세 가지 줄 형식(`- 키: 값 — 상태: ... / 근거: ...`,
`최소 입력 누락`의 `범위:`·`결정:` 위치, `- 차단 항목: ... — 범주: ...`)을 코드
블록으로 고정했다. `—` 뒤에는 `상태:`와 `근거:`만 오고 설명은 값 안에 넣으며,
`근거:`에 맨 `없음`을 쓰지 않는다.

validator는 판정과 무관하게 `### 설계 차단 항목`의 모든 bullet이 keyed 형식을
지키는지 검사한다. 이전에는 `추가 정보 필요` 판정에서만 검사했으므로 다른 판정의
자유 서술 차단 항목이 조용히 통과했다.

### 검증 결과

- 계약 테스트 4건 추가, `python3 scripts/run_quality_gate.py` 통과(unit test
  126건).
- Detailed E2E 재실행: `/tmp/opencode-acceptance-det5`, 대상
  `/home/daolts/jpetstore-6` @ `e1dd9a31d1cef68793cd0933ae06898e6fcfa807`,
  117줄 보고서를 1분 56초에 완성. 대상 Git 상태는 전후 모두
  `## master...origin/master`.
- validator 실패 45건 → 14건. 속성 라인 형식 위반은 약 40건에서 1건
  (`- 경로: . (루트)`)으로 줄었고, `설계 차단 항목` keyed 형식 위반은 0건이다.
- 남은 14건은 `미확인` 근거의 `검색(...)` 누락 5건, `상충됨` 근거의 양쪽 source
  파싱 실패 3건(`Dockerfile:21의 ...`처럼 참조 뒤에 설명이 붙음), 근거에
  `:line`이 없거나 설명이 붙은 3건, 저장소 상대 경로가 아닌 인용 2건이다.
  각각 `DET-006`과 `DET-007`에서 처리한다.

첫 재실행은 `mktemp` 무작위 경로 때문에 모델이 Skill 경로를 오타로 옮겨 적어 모든
reference read가 신뢰 경로 검사에서 거부되었다. 그 실행은 결과로 세지 않았고,
절차 교훈은 `memory/opencode-e2e.md`에 기록했다.

## DET-006 — 부재 근거 표기를 한국어 `검색(...)` 형식으로 강제한다

- 상태: 계획
- 결함: 부재 근거 10건이 `搜索(...)`처럼 중국어로 출력되었고, `검색(전체,
  pattern=...)`처럼 `scope=` 키를 빠뜨렸다. `DET-005` 재실행에서는 `search(...)`
  영문 표기와, `미확인` 근거에 `검색(...)` 대신 file:line만 적은 5건이 남았다.
- 작업: `미확인` 근거의 정확한 문자열 형식을 agent 지시와 템플릿에 예시로
  넣는다. 사용자 표시 식별자를 번역하지 말라는 규칙을 부재 근거에도 명시한다.
  `상충됨` 근거는 참조 두 개를 설명 없이 나열해야 한다는 규칙도 함께 고정한다.
- 검증: 계약 테스트로 비한국어 `검색` 대체 표기를 거부하고, Quality Gate와
  E2E 재실행으로 확인한다.

## DET-007 — 근거 경로를 저장소 상대 경로로 강제한다

- 상태: 계획
- 결함: `applicationContext.xml:31-34`, `web.xml:34-36`처럼 파일명만 인용해
  `--repo-root` 검증이 실패했다. 실제 경로는
  `src/main/webapp/WEB-INF/applicationContext.xml`이다. `DET-005` 재실행에서도
  같은 형태 2건과, `Dockerfile:17.WAR 이미지 별도 정의 없음`처럼 참조 뒤에 설명을
  붙이거나 `:line`을 빠뜨린 3건이 남았다.
- 작업: 근거는 저장소 루트 기준 상대 경로와 `:line`만 쓰고 그 뒤에 설명을 붙이지
  않는다는 규칙을 agent 지시에 추가하고, 표 금지 규칙 위반(최종 보고서 표 2줄)도
  같은 티켓에서 잡는다.
- 검증: `--repo-root`를 붙인 계약 테스트, Quality Gate, E2E 재실행.

## 구현 순서와 커밋 경계

```text
DET-004 판정 일치성 → DET-005 속성 라인 형식 → DET-006 부재 근거 표기
  → DET-007 저장소 상대 경로와 표 금지
```

티켓별로 하나의 커밋을 만든다. `DET-005`~`DET-007`은 agent 지시 변경이므로
각 티켓 완료 시 Detailed E2E를 다시 실행해 validator 결과를 기록한다.
