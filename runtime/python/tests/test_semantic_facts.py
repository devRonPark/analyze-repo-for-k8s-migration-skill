"""Accepted semantic facts retain typed values and server-owned provenance."""
from __future__ import annotations

import unittest

from analysis_pipeline.stage_contracts import (
    project_discovery_handoff,
    promote_discovery_facts,
    validate_discovery_payload,
)
from analysis_pipeline.state import create_state


BINDING = {
    "binding_id": "binding-semantic",
    "target_realpath": "C:/pinned/jpetstore-6",
    "target_snapshot_hash": "snapshot-jpetstore",
    "skill_manifest_hash": "skill",
    "required_rule_ids": [],
}


class Registry:
    def resolve(self, reference: str, stage: str, snapshot: object) -> dict:
        if reference != "obs_pom" or stage != "discovery":
            raise ValueError("unknown observation reference")
        return {
            "snapshot_hash": "snapshot-jpetstore",
            "canonical_evidence": {
                "location": "pom.xml",
                "range": "33-147",
                "status": "confirmed",
                "content_fingerprint": "pinned-jpetstore-pom",
                "redacted": True,
            },
        }


class RegistryWithAbsence(Registry):
    def resolve(self, reference: str, stage: str, snapshot: object) -> dict:
        if reference == "obs_absence" and stage == "discovery":
            return {
                "snapshot_hash": "snapshot-jpetstore",
                "canonical_evidence": {
                    "location": "search:project metadata",
                    "range": "0-0",
                    "status": "unknown",
                    "content_fingerprint": "pinned-jpetstore-absence",
                    "redacted": True,
                },
                "absence": {"scope": "project metadata", "glob": "pom.xml", "pattern": "release"},
            }
        return super().resolve(reference, stage, snapshot)


class RuntimeRegistry(RegistryWithAbsence):
    """Static JPetStore evidence candidates used only by semantic-fact tests."""

    _OBSERVATIONS = {
        "obs_readme": ("README.md", "45-48", "pinned-jpetstore-readme"),
        "obs_pom": ("pom.xml", "180-184", "pinned-jpetstore-pom-runtime"),
        "obs_dockerfile": ("Dockerfile", "1-12", "pinned-jpetstore-dockerfile"),
        "obs_compose": ("docker-compose.yaml", "1-18", "pinned-jpetstore-compose"),
    }

    def resolve(self, reference: str, stage: str, snapshot: object) -> dict:
        if reference in self._OBSERVATIONS and stage == "discovery":
            location, line_range, fingerprint = self._OBSERVATIONS[reference]
            return {
                "snapshot_hash": "snapshot-jpetstore",
                "canonical_evidence": {
                    "location": location,
                    "range": line_range,
                    "status": "confirmed",
                    "content_fingerprint": fingerprint,
                    "redacted": True,
                },
            }
        return super().resolve(reference, stage, snapshot)


class SemanticFactTests(unittest.TestCase):
    @staticmethod
    def payload(semantic_facts: list[dict]) -> dict:
        return {
            "schema_version": 1,
            "stage": "discovery",
            "evidence": [{"alias": "pom", "observation_ref": "obs_pom"}],
            "claims": [{"id": "project-metadata", "status": "confirmed", "evidence_aliases": ["pom"]}],
            "semantic_facts": semantic_facts,
            "rule_applications": [],
            "signals": ["maven-java"],
            "candidate_ids": ["jpetstore-web"],
            "decisions": ["project-identity"],
        }

    @staticmethod
    def fact(kind: str, value: object, *, value_type: str = "string", aliases: list[str] | None = None, status: str = "confirmed") -> dict:
        return {
            "kind": kind,
            "value_type": value_type,
            "value": value,
            "status": status,
            "evidence_aliases": aliases or ["pom"],
        }

    def runtime_payload(self, facts: list[dict], evidence: list[dict]) -> dict:
        payload = self.payload(facts)
        payload["evidence"] = evidence
        payload["claims"] = [{"id": "runtime-metadata", "status": "confirmed", "evidence_aliases": [item["alias"] for item in evidence]}]
        return payload

    def test_jpetstore_runtime_facts_preserve_typed_values_and_provenance(self) -> None:
        payload = self.runtime_payload(
            [
                self.fact("build.command", "./mvnw clean package", aliases=["pom"]),
                self.fact("runtime.server", "Tomcat 9", aliases=["pom"]),
                self.fact("runtime.start_command", "./mvnw cargo:run -P tomcat9", aliases=["readme"]),
                self.fact("runtime.listening_port", 8080, value_type="integer", aliases=["pom"]),
                self.fact("runtime.context_path", "/jpetstore/", aliases=["pom"]),
                self.fact("container.dockerfile", "Dockerfile", aliases=["dockerfile"]),
                self.fact("container.compose", "docker-compose.yaml", aliases=["compose"]),
            ],
            [
                {"alias": "readme", "observation_ref": "obs_readme"},
                {"alias": "pom", "observation_ref": "obs_pom"},
                {"alias": "dockerfile", "observation_ref": "obs_dockerfile"},
                {"alias": "compose", "observation_ref": "obs_compose"},
            ],
        )
        accepted = promote_discovery_facts(
            create_state(BINDING), validate_discovery_payload(payload, RuntimeRegistry(), object(), BINDING)
        )
        facts = project_discovery_handoff(accepted)["semantic_facts"]
        self.assertEqual(
            [(fact["kind"], fact["value_type"], fact["value"]) for fact in facts],
            [
                ("build.command", "string", "./mvnw clean package"),
                ("runtime.server", "string", "Tomcat 9"),
                ("runtime.start_command", "string", "./mvnw cargo:run -P tomcat9"),
                ("runtime.listening_port", "integer", 8080),
                ("runtime.context_path", "string", "/jpetstore/"),
                ("container.dockerfile", "string", "Dockerfile"),
                ("container.compose", "string", "docker-compose.yaml"),
            ],
        )
        start_command = next(fact for fact in facts if fact["kind"] == "runtime.start_command")
        self.assertEqual(len(start_command["evidence_ids"]), 1)

    def test_runtime_start_command_conflict_and_unknown_are_preserved(self) -> None:
        payload = self.runtime_payload(
            [
                self.fact(
                    "runtime.start_command",
                    "./mvnw cargo:run -P tomcat9",
                    aliases=["readme", "dockerfile"],
                    status="conflicted",
                ),
                {
                    "kind": "runtime.context_path",
                    "value_type": "string",
                    "value": None,
                    "status": "unknown",
                    "evidence_aliases": ["absence"],
                    "scope": "runtime context configuration",
                    "blocked_decision": "runtime-context",
                },
            ],
            [
                {"alias": "readme", "observation_ref": "obs_readme"},
                {"alias": "dockerfile", "observation_ref": "obs_dockerfile"},
                {"alias": "absence", "observation_ref": "obs_absence"},
            ],
        )
        accepted = promote_discovery_facts(
            create_state(BINDING), validate_discovery_payload(payload, RuntimeRegistry(), object(), BINDING)
        )
        facts = project_discovery_handoff(accepted)["semantic_facts"]
        conflict, unknown = facts
        self.assertEqual(conflict["status"], "conflicted")
        self.assertEqual(len(conflict["evidence_ids"]), 2)
        self.assertEqual((unknown["status"], unknown["value"]), ("unknown", None))

    def test_jpetstore_project_metadata_survives_discovery_with_typed_provenance(self) -> None:
        # Values and line range are from the pinned JPetStore 6 static golden
        # evidence, not an agent prompt or a JPetStore-specific code path.
        payload = validate_discovery_payload(self.payload([
            self.fact("application.name", "JPetStore"),
            self.fact("project.language", "Java"),
            self.fact("project.language_version", "17"),
            self.fact("project.framework", "MyBatis"),
            self.fact("project.framework", "Spring"),
            self.fact("project.framework", "Stripes"),
            self.fact("build.tool", "Maven Wrapper"),
            self.fact("build.artifact_type", "WAR"),
        ]), Registry(), object(), BINDING)
        state = create_state(BINDING)
        accepted = promote_discovery_facts(state, payload)
        facts = project_discovery_handoff(accepted)["semantic_facts"]

        self.assertEqual(
            [(fact["kind"], fact["value_type"], fact["value"]) for fact in facts],
            [
                ("application.name", "string", "JPetStore"),
                ("project.language", "string", "Java"),
                ("project.language_version", "string", "17"),
                ("project.framework", "string", "MyBatis"),
                ("project.framework", "string", "Spring"),
                ("project.framework", "string", "Stripes"),
                ("build.tool", "string", "Maven Wrapper"),
                ("build.artifact_type", "string", "WAR"),
            ],
        )
        self.assertTrue(all(fact["ref"].startswith("semantic_fact_discovery_") for fact in facts))
        self.assertTrue(all(fact["evidence_ids"] for fact in facts))

    def test_rejects_client_owned_or_dangling_semantic_fact_provenance(self) -> None:
        forged = self.fact("project.language", "Java") | {"ref": "semantic_fact_discovery_forged"}
        with self.assertRaisesRegex(ValueError, "client semantic fact field"):
            validate_discovery_payload(self.payload([forged]), Registry(), object(), BINDING)

        dangling = self.fact("project.language", "Java") | {"evidence_aliases": ["missing"]}
        with self.assertRaisesRegex(ValueError, "unknown evidence alias"):
            validate_discovery_payload(self.payload([dangling]), Registry(), object(), BINDING)

        accepted = validate_discovery_payload(self.payload([self.fact("project.language", "Java")]), Registry(), object(), BINDING)
        accepted["semantic_facts"][0]["ref"] = "semantic_fact_discovery_forged"
        with self.assertRaisesRegex(ValueError, "forged semantic fact reference"):
            promote_discovery_facts(create_state(BINDING), accepted)

    def test_preserves_unknown_and_conflicted_semantic_statuses(self) -> None:
        payload = self.payload([
            {
                "kind": "project.language_version",
                "value_type": "string",
                "value": None,
                "status": "unknown",
                "evidence_aliases": ["absence"],
                "scope": "project metadata",
                "blocked_decision": "project-identity",
            },
            {
                "kind": "build.tool",
                "value_type": "string",
                "value": "Maven",
                "status": "conflicted",
                "evidence_aliases": ["pom"],
            },
        ])
        payload["evidence"].append({"alias": "absence", "observation_ref": "obs_absence"})
        accepted = promote_discovery_facts(
            create_state(BINDING), validate_discovery_payload(payload, RegistryWithAbsence(), object(), BINDING)
        )
        facts = project_discovery_handoff(accepted)["semantic_facts"]
        self.assertEqual([(fact["kind"], fact["status"], fact["value"]) for fact in facts], [
            ("project.language_version", "unknown", None),
            ("build.tool", "conflicted", "Maven"),
        ])


if __name__ == "__main__":
    unittest.main()
