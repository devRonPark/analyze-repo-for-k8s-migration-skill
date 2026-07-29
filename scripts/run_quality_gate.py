#!/usr/bin/env python3
"""Run the repository's validation and regression checks in a fixed order."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def commands(root: Path) -> list[tuple[str, list[str]]]:
    python = sys.executable
    return [
        (
            "package validation",
            [python, str(root / "scripts/validate_skill.py"), str(root)],
        ),
        (
            "unit tests",
            [
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        ),
        (
            "executable scenario evaluator",
            [
                python,
                str(root / "scripts/evaluate_scenarios.py"),
                "--cases",
                str(root / "tests/evaluation/cases.json"),
                "--actual-dir",
                str(root / "tests/evaluation/golden-actual"),
            ],
        ),
    ]


def run_gate(root: Path, runner: CommandRunner = subprocess.run) -> int:
    for label, command in commands(root):
        print(f"== {label} ==")
        result = runner(command, cwd=root, check=False)
        if result.returncode != 0:
            print(f"Quality gate failed: {label} (exit code {result.returncode})")
            return result.returncode

    print(
        "Quality gate passed: package validation, unit tests, and "
        "8 executable scenario cases. Scenario fixtures are not agent E2E coverage."
    )
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    return run_gate(root)


if __name__ == "__main__":
    sys.exit(main())
