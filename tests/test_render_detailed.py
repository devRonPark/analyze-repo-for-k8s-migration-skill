import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.render_detailed import render_detailed


ROOT = Path(__file__).resolve().parents[1]


def load_fixture() -> dict:
    return json.loads((ROOT / "tests/fixtures/reports/valid-detailed.json").read_text(encoding="utf-8"))


def validate(report: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "detailed.md"
        path.write_text(report, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_report.py"), str(path), "--mode", "detailed"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )


class DetailedRendererTests(unittest.TestCase):
    def test_renders_schema_payload_as_valid_detailed_markdown(self):
        payload = load_fixture()

        report = render_detailed(payload)

        self.assertTrue(report.startswith("# Kubernetes 설계 입력 상세 평가\n"))
        self.assertIn("<!-- analyze-repo-for-kubernetes: report-contract=1.0 -->", report)
        result = validate(report)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_non_detailed_payloads(self):
        payload = load_fixture()
        payload["mode"] = "summary"

        with self.assertRaises(ValueError):
            render_detailed(payload)

    def test_no_markdown_table_in_rendered_output(self):
        payload = load_fixture()

        report = render_detailed(payload)

        for line in report.splitlines():
            self.assertFalse(line.lstrip().startswith("|"), f"Markdown table row found: {line}")

    def test_renders_multiple_candidate_cards(self):
        payload = load_fixture()
        second = copy.deepcopy(payload["components"][0])
        second["name"] = "worker"
        payload["components"].append(second)

        report = render_detailed(payload)

        self.assertIn("### 배포 대상: web", report)
        self.assertIn("### 배포 대상: worker", report)
        for name in ("web", "worker"):
            card_start = report.index(f"### 배포 대상: {name}")
            card_end = report.find("### 배포 대상:", card_start + 1)
            if card_end == -1:
                card_end = report.find("## 4. 구성과 관계", card_start)
            card = report[card_start:card_end]
            for heading in ("#### 실행 정보", "#### 설정과 상태", "#### Kubernetes 최소 설계 입력", "#### 최소 입력 누락"):
                self.assertIn(heading, card)

        result = validate(report)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dependency_matrix_and_text_graph_stay_in_sync(self):
        payload = load_fixture()
        second = {
            "source": "web",
            "target": "tomcat",
            "evidence": [{"status": "상충됨", "reference": "Dockerfile:21, pom.xml:337"}],
            "fields": {
                "종류": "application server",
                "protocol 또는 mechanism": "HTTP",
                "endpoint 또는 configuration": "미확인",
                "적용 시점": "배포 시점",
                "실행 위치": "동일 컨테이너",
                "기능 실행에 필요": "필요",
                "확인된 실행 정의에서 사용 여부": "미확인",
                "공급 또는 관리 경계": "이미지 빌드",
                "상태 또는 영속성": "미확인",
            },
        }
        payload["dependencies"].append(second)

        report = render_detailed(payload)
        matrix = report.split("### Dependency matrix", 1)[1].split("### Text dependency graph", 1)[0]
        graph = report.split("### Text dependency graph", 1)[1].split("### 배포 대상 후보에서 제외한 항목", 1)[0]

        for dependency in payload["dependencies"]:
            source, target = dependency["source"], dependency["target"]
            fields = dependency["fields"]
            self.assertIn(f"연결 workload: {source}; 의존 대상: {target}", matrix)
            self.assertIn(fields["종류"], matrix)
            self.assertIn(f"{source} --[{fields['종류']}, {fields['적용 시점']}, {fields['실행 위치']}]--> {target}", graph)

    def test_renders_conflicting_dependency_evidence(self):
        payload = load_fixture()
        payload["dependencies"][0]["evidence"] = [{"status": "상충됨", "reference": "Dockerfile:21, pom.xml:337"}]

        report = render_detailed(payload)

        self.assertIn("근거: Dockerfile:21, pom.xml:337", report)
        result = validate(report)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_input_requires_scope_and_decision_for_unresolved_state(self):
        payload = load_fixture()
        payload["components"][0]["missing_inputs"] = [{
            "key": "Ingress",
            "description": "Ingress 미정의",
            "status": "미확인",
            "reference": "검색(scope=., pattern=Ingress, result=없음)",
        }]

        with self.assertRaises(ValueError):
            render_detailed(payload)

    def test_missing_input_rejects_estimated_status(self):
        payload = load_fixture()
        payload["components"][0]["missing_inputs"] = [{
            "key": "Ingress",
            "description": "Ingress 미정의",
            "범위": "web",
            "결정": "open decision",
            "status": "추정됨",
            "reference": "Dockerfile:1",
            "reason": "추정 근거",
        }]

        with self.assertRaises(ValueError):
            render_detailed(payload)

    def test_requires_blockers_for_additional_information_verdict(self):
        payload = load_fixture()
        payload["missing_inputs"] = []

        with self.assertRaises(ValueError):
            render_detailed(payload)

    def test_cli_renders_json_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "detailed.md"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/render_detailed.py"), str(ROOT / "tests/fixtures/reports/valid-detailed.json")],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            report.write_text(result.stdout, encoding="utf-8")
            validation = subprocess.run(
                [sys.executable, str(ROOT / "scripts/validate_report.py"), str(report), "--mode", "detailed"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)


if __name__ == "__main__":
    unittest.main()
