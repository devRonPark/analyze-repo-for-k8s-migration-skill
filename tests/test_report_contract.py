from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts import report_contract


ROOT = Path(__file__).resolve().parents[1]
REPORT_VALIDATOR = ROOT / "scripts/validate_report.py"
REPORT_FIXTURES = ROOT / "tests/fixtures/reports"


class ReportContractTests(unittest.TestCase):
    def run_validator(self, report: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(REPORT_VALIDATOR), str(report), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_current_summary_and_detailed_fixtures_pass(self):
        summary = self.run_validator(REPORT_FIXTURES / "valid-summary.md", "--mode", "summary")
        detailed = self.run_validator(REPORT_FIXTURES / "valid-detailed.md", "--mode", "detailed")

        self.assertEqual(summary.returncode, 0, summary.stdout + summary.stderr)
        self.assertEqual(detailed.returncode, 0, detailed.stdout + detailed.stderr)

    def test_detailed_instructions_require_completion_first_evidence_slots(self):
        for path in (
            ROOT / "SKILL.md",
            ROOT / "runtime/agents/kubernetes-migration-analyzer.md",
            ROOT / "references/repository-analysis-checklist.md",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn("eight-section", text)
            self.assertIn("evidence slot", text)

    def test_detailed_repeats_one_verdict_in_the_decision_summary(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8")

        self.assertIn("### 핵심 요약", report)
        self.assertEqual(report.count("- 판정: 설계 입력 충분"), 2)

    def test_detailed_rejects_conflicting_verdicts(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 판정: 설계 입력 충분", "- 판정: 분석 불가", 1
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("판정이 서로 다릅니다", result.stdout)

    def test_repeated_more_information_verdict_still_requires_a_keyed_blocker(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 판정: 설계 입력 충분", "- 판정: 추가 정보 필요"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("설계 차단 항목", result.stdout)

    def test_detailed_instructions_pin_report_line_shapes(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        template = (ROOT / "assets/migration-assessment-template.md").read_text(encoding="utf-8")
        for shape in (
            "- 키: 값 — 상태:",
            "- 차단 항목:",
        ):
            self.assertIn(shape, agent)
            self.assertIn(shape, template)
        self.assertIn("범위:", agent)
        self.assertIn("결정:", agent)
        self.assertNotIn("근거: 없음", agent)

    def test_detailed_instructions_pin_absence_and_conflict_evidence(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        template = (ROOT / "assets/migration-assessment-template.md").read_text(encoding="utf-8")

        for text in (agent, template):
            self.assertIn("검색(scope=", text)
        self.assertIn("Never translate", agent)
        self.assertIn("상태: 상충됨", agent)

    def test_report_rejects_a_translated_absence_marker(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "검색(scope=., pattern=SECRET, result=없음)",
            "搜索(scope=., pattern=SECRET, result=없음)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("부재 근거는 검색(scope=", result.stdout)

    def test_report_rejects_an_english_absence_marker(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "검색(scope=., pattern=SECRET, result=없음)",
            "search(scope=., pattern=SECRET, result=없음)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("부재 근거는 검색(scope=", result.stdout)

    def test_detailed_instructions_forbid_absence_claims_about_read_files(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")

        self.assertIn("result=없음", agent)
        self.assertIn("a file you read", agent)
        self.assertIn("pattern=Dockerfile", agent)

    def test_absence_claim_about_a_cited_file_is_rejected(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- Secret: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)",
            "- Secret: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=Dockerfile, result=없음)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("이미 인용한 파일", result.stdout)

    def test_absence_claim_about_an_existing_repository_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            (repo / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            (repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
            report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
                "- Secret: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)",
                "- Secret: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=compose.yaml, result=없음)",
            )
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed", "--repo-root", str(repo))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("저장소에 존재", result.stdout)

    def test_detailed_instructions_require_read_line_numbers_and_all_sections(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")

        self.assertIn("line numbers that appeared in the `read`", agent)
        self.assertIn("## 6. 설정과 상태 상세", agent)
        self.assertIn("never smaller than its start", agent)

    def test_reversed_line_range_is_reported_as_reversed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "pom.xml").write_text("<project/>\n" * 200, encoding="utf-8")
            (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
                "- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1",
                "- 언어: Java — 상태: 확인됨 / 근거: pom.xml:125-106",
            )
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed", "--repo-root", str(repo))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("인용 줄 범위가 거꾸로입니다", result.stdout)

    def test_detailed_instructions_require_repository_relative_references(self):
        agent = (ROOT / "runtime/agents/kubernetes-migration-analyzer.md").read_text(encoding="utf-8")
        template = (ROOT / "assets/migration-assessment-template.md").read_text(encoding="utf-8")

        self.assertIn("repository-root-relative", agent)
        self.assertIn("저장소 루트 기준 상대 경로", template)
        for forbidden in ("bare filename", "absolute path"):
            self.assertIn(forbidden, agent)

    def test_bare_filename_reference_names_its_repository_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "src/main/webapp/WEB-INF").mkdir(parents=True)
            (repo / "src/main/webapp/WEB-INF/applicationContext.xml").write_text(
                "<beans/>\n" * 40, encoding="utf-8"
            )
            (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
                "- 실행 형태: HTTP 서버 — 상태: 확인됨 / 근거: Dockerfile:1",
                "- 실행 형태: HTTP 서버 — 상태: 확인됨 / 근거: applicationContext.xml:31-34",
            )
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed", "--repo-root", str(repo))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("src/main/webapp/WEB-INF/applicationContext.xml", result.stdout)

    def test_reference_with_trailing_prose_is_rejected(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1",
            "- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1(java.version=17)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("file:line 또는 검색(...)이 없습니다", result.stdout)

    def test_detailed_rejects_property_line_without_status_and_evidence(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 실행 형태: HTTP 서버 — 상태: 확인됨 / 근거: Dockerfile:1",
            "- 실행 형태: HTTP 서버 — Servlet 컨테이너 위에서 기동",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("상태 / 근거 형식", result.stdout)

    def test_detailed_rejects_minimum_input_with_status_after_scope(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
            "- image: registry 미확인 — 범위: web / 결정: blocked / 상태: 미확인 / 근거: 검색(scope=., pattern=image, result=없음)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("상태 / 근거 형식", result.stdout)

    def test_detailed_rejects_unkeyed_design_blocker_line(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: Dockerfile:1",
            "- Dockerfile 프로필 미일치: pom.xml에 없음 — 이미지만 영향 / 영향 범위: 전체 / 상태: 상충됨 / 근거: Dockerfile:1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("차단 항목", result.stdout)

    def test_detailed_rejects_unterminated_minimum_input_slot(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
            "- image: registry decision remains open — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: image name is absent",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence slot", result.stdout)

    def test_detailed_unknown_minimum_input_identifies_scope_and_decision(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
            "- image: image registry is unknown — 상태: 미확인 / 근거: 검색(scope=., pattern=image registry, result=없음)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("범위와 결정", result.stdout)

    def test_report_rejects_literal_credential_values(self):
        report = (REPORT_FIXTURES / "valid-detailed.md").read_text(encoding="utf-8").replace(
            "- Secret: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)",
            "- Secret: password: hunter2 — 상태: 확인됨 / 근거: Dockerfile:1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detailed.md"
            path.write_text(report, encoding="utf-8")
            result = self.run_validator(path, "--mode", "detailed")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential literal", result.stdout)

    def test_legacy_verdict_is_rejected_by_default(self):
        report = REPORT_FIXTURES / "valid-summary.md"
        legacy = report.read_text(encoding="utf-8").replace("설계 입력 충분", "준비됨")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.md"
            path.write_text(legacy, encoding="utf-8")
            result = self.run_validator(path, "--mode", "summary")

        self.assertNotEqual(result.returncode, 0)

    def test_legacy_mode_is_explicit(self):
        result = self.run_validator(ROOT / "tests/fixtures/regression/invalid-actual-output.md", "--legacy")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("필수 키", result.stdout)

    def test_json_fixture_has_schema_version_and_passes(self):
        result = self.run_validator(REPORT_FIXTURES / "valid-summary.json", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads((REPORT_FIXTURES / "valid-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], report_contract.SCHEMA_VERSION)

    def test_json_without_schema_version_fails(self):
        payload = json.loads((REPORT_FIXTURES / "valid-summary.json").read_text(encoding="utf-8"))
        payload.pop("schema_version")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(path, "--format", "json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema_version", result.stdout)

    def test_json_mode_contracts_have_different_required_fields(self):
        summary = json.loads((REPORT_FIXTURES / "valid-summary.json").read_text(encoding="utf-8"))
        summary.pop("dependencies", None)
        self.assertEqual(report_contract.validate_json_payload(summary), [])

        detailed = dict(summary)
        detailed["mode"] = "detailed"
        self.assertIn("dependencies", " ".join(report_contract.validate_json_payload(detailed)))

    def test_schema_enums_match_runtime_contract(self):
        schema = json.loads((ROOT / "schemas/analysis-result.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(
            schema["properties"]["design_input_verdict"]["enum"],
            list(report_contract.READINESS_VERDICTS),
        )
        self.assertEqual(
            schema["$defs"]["evidenceStatus"]["enum"],
            list(report_contract.EVIDENCE_STATUSES),
        )
        self.assertEqual(
            schema["$defs"]["containerization"]["enum"],
            list(report_contract.CONTAINERIZATION_VALUES),
        )
        self.assertEqual(
            schema["$defs"]["configurationTiming"]["enum"],
            list(report_contract.CONFIGURATION_TIMING),
        )

    def test_schema_fixture_changes_contract_values_without_python_constants(self):
        schema = json.loads((ROOT / "schemas/analysis-result.schema.json").read_text(encoding="utf-8"))
        schema["$defs"]["evidenceStatus"]["enum"].append("fixture-status")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schema.json"
            path.write_text(json.dumps(schema), encoding="utf-8")
            contract = report_contract.load_contract(path)

        self.assertIn("fixture-status", contract["evidence_statuses"])

    def test_summary_template_sections_are_declared_in_markdown_contract(self):
        from scripts import markdown_contract

        sections = markdown_contract.load()["summary"]["sections"]
        template = (ROOT / "assets/migration-summary-template.md").read_text(encoding="utf-8")

        self.assertTrue(all(section in template for section in sections))

    def test_summary_v2_requires_conclusion_first_and_ordered_sections(self):
        report = REPORT_FIXTURES / "valid-summary.md"
        invalid = report.read_text(encoding="utf-8").replace("## 1. 결론", "## 1. 분석 범위")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(invalid, encoding="utf-8")
            result = self.run_validator(path, "--mode", "summary")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("섹션", result.stdout)

    def test_summary_v2_requires_deployment_overview_fields(self):
        report = REPORT_FIXTURES / "valid-summary.md"
        invalid = report.read_text(encoding="utf-8").replace("주요 의존성:", "의존성:")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(invalid, encoding="utf-8")
            result = self.run_validator(path, "--mode", "summary")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("배포 개요 bullet", result.stdout)

    def test_summary_v2_rejects_verdict_without_matching_blocker(self):
        invalid = (REPORT_FIXTURES / "valid-summary.md").read_text(encoding="utf-8").replace("- 판정: 설계 입력 충분", "- 판정: 추가 정보 필요")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(invalid, encoding="utf-8")
            result = self.run_validator(path, "--mode", "summary")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hard_blocker", result.stdout)

    def test_summary_v2_rejects_internal_open_item_labels(self):
        invalid = (REPORT_FIXTURES / "valid-summary.md").read_text(encoding="utf-8").replace(
            "분류: 배포 입력;", "분류: deployment_value;"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(invalid, encoding="utf-8")
            result = self.run_validator(path, "--mode", "summary")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("열린 항목 분류", result.stdout)


if __name__ == "__main__":
    unittest.main()
