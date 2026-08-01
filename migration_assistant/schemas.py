"""Schema boundary reserved for the separate analysis and migration contracts."""

from __future__ import annotations

try:
    from pydantic import BaseModel, ConfigDict
except ModuleNotFoundError:
    BaseModel = None  # type: ignore[assignment,misc]


if BaseModel is None:

    class AnalysisResult:
        """Dependency-free placeholder for the future Pydantic contract."""

        __slots__ = ()

    class KubernetesMigrationPlan:
        """Dependency-free placeholder for the future Pydantic contract."""

        __slots__ = ()

else:

    class AnalysisResult(BaseModel):
        """Strict Pydantic boundary for repository analysis results."""

        model_config = ConfigDict(extra="forbid")

    class KubernetesMigrationPlan(BaseModel):
        """Strict Pydantic boundary for Kubernetes migration plans."""

        model_config = ConfigDict(extra="forbid")
