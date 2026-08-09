"""Provider-free static MCP catalog and stderr-isolation smoke test."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "runtime" / "python" / "launch_mcp.py"


def run(messages, command_directory):
    completed = subprocess.run(
        [sys.executable, str(LAUNCHER)],
        cwd=command_directory,
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert not completed.stderr, completed.stderr
    return [json.loads(line) for line in completed.stdout.splitlines()]


def main():
    with tempfile.TemporaryDirectory(dir=Path(os.environ["SystemRoot"]) / "Temp") as temporary:
        target = Path(temporary) / "target"
        target.mkdir()
        subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
        (target / "README.md").write_text("smoke\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=target, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Smoke", "-c", "user.email=smoke@example.invalid", "commit", "-m", "fixture"], cwd=target, check=True, capture_output=True)
        responses = run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"target_path": ".", "mode": "summary"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        ], target)
    assert "listChanged" not in responses[0]["result"]["capabilities"]["tools"]
    names = [tool["name"] for tool in responses[1]["result"]["tools"]]
    assert len(names) == 12
    assert names == [tool["name"] for tool in responses[3]["result"]["tools"]]
    handoff = responses[2]["result"]["structuredContent"]
    assert handoff["next_skill"] == "analyze-k8s-discovery"
    print("MCP smoke: PASS")


if __name__ == "__main__":
    main()
