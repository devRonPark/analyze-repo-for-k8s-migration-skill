"""Minimal executable entrypoint for checking the application foundation."""

from __future__ import annotations

import sys
from typing import Sequence

from .service import ApplicationService


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None and __name__ == "__main__" else argv or [])
    if arguments:
        from .cli import main as cli_main

        return cli_main(arguments)
    ApplicationService.from_environment()
    print("Kubernetes Migration Assistant foundation이 준비되었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
