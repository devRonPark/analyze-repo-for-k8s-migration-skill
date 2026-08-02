# OpenCode 레거시 제거 설계

## 목표

저장소를 Kubernetes Migration Assistant의 현재 ADK 실행 경로만 포함하는
구조로 정리한다. OpenCode Skill 패키지, 설치/distribution, custom command,
레거시 report 계약, OpenCode acceptance harness와 그 전용 문서·fixture·테스트는
현재 제품의 실행 경로와 무관하므로 제거한다.

## 보존 경계

- `migration_assistant/`: ADK agent, OpenAI-compatible adapter, repository tools,
  schema, guardrail, analysis, renderer, service와 CLI
- `devtools/run_phase1_live_acceptance.py`, `devtools/env_file.py`: 현재 ADK live
  acceptance와 개발용 LLM 환경 변수 로더
- ADK 경로를 직접 검증하는 테스트: agent, analysis, CLI, exploration, live planner,
  model compatibility, phase1 ADK/live harness, repository tools, target safety,
  migration assistant foundation
- `docs/phase1-adk-experiment-log.md`, `docs/agent-tool-design-best-practices.md`,
  2026-08-02 ADK 관련 `docs/superpowers` 문서
- `AGENTS.md`, `CONTEXT.md`, `CLAUDE.md`, `pyproject.toml`, `uv.lock`, workflow와
  제품 라이선스/변경 기록. 단, 내용은 새 ADK 경계에 맞게 갱신한다.

## 제거 범위

- root `SKILL.md`, `agents/`, `runtime/`, `runtime-files.txt`
- OpenCode Skill용 `assets/`, `contracts/`, `references/`
- OpenCode/Qwen/Codex 설치·distribution·report validator·scenario evaluator와
  acceptance 전용 `scripts/` 전체
- OpenCode Skill 패키지·report contract·distribution·scenario·legacy summary
  전용 테스트와 fixture
- `docs/development/`, OpenCode/Qwen 조사 `memory/`, `_review/`의 구형 report
  산출물
- 구형 `docs/superpowers/specs/2026-07-30-det-001-*`와 OpenCode 평가 golden
  자료

## 재작성

- `README.md`: 한국어 Streamlit/ADK 제품 목적, 입력 안전 경계, 실행/검증 방법만
  설명한다.
- `AGENTS.md`, `CONTEXT.md`, `CLAUDE.md`: OpenCode 레거시 경계를 삭제하고 현재
  ADK architecture와 협업 규칙만 남긴다.
- `.github/workflows/test.yml`: legacy quality gate 대신 현재 Python package와
  ADK 테스트 명령만 실행한다.
- `CHANGELOG.md`: 현재 제품의 ADK migration 기록으로 정리한다.

## 영향 분석과 보호 조치

- 레거시 삭제와 workflow·문서·테스트 정리는 하나의 변경 단위로 처리한다. 실행
  파일만 먼저 삭제하면 CI와 사용자 안내가 깨진 상태가 된다.
- 현재 사용자 변경 중 `test_package.py`, `test_report_contract.py`,
  `test_skill_validator.py` 등 삭제 대상 레거시 테스트에 대한 수정은 파일 삭제와
  함께 사라진다. 이는 되돌리기가 아니라 더 이상 제품 범위에 없는 테스트의 제거다.
- `devtools/env_file.py`, `tests/test_env_file_loader.py`,
  `tests/test_phase1_live_acceptance_harness.py`,
  `docs/phase1-adk-experiment-log.md`의 변경은 ADK live 검증과 직접 관련되므로
  보존한다.
- `tests/test_phase1_adk_contract.py` 등 정책 문서를 읽는 ADK 테스트는
  `AGENTS.md`와 `CONTEXT.md` 재작성 후 우선 검증한다.
- `.github/workflows/test.yml`에서 legacy `scripts/` 호출이 남아 있으면 현재
  Python package와 ADK 테스트 명령으로 같은 변경에서 교체한다.

## 실행 전 체크포인트

1. 삭제 후보별로 `migration_assistant/`, `devtools/`, 보존 대상 테스트와 workflow의
   import·경로 참조를 다시 검색한다.
2. workflow, README, 정책 문서를 먼저 ADK 기준으로 재작성해 삭제 뒤에도 남는
   실행 방법과 검증 방법을 제공한다.
3. 삭제 직후 tracked 파일에서 OpenCode, Qwen, Skill distribution/install/runtime의
   실행 참조가 남지 않는지 확인한다.
4. 남은 ADK 테스트를 우선 실행하고, Windows Codex sandbox의 temporary-directory
   ACL 오류는 제품 테스트 실패와 분리해 full-access 비교 실행으로 판정한다.

## 필요성 판단

이 작업은 ADK 런타임을 실행하기 위한 기술적 선행조건은 아니다. 그러나 현재
OpenCode 전용 테스트와 문서가 ADK 경로와 함께 남아 있어 환경 오류를 제품 결함처럼
보이게 하고, CI와 사용법을 잘못 안내하며, 이후 변경에서 레거시 report/distribution
코드를 재사용할 위험을 만든다. 따라서 ADK MVP를 계속 개발하고 검증하기 위한
구조적 정리로 수행한다.

## 검증 기준

1. `migration_assistant`와 `devtools`에서 삭제된 경로를 import하지 않는다.
2. tracked 파일에 `OpenCode`, `Qwen`, Skill distribution/install/runtime 관련
   실행 참조가 남지 않는다. 정책 문서의 과거 경계 설명도 현재 구조에 맞게
   갱신한다.
3. 현재 테스트만 수집되며, legacy validator/report/evaluation 테스트가 남아
   있지 않다.
4. Windows에서는 `.venv`와 user temp를 테스트 검색 대상에서 제외하고,
   샌드박스 ACL에 막히는 테스트는 명시적 full-access 검증으로 분리한다.
5. 변경 전 사용자 수정사항은 보존하며, 삭제 대상이 아닌 파일은 내용과 Git
   상태를 확인한 뒤에만 수정한다.
