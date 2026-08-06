# Phase 1 ADK 실험 기록

이 문서는 Google ADK Agent/Runner와 OpenAI-compatible model adapter를 연결할 때
발생한 문제를 재현 가능한 가설과 관찰로 남기는 학습용 기록이다. API key, 전체
request body, system prompt 원문, model reasoning, 실제 secret 값은 기록하지 않는다.

## 실험 목적

- 하나의 Google ADK `Agent`와 `Runner`가 정확히 8개 Repository Tool을 사용한다.
- Solar Pro 3 OpenAI-compatible endpoint에서 탐색 tool call과 후속 turn을 유지한다.
- Agent가 관찰 결과를 바탕으로 `validate_analysis`를 호출하고 실제 Pydantic
  `AnalysisResult`를 통과한다.
- 실패 시 fake planner로 우회하지 않고, partial/failed/configuration을 구분한다.

## 기준과 안전 조건

- 승인 model profile: `LLM_MODEL=solar-pro3`, endpoint는 configured 여부만 취급한다.
- 매 live 실행은 Spring PetClinic 입력 Repository를 read-only로 사용하고 새로운
  sibling output directory를 사용했다.
- 입력 Repository Git status는 각 실행 전후 동일한지 확인했다.
- 결과 artifact는 `analysis-result.json`과 `analysis-report.md`가 생성됐는지 확인했다.
- 이 문서에는 output directory 이름과 공개된 실패 분류만 기록한다.

## 문제를 푸는 관점

| 관점 | 질문 | 판별 신호 |
|---|---|---|
| Provider/API | endpoint가 tool call 자체를 지원하는가? | 최소 chat, nested function 요청의 HTTP 성공 여부 |
| ADK lifecycle | ADK가 tool response를 다음 model turn에 전달하는가? | 실제 Agent/Runner에서 2개 이상의 turn과 tool response 확인 |
| Schema boundary | Gemini/OpenAPI schema가 OpenAI JSON Schema로 변환됐는가? | 함수 이름에 인자가 붙거나 인자 JSON이 깨지는 현상 |
| Agent behavior | 모델이 충분한 탐색 후 검증 tool을 선택하는가? | `validate_analysis` 호출 여부, 중복/no-progress 여부 |
| Context budget | 전체 대화가 너무 커져 후반 행동 품질이 떨어지는가? | 반복 search, timeout, prose 종료, iteration별 payload 증가 |
| Application contract | Pydantic/exit/artifact가 결과를 올바르게 분류하는가? | schema error가 성공으로 위장되지 않는지 |

## 시행착오와 관찰

### 초기 live 시도들: ADK 경계가 아직 불안정한 상태

초기 1~11회 실행에서는 다음 현상이 번갈아 나타났다.

- provider 응답의 함수 이름이 공개 tool 이름과 다르게 변형됐다. 예를 들어
  underscore가 사라지거나 함수 이름 뒤에 인자 JSON이 붙었다.
- `.git` 경로 요청이 안전 경계에서 거부되었고, 일부 실행은 같은 tool call을
  반복하여 no-progress로 종료됐다.
- line range가 실제 file 범위를 넘는 요청이 발생했다.
- structured final candidate에서 `status`가 빠지거나, 일반 prose가 반환되었다.
- 실제 tool call 뒤 후속 turn은 도달했지만, 최종 `validate_analysis`까지 가지 못했다.

초기 결론은 “Solar Pro 3와 ADK가 기술적으로 연결 불가”가 아니었다. 실제로
최소 chat completion, ADK tool call, tool response 이후 후속 turn까지 성공했기
때문이다. 따라서 provider 교체나 fake planner 우회는 하지 않고 adapter와
termination protocol을 계속 검증했다.

### 독립 코드 리뷰에서 세운 가설

Claude의 읽기 전용 검토에서 다음 가설을 얻었다.

1. ADK의 `google.genai.types.Schema`는 `OBJECT`, `STRING` 같은 Gemini enum을
   포함할 수 있는데 OpenAI-compatible JSON Schema는 보통 lowercase type을
   기대한다. 이 변환 누락이 malformed function name/arguments를 만들 수 있다.
2. `validate_analysis(analysis: dict[str, object])`는 model에게 내부 필드 구조를
   거의 보여주지 못한다. 전체 candidate의 top-level field를 간단한 function
   parameters로 노출하는 편이 provider-neutral하다.
3. validation 성공 뒤에도 Runner가 다음 turn을 기다리면 budget/no-progress가
   성공 결과를 partial로 덮어쓸 수 있다. `ledger.result`를 관찰하는 즉시 같은
   Agent/Runner generator를 닫아야 한다.
4. 실패 fallback에서 이미 수집한 line-backed observation을 버리면 partial도
   학습 가능한 결과가 되지 않는다.
5. search hit와 file response가 커지면 ADK가 매 turn history 전체를 다시 보내므로
   후반 timeout/prose 종료 가능성이 높아진다.

### 적용한 실험 변수

- `_tools()`에서 ADK schema를 OpenAI JSON Schema로 재귀 변환했다. `type`을
  lowercase로 바꾸고 provider-specific이 아닌 schema dialect 차이만 경계에서
  처리했다. `nullable`, `propertyOrdering`, `example` 등 호환성 위험 필드는
  전달하지 않는다.
- `validate_analysis`를 `status`, `summary`, `evidence`, `iterations`, `errors`
  의 flat function parameters로 바꿨다. 최종 candidate 전체가 한 번의 tool call에
  들어가며, 내부 결과는 여전히 실제 Pydantic `AnalysisResult`로 검증한다.
- ledger에 search/read line observation을 보존하고, no-progress/parse 실패의
  partial artifact에도 관찰된 line evidence를 남긴다.
- `validate_analysis` 성공 즉시 ADK event loop를 종료한다. 성공 결과를 후속
  budget exhaustion이 덮어쓰지 않도록 했다.
- default search result cap을 200에서 64, tool response cap을 256 KiB에서
  48 KiB로 줄였다. 이는 정확성 변경이 아니라 history/context 안전 경계 실험이다.

## Live 실행 기록

### Run 12 — schema/flat validation 이후 첫 회귀 실험

- output: `spring-petclinic-phase1-remediation-20260801-12`
- 실제 ADK Agent/Runner가 실행됐고 iteration은 14였다.
- line-backed evidence 100개가 artifact에 남았다.
- 상태는 `partial`, exit code는 2였다.
- `analysis-result.json`, `analysis-report.md`는 생성됐다.
- 공개된 실패 분류: structured final parsing failure와 잘못된 line range 한 건.
- 입력 Repository Git status는 unchanged였다.

해석: schema 변환으로 tool 탐색은 상당히 회복됐지만, search context가 커진
후반에 Agent가 `validate_analysis` 대신 prose로 종료했다. 아직 provider
incompatibility의 증거는 아니다.

### Run 13 — context cap 감소 가설

Run 12와 비교한 변수는 search hit cap과 개별 tool response 크기였다. 실제로
evidence 수는 100에서 64로 줄었지만 Agent는 24 iteration 뒤에도
`validate_analysis` 대신 prose로 종료했다. 상태는 `partial`, exit code는 2였고
artifact/input Git 조건은 유지됐다. context 크기만 줄이는 것으로는 충분하지
않다는 가설을 세웠다.

### Run 14 — malformed validation call 복구 가설

- output: `spring-petclinic-phase1-remediation-20260801-14`
- 실제 ADK 경로에서 iteration 1, confirmed line evidence 10개가 생성됐다.
- 모델은 `validate_analysis`를 선택했지만 필수 `summary` field를 누락했다.
- 상태는 `failed`, exit code는 1이었다.
- artifact 두 개는 생성됐고 입력 Repository Git status는 unchanged였다.

해석: Run 14는 “tool을 전혀 탐색하지 못한다”는 가설과 다르다. Agent가 승인된
종료 tool까지 도달했지만 ADK automatic function calling의 mandatory argument
검사에서 멈췄다. 기존 recovery 조건은 prose final만 대상으로 했기 때문에 이
malformed tool call을 재질문하지 못했다. 다음 실험에서는 tool call/validation
오류도 같은 Agent와 session에서 한 번 복구하도록 변경한다.

### Run 15 — 실제 validate_analysis 도달 및 partial 사유 검증

- output: `spring-petclinic-phase1-remediation-20260801-15`
- Agent/Runner가 26 iteration 수행, confirmed line evidence 4개를 남겼다.
- `validate_analysis`를 통해 candidate가 Pydantic을 통과했지만 status는 `partial`이었다.
- exit code는 2였고 artifact 두 개와 input Git unchanged 조건은 만족했다.
- candidate의 errors가 비어 있어 partial 사유 계약은 부족했다.

해석: ADK tool 탐색과 실제 Pydantic validation 통로는 작동한다. 하지만 모델이
“준비를 완료했다”는 summary와 `partial` status를 혼합할 수 있으므로, partial은
반드시 `errors`에 genuine unresolved repository ambiguity를 기록하도록 Pydantic
계약을 강화했다. 다음 live 실험에서 이 validation feedback이 complete 또는
근거 있는 partial로 회복되는지 확인한다.

### Run 16 — partial 사유 feedback의 첫 검증

- output: `spring-petclinic-phase1-remediation-20260801-16`
- 32 iteration, confirmed evidence 64개까지 수집했다.
- 모델은 partial candidate를 반복 제출했지만 `errors=[]`를 유지했다.
- Pydantic은 이를 정확히 거부했고, line evidence response budget 및 invalid range
  feedback도 함께 관찰됐다. 최종 상태는 `failed`, exit code는 1이었다.
- artifact 두 개와 input Git unchanged는 유지됐다.

해석: Pydantic fail-closed는 작동했지만, optional parameter는 model에게 너무
약한 신호였다. 다음에는 `iterations`와 `errors`도 ADK function schema상 required로
만들고, recovery prompt에 partial reason 규칙을 직접 명시한다.

### Run 17 — required field 이후 duplicate/no-progress 가설

- output: `spring-petclinic-phase1-remediation-20260801-17`
- 32 iteration, confirmed evidence 40개를 수집했다.
- required validation field 누락은 없었지만 동일 Tool 반복으로 종료됐다.
- 상태는 `partial`, exit code는 2였고, 원인은 genuine repository ambiguity가
  아니라 no-progress였다. artifact 두 개와 input Git unchanged는 유지됐다.

해석: validation schema는 개선됐지만 모델이 충분한 근거 이후에도 탐색을 이어가며
잘못된 line range/반복 호출에 빠질 수 있다. 다음에는 검색 context를 더 작게 하고,
duplicate feedback에 canonical tool/args를 노출하며, “몇 개의 line evidence면 즉시
검증” 규칙을 더 선명하게 한다.

### Run 18 — secret redaction과 complete 판단

- output: `spring-petclinic-phase1-remediation-20260801-18`
- duplicate/no-progress는 발생하지 않았고, confirmed evidence 4개로 검증 tool에
  도달했다.
- 모델은 DB password 값이 redacted되어 확인할 수 없다는 이유로 partial을 제출했다.
- 상태는 `partial`, exit code는 2였고 artifact 두 개 및 input Git unchanged는
  유지됐다.

해석: secret 값은 계약상 절대 필요하지 않다. Agent가 secret의 이름/위치/필요성은
근거로 사용하되 값의 redaction을 분석 불가능으로 오해하지 않도록 prompt를
보강한다. 이 실험은 tool protocol 실패가 아니라 Agent 판단 기준의 문제다.

### Run 19 — Evidence status vocabulary 검증

- output: `spring-petclinic-phase1-remediation-20260801-19`
- 10 iteration, 실제 artifact에는 fallback으로 보존된 confirmed evidence 64개가
  남았다.
- model structured result의 일부 Evidence에 허용되지 않은 `status=absence`가
  포함됐다.
- Pydantic validation이 이를 거부했고 exit code는 2(partial fallback)였다.
- artifact 두 개와 input Git unchanged는 유지됐다.

해석: Evidence status vocabulary를 prompt에 설명했어도 final structured response가
계약 밖 값을 만들 수 있다. 다음 recovery prompt에 `absence -> unresolved` 매핑과
상태별 필수 field를 반복해 schema feedback을 더 직접적으로 제공한다.

### Run 20 — 근거 없는 partial 차단

- output: `spring-petclinic-phase1-remediation-20260801-20`
- 15 iteration 후 model이 k8s 설정의 핵심 근거가 부족하다는 partial을 제출했다.
- 그러나 evidence가 0개였다. 현재 contract에서는 errors만 있으면 partial이
  통과하는 빈틈이 확인됐다.
- exit code는 2였고 artifact 두 개 및 input Git unchanged는 유지됐다.

해석: 사용자 acceptance 조건상 partial에도 non-empty line-backed evidence가
필수다. Pydantic에서 partial도 최소 하나의 positive line evidence를 요구하도록
강화해 근거 없는 partial을 fail-closed로 만든다.

### Run 21 — optional 운영 요소 부재와 complete 기준

- output: `spring-petclinic-phase1-remediation-20260801-21`
- 7 iteration, confirmed line evidence 8개로 `validate_analysis`를 통과했다.
- partial 사유는 Helm, Ingress, PVC/Storage, ConfigMap/Secret binding, Service
  관련 요소가 발견되지 않았다는 repository 관찰이었다.
- 상태는 `partial`, exit code는 2였으며 duplicate, budget, parsing 실패는 없었다.
- artifact 두 개와 input Git unchanged는 유지됐다.

해석: 이 partial은 protocol 실패가 아니라 Agent의 completeness 판단이다. 기본
분석의 complete 기준은 component/build/runtime 근거이며, 선택적 운영 요소의
부재만으로 partial을 강제하지 않도록 prompt를 보강한다. 부재 자체가 중요한
사실이면 unresolved Evidence로 남기되, 분석을 완료할 수 있다.

### Run 22 — bounded conversation history 가설

- output: `spring-petclinic-phase1-remediation-20260801-22`
- 35 iteration, confirmed evidence 30개를 수집했다.
- 최종 실패는 `AdapterTransportError`의 endpoint read timeout이었다.
- 상태는 `failed`, exit code는 1이었고 artifact 두 개와 input Git unchanged는
  유지됐다. duplicate/no-progress나 Pydantic 오류가 주원인은 아니었다.

해석: OpenAI-compatible adapter가 ADK의 전체 tool history를 매 turn 재전송해
context가 계속 커졌다. 다음에는 assistant tool call과 대응 tool response를
한 덩어리로 유지하면서 오래된 덩어리를 bounded compaction한다. 생략된 관찰은
추정하지 말라는 안내를 추가해 context trimming이 근거를 합성하지 않도록 한다.

### Run 23 — bounded history 후 malformed tool name 변형

- output: `spring-petclinic-phase1-remediation-20260801-23`
- endpoint timeout은 발생하지 않았고 12 iteration, confirmed evidence 62개를
  수집했다.
- provider 응답의 `read_filearg`가 공개 tool registry에 전달되어 ADK dispatch가
  실패했다. 상태는 `failed`, exit code는 1이었다.
- artifact 두 개와 input Git unchanged는 유지됐다.

해석: history compaction은 timeout 가설을 지지했지만, provider-neutral boundary의
malformed name normalizer가 singular `arg` 변형을 놓쳤다. `arg/args/argument(s)`
suffix를 공개 tool 이름으로 복원하되, 실제 인자 JSON은 그대로 model이 제공한
값만 사용하도록 수정한다.

### Run 24 — genuine unresolved image registry ambiguity

- output: `spring-petclinic-phase1-remediation-20260801-24`
- timeout, duplicate/no-progress, budget exhaustion, malformed final 오류 없이
  6 iteration에서 `validate_analysis`를 통과했다.
- confirmed line-backed evidence 3개가 남았고 상태는 `partial`, exit code는 2였다.
- Agent summary는 Spring Boot component와 Kubernetes YAML을 근거로 설명했고,
  Repository 안에 image registry URL/imagePullSecrets가 명시되지 않아 외부
  registry 사용 여부를 결정할 수 없다는 genuine unresolved 사유를 기록했다.
- `analysis-result.json`, `analysis-report.md` 생성 및 input Git unchanged를
  확인했다.

해석: 이 partial은 budget, duplicate loop, model parsing 실패가 아니라 실제
Repository가 제공하지 않는 외부 배포 정보의 ambiguity다. line-backed positive
evidence와 명시적 사유가 있으므로 사용자 계약의 partial 허용 조건을 만족한다.

## 현재까지의 ADK 인사이트

1. ADK를 붙였다는 사실보다 ADK 경계에서 실제 wire contract를 확인하는 것이
   중요하다. ADK 내부 schema와 OpenAI-compatible schema는 이름이 비슷해도
   그대로 전달하면 안 된다.
2. Tool-calling Agent에서 “최종 JSON을 출력하라”는 prompt만으로는 종료 계약이
   충분하지 않다. 검증을 tool call로 만들고, application이 `valid=true`를
   종료 신호로 취급해야 한다.
3. Tool 결과는 관찰 사실이지 Evidence status가 아니다. line-backed observation을
   ledger에 보존하되, confirmed/inferred/unresolved/conflicting 분류는 Agent가
   candidate에 명시하고 Pydantic이 구조를 검증해야 한다.
4. duplicate/no-progress는 단순 retry count가 아니라 canonical
   `(tool_name, normalized_args)` signature로 감지해야 한다. 차단 feedback은
   Agent가 다른 탐색이나 최종 검증을 선택할 수 있도록 구조화되어야 한다.
5. context budget은 파일 byte budget과 별개가 아니다. 검색 결과 수, tool response
   크기, 전체 history가 함께 모델의 후반 판단 품질을 좌우하므로 실행 budget의
   한 경계로 다뤄야 한다.

## 참고한 공개 ADK 패턴

- [Google ADK Python](https://github.com/google/adk-python): model-agnostic Agent/
  Runner와 tool lifecycle의 기준.
- [ADK issue #283](https://github.com/google/adk-python/issues/283): assistant
  tool call마다 대응하는 tool message가 필요한 OpenAI 계열 대화 규칙을 확인하는
  참고 사례.
- [ADK issue #701](https://github.com/google/adk-python/issues/701): tool calling과
  structured output을 동시에 provider에 강제할 때의 호환성 문제. 이 프로젝트는
  multi-agent formatter나 provider-specific 분기 대신 `validate_analysis` tool을
  사용한다.

## 다음 기록 규칙

각 추가 실험은 다음 다섯 항목을 반드시 남긴다.

1. 바꾼 변수 하나와 그 가설
2. 실제 실행 명령의 비밀값 제거 버전
3. tool sequence, iteration, evidence 상태 수
4. exit code와 artifact/input Git 상태
5. 다음 실험에서 유지할 것과 폐기할 것

### Run 25 — development-only live acceptance harness 도입 (live 미실행)

1. 바꾼 변수 하나와 그 가설: Runner가 관찰한 `terminal`, Secret-safe
   `protocol_issues`, tool trajectory를 `analyze()`의 선택적 handoff로 전달하고,
   별도 output directory 3개를 사용하는 harness를 도입했다. `complete` 형태만으로
   terminal 수락을 추론하지 않으면 3-of-3 gate가 실제 `validate_analysis` 수락만
   통과시킬 것이라는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전: live harness는 아직 실행하지 않았다.
   network 없는 fake runner 기반 `\.venv\Scripts\python.exe -m unittest
   tests.test_phase1_live_acceptance_harness -v`만 실행했다.
3. tool sequence, iteration, evidence 상태 수: live 실행 결과는 없어 기록할
   sequence/iteration/evidence 상태 수가 없다. 결정론적 테스트에서는
   `validate_analysis` trajectory와 positive evidence count 조건, zero-tool
   `complete` 실패 조건을 검증했다.
4. exit code와 artifact/input Git 상태: live exit code와 live artifact는 아직
   없다. fake runner 테스트는 통과했고 input Repository를 변경하지 않았다.
5. 다음 실험에서 유지할 것과 폐기할 것: 유지할 것은 run별 격리 output, terminal
   사실 전달, protocol error code만의 summary redaction, 3-of-3 gate다. 폐기할
   것은 아직 없으며, 다음 실험에서 실제 local checkout live 실행 결과를 별도로
   기록한다.

### Run 26 — jpetstore-6 live 최초 실행과 3-of-3 gate 기준선

1. 바꾼 변수 하나와 그 가설: fake runner 대신 실제 live 모델로 harness를
   실행했다. T1–T5의 typed protocol과 bounded recovery가 갖춰졌으므로 3회 연속
   `complete` + `terminal`에 도달할 것이라는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전:

   ```powershell
   python -m devtools.run_phase1_live_acceptance --repository <jpetstore-6-checkout> --output-parent <output-parent> --runs 1
   python -m devtools.run_phase1_live_acceptance --repository <jpetstore-6-checkout> --output-parent <output-parent> --runs 3
   ```

   다섯 개 LLM 설정은 모두 `~/.config/kubernetes-migration-assistant/env`에서
   로드됐다. 비밀값은 출력하지 않았다. 비-비밀 설정은 base URL
   `https://api.upstage.ai/v1`, model `solar-pro3`, timeout 60s, max_tokens 4096이다.
3. tool sequence, iteration, evidence 상태 수: 진단 1회는 20개 tool call이
   `validate_analysis`로 종료했고 positive evidence 6건이었다. 이어진 gate 3회는
   각각 11/8/14 call, iteration 13/9/17로 종료했고 evidence는 모두 0건이었다.
   protocol error code는 run별로 `invalid_arguments`+`not_found`,
   `malformed_arguments`+`candidate_schema`+`duplicate_call`,
   `invalid_arguments`였다.
4. exit code와 artifact/input Git 상태: 진단 run은 exit 0, gate 3회는 모두 exit 1로
   `passed=false`, `successes=0/3`이었다. 입력 checkout은 commit
   `3ebd25fd04f1b48361ab879e113ba353838ffe6a`에서 `git status` 빈 출력으로 무변경을
   확인했다. artifact는 target 밖 run별 분리 directory에만 기록됐다.
5. 다음 실험에서 유지할 것과 폐기할 것: 유지할 것은 run별 격리 output, terminal
   사실 전달, 무변경 target 검증이다. 폐기할 것은 "T1–T5 완료가 곧 live 신뢰성"이라는
   가정이다. 계측 실행에서 Agent가 `validate_analysis`에 도달하지만 excerpt가 실제
   line과 불일치해 `evidence_grounding`으로 거부되는 것을 확인했다. 예를 들어
   `pom.xml:13-13`은 실제로는 Apache 라이선스 헤더 줄이다. 비교 함수는 공백과 CRLF를
   무시하므로 과엄격이 아니고, `evidence_corrections`도 모델에 전달된다. 즉 거부는
   설계대로의 올바른 동작이고 원인은 모델의 line 번호 조작이다.

### Run 27 — invalid_arguments 사유 보존

1. 바꾼 변수 하나와 그 가설: Pydantic validator의 구체적 사유를 error envelope
   message에 유지하도록 고쳤다. 이전에는 모든 제약 위반이 "Tool 인자 값이 schema
   제약을 위반했습니다."로 덮여, 모델이 `read_file_lines`의 4줄 상한을 알 수 없어
   같은 호출을 반복하고 bounded recovery를 소진했다. 사유를 전달하면 반복이 줄어들
   것이라는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전: Run 26과 동일한 `--runs 3` 명령이며 모델
   설정도 동일하다. 코드 변경은 `migration_assistant/adk_function_tool.py`
   한 곳이고, 먼저 RED를 확인한 뒤 구현했다.
3. tool sequence, iteration, evidence 상태 수: run 1은 7 call로 `validate_analysis`에
   도달해 positive evidence 4건을 남겼다. run 2는 10 call, run 3은 9 call로 evidence
   0건이었다. protocol error code는 `candidate_schema`,
   `duplicate_call`+`not_found`+`duplicate_call`, `invalid_arguments`였다.
4. exit code와 artifact/input Git 상태: exit 0/1/1로 `passed=false`,
   `successes=1/3`이었다. 입력 checkout은 여전히 무변경이다. 결정론적 테스트는
   focused 55개와 전체 142개 모두 통과했다.
5. 다음 실험에서 유지할 것과 폐기할 것: 유지할 것은 사유 보존 수정이다. 0/3에서
   1/3로 올랐지만 n=3이라 개선 폭의 통계적 근거는 약하다. 폐기할 것은 "지시문 강화가
   남은 레버"라는 가정이다. `migration_assistant/agent.py`는 이미 excerpt를
   `read_file_lines` 응답에서 그대로 복사하고 `evidence_corrections`를 그대로
   재제출하라고 명시하고 있으며, 모델이 이를 따르지 않는 상태다.

### Run 28 — 출력 token 상한 상향

1. 바꾼 변수 하나와 그 가설: `LLM_MAX_TOKENS`만 4096에서 8192로 올렸다.
   `candidate_schema`와 `malformed_arguments`가 evidence 여러 건과 excerpt를 담은
   `validate_analysis` 인자의 출력 절단에서 온다면 상향으로 해소될 것이라는 가설이다.
   사용자 env 파일은 수정하지 않고 프로세스 환경변수로만 덮어썼다.
2. 실제 실행 명령의 비밀값 제거 버전: Run 26과 동일한 `--runs 3` 명령이며
   `LLM_MAX_TOKENS=8192`만 다르다. summary의 `llm_max_tokens_source`는
   `environment`로 기록됐다.
3. tool sequence, iteration, evidence 상태 수: 8/16/17 call로 종료했고 evidence는
   모두 0건이었다. protocol error code는 `duplicate_call`+`invalid_arguments`,
   `invalid_arguments`+`duplicate_call`, `not_found`+`invalid_arguments`였다.
4. exit code와 artifact/input Git 상태: 3회 모두 exit 1로 `passed=false`,
   `successes=0/3`이었다. 입력 checkout은 무변경이다.
5. 다음 실험에서 유지할 것과 폐기할 것: 폐기할 것은 출력 절단 가설이다. 상향은
   오히려 0/3이었다. 유지할 것은 `LLM_MAX_TOKENS=4096`이다. 성공한 run의 결과
   artifact는 2,948 bytes와 4,309 bytes로 4096 token 상한에 근접하지 않았다.
   함께 확인한 사실로, `LLM_MAX_TOKENS`는 요청 body의 `max_tokens`이므로 응답 1건의
   출력 상한이지 총 컨텍스트가 아니다. 입력 쪽 한도는
   `migration_assistant/adk_model.py`의 `_bound_messages` 기본값 160 KiB로
   하드코딩돼 있고 env로 노출되지 않는다. 이 워크로드의 대략 3~4 bytes/token 기준으로
   약 45~55K token에 해당하므로, 128K 컨텍스트를 실제로 활용하려면 이 bound를 토큰
   기준으로 바꾸고 설정으로 노출하는 별도 작업이 필요하다. 다만 현재 실패 run은
   8~17 call에서 끝나 이 한도에 닿지 않으므로 gate 실패의 원인은 아니다.

### T6 현재 판정

`jpetstore-6` 3-of-3 gate는 세 차례 모두 미달했다: `successes` 0/3, 1/3, 0/3.
진단 실행을 포함한 live 10회 중 `complete` + `terminal`은 2회다. Task 6의 acceptance
기준은 충족되지 않았다.

남은 후속 작업은 다음과 같다.

- 교차 저장소 회귀(`spring-petclinic`, `full-stack-fastapi-template`)는 primary
  gate가 통과하지 않아 아직 수행하지 않았다.
- Go holdout은 설정 자체가 없다. `GO_HOLDOUT_REPO`가 process와 user scope 모두
  비어 있고 대상 checkout도 없다. `CONTEXT.md`에 따라 이는 skip이 아니라
  configuration failure로 남긴다.
- 모델 교체는 설정 결정이므로 이 기록 시점에는 수행하지 않았다.

### Run 29 — 관측 출처 계측 도입

1. 바꾼 변수 하나와 그 가설: 어느 Tool이 어느 줄을 관측했는지를 좌표로 기록하고
   Evidence별로 귀속하는 계측을 추가했다. 설계 판단의 전제인 "근거가 실제로 어느
   Tool에서 오는가"를 측정할 수 있게 되면, 관측 원장 설계의 기대 효과를 데이터로
   판정할 수 있다는 가설이다. 계측은 기록 전용이며 grounding 판정 경로를 바꾸지 않는다.
2. 실제 실행 명령의 비밀값 제거 버전: Run 26과 동일한 `--runs 3` 명령이며 모델 설정도
   동일하다(`solar-pro3`, max_tokens 4096).
3. tool sequence, iteration, evidence 상태 수: 세 run 모두 evidence 0건이라 Evidence별
   귀속 데이터는 비어 있다. 관측 분포는 다음과 같다.

   | run | read_file | read_file_lines | search_text | 관측 path 수 |
   | --- | --- | --- | --- | --- |
   | 1 | 644 lines | 10 lines | 0 lines (호출 1회) | 3 |
   | 2 | 767 lines | 0 lines (호출 0회) | 0 lines (호출 2회) | 6 |
   | 3 | 0 lines (호출 0회) | 4 lines | 0 lines (호출 0회) | 1 |

4. exit code와 artifact/input Git 상태: 3회 모두 exit 1로 `passed=false`,
   `successes=0/3`이었다. 입력 checkout은 무변경이다. 결정론적 테스트는 신규 11개를
   포함해 153개 전부 통과했다.
5. 다음 실험에서 유지할 것과 폐기할 것:

   유지할 것은 계측 자체다. 이 한 번의 실행으로 이전에는 보이지 않던 두 가지가 드러났다.

   - **관측이 `read_file`에 압도적으로 쏠려 있다.** 전체 관측 1,425줄 중 1,411줄이
     whole-file read이고 좁은 관측은 14줄뿐이다. 관측 원장 설계는 좁은 관측에만 전사
     면제를 주려 했으므로, 이 분포에서는 기대 효과가 0에 가깝다. 독립 검토가 지적했던
     "효과를 측정할 수 없다"는 우려가 데이터로 확인됐다.
   - **`search_text`가 세 번 호출되어 hit 0건이었다.** Tool 결함은 아니다. 같은
     Repository에 `java.version`, `<packaging>`, `port`, `jdbc`, `8080`을 직접
     질의하면 각각 8, 1, 32, 32, 4건이 나온다. 즉 모델이 아무것도 매치되지 않는 패턴을
     고르고 있다. 지시문(`migration_assistant/agent.py:62`)은 "주장마다 먼저
     search_text hit를 확보하라"고 요구하는데, 지시된 경로가 실제로는 성립하지 않는다.

   폐기할 것은 "관측 원장 grounding이 다음 우선순위"라는 가정이다. 위 분포는 무엇을
   검색해야 하는지 모르는 것이 더 앞선 원인임을 가리킨다.

   해석 한계: 세 run 모두 evidence가 0건이라 이 수치는 **모델이 무엇을 열어봤는지**를
   말할 뿐 **무엇을 인용했는지**를 말하지 않는다. n=3이다. Evidence별 귀속과
   `unobserved_evidence_count`는 성공 run이 나와야 값을 갖는다.

### Run 30 — component 계약을 선택 필드로 노출

1. 바꾼 변수 하나와 그 가설: `AnalysisResult`와 `validate_analysis` wire schema에
   `components`를 선택 필드로 추가했다(`11d6d9d`). 강제하기 전에 모델이 계약을 스스로
   채우는지 먼저 재면, 필수화가 실패율을 올릴 위험을 사전에 판단할 수 있다는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전:

   ```powershell
   python -m devtools.run_phase1_live_acceptance --repository <jpetstore-6-checkout> --output-parent <output-parent> --runs 10
   ```

   모델은 `solar-pro3`, max_tokens 4096, 그 외 설정은 이전과 동일하다.
3. tool sequence, iteration, evidence 상태 수: 10회 모두 `failed`이고 positive
   evidence 0건이다. artifact 10개 전부 `components: []`다. 관측은 `read_file`
   5,519줄 대 좁은 관측 91줄로 read_file 비중 98.4%다. `search_text`는 22회 호출에
   14회가 0건(0.636)이며 검색을 한 번이라도 한 run은 4/10이다. 첫 Tool이
   `inspect_target`인 run은 10/10이다.
4. exit code와 artifact/input Git 상태: 10회 모두 exit 1이다. 입력 checkout은
   무변경이다.
5. 다음 실험에서 유지할 것과 폐기할 것: 확정된 사실은 **모델이 지시받지 않으면
   components를 채우지 않는다**는 것이다. 따라서 계약 필수화(1b)보다 지시문 도메인
   복원이 먼저다. 못 채우는 것을 필수로 만들면 실패율만 오른다.

   방법론 오류를 기록한다. 설계 문서는 "변경 전 코드로" 기준선을 잡으라고 정했는데
   이 측정은 계약 노출 이후에 실행했다. 따라서 이 값은 1a 이전 대비 변화를 말하지
   못한다. 다만 `components`는 wire schema의 required가 아니므로 관측된
   `candidate_schema` 실패의 직접 원인일 수는 없다.

### Run 31 — 지시문에 이관 도메인 복원

1. 바꾼 변수 하나와 그 가설: 지시문을 역할·도메인·근거·계약·종료 다섯 구획으로
   재구성하고 이관 도메인을 신설했다(`f447de5`). 탐색 순서, 네 실행 단계 분리, 네 분류
   버킷, 도메인 함정, 검색 0건 대응, components 채우는 법을 넣었다. Tool 규약 중복을
   덜어내 길이 증가는 4,183 → 4,598자(+10%)에 그쳤다. 무엇을 찾아야 하는지 알려주면
   탐색이 좁은 관측으로 옮겨가고 계약이 채워질 것이라는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전: Run 30과 동일하다.
3. tool sequence, iteration, evidence 상태 수: 10회 모두 `failed`, positive evidence
   0건, `components: []` 10/10이다. 탐색 지표는 움직였다. 검색한 run 4→9,
   0건 비율 0.636→0.514, 좁은 관측 91→230줄, read_file 비중 98.4%→95.0%다.
   첫 Tool 준수는 10/10을 유지했다.
4. exit code와 artifact/input Git 상태: 10회 모두 exit 1, 입력 무변경, 결정론적
   테스트 170개 통과다.
5. 다음 실험에서 유지할 것과 폐기할 것: 유지한다. 사전 등록한 롤백 조건(지시문 길이
   증가에 따른 첫 Tool 준수율 하락)이 발동하지 않았다.

   이 시점에 `protocol_error_fields` 계측(`f30512d`)을 넣어 실패 지점이 처음 보였다.
   `$.line_end`가 6건으로 최다였고 `$.components[0].commands.production_startup`이
   1건 나왔다. 후자는 모델이 계약을 채우려 시도했다는 첫 신호다.

### Run 32 — line evidence 상한 4 → 10

1. 바꾼 변수 하나와 그 가설: `_MAX_LINE_EVIDENCE_LINES`를 4에서 10으로 올렸다
   (`ba7f73b`). 거부된 인자 값 계측(`20631fe`)을 넣고 진단 3회를 돌린 결과 거부된
   `line_end`가 10, 5, 5였다. 파일 끝 초과도 순서 혼동도 아닌 정상 범위 요청이
   상한에 걸린 것이므로, 상한을 넓히면 recovery 예산 낭비가 사라질 것이라는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전: Run 30과 동일하다.
3. tool sequence, iteration, evidence 상태 수: 10회 모두 `failed`, positive evidence
   0건, `components: []` 10/10이다. `$.line_end` 거부는 6→4로 줄었을 뿐 사라지지
   않았다. 검색 지표는 0건 비율 0.514→0.667, 검색한 run 9→5로 Run 30 수준으로
   돌아갔다. read_file 비중은 95.0%→96.1%다.
4. exit code와 artifact/input Git 상태: 10회 모두 exit 1, 입력 무변경, 결정론적
   테스트 175개 통과다.
5. 다음 실험에서 유지할 것과 폐기할 것: 상한 변경은 유지한다. 4줄이 maven property
   블록이나 compose service 정의를 담지 못하는 것은 사실이고 어떤 지표도 악화시키지
   않았다.

   폐기할 것은 두 가지다. 첫째, **line 상한이 병목이라는 진단**이다. 상한을 2.5배로
   늘렸는데 거부가 남았다는 것은 표본 3건에 과적합한 판단이었음을 뜻한다. 둘째,
   **Run 31을 "검색 개선"으로 읽은 해석**이다. 같은 조건에서 재현되지 않았으므로
   이 지표는 n=10에서도 흔들림이 크다.

   이 시점의 누적 사실이 더 중요하다. 세 라운드 30회 실행에서 `complete`,
   positive evidence, components가 모두 0이다. 실패 코드는 고칠 때마다
   `$.line_end`→`$.relative`/`$.summary`/`$.tool_calls[0].function.arguments`로
   자리를 옮겼을 뿐 사라지지 않았다. 특정 필드의 문제가 아니라 구조화된 tool 호출을
   안정적으로 생성하지 못하는 것이 공통 원인으로 보인다.

### Run 33 — 모델 교체 solar-pro3 → solar-pro2

1. 바꾼 변수 하나와 그 가설: 코드는 `ba7f73b` 그대로 두고 `LLM_MODEL`만
   `solar-pro3`에서 `solar-pro2`로 바꿨다. base URL, timeout, max_tokens는 동일하며
   사용자 env 파일을 수정하지 않고 프로세스 환경변수로만 덮었다. 30회 0성공이 코드
   문제인지 모델 문제인지 가르는 것이 목적이다.
2. 실제 실행 명령의 비밀값 제거 버전: Run 30과 동일하며 `LLM_MODEL=solar-pro2`만
   다르다. summary의 `llm_model_source`는 `environment`로 기록됐다.
3. tool sequence, iteration, evidence 상태 수: `complete` 2, `partial` 3, `failed` 5다.
   positive evidence 총 28건, components를 채운 run 5/10에 총 18개다. 평균 tool 호출은
   12.4→36.7로 세 배다. 검색 0건 비율 0.500, 검색한 run 8/10이다. 관측은 read_file
   3,722줄 대 좁은 관측 735줄로 비중이 96.1%→83.5%로 내려갔다. 첫 Tool 준수는
   10/10이다.
4. exit code와 artifact/input Git 상태: `complete` + `terminal`이 2/10이므로 gate
   기준에는 미달이다. 입력 checkout은 무변경이다.
5. 다음 실험에서 유지할 것과 폐기할 것: **모델이 병목이었다는 것이 확정됐다.** 동일
   코드에서 `solar-pro3`는 30회 연속 아무 산출물도 내지 못했고 `solar-pro2`는 10회 중
   2회 완주했다.

   이 결과가 소급해서 확인해준 것이 있다. component 계약은 모델이 채울 수 있는
   형태이고(5 run에서 18개), 도메인 지시문은 의도한 탐색 행동을 만든다(좁은 관측
   4배). `solar-pro3`에서는 계약을 채우는 단계까지 도달하지 못해 검증이 불가능했던
   것이다.

   다만 2/10은 3-of-3 gate를 통과하지 못한다. `candidate_schema`가 10건으로 최다이며
   실패 지점이 `$.components[0].production_startup`, `$.components[0].ports`처럼
   component 필드로 옮겨갔다. 병목이 "아무것도 못 함"에서 "계약을 정확히 못 채움"으로
   이동한 것이지 해소된 것이 아니다.

   `solar-pro2`가 `solar-pro3`보다 나은 이유는 확인하지 않았다. tool 호출이 세 배인
   것으로 보아 더 오래 탐색하는 특성으로 추정되나 근거는 없다.

### Run 34 — callback telemetry 반영 후 solar-pro2 smoke 재검증

1. 바꾼 변수 하나와 그 가설: callback의 `after_tool` telemetry가 실제 Tool 실행
   여부를 구분하도록 보강한 현재 코드(`ff7668a`)에서 `solar-pro2` 1회 smoke를
   재실행했다. before callback이 호출을 차단하더라도 ADK가 after callback을 호출할
   수 있으므로, telemetry의 `executed` 값이 실제 실행과 차단을 구분하면서 기존
   acceptance 결과를 보존할 것이라는 가설이다.
2. 실제 실행 명령의 비밀값 제거 버전:

   ```powershell
   python -m devtools.run_phase1_live_acceptance --repository <jpetstore-6-checkout> --output-parent <output-parent> --runs 1
   ```

   target commit은 `3ebd25fd04f1b48361ab879e113ba353838ffe6a`였고, endpoint는
   `https://api.upstage.ai/v1`, model은 `solar-pro2`, timeout은 60초, max tokens는
   4096이었다. API key와 raw request/response는 기록하지 않았다.
3. tool sequence, iteration, 오류 상태: 21회 iteration에서 다음 Tool sequence가
   관찰됐다: `inspect_target`, `list_tree`, `read_file`, `search_text`,
   `read_file_lines`, `validate_analysis` 등. protocol 오류는
   `invalid_arguments`(`$.line_end`), `duplicate_call`, `candidate_schema`
   (`$.iterations`), `evidence_grounding` 3회였다. `prebinding_rejections=1`,
   `validation_attempts=2`, `inline_corrections=3`, `recovery_attempts=0`이었다.
   마지막 오류는 unresolved absence evidence 검증 실패였고, `absence_contradicted`
   또는 `absence_unverified`의 세부 원인은 raw candidate를 저장하지 않는 현재
   Secret-safe artifact만으로는 확정할 수 없다.
4. exit code와 artifact/input Git 상태: exit 1, `status=failed`, `terminal=false`,
   positive Evidence 0건, acceptance `successes=0/1`이었다. 결과는 target 밖
   `.dryforge/live-stage8-20260806/run-1`에 저장됐고, target Git 상태는 clean이었다.
5. 다음 실험에서 유지할 것과 폐기할 것: 유지할 것은 callback telemetry의
   Secret-safe 실행 여부 구분과 smoke 실패 시 공식 3-run을 중단하는 gate다. 폐기할
   것은 "callback telemetry 보강만으로 모델의 evidence 수정 실패가 해결된다"는
   가정이다. 다음 deterministic 작업은 unresolved absence 실패의 typed issue를
   보존해 `absence_contradicted`와 `absence_unverified`를 분리 관찰하는 것이다.

### Run 35 — exploration policy/coverage/stop gate 도입 후 solar-pro2 smoke

1. 바꾼 변수 하나와 그 가설: `docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md`의
   Task 0~6(선언적 exploration registry, Secret-safe coverage ledger,
   `CoverageSnapshot -> ContextProjection` 피드백, Role/Mission/Policy/Stop
   instruction 재구성, `exploration_signals`, 기계적 `stop_decision()`,
   fixture 기반 trajectory 평가기)을 적용한 뒤 `jpetstore-6` 대상 1회 smoke를
   실행했다. 가설은 탐색 우선순위와 coverage 피드백이 모델의 파일 선택을
   좁혀 evidence grounding 실패를 줄일 것이라는 것이었다.
2. 실제 실행 명령의 비밀값 제거 버전, 그리고 전체 suite 결과(Task 7 Step 2):

   ```powershell
   python -m pytest -q -p no:cacheprovider
   python -m devtools.run_phase1_live_acceptance --repository <jpetstore-6-checkout> --output-parent .dryforge/live-exploration-policy-20260806 --runs 1
   ```

   전체 suite는 `1 failed, 318 passed, 3 skipped`였다. 유일한 실패는 기존 known
   baseline인 `tests/test_migration_assistant_foundation.py::test_module_entrypoint_routes_cli_arguments_to_analysis_cli`의
   Windows subprocess UTF-8 디코딩 문제이며, 이번 세션의 새 실패는 없었다.

   target commit은 `3ebd25fd04f1b48361ab879e113ba353838ffe6a`(branch master, clean)였고,
   endpoint는 `https://api.upstage.ai/v1`, model은 `solar-pro2`, timeout은 60초,
   max tokens는 4096이었다. API key와 raw request/response는 기록하지 않는다.
3. tool sequence, iteration, 오류 상태: 38개 Tool 호출 중 `inspect_target`,
   `list_tree` 이후 거의 전부가 `read_file`/`read_file_lines`였고 `search_text`
   호출은 0회였다 — `exploration_coverage`의 7개 질문 모두
   `has_search_scope=false`, `has_search_pattern=false`로 기록되어, instruction의
   "search_text hit부터 확보" 지시를 모델이 따르지 않고 광범위한 read로만
   탐색했음을 관찰로 확인했다. `protocol_error_codes`는
   `["malformed_arguments", "evidence_grounding", "evidence_grounding",
   "invalid_arguments"]`였고, `recovery_attempts=1`(cap 1),
   `inline_corrections=2`(cap 3), `validation_attempts=1`(cap 2),
   `prebinding_rejections=0`이었다. 마지막 `validate_analysis` 실패는
   `pom.xml:105-113`, `pom.xml:129-133`의 evidence excerpt가 실제 Repository
   line과 불일치한 evidence_grounding 오류였고, recovery turn 이후
   `read_file_lines` 2회가 더 있었지만 `validate_analysis` 재제출 없이 종료됐다.
4. exit code와 artifact/input Git 상태: exit 1, `status=failed`, `terminal=false`,
   positive Evidence 0건, acceptance `successes=0/1`이었다. `run_metadata.stop_decision`은
   `{"allowed": false, "reason": "no_evidence: ...", "allowed_status": [],
   "synthetic_values": {}}`로 Evidence 0건을 정확히 반영했다 — Task 5의
   기계적 stop 판정이 live 경로에서도 그대로 계산됐다. 결과는 target 밖
   `.dryforge/live-exploration-policy-20260806/run-1`에 저장됐고, target Git
   상태는 실행 전후 모두 clean이었다. artifact 전체에서 plan Step 4가 지정한
   전체 패턴 `api[_-]?key|authorization|bearer|password|token|secret`(대소문자
   무시)로 검색한 결과는 1건이었고, 그 1건은 `run-metadata.json`의
   `runtime_config_and_secret_names`라는 우리 자신의 question_id 필드 이름일
   뿐 실제 Secret 값이 아니었다. 최초 기록 시 `secret`을 빠뜨린 축소된
   패턴으로만 검색했던 것을 독립 리뷰가 지적해 전체 패턴으로 재검증했다.
5. 다음 실험에서 유지할 것과 폐기할 것: 유지할 것은 smoke 실패 시 공식
   3-run을 중단하는 gate와, `exploration_coverage`/`stop_decision`이 live
   실행에서 실제로 채워진다는 확인이다. 폐기할 것은 "탐색 우선순위 registry와
   coverage 피드백만으로 solar-pro2의 evidence grounding 실패가 해결된다"는
   가정이다. Run 34와 Run 35를 다시 대조하면 Run 34의 tool sequence에는
   `search_text`가 최소 1회 포함됐지만 Run 35는 38회 호출 중 0회였다 — 이는
   "동일한 경향"이 아니라 이번 run에서 오히려 더 심해졌을 수 있는 관측치이며,
   독립 리뷰가 초안의 "동일하게"라는 단정적 표현이 근거보다 강하다고 지적해
   바로잡는다. 공통된 것은 이 model이 `search_text` 기반 정밀 탐색보다
   광범위한 `read_file`을 선호하고 excerpt를 부정확하게 재구성하는 경향
   뿐이며, 그 정도가 Run 35에서 더 심했는지는 단일 run 비교로는 통계적으로
   결론 내릴 수 없다 — 이 실패를 "이미 해결 방향이 있는 known 경향"으로
   과소평가하지 않는다.
   다음 deterministic 작업 후보는 `meta.exploration_signals`/`context_projection`가
   실제로 `search_text` 사용 빈도를 높이는지 별도 A/B 없이는 판단할 수 없다는
   점을 인정하고, tool 선택 편향 자체를 로그로 남기는 지표(예: 질문별
   `search_text` 대 `read_file` 비율)를 telemetry에 추가하는 것이다.

## 개발 환경 변수 파일

Live harness는 다음 순서로 처음 발견되는 env 파일 하나를 읽습니다: 명시적
`--env-file`, `MIGRATION_ASSISTANT_ENV_FILE`, Repository root의 `.env`,
`~/.config/kubernetes-migration-assistant/env`. 이미 셸에 설정된 환경변수는
파일 값보다 우선합니다. 일반 `migration_assistant` CLI는 제품 package의
경계를 유지하기 위해 env 파일을 자동으로 읽지 않으므로, 실행할 때 같은 파일을
셸 프로세스에 먼저 로드합니다.

Windows PowerShell 한 줄:

```powershell
$envFile=Join-Path ([Environment]::GetFolderPath('UserProfile')) '.config/kubernetes-migration-assistant/env'; Get-Content -LiteralPath $envFile -Encoding utf8 | ForEach-Object { $line=$_.Trim(); if ($line -and -not $line.StartsWith('#')) { if ($line.StartsWith('export ')) { $line=$line.Substring(7).Trim() }; $pair=$line.Split('=',2); $key=$pair[0].Trim(); if ($pair.Count -eq 2 -and $key -match '^[A-Za-z_][A-Za-z0-9_]*$' -and -not [Environment]::GetEnvironmentVariables('Process').Contains($key)) { $value=$pair[1].Trim(); if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) { $value=$value.Substring(1,$value.Length-2) }; [Environment]::SetEnvironmentVariable($key,$value,'Process') } } }; python -m migration_assistant analyze <repository-path>
```

Ubuntu bash 한 줄:

```bash
set -a; . "$HOME/.config/kubernetes-migration-assistant/env"; set +a; python -m migration_assistant analyze <repository-path>
```

위 명령은 사용자가 직접 관리하는 설정 파일을 셸 문법으로 로드하므로 해당
파일을 신뢰할 수 있을 때 사용합니다. harness의 `devtools.env_file` 로더는
명령 치환이나 변수 보간 없이 `KEY=VALUE`만 파싱합니다.
