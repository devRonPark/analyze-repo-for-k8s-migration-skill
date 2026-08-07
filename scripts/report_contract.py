"""Read JSON report contract values from the authoritative JSON Schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MARKDOWN_VERSION_MARKER = "<!-- analyze-repo-for-kubernetes: report-contract=1.0 -->"
SUMMARY_V2_MARKDOWN_VERSION_MARKER = "<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/analysis-result.schema.json"


def load_contract(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """Extract the subset of JSON Schema enforced by the built-in validator."""
    schema = json.loads(path.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    required_by_mode = {
        branch["properties"]["mode"]["const"]: tuple(branch["required"])
        for branch in schema["oneOf"]
    }
    return {
        "schema_version": schema["properties"]["schema_version"]["const"],
        "modes": tuple(schema["properties"]["mode"]["enum"]),
        "required_by_mode": required_by_mode,
        "evidence_statuses": tuple(definitions["evidenceStatus"]["enum"]),
        "readiness_verdicts": tuple(schema["properties"]["design_input_verdict"]["enum"]),
        "containerization_values": tuple(definitions["containerization"]["enum"]),
        "configuration_timing": tuple(definitions["configurationTiming"]["enum"]),
        "evidence_required": tuple(definitions["evidence"]["required"]),
        "component_required": tuple(definitions["component"]["required"]),
        "dependency_required": tuple(definitions["dependency"]["required"]),
        "array_fields": tuple(name for name, value in schema["properties"].items() if value.get("type") == "array"),
    }


CONTRACT = load_contract()
SCHEMA_VERSION = CONTRACT["schema_version"]
EVIDENCE_STATUSES = CONTRACT["evidence_statuses"]
READINESS_VERDICTS = CONTRACT["readiness_verdicts"]
CONTAINERIZATION_VALUES = CONTRACT["containerization_values"]
CONFIGURATION_TIMING = CONTRACT["configuration_timing"]
MODES = CONTRACT["modes"]
MODE_REQUIRED_FIELDS = CONTRACT["required_by_mode"]
OPEN_ITEM_LABELS = {
    "hard_blocker": "설계 차단",
    "open_design_decision": "설계 결정",
    "deployment_value": "배포 입력",
    "recommendation": "권장 사항",
}


def _validate_evidence(value: Any, path: str, contract: dict[str, Any]) -> list[str]:
    if not isinstance(value, list):
        return [f"{path} must be an array"]
    errors: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path} must be an object")
            continue
        if item.get("status") not in contract["evidence_statuses"]:
            errors.append(f"{item_path}.status must be one of the current evidence statuses")
        for field in contract["evidence_required"]:
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{item_path}.{field} is required")
    return errors


def validate_json_payload(payload: Any, contract: dict[str, Any] = CONTRACT) -> list[str]:
    if not isinstance(payload, dict):
        return ["JSON report must be an object"]

    errors: list[str] = []
    mode = payload.get("mode")
    required = contract["required_by_mode"].get(mode, ())
    for field in required:
        if field not in payload:
            errors.append(f"required JSON field is missing: {field}")
    if payload.get("schema_version") != contract["schema_version"]:
        errors.append(f"schema_version must be {contract['schema_version']}")
    if mode not in contract["modes"]:
        errors.append("mode must be summary or detailed")
    if payload.get("design_input_verdict") not in contract["readiness_verdicts"]:
        errors.append("design_input_verdict must be one current readiness verdict")

    for field in contract["array_fields"]:
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field} must be an array")
    if "evidence" in payload:
        errors.extend(_validate_evidence(payload["evidence"], "evidence", contract))
    if isinstance(payload.get("components"), list):
        for index, component in enumerate(payload["components"]):
            path = f"components[{index}]"
            if not isinstance(component, dict):
                errors.append(f"{path} must be an object")
                continue
            for field in contract["component_required"]:
                if not isinstance(component.get(field), str) or not component[field].strip():
                    errors.append(f"{path}.{field} is required")
            if "evidence" in component:
                errors.extend(_validate_evidence(component["evidence"], f"{path}.evidence", contract))
    if isinstance(payload.get("dependencies"), list):
        for index, dependency in enumerate(payload["dependencies"]):
            path = f"dependencies[{index}]"
            if not isinstance(dependency, dict):
                errors.append(f"{path} must be an object")
                continue
            for field in contract["dependency_required"]:
                if not isinstance(dependency.get(field), str) or not dependency[field].strip():
                    errors.append(f"{path}.{field} is required")
            if "evidence" in dependency:
                errors.extend(_validate_evidence(dependency["evidence"], f"{path}.evidence", contract))
    if mode == "summary" and isinstance(payload.get("missing_inputs"), list):
        for index, item in enumerate(payload["missing_inputs"]):
            if isinstance(item, dict) and item.get("classification") == "recommendation":
                label = item.get("description") or item.get("key") or f"missing_inputs[{index}]"
                errors.append(
                    f"missing_inputs[{index}] classification must not be recommendation in Summary mode: {label}"
                )
    if mode == "detailed":
        errors.extend(detailed_json_errors(payload))
    return errors


DEPENDENCY_FIELD_KEYS = (
    "종류", "protocol 또는 mechanism", "endpoint 또는 configuration", "적용 시점",
    "실행 위치", "기능 실행에 필요", "확인된 실행 정의에서 사용 여부",
    "공급 또는 관리 경계", "상태 또는 영속성",
)
BLOCKER_CATEGORIES = {
    "image", "runtime", "secret", "external_dependency", "other",
    "이미지", "Secret", "외부 의존성", "기타",
}
IMPACT_SCOPES = {"전체", "특정 배포 대상", "production 경로"}


def detailed_json_errors(payload: dict[str, Any]) -> list[str]:
    """Detailed-specific field checks, mirroring validate_report.py's Markdown-level
    evidence_semantic_errors/readiness_blocker_errors rules at the JSON layer."""
    errors: list[str] = []

    for c_index, component in enumerate(payload.get("components") or []):
        if not isinstance(component, dict):
            continue
        for m_index, item in enumerate(component.get("missing_inputs") or []):
            if not isinstance(item, dict):
                continue
            key = item.get("key", f"missing_inputs[{m_index}]")
            status = item.get("status")
            path = f"components[{c_index}].missing_inputs[{m_index}]"
            if status == "추정됨":
                errors.append(f"{path}.status에는 추정됨을 사용할 수 없습니다: {key}")
            if status == "미확인" and (not item.get("범위") or not item.get("결정")):
                errors.append(f"{path}에 범위/결정이 필요합니다 (미확인): {key}")

    for d_index, dependency in enumerate(payload.get("dependencies") or []):
        if not isinstance(dependency, dict):
            continue
        fields = dependency.get("fields") if isinstance(dependency.get("fields"), dict) else {}
        for field in DEPENDENCY_FIELD_KEYS:
            if not str(fields.get(field, "")).strip():
                errors.append(f"dependencies[{d_index}].fields에 필수 키가 없습니다: {field}")

    for b_index, blocker in enumerate(payload.get("missing_inputs") or []):
        if not isinstance(blocker, dict):
            continue
        if blocker.get("category") not in BLOCKER_CATEGORIES:
            errors.append(f"missing_inputs[{b_index}]에 유효한 범주(category)가 없습니다")
        if blocker.get("impact_scope") not in IMPACT_SCOPES:
            errors.append(f"missing_inputs[{b_index}]의 impact_scope 값이 유효하지 않습니다")

    if payload.get("design_input_verdict") == "추가 정보 필요" and not payload.get("missing_inputs"):
        errors.append("design_input_verdict가 추가 정보 필요이면 missing_inputs가 최소 1개 필요합니다")

    return errors
