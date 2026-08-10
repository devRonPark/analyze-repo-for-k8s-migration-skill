"""Pinned, normal-flow acceptance coverage for the JPetStore demo target."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.report_projection import validate_markdown
from analysis_pipeline.runtime_contracts import resolve_runtime_contracts
from analysis_pipeline.stage_contracts import required_report_slot_ids
from analysis_pipeline.workload_grouping import derive_workload_unit_id


ROOT = Path(__file__).resolve().parents[3]
TARGET = Path(r"C:\temp\opencode-e2e-jpetstore-6")
PINNED_REVISION = "e1dd9a31d1cef68793cd0933ae06898e6fcfa807"


class JPetStoreDemoGoldenTests(unittest.TestCase):
    """Exercise accepted IR and final rendering; never inject report prose."""

    @classmethod
    def setUpClass(cls) -> None:
        if not TARGET.is_dir():
            raise unittest.SkipTest(f"pinned JPetStore fixture is unavailable: {TARGET}")
        revision = subprocess.run(
            ["git", "-C", str(TARGET), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        if revision != PINNED_REVISION:
            raise unittest.SkipTest(f"JPetStore fixture revision is not pinned: {revision}")

    def _survey_refs(self, handoff: dict) -> dict[str, str]:
        return {
            item["reference"].split(":", 1)[0]: item["observation_ref"]
            for item in handoff["stage_input"]["survey"]["observations"]
            if item["status"] == "confirmed"
        }

    def _submit(self, server: Server, tool: str, payload: dict) -> dict:
        result, failed = server.tool_call(tool, {"payload": payload})
        self.assertFalse(failed, result)
        return result

    def test_pinned_target_preserves_grounded_jpetstore_state_and_markdown(self) -> None:
        server = Server(command_directory=TARGET.parent)
        started, failed = server.tool_call("start_analysis", {"target_path": str(TARGET), "mode": "summary"})
        self.assertFalse(failed, started)
        self.assertEqual(server.session.binding["git_revision"], PINNED_REVISION)
        discovery_refs = self._survey_refs(started)

        discovery = self._submit(server, "submit_discovery", {
            "schema_version": 1, "stage": "discovery",
            "evidence": [
                {"alias": "pom", "observation_ref": discovery_refs["pom.xml"]},
                {"alias": "docker", "observation_ref": discovery_refs["Dockerfile"]},
                {"alias": "compose", "observation_ref": discovery_refs["docker-compose.yaml"]},
                {"alias": "webxml", "observation_ref": discovery_refs["src/main/webapp/WEB-INF/web.xml"]},
                {"alias": "spring", "observation_ref": discovery_refs["src/main/webapp/WEB-INF/applicationContext.xml"]},
            ],
            "claims": [
                {"id": "candidate", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"id": "conflict", "status": "conflicted", "evidence_aliases": ["pom", "docker"]},
                {"id": "credential", "status": "confirmed", "evidence_aliases": ["spring"]},
            ],
            "semantic_facts": [
                {"kind": "application.name", "value_type": "string", "value": "JPetStore 6", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"kind": "project.language", "value_type": "string", "value": "Java", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"kind": "project.language_version", "value_type": "string", "value": "17", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"kind": "project.framework", "value_type": "string", "value": "Spring", "status": "confirmed", "evidence_aliases": ["spring"]},
                {"kind": "project.framework", "value_type": "string", "value": "MyBatis", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"kind": "build.tool", "value_type": "string", "value": "Maven Wrapper", "status": "confirmed", "evidence_aliases": ["docker"]},
                {"kind": "build.artifact_type", "value_type": "string", "value": "WAR", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"kind": "build.command", "value_type": "string", "value": "./mvnw package", "status": "confirmed", "evidence_aliases": ["docker"]},
                {"kind": "runtime.server", "value_type": "string", "value": "Apache Tomcat", "status": "confirmed", "evidence_aliases": ["pom"]},
                {"kind": "runtime.start_command", "value_type": "string", "value": "./mvnw cargo:run -P tomcat90; active profile tomcat9", "status": "conflicted", "evidence_aliases": ["docker", "pom"]},
                {"kind": "runtime.listening_port", "value_type": "integer", "value": 8080, "status": "confirmed", "evidence_aliases": ["compose"]},
                {"kind": "runtime.context_path", "value_type": "string", "value": "/", "status": "confirmed", "evidence_aliases": ["webxml"]},
                {"kind": "container.dockerfile", "value_type": "string", "value": "Dockerfile", "status": "confirmed", "evidence_aliases": ["docker"]},
                {"kind": "container.compose", "value_type": "string", "value": "docker-compose.yaml", "status": "confirmed", "evidence_aliases": ["compose"]},
            ],
            "rule_applications": [], "signals": ["java-web-application"],
            "candidate_ids": ["candidate-jpetstore-web"], "decisions": ["decision-jpetstore-runtime"],
        })
        execution_evidence, failed = server.tool_call("read_evidence", {"path": "Dockerfile", "offset": 15, "limit": 8})
        self.assertFalse(failed, execution_evidence)
        semantic_facts = discovery["accepted_output"]["semantic_facts"]
        process_fact_refs = [fact["ref"] for fact in semantic_facts if fact["kind"].startswith("runtime.")]
        execution = self._submit(server, "submit_execution", {
            "schema_version": 1, "stage": "execution",
            "evidence": [{"alias": "runtime", "observation_ref": execution_evidence["observation_ref"]}],
            "claims": [
                {"id": "build", "status": "confirmed", "evidence_aliases": ["runtime"]},
                {"id": "port", "status": "confirmed", "evidence_aliases": ["runtime"]},
            ], "rule_applications": [],
            "discovery_fact_refs": discovery["accepted_output"]["discovery_fact_refs"],
            "runtime_processes": [{"candidate_ids": ["candidate-jpetstore-web"], "role": "web", "execution_pattern": "continuous", "semantic_fact_refs": process_fact_refs}],
        })
        process = execution["accepted_output"]["runtime_processes"][0]
        relationship_evidence, failed = server.tool_call("read_evidence", {"path": "src/main/webapp/WEB-INF/applicationContext.xml", "offset": 30, "limit": 6})
        self.assertFalse(failed, relationship_evidence)
        relationships = self._submit(server, "submit_relationships", {
            "schema_version": 1, "stage": "relationships",
            "evidence": [{"alias": "database", "observation_ref": relationship_evidence["observation_ref"]}],
            "claims": [{"id": "hsqldb", "status": "confirmed", "evidence_aliases": ["database"]}],
            "rule_applications": [], "discovery_fact_refs": discovery["accepted_output"]["discovery_fact_refs"],
            "execution_fact_refs": execution["accepted_output"]["execution_fact_refs"],
            "graph_edges": [{"id": "edge-hsqldb", "source_process_id": process["id"], "target_id": "hsqldb", "target_kind": "external_system", "dependency_type": "data_store", "mechanism": "jdbc", "endpoint_name": "embedded-hsqldb", "required_for_function": "unknown", "startup_use": "unknown", "status": "confirmed", "management_boundary": "repository_managed", "timing": "runtime", "execution_location": "server_process", "claim_ids": ["hsqldb"]}],
        })
        boundary_evidence, failed = server.tool_call("read_evidence", {"path": "docker-compose.yaml", "offset": 16, "limit": 10})
        self.assertFalse(failed, boundary_evidence)
        unit_id = "unit-jpetstore-web"
        boundaries = self._submit(server, "submit_boundaries", {
            "schema_version": 1, "stage": "boundaries",
            "evidence": [{"alias": "compose", "observation_ref": boundary_evidence["observation_ref"]}],
            "claims": [
                {"id": "boundary", "status": "confirmed", "evidence_aliases": ["compose"]},
                {"id": "lifecycle", "status": "confirmed", "evidence_aliases": ["compose"]},
                {"id": "state", "status": "confirmed", "evidence_aliases": ["compose"]},
                {"id": "deployable", "status": "confirmed", "evidence_aliases": ["compose"]},
            ], "rule_applications": [],
            "discovery_fact_refs": discovery["accepted_output"]["discovery_fact_refs"], "execution_fact_refs": execution["accepted_output"]["execution_fact_refs"], "relationship_fact_refs": relationships["accepted_output"]["relationship_fact_refs"],
            "workload_units": [{"id": unit_id, "process_ids": [process["id"]], "candidate_ids": ["candidate-jpetstore-web"], "start_definition_status": "confirmed", "independent_lifecycle_status": "confirmed", "boundary_status": "confirmed", "lifecycle": "continuous", "state_decision": "externalized", "deployable": True, "deployability_status": "confirmed", "boundary_claim_ids": ["boundary"], "lifecycle_claim_ids": ["lifecycle"], "state_claim_ids": ["state"], "deployability_claim_ids": ["deployable"]}], "candidate_exclusions": [],
        })
        contract_evidence, failed = server.tool_call("locate_evidence", {"glob": "*.properties", "path": ".", "pattern": "PRODUCTION_PERSISTENCE"})
        self.assertFalse(failed, contract_evidence)
        predecessor = boundaries["stage_input"]["fact_statuses"]
        slots = required_report_slot_ids("summary")
        fact_for = {
            "deployment_targets": "fact_discovery_candidate", "build_image_start": "fact_execution_build",
            "reachable_port_or_path": "fact_execution_port", "runtime_dependencies_state": "fact_relationships_hsqldb",
            "execution_conflicts": "fact_discovery_conflict", "credential_exposure": "fact_discovery_credential",
        }
        contracts = self._submit(server, "submit_contracts", {
            "schema_version": 1, "stage": "contracts",
            "evidence": [{"alias": "persistence", "observation_ref": contract_evidence["observation_ref"]}],
            "claims": [{"id": "minimum", "status": "unknown", "scope": "application data path", "blocked_decision": "durable production persistence", "evidence_aliases": ["persistence"]}],
            "rule_applications": [], "discovery_fact_refs": discovery["accepted_output"]["discovery_fact_refs"], "execution_fact_refs": execution["accepted_output"]["execution_fact_refs"], "relationship_fact_refs": relationships["accepted_output"]["relationship_fact_refs"], "boundaries_fact_refs": boundaries["accepted_output"]["boundaries_fact_refs"],
            "report_slots": [{"id": slot, "status": predecessor[fact_for[slot]], "fact_refs": [fact_for[slot]], "claim_ids": []} if slot in fact_for else {"id": slot, "status": "unknown", "fact_refs": [], "claim_ids": ["minimum"]} for slot in slots],
        })
        final, failed = server.tool_call("finalize_analysis", {})
        self.assertFalse(failed, final)

        facts = {fact["kind"]: fact for fact in semantic_facts}
        self.assertEqual(facts["application.name"]["value"], "JPetStore 6")
        self.assertEqual(facts["project.language_version"]["value"], "17")
        self.assertEqual(facts["build.artifact_type"]["value"], "WAR")
        self.assertEqual(facts["runtime.listening_port"]["value"], 8080)
        self.assertEqual(facts["runtime.start_command"]["status"], "conflicted")
        self.assertIn("tomcat90", facts["runtime.start_command"]["value"])
        self.assertIn("tomcat9", facts["runtime.start_command"]["value"])
        self.assertEqual(len(boundaries["accepted_output"]["unit_ids"]), 1)
        self.assertEqual(process["role"], "web")
        self.assertEqual(process["execution_pattern"], "continuous")
        runtime_contract = resolve_runtime_contracts(
            [{"unit_id": derive_workload_unit_id([process["id"]]), "process_ids": [process["id"]], "candidate_ids": ["candidate-jpetstore-web"]}],
            [process], semantic_facts,
        )[0]
        self.assertEqual(runtime_contract["runtime"]["start_command_fact_ref"], facts["runtime.start_command"]["ref"])
        self.assertEqual(runtime_contract["runtime"]["listening_port_fact_ref"], facts["runtime.listening_port"]["ref"])
        markdown = final["markdown"]
        self.assertEqual(validate_markdown(markdown, "summary", {"branch, tag 또는 commit": PINNED_REVISION}), [])
        for value in ("JPetStore 6", "Java", "17", "Maven Wrapper", "WAR", "Spring", "MyBatis", "Apache Tomcat", "8080", "Dockerfile", "docker-compose.yaml", "tomcat90", "tomcat9", "pom.xml:", "Dockerfile:"):
            self.assertIn(value, markdown)
        self.assertNotIn("Start Command: 미확인", markdown)
        self.assertNotIn("Start Command: 확인됨", markdown)
        self.assertIn("Start Command: ./mvnw cargo:run -P tomcat90; active profile tomcat9 (상태: 상충됨", markdown)
        self.assertEqual(contracts["next_skill"], "analyze-k8s-finalize")


if __name__ == "__main__":
    unittest.main()
