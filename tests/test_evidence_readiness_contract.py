from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "tests/fixtures/reports/valid-summary.md"


class EvidenceReadinessContractTests(unittest.TestCase):
    def validate(self, text: str, repo_root: Path | None = None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.md"
            report.write_text(text, encoding="utf-8")
            command = ["python3", str(ROOT / "scripts/validate_report.py"), str(report), "--mode", "summary"]
            if repo_root is not None:
                command.extend(["--repo-root", str(repo_root)])
            return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_fabricated_file_line_fails_with_repository_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            result = self.validate(VALID.read_text(encoding="utf-8").replace("Dockerfile:1", "missing.md:1"), repo)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("인용 파일", result.stdout)

    def test_unstructured_absence_fails(self):
        report = VALID.read_text(encoding="utf-8").replace(
            "검색(scope=., pattern=Ingress, result=없음)",
            "저장소에서 찾지 못함",
        )

        result = self.validate(report)

        self.assertNotEqual(result.returncode, 0)

    def test_inference_requires_reasoning(self):
        report = VALID.read_text(encoding="utf-8").replace(
            "- 이미지 빌드 명령: docker build -t web . — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: Dockerfile 기반 후보",
            "- 이미지 빌드 명령: docker build -t web . — 상태: 추정됨 / 근거: Dockerfile:1",
        )

        result = self.validate(report)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("판단", result.stdout)

    def test_conflict_requires_both_sources(self):
        report = VALID.read_text(encoding="utf-8").replace(
            "- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1",
            "- 설정: APP_MODE — 상태: 상충됨 / 근거: pom.xml:1",
        )

        result = self.validate(report)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("상충", result.stdout)

    def test_unknown_requires_checked_scope(self):
        report = VALID.read_text(encoding="utf-8").replace(
            "- 쓰기 상태 또는 영속성: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=volume|database, result=없음)",
            "- 쓰기 상태 또는 영속성: 없음 — 상태: 미확인 / 근거: 확인하지 못함",
        )

        result = self.validate(report)

        self.assertNotEqual(result.returncode, 0)

    def test_blocking_additional_information_requires_scope(self):
        report = VALID.read_text(encoding="utf-8").replace(
            "- 판정: 설계 입력 충분",
            "- 판정: 추가 정보 필요",
        ).replace(
            "- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: Dockerfile:1",
            "- 차단 항목: image — 범주: 이미지 / 영향 범위: 특정 배포 대상 / 상태: 미확인 / 근거: 검색(scope=., pattern=image, result=없음)",
        )

        result = self.validate(report)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_non_blocking_unknown_can_keep_sufficient_verdict(self):
        result = self.validate(VALID.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
