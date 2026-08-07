#!/usr/bin/env python3
"""Finalize a Summary validation receipt only after validation succeeds."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def finalize(report: Path, repository_root: Path | None = None, *, mode: str = "summary") -> int:
    command = [sys.executable, str(Path(__file__).with_name("validate_report.py")), str(report), "--mode", mode]
    if repository_root is not None:
        command.extend(["--repo-root", str(repository_root)])
    result = subprocess.run(command, check=False)
    if result.returncode:
        return result.returncode
    if mode != "summary":
        # Only the Summary v2 contract carries a "Validation: pending" receipt
        # line to flip; other modes have no such field in their template.
        return 0
    text = report.read_text(encoding="utf-8")
    if "Validation: pending" not in text:
        print("실패: Validation: pending Receipt가 없습니다")
        return 1
    temporary = report.with_suffix(report.suffix + ".tmp")
    temporary.write_text(text.replace("Validation: pending", "Validation: passed", 1), encoding="utf-8")
    temporary.replace(report)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--mode", choices=["summary", "detailed"], default="summary")
    args = parser.parse_args()
    raise SystemExit(finalize(args.report, args.repo_root, mode=args.mode))
