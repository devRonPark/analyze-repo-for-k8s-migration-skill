from __future__ import annotations

import os
import shutil
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from devtools.env_file import EnvFileLoadResult, load_environment
from devtools.run_phase1_live_acceptance import _model_summary, build_parser, main


class EnvFileLoaderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / f".env-file-loader-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.environment: dict[str, str] = {}
        self.home = self.root / "home"
        (self.home / ".config" / "kubernetes-migration-assistant").mkdir(parents=True)

    def _load(self, *, explicit_path: Path | None = None):
        with patch.dict(os.environ, {}, clear=True), patch(
            "devtools.env_file.Path.home", return_value=self.home
        ):
            return load_environment(
                self.repository,
                explicit_path=explicit_path,
                environment=self.environment,
            )

    def test_existing_environment_variable_is_never_overwritten(self):
        env_file = self.repository / ".env"
        env_file.write_text("LLM_MODEL=from-file\nEMPTY=\n", encoding="utf-8")

        with patch.dict(os.environ, {"LLM_MODEL": "from-shell", "EMPTY": ""}, clear=True), patch(
            "devtools.env_file.Path.home", return_value=self.home
        ):
            result = load_environment(self.repository)
            self.assertEqual(os.environ["LLM_MODEL"], "from-shell")
            self.assertEqual(os.environ["EMPTY"], "")
        self.assertNotIn("LLM_MODEL", result.injected_keys)
        self.assertNotIn("EMPTY", result.injected_keys)

    def test_explicit_file_has_highest_file_priority(self):
        explicit = self.root / "explicit.env"
        configured = self.root / "configured.env"
        explicit.write_text("SELECTED=explicit\n", encoding="utf-8")
        configured.write_text("SELECTED=configured\n", encoding="utf-8")
        (self.repository / ".env").write_text("SELECTED=repository\n", encoding="utf-8")
        (self.home / ".config" / "kubernetes-migration-assistant" / "env").write_text(
            "SELECTED=home\n", encoding="utf-8"
        )

        self.environment["MIGRATION_ASSISTANT_ENV_FILE"] = str(configured)
        result = self._load(explicit_path=explicit)

        self.assertEqual(self.environment["SELECTED"], "explicit")
        self.assertEqual(result.selected_path, explicit)

    def test_environment_pointer_precedes_repository_and_home_files(self):
        configured = self.root / "configured.env"
        configured.write_text("SELECTED=configured\n", encoding="utf-8")
        (self.repository / ".env").write_text("SELECTED=repository\n", encoding="utf-8")
        (self.home / ".config" / "kubernetes-migration-assistant" / "env").write_text(
            "SELECTED=home\n", encoding="utf-8"
        )

        self.environment["MIGRATION_ASSISTANT_ENV_FILE"] = str(configured)
        result = self._load()

        self.assertEqual(self.environment["SELECTED"], "configured")
        self.assertEqual(result.selected_path, configured)

    def test_repository_file_precedes_home_file(self):
        (self.repository / ".env").write_text("SELECTED=repository\n", encoding="utf-8")
        home_file = self.home / ".config" / "kubernetes-migration-assistant" / "env"
        home_file.write_text("SELECTED=home\n", encoding="utf-8")

        result = self._load()

        self.assertEqual(self.environment["SELECTED"], "repository")
        self.assertEqual(result.selected_path, self.repository / ".env")

    def test_home_file_is_the_default_when_repository_override_is_missing(self):
        home_file = self.home / ".config" / "kubernetes-migration-assistant" / "env"
        home_file.write_text("SELECTED=home\n", encoding="utf-8")

        result = self._load()

        self.assertEqual(self.environment["SELECTED"], "home")
        self.assertEqual(result.selected_path, home_file)

    def test_missing_files_are_a_no_op(self):
        result = self._load()

        self.assertEqual(result.injected_keys, frozenset())
        self.assertIsNone(result.selected_path)
        self.assertEqual(self.environment, {})

    def test_parser_handles_bom_quotes_export_comments_blank_lines_and_newlines(self):
        env_file = self.repository / ".env"
        env_file.write_bytes(
            b"\xef\xbb\xbf# comment\r\n\r\n"
            b"PLAIN=plain value\r\n"
            b"DOUBLE=\"double value\"\n"
            b"SINGLE='single value'\r\n"
            b"export PREFIX=accepted\n"
            b"LITERAL=$(printf not-run)\n"
        )

        result = self._load()

        self.assertEqual(self.environment["PLAIN"], "plain value")
        self.assertEqual(self.environment["DOUBLE"], "double value")
        self.assertEqual(self.environment["SINGLE"], "single value")
        self.assertEqual(self.environment["PREFIX"], "accepted")
        self.assertEqual(self.environment["LITERAL"], "$(printf not-run)")
        self.assertEqual(result.injected_keys, frozenset({"PLAIN", "DOUBLE", "SINGLE", "PREFIX", "LITERAL"}))

    def test_invalid_lines_are_skipped_without_recording_line_contents(self):
        env_file = self.repository / ".env"
        secret = "invalid-line-secret-value"
        env_file.write_text(
            f"GOOD=kept\nBAD-KEY={secret}\n{secret}\nexport =still-invalid\nAFTER=also-kept\n",
            encoding="utf-8",
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = self._load()

        warning_text = " ".join(str(item.message) for item in caught)
        self.assertEqual(self.environment["GOOD"], "kept")
        self.assertEqual(self.environment["AFTER"], "also-kept")
        self.assertEqual(result.invalid_line_numbers, (2, 3, 4))
        self.assertNotIn(secret, repr(result))
        self.assertNotIn(secret, warning_text)
        self.assertIn("2", warning_text)

    def test_reading_failure_reports_only_the_path(self):
        unreadable = self.repository / ".env"
        unreadable.mkdir()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = self._load()

        warning_text = " ".join(str(item.message) for item in caught)
        self.assertEqual(result.selected_path, unreadable)
        self.assertIn(unreadable.name, warning_text)
        self.assertNotIn("[Errno", warning_text)

    def test_phase1_parser_accepts_env_file_option(self):
        path = self.root / "settings.env"

        args = build_parser().parse_args([
            "--repository", str(self.repository),
            "--output-parent", str(self.root / "outputs"),
            "--env-file", str(path),
        ])

        self.assertEqual(args.env_file, path)

    def test_phase1_entrypoint_loads_explicit_file_before_acceptance(self):
        path = self.root / "settings.env"
        load_result = EnvFileLoadResult(
            injected_keys=frozenset({"LLM_MODEL"}),
            selected_path=path,
        )
        with patch(
            "devtools.run_phase1_live_acceptance.load_environment",
            return_value=load_result,
        ) as load_environment_mock, patch(
            "devtools.run_phase1_live_acceptance.run_acceptance",
            return_value={"passed": True},
        ) as run_acceptance_mock, patch("builtins.print"):
            exit_code = main([
                "--repository", str(self.repository),
                "--output-parent", str(self.root / "outputs"),
                "--env-file", str(path),
            ])

        load_environment_mock.assert_called_once_with(self.repository, explicit_path=path)
        run_acceptance_mock.assert_called_once_with(
            self.repository,
            self.root / "outputs",
            runs=3,
            env_file=load_result,
        )
        self.assertEqual(exit_code, 0)


class EnvFileSummaryTests(unittest.TestCase):
    def test_model_summary_distinguishes_env_file_from_environment(self):
        env_file_path = Path("settings.env")
        load_result = EnvFileLoadResult(
            injected_keys=frozenset({"LLM_MODEL"}),
            selected_path=env_file_path,
        )
        with patch.dict(os.environ, {"LLM_MODEL": "from-file", "LLM_API_KEY": "secret"}, clear=True):
            summary = _model_summary(env_file=load_result)

        self.assertEqual(summary["llm_model_source"], "env_file")
        self.assertEqual(summary["environment_variables"]["LLM_MODEL"]["source"], "env_file")
        self.assertEqual(summary["environment_variables"]["LLM_API_KEY"]["source"], "environment")
        self.assertEqual(summary["env_file_path"], str(env_file_path))
        self.assertNotIn("secret", repr(summary))


if __name__ == "__main__":
    unittest.main()
