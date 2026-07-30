from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from scripts import project_metadata
from scripts import run_opencode_acceptance as adapter


ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_loader_rejects_missing_required_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts/project-metadata.json").write_text('{"skill_id": "skill"}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "agent_id"):
                project_metadata.load(root)

    def test_builder_uses_metadata_version_and_manifest_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            output = Path(tmp) / "output"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".artifacts", "dist", "__pycache__"))
            metadata_path = source / "contracts/project-metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata.update(skill_version="9.9.9", manifest_name="package.json")
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = subprocess.run(
                ["python3", str(source / "scripts/build_dist.py"), "--source-root", str(source), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((output / "package.json").read_text(encoding="utf-8"))["version"], "9.9.9")

    def test_acceptance_uses_metadata_agent_id(self):
        project = project_metadata.ProjectMetadata("analyze-repo-for-kubernetes", "fixture-agent", "1.0.0", "manifest.json")
        case = {"id": "metadata", "query": "query", "repository_fixture": "tests/fixtures/repos/sample"}

        def runner(command, **kwargs):
            self.assertIn("fixture-agent", command)
            return subprocess.CompletedProcess(command, 0, '{"type":"text","text":"ok"}\n', "")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts/project-metadata.json").write_text(json.dumps(project.__dict__), encoding="utf-8")
            (root / "SKILL.md").write_text("---\ndescription: test\n---\n", encoding="utf-8")
            trace = adapter.run_case(case, ROOT / "runtime/opencode.json", "/bin/echo", root, root, root, runner=runner)

        self.assertEqual(trace["agent"], "fixture-agent")


if __name__ == "__main__":
    unittest.main()
