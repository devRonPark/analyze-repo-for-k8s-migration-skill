from pathlib import Path
import subprocess
import unittest

from scripts import run_quality_gate


ROOT = Path(__file__).resolve().parents[1]


class QualityGateTests(unittest.TestCase):
    def test_gate_stops_and_returns_child_failure(self):
        calls: list[list[str]] = []

        def failing_runner(command, *, cwd, check):
            calls.append(command)
            return subprocess.CompletedProcess(command, 17)

        result = run_quality_gate.run_gate(ROOT, runner=failing_runner)

        self.assertEqual(result, 17)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
