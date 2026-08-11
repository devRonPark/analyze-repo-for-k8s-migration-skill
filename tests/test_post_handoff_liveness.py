import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import run_opencode_acceptance as adapter


def _call(name, *, start, end, next_skill=None, completed_stage=None, status="accepted"):
    payload = {"status": status}
    if next_skill is not None:
        payload["next_skill"] = next_skill
        payload["completed_stage"] = completed_stage
    return {
        "name": f"analysis_{name}",
        "state": {
            "time": {"start": start, "end": end},
            "output": json.dumps(payload),
        },
    }


def _skill(name, *, start, end):
    return {
        "name": "skill",
        "state": {"input": {"name": name}, "time": {"start": start, "end": end}},
    }


class PostHandoffLivenessTests(unittest.TestCase):
    def test_sqlite_part_artifacts_expose_skill_calls_and_assistant_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "opencode.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE message (id TEXT, data TEXT, time_created INTEGER)")
                connection.execute("CREATE TABLE part (id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER)")
                connection.execute(
                    "INSERT INTO message VALUES (?, ?, ?)",
                    ("msg_1", json.dumps({"id": "msg_1", "role": "assistant"}), 100),
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?)",
                    (
                        "part_1",
                        json.dumps({"type": "tool", "name": "skill", "state": {"input": {"name": "analyze-k8s-execution"}}}),
                        110,
                        120,
                    ),
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?)",
                    ("part_2", json.dumps({"type": "text", "messageID": "msg_1", "text": "progress"}), 130, 130),
                )
                connection.commit()
            finally:
                connection.close()

            calls = adapter._static_tool_calls(database)
            text_parts = adapter._static_assistant_text_parts(database)

        self.assertEqual(calls[0]["name"], "skill")
        self.assertEqual(calls[0]["state"]["input"]["name"], "analyze-k8s-execution")
        self.assertEqual(text_parts, [{"kind": "assistant_text", "observed_at": 130}])

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
                "relation_to_first_stage_action": "before",
            },
        )
        self.assertEqual(transition["first_next_stage_action"]["name"], "read_evidence")
        self.assertTrue(transition["next_stage_submission"]["accepted"])
        self.assertEqual(transition["classification"], "stage_progressed")

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
