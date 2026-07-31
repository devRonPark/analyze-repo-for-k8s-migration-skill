# analyze-repo-for-kubernetes-skill

OpenCode에서 `analyze-repo-for-kubernetes` Skill을 로드하여 애플리케이션 Repository를 Kubernetes 이관 관점에서 근거 기반으로 분석합니다.

이 프로젝트가 지원하는 Agent Runtime은 OpenCode 순정 환경입니다. 분석 대상 Repository는 읽기 전용으로 취급하며, 분석 중 대상 파일을 수정하거나 배포 산출물을 생성하지 않습니다.

## 주요 기능

- Local Git worktree 대상 확인과 Target Resolution Gate
- Dockerfile이 없거나 모노레포인 Repository의 구조·런타임 탐색
- 배포 대상 후보, 저장소 런타임 의존성, 외부 런타임 의존성, 제외 항목 분류
- Build·Runtime 동작, 포트, 설정, 스토리지 및 의존성 분석
- 관계별 실행 위치와 설정별 적용 시점 분류
- `확인됨`, `추정됨`, `미확인`, `상충됨` 근거 수준 표시
- `설계 입력 충분`, `추가 정보 필요`, `분석 불가` 상태 판단
- 기본 `summary` 보고서와 명시적 요청에 의한 `detailed` 보고서
- Summary/Detailed/JSON 보고서 계약과 정적 Report Validator
- Repository prompt injection 방어와 read-only 기본 권한
- OpenCode Skill 발견·권한·비관련 요청·대상 Repository 불변성 Acceptance Harness

## OpenCode 설치

먼저 이 Repository를 clone하고 이동합니다.

```bash
git clone https://github.com/devRonPark/analyze-repo-for-k8s-migration-skill.git ~/skills-src/analyze-repo-for-k8s-migration-skill
cd ~/skills-src/analyze-repo-for-k8s-migration-skill
```

전역 OpenCode Skill을 설치합니다.

```bash
bash scripts/install-opencode.sh
```

기본 설치 위치:

```text
~/.config/opencode/skill/analyze-repo-for-kubernetes
```

설치 스크립트는 allowlist 기반 distribution을 생성하고 패키지 구조를 검사한 뒤 파일을 복사합니다. 또한 `kubernetes-migration-analyzer` Agent와 `/analyze-repo-for-kubernetes` command를 전역 OpenCode 설정에 등록합니다. 동일한 Skill ID가 `~/.agents/skills` 또는 `~/.claude/skills` 같은 호환 경로에 이미 있어도 설치를 중단하지 않고 현재 배포본으로 함께 갱신합니다.

특정 Project 내부에 설치할 수도 있습니다. 이 방식은 해당 Project에 `.opencode/skill`, `.opencode/agent`, `.opencode/command`를 생성하므로, 분석 대상 Repository를 변경하지 않아야 하는 경우에는 전역 설치를 사용합니다.

```bash
bash scripts/install-opencode.sh --project-local /path/to/project
```

## OpenCode Agent 설정

`runtime/opencode.json`에는 로컬 OpenAI-compatible endpoint, 모델 선택, Skill allowlist, read-only 권한, 제한된 Git 조회 규칙이 정의되어 있습니다. 환경에 맞게 endpoint와 model을 확인한 뒤 OpenCode에 적용합니다.
`bash scripts/install-opencode.sh`는 `/analyze-repo-for-kubernetes` custom command와 해당 command가 사용할 `kubernetes-migration-analyzer` agent까지 함께 등록합니다.

사용자 실행과 격리 테스트 실행은 서로 다른 경계를 사용합니다.

사용자 실행은 분석 대상 Application Repository에서 OpenCode를 시작하고,
현재 사용자의 전역 config·Agent·`~/.config/opencode/skills`를 그대로 사용합니다.
대상 Repository 안에 `.opencode`를 생성하거나 복사하지 않습니다.

```bash
cd /path/to/analyzed-repository
opencode --agent kubernetes-migration-analyzer --dir "$PWD"
```

대화형 실행 예:

```bash
cd /path/to/analyzed-repository
opencode --mini --agent kubernetes-migration-analyzer --dir "$PWD"
```

위 설정을 사용하면 OpenCode에서 다음 custom command로 호출할 수 있습니다.

```text
/analyze-repo-for-kubernetes
```

명시 subdirectory를 분석하려면 `.` 또는 현재 worktree 안의 Local path를
인자로 제공합니다. `--help`, `도움말`, `사용법`은 repository를 읽지 않는
사용 가이드만 반환합니다. Repository URL과 현재 worktree 밖 경로는 지원하지
않습니다.

분석 요청:

```text
현재 저장소를 Kubernetes 이관 관점에서 분석해줘.
```

기본 응답은 Summary입니다. 전체 분석이 필요할 때만 `Detailed` 또는 `상세`를 명시합니다.

```text
현재 저장소를 Kubernetes 이관 관점에서 Detailed로 상세 분석해줘.
```

Agent의 주요 제한:

- `read`, `glob`, `grep`, `list` 중심의 Repository 탐색만 허용
- `edit`, `write`, `patch`, `task`, web 도구 및 임의 Bash 실행 거부
- `git status`, `git rev-parse`, `git symbolic-ref`와 실제 `git -C` 조회 형태만 허용
- 분석 대상 Repository 밖의 경로 접근 거부
- 필요한 필드를 확인하거나 범위가 정해진 미확인 상태가 되면 Summary를 생성

## 보고서 검증

OpenCode의 응답을 분석 대상 Repository 밖의 파일로 저장한 뒤 Report Validator를 실행합니다.

Summary 검증:

```bash
python3 scripts/validate_report.py /tmp/kubernetes-migration-summary.md --mode summary --repo-root /path/to/analyzed-repository
```

상세 보고서 검증:

```bash
python3 scripts/validate_report.py /tmp/kubernetes-migration-assessment.md --mode detailed --repo-root /path/to/analyzed-repository
```

JSON 결과는 다음처럼 검증합니다.

```bash
python3 scripts/validate_report.py /tmp/analysis-result.json --format json --repo-root /path/to/analyzed-repository
```

보고서에는 파일·라인 근거, 근거 수준, 미확인 범위와 Kubernetes 설계 입력 상태를 포함해야 합니다. Kubernetes manifest나 Dockerfile은 이 Skill의 산출물이 아닙니다.

## Acceptance Harness

OpenCode 실행 파일이 설치된 환경에서는 Skill distribution, Agent 로드, 관련 요청의 Skill 호출, 비관련 요청의 Skill 미호출, 권한 거부, 보고서 반환 및 대상 Repository 불변성을 검증할 수 있습니다.

```bash
python3 scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --output-dir .artifacts/opencode
```

격리 acceptance/debug 실행은 분석 대상 Repository를 `--dir`와 subprocess `cwd`로
동시에 사용하지만, OpenCode의 `HOME`, `OPENCODE_CONFIG`,
`OPENCODE_CONFIG_DIR`, Agent, Skill, 로그는 임시 디렉터리로 분리합니다.
임시 config에는 `runtime/opencode.json`, 지정 Agent, 현재 Skill,
`analyze-repo-for-kubernetes` custom command만 들어갑니다.

```bash
python3 scripts/run_opencode_acceptance.py --mode isolated --cases tests/evaluation/opencode-cases.json --repository-root /path/to/analyzed-repository --output-dir /tmp/opencode-acceptance-output --repeat 3
```

실제 사용자 환경을 측정할 때는 `--mode user`를 사용합니다. 이 모드는 config나
Skill을 설치하지 않고 전역 discovery 경로를 읽어 trace에 기록합니다.

```bash
python3 scripts/run_opencode_acceptance.py --mode user --cases tests/evaluation/opencode-cases.json --repository-root /path/to/analyzed-repository --output-dir /tmp/opencode-user-output
```

두 모드는 모두 `--output-dir`가 분석 대상 Repository 밖에 있어야 하며,
`debug config`, `debug startup`, `debug skill`,
`debug agent kubernetes-migration-analyzer`를 실행하고
`--print-logs --log-level DEBUG` 결과를 보존합니다. 각 trace에는 `cwd`,
`HOME`, `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, Skill discovery path,
Agent path, command path, provider/model, 권한 audit, 대상 Repository의
`.opencode` 존재 여부와 Git/filesystem 전후 비교가 포함됩니다.

대표 interactive 실행도 별도로 남길 때는 `--interactive`를 추가합니다.
interactive 결과는 `interactive.json`과 별도 stdout/stderr log로 저장되며,
timeout 또는 provider 오류는 `UNAVAILABLE`/`FAIL`로 유지됩니다.

`--project-local` 설치는 계속 지원하지만 대상 Repository의 `.opencode`를
변경할 수 있으므로 acceptance/debug 실행에서는 사용하지 않습니다.

측정 결과는 실제 trace의 loaded file bytes/lines, tool call, event/step,
elapsed time만 집계합니다. Provider/model usage event가 없으면 해당 수치는
`null`로 남기며 추정하지 않습니다.

```bash
python3 scripts/measure_context.py --traces /tmp/opencode-acceptance-output --output /tmp/opencode-acceptance-output/context-measurement.json
```

실제 분석 대상 Repository에서 실행하려면 `--repository-root`를 추가합니다.

```bash
python3 scripts/run_opencode_acceptance.py --config runtime/opencode.json --cases tests/evaluation/opencode-cases.json --repository-root /path/to/analyzed-repository --timeout 180 --output-dir .artifacts/opencode
```

각 Case의 `trace.json`에는 실행 상태, 로드된 Skill, 도구 호출, 권한 거부, supporting reads, 최종 출력이 기록됩니다. 환경·Provider가 제한 시간 안에 응답하지 않으면 `UNAVAILABLE`로 기록하며 성공으로 간주하지 않습니다.

## 패키지 검사와 테스트

배포 패키지 구조 검사:

```bash
python3 scripts/validate_skill.py .
```

Distribution 생성:

```bash
python3 scripts/build_dist.py --output .artifacts/analyze-repo-for-kubernetes
```

전체 Quality Gate:

```bash
python3 scripts/run_quality_gate.py
```

Quality Gate는 package validation, 전체 unittest, 8개 executable scenario를 실행합니다. Scenario fixture 검증은 실제 OpenCode Provider E2E를 대신하지 않습니다.

Scenario evaluator를 직접 실행하려면 다음 명령을 사용합니다.

```bash
python3 scripts/evaluate_scenarios.py --cases tests/evaluation/cases.json --actual-dir tests/evaluation/golden-actual
```

## Private Repository

인증 정보 자체를 Agent 대화에 입력하지 않습니다. 먼저 인증된 local checkout 또는 Git credential helper를 준비한 뒤 Local path를 분석 대상으로 제공합니다.

## 저장소 관리 원칙

- 분석 대상 Repository는 read-only로 유지합니다.
- 생성 보고서와 Acceptance 산출물은 분석 대상 Repository 밖에 저장합니다.
- 배포 manifest, Helm chart, Dockerfile은 생성하지 않습니다.
- 실행한 검증만 성공으로 보고합니다.
- 생성된 distribution, Acceptance 산출물, 캐시 및 로컬 환경 파일은 커밋하지 않습니다.

## 현재 검증 상태

- Quality Gate: 88개 테스트와 8개 executable scenario 통과
- isolated profile의 `debug config/startup/skill/agent`와 read-only 대상 불변성 검증 통과
- 현재 Provider 실행은 제한 시간 내 최종 Summary와 Report Validator 통과를 확인하지 못했으며, `UNAVAILABLE`로 기록합니다.
- 현재 user profile은 전역 OpenCode log 경로 쓰기 권한과 전역 Agent 설치 여부가 blocker이며, 성공으로 보고하지 않습니다.
- OpenShell 검증은 이번 범위가 아니며 VS-010/VS-011에 남깁니다.

## License

MIT
