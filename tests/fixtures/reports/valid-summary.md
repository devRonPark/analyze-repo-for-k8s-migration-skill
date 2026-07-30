# Kubernetes 설계 입력 요약

<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->

Target: /tmp/web @ abc123def | Skill: analyze-repo-for-kubernetes 1.0.0 | Contract: 2.0 | Validation: pending

## 1. 결론

- 판정: 설계 입력 충분
- 배포 대상: web — 근거: Dockerfile:1
- 주요 런타임 의존성: 없음 — 근거: 검색(scope=., pattern=postgres|redis, result=없음)
- 열린 항목 요약: image registry — 근거: 검색(scope=., pattern=registry, result=없음)

## 2. 예상 Kubernetes 구성

| 대상 | Repository 사실 | 역할 | Kubernetes 해석 | 포트 | 상태 | 주요 의존성 | 근거 |
|---|---|---|---|---|---|---|---|
| web | 배포 대상 후보 | API | Deployment 후보 | 8080 | Stateless | 없음 | Dockerfile:1 |

## 3. 관계와 운영 경계

| 관계 또는 경계 | Kubernetes 해석 | 근거 |
|---|---|---|
| web ingress | Ingress 설계 결정 | Dockerfile:1 |

## 4. 열린 항목

| 분류 | 항목 | 영향 | 근거 |
|---|---|---|---|
| deployment_value | image registry | 배포 시 입력 | 검색(scope=., pattern=registry, result=없음) |

## 5. 핵심 근거

- web runtime: Dockerfile:1
