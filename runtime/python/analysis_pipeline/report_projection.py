"""Pure projection of accepted pipeline facts into canonical Markdown."""
from __future__ import annotations

import re
from typing import Any, Mapping

from scripts.markdown_contract import profile
from scripts.report_contract import MARKDOWN_VERSION_MARKER, SUMMARY_V2_MARKDOWN_VERSION_MARKER
from scripts.validate_report import (
    absence_marker_errors,
    component_briefing_errors,
    credential_literal_errors,
    dependency_and_readiness_errors,
    design_blocker_format_errors,
    detect_mode,
    detailed_evidence_slot_errors,
    disallowed_section_errors,
    evidence_semantic_errors,
    evidence_table_errors,
    false_absence_errors,
    has_valid_evidence,
    is_summary_v2,
    mode_specific_errors,
    overview_errors,
    readiness_blocker_errors,
)
from .stage_contracts import required_report_slot_ids
from .state import PipelineState


STATUS_LABEL = {
    "confirmed": "확인됨",
    "inferred": "추정됨",
    "unknown": "미확인",
    "conflicted": "상충됨",
    "not_applicable": "확인됨",
}
SUMMARY_SECTIONS = (
    "## 1. 결론", "## 2. 예상 Kubernetes 구성", "## 3. 관계와 운영 경계",
    "## 4. 열린 항목", "## 5. 핵심 근거",
)
DETAILED_SECTIONS = (
    "## 1. 분석 범위", "## 2. 배포 대상 후보", "## 3. 배포 대상별 실행 정보",
    "## 4. 구성과 관계", "## 5. 운영 환경 배포 근거", "## 6. 설정과 상태 상세",
    "## 7. 제외 항목과 설계 차단 항목 상세", "## 8. Kubernetes 설계 입력 상태",
)
SECRET_LITERAL = re.compile(r"(?i)\b(?:password|passwd|token|api[_ -]?key)\s*[:=]\s*(?!\[REDACTED\])[^\s,;]+")


def _claims(state: PipelineState, stage: str) -> dict[str, Mapping[str, Any]]:
    payload = state.outputs.get(stage)
    items = payload.get("claims") if isinstance(payload, Mapping) else None
    if not isinstance(items, list):
        raise ValueError("accepted report state is incomplete")
    return {
        claim["id"]: claim
        for claim in items
        if isinstance(claim, Mapping) and isinstance(claim.get("id"), str)
    }


def _references_for_claim(state: PipelineState, stage: str, claim_id: str) -> list[str]:
    claim = _claims(state, stage).get(claim_id)
    if not isinstance(claim, Mapping):
        raise ValueError("report claim is unavailable")
    evidence_ids = claim.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise ValueError("report claim lacks evidence")
    references: list[str] = []
    for evidence_id in evidence_ids:
        evidence = state.evidence.get(evidence_id)
        if not isinstance(evidence, Mapping):
            raise ValueError("report evidence is unavailable")
        location, line_range = evidence.get("location"), evidence.get("range")
        if not isinstance(location, str) or not isinstance(line_range, str):
            raise ValueError("report evidence is invalid")
        evidence_status = evidence.get("status")
        if evidence_status not in STATUS_LABEL:
            raise ValueError("report evidence status is invalid")
        if evidence_status == "unknown":
            absence = evidence.get("absence")
            if not isinstance(absence, Mapping):
                raise ValueError("unknown report evidence lacks absence descriptor")
            scope, glob, pattern = absence.get("scope"), absence.get("glob"), absence.get("pattern")
            if not isinstance(scope, str) or not isinstance(glob, str) or (pattern is not None and not isinstance(pattern, str)):
                raise ValueError("unknown report evidence has invalid absence descriptor")
            reference = f"검색(scope={scope}, pattern={pattern or glob}, result=없음)"
        else:
            reference = f"{location}:{line_range}"
        if reference not in references:
            references.append(reference)
    return references


def _references_for_fact(state: PipelineState, fact_ref: str) -> list[str]:
    parts = fact_ref.split("_", 2)
    if len(parts) != 3 or parts[0] != "fact":
        raise ValueError("report fact is invalid")
    return _references_for_claim(state, parts[1], parts[2])


def _slot_records(state: PipelineState, mode: str) -> dict[str, dict[str, str]]:
    payload = state.outputs.get("contracts")
    raw_slots = payload.get("report_slots") if isinstance(payload, Mapping) else None
    if not isinstance(raw_slots, list):
        raise ValueError("accepted report slots are unavailable")
    expected = required_report_slot_ids(mode)
    slots: dict[str, dict[str, str]] = {}
    for raw in raw_slots:
        if not isinstance(raw, Mapping):
            raise ValueError("accepted report slot is invalid")
        slot_id, status = raw.get("id"), raw.get("status")
        if not isinstance(slot_id, str) or status not in STATUS_LABEL or slot_id in slots:
            raise ValueError("accepted report slot is invalid")
        references: list[str] = []
        for fact_ref in raw.get("fact_refs", []):
            if not isinstance(fact_ref, str):
                raise ValueError("accepted report fact is invalid")
            references.extend(reference for reference in _references_for_fact(state, fact_ref) if reference not in references)
        for claim_id in raw.get("claim_ids", []):
            if not isinstance(claim_id, str):
                raise ValueError("accepted report claim is invalid")
            references.extend(reference for reference in _references_for_claim(state, "contracts", claim_id) if reference not in references)
        if not references:
            raise ValueError("accepted report slot lacks evidence")
        if status == "conflicted" and len(references) < 2:
            raise ValueError("conflicted report slot requires two evidence sources")
        slots[slot_id] = {"status": status, "reference": ", ".join(references)}
    if set(slots) != set(expected):
        raise ValueError("accepted report slots do not match mode")
    return slots


def _status(slots: Mapping[str, Mapping[str, str]], slot_id: str) -> str:
    value = slots.get(slot_id, {}).get("status", "unknown")
    return STATUS_LABEL[value]


def _reference(slots: Mapping[str, Mapping[str, str]], slot_id: str) -> str:
    value = slots.get(slot_id, {}).get("reference")
    if not isinstance(value, str) or not value:
        raise ValueError("report slot reference is unavailable")
    return value


def _slot_value(slots: Mapping[str, Mapping[str, str]], slot_id: str) -> str:
    status = slots[slot_id]["status"]
    return "해당 없음" if status == "not_applicable" else f"{slot_id}: {STATUS_LABEL[status]}"


def _verdict(slots: Mapping[str, Mapping[str, str]], components: list[str]) -> str:
    if not components:
        return "분석 불가"
    statuses = {slot["status"] for slot in slots.values()}
    return "추가 정보 필요" if statuses & {"unknown", "conflicted"} else "설계 입력 충분"


def _missing_inputs(slots: Mapping[str, Mapping[str, str]]) -> list[dict[str, str]]:
    return [
        {"slot_id": slot_id, "status": slot["status"], "reference": slot["reference"]}
        for slot_id, slot in slots.items()
        if slot["status"] in {"unknown", "conflicted"}
    ]


def project_report_payload(state: PipelineState, mode: str, target_metadata: Mapping[str, str]) -> dict[str, Any]:
    """Project only accepted state; no model prose or repository text enters the report."""
    if mode not in {"summary", "detailed"}:
        raise ValueError("invalid report mode")
    slots = _slot_records(state, mode)
    boundaries = state.outputs.get("boundaries", {})
    units = boundaries.get("workload_units", []) if isinstance(boundaries, Mapping) else []
    components = [str(unit["id"]) for unit in units if isinstance(unit, Mapping) and isinstance(unit.get("id"), str)]
    if not components:
        raise ValueError("accepted report requires workload unit")
    relationships = state.outputs.get("relationships", {})
    edges = relationships.get("graph_edges", []) if isinstance(relationships, Mapping) else []
    dependencies = [
        {"source": str(edge.get("source_process_id", "미확인")), "target": str(edge.get("target_id", "미확인"))}
        for edge in edges if isinstance(edge, Mapping)
    ]
    exclusions = boundaries.get("candidate_exclusions", []) if isinstance(boundaries, Mapping) else []
    return {
        "mode": mode,
        "scope": dict(target_metadata),
        "components": components,
        "dependencies": dependencies,
        "excluded_items": [str(item.get("candidate_id", "미확인")) for item in exclusions if isinstance(item, Mapping)],
        "slots": slots,
        "missing_inputs": _missing_inputs(slots),
        "design_input_verdict": _verdict(slots, components),
    }


def _summary(payload: Mapping[str, Any]) -> str:
    slots, components = payload["slots"], payload["components"]
    reference = _reference(slots, "deployment_targets")
    open_items = payload["missing_inputs"]
    lines = [
        "# Kubernetes 설계 입력 요약", "", "<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->", "",
        f"Target: {payload['scope'].get('Repository URL 또는 Local path', '.') } @ {payload['scope'].get('branch, tag 또는 commit', 'unknown')} | Skill: analyze-repo-for-kubernetes | Contract: 2.0 | Validation: pending", "",
        "## 1. 결론", "", f"- 판정: {payload['design_input_verdict']}",
        f"- 배포 대상: {', '.join(components)} — 근거: {reference}",
        f"- 주요 런타임 의존성: {', '.join(item['target'] for item in payload['dependencies']) or '없음'} — 근거: {_reference(slots, 'runtime_dependencies_state')}",
        f"- 열린 항목 요약: {'있음' if open_items else '없음'} — 근거: {_reference(slots, 'minimum_design_inputs')}", "",
        "## 2. 예상 Kubernetes 구성", "",
    ]
    for component in components:
        lines.append(
            f"- {component} — Repository 사실: 배포 대상 후보; 역할: {_slot_value(slots, 'build_image_start')}; "
            f"Kubernetes 해석: 승인된 workload 경계; 포트: {_slot_value(slots, 'reachable_port_or_path')}; "
            f"상태: {_slot_value(slots, 'minimum_design_inputs')}; 주요 의존성: {_slot_value(slots, 'runtime_dependencies_state')}; 근거: {reference}"
        )
    lines.extend(["", "## 3. 관계와 운영 경계", ""])
    if payload["dependencies"]:
        for dependency in payload["dependencies"]:
            lines.append(f"- {dependency['source']} → {dependency['target']} — Kubernetes 해석: 승인된 런타임 연결; 근거: {_reference(slots, 'runtime_dependencies_state')}")
    else:
        lines.append(f"- 없음 — Kubernetes 해석: 승인된 외부 런타임 연결 없음; 근거: {_reference(slots, 'runtime_dependencies_state')}")
    lines.extend(["", "## 4. 열린 항목", ""])
    if open_items:
        for item in open_items:
            label = "설계 차단"
            lines.append(f"- 분류: {label}; 항목: {item['slot_id']}; 영향: 전체; 근거: {item['reference']}")
    else:
        lines.append(f"- 분류: 배포 입력; 항목: 없음; 영향: 없음; 근거: {_reference(slots, 'credential_exposure')}")
    lines.extend(["", "## 5. 핵심 근거", "", f"- 판정: {_reference(slots, 'minimum_design_inputs')}"])
    return "\n".join(lines) + "\n"


def _property(name: str, value: str, status: str, reference: str) -> str:
    return f"- {name}: {value} — 상태: {status} / 근거: {reference}"


def _detailed(payload: Mapping[str, Any]) -> str:
    slots, components = payload["slots"], payload["components"]
    deployment_reference = _reference(slots, "deployment_targets")
    lines = ["# Kubernetes 설계 입력 상세 평가", "", "<!-- analyze-repo-for-kubernetes: report-contract=1.0 -->", "", "## 1. 분석 범위", ""]
    for key in ("대상 유형", "Repository URL 또는 Local path", "접근 방식", "확인된 저장소 루트", "branch, tag 또는 commit", "분석 경로", "출력 모드"):
        lines.append(f"- {key}: {payload['scope'].get(key, 'detailed' if key == '출력 모드' else '미확인')}")
    lines.extend(["", "### 핵심 요약", "", f"- 판정: {payload['design_input_verdict']}", f"- 배포 대상: {', '.join(components)}", f"- 최우선 차단 요소: {payload['missing_inputs'][0]['slot_id'] if payload['missing_inputs'] else '없음'}", f"- 최소 입력 누락: {'있음' if payload['missing_inputs'] else '없음'}", "", "## 2. 배포 대상 후보", ""])
    for component in components:
        lines.append(_property("배포 대상 후보", component, _status(slots, "deployment_targets"), deployment_reference))
    execution_fields = ("실행 형태", "경로", "언어", "프레임워크", "런타임", "패키지 관리자", "설치 명령", "빌드 명령", "이미지 빌드 명령", "운영 기동 명령", "컨테이너화", "프로토콜", "수신 포트", "상태 확인")
    configuration_fields = ("설정", "Secret", "쓰기 상태 또는 영속성", "적용 시점", "종료와 복구", "관찰 가능성")
    minimum_fields = ("workload.kind", "metadata.name", "image", "command", "args", "containerPort", "Service", "Ingress")
    lines.extend(["", "## 3. 배포 대상별 실행 정보", ""])
    for component in components:
        lines.extend([f"### 배포 대상: {component}", "", "#### 실행 정보", ""])
        for field in execution_fields:
            slot = "reachable_port_or_path" if field == "수신 포트" else "build_image_start"
            lines.append(_property(field, _slot_value(slots, slot), _status(slots, slot), _reference(slots, slot)))
        lines.extend(["", "#### 설정과 상태", ""])
        for field in configuration_fields:
            slot = {"적용 시점": "configuration_timing", "종료와 복구": "lifecycle_recovery", "관찰 가능성": "observability"}.get(field, "minimum_design_inputs")
            lines.append(_property(field, _slot_value(slots, slot), _status(slots, slot), _reference(slots, slot)))
        lines.extend(["", "#### Kubernetes 최소 설계 입력", ""])
        for field in minimum_fields:
            lines.append(_property(field, _slot_value(slots, "minimum_design_inputs"), _status(slots, "minimum_design_inputs"), _reference(slots, "minimum_design_inputs")))
        lines.extend(["", "#### 최소 입력 누락", ""])
        if payload["missing_inputs"]:
            for item in payload["missing_inputs"]:
                lines.append(_property(item["slot_id"], "추가 설계 입력 필요", STATUS_LABEL[item["status"]], item["reference"]))
        else:
            lines.append(_property("없음", "추가 입력 없음", "확인됨", _reference(slots, "minimum_design_inputs")))
        lines.append("")
    lines.extend(["## 4. 구성과 관계", "", "### Dependency matrix", ""])
    dependencies = payload["dependencies"] or [{"source": "없음", "target": "없음"}]
    for dependency in dependencies:
        lines.append(
            f"- 연결 workload: {dependency['source']}; 의존 대상: {dependency['target']}; 종류: 승인된 관계 상태; protocol 또는 mechanism: 미확인; endpoint 또는 configuration: 미확인; 적용 시점: 미확인; 실행 위치: 미확인; 기능 실행에 필요: 미확인; 확인된 실행 정의에서 사용 여부: 미확인; 공급 또는 관리 경계: 미확인; 상태 또는 영속성: 미확인; 근거: {_reference(slots, 'runtime_dependencies_state')}"
        )
    lines.extend(["", "### Text dependency graph", "", "```text"])
    lines.extend(f"{item['source']} --[승인된 관계 상태, 미확인, 미확인]--> {item['target']}" for item in dependencies)
    lines.extend(["```", "", "### 배포 대상 후보에서 제외한 항목", ""])
    exclusions = payload["excluded_items"]
    if exclusions:
        for exclusion in exclusions:
            lines.append(_property(exclusion, "승인된 후보 제외", _status(slots, "execution_conflicts"), _reference(slots, "execution_conflicts")))
    else:
        lines.append(_property("없음", "제외 항목 없음", "확인됨", deployment_reference))
    lines.extend(["", "## 5. 운영 환경 배포 근거", ""])
    for field in ("확인된 배포 선언", "저장소에서 확인한 기동 정의", "운영 환경 배포 기준 구성"):
        lines.append(_property(field, _slot_value(slots, "deployment_evidence"), _status(slots, "deployment_evidence"), _reference(slots, "deployment_evidence")))
    lines.extend(["", "## 6. 설정과 상태 상세", "", _property("승인된 설정·상태 슬롯", _slot_value(slots, "configuration_timing"), _status(slots, "configuration_timing"), _reference(slots, "configuration_timing")), "", "## 7. 제외 항목과 설계 차단 항목 상세", "", "### 설계 차단 항목", ""])
    if payload["missing_inputs"]:
        for item in payload["missing_inputs"]:
            lines.append(f"- 차단 항목: {item['slot_id']} 상태 확인 필요 — 범주: 기타 / 영향 범위: 전체 / 상태: {STATUS_LABEL[item['status']]} / 근거: {item['reference']}")
    else:
        lines.append(f"- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: {_reference(slots, 'minimum_design_inputs')}")
    lines.extend(["", "## 8. Kubernetes 설계 입력 상태", "", f"- 판정: {payload['design_input_verdict']}", f"- 이유: 승인된 report slot 상태에 따른 결정", f"- 판정을 뒷받침하는 근거: {_reference(slots, 'readiness_verdict')}"])
    return "\n".join(lines) + "\n"


def validate_markdown(text: str, mode: str, target_metadata: Mapping[str, str]) -> list[str]:
    """Validate the final in-memory bytes without touching a target repository."""
    if mode not in {"summary", "detailed"}:
        return ["invalid report mode"]
    if not isinstance(text, str) or not text.endswith("\n"):
        return ["report must be newline-terminated text"]
    detected = detect_mode(text)
    errors: list[str] = []
    if detected is None:
        errors.append("report heading does not match mode")
    elif detected != mode:
        errors.append("report heading does not match mode")
    for section in profile(mode, False)["sections"]:
        if section not in text:
            errors.append(f"report section is missing: {section}")
    verdicts = re.findall(r"(?m)^- 판정: (설계 입력 충분|추가 정보 필요|분석 불가)$", text)
    if not verdicts:
        errors.append("report has no explicit readiness verdict")
    elif len(set(verdicts)) > 1:
        errors.append("report readiness verdicts conflict")
    if not has_valid_evidence(text):
        errors.append("report has no valid evidence reference")
    errors.extend(evidence_table_errors(text))
    summary_v2 = mode == "summary" and is_summary_v2(text)
    if not summary_v2:
        errors.extend(component_briefing_errors(text, mode, False))
        errors.extend(evidence_semantic_errors(text))
        errors.extend(readiness_blocker_errors(text))
        if mode == "detailed":
            errors.extend(detailed_evidence_slot_errors(text))
            errors.extend(design_blocker_format_errors(text))
    errors.extend(absence_marker_errors(text))
    errors.extend(false_absence_errors(text, None))
    errors.extend(credential_literal_errors(text))
    errors.extend(overview_errors(text) if not summary_v2 else [])
    if summary_v2:
        from scripts.validate_report import summary_v2_errors
        errors.extend(summary_v2_errors(text))
    else:
        errors.extend(dependency_and_readiness_errors(text))
    errors.extend(disallowed_section_errors(text))
    errors.extend(mode_specific_errors(text, mode))
    marker = SUMMARY_V2_MARKDOWN_VERSION_MARKER if summary_v2 else MARKDOWN_VERSION_MARKER
    if marker not in text:
        errors.append("report contract marker is missing")
    if SECRET_LITERAL.search(text):
        errors.append("report contains an unredacted credential literal")
    if target_metadata.get("branch, tag 또는 commit") and str(target_metadata["branch, tag 또는 commit"]) not in text:
        errors.append("report target metadata is missing")
    return errors


def finalize_markdown(text: str, mode: str, target_metadata: Mapping[str, str]) -> str:
    errors = validate_markdown(text, mode, target_metadata)
    if errors:
        raise ValueError("invalid final report: " + "; ".join(errors))
    if mode == "summary":
        if text.count("Validation: pending") != 1:
            raise ValueError("summary receipt is invalid")
        text = text.replace("Validation: pending", "Validation: passed", 1)
    return text


def project_and_render(state: PipelineState, mode: str, target_metadata: Mapping[str, str]) -> str:
    payload = project_report_payload(state, mode, target_metadata)
    rendered = _summary(payload) if mode == "summary" else _detailed(payload)
    return finalize_markdown(rendered, mode, target_metadata)
