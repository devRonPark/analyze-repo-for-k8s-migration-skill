import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CodeReviewGraphConfigTests(unittest.TestCase):
    def test_codex_project_config_uses_repository_scope_and_inline_hooks(self):
        with (ROOT / ".codex" / "config.toml").open("rb") as config_file:
            config = tomllib.load(config_file)

        server = config["mcp_servers"]["code-review-graph"]
        self.assertEqual(server["cwd"], str(ROOT).replace("\\", "/"))
        self.assertEqual(server["args"][0], "serve")
        self.assertIn("--repo", server["args"])
        self.assertTrue(config["hooks"]["PostToolUse"])
        self.assertNotIn(".codex/hooks.json", str(config))

    def test_claude_project_config_has_valid_nested_post_tool_hook(self):
        config = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        hook_group = config["hooks"]["PostToolUse"][0]
        self.assertEqual(hook_group["matcher"], "Write|Edit|Bash")
        self.assertEqual(hook_group["hooks"][0]["type"], "command")

    def test_claude_mcp_config_is_project_rooted(self):
        config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["code-review-graph"]
        self.assertEqual(server["cwd"], str(ROOT))
        self.assertEqual(server["args"][0], "serve")
        self.assertIn("--repo", server["args"])


if __name__ == "__main__":
    unittest.main()
