from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryDistributionTests(unittest.TestCase):
    def test_public_repository_files_exist(self):
        for rel in [
            "LICENSE",
            "CHANGELOG.md",
            ".gitignore",
            ".github/workflows/test.yml",
            "scripts/install-qwen.sh",
            "scripts/update-qwen.sh",
        ]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_shell_scripts_are_valid(self):
        for rel in [
            "scripts/install-qwen.sh",
            "scripts/update-qwen.sh",
            "scripts/install-codex.sh",
            "scripts/install-opencode.sh",
        ]:
            result = subprocess.run(
                ["bash", "-n", str(ROOT / rel)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_install_script_creates_qwen_skill_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-qwen.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = home / ".qwen/skills/analyze-repo-for-kubernetes"
            self.assertTrue(installed.is_symlink())
            self.assertEqual(installed.resolve(), ROOT.resolve())

    def run_builder(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(ROOT / "scripts/build_dist.py"), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_build_is_repeatable_and_excludes_development_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first" / "analyze-repo-for-kubernetes"
            second = Path(tmp) / "second" / "analyze-repo-for-kubernetes"
            first_result = self.run_builder(first)
            second_result = self.run_builder(second)
            self.assertEqual(first_result.returncode, 0, first_result.stdout + first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stdout + second_result.stderr)

            def snapshot(directory: Path) -> dict[str, bytes]:
                return {
                    str(path.relative_to(directory)): path.read_bytes()
                    for path in directory.rglob("*")
                    if path.is_file()
                }

            self.assertEqual(snapshot(first), snapshot(second))
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["skill_id"], "analyze-repo-for-kubernetes")
            self.assertTrue(manifest["source_revision"])
            self.assertNotIn("README.md", snapshot(first))
            self.assertNotIn("CHANGELOG.md", snapshot(first))
            self.assertNotIn("agents/openai.yaml", snapshot(first))
            self.assertNotIn("tests/scenarios.md", snapshot(first))
            self.assertNotIn("scripts/install-codex.sh", snapshot(first))
            self.assertNotIn("scripts/install-qwen.sh", snapshot(first))

    def test_built_distribution_passes_package_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analyze-repo-for-kubernetes"
            build = self.run_builder(output)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/validate_skill.py"), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_opencode_installer_copies_global_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-opencode.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = home / ".config/opencode/skills/analyze-repo-for-kubernetes"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertFalse(installed.is_symlink())

    def test_opencode_installer_supports_project_local_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project = Path(tmp) / "project"
            home.mkdir()
            project.mkdir()
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-opencode.sh"), "--project-local", str(project)],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((project / ".opencode/skills/analyze-repo-for-kubernetes/SKILL.md").is_file())

    def test_opencode_installer_rejects_duplicate_locations_without_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            duplicate = home / ".agents/skills/analyze-repo-for-kubernetes"
            duplicate.mkdir(parents=True)
            (duplicate / "SKILL.md").write_text("duplicate", encoding="utf-8")
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-opencode.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate", result.stdout + result.stderr)

            override = subprocess.run(
                ["bash", str(ROOT / "scripts/install-opencode.sh"), "--allow-duplicates"],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(override.returncode, 0, override.stdout + override.stderr)

    def test_markdown_commands_do_not_use_shell_line_continuations(self):
        for path in ROOT.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(line.rstrip().endswith("\\"), f"{path}: {line}")


if __name__ == "__main__":
    unittest.main()
