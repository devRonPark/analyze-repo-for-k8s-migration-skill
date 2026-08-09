# Language Discovery Rules

Load this reference only after a language signal is confirmed.

## Shared command boundary

Keep dependency installation, application build, image build, and production
startup as four distinct facts. A dependency install is not an application
build; an application build is not image creation; a development server is not
production startup.

## Node.js and TypeScript

Inspect the nearest component `package.json`, workspace declaration, framework
configuration, source entrypoint, environment access, and scripts. Prefer the
component `packageManager`, then its owning workspace declaration, then the
nearest manifest; use a matching lockfile only when that boundary remains
ambiguous. Report conflicting equally-applicable signals without resolving them.

## Python

Inspect `pyproject.toml`, requirements files, framework entrypoints, WSGI or
ASGI configuration, settings modules, migration tools, and startup scripts.
Do not treat a development server as production process evidence.

## Go

Inspect `go.mod`, `cmd/`, main packages, flags, environment access, embedded
assets, server binding code, and build workflows.

## Java and Kotlin

Inspect adjacent Maven or Gradle wrappers and build files, module settings,
application configuration, main classes, profiles, ports, and executable
packaging. Determine module scope before selecting a toolchain. When Maven and
Gradle coexist, preserve both scopes unless evidence excludes one.

## Other languages

For .NET inspect solutions/projects, `Program.cs`, and hosting configuration;
launch settings are development evidence. For Rust inspect `Cargo.toml`,
workspace members, binaries, features, configuration loading, and server
binding. For any other language, identify the nearest manifest, entrypoint,
runtime configuration, and executable command before deciding candidacy.

## Evidence limits

A dependency declaration does not prove runtime use. Framework defaults may
support an inferred finding but never a confirmed finding without repository
evidence.
