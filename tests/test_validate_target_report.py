from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ValidateTargetReportTests(unittest.TestCase):
    def test_receipt_changes_only_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            shutil.copy(ROOT / "tests/fixtures/reports/valid-summary.md", report)
            result = subprocess.run(["python3", str(ROOT / "scripts/validate_target_report.py"), str(report)], check=False)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Validation: passed", report.read_text(encoding="utf-8"))

