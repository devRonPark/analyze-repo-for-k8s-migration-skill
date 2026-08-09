import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FinalizationSkillTests(unittest.TestCase):
    def test_finalizer_relays_only_the_canonical_server_markdown(self) -> None:
        skill = (ROOT / "runtime/stage-skills/analyze-k8s-finalize/SKILL.md").read_text(encoding="utf-8")

        for term in ("Finalize", "finalize_analysis", "canonical Markdown", "Relay"):
            self.assertIn(term, skill)
        self.assertIn("Do not read target evidence", skill)
        for forbidden in ("read_evidence", "list_target_paths"):
            self.assertNotIn(forbidden, skill)


if __name__ == "__main__":
    unittest.main()
