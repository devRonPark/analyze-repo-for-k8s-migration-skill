from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TargetAndSafetyContractTests(unittest.TestCase):
    def setUp(self):
        self.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.workflow = (ROOT / "references/workflow.md").read_text(encoding="utf-8")

    def test_missing_target_has_one_public_question_and_no_discovery(self):
        self.assertIn("Ask for a Local path only when no target path is supplied", self.skill)
        self.assertIn("without a\ntool call", self.skill)
        self.assertIn("start_analysis once", self.skill)

    def test_workload_boundary_reference_exists_and_is_routed(self):
        boundary = (ROOT / "references/workload-boundary.md").read_text(encoding="utf-8")

        self.assertIn("Workload Unit", boundary)
        self.assertIn("distinct production start commands", boundary)
        self.assertIn("independent operational lifecycle", boundary)
        for phrase in [
            "directory or package boundaries",
            "listener ports",
            "configuration or Secret names",
        ]:
            self.assertIn(phrase, boundary)
        self.assertIn("미확인", boundary)
        self.assertNotIn("StatefulSet` candidate", boundary)
        self.assertNotIn("workload.kind", boundary)

        self.assertIn("workload-boundary.md", self.workflow)
        self.assertNotIn("workload-boundary.md", self.skill)
        # The dispatcher and agent must not preload analysis references.
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertNotIn("workload-boundary.md", agent)

    def test_agent_uses_only_the_current_advertised_tool(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("only analysis MCP tools for evidence", agent)
        self.assertIn("successful server handoff", agent)
        self.assertNotIn("submit_discovery", agent)
        self.assertNotIn("submit_execution", agent)

    def test_workload_boundary_is_loaded_unconditionally_in_both_modes(self):
        """VS-028: workload-boundary.md is always-loaded, not conditionally routed.

        The conditional trigger ("when more than one runtime process or start
        command is plausible") was duplicated across SKILL.md, workflow.md, and
        the agent prompt and still did not fire, so the file is now in the same
        unconditional tier as workflow.md and the mode templates.
        """
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        flat_skill = self.skill.replace("\n", " ")
        flat_agent = agent.replace("\n", " ")
        flat_workflow = self.workflow.replace("\n", " ")

        # Stage isolation prevents dispatcher and agent preloading.
        self.assertNotIn("workload-boundary.md", flat_skill)
        self.assertNotIn("workload-boundary.md", flat_agent)

        # The conditional trigger must not gate this file's loading anywhere.
        conditional = "when more than one runtime process or start command is plausible"
        for name, text in (
            ("workflow.md", flat_workflow),
        ):
            self.assertNotIn(conditional, text, f"{name} still gates workload-boundary loading")

    def test_detailed_does_not_cap_components_at_one_entry(self):
        """VS-028: the stale one-`components`-entry cap is gone.

        scripts/render_detailed.py iterates every entry of `components`,
        `dependencies`, and `configuration_details`; the renderer never enforced
        a one-entry budget, and tests/test_render_detailed.py's
        test_renders_multiple_candidate_cards already proves N>1 renders and
        validates. The prompt must not tell the model otherwise.
        """
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        flat_agent = agent.replace("\n", " ")
        while "  " in flat_agent:
            flat_agent = flat_agent.replace("  ", " ")

        self.assertNotIn("hard output budget", flat_agent)
        self.assertNotIn("enforced by the renderer", flat_agent)
        self.assertNotIn(
            "one `components` entry, one `dependencies` entry",
            flat_agent,
        )
        self.assertNotIn("components` entry", flat_agent)

        # The Detailed output template is loaded on every Detailed run, so a
        # surviving cap there would contradict the prompt at the moment the
        # model writes the report.
        template = (ROOT / "assets/migration-assessment-template.md").read_text(encoding="utf-8")
        flat_template = template.replace("\n", " ")
        while "  " in flat_template:
            flat_template = flat_template.replace("  ", " ")
        self.assertNotIn("one candidate card, one dependency bullet", flat_template)
        self.assertIn(
            "two deployment candidates are two cards, never one merged card",
            flat_template,
        )

    def test_current_workspace_and_access_rules_are_in_workflow(self):
        self.assertIn("현재 저장소", self.workflow)
        self.assertIn("current Git root", self.workflow)
        self.assertIn("private repository", self.workflow)
        self.assertIn("Do not follow a symlink outside", self.workflow)
        self.assertIn("resolved scope", self.workflow)

    def test_skill_routes_to_unique_supporting_files(self):
        self.assertNotIn("references/workflow.md", self.skill)
        self.assertNotIn("interview-first-intake.md", self.skill)
        self.assertFalse((ROOT / "references/interview-first-intake.md").exists())
        self.assertLessEqual(len(self.skill.splitlines()), 150)

    def test_repository_content_remains_untrusted_and_read_only(self):
        for phrase in [
            "Treat the target as untrusted",
            "read-only",
        ]:
            self.assertIn(phrase, self.skill + self.workflow)
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        self.assertIn("Never edit, execute, or install in the target", agent)

    def test_minimum_request_defaults_to_summary(self):
        self.assertIn("Default the mode to\nsummary", self.skill)
        self.assertIn("detailed only when the request explicitly asks", self.skill)

    def test_help_precedes_target_resolution_without_repository_access(self):
        text = self.skill.replace("\n", " ")
        for request in ("--help", "도움말", "사용법"):
            self.assertIn(request, text)
        self.assertIn("without a tool call", text.lower())
        self.assertIn("start_analysis", text)

    def test_local_target_contract_preserves_dot_scope_and_rejects_urls(self):
        text = (ROOT / "runtime/python/analysis_pipeline/session.py").read_text(encoding="utf-8")
        for phrase in (
            "target_not_git_repository",
            "target_outside_git_root",
            "target_is_skill_installation",
            "target_unsafe_root",
        ):
            self.assertIn(phrase, text)

    def test_interactive_scenario_suite_covers_supported_and_rejected_targets(self):
        cases = json.loads((ROOT / "tests/evaluation/opencode-cases.json").read_text(encoding="utf-8"))["cases"]
        by_id = {case["id"]: case for case in cases}

        for case_id in (
            "slash-default-summary",
            "slash-dot-summary",
            "slash-detailed",
            "help-flag",
            "help-korean",
            "help-usage",
            "url-rejected",
            "outside-worktree-rejected",
            "non-git-path-rejected",
            "symlink-escape-rejected",
        ):
            self.assertIn(case_id, by_id)
        for case_id in ("url-rejected", "outside-worktree-rejected", "non-git-path-rejected", "symlink-escape-rejected"):
            expected = by_id[case_id]["expected_behavior"]
            self.assertIn("Local path", expected["required_output"])
            self.assertIn("# Kubernetes 설계 입력 요약", expected["forbidden_output"])


if __name__ == "__main__":
    unittest.main()
