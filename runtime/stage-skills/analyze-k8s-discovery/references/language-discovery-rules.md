# Language Discovery Rules

Load this reference only after a language signal is confirmed.

## Node.js and TypeScript

Inspect the nearest component `package.json`, workspace declaration, framework
configuration, and source entrypoint to establish component scope. Prefer the
component `packageManager`, then its owning workspace declaration, then the
nearest manifest. Use a matching lockfile only when the component boundary is
ambiguous. Keep equally-applicable package-manager signals visible.

## Python

Inspect `pyproject.toml`, requirements files, framework entrypoints, WSGI or
ASGI configuration, settings modules, and migration tools to establish scope.

## Go

Inspect `go.mod`, `cmd/`, and main packages to establish scope.

## Java and Kotlin

Inspect adjacent Maven or Gradle wrappers and build files, module settings,
application configuration, and main classes. Determine module scope before
selecting a toolchain. When Maven and Gradle coexist, preserve both scopes
unless evidence excludes one.

## Other languages

For .NET inspect solutions/projects and `Program.cs`. For Rust inspect
`Cargo.toml`, workspace members, and binaries. For any other language, identify
the nearest manifest and entrypoint before deciding candidacy.

## Evidence limits

A dependency declaration alone does not prove that an item is deployable.
Framework defaults may support an inferred candidate signal but never a
confirmed runtime fact without repository evidence.
