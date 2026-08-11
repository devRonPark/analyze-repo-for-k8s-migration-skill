"""D12 deterministic contract tests for the reversible host-owned seam."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path

from analysis_pipeline.host_continuation import HostContinuationError, load_host_continuation
from analysis_pipeline.mcp_server import Server


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "runtime" / "stage-skills"


class HostOwnedTransitionTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        command_directory = Path(temporary.name) / "command"
        target = command_directory / "external-target"
        target.mkdir(parents=True)
        (target / "Dockerfile").write_text("FROM python:3.13\nCMD [\"python\", \"app.py\"]\n", encoding="utf-8")
        (target / "app.py").write_text("print('ready')\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
            cwd=target,
            check=True,
            capture_output=True,
        )
        return temporary, command_directory, target

    @staticmethod
    def discovery_payload(observation_ref: str) -> dict[str, object]:
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

    def started(self, mode: str = "host_owned") -> tuple[tempfile.TemporaryDirectory[str], Server]:
        temporary, command_directory, _ = self.fixture()
        server = Server(
            command_directory=command_directory,
            transition_mode=mode,
            skill_root=SKILL_ROOT,
            host_activation_state_path=Path(temporary.name) / "host-activation.json",
        )
        return temporary, server

    def test_model_routed_default_handoff_is_unchanged(self) -> None:
        temporary, server = self.started("model_routed")
        with temporary:
            handoff, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})

        self.assertFalse(failed, handoff)
        self.assertEqual(handoff["next_skill"], "analyze-k8s-discovery")
        self.assertNotIn("host_continuation", handoff)

    def test_host_consumes_the_accepted_server_next_skill_exactly(self) -> None:
        temporary, server = self.started()
        with temporary:
            initial, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
            self.assertFalse(failed, initial)
            observation, failed = server.tool_call("read_evidence", {"path": "Dockerfile"})
            self.assertFalse(failed, observation)
            handoff, failed = server.tool_call(
                "submit_discovery", {"payload": self.discovery_payload(observation["observation_ref"])}
            )
            state = json.loads((Path(temporary.name) / "host-activation.json").read_text(encoding="utf-8"))

        self.assertFalse(failed, handoff)
        continuation = handoff["host_continuation"]
        self.assertEqual(handoff["next_skill"], "analyze-k8s-execution")
        self.assertEqual(continuation["requested_skill"], "analyze-k8s-execution")
        self.assertEqual(continuation["skill_load"], "completed")
        self.assertEqual(continuation["skill_content"], (SKILL_ROOT / "analyze-k8s-execution" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(state["transition_owner"], "host")
        self.assertEqual(state["next_skill"], handoff["next_skill"])
        self.assertEqual(state["analysis_id"], handoff["analysis_id"])
        self.assertEqual(state["revision"], handoff["revision"])
        self.assertEqual(state["transition_token"], handoff["transition_token"])

    def test_host_mode_without_a_guard_state_path_fails_closed(self) -> None:
        temporary, command_directory, _ = self.fixture()
        with temporary:
            server = Server(command_directory=command_directory, transition_mode="host_owned", skill_root=SKILL_ROOT)
            result, failed = server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})

        self.assertTrue(failed)
        self.assertEqual(result["code"], "host_continuation_failed")
        self.assertEqual(result["issues"], ["missing_host_activation_state"])

    def test_rejected_stage_does_not_host_transition_or_advance(self) -> None:
        temporary, server = self.started()
        with temporary:
            server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
            rejected, failed = server.tool_call("submit_discovery", {"payload": self.discovery_payload("not-issued")})

        self.assertTrue(failed)
        self.assertNotIn("host_continuation", rejected)
        self.assertEqual(server.session.current_stage, "discovery")

    def test_rejected_handoff_cannot_be_loaded_directly(self) -> None:
        with self.assertRaisesRegex(HostContinuationError, "handoff_not_accepted"):
            load_host_continuation(
                {"status": "rejected", "next_skill": "analyze-k8s-execution"},
                analysis_id="an_test", revision=1, transition_token="tr_test",
                expected_skill="analyze-k8s-execution", skill_root=SKILL_ROOT,
            )

    def test_unknown_and_missing_next_skill_fail_closed(self) -> None:
        common = {"status": "accepted", "analysis_id": "an_test", "revision": 1, "transition_token": "tr_test"}
        with self.assertRaisesRegex(HostContinuationError, "unknown_next_skill"):
            load_host_continuation(
                {**common, "next_skill": "not-a-skill"}, analysis_id="an_test", revision=1,
                transition_token="tr_test", expected_skill="not-a-skill", skill_root=SKILL_ROOT,
            )
        with self.assertRaisesRegex(HostContinuationError, "missing_next_skill"):
            load_host_continuation(
                common, analysis_id="an_test", revision=1, transition_token="tr_test",
                expected_skill="analyze-k8s-execution", skill_root=SKILL_ROOT,
            )

    def test_stale_transition_token_fails_closed(self) -> None:
        handoff = {"status": "accepted", "analysis_id": "an_test", "revision": 1, "transition_token": "tr_stale", "next_skill": "analyze-k8s-execution"}
        with self.assertRaisesRegex(HostContinuationError, "invalid_transition_token"):
            load_host_continuation(
                handoff, analysis_id="an_test", revision=1, transition_token="tr_current",
                expected_skill="analyze-k8s-execution", skill_root=SKILL_ROOT,
            )

    def test_multiple_handoffs_consume_only_each_server_issued_skill_in_order(self) -> None:
        skills = [
            ("analyze-k8s-discovery", "analyze-k8s-discovery"),
            ("analyze-k8s-execution", "analyze-k8s-execution"),
            ("analyze-k8s-relationships", "analyze-k8s-relationships"),
            ("analyze-k8s-boundaries", "analyze-k8s-boundaries"),
            ("analyze-k8s-contracts", "analyze-k8s-contracts"),
            ("analyze-k8s-finalize", "analyze-k8s-finalize"),
        ]
        consumed = []
        for revision, (issued, expected) in enumerate(skills):
            continuation = load_host_continuation(
                {"status": "accepted", "analysis_id": "an_test", "revision": revision, "transition_token": f"tr_{revision}", "next_skill": issued},
                analysis_id="an_test", revision=revision, transition_token=f"tr_{revision}", expected_skill=expected, skill_root=SKILL_ROOT,
            )
            consumed.append(continuation["requested_skill"])
        self.assertEqual(consumed, [issued for issued, _ in skills])

    def test_validation_failure_after_host_transition_is_unchanged(self) -> None:
        temporary, server = self.started()
        with temporary:
            server.tool_call("start_analysis", {"target_path": "external-target", "mode": "summary"})
            observation, _ = server.tool_call("read_evidence", {"path": "Dockerfile"})
            accepted, failed = server.tool_call("submit_discovery", {"payload": self.discovery_payload(observation["observation_ref"])})
            self.assertFalse(failed, accepted)
            rejected, failed = server.tool_call("submit_execution", {"payload": {}})

        self.assertTrue(failed)
        self.assertNotIn("host_continuation", rejected)
        self.assertEqual(server.session.current_stage, "execution")


if __name__ == "__main__":
    unittest.main()
