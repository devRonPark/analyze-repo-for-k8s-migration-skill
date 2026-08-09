import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server


class SubmitRetryBudgetTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp")
        command_directory = Path(temporary.name) / "command"
        target = command_directory / "external-target"
        target.mkdir(parents=True)
        (target / "Dockerfile").write_text("FROM python:3.13\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
            cwd=target,
            check=True,
            capture_output=True,
        )
        return temporary, command_directory, target

    def started(self) -> tuple[tempfile.TemporaryDirectory[str], Server, Path]:
        temporary, command_directory, target = self.fixture()
        server = Server(command_directory=command_directory)
        server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
        return temporary, server, target

    @staticmethod
    def envelope(server: Server) -> dict:
        return {
            "analysis_id": server.session.analysis_id,
            "revision": server.session.revision,
            "transition_token": server.session.transition_token,
        }

    @staticmethod
    def payload(observation_ref: str) -> dict:
        return {
            "schema_version": 1,
            "stage": "discovery",
            "evidence": [{"alias": "container", "observation_ref": observation_ref}],
            "claims": [{"id": "claim-container", "status": "confirmed", "evidence_aliases": ["container"]}],
            "rule_applications": [],
            "signals": ["container-runtime"],
            "candidate_ids": ["candidate-web"],
            "decisions": ["decision-runtime"],
        }

    def foreign_observation_ref(self, server: Server, target: Path) -> str:
        # An observation issued under a stage other than the current one is a
        # cheap, repeatable way to trigger a genuine payload rejection
        # ("observation stage mismatch") without needing a fresh precision
        # call — and unlike most rejection codes it is retryable=True by
        # default, which is exactly the shape the retry budget needs to cap.
        return server.session.registry.issue_present(
            "execution", target / "Dockerfile", 1, 1, "1: FROM python:3.13"
        )["observation_ref"]

    def test_first_three_rejections_stay_retryable(self) -> None:
        temporary, server, target = self.started()
        with temporary:
            results = []
            for _ in range(3):
                ref = self.foreign_observation_ref(server, target)
                result, failed = server.tool_call(
                    "submit_discovery", {**self.envelope(server), "payload": self.payload(ref)}
                )
                results.append((result, failed))

        for result, failed in results:
            self.assertTrue(failed)
            self.assertEqual(result["code"], "observation_stage_mismatch")
            self.assertTrue(result["retryable"])

    def test_fourth_rejection_becomes_non_retryable_with_a_budget_note(self) -> None:
        temporary, server, target = self.started()
        with temporary:
            for _ in range(3):
                ref = self.foreign_observation_ref(server, target)
                server.tool_call("submit_discovery", {**self.envelope(server), "payload": self.payload(ref)})
            ref = self.foreign_observation_ref(server, target)
            fourth, fourth_failed = server.tool_call(
                "submit_discovery", {**self.envelope(server), "payload": self.payload(ref)}
            )
            fifth, fifth_failed = server.tool_call(
                "submit_discovery", {**self.envelope(server), "payload": self.payload(ref)}
            )

        self.assertTrue(fourth_failed)
        self.assertEqual(fourth["code"], "observation_stage_mismatch")
        self.assertFalse(fourth["retryable"])
        self.assertIn("retry budget", fourth["issues"][0])
        self.assertTrue(fifth_failed)
        self.assertFalse(fifth["retryable"])
        self.assertEqual(server.session.current_stage, "discovery")

    def test_envelope_errors_count_toward_the_same_retry_budget(self) -> None:
        # A live run against a real repository (2026-08-09) showed a
        # noncompliant model repeat a stale-envelope call unboundedly once it
        # got confused about stage state -- the exact loop shape this budget
        # exists to prevent, just on an envelope error instead of a payload
        # one. Envelope-class codes (stale_revision, stage_order, ...) now
        # count toward the same per-stage budget as payload rejections.
        temporary, server, target = self.started()
        with temporary:
            stale_envelope = {**self.envelope(server), "revision": 999}
            results = []
            for _ in range(5):
                ref = self.foreign_observation_ref(server, target)
                result, failed = server.tool_call(
                    "submit_discovery", {**stale_envelope, "payload": self.payload(ref)}
                )
                results.append((result, failed))

        for result, failed in results[:3]:
            self.assertTrue(failed)
            self.assertEqual(result["code"], "stale_revision")
        self.assertTrue(results[3][1])
        self.assertFalse(results[3][0]["retryable"])
        self.assertIn("retry budget", results[3][0]["issues"][0])
        self.assertTrue(results[4][1])
        self.assertIn("retry budget", results[4][0]["issues"][0])

    def test_finalize_analysis_shares_the_retry_budget_and_stops_looping(self) -> None:
        # Reproduces the live-run failure directly: submit_boundaries never
        # succeeded, so current_stage stayed "boundaries" while the model
        # called finalize_analysis repeatedly against a stage_order rejection
        # it never fixed. finalize_analysis was not covered by any budget
        # before this fix.
        temporary, server, _ = self.started()
        with temporary:
            results = [server.tool_call("finalize_analysis", self.envelope(server)) for _ in range(5)]

        for result, failed in results[:3]:
            self.assertTrue(failed)
            self.assertEqual(result["code"], "stage_order")
            self.assertNotIn("retry budget", result["issues"][0])
        for result, failed in results[3:]:
            self.assertTrue(failed)
            self.assertEqual(result["code"], "stage_order")
            self.assertFalse(result["retryable"])
            self.assertIn("retry budget", result["issues"][0])


if __name__ == "__main__":
    unittest.main()
