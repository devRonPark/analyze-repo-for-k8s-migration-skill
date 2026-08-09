import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_dist
from scripts import install_distribution


ROOT = Path(__file__).resolve().parents[1]
SKILLS = set(build_dist.SKILL_IDS)


class BundleInstallerTests(unittest.TestCase):
    def build_bundle(self, root: Path) -> Path:
        bundle = root / "bundle"
        build_dist.build(ROOT, bundle)
        return bundle

    def test_installs_exact_skill_topology_and_absolute_launcher_fragment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / "config"
            bundle = self.build_bundle(root)

            install_distribution.install_bundle(bundle, config_root)

            self.assertEqual(
                {path.name for path in (config_root / "skills").iterdir()},
                SKILLS,
            )
            runtime_root = config_root / "analyze-repo-for-kubernetes" / "runtime"
            self.assertTrue((runtime_root / "python" / "launch_mcp.py").is_file())
            self.assertTrue((config_root / "agent" / "kubernetes-migration-analyzer.md").is_file())
            self.assertTrue((config_root / "command" / "analyze-repo-for-kubernetes.md").is_file())
            fragment = json.loads(
                (config_root / "analyze-repo-for-kubernetes" / "opencode-mcp.json").read_text(encoding="utf-8")
            )
            command = fragment["mcp"]["analysis"]["command"]
            self.assertEqual(Path(command[1]), (runtime_root / "python" / "launch_mcp.py").resolve())
            self.assertTrue(Path(command[1]).is_absolute())

    def test_each_partial_swap_failure_restores_existing_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / "config"
            bundle = self.build_bundle(root)
            install_distribution.install_bundle(bundle, config_root)
            before = {
                str(path.relative_to(config_root)): path.read_bytes()
                for path in config_root.rglob("*")
                if path.is_file()
            }
            targets = install_distribution.bundle_targets(bundle, config_root)
            original_replace = Path.replace

            for failure_target in targets:
                def fail_one(source: Path, destination: Path, *, expected=failure_target):
                    if destination == expected and ".stage-" in source.name:
                        raise OSError("injected bundle swap failure")
                    return original_replace(source, destination)

                with patch.object(Path, "replace", new=fail_one):
                    with self.assertRaisesRegex(OSError, "injected bundle swap failure"):
                        install_distribution.install_bundle(bundle, config_root)
                self.assertEqual(
                    {
                        str(path.relative_to(config_root)): path.read_bytes()
                        for path in config_root.rglob("*")
                        if path.is_file()
                    },
                    before,
                )

    def test_rejects_a_tampered_sealed_bundle_before_creating_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self.build_bundle(root)
            skill = bundle / "skills" / "analyze-k8s-discovery" / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid bundle"):
                install_distribution.install_bundle(bundle, root / "config")

            self.assertFalse((root / "config").exists())


if __name__ == "__main__":
    unittest.main()
