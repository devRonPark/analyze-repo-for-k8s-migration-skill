# Ubiquitous Language

## Analysis Intent

A request to assess a repository for Kubernetes migration readiness. The
`/analyze-repo-for-kubernetes` command always expresses Analysis Intent;
natural-language requests require both a Kubernetes term and an analysis or
migration term.

## Analysis Target

The local Git repository scope selected for an Analysis Intent. It is either an
Explicit Target or the Current Repository according to the target-selection
rules.

## Explicit Target

A user-supplied local path, including `.`. It must resolve within the current
local Git repository; `.` preserves the current directory as the analysis
subdirectory.

## Current Repository

The Git root containing the interactive working directory. It is the Analysis
Target when the user refers implicitly to the current repository and no
Explicit Target is present.

## Target Resolution Failure

A missing, ambiguous, inaccessible, non-Git, or unsafe target. It leaves the
current session unchanged and returns one Korean sentence containing the reason
and a request for a Local path.
