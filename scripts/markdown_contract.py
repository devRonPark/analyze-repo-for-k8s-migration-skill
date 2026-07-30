"""Load the declarative Markdown report structure contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contracts/markdown-report-contract.json"


def load(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    profiles = value.get("profiles") if isinstance(value, dict) else None
    if not isinstance(profiles, dict):
        raise ValueError("Markdown report contract requires profiles")
    return profiles


def profile(text: str, mode: str, legacy: bool, profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    profiles = profiles or load()
    key = f"legacy_{mode}" if legacy else mode
    value = profiles.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Markdown report contract has no {key} profile")
    return value
