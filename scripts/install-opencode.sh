#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE_REAL="$(realpath -m "$SOURCE_DIR")"
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
    --allow-duplicates|--force)
      # Backward-compatible no-op. Duplicate locations are refreshed by default.
      shift
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

metadata_field() {
  python3 "$SOURCE_DIR/scripts/project_metadata.py" --root "$SOURCE_DIR" --field "$1"
}

SKILL_ID="$(metadata_field skill_id)"
AGENT_ID="$(metadata_field agent_id)"
if [ -n "$PROJECT_LOCAL" ]; then
  TARGET_ROOT="$PROJECT_LOCAL/.opencode/skill"
  AGENT_DIR="$PROJECT_LOCAL/.opencode/agent"
  COMMAND_DIR="$PROJECT_LOCAL/.opencode/command"
else
  TARGET_ROOT="${OPENCODE_SKILLS_DIR:-$HOME/.config/opencode/skill}"
  AGENT_DIR="$HOME/.config/opencode/agent"
  COMMAND_DIR="$HOME/.config/opencode/command"
fi
TARGET_DIR="$TARGET_ROOT/$SKILL_ID"
AGENT_PATH="$AGENT_DIR/$AGENT_ID.md"
COMMAND_PATH="$COMMAND_DIR/$SKILL_ID.md"

duplicate_paths=()
path_is_source() {
  [ "$(realpath -m "$1")" = "$SOURCE_REAL" ]
}

check_duplicate() {
  candidate="$1"
  if [ "$candidate" != "$TARGET_DIR" ] \
    && { [ -e "$candidate" ] || [ -L "$candidate" ]; } \
    && ! path_is_source "$candidate"; then
    duplicate_paths+=("$candidate")
  fi
}

check_duplicate "$HOME/.config/opencode/skills/$SKILL_ID"
check_duplicate "$HOME/.claude/skills/$SKILL_ID"
check_duplicate "$HOME/.agents/skills/$SKILL_ID"
if [ -n "$PROJECT_LOCAL" ]; then
  check_duplicate "$PROJECT_LOCAL/.opencode/skills/$SKILL_ID"
  check_duplicate "$PROJECT_LOCAL/.claude/skills/$SKILL_ID"
  check_duplicate "$PROJECT_LOCAL/.agents/skills/$SKILL_ID"
fi

if path_is_source "$TARGET_DIR"; then
  echo "오류: source checkout과 설치 대상이 같습니다: $TARGET_DIR" >&2
  echo "분리된 source checkout에서 설치를 실행해 주세요." >&2
  exit 1
fi

temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT
python3 "$SOURCE_DIR/scripts/build_dist.py" \
  --source-root "$SOURCE_DIR" \
  --output "$temporary_root/$SKILL_ID"

install_paths=("$TARGET_DIR" "${duplicate_paths[@]}")
for install_path in "${install_paths[@]}"; do
  mkdir -p "$(dirname "$install_path")"
  if [ -e "$install_path" ] || [ -L "$install_path" ]; then
    rm -rf "$install_path"
  fi
  cp -R "$temporary_root/$SKILL_ID" "$install_path"
done

mkdir -p "$AGENT_DIR" "$COMMAND_DIR"
cp "$SOURCE_DIR/runtime/agents/$AGENT_ID.md" "$AGENT_PATH"
cp "$SOURCE_DIR/runtime/commands/$SKILL_ID.md" "$COMMAND_PATH"

echo "OpenCode Skill 설치 완료: $TARGET_DIR"
echo "OpenCode Agent 등록 완료: $AGENT_PATH"
echo "OpenCode Command 등록 완료: /$SKILL_ID"
