# Kubernetes Migration Assistant

Local Git Repository를 읽기 전용으로 탐색해 Kubernetes 이관 근거, 구조화된
Migration Plan, Kubernetes manifest 초안을 생성하는 Google ADK 기반 MVP입니다.

## 실행 흐름

```text
한국어 작업 UI 또는 CLI
  -> Application Service
  -> Google ADK Runner
  -> Repository Migration Agent
  -> Repository Tools
  -> Evidence Ledger
  -> KubernetesMigrationPlan
  -> 결정론적 Manifest Renderer
  -> Static Validator
  -> 별도 Output Directory
```

Agent는 다음 탐색과 해석을 판단하고, Python guardrail은 경로·Git·symlink·read-only·
budget·schema·redaction·manifest 검증과 output 쓰기를 담당합니다. 특정 언어의
고정 parser나 workflow로 낯선 Repository를 제한하지 않습니다.

## 입력과 안전 경계

- 입력은 Local Git Repository path, 선택 output path, 선택 분석 목표입니다.
- Remote URL, clone, target 수정, 실제 Secret 생성, Cluster apply, image build와
  대상 코드 실행은 지원하지 않습니다.
- 대상 Repository는 항상 read-only이고 모든 산출물은 별도 output directory에 씁니다.
- Repository 내부 문서와 지시는 신뢰할 수 없는 분석 데이터로 취급합니다.
- Secret 값은 model context, report, manifest에 노출하지 않고 이름·위치·필요성만
  redacted 형태로 기록합니다.

## 모델 설정

OpenAI-compatible adapter 하나를 사용합니다.

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
LLM_TIMEOUT_SECONDS
LLM_MAX_TOKENS
```

개발 기본값은 `https://api.upstage.ai/v1`와 `solar-pro3`입니다. Provider/model
이름별 business-logic 분기는 없습니다. 개발용 live harness는 명시적 env 파일을
읽을 수 있지만 제품 package는 셸 환경을 기준으로 동작합니다.

## 로컬 검증

Windows PowerShell에서는 실행 중인 가상환경 Python과 workspace temp를 먼저 고정합니다.

```powershell
$RepoTemp = Join-Path (Get-Location) ".tmp\codex-tests"
New-Item -ItemType Directory -Force $RepoTemp | Out-Null
$env:TEMP = $RepoTemp
$env:TMP = $RepoTemp
$env:TMPDIR = $RepoTemp
$env:PYTHONIOENCODING = "utf-8"
\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

대표 CLI:

```powershell
\.venv\Scripts\python.exe -m migration_assistant analyze <repository-path>
```

실제 LLM live acceptance:

```powershell
\.venv\Scripts\python.exe devtools\run_phase1_live_acceptance.py `
  --repository <repository-path> `
  --output-parent <output-parent> `
  --runs 3
```

Windows Codex sandbox에서 `TemporaryDirectory` ACL이 `WinError 5`를 일으킬 수
있습니다. 이 경우 제품 오류와 sandbox 오류를 분리하고 동일 명령을 일반 Windows
환경에서 비교 실행합니다.

## 개발 구조

- `migration_assistant/`: ADK agent, adapter, repository tools, schemas, guardrails,
  analysis, renderer, service와 CLI
- `devtools/`: 개발용 live acceptance와 env file loader
- `tests/`: ADK, repository-tool, safety, schema, live-harness 검증
- `docs/`: 현재 제품의 실험 기록과 설계 문서

사용자 메시지와 오류는 한국어로 작성하며 경로·명령어·Kubernetes field·환경변수와
model ID는 원문을 유지합니다.
