# ADK Tool Call과 Callback 입문 학습 문서

이 문서는 Google ADK의 Agent Tool 호출을 처음 접하는 개발자를 위한 학습 문서입니다.
현재 저장소의 callback 구현을 이해하고, 왜 phase·grounding·candidate 오류가 생기는지
직접 역추적할 수 있도록 작성했습니다.

이 문서의 목표는 ADK 전체를 외우는 것이 아닙니다. 오늘은 다음 질문에 답할 수 있으면
충분합니다.

1. 모델은 왜 Python 함수를 직접 실행하지 않고 Tool Call이라는 메시지를 보내는가?
2. `before_tool_callback`은 언제 실행되고 무엇을 막을 수 있는가?
3. Tool 오류가 나면 모델은 어떤 응답을 받고 다음에 무엇을 하는가?
4. 현재 코드에서 grounding 오류가 phase 오류로 바뀌는 이유는 무엇인가?
5. callback 상태를 어디에서 어떻게 관리해야 안전한가?

---

## 0. 먼저 실행해 보는 작은 전체 예제

아래 코드는 ADK를 호출하지 않습니다. 그래서 API key나 네트워크가 필요하지 않습니다.
Agent와 Tool의 관계만 눈으로 확인하는 장난감 예제입니다.

```python
# tool_call_lesson.py

from dataclasses import dataclass


@dataclass
class ToolCall:
    name: str
    args: dict


def search_repository(pattern: str) -> dict:
    """실제 Repository 대신 고정된 관찰 결과를 반환합니다."""
    print(f"[Tool 실행] search_repository(pattern={pattern!r})")
    return {
        "hits": [
            {"path": "app.py", "line": 1, "text": "PORT = 8080"}
        ]
    }


def before_tool_callback(call: ToolCall) -> dict | None:
    """Tool을 실행해도 되는지 검사합니다."""
    allowed_tools = {"search_repository"}

    if call.name not in allowed_tools:
        return {
            "ok": False,
            "error": f"허용되지 않은 Tool입니다: {call.name}",
        }

    if not isinstance(call.args.get("pattern"), str):
        return {
            "ok": False,
            "error": "pattern은 문자열이어야 합니다.",
        }

    return None


def run_one_model_turn(call: ToolCall) -> dict:
    """모델의 Tool Call을 callback을 거쳐 실행합니다."""
    blocked_result = before_tool_callback(call)

    if blocked_result is not None:
        print("[Callback 차단] Tool 함수는 실행되지 않았습니다.")
        return blocked_result

    if call.name == "search_repository":
        return search_repository(**call.args)

    raise RuntimeError("등록은 되었지만 실행 코드가 없습니다.")


print("=== 정상 호출 ===")
print(run_one_model_turn(
    ToolCall(name="search_repository", args={"pattern": "PORT"})
))

print("\n=== 잘못된 호출 ===")
print(run_one_model_turn(
    ToolCall(name="delete_repository", args={"path": "."})
))
```

실행 명령입니다.

```powershell
python tool_call_lesson.py
```

정상 호출은 다음 순서입니다.

```text
모델이 Tool Call 생성
  -> before callback이 검사
  -> None 반환
  -> 실제 Tool 실행
  -> Tool 결과가 모델에게 전달
```

잘못된 호출은 다음 순서입니다.

```text
모델이 Tool Call 생성
  -> before callback이 검사
  -> dictionary 반환
  -> 실제 Tool은 실행되지 않음
  -> dictionary가 Tool 결과처럼 모델에게 전달
```

ADK 공식 문서도 `before_tool_callback`이 `None`을 반환하면 Tool이 실행되고,
dictionary를 반환하면 Tool 실행을 건너뛰고 그 dictionary를 결과로 사용한다고 설명합니다.
[ADK Before Tool Callback 공식 문서](https://adk.dev/callbacks/types-of-callbacks/)

### 12살도 이해할 수 있는 비유

모델은 요리사이고 Tool은 주방 도구입니다.

- 모델: “냄비로 물을 끓여 주세요.”
- Tool Call: 요리사가 주방에 제출하는 주문서
- `before_tool_callback`: 주방장이 주문서를 검사하는 단계
- 실제 Tool: 주방 도구를 사용하는 단계
- Tool 결과: 끓인 물을 요리사에게 돌려주는 단계

주방장이 주문서를 거절했다면 냄비가 실제로 움직이면 안 됩니다. 현재 코드의 가장
중요한 문제는 주문서를 거절하면서 주방의 다음 작업 순서표까지 함께 바꾸는 데 있습니다.

---

## 1. ADK Tool Call의 기본 흐름

ADK에서 Tool은 모델이 사용할 수 있는 개발자 작성 함수입니다. 모델이 함수의 이름과
인자를 선택하고, ADK가 해당 함수를 실행한 뒤 결과를 다시 모델에게 전달합니다.

공식 문서의 기본 흐름은 다음과 같습니다.

```text
1. Reasoning      모델이 무엇을 조사할지 생각
2. Selection      사용할 Tool 선택
3. Invocation     Tool 이름과 arguments 생성
4. Observation    Tool 결과 수신
5. Finalization   결과를 바탕으로 다음 Tool 또는 최종 답변 선택
```

[ADK Custom Tools 공식 문서](https://adk.dev/tools-custom/)

현재 프로젝트에 대입하면 다음과 같습니다.

```text
Solar 모델
  -> inspect_target
  -> search_text / read_file / read_file_lines
  -> validate_analysis
  -> accepted AnalysisResult
```

중요한 점은 모델이 Repository를 직접 읽는 것이 아니라는 점입니다.

```text
모델: “pom.xml을 찾아야겠다.”
  -> find_files(pattern="**/pom.xml")라는 주문서를 생성
  -> Python Repository Tool이 실제 파일을 읽음
  -> 결과를 모델에게 반환
```

모델은 판단하고, Python은 실제 안전 경계와 파일 읽기를 담당합니다. 이것이 현재
프로젝트가 “Agent는 판단, Python은 guardrail” 구조를 사용하는 이유입니다.

---

## 2. Callback은 언제 실행되는가

현재 프로젝트에서 사용 중인 callback은 세 가지입니다.

```python
Agent(
    after_model_callback=toolset.after_model_callback,
    before_tool_callback=toolset.before_tool_callback,
    on_tool_error_callback=toolset.on_tool_error_callback,
)
```

### 2.1 `after_model_callback`

모델이 응답을 만든 직후, ADK가 그 응답을 다음 단계로 넘기기 전에 실행됩니다.

현재 코드 위치:

- [`migration_assistant/adk_tools.py:328`](../migration_assistant/adk_tools.py:328)

현재 역할:

- 여러 Tool Call 차단
- 등록되지 않은 Tool 이름 차단
- Tool 이름 정규화
- adapter 오류 기록

공식 문서의 용도는 모델 응답 검사·수정·민감정보 필터링·특정 오류 처리입니다.
[ADK After Model Callback 공식 문서](https://adk.dev/callbacks/types-of-callbacks/)

### 2.2 `before_tool_callback`

모델이 Tool Call을 만든 뒤, 실제 Tool 함수가 실행되기 직전에 실행됩니다.

현재 코드 위치:

- [`migration_assistant/adk_tools.py:396`](../migration_assistant/adk_tools.py:396)

현재 역할:

- 공개 Tool allowlist 확인
- malformed adapter 응답 처리
- argument schema 검사
- duplicate 검사
- 현재 phase 검사
- budget 검사
- recovery lease 승인

이 callback은 “실행 전 문지기”입니다. Repository를 실제로 읽기 전에 차단할 수 있다는
점이 가장 중요합니다.

### 2.3 `on_tool_error_callback`

Tool binding이나 실행 과정에서 예외가 발생했을 때 오류를 모델이 이해할 수 있는
envelope으로 바꿉니다.

현재 코드 위치:

- [`migration_assistant/adk_tools.py:486`](../migration_assistant/adk_tools.py:486)

설치된 현재 ADK `Agent` 생성자의 실제 signature에도 `on_tool_error_callback`이
존재하는 것을 확인했습니다. 다만 오류 callback은 사용 중인 ADK 버전의 동작 차이가
있을 수 있으므로, 직접 호출하는 단위 테스트뿐 아니라 실제 `Runner`를 통과하는
통합 테스트가 필요합니다.

---

## 3. 현재 코드에서 가장 먼저 고쳐야 할 문제

### 문제 A. Phase 오류가 이전 recovery 상태를 덮어씁니다

현재 `validate_analysis`가 잘못된 Evidence excerpt를 제출하면 다음과 같은 상태가
만들어집니다.

```text
evidence_grounding
허용: search_text, read_file, read_file_lines
후속: validate_analysis
```

이 뜻은 다음과 같습니다.

```text
새로운 관찰 Tool을 최대 1회 실행
  -> 수정된 전체 candidate를 validate_analysis에 제출
```

그런데 모델이 관찰 전에 `validate_analysis`를 다시 호출하면 현재 코드는 다음처럼
동작합니다.

```text
evidence_grounding
  -> invalid_arguments / category=state / $.name
  -> 기존 follow_up_actions가 빈 값으로 바뀜
  -> stop_requested는 False
```

현재 코드의 관련 부분입니다.

```python
# migration_assistant/adk_tools.py
argument_issue = declared_tool.argument_issue(args)
if argument_issue is not None:
    self._record_issue(argument_issue, ...)
    return error_envelope(...)

if name not in allowed:
    self._record_issue(issue, ...)
    return error_envelope(...)

disposition = self.control.authorize_action(name, allowed)
```

phase 위반은 `authorize_action()`보다 먼저 반환됩니다.

### 왜 문제인가요?

학교 복도에 다음 안내문이 있다고 생각해 보겠습니다.

```text
지금은 1번 교실에서 자료를 확인한 뒤 2번 교실로 가세요.
```

학생이 바로 2번 교실로 가면 선생님은 “순서가 잘못되었습니다”라고 하고 멈춰야
합니다. 그런데 현재 코드는 안내문을 지우고 “다시 아무 교실이나 가도 됩니다”처럼
상태를 바꿉니다.

### 어떻게 개선해야 하나요?

phase 위반은 다음 세 가지를 지켜야 합니다.

```text
1. 기존 grounding 후속 상태를 덮어쓰지 않음
2. 허용되지 않은 action이면 즉시 bounded STOP
3. Repository Tool을 실행하지 않음
```

권장 순서는 다음입니다.

```text
등록 Tool 확인
  -> duplicate 확인
  -> 현재 phase allowlist 확인
  -> argument schema 확인
  -> budget 확인
  -> recovery lease 승인
  -> 실제 Tool 실행
```

그리고 모든 상태 변경은 다음처럼 “판정”과 “커밋”을 분리해야 합니다.

```python
decision = control.decide(tool_name, args)

if decision.reject:
    # 오류를 반환하지만 기존 상태를 함부로 덮어쓰지 않습니다.
    return error_envelope(
        decision.issue,
        allowed_next_actions=decision.allowed_actions,
    )

# 여기까지 통과한 경우에만 lease와 phase를 변경합니다.
control.commit(decision)
return None
```

---

### 문제 B. argument 오류와 phase 오류가 섞입니다

현재 코드는 argument 검사를 phase 검사보다 먼저 합니다.

그래서 grounding repair 중에 `status="bad"`인 candidate를 보내면 원래는 다음처럼
나와야 합니다.

```text
phase 오류
category=state
field=$.name
```

하지만 현재 결과는 다음입니다.

```text
candidate_schema
category=validation
field=$.status
```

이것은 모델에게 “지금은 validate를 하면 안 된다”가 아니라 “status만 고쳐라”라고
잘못 알려주는 셈입니다.

### 왜 문제인가요?

교통 신호등으로 비유하면, 빨간불인데 자동차의 타이어 공기압부터 검사하는
상황입니다. 먼저 “지금 출발해도 되는가”를 판단하고, 출발이 허용된 뒤에 자동차의
세부 상태를 검사해야 합니다.

### 개선 방향

다음 순서를 계약 테스트로 고정해야 합니다.

```python
duplicate = check_duplicate(call)
if duplicate:
    return duplicate_error()

phase_error = check_phase(call)
if phase_error:
    return phase_error

argument_error = check_schema(call)
if argument_error:
    return argument_error
```

그러면 모델이 잘못된 phase에서 엉터리 candidate를 보내도, candidate 내부의
`$.status`보다 먼저 현재 실행 순서가 잘못되었다는 사실을 알 수 있습니다.

---

### 문제 C. `after_model_callback`이 응답 객체를 직접 수정합니다

현재 코드입니다.

```python
call.name = canonical_name
llm_response.custom_metadata = {
    **metadata,
    "canonicalized_calls": canonicalized,
}
```

`call.name`을 원래 `LlmResponse` 안에서 직접 바꾸고 있습니다.

### 왜 문제인가요?

택배 상자를 생각해 보겠습니다.

- 원래 송장: `read_fileargs`
- 정규화된 이름: `read_file`

택배 접수 기록은 원래 송장을 보관해야 하는데, 현재 코드는 송장 자체의 글자를
바꿉니다. 그러면 나중에 “고객이 처음 무엇을 적었는가?”와 “우리가 무엇으로
고쳤는가?”를 구분하기 어려워집니다.

### 개선 방향

ADK 공식 예시처럼 response와 parts를 복사한 후 새 응답을 반환하는 편이 안전합니다.

```python
from copy import deepcopy

parts = [deepcopy(part) for part in llm_response.content.parts]
parts[index].function_call.name = canonical_name

return LlmResponse(
    content=types.Content(role="model", parts=parts),
    custom_metadata={
        **(llm_response.custom_metadata or {}),
        "canonicalized_calls": canonicalized,
    },
)
```

원본 response와 수정된 response를 분리하면 trajectory 분석도 다음처럼 명확해집니다.

```text
model_original_name = read_fileargs
dispatch_name       = read_file
```

---

### 문제 D. callback context 타입이 `object`입니다

현재 코드의 형태입니다.

```python
def before_tool_callback(
    self,
    tool: object,
    args: dict[str, Any],
    tool_context: object,
):
    ...
```

공식 ADK callback은 callback 종류에 맞는 context를 사용합니다.

```python
from google.adk.agents import CallbackContext
from google.adk.tools.tool_context import ToolContext


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

공식 문서는 callback에서 올바른 context 타입을 사용해야 state, invocation 정보,
callback action 같은 실행 정보를 안전하게 사용할 수 있다고 설명합니다.
[ADK Callback Context 공식 문서](https://adk.dev/callbacks/types-of-callbacks/)

현재 `object`가 즉시 실행을 깨뜨리는 것은 아닙니다. 하지만 IDE와 type checker가
다음 실수를 잡아주지 못합니다.

```python
tool_context.invocation_id
tool_context.state
tool_context.actions
```

---

### 문제 E. Tool 성공 후 처리가 `_call()`에 너무 많이 들어 있습니다

현재 [`adk_tools.py:551`](../migration_assistant/adk_tools.py:551)의 `_call()`은 다음을
모두 수행합니다.

```text
Tool 실행
중복 검사
Repository 오류 처리
ledger 기록
provenance 기록
budget 상태 정리
phase 변경
recovery 후속 상태 정리
```

ADK의 `after_tool_callback`은 Tool이 성공한 직후 결과를 기록하거나 수정하기 위한
자리입니다. [ADK After Tool Callback 공식 문서](https://adk.dev/callbacks/types-of-callbacks/)

현재 구조가 당장 틀렸다는 뜻은 아닙니다. 모든 public Tool이 `_call()`을 통과하므로
공통 처리가 빠지는 것을 막고 있습니다. 다만 앞으로 Tool을 하나 추가할 때 다음
질문을 반드시 기억해야 합니다.

```text
이 Tool도 _call()을 사용했는가?
provenance가 기록되는가?
phase가 올바르게 바뀌는가?
duplicate가 같은 방식으로 처리되는가?
```

장기적으로는 다음처럼 분리하는 것이 이해하기 쉽습니다.

```text
before_tool_callback
  -> 실행 허용/차단

Tool 함수
  -> read-only Repository 관찰

after_tool_callback
  -> 성공 결과 기록 및 provenance 기록

on_tool_error_callback
  -> 오류 envelope 및 recovery 처리
```

---

### 문제 F. recovery prompt가 일반 user 메시지로 들어갑니다

현재 [`adk_runner.py:183`](../migration_assistant/adk_runner.py:183)은 recovery를 다음처럼
새로운 user message로 보냅니다.

```python
recovery = types.Content(
    role="user",
    parts=[types.Part(text=_recovery_prompt(...))],
)
```

장점은 recovery를 별도 turn으로 명확히 제한할 수 있다는 점입니다. 다만 모델과
session history에서는 실제 사용자가 보낸 문장처럼 보일 수 있습니다.

ADK의 `before_model_callback`은 LLM 요청 직전에 state에 따라 request를 수정하는
용도로 설계되어 있습니다. [ADK Before Model Callback 공식 문서](https://adk.dev/callbacks/types-of-callbacks/)

따라서 장기적으로는 다음 구조를 검토할 수 있습니다.

```text
외부 사용자 메시지
  -> session history

recovery 상태
  -> invocation-local control 또는 임시 state

before_model_callback
  -> 내부 recovery instruction을 model request에 추가
```

다만 현재 MVP의 “recovery turn 1회” 계약을 유지해야 하므로, 이 항목은 첫 번째
수정 대상이 아니라 phase 상태 문제를 고친 뒤 검토할 항목입니다.

---

## 4. ADK 공식 원칙과 현재 코드 비교표

| 공식 원칙 | 현재 코드 | 판정 |
|---|---|---|
| before callback에서 실행 전 guardrail 적용 | `before_tool_callback`에서 Repository 실행 전 차단 | 잘 되어 있음 |
| dictionary 반환 시 Tool 실행 생략 | `error_envelope()` 반환 | 잘 되어 있음 |
| callback은 한 가지 책임에 집중 | before callback이 schema·phase·budget·recovery를 모두 담당 | 개선 필요 |
| callback 오류는 graceful하게 처리 | 오류를 envelope으로 변환 | 잘 되어 있음 |
| callback 상태는 명확히 관리 | 별도 `RunControlLedger` 사용 | 의도는 좋지만 전이 원자성 필요 |
| 상태는 context state로 추적 가능 | `tool_context`를 `object`로 숨김 | 개선 필요 |
| 재실행에 안전한 idempotency | callback이 retry count와 fingerprint를 직접 변경 | 검토 필요 |
| after tool에서 결과 후처리 | `_call()` 안에 후처리 집중 | 개선 필요 |
| 실제 lifecycle 통합 테스트 | callback 직접 호출 테스트 중심 | 보강 필요 |

공식 best practice는 callback을 한 가지 목적에 집중하고, callback이 동기 실행 루프를
막지 않도록 하며, 상태를 명확히 관리하고, 재시도에 안전하게 설계하라고 권장합니다.
[ADK Callback Design Patterns 공식 문서](https://adk.dev/callbacks/design-patterns-and-best-practices/)

---

## 5. 초보자가 반드시 구분해야 하는 세 가지 오류

### 5.1 모델 입력 오류

예시:

```text
read_file_lines(line_end=abc)
```

Tool 이름은 맞지만 인자가 틀렸습니다.

```text
책임: 모델
정상 반응: 같은 Tool의 올바른 인자 1회
Repository 실행: 하지 않음
```

### 5.2 모델 상태 선택 오류

예시:

```text
grounding 오류 후 바로 validate_analysis 재호출
```

인자는 멀쩡할 수 있지만 지금 phase에서 그 Tool을 부르면 안 됩니다.

```text
책임: 모델의 순서 선택 + runtime의 명확한 차단
정상 반응: 허용된 observation 1회 또는 즉시 bounded STOP
```

### 5.3 runtime recovery 오류

예시:

```text
phase 오류가 기존 grounding follow-up을 덮어씀
```

모델이 처음 잘못했더라도 runtime이 오류 정보를 더 혼란스럽게 만들면 안 됩니다.

```text
책임: runtime
정상 반응: 기존 상태 보존, 원래 오류와 허용 action 전달
```

이 세 가지를 모두 `invalid_arguments` 하나로 세면 원인을 알 수 없습니다.

---

## 6. 오늘 저녁 학습 순서

### 1단계: 15분 — 장난감 예제 실행

위의 `tool_call_lesson.py`를 직접 실행하고 다음을 확인합니다.

```text
callback이 dictionary를 반환하면 실제 함수가 실행되지 않는다.
```

### 2단계: 20분 — 공식 문서 읽기

다음 순서로 읽으시면 됩니다.

1. [ADK Custom Tools](https://adk.dev/tools-custom/)
2. [ADK Function Tools](https://adk.dev/tools/function-tools/)
3. [ADK Types of Callbacks](https://adk.dev/callbacks/types-of-callbacks/)
4. [ADK Callback Design Patterns](https://adk.dev/callbacks/design-patterns-and-best-practices/)
5. [ADK State](https://adk.dev/sessions/state/)

### 3단계: 20분 — 현재 코드 읽기

다음 파일만 읽으시면 됩니다.

```text
migration_assistant/agent.py
migration_assistant/adk_tools.py
migration_assistant/tool_protocol.py
migration_assistant/adk_runner.py
```

읽는 순서는 다음과 같습니다.

```text
agent.py
  -> 어떤 callback이 등록되는가

adk_tools.py
  -> callback에서 무엇을 검사하는가

tool_protocol.py
  -> 검사 결과가 어떤 상태를 바꾸는가

adk_runner.py
  -> 오류 뒤 stream과 recovery turn이 어떻게 이어지는가
```

### 4단계: 20분 — deterministic test 실행

```powershell
python -m pytest -q -p no:cacheprovider `
  tests/test_adk_runner_recovery.py `
  tests/test_phase1_adk_contract.py
```

현재 기준 결과는 `46 passed`입니다.

### 5단계: 15분 — 다음 질문에 답하기

아래 질문에 답할 수 있으면 기본기를 갖춘 것입니다.

1. `before_tool_callback`이 `None`을 반환하면 무엇이 실행됩니까?
2. dictionary를 반환하면 무엇이 실행되지 않습니까?
3. grounding 오류 뒤 바로 validate하면 현재 어떤 오류가 나옵니까?
4. phase 오류가 `authorize_action()`보다 먼저 반환되는 이유는 무엇입니까?
5. `call.name = canonical_name`이 원본 history에 미칠 수 있는 영향은 무엇입니까?

---

## 7. 개선 작업의 권장 순서

### 1순위: phase/recovery 상태 전이 수정

목표:

```text
phase 오류가 기존 grounding follow-up을 지우지 않음
허용되지 않은 action은 bounded STOP
observation 최대 횟수를 우회하지 못함
```

### 2순위: callback 계약 테스트 추가

반드시 고정할 trajectory입니다.

```text
grounding
  -> 잘못된 validate
  -> phase 오류
  -> 추가 observation 허용 여부 확인

candidate schema
  -> 잘못된 candidate
  -> 같은 candidate 반복
  -> handler validation 0회인지 확인
```

### 3순위: `after_model_callback` 불변 응답 처리

목표:

```text
원본 모델 call name 보존
정규화된 dispatch name 별도 기록
call linkage와 history 불일치 방지
```

### 4순위: context 타입과 invocation telemetry 보강

목표:

```text
agent_name
invocation_id
tool_name
call_id
phase
issue code
```

단, raw arguments와 Secret은 계속 기록하지 않아야 합니다.

### 5순위: 실제 Runner 통합 테스트

callback 함수를 직접 호출하는 테스트만으로는 ADK가 실제로 어떤 순서로 callback을
호출하는지 보장할 수 없습니다. 최소 한 개의 fake LLM과 실제 ADK `Runner`를 사용해
다음 내용을 검사해야 합니다.

```text
model response
  -> after_model_callback
  -> before_tool_callback
  -> Tool 또는 callback 반환 dictionary
  -> function response
  -> 다음 model call
```

---

## 8. 최종 요약

현재 코드는 “모델이 위험한 Tool을 직접 실행하지 못하게 막는 구조”는 잘 갖추고
있습니다. 문제가 되는 부분은 callback을 너무 많이 사용해서, 한 번의 잘못된 Tool
Call이 다음 상태까지 바꾸는 점입니다.

가장 먼저 기억하실 문장은 이것입니다.

> callback은 문지기이고, 상태 머신은 판정 결과를 기록하는 별도 관리자여야 합니다.

현재는 문지기가 동시에 관리자 역할까지 하고 있습니다. 그래서 phase 오류가
grounding recovery 상태를 덮어씁니다.

개선 순서는 다음 한 줄로 기억하시면 됩니다.

```text
phase 상태 보존
  -> callback 판정/상태 커밋 분리
  -> 원본 LLM response 복사 처리
  -> after_tool 후처리 분리
  -> 실제 Runner 통합 테스트
```

이 순서대로 진행하면 ADK의 Tool Call을 전부 외우지 않아도 현재 실패 trajectory를
코드 한 줄씩 역추적할 수 있습니다.

문서 작성 기준일: 2026-08-06
