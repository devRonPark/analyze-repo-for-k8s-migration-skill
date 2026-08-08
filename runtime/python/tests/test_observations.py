from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis_pipeline.observations import ObservationRegistry, TargetSnapshot


class ObservationRegistryTests(unittest.TestCase):
    def test_tool_issued_observation_is_stage_bound_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Dockerfile"
            source.write_text("token=[REDACTED]\n", encoding="utf-8")
            snapshot = TargetSnapshot.capture(root)
            registry = ObservationRegistry(root, {"binding_id": "bind-1", "target_snapshot_hash": snapshot.digest})

            issued = registry.issue_present("discovery", source, 1, 1, "token=[REDACTED]")
            resolved = registry.resolve(issued["observation_ref"], "discovery", TargetSnapshot.capture(root))

            self.assertTrue(issued["observation_ref"].startswith("obs_"))
            self.assertNotIn("token=", repr(resolved))
            self.assertEqual(resolved["canonical_evidence"]["location"], "Dockerfile")

    def test_changed_file_and_wrong_stage_invalidate_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Dockerfile"
            source.write_text("FROM python\n", encoding="utf-8")
            snapshot = TargetSnapshot.capture(root)
            registry = ObservationRegistry(root, {"binding_id": "bind-1", "target_snapshot_hash": snapshot.digest})
            issued = registry.issue_present("discovery", source, 1, 1, "FROM python")
            source.write_text("FROM python:3.13\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "snapshot|source changed"):
                registry.resolve(issued["observation_ref"], "discovery", TargetSnapshot.capture(root))
            with self.assertRaisesRegex(ValueError, "stage"):
                registry.resolve(issued["observation_ref"], "execution", snapshot)


if __name__ == "__main__":
    unittest.main()
