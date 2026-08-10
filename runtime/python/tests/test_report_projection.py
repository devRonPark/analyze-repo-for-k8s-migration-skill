"""Canonical report projection renders accepted values, never repository text."""
from __future__ import annotations

import unittest

from analysis_pipeline.report_projection import project_and_render, project_report_payload
from analysis_pipeline.state import PipelineState, create_state


class ReportProjectionTests(unittest.TestCase):
    def accepted_state(self, facts: list[dict], mode: str = "summary") -> PipelineState:
        state = create_state("projection-test")
        evidence = {
            f"ev-{index}": {
                "location": f"evidence-{index}.txt", "range": "1-1", "status": "confirmed",
            }
            for index in range(1, 30)
        }
        slot_ids = [
            "deployment_targets", "build_image_start", "reachable_port_or_path",
            "runtime_dependencies_state", "execution_conflicts", "credential_exposure", "minimum_design_inputs",
        ]
        if mode == "detailed":
            slot_ids.extend(("configuration_timing", "lifecycle_recovery", "observability", "deployment_evidence", "readiness_verdict"))
        claims = [
            {"id": f"slot-{slot}", "evidence_ids": [f"ev-{index + 1}"]}
            for index, slot in enumerate(slot_ids)
        ]
        slots = [
            {"id": claim["id"][5:], "status": "confirmed", "fact_refs": [], "claim_ids": [claim["id"]]}
            for claim in claims
        ]
        for index, fact in enumerate(facts, start=10):
            fact.setdefault("ref", f"semantic_fact_discovery_{index}")
            fact.setdefault("status", "confirmed")
            fact.setdefault("evidence_ids", [f"ev-{index}"])
        process = {
            "id": "process-web", "role": "web", "execution_pattern": "continuous",
            "semantic_fact_refs": [fact["ref"] for fact in facts if fact["kind"].startswith("runtime.")],
        }
        return PipelineState(
            binding=state.binding, revision=5, current_stage="contracts", state_hash="test",
            evidence=evidence,
            outputs={
                "discovery": {"semantic_facts": facts, "claims": []},
                "execution": {"runtime_processes": [process], "claims": []},
                "boundaries": {"workload_units": [{"id": "unit-web", "boundary_status": "confirmed", "boundary_claim_ids": ["unit-boundary"]}], "claims": [{"id": "unit-boundary", "evidence_ids": ["ev-29"]}]},
                "relationships": {"graph_edges": []},
                "contracts": {"report_slots": slots, "claims": claims},
            },
        )

    @staticmethod
    def fact(kind: str, value: object) -> dict:
        return {"kind": kind, "value": value}

    def test_projects_accepted_jpetstore_values_and_provenance(self) -> None:
        state = self.accepted_state([
            self.fact("application.name", "JPetStore"), self.fact("project.language", "Java"),
            self.fact("project.language_version", "17"), self.fact("project.framework", "Spring"),
            self.fact("build.tool", "Maven Wrapper"), self.fact("build.command", "./mvnw clean package"),
            self.fact("build.artifact_type", "WAR"), self.fact("runtime.server", "Tomcat 9"),
            self.fact("runtime.start_command", "./mvnw cargo:run -P tomcat9"),
            self.fact("runtime.listening_port", 8080), self.fact("runtime.context_path", "/jpetstore/"),
            self.fact("container.dockerfile", "Dockerfile"), self.fact("container.compose", "docker-compose.yaml"),
        ])

        for mode in ("summary", "detailed"):
            with self.subTest(mode=mode):
                report = project_and_render(self.accepted_state(list(state.outputs["discovery"]["semantic_facts"]), mode), mode, {"branch, tag 또는 commit": "test"})
                for value in ("JPetStore", "Java", "17", "Maven Wrapper", "./mvnw clean package", "WAR", "Tomcat 9", "8080", "/jpetstore/", "Dockerfile", "docker-compose.yaml", "web", "continuous", "unit-web"):
                    self.assertIn(value, report)
                self.assertIn("evidence-10.txt:1-1", report)

    def test_wrong_confirmed_kind_does_not_satisfy_language(self) -> None:
        payload = project_report_payload(
            self.accepted_state([self.fact("container.dockerfile", "Dockerfile")]), "summary", {}
        )

        self.assertEqual(payload["grounded_fields"]["Language"]["value"], "미확인")
        self.assertEqual(payload["grounded_fields"]["Language"]["status"], "unknown")
        self.assertEqual(
            payload["grounded_fields"]["Language"]["reference"],
            "검색(scope=accepted-semantic-facts, pattern=project.language, result=없음)",
        )

    def test_detailed_projection_keeps_existing_card_fields_when_semantic_facts_are_missing(self) -> None:
        from analysis_pipeline.report_projection import validate_markdown

        state = self.accepted_state([], mode="detailed")
        metadata = {"branch, tag 또는 commit": "test"}
        report = project_and_render(state, "detailed", metadata)

        self.assertEqual(validate_markdown(report, "detailed", metadata), [])
        self.assertIn("- 언어:", report)
        self.assertIn("검색(scope=accepted-semantic-facts, pattern=project.language, result=없음)", report)

    def test_unknown_semantic_fact_is_rendered_explicitly(self) -> None:
        state = self.accepted_state([{
            "kind": "runtime.context_path", "value": None, "status": "unknown", "ref": "semantic_fact_discovery_unknown",
            "evidence_ids": ["ev-10"],
        }])
        state.evidence["ev-10"] = {
            "location": "unused", "range": "1-1", "status": "unknown",
            "absence": {"scope": "runtime", "glob": "*.xml", "pattern": "context-path"},
        }

        report = project_and_render(state, "summary", {"branch, tag 또는 commit": "test"})

        self.assertIn("Context Path: 미확인 (상태: 미확인; 근거: 검색(scope=runtime, pattern=context-path, result=없음))", report)

    def test_conflicted_fact_renders_all_accepted_references(self) -> None:
        state = self.accepted_state([{
            "kind": "build.tool", "value": "Maven", "status": "conflicted", "ref": "semantic_fact_discovery_conflict",
            "evidence_ids": ["ev-10", "ev-11"],
        }])

        payload = project_report_payload(state, "summary", {})

        record = payload["grounded_fields"]["Build Tool"]
        self.assertEqual(record["status"], "conflicted")
        self.assertEqual(record["reference"], "evidence-10.txt:1-1, evidence-11.txt:1-1")


if __name__ == "__main__":
    unittest.main()
