import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch


class MigrationAssistantFoundationTests(unittest.TestCase):
    def test_package_exposes_application_foundation_without_legacy_imports(self):
        from migration_assistant import __version__
        from migration_assistant.agent import AgentApplication
        from migration_assistant.service import ApplicationService

        self.assertEqual(__version__, "0.1.0")
        self.assertTrue(issubclass(AgentApplication, object))
        self.assertTrue(issubclass(ApplicationService, object))

    def test_settings_read_only_the_openai_compatible_environment_contract(self):
        from migration_assistant.config import Settings

        values = {
            "LLM_BASE_URL": "https://llm.example/v1",
            "LLM_API_KEY": "secret-value",
            "LLM_MODEL": "example-model",
            "LLM_TIMEOUT_SECONDS": "12.5",
            "LLM_MAX_TOKENS": "2048",
            "MIGRATION_ASSISTANT_PROVIDER": "ignored-provider",
        }

        with patch.dict(os.environ, values, clear=True):
            settings = Settings.from_environment()

        self.assertEqual(settings.llm_base_url, "https://llm.example/v1")
        self.assertEqual(settings.llm_api_key, "secret-value")
        self.assertEqual(settings.llm_model, "example-model")
        self.assertEqual(settings.llm_timeout_seconds, 12.5)
        self.assertEqual(settings.llm_max_tokens, 2048)
        self.assertNotIn("secret-value", repr(settings))

    def test_default_settings_are_provider_agnostic_and_demo_ready(self):
        from migration_assistant.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_environment()

        self.assertEqual(settings.llm_base_url, "https://api.upstage.ai/v1")
        self.assertEqual(settings.llm_model, "solar-pro3")
        self.assertEqual(settings.llm_timeout_seconds, 60.0)
        self.assertEqual(settings.llm_max_tokens, 4096)

    def test_new_application_boundary_contains_exactly_eight_agent_tools(self):
        from migration_assistant.agent import PUBLIC_AGENT_TOOL_NAMES

        self.assertEqual(
            PUBLIC_AGENT_TOOL_NAMES,
            (
                "inspect_target",
                "list_tree",
                "find_files",
                "search_text",
                "read_file",
                "read_file_lines",
                "inspect_git_metadata",
                "validate_analysis",
            ),
        )

    def test_schema_and_deterministic_output_boundaries_are_separate(self):
        from migration_assistant.guardrails import Guardrail
        from migration_assistant.renderer import ManifestRenderer
        from migration_assistant.schemas import AnalysisResult, KubernetesMigrationPlan
        from migration_assistant.validator import ManifestValidator

        self.assertIsNot(AnalysisResult, KubernetesMigrationPlan)
        self.assertTrue(isinstance(Guardrail, type))
        self.assertTrue(isinstance(ManifestRenderer, type))
        self.assertTrue(isinstance(ManifestValidator, type))

    def test_application_service_is_constructed_from_environment_settings(self):
        from migration_assistant.service import ApplicationService

        with patch.dict(os.environ, {"LLM_MODEL": "test-model"}, clear=True):
            service = ApplicationService.from_environment()

        self.assertEqual(service.settings.llm_model, "test-model")
        self.assertIs(service.agent.settings, service.settings)

    def test_module_entrypoint_reports_foundation_status_in_korean(self):
        from migration_assistant.__main__ import main

        output = StringIO()
        with redirect_stdout(output), patch.dict(os.environ, {}, clear=True):
            result = main()

        self.assertEqual(result, 0)
        self.assertIn("Kubernetes Migration Assistant", output.getvalue())

    def test_module_entrypoint_routes_cli_arguments_to_analysis_cli(self):
        result = subprocess.run(
            [sys.executable, "-m", "migration_assistant", "analyze", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local Git Repository", result.stdout)


if __name__ == "__main__":
    unittest.main()
