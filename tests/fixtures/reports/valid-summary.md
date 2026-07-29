# Kubernetes 설계 입력 요약

<!-- analyze-repo-for-kubernetes: report-contract=1.0 -->

## 1. 분석 범위

- 대상 유형: Local path
- Repository URL 또는 Local path: /tmp/web
- 접근 방식: read-only local checkout
- 확인된 저장소 루트: /tmp/web
- branch, tag 또는 commit: main@abc123
- 분석 경로: .
- 출력 모드: summary

## 2. 배포 대상 후보와 주요 제외

- 배포 대상 후보: web (HTTP 서버) — 상태: 확인됨 / 근거: Dockerfile:1
- 주요 제외 항목: test fixtures — 상태: 확인됨 / 근거: pom.xml:1

## 3. 배포 대상별 요약

### 배포 대상: web

#### 핵심 입력

- 실행 형태: HTTP 서버 — 상태: 확인됨 / 근거: Dockerfile:1
- 런타임: Java 17 — 상태: 확인됨 / 근거: pom.xml:1
- 빌드 명령: ./mvnw package — 상태: 확인됨 / 근거: pom.xml:1
- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- 이미지 빌드 명령: docker build -t web . — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: Dockerfile 기반 후보
- 컨테이너화: 기존 컨테이너 정의 있음 — 상태: 확인됨 / 근거: Dockerfile:1
- 프로토콜: HTTP — 상태: 확인됨 / 근거: Dockerfile:1
- 수신 포트: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1
- Secret: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)
- 쓰기 상태 또는 영속성: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=volume|database, result=없음)
- 런타임 의존성: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=postgres|redis|rabbitmq, result=없음)

#### Kubernetes 최소 입력

- image: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=image name|registry, result=없음)
- command: java — 상태: 확인됨 / 근거: Dockerfile:1
- args: -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- containerPort: 8080 — 상태: 확인됨 / 근거: Dockerfile:1

#### 최소 입력 누락

- image: registry/image 이름이 없어 후속 이미지 설계를 차단함 — 상태: 미확인 / 근거: 검색(scope=., pattern=image name|registry, result=없음)

## 4. Kubernetes 설계 입력 상태

- 판정: 추가 정보 필요
- 이유: image 이름이 저장소에서 확인되지 않음
- 판정을 뒷받침하는 근거: 검색(scope=., pattern=image name|registry, result=없음)

### 설계 차단 항목

- 차단 항목: image — 범주: 이미지 / 영향 범위: 특정 배포 대상 / 상태: 미확인 / 근거: 검색(scope=., pattern=image name|registry, result=없음)
