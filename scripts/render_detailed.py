"""Render a validated Detailed payload as deterministic Markdown."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.report_contract import EVIDENCE_STATUSES, MARKDOWN_VERSION_MARKER, validate_json_payload
    from scripts.render_summary import (
        _component_evidence,
        _fallback_reference,
        _judgment,
        _property_line,
        _reference,
    )
    from scripts.validate_report import ABSENCE_REFERENCE as ABSENCE, FILE_LINE_REFERENCE as FILE_LINE
except ModuleNotFoundError:  # Direct invocation: python3 scripts/render_detailed.py ...
    from report_contract import EVIDENCE_STATUSES, MARKDOWN_VERSION_MARKER, validate_json_payload
    from render_summary import (
        _component_evidence,
        _fallback_reference,
        _judgment,
        _property_line,
        _reference,
    )
    from validate_report import ABSENCE_REFERENCE as ABSENCE, FILE_LINE_REFERENCE as FILE_LINE


EXECUTION_FIELDS = (
    "실행 형태", "경로", "언어", "프레임워크", "런타임", "패키지 관리자",
    "설치 명령", "빌드 명령", "이미지 빌드 명령", "운영 기동 명령",
    "컨테이너화", "프로토콜", "수신 포트", "상태 확인",
)
CONFIG_STATE_FIELDS = (
    "설정", "Secret", "쓰기 상태 또는 영속성", "적용 시점", "종료와 복구", "관찰 가능성",
)
MINIMUM_INPUT_FIELDS = (
    "workload.kind", "metadata.name", "image", "command", "args", "containerPort", "Service", "Ingress",
)
DEPENDENCY_FIELD_KEYS = (
    "종류", "protocol 또는 mechanism", "endpoint 또는 configuration", "적용 시점",
    "실행 위치", "기능 실행에 필요", "확인된 실행 정의에서 사용 여부",
    "공급 또는 관리 경계", "상태 또는 영속성",
)
DEPLOYMENT_BASIS_FIELDS = ("확인된 배포 선언", "저장소에서 확인한 기동 정의", "운영 환경 배포 기준 구성")
CONFIGURATION_DETAIL_FIELDS = (
    "연결 배포 대상", "목적", "적용 시점", "source 또는 injection 방식", "변경 효과",
    "Secret 여부", "쓰기 상태 또는 영속성", "종료와 복구", "관찰 가능성",
)
BLOCKER_CATEGORY_MAP = {
    "image": "이미지", "runtime": "runtime", "secret": "Secret",
    "external_dependency": "외부 의존성", "other": "기타",
}
BLOCKER_CATEGORIES = {"이미지", "Secret", "외부 의존성", "runtime", "기타"}
IMPACT_SCOPES = {"전체", "특정 배포 대상", "production 경로"}


def _scope_lines(scope: dict[str, Any]) -> list[str]:
    keys = (
        "대상 유형", "Repository URL 또는 Local path", "접근 방식",
        "확인된 저장소 루트", "branch, tag 또는 commit", "분석 경로", "출력 모드",
    )
    return [f"- {key}: {scope.get(key, 'detailed' if key == '출력 모드' else '미확인')}" for key in keys]


def _verdict(payload: dict[str, Any]) -> str:
    return payload.get("design_input_verdict", "추가 정보 필요")


def _blocker_description(item: Any) -> str:
    item = item if isinstance(item, dict) else {}
    return str(item.get("description") or item.get("key") or "없음")


def _core_summary_lines(payload: dict[str, Any]) -> list[str]:
    verdict = _verdict(payload)
    names = [str(c.get("name", "미확인")) for c in (payload.get("components") or [])]
    blockers = payload.get("missing_inputs") or []
    top_blocker = _blocker_description(blockers[0]) if blockers else "없음"
    has_missing = bool(blockers) or any(
        (component.get("missing_inputs") or []) for component in (payload.get("components") or []) if isinstance(component, dict)
    )
    return [
        "### 핵심 요약",
        "",
        f"- 판정: {verdict}",
        f"- 배포 대상: {', '.join(names) or '없음'}",
        f"- 최우선 차단 요소: {top_blocker}",
        f"- 최소 입력 누락: {'있음' if has_missing else '없음'}",
        "",
    ]


def _candidate_overview_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["## 2. 배포 대상 후보", ""]
    for component in payload.get("components") or []:
        name = str(component.get("name", "미확인"))
        evidence = _component_evidence(payload, component)
        lines.append(
            f"- 배포 대상 후보: {name} — 상태: {evidence.get('status')} / 근거: "
            f"{str(evidence.get('reference')).strip('`')}"
            f"{_judgment(evidence.get('status'), evidence.get('reason'))}"
        )
    lines.append("")
    return lines


def _missing_input_line(payload: dict[str, Any], component_name: str, item: dict[str, Any]) -> str:
    key = str(item.get("key", "미확인"))
    status = item.get("status", "미확인")
    if status not in {"확인됨", "미확인", "상충됨"}:
        raise ValueError(f"invalid missing_inputs status for {component_name}.{key}: {status}")
    if status == "미확인" and (not item.get("범위") or not item.get("결정")):
        raise ValueError(f"missing_inputs entry requires 범위/결정 for {component_name}.{key}")
    description = str(item.get("description", "추가 입력 필요"))
    scope = item.get("범위", component_name)
    decision = item.get("결정", "open decision")
    reference = _reference(payload, item.get("reference"), key, status)
    return (
        f"- {key}: {description}; 범위: {scope}; 결정: {decision} — 상태: {status} / 근거: {reference}"
        f"{_judgment(status, item.get('reason'))}"
    )


def _render_candidate_card(payload: dict[str, Any], component: dict[str, Any]) -> list[str]:
    name = str(component.get("name", "미확인"))
    lines = [f"### 배포 대상: {name}", "", "#### 실행 정보", ""]
    execution_info = component.get("execution_info") if isinstance(component.get("execution_info"), dict) else {}
    for key in EXECUTION_FIELDS:
        lines.append(_property_line(payload, key, execution_info.get(key, {})))
    lines.extend(["", "#### 설정과 상태", ""])
    configuration_state = component.get("configuration_state") if isinstance(component.get("configuration_state"), dict) else {}
    for key in CONFIG_STATE_FIELDS:
        lines.append(_property_line(payload, key, configuration_state.get(key, {})))
    lines.extend(["", "#### Kubernetes 최소 설계 입력", ""])
    minimum_inputs = component.get("minimum_inputs") if isinstance(component.get("minimum_inputs"), dict) else {}
    for key in MINIMUM_INPUT_FIELDS:
        lines.append(_property_line(payload, key, minimum_inputs.get(key, {})))
    lines.extend(["", "#### 최소 입력 누락", ""])
    missing = component.get("missing_inputs") or []
    if not missing:
        lines.append(f"- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: {_fallback_reference(payload, name)}")
    else:
        for item in missing:
            item = item if isinstance(item, dict) else {"key": str(item)}
            lines.append(_missing_input_line(payload, name, item))
    lines.append("")
    return lines


def _dependency_row(payload: dict[str, Any], dependency: dict[str, Any]) -> tuple[str, str]:
    source = str(dependency.get("source", "미확인"))
    target = str(dependency.get("target", "미확인"))
    fields = dependency.get("fields") if isinstance(dependency.get("fields"), dict) else {}

    def value(key: str) -> str:
        return str(fields.get(key, "미확인"))

    evidence_list = dependency.get("evidence")
    evidence = evidence_list[0] if isinstance(evidence_list, list) and evidence_list and isinstance(evidence_list[0], dict) else {}
    status = evidence.get("status", "미확인")
    if status not in EVIDENCE_STATUSES:
        status = "미확인"
    reference = _reference(payload, evidence.get("reference"), f"{source}-{target}", status)
    kind, timing, location = value("종류"), value("적용 시점"), value("실행 위치")
    bullet = (
        f"- 연결 workload: {source}; 의존 대상: {target}; 종류: {kind}; "
        f"protocol 또는 mechanism: {value('protocol 또는 mechanism')}; "
        f"endpoint 또는 configuration: {value('endpoint 또는 configuration')}; "
        f"적용 시점: {timing}; 실행 위치: {location}; "
        f"기능 실행에 필요: {value('기능 실행에 필요')}; "
        f"확인된 실행 정의에서 사용 여부: {value('확인된 실행 정의에서 사용 여부')}; "
        f"공급 또는 관리 경계: {value('공급 또는 관리 경계')}; "
        f"상태 또는 영속성: {value('상태 또는 영속성')}; 근거: {reference}"
    )
    graph_line = f"{source} --[{kind}, {timing}, {location}]--> {target}"
    return bullet, graph_line


def _fallback_dependency_row(payload: dict[str, Any]) -> tuple[str, str]:
    reference = _fallback_reference(payload, "dependencies")
    bullet = (
        "- 연결 workload: 없음; 의존 대상: 없음; 종류: 없음; protocol 또는 mechanism: 없음; "
        "endpoint 또는 configuration: 없음; 적용 시점: 미확인; 실행 위치: 미확인; "
        "기능 실행에 필요: 미확인; 확인된 실행 정의에서 사용 여부: 미확인; "
        f"공급 또는 관리 경계: 미확인; 상태 또는 영속성: 미확인; 근거: {reference}"
    )
    return bullet, "없음 --[없음, 미확인, 미확인]--> 없음"


def _dependency_matrix_and_graph(payload: dict[str, Any]) -> list[str]:
    dependencies = payload.get("dependencies") or []
    rows = [_dependency_row(payload, dependency) for dependency in dependencies if isinstance(dependency, dict)]
    if not rows:
        rows = [_fallback_dependency_row(payload)]
    bullets, graph_lines = zip(*rows)
    lines = ["### Dependency matrix", "", *bullets, "", "### Text dependency graph", "", "```text"]
    lines.extend(graph_lines)
    lines.extend(["```", ""])
    return lines


def _excluded_candidates_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["### 배포 대상 후보에서 제외한 항목", ""]
    excluded = payload.get("excluded_items") or []
    if not excluded:
        lines.append(f"- 없음: 제외 항목 없음 — 상태: 확인됨 / 근거: {_fallback_reference(payload, 'excluded_items')}")
    else:
        for value in excluded:
            item = value if isinstance(value, dict) else {"name": str(value)}
            name = str(item.get("name", "미확인"))
            reason = str(item.get("reason", item.get("description", "제외")))
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            status = evidence.get("status", "미확인")
            if status not in EVIDENCE_STATUSES:
                status = "미확인"
            reference = _reference(payload, evidence.get("reference"), name, status)
            lines.append(
                f"- {name}: {reason} — 상태: {status} / 근거: {reference}"
                f"{_judgment(status, evidence.get('reason'))}"
            )
    lines.append("")
    return lines


def _deployment_basis_lines(payload: dict[str, Any]) -> list[str]:
    basis = payload.get("deployment_basis") if isinstance(payload.get("deployment_basis"), dict) else {}
    lines = ["## 5. 운영 환경 배포 근거", ""]
    for key in DEPLOYMENT_BASIS_FIELDS:
        lines.append(_property_line(payload, key, basis.get(key, {})))
    lines.append("")
    return lines


def _configuration_detail_line(payload: dict[str, Any], item: dict[str, Any]) -> str:
    name = str(item.get("이름", "미확인"))
    status = item.get("status", "미확인")
    if status not in EVIDENCE_STATUSES:
        status = "미확인"
    reference = _reference(payload, item.get("reference"), name, status)
    detail = "; ".join(f"{field}={item.get(field, '미확인')}" for field in CONFIGURATION_DETAIL_FIELDS)
    return f"- {name}: {detail} — 상태: {status} / 근거: {reference}{_judgment(status, item.get('reason'))}"


def _configuration_details_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["## 6. 설정과 상태 상세", ""]
    details = payload.get("configuration_details") or []
    if not details:
        lines.append(f"- 없음: 추가 설정 없음 — 상태: 확인됨 / 근거: {_fallback_reference(payload, 'configuration_details')}")
    else:
        for item in details:
            if isinstance(item, dict):
                lines.append(_configuration_detail_line(payload, item))
    lines.append("")
    return lines


def _design_blockers_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["## 7. 제외 항목과 설계 차단 항목 상세", "", "### 설계 차단 항목", ""]
    blockers = payload.get("missing_inputs") or []
    verdict = _verdict(payload)
    if verdict == "추가 정보 필요" and not blockers:
        raise ValueError("추가 정보 필요 판정에는 missing_inputs가 필요합니다")
    if not blockers:
        lines.append(f"- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: {_fallback_reference(payload, 'blockers')}")
    else:
        for item in blockers:
            item = item if isinstance(item, dict) else {"key": str(item)}
            category = item.get("category", "기타")
            category = BLOCKER_CATEGORY_MAP.get(category, category)
            if category not in BLOCKER_CATEGORIES:
                raise ValueError(f"invalid blocker category: {item.get('category')}")
            impact = item.get("impact_scope", "전체")
            if impact not in IMPACT_SCOPES:
                impact = "전체"
            status = item.get("status", "미확인")
            if status not in EVIDENCE_STATUSES:
                status = "미확인"
            key = str(item.get("key", "missing"))
            reference = _reference(payload, item.get("reference"), key, status)
            description = _blocker_description(item)
            lines.append(
                f"- 차단 항목: {description} — 범주: {category} / 영향 범위: {impact} / "
                f"상태: {status} / 근거: {reference}{_judgment(status, item.get('reason'))}"
            )
    lines.append("")
    return lines


def _verdict_lines(payload: dict[str, Any]) -> list[str]:
    verdict = _verdict(payload)
    reason = payload.get("verdict_reason", "구조화된 분석 결과에 따른 판정")
    verdict_evidence = payload.get("verdict_evidence") or payload.get("evidence") or []
    references: list[str] = []
    for item in verdict_evidence:
        if not isinstance(item, dict):
            continue
        reference = str(item.get("reference", "")).strip("`")
        if FILE_LINE.search(reference) or ABSENCE.search(reference):
            references.append(reference)
    return [
        "## 8. Kubernetes 설계 입력 상태",
        "",
        f"- 판정: {verdict}",
        f"- 이유: {reason}",
        f"- 판정을 뒷받침하는 근거: {', '.join(references) or _fallback_reference(payload, 'verdict')}",
    ]


def render_detailed(payload: dict[str, Any]) -> str:
    """Render the Detailed contract from a validated JSON payload."""
    errors = validate_json_payload(payload)
    if errors:
        raise ValueError("invalid Detailed JSON: " + "; ".join(errors))
    if payload.get("mode") != "detailed":
        raise ValueError("renderer requires mode=detailed")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("detailed requires at least one component")

    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    lines = ["# Kubernetes 설계 입력 상세 평가", "", MARKDOWN_VERSION_MARKER, "", "## 1. 분석 범위", ""]
    lines.extend(_scope_lines(scope))
    lines.append("")
    lines.extend(_core_summary_lines(payload))
    lines.extend(_candidate_overview_lines(payload))
    lines.extend(["## 3. 배포 대상별 실행 정보", ""])
    for component in components:
        if isinstance(component, dict):
            lines.extend(_render_candidate_card(payload, component))
    lines.extend(["## 4. 구성과 관계", ""])
    lines.extend(_dependency_matrix_and_graph(payload))
    lines.extend(_excluded_candidates_lines(payload))
    lines.extend(_deployment_basis_lines(payload))
    lines.extend(_configuration_details_lines(payload))
    lines.extend(_design_blockers_lines(payload))
    lines.extend(_verdict_lines(payload))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Detailed JSON payload as Markdown.")
    parser.add_argument("payload", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        print(render_detailed(payload), end="")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"renderer error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
