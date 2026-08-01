from __future__ import annotations

import unittest

from migration_assistant.agent import PUBLIC_AGENT_TOOL_NAMES
from migration_assistant.live_planner import LiveRepositoryPlanner


class FakeAdapter:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def complete(self, messages, *, tools=None, response_format=None):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "response_format": response_format,
            }
        )
        return next(self.responses)


class LivePlannerTests(unittest.TestCase):
    def test_planner_exposes_exact_repository_tools_and_continues_after_tool_result(self):
        adapter = FakeAdapter(
            [
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "inspect_target", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": '{"stop": true}',
                            }
                        }
                    ]
                },
            ]
        )
        planner = LiveRepositoryPlanner(adapter)

        action = planner.next_action(None)
        self.assertEqual(action, {"tool": "inspect_target", "args": {}})
        self.assertEqual(
            [tool["function"]["name"] for tool in adapter.calls[0]["tools"]],
            list(PUBLIC_AGENT_TOOL_NAMES),
        )

        stop = planner.next_action({"repository_relative": ".", "read_only": True})
        self.assertEqual(stop, {"stop": True})
        follow_up = adapter.calls[1]["messages"]
        self.assertEqual(follow_up[-2]["role"], "assistant")
        self.assertEqual(follow_up[-2]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(follow_up[-1]["role"], "tool")
        self.assertEqual(follow_up[-1]["tool_call_id"], "call-1")
        self.assertIn("read_only", follow_up[-1]["content"])
        self.assertIsNone(adapter.calls[1]["response_format"])

    def test_planner_rejects_unknown_tool_call(self):
        adapter = FakeAdapter(
            [{"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "shell", "arguments": "{}"}}]}}]}]
        )
        planner = LiveRepositoryPlanner(adapter)

        with self.assertRaises(ValueError):
            planner.next_action(None)


if __name__ == "__main__":
    unittest.main()
