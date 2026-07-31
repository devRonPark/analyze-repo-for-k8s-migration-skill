# Kubernetes 설계 입력 요약

<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->

Target: fixture @ fixed | Skill: analyze-repo-for-kubernetes 1.0.0 | Contract: 2.0 | Validation: passed

## 1. 결론

- 판정: 설계 입력 충분
- 배포 대상: backend, frontend, prestart — 근거: compose.yml:2-7
- 주요 런타임 의존성: PostgreSQL — 근거: compose.yml:8-9
- 열린 항목 요약: Registry와 Tag — 근거: 검색(scope=., pattern=registry, result=없음)

## 2. 예상 Kubernetes 구성

- backend — Repository 사실: 배포 대상 후보; 역할: API; Kubernetes 해석: Deployment 후보; 포트: 8000; 상태: Stateless; 주요 의존성: PostgreSQL; 근거: compose.yml:2-3
- frontend — Repository 사실: 배포 대상 후보; 역할: Web; Kubernetes 해석: Deployment 후보; 포트: 80; 상태: Stateless; 주요 의존성: 없음; 근거: compose.yml:4-5
- prestart — Repository 사실: 배포 대상 후보; 역할: Migration; Kubernetes 해석: Job 후보; 포트: 없음; 상태: Stateless; 주요 의존성: PostgreSQL; 근거: compose.yml:6-7
- PostgreSQL — Repository 사실: 저장소에 정의된 런타임 의존성; 역할: DB; Kubernetes 해석: StatefulSet 또는 외부 관리; 포트: 5432; 상태: Persistent; 주요 의존성: 없음; 근거: compose.yml:8-9

## 3. 관계와 운영 경계

- PostgreSQL 운영 모델 — Kubernetes 해석: open design decision; 근거: compose.yml:8-9

## 4. 열린 항목

- 분류: 배포 입력; 항목: Registry와 Tag; 영향: 배포 시 입력; 근거: 검색(scope=., pattern=registry, result=없음)

## 5. 핵심 근거

- Compose runtime: compose.yml:2-9
