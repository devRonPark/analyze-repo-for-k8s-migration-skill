import importlib
import inspect
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_dist, mcp_smoke


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "python"))
git_metadata = importlib.import_module("analysis_pipeline.tools.git_metadata")


class SubprocessEncodingTests(unittest.TestCase):
    def test_captured_project_subprocesses_explicitly_decode_utf8(self):
        completed = subprocess.CompletedProcess([], 0, "Kubernetes 설계 입력 요약\n", "")
        with patch("scripts.build_dist.subprocess.run", return_value=completed) as mocked:
            self.assertEqual(build_dist.revision(ROOT), "Kubernetes 설계 입력 요약")
            self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")
        with patch("scripts.mcp_smoke.subprocess.run", return_value=completed) as mocked:
            self.assertEqual(mcp_smoke.git_status(ROOT), "Kubernetes 설계 입력 요약\n")
            self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")
        self.assertIn('text=True, encoding="utf-8"', inspect.getsource(mcp_smoke.make_external_fixture))
        with patch("analysis_pipeline.tools.git_metadata.subprocess.run", return_value=completed) as mocked:
            self.assertIn("Kubernetes 설계 입력 요약", git_metadata.git_metadata(ROOT))
            self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")


if __name__ == "__main__":
    unittest.main()
