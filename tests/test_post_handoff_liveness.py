import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import run_opencode_acceptance as adapter


def _call(
    name,
    *,
    start,
    end,
    next_skill=None,
    completed_stage=None,
    status="accepted",
    message_id=None,
    session_id=None,
):
    payload = {"status": status}
    if next_skill is not None:
        payload["next_skill"] = next_skill
        payload["completed_stage"] = completed_stage
    call = {
        "name": f"analysis_{name}",
        "state": {
            "time": {"start": start, "end": end},
            "output": json.dumps(payload),
        },
    }
    if message_id is not None:
        call["message_id"] = message_id
    if session_id is not None:
        call["session_id"] = session_id
    return call


def _skill(name, *, start, end, message_id=None, session_id=None):
    call = {
        "name": "skill",
        "state": {"input": {"name": name}, "time": {"start": start, "end": end}},
    }
    if message_id is not None:
        call["message_id"] = message_id
    if session_id is not None:
        call["session_id"] = session_id
    return call


def _assistant(message_id, *, created_at, terminal_state, session_id="session-1", part_types=(), **fields):
    return {
        "message_id": message_id,
        "session_id": session_id,
        "created_at": created_at,
        "terminal_state": terminal_state,
        "part_types": list(part_types),
        **fields,
    }


class PostHandoffLivenessTests(unittest.TestCase):
    def test_sqlite_part_artifacts_expose_skill_calls_and_assistant_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "opencode.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER)")
                connection.execute("CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER)")
                connection.execute(
                    "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
                    ("msg_1", "session_1", json.dumps({"id": "msg_1", "role": "assistant", "time": {"created": 100, "completed": 140}, "finish": "tool-calls"}), 100, 140),
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "part_1",
                        "msg_1",
                        "session_1",
                        json.dumps({"type": "tool", "tool": "skill", "state": {"input": {"name": "analyze-k8s-execution"}}}),
                        110,
                        120,
                    ),
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                    ("part_2", "msg_1", "session_1", json.dumps({"type": "text", "text": "progress"}), 130, 130),
                )
                connection.commit()
            finally:
                connection.close()

            calls = adapter._static_tool_calls(database)
            text_parts = adapter._static_assistant_text_parts(database)
            messages = adapter._static_assistant_messages(database)

        self.assertEqual(calls[0]["name"], "skill")
        self.assertEqual(calls[0]["state"]["input"]["name"], "analyze-k8s-execution")
        self.assertEqual(
            text_parts,
            [{"kind": "assistant_text", "observed_at": 130, "message_id": "msg_1", "session_id": "session_1"}],
        )
        self.assertEqual(
            messages,
            [{"message_id": "msg_1", "session_id": "session_1", "created_at": 100, "completed_at": 140, "finish_reason": "tool-calls", "terminal_state": "completed", "part_types": ["text", "tool"]}],
        )

    def test_normal_progression_records_handoff_skill_action_and_submission(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=170),
                _call("read_evidence", start=200, end=210, status="completed"),
                _call("submit_execution", start=240, end=270, completed_stage="execution", next_skill="analyze-k8s-relationships"),
            ],
            [],
            terminal_reason=None,
        )

        transition = transitions[0]
        self.assertEqual(transition["completed_stage"], "discovery")
        self.assertEqual(transition["next_skill"], "analyze-k8s-execution")
        self.assertEqual(
            transition["skill_load"],
            {
                "status": "observed",
                "observed_at": 150,
                "completed_at": 170,
                "content_bytes": None,
                "relation_to_first_stage_action": "before",
            },
        )
        self.assertEqual(transition["first_next_stage_action"]["name"], "read_evidence")
        self.assertTrue(transition["next_stage_submission"]["accepted"])
        self.assertEqual(transition["classification"], "stage_progressed")

    def test_sqlite_message_lifecycle_extracts_completion_error_and_abort_safely(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "opencode.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER)")
                records = [
                    ("completed", {"id": "completed", "role": "assistant", "time": {"created": 100, "completed": 120}, "finish": "stop"}),
                    ("errored", {"id": "errored", "role": "assistant", "time": {"created": 130, "completed": 150}, "error": {"name": "APIError", "data": {"message": "token=must-not-be-retained"}}}),
                    ("aborted", {"id": "aborted", "role": "assistant", "time": {"created": 160, "completed": 170}, "error": {"name": "MessageAbortedError"}}),
                ]
                connection.executemany(
                    "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
                    [(identifier, "session_1", json.dumps(data), data["time"]["created"], data["time"]["completed"]) for identifier, data in records],
                )
                connection.commit()
            finally:
                connection.close()

            messages = {item["message_id"]: item for item in adapter._static_assistant_messages(database)}

        self.assertEqual(messages["completed"]["terminal_state"], "completed")
        self.assertEqual(messages["errored"]["terminal_state"], "errored")
        self.assertEqual(messages["errored"]["error_category"], "APIError")
        self.assertNotIn("error_message", messages["errored"])
        self.assertEqual(messages["aborted"]["terminal_state"], "aborted")

    def test_timeout_without_observable_action_does_not_claim_skill_load_failure(self):
        transitions = adapter.trace_stage_transitions(
            [_call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution")],
            [],
            terminal_reason="OpenCode PTY did not produce a complete final Markdown report before timeout",
        )

        transition = transitions[0]
        self.assertEqual(transition["skill_load"]["status"], "unavailable")
        self.assertEqual(transition["classification"], "timeout_before_observable_action")

    def test_observed_skill_without_analysis_action_is_classified_narrowly(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=170),
            ],
            [],
            terminal_reason="OpenCode PTY did not produce a complete final Markdown report before timeout",
        )

        transition = transitions[0]
        self.assertEqual(transition["skill_load"]["status"], "observed")
        self.assertIsNone(transition["first_next_stage_action"])
        self.assertEqual(transition["classification"], "skill_loaded_no_stage_action")

    def test_assistant_text_without_an_action_has_no_ordering_claim(self):
        transitions = adapter.trace_stage_transitions(
            [_call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution")],
            [{"kind": "assistant_text", "observed_at": 150}],
            terminal_reason="OpenCode PTY did not produce a complete final Markdown report before timeout",
        )

        transition = transitions[0]
        self.assertEqual(
            transition["assistant_text_relation_to_next_stage_action"],
            "action_not_observed",
        )
        self.assertEqual(transition["first_post_handoff_event"]["kind"], "assistant_text")
        self.assertEqual(transition["classification"], "assistant_text_no_stage_action")

    def test_assistant_text_without_timestamp_has_unknown_relation_to_action(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                {"kind": "assistant_text"},
                _call("read_evidence", start=200, end=210, status="completed"),
            ],
            [],
            terminal_reason=None,
        )

        self.assertEqual(
            transitions[0]["assistant_text_relation_to_next_stage_action"],
            "order_unknown",
        )

    def test_skill_loaded_after_first_action_keeps_after_relation(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _call("read_evidence", start=150, end=160, status="completed"),
                _skill("analyze-k8s-execution", start=200, end=210),
            ],
            [],
            terminal_reason=None,
        )

        self.assertEqual(transitions[0]["skill_load"]["relation_to_first_stage_action"], "after")

    def test_skill_and_action_without_timestamps_have_unknown_relation(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                {"name": "skill", "state": {"input": {"name": "analyze-k8s-execution"}}},
                {"name": "analysis_read_evidence", "state": {"output": json.dumps({"status": "completed"})}},
            ],
            [],
            terminal_reason=None,
        )

        self.assertEqual(transitions[0]["skill_load"]["relation_to_first_stage_action"], "order_unknown")

    def test_post_skill_completed_turn_with_action_preserves_normal_progression(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-turn", session_id="session-1"),
                _call("read_evidence", start=200, end=210, status="completed", message_id="post-skill-turn", session_id="session-1"),
                _call("submit_execution", start=240, end=250, completed_stage="execution", next_skill="analyze-k8s-relationships", message_id="post-skill-turn", session_id="session-1"),
            ],
            [],
            terminal_reason=None,
            assistant_messages=[
                _assistant("post-skill-turn", created_at=180, terminal_state="completed", part_types=("tool", "step-start", "step-finish"), completed_at=260, finish_reason="tool-calls"),
            ],
        )

        self.assertEqual(transitions[0]["classification"], "stage_progressed")
        self.assertEqual(transitions[0]["post_skill_turn"]["status"], "completed")
        self.assertEqual(transitions[0]["post_skill_turn"]["part_observations"]["tool"], "observed")

    def test_stage_comparison_projects_only_content_sizes_and_proven_timing(self):
        handoff = _call(
            "submit_discovery",
            start=100,
            end=120,
            completed_stage="discovery",
            next_skill="analyze-k8s-execution",
        )
        handoff["state"]["output"] = json.dumps(
            {
                "status": "accepted",
                "completed_stage": "discovery",
                "next_skill": "analyze-k8s-execution",
                "stage_input": {"mode": "summary", "candidate_ids": ["web"]},
            }
        )
        skill = _skill("analyze-k8s-execution", start=150, end=170)
        skill["state"]["output"] = "skill content"

        transitions = adapter.trace_stage_transitions(
            [handoff, skill, _call("submit_execution", start=200, end=220)],
            [],
            terminal_reason=None,
        )

        transition = transitions[0]
        self.assertEqual(transition["skill_load"]["completed_at"], 170)
        self.assertEqual(transition["skill_load"]["content_bytes"], len("skill content".encode("utf-8")))
        self.assertEqual(transition["stage_input_serialized_bytes"], len(b'{"candidate_ids":["web"],"mode":"summary"}'))
        self.assertEqual(transition["skill_completion_to_first_stage_action_ms"], 30)

    def test_active_post_skill_turn_at_timeout_requires_persisted_nonterminal_message(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-turn", session_id="session-1"),
            ],
            [],
            terminal_reason="OpenCode PTY did not produce a complete final Markdown report before timeout",
            assistant_messages=[_assistant("active-turn", created_at=180, terminal_state="active")],
        )

        self.assertEqual(transitions[0]["classification"], "model_turn_active_at_timeout")
        self.assertEqual(transitions[0]["post_skill_turn"]["status"], "active_at_timeout")

    def test_completed_post_skill_turn_without_action_is_distinct(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-turn", session_id="session-1"),
            ],
            [],
            terminal_reason=None,
            assistant_messages=[_assistant("completed-turn", created_at=180, terminal_state="completed", completed_at=220, finish_reason="stop")],
        )

        self.assertEqual(transitions[0]["classification"], "model_turn_completed_no_stage_action")

    def test_explicit_error_and_abort_remain_distinct(self):
        base_calls = [
            _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
            _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-turn", session_id="session-1"),
        ]
        errored = adapter.trace_stage_transitions(
            base_calls,
            [],
            terminal_reason=None,
            assistant_messages=[_assistant("error-turn", created_at=180, terminal_state="errored", error_category="APIError")],
        )
        aborted = adapter.trace_stage_transitions(
            base_calls,
            [],
            terminal_reason=None,
            assistant_messages=[_assistant("abort-turn", created_at=180, terminal_state="aborted", error_category="MessageAbortedError")],
        )

        self.assertEqual(errored[0]["classification"], "model_turn_errored_before_stage_action")
        self.assertEqual(errored[0]["post_skill_turn"]["error_category"], "APIError")
        self.assertEqual(aborted[0]["classification"], "model_turn_aborted_before_stage_action")
        self.assertTrue(aborted[0]["post_skill_turn"]["abort_observed"])

    def test_reasoning_and_text_parts_are_observations_not_negative_claims(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-turn", session_id="session-1"),
            ],
            [],
            terminal_reason=None,
            assistant_messages=[_assistant("observed-parts", created_at=180, terminal_state="completed", part_types=("reasoning", "text"))],
        )

        observations = transitions[0]["post_skill_turn"]["part_observations"]
        self.assertEqual(observations["reasoning"], "observed")
        self.assertEqual(observations["text"], "observed")
        self.assertEqual(observations["tool"], "not_observed")

    def test_missing_lifecycle_data_is_unavailable_not_a_timeout_claim(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-turn", session_id="session-1"),
            ],
            [],
            terminal_reason="OpenCode PTY did not produce a complete final Markdown report before timeout",
            assistant_messages=[],
        )

        self.assertEqual(transitions[0]["classification"], "post_skill_turn_lifecycle_unavailable")

    def test_lifecycle_evidence_is_bounded_to_its_own_handoff(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=150, end=160, message_id="skill-1", session_id="session-1"),
                _call("submit_execution", start=240, end=250, completed_stage="execution", next_skill="analyze-k8s-relationships", message_id="turn-1", session_id="session-1"),
                _skill("analyze-k8s-relationships", start=270, end=280, message_id="skill-2", session_id="session-1"),
            ],
            [],
            terminal_reason=None,
            assistant_messages=[
                _assistant("turn-1", created_at=180, terminal_state="completed"),
                _assistant("turn-2", created_at=300, terminal_state="completed"),
            ],
        )

        self.assertEqual(transitions[0]["post_skill_turn"]["message_id"], "turn-1")
        self.assertEqual(transitions[1]["post_skill_turn"]["message_id"], "turn-2")

    def test_multi_stage_handoffs_have_independent_records(self):
        transitions = adapter.trace_stage_transitions(
            [
                _call("submit_discovery", start=100, end=120, completed_stage="discovery", next_skill="analyze-k8s-execution"),
                _skill("analyze-k8s-execution", start=140, end=150),
                _call("submit_execution", start=180, end=200, completed_stage="execution", next_skill="analyze-k8s-relationships"),
                _skill("analyze-k8s-relationships", start=220, end=230),
                _call("submit_relationships", start=250, end=270, completed_stage="relationships", next_skill="analyze-k8s-boundaries"),
            ],
            [],
            terminal_reason=None,
        )

        self.assertEqual([item["completed_stage"] for item in transitions], ["discovery", "execution", "relationships"])
        self.assertEqual([item["classification"] for item in transitions[:2]], ["stage_progressed", "stage_progressed"])
        self.assertFalse(transitions[2]["next_stage_submission"]["observed"])

    def test_old_trace_without_liveness_fields_remains_readable(self):
        trace = {"tool_calls": [], "turns": []}

        self.assertEqual(trace.get("stage_transitions", []), [])
        self.assertEqual(adapter.summarize_stage_timeline(trace.get("turns", [])), {})


if __name__ == "__main__":
    unittest.main()
