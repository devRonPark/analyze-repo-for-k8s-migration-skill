import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_dist

ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "analyze-repo-for-kubernetes",
    "analyze-k8s-discovery",
    "analyze-k8s-execution",
    "analyze-k8s-relationships",
    "analyze-k8s-boundaries",
    "analyze-k8s-contracts",
    "analyze-k8s-finalize",
)


class SkillBundleTests(unittest.TestCase):
    def test_bundle_has_exact_sibling_skill_inventory_and_contract_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            build_dist.build(ROOT, output)
            skills = output / "skills"
            self.assertEqual(sorted(path.name for path in skills.iterdir()), sorted(SKILLS))
            self.assertTrue((skills / "analyze-repo-for-kubernetes" / "SKILL.md").is_file())
            self.assertFalse(any(path.name == "__pycache__" for path in output.rglob("__pycache__")))
            self.assertFalse((output / "runtime" / "python" / "tests").exists())
            projection = json.loads((skills / "analyze-k8s-discovery" / "references" / "payload-contract.json").read_text(encoding="utf-8"))
            source = json.loads((ROOT / "contracts" / "stage-payload-contracts.json").read_text(encoding="utf-8"))
            manifest = json.loads((output / "bundle-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(projection, source["stages"]["discovery"])
        self.assertEqual(set(manifest["skill_policies"]), set(SKILLS))
        self.assertEqual(manifest["skill_policies"]["analyze-repo-for-kubernetes"]["tools"], ["start_analysis"])
        self.assertNotIn("reopen_analysis", manifest["skill_policies"]["analyze-k8s-discovery"]["tools"])


if __name__ == "__main__":
    unittest.main()
