#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_LOCAL=""
ALLOW_DUPLICATES=0

usage() {
  echo "사용법: $0 [--project-local PROJECT_ROOT] [--allow-duplicates]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-local)
      if [ "$#" -lt 2 ]; then usage; exit 2; fi
      PROJECT_LOCAL="$2"
      shift 2
      ;;
    --allow-duplicates|--force)
      ALLOW_DUPLICATES=1
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

SKILL_ID="analyze-repo-for-kubernetes"
if [ -n "$PROJECT_LOCAL" ]; then
  TARGET_ROOT="$PROJECT_LOCAL/.opencode/skills"
else
  TARGET_ROOT="${OPENCODE_SKILLS_DIR:-$HOME/.config/opencode/skills}"
fi
TARGET_DIR="$TARGET_ROOT/$SKILL_ID"

duplicate_paths=()
check_duplicate() {
  candidate="$1"
  if [ "$candidate" != "$TARGET_DIR" ] && [ -e "$candidate" ]; then
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

if [ "$ALLOW_DUPLICATES" -eq 0 ] && [ "${#duplicate_paths[@]}" -gt 0 ]; then
  echo "오류: duplicate Skill installation detected:" >&2
  printf ' - %s\n' "${duplicate_paths[@]}" >&2
  echo "명시적으로 --allow-duplicates를 사용해야 계속할 수 있습니다." >&2
  exit 1
fi

temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT
python3 "$SOURCE_DIR/scripts/build_dist.py" \
  --source-root "$SOURCE_DIR" \
  --output "$temporary_root/$SKILL_ID"

mkdir -p "$TARGET_ROOT"
if [ -e "$TARGET_DIR" ] || [ -L "$TARGET_DIR" ]; then
  rm -rf "$TARGET_DIR"
fi
cp -R "$temporary_root/$SKILL_ID" "$TARGET_DIR"

echo "OpenCode Skill 설치 완료: $TARGET_DIR"
