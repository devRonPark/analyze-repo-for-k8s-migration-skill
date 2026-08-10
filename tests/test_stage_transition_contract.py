import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

NON_FINAL_STAGE_SKILLS = [
    "analyze-k8s-discovery",
    "analyze-k8s-execution",
    "analyze-k8s-relationships",
    "analyze-k8s-boundaries",
    "analyze-k8s-contracts",
]


class StageTransitionContractTests(unittest.TestCase):
    def test_every_non_final_stage_has_unambiguous_accepted_and_rejected_branches(self) -> None:
        for name in NON_FINAL_STAGE_SKILLS:
            with self.subTest(skill=name):
                skill = (ROOT / f"runtime/stage-skills/{name}/SKILL.md").read_text(encoding="utf-8")

                self.assertIn("## Transition", skill)
                self.assertIn("If the submission is accepted:", skill)
                self.assertIn("If the submission is rejected:", skill)
                self.assertIn("handoff.next_skill", skill)
                self.assertIn(
                    "A response without `status: accepted` never authorizes a stage transition.",
                    skill,
                )
                self.assertIsNone(
                    re.search(r"Submit[^\n]*\bonce\b", skill),
                    "a Submit instruction still uses the ambiguous 'once' wording",
                )
                self.assertNotIn("End this stage after the server response", skill)

    def test_finalize_forbids_a_fallback_report_on_failure(self) -> None:
        skill = (ROOT / "runtime/stage-skills/analyze-k8s-finalize/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("If `finalize_analysis` fails, do not draft a fallback report.", skill)
        self.assertIsNone(re.search(r"call[^\n]*\bonce\b", skill))


if __name__ == "__main__":
    unittest.main()
