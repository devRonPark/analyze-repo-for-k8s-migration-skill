"""Fail when a delivered analysis runtime path reintroduces JS/TS tooling."""
from __future__ import annotations

import argparse
from pathlib import Path


RUNTIME_PATHS = (
    "runtime",
    "runtime-files.txt",
    "scripts/install-opencode.sh",
    "scripts/run_opencode_acceptance.py",
    "scripts/mcp_smoke.py",
)
FORBIDDEN_SUFFIXES = {".ts", ".js", ".mts", ".cts"}
FORBIDDEN_TEXT = ("@opencode-ai/plugin", "bun.", "bun ", "node:")


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for relative in RUNTIME_PATHS:
        path = root / relative
        files = [path] if path.is_file() else sorted(candidate for candidate in path.rglob("*") if candidate.is_file()) if path.is_dir() else []
        for file in files:
            shown = file.relative_to(root).as_posix()
            if file.suffix.lower() in FORBIDDEN_SUFFIXES:
                findings.append(f"legacy artifact: {shown}")
                continue
            text = file.read_text(encoding="utf-8", errors="replace").lower()
            for token in FORBIDDEN_TEXT:
                if token in text:
                    findings.append(f"legacy runtime reference ({token}): {shown}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Python-only delivered analysis runtime.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    findings = scan(args.root.resolve())
    if findings:
        print("\n".join(findings))
        return 1
    print("Python runtime scan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
