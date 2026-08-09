import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DiscoverySkillTests(unittest.TestCase):
    def test_discovery_is_a_grounded_vertical_slice_with_its_own_references(self) -> None:
        skill = (ROOT / "runtime/stage-skills/analyze-k8s-discovery/SKILL.md").read_text(encoding="utf-8")
        workflow = ROOT / "runtime/stage-skills/analyze-k8s-discovery/references/workflow.md"
        language_rules = ROOT / "runtime/stage-skills/analyze-k8s-discovery/references/language-discovery-rules.md"

        self.assertIn("Vertical Slice", skill)
        self.assertIn("Grounding", skill)
        self.assertIn("submit_discovery", skill)
        self.assertIn("Submit", skill)
        self.assertNotIn("reopen_analysis", skill)
        self.assertTrue(workflow.is_file())
        self.assertTrue(language_rules.is_file())
        self.assertNotIn("analyze-k8s-execution", skill)
        self.assertNotIn("submit_execution", skill)
