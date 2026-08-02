from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
from migration_assistant.repository_tools import RepositoryTools
from migration_assistant.target import SafetyBudget
from migration_assistant.tool_protocol import ToolErrorCode, ToolIssue, error_envelope


class RejectedInputCaptureTests(unittest.TestCase):
    def make_tool(self, name: str):
        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())
        return toolset, next(tool for tool in toolset.functions() if tool.name == name)

    def test_rejected_argument_value_is_recorded_for_measurement(self):
        _, read_lines = self.make_tool("read_file_lines")

        issue = read_lines.argument_issue(
            {"relative": "pom.xml", "line_start": 60, "line_end": 92}
        )

        self.assertEqual(issue.code, ToolErrorCode.INVALID_ARGUMENTS)
        self.assertEqual(issue.field_path, "$.line_end")
        # Knowing it was line_end is not enough to tell whether the model asked
        # for a 33 line span or an out-of-file line.
        self.assertEqual(issue.rejected_input, "92")

    def test_string_input_is_recorded_by_shape_only(self):
        _, search = self.make_tool("search_text")
        secret = "sk-live-0123456789abcdef"

        issue = search.argument_issue({"pattern": "ok", "relative": ".", "token": secret})

        self.assertIsNotNone(issue)
        # Redaction keys off surrounding names, so a bare value would survive it.
        self.assertNotIn(secret, issue.rejected_input or "")
        self.assertEqual(issue.rejected_input, f"str(len={len(secret)})")

    def test_rejected_input_never_reaches_the_model_envelope(self):
        issue = ToolIssue(
            code=ToolErrorCode.INVALID_ARGUMENTS,
            category="validation",
            message="범위 오류",
            field_path="$.line_end",
            retryable=True,
            rejected_input="92",
        )

        envelope = error_envelope(issue, allowed_next_actions=("read_file_lines",))

        # The envelope is the model-facing contract; measurement must not widen it.
        self.assertNotIn("rejected_input", envelope["error"])
        self.assertNotIn("92", json.dumps(envelope, ensure_ascii=False))

    def test_valid_arguments_produce_no_issue(self):
        _, read_lines = self.make_tool("read_file_lines")

        self.assertIsNone(
            read_lines.argument_issue({"relative": "pom.xml", "line_start": 1, "line_end": 2})
        )


if __name__ == "__main__":
    unittest.main()
