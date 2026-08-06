# Claude Code 구현 Handoff: Kubernetes Migration Agent 개선

> 이 문서는 Claude Code가 현재 세션을 이어서 구현하기 위한 작업 인계 문서입니다. 구현의 원본 계획은 [2026-08-06 Kubernetes Migration Agent 개선계획](../plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md)입니다.

## 1. 현재 상태

- Repository: `C:\Users\박병찬\Desktop\analyze-repo-for-k8s-migration-adk`
- Branch: `feat/adk-k8s-migration-demo`
- Handoff 작성 시점의 작업 트리: clean
- 최신 계획 반영 commit: `3e9b061 docs: close migration plan review gaps`
- 최근 Lesson Learned 문서 commit: `0b1f9e3 docs: capture migration agent lessons learned`
- 현재 제품 코드에는 아직 `exploration_policy.py`, `exploration_ledger.py`, `exploration_context.py`가 구현되어 있지 않습니다. 다음 구현은 새로 추가된 **Task 0**부터 시작합니다.

현재는 “Repository 전체를 설명하는 Agent”를 만들려는 것이 아닙니다. 목표는 Kubernetes 이관에 필요한 최소한의 근거를 수집하는 read-only 분석 Agent입니다.

비유하면, 모든 책을 읽는 학생이 아니라 “이사할 집의 전기·수도·가구 배치만 확인하는 점검 기사”를 만드는 작업입니다.

## 2. 반드시 먼저 읽을 파일

순서대로 읽으십시오.

1. `AGENTS.md`
2. 이 문서
3. `docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md`
4. `migration_assistant/agent.py`
5. `migration_assistant/adk_tools.py`
6. `migration_assistant/adk_runner.py`
7. `migration_assistant/analysis.py`
8. `migration_assistant/tool_protocol.py`
9. `migration_assistant/repository_tools.py`
10. `tests/test_adk_agent.py`
11. `tests/test_phase1_adk_contract.py`
12. `tests/test_adk_runner_recovery.py`

읽기 전에 다음을 실행하여 기존 사용자 변경을 확인하십시오.

~~~powershell
git status --short
git branch --show-current
~~~

기존 변경이 발견되면 되돌리거나 stash하지 말고 사용자에게 보고하십시오.

## 3. 영구 불변식

아래 항목은 구현 중에도 절대 깨지면 안 됩니다.

- public Agent Tool은 정확히 다음 8개입니다.

  ~~~text
  inspect_target
  list_tree
  find_files
  search_text
  read_file
  read_file_lines
  inspect_git_metadata
  validate_analysis
  ~~~

- Repository는 read-only입니다. 대상 코드·build·test·server·container를 실행하지 않습니다.
- Remote clone, target Repository 수정, Cluster apply, 실제 Secret 생성은 하지 않습니다.
- Repository 밖으로 나가는 symlink, unsafe path, 과도한 file/byte/iteration/no-progress 사용을 차단합니다.
- Secret 값은 model context, report, manifest, telemetry에 넣지 않습니다.
- unknown ecosystem도 generic 경로로 분석하며, 모르는 값은 `unresolved`, 충돌은 `conflicting`으로 남깁니다.
- Registry는 탐색 우선순위와 검색 신호만 제공합니다. port, image, workload, Service, Storage, environment value를 생성하지 않습니다.
- Renderer는 `KubernetesMigrationPlan`만 입력받고, manifest validator는 생성된 manifest set만 입력받습니다.
- ADK graph workflow, multi-agent, A2A, Helm, HPA, NetworkPolicy, Cluster apply는 이번 작업 범위가 아닙니다.
- live endpoint로 Repository를 전송하는 실행은 별도 사용자의 명시적 승인이 있을 때만 합니다.

## 4. 구현 순서

### Phase 0 — 계약 먼저 고정

계획 문서의 **Task 0**을 구현하십시오.

생성 대상:

~~~text
tests/fixtures/adk_migration_contract/question-dispositions.json
tests/fixtures/adk_migration_contract/stop-gate-cases.json
tests/test_migration_contract.py
~~~

반드시 고정할 계약:

- 질문 중요도: `required`, `conditional`, `optional`
- 질문 상태: `confirmed`, `inferred`, `unresolved`, `conflicting`, `not_applicable`
- 모델 문장만으로 `unresolved`를 인정하지 않음
- `AnalysisResult`는 도메인 결과, `run_metadata`는 실행 telemetry
- 실행 artifact에서는 `analysis-result.json`과 Secret-safe `run-metadata.json`을 분리
- `exploration_signals` 허용 필드:

  ~~~text
  question_id
  trigger_rule_id
  observed_fact_ref
  candidate_observation_kind
  ~~~

- `workload=Deployment`, `port=8080`, `next_tool=read_file`, `confirmed` 같은 결론·상태·행동은 signal에 넣지 않음
- Evidence가 0건이면 분석 제출 불가
- positive 값에 Evidence가 없으면 제출 불가
- duplicate/no-progress/iteration budget 초과는 bounded stop

실행:

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_migration_contract.py
~~~

RED를 확인한 뒤 최소 구현하고, focused test가 통과하면 다음 commit을 생성하십시오.

~~~text
test: define migration exploration contracts
~~~

### Phase 1 — 순수 탐색 정책

계획 문서의 **Task 1**을 구현하십시오.

~~~text
migration_assistant/exploration_policy.py
tests/test_exploration_policy.py
~~~

정책은 Kubernetes 질문과 검색 우선순위를 정의하지만 결론값을 만들면 안 됩니다. 언어별 if/else 실행 흐름을 추가하지 마십시오.

commit:

~~~text
feat: define migration exploration signals
~~~

### Phase 2 — Coverage와 Context Projection

먼저 **Task 2**에서 Secret-safe coverage ledger를 구현하십시오. 그 다음 **Task 2A**에서 반드시 다음 피드백 경로를 연결하십시오.

~~~text
Tool result
  -> ExplorationLedger update
  -> CoverageSnapshot
  -> ContextProjection
  -> next model context metadata
  -> Agent chooses an allowed Tool
~~~

중요한 점은 coverage를 기록하는 것만으로는 모델 행동이 바뀌지 않는다는 것입니다. `run_metadata`에만 저장하지 말고, 다음 LLM 호출 전에 미해결 질문 ID·우선순위·signal rule ID를 Secret-safe compact metadata로 전달하십시오.

단, Context Projection도 구체적인 path, port/image 값, 특정 `next_tool`을 만들면 안 됩니다.

commit:

~~~text
feat: track migration exploration coverage
feat: project migration coverage into model context
~~~

### Phase 3 — Agent instruction 개편

계획 문서의 **Task 3**을 구현하십시오.

Instruction은 다음 네 부분을 가져야 합니다.

~~~text
Role: Kubernetes DevOps Engineer 관점의 read-only migration analyst
Mission: 이관 결정에 필요한 최소 line-backed Evidence 수집
Policy: Tier 0 -> Tier 1 -> 실제 hit 기반 Tier 2/3
Stop: confirmed/inferred/unresolved/conflicting/not_applicable을 분류하고 validate_analysis
~~~

“전체 Repository를 설명한다”는 문구를 다시 넣지 마십시오. 목표는 Repository 전체 요약이 아니라 Kubernetes 배포 결정에 필요한 최소 근거입니다.

commit:

~~~text
refactor: focus agent on Kubernetes migration questions
~~~

### Phase 4 — Signal과 기계적 Stop Gate

Task 4에서 advisory signal을 연결하고, Task 5에서 Task 0의 Stop truth table을 코드로 구현하십시오.

주의할 점:

- Tool은 관찰 사실을 반환합니다.
- Signal은 다음 관찰을 위한 힌트일 뿐 결론이 아닙니다.
- 모델이 “못 찾았다”고 말하는 것만으로 genuine `unresolved`가 되지 않습니다.
- Ledger가 탐색 범위, pattern, scope 제한, 관찰 횟수/budget, 종료 이유를 검증해야 합니다.
- conflicting positive observation은 자동으로 하나를 선택하지 않습니다.

commit:

~~~text
feat: guide exploration from observed signals
feat: bound migration exploration completion
~~~

### Phase 5 — Trajectory 평가와 live gate

Task 6의 trajectory evaluator는 다음을 평가하십시오.

- 첫 Tool이 `inspect_target`인지
- required 질문의 disposition 충족률
- positive Evidence가 실제 관찰 line에 연결되는지
- 미근거 positive value 수가 0인지
- grounding 오류 후 fresh observation이 있었는지
- duplicate와 정상 recovery 재시도를 구분하는지
- no-progress/iteration budget이 bounded stop 되는지
- context projection이 과도한 raw 내용이나 Secret을 노출하지 않는지

`question_coverage >= 4`, `duplicate_rate == 0`처럼 target/model에 과적합되는 고정 기준은 사용하지 마십시오.

Task 7의 live 실행 전에는 다음 preflight metadata를 남기십시오.

~~~text
target absolute path
repository revision
endpoint host (Secret 제외)
model ID
전송 범위
approval reference
budget / timeout
~~~

비교 모델 실행 시 model ID 외 endpoint 정책, Repository revision, prompt, Tool surface, budget, timeout을 고정하고 output directory만 분리하십시오. smoke가 실패하면 공식 3-run으로 확대하지 마십시오.

## 5. 검증 명령

Task별 focused test:

~~~powershell
python -m pytest -q -p no:cacheprovider tests/test_migration_contract.py
python -m pytest -q -p no:cacheprovider tests/test_exploration_policy.py
python -m pytest -q -p no:cacheprovider tests/test_exploration_ledger.py tests/test_exploration_context.py
python -m pytest -q -p no:cacheprovider tests/test_adk_runner_recovery.py tests/test_phase1_adk_contract.py
~~~

전체 검증:

~~~powershell
python -m pytest -q -p no:cacheprovider
~~~

또는:

~~~powershell
.\scripts\run_tests.ps1
~~~

기존 known baseline인 Windows subprocess UTF-8 실패는 새 실패와 구분해 기록하십시오. 실행하지 않은 테스트를 통과했다고 보고하지 마십시오.

## 6. 커밋·보고 규칙

각 Phase는 다음 순서를 지키십시오.

~~~text
failing test 작성
-> RED 확인
-> 최소 구현
-> focused verification
-> 해당 기능과 테스트를 함께 commit
-> commit hash와 검증 결과 보고
~~~

중간에 계획과 실제 코드 계약이 충돌하면 조용히 범위를 넓히지 말고 다음을 보고하십시오.

~~~text
충돌한 계획 문장
실제 코드 근거
안전한 대안
사용자에게 필요한 결정
~~~

특히 다음 작업은 임의로 실행하지 마십시오.

- `jpetstore-6` 또는 다른 Repository의 live endpoint 전송
- solar model 비교 실행
- dependency 설치 또는 외부 network 접근
- 기존 사용자 변경을 덮어쓰는 Git 명령
- public Tool 추가

## 7. Claude Code 시작용 복사·붙여넣기 프롬프트

아래 프롬프트를 Claude Code 세션의 첫 메시지로 사용할 수 있습니다.

~~~text
이 Repository의 AGENTS.md와
docs/superpowers/handoffs/2026-08-06-claude-code-migration-agent-implementation-handoff.md를 먼저 읽어 주세요.

그 다음 원본 계획인
docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md의 Task 0만 구현해 주세요.

목표는 Kubernetes migration exploration contract를 결정론적 테스트로 고정하는 것입니다. 현재 public Agent Tool 8개, read-only Repository, Secret redaction, generic fallback, Evidence grounding, budget/recovery 불변식을 유지해 주세요.

작업 순서는 failing test -> RED 확인 -> 최소 구현 -> focused test -> 한 단계 commit입니다. Task 0 focused test가 통과하기 전에는 Task 1 이후로 진행하지 마세요.

live endpoint 전송, 외부 network, dependency 설치, target Repository 수정은 하지 마세요.

완료 시 변경 파일, 실행한 명령과 결과, commit hash, 남은 위험을 한국어 존댓말로 보고해 주세요.
~~~

## 8. 성공 조건

Claude Code가 첫 handoff 단계에서 아래를 만족하면 올바르게 시작한 것입니다.

- Task 0 테스트가 실제로 RED였다가 최소 구현 후 통과합니다.
- `unresolved`가 모델 문장만으로 승인되지 않습니다.
- `AnalysisResult`와 `run_metadata`가 섞이지 않습니다.
- signal에 결론값·상태·특정 Tool 호출이 들어가지 않습니다.
- 변경이 Task 0 범위를 넘지 않습니다.
- focused test 결과와 commit hash가 보고됩니다.

