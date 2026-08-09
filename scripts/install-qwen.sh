#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DEFAULT_SKILLS_DIR="$HOME/.qwen/skills"
SKILLS_DIR="${QWEN_SKILLS_DIR:-$DEFAULT_SKILLS_DIR}"
if [ -n "${QWEN_CONFIG_DIR:-}" ]; then
  CONFIG_ROOT="$QWEN_CONFIG_DIR"
else
  CONFIG_ROOT="$(dirname "$SKILLS_DIR")"
fi
TEMPORARY_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMPORARY_ROOT"' EXIT

python3 "$SOURCE_DIR/scripts/build_dist.py" --source-root "$SOURCE_DIR" --output "$TEMPORARY_ROOT/bundle"
python3 "$SOURCE_DIR/scripts/install_distribution.py" --bundle "$TEMPORARY_ROOT/bundle" --config-root "$CONFIG_ROOT"

echo "Qwen bundle 설치 완료: $CONFIG_ROOT/skills"
echo "MCP fragment: $CONFIG_ROOT/analyze-repo-for-kubernetes/opencode-mcp.json"
