# Static Stage Rule Ownership

- Status: Approved implementation baseline
- Date: 2026-08-09
- Authority: Static MCP and Progressive Stage Skills Design
- Change rule: changing a canonical owner requires an amendment to the approved
  implementation plan before implementation.

The matrix makes one runtime owner accountable for each current analysis rule.
The stage Skill may load only the assets assigned to its current slice. Server
validators enforce evidence and report-field completion; they do not duplicate
reference prose.

| Existing asset | Canonical owner | Validator owner | Skill stage | Summary/Detailed condition | Report fields | Characterization or golden test |
| --- | --- | --- | --- | --- | --- | --- |
| references/workflow.md | runtime/stage-skills/analyze-k8s-discovery/references/workflow.md | discovery payload contract | discovery | Both modes | target, revision, evidence grounding | discovery stage test; all six mode goldens |
| references/language-discovery-rules.md | runtime/stage-skills/analyze-k8s-discovery/references/language-discovery-rules.md | discovery payload contract | discovery | Summary high-signal; Detailed full discovery | candidates, exclusions | discovery stage test; JPetStore golden |
| references/dependency-analysis.md | runtime/stage-skills/analyze-k8s-relationships/references/dependency-analysis.md | relationships payload contract | relationships | Detailed; Summary material dependencies only | dependency edges, external dependencies | relationships stage test; Flask/Celery golden |
| references/workload-boundary.md | runtime/stage-skills/analyze-k8s-boundaries/references/workload-boundary.md | boundaries payload contract | boundaries | Both modes | deployable units, exclusions, writable state | boundaries stage test; FastAPI golden |
| references/configuration-timing.md | runtime/stage-skills/analyze-k8s-contracts/references/configuration-timing.md | contracts payload contract | contracts | Detailed; Summary material configuration only | configuration timing, Secret names | contracts stage test; all detailed goldens |
| references/evidence-and-readiness.md | runtime/stage-skills/analyze-k8s-contracts/references/evidence-and-readiness.md | contracts payload contract | contracts | Both modes | evidence statuses, blockers, verdict | contracts stage test; all six mode goldens |
| references/repository-analysis-checklist.md | runtime/stage-skills/analyze-k8s-contracts/references/repository-analysis-checklist.md | contracts payload contract | contracts | Detailed only | detailed completion slots | contracts stage test; detailed goldens |
| assets/migration-summary-template.md | installed runtime assets/migration-summary-template.md | report projection and Markdown validator | finalize | Summary only | Kubernetes 설계 입력 요약 | finalization stage test; summary goldens |
| assets/migration-assessment-template.md | installed runtime assets/migration-assessment-template.md | report projection and Markdown validator | finalize | Detailed only | Kubernetes 설계 입력 상세 평가 | finalization stage test; detailed goldens |
| contracts/markdown-report-contract.json | installed runtime contracts/markdown-report-contract.json | report projection and Markdown validator | finalize | Both modes | report structure and redaction | finalization stage test; all six mode goldens |
| schemas/analysis-result.schema.json | installed runtime schemas/analysis-result.schema.json | report projection JSON validation | finalize | Both modes | mode-specific JSON projection | finalization stage test; all six mode goldens |

The original root reference and asset files remain during migration only. Their
owner stage moves them and removes the old runtime copy after its
characterization test passes. No new duplicate rule text is permitted.
