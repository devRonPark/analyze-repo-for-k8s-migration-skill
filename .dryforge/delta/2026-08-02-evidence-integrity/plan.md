# Phase 1 Evidence Integrity Delta Cycle 실행 계획

```yaml
cycle_type: delta
delta_id: 2026-08-02-evidence-integrity
cycle_marker: 2026-08-02-evidence-integrity
baseline_commit: 1686be7
product_baseline: 1686be7
control_plane_parent_commit: b761676
control_plane_commit: HEAD after this documentation-only routing commit (parent b761676)
executable_plan_path: .dryforge/delta/2026-08-02-evidence-integrity/plan.md
first_task: D1
last_task: D6
root_plan_execution: forbidden in this delta
t7_execution: forbidden until this delta is complete and Claude approves it
routing_status: BLOCKED
first_cycle_graph: unchanged
regen_barriers: []
```

이 계획은 기존 First Cycle의 T1~T14 계획을 대체하지 않는다. 이 delta의 단일 실행 대상은
`.dryforge/delta/2026-08-02-evidence-integrity/plan.md`이며 첫 task는 D1, 마지막 task는 D6이다.
root `.dryforge/plan.md`의 T1~T14 graph는 이번 delta 실행 대상이 아니다. T7은 이 delta가
완료되고 Claude가 승인하기 전까지 실행 금지다. 현재 routing은 BLOCKED이며, 아래 공식 계약상
delta plan을 직접 선택하는 `dryforge go` 호출이 없으므로 `dryforge go`를 실행하지 않는다.

## 실제 Dryforge routing 계약

설치된 `dryforge 1.1.1`의 실제 정의를 다음 파일에서 확인했다.

- `C:\Users\박병찬\.codex\plugins\cache\dryforge\dryforge\1.1.1\skills\go\SKILL.md:99-101`은
  사용자가 `go` skill을 호출하면 project-root-relative `.dryforge/{handoff,spec,plan}.md`를
  읽도록 한다. `go` skill에는 delta plan path 또는 cycle ID 인자가 없다.
- `...\skills\go\references\harness-lifecycle.md:8-18`은 `.dryforge/status.json`의
  `{ "initialized": true }` marker 존재 여부로 cycle을 구분한다. marker가 있으면 delta,
  없으면 first cycle이다. marker는 first cycle의 성공적인 user approval/archive 뒤에 생성된다.
- `...\skills\go\SKILL.md:124-134,260-295`는 marker가 없을 때 first-cycle precondition과
  root 3-doc/harness 생성·archive를 적용한다. 현재 repository에는 `.dryforge/status.json`이
  없으므로 delta로 간주할 근거가 없다.
- `...\skills\go\agents\openai.yaml:1-7` 및 plugin manifest의 go default prompt는
  `Use dryforge go to execute the 3-doc in .dryforge.`뿐이다. 설치된 command/interface에는
  active cycle 선택, cycle ID, 또는 plan path 선택 옵션이 없다.

따라서 공식 Delta Go 호출 문구는 없다. 위의 root 호출 문구를 delta 호출이라고 재해석할 수
없으며, 그것은 root `.dryforge/plan.md`를 읽어 T1부터 실행할 수 있는 first-cycle 경로다.
`status.json`을 추측으로 생성하지 않는다. 이 상태에서 승인된 실행 경로에서 root T1~T14
실행 가능성을 제거하고, 공식 plan 선택 방법이 추가될 때까지 BLOCKED로 유지한다.

## D1 — Path 및 Secret 경계

목표: 모든 Repository observation과 출력 가능한 관찰 결과에 동일한 canonical path 및
redaction 경계를 적용한다.

### Baseline에서 이미 확인된 동작

- `migration_assistant/repository_tools.py:57-67`의 `_resolve`는 repository 밖 traversal을
  거부하고 각 path component의 symlink/junction을 검사한다.
- `migration_assistant/repository_tools.py:69-80,189-229`의 file read는 file type, file
  size, file budget과 line range를 제한한다.
- `migration_assistant/repository_tools.py:82-85`의 기본 redactor와
  `migration_assistant/analysis.py:42-43,103-111`의 schema 입력 redaction은 assignment형
  secret 및 bearer 일부를 처리한다.
- `migration_assistant/repository_tools.py:231-248`의 `inspect_git_metadata`는 path를
  받지 않고 branch, HEAD, short status만 제한적으로 반환한다. `.git/...` 임의 path를
  읽거나 Git config 전체/credential을 반환하는 동작은 없다. 이것은 예외적으로 허용된
  metadata 관찰이며 Agent Tool surface 8개는 유지한다(`migration_assistant/tool_contract.py:6-14`).

### 실제 잔여 gap — D1은 아래 항목만 구현 대상으로 삼는다

1. `find_files`의 glob 결과가 `_resolve`를 거치지 않는다
   (`migration_assistant/repository_tools.py:121-134`, 특히 `127-131`). 결과마다 canonical
   boundary와 symlink/junction 검사를 재적용하고, 결과에 대해 `.git` component를
   case-insensitive하게 차단해야 한다. 현재 glob filter는 `".git" in parts`를 그대로
   사용하므로 `.GIT`/`.Git` 및 다른 case variant를 통과시킨다.
2. 같은 case-insensitive `.git` 검사가 공통화되어 있지 않다. `_reject_git`는
   `migration_assistant/repository_tools.py:48-52`, `_resolve` 호출은 `57-60`, tree walk
   검사는 `103-107` 및 내부 walk `172-176`에 각각 분산되어 모두 exact-case 비교다.
   따라서 `list_tree`, `find_files`, `search_text`, `read_file`, `read_file_lines`의 입력과
   glob/walk 결과가 동일한 검사를 받는지 보장하는 것이 잔여 범위다. 이미 작동하는
   outside/symlink/junction 검사를 다시 설계하지 않는다.
3. Git remote URL credential redaction이 없다. `inspect_git_metadata`는
   `migration_assistant/repository_tools.py:231-248`에서 remote를 반환하지 않고,
   `_redact`(`82-85`)도 URL authority `user:password@host`를 처리하지 않는다. D1에서
   승인된 metadata에 remote URL이 포함되는 경우 scheme/host/port/path/query는 보존하고
   authority credential 값만 redaction하는 공통 경계를 정의해야 한다. Git config 전체나
   credential 자체를 반환하는 것은 범위 밖이다.
4. JDBC 및 일반 connection URL credential redaction이 없다. 현재 redactor는
   `migration_assistant/repository_tools.py:25-28,82-85`,
   `migration_assistant/exploration.py:50-52,130-144`,
   `migration_assistant/analysis.py:37-43,68-70`에서 assignment/bearer 패턴만 처리한다.
   JDBC URL과 일반 URL의 authority/query credential 값이 Tool output과 Evidence에 남지
   않도록 같은 URL redaction을 추가해야 한다.
5. 공통 redaction이 Tool history, exception, artifact, report까지 전파되지 않는다.
   `DuplicateTracker`는 `migration_assistant/adk_tools.py:19-30`에서 raw normalized args를
   반환하고, `_call`은 `72-81`에서 raw exception을 ledger와 response에 저장한다.
   Exploration history는 `migration_assistant/exploration.py:91-94,137-144`의 별도
   assignment-only redactor를 사용한다. artifact/report는
   `migration_assistant/analysis.py:165-178,249-252`의 별도 경로이고, ADK exception은
   `migration_assistant/adk_runner.py:140-146,153-173`에서 일부 API key만 치환한다.
   이 분산 경로들을 하나의 redactor 경계로 연결하는 것이 잔여 범위이며, D1에서 새
   Tool을 추가하거나 `inspect_git_metadata` 예외를 넓히지 않는다.

`inspect_git_metadata`는 다음 제한된 예외다: `.git` 직접 경로를 입력받지 않고, 승인된
branch/HEAD/status 및 향후 명시적으로 승인된 safe metadata만 반환하며, Git config 전체와
credential을 반환하지 않는다. 나머지 다섯 read/search 계열 Tool은 `.git` 직접 경로를
거부한다. Agent Tool surface는 정확히 기존 8개를 유지한다.

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
