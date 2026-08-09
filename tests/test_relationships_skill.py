import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RelationshipsSkillTests(unittest.TestCase):
    def test_relationships_is_a_current_only_grounded_quality_gate(self) -> None:
        skill = (ROOT / "runtime/stage-skills/analyze-k8s-relationships/SKILL.md").read_text(encoding="utf-8")
        rules = ROOT / "runtime/stage-skills/analyze-k8s-relationships/references/dependency-analysis.md"

        for leading_word in ("Grounding", "Quality Gate", "Vertical Slice", "Submit"):
            self.assertIn(leading_word, skill)
        self.assertIn("submit_relationships", skill)
        for field in ("mode", "discovery_fact_refs", "execution_fact_refs", "process_ids", "unknown_ids"):
            self.assertIn(field, skill)
        self.assertTrue(rules.is_file())
        rules_text = rules.read_text(encoding="utf-8")
        self.assertIn("확인된 저장소 기동 정의에서 사용되는지", rules_text)
        self.assertIn("공급 또는 관리 경계", rules_text)
        self.assertIn("Summary uses one concise runtime-dependency", rules_text)
        self.assertIn("does not require a dependency matrix", rules_text)
        self.assertIn("Detailed uses both", rules_text)
        self.assertIn("two representations must agree", rules_text)
        self.assertIn("structured graph edges", " ".join(skill.split()))
        self.assertNotIn("analyze-k8s-boundaries", skill)
        self.assertNotIn("submit_boundaries", skill)
        self.assertNotIn("reopen_analysis", skill)


if __name__ == "__main__":
    unittest.main()
