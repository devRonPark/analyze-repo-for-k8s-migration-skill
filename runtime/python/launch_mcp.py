"""Stable absolute-path launcher for the bundled MCP server."""
import sys
from pathlib import Path

if sys.version_info[:2] != (3, 13):
    raise SystemExit("trusted-analysis-pipeline requires Python 3.13")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_pipeline.mcp_server import main

COMMAND_DIRECTORY = Path.cwd()
main(command_directory=COMMAND_DIRECTORY)
