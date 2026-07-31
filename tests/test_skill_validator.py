from pathlib import Path
import tempfile
import unittest
import json

from scripts import validate_skill


DESCRIPTION = (
    "Analyzes application repositories for Kubernetes migration readiness, "
    "including Docker Compose and GitOps, and reports evidence-backed design inputs."
)


class SkillValidatorTests(unittest.TestCase):
    def make_package(self, *, directory="analyze-repo-for-kubernetes", description=DESCRIPTION, skill_id="analyze-repo-for-kubernetes"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / directory
        (root / "references").mkdir(parents=True)
        (root / "assets").mkdir()
        (root / "scripts").mkdir()
        (root / "contracts").mkdir()
        (root / "scripts/validate_report.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        (root / "references/workflow.md").write_text("# Workflow\n", encoding="utf-8")
        (root / "SKILL.md").write_text(
            f"---\nname: {skill_id}\ndescription: {description}\n---\n\n"
            "Read [workflow](references/workflow.md).\n",
            encoding="utf-8",
        )
        (root / "contracts/project-metadata.json").write_text(
            json.dumps({
                "skill_id": skill_id,
                "agent_id": "kubernetes-migration-analyzer",
                "skill_version": "1.0.0",
                "manifest_name": "manifest.json",
            }),
            encoding="utf-8",
        )
        self.addCleanup(temporary.cleanup)
        return root

    def test_valid_metadata_and_structure_passes(self):
        errors = validate_skill.validate(self.make_package())

        self.assertEqual(errors, [])

    def test_metadata_defines_expected_skill_name(self):
        errors = validate_skill.validate(self.make_package(directory="other-skill", skill_id="other-skill"))

        self.assertEqual(errors, [])

    def test_invalid_name_fails(self):
        root = self.make_package()
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        (root / "SKILL.md").write_text(skill.replace("name: analyze-repo-for-kubernetes", "name: Bad_Name"), encoding="utf-8")

        errors = validate_skill.validate(root)

        self.assertTrue(any("name" in error for error in errors))

    def test_directory_name_must_match_for_distribution_package(self):
        errors = validate_skill.validate(self.make_package(directory="wrong-directory"))

        self.assertTrue(any("directory" in error for error in errors))

    def test_description_over_1024_characters_fails(self):
        errors = validate_skill.validate(self.make_package(description="A" * 1025))

        self.assertTrue(any("description" in error for error in errors))

    def test_xml_tag_in_description_fails(self):
        errors = validate_skill.validate(self.make_package(description="Analyzes <unsafe> repositories."))

        self.assertTrue(any("XML" in error for error in errors))

    def test_broken_direct_link_fails(self):
        root = self.make_package()
        skill_path = root / "SKILL.md"
        skill_path.write_text(
            skill_path.read_text(encoding="utf-8").replace("references/workflow.md", "references/missing.md"),
            encoding="utf-8",
        )

        errors = validate_skill.validate(root)

        self.assertTrue(any("broken" in error for error in errors))

    def test_unclosed_code_fence_fails(self):
        root = self.make_package()
        skill_path = root / "SKILL.md"
        skill_path.write_text(skill_path.read_text(encoding="utf-8") + "\n```python\n", encoding="utf-8")

        errors = validate_skill.validate(root)

        self.assertTrue(any("fence" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
