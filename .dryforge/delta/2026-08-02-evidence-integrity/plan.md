# Phase 1 Evidence Integrity Delta Cycle 실행 계획

```yaml
cycle_type: delta
cycle_marker: phase1-evidence-integrity-2026-08-02
baseline_commit: 1686be7
first_cycle_graph: unchanged
regen_barriers: []
```

이 계획은 기존 First Cycle의 T1~T14 계획을 대체하지 않는다. 현재 Ready에서는 이 문서와
동일 delta directory의 spec/handoff만 생성한다. 각 task는 사용자 승인 후 `dryforge go`가
실행하며, Ready가 제품 코드·테스트를 생성하거나 live acceptance를 호출하지 않는다.

## D1 — Path 및 Secret 경계

목표: 모든 Repository observation과 출력 가능한 관찰 결과에 동일한 canonical path 및
redaction 경계를 적용한다.

작업 범위:

- `.git`, `.GIT`, `.Git` 및 모든 case variant를 모든 tool 입력에서 차단한다.
- lexical 검사 후 canonical resolve를 수행하고, resolve 이후 `.git` component를 다시
  검사한다.
- symlink와 Windows junction을 따라 Repository 밖 또는 `.git`으로 우회하는 경로를
  차단한다.
- `list_tree`, `find_files`, `search_text`, `read_file`, `read_file_lines`에 같은 경계를
  적용한다.
- URL authority의 `user:password@host`, Git remote, JDBC 및 general connection URL의
  credential을 scheme/host/port/path/query 구조는 보존하면서 값만 redaction한다.
- Tool output, history, ledger, report, artifact, exception 경계에서 동일 redactor를
  사용한다.

검증: `.git` 대소문자, `..` canonical traversal, symlink/junction alias, URL authority,
Git remote, JDBC/general connection URL fixture와 target immutability를 확인한다.

## D2 — AnalysisResult 최소 계약 확장

목표: 기존 `analysis.py` 중심 계약을 최소 확장하여 finding과 Evidence의 연결 및
미확인 결정의 책임 정보를 표현한다.

계약 확장:

- structured finding: stable finding ID, 상태, claim/summary, Evidence ID 목록
- Evidence ID와 실제 line `excerpt`
- unresolved decision: 결정 내용, `resolution_owner` 또는 `resolution_source`
- absence claim: `absence_scope`, `absence_pattern`, `absence_result`
- repository-relative path와 line 범위의 기존 계약 유지

새 대규모 schema 모듈을 만들거나 기존 AnalysisResult를 전면 재설계하지 않는다. extra
field 금지와 네 Evidence 상태 분리는 유지한다. Secret 값은 새 필드에도 허용하지 않는다.

검증: positive line-backed Evidence, unresolved absence, finding-to-Evidence reference,
resolution owner/source, 실제 excerpt, extra field rejection과 redaction을 확인한다.

## D3 — Repository-aware complete validation

목표: `complete`의 유일한 승인 경로를 실제 Repository와 대조된 `ledger.result`로
고정한다.

작업 범위:

- `validate_analysis` 성공 없이 `complete`를 반환·저장·렌더링하지 않는다.
- 0-tool final candidate도 동일한 validation을 거치며, 검증이 없으면 complete가 아니다.
- 모든 positive path, line range, excerpt를 실제 Repository와 대조한다.
- 허위 path, line, excerpt, claim과 존재하지 않는 Evidence ID를 거부한다.
- 모든 finding의 Evidence 연결과 상태 일관성을 검증한다.
- external deployment decision은 unresolved로 허용하되, 그 이유만으로 partial을
  강제하지 않는다.
- `ledger.result`가 없거나 검증 실패이면 실행 경로에 따라 `partial` 또는 `failed`를
  선택하되 complete로 보정하지 않는다.

검증: validate_analysis 없는 complete, 0-tool 허위 complete, 허위 path/line/excerpt,
finding 연결 누락, external decision unresolved + complete, budget/no-progress partial을
확인한다.

## D4 — ADK 종료와 fallback 무결성

목표: ADK Runner 종료, Agent instruction, validation feedback, fallback 모두 같은 상태
의미론을 사용하게 한다.

작업 범위:

- 미검증 final response는 complete가 아니며, validation feedback을 받아 재탐색하거나
  정직한 partial/failed로 종료한다.
- fallback observation을 자동으로 `confirmed`로 승격하지 않는다.
- Agent의 판단이 없으면 observation은 diagnostic 또는 unresolved이며, fallback은
  `partial` 또는 `failed`로만 종료한다.
- Agent instruction과 validation feedback에서 외부 배포 unresolved, budget/no-progress,
  validation failure의 상태 의미를 동일하게 유지한다.
- Markdown report는 validated finding과 Evidence만 렌더링하고 원시/허위 summary를
  독립적으로 신뢰하지 않는다.

검증: fallback complete 금지, fallback confirmed 승격 금지, validation feedback loop,
history/exception/report redaction, finding/Evidence 기반 report rendering을 확인한다.

## D5 — 회귀 테스트

목표: D1~D4의 계약을 테스트 우선으로 고정한다.

실행 순서:

1. 아래 회귀 테스트를 먼저 실패 상태로 추가한다.
2. D1~D4 구현을 수행한다.
3. 각 테스트를 통과시키고 기존 Phase 1 테스트의 상태 의미론을 재확인한다.

필수 회귀 항목:

- `.git`, `.GIT`, `.Git`
- canonical traversal
- symlink 또는 junction 우회
- validate_analysis 없는 complete
- 0-tool 허위 complete
- 허위 path, line, excerpt
- external decision unresolved + complete
- budget 또는 no-progress partial
- fallback complete 금지
- fallback confirmed 승격 금지
- finding과 Evidence 연결
- URL, Git remote, JDBC credential redaction
- Tool output, history, artifact, report, exception redaction

D5는 기존 Agent Tool 8개 이름이나 surface를 추가·삭제하지 않는다. 회귀 테스트는 그
surface와 현재 ADK Runner contract를 검증하는 범위에 한정한다.

## D6 — Solar Pro 3 live acceptance

목표: 사용자 승인 후 실제 Google ADK Runner와 Upstage Solar Pro 3에서 delta 계약을
검증한다.

필수 조건과 결과:

- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`로
  Upstage Solar Pro 3를 설정한다.
- 실제 Google ADK Runner를 사용한다.
- `validate_analysis` 성공, 실제 내용이 있는 line-backed Evidence, structured finding과
  Evidence ID 연결을 결과 artifact에서 확인한다.
- 외부 배포 선택사항은 unresolved로 남을 수 있고, 정상 Repository 탐색 완료는
  complete여야 한다.
- target Git 상태가 불변이고 Secret leak가 0이어야 한다.
- T7이 미시작이며 기존 T1~T14 graph가 변경되지 않았음을 확인한다.
- 검증 증거를 기록한 뒤 구현 delta commit을 생성한다.

D6는 Ready에서 실행하지 않는다. 네트워크, credential, 실제 Runner 호출 및 target
acceptance는 사용자 승인 이후에만 수행한다.

## Execution Graph

```yaml
tasks:
  - id: D1
    title: Path 및 Secret 경계
    depends: []
    risk: RISKY
  - id: D2
    title: AnalysisResult 최소 계약 확장
    depends: [D1]
    risk: RISKY
  - id: D3
    title: Repository-aware complete validation
    depends: [D1, D2]
    risk: RISKY
  - id: D4
    title: ADK 종료와 fallback 무결성
    depends: [D3]
    risk: RISKY
  - id: D5
    title: 회귀 테스트
    depends: [D1, D2, D3, D4]
    risk: RISKY
  - id: D6
    title: Solar Pro 3 live acceptance
    depends: [D5]
    risk: RISKY
regen_barriers: []
```

그래프는 D1에서 시작하여 D6으로 끝나며 모든 dependency가 선언된 task를 참조한다.
cycle 또는 dangling dependency가 없다. 기존 First Cycle graph는 이 그래프의 입력이나
출력이 아니며 변경 대상도 아니다.
