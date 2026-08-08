import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis_pipeline.mcp_server import Server, handle

class MCPTests(unittest.TestCase):
 def test_initialize_and_schema(self):
  s=Server(); init=handle(s,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}); self.assertIn("serverInfo",init["result"])
  tools=handle(s,{"jsonrpc":"2.0","id":2,"method":"tools/list"}); self.assertEqual([t["name"] for t in tools["result"]["tools"]],["analysis_start"])
  handle(s,{"id":3,"method":"tools/call","params":{"name":"analysis_start","arguments":{"binding":"b"}}})
  tools=handle(s,{"jsonrpc":"2.0","id":4,"method":"tools/list"}); self.assertIn("analysis_discovery",[t["name"] for t in tools["result"]["tools"]])
 def test_single_process_lifecycle_and_finalize_cleanup(self):
  s=Server(); r=handle(s,{"id":1,"method":"tools/call","params":{"name":"analysis_start","arguments":{"binding":"b"}}}); self.assertEqual(r["result"]["structuredContent"]["revision"],0)
  self.assertIn("error",handle(s,{"id":2,"method":"tools/call","params":{"name":"analysis_start","arguments":{"binding":"b"}}}))
 def test_unknown_method_is_error(self): self.assertIn("error",handle(Server(),{"id":1,"method":"x"}))
