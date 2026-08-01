"""Minimal executable entrypoint for checking the application foundation."""

from __future__ import annotations

from .service import ApplicationService


def main() -> int:
    ApplicationService.from_environment()
    print("Kubernetes Migration Assistant foundation이 준비되었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
