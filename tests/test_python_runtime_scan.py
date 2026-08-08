import unittest
from pathlib import Path

from scripts.verify_python_runtime import scan


ROOT = Path(__file__).resolve().parents[1]


class PythonRuntimeScanTests(unittest.TestCase):
    def test_delivered_runtime_has_no_legacy_javascript_artifacts(self):
        self.assertEqual(scan(ROOT), [])
