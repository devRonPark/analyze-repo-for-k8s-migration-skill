#!/usr/bin/env python3
"""Validate the sealed static-evidence golden inputs for MCP acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_CASES = {
    ("jpetstore-6", "summary"): "static-mcp-jpetstore-6-summary-golden.md",
    ("jpetstore-6", "detailed"): "static-mcp-jpetstore-6-detailed-golden.md",
    ("flask-celery", "summary"): "static-mcp-flask-celery-summary-golden.md",
    ("flask-celery", "detailed"): "static-mcp-flask-celery-detailed-golden.md",
    ("fastapi-template", "summary"): "static-mcp-fastapi-template-summary-golden.md",
    ("fastapi-template", "detailed"): "static-mcp-fastapi-template-detailed-golden.md",
}
REQUIRED_GOLDEN_HEADINGS = (
    "## Required findings",
    "## Required blockers and unknowns",
    "## Scoring weights",
)


def canonical_text_sha256(path: Path) -> str:
    """Hash canonical Git text bytes despite checkout newline conversion."""
    canonical = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def sha256(path: Path) -> str:
    return canonical_text_sha256(path)


def validate_manifest(path: Path) -> list[str]:
    """Return deterministic errors for a closed target/mode golden manifest."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["golden manifest is missing"]
    except json.JSONDecodeError:
        return ["golden manifest is invalid JSON"]
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return ["golden manifest must use schema_version 1"]
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        return ["golden manifest cases must be an array"]

    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object")
            continue
        target, mode = case.get("target"), case.get("mode")
        key = (target, mode) if isinstance(target, str) and isinstance(mode, str) else None
        if key not in EXPECTED_CASES:
            errors.append(f"{prefix} has unknown target/mode")
            continue
        if key in seen:
            errors.append(f"{prefix} duplicates target/mode")
            continue
        seen.add(key)
        expected_golden = EXPECTED_CASES[key]
        if case.get("id") != f"{target}-{mode}":
            errors.append(f"{prefix} has invalid case id")
        if case.get("golden") != expected_golden:
            errors.append(f"{prefix} has invalid golden path")
            continue
        digest = case.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            errors.append(f"{prefix} has invalid sha256")
            continue
        golden = path.parent / expected_golden
        if not golden.is_file():
            errors.append(f"{prefix} golden file is missing")
            continue
        if sha256(golden) != digest:
            errors.append(f"{prefix} sha256 mismatch")
            continue
        text = golden.read_text(encoding="utf-8")
        if not text.startswith("# Static MCP Golden"):
            errors.append(f"{prefix} golden heading is invalid")
        if not all(heading in text for heading in REQUIRED_GOLDEN_HEADINGS):
            errors.append(f"{prefix} golden required sections are missing")

    missing = set(EXPECTED_CASES) - seen
    if missing:
        errors.append("golden manifest is missing target/mode cases: " + ", ".join(f"{target}/{mode}" for target, mode in sorted(missing)))
    if len(cases) != len(EXPECTED_CASES):
        errors.append("golden manifest must contain exactly six cases")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate static MCP golden digests.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests" / "evaluation" / "static-mcp-golden-manifest.json",
    )
    args = parser.parse_args()
    errors = validate_manifest(args.manifest)
    if errors:
        print("\n".join(errors))
        return 1
    print("Static MCP golden manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
