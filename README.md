# analyze-repo-for-kubernetes-skill

OpenCode에서 `analyze-repo-for-kubernetes` Skill을 로드하여 애플리케이션 Repository를 Kubernetes 이관 관점에서 근거 기반으로 분석합니다.

이 프로젝트가 지원하는 Agent Runtime은 OpenCode 순정 환경입니다. 분석 대상 Repository는 읽기 전용으로 취급하며, 분석 중 대상 파일을 수정하거나 배포 산출물을 생성하지 않습니다.

## 주요 기능

- Local path 또는 Repository URL 대상 확인과 Target Resolution Gate
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
~/.config/opencode/skills/analyze-repo-for-kubernetes
```

설치 스크립트는 allowlist 기반 distribution을 생성하고 패키지 구조를 검사한 뒤 파일을 복사합니다. 기존 중복 설치가 있으면 중단하며, 중복을 명시적으로 허용해야 하는 경우에만 다음 옵션을 사용합니다.

```bash
bash scripts/install-opencode.sh --allow-duplicates
```

특정 Project 내부에 설치할 수도 있습니다. 이 방식은 해당 Project에 `.opencode/skills`를 생성하므로, 분석 대상 Repository를 변경하지 않아야 하는 경우에는 전역 설치를 사용합니다.

```bash
bash scripts/install-opencode.sh --project-local /path/to/project
```

## OpenCode Agent 설정

분석 전용 Agent 정의를 OpenCode Agent 디렉터리에 복사합니다.

```bash
mkdir -p ~/.config/opencode/agents
cp runtime/agents/kubernetes-migration-analyzer.md ~/.config/opencode/agents/
```

`runtime/opencode.json`에는 로컬 OpenAI-compatible endpoint, 모델 선택, Skill allowlist, read-only 권한, 제한된 Git 조회 규칙이 정의되어 있습니다. 환경에 맞게 endpoint와 model을 확인한 뒤 OpenCode에 적용합니다.

대화형 실행 예:

```bash
OPENCODE_CONFIG="$PWD/runtime/opencode.json" opencode --pure --mini --agent kubernetes-migration-analyzer /path/to/analyzed-repository
```

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

- Quality Gate: 79개 테스트와 8개 executable scenario 통과
- OpenCode Skill 발견, Agent 권한, read-only Git 규칙 및 Acceptance Harness 검증 완료
- 설정된 Provider를 이용한 실제 E2E에서는 제한 시간 내 최종 Summary와 Report Validator 통과를 확인하지 못했으며, 해당 상태는 `UNAVAILABLE` 또는 `PARTIAL`로 기록합니다.

## License

MIT
