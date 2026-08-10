import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import run_opencode_acceptance as adapter


def _tool_call(name: str, *, start=None, end=None, input_payload=None, output_payload=None, status="accepted"):
    state: dict = {}
    if start is not None and end is not None:
        state["time"] = {"start": start, "end": end}
    if input_payload is not None:
        state["input"] = input_payload
    if output_payload is not None:
        state["output"] = json.dumps({"structuredContent": {"status": status, **output_payload}})
    elif status is not None:
        state["output"] = json.dumps({"structuredContent": {"status": status}})
    return {"name": f"analysis_{name}", "state": state}


def _real_shaped_call(name: str, *, start, end, accepted: bool):
    """Mirror a live-captured PTY/SQLite tool part, not the structuredContent
    convention `_tool_call` above uses.

    Confirmed against a real `jpetstore-6-summary`/local-sglang capture:
    `state.status` is OpenCode's own tool-execution lifecycle field
    ("completed"/"error"), always present and unrelated to the pipeline's own
    accepted/rejected outcome, which instead lives at the top level of the
    JSON body under `state.output` (never under `structuredContent`) --
    absent entirely on a rejection, which carries `state.error` instead.
    """
    state: dict = {"time": {"start": start, "end": end}}
    if accepted:
        state["status"] = "completed"
        state["output"] = json.dumps({"status": "accepted", "next_skill": "irrelevant"})
    else:
        state["status"] = "error"
        state["error"] = json.dumps({"code": "some rejection", "issues": ["x"], "retryable": False})
    return {"name": f"analysis_{name}", "state": state}


class StageTimingInstrumentationTests(unittest.TestCase):
    def test_turn_record_has_stage_start_completion_and_elapsed(self):
        calls = [
            _tool_call("start_analysis", start=1_000, end=1_100),
            _tool_call("submit_discovery", start=1_500, end=1_650),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        second = turns[1]
        self.assertEqual(second["stage"], "discovery")
        self.assertEqual(second["started_at"], 1_100)
        self.assertEqual(second["completed_at"], 1_500)
        self.assertEqual(second["elapsed_ms"], 400)

    def test_first_turn_has_no_prior_anchor_and_is_reported_as_none_not_zero(self):
        calls = [_tool_call("start_analysis", start=1_000, end=1_100)]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertIsNone(turns[0]["started_at"])
        self.assertIsNone(turns[0]["elapsed_ms"])

    def test_elapsed_ms_is_never_negative_even_with_out_of_order_timestamps(self):
        calls = [
            _tool_call("start_analysis", start=2_000, end=2_500),
            _tool_call("submit_discovery", start=2_100, end=2_200),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[1]["elapsed_ms"], 0)
        self.assertGreaterEqual(turns[1]["elapsed_ms"], 0)

    def test_known_stage_tools_attribute_to_their_documented_stage(self):
        expected = {
            "start_analysis": "dispatcher/start",
            "submit_discovery": "discovery",
            "submit_execution": "execution",
            "submit_relationships": "relationships",
            "submit_boundaries": "boundaries",
            "submit_contracts": "contracts",
            "finalize_analysis": "finalize",
        }
        for tool, stage in expected.items():
            with self.subTest(tool=tool):
                turns = adapter.attribute_stage_timeline([_tool_call(tool, start=0, end=10)])
                self.assertEqual(turns[0]["stage"], stage)

    def test_precision_tool_inherits_the_most_recently_entered_stage(self):
        calls = [
            _tool_call("start_analysis", start=0, end=100),
            _tool_call("submit_discovery", start=200, end=300),
            _tool_call("read_evidence", start=400, end=450),
            _tool_call("submit_execution", start=500, end=600),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[2]["stage"], "execution")

    def test_precision_tool_before_any_accepted_stage_call_is_unknown(self):
        calls = [_tool_call("read_evidence", start=0, end=10)]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[0]["stage"], "unknown")

    def test_stage_advances_on_the_real_top_level_status_shape_not_just_structuredContent(self):
        calls = [
            _real_shaped_call("start_analysis", start=0, end=100, accepted=True),
            _real_shaped_call("submit_discovery", start=200, end=300, accepted=True),
            _real_shaped_call("read_evidence", start=400, end=450, accepted=True),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[2]["stage"], "execution")

    def test_rejected_real_shaped_submit_does_not_advance_the_stage(self):
        calls = [
            _real_shaped_call("start_analysis", start=0, end=100, accepted=True),
            _real_shaped_call("submit_discovery", start=200, end=300, accepted=True),
            _real_shaped_call("submit_execution", start=400, end=500, accepted=False),
            _real_shaped_call("read_evidence", start=600, end=650, accepted=True),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[3]["stage"], "execution")

    def test_rejected_submit_does_not_advance_the_stage_for_later_precision_calls(self):
        calls = [
            _tool_call("start_analysis", start=0, end=100),
            _tool_call("submit_discovery", start=200, end=300, status="accepted"),
            _tool_call("submit_execution", start=400, end=500, status="rejected"),
            _tool_call("read_evidence", start=600, end=650),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[2]["stage"], "execution")
        self.assertEqual(turns[3]["stage"], "execution")

    def test_tool_execution_time_is_stored_separately_from_model_turn_time(self):
        calls = [
            _tool_call("start_analysis", start=0, end=50),
            _tool_call("submit_discovery", start=3_000, end=3_220),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertEqual(turns[1]["tool_calls"][0]["elapsed_ms"], 220)
        self.assertEqual(turns[1]["elapsed_ms"], 2_950)
        self.assertNotEqual(turns[1]["tool_calls"][0]["elapsed_ms"], turns[1]["elapsed_ms"])

    def test_missing_timestamps_yield_none_elapsed_but_size_metrics_still_populate(self):
        call = {
            "name": "analysis_submit_discovery",
            "state": {
                "input": {"candidate_ids": ["jpetstore"]},
                "output": json.dumps({"structuredContent": {"status": "accepted"}}),
            },
        }

        turns = adapter.attribute_stage_timeline([call])

        self.assertIsNone(turns[0]["elapsed_ms"])
        self.assertIsNone(turns[0]["tool_calls"][0]["elapsed_ms"])
        self.assertIsNotNone(turns[0]["output_chars"])
        self.assertNotIn("tokens", turns[0])
        self.assertNotIn("input_tokens", turns[0])
        self.assertNotIn("output_tokens", turns[0])

    def test_input_chars_reflects_the_previous_turns_tool_response(self):
        calls = [
            _tool_call("start_analysis", start=0, end=10, output_payload={"survey": "x" * 50}),
            _tool_call("submit_discovery", start=20, end=30, input_payload={"candidate_ids": ["a"]}),
        ]

        turns = adapter.attribute_stage_timeline(calls)

        self.assertGreater(turns[1]["input_chars"], 0)
        self.assertIsNone(turns[0]["input_chars"])

    def test_row_level_timestamps_are_used_when_state_time_is_absent(self):
        call = {
            "name": "analysis_submit_discovery",
            "state": {"output": json.dumps({"structuredContent": {"status": "accepted"}})},
            "row_time_created": 5_000,
            "row_time_updated": 5_180,
        }

        turns = adapter.attribute_stage_timeline([call])

        self.assertEqual(turns[0]["tool_calls"][0]["elapsed_ms"], 180)

    def test_static_tool_calls_preserves_row_level_timestamps_alongside_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "opencode.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TABLE part (id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER)"
                )
                payload = json.dumps(
                    {
                        "type": "tool",
                        "name": "analysis_submit_discovery",
                        "state": {"output": json.dumps({"structuredContent": {"status": "accepted"}})},
                    }
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?)",
                    ("part_1", payload, 1_700_000_000_000, 1_700_000_000_500),
                )
                connection.commit()
            finally:
                connection.close()

            calls = adapter._static_tool_calls(database)

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["row_time_created"], 1_700_000_000_000)
            self.assertEqual(calls[0]["row_time_updated"], 1_700_000_000_500)

    def test_summarize_stage_timeline_aggregates_totals_mean_and_max_per_stage(self):
        turns = [
            {"stage": "discovery", "elapsed_ms": 100, "tool_calls": [{"tool": "submit_discovery", "elapsed_ms": 20}]},
            {"stage": "discovery", "elapsed_ms": 300, "tool_calls": [{"tool": "read_evidence", "elapsed_ms": 10}]},
            {"stage": "execution", "elapsed_ms": 200, "tool_calls": [{"tool": "submit_execution", "elapsed_ms": 15}]},
        ]

        summary = adapter.summarize_stage_timeline(turns)

        self.assertEqual(summary["discovery"]["turn_count"], 2)
        self.assertEqual(summary["discovery"]["model_turn_ms_total"], 400)
        self.assertEqual(summary["discovery"]["model_turn_ms_mean"], 200)
        self.assertEqual(summary["discovery"]["model_turn_ms_max"], 300)
        self.assertEqual(summary["discovery"]["tool_ms_total"], 30)
        self.assertEqual(summary["execution"]["turn_count"], 1)

    def test_summarize_stage_timeline_reports_none_rather_than_zero_when_no_timestamps_exist(self):
        turns = [{"stage": "boundaries", "elapsed_ms": None, "tool_calls": [{"tool": "submit_boundaries", "elapsed_ms": None}]}]

        summary = adapter.summarize_stage_timeline(turns)

        self.assertEqual(summary["boundaries"]["turn_count"], 1)
        self.assertIsNone(summary["boundaries"]["model_turn_ms_total"])
        self.assertIsNone(summary["boundaries"]["tool_ms_total"])

    def test_summarize_stage_timeline_tolerates_an_empty_turns_list_without_raising(self):
        self.assertEqual(adapter.summarize_stage_timeline([]), {})

    def test_pre_instrumentation_trace_without_a_turns_key_summarizes_cleanly(self):
        trace_path = (
            Path(__file__).resolve().parents[1]
            / "tests/evaluation/vs030-followup-e2e/attempt-2/jpetstore-6-summary/trace.json"
        )
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        self.assertNotIn("turns", trace)

        summary = adapter.summarize_stage_timeline(trace.get("turns", []))

        self.assertEqual(summary, {})


if __name__ == "__main__":
    unittest.main()
