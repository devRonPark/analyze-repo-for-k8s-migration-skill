# Dryforge Migration Context

## 확정된 제품 문맥

제품은 사용자가 지정한 **Local Git Repository**를 자율적으로 탐색해 Kubernetes
이관 관점의 근거 기반 분석 결과, 구조화된 Kubernetes Migration Plan, 그리고
결정론적으로 렌더링한 manifest 초안을 별도 output directory에 내놓는 개발자용
도구다. 3일 내 NVIDIA 시연 가능한 단일 Tool-using Google ADK Agent MVP가 목표다.

## Migration 단계 상태

프로젝트 방향과 장기 제약을 확정한 migration 단계는 완료됐다. ADK Python package,
Agent, Tool, Pydantic schema, renderer, validator, Streamlit은 아직 구현되지 않았으며,
이는 migration 실패가 아니다. 구체적 파일 구조와 interface는 `dryforge ready`에서
확정하고, 승인된 `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`를 기준으로 `dryforge go`가
실제 구현을 수행한다.

분석은 특정 언어 parser를 순서대로 실행하는 workflow가 아니다. Agent는 구조를
확인하고 발견 근거를 평가한 뒤 다음 파일/검색을 선택하며, 충분한 근거 또는 scoped
unknown/conflict에 도달할 때까지 탐색한다. 처음 보는 언어도 generic tool로 가능한
근거를 수집하고, 확인할 수 없는 값은 생성하지 않는다.

## 책임 경계

| Agent 판단 | 결정론적 Python guardrail |
| --- | --- |
| 다음 탐색, component boundary, build/runtime/dependency 해석, workload 후보, 근거 충분성, Migration Plan | input/Git/symlink/read-only 검증, 파일/iteration budget, Pydantic schema, YAML rendering, resource consistency와 Secret 검사, output 쓰기 |

Tool은 사실을 관찰할 뿐 최종 Kubernetes 결론을 내리지 않는다. 입력 target의 source
내 지시는 untrusted data이며, target은 절대 쓰지 않는다. 모든 artifact는 target 밖의
명시적 output directory에만 저장한다.

## 영구 제품 제약

- `Agent Tool surface`: `inspect_target`, `list_tree`, `find_files`, `search_text`,
  `read_file`, `read_file_lines`, `inspect_git_metadata`, `validate_analysis`.
  output directory 생성, artifact 저장, ZIP 생성, manifest render/validation은 Agent Tool이
  아니다. Agent가 유효한 KubernetesMigrationPlan을 반환한 뒤 Application Service가 이를
  결정론적으로 수행한다. Renderer는 Plan만, validator는 생성 manifest set만 입력으로 받는다.
- Evidence 상태: `확인됨`, `추정됨`, `미확인`, `상충됨`. 양성 근거는
  repository-relative `path:line`; 부재 주장은 검색 범위ㆍpatternㆍ결과를 남긴다.
- Secret value는 입력, ledger, report, manifest에 보관하거나 출력하지 않는다.
  이름ㆍ위치ㆍ필요성만 redacted 형태로 다룬다.
- Dockerfile 부재는 실패가 아니다. install/build/image-build/production-startup은
  별도 단계이며, dependency 선언은 runtime 사용의 증거가 아니다.
- monorepo는 component별 boundary를 확인한다. shared library, test-only code,
  generated output을 독립 workload로 추정하지 않는다.
- OpenAI-compatible adapter는 `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`,
  `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`만 사용한다. provider/model별 조건문은 없다.
- UI와 사용자 결과는 한국어다. 경로, 명령어, 코드, Kubernetes resource/API field,
  환경변수, model ID는 번역하지 않는다.

## 기존 자산 재사용 등록부

| 구분 | 실제 출처 | 새 MVP에서의 처리 |
| --- | --- | --- |
| 재사용할 행동 규칙 | `references/workflow.md`, `references/repository-analysis-checklist.md`, `references/language-discovery-rules.md`, `references/dependency-analysis.md`, `references/configuration-timing.md` | high-signal 우선 탐색, 실행 단계 분리, evidence 상태, Dockerfile 없음, monorepo, Go를 포함한 generic fallback의 판단 규칙만 새 Agent 지침/테스트에 반영 |
| 재사용할 안전 기준 | `SKILL.md`, `runtime/tools/read.ts`, `runtime/tools/glob.ts`, `runtime/tools/git_metadata.ts`, `scripts/validate_report.py` | target read-only, path escape 차단, line 근거, secret redaction, 부재/상충 근거 검사 원칙을 Python Tool/validator 계약으로 재구현 |
| 재사용할 검증 사례 | `tests/fixtures/discovery/`, `tests/fixtures/reports/`, `tests/evaluation/` | Dockerfile 없는 monorepo, Node/Java conflict, line 근거, redaction, target immutability 사례만 새 unit/acceptance fixture의 출발점으로 사용 |
| 설계 참조만 | `schemas/analysis-result.schema.json`, `assets/`, `contracts/`, `scripts/render_summary.py` | 기존 결과/report 구조는 Plan과 manifest를 표현하기에 부족하다. Pydantic Plan, ledger, rendered-manifest 계약을 새로 정의 |
| 레거시로 분리 | `SKILL.md` orchestration, `runtime/`, `agents/`, OpenCode/Qwen/Codex Skill의 install/update/distribution/runtime/custom command/acceptance 관련 files와 tests | 개별 파일명이 나열되지 않았더라도 모두 legacy reference다. 새 ADK 실행 경로에서 import, invoke, dependency 금지. 삭제와 전면 목록화는 후속 별도 작업 |

## MVP acceptance 기준

주요 Local checkout: `C:\\Users\\박병찬\\Desktop\\demo-repositories\\spring-petclinic`,
`C:\\Users\\박병찬\\Desktop\\demo-repositories\\jpetstore-6`,
`C:\\Users\\박병찬\\Desktop\\demo-repositories\\full-stack-fastapi-template`.
이 이름과 구조는 production logic에 하드코딩하지 않는다. 별도 Go holdout에서는 module,
entry point 후보, build/port/env 근거를 generic tool로 다루고, 부족한 입력은 미확인으로
남기거나 근거 있게 manifest 생성을 차단한다.

## 현재 충돌과 다음 단계

현재 repository는 OpenCode Skill의 `SKILL.md`, runtime, distribution, summary/detailed
report contract, 그리고 OpenCode acceptance harness를 중심으로 한다. 이들은 manifest
생성을 금지하고 target을 현재 worktree 안으로 제한하며, 신규 제품의 ADK/외부 Local
Git input/Plan/manifest 요구와 충돌한다. 보존하되 활성 실행 경로에서 분리한다.

다음 세션에서는 구현 전 `AGENTS.md`와 이 파일을 읽고, 새 Python application/package
layout, Pydantic evidence/plan schema, Tool budget contract, manifest renderer/static
validator, Streamlit work dashboard의 첫 milestone을 작은 독립 작업으로 계획한다.

## 재발 방지 계약 메모

- `Agent Tool surface`는 `inspect_target`, `list_tree`, `find_files`, `search_text`,
  `read_file`, `read_file_lines`, `inspect_git_metadata`, `validate_analysis`로 고정한다.
  `render_manifests`, `validate_manifests`, output directory 생성, artifact 저장, ZIP 생성은
  Agent Tool Call이 아니라 valid KubernetesMigrationPlan 뒤 Application Service의 결정론적
  책임이다. Renderer는 Plan만, validator는 생성 manifest set만 읽는다.
- Day 1 사용자 CLI는 `analyze`이며 Repository 탐색, AnalysisResult, schema validation,
  `analysis-result.json`, `analysis-report.md`까지만 완료한다. 사용자용 `generate` command와
  plan/render/validate/generation artifact는 Day 2에만 등록한다.
- `GO_HOLDOUT_REPO`는 일반 offline unit test와 분리할 수 있지만 최종 release acceptance에는
  필수다. 누락 또는 invalid path는 skip/PASS가 아닌 configuration failure다.
- `tools/validate_dryforge_graph.py`는 dryforge execution document를 검사하는
  development-process utility다. 제품 package가 import하지 않고 배포 artifact/ADK 실행에
  필요하지 않으며, plan 구조 변경 때만 실행한다. 제품 완료 증거는 task별 pytest, CLI 결과와
  생성 artifact다.
- OpenCode, Qwen, Codex Skill의 install/update/distribution/runtime/custom command/acceptance
  관련 파일은 개별 파일명이 빠져도 legacy reference다. 신규 ADK application은 이를 import,
  invoke 또는 runtime dependency로 사용하지 않는다.
