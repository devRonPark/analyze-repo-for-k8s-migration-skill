import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_static_mcp_goldens import validate_manifest


ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "tests" / "evaluation"
MANIFEST = EVALUATION / "static-mcp-golden-manifest.json"


class StaticMCPGoldenManifestTests(unittest.TestCase):
    def copied_manifest(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            golden = case["golden"]
            shutil.copy2(EVALUATION / golden, root / golden)
        copied = root / "static-mcp-golden-manifest.json"
        copied.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return temporary, copied

    def test_manifest_seals_exactly_the_six_target_mode_goldens(self):
        self.assertEqual(validate_manifest(MANIFEST), [])

    def test_manifest_rejects_a_changed_golden_digest(self):
        temporary, manifest = self.copied_manifest()
        with temporary:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            (manifest.parent / payload["cases"][0]["golden"]).write_text("tampered\n", encoding="utf-8")
            self.assertTrue(any("sha256 mismatch" in error for error in validate_manifest(manifest)))

    def test_manifest_rejects_a_missing_golden_file(self):
        temporary, manifest = self.copied_manifest()
        with temporary:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            (manifest.parent / payload["cases"][0]["golden"]).unlink()
            self.assertTrue(any("golden file is missing" in error for error in validate_manifest(manifest)))

    def test_manifest_rejects_an_unknown_target_mode_case(self):
        temporary, manifest = self.copied_manifest()
        with temporary:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["cases"][0]["target"] = "unknown-target"
            manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(any("unknown target/mode" in error for error in validate_manifest(manifest)))


if __name__ == "__main__":
    unittest.main()
