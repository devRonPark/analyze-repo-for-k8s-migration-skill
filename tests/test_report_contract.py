from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts import report_contract


ROOT = Path(__file__).resolve().parents[1]
REPORT_VALIDATOR = ROOT / "scripts/validate_report.py"
REPORT_FIXTURES = ROOT / "tests/fixtures/reports"


class ReportContractTests(unittest.TestCase):
    def run_validator(self, report: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(REPORT_VALIDATOR), str(report), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_current_summary_and_detailed_fixtures_pass(self):
        summary = self.run_validator(REPORT_FIXTURES / "valid-summary.md", "--mode", "summary")
        detailed = self.run_validator(REPORT_FIXTURES / "valid-detailed.md", "--mode", "detailed")

        self.assertEqual(summary.returncode, 0, summary.stdout + summary.stderr)
        self.assertEqual(detailed.returncode, 0, detailed.stdout + detailed.stderr)

    def test_legacy_verdict_is_rejected_by_default(self):
        report = REPORT_FIXTURES / "valid-summary.md"
        legacy = report.read_text(encoding="utf-8").replace("추가 정보 필요", "준비됨")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.md"
            path.write_text(legacy, encoding="utf-8")
            result = self.run_validator(path, "--mode", "summary")

        self.assertNotEqual(result.returncode, 0)

    def test_legacy_mode_is_explicit(self):
        result = self.run_validator(ROOT / "tests/fixtures/regression/invalid-actual-output.md", "--legacy")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("필수 키", result.stdout)

    def test_json_fixture_has_schema_version_and_passes(self):
        result = self.run_validator(REPORT_FIXTURES / "valid-summary.json", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads((REPORT_FIXTURES / "valid-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], report_contract.SCHEMA_VERSION)

    def test_json_without_schema_version_fails(self):
        payload = json.loads((REPORT_FIXTURES / "valid-summary.json").read_text(encoding="utf-8"))
        payload.pop("schema_version")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(path, "--format", "json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema_version", result.stdout)

    def test_json_mode_contracts_have_different_required_fields(self):
        summary = json.loads((REPORT_FIXTURES / "valid-summary.json").read_text(encoding="utf-8"))
        summary.pop("dependencies", None)
        self.assertEqual(report_contract.validate_json_payload(summary), [])

        detailed = dict(summary)
        detailed["mode"] = "detailed"
        self.assertIn("dependencies", " ".join(report_contract.validate_json_payload(detailed)))

    def test_schema_enums_match_runtime_contract(self):
        schema = json.loads((ROOT / "schemas/analysis-result.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(
            schema["properties"]["design_input_verdict"]["enum"],
            list(report_contract.READINESS_VERDICTS),
        )
        self.assertEqual(
            schema["$defs"]["evidenceStatus"]["enum"],
            list(report_contract.EVIDENCE_STATUSES),
        )
        self.assertEqual(
            schema["$defs"]["containerization"]["enum"],
            list(report_contract.CONTAINERIZATION_VALUES),
        )
        self.assertEqual(
            schema["$defs"]["configurationTiming"]["enum"],
            list(report_contract.CONFIGURATION_TIMING),
        )

    def test_schema_fixture_changes_contract_values_without_python_constants(self):
        schema = json.loads((ROOT / "schemas/analysis-result.schema.json").read_text(encoding="utf-8"))
        schema["$defs"]["evidenceStatus"]["enum"].append("fixture-status")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schema.json"
            path.write_text(json.dumps(schema), encoding="utf-8")
            contract = report_contract.load_contract(path)

        self.assertIn("fixture-status", contract["evidence_statuses"])


if __name__ == "__main__":
    unittest.main()
