from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts import run_opencode_acceptance as adapter


ROOT = Path(__file__).resolve().parents[1]


class OpenCodeAdapterTests(unittest.TestCase):
    def test_isolated_config_allows_only_the_actual_temporary_skill_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "config" / "skills" / adapter.SKILL_ID
            config = root / "runtime" / "opencode.json"
            adapter.copy_skill(ROOT, skill)
            adapter.isolated_config(ROOT / "runtime/opencode.json", config, skill)
            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["permission"]["external_directory"],
                {f"{skill.resolve().as_posix()}/**": "allow"},
            )
            self.assertFalse((root / "target" / ".opencode").exists())

    def test_rendered_isolated_agent_does_not_allow_application_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "config" / "skills" / adapter.SKILL_ID
            agent = root / "config" / "agents" / f"{adapter.AGENT_ID}.md"
            adapter.render_agent(ROOT / "runtime/agents/kubernetes-migration-analyzer.md", agent, skill)
            text = agent.read_text(encoding="utf-8")
            self.assertIn(f'"{skill.resolve().as_posix()}/**": allow', text)
            self.assertNotIn("/tmp/opencode-acceptance-*/config/skills", text)
            self.assertNotIn('"$HOME/.config/opencode/skills', text)
            self.assertNotIn('"$HOME/.agents/skills', text)
            self.assertNotIn('"$HOME/.claude/skills', text)

    def test_discovery_audit_reports_stale_and_unexpected_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = root / ".config" / "opencode" / "skills"
            current = skills / adapter.SKILL_ID
            stale = skills / "old-test-skill"
            adapter.copy_skill(ROOT, current)
            stale.mkdir(parents=True)
            (current / "SKILL.md").write_text("stale\n", encoding="utf-8")
            audit = adapter.discovery_audit(ROOT, root, None, root / "application", "user")
            self.assertIn(str(current), audit["stale_or_mismatched_skill_paths"])
            self.assertIn("old-test-skill", audit["unexpected_skill_ids"])

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
        self.assertRegex(agent, r"(?m)^steps:\s+14$")
        self.assertIn("bounded high-signal pass", agent)
        self.assertRegex(agent, r"synthesize the\s+Summary immediately")
        for rule in (
            '"git -C * status": allow',
            '"git -C * status *": allow',
            '"git -C * rev-parse *": allow',
            '"git -C * symbolic-ref *": allow',
        ):
            self.assertIn(rule, agent)

    def test_summary_and_detailed_routing_are_explicit(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("default Summary", agent)
        self.assertIn("For an explicit Detailed request", agent)
        for reference in (
            "repository-analysis-checklist.md",
            "migration-assessment-template.md",
            "configuration-timing.md",
            "dependency-analysis.md",
        ):
            self.assertIn(reference, agent)
        self.assertIn("Do not inspect lockfiles by default", agent)

    def test_acceptance_cases_enforce_mode_specific_reads(self):
        cases = json.loads((ROOT / "tests/evaluation/opencode-cases.json").read_text(encoding="utf-8"))["cases"]
        summary = next(case for case in cases if case["id"] == "minimal-summary")
        detailed = next(case for case in cases if case["id"] == "explicit-detailed")
        self.assertIn("repository-analysis-checklist.md", summary["forbidden_behavior"]["reads"])
        self.assertIn("migration-assessment-template.md", detailed["expected_behavior"]["required_reads"])
        self.assertIn("repository-analysis-checklist.md", detailed["expected_behavior"]["required_reads"])

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

    def test_event_normalization_uses_actual_tool_inputs_and_errors(self):
        events = [
            {"part": {"tool": "skill", "state": {"input": {"name": adapter.SKILL_ID}}}},
            {"part": {"tool": "read", "state": {"input": {
                "filePath": "/tmp/skills/assets/migration-summary-template.md",
            }}}},
            {"part": {"tool": "edit", "state": {
                "status": "error", "error": "tool unavailable",
                "input": {"filePath": "/tmp/README.md"},
            }}},
        ]
        trace = adapter.normalize_trace(events, "", "", 0, ["opencode"], {"description": "desc"}, "PASS")
        self.assertTrue(trace["skill"]["loaded"])
        self.assertIn("SKILL.md", trace["supporting_reads"])
        self.assertEqual(
            trace["supporting_reads"],
            ["SKILL.md", "assets/migration-summary-template.md"],
        )
        self.assertIn("edit", " ".join(item["event"] for item in trace["permission_denials"]))

    def test_skill_name_in_agent_text_does_not_count_as_loaded(self):
        trace = adapter.normalize_trace(
            [{"type": "text", "text": f"Agent may use {adapter.SKILL_ID}."}],
            "",
            "",
            0,
            ["opencode"],
            {"description": "desc"},
            "PASS",
        )
        self.assertFalse(trace["skill"]["loaded"])

    def test_extract_report_reads_complete_event_when_final_output_is_truncated(self):
        report = {
            "schema_version": "1.0",
            "mode": "summary",
            "components": [],
            "dependencies": [],
            "excluded_items": [],
            "missing_inputs": [],
            "evidence": [],
            "design_input_verdict": "추가 정보 필요",
        }
        text = "```json\n" + json.dumps(report, ensure_ascii=False) + "\n```\n" + ("x" * 12000)
        trace = {"final_output": text[-12000:], "events": [{"type": "text", "text": text}]}
        self.assertEqual(adapter.extract_report(trace), report)

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

    def test_user_mode_runs_from_application_repository_without_overriding_config(self):
        case = {"id": "user", "query": "query", "repository_fixture": "tests/fixtures/repos/sample"}
        captured = {}

        def runner(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, '{"type":"text","text":"ok"}\n', "")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "application"
            target.mkdir()
            (target / "README.md").write_text("fixture\n", encoding="utf-8")
            home = Path(tmp) / "home"
            home.mkdir()
            trace = adapter.run_case(
                case,
                None,
                "/bin/echo",
                ROOT,
                home,
                home / ".config" / "opencode",
                repository_root=target,
                mode="user",
                runner=runner,
                pure=False,
            )
        self.assertEqual(trace["status"], "PASS")
        self.assertEqual(captured["kwargs"]["cwd"], target)
        self.assertEqual(captured["command"][captured["command"].index("--dir") + 1], str(target.resolve()))
        self.assertNotIn("--pure", captured["command"])
        self.assertTrue(trace["repository"]["unchanged"])

    def test_analysis_case_connects_custom_command_to_named_agent(self):
        case = {
            "id": "command-link",
            "query": "query",
            "repository_fixture": "tests/fixtures/repos/sample",
            "acceptance_type": "analysis",
        }

        def runner(command, **kwargs):
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
        self.assertIn("--command", trace["command"])
        self.assertEqual(trace["command_agent"], adapter.AGENT_ID)
        self.assertTrue(trace["command_agent_matches"])

    def test_debug_probes_preserve_stdout_and_stderr_outside_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "application"
            target.mkdir()
            output = root / "debug"
            result = adapter.run_debug_probes(
                "/bin/echo",
                target,
                {"HOME": str(root / "home")},
                output,
                timeout=1,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["probes"]), 4)
            self.assertTrue((output / "config.stdout.log").is_file())
            self.assertFalse((target / ".opencode").exists())

    def test_interactive_probe_uses_application_dir_and_preserves_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "application"
            target.mkdir()
            output = root / "interactive"
            result = adapter.run_interactive_probe(
                "/bin/echo",
                target,
                {"HOME": str(root / "home")},
                output,
                pure=True,
                timeout=1,
            )
            self.assertTrue(Path(result["stdout_file"]).is_file())
        self.assertEqual(result["status"], "PASS")
        self.assertIn("--interactive", result["command"])
        self.assertIn("--dir", result["command"])

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
