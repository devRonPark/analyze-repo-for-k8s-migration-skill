from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/golden/full-stack-fastapi-template-summary.md"


class SummaryQualityTests(unittest.TestCase):
    def test_golden_is_compact_and_valid(self):
        text = GOLDEN.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 90)
        for name in ("backend", "frontend", "prestart", "PostgreSQL"):
            self.assertIn(name, text)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_report.py"), str(GOLDEN), "--mode", "summary"], check=False, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout)
