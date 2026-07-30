#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.report_contract import (  # noqa: E402
    MARKDOWN_VERSION_MARKER,
    OPEN_ITEM_LABELS,
    SUMMARY_V2_MARKDOWN_VERSION_MARKER,
    validate_json_payload,
)
from scripts.markdown_contract import profile  # noqa: E402

FIXTURES = {
    "no-dockerfile-monorepo": [
        "frontend", "api", "worker", "shared",
        "컨테이너화 필요", "PostgreSQL", "Redis", "RabbitMQ",
        "8009", "추가 정보 필요", "브라우저", "빌드 시점",
    ]
}

FILE_LINE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?P<path>(?:[A-Za-z0-9_.@+\-\[\]]+/)*[A-Za-z0-9_.@+\-\[\]]+):(?P<start>\d+)(?:-(?P<end>\d+))?(?=$|[`\s,;|)\]])"
)
ABSENCE_REFERENCE = re.compile(
    r"검색\(scope=.+,\s*pattern=.+,\s*result=없음\)"
)
# 부재 근거 marker를 번역하거나 표기를 바꾼 형태. 사용자 표시 식별자이므로 그대로 써야 한다.
ABSENCE_MARKER_ALIAS = re.compile(
    r"(?i)(?:搜索|検索|search|검색\s+|찾기)\s*\(\s*(?:scope|범위)="
)
COMPONENT_HEADING = re.compile(r"^### 구성 요소:\s*\S+", re.MULTILINE)
WORKLOAD_HEADING = re.compile(r"^### 배포 대상:\s*\S+", re.MULTILINE)
PROPERTY_LINE = re.compile(
    r"^- [^:\n]+:.+ — 상태: (확인됨|추정됨|미확인|상충됨) / 근거: (.+)$"
)
BLOCKER_LINE = re.compile(
    r"범주: (이미지|Secret|외부 의존성|runtime|기타) / "
    r"영향 범위: (전체|특정 배포 대상|production 경로) / "
    r"상태: (확인됨|추정됨|미확인|상충됨) / 근거: (.+)$"
)
CREDENTIAL_LITERAL = re.compile(
    r"(?i)\b(?:password|passwd|token|api[_ -]?key)\s*[:=]\s*(?!\[REDACTED\])[^\s,;]+"
)
KOREAN_CREDENTIAL_LITERAL = re.compile(
    r"(?:비밀번호|패스워드)\s+(?!값|정책|필드|없음|미확인|관련|입력|노출|문자열|변수|환경|value\b)[A-Za-z0-9][A-Za-z0-9_./+=-]*"
)


def detect_mode(text: str, legacy: bool = False) -> str | None:
    stripped = text.lstrip()
    if stripped.startswith("# Kubernetes 설계 입력 요약"):
        return "summary"
    if stripped.startswith("# Kubernetes 설계 입력 상세 평가"):
        return "detailed"
    if legacy and stripped.startswith("# Kubernetes 이관 요약"):
        return "summary"
    if legacy and stripped.startswith("# Kubernetes 이관 상세 평가"):
        return "detailed"
    return None


def has_valid_evidence(value: str) -> bool:
    return bool(FILE_LINE_REFERENCE.search(value) or ABSENCE_REFERENCE.search(value))


def is_summary_v2(text: str) -> bool:
    return SUMMARY_V2_MARKDOWN_VERSION_MARKER in text


def summary_v2_errors(text: str) -> list[str]:
    errors: list[str] = []
    sections = profile("summary", False)["sections"]
    positions = [text.find(section) for section in sections]
    if any(position == -1 for position in positions) or positions != sorted(positions):
        errors.append("Summary v2 섹션 순서가 계약과 다릅니다")
    first_lines = [line for line in text.splitlines() if line.strip()][:20]
    for field in ("판정:", "배포 대상:", "주요 런타임 의존성:", "열린 항목 요약:"):
        if not any(field in line for line in first_lines):
            errors.append(f"Summary v2 첫 화면에 필수 값이 없습니다: {field[:-1]}")
    overview = text.partition("## 2. 예상 Kubernetes 구성")[2].partition("## 3. 관계와 운영 경계")[0]
    required = ("Repository 사실:", "역할:", "Kubernetes 해석:", "포트:", "상태:", "주요 의존성:", "근거:")
    if not any(line.startswith("- ") and all(field in line for field in required) for line in overview.splitlines()):
        errors.append("Summary v2 배포 개요 bullet에 필수 필드가 없습니다")
    labels = tuple(OPEN_ITEM_LABELS.values())
    open_section = text.partition("## 4. 열린 항목")[2].partition("## 5. 핵심 근거")[0]
    open_rows = [line for line in open_section.splitlines() if line.startswith("- 분류:")]
    if any(not any(f"분류: {label};" in row for label in labels) for row in open_rows):
        errors.append("열린 항목 분류가 유효하지 않습니다")
    for line in text.splitlines():
        if not line.startswith("- ") or "근거:" not in line:
            continue
        if not has_valid_evidence(line.rpartition("근거:")[2]):
            errors.append(f"근거에 file:line 또는 검색(...)이 없습니다: {line}")
    verdict = re.search(r"(?m)^- 판정: (설계 입력 충분|추가 정보 필요|분석 불가)$", text)
    has_blocker = any(f"분류: {OPEN_ITEM_LABELS['hard_blocker']};" in row for row in open_rows)
    if verdict and ((verdict.group(1) == "추가 정보 필요" and not has_blocker) or (verdict.group(1) == "설계 입력 충분" and has_blocker)):
        errors.append("판정과 hard_blocker 분류가 일치하지 않습니다")
    return errors


def repository_relative_hint(root: Path, name: str, limit: int = 3) -> str:
    """같은 이름의 파일이 저장소에 있으면 저장소 상대 경로를 알려 준다."""
    matches: list[str] = []
    for candidate in root.rglob(name):
        if candidate.is_file() and ".git" not in candidate.parts:
            matches.append(candidate.relative_to(root).as_posix())
            if len(matches) > limit:
                return ""
    if not matches:
        return ""
    return " (저장소 상대 경로로 인용하세요: " + ", ".join(sorted(matches)) + ")"


def repository_reference_errors(text: str, repository_root: Path | None) -> list[str]:
    """--repo-root가 주어진 경우 positive evidence의 파일과 줄 범위를 검증한다."""
    if repository_root is None:
        return []

    errors: list[str] = []
    root = repository_root.resolve()
    # `redis-cart:6379` 같은 endpoint는 file:line과 표기가 같으므로,
    # 실제 인용 필드인 `근거:` 뒤에 있는 값만 검사한다.
    evidence_values = [line.split("근거:", 1)[1] for line in text.splitlines() if "근거:" in line]
    for evidence in evidence_values:
        for reference in FILE_LINE_REFERENCE.finditer(evidence):
            relative_path = Path(reference.group("path"))
            # 서비스 endpoint(`shoppingassistantservice:80`)는 근거 문장 안에
            # 있을 수 있지만 file:line 인용은 아니다. 경로 구분자나 확장자가
            # 없는 소문자 단일 이름은 파일 인용으로 해석하지 않는다.
            bare_name = relative_path.name
            if "/" not in reference.group("path") and "." not in bare_name and bare_name not in {"Dockerfile", "Makefile", "README", "LICENSE"}:
                continue
            candidate = (root / relative_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"저장소 밖 경로를 인용했습니다: {reference.group(0)}")
                continue
            if not candidate.is_file():
                hint = repository_relative_hint(root, bare_name)
                errors.append(f"인용 파일이 저장소에 없습니다: {reference.group(0)}{hint}")
                continue
            line_count = len(candidate.read_text(encoding="utf-8", errors="replace").splitlines())
            start = int(reference.group("start"))
            end = int(reference.group("end") or start)
            if start < 1 or end < start or end > line_count:
                errors.append(
                    f"인용 줄 범위가 파일 범위를 벗어났습니다: {reference.group(0)} "
                    f"(파일 줄 수: {line_count})"
                )
    return errors


def evidence_table_errors(text: str) -> list[str]:
    """관계 표처럼 남아 있는 표의 근거 셀도 검사한다."""
    errors: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        header = lines[index]
        if not header.lstrip().startswith("|"):
            index += 1
            continue
        columns = [cell.strip() for cell in header.strip().strip("|").split("|")]
        evidence_column = next(
            (position for position, column in enumerate(columns) if column.startswith("근거")),
            None,
        )
        if evidence_column is None or index + 1 >= len(lines):
            index += 1
            continue
        separator = lines[index + 1].strip()
        if not separator.startswith("|") or "-" not in separator:
            index += 1
            continue
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            if any(cell for position, cell in enumerate(row) if position != evidence_column):
                evidence = row[evidence_column] if evidence_column < len(row) else ""
                if not has_valid_evidence(evidence):
                    errors.append(f"{index + 1}행 근거 셀에 file:line 또는 검색(...) 근거가 없습니다")
            index += 1
    return errors


def component_cards(text: str) -> list[tuple[str, str]]:
    headings = list(COMPONENT_HEADING.finditer(text)) + list(WORKLOAD_HEADING.finditer(text))
    headings.sort(key=lambda heading: heading.start())
    cards: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        next_top_level = text.find("\n## ", heading.end())
        if next_top_level != -1 and next_top_level < end:
            end = next_top_level
        cards.append((heading.group(0), text[heading.end():end]))
    return cards


def component_briefing_errors(text: str, mode: str, legacy: bool) -> list[str]:
    """구성 요소마다 분류된 key:value 속성과 속성별 근거를 요구한다."""
    errors: list[str] = []
    cards = component_cards(text)
    if not cards:
        return ["구성 요소별 배포 브리핑에 구성 요소 카드가 없습니다"]

    card = profile(mode, legacy).get("card")
    if not isinstance(card, dict):
        return []
    categories = card["categories"]
    required_properties = card["properties"]
    minimum_fields = card["minimum_fields"]
    minimum_heading = card["minimum_heading"]

    for heading, card in cards:
        for category in categories:
            if category not in card:
                errors.append(f"{heading}에 범주가 없습니다: {category[5:]}")
        for property_name in required_properties:
            if property_name not in card:
                errors.append(f"{heading}에 필수 속성이 없습니다: {property_name[:-1]}")

        minimum_start = card.find(minimum_heading)
        missing_start = card.find("#### 최소 입력 누락")
        minimum = card[minimum_start:missing_start] if minimum_start != -1 and missing_start != -1 else ""
        missing = card[missing_start:] if missing_start != -1 else ""
        for property_name in minimum_fields:
            if property_name not in minimum and property_name not in missing:
                errors.append(f"{heading}에 최소 초안 값 또는 최소 입력 누락이 없습니다: {property_name[:-1]}")

        for line in card.splitlines():
            if not line.startswith("- "):
                continue
            match = PROPERTY_LINE.match(line)
            if not match:
                errors.append(f"{heading}의 속성이 key: value — 상태 / 근거 형식이 아닙니다: {line}")
                continue
            if not has_valid_evidence(match.group(2)):
                errors.append(f"{heading}의 속성 근거에 file:line 또는 검색(...)이 없습니다: {line}")
    return errors


def evidence_semantic_errors(text: str) -> list[str]:
    """Validate the extra information required by each evidence state."""
    errors: list[str] = []
    state_pattern = re.compile(
        r"— 상태: (확인됨|추정됨|미확인|상충됨) / 근거: (?P<evidence>.+)$"
    )
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        match = state_pattern.search(line)
        if not match:
            continue
        state = match.group(1)
        evidence = match.group("evidence")
        if state == "추정됨" and "/ 판단:" not in line:
            errors.append(f"추정됨 근거에 판단 이유가 없습니다: {line}")
        if state == "미확인" and not ABSENCE_REFERENCE.search(evidence):
            errors.append(f"미확인 근거에 확인 범위와 부족한 정보가 없습니다: {line}")
        if state == "상충됨":
            references = FILE_LINE_REFERENCE.findall(evidence)
            absence_count = len(ABSENCE_REFERENCE.findall(evidence))
            if len(references) + absence_count < 2:
                errors.append(f"상충됨 근거에 양쪽 source가 보존되지 않았습니다: {line}")
    return errors


def absence_marker_errors(text: str) -> list[str]:
    """부재 근거 marker가 번역되거나 표기가 바뀐 줄을 거부한다."""
    errors: list[str] = []
    for line in text.splitlines():
        if "근거:" not in line or not ABSENCE_MARKER_ALIAS.search(line):
            continue
        errors.append(
            "부재 근거는 검색(scope=<범위>, pattern=<패턴>, result=없음) 형식이어야 합니다: "
            f"{line}"
        )
    return errors


def credential_literal_errors(text: str) -> list[str]:
    """Reject values that must be redacted from a repository analysis report."""
    errors: list[str] = []
    for line in text.splitlines():
        if CREDENTIAL_LITERAL.search(line) or KOREAN_CREDENTIAL_LITERAL.search(line):
            errors.append(f"credential literal must be redacted: {line}")
    return errors


def detailed_evidence_slot_errors(text: str) -> list[str]:
    """Require each Detailed minimum-input slot to reach a usable terminal state."""
    errors: list[str] = []
    for heading, card in component_cards(text):
        start = card.find("#### 최소 입력 누락")
        if start == -1:
            continue
        entries = [line for line in card[start:].splitlines() if line.startswith("- ")]
        if not entries:
            errors.append(f"{heading}에 최소 입력 누락 evidence slot이 없습니다")
            continue
        for entry in entries:
            match = re.search(r"— 상태: (확인됨|추정됨|미확인|상충됨) / 근거:", entry)
            if not match:
                continue
            state = match.group(1)
            if state == "추정됨":
                errors.append(f"{heading}의 최소 입력 누락 evidence slot이 종료되지 않았습니다: {entry}")
            if state == "미확인" and ("범위:" not in entry or "결정:" not in entry):
                errors.append(f"{heading}의 미확인 최소 입력에는 범위와 결정이 필요합니다: {entry}")
    return errors


def design_blocker_lines(text: str) -> list[str]:
    """`### 설계 차단 항목` 절의 bullet만 돌려준다."""
    section = text.split("### 설계 차단 항목", 1)
    if len(section) == 1:
        return []
    body = section[1].split("\n## ", 1)[0]
    return [line for line in body.splitlines() if line.startswith("- ")]


def design_blocker_format_errors(text: str) -> list[str]:
    """차단 항목 bullet이 keyed 형식을 지키는지 판정과 무관하게 검사한다."""
    errors: list[str] = []
    for line in design_blocker_lines(text):
        match = BLOCKER_LINE.search(line)
        if not line.startswith("- 차단 항목:") or not match or not has_valid_evidence(match.group(4)):
            errors.append(f"설계 차단 항목은 차단 항목·범주·영향 범위·상태·근거 형식이어야 합니다: {line}")
    return errors


def readiness_blocker_errors(text: str) -> list[str]:
    verdicts = re.findall(r"(?m)^- 판정: (설계 입력 충분|추가 정보 필요|분석 불가)$", text)
    if set(verdicts) != {"추가 정보 필요"}:
        return []
    errors: list[str] = []
    blocker_lines = [line for line in design_blocker_lines(text) if line.startswith("- 차단 항목:")]
    if not blocker_lines or any("차단 항목: 없음" in line for line in blocker_lines):
        return ["추가 정보 필요 판정에는 구체적인 설계 차단 항목이 필요합니다"]
    for line in blocker_lines:
        match = BLOCKER_LINE.search(line)
        if not match or not has_valid_evidence(match.group(4)):
            errors.append(f"설계 차단 항목에 범주·영향 범위·상태·근거가 없습니다: {line}")
    return errors


def disallowed_section_errors(text: str) -> list[str]:
    errors: list[str] = []
    for label in ["## 다음 작업", "다음 인계:"]:
        if label in text:
            errors.append(f"출력하면 안 되는 작업 계획 항목이 있습니다: {label}")
    return errors


def dependency_and_readiness_errors(text: str) -> list[str]:
    errors: list[str] = []
    summary_contract = "## 3. 배포 대상별 요약" in text
    new_contract = "## 3. 배포 대상별 실행 정보" in text
    dependency_fields = (
        ["런타임 의존성:"] if summary_contract
        else ["기능 실행에 필요", "공급 또는 관리 경계"] if new_contract
        else ["애플리케이션 필수 여부", "선택한 배포 구성에서 필요"]
    )
    for field in dependency_fields:
        if field not in text:
            errors.append(f"의존성 필요 여부 필드가 없습니다: {field}")
    headings = ["### 설계 차단 항목"] if (new_contract or summary_contract) else ["### Readiness 차단 요인", "### 일반 운영 권장사항"]
    for heading in headings:
        if heading not in text:
            errors.append(f"최종 판정에 필수 구분이 없습니다: {heading[4:]}")
    return errors


def mode_specific_errors(text: str, mode: str | None) -> list[str]:
    errors: list[str] = []
    if mode == "summary" and ("## 3. 배포 대상별 요약" in text or is_summary_v2(text)):
        for marker in [
            "### Dependency matrix",
            "### Text dependency graph",
            "## 5. 운영 환경 배포 근거",
            "## 6. 설정과 상태 상세",
            "## 7. 제외 항목과 설계 차단 항목 상세",
            "종료와 복구:",
            "관찰 가능성:",
        ]:
            if marker in text:
                errors.append(f"summary 모드에 Detailed 전용 항목이 있습니다: {marker}")
    if mode == "detailed" and (
        "## 3. 배포 대상별 실행 정보" in text
        or "## 3. 구성 요소별 배포 브리핑" in text
    ):
        for heading in ["### Dependency matrix", "### Text dependency graph"]:
            if "## 3. 배포 대상별 실행 정보" in text and heading not in text:
                errors.append(f"detailed 모드에 필수 관계 표현이 없습니다: {heading[4:]}")
            elif "## 3. 구성 요소별 배포 브리핑" in text and heading not in text:
                errors.append(f"detailed 모드에 필수 관계 표현이 없습니다: {heading[4:]}")
    return errors


def overview_errors(text: str) -> list[str]:
    errors: list[str] = []
    summary_contract = "## 3. 배포 대상별 요약" in text
    new_contract = "## 3. 배포 대상별 실행 정보" in text
    if summary_contract:
        overview = text.split("## 3. 배포 대상별 요약", 1)[0]
        for field in ["배포 대상 후보:", "주요 제외 항목:"]:
            if field not in overview:
                errors.append(f"후보와 주요 제외에 필수 키가 없습니다: {field[:-1]}")
        return errors
    required = [
        "배포 가능한 구성 요소:",
        "기본 배포 구성:",
        "제외한 선택·개발용 구성:",
        "제외한 주요 package:",
        "확인된 수신 포트:",
        "적용을 막는 최소 입력 누락:",
    ]
    if new_contract:
        return []
    overview = text.split("## 3. 구성 요소별 배포 브리핑", 1)[0]
    for field in required:
        if field not in overview:
            errors.append(f"한눈에 보기에 필수 키가 없습니다: {field[:-1]}")
    return errors


def validate_json_file(path: Path, requested_mode: str, legacy: bool) -> tuple[str | None, list[str]]:
    if legacy:
        return None, ["JSON reports do not support --legacy mode"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [f"JSON report를 읽을 수 없습니다: {error}"]
    errors = validate_json_payload(payload)
    detected = payload.get("mode") if isinstance(payload, dict) else None
    if requested_mode != "auto" and detected != requested_mode:
        errors.append(f"JSON report mode는 {detected}이지만 요청 모드는 {requested_mode}입니다")
    return detected if detected in {"summary", "detailed"} else None, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="생성된 Kubernetes 이관 보고서를 검증합니다.")
    parser.add_argument("report", help="생성된 Markdown 보고서")
    parser.add_argument("--mode", choices=["auto", "summary", "detailed"], default="auto")
    parser.add_argument("--format", choices=["auto", "markdown", "json"], default="auto")
    parser.add_argument("--legacy", action="store_true", help="기존 Markdown 계약을 명시적으로 검증합니다")
    parser.add_argument("--fixture", choices=sorted(FIXTURES), help="fixture별 검사를 적용합니다")
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="인용한 file:line 위치를 검증할 분석 대상 저장소 루트",
    )
    args = parser.parse_args()

    path = Path(args.report)
    if not path.is_file():
        print(f"실패: 보고서를 찾을 수 없습니다: {path}")
        return 1

    report_format = args.format
    if report_format == "auto":
        report_format = "json" if path.suffix.lower() == ".json" else "markdown"
    if report_format == "json":
        _, json_errors = validate_json_file(path, args.mode, args.legacy)
        if json_errors:
            for error in json_errors:
                print(f"실패: {error}")
            return 1
        print("성공: JSON 보고서가 현재 schema contract를 만족합니다.")
        return 0

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"실패: Markdown 보고서를 읽을 수 없습니다: {error}")
        return 1
    errors: list[str] = []
    if args.repo_root is not None and not args.repo_root.is_dir():
        errors.append(f"저장소 루트를 찾을 수 없습니다: {args.repo_root}")
    detected = detect_mode(text, legacy=args.legacy)
    mode = detected if args.mode == "auto" else args.mode
    if mode is None:
        errors.append("제목에서 보고서 모드를 감지할 수 없습니다")
    elif detected is not None and args.mode != "auto" and detected != args.mode:
        errors.append(f"보고서 제목은 {detected} 모드를 가리키지만 요청 모드는 {args.mode}입니다")

    new_contract = not args.legacy
    required_sections = profile(mode or "summary", args.legacy)["sections"]
    for section in required_sections:
        if section not in text:
            errors.append(f"섹션이 없습니다: {section}")
    verdict_pattern = (
        r"(?m)^- 판정: (설계 입력 충분|추가 정보 필요|분석 불가)$"
        if not args.legacy
        else r"(?m)^- 판정: (준비됨|추가 정보 필요|분석 불가|진행 불가)$"
    )
    verdicts = re.findall(verdict_pattern, text)
    if not args.legacy and re.search(r"(?m)^- 판정: (준비됨|진행 불가)$", text):
        errors.append("legacy readiness verdict는 --legacy에서만 허용됩니다")
    if not verdicts:
        errors.append("명시적인 최종 판정이 없습니다")
    elif len(set(verdicts)) > 1:
        # 결론 우선 요약과 최종 절이 같은 판정을 반복하는 것은 허용하고,
        # 서로 다른 판정만 거부한다.
        errors.append(f"최종 판정이 서로 다릅니다: {', '.join(dict.fromkeys(verdicts))}")
    if not has_valid_evidence(text):
        errors.append("file:line 또는 검색(...) 근거를 찾을 수 없습니다")

    errors.extend(evidence_table_errors(text))
    summary_v2 = mode == "summary" and is_summary_v2(text)
    if mode is not None and not summary_v2:
        errors.extend(component_briefing_errors(text, mode, args.legacy))
    if not args.legacy:
        if not summary_v2:
            errors.extend(evidence_semantic_errors(text))
            errors.extend(readiness_blocker_errors(text))
            if mode == "detailed":
                errors.extend(detailed_evidence_slot_errors(text))
                errors.extend(design_blocker_format_errors(text))
        errors.extend(absence_marker_errors(text))
        errors.extend(credential_literal_errors(text))
    if summary_v2:
        errors.extend(summary_v2_errors(text))
    else:
        errors.extend(overview_errors(text))
    errors.extend(disallowed_section_errors(text))
    if not summary_v2:
        errors.extend(dependency_and_readiness_errors(text))
    errors.extend(mode_specific_errors(text, mode))
    errors.extend(
        repository_reference_errors(
            text,
            args.repo_root if args.repo_root is not None and args.repo_root.is_dir() else None,
        )
    )
    expected_marker = SUMMARY_V2_MARKDOWN_VERSION_MARKER if mode == "summary" and not args.legacy else MARKDOWN_VERSION_MARKER
    if not args.legacy and expected_marker not in text:
        errors.append(f"현재 Markdown contract marker가 없습니다: {expected_marker}")
    for field in ([] if new_contract else ["실행 위치", "적용 시점"]):
        if field not in text:
            errors.append(f"필수 필드가 없습니다: {field}")
    if args.fixture:
        for term in FIXTURES[args.fixture]:
            if term not in text:
                errors.append(f"fixture 기대값을 찾을 수 없습니다: {term}")

    if errors:
        for error in errors:
            print(f"실패: {error}")
        return 1
    print(f"성공: 보고서에 필요한 {mode} 브리핑 구조가 포함되어 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
