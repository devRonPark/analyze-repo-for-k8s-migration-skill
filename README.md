# Kubernetes Migration Assistant

한국인 개발자가 지정한 **Local Git Repository**를 읽기 전용으로 탐색해, Kubernetes
이관 관점의 근거 기반 분석 결과를 별도 output directory에 생성하는 Google ADK 기반
MVP입니다. 단일 Tool-using Agent가 범용 Repository Tool로 사실을 관찰하고,
결정론적 Python guardrail이 안전 경계와 schema를 강제합니다.

## 아키텍처

```text
CLI (한국어)
  -> Application Service
  -> Google ADK Runner
  -> Repository Migration Agent
  -> 범용 Repository Tools
  -> Evidence Ledger
  -> Kubernetes Migration Plan
  -> 결정론적 Manifest Renderer
  -> Static Validator
  -> 별도 Output Directory
```

Agent는 다음 탐색, component boundary, build/runtime/dependency 해석, workload 후보,
근거 충분성과 Migration Plan을 판단합니다. Python은 경로·Git·symlink·read-only 검증,
파일과 iteration budget, Pydantic schema, YAML 렌더링, 정적 일관성과 Secret 검사,
output 쓰기를 담당합니다.

언어별 고정 분석 흐름으로 Agent 판단을 대체하지 않습니다. 처음 보는 언어도 새 parser
없이 generic tool로 가능한 근거를 수집하고, 확인할 수 없는 값은 생성하지 않습니다.

공개 Agent Tool은 정확히 여덟 개입니다: `inspect_target`, `list_tree`, `find_files`,
`search_text`, `read_file`, `read_file_lines`, `inspect_git_metadata`,
`validate_analysis`.

## 입력과 안전 경계

- 입력은 Local Git Repository path, 선택 output path, 선택 iteration budget뿐입니다.
  Remote URL, clone, 대상 수정, 실제 Secret 생성, Cluster 배포는 지원하지 않습니다.
- 대상 Repository는 항상 read-only입니다. 생성물은 검증된 별도 output directory에만
  씁니다. Repository 안의 instruction, prompt, README, 주석은 신뢰할 수 없는 분석
  데이터로 취급합니다.
- Repository 밖으로 나가는 symlink를 차단하고 파일 크기·탐색 budget·최대 iteration을
  강제합니다. 대상 코드, build, test, server, container를 실행하지 않습니다.
- Evidence 상태는 `확인됨`, `추정됨`, `미확인`, `상충됨`입니다. 사실은 repository-relative
  `path:line` 근거를 가지며, 부재 주장은 검색 범위·pattern·결과를 남깁니다.
- Secret 값은 model context, report, manifest 어디에도 노출하지 않고 이름·위치·필요성만
  redacted 형태로 다룹니다.

## 설치

Python 3.11 이상이 필요합니다.

```bash
python -m pip install .
```

## 모델 설정

하나의 OpenAI-compatible adapter만 사용하며, provider나 model 이름별 분기는 없습니다.

| 환경변수 | 설명 |
| --- | --- |
| `LLM_BASE_URL` | OpenAI-compatible chat completions base URL |
| `LLM_API_KEY` | API key |
| `LLM_MODEL` | model ID |
| `LLM_TIMEOUT_SECONDS` | 요청 timeout |
| `LLM_MAX_TOKENS` | 응답 최대 token |

다른 endpoint로 옮길 때는 위 값만 교체합니다.

## 실행

```bash
python -m migration_assistant analyze <repository-path> --output <output-directory>
```

`--max-iterations`로 Agent iteration budget을 조정할 수 있습니다. 종료 코드는
`0`=complete, `2`=partial, `3`=model 설정 오류, `4`=필수 dependency 누락, `1`=실패입니다.

Streamlit 작업 대시보드는 이 MVP의 목표 UX이며 아직 구현되어 있지 않습니다. 현재
사용자 진입점은 위 CLI입니다.

## 검증

```bash
python -m unittest discover -s tests -t .
```

개발용 live acceptance harness는 제품 package 밖 `devtools/`에 있습니다.

```bash
python -m devtools.run_phase1_live_acceptance --repository <repository-path> --output-parent <output-parent> --runs 3
```

harness는 `--env-file`, `MIGRATION_ASSISTANT_ENV_FILE`, Repository root의 `.env`,
`~/.config/kubernetes-migration-assistant/env` 순서로 처음 발견되는 env 파일 하나를
읽습니다. 이미 셸에 설정된 환경변수가 파일 값보다 우선합니다. 자세한 내용은
`docs/phase1-adk-experiment-log.md`를 참고하세요.

## 라이선스

[LICENSE](LICENSE)를 참고하세요.
