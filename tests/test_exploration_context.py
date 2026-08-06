"""Lock the CoverageSnapshot -> ContextProjection contract (Task 2A).

The projection tells the model which migration questions still need an
observation and how important they are -- nothing else. It must never
carry a resolved value, a path, or force a specific next Tool call.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.exploration_context import (
    CoverageSnapshot,
    build_coverage_snapshot,
    project_next_observations,
)
from migration_assistant.exploration_ledger import ExplorationLedger
from migration_assistant.exploration_policy import DEFAULT_MIGRATION_POLICY
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget


class ExplorationContextTests(unittest.TestCase):
    def test_context_projection_lists_unresolved_questions_without_values(self):
        snapshot = CoverageSnapshot(unresolved_question_ids=("production_startup", "writable_state_path"))
        projection = project_next_observations(snapshot)
        self.assertEqual(projection[0]["question_id"], "production_startup")
        self.assertNotIn("container_port", repr(projection))
        self.assertNotIn("8080", repr(projection))
        self.assertNotIn("next_tool", repr(projection))

    def test_projection_never_includes_a_resolved_value_field(self):
        snapshot = CoverageSnapshot(unresolved_question_ids=DEFAULT_MIGRATION_POLICY.question_ids())
        for entry in project_next_observations(snapshot):
            self.assertEqual(set(entry), {"question_id", "importance", "signal_rule_ids"})

    def test_projection_orders_required_questions_before_optional(self):
        snapshot = CoverageSnapshot(unresolved_question_ids=("writable_state_path", "production_startup"))
        projection = project_next_observations(snapshot)
        importances = [entry["importance"] for entry in projection]
        self.assertEqual(importances, sorted(importances, key=lambda value: {"required": 0, "conditional": 1, "optional": 2}[value]))

    def test_projection_carries_signal_rule_ids_not_full_rule_objects(self):
        snapshot = CoverageSnapshot(unresolved_question_ids=("production_startup",))
        projection = project_next_observations(snapshot)
        self.assertTrue(projection[0]["signal_rule_ids"])
        for rule_id in projection[0]["signal_rule_ids"]:
            self.assertIsInstance(rule_id, str)

    def test_projection_skips_unknown_question_ids_instead_of_erroring(self):
        snapshot = CoverageSnapshot(unresolved_question_ids=("no_such_question",))
        self.assertEqual(project_next_observations(snapshot), [])

    def test_build_coverage_snapshot_reports_only_unobserved_questions(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        snapshot = build_coverage_snapshot(ledger)
        self.assertNotIn("production_startup", snapshot.unresolved_question_ids)
        self.assertIn("receiving_port", snapshot.unresolved_question_ids)

    def test_build_coverage_snapshot_is_secret_safe(self):
        ledger = ExplorationLedger()
        ledger.record_observation("runtime_config_and_secret_names", "read_file_lines", "config/application.yml", 1, 1)
        snapshot = build_coverage_snapshot(ledger)
        self.assertNotIn("application.yml", repr(snapshot))


class AdkToolsetContextProjectionWiringTests(unittest.TestCase):
    """Task 2A Step 2: the projection must reach the model on the very next
    Tool response -- not just at recovery time."""

    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "Dockerfile").write_text('FROM python:3.11\nENTRYPOINT ["python", "app.py"]\n', encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "Dockerfile"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--quiet", "-m", "fixture"],
            check=True,
        )
        return repo

    def test_successful_tool_response_carries_a_context_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            result = toolset.search_text("ENTRYPOINT", ".")

            projection = result["meta"]["context_projection"]
            self.assertTrue(projection)
            self.assertNotIn("next_tool", repr(projection))
            self.assertNotIn("Dockerfile", repr(projection))

    def test_touching_a_file_shrinks_the_next_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            before = set(DEFAULT_MIGRATION_POLICY.question_ids())
            first = toolset.search_text("ENTRYPOINT", ".")
            after_first = {entry["question_id"] for entry in first["meta"]["context_projection"]}
            # Touching the Dockerfile covers several questions at once; the
            # projection must shrink, never invent that nothing was covered.
            self.assertLess(after_first, before)

            second = toolset.inspect_git_metadata()
            after_second = {entry["question_id"] for entry in second["meta"]["context_projection"]}
            self.assertLessEqual(after_second, after_first)


if __name__ == "__main__":
    unittest.main()
