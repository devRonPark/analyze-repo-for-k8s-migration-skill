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

## 2. 배포 대상 후보

- 배포 대상 후보: web (HTTP 서버) — 상태: 확인됨 / 근거: Dockerfile:1

## 3. 배포 대상별 실행 정보

### 배포 대상: web

#### 실행 정보

- 실행 형태: HTTP 서버 — 상태: 확인됨 / 근거: Dockerfile:1
- 경로: . — 상태: 확인됨 / 근거: pom.xml:1
- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1
- 프레임워크: Spring — 상태: 확인됨 / 근거: pom.xml:1
- 런타임: Java 17 — 상태: 확인됨 / 근거: pom.xml:1
- 패키지 관리자: Maven — 상태: 확인됨 / 근거: pom.xml:1
- 설치 명령: ./mvnw dependency:go-offline — 상태: 추정됨 / 근거: pom.xml:1 / 판단: Maven dependency resolution 후보
- 빌드 명령: ./mvnw package — 상태: 확인됨 / 근거: pom.xml:1
- 이미지 빌드 명령: docker build -t web . — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: Dockerfile 기반 후보
- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- 컨테이너화: 기존 컨테이너 정의 있음 — 상태: 확인됨 / 근거: Dockerfile:1
- 프로토콜: HTTP — 상태: 확인됨 / 근거: Dockerfile:1
- 수신 포트: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- 상태 확인: GET /health — 상태: 확인됨 / 근거: Dockerfile:1

#### 설정과 상태

- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1
- Secret: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)
- 쓰기 상태 또는 영속성: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=volume|database, result=없음)
- 적용 시점: 애플리케이션 시작 — 상태: 확인됨 / 근거: pom.xml:1
- 종료와 복구: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=graceful|shutdown|retry, result=없음)
- 관찰 가능성: 상태 확인 endpoint만 확인됨 — 상태: 확인됨 / 근거: Dockerfile:1

#### Kubernetes 최소 설계 입력

- workload.kind: Deployment — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: 지속 HTTP 서버
- metadata.name: web — 상태: 확인됨 / 근거: pom.xml:1
- image: registry.example/web:1.0 — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: 이미지 이름 입력 필요
- command: java — 상태: 확인됨 / 근거: Dockerfile:1
- args: -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- containerPort: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- Service: port 8080 — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: HTTP listener 노출 후보
- Ingress: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=Ingress, result=없음)

#### 최소 입력 누락

- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1

## 4. 구성과 관계

### 저장소에 정의된 런타임 의존성: 없음

- 기능 실행에 필요: 아니오 — 상태: 확인됨 / 근거: 검색(scope=., pattern=postgres|redis|rabbitmq, result=없음)
- 공급 또는 관리 경계: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=compose|kustomization, result=없음)

## 5. 운영 환경 배포 근거

- 확인된 배포 선언: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=helm|kustomization|deployment.yaml, result=없음)
- 저장소에서 확인한 기동 정의: Dockerfile CMD — 상태: 확인됨 / 근거: Dockerfile:1
- 운영 환경 배포 기준 구성: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=helm|kustomization|deployment.yaml, result=없음)

## 6. Kubernetes 설계 입력 상태

- 판정: 설계 입력 충분
- 이유: 저장소 기준 실행 정보가 확인됨
- 판정을 뒷받침하는 근거: pom.xml:1, Dockerfile:1

### 설계 차단 항목

- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: Dockerfile:1
