import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_dist import build
from scripts.mcp_smoke import isolated_launcher_command, isolated_runtime_environment


CONFIGS = Path(__file__).resolve().parents[2] / "configs"
ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "scripts" / "mcp_smoke.py"


class ClientConfigTests(unittest.TestCase):
    def test_templates_use_absolute_launcher_environment(self):
        for name in ("opencode-mcp.json", "claude-code-mcp.json", "gemini-cli-mcp.json"):
            config = json.loads((CONFIGS / name).read_text(encoding="utf-8"))
            server = config.get("mcp", {}).get("analysis") or config["mcpServers"]["analysis"]
            self.assertNotIn("cwd", server, name)
            command = server["command"] if isinstance(server["command"], list) else [server["command"]]
            rendered = " ".join([*command, *server.get("args", [])])
            self.assertIn("ANALYSIS_PIPELINE_PYTHON", rendered)
            self.assertIn("ANALYSIS_PIPELINE_LAUNCHER", rendered)

    def test_opencode_template_enables_the_local_server(self):
        config = json.loads((CONFIGS / "opencode-mcp.json").read_text(encoding="utf-8"))
        self.assertTrue(config["mcp"]["analysis"]["enabled"])

    def test_source_launcher_initializes_without_package_installation(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "runtime" / "python" / "launch_mcp.py")],
            cwd=ROOT,
            input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONUTF8": "1"},
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(completed.stderr, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["result"]["serverInfo"]["name"], "trusted-analysis-pipeline")

    def test_smoke_child_uses_an_isolated_interpreter_and_denies_network_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "network_probe.py"
            probe.write_text(
                "import socket\nsocket.create_connection(('198.18.0.1', 9), timeout=1)\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                isolated_launcher_command([sys.executable, str(probe)]),
                check=False,
                capture_output=True,
                text=True,
                env={**isolated_runtime_environment(), "PYTHONPATH": str(ROOT / "runtime" / "python")},
                timeout=30,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("network_disabled", completed.stderr)
        environment = isolated_runtime_environment()
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            self.assertNotIn(name, environment)

    def test_build_includes_all_portable_client_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = build(ROOT, Path(directory) / "bundle")
            for name in ("opencode-mcp.json", "claude-code-mcp.json", "gemini-cli-mcp.json"):
                self.assertTrue((bundle / "configs" / name).is_file(), name)

    def test_portable_smoke_uses_installed_launcher_for_every_template(self):
        with tempfile.TemporaryDirectory() as directory:
            config_root = Path(directory) / "isolated config"
            completed = subprocess.run(
                [sys.executable, str(SMOKE), "--config-root", str(config_root), "--all-clients"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONUTF8": "1"},
                timeout=60,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue((config_root / "analyze-repo-for-kubernetes" / "runtime" / "python" / "launch_mcp.py").is_file())
            for name in ("opencode-mcp.json", "claude-code-mcp.json", "gemini-cli-mcp.json"):
                self.assertIn(name, completed.stdout)
