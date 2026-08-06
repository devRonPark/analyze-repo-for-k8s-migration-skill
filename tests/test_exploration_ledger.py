"""Lock the Secret-safe per-question exploration coverage ledger (Task 2).

The ledger records that a question was *touched* by an observation -- never
the observed value, path text, or excerpt itself. It is measurement only:
recording coverage must never promote a value into a grounded finding.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.exploration_ledger import ExplorationLedger
from migration_assistant.exploration_policy import DEFAULT_MIGRATION_POLICY, QuestionImportance
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget


class ExplorationLedgerTests(unittest.TestCase):
    def test_observed_question_is_not_reported_as_grounded_value(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 3)
        summary = ledger.summary()
        self.assertEqual(summary["questions"]["production_startup"]["status"], "observed")
        self.assertNotIn("value", repr(summary))

    def test_unobserved_question_is_absent_from_summary(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        self.assertNotIn("receiving_port", ledger.summary()["questions"])

    def test_observation_count_and_bounded_line_count_accumulate(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 3)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertEqual(summary["observation_count"], 2)
        self.assertEqual(summary["observed_line_count"], 4)

    def test_observed_line_count_is_bounded_per_observation(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "read_file", "Dockerfile", 1, 500)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertLessEqual(summary["observed_line_count"], 10)

    def test_positive_evidence_count_only_increments_when_flagged(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 1, positive=True)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertEqual(summary["positive_evidence_count"], 1)

    def test_tool_names_are_deduplicated(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 1, 1)
        ledger.record_observation("production_startup", "search_text", "Dockerfile", 2, 2)
        summary = ledger.summary()["questions"]["production_startup"]
        self.assertEqual(summary["tool_names"], ["search_text"])

    def test_ledger_never_retains_raw_path_or_excerpt(self):
        ledger = ExplorationLedger()
        ledger.record_observation("runtime_config_and_secret_names", "read_file_lines", "config/application.yml", 4, 4)
        rendered = repr(ledger.summary())
        self.assertNotIn("application.yml", rendered)

    def test_summary_covers_multiple_questions_independently(self):
        ledger = ExplorationLedger()
        ledger.record_observation("production_startup", "read_file_lines", "Dockerfile", 1, 1)
        ledger.record_observation("receiving_port", "search_text", "Dockerfile", 2, 2)
        summary = ledger.summary()["questions"]
        self.assertEqual(set(summary), {"production_startup", "receiving_port"})


class ExplorationLedgerAdkWiringTests(unittest.TestCase):
    """Task 2 Step 3: Tool result -> ExplorationLedger update, without a live model."""

    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        (repo / "Dockerfile").write_text('FROM python:3.11\nENTRYPOINT ["python", "app.py"]\n', encoding="utf-8")
        return repo

    def test_toolset_owns_an_exploration_ledger_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            self.assertIsInstance(toolset.exploration_ledger, ExplorationLedger)

    def test_search_text_hit_updates_exploration_coverage_for_matched_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("ENTRYPOINT", ".")

            coverage = toolset.exploration_ledger.summary()["questions"]
            self.assertIn("production_startup", coverage)
            self.assertEqual(coverage["production_startup"]["tool_names"], ["search_text"])

    def test_unrelated_observation_records_no_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "README.md").write_text("hello world\n", encoding="utf-8")
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("hello", ".")

            self.assertEqual(toolset.exploration_ledger.summary()["questions"], {})

    def test_exploration_coverage_never_leaks_the_observed_path_in_repr(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("ENTRYPOINT", ".")

            self.assertNotIn("Dockerfile", repr(toolset.exploration_ledger.summary()))

    def test_accepted_positive_evidence_increments_positive_evidence_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            toolset.inspect_target()

            response = toolset.validate_analysis(
                status="partial",
                summary="기동 명령을 확인했습니다.",
                evidence=[
                    {
                        "id": "e1",
                        "status": "confirmed",
                        "path": "Dockerfile",
                        "line_start": 2,
                        "line_end": 2,
                        "claim": "기동 명령",
                        "text": 'ENTRYPOINT ["python", "app.py"]',
                    }
                ],
                findings=[],
                iterations=1,
                errors=["writable path는 확인하지 못했습니다."],
            )

            self.assertTrue(response["ok"], response)
            coverage = toolset.exploration_ledger.summary()["questions"]
            self.assertIn("production_startup", coverage)
            self.assertEqual(coverage["production_startup"]["positive_evidence_count"], 1)

    def test_unresolved_evidence_never_counts_as_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            toolset.inspect_target()

            toolset.validate_analysis(
                status="partial",
                summary="확인하지 못했습니다.",
                evidence=[
                    {
                        "id": "e1",
                        "status": "unresolved",
                        "absence_scope": "Dockerfile*",
                        "absence_pattern": "VOLUME",
                        "result": "no match",
                    }
                ],
                findings=[],
                iterations=1,
                errors=["writable path는 확인하지 못했습니다."],
            )

            self.assertEqual(toolset.exploration_ledger.summary()["questions"], {})

    def test_conflicting_evidence_counts_as_conflicting_not_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())
            toolset.inspect_target()

            toolset.validate_analysis(
                status="partial",
                summary="상충하는 근거를 확인했습니다.",
                evidence=[
                    {
                        "id": "e1",
                        "status": "conflicting",
                        "path": "Dockerfile",
                        "line_start": 2,
                        "line_end": 2,
                        "claim": "기동 명령 상충",
                        "text": 'ENTRYPOINT ["python", "app.py"]',
                    }
                ],
                findings=[],
                iterations=1,
                errors=["기동 명령이 상충합니다."],
            )

            coverage = toolset.exploration_ledger.summary()["questions"]["production_startup"]
            self.assertEqual(coverage["conflicting_evidence_count"], 1)
            self.assertEqual(coverage["positive_evidence_count"], 0)

    def test_zero_hit_search_earns_a_genuine_unresolved_search_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("VOLUME", ".")

            coverage = toolset.exploration_ledger.summary()["questions"]["writable_state_path"]
            self.assertTrue(coverage["has_search_scope"])
            self.assertTrue(coverage["has_search_pattern"])
            self.assertEqual(coverage["positive_evidence_count"], 0)

    def test_zero_hit_search_never_retains_the_pattern_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            toolset = AdkRepositoryToolset(RepositoryTools(repo, budget=SafetyBudget()), ValidationLedger(), DuplicateTracker())

            toolset.search_text("VOLUME", ".")

            self.assertNotIn("VOLUME", repr(toolset.exploration_ledger.summary()))

    def test_injected_exploration_ledger_is_used_instead_of_a_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            ledger = ExplorationLedger()
            toolset = AdkRepositoryToolset(
                RepositoryTools(repo, budget=SafetyBudget()),
                ValidationLedger(),
                DuplicateTracker(),
                exploration_ledger=ledger,
            )

            toolset.search_text("ENTRYPOINT", ".")

            self.assertIs(toolset.exploration_ledger, ledger)
            self.assertIn("production_startup", ledger.summary()["questions"])


class StopDecisionTests(unittest.TestCase):
    """Task 5: mechanically apply the Task 0 stop-gate truth table."""

    def test_zero_evidence_blocks_submission(self):
        ledger = ExplorationLedger()
        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=0)
        self.assertFalse(decision.allowed)
        self.assertIn("no_evidence", decision.reason)
        self.assertEqual(decision.synthetic_values, {})

    def test_positive_value_without_evidence_blocks_submission(self):
        ledger = ExplorationLedger()
        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=1, positive_without_evidence=True)
        self.assertFalse(decision.allowed)
        self.assertIn("ungrounded_positive_value", decision.reason)

    def test_bounded_stop_is_allowed_but_bounded(self):
        ledger = ExplorationLedger()
        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=1, bounded_stop_triggered=True)
        self.assertTrue(decision.allowed)
        self.assertIn("bounded_stop", decision.reason)
        self.assertEqual(decision.allowed_status, ("failed", "partial"))

    def test_verbal_only_unresolved_claim_is_not_backed_without_a_ledger_record(self):
        """A model saying "I looked and found nothing" must not earn `unresolved`
        by itself -- the ledger must hold a recorded scope, pattern, and
        observation count for that specific question."""
        ledger = ExplorationLedger()
        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=1)
        self.assertTrue(decision.allowed)
        self.assertIn("insufficient_exploration", decision.reason)
        self.assertIn("workload_deployment_unit", decision.reason)
        self.assertEqual(decision.synthetic_values, {})

    def test_genuine_unresolved_is_granted_only_with_a_recorded_search_attempt(self):
        ledger = ExplorationLedger()
        for question in DEFAULT_MIGRATION_POLICY.questions:
            if question.importance == QuestionImportance.REQUIRED:
                ledger.record_observation(question.question_id, "search_text", "app.py", 1, 1, positive=True)
        ledger.record_search_attempt("writable_state_path", "search_text", ".", "VOLUME")

        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=5)

        self.assertTrue(decision.allowed)
        self.assertIn("unresolved", decision.reason)
        self.assertIn("writable_state_path", decision.reason)
        self.assertEqual(decision.synthetic_values, {})
        self.assertEqual(decision.allowed_status, ("complete", "partial"))

    def test_required_genuine_unresolved_limits_submission_to_partial(self):
        ledger = ExplorationLedger()
        for question in DEFAULT_MIGRATION_POLICY.questions:
            if question.importance == QuestionImportance.REQUIRED and question.question_id != "production_startup":
                ledger.record_observation(question.question_id, "search_text", "app.py", 1, 1, positive=True)
        ledger.record_search_attempt("production_startup", "search_text", ".", "ENTRYPOINT")

        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=4)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.allowed_status, ("partial",))
        self.assertIn("production_startup", decision.reason)

    def test_conflicting_evidence_blocks_auto_selection(self):
        ledger = ExplorationLedger()
        for question in DEFAULT_MIGRATION_POLICY.questions:
            if question.importance == QuestionImportance.REQUIRED:
                ledger.record_observation(question.question_id, "search_text", "app.py", 1, 1, positive=True)
        ledger.record_observation("receiving_port", "read_file_lines", "app.py", 2, 2, conflicting=True)

        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=6)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.allowed_status, ("partial",))
        self.assertIn("conflicting", decision.reason)
        self.assertIn("receiving_port", decision.reason)

    def test_conditional_question_is_not_applicable_when_precondition_never_observed(self):
        ledger = ExplorationLedger()
        question = DEFAULT_MIGRATION_POLICY.question("external_dependency")
        self.assertEqual(ledger.disposition(question), "not_applicable")

    def test_conditional_question_stands_on_its_own_once_precondition_is_observed(self):
        """Once the precondition question has actually been looked at, the
        ledger cannot know its resolved value (it never stores one), so the
        conditional question is no longer dismissed as not_applicable --
        it must earn its own disposition."""
        ledger = ExplorationLedger()
        ledger.record_observation("runtime_config_and_secret_names", "search_text", "app.py", 3, 3, positive=True)
        question = DEFAULT_MIGRATION_POLICY.question("external_dependency")
        self.assertEqual(ledger.disposition(question), "rejected")

    def test_stop_decision_never_returns_a_synthetic_value(self):
        ledger = ExplorationLedger()
        for question in DEFAULT_MIGRATION_POLICY.questions:
            ledger.record_observation(question.question_id, "search_text", "app.py", 1, 1, positive=True)
        decision = ledger.stop_decision(DEFAULT_MIGRATION_POLICY, total_evidence_count=7)
        self.assertEqual(decision.synthetic_values, {})

    def test_record_search_attempt_never_retains_the_pattern_text(self):
        ledger = ExplorationLedger()
        ledger.record_search_attempt("production_startup", "search_text", ".", "ENTRYPOINT")
        self.assertNotIn("ENTRYPOINT", repr(ledger.summary()))


if __name__ == "__main__":
    unittest.main()
