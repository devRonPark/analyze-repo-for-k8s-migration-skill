#!/usr/bin/env python3
"""Finalize a Summary validation receipt only after validation succeeds."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def finalize(report: Path) -> int:
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("validate_report.py")), str(report), "--mode", "summary"], check=False)
    if result.returncode:
        return result.returncode
    text = report.read_text(encoding="utf-8")
    if "Validation: pending" not in text:
        print("실패: Validation: pending Receipt가 없습니다")
        return 1
    temporary = report.with_suffix(report.suffix + ".tmp")
    temporary.write_text(text.replace("Validation: pending", "Validation: passed", 1), encoding="utf-8")
    temporary.replace(report)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    raise SystemExit(finalize(parser.parse_args().report))
