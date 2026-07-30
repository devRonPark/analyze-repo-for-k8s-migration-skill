#!/usr/bin/env python3
"""Load the project identity shared by build, validation, and installation."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path


METADATA_PATH = Path("contracts/project-metadata.json")
FIELDS = ("skill_id", "agent_id", "skill_version", "manifest_name")


@dataclass(frozen=True)
class ProjectMetadata:
    skill_id: str
    agent_id: str
    skill_version: str
    manifest_name: str


def load(root: Path) -> ProjectMetadata:
    path = root / METADATA_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"project metadata is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"project metadata is not valid JSON: {path}: {error.msg}") from error

    if not isinstance(value, dict):
        raise ValueError("project metadata must be a JSON object")
    invalid = [field for field in FIELDS if not isinstance(value.get(field), str) or not value[field]]
    if invalid:
        raise ValueError(f"project metadata requires non-empty string fields: {', '.join(invalid)}")
    return ProjectMetadata(**{field: value[field] for field in FIELDS})


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a project metadata field.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--field", choices=FIELDS, required=True)
    args = parser.parse_args()
    try:
        print(getattr(load(args.root.resolve()), args.field))
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
