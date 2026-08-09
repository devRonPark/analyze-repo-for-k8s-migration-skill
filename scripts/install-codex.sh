#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CONFIG_ROOT="${CODEX_HOME:-$HOME/.codex}"
TEMPORARY_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMPORARY_ROOT"' EXIT

python3 "$SOURCE_DIR/scripts/build_dist.py" --source-root "$SOURCE_DIR" --output "$TEMPORARY_ROOT/bundle"
python3 "$SOURCE_DIR/scripts/install_distribution.py" --bundle "$TEMPORARY_ROOT/bundle" --config-root "$CONFIG_ROOT"

echo "Codex bundle 설치 완료: $CONFIG_ROOT/skills"
echo "MCP fragment: $CONFIG_ROOT/analyze-repo-for-kubernetes/opencode-mcp.json"
