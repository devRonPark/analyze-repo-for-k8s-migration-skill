import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_dist

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("analyze-repo-for-kubernetes",)


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
            source = json.loads((ROOT / "contracts" / "stage-payload-contracts.json").read_text(encoding="utf-8"))
            manifest = json.loads((output / "bundle-manifest.json").read_text(encoding="utf-8"))
            projections = {
                stage: json.loads((skills / "analyze-repo-for-kubernetes" / "references" / "stages" / stage / "payload-contract.json").read_text(encoding="utf-8"))
                for stage in ("discovery", "execution", "relationships", "boundaries", "contracts")
            }
        self.assertEqual(projections, {stage: source["stages"][stage] for stage in projections})
        self.assertEqual(set(manifest["skill_policies"]), set(SKILLS))
        self.assertIn("submit_discovery", manifest["skill_policies"]["analyze-repo-for-kubernetes"]["tools"])
        self.assertNotIn("reopen_analysis", manifest["skill_policies"]["analyze-repo-for-kubernetes"]["tools"])


if __name__ == "__main__":
    unittest.main()
