import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BoundariesSkillTests(unittest.TestCase):
    def test_boundaries_is_a_current_only_workload_boundary_quality_gate(self) -> None:
        skill = (ROOT / "references/stages/boundaries.md").read_text(encoding="utf-8")
        rules = ROOT / "references/stages/boundaries/workload-boundary.md"

        for term in ("Workload Boundary", "Quality Gate", "Submit", "submit_boundaries", "processes", "fact references"):
            self.assertIn(term, skill)
        self.assertTrue(rules.is_file())
        rule_text = " ".join(rules.read_text(encoding="utf-8").split())
        self.assertIn("directory, package, port", rule_text)
        self.assertIn("alone never establish a boundary", rule_text)
        self.assertIn("candidate inclusion or exclusion", rule_text)
        self.assertIn("confirmed boundary may have an unknown state decision", rule_text)
        self.assertIn("Summary records only", rule_text)
        self.assertIn("Detailed additionally records", rule_text)
        self.assertNotIn("submit_contracts", skill)

    def test_single_process_grouping_is_deterministic_and_evidence_bounded(self) -> None:
        rules = ROOT / "references/stages/boundaries/workload-boundary.md"
        rule_text = " ".join(rules.read_text(encoding="utf-8").split())

        self.assertIn("Workload Grouping is deterministic", rule_text)
        self.assertIn(
            "Do not search for healthcheck, volume, restart-policy, state, or listening-port signals",
            rule_text,
        )


if __name__ == "__main__":
    unittest.main()
