from pathlib import Path
import json
import tempfile
import unittest

from scripts import measure_context


class ContextMeasurementTests(unittest.TestCase):
    def test_measurement_counts_loaded_files_and_preserves_missing_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            skill.mkdir()
            loaded = skill / "SKILL.md"
            loaded.write_text("one\ntwo\n", encoding="utf-8")
            trace_dir = root / "traces" / "case"
            trace_dir.mkdir(parents=True)
            trace = {
                "case_id": "case",
                "status": "PASS",
                "profile": {
                    "mode": "isolated",
                    "cwd": str(root / "application"),
                    "skill_discovery_paths": [str(skill)],
                    "agent_paths": [],
                    "environment": {
                        "HOME": str(root / "home"),
                        "OPENCODE_CONFIG": str(root / "runtime.json"),
                        "OPENCODE_CONFIG_DIR": str(root / "config"),
                    },
                },
                "supporting_reads": ["SKILL.md"],
                "tool_calls": [{"tool": "read"}],
                "events": [{"type": "step_finish"}],
                "repository": {"unchanged": True},
            }
            (trace_dir / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
            result = measure_context.measure(root / "traces")
        measurement = result["measurements"][0]
        self.assertEqual(measurement["loaded_files"]["bytes"], len(b"one\ntwo\n"))
        self.assertEqual(measurement["loaded_files"]["lines"], 2)
        self.assertIsNone(measurement["provider_usage"])
        self.assertEqual(measurement["tool_call_count"], 1)
        self.assertTrue(measurement["repository_unchanged"])

    def test_usage_is_only_reported_when_events_expose_numeric_usage(self):
        trace = {
            "events": [{"usage": {"input_tokens": 10, "output_tokens": 3}}],
            "profile": {},
            "supporting_reads": [],
            "tool_calls": [],
        }
        result = measure_context.trace_measurement(Path("trace.json"), trace)
        self.assertEqual(result["provider_usage"], {"input_tokens": 10, "output_tokens": 3})


if __name__ == "__main__":
    unittest.main()
