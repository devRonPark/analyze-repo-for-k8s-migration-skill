import unittest
import os
import tempfile
from pathlib import Path
from analysis_pipeline.tools import read, glob_paths, locate_evidence
from analysis_pipeline.tools.safe_paths import safe_path
class ToolTests(unittest.TestCase):
 def test_read_redacts_and_bounds_paths(self):
  root=str(Path(__file__).resolve().parents[1])
  self.assertIn('trusted-analysis-pipeline',read(root,'pyproject.toml'))
  with self.assertRaises(ValueError): read(root,'../secret')
 def test_glob_and_locate(self):
  root=str(Path(__file__).resolve().parents[1])
  self.assertIn('pyproject.toml',glob_paths(root,'*.toml'))
  self.assertEqual(locate_evidence(root,'*.toml')['status'],'found')
 def test_safe_path_rejects_an_in_root_symlink(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); source=root/'source.txt'; source.write_text('safe',encoding='utf-8')
   link=root/'link.txt'
   try: os.symlink(source,link)
   except OSError as error: self.skipTest(f'symlink unavailable: {error}')
   with self.assertRaisesRegex(ValueError,'symlink|reparse'):
    safe_path(root,'link.txt')
