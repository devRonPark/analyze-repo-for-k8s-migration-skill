"""Shared machine-readable values and lightweight JSON contract checks."""
from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "1.0"
MARKDOWN_VERSION_MARKER = "<!-- analyze-repo-for-kubernetes: report-contract=1.0 -->"
EVIDENCE_STATUSES = ("확인됨", "추정됨", "미확인", "상충됨")
READINESS_VERDICTS = ("설계 입력 충분", "추가 정보 필요", "분석 불가")
CONTAINERIZATION_VALUES = (
    "기존 컨테이너 정의 있음",
    "대체 이미지 빌드 방식",
    "컨테이너화 필요",
    "컨테이너화 불필요",
    "미확인",
)
CONFIGURATION_TIMING = (
    "빌드 시점",
    "배포 시점",
    "프로세스 시작 시점",
    "실행 중",
    "관리 시점",
    "미확인",
)
MODES = ("summary", "detailed")
COMMON_REQUIRED_FIELDS = (
    "schema_version",
    "mode",
    "components",
    "excluded_items",
    "missing_inputs",
    "evidence",
    "design_input_verdict",
)
MODE_REQUIRED_FIELDS = {
    "summary": COMMON_REQUIRED_FIELDS,
    "detailed": COMMON_REQUIRED_FIELDS + ("dependencies",),
}


def _validate_evidence(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{path} must be an array"]
    errors: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path} must be an object")
            continue
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{item_path}.status must be one of the current evidence statuses")
        if not isinstance(item.get("reference"), str) or not item["reference"].strip():
            errors.append(f"{item_path}.reference is required")
    return errors


def validate_json_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["JSON report must be an object"]

    errors: list[str] = []
    mode = payload.get("mode")
    required = MODE_REQUIRED_FIELDS.get(mode, COMMON_REQUIRED_FIELDS)
    for field in required:
        if field not in payload:
            errors.append(f"required JSON field is missing: {field}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if mode not in MODES:
        errors.append("mode must be summary or detailed")
    if payload.get("design_input_verdict") not in READINESS_VERDICTS:
        errors.append("design_input_verdict must be one current readiness verdict")

    for field in ("components", "dependencies", "excluded_items", "missing_inputs"):
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field} must be an array")
    if "evidence" in payload:
        errors.extend(_validate_evidence(payload["evidence"], "evidence"))
    if isinstance(payload.get("components"), list):
        for index, component in enumerate(payload["components"]):
            path = f"components[{index}]"
            if not isinstance(component, dict) or not isinstance(component.get("name"), str):
                errors.append(f"{path}.name is required")
            elif "evidence" in component:
                errors.extend(_validate_evidence(component["evidence"], f"{path}.evidence"))
    if isinstance(payload.get("dependencies"), list):
        for index, dependency in enumerate(payload["dependencies"]):
            path = f"dependencies[{index}]"
            if not isinstance(dependency, dict):
                errors.append(f"{path} must be an object")
                continue
            for field in ("source", "target"):
                if not isinstance(dependency.get(field), str) or not dependency[field].strip():
                    errors.append(f"{path}.{field} is required")
            if "evidence" in dependency:
                errors.extend(_validate_evidence(dependency["evidence"], f"{path}.evidence"))
    return errors
