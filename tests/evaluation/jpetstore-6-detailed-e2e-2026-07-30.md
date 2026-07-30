<!-- Retained E2E diagnostic evidence, not a fixture.
     Run: 2026-07-30, /tmp/opencode-acceptance-det9, detached tmux,
     provider local-sglang/Qwen/Qwen3.6-35B-A3B-FP8,
     request /analyze-repo-for-kubernetes Detailed,
     target /home/daolts/jpetstore-6 @ e1dd9a31d1cef68793cd0933ae06898e6fcfa807,
     duration 2m 5s, target Git status unchanged before and after,
     validate_report.py --mode detailed --repo-root <target>: 7 failures,
     golden-set score 72/100 (see jpetstore-6-detailed-scorecard.md). -->

# Kubernetes 설계 입력 상세 평가

<!-- analyze-repo-for-kubernetes: report-contract=1.0 -->

## 1. 분석 범위

- 대상 유형: Java EE WAR + Spring + MyBatis 웹 애플리케이션
- Repository URL 또는 Local path: GitHub (mybatis/jpetstore-6) / Local `.`
- 접근 방식: Dockerfile, Compose, Maven pom.xml, web.xml, applicationContext.xml, README 기반 정적 분석
- 확인된 저장소 루트: /home/daolts/jpetstore-6
- branch, tag 또는 commit: master, e1dd9a31d1cef68793cd0933ae06898e6fcfa807
- 분석 경로: .
- 출력 모드: detailed

### 핵심 요약

- 판정: 추가 정보 필요
- 배포 대상: jpetstore (WAR, Java 17, Spring/MyBatis/Stripes)
- 최우선 차단 요소: Dockerfile CMD의 `-P tomcat90` 프로파일 ID가 pom.xml에 미존재 — 선택 서버 상충
- 최소 입력 누락: Kubernetes workload.kind, metadata.name, image, Service, Ingress 등 기초 입력 전항 미확인

## 2. 배포 대상 후보

- jpetstore — WAR 패키징, Cargo插件으로 다중 Application Server에 배포 — 상태: 확인됨 / 근거: pom.xml:33, pom.xml:247, pom.xml:334-565

## 3. 배포 대상별 실행 정보

### 배포 대상: jpetstore

#### 실행 정보

- 실행 형태: Java WAR — 상태: 확인됨 / 근거: pom.xml:33
- 경로: src/main/webapp/ — 상태: 확인됨 / 근거: glob(src/main/webapp/**/*.xml)
- 언어: Java 17 — 상태: 확인됨 / 근거: pom.xml:62
- 프레임워크: Spring 5 (spring-web 5.3.39), MyBatis 3.5.19, Stripes 1.6.0 — 상태: 확인됨 / 근거: pom.xml:98-147
- 런타임: Jakarta Servlet 4.0 API (javax.servlet), JSP 3.0 (web.xml:24-27) — 상태: 확인됨 / 근거: src/main/webapp/WEB-INF/web.xml:24-27, pom.xml:156-158
- 패키지 관리자: Maven (mvnw) — 상태: 확인됨 / 근거: pom.xml:1, mvnw
- 설치 명령: `./mvnw clean package` — 상태: 확인됨 / 근거: README.md:33
- 빌드 명령: `./mvnw clean package` — 상태: 확인됨 / 근거: pom.xml:247, README.md:33
- 이미지 빌드 명령: `docker build .` — 상태: 확인됨 / 근거: Dockerfile:17-21
- 운영 기동 명령: `./mvnw cargo:run -P tomcat90` — 상태: 확인됨 / 근거: Dockerfile:21, README.md:39 — 상충됨: pom.xml에 tomcat90 프로파일 미존재, 존재하는 것은 tomcat9 (기본)
- 컨테이너화: Dockerfile 있음, Compose 있음 — 상태: 확인됨 / 근거: Dockerfile:1, docker-compose.yaml:1
- 프로토콜: HTTP — 상태: 확인됨 / 근거: docker-compose.yaml:25
- 수신 포트: 8080 — 상태: 확인됨 / 근거: Dockerfile:21(cargo 기본), docker-compose.yaml:25
- 상태 확인: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*health*,**/*ready*,**/*liveness*}, result=없음)

#### 설정과 상태

- 설정: applicationContext.xml (Spring JDBC, MyBatis SQLFactory, transactionManager, component-scan), web.xml (StripesFilter, DispatcherServlet) — 상태: 확인됨 / 근거: src/main/webapp/WEB-INF/applicationContext.xml:1-55, src/main/webapp/WEB-INF/web.xml:1-64
- Secret: 내장 HSQLDB 시드 데이터에 credential-shaped demo seed data 포함 (signon.username/password, account.userid/password 등) — 상태: 확인됨 / 근거: src/main/resources/database/jpetstore-hsqldb-dataload.sql:17-30
- 쓰기 상태 또는 영속성: HSQLDB 내장 임베디드 DB (Spring `jdbc:embedded-database`) — 상태: 확인됨 / 근거: src/main/webapp/WEB-INF/applicationContext.xml:31-34 — 생명주기 결정: 미확인 (PersistentVolume/StatefulSet 요구 여부 미결정)
- 적용 시점: applicationContext.xml — 기동 시 (Spring ContextLoaderListener, web.xml:35) — 상태: 확인됨 / 근거: src/main/webapp/WEB-INF/web.xml:34-36, src/main/webapp/WEB-INF/applicationContext.xml:31-34
- 종료와 복구: 미확인 — 상태: 미확인 / 근거: 검색(scope=src/main/webapp/WEB-INF, pattern={**/*shutdown*,**/*preDestroy*}, result=없음)
- 관찰 가능성: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*actuator*,**/*prometheus*,**/log4j*,**/logging*}, result=없음)

#### Kubernetes 최소 설계 입력

- workload.kind: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*deployment*,**/kustomization*,**/helm*}, result=없음)
- metadata.name: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*deployment*,**/kustomization*}, result=없음)
- image: openjdk:25 (Dockerfile:17) — 상태: 확인됨 / 근거: Dockerfile:17
- command: 미확인 (CMD `./mvnw cargo:run -P tomcat90`은 Dockerfile 내 빌드+기동 통합 명령, K8s 분리 필요) — 상태: 확인됨 / 근거: Dockerfile:21
- args: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/k8s*,**/*kustomization*}, result=없음)
- containerPort: 8080 — 상태: 확인됨 / 근거: docker-compose.yaml:25
- Service: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*service*,**/kustomization*}, result=없음)
- Ingress: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*ingress*,**/kustomization*}, result=없음)

#### 최소 입력 누락

- workload.kind: K8s 워크로드 정의 없음; Deployment vs StatefulSet 등 결정 필요 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/*deployment*,**/kustomization*}, result=없음)
- metadata.name: K8s 리소스명 미정 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/kustomization*,**/*k8s*}, result=없음)
- image tag: openjdk:25 — 상태: 확인됨 / 근거: Dockerfile:17 (tag은 존재하지만 Java 17 compile과 openjdk:25 최신 버전 간 호환성은 미확인)
- Service port mapping: 8080 확인됨 — 상태: 확인됨 / 근거: docker-compose.yaml:25
- persistence: 임베디드 HSQLDB — 데이터 생명주기 ( ephemeral vs PersistentVolume ) 결정 필요 — 상태: 미확인 / 근거: src/main/webapp/WEB-INF/applicationContext.xml:31-34

## 4. 구성과 관계

### Dependency matrix

- 연결 workload: jpetstore (WAR); 의존 대상: HSQLDB (임베디드); 종류: 데이터베이스; protocol 또는 mechanism: JDBC (Spring jdbc:embedded-database); endpoint 또는 configuration: applicationContext.xml:31-34; 적용 시점: 기동 시; 실행 위치: jpetstore 프로세스内; 기능 실행에 필요: yes; 확인된 실행 정의에서 사용 여부: yes; 공급 또는 관리 경계: 저장소 내; 상태 또는 영속성: 임베디드/ephemeral(미확인); 근거: src/main/webapp/WEB-INF/applicationContext.xml:31-34, pom.xml:171-173

- 연결 workload: jpetstore (WAR); 의존 대상: Tomcat 9 / TomEE 8 / WildFly 26 / Liberty EE8 / Jetty 12 / GlassFish 5 / Payara 5 / Resin 4 (Cargo_profiles); 종류: Application Server; protocol 또는 mechanism: cargo-maven3-plugin installed container; endpoint 또는 configuration: pom.xml:334-565; 적용 시점: 빌드/기동 시; 실행 위치: 별도_process_; 기능 실행에 필요: yes(K8s 배포 시 적용 서버 선택 전필요); 확인된 실행 정의에서 사용 여부: Dockerfile의 CMD에서 tomcat90(미존재)으로 상충; 공급 또는 관리 경계: 저장소 내 정의; 상태 또는 영속성: 없음; 근거: pom.xml:334-565, Dockerfile:21

### Text dependency graph

```
jpetstore WAR --[runtime, 기동 시, jpetstore 프로세스内]--> HSQLDB (임베디드)
jpetstore WAR --[build/runtime, 기동 시, 별도_process_]--> Application Server (Cargo profiles — 선택 상충)
```

### 배포 대상 후보에서 제외한 항목

- CI (GitHub Actions): 일회성 검증 파이프라인 — 상태: 확인됨 / 근거: pom.xml:48-51
- 테스트 의존성 (JUnit, Mockito, Selenium, Selenide): 테스트 전용 — 상태: 확인됨 / 근거: pom.xml:184-243
- site-migration / sitedeploy: GitHub Pages 사이트 배포 — 상태: 확인됨 / 근거: pom.xml:52-58

## 5. 운영 환경 배포 근거

- 확인된 배포 선언: 미확인 (Helm, Kustomize, manifest, GitOps 없음) — 상태: 미확인 / 근거: 검색(scope=., pattern={**/k8s*,**/helm*,**/kustomization*,**/.github/workflows/*deploy*}, result=없음)
- 저장소에서 확인한 기동 정의: Dockerfile CMD `./mvnw cargo:run -P tomcat90` (상충: profile 미존재), docker-compose.yaml 서비스 jpetstore (port 8080:8080, restart: always) — 상태: 확인됨 / 근거: Dockerfile:21, docker-compose.yaml:20-27
- 운영 환경 배포 기준 구성: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern={**/prod*,**/*production*}, result=없음)

## 6. 설정과 상태 상세

- applicationContext.xml: Spring Bean 구성, 내장 HSQLDB(기동 시 schema+dataload 로드), DataSourceTransactionManager, MyBatis SqlSessionFactory, component-scan — 적용 시점: 기동 시 (ContextLoaderListener) — Secret 여부: 아님 — 근거: src/main/webapp/WEB-INF/applicationContext.xml:1-55
- web.xml: StripesFilter + DispatcherServlet, JSP/JSTL context, Servlet 3.0(namespace) — 적용 시점: 기동 시 — Secret 여부: 아님 — 근거: src/main/webapp/WEB-INF/web.xml:1-64
- jpetstore-hsqldb-dataload.sql: credential-shaped demo seed data (signon, account 테이블). 외부 Secret으로 이동 필요 — Secret 여부: 예 (시드 데이터에 username/password 포함) — 근거: src/main/resources/database/jpetstore-hsqldb-dataload.sql:17-30
- Dockerfile: 빌드+기동 통합 CMD — 운영 환경에서 K8s command/args로 분리 필요 — 근거: Dockerfile:17-21
- docker-compose.yaml: 단일 서비스, 포트 8080, restart: always — 운영 환경 Production config 아님 — 근거: docker-compose.yaml:17-27

## 7. 제외 항목과 설계 차단 항목 상세

### 설계 차단 항목

- 차단 항목: Dockerfile CMD의 `-P tomcat90`이 pom.xmlprofiles에 없음 — cargo-maven3-plugin이 프로파일을 해석하지 못해 기동 실패 — 범주: runtime / 영향 범위: 전체 / 상태: 상충됨 / 근거: Dockerfile:21, pom.xml:337-346
- 차단 항목: 내장 HSQLDB 시드 SQL(jpetstore-hsqldb-dataload.sql)에 credential-shaped demo seed data 포함 — 기동 시 인메모리에 로드되나, PersistentVolume 없이 Pod 재기동 시 데이터 손실 — 범주: Secret / 영향 범위: 전체 / 상태: 확인됨 / 근거: src/main/resources/database/jpetstore-hsqldb-dataload.sql:17-30
- 차단 항목: Kubernetes 최소 설계 입력(workload.kind, metadata.name, Service, Ingress, command, args)이 저장소에 없음 — 후속 K8s 설계 단계에서 필수 — 범주: 기타 / 영향 범위: 전체 / 상태: 미확인 / 근거: 검색(scope=., pattern={**/k8s*,**/kustomization*,**/helm*,**/deployment*}, result=없음)

## 8. Kubernetes 설계 입력 상태

- 판정: 추가 정보 필요
- 이유: Dockerfile CMD의 `-P tomcat90` 프로파일 ID가 pom.xml에 정의된 profile 중 어느 것도 매칭되지 않아 Application Server 실행 환경이 상충됨. Additionally, Kubernetes workload.kind, metadata.name, Service, Ingress, command/args 분리 등 기초 설계 입력이 전항 미확인. Embedded HSQLDB 시드 SQL의 credential exposure도 별도 처리 필요.
- 판정을 뒷받침하는 근거:
  - Dockerfile:21 (`-P tomcat90`) vs pom.xml:337-346 (실제 profile id `tomcat9`) — 상충
  - 검색 결과: Kubernetes manifest, Helm, Kustomize, GitOps, CI deploy workflow 없음 — scope=., pattern={**/k8s*,**/kustomization*,**/helm*,**/deployment*,**/.github/workflows/*deploy*}, result=없음
  - applicationContext.xml:31-34 — 임베디드 DB + 시드 SQL (credential-shaped demo seed data in jpetstore-hsqldb-dataload.sql:17-30)
