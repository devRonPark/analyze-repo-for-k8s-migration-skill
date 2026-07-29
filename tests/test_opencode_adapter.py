from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts import run_opencode_acceptance as adapter


ROOT = Path(__file__).resolve().parents[1]


class OpenCodeAdapterTests(unittest.TestCase):
    def test_runtime_config_and_agent_use_supported_analysis_permissions(self):
        config = json.loads((ROOT / "runtime/opencode.json").read_text(encoding="utf-8"))
        provider = config["provider"]["local-sglang"]
        self.assertEqual(provider["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(provider["options"]["baseURL"], "http://172.16.4.249:30000/v1")
        self.assertIn("Qwen/Qwen3.6-35B-A3B-FP8", provider["models"])
        self.assertEqual(
            provider["models"]["Qwen/Qwen3.6-35B-A3B-FP8"]["options"]["reasoningEffort"],
            "none",
        )
        self.assertEqual(config["model"], "local-sglang/Qwen/Qwen3.6-35B-A3B-FP8")
        command = config["command"]["analyze-repo-for-kubernetes"]
        self.assertEqual(command["agent"], "kubernetes-migration-analyzer")
        self.assertFalse(command["subtask"])
        self.assertIn("Kubernetes", command["template"])
        permissions = config["permission"]
        self.assertEqual(permissions["edit"], "deny")
        self.assertEqual(permissions["external_directory"], "deny")
        self.assertEqual(permissions["skill"]["*"] , "deny")
        self.assertEqual(permissions["skill"]["analyze-repo-for-kubernetes"], "allow")
        self.assertEqual(permissions["bash"]["*"], "deny")
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("mode: primary", agent)
        self.assertIn("analyze-repo-for-kubernetes: allow", agent)

    def test_e2e_agent_has_bounded_summary_and_read_only_git_rules(self):
        config = json.loads((ROOT / "runtime/opencode.json").read_text(encoding="utf-8"))
        bash_rules = config["permission"]["bash"]
        for rule in (
            "git -C * status",
            "git -C * status *",
            "git -C * rev-parse *",
            "git -C * symbolic-ref *",
        ):
            self.assertEqual(bash_rules[rule], "allow")

        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertRegex(agent, r"(?m)^steps:\s+20$")
        self.assertIn("bounded high-signal pass", agent)
        self.assertRegex(agent, r"synthesize the\s+Summary immediately")
        for rule in (
            '"git -C * status": allow',
            '"git -C * status *": allow',
            '"git -C * rev-parse *": allow',
            '"git -C * symbolic-ref *": allow',
        ):
            self.assertIn(rule, agent)

    def test_event_normalization_extracts_skill_reads_and_denial(self):
        events = [
            {"type": "tool_use", "tool": "skill", "input": {"name": "analyze-repo-for-kubernetes"}},
            {"type": "tool_use", "tool": "read", "input": {"path": "assets/migration-summary-template.md"}},
            {"type": "error", "message": "Permission denied: edit"},
        ]
        trace = adapter.normalize_trace(events, "", "", 0, ["opencode"], {"description": "desc"}, "PASS")
        self.assertTrue(trace["skill"]["loaded"])
        self.assertIn("assets/migration-summary-template.md", trace["supporting_reads"])
        self.assertTrue(trace["permission_denials"])

    def test_missing_opencode_is_unavailable(self):
        case = {"id": "missing", "query": "query", "repository_fixture": "tests/fixtures/repos/sample"}
        trace = adapter.run_case(
            case,
            ROOT / "runtime/opencode.json",
            str(ROOT / "does-not-exist-opencode"),
            ROOT,
            Path(tempfile.mkdtemp()),
            Path(tempfile.mkdtemp()),
        )
        self.assertEqual(trace["status"], "UNAVAILABLE")
        self.assertNotEqual(trace["status"], "PASS")

    def test_command_uses_pure_json_agent_and_directory_flags(self):
        case = {"id": "command", "query": "query", "repository_fixture": "tests/fixtures/repos/sample"}

        def runner(command, **kwargs):
            self.assertIn("--pure", command)
            self.assertIn("--format", command)
            self.assertIn("json", command)
            self.assertIn("--agent", command)
            self.assertIn("--dir", command)
            return subprocess.CompletedProcess(command, 0, '{"type":"text","text":"ok"}\n', "")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config_dir = root / "config"
            home.mkdir()
            config_dir.mkdir()
            trace = adapter.run_case(
                case,
                ROOT / "runtime/opencode.json",
                "/bin/echo",
                ROOT,
                home,
                config_dir,
                runner=runner,
            )
        self.assertEqual(trace["status"], "PASS")

    def test_timeout_preserves_partial_json_events(self):
        case = {"id": "timeout", "query": "query", "repository_fixture": "tests/fixtures/repos/sample"}

        def runner(command, **kwargs):
            raise subprocess.TimeoutExpired(
                command,
                1,
                output='{"type":"tool_use","tool":"skill","input":{"name":"analyze-repo-for-kubernetes"}}\n',
                stderr="partial log",
            )

        with tempfile.TemporaryDirectory() as tmp:
            trace = adapter.run_case(
                case,
                ROOT / "runtime/opencode.json",
                "/bin/echo",
                ROOT,
                Path(tmp),
                Path(tmp),
                runner=runner,
            )
        self.assertEqual(trace["status"], "UNAVAILABLE")
        self.assertEqual(trace["returncode"], 124)
        self.assertTrue(trace["tool_calls"])


if __name__ == "__main__":
    unittest.main()
