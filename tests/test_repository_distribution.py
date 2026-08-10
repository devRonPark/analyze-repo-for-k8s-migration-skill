from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_dist
from scripts import install_distribution

ROOT = Path(__file__).resolve().parents[1]
BASH_PROCESS_UNAVAILABLE = sys.platform == "win32"


def _msys_posix_path(path: Path) -> str:
    """Render a Windows path the way MSYS bash resolves it via $PATH."""
    drive = path.drive.rstrip(":").lower()
    return f"/{drive}{path.as_posix()[2:]}"


# The installer scripts require python3 on PATH. The tests sandbox PATH to
# "/usr/bin:/bin" so they exercise only what install-opencode.sh/install-qwen.sh
# actually need. On Unix, that already contains a working python3, so the
# sandbox is left untouched there; on Windows, the interpreter running this
# suite is rarely on /usr/bin or /bin, so its directory must be added
# explicitly, translated to the form MSYS bash's $PATH search understands.
if sys.platform == "win32":
    SANDBOX_PATH = f"/usr/bin:/bin:{_msys_posix_path(Path(sys.executable).parent)}"
else:
    SANDBOX_PATH = "/usr/bin:/bin"


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

    @unittest.skipIf(BASH_PROCESS_UNAVAILABLE, "MSYS Bash process isolation is unavailable on Windows")
    def test_shell_scripts_are_valid(self):
        for rel in [
            "scripts/install-qwen.sh",
            "scripts/update-qwen.sh",
            "scripts/install-codex.sh",
            "scripts/install-opencode.sh",
        ]:
            result = subprocess.run(
                # Passing a Korean absolute Windows path through MSYS bash can
                # fail while decoding its diagnostic stream. The command is
                # intentionally relative to the checkout used as cwd.
                ["bash", "-n", rel],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipIf(BASH_PROCESS_UNAVAILABLE, "MSYS Bash process isolation is unavailable on Windows")
    def test_install_script_creates_qwen_static_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", "scripts/install-qwen.sh"],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": SANDBOX_PATH},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            skills = home / ".qwen/skills"
            self.assertEqual({path.name for path in skills.iterdir()}, set(build_dist.SKILL_IDS))
            self.assertTrue((home / ".qwen/analyze-repo-for-kubernetes/runtime/python/launch_mcp.py").is_file())

    def run_builder(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_dist.py"), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_builder_cli_uses_utf8_stdout(self):
        # Keep staging out of the host TEMP directory: its ACL defect is
        # independently covered by G0B. ROOT still contains Korean text.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            result = self.run_builder(Path(tmp) / "bundle")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Built bundle:", result.stdout)

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
            manifest = json.loads((first / "bundle-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["skills"], list(build_dist.SKILL_IDS))
            self.assertTrue(manifest["source_revision"])
            self.assertNotIn("README.md", snapshot(first))
            self.assertNotIn("CHANGELOG.md", snapshot(first))
            self.assertNotIn("agents/openai.yaml", snapshot(first))
            self.assertNotIn("tests/scenarios.md", snapshot(first))
            self.assertNotIn("scripts/install-codex.sh", snapshot(first))
            self.assertNotIn("scripts/install-qwen.sh", snapshot(first))

    def test_build_falls_back_when_output_parent_rejects_staging_directory(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            output = Path(tmp) / "analyze-repo-for-kubernetes"
            real_mkdtemp = build_dist.tempfile.mkdtemp

            def reject_nested_staging(*, prefix, dir=None):
                if dir == output.parent:
                    raise PermissionError("injected restrictive temporary directory")
                return real_mkdtemp(prefix=prefix, dir=dir)

            with patch("scripts.build_dist.tempfile.mkdtemp", side_effect=reject_nested_staging):
                build_dist.build(ROOT, output)

            self.assertTrue((output / "bundle-manifest.json").is_file())

    def test_built_distribution_passes_package_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analyze-repo-for-kubernetes"
            build = self.run_builder(output)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/validate_skill.py"), str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_distribution_swap_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analyze-repo-for-kubernetes"
            output.mkdir()
            (output / "previous.txt").write_text("previous", encoding="utf-8")

            real_replace = build_dist.os.replace

            def fail_staging_swap(source, destination):
                if Path(source).name == output.name:
                    raise OSError("injected swap failure")
                return real_replace(source, destination)

            with patch("scripts.build_dist.os.replace", side_effect=fail_staging_swap):
                with self.assertRaises(OSError):
                    build_dist.build(ROOT, output)

            self.assertEqual((output / "previous.txt").read_text(encoding="utf-8"), "previous")

    @unittest.skipIf(BASH_PROCESS_UNAVAILABLE, "MSYS Bash process isolation is unavailable on Windows")
    def test_opencode_installer_copies_global_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", "scripts/install-opencode.sh"],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": SANDBOX_PATH},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = home / ".config/opencode"
            installed = config / "skills/analyze-repo-for-kubernetes"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertFalse(installed.is_symlink())
            self.assertTrue((home / ".config/opencode/agent/kubernetes-migration-analyzer.md").is_file())
            self.assertTrue((home / ".config/opencode/command/analyze-repo-for-kubernetes.md").is_file())
            self.assertTrue((config / "analyze-repo-for-kubernetes/runtime/python/launch_mcp.py").is_file())
            self.assertTrue((config / "analyze-repo-for-kubernetes/opencode-mcp.json").is_file())

    def test_failed_multi_path_install_restores_every_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "new"
            source.mkdir()
            (source / "version").write_text("new", encoding="utf-8")
            targets = [root / "one" / "skill", root / "two" / "skill"]
            for target in targets:
                target.mkdir(parents=True)
                (target / "version").write_text("old", encoding="utf-8")

            real_replace = Path.replace
            injected = False

            def fail_second_swap(source_path, target_path):
                nonlocal injected
                if not injected and source_path != target_path and target_path == targets[1]:
                    injected = True
                    raise OSError("injected swap failure")
                return real_replace(source_path, target_path)

            with patch.object(Path, "replace", new=fail_second_swap):
                with self.assertRaisesRegex(OSError, "injected"):
                    install_distribution.install(source, targets)

            self.assertEqual([target.joinpath("version").read_text(encoding="utf-8") for target in targets], ["old", "old"])

    @unittest.skipIf(BASH_PROCESS_UNAVAILABLE, "MSYS Bash process isolation is unavailable on Windows")
    def test_opencode_installer_supports_project_local_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project = Path(tmp) / "project"
            home.mkdir()
            project.mkdir()
            result = subprocess.run(
                ["bash", "scripts/install-opencode.sh", "--project-local", str(project)],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": SANDBOX_PATH},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((project / ".opencode/skills/analyze-repo-for-kubernetes/SKILL.md").is_file())
            self.assertTrue((project / ".opencode/agent/kubernetes-migration-analyzer.md").is_file())
            self.assertTrue((project / ".opencode/command/analyze-repo-for-kubernetes.md").is_file())
            installed = project / ".opencode/analyze-repo-for-kubernetes"
            self.assertTrue((installed / "runtime/python/launch_mcp.py").is_file())
            self.assertTrue((installed / "opencode-mcp.json").is_file())

    @unittest.skipIf(BASH_PROCESS_UNAVAILABLE, "MSYS Bash process isolation is unavailable on Windows")
    def test_opencode_installer_leaves_legacy_duplicate_locations_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            duplicate = home / ".agents/skills/analyze-repo-for-kubernetes"
            duplicate.mkdir(parents=True)
            stale_skill = duplicate / "SKILL.md"
            stale_skill.write_text("stale test Skill", encoding="utf-8")
            result = subprocess.run(
                ["bash", "scripts/install-opencode.sh"],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": SANDBOX_PATH},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = home / ".config/opencode/skills/analyze-repo-for-kubernetes/SKILL.md"
            self.assertTrue(installed.is_file())
            self.assertEqual(stale_skill.read_text(encoding="utf-8"), "stale test Skill")

    @unittest.skipIf(BASH_PROCESS_UNAVAILABLE, "MSYS Bash process isolation is unavailable on Windows")
    def test_opencode_installer_does_not_replace_source_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            source = home / ".agents/skills/analyze-repo-for-kubernetes"
            home.mkdir()
            shutil.copytree(
                ROOT,
                source,
                ignore=shutil.ignore_patterns(".git", ".artifacts", "dist", "__pycache__"),
            )
            result = subprocess.run(
                ["bash", str(source / "scripts/install-opencode.sh")],
                cwd=source,
                env={"HOME": str(home), "PATH": SANDBOX_PATH},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((source / "README.md").is_file())
            self.assertTrue((home / ".config/opencode/skills/analyze-repo-for-kubernetes/SKILL.md").is_file())

    def test_markdown_commands_do_not_use_shell_line_continuations(self):
        for path in ROOT.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(line.rstrip().endswith("\\"), f"{path}: {line}")


if __name__ == "__main__":
    unittest.main()
