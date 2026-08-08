import unittest
from pathlib import Path
from analysis_pipeline.tools import read, glob_paths, locate_evidence
class ToolTests(unittest.TestCase):
 def test_read_redacts_and_bounds_paths(self):
  root=str(Path(__file__).resolve().parents[1])
  self.assertIn('trusted-analysis-pipeline',read(root,'pyproject.toml'))
  with self.assertRaises(ValueError): read(root,'../secret')
 def test_glob_and_locate(self):
  root=str(Path(__file__).resolve().parents[1])
  self.assertIn('pyproject.toml',glob_paths(root,'*.toml'))
  self.assertIsNotNone(locate_evidence(root,'*.toml')['location'])
