"""Deterministic Kubernetes manifest renderer boundary."""

from __future__ import annotations

from typing import Mapping, Protocol

from .schemas import KubernetesMigrationPlan


ManifestSet = Mapping[str, str]


class ManifestRenderer(Protocol):
    """Renders only a validated KubernetesMigrationPlan into manifests."""

    def render(self, plan: KubernetesMigrationPlan) -> ManifestSet:
        """Render manifests without performing Agent calls or filesystem writes."""
