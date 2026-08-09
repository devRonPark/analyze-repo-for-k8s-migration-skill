"""Load the single stage-payload contract source of truth."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "stage-payload-contracts.json"


def load_contracts(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_contract(stage: str, path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contracts = load_contracts(path)
    try:
        return contracts["stages"][stage]
    except KeyError as exc:
        raise ValueError("unknown_stage_contract") from exc
