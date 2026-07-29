# Language and Command Discovery Rules

Use these rules only for languages found in the target. They define file signals,
precedence, and exceptions; common classification and report fields belong to
`workflow.md` and `repository-analysis-checklist.md`.

## Shared command stages

Record four distinct stages for each candidate:

1. dependency installation;
2. application build;
3. image build;
4. production startup.

Do not use one stage as evidence for another. `npm install` is not an
application build, `npm run build` is not production startup, `docker build` is
not an application build, and a development server is not production startup.

## Node.js and TypeScript

Inspect the nearest component `package.json`, workspace declaration, matching
lockfile, framework configuration, source entrypoint, environment access, and
scripts. Distinguish development servers from production startup and static
builds.

Determine the package manager for each component in this precedence order:

1. the component `packageManager` field;
2. the owning workspace package-manager declaration;
3. the nearest component manifest and its scripts;
4. the lockfile matching that component.

Root-level evidence does not override stronger component-level evidence. A
workspace declaration applies only to components it owns. Mixed managers are
reported per component. If equally applicable signals conflict, preserve the
conflict as `상충됨`; if only weak or incomplete signals exist, use `미확인`.
Do not force one manager from a filename alone.

Record install, build, image build, and production startup separately. A `dev`
script is not production startup evidence.

## Python

Inspect `pyproject.toml`, requirements files, lockfiles, framework entrypoints,
WSGI or ASGI configuration, settings modules, migration tools, and startup
scripts. Distinguish development servers from production process commands.

## Go

Inspect `go.mod`, `cmd/`, `main` packages, flags, environment access, embedded
assets, server binding code, and build workflows.

## Java and Kotlin

Inspect the wrapper and build files adjacent to the component, Maven or Gradle
module settings, application configuration, main classes, framework profiles,
ports, and executable packaging.

Prefer a Maven or Gradle wrapper adjacent to the component over a repository-root
wrapper. Determine the applicable module scope before selecting a toolchain. When
Maven and Gradle coexist, keep both scopes and evidence visible; do not select a
single toolchain merely because both files exist. If the applicable scopes or
runtime commands conflict, preserve `상충됨` or `미확인`.

Keep dependency resolution, application packaging, image creation, and runtime
startup distinct. Never infer production startup from a build command alone.

## .NET, Rust, and other languages

For .NET inspect solution and project files, `Program.cs`, hosting configuration,
and treat launch settings as development evidence only. For Rust inspect
`Cargo.toml`, workspace members, binaries, features, configuration loading, and
server binding code. For any other language, identify the nearest manifest,
entrypoint, runtime configuration, and executable command before making a
candidate decision.

## Evidence exceptions

A dependency declaration does not prove runtime use. A development command does
not prove the production startup command. Framework defaults may support an
`추정됨` finding but never a `확인됨` finding without repository evidence.
