"""Korean analysis-only command line entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .analysis import ModelConfigurationError, PydanticDependencyError, analyze
from .exploration import Planner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Git Repository Kubernetes 이관 분석")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze_command = commands.add_parser("analyze", help="Repository를 analysis-only로 분석합니다.")
    analyze_command.add_argument("repository", type=Path, help="분석할 Local Git Repository path")
    analyze_command.add_argument("--output", type=Path, default=None, help="별도 output directory")
    return parser


def main(argv: Sequence[str] | None = None, planner: Planner | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "analyze":
        return 1
    try:
        result = analyze(args.repository, args.output, planner)
    except PydanticDependencyError as error:
        print(f"필수 dependency 오류: {error}", file=sys.stderr)
        return 1
    except ModelConfigurationError as error:
        print(f"분석을 시작할 수 없습니다: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"분석에 실패했습니다: {error}", file=sys.stderr)
        return 1
    print(f"분석 상태: {result.status}")
    return 0 if result.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
