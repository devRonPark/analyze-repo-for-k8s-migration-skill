import json
import unittest
from pathlib import Path


CONFIGS = Path(__file__).resolve().parents[2] / "configs"


class ClientConfigTests(unittest.TestCase):
    def test_templates_use_absolute_launcher_environment(self):
        for name in ("opencode-mcp.json", "claude-code-mcp.json", "gemini-cli-mcp.json"):
            config = json.loads((CONFIGS / name).read_text(encoding="utf-8"))
            server = config.get("mcp", {}).get("servers", {}).get("analysis") or config["mcpServers"]["analysis"]
            self.assertNotIn("cwd", server, name)
            command = server["command"] if isinstance(server["command"], list) else [server["command"]]
            rendered = " ".join([*command, *server.get("args", [])])
            self.assertIn("ANALYSIS_PIPELINE_PYTHON", rendered)
            self.assertIn("ANALYSIS_PIPELINE_LAUNCHER", rendered)
