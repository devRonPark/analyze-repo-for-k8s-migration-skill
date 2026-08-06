# Kubernetes Migration Agent Lessons Learned and Improvement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 단일 ADK Agent의 구성·동작·실패 원인과 시행착오를 공유 가능한 Lesson Learned로 정리하고, 일반적인 Repository 설명 Agent가 아니라 Kubernetes 이관 결정을 위한 DevOps 분석 Agent로 방향을 전환하는 실행 계획을 정의합니다.

**Architecture:** 기존 단일 Google ADK Agent, OpenAI-compatible adapter, 정확히 8개의 read-only Repository Tool, Evidence Ledger, Pydantic validator, deterministic renderer/validator는 유지합니다. 개선의 중심은 모델을 더 강하게 지시하는 것이 아니라 Kubernetes 이관 질문, 선언적 탐색 신호, 질문별 coverage, bounded stop gate, trajectory 평가를 분리해 현재 Agent의 판단 범위를 좁히는 것입니다.

**Tech Stack:** Python 3.11+, Google ADK 현재 lock version, Pydantic, dataclasses, pytest, OpenAI-compatible adapter, Local Git Repository.

## Global Constraints

- Repository는 read-only이며 대상 코드·build·test·server·container를 실행하지 않습니다.
- public Agent Tool surface는 inspect_target, list_tree, find_files, search_text, read_file, read_file_lines, inspect_git_metadata, validate_analysis 정확히 8개입니다.
- 기존 Secret redaction, symlink escape, path/read-only/file/byte/iteration/no-progress budget을 유지합니다.
- Spring, FastAPI, Maven, Gradle, Go별 고정 실행 흐름을 추가하지 않습니다. 언어 신호는 선언적 registry로만 관리합니다.
- registry는 관찰 우선순위와 검색 힌트만 제공하고 port, image, environment variable, workload 등 결론값을 채우지 않습니다.
- unknown ecosystem은 generic 탐색으로 진행하고 확인할 수 없는 값은 unresolved, 충돌은 conflicting으로 남깁니다.
- 이번 개선에서 code structure graph, ADK graph workflow, multi-agent, A2A, persistent Session DB는 추가하지 않습니다.
- 모든 구현 Task는 failing test → RED 확인 → 최소 구현 → focused verification → 별도 commit 순서로 진행합니다.
- 현재 known baseline인 Windows subprocess UTF-8 테스트 실패는 새 실패와 분리해 기록합니다.

---

## 1. 상사 공유용 요약

### 한 문장 결론

이번 작업은 단순히 “파일을 읽고 Kubernetes YAML을 출력하는 기능”이 아니었습니다. 모델이 임의로 파일을 읽고 값을 추론하지 못하도록 하면서도, 처음 보는 언어와 Repository를 generic하게 분석하고, 모든 결론에 path:line 근거를 붙이고, 잘못된 Tool Call을 bounded하게 복구해야 했기 때문에 애플리케이션 기능·Agent orchestration·안전 경계·검증 계약을 동시에 설계해야 했습니다.

### 현재 판정

현재 구현은 다음 목적에는 유효합니다.

~~~text
Local Git Repository
  -> read-only 관찰
  -> line-backed Evidence
  -> Kubernetes 이관 분석 결과
  -> manifest 초안
~~~

하지만 다음 상태까지는 아직 도달하지 않았습니다.

~~~text
Kubernetes DevOps 질문을 기준으로
Agent가 항상 최소한의 관련 파일만 선택하고
안정적으로 terminal AnalysisResult를 제출하는 상태
~~~

최근 solar-pro2 smoke도 invalid_arguments, duplicate_call, candidate_schema, evidence_grounding을 거쳐 failed로 종료했습니다. 이는 안전장치가 없는 문제가 아니라, 다음 파일 선택과 후보 수정이 여전히 모델의 자연어 판단에 많이 의존한다는 증거입니다.

## 2. 기존 Agent는 무엇으로 구성되어 있었는가

### 기존 아키텍처

~~~text
CLI/Application Service
  -> Google ADK Runner
  -> 하나의 Repository Migration Agent
  -> 8개 범용 Repository Tool
  -> ValidationLedger / RunControlLedger
  -> AnalysisResult
  -> KubernetesMigrationPlan
  -> deterministic renderer / validator
~~~

주요 책임은 다음처럼 나누었습니다.

| 구성 | 기존 책임 |
|---|---|
| agent.py | Agent 역할, 긴 instruction, Tool 등록, callback 등록 |
| adk_model.py | OpenAI-compatible 응답을 ADK LlmResponse로 변환 |
| adk_tools.py | Tool adapter, argument validation, callback, provenance, recovery envelope |
| repository_tools.py | read-only path, Git, symlink, file/budget, 검색·읽기 |
| tool_protocol.py | phase, duplicate, retry, allowed action, bounded stop |
| adk_runner.py | ADK Runner stream, event 소비, recovery turn, terminal handoff |
| analysis.py | Pydantic AnalysisResult, Evidence·Finding·Component 계약 |
| provenance.py | Evidence line을 실제 어떤 Tool이 관찰했는지 기록 |
| renderer.py / validator.py | 분석 결과를 manifest로 변환하고 정적 검증 |

현재 코드 링크:

- [agent.py](C:/Users/박병찬/Desktop/analyze-repo-for-k8s-migration-adk/migration_assistant/agent.py)
- [adk_tools.py](C:/Users/박병찬/Desktop/analyze-repo-for-k8s-migration-adk/migration_assistant/adk_tools.py)
- [adk_runner.py](C:/Users/박병찬/Desktop/analyze-repo-for-k8s-migration-adk/migration_assistant/adk_runner.py)
- [repository_tools.py](C:/Users/박병찬/Desktop/analyze-repo-for-k8s-migration-adk/migration_assistant/repository_tools.py)
- [analysis.py](C:/Users/박병찬/Desktop/analyze-repo-for-k8s-migration-adk/migration_assistant/analysis.py)

## 3. 기존 Agent는 어떻게 동작했는가

~~~text
모델
  -> Tool Call 생성
  -> after_model_callback: dispatch 가능한지 검사
  -> before_tool_callback: phase·argument·duplicate·budget 검사
  -> 허용 시 Repository Tool 실행
  -> after_tool_callback: 결과·실행 여부 telemetry 기록
  -> Tool result를 모델에게 전달
  -> 다음 탐색 또는 validate_analysis
~~~

Agent instruction은 다음 자연어 우선순위를 제공했습니다.

~~~text
inspect_target
  -> list_tree
  -> build/package manifest
  -> Dockerfile/Compose/entrypoint
  -> configuration/runtime dependency
  -> 필요한 source line
  -> validate_analysis
~~~

모델에게 찾도록 지시한 이관 값은 다음과 같습니다.

~~~text
배포 단위
production startup
build 단계
image build
수신 port
environment variable와 Secret 이름
외부 DB/broker/API
writable path
~~~

Python은 모델의 결론을 대신 만들지 않고 Repository 밖 path 차단, instruction file과 build output 제한, budget, schema, Evidence line 비교, Secret redaction, phase·duplicate·recovery cap, manifest static validation을 담당했습니다.

## 4. 주요 문제점과 실제 실패 증거

### 문제 1: 탐색 우선순위가 prompt에만 있었다

instruction에 “강한 신호부터 읽으라”고 적었지만, 실제 다음 파일을 고르는 결정론적 frontier나 후보 ranking은 없었습니다.

~~~text
모델이 우선순위를 이해하면 정상
모델이 우선순위를 놓치면
  -> broad read
  -> 잘못된 line range
  -> 불필요한 recovery
  -> candidate 제출 실패
~~~

최근 smoke에서는 read_file_lines의 line_end 오류, duplicate call, candidate schema 오류가 연속으로 발생했습니다.

### 문제 2: Evidence 규칙은 강했지만 모델이 수정할 맥락이 부족했다

검증기는 path 존재, 실제 line 범위, excerpt 일치, finding의 Evidence 연결, component field의 Evidence 또는 scoped absence를 확인합니다. 검증 자체는 안전성 측면에서 올바릅니다. 그러나 모델이 오류 뒤 어느 파일을 다시 읽고 어떤 candidate field만 바꿔야 하는지가 충분히 구조화되어 있지 않으면 evidence_grounding과 candidate_schema가 반복됩니다.

### 문제 3: phase·candidate·grounding 오류의 복구가 서로 얽혔다

모델은 잘못된 argument를 고칠지, 새 line observation을 할지, 전체 candidate를 다시 제출할지, 현재 phase의 허용 action을 바꿀지 혼동할 수 있었습니다. 이를 해결하기 위해 RunControlLedger, typed error envelope, callback idempotency, 실제 ADK Runner 통합 검증을 단계적으로 추가했습니다.

### 문제 4: Agent 결과는 이관 구조를 갖지만 탐색 coverage는 보이지 않았다

AnalysisResult는 Evidence, Finding, Component를 표현하지만 다음 질문이 확인됐는지는 별도 계약이 아니었습니다.

~~~text
startup은 관찰했는가?
port는 검색했지만 못 찾은 것인가?
runtime dependency는 아직 탐색하지 않은 것인가?
writable path는 실제 부재를 확인한 것인가?
~~~

### 문제 5: 제품 목적과 codebase graph 목적을 혼동했다

코드베이스 graph는 파일·심볼·호출 관계를 찾는 데 유용하지만, 현재 제품의 목적은 code structure graph 출력이 아니라 Kubernetes 이관 Evidence 수집입니다. 따라서 graph workflow나 Tree-sitter graph를 추가하는 방향은 현재 MVP 범위를 넓히고 generic fallback·read-only·3일 MVP 제약과 충돌합니다.

## 5. 왜 구현이 오래 걸렸는가

겉으로는 Repository 읽기에서 Kubernetes YAML 생성까지처럼 보입니다. 실제로는 다음 계약을 동시에 만족해야 했습니다.

~~~text
확률적인 Tool 선택
  + ADK callback lifecycle
  + OpenAI-compatible protocol 차이
  + read-only Repository safety
  + unknown ecosystem generic fallback
  + line-backed Evidence
  + Secret redaction
  + bounded recovery
  + Pydantic nested schema
  + renderer/validator consistency
~~~

시간이 늘어난 핵심 원인은 다음과 같습니다.

1. callback은 단순 함수가 아니라 실제 ADK Runner 생명주기와 연결된 framework 계약이었습니다.
2. OpenAI-compatible 응답도 ADK LlmResponse, function call linkage, callback context 계약에 맞춰야 했습니다.
3. 오류 하나를 전달하는 것만으로는 부족했고 code, field_path, allowed_next_actions, phase, retry lease가 필요했습니다.
4. 최종 JSON 검증만으로는 부족했고 실제 line 관찰과 unresolved absence 검증이 필요했습니다.
5. live 실패는 재현성이 낮아 deterministic fake model과 direct callback test가 먼저 필요했습니다.
6. 모델 교체와 설계 개선을 구분하기 위해 solar-pro2/solar-pro3 비교가 필요했습니다.

이는 단순한 구현 지연이 아니라 “모델이 잘하면 통과”하는 prototype을 “모델이 틀려도 안전하게 실패하고 원인을 설명할 수 있는 시스템”으로 바꾸는 데 사용된 시간입니다.

## 6. ADK로 구현하며 얻은 인사이트

### Insight 1: Tool은 모델의 손이지만 판단 엔진은 아니다

search_text를 제공한다고 해서 Agent가 올바른 search pattern을 자동으로 선택하지는 않습니다. 목적·탐색 규칙·중단 조건은 instruction이나 별도 orchestration이 제공해야 합니다.

### Insight 2: Callback은 문지기이지 탐색 계획자가 아니다

before_tool_callback은 잘못된 action을 차단하는 데 적합합니다. 어떤 파일을 다음에 읽을지까지 callback이 결정하면 validation, routing, telemetry가 한 곳에 섞입니다.

~~~text
Agent       다음 관찰 후보를 선택
Policy      이관 질문과 신호 우선순위를 제공
Callback    실행 전 안전·phase·argument를 검사
Tool        관찰 사실을 반환
Ledger      coverage·provenance·telemetry를 기록
Validator   최종 계약을 판정
~~~

### Insight 3: Session history와 domain context는 다르다

ADK Session은 이전 event와 Tool result를 보존하지만, 긴 event history가 곧 Kubernetes 이관 맥락은 아닙니다. 모델에게 현재 어떤 질문이 아직 비어 있는지 compact metadata로 알려야 합니다.

### Insight 4: 최종 출력보다 trajectory가 중요한 디버깅 자료다

모델이 어떤 Tool을 호출했는지, 실제 실행됐는지, 어떤 phase에서 거부됐는지, 어떤 line을 관찰했는지, 같은 action을 반복했는지를 함께 봐야 합니다.

### Insight 5: 모델 변경은 설계 개선이 아니다

solar-pro2와 solar-pro3 비교는 모델 특성 차이를 보여 주지만, 모델 변경은 실험 변수일 뿐입니다. 탐색 정책·validator·trajectory 평가가 먼저 안정되어야 합니다.

## 7. 방향 전환: Kubernetes DevOps Engineer 관점

단순히 “당신은 Kubernetes DevOps Engineer입니다”를 추가하지 않습니다. Persona를 다음 실행 계약으로 바꿉니다.

~~~text
Role
  Kubernetes 이관 전 read-only 분석 담당

Mission
  Kubernetes manifest 작성에 필요한 최소 Repository Evidence 수집

Questions
  workload, startup, build stages, network, runtime config,
  external dependency, writable state

Stop gate
  확인된 값은 Evidence로 연결하고,
  확인 불가 값은 unresolved로 명시한 뒤 제출
~~~

탐색 계층은 다음과 같습니다.

~~~text
Tier 0: inspect_target, list_tree
Tier 1: build/package, container/process, config/deployment 후보
Tier 2: 실제 hit가 가리키는 startup·port·dependency 관찰
Tier 3: unresolved 질문에 필요한 source/config만 보충
Stop: 전체 Repository를 읽지 않고 validate_analysis
~~~

목표는 모든 파일을 이해하는 Agent가 아니라 이관 결정을 위해 필요한 질문에 답하는 Agent입니다.

## 8. 개선 구현 계획

구현 전에 관찰 범위와 종료 조건의 계약을 먼저 고정합니다. Coverage를 기록하는 것만으로는 모델의 다음 행동이 바뀌지 않으므로, 기록·문맥 투영·모델 호출·기계적 종료 판정을 분리하되 연결 경로를 계획에 명시합니다.

### Task 0: 탐색 계약과 경계 확정

**Files:**
- Modify: this plan
- Create: tests/fixtures/adk_migration_contract/question-dispositions.json
- Create: tests/fixtures/adk_migration_contract/stop-gate-cases.json
- Test: tests/test_migration_contract.py

**Produces:** 구현 전에 고정된 질문 상태표, Stop truth table, metadata 경계, signal 허용 필드 계약

- [x] **Step 1: migration question disposition 정의**

각 질문은 `required`, `conditional`, `optional` 중 하나의 중요도를 가집니다. 모든 질문은 다음 상태 중 하나로 종료됩니다.

~~~text
confirmed   : 실제 관찰 line-backed Evidence가 있음
inferred    : positive Evidence에서 파생됐지만 직접 관찰값과 구분됨
unresolved  : 정해진 탐색 범위·패턴·budget을 소진했으나 근거가 없음
conflicting : 둘 이상의 positive 관찰이 서로 충돌함
not_applicable : 조건부 질문의 선행 조건이 관찰되지 않음
~~~

`unresolved`는 모델의 문장만으로 생성하지 않습니다. Ledger가 탐색 범위, 사용한 pattern, 관찰 횟수 또는 scope 제한, 종료 이유를 보유할 때만 인정합니다.

- [x] **Step 2: AnalysisResult와 RunMetadata 경계 확정**

`AnalysisResult`는 Evidence·Finding·Component·분석 상태를 담는 도메인 결과로 유지합니다. `run_metadata`는 callback telemetry, Tool trajectory, exploration coverage, budget, approval preflight를 담는 실행 telemetry로 유지하며 모델 결과 schema에 섞지 않습니다.

~~~text
AnalysisResult -> renderer -> KubernetesMigrationPlan -> manifest validator
run_metadata  -> run artifact / live acceptance telemetry
~~~

`renderer`는 `KubernetesMigrationPlan`만 입력받고, `validator`는 manifest set만 입력받습니다. 실행 결과 artifact에는 `analysis-result.json`과 Secret-safe `run-metadata.json`을 별도 파일로 저장하거나, 기존 artifact contract 안에서 두 영역을 명시적으로 분리합니다. 이 위치와 schema version을 테스트로 고정합니다.

- [x] **Step 3: exploration signal 허용·금지 계약 확정**

Tool이 반환하는 raw observation과 별도의 advisory control metadata를 구분합니다. `exploration_signals`의 허용 필드는 `question_id`, `trigger_rule_id`, `observed_fact_ref`, `candidate_observation_kind`입니다.

다음은 금지합니다.

~~~text
workload=Deployment, port=8080 같은 결론값
confirmed/unresolved 같은 최종 상태 확정
next_tool=read_file 같은 특정 Tool 호출 강제
registry에 없는 생태계의 parser·business logic 우회
~~~

- [x] **Step 4: Stop truth table과 테스트 fixture 작성**

| 조건 | 제출 가능 | 허용 상태 | 필수 근거 |
|---|---:|---|---|
| required 질문이 confirmed/inferred이고 충돌 없음 | 예 | complete 또는 partial | positive line-backed Evidence |
| required 질문을 범위·pattern·budget을 소진해 확인하지 못함 | 예 | partial | ledger가 기록한 genuine unresolved |
| conditional 질문의 선행 조건이 관찰되지 않음 | 예 | partial | `not_applicable` 근거 |
| positive 값이 있으나 Evidence가 없음 | 아니오 | 오류 | fresh observation 후 수정 |
| conflicting 관찰이 있음 | 예 | partial | conflicting Evidence와 자동 선택 금지 |
| Evidence가 0건 | 아니오 | 오류 | 분석 제출 불가 |
| duplicate/no-progress/iteration budget 초과 | 예 | failed 또는 partial | bounded stop 사유 |

`tests/test_migration_contract.py`는 위 경우를 모두 검증하며, 모델이 `unresolved`를 임의 선언하거나 Tool이 결론을 반환해도 통과하지 않도록 합니다.

- [x] **Step 5: RED 확인 및 계약 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_migration_contract.py
git add tests/fixtures/adk_migration_contract tests/test_migration_contract.py docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md
git commit -m "test: define migration exploration contracts"
~~~

### Task 1: 탐색 질문·신호 registry 정의

**Files:**
- Create: migration_assistant/exploration_policy.py
- Test: tests/test_exploration_policy.py

**Produces:** ExplorationQuestion, SignalRule, ExplorationPolicy, DEFAULT_MIGRATION_POLICY

- [x] **Step 1: failing test 작성**

~~~python
def test_policy_prioritizes_startup_signals_without_creating_values():
    rules = DEFAULT_MIGRATION_POLICY.rules_for("production_startup")
    assert rules[0].priority == 10
    assert "Dockerfile*" in rules[0].file_globs
    assert "port_value" not in rules[0].__dict__
~~~

- [x] **Step 2: RED 확인**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_exploration_policy.py
~~~

- [x] **Step 3: 최소 구현**

~~~python
@dataclass(frozen=True, slots=True)
class SignalRule:
    key: str
    question_ids: tuple[str, ...]
    priority: int
    file_globs: tuple[str, ...]
    search_patterns: tuple[str, ...]
    reason: str
~~~

registry는 관찰 우선순위만 제공하고 port, image, startup 값은 생성하지 않습니다.

- [x] **Step 4: focused test와 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_exploration_policy.py
git add migration_assistant/exploration_policy.py tests/test_exploration_policy.py
git commit -m "feat: define migration exploration signals"
~~~

### Task 2: 질문별 exploration coverage 기록

**Files:**
- Create: migration_assistant/exploration_ledger.py
- Modify: migration_assistant/adk_tools.py
- Modify: migration_assistant/adk_runner.py
- Modify: migration_assistant/analysis.py
- Test: tests/test_exploration_ledger.py

**Produces:** Secret-safe `run_metadata["exploration_coverage"]`와 별도 실행 artifact 저장 계약

- [ ] **Step 1: failing test 작성**

~~~python
def test_observed_question_is_not_reported_as_grounded_value():
    ledger = ExplorationLedger()
    ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 3)
    summary = ledger.summary()
    assert summary["questions"]["production_startup"]["status"] == "observed"
    assert "value" not in repr(summary)
~~~

- [ ] **Step 2: RED 확인 및 최소 구현**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_exploration_ledger.py
~~~

Ledger는 raw args, raw excerpt, Secret 값을 저장하지 않고 question status, Tool 이름, bounded line count, positive Evidence count만 기록합니다. 이 단계의 coverage는 관찰성과 telemetry를 위한 것이며, 이것만으로 모델의 다음 행동이 바뀐다고 가정하지 않습니다.

- [ ] **Step 3: ADK handoff 연결과 focused test**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_exploration_ledger.py tests/test_phase1_adk_contract.py
~~~

- [ ] **Step 4: commit**

~~~powershell
git add migration_assistant/exploration_ledger.py migration_assistant/adk_tools.py migration_assistant/adk_runner.py migration_assistant/analysis.py tests/test_exploration_ledger.py
git commit -m "feat: track migration exploration coverage"
~~~

### Task 2A: Coverage를 다음 모델 호출 문맥으로 투영

**Files:**
- Create: migration_assistant/exploration_context.py
- Test: tests/test_exploration_context.py
- Modify: migration_assistant/adk_runner.py

**Produces:** `CoverageSnapshot -> ContextProjection -> next LLM call` 피드백 경로

- [ ] **Step 1: failing test 작성**

~~~python
def test_context_projection_lists_unresolved_questions_without_values():
    projection = project_next_observations(snapshot)
    assert projection[0]["question_id"] == "production_startup"
    assert "port" not in repr(projection)
    assert "next_tool" not in repr(projection)
~~~

- [ ] **Step 2: 최소 구현과 ADK handoff 연결**

`ContextProjection`은 미해결 질문 ID, 해당 질문의 우선순위, 관찰이 필요한 signal rule ID만 Secret-safe compact metadata로 만듭니다. 구체적인 path, port/image 값, 특정 Tool 호출을 생성하지 않습니다. `adk_runner.py`는 다음 모델 호출 전에 이 projection을 별도 context metadata로 전달하며, 모델의 자연어 판단을 대체하지 않습니다.

~~~text
Tool result
  -> ExplorationLedger update
  -> CoverageSnapshot
  -> ContextProjection
  -> next model context metadata
  -> Agent chooses an allowed Tool
~~~

- [ ] **Step 3: focused test와 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_exploration_context.py tests/test_adk_runner_recovery.py
git add migration_assistant/exploration_context.py migration_assistant/adk_runner.py tests/test_exploration_context.py
git commit -m "feat: project migration coverage into model context"
~~~

### Task 3: Agent instruction을 Role·Mission·Policy·Stop으로 재구성

**Files:**
- Modify: migration_assistant/agent.py
- Modify: migration_assistant/exploration_policy.py
- Test: tests/test_adk_agent.py

- [ ] **Step 1: failing test 작성**

~~~python
def test_instruction_focuses_on_migration_questions_not_generic_repository_summary():
    instruction = build_migration_instruction(DEFAULT_MIGRATION_POLICY)
    assert "production_startup" in instruction
    assert "Kubernetes" in instruction
    assert "read-only" in instruction
    assert "evidence" in instruction.lower()
    assert "unresolved" in instruction
~~~

- [ ] **Step 2: RED 확인**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_adk_agent.py -k instruction
~~~

- [ ] **Step 3: 최소 instruction 변경**

~~~text
Role: Kubernetes DevOps Engineer 관점의 read-only migration analyst
Mission: 이관 결정에 필요한 최소 line-backed Evidence 수집
Policy: Tier 0 → Tier 1 → 실제 hit 기반 Tier 2/3
Stop: 확인·미확인·상충 질문을 분류하고 validate_analysis
~~~

Persona는 관점만 설정하며 일반적인 port/image/storage 값을 추정하라는 문구는 넣지 않습니다.

- [ ] **Step 4: 기존 Tool·callback 등록 보존 확인과 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_adk_agent.py tests/test_phase1_adk_contract.py
git add migration_assistant/agent.py migration_assistant/exploration_policy.py tests/test_adk_agent.py
git commit -m "refactor: focus agent on Kubernetes migration questions"
~~~

### Task 4: 관찰 결과에 다음 탐색 guidance 추가

**Files:**
- Modify: migration_assistant/adk_tools.py
- Modify: migration_assistant/agent.py
- Modify: migration_assistant/exploration_policy.py
- Test: tests/test_phase1_adk_contract.py

- [ ] **Step 1: failing test 작성**

~~~python
def test_observation_meta_contains_signal_without_conclusion():
    response = toolset.search_text("ENTRYPOINT")
    signal = response["meta"]["exploration_signals"][0]
    assert signal["question_id"] == "production_startup"
    assert set(signal) <= {
        "question_id",
        "trigger_rule_id",
        "observed_fact_ref",
        "candidate_observation_kind",
    }
    assert "value" not in signal
    assert "next_tool" not in signal
~~~

- [ ] **Step 2: RED 확인**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_phase1_adk_contract.py -k signal
~~~

- [ ] **Step 3: metadata-only 구현**

~~~json
{
  "exploration_signals": [
    {
      "question_id": "production_startup",
      "trigger_rule_id": "container_or_process_descriptor",
      "observed_fact_ref": "observation-17",
      "candidate_observation_kind": "container_entrypoint_hit"
    }
  ]
}
~~~

metadata는 raw Tool observation과 별도의 advisory control envelope입니다. 결론값, 최종 상태, 구체적인 `next_tool` 호출을 포함하지 않으며, Tool이 분석 결론을 하드코딩하지 않도록 허용 필드를 schema로 제한합니다.

- [ ] **Step 4: phase·argument·duplicate·budget 회귀 테스트와 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_phase1_adk_contract.py tests/test_adk_runner_recovery.py
git add migration_assistant/adk_tools.py migration_assistant/agent.py migration_assistant/exploration_policy.py tests/test_phase1_adk_contract.py
git commit -m "feat: guide exploration from observed signals"
~~~

### Task 5: 기계적 coverage stop gate와 unresolved 경로 고정

**Files:**
- Modify: migration_assistant/exploration_ledger.py
- Modify: migration_assistant/adk_tools.py
- Modify: migration_assistant/tool_protocol.py
- Test: tests/test_adk_runner_recovery.py
- Test: tests/test_phase1_adk_contract.py

- [ ] **Step 1: failing test 작성**

~~~python
def test_unknown_optional_value_is_unresolved_not_fabricated():
    decision = ledger.stop_decision()
    assert decision.allowed is True
    assert "unresolved" in decision.reason
    assert decision.synthetic_values == {}
~~~

- [ ] **Step 2: RED 확인**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_adk_runner_recovery.py tests/test_phase1_adk_contract.py -k unresolved
~~~

- [ ] **Step 3: stop gate 구현**

`Task 0`의 Stop truth table을 코드로 구현합니다. 모델이 말로 `unresolved`를 선언하는 것만으로는 종료할 수 없습니다. Ledger가 해당 질문의 required/conditional/optional 분류, 탐색 범위·pattern·scope 제한, 관찰 횟수 또는 budget 소진, 종료 이유를 기록하고, 그 기록이 있을 때만 genuine unresolved를 인정합니다.

~~~text
required confirmed/inferred + positive Evidence + no conflict -> submit 가능
required genuine unresolved + 탐색 종료 metadata        -> partial submit 가능
conditional 선행 조건 미관찰 + not_applicable            -> partial submit 가능
conflicting positive observations                        -> partial submit, 자동 선택 금지
positive 값 + Evidence 0                                  -> 거부
Evidence 0 전체                                            -> 거부
duplicate/no-progress/iteration budget 초과              -> bounded failed/partial stop
~~~

gate는 port/image/Service/Storage를 생성하지 않으며 unknown ecosystem의 generic fallback을 막지 않습니다. `AnalysisResult`의 도메인 판정과 `run_metadata`의 stop 사유를 모두 보존하되 renderer는 coverage나 telemetry에 의존하지 않습니다.

- [ ] **Step 4: recovery 회귀 테스트와 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_adk_runner_recovery.py tests/test_phase1_adk_contract.py
git add migration_assistant/exploration_ledger.py migration_assistant/adk_tools.py migration_assistant/tool_protocol.py tests/test_adk_runner_recovery.py tests/test_phase1_adk_contract.py
git commit -m "feat: bound migration exploration completion"
~~~

### Task 6: trajectory·coverage 평가 추가

**Files:**
- Create: tests/fixtures/adk_migration_trajectory/valid-minimal.test.json
- Create: tests/fixtures/adk_migration_trajectory/grounding-recovery.test.json
- Create: tests/test_migration_trajectory_contract.py
- Modify: tests/test_phase1_live_acceptance_harness.py
- Modify: devtools/run_phase1_live_acceptance.py

- [ ] **Step 1: failing fixture test 작성**

~~~python
def test_trajectory_reports_question_coverage_and_context_efficiency():
    result = evaluate_trajectory(load_fixture("valid-minimal.test.json"))
    assert result["required_question_disposition_rate"] == 1.0
    assert result["ungrounded_positive_value_count"] == 0
    assert result["unobserved_evidence_count"] == 0
    assert result["fresh_observation_after_grounding_error"] is True
~~~

- [ ] **Step 2: RED 확인과 evaluator 구현**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_migration_trajectory_contract.py
~~~

exact file order를 강제하지 않고 첫 Tool, observed Evidence, required question disposition, 미근거 positive value, grounding 오류 후 fresh observation, duplicate/no-progress budget, bounded context efficiency를 검사합니다. `question_coverage >= 4` 같은 고정 개수나 모든 duplicate 0을 강제하지 않습니다. Duplicate는 정상적인 recovery 재시도와 no-progress 반복을 구분하고, 종류별 상한과 bounded stop 준수로 평가합니다.

- [ ] **Step 3: focused test와 commit**

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_migration_trajectory_contract.py tests/test_phase1_live_acceptance_harness.py
git add tests/fixtures/adk_migration_trajectory tests/test_migration_trajectory_contract.py tests/test_phase1_live_acceptance_harness.py devtools/run_phase1_live_acceptance.py
git commit -m "test: evaluate migration exploration trajectories"
~~~

### Task 7: 전체 회귀·live gate·Lesson Learned 기록

**Files:**
- Modify: docs/phase1-adk-experiment-log.md
- Modify: this plan
- Test: existing tests/

- [ ] **Step 1: focused·static 검증**

~~~powershell
python -m py_compile migration_assistant/exploration_policy.py migration_assistant/exploration_ledger.py migration_assistant/exploration_context.py
python -m pytest -q -p no:cacheprovider tests/test_migration_contract.py tests/test_exploration_policy.py tests/test_exploration_ledger.py tests/test_exploration_context.py tests/test_migration_trajectory_contract.py tests/test_adk_runner_recovery.py tests/test_phase1_adk_contract.py
~~~

- [ ] **Step 2: 전체 suite 실행**

~~~powershell
python -m pytest -q -p no:cacheprovider
~~~

새 실패와 기존 Windows subprocess UTF-8 실패를 구분해 기록합니다.

- [ ] **Step 3: 명시적 외부 전송 승인 후 smoke 실행**

실행 전 preflight metadata에 target absolute path의 repository revision, endpoint host(Secret 제외), model ID, 전송 범위, 승인 reference, budget/timeout 설정을 기록합니다. 비교 모델 실행은 model ID 외 endpoint 정책, Repository revision, prompt, Tool surface, budget, timeout을 고정하고 output directory를 분리합니다. 한 실행의 승인을 다른 target/model/endpoint에 재사용하지 않습니다.

~~~powershell
python -m devtools.run_phase1_live_acceptance --repository "C:\Users\박병찬\Desktop\demo-repositories\jpetstore-6" --output-parent ".dryforge\live-exploration-policy-20260806" --runs 1
~~~

smoke가 실패하면 공식 3-run을 실행하지 않고 deterministic trajectory와 대조합니다. smoke 성공 시에만 동일 model 3-run을 실행하고, 비교 model은 LLM_MODEL만 변경합니다.

- [ ] **Step 4: target·artifact·Secret 검증**

~~~powershell
git -C "C:\Users\박병찬\Desktop\demo-repositories\jpetstore-6" status --short
rg -n -i "api[_-]?key|authorization|bearer|password|token|secret" .dryforge\live-exploration-policy-20260806
~~~

검색 결과는 Secret 값 자체를 출력하지 않고 redaction 위반 여부만 확인합니다.

- [ ] **Step 5: commit**

~~~powershell
git add docs/phase1-adk-experiment-log.md docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md
git commit -m "docs: record migration agent lessons learned"
~~~

## 9. 완료 기준

### 공유 가능한 Lesson Learned

- [ ] 기존 Agent 구성과 event 흐름이 한 장의 diagram으로 설명됩니다.
- [ ] 주요 실패가 phase, argument, candidate, grounding, duplicate로 분류됩니다.
- [ ] 각 실패에 deterministic test 또는 live telemetry가 연결됩니다.
- [ ] 구현이 오래 걸린 이유가 ADK lifecycle, protocol adapter, safety boundary, schema, recovery의 결합으로 설명됩니다.
- [ ] 모델 변경과 탐색 정책·검증 계약 개선을 구분합니다.

### 구현

- [ ] Kubernetes DevOps persona가 Role·Mission·Policy·Stop gate로 분리됩니다.
- [ ] `CoverageSnapshot -> ContextProjection -> next LLM call` 경로가 테스트로 검증됩니다.
- [ ] registry는 결론값을 만들지 않고 관찰 우선순위만 제공합니다.
- [ ] `exploration_signals`는 허용 필드만 가지며 값·최종 상태·구체적인 Tool 호출을 포함하지 않습니다.
- [ ] question coverage가 Secret-safe metadata로 기록됩니다.
- [ ] `AnalysisResult`와 `RunMetadata`의 저장·직렬화 경계가 명시되고 schema version이 검증됩니다.
- [ ] unknown ecosystem은 generic fallback으로 진행됩니다.
- [ ] 기존 Tool·callback·error envelope·read-only 계약이 유지됩니다.

### 검증

- [ ] inspect_target가 첫 관찰입니다.
- [ ] positive Evidence가 실제 관찰된 line과 연결됩니다.
- [ ] grounding 오류 뒤 fresh observation이 요구됩니다.
- [ ] candidate 오류가 reported field 단위로 bounded하게 복구됩니다.
- [ ] Stop truth table이 `confirmed`, `unresolved`, `conflicting`, `not_applicable`, Evidence 0건, budget 초과를 모두 판정합니다.
- [ ] duplicate/phase/no-progress가 bounded STOP됩니다.
- [ ] trajectory와 question disposition 지표가 live 결과에 포함됩니다.

## 10. 최종 공유 메시지

~~~text
이번 프로젝트의 핵심 난점은 Kubernetes YAML 생성 자체가 아니었습니다.
처음 보는 Repository에서 어떤 근거를 읽어야 하는지 모델이 판단해야 했고,
그 판단이 틀려도 안전하게 차단하며, 최종 결과의 모든 값이 실제 파일 line과
연결되어야 했습니다.

초기에는 긴 prompt와 callback 보강으로 문제를 해결하려 했습니다.
실험 결과 callback은 실행 안전성과 복구에 필요하지만, Kubernetes 이관에
필요한 파일 선택까지 대신할 수는 없었습니다.

따라서 다음 단계에서는 Kubernetes DevOps Engineer라는 역할을 단순한 persona
문구로 사용하지 않고, 이관 질문·관찰 우선순위·coverage·중단 조건으로 분리합니다.
이렇게 하면 Agent는 Repository 전체를 설명하려 하지 않고, 실제 배포 결정에
필요한 최소 Evidence를 모으면서도 모르는 값은 안전하게 미확인으로 남길 수 있습니다.
~~~
