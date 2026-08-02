from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from devtools.env_file import EnvFileLoadResult
from devtools.run_phase1_live_acceptance import AcceptanceRun, _model_summary, evaluate_runs, run_acceptance
from migration_assistant.adk_runner import AdkRun
from migration_assistant.analysis import AnalysisResult, analyze


def run(
    exit_code: int,
    status: str,
    *,
    terminal: bool,
    tool_calls: tuple[str, ...] = ("inspect_target", "validate_analysis"),
    evidence_count: int = 1,
    positive_evidence_count: int = 1,
    protocol_error_codes: tuple[str, ...] = (),
) -> AcceptanceRun:
    return AcceptanceRun(
        output_path=Path("output") / str(exit_code) / status,
        exit_code=exit_code,
        status=status,
        terminal=terminal,
        tool_calls=tool_calls,
        evidence_count=evidence_count,
        positive_evidence_count=positive_evidence_count,
        protocol_error_codes=protocol_error_codes,
    )


class Phase1LiveAcceptanceHarnessTests(unittest.TestCase):
    def setUp(self):
        self._root_harness_dirs_before = frozenset(Path.cwd().glob(".phase1-harness-*"))
        # The managed Windows runner creates %TEMP% directories with an ACL that
        # rejected both child mkdir and cleanup (WinError 5), so use an ignored cwd
        # fixture until that environment issue is removed.
        self.test_root = Path.cwd() / f".phase1-harness-{uuid4().hex}"
        self.test_root.mkdir()
        self.addCleanup(self._assert_no_project_root_harness_residue)
        self.addCleanup(shutil.rmtree, self.test_root, ignore_errors=True)

    def _assert_no_project_root_harness_residue(self):
        self.assertEqual(
            frozenset(Path.cwd().glob(".phase1-harness-*")),
            self._root_harness_dirs_before,
        )

    def test_fixture_cleanup_leaves_no_directory_under_project_root(self):
        self.assertEqual(self.test_root.parent.resolve(), Path.cwd().resolve())
        self.assertIn(".phase1-harness-*", Path(".gitignore").read_text(encoding="utf-8"))

    def test_model_summary_marks_missing_environment_values_as_package_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            summary = _model_summary()

        self.assertEqual(summary["llm_model_source"], "package_default")
        self.assertEqual(summary["llm_base_url_source"], "package_default")
        self.assertEqual(summary["llm_timeout_seconds_source"], "package_default")
        self.assertEqual(summary["llm_max_tokens_source"], "package_default")
        self.assertFalse(summary["environment_variables"]["LLM_MODEL"]["present"])
        self.assertFalse(summary["environment_variables"]["LLM_API_KEY"]["present"])

    def test_model_summary_never_contains_api_key_value(self):
        secret = "summary-api-key-value"
        with patch.dict(os.environ, {"LLM_API_KEY": secret}, clear=True):
            summary = _model_summary()

        self.assertTrue(summary["environment_variables"]["LLM_API_KEY"]["present"])
        self.assertNotIn(secret, json.dumps(summary, ensure_ascii=False))

    def test_model_summary_marks_loaded_file_values_as_env_file(self):
        load_result = EnvFileLoadResult(
            injected_keys=frozenset({"LLM_MODEL"}),
            selected_path=Path("settings.env"),
        )
        with patch.dict(os.environ, {"LLM_MODEL": "file-model"}, clear=True):
            summary = _model_summary(env_file=load_result)

        self.assertEqual(summary["llm_model_source"], "env_file")
        self.assertEqual(summary["environment_variables"]["LLM_MODEL"]["source"], "env_file")

    def test_summary_reports_evidence_provenance_for_measurement(self):
        repository = self.test_root / "repository"
        output_parent = self.test_root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, max_iterations
            Path(output).mkdir(parents=True)
            run_metadata.update({
                "terminal": True,
                "tool_calls": ["inspect_target", "read_file", "validate_analysis"],
                "protocol_issues": [],
                "evidence_provenance": [
                    {"id": "e1", "sources": ["read_file_lines"]},
                    {"id": "e2", "sources": []},
                ],
                "provenance_summary": {
                    "observed_lines": {"read_file": 120, "read_file_lines": 4},
                    "observed_paths": 2,
                    "truncated": False,
                    "search_calls": 3,
                    "search_zero_hit_calls": 3,
                    "search_zero_hit_ratio": 1.0,
                },
            })
            return SimpleNamespace(
                status="complete",
                evidence=[SimpleNamespace(status="confirmed", path="app.py", line_start=1, line_end=1)],
            )

        summary = run_acceptance(repository, output_parent, runs=1, analyze_fn=fake_analyze)
        first = summary["runs"][0]

        self.assertEqual(
            first["evidence_provenance"],
            [{"id": "e1", "sources": ["read_file_lines"]}, {"id": "e2", "sources": []}],
        )
        self.assertEqual(first["provenance_summary"]["observed_lines"]["read_file"], 120)
        # An Evidence with no source was cited without ever being observed.
        self.assertEqual(first["unobserved_evidence_count"], 1)
        # Search effectiveness is the rollback signal for the registry patterns,
        # so the harness must not drop it.
        self.assertEqual(first["provenance_summary"]["search_zero_hit_ratio"], 1.0)

    def test_summary_keeps_the_field_path_of_each_protocol_error(self):
        repository = self.test_root / "repository"
        output_parent = self.test_root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, max_iterations
            Path(output).mkdir(parents=True)
            run_metadata.update({
                "terminal": False,
                "tool_calls": ["inspect_target", "validate_analysis"],
                "protocol_issues": [
                    {"code": "candidate_schema", "message": "필수 Tool 인자가 누락되었습니다.", "field_path": "$.iterations"},
                    {"code": "invalid_arguments", "message": "범위 오류", "field_path": "$.line_end"},
                    {"code": "duplicate_call", "message": "중복", "field_path": None},
                ],
            })
            return SimpleNamespace(status="failed", evidence=[])

        summary = run_acceptance(repository, output_parent, runs=1, analyze_fn=fake_analyze)

        # A bare error code cannot tell which argument the model got wrong,
        # which is the only thing that makes the failure actionable.
        self.assertEqual(
            summary["runs"][0]["protocol_error_fields"],
            ["$.iterations", "$.line_end", None],
        )

    def test_unresolved_evidence_does_not_count_as_gate_success(self):
        repository = self.test_root / "repository"
        output_parent = self.test_root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, max_iterations
            Path(output).mkdir(parents=True)
            run_metadata.update({
                "terminal": True,
                "tool_calls": ["inspect_target", "validate_analysis"],
                "protocol_issues": [],
            })
            return SimpleNamespace(
                status="complete",
                evidence=[SimpleNamespace(status="unresolved", path=None, line_start=None, line_end=None)],
            )

        summary = run_acceptance(repository, output_parent, runs=3, analyze_fn=fake_analyze)

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["successes"], 0)
        self.assertEqual(summary["runs"][0]["evidence_count"], 1)
        self.assertEqual(summary["runs"][0]["positive_evidence_count"], 0)

    def test_gate_requires_three_of_three_complete_terminal_runs(self):
        summary = evaluate_runs([
            run(0, "complete", terminal=True),
            run(0, "complete", terminal=True),
            run(2, "partial", terminal=True),
        ])

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["successes"], 2)
        self.assertEqual(summary["required"], 3)

    def test_zero_tool_complete_shaped_response_does_not_pass_gate(self):
        summary = evaluate_runs([
            run(0, "complete", terminal=False, tool_calls=(), evidence_count=0),
            run(0, "complete", terminal=True),
            run(0, "complete", terminal=True),
        ])

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["successes"], 2)

    def test_runs_use_distinct_output_directories_outside_target(self):
        root = self.test_root
        repository = root / "repository"
        output_parent = root / "outputs"
        repository.mkdir()
        seen_outputs: list[Path] = []

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, max_iterations
            output_path = Path(output)
            output_path.mkdir(parents=True)
            seen_outputs.append(output_path)
            run_metadata.update({
                "terminal": True,
                "tool_calls": ["inspect_target", "validate_analysis"],
                "protocol_issues": [],
            })
            return SimpleNamespace(
                status="complete",
                evidence=[SimpleNamespace(status="confirmed", path="app.py", line_start=1, line_end=1)],
            )

        summary = run_acceptance(
            repository,
            output_parent,
            runs=3,
            analyze_fn=fake_analyze,
        )

        self.assertEqual(len(seen_outputs), 3)
        self.assertEqual(len(set(seen_outputs)), 3)
        for output in seen_outputs:
            self.assertNotEqual(output, repository)
            self.assertNotIn(repository, output.parents)
        self.assertTrue(summary["passed"])
        self.assertTrue(summary["gate_mode"])

    def test_one_run_is_reported_as_a_non_gate_diagnostic(self):
        repository = self.test_root / "repository"
        output_parent = self.test_root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, max_iterations
            Path(output).mkdir(parents=True)
            run_metadata.update({
                "terminal": True,
                "tool_calls": ["inspect_target", "validate_analysis"],
                "protocol_issues": [],
            })
            return SimpleNamespace(
                status="complete",
                evidence=[SimpleNamespace(status="confirmed", path="app.py", line_start=1, line_end=1)],
            )

        summary = run_acceptance(
            repository,
            output_parent,
            runs=1,
            analyze_fn=fake_analyze,
        )

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["successes"], 1)
        self.assertEqual(summary["required"], 3)
        self.assertFalse(summary["gate_mode"])
        self.assertEqual(len(summary["runs"]), 1)

    def test_zero_runs_are_rejected(self):
        with self.assertRaises(ValueError):
            run_acceptance(self.test_root / "repository", self.test_root / "outputs", runs=0)

    def test_summary_does_not_contain_secret_values(self):
        secret = "super-secret-value"

        root = self.test_root
        repository = root / "repository"
        output_parent = root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, max_iterations
            Path(output).mkdir(parents=True)
            run_metadata.update({
                "terminal": False,
                "tool_calls": ["inspect_target"],
                "protocol_issues": [{
                    "code": "invalid_arguments",
                    "message": f"token={secret}",
                }],
            })
            return SimpleNamespace(status="failed", evidence=[])

        summary = run_acceptance(
            repository,
            output_parent,
            runs=3,
            analyze_fn=fake_analyze,
        )

        self.assertNotIn(secret, json.dumps(summary, ensure_ascii=False))
        self.assertEqual(summary["runs"][0]["protocol_error_codes"], ["invalid_arguments"])

    def test_failed_run_keeps_typed_redacted_exception_and_metadata(self):
        secret = "diagnostic-api-key-value"
        repository = self.test_root / "repository"
        output_parent = self.test_root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, output, max_iterations
            run_metadata.update({
                "terminal": True,
                "tool_calls": ["search_text", "validate_analysis"],
                "protocol_issues": [{"code": "invalid_arguments", "message": "token=hidden"}],
            })
            raise RuntimeError(f"model failed with key {secret}")

        with patch.dict(os.environ, {"LLM_API_KEY": secret}, clear=False):
            summary = run_acceptance(
                repository,
                output_parent,
                runs=3,
                analyze_fn=fake_analyze,
            )

        failed = summary["runs"][0]
        self.assertEqual(failed["error_type"], "RuntimeError")
        self.assertIn("model failed", failed["error_message"])
        self.assertLessEqual(len(failed["error_message"]), 500)
        self.assertNotIn(secret, json.dumps(summary, ensure_ascii=False))
        self.assertEqual(failed["tool_calls"], ["search_text", "validate_analysis"])
        self.assertEqual(failed["protocol_error_codes"], ["invalid_arguments"])
        self.assertTrue(failed["terminal"])

    def test_run_details_survive_summary_assembly_failure(self):
        repository = self.test_root / "repository"
        output_parent = self.test_root / "outputs"
        repository.mkdir()

        def fake_analyze(repository_path, output, *, max_iterations, run_metadata):
            del repository_path, output, max_iterations
            run_metadata.update({
                "terminal": True,
                "tool_calls": ["inspect_target", "validate_analysis"],
                "protocol_issues": [],
            })
            return SimpleNamespace(
                status="complete",
                evidence=[SimpleNamespace(status="confirmed", path="app.py", line_start=1, line_end=1)],
            )

        with patch(
            "devtools.run_phase1_live_acceptance._model_summary",
            side_effect=RuntimeError("summary assembly failed"),
        ):
            summary = run_acceptance(
                repository,
                output_parent,
                runs=3,
                analyze_fn=fake_analyze,
            )

        self.assertTrue(summary["passed"])
        self.assertEqual(len(summary["runs"]), 3)
        self.assertEqual(summary["runs"][0]["tool_calls"], ["inspect_target", "validate_analysis"])
        self.assertEqual(summary["summary_errors"]["model"]["error_type"], "RuntimeError")

    def test_analyze_hands_off_runner_telemetry_without_changing_result_contract(self):
        repository = self.test_root / "repository"
        output = self.test_root / "output"
        repository.mkdir()
        (repository / "app.py").write_text("PORT = 8080\n", encoding="utf-8")
        subprocess.run(["git", "init", str(repository)], capture_output=True, check=True)
        result = AnalysisResult.model_validate({
            "status": "complete",
            "summary": "검증된 결과",
            "evidence": [{
                "id": "e1",
                "status": "confirmed",
                "path": "app.py",
                "line_start": 1,
                "line_end": 1,
                "claim": "애플리케이션 포트가 확인됨",
                "excerpt": "PORT = 8080",
            }],
            "findings": [{
                "id": "f1",
                "status": "confirmed",
                "claim": "애플리케이션 실행 포트가 확인됨",
                "evidence_ids": ["e1"],
            }],
        })
        run_result = AdkRun(
            result=result,
            terminal=True,
            tool_calls=["inspect_target", "validate_analysis"],
            protocol_issues=[{"code": "invalid_arguments", "message": "token=super-secret-value"}],
        )
        metadata: dict[str, object] = {"stale": True}

        with patch("migration_assistant.adk_runner.run_adk_agent", return_value=run_result):
            returned = analyze(repository, output, adk_model=object(), run_metadata=metadata)

        self.assertEqual(returned.status, "complete")
        self.assertTrue(metadata["terminal"])
        self.assertEqual(metadata["tool_calls"], ["inspect_target", "validate_analysis"])
        self.assertNotIn("super-secret-value", json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
