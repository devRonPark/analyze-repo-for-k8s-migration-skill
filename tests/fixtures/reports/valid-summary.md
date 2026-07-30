# Kubernetes 설계 입력 요약

<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->

Target: /tmp/web @ abc123def | Skill: analyze-repo-for-kubernetes 1.0.0 | Contract: 2.0 | Validation: pending

## 1. 결론

- 판정: 설계 입력 충분
- 배포 대상: web — 근거: Dockerfile:1
- 주요 런타임 의존성: 없음 — 근거: 검색(scope=., pattern=postgres|redis, result=없음)
- 열린 항목 요약: image registry — 근거: 검색(scope=., pattern=registry, result=없음)

## 2. 예상 Kubernetes 구성

- web — Repository 사실: 배포 대상 후보; 역할: API; Kubernetes 해석: Deployment 후보; 포트: 8080; 상태: Stateless; 주요 의존성: 없음; 근거: Dockerfile:1

## 3. 관계와 운영 경계

- web ingress — Kubernetes 해석: Ingress 설계 결정; 근거: Dockerfile:1

## 4. 열린 항목

- 분류: 배포 입력; 항목: image registry; 영향: 배포 시 입력; 근거: 검색(scope=., pattern=registry, result=없음)

## 5. 핵심 근거

- web runtime: Dockerfile:1
