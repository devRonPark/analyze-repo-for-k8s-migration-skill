import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.observations import ObservationRegistry, TargetSnapshot
from analysis_pipeline.tools.survey import SURVEY_OBSERVATION_CAP, compute_survey


class SurveyTests(unittest.TestCase):
    def registry(self, root: Path) -> ObservationRegistry:
        binding = {"binding_id": "b_test", "target_snapshot_hash": ""}
        registry = ObservationRegistry(root, binding)
        registry._snapshot_digest = TargetSnapshot.capture(root).digest
        return registry

    def test_missing_categories_each_issue_exactly_one_absence_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("nothing high-signal here\n", encoding="utf-8")
            survey = compute_survey(root, "discovery", self.registry(root))

        self.assertEqual(survey["stage"], "discovery")
        self.assertTrue(survey["surveyed"])
        self.assertEqual(len(survey["observations"]), len(survey["categories"]))
        self.assertTrue(all(status is False for status in survey["categories"].values()))
        self.assertTrue(all(observation["status"] == "unknown" for observation in survey["observations"]))
        self.assertTrue(all("reference" not in observation for observation in survey["observations"]))

    def test_present_matches_never_exceed_the_observation_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Every discovery build-manifest candidate name present at once,
            # each with several matching lines, to try to blow past the cap.
            for name in ("pom.xml", "build.gradle", "build.gradle.kts", "package.json", "requirements.txt", "pyproject.toml", "go.mod"):
                (root / name).write_text("\n".join(f"line {i}" for i in range(1, 30)), encoding="utf-8")
            (root / "Dockerfile").write_text("FROM python:3.13\n", encoding="utf-8")
            (root / "docker-compose.yml").write_text("services:\n  web:\n    image: app\n", encoding="utf-8")
            (root / "web.xml").write_text("<web-app></web-app>\n", encoding="utf-8")
            (root / ".env").write_text("KEY=value\n", encoding="utf-8")
            survey = compute_survey(root, "discovery", self.registry(root))

        self.assertLessEqual(len(survey["observations"]), SURVEY_OBSERVATION_CAP)

    def test_observation_stage_is_rejected_by_a_different_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dockerfile").write_text("FROM python:3.13\n", encoding="utf-8")
            registry = self.registry(root)
            survey = compute_survey(root, "execution", registry)
            present = next(o for o in survey["observations"] if o["status"] == "confirmed")
            with self.assertRaises(ValueError) as raised:
                registry.resolve(present["observation_ref"], "discovery", TargetSnapshot.capture(root))
        self.assertEqual(str(raised.exception), "observation stage mismatch")

    def test_contracts_survey_supplies_distinct_evidence_for_each_unclaimed_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dockerfile").write_text("FROM python:3.13\nHEALTHCHECK CMD true\n", encoding="utf-8")
            (root / "docker-compose.yml").write_text(
                "services:\n  web:\n    ports:\n      - 8080:8080\n    logging:\n      driver: json\n",
                encoding="utf-8",
            )
            required_slots = ["a_slot", "b_slot", "c_slot"]
            fact_statuses: dict[str, str] = {}
            registry = self.registry(root)

            import analysis_pipeline.tools.survey as survey_module

            original = survey_module._slots_needing_fresh_evidence
            survey_module._slots_needing_fresh_evidence = lambda slots, statuses: list(required_slots)
            try:
                survey = compute_survey(
                    root, "contracts", registry, required_report_slots=required_slots, fact_statuses=fact_statuses
                )
            finally:
                survey_module._slots_needing_fresh_evidence = original

        slot_observations = [o for o in survey["observations"] if o["category"].startswith("report_slot:")]
        self.assertEqual({o["category"] for o in slot_observations}, {f"report_slot:{slot}" for slot in required_slots})
        # Each report-slot observation must be distinct so the submitted
        # claims never collide on stage_contracts.py's "report slot evidence
        # duplicate" rule.
        self.assertEqual(len({o["observation_ref"] for o in slot_observations}), len(slot_observations))
        present_refs = [o.get("reference") for o in slot_observations if o["status"] == "confirmed"]
        self.assertEqual(len(present_refs), len(set(present_refs)))


if __name__ == "__main__":
    unittest.main()
