from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/evaluation/cases.json"
GOLDEN = ROOT / "tests/evaluation/golden-actual"
EVALUATOR = ROOT / "scripts/evaluate_scenarios.py"


class ScenarioEvaluatorTests(unittest.TestCase):
    def run_evaluator(self, cases: Path = CASES, actual: Path = GOLDEN):
        return subprocess.run(
            [sys.executable, str(EVALUATOR), "--cases", str(cases), "--actual-dir", str(actual)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_golden_actual_reports_pass(self):
        result = self.run_evaluator()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(len(payload["cases"]), 8)

    def test_missing_actual_report_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_evaluator(actual=Path(tmp))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing actual report", result.stdout)

    def test_wrong_candidate_or_dependency_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = Path(tmp) / "actual"
            shutil.copytree(GOLDEN, actual)
            report = actual / "confirmed-summary/report.json"
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["components"][0]["name"] = "wrong"
            report.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_evaluator(actual=actual)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate", result.stdout)

    def test_repository_change_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            copied_repo = temporary / "confirmed-repo"
            shutil.copytree(ROOT / "tests/evaluation/repos/confirmed", copied_repo)
            (copied_repo / "README.md").write_text("changed\n", encoding="utf-8")
            cases = json.loads(CASES.read_text(encoding="utf-8"))
            confirmed = next(case for case in cases["cases"] if case["id"] == "confirmed-summary")
            confirmed["repository_fixture"] = str(copied_repo)
            cases_path = temporary / "cases.json"
            cases_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
            result = self.run_evaluator(cases=cases_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repository changed", result.stdout)

    def test_repeated_core_fields_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = Path(tmp) / "actual"
            shutil.copytree(GOLDEN, actual)
            repeat = actual / "confirmed-summary/repeat.json"
            payload = json.loads(repeat.read_text(encoding="utf-8"))
            payload["design_input_verdict"] = "분석 불가"
            repeat.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_evaluator(actual=actual)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repeat", result.stdout)


if __name__ == "__main__":
    unittest.main()
