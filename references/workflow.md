# Repository Analysis Workflow

`SKILL.md` owns target resolution, safety, output mode, evidence semantics, and
the final verdict. This file owns the high-signal inventory and analysis order.
After that gate, `현재 저장소` means the current Git root and `.` means the
current subdirectory. A missing target follows it and must Stop the turn after asking. For a private repository, use its authenticated Local path. Analyze only paths within the current worktree. Do not clone Repository URLs. Do not follow a symlink outside the resolved scope.

## 1. High-signal inventory

First inspect manifests and container/runtime configuration that are present and
relevant: package or build manifests, wrappers, Dockerfiles, Compose files,
deployment declarations, environment/configuration files, web descriptors,
application context, entrypoints, and database or broker configuration. For a
Maven candidate, prioritize `pom.xml`, `mvnw`/wrapper and build/package settings,
`Dockerfile`, Compose, `web.xml`, and `applicationContext.xml`.

Apply the conditional lockfile policy in `SKILL.md`; for Maven, do not search
for lockfiles when `pom.xml` and wrapper/build/package settings are sufficient.

If a Dockerfile or documented launch command selects a Maven/Gradle profile,
read the profile definitions and compare the selected identifier with the
invocation. Also compare an explicit container base-image version with the
compiled target version. These are execution facts: disagreements are
`상충됨`, not a reason to choose the more plausible runtime. For a Java web
application, inspect its web descriptor for the Java EE/Jakarta API level.

When an application context or equivalent startup configuration loads a schema
or data SQL file, inspect that referenced file only far enough to classify
credential-shaped seed records. Do not output values. Treat an embedded
database as an in-process dependency and state concern, but do not infer a
PersistentVolume, StatefulSet, or external database requirement without direct
evidence. Record the intended data lifecycle as a decision instead.

Use README, CI, logs, migrations, tests, and broad source-tree reads only when a
first-pass finding needs evidence. Exclude generated output, caches, vendored
code, binaries, test-only dependencies, and the full README unless directly
relevant.

## 2. Analyze in one pass

Classify findings into exactly one of `배포 대상 후보`, `저장소에 정의된
런타임 의존성`, `외부 런타임 의존성`, or `배포 대상 후보에서 제외한 항목`.
Evaluate migration/initialization commands as one-time job candidates before
excluding them. For each candidate, keep install, build, image, and production
startup evidence separate.

For Summary, collect only the fields named in `SKILL.md`, then synthesize
immediately. Route to language, configuration-timing, and dependency references
only after the corresponding finding exists. For Detailed, complete the full
component card and both relationship representations; their rules live in the
Detailed-only checklist and conditional references.

Keep repository launch definitions distinct from operating-environment evidence.
Do not infer production configuration from local Compose, source defaults, or a
startup script. Do not execute repository scripts, builds, tests, migrations,
servers, or containers.

## 3. Completion gate

Before returning a report, check candidate boundaries, launch/operating-evidence
separation, valid evidence references, redaction, keyed minimum-input gaps, and
the single readiness verdict from `SKILL.md`. Never generate Kubernetes
manifests, Dockerfiles, Helm charts, application code, or deployment plans.
