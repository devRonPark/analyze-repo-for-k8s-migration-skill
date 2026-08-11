import unittest
import json
from pathlib import Path

from analysis_pipeline.mcp_server import Server
from analysis_pipeline.protocol import TOOLS


class RetryProtocolCorrectionTests(unittest.TestCase):
    def test_undelivered_reopen_is_not_an_mcp_affordance(self) -> None:
        self.assertNotIn("reopen_analysis", {tool["name"] for tool in TOOLS})
        root = Path(__file__).resolve().parents[3]
        catalog = json.loads((root / "contracts" / "mcp-static-catalog.json").read_text(encoding="utf-8"))
        self.assertNotIn("reopen_analysis", catalog["tools"])

    def test_relationship_mechanism_error_names_the_wire_path_and_format(self) -> None:
        result = Server()._validation_error("invalid relationship mechanism")

        self.assertEqual(result["code"], "invalid_relationship_mechanism")
        self.assertTrue(result["retryable"])
        self.assertIn("payload.graph_edges[].mechanism", result["issues"][0])
        self.assertIn("^[A-Za-z][A-Za-z0-9_.-]{0,63}$", result["issues"][0])


if __name__ == "__main__":
    unittest.main()
