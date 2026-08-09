import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContractsSkillTests(unittest.TestCase):
    def test_contracts_is_a_current_only_report_slot_quality_gate(self) -> None:
        skill = (ROOT / "runtime/stage-skills/analyze-k8s-contracts/SKILL.md").read_text(encoding="utf-8")
        references = [
            ROOT / "runtime/stage-skills/analyze-k8s-contracts/references/configuration-timing.md",
            ROOT / "runtime/stage-skills/analyze-k8s-contracts/references/evidence-and-readiness.md",
            ROOT / "runtime/stage-skills/analyze-k8s-contracts/references/repository-analysis-checklist.md",
        ]

        for term in ("Gap Analysis", "Quality Gate", "Submit", "submit_contracts", "report_slots", "boundaries_fact_refs"):
            self.assertIn(term, skill)
        for reference in references:
            self.assertTrue(reference.is_file())
        self.assertIn("only when `mode` is `detailed`", skill)
        self.assertNotIn("analyze-k8s-finalize", skill)
        self.assertNotIn("finalize_analysis", skill)


if __name__ == "__main__":
    unittest.main()
