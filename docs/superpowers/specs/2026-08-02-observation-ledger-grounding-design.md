# 관측 원장 기반 Evidence Grounding 설계

## 상태

- 범위: live 신뢰성 개선. Evidence grounding 판정 기준과 `validate_analysis`
  수용 단위 변경
- 제외: public Tool 추가, provider별 business logic, 모델 교체, Streamlit
- 구현 상태: 미구현, 설계 승인 대기
- 전제 제약: 모델은 `solar-pro3`로 고정한다. 모델 교체는 현실적으로 어렵다는
  사용자 결정을 설계 입력으로 받는다
- 개정: 최초 초안의 자기 검토에서 발견한 Critical 2건, Important 2건, Minor 2건을
  반영했다. 상세는 마지막 절에 남긴다

## 문제의 본질

`docs/phase1-adk-experiment-log.md`의 Run 26~28에서 live 10회 중
`complete` + `terminal`은 2회였다. 실패의 지배적 형태는 하나다.

Agent는 파일을 실제로 관측한다. `read_file_lines`와 `search_text` 호출이
trajectory에 남아 있다. 그런데 최종 `validate_analysis` payload에서 line 번호와
excerpt를 **옮겨 적는 과정**에서 틀린다. 예를 들어 `pom.xml:13-13`을 근거로
제출했지만 그 줄은 Apache 라이선스 헤더다.

가드레일 쪽 원인은 배제됐다.

- 비교 함수는 공백과 CRLF를 무시하므로 과엄격이 아니다
  (`migration_assistant/repository_tools.py:891`, `_compact`는 `\s+`를 제거한다)
- 교정본은 모델에게 실제로 전달된다 (`migration_assistant/adk_tools.py:564`)
- 지시문은 이미 그대로 복사하라고 명시한다
  (`migration_assistant/agent.py:62`, `migration_assistant/agent.py:76`)
- 출력 절단 가설은 반증됐다 (Run 28, `LLM_MAX_TOKENS` 8192에서 0/3)

즉 거부 자체는 설계대로의 올바른 동작이다. 문제는 **전사(transcription)라는 순수
기계적 작업을 확률적 구성요소에 맡긴 책임 배치**다. `AGENTS.md`의 책임 분리는
"Agent는 판단, 결정론적 Python은 기계적 작업"인데, 현재 excerpt 전사는 이 분리를
거꾸로 적용하고 있다.

## 이미 존재하는 미사용 자산

`migration_assistant/adk_tools.py:398-405`는 모든 `search_text` hit와
`read_file_lines` 결과를 `ledger.observations`에 기록한다. 기록 단위는 line 하나이며
shape는 두 Tool이 동일하다.

```python
{"path": ..., "line_start": n, "line_end": n, "text": ..., "excerpt": ...}
```

`migration_assistant/repository_tools.py:536`과
`migration_assistant/repository_tools.py:657`이 이 shape를 생성하며 값은 이미
redaction을 거친다.

그러나 `observations`를 읽는 코드는 없다. 시스템은 "모델이 어떤 line을 실제로
열었는지"를 이미 알면서 버리고, 대신 모델의 전사본을 문자열 비교한다.

## 설계

### 1. 관측 출처에 따른 등급화 grounding

positive Evidence 판정은 관측 출처에 따라 두 등급으로 나눈다.

| 관측 출처 | 관측 단위 | 수용 조건 |
| --- | --- | --- |
| `search_text`, `read_file_lines` | 정확한 line 하나 | 원장에 그 line이 있으면 수용. excerpt 불필요 |
| `read_file` | 반환된 텍스트 전체 | 원장 확인에 더해 **excerpt 일치도 요구**(현행 검사) |
| 관측 없음 | — | 거부. excerpt가 정확해도 거부 |

**이 등급화가 이 설계의 핵심이며, 생략하면 설계가 무너진다.**
`migration_assistant/repository_tools.py:609`의 `read_file`은 파일을 최대 32 KiB까지
통째로 반환한다. 반환된 모든 line을 무조건 관측으로 인정하면 `read_file("pom.xml")`
한 번으로 그 파일 전 줄이 관측 상태가 되고, 모델은 아무 줄이나 인용해 통과할 수 있다.
좁은 관측(`search_text`, `read_file_lines`)에만 전사 면제를 주는 이유가 이것이다.

따라서 이 설계는 grounding을 일률적으로 강화하지 않는다. **출처별 교환**이다.

- 좁은 관측: 현행보다 강해진다. 텍스트 재현이 아니라 "그 줄을 실제로 열었을 것"을
  요구하므로 우회할 수 없다
- 전체 읽기: 현행과 같다. excerpt 일치를 그대로 요구한다
- 관측 없음: 현행보다 강해진다. 오늘은 excerpt만 맞으면 통과하지만 앞으로는 거부된다

`excerpt`와 `text`는 좁은 관측 경로에서만 선택 입력이 된다. 값이 오더라도 판정에
쓰지 않고 Python이 `path`와 line 범위로 파일을 다시 읽어 채운다. 이 역참조는
`migration_assistant/repository_tools.py:875`가 이미 수행하는 동작과 같다.

### 2. 관측 기록을 line 좌표 집합으로 분리

현재 `observations`는 전체 record를 보관하고 64개에서 앞쪽을 버린다
(`migration_assistant/adk_tools.py:404`). 이 상한이 남아 있으면 초반에 관측한
정당한 근거가 원장에서 사라져 **거짓 거부**가 발생한다.

record 보관과 별도로 `(path, line, 출처등급)` 좌표만 담는 집합을 유지한다. excerpt는
보관하지 않고 검증 시점에 파일에서 읽는다.

상한은 무한이 아니라 예산에서 유도한다. `max_explorations=100`과
`max_tool_response_bytes=32 KiB`(`migration_assistant/target.py:26,31`)에서 최악의
좌표 수는 10만 단위다. 좌표 집합의 상한을 이 규모 이상으로 명시하고, 상한에 도달하면
**좌표를 버리지 않고 exploration budget 초과로 run을 종료한다.** 좌표를 버리면 거짓
거부가 되어 이 설계의 목적을 스스로 깨기 때문이다.

### 3. 관측 좌표를 만들지 않는 Tool

`list_tree`, `find_files`, `inspect_target`, `inspect_git_metadata`는 파일 내용을
반환하지 않으므로 좌표를 만들지 않는다. 현재 지시문이 이들을 Evidence로 쓰지 말라고
규정한 것과 일치한다 (`migration_assistant/agent.py:61`).

`validate_analysis` 자체도 좌표를 만들지 않는다. 검증 대상이 검증 근거를 생성하는
순환을 막는다.

`read_file`이 잘려서 반환된 경우 반환된 부분까지만 좌표를 만든다. 반환하지 않은
line은 관측이 아니다.

### 4. 부분 수용의 정확한 명세

현재 `migration_assistant/adk_tools.py:535`는 한 항목이라도 어긋나면 candidate
전체를 버리고 `ledger.result`를 비워 둔다. Run 27의 run-1은 4건을 통과시켰지만 다른
run들은 한 건 때문에 0건이 됐다.

grounding을 통과한 Evidence를 run 단위로 보존하되, 다음을 명시적으로 고정한다.

- **동일성 키**: 모델이 부여한 Evidence `id`. 코드가 키를 만들지 않는다
- **충돌 해소**: 같은 `id`가 다시 오면 최신 제출이 이긴다. 최신 제출이 모델의
  현재 의도이기 때문이다
- **보존 대상**: grounding을 통과한 Evidence 항목만. 거부된 항목은 보존하지 않는다
- **최종 candidate 조립**: `findings`, `status`, `summary`는 **최신 제출본만** 쓴다.
  Evidence만 보존 집합과 최신 제출본의 합집합으로 구성한다. 최신 `findings`의
  `evidence_ids`가 어느 쪽에도 없는 `id`를 가리키면 candidate를 거부한다

이 규칙에서 코드가 하는 일은 모델이 authoring한 항목들을 모델이 부여한 키로 합치는
것뿐이다. **어떤 Finding이 살아남는지는 코드가 판단하지 않는다.** 최신 제출의
`findings` 블록이 그대로 지배한다.

**채택하지 않은 대안**: 어긋난 Evidence를 자동으로 버리고 나머지로 수용하는 방식.
이 경우 Evidence를 잃은 Finding의 생사를 코드가 결정해야 하고, 그것은 의미
authoring이다. 명시적으로 거부한다.

## 변경 지점

- `migration_assistant/adk_tools.py:398-405`: 좌표 집합 기록, 출처 등급 부여,
  `read_file` 경로 추가, 64건 상한 제거
- `migration_assistant/adk_tools.py:535`: 부분 수용과 항목별 결과 응답
- `migration_assistant/repository_tools.py:862`: `excerpt`가 비어 있으면 실패시키는
  현행 검사를 좁은 관측 경로에서 해제한다. 이 지점을 함께 고치지 않으면 설계 1이
  동작하지 않는다
- `migration_assistant/repository_tools.py:889-902`: 등급에 따른 판정 분기
- `migration_assistant/adk_tools.py:68-79` `ValidateEvidenceInput`: `text`/`excerpt`
  설명을 선택 입력으로 갱신

**변경하지 않는 곳**: `migration_assistant/analysis.py`의 `AnalysisResult`. 이 계층은
positive evidence에 path와 유효한 line 범위만 요구하고 excerpt를 요구하지 않으며
(`migration_assistant/analysis.py:64-70`), `text`와 `excerpt`를 상호 보완한다
(`migration_assistant/analysis.py:71-74`). 불필요한 변경을 하지 않는다.

## 보존 경계

- public Agent Tool은 정확히 여덟 개를 유지한다. 새 Tool을 추가하지 않는다
- 대상 Repository는 read-only이며 artifact는 output directory에만 쓴다
- provider나 model 이름별 분기를 추가하지 않는다
- `status`, `claim`, Finding과 Evidence의 연결, 부재 주장의 scope와 pattern은
  계속 모델이 정한다. 코드가 만들지 않는다
- Secret redaction 경계를 유지한다. 좌표에는 파일 내용이 포함되지 않으며, 역참조한
  excerpt는 기존 redaction 경로를 그대로 통과한다
- 부재(unresolved) Evidence는 line 좌표가 없으므로 기존 absence 검증 경로를 그대로
  둔다. 본 설계는 positive Evidence에만 적용한다

## 제약 충돌과 그 처리

`docs/superpowers/plans/2026-08-02-agent-tool-protocol-reliability.md:19`의 Global
Constraints는 "Evidence ID, status, link, owner, reason, excerpt를 모델 대신
authoring하지 말 것"을 요구한다. 본 설계의 excerpt 역참조는 이 조항과 형식상
충돌한다.

이 조항의 의도는 **의미를 지어내지 말라**는 것이다. excerpt는 `path`와 line 범위의
역참조 결과이며 새 의미가 아니다. 어떤 line이 근거인지, 그것이 무엇을 주장하는지는
계속 모델이 정한다.

그렇더라도 조항을 조용히 위반하지 않는다. 구현 전에 해당 plan의 Global Constraints를
"의미(status, claim, link, 부재 근거)는 authoring하지 않는다. path와 line 범위의
결정론적 역참조는 guardrail의 책임이다"로 명시 개정하고, 개정 사실을 기록한다.

## 평가 방법과 롤백 조건

**pass/fail gate와 효과 측정을 분리한다.** 3-of-3 gate는 출시 판정 도구이지 개선
측정 도구가 아니다. 기저 성공률이 약 20%인 구간에서 3회 시행은 개선을 탐지할 검정력이
사실상 없다. Run 27의 0/3 → 1/3을 해석할 수 없었던 것이 그 실례다.

측정 절차는 다음과 같다.

1. **기준선 재확보**: 변경 직전 코드 상태에서 `jpetstore-6` 10회 이상을 실행해
   `complete` + `terminal` 비율을 기록한다. Run 26은 `adk_function_tool` 수정 이전
   상태이고 Run 27~28은 이후 상태이므로 **두 기록을 하나의 기준선으로 쓰지 않는다.**
   현재 유효한 사후 기준선은 gate 1회분(1/3)뿐이며 이는 기준선으로 불충분하다
2. **사후 측정**: 동일 commit, 동일 비-비밀 모델 설정, 동일 budget으로 10회 이상을
   실행한다
3. **판단 규칙(사전 등록)**: 사후 성공률의 점추정이 기준선 점추정보다 높고, 새로
   도입한 실패 코드가 나타나지 않을 때만 채택한다
4. **롤백 조건(사전 등록)**: 사후 성공률이 기준선 이하이거나, `evidence_grounding`
   거부가 좁은 관측 경로에서 발생하면 변경을 되돌린다. 후자는 거짓 거부 신호이며
   설계 2의 좌표 상한 처리가 실패했음을 뜻한다
5. **기록**: 위 결과를 `docs/phase1-adk-experiment-log.md`에 Run 26~28과 같은 다섯
   항목 형식으로 남긴다

3-of-3 gate는 위 채택 판정을 통과한 뒤에만 실행한다.

## 실행 전 체크포인트

1. `ledger.observations`를 소비하는 코드가 없음을 다시 확인하고, 좌표 집합 도입이
   기존 record 사용처를 깨지 않는지 검색한다
2. `read_file`의 반환 line 범위 계산이 truncation과 CRLF에서 정확한지 결정론적
   테스트로 먼저 고정한다
3. plan Global Constraints 개정을 먼저 커밋한다. 코드 변경이 문서보다 앞서지 않게 한다
4. 설계 1의 등급화와 설계 3의 `read_file` 좌표 기록은 하나의 변경 단위로 처리한다.
   어느 한쪽만 넣으면 grounding이 약해지거나 통과율이 떨어진다

## 필요성 판단

모델이 고정 제약이면 남은 개선 여지는 모델에게 요구하는 작업의 종류를 바꾸는 것뿐이다.
현재 설계는 관측에 성공한 모델에게 전사를 한 번 더 요구하고, 전사 한 건이 틀리면 run
전체를 버린다. 본 설계는 좁은 관측 경로에서 그 요구를 없애고 실패 단위를 항목으로
낮춘다.

이것으로 3-of-3 gate 통과가 보장되지는 않는다. 관측된 실패의 지배적 클래스를 줄일
뿐이며, `duplicate_call`과 `invalid_arguments` 반복은 별개 문제로 남는다.

## 검증 기준

1. 관측하지 않은 line을 인용한 positive Evidence는 `evidence_grounding`으로
   거부된다. excerpt를 정확히 적어 보내도 거부된다
2. `search_text` 또는 `read_file_lines`로 관측한 line을 인용하고 excerpt를 생략한
   Evidence는 수용되며, 저장된 결과의 excerpt는 파일 실제 내용과 일치한다
3. `read_file`로만 관측한 line은 excerpt가 일치할 때만 수용되고, 불일치하면
   거부된다. 파일을 읽었다는 사실만으로는 수용되지 않는다
4. `read_file`이 잘려서 반환되지 않은 line은 관측으로 인정되지 않는다
5. 관측이 64건을 넘어도 초반에 관측한 line을 인용한 Evidence가 거부되지 않는다
6. 좌표 상한에 도달하면 좌표를 버리지 않고 budget 초과로 종료한다
7. 일부 Evidence만 어긋난 candidate에서, 수용된 항목은 다음 제출까지 유지되고 응답은
   거부된 항목만 지목한다. 최신 `findings`가 존재하지 않는 `id`를 참조하면 거부된다
8. `PUBLIC_AGENT_TOOL_NAMES`가 변하지 않고 target Repository가 변경되지 않는다
9. Secret 값이 좌표, 오류 응답, 저장된 artifact 어디에도 나타나지 않는다
10. 위 항목을 결정론적 테스트로 먼저 고정한 뒤, 「평가 방법과 롤백 조건」 절차를
    수행한다

## 개정 이력

최초 초안의 자기 검토에서 다음을 발견해 반영했다.

- **Critical**: 초안은 `read_file`로 관측한 line도 무조건 인정하면서 "우회가
  불가능하다", "grounding을 강화한다"고 단정했다. 실제로는 `read_file` 한 번으로
  파일 전 줄이 관측 상태가 되어 설계가 무너진다. 출처별 등급화로 바꾸고, 강화가
  아니라 교환임을 표로 명시했다
- **Critical**: 초안의 검증 기준은 live gate 재실행뿐이어서, Run 27에서 이미 겪은
  "n=3으로는 개선 여부를 알 수 없음"을 그대로 반복했다. 효과 측정을 gate와 분리하고
  기준선 재확보, 사전 등록 판단 규칙, 롤백 조건을 추가했다
- **Important**: 설계 4의 동일성 키, 충돌 해소, 최종 candidate 조립 주체가
  미명세여서 코드가 의미를 authoring할 여지가 있었다. 세 가지를 모두 고정했다
- **Important**: `migration_assistant/repository_tools.py:862`의 excerpt 필수 검사가
  변경 지점에서 누락됐다. 반대로 `AnalysisResult`는 변경 불필요임을 근거와 함께
  명시했다
- **Minor**: 좌표 보관 상한을 "무한"에서 예산 유도값과 초과 시 동작으로 바꿨다
- **Minor**: Run 26과 Run 27~28이 서로 다른 코드 상태임을 명시하고, 하나의 기준선으로
  쓰지 않도록 했다
