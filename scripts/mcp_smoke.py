"""Provider-free MCP process, catalog, and stderr-isolation smoke test."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "runtime" / "python" / "launch_mcp.py"


def run(messages):
    completed = subprocess.run(
        [sys.executable, str(LAUNCHER)],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert not completed.stderr, completed.stderr
    return [json.loads(line) for line in completed.stdout.splitlines()]


def main():
    first = run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start_analysis", "arguments": {"binding": "smoke"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
    ])
    assert first[0]["result"]["capabilities"]["tools"]["listChanged"]
    assert [tool["name"] for tool in first[1]["result"]["tools"]] == ["start_analysis"]
    assert first[3]["method"] == "notifications/tools/list_changed"
    assert {"submit_discovery", "reopen_analysis"}.issubset({tool["name"] for tool in first[4]["result"]["tools"]})
    second = run([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert [tool["name"] for tool in second[0]["result"]["tools"]] == ["start_analysis"]
    print("MCP smoke: PASS")


if __name__ == "__main__":
    main()
