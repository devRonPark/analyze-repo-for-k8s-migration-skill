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
    def fact(kind: str, value: str) -> dict:
        return {
            "kind": kind,
            "value_type": "string",
            "value": value,
            "status": "confirmed",
            "evidence_aliases": ["pom"],
        }

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
