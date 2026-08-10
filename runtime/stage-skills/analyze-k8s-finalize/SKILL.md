---
name: analyze-k8s-finalize
description: Finalize the accepted Kubernetes report without drafting a second report.
---

# Finalize

Use the incoming handoff only.

1. **Finalize:** submit one complete `finalize_analysis` attempt with the
   incoming envelope. Retry only after an explicit server rejection, within
   the allowed retry budget.
2. Relay its canonical Markdown unchanged. Do not read target evidence, draft,
   summarize, reformat, or load another Skill.
3. If `finalize_analysis` fails, do not draft a fallback report.
