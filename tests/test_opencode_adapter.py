from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts import run_opencode_acceptance as adapter
from scripts import evaluate_scenarios


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
        self.assertEqual(permissions["glob"], "allow")
        self.assertEqual(permissions["git_metadata"], "allow")
        for tool_name in ("grep", "list"):
            self.assertEqual(permissions[tool_name], "deny")
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("mode: primary", agent)
        self.assertIn("analyze-repo-for-kubernetes: allow", agent)
        self.assertIn("trusted `glob` tool only to list target paths", agent)
        self.assertIn("call only trusted `git_metadata`", agent)

    def test_e2e_agent_has_bounded_summary_and_no_target_shell_rules(self):
        config = json.loads((ROOT / "runtime/opencode.json").read_text(encoding="utf-8"))
        bash_rules = config["permission"]["bash"]
        self.assertEqual(bash_rules, {"*": "deny"})

        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertRegex(agent, r"(?m)^steps:\s+32$")
        self.assertIn("bounded high-signal pass", agent)
        self.assertRegex(agent, r"synthesize the\s+Summary immediately")
        self.assertIn("no more than twelve target `read` calls", agent)

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

    def test_summary_prompt_requires_direct_markdown_contract(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("final assistant response must be the completed Markdown report", agent)
        self.assertIn("progress updates are allowed", agent)
        self.assertIn("# Kubernetes 설계 입력 요약", agent)
        self.assertIn("Korean 열린 항목 labels", agent)
        self.assertNotIn("For renderer input JSON", agent)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("progress\nupdates are allowed", skill)

    def test_detailed_output_has_compact_decision_summary_rules(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        template = (ROOT / "assets/migration-assessment-template.md").read_text(encoding="utf-8")
        self.assertIn("### 핵심 요약", agent)
        self.assertIn("Do not expose planning", agent)
        self.assertIn("### 핵심 요약", template)
        self.assertIn("기본값이나 예시를 채우지 않는다", template)
        self.assertIn("70 lines and 1,200 Korean words", agent)
        self.assertNotIn("| 연결 workload |", template)
        self.assertIn("Detailed output must not use Markdown tables", agent)

    def test_detailed_final_output_uses_the_verbatim_markdown_contract(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        normalized = agent.replace("\n", " ")
        self.assertIn("must begin exactly with `# Kubernetes 설계 입력 상세 평가`", agent)
        self.assertIn("all eight `##` headings from the Detailed template verbatim", normalized)
        self.assertIn("report-contract=1.0", agent)

    def test_agent_requires_high_signal_runtime_conflict_and_seed_checks(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for text in (
            "report a disagreement as `상충됨`",
            "image tags exactly",
            "credential-exposure location",
            "external database",
            "final evidence self-check",
            "Never emit a\nseed username",
            "never call it missing, unstable, unavailable",
        ):
            self.assertIn(text, agent)
        self.assertIn("Embedded startup\ndata alone does not evidence a PersistentVolume", skill)
        summary = (ROOT / "assets/migration-summary-template.md").read_text(encoding="utf-8")
        self.assertIn("embedded database is a runtime dependency", summary)
        self.assertNotIn("| <설계 차단|설계 결정|배포 입력|권장 사항>", summary)
        self.assertIn("Release gate", agent)

    def test_acceptance_cases_enforce_mode_specific_reads(self):
        cases = json.loads((ROOT / "tests/evaluation/opencode-cases.json").read_text(encoding="utf-8"))["cases"]
        summary = next(case for case in cases if case["id"] == "minimal-summary")
        detailed = next(case for case in cases if case["id"] == "explicit-detailed")
        self.assertIn("workflow.md", summary["expected_behavior"]["required_reads"])
        self.assertIn("migration-summary-template.md", summary["expected_behavior"]["required_reads"])
        self.assertIn("repository-analysis-checklist.md", summary["forbidden_behavior"]["reads"])
        self.assertIn("migration-assessment-template.md", detailed["expected_behavior"]["required_reads"])
        self.assertIn("repository-analysis-checklist.md", detailed["expected_behavior"]["required_reads"])

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

    def test_detailed_output_has_compact_decision_summary_rules(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        template = (ROOT / "assets/migration-assessment-template.md").read_text(encoding="utf-8")
        self.assertIn("### 핵심 요약", agent)
        self.assertIn("Do not expose planning", agent)
        self.assertIn("### 핵심 요약", template)
        self.assertIn("기본값이나 예시를 채우지 않는다", template)

    def test_acceptance_cases_enforce_mode_specific_reads(self):
        cases = json.loads((ROOT / "tests/evaluation/opencode-cases.json").read_text(encoding="utf-8"))["cases"]
        summary = next(case for case in cases if case["id"] == "minimal-summary")
        detailed = next(case for case in cases if case["id"] == "explicit-detailed")
        self.assertIn("workflow.md", summary["expected_behavior"]["required_reads"])
        self.assertIn("migration-summary-template.md", summary["expected_behavior"]["required_reads"])
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

    def test_retains_only_a_valid_direct_summary_markdown(self):
        markdown = (ROOT / "tests/fixtures/reports/valid-summary.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            report = adapter.retain_summary_markdown(
                markdown,
                Path(tmp),
                ROOT / "tests/fixtures/repos/sample",
            )

        self.assertTrue(report.startswith("# Kubernetes 설계 입력 요약\n"))

    def test_retains_the_final_summary_after_interactive_progress(self):
        report = (ROOT / "tests/fixtures/reports/valid-summary.md").read_text(encoding="utf-8")
        markdown = "분석 중입니다.\n" + report
        with tempfile.TemporaryDirectory() as tmp:
            retained = adapter.retain_summary_markdown(
                markdown,
                Path(tmp),
                ROOT / "tests/fixtures/repos/sample",
            )
        self.assertEqual(retained, report)

    def test_rejects_summary_without_a_final_report_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "does not contain"):
                adapter.retain_summary_markdown(
                    "분석 중입니다.",
                    Path(tmp),
                    ROOT / "tests/fixtures/repos/sample",
                )

    def test_evaluator_uses_direct_summary_markdown(self):
        case = {
            "id": "summary",
            "repository_fixture": "tests/fixtures/repos/sample",
            "repository_snapshot": {"pom.xml": "<project/>\n", "Dockerfile": "FROM scratch\n"},
            "expected_behavior": {"report_mode": "summary", "skill_loaded": True, "skill_id": "analyze-repo-for-kubernetes"},
            "forbidden_behavior": {"reads": [], "tools": []},
        }
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "summary"
            case_dir.mkdir()
            report = (ROOT / "tests/fixtures/reports/valid-summary.md").read_text(encoding="utf-8")
            (case_dir / "report.md").write_text(report, encoding="utf-8")
            (case_dir / "trace.json").write_text(json.dumps({
                "status": "PASS",
                "skill": {"loaded": True, "id": "analyze-repo-for-kubernetes"},
                "supporting_reads": [],
                "tool_calls": [],
                "permission_denials": [],
                "final_output": report,
            }), encoding="utf-8")
            result = evaluate_scenarios.validate_opencode_case(case, Path(tmp))

        self.assertTrue(result["passed"], result["errors"])

    def test_evaluator_accepts_help_without_repository_tools(self):
        case = {
            "id": "help",
            "repository_fixture": "tests/fixtures/repos/sample",
            "repository_snapshot": {"pom.xml": "<project/>\n", "Dockerfile": "FROM scratch\n"},
            "expected_behavior": {
                "required_output": ["/analyze-repo-for-kubernetes", "Detailed"],
                "forbidden_output": ["# Kubernetes 설계 입력 요약"],
                "forbidden_tools": ["read", "glob", "grep", "list", "bash"],
            },
            "forbidden_behavior": {"reads": [], "tools": []},
        }
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "help"
            case_dir.mkdir()
            (case_dir / "trace.json").write_text(json.dumps({
                "status": "PASS",
                "skill": {"loaded": False},
                "supporting_reads": [],
                "tool_calls": [],
                "permission_denials": [],
                "final_output": "/analyze-repo-for-kubernetes\nDetailed 분석을 요청할 수 있습니다.",
            }), encoding="utf-8")
            result = evaluate_scenarios.validate_opencode_case(case, Path(tmp))

        self.assertTrue(result["passed"], result["errors"])
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

    def test_command_preserves_help_as_a_command_argument(self):
        case = {"id": "help", "query": "--help", "repository_fixture": "tests/fixtures/repos/sample"}

        def runner(command, **kwargs):
            self.assertEqual(command[-2:], ["--", "--help"])
            return subprocess.CompletedProcess(command, 0, '{"type":"text","text":"ok"}\n', "")

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
        self.assertEqual(trace["status"], "PASS")

    def test_command_case_uses_the_installed_slash_command(self):
        case = {
            "id": "slash-command",
            "query": ".",
            "command": "analyze-repo-for-kubernetes",
            "repository_fixture": "tests/fixtures/repos/sample",
        }

        def runner(command, **kwargs):
            self.assertIn("--command", command)
            self.assertIn("analyze-repo-for-kubernetes", command)
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
        # A case reaches the custom command by naming it; `acceptance_type`
        # alone no longer implies one, so the natural-language cases keep
        # exercising the plain prompt entry.
        case = {
            "id": "command-link",
            "query": "query",
            "command": "analyze-repo-for-kubernetes",
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
        self.assertEqual(trace["status"], "PASS")
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
