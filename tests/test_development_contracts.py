from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

ADR_AND_TICKETS = {
    "adr": ROOT / "docs/development/daily/2026-08-08/ADR-2026-08-08-004-analysis-pipeline-orchestration.md",
    "pipe_001": ROOT / "docs/development/tickets/PIPE-001-pipeline-state-and-validator.md",
    "pipe_002": ROOT / "docs/development/tickets/PIPE-002-session-tool-and-secure-snapshot.md",
    "pipe_003": ROOT / "docs/development/tickets/PIPE-003-stage-contract-injection-and-agent-migration.md",
    "pipe_004": ROOT / "docs/development/tickets/PIPE-004-runtime-finalizer-and-deterministic-renderer.md",
    "pipe_005": ROOT / "docs/development/tickets/PIPE-005-pipeline-acceptance-and-interactive-e2e.md",
    "pipe_006": ROOT / "docs/development/tickets/PIPE-006-terminal-skill-pruning.md",
}
RULE_OWNERSHIP = ROOT / "docs/development/specifications/static-stage-rule-ownership-2026-08-09.md"


class DevelopmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contents = {name: path.read_text(encoding="utf-8") for name, path in ADR_AND_TICKETS.items()}
        cls.combined = "\n".join(cls.contents.values())

    def test_pipeline_contract_uses_python_mcp_design(self):
        for term in [
            "Python MCP",
            "one active analysis",
            "Python",
            "MCP",
            "offline",
            "OpenCode, Claude Code, and Gemini CLI",
        ]:
            self.assertIn(term, self.combined)

    def test_tickets_define_python_runtime_boundaries(self):
        expected_terms = {
            "pipe_001": ["pure Python", "runtime/python/", "provider-free"],
            "pipe_002": ["fresh server process per interactive analysis session", "stdio MCP server", "offline-reproducible"],
            "pipe_003": ["Python MCP server", "parity", "client-specific minimal configuration templates"],
            "pipe_004": ["Python public-report projector", "receipt", "deterministic Markdown"],
            "pipe_005": ["OpenCode, Claude Code, and Gemini CLI", "ordered submissions", "canonical report hash"],
            "pipe_006": ["terminal no-op deletion sweep", ".ts", ".js", "Node", "Bun"],
        }
        for name, terms in expected_terms.items():
            for term in terms:
                self.assertIn(term, self.contents[name], f"{name} missing {term!r}")

    def test_legacy_typescript_and_session_requirements_are_removed(self):
        forbidden_terms = [
            "context.sessionID",
            "runtime/tools/analysis_pipeline.ts",
            "OpenCode caller/session identity",
            "TypeScript validator",
            "Pure TypeScript",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, self.combined)

    def test_static_stage_skill_amendment_and_rule_ownership_are_present(self):
        for content in self.contents.values():
            self.assertIn("Static MCP Stage Skills", content)

        ownership = RULE_OWNERSHIP.read_text(encoding="utf-8")
        for heading in [
            "Canonical owner",
            "Validator owner",
            "Skill stage",
            "Summary/Detailed condition",
            "Report fields",
            "Characterization or golden test",
            "workflow.md",
            "migration-summary-template.md",
            "migration-assessment-template.md",
        ]:
            self.assertIn(heading, ownership)


if __name__ == "__main__":
    unittest.main()
