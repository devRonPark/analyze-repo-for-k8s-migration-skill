import os
import unittest
from unittest.mock import patch

from migration_assistant.adapter import (
    AdapterConfigurationError,
    AdapterRequestError,
    ChatCompletionRequest,
    OpenAICompatibleAdapter,
)
from migration_assistant.config import Settings


class ModelCompatibilityTests(unittest.TestCase):
    def test_endpoint_and_model_changes_keep_the_same_request_contract(self):
        first = OpenAICompatibleAdapter(
            Settings(
                llm_base_url="https://provider-one.example/v1",
                llm_api_key="key-one",
                llm_model="model-one",
                llm_timeout_seconds=12.5,
                llm_max_tokens=321,
            )
        ).build_request([{"role": "user", "content": "hello"}])
        second = OpenAICompatibleAdapter(
            Settings(
                llm_base_url="http://provider-two.example/openai/",
                llm_api_key="key-two",
                llm_model="model-two",
                llm_timeout_seconds=7.0,
                llm_max_tokens=654,
            )
        ).build_request([{"role": "user", "content": "hello"}])

        self.assertIsInstance(first, ChatCompletionRequest)
        self.assertIs(type(first), type(second))
        self.assertEqual(first.url, "https://provider-one.example/v1/chat/completions")
        self.assertEqual(second.url, "http://provider-two.example/openai/chat/completions")
        self.assertEqual(first.payload["model"], "model-one")
        self.assertEqual(second.payload["model"], "model-two")
        self.assertEqual(first.payload["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(second.payload["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(first.payload["max_tokens"], 321)
        self.assertEqual(second.payload["max_tokens"], 654)

    def test_timeout_and_api_key_are_transport_metadata_and_secret_is_redacted(self):
        settings = Settings(
                llm_base_url="https://llm.example/v1",
                llm_api_key="super-secret-key",
                llm_model="compatible-model",
                llm_timeout_seconds=3.25,
                llm_max_tokens=99,
            )
        adapter = OpenAICompatibleAdapter(settings)
        request = adapter.build_request([{"role": "user", "content": "hello"}])

        self.assertEqual(request.timeout_seconds, 3.25)
        self.assertEqual(request.headers["Authorization"], "Bearer super-secret-key")
        self.assertEqual(request.headers["Content-Type"], "application/json")
        self.assertNotIn("super-secret-key", repr(settings))
        self.assertNotIn("super-secret-key", repr(adapter))
        self.assertNotIn("super-secret-key", repr(request))

    def test_missing_api_key_keeps_request_usable_without_auth_header(self):
        request = OpenAICompatibleAdapter(
            Settings(llm_base_url="https://llm.example/v1", llm_api_key=None)
        ).build_request([{"role": "user", "content": "hello"}])

        self.assertNotIn("Authorization", request.headers)

    def test_invalid_adapter_settings_are_rejected_at_the_boundary(self):
        with self.assertRaises(AdapterConfigurationError):
            OpenAICompatibleAdapter(Settings(llm_base_url="  "))
        with self.assertRaises(AdapterConfigurationError):
            OpenAICompatibleAdapter(Settings(llm_model="  "))
        with self.assertRaises(AdapterConfigurationError):
            OpenAICompatibleAdapter(Settings(llm_timeout_seconds=0))
        with self.assertRaises(AdapterConfigurationError):
            OpenAICompatibleAdapter(Settings(llm_max_tokens=0))

    def test_invalid_environment_limits_are_rejected_by_settings_boundary(self):
        with patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "not-a-number"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_environment()
        with patch.dict(os.environ, {"LLM_MAX_TOKENS": "0"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_environment()

        for non_finite_timeout in ("nan", "inf", "-inf"):
            with self.subTest(timeout=non_finite_timeout):
                with patch.dict(
                    os.environ,
                    {"LLM_TIMEOUT_SECONDS": non_finite_timeout},
                    clear=True,
                ):
                    with self.assertRaises(ValueError):
                        Settings.from_environment()

    def test_invalid_messages_are_rejected_without_transport_side_effects(self):
        adapter = OpenAICompatibleAdapter(Settings())

        with self.assertRaises(AdapterRequestError):
            adapter.build_request([])
        with self.assertRaises(AdapterRequestError):
            adapter.build_request([{"role": "user"}])
        with self.assertRaises(AdapterRequestError):
            adapter.build_request([{"role": "", "content": "hello"}])

    def test_assistant_tool_call_message_may_have_null_content(self):
        request = OpenAICompatibleAdapter(Settings()).build_request(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "inspect_target", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "{}"},
            ]
        )

        self.assertIsNone(request.payload["messages"][0]["content"])

    def test_tool_and_response_format_parameters_are_kept_in_the_generic_payload(self):
        adapter = OpenAICompatibleAdapter(Settings())

        request = adapter.build_request(
            [{"role": "user", "content": "inspect"}],
            tools=[{"type": "function", "function": {"name": "inspect_target"}}],
            response_format={"type": "json_object"},
        )

        self.assertEqual(request.payload["tools"], [{"type": "function", "function": {"name": "inspect_target"}}])
        self.assertEqual(request.payload["response_format"], {"type": "json_object"})

    def test_transport_error_does_not_expose_api_key(self):
        from migration_assistant.adapter import AdapterTransportError

        error = AdapterTransportError("request failed", secret="super-secret-key")

        self.assertNotIn("super-secret-key", str(error))


if __name__ == "__main__":
    unittest.main()
