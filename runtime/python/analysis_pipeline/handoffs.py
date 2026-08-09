"""Server-owned redacted next-stage handoff projections."""
from __future__ import annotations

from typing import Any


def project_start_handoff(session: Any) -> dict[str, Any]:
    return session.handoff(None)
