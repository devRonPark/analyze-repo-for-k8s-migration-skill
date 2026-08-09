---
name: analyze-k8s-finalize
description: Finalize the accepted Kubernetes report without drafting a second report.
---

# Finalize

Use the incoming handoff only.

1. **Finalize:** call `finalize_analysis` once with the incoming envelope.
2. Relay its canonical Markdown unchanged. Do not read target evidence, draft,
   summarize, reformat, or load another Skill.
