import json
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_opencode_acceptance as adapter


ROOT = Path(__file__).resolve().parents[1]


class StaticMCPOpenCodeAcceptanceTests(unittest.TestCase):
    def test_case_manifest_covers_exactly_the_sealed_six_goldens(self):
        cases = adapter.load_static_mcp_cases(ROOT / "tests/evaluation/static-mcp-opencode-cases.json")
        sealed = adapter.load_static_mcp_golden_manifest(
            ROOT / "tests/evaluation/static-mcp-golden-manifest.json"
        )

        self.assertEqual(adapter.validate_static_mcp_cases(cases, sealed), [])
        self.assertEqual(len(cases), 6)
        self.assertEqual({case["path_style"] for case in cases}, {"absolute", "command-relative"})

    def test_command_prompt_preserves_selected_path_and_mode(self):
        absolute = {
            "target_path": r"C:\temp\opencode-e2e-jpetstore-6",
            "mode": "summary",
        }
        relative = {
            "target_path": "opencode-e2e-flask-celery",
            "mode": "detailed",
        }

        self.assertEqual(
            adapter.static_mcp_command_prompt(absolute),
            r"/analyze-repo-for-kubernetes C:\temp\opencode-e2e-jpetstore-6 Summary",
        )
        self.assertEqual(
            adapter.static_mcp_command_prompt(relative),
            "/analyze-repo-for-kubernetes opencode-e2e-flask-celery Detailed",
        )
        self.assertEqual(
            adapter.static_mcp_command_keystrokes(relative),
            ["/", "analyze-repo-for-kubernetes opencode-e2e-flask-celery Detailed", "\r"],
        )

    def test_transition_audit_requires_one_complete_accepted_path(self):
        complete = [
            {"name": "analysis_start_analysis", "result": {"status": "accepted"}},
            {"name": "analysis_submit_discovery", "result": {"status": "accepted"}},
            {"name": "analysis_submit_execution", "result": {"status": "accepted"}},
            {"name": "analysis_submit_relationships", "result": {"status": "accepted"}},
            {"name": "analysis_submit_boundaries", "result": {"status": "accepted"}},
            {"name": "analysis_submit_contracts", "result": {"status": "accepted"}},
            {"name": "analysis_finalize_analysis", "result": {"status": "finalized"}},
        ]

        self.assertEqual(adapter.static_mcp_transition_errors(complete), [])
        self.assertIn(
            "submit_contracts must be accepted exactly once",
            adapter.static_mcp_transition_errors(complete[:-2]),
        )

    def test_transition_audit_reads_real_opencode_state_output(self):
        calls = [
            {
                "name": f"analysis_{name}",
                "state": {"output": json.dumps({"structuredContent": {"status": status}})},
            }
            for name, status in adapter.STATIC_MCP_TOOL_SEQUENCE
        ]
        self.assertEqual(adapter.static_mcp_transition_errors(calls), [])

    def test_final_markdown_score_records_citations_without_claiming_semantic_equivalence(self):
        golden = ROOT / "tests/evaluation/static-mcp-jpetstore-6-summary-golden.md"
        result = adapter.score_static_mcp_markdown(
            "# Kubernetes 설계 입력 요약\n\n- `pom.xml:33`\n- `Dockerfile:21`\n",
            golden,
        )

        self.assertEqual(result["required_citations"], 8)
        self.assertEqual(result["matched_citations"], 2)
        self.assertFalse(result["semantic_score_claimed"])

    def test_config_command_template_accepts_user_arguments(self):
        payload = json.loads((ROOT / "runtime/opencode.json").read_text(encoding="utf-8"))
        self.assertIn(
            "$ARGUMENTS",
            payload["command"]["analyze-repo-for-kubernetes"]["template"],
        )

    def test_isolated_config_can_select_the_required_windows_python_launcher(self):
        class Destination:
            parent: "Destination"

            def __init__(self):
                self.parent = self
                self.rendered = ""

            def mkdir(self, **_kwargs):
                return None

            def write_text(self, text, **_kwargs):
                self.rendered = text

        config = Destination()
        adapter.isolated_config_bundle(
            ROOT / "runtime/opencode.json",
            config,  # type: ignore[arg-type]
            ROOT / ".artifacts" / "static-mcp-config",
            runtime_python=r"C:\Python313\python.exe",
        )
        payload = json.loads(config.rendered)
        self.assertEqual(
            payload["mcp"]["analysis"]["command"][0],
            r"C:\Python313\python.exe",
        )

    def test_windows_pty_environment_forwards_only_runtime_variables_and_optional_provider_key(self):
        environment = adapter.static_mcp_runtime_environment(
            {
                "PATH": r"C:\Windows\System32",
                "UPSTAGE_API_KEY": "not-printed",
                "UNRELATED_SECRET": "must-not-forward",
            },
            home=Path("temp/home"),
            config=Path("temp/opencode.json"),
            config_dir=Path("temp/config"),
            log_root=Path("temp/logs"),
        )

        self.assertNotIn("UNRELATED_SECRET", environment)
        self.assertEqual(environment["UPSTAGE_API_KEY"], "not-printed")
        self.assertEqual(environment["OPENCODE_CONFIG_DIR"], str(Path("temp/config").resolve()))
        self.assertEqual(environment["PYWINPTY_BLOCK"], "0")
        self.assertEqual(environment["TERM"], "xterm-256color")
        self.assertEqual(environment["COLORTERM"], "truecolor")
        self.assertNotIn("WSLENV", environment)

    def test_windows_pty_dependency_is_rejected_off_windows(self):
        with mock.patch.object(adapter.os, "name", "posix"):
            with self.assertRaisesRegex(ValueError, "Windows PTY"):
                adapter.windows_pty_process(None)

    def test_windows_pty_spawn_makes_the_parent_read_nonblocking(self):
        captured = {}

        class StubPty:
            @staticmethod
            def spawn(*args, **kwargs):
                captured["blocking"] = adapter.os.environ.get("PYWINPTY_BLOCK")
                captured["args"] = args
                captured["kwargs"] = kwargs
                return object()

        with mock.patch.dict(adapter.os.environ, {"PYWINPTY_BLOCK": "1"}):
            process = adapter.spawn_windows_pty(
                StubPty,
                ["opencode.exe", "C:\\temp"],
                cwd="C:\\temp",
                environment={"PATH": "C:\\Windows"},
            )

            self.assertEqual(captured["blocking"], "0")
            self.assertEqual(adapter.os.environ["PYWINPTY_BLOCK"], "1")
            self.assertIsNotNone(process)

    def test_windows_pty_read_discards_idle_events_before_readiness_detection(self):
        class StubPty:
            @staticmethod
            def read(_size):
                return "0011IgnoreAsk anything..."

        self.assertEqual(adapter.read_windows_pty(StubPty()), "Ask anything...")

    def test_terminal_agent_stop_is_an_early_static_mcp_failure(self):
        reason = adapter.static_mcp_terminal_stop_reason(
            "No further tool calls can be made until the next user interaction or handoff acceptance."
        )

        self.assertEqual(reason, "OpenCode agent stopped before the MCP workflow finalized")
        self.assertIsNone(adapter.static_mcp_terminal_stop_reason("analysis_submit_discovery completed"))


if __name__ == "__main__":
    unittest.main()
