import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BoundariesSkillTests(unittest.TestCase):
    def test_boundaries_is_a_current_only_workload_boundary_quality_gate(self) -> None:
        skill = (ROOT / "runtime/stage-skills/analyze-k8s-boundaries/SKILL.md").read_text(encoding="utf-8")
        rules = ROOT / "runtime/stage-skills/analyze-k8s-boundaries/references/workload-boundary.md"

        for term in ("Workload Boundary", "Quality Gate", "Submit", "submit_boundaries", "process_ids", "relationship_fact_refs"):
            self.assertIn(term, skill)
        self.assertTrue(rules.is_file())
        rule_text = " ".join(rules.read_text(encoding="utf-8").split())
        self.assertIn("directory, package, port", rule_text)
        self.assertIn("alone never establish a boundary", rule_text)
        self.assertIn("candidate inclusion or exclusion", rule_text)
        self.assertIn("confirmed boundary may have an unknown state decision", rule_text)
        self.assertIn("Summary records only", rule_text)
        self.assertIn("Detailed additionally records", rule_text)
        self.assertNotIn("analyze-k8s-contracts", skill)
        self.assertNotIn("submit_contracts", skill)


if __name__ == "__main__":
    unittest.main()
