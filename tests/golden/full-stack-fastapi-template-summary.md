# Kubernetes 설계 입력 요약

<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->

Target: fixture @ fixed | Skill: analyze-repo-for-kubernetes 1.0.0 | Contract: 2.0 | Validation: passed

## 1. 결론

- 판정: 설계 입력 충분
- 배포 대상: backend, frontend, prestart — 근거: compose.yml:2-7
- 주요 런타임 의존성: PostgreSQL — 근거: compose.yml:8-9
- 열린 항목 요약: Registry와 Tag — 근거: 검색(scope=., pattern=registry, result=없음)

## 2. 예상 Kubernetes 구성

| 대상 | Repository 사실 | 역할 | Kubernetes 해석 | 포트 | 상태 | 주요 의존성 | 근거 |
|---|---|---|---|---|---|---|---|
| backend | 배포 대상 후보 | API | Deployment 후보 | 8000 | Stateless | PostgreSQL | compose.yml:2-3 |
| frontend | 배포 대상 후보 | Web | Deployment 후보 | 80 | Stateless | 없음 | compose.yml:4-5 |
| prestart | 배포 대상 후보 | Migration | Job 후보 | 없음 | Stateless | PostgreSQL | compose.yml:6-7 |
| PostgreSQL | 저장소에 정의된 런타임 의존성 | DB | StatefulSet 또는 외부 관리 | 5432 | Persistent | 없음 | compose.yml:8-9 |

## 3. 관계와 운영 경계

| 관계 또는 경계 | Kubernetes 해석 | 근거 |
|---|---|---|
| PostgreSQL 운영 모델 | open design decision | compose.yml:8-9 |

## 4. 열린 항목

| 분류 | 항목 | 영향 | 근거 |
|---|---|---|---|
| 배포 입력 | Registry와 Tag | 배포 시 입력 | 검색(scope=., pattern=registry, result=없음) |

## 5. 핵심 근거

- Compose runtime: compose.yml:2-9
