from __future__ import annotations

import unittest
from pathlib import Path

from migration_assistant.analysis import DEPLOYMENT_CANDIDATE, AnalysisResult


def field(value: object, *, evidence_ids: list[str] | None = None) -> dict[str, object]:
    # An explicit empty list must survive; `or` would silently restore the default.
    return {
        "status": "confirmed",
        "value": value,
        "evidence_ids": ["e1"] if evidence_ids is None else evidence_ids,
    }


def unresolved(scope: str = "src") -> dict[str, object]:
    return {
        "status": "unresolved",
        "absence_scope": scope,
        "absence_pattern": "EXPOSE",
        "result": "없음",
    }


EVIDENCE = [
    {
        "id": "e1",
        "status": "confirmed",
        "path": "app.py",
        "line_start": 1,
        "line_end": 1,
        "claim": "기동 명령",
        "text": "uvicorn app.main:app",
    }
]
FINDINGS = [{"id": "f1", "status": "confirmed", "claim": "기동 명령", "evidence_ids": ["e1"]}]


def result(components: list[dict[str, object]] | None, status: str = "complete") -> AnalysisResult:
    payload: dict[str, object] = {
        "status": status,
        "summary": "분석 결과",
        "evidence": EVIDENCE,
        "findings": FINDINGS,
    }
    if components is not None:
        payload["components"] = components
    return AnalysisResult.model_validate(payload)


class FieldValueContractTests(unittest.TestCase):
    def test_positive_field_requires_value_and_evidence(self):
        with self.assertRaisesRegex(ValueError, "Evidence"):
            result([{"name": field("backend", evidence_ids=[]), "classification": field(DEPLOYMENT_CANDIDATE)}])
        with self.assertRaisesRegex(ValueError, "value"):
            result([{"name": field(None), "classification": field(DEPLOYMENT_CANDIDATE)}])

    def test_unresolved_field_requires_scope_pattern_and_result(self):
        with self.assertRaisesRegex(ValueError, "absence"):
            result([
                {
                    "name": field("backend"),
                    "classification": field(DEPLOYMENT_CANDIDATE),
                    "container_image": {"reference": {"status": "unresolved"}},
                }
            ])

    def test_field_evidence_ids_must_reference_existing_evidence(self):
        with self.assertRaisesRegex(ValueError, "Evidence"):
            result([
                {
                    "name": field("backend", evidence_ids=["missing"]),
                    "classification": field(DEPLOYMENT_CANDIDATE),
                }
            ])

    def test_unknown_evidence_status_is_rejected(self):
        with self.assertRaises(ValueError):
            result([
                {
                    "name": {"status": "present", "value": "backend", "evidence_ids": ["e1"]},
                    "classification": field(DEPLOYMENT_CANDIDATE),
                }
            ])


class ComponentContractTests(unittest.TestCase):
    def test_component_requires_name_and_classification(self):
        with self.assertRaises(ValueError):
            result([{"classification": field(DEPLOYMENT_CANDIDATE)}])
        with self.assertRaises(ValueError):
            result([{"name": field("backend")}])

    def test_classification_must_be_one_of_the_four_buckets(self):
        with self.assertRaisesRegex(ValueError, "classification"):
            result([{"name": field("backend"), "classification": field("배포하고 싶은 것")}])

    def test_port_entry_requires_container_port(self):
        with self.assertRaises(ValueError):
            result([
                {
                    "name": field("backend"),
                    "classification": field(DEPLOYMENT_CANDIDATE),
                    "ports": [{"purpose": field("http")}],
                }
            ])

    def test_full_minimal_component_is_accepted(self):
        analysis = result([
            {
                "name": field("backend"),
                "classification": field(DEPLOYMENT_CANDIDATE),
                "commands": {"production_startup": field("uvicorn app.main:app")},
                "ports": [{"container_port": field(8009), "purpose": field("http")}],
                "container_image": {"reference": unresolved()},
            }
        ])

        component = analysis.components[0]
        self.assertEqual(component.name.value, "backend")
        self.assertEqual(component.ports[0].container_port.value, 8009)
        self.assertEqual(component.container_image.reference.status, "unresolved")

    def test_components_stay_optional_until_the_complete_rule_is_enabled(self):
        # Step 1a introduces the type only. Enforcing it for complete is a
        # separate change so the existing fixtures are not rewritten twice.
        self.assertEqual(result(None).components, [])


class ComponentWireSchemaTests(unittest.TestCase):
    def wire_validate_analysis(self) -> dict[str, object]:
        from google.genai import types
        from google.adk.models.llm_request import LlmRequest

        from migration_assistant.adk_model import OpenAICompatibleAdkLlm
        from migration_assistant.adk_tools import AdkRepositoryToolset, DuplicateTracker, ValidationLedger
        from migration_assistant.repository_tools import RepositoryTools
        from migration_assistant.target import SafetyBudget

        repository = RepositoryTools(Path.cwd(), budget=SafetyBudget())
        toolset = AdkRepositoryToolset(repository, ValidationLedger(), DuplicateTracker())
        declarations = [tool._get_declaration() for tool in toolset.functions()]
        request = LlmRequest(config=types.GenerateContentConfig(tools=[types.Tool(function_declarations=declarations)]))
        wire = OpenAICompatibleAdkLlm._tools(request)
        return next(item for item in wire if item["function"]["name"] == "validate_analysis")

    def test_components_is_exposed_but_not_required(self):
        parameters = self.wire_validate_analysis()["function"]["parameters"]

        self.assertIn("components", parameters["properties"])
        # Keeping it optional is what stops this change from rewriting every
        # existing complete fixture at once.
        self.assertNotIn("components", parameters["required"])

    def test_component_items_expose_typed_fields(self):
        parameters = self.wire_validate_analysis()["function"]["parameters"]
        reference = parameters["properties"]["components"]["items"]["$ref"]
        component = parameters["$defs"][reference.removeprefix("#/$defs/")]

        self.assertIn("classification", component["properties"])
        self.assertIn("commands", component["properties"])
        self.assertIn("ports", component["properties"])
        self.assertEqual(set(component["required"]), {"name", "classification"})


if __name__ == "__main__":
    unittest.main()
