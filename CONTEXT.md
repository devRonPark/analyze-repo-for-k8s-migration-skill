# 제품 문맥

## 확정된 제품 문맥

제품은 사용자가 지정한 **Local Git Repository**를 자율적으로 탐색해 Kubernetes
이관 관점의 근거 기반 분석 결과, 구조화된 Kubernetes Migration Plan, 그리고
결정론적으로 렌더링한 manifest 초안을 별도 output directory에 내놓는 개발자용
도구다. 단일 Tool-using Google ADK Agent MVP가 목표다.

분석은 특정 언어 parser를 순서대로 실행하는 workflow가 아니다. Agent는 구조를
확인하고 발견 근거를 평가한 뒤 다음 파일/검색을 선택하며, 충분한 근거 또는 scoped
unknown/conflict에 도달할 때까지 탐색한다. 처음 보는 언어도 generic tool로 가능한
근거를 수집하고, 확인할 수 없는 값은 생성하지 않는다.

## 구현 상태

| 영역 | 상태 |
| --- | --- |
| ADK Python package, Agent, 여덟 개 Tool, Pydantic schema, guardrail | 구현됨 |
| OpenAI-compatible adapter, tool protocol, typed recovery, `analyze` CLI | 구현됨 |
| 개발 전용 live acceptance harness (`devtools/`) | 구현됨. live 3-of-3 gate는 미실행 |
| Streamlit 작업 대시보드 | 미구현 |

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

## 재사용하는 행동 규칙

이전 OpenCode Skill 자산은 제거됐고, 그중 다음 판단 규칙만 현재 Agent 지침과
테스트 안에 행동 규칙으로 남아 있다. 파일 참조가 아니라 계약으로만 유지한다.

- high-signal 우선 탐색과 실행 단계(install/build/image-build/startup) 분리
- evidence 상태 분류와 `path:line` 근거, 부재 주장의 검색 범위 기록
- target read-only, path escape 차단, Secret redaction
- Dockerfile 없음과 monorepo component 관계 처리
- Go를 포함한 generic fallback: 언어 전용 parser를 추가하지 않는다

## MVP acceptance 기준

주요 Local checkout: `spring-petclinic`, `jpetstore-6`,
`full-stack-fastapi-template`. 이 이름과 구조는 production logic에 하드코딩하지
않으며 경로는 실행 인자로만 전달한다. 별도 Go holdout에서는 module, entry point
후보, build/port/env 근거를 generic tool로 다루고, 부족한 입력은 미확인으로
남기거나 근거 있게 manifest 생성을 차단한다.

## 재발 방지 계약 메모

- `Agent Tool surface`는 위 여덟 개로 고정한다. `render_manifests`,
  `validate_manifests`, output directory 생성, artifact 저장, ZIP 생성은 Agent Tool Call이
  아니라 valid KubernetesMigrationPlan 뒤 Application Service의 결정론적 책임이다.
- 사용자 CLI는 `analyze`이며 Repository 탐색, AnalysisResult, schema validation,
  `analysis-result.json`, `analysis-report.md`까지 완료한다. `generate` command와
  plan/render/validate artifact는 별도 단계에서 등록한다.
- `GO_HOLDOUT_REPO`는 일반 offline unit test와 분리할 수 있지만 최종 release acceptance에는
  필수다. 누락 또는 invalid path는 skip/PASS가 아닌 configuration failure다.
- `devtools/`는 개발 전용이다. 제품 package는 이를 import하지 않으며 배포
  artifact나 ADK 실행에 필요하지 않다. 제품 완료 증거는 테스트, CLI 결과와 생성
  artifact다.
