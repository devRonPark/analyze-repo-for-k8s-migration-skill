import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.render_summary import render_summary


ROOT = Path(__file__).resolve().parents[1]


def evidence(value: str, reference: str = "Dockerfile:1", status: str = "확인됨") -> dict[str, str]:
    return {"value": value, "status": status, "reference": reference}


class SummaryRendererTests(unittest.TestCase):
    def test_renders_korean_open_item_labels(self):
        payload = json.loads((ROOT / "tests/fixtures/reports/valid-summary.json").read_text(encoding="utf-8"))
        payload["missing_inputs"] = [{
            "key": "registry",
            "description": "image registry",
            "impact_scope": "배포 시 입력",
            "status": "미확인",
            "reference": "검색(scope=., pattern=registry, result=없음)",
            "classification": "deployment_value",
        }]

        report = render_summary(payload)

        self.assertIn("| 배포 입력 | image registry | 배포 시 입력 |", report)

    def test_rejects_non_summary_payloads(self):
        payload = json.loads((ROOT / "tests/fixtures/reports/valid-summary.json").read_text(encoding="utf-8"))
        payload["mode"] = "detailed"

        with self.assertRaises(ValueError):
            render_summary(payload)

    def test_requires_blockers_for_additional_information_verdict(self):
        payload = json.loads((ROOT / "tests/fixtures/reports/valid-summary.json").read_text(encoding="utf-8"))
        payload["design_input_verdict"] = "추가 정보 필요"

        with self.assertRaises(ValueError):
            render_summary(payload)

    def test_keeps_candidate_and_exclusion_evidence_separate(self):
        payload = json.loads((ROOT / "tests/fixtures/reports/valid-summary.json").read_text(encoding="utf-8"))
        payload["components"].append({
            "name": "worker",
            "evidence": [{"status": "확인됨", "reference": "worker.py:2"}],
        })
        payload["excluded_items"] = [
            {"name": "docs"},
            {"name": "tests", "evidence": {"status": "확인됨", "reference": "README.md:2"}},
        ]

        report = render_summary(payload)

        self.assertIn("- 배포 대상: web, worker — 근거: Dockerfile:1", report)
        self.assertIn("| worker | 배포 대상 후보 | 애플리케이션 | Deployment 후보 | 없음 | Stateless | 없음 | worker.py:2 |", report)

    def test_renders_schema_payload_as_valid_summary_markdown(self):
        fields = {
            key: evidence("확인")
            for key in (
                "실행 형태", "런타임", "빌드 명령", "운영 기동 명령",
                "이미지 빌드 명령", "컨테이너화", "프로토콜", "수신 포트",
                "설정", "Secret", "쓰기 상태 또는 영속성", "런타임 의존성",
            )
        }
        payload = {
            "schema_version": "1.0",
            "mode": "summary",
            "scope": {
                "대상 유형": "Local path",
                "Repository URL 또는 Local path": "/tmp/web",
                "접근 방식": "read-only",
                "확인된 저장소 루트": "/tmp/web",
                "branch, tag 또는 commit": "main",
                "분석 경로": ".",
            },
            "components": [{
                "name": "web",
                "fields": fields,
                "minimum_inputs": {
                    key: evidence("확인")
                    for key in ("image", "command", "args", "containerPort")
                },
                "missing_inputs": [],
            }],
            "excluded_items": [],
            "missing_inputs": [],
            "evidence": [{"status": "확인됨", "reference": "Dockerfile:1"}],
            "design_input_verdict": "설계 입력 충분",
            "verdict_reason": "필수 입력 확인",
            "verdict_evidence": [{"status": "확인됨", "reference": "Dockerfile:1"}],
        }

        report = render_summary(payload)
        self.assertTrue(report.startswith("# Kubernetes 설계 입력 요약\n"))
        self.assertIn("<!-- analyze-repo-for-kubernetes: report-contract=2.0 -->", report)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(report, encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/validate_report.py"), str(path), "--mode", "summary"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        payload["components"][0]["fields"] = {}
        payload["components"][0]["minimum_inputs"] = {}
        report = render_summary(payload)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(report, encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/validate_report.py"), str(path), "--mode", "summary"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_renders_json_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/render_summary.py"), str(ROOT / "tests/fixtures/reports/valid-summary.json")],
                capture_output=True,
                text=True,
                check=False,
            )
            report.write_text(result.stdout, encoding="utf-8")
            validation = subprocess.run(
                ["python3", str(ROOT / "scripts/validate_report.py"), str(report), "--mode", "summary"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)


if __name__ == "__main__":
    unittest.main()
