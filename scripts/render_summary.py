"""Render a validated Summary payload as deterministic Markdown."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.report_contract import (
        EVIDENCE_STATUSES,
        MARKDOWN_VERSION_MARKER,
        validate_json_payload,
    )
    from scripts.validate_report import ABSENCE_REFERENCE as ABSENCE, FILE_LINE_REFERENCE as FILE_LINE
except ModuleNotFoundError:  # Direct invocation: python3 scripts/render_summary.py ...
    from report_contract import EVIDENCE_STATUSES, MARKDOWN_VERSION_MARKER, validate_json_payload
    from validate_report import ABSENCE_REFERENCE as ABSENCE, FILE_LINE_REFERENCE as FILE_LINE


CORE_FIELDS = (
    "실행 형태", "런타임", "빌드 명령", "운영 기동 명령", "이미지 빌드 명령",
    "컨테이너화", "프로토콜", "수신 포트", "설정", "Secret",
    "쓰기 상태 또는 영속성", "런타임 의존성",
)
MINIMUM_FIELDS = ("image", "command", "args", "containerPort")
def _fallback_reference(payload: dict[str, Any], key: str) -> str:
    for item in payload.get("evidence", []):
        if not isinstance(item, dict) or item.get("status") != "확인됨":
            continue
        if isinstance(item.get("reference"), str):
            reference = item["reference"].strip("`")
            if FILE_LINE.search(reference) or ABSENCE.search(reference):
                return reference
    return _absence_reference(payload, key)


def _absence_reference(payload: dict[str, Any], key: str) -> str:
    scope = payload.get("scope", {}).get("분석 경로", ".")
    return f"검색(scope={scope}, pattern={key}, result=없음)"


def _reference(payload: dict[str, Any], raw: Any, key: str, status: str) -> str:
    value = str(raw or "").strip("`")
    if status == "미확인":
        return value if ABSENCE.search(value) else _absence_reference(payload, key)
    if not (FILE_LINE.search(value) or ABSENCE.search(value)):
        raise ValueError(f"invalid evidence reference for {key}: {value}")
    if status == "상충됨" and len(FILE_LINE.findall(value)) + len(ABSENCE.findall(value)) < 2:
        raise ValueError(f"conflicting evidence needs two references for {key}: {value}")
    return value


def _field(payload: dict[str, Any], raw: Any, key: str) -> tuple[str, str, str, str, str | None]:
    item = raw if isinstance(raw, dict) else {"value": raw}
    status = item.get("status", "미확인")
    if status not in EVIDENCE_STATUSES:
        raise ValueError(f"invalid evidence status for {key}: {status}")
    value = str(item.get("value", "미확인"))
    reference = _reference(payload, item.get("reference"), key, status)
    return key, value, status, reference, item.get("reason")


def _judgment(status: str, reason: Any = None) -> str:
    if status == "추정됨":
        return f" / 판단: {reason or '복수 repository 신호에 따른 추정'}"
    return ""


def _property_line(payload: dict[str, Any], key: str, raw: Any) -> str:
    name, value, status, reference, reason = _field(payload, raw, key)
    line = f"- {name}: {value} — 상태: {status} / 근거: {reference}"
    return line + _judgment(status, reason)


def _scope_lines(scope: dict[str, Any]) -> list[str]:
    keys = (
        "대상 유형", "Repository URL 또는 Local path", "접근 방식",
        "확인된 저장소 루트", "branch, tag 또는 commit", "분석 경로", "출력 모드",
    )
    return [f"- {key}: {scope.get(key, 'summary' if key == '출력 모드' else '미확인')}" for key in keys]


def _component_evidence(payload: dict[str, Any], component: dict[str, Any]) -> dict[str, Any]:
    evidence = component.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict) or item.get("status") not in EVIDENCE_STATUSES:
                continue
            reference = _reference(payload, item.get("reference"), component.get("name", "component"), item["status"])
            return {**item, "reference": reference}
    return {"status": "미확인", "reference": _absence_reference(payload, component.get("name", "component"))}


def render_summary(payload: dict[str, Any]) -> str:
    errors = validate_json_payload(payload)
    if errors:
        raise ValueError("invalid Summary JSON: " + "; ".join(errors))
    if payload.get("mode") != "summary":
        raise ValueError("renderer requires mode=summary")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("summary requires at least one component")

    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    lines = ["# Kubernetes 설계 입력 요약", "", MARKDOWN_VERSION_MARKER, "", "## 1. 분석 범위", ""]
    lines.extend(_scope_lines(scope))
    lines.extend(["", "## 2. 배포 대상 후보와 주요 제외", ""])
    for component in components:
        name = str(component.get("name", "미확인"))
        candidate_evidence = _component_evidence(payload, component)
        lines.append(
            f"- 배포 대상 후보: {name} — 상태: {candidate_evidence.get('status')} / 근거: "
            f"{str(candidate_evidence.get('reference')).strip('`')}"
            f"{_judgment(candidate_evidence.get('status'), candidate_evidence.get('reason'))}"
        )
    excluded = payload.get("excluded_items") or []
    if excluded:
        for value in excluded:
            item = value if isinstance(value, dict) else {"name": str(value)}
            name = str(item.get("name", "미확인"))
            evidence = item.get("evidence", {})
            status = evidence.get("status", "미확인") if isinstance(evidence, dict) else "미확인"
            if status not in EVIDENCE_STATUSES:
                status = "미확인"
            reference = _reference(payload, evidence.get("reference") if isinstance(evidence, dict) else None, name, status)
            lines.append(
                f"- 주요 제외 항목: {name} — 상태: {status} / 근거: {reference}"
                f"{_judgment(status, evidence.get('reason') if isinstance(evidence, dict) else None)}"
            )
    else:
        lines.append(f"- 주요 제외 항목: 없음 — 상태: 확인됨 / 근거: {_fallback_reference(payload, 'excluded_items')}")

    lines.extend(["", "## 3. 배포 대상별 요약", ""])
    for component in components:
        name = str(component.get("name", "미확인"))
        lines.extend([f"### 배포 대상: {name}", "", "#### 핵심 입력", ""])
        fields = component.get("fields") if isinstance(component.get("fields"), dict) else {}
        for key in CORE_FIELDS:
            lines.append(_property_line(payload, key, fields.get(key, {})))
        lines.extend(["", "#### Kubernetes 최소 입력", ""])
        minimum = component.get("minimum_inputs") if isinstance(component.get("minimum_inputs"), dict) else {}
        for key in MINIMUM_FIELDS:
            lines.append(_property_line(payload, key, minimum.get(key, {})))
        lines.extend(["", "#### 최소 입력 누락", ""])
        missing = component.get("missing_inputs") or []
        if not missing:
            lines.append(f"- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: {_fallback_reference(payload, name)}")
        else:
            for item in missing:
                item = item if isinstance(item, dict) else {"key": str(item)}
                key = str(item.get("key", "미확인"))
                description = str(item.get("description", "추가 입력 필요"))
                lines.append(_property_line(payload, key, {**item, "value": description}))
        lines.append("")

    lines.extend(["## 4. Kubernetes 설계 입력 상태", ""])
    verdict = payload.get("design_input_verdict", "추가 정보 필요")
    lines.append(f"- 판정: {verdict}")
    lines.append(f"- 이유: {payload.get('verdict_reason', '구조화된 분석 결과에 따른 판정')}")
    verdict_evidence = payload.get("verdict_evidence") or payload.get("evidence") or []
    references = []
    for item in verdict_evidence:
        if not isinstance(item, dict):
            continue
        reference = str(item.get("reference", "")).strip("`")
        if FILE_LINE.search(reference) or ABSENCE.search(reference):
            references.append(reference)
    lines.append(f"- 판정을 뒷받침하는 근거: {', '.join(references) or _fallback_reference(payload, 'verdict')}")
    lines.extend(["", "### 설계 차단 항목", ""])
    blockers = payload.get("missing_inputs") or []
    if verdict == "추가 정보 필요" and not blockers:
        raise ValueError("추가 정보 필요 판정에는 missing_inputs가 필요합니다")
    if not blockers:
        lines.append(f"- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: {_fallback_reference(payload, 'blockers')}")
    else:
        for item in blockers:
            item = item if isinstance(item, dict) else {"key": str(item)}
            category = item.get("category", "기타")
            category = {"image": "이미지", "runtime": "runtime", "secret": "Secret"}.get(category, category)
            impact = item.get("impact_scope", "전체")
            if impact not in {"전체", "특정 배포 대상", "production 경로"}:
                impact = "전체"
            status = item.get("status", "미확인")
            if status not in EVIDENCE_STATUSES:
                status = "미확인"
            key = str(item.get("key", "missing"))
            reference = _reference(payload, item.get("reference"), key, status)
            description = item.get("description", item.get("key", "추가 입력"))
            lines.append(
                f"- 차단 항목: {description} — 범주: {category} / 영향 범위: {impact} / "
                f"상태: {status} / 근거: {reference}{_judgment(status, item.get('reason'))}"
            )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Summary JSON payload as Markdown.")
    parser.add_argument("payload", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        print(render_summary(payload), end="")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"renderer error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
