from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/fixtures/discovery/cases.json"
ALLOWED_OUTCOMES = {
    "배포 대상 후보",
    "저장소에 정의된 런타임 의존성",
    "외부 런타임 의존성",
    "배포 대상 후보에서 제외한 항목",
}


class DiscoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CASES.read_text(encoding="utf-8"))
        cls.fixture_root = CASES.parent

    def test_every_item_has_one_allowed_classification_and_evidence(self):
        for case in self.payload["cases"]:
            for item in case["items"]:
                self.assertIn(item["classification"], ALLOWED_OUTCOMES)
                self.assertTrue(item["evidence"])
                for path in item["evidence"]:
                    self.assertTrue((self.fixture_root / case["fixture"] / path).is_file(), path)

    def test_manifests_alone_do_not_make_shared_library_a_candidate(self):
        shared = next(
            item
            for case in self.payload["cases"]
            for item in case["items"]
            if item["name"] == "shared"
        )

        self.assertEqual(shared["classification"], "배포 대상 후보에서 제외한 항목")
        self.assertTrue(shared["reason"])

    def test_dockerfile_free_runtime_candidates_remain_analyzable(self):
        case = next(case for case in self.payload["cases"] if case["id"] == "dockerfile-free-node")

        self.assertFalse(case["dockerfile_present"])
        self.assertTrue(any(item["classification"] == "배포 대상 후보" for item in case["items"]))
        self.assertEqual(case["containerization"], "컨테이너화 필요")

    def test_node_and_java_conflicts_remain_visible(self):
        for case_id in ("node-package-manager-conflict", "java-build-tool-conflict"):
            case = next(case for case in self.payload["cases"] if case["id"] == case_id)
            self.assertIn(case["status"], {"상충됨", "미확인"})
            self.assertGreaterEqual(len(case["evidence"]), 2)

    def test_build_image_and_startup_stages_are_distinct(self):
        for case in self.payload["cases"]:
            for item in case["items"]:
                stages = item.get("commands")
                if not stages:
                    continue
                self.assertEqual(set(stages), {"install", "build", "image", "startup"})

    def test_rule_ownership_is_separated(self):
        workflow = (ROOT / "references/workflow.md").read_text(encoding="utf-8")
        checklist = (ROOT / "references/repository-analysis-checklist.md").read_text(encoding="utf-8")
        language = (ROOT / "references/language-discovery-rules.md").read_text(encoding="utf-8")

        self.assertIn("Classify findings", workflow)
        self.assertIn("Required Component Fields", checklist)
        self.assertIn("Node.js", language)
        self.assertIn("Java and Kotlin", language)
        self.assertNotIn("packageManager", workflow)
        self.assertNotIn("Maven", checklist)


if __name__ == "__main__":
    unittest.main()
