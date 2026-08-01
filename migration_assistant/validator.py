"""Static manifest validator boundary."""

from __future__ import annotations

from typing import Protocol

from .renderer import ManifestSet


class ManifestValidator(Protocol):
    """Validates only an already-rendered manifest set."""

    def validate(self, manifests: ManifestSet) -> None:
        """Raise a deterministic validation error when manifests are invalid."""
