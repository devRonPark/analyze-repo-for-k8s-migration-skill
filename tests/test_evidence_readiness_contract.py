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
            "검색(scope=., pattern=registry, result=없음)",
            "저장소에서 찾지 못함",
        )

        result = self.validate(report)

        self.assertNotEqual(result.returncode, 0)

    def test_blocking_additional_information_requires_scope(self):
        report = VALID.read_text(encoding="utf-8").replace(
            "- 판정: 설계 입력 충분",
            "- 판정: 추가 정보 필요",
        ).replace(
            "- 분류: 배포 입력; 항목: image registry; 영향: 배포 시 입력; 근거: 검색(scope=., pattern=registry, result=없음)",
            "- 분류: 설계 차단; 항목: image; 영향: 특정 배포 대상; 근거: 검색(scope=., pattern=image, result=없음)",
        )

        result = self.validate(report)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_non_blocking_unknown_can_keep_sufficient_verdict(self):
        result = self.validate(VALID.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
