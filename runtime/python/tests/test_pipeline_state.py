import sys, unittest
sys.path.insert(0, 'runtime/python')
from analysis_pipeline import *
class PipelineTests(unittest.TestCase):
 def test_canonical_and_order(self):
  self.assertEqual(canonical_json({'b':1,'a':2}),'{"a":2,"b":1}')
  s=create_state('p'); s2=submit(s,'inventory',{},0,s.digest()); self.assertEqual(s.revision,0); self.assertEqual(s2.revision,1)
  with self.assertRaises(ValueError): submit(s2,'runtime',{},1,s2.digest())
 def test_stale_and_finalize(self):
  s=create_state('p')
  for i,stage in enumerate(STAGES): s=submit(s,stage,{},i,s.digest())
  s=finalize(s,6,s.digest()); self.assertTrue(s.finalized)
  with self.assertRaises(ValueError): finalize(s,7,s.digest())
 def test_evidence_id(self): self.assertEqual(derive_evidence_id({'x':1}),derive_evidence_id({'x':1}))
if __name__=='__main__': unittest.main()
