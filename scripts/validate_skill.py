#!/usr/bin/env python3
"""Validate the structural contract of an OpenCode Agent Skill package."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    from scripts.project_metadata import load
except ModuleNotFoundError:  # Direct invocation: python3 scripts/validate_skill.py ...
    from project_metadata import load


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
NON_RUNTIME_DIRECTORIES = {".git", ".artifacts", "dist", "docs", "runtime", "tests"}
BUNDLE_SKILL_IDS = (
    "analyze-repo-for-kubernetes",
    "analyze-k8s-discovery",
    "analyze-k8s-execution",
    "analyze-k8s-relationships",
    "analyze-k8s-boundaries",
    "analyze-k8s-contracts",
    "analyze-k8s-finalize",
)
BUNDLE_STAGE_IDS = ("discovery", "execution", "relationships", "boundaries", "contracts")
BUNDLE_SKILL_POLICIES = {
    "analyze-repo-for-kubernetes": {"tools": ["start_analysis"], "references": []},
    "analyze-k8s-discovery": {
        "tools": ["list_target_paths", "read_evidence", "locate_evidence", "get_target_git_metadata", "submit_discovery"],
        "references": ["references/workflow.md", "references/language-discovery-rules.md", "references/payload-contract.json"],
    },
    "analyze-k8s-execution": {
        "tools": ["list_target_paths", "read_evidence", "locate_evidence", "get_target_git_metadata", "submit_execution"],
        "references": ["references/execution-rules.md", "references/payload-contract.json"],
    },
    "analyze-k8s-relationships": {
        "tools": ["list_target_paths", "read_evidence", "locate_evidence", "get_target_git_metadata", "submit_relationships"],
        "references": ["references/dependency-analysis.md", "references/payload-contract.json"],
    },
    "analyze-k8s-boundaries": {
        "tools": ["list_target_paths", "read_evidence", "locate_evidence", "get_target_git_metadata", "submit_boundaries"],
        "references": ["references/workload-boundary.md", "references/payload-contract.json"],
    },
    **{
        f"analyze-k8s-{stage}": {"tools": [], "references": ["references/payload-contract.json"]}
        for stage in BUNDLE_STAGE_IDS if stage not in {"discovery", "execution", "relationships", "boundaries"}
    },
    "analyze-k8s-finalize": {"tools": [], "references": []},
}


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


def validate_installed_skill(skill_path: Path, expected_name: str) -> list[str]:
    """Validate one sibling Skill without requiring repository metadata."""
    errors: list[str] = []
    package_root = skill_path.parent
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"SKILL.md is not valid UTF-8: {skill_path}"]
    frontmatter, frontmatter_errors = parse_frontmatter(skill_text)
    errors.extend(frontmatter_errors)
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if name != expected_name:
        errors.append(f"unexpected Skill name: {name or '<missing>'}")
    elif len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        errors.append("name must match ^[a-z0-9]+(-[a-z0-9]+)*$ and be 1-64 characters")
    if not description:
        errors.append("frontmatter requires description")
    elif len(description) > 1024:
        errors.append("description must be 1-1024 characters")
    elif XML_TAG_PATTERN.search(description):
        errors.append("description must not contain XML tags")
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


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bundle(root: Path) -> list[str]:
    """Validate the sealed seven-Skill artifact used by all client adapters."""
    root = root.resolve()
    errors: list[str] = []
    skills_root = root / "skills"
    observed = {path.name for path in skills_root.iterdir()} if skills_root.is_dir() else set()
    if observed != set(BUNDLE_SKILL_IDS):
        errors.append("bundle must contain exactly the declared sibling Skill inventory")
        return errors
    try:
        manifest = json.loads((root / "bundle-manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        errors.append("bundle manifest is missing or invalid")
        return errors
    if not isinstance(manifest, dict) or manifest.get("skills") != list(BUNDLE_SKILL_IDS):
        errors.append("bundle manifest Skill inventory does not match the static catalog")
    if not isinstance(manifest, dict) or manifest.get("skill_policies") != BUNDLE_SKILL_POLICIES:
        errors.append("bundle manifest Skill tool and reference policies do not match the static catalog")
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        errors.append("bundle manifest requires file digests")
    else:
        actual_files = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file() and path.name != "bundle-manifest.json"
        }
        if set(files) != set(actual_files):
            errors.append("bundle manifest file inventory does not match the artifact")
        for relative, path in actual_files.items():
            declared = files.get(relative)
            if (
                not isinstance(declared, dict)
                or declared.get("sha256") != file_sha256(path)
                or declared.get("size") != path.stat().st_size
            ):
                errors.append(f"bundle manifest digest mismatch: {relative}")
    try:
        contracts = json.loads((root / "contracts" / "stage-payload-contracts.json").read_text(encoding="utf-8"))
        stages = contracts["stages"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        errors.append("stage payload contract source is missing or invalid")
        stages = {}
    for skill_id in BUNDLE_SKILL_IDS:
        skill_path = skills_root / skill_id / "SKILL.md"
        if not skill_path.is_file():
            errors.append(f"bundle Skill is missing SKILL.md: {skill_id}")
            continue
        errors.extend(validate_installed_skill(skill_path, skill_id))
    for stage in BUNDLE_STAGE_IDS:
        projection_path = skills_root / f"analyze-k8s-{stage}" / "references" / "payload-contract.json"
        try:
            projection = json.loads(projection_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            errors.append(f"stage payload projection is missing or invalid: {stage}")
            continue
        expected = stages.get(stage, {})
        if projection != expected:
            errors.append(f"stage payload projection does not match the source contract: {stage}")
    required = (
        root / "runtime" / "python" / "launch_mcp.py",
        root / "agents" / "kubernetes-migration-analyzer.md",
        root / "commands" / "analyze-repo-for-kubernetes.md",
    )
    for path in required:
        if not path.is_file():
            errors.append(f"bundle required runtime file is missing: {path.relative_to(root)}")
    return errors


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
        metadata = load(package_root)
    except ValueError as error:
        return [str(error)]
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
    elif name != metadata.skill_id:
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

    root = Path(args.root)
    errors = validate_bundle(root) if (root / "skills").is_dir() else validate(root)
    if errors:
        return fail(errors)

    print("성공: 정적 Skill 번들 구조가 유효합니다." if (root / "skills").is_dir() else f"성공: {load(root.resolve()).skill_id} 패키지 구조가 유효합니다.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
