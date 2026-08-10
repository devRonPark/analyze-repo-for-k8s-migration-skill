"""Runtime contracts bind accepted semantic facts to resolved workload units."""
from __future__ import annotations

import unittest

from analysis_pipeline.runtime_contracts import resolve_runtime_contracts, validate_runtime_contracts
from analysis_pipeline.validation import derive_runtime_process_id, derive_semantic_fact_ref
from analysis_pipeline.workload_grouping import derive_workload_unit_id


class RuntimeContractTests(unittest.TestCase):
    @staticmethod
    def fact(kind: str, value: object, *, value_type: str, status: str = "confirmed") -> dict:
        identity = {
            "kind": kind,
            "value_type": value_type,
            "value": value,
            "status": status,
            "evidence_ids": ["evidence-runtime"],
        }
        return {"ref": derive_semantic_fact_ref(identity), **identity}

    def jpetstore_unit(self) -> tuple[list[dict], list[dict]]:
        facts = [
            self.fact("runtime.start_command", "./mvnw cargo:run -P tomcat9", value_type="string"),
            self.fact("runtime.listening_port", 8080, value_type="integer"),
        ]
        process_identity = {
            "candidate_ids": ["candidate-jpetstore-web"],
            "role": "web",
            "execution_pattern": "continuous",
            "semantic_fact_refs": [fact["ref"] for fact in facts],
        }
        process = {"id": derive_runtime_process_id(process_identity), **process_identity}
        unit = {
            "unit_id": derive_workload_unit_id([process["id"]]),
            "process_ids": [process["id"]],
            "candidate_ids": ["candidate-jpetstore-web"],
        }
        return [unit], [process], facts

    def test_binds_start_command_and_listening_port_without_copying_values(self) -> None:
        units, processes, facts = self.jpetstore_unit()

        contracts = resolve_runtime_contracts(units, processes, facts)

        runtime = contracts[0]["runtime"]
        self.assertEqual(contracts[0]["unit_id"], units[0]["unit_id"])
        self.assertEqual(runtime["start_command_fact_ref"], facts[0]["ref"])
        self.assertEqual(runtime["listening_port_fact_ref"], facts[1]["ref"])
        self.assertEqual(contracts[0]["fact_statuses"][facts[1]["ref"]], "confirmed")
        self.assertNotIn("value", str(contracts))

    def test_rejects_a_runtime_fact_not_owned_by_the_unit_process(self) -> None:
        units, processes, facts = self.jpetstore_unit()
        processes[0]["semantic_fact_refs"] = [facts[1]["ref"]]

        with self.assertRaisesRegex(ValueError, "runtime fact subject mismatch"):
            resolve_runtime_contracts(units, processes, facts)

    def test_binds_project_build_server_and_context_refs_without_secret_literals(self) -> None:
        units, processes, facts = self.jpetstore_unit()
        remaining = [
            self.fact("application.name", "JPetStore", value_type="string"),
            self.fact("project.language", "Java", value_type="string"),
            self.fact("project.framework", "Spring", value_type="string"),
            self.fact("build.tool", "Maven Wrapper", value_type="string"),
            self.fact("build.artifact_type", "WAR", value_type="string"),
            self.fact("build.command", "./mvnw package password=not-a-contract-literal", value_type="string"),
            self.fact("runtime.server", "Tomcat 9", value_type="string"),
            self.fact("runtime.context_path", "/jpetstore/", value_type="string"),
        ]
        facts.extend(remaining)
        processes[0]["semantic_fact_refs"].extend(
            fact["ref"] for fact in remaining if fact["kind"].startswith("runtime.")
        )

        contract = resolve_runtime_contracts(units, processes, facts)[0]

        self.assertEqual(set(contract["project_fact_refs"]), {fact["ref"] for fact in remaining[:3]})
        self.assertEqual(set(contract["build_fact_refs"]), {fact["ref"] for fact in remaining[3:6]})
        self.assertEqual(contract["runtime"]["server_fact_ref"], remaining[6]["ref"])
        self.assertEqual(contract["runtime"]["context_path_fact_ref"], remaining[7]["ref"])
        self.assertNotIn("password=not-a-contract-literal", str(contract))

    def test_unknown_and_conflicted_runtime_statuses_are_preserved(self) -> None:
        units, processes, facts = self.jpetstore_unit()
        facts[0] = self.fact("runtime.start_command", None, value_type="string", status="unknown")
        facts[1] = self.fact("runtime.listening_port", 8080, value_type="integer", status="conflicted")
        processes[0]["semantic_fact_refs"] = [fact["ref"] for fact in facts]

        contract = resolve_runtime_contracts(units, processes, facts)[0]

        self.assertEqual(contract["fact_statuses"][facts[0]["ref"]], "unknown")
        self.assertEqual(contract["fact_statuses"][facts[1]["ref"]], "conflicted")

    def test_validation_rejects_dangling_and_wrong_kind_runtime_refs(self) -> None:
        units, processes, facts = self.jpetstore_unit()
        contract = resolve_runtime_contracts(units, processes, facts)[0]
        dangling = {**contract, "runtime": {**contract["runtime"], "start_command_fact_ref": "semantic_fact_discovery_missing"}}
        dangling["fact_statuses"] = {
            **contract["fact_statuses"],
            "semantic_fact_discovery_missing": "confirmed",
        }
        with self.assertRaisesRegex(ValueError, "fact dangling"):
            validate_runtime_contracts(units, processes, facts, [dangling])

        unrelated = self.fact("container.dockerfile", "Dockerfile", value_type="string")
        facts.append(unrelated)
        processes[0]["semantic_fact_refs"].append(unrelated["ref"])
        wrong_kind = {**contract, "runtime": {**contract["runtime"], "start_command_fact_ref": unrelated["ref"]}}
        wrong_kind["fact_statuses"] = dict(contract["fact_statuses"])
        del wrong_kind["fact_statuses"][facts[0]["ref"]]
        wrong_kind["fact_statuses"][unrelated["ref"]] = "confirmed"
        with self.assertRaisesRegex(ValueError, "runtime fact kind mismatch"):
            validate_runtime_contracts(units, processes, facts, [wrong_kind])

    def test_validation_requires_exactly_one_contract_for_each_resolved_unit(self) -> None:
        units, processes, facts = self.jpetstore_unit()

        with self.assertRaisesRegex(ValueError, "one runtime contract"):
            validate_runtime_contracts(units, processes, facts, [])

    def test_validation_rejects_a_contract_bound_to_another_unit(self) -> None:
        units, processes, facts = self.jpetstore_unit()
        contract = resolve_runtime_contracts(units, processes, facts)[0]
        wrong_unit = {**contract, "unit_id": "unit_other"}

        with self.assertRaisesRegex(ValueError, "unit binding mismatch"):
            validate_runtime_contracts(units, processes, facts, [wrong_unit])


if __name__ == "__main__":
    unittest.main()
