from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts import run_opencode_acceptance as adapter
from scripts import evaluate_scenarios


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
        self.assertRegex(agent, r"(?m)^steps:\s+32$")
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

    def test_summary_prompt_requires_renderer_input_contract(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("return exactly one JSON object", agent)
        self.assertIn("do not emit Markdown, fences, progress text, or commentary", agent)
        self.assertIn("For renderer input JSON", agent)
        self.assertIn("minimum_inputs", agent)
        self.assertIn("verdict_reason", agent)

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

    def test_summary_extraction_rejects_prose_around_json(self):
        payload = (ROOT / "tests/fixtures/reports/valid-summary.json").read_text(encoding="utf-8")

        self.assertIsNone(adapter.extract_report({"final_output": f"progress\n{payload}"}))
        self.assertIsNone(adapter.extract_report({"final_output": f"```json\n{payload}\n```"}))

    def test_finalizes_summary_before_exposing_it(self):
        payload = json.loads((ROOT / "tests/fixtures/reports/valid-summary.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            report = adapter.finalize_summary(
                payload,
                Path(tmp),
                ROOT / "tests/fixtures/repos/sample",
            )

        self.assertIn("Validation: passed", report)
        self.assertTrue(report.startswith("# Kubernetes 설계 입력 요약\n"))

    def test_evaluator_uses_finalized_summary_markdown(self):
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
            report = (ROOT / "tests/fixtures/reports/valid-summary.md").read_text(encoding="utf-8").replace(
                "Validation: pending", "Validation: passed"
            )
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
