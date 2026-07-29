#!/usr/bin/env python3
"""Validate the structural contract of an OpenCode Agent Skill package."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
XML_TAG_PATTERN = re.compile(r"<\/?[A-Za-z][^>]*>")
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TBD|TODO|FIXME)\b")
FRONTMATTER_FIELD_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*):(?:[ \t]*(.*))?$")
FRONTMATTER_MAP_FIELD_PATTERN = re.compile(r"^\s{2,}[A-Za-z][A-Za-z0-9_.-]*:\s*.*$")

# These are runtime roles. README, development documents, tests, and legacy
# client adapters are not required merely because they exist in the checkout.
REQUIRED_RUNTIME_FILES = ("scripts/validate_report.py",)
NON_RUNTIME_DIRECTORIES = {".git", ".artifacts", "dist", "docs", "tests"}


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    """Parse the scalar fields needed by OpenCode without executing YAML."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}, ["SKILL.md frontmatter must start with ---"]

    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, ["SKILL.md frontmatter is not closed with ---"]

    values: dict[str, str] = {}
    errors: list[str] = []
    current_key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        match = FRONTMATTER_FIELD_PATTERN.match(line)
        if match and not line.startswith((" ", "\t")):
            key, value = match.groups()
            if key in values:
                errors.append(f"duplicate frontmatter field: {key}")
            values[key] = value or ""
            current_key = key
            continue
        if current_key == "metadata" and FRONTMATTER_MAP_FIELD_PATTERN.match(line):
            continue
        errors.append("frontmatter contains an unsupported or malformed line")

    return values, errors


def package_markdown_paths(root: Path, skill_path: Path) -> list[Path]:
    """Return Markdown files belonging to the runtime package, not development docs."""
    paths = {skill_path}
    for directory in ("references", "assets", "schemas"):
        candidate = root / directory
        if candidate.is_dir():
            paths.update(path for path in candidate.rglob("*.md") if path.is_file())
    return sorted(paths)


def validate_links(skill_path: Path, package_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return errors

    for target in LINK_PATTERN.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_path = target.split("#", 1)[0]
        relative = Path(target_path)
        candidate = (package_root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not candidate.is_relative_to(package_root.resolve()):
            errors.append(f"SKILL.md contains a non-direct relative link: {target_path}")
        elif not candidate.is_file():
            errors.append(f"broken SKILL.md link: {target_path}")
    return errors


def validate_code_fences(path: Path, text: str) -> list[str]:
    fence_character: str | None = None
    for line in text.splitlines():
        match = FENCE_PATTERN.match(line)
        if not match:
            continue
        marker = match.group(1)[0]
        if fence_character is None:
            fence_character = marker
        elif fence_character == marker:
            fence_character = None
    if fence_character is not None:
        return [f"unclosed code fence: {path}"]
    return []


def validate(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    skill_files = [
        path
        for path in root.rglob("SKILL.md")
        if path.is_file()
        and not any(part in NON_RUNTIME_DIRECTORIES for part in path.relative_to(root).parts[:-1])
    ]
    if len(skill_files) != 1:
        errors.append(f"SKILL.md must exist exactly once, found {len(skill_files)}")
        return errors

    skill_path = skill_files[0]
    package_root = skill_path.parent
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"SKILL.md is not valid UTF-8: {skill_path}")
        return errors

    frontmatter, frontmatter_errors = parse_frontmatter(skill_text)
    errors.extend(frontmatter_errors)
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")

    if not name:
        errors.append("frontmatter requires name")
    elif len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        errors.append("name must match ^[a-z0-9]+(-[a-z0-9]+)*$ and be 1-64 characters")
    elif name != "analyze-repo-for-kubernetes":
        errors.append(f"unexpected Skill name: {name}")

    if not description:
        errors.append("frontmatter requires description")
    elif len(description) > 1024:
        errors.append("description must be 1-1024 characters")
    elif XML_TAG_PATTERN.search(description):
        errors.append("description must not contain XML tags")

    # A checked-out source repository is not itself an OpenCode skill directory.
    # Distribution directories and nested Skill definitions must match the ID.
    if package_root.name != name and not (package_root == root and (root / ".git").exists()):
        errors.append("Skill name must match its containing directory")

    for relative in REQUIRED_RUNTIME_FILES:
        if not (package_root / relative).is_file():
            errors.append(f"required runtime file is missing: {relative}")

    errors.extend(validate_links(skill_path, package_root))
    for path in package_markdown_paths(package_root, skill_path):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"Markdown is not valid UTF-8: {path.relative_to(package_root)}")
            continue
        errors.extend(validate_code_fences(path.relative_to(package_root), text))
        if PLACEHOLDER_PATTERN.search(text):
            errors.append(f"placeholder found in runtime Markdown: {path.relative_to(package_root)}")

    return errors


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"실패: {error}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="스킬 패키지 구조를 검증합니다.")
    parser.add_argument("root", nargs="?", default=".", help="스킬 패키지 디렉터리")
    args = parser.parse_args()

    errors = validate(Path(args.root))
    if errors:
        return fail(errors)

    print("성공: analyze-repo-for-kubernetes 패키지 구조가 유효합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
