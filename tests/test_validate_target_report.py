from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ValidateTargetReportTests(unittest.TestCase):
    def test_receipt_changes_only_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            shutil.copy(ROOT / "tests/fixtures/reports/valid-summary.md", report)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_target_report.py"), str(report)], check=False)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Validation: passed", report.read_text(encoding="utf-8"))

    def test_detailed_finalize_skips_the_summary_only_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "detailed.md"
            shutil.copy(ROOT / "tests/fixtures/reports/valid-detailed.md", report)
            before = report.read_text(encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/validate_target_report.py"), str(report), "--mode", "detailed"],
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(report.read_text(encoding="utf-8"), before)

