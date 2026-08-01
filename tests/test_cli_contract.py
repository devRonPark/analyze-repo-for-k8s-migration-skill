from __future__ import annotations

import unittest
from unittest.mock import patch

from migration_assistant import cli
from migration_assistant.analysis import ModelConfigurationError, PydanticDependencyError


class CliContractTests(unittest.TestCase):
    def test_max_iterations_is_configurable_and_defaults_to_shared_budget(self):
        args = cli.build_parser().parse_args(["analyze", "repo"])
        self.assertEqual(args.max_iterations, 50)

    def test_failure_categories_have_distinct_exit_codes(self):
        cases = (
            (ModelConfigurationError("configuration"), 3),
            (PydanticDependencyError("dependency"), 4),
        )
        for error, expected in cases:
            with self.subTest(error=type(error).__name__), patch.object(cli, "analyze", side_effect=error):
                self.assertEqual(cli.main(["analyze", "repo"]), expected)


if __name__ == "__main__":
    unittest.main()
