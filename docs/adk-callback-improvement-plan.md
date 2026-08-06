# ADK Tool Call Callback 개선 계획

이 문서는 현재 `phase`, `grounding`, `candidate` 오류를 안전하게 줄이기 위한
실행 계획입니다. 대상은 ADK callback과 bounded recovery이며, Kubernetes renderer,
Repository target, 모델 provider business logic은 변경하지 않습니다.

## 1. 목표

모델이 잘못된 Tool Call을 만들어도 callback이 오류를 더 복잡하게 만들지 않고,
정확한 오류와 허용된 다음 행동을 전달한 뒤 bounded하게 종료하거나 복구하도록
만듭니다.

### 쉬운 비유

현재 callback은 학교 복도의 한 안내원이 다음 일을 모두 하는 상태입니다.

```text
출입 확인
교실 순서 검사
숙제 내용 검사
시간표 변경
사고 기록
```

안내원이 한 학생의 잘못을 처리하다가 전체 시간표를 바꾸면 안 됩니다.
이번 개선은 검사, 실제 이동, 결과 기록을 분리하는 작업입니다.

## 2. 현재 baseline과 완료 기준

### 현재 baseline

- `solar-pro2` 공식 3-run: `0/3`
- `solar-pro3` 공식 3-run: `0/3`
- 두 모델 모두 target Repository는 변경하지 않음
- deterministic focused suite: `46 passed`
- 주요 실패:
  - 모델의 잘못된 line/path/candidate 생성
  - grounding 오류 후 phase 상태가 덮어써지는 runtime 문제
  - pre-binding candidate 오류와 handler validation의 구분 문제

상세 telemetry는 [solar-live-recovery-comparison-20260806.md](../.dryforge/solar-live-recovery-comparison-20260806.md)에 있습니다.

### 최종 완료 기준

```text
1. grounding 오류 후 잘못된 validate 호출이 기존 follow-up을 잃지 않는다.
2. 허용되지 않은 phase action은 Repository를 실행하지 않고 bounded STOP한다.
3. 잘못된 phase의 candidate가 candidate_schema로 오분류되지 않는다.
4. after_model callback이 원본 LlmResponse를 직접 수정하지 않는다.
5. 실제 ADK Runner에서 callback 반환 dictionary와 function response linkage가 유지된다.
6. focused suite가 통과한다.
7. 전체 suite 결과에서 기존 실패와 새 실패를 구분할 수 있다.
8. live smoke 성공 후에만 공식 3-run을 실행한다.
9. target Git 상태와 Secret redaction 검증이 유지된다.
```

## 3. 공식 ADK 원칙

ADK Tool의 기본 흐름은 다음과 같습니다.

```text
모델이 Tool 선택
  -> Tool Call 생성
  -> before_tool_callback 검사
  -> Tool 실행 또는 callback dictionary로 차단
  -> Tool 결과를 모델에 전달
  -> 다음 Tool 또는 최종 답변
```

- [ADK Custom Tools](https://adk.dev/tools-custom/)
- [ADK Function Tools](https://adk.dev/tools/function-tools/)
- [ADK Callback 종류](https://adk.dev/callbacks/types-of-callbacks/)
- [ADK Callback 설계 원칙](https://adk.dev/callbacks/design-patterns-and-best-practices/)
- [ADK State](https://adk.dev/sessions/state/)

ADK 문서에 따르면 `before_tool_callback`이 `None`을 반환하면 Tool이 실행되고,
dictionary를 반환하면 Tool 실행을 건너뛰고 그 dictionary를 결과로 사용합니다.

이번 계획의 핵심은 callback을 문지기로 사용하되, 상태 머신의 여러 상태를 문지기가
중간에 함부로 덮어쓰지 않게 만드는 것입니다.

## 4. 단계별 실행 계획

### 단계 0 — baseline 고정

#### 작업

1. branch, `git status --short`, `git diff --stat` 기록
2. focused test 실행
3. 전체 suite 실행
4. deterministic reproducer 출력 보존
5. live artifact의 Secret-safe telemetry 확인

#### 명령

```powershell
git branch --show-current
git status --short
git diff --stat

python -m pytest -q -p no:cacheprovider `
  tests/test_adk_runner_recovery.py `
  tests/test_phase1_adk_contract.py

python -m pytest -q -p no:cacheprovider
```

#### 규칙

baseline을 기록하기 전에 source code를 수정하지 않습니다.
기존 사용자 변경은 보존합니다.

### 단계 1 — callback 역할 고정

각 callback의 책임을 다음처럼 제한합니다.

```text
after_model_callback
  모델 응답을 dispatch 가능한 형태인지 검사하고 필요하면 복사본을 반환

before_tool_callback
  실제 Tool 실행 전 allow/deny만 결정

Tool handler
  read-only Repository를 실제로 관찰

after_tool_callback 또는 공통 성공 처리
  성공 결과와 provenance를 기록

on_tool_error_callback
  ADK 예외를 Secret-safe envelope으로 변환
```

변경하지 않을 것:

- public Agent Tool 8개
- `error_envelope` JSON shape
- Repository read-only 경계
- Secret redaction 경계
- provider/model 이름별 business logic

### 단계 2 — phase와 grounding 상태 전이 수정

이 단계가 최우선입니다.

#### 현재 문제

현재 `before_tool_callback`은 argument, duplicate, phase, budget, recovery를
한 함수에서 처리합니다. 특히 phase 오류가 `authorize_action()`보다 먼저 반환되어
불허된 action이 recovery lease를 제대로 소비하지 않고 기존
`follow_up_actions`를 덮어쓸 수 있습니다.

관련 코드:

- [adk_tools.py:425](../migration_assistant/adk_tools.py:425)
- [adk_tools.py:454](../migration_assistant/adk_tools.py:454)
- [tool_protocol.py:161](../migration_assistant/tool_protocol.py:161)

#### 권장 판단 순서

```text
1. 등록 Tool인지 확인
2. 이미 차단된 동일 signature인지 확인
3. 현재 phase에서 허용되는지 확인
4. argument schema 확인
5. budget 확인
6. recovery lease 승인
7. 실제 Tool 실행
```

#### 권장 구조

```python
decision = control.decide_action(
    action=name,
    phase_actions=allowed,
    issue=control.protocol_issue,
)

if decision.disposition == RecoveryDisposition.STOP:
    return error_envelope(
        decision.issue,
        allowed_next_actions=decision.allowed_actions,
    )

# 실제 실행 직전에만 lease와 상태를 커밋합니다.
control.commit_action(decision)
return None
```

`decide_action`은 순수 판정 함수로 만들고, `commit_action`은 실행 직전에만
호출하는 것이 핵심입니다.

#### phase 위반 정책: 하나로 고정

계획에서 가장 중요한 정책은 다음 하나로 고정합니다.

```text
active recovery 중 허용되지 않은 action
  -> 즉시 bounded STOP
  -> stop_requested=True
  -> allowed_next_actions=[]
  -> Repository 실행 0회
  -> 후속 Tool 실행 0회
```

기존 grounding 오류는 현재 active 오류를 계속 허용하기 위한 상태가 아니라,
Secret-safe audit/diagnostic 기록으로만 보존합니다.

즉, 다음 두 정책을 동시에 사용하지 않습니다.

```text
정책 A: 허용되지 않은 action이면 즉시 STOP
정책 B: 허용되지 않은 action 뒤에도 observation을 계속 허용
```

이번 MVP에서는 안전성과 해석 가능성이 높은 정책 A를 사용합니다.

#### 최소 상태 전이표

구현 전에 아래 표를 테스트로 고정합니다.

| 현재 상태 | 모델 action | callback 결과 | Repository 실행 | 다음 상태 |
|---|---|---|---:|---|
| `GROUNDING_PENDING` | 허용된 observation | 허용 | 1회 | `GROUNDING_PENDING` 또는 `VALIDATE_ONLY` |
| `GROUNDING_PENDING` | `validate_analysis` | phase 오류 후 STOP | 0회 | `STOPPED` |
| `CANDIDATE_REPAIR` | 변경된 `validate_analysis` | 허용 | 1회 | `VALIDATE` |
| 모든 repair 상태 | 같은 오류 재발 | bounded STOP | 0회 | `STOPPED` |
| 정상 phase | schema 오류 | schema envelope | 0회 | 같은 phase의 correction lease |

여기서 `previous_issue`는 진단 기록이고, `allowed_next_actions`는 현재 실행을
허용하는 active 상태입니다. 둘을 같은 필드로 재사용하지 않습니다.

#### grounding 계약

```text
evidence_grounding 발생
  -> search_text/read_file/read_file_lines 중 최대 1회
  -> validate_analysis 1회
  -> 성공 또는 bounded 실패
```

grounding 오류의 원래 내용은 audit용으로 유지하되, phase 위반 뒤에는 active action을
더 허용하지 않습니다.

```python
previous_issue = evidence_grounding
stop_requested = True
active_next_actions = ()
```

#### 필수 deterministic test

```text
정상 경로
1. grounding 오류 생성
2. 허용된 observation 1회 호출
3. 두 번째 observation은 차단
4. corrected validate_analysis 허용 확인

오류 경로
1. grounding 오류 생성
2. observation 전에 validate_analysis 호출
3. phase/state 오류 확인
4. stop_requested=True 확인
5. 기존 grounding issue가 audit 기록에만 보존되는지 확인
6. 잘못된 action 뒤 Repository 실행 횟수 0 확인
```

phase 위반 테스트의 기대 결과는 다음과 같습니다.

```text
grounding
  -> observation 전에 validate_analysis 호출
  -> invalid_arguments / category=state / $.name
  -> stop_requested=True
  -> allowed_next_actions=[]
  -> Repository 실행 0회
```

### 단계 3 — candidate 오류 경계 분리

#### Pre-binding schema 오류

ADK가 handler에 들어가기 전에 argument를 거부한 경우입니다.

```text
validation_attempts = 0
prebinding_rejections = 1
Repository validator 호출 = 0
```

#### Handler candidate 오류

argument는 schema를 통과했지만 Repository Evidence 검증에서 실패한 경우입니다.

```text
validation_attempts = 1
prebinding_rejections = 0
Repository validator 호출 = 1
```

#### 판단 규칙

잘못된 phase에서 잘못된 candidate가 들어오면 phase 오류를 먼저 반환합니다.

```text
phase 오류가 먼저
  -> candidate schema 검사는 나중에
```

정상 phase에서 candidate field가 틀렸다면 candidate schema를 반환합니다.

#### 필수 테스트

```text
grounding repair 중 {status: "bad"}
  기대: invalid_arguments / category=state / $.name

정상 phase에서 {status: "bad"}
  기대: candidate_schema / $.status

같은 pre-binding 오류 반복
  기대: 두 번째 허용 action 없음, handler validation 0회
```

#### 내부 예외와 candidate 오류 분리

`validate_analysis`의 모든 예외를 `candidate_schema`로 바꾸지 않습니다.

```text
TypeError 또는 ADK argument binding 오류
  -> candidate_schema
  -> prebinding rejection으로 집계

예상하지 못한 RuntimeError/내부 오류
  -> category=execution 또는 internal
  -> retryable=False
  -> allowed_next_actions=[]
  -> bounded STOP
```

추가 acceptance criteria:

```text
validate TypeError
  -> candidate_schema
  -> handler validation=0

validate RuntimeError
  -> execution/internal
  -> retryable=False
  -> allowed_next_actions=[]
  -> stop_requested=True
```

### 단계 4 — after_model 응답 불변성 확보

#### 현재 문제

현재 정규화 과정에서 원본 객체를 직접 수정합니다.

```python
call.name = canonical_name
```

이러면 “모델이 원래 보낸 이름”과 “runtime이 고친 이름”을 구분하기 어렵습니다.

#### 변경 방향

공식 ADK 예시처럼 response와 parts를 복사합니다.

```python
from copy import deepcopy

original = llm_response
modified = deepcopy(original)
modified.content.parts[index].function_call.name = canonical_name
modified.custom_metadata = {
    **(modified.custom_metadata or {}),
    "canonicalized_calls": canonicalized,
}

return modified
```

새 `LlmResponse`를 직접 조립할 경우 `finish_reason`, `usage_metadata`,
`grounding_metadata`, `partial`, `error_code` 같은 필드를 잃을 수 있습니다.
따라서 설치된 ADK version에서 지원되는 deep-copy 방식으로 원본의 전체 필드를
보존하는지 먼저 확인합니다.

#### 필수 테스트

```text
원본 call.name은 변경되지 않음
수정된 response의 call.name만 canonical name
call_linkage id/name은 원래 호출과 일치
malformed arguments 원문은 metadata에 저장되지 않음
```

### 단계 5 — callback context와 telemetry 정리

공식 ADK는 callback 종류별 context 타입을 제공합니다.

```python
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.base_tool import BaseTool

def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
):
    ...

def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
):
    ...
```

참고: [ADK Callback Context](https://adk.dev/callbacks/types-of-callbacks/)

raw arguments를 저장하지 않고 다음 metadata만 기록합니다.

```text
agent_name
invocation_id
tool_name
call_id가 있으면 call_id
phase
issue code
category
field_path
allowed action
callback stage
```

현재처럼 Secret-safe 규칙은 유지해야 합니다.

#### State 구분

[ADK State 문서](https://adk.dev/sessions/state/)의 state는 session과 event를 통해
추적할 수 있습니다. 하지만 `RunControlLedger`는 현재 분석 실행 안에서만 필요한
bounded control 상태이므로 전부 session state로 옮기지 않습니다.

```text
Session state
  -> 여러 turn 사이에 남겨도 되는 상태

RunControlLedger
  -> 현재 분석 실행 안에서만 필요한 상태
```

이 구분은 유지하되 callback context를 정확히 사용해 invocation 정보를 얻습니다.

#### callback idempotency

callback은 framework 재시도나 동일 event 전달에 대비해 같은 delivery를 두 번
처리해도 상태를 한 번만 변경해야 합니다.

처리 식별자는 다음 조합을 사용합니다.

```text
invocation_id + call_id + callback_stage
```

추가 acceptance criteria:

```text
동일 callback delivery 2회
  -> retry count 증가 1회
  -> lease 소비 1회
  -> 두 번째 delivery만으로 STOP하지 않음
```

raw arguments와 Secret은 idempotency key에 포함하지 않습니다.

#### ADK version 계약

현재 lock으로 검증된 ADK는 `1.37.0`입니다. 구현과 lifecycle 통합 테스트는
우선 이 버전을 기준으로 고정합니다. dependency 범위를 바꾸거나 ADK를 올리는
작업은 별도 compatibility 검증 없이는 이번 변경에 포함하지 않습니다.

#### 학습 문서도 같은 version으로 검증

초보자용 문서의 callback import와 예제는 설치된 ADK에서 실제 실행해야 합니다.

```python
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
```

장난감 예제 뒤에는 네트워크 없는 실제 `Runner + fake model` 예제를 추가합니다.
이를 통해 직접 callback을 호출한 경우와 ADK lifecycle이 callback을 호출한 경우를
구분할 수 있어야 합니다.

### 단계 6 — after_tool_callback 도입 여부 결정

이 단계는 phase 문제를 해결한 뒤 진행합니다.

현재 `_call()`은 모든 Tool의 공통 진입점이므로 실제 실행 여부의 유일한 기준으로
유지하고, 바로 전부 `after_tool_callback`으로 옮기지 않습니다.
먼저 다음 책임을 구분합니다.

```text
before_tool_callback
  -> allow/deny

_call()
  -> 실제 Repository 실행과 Tool별 오류 변환

after_tool_callback
  -> telemetry 전용 후처리
```

before callback이 dictionary를 반환해 Tool 실행을 차단했거나
`on_tool_error_callback`이 오류 dictionary를 반환한 경우에도
`after_tool_callback`이 호출될 수 있으므로, callback 호출 자체를 성공 실행으로
해석하지 않습니다.

최소 MVP에서는 `_call()`의 실제 operation 성공 경로에서만 provenance를 기록하고,
`after_tool_callback`은 다음 값을 관찰하는 용도로만 제한합니다.

```text
정상 실행: handler=1, executed=true, provenance=1
before 차단: handler=0, executed=false, provenance=0
Tool 예외: handler=1, executed=false, provenance=0
```

`executed`는 public envelope을 넓히지 않고 내부 telemetry에만 기록합니다.

### 단계 7 — 실제 ADK Runner 통합 테스트

callback 함수를 직접 호출하는 테스트만으로는 ADK의 실제 호출 순서를 보장할 수
없습니다.

#### 필요한 fake trajectory

```text
fake model
  -> inspect_target
  -> 잘못된 read_file_lines
  -> 수정된 read_file_lines
  -> validate_analysis
```

#### 확인 항목

```text
1. after_model_callback 실행
2. before_tool_callback 실행
3. 오류 dictionary가 function response로 전달
4. 원래 function call id/name 유지
5. 잘못된 Tool의 Repository 실행 0회
6. 다음 model call이 허용 action으로 이어짐
7. recovery cap이 1을 넘지 않음
```

보안 trajectory도 확인합니다.

```text
Secret처럼 보이는 argument
  -> callback envelope에 원문 없음
  -> issue fingerprint에 원문 없음
  -> protocol telemetry에 원문 없음
```

### 단계 8 — 검증과 live 실행

live 모델은 deterministic 검증이 끝난 뒤에만 실행합니다.

```text
1. py_compile
2. 순수 RunControlLedger 상태 머신 테스트
3. callback 직접 호출 테스트
4. 실제 ADK Runner + fake model 통합 테스트
5. focused ADK contract tests
6. 전체 pytest
7. solar-pro2 1-run smoke
8. solar-pro2 공식 3-run
9. model ID만 solar-pro3로 변경한 비교 3-run
```

live 조건:

```text
focused suite 통과
전체 suite에서 새 실패 없음
target Repository clean
output directory가 target 밖
Secret scan 통과
외부 전송 승인 확인
```

## 5. 오늘 저녁 실행 일정

### 1회차 — 개념 30분

```text
Tool = 모델이 호출할 수 있는 개발자 함수
Tool Call = 함수 이름과 arguments를 담은 모델의 주문서
before callback = 실행 전 문지기
Tool result = 실행된 함수의 결과
```

읽을 문서:

- [ADK Custom Tools](https://adk.dev/tools-custom/)
- [ADK Function Tools](https://adk.dev/tools/function-tools/)

### 2회차 — 현재 코드 30분

```text
agent.py
  -> callback 등록

adk_tools.py
  -> callback 판단

tool_protocol.py
  -> 상태 전이

adk_runner.py
  -> stream/recovery
```

### 3회차 — deterministic test 30분

```powershell
python -m pytest -q -p no:cacheprovider `
  tests/test_adk_runner_recovery.py `
  tests/test_phase1_adk_contract.py
```

각 실패마다 다음 세 줄을 직접 적습니다.

```text
모델은 어떤 Tool Call을 만들었는가?
callback은 무엇을 반환했는가?
그 반환 뒤 state가 어떻게 바뀌었는가?
```

## 6. 최종 체크리스트

### 코드

- [ ] phase 오류가 기존 follow-up을 덮어쓰지 않음
- [ ] disallowed action이 bounded STOP
- [ ] phase 검사와 argument 검사의 순서가 명확함
- [ ] pre-binding과 handler validation이 분리됨
- [ ] LlmResponse를 직접 수정하지 않음
- [ ] callback context 타입이 정확함
- [ ] invocation telemetry가 Secret-safe임
- [ ] 동일 callback delivery의 idempotency가 보장됨
- [ ] ADK version 계약이 검증된 lock version과 일치함
- [ ] 내부 RuntimeError가 candidate 오류로 오분류되지 않음

### 테스트

- [ ] callback 직접 호출 테스트
- [ ] 실제 ADK Runner 통합 테스트
- [ ] before 차단/정상 실행/Tool 예외의 handler 실행 횟수 테스트
- [ ] Tool 실행 횟수 테스트
- [ ] function call id/name linkage 테스트
- [ ] LlmResponse 원본 전체 필드 보존 테스트
- [ ] recovery cap 테스트
- [ ] grounding observation cap 테스트
- [ ] candidate pre-binding cap 테스트
- [ ] Secret redaction 테스트

### live

- [ ] smoke 1회 성공
- [ ] 동일 모델 공식 3-run 성공
- [ ] 비교 모델은 model ID만 변경
- [ ] target Git clean
- [ ] artifact에 raw argument와 API key 없음

### 학습 문서

- [ ] callback context import가 설치된 ADK version에서 실제 실행됨
- [ ] 장난감 예제 다음에 네트워크 없는 실제 Runner + fake model 예제가 있음

## 7. 최종 기대 흐름

```text
모델이 Tool Call 생성
  -> after_model_callback이 복사본으로 protocol 검사
  -> before_tool_callback이 phase와 schema 검사
  -> 허용되면 Tool 실행
  -> 성공 결과와 provenance 기록
  -> 오류면 원래 상태를 보존한 envelope 반환
  -> 모델이 허용된 다음 행동 선택
  -> validate_analysis terminal 성공
```

가장 중요한 원칙은 다음입니다.

> callback은 문지기이고, 상태 머신은 판정 결과를 기록하는 관리자여야 합니다.

현재 문제는 문지기가 관리자 역할까지 동시에 수행하면서, 잘못된 한 번의 호출이
다음 실행 순서까지 바꾸는 데서 시작됩니다.
