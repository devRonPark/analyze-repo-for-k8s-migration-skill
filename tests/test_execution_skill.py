import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExecutionSkillTests(unittest.TestCase):
    def test_execution_is_a_current_only_grounded_quality_gate(self) -> None:
        skill = (ROOT / "references/stages/execution.md").read_text(encoding="utf-8")
        rules = ROOT / "references/execution-rules.md"

        self.assertIn("Grounding", skill)
        self.assertIn("Quality Gate", skill)
        self.assertIn("Vertical Slice", skill)
        self.assertIn("Submit", skill)
        self.assertIn("submit_execution", skill)
        for field in ("candidate_ids", "discovery_fact_refs", "unknown"):
            self.assertIn(field, skill)
        self.assertTrue(rules.is_file())
        self.assertNotIn("submit_relationships", skill)
        self.assertNotIn("reopen_analysis", skill)

    def test_execution_rules_are_not_preloaded_by_discovery(self) -> None:
        discovery = (ROOT / "references/workflow.md").read_text(encoding="utf-8")
        language = (ROOT / "references/language-discovery-rules.md").read_text(encoding="utf-8")
        execution = (ROOT / "references/execution-rules.md").read_text(encoding="utf-8")

        self.assertIn("production startup", execution)
        self.assertNotIn("production startup", discovery)
        self.assertNotIn("production startup", discovery)
