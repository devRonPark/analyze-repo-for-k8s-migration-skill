import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STAGES = ("discovery", "execution", "relationships", "boundaries", "contracts", "finalize")


class StageTransitionContractTests(unittest.TestCase):
    def test_public_skill_uses_only_server_current_stage_for_progressive_disclosure(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("`current_stage`", skill)
        self.assertIn("references/stages/<current_stage>.md", skill)
        self.assertNotIn("next_skill", skill)
        self.assertNotIn("load exactly", skill)

    def test_each_stage_procedure_isolated_and_has_its_current_submit_checkpoint(self) -> None:
        for stage in STAGES:
            with self.subTest(stage=stage):
                procedure = (ROOT / f"references/stages/{stage}.md").read_text(encoding="utf-8")
                expected_tool = "finalize_analysis" if stage == "finalize" else f"submit_{stage}"

                self.assertIn(expected_tool, procedure)
                self.assertNotIn("next_skill", procedure)
                self.assertNotIn("## Transition", procedure)

    def test_finalize_forbids_a_fallback_report_on_failure(self) -> None:
        procedure = (ROOT / "references/stages/finalize.md").read_text(encoding="utf-8")
        self.assertIn("If `finalize_analysis` fails, do not draft a fallback report.", procedure)


if __name__ == "__main__":
    unittest.main()
