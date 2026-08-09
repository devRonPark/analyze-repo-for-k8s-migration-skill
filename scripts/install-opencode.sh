#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROJECT_LOCAL=""

usage() {
  echo "사용법: $0 [--project-local PROJECT_ROOT]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-local)
      if [ "$#" -lt 2 ]; then usage; exit 2; fi
      PROJECT_LOCAL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [ -n "$PROJECT_LOCAL" ]; then
  CONFIG_ROOT="$PROJECT_LOCAL/.opencode"
else
  CONFIG_ROOT="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
fi

TEMPORARY_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMPORARY_ROOT"' EXIT
python3 "$SOURCE_DIR/scripts/build_dist.py" --source-root "$SOURCE_DIR" --output "$TEMPORARY_ROOT/bundle"
python3 "$SOURCE_DIR/scripts/install_distribution.py" --bundle "$TEMPORARY_ROOT/bundle" --config-root "$CONFIG_ROOT"

echo "OpenCode Skill 설치 완료: $CONFIG_ROOT/skills"
echo "OpenCode Agent 등록 완료: $CONFIG_ROOT/agent/kubernetes-migration-analyzer.md"
echo "OpenCode Command 등록 완료: $CONFIG_ROOT/command/analyze-repo-for-kubernetes.md"
echo "MCP fragment: $CONFIG_ROOT/analyze-repo-for-kubernetes/opencode-mcp.json"
