"""Measurement-only record of how a run observed the repository.

This module never participates in Evidence validation. It exists so a run can be
measured after the fact: which observation Tool supported each Evidence, how
often the Agent cited lines it never opened, and whether its searches found
anything. Recording must therefore be cheap, bounded, and free of repository
content or model-authored text.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


# Only Tools that return file content can witness a line.
OBSERVATION_TOOLS = ("search_text", "read_file_lines", "read_file")

DEFAULT_MAX_LINES = 200_000


@dataclass
class ObservationProvenance:
    """Line coordinates observed per Tool, without any observed text."""

    max_lines: int = DEFAULT_MAX_LINES
    truncated: bool = False
    search_calls: int = 0
    search_zero_hit_calls: int = 0
    _lines_by_path: dict[str, dict[str, set[int]]] = field(default_factory=dict)
    _recorded: int = 0

    def record_search(self, hits: int) -> None:
        """Record one completed search and whether it found anything.

        Only successful calls are recorded. A rejected pattern is a protocol
        error, not evidence that the repository lacks the term.
        """

        if hits < 0:
            return
        self.search_calls += 1
        if hits == 0:
            self.search_zero_hit_calls += 1

    def record(self, tool: str, path: str, line_start: int, line_end: int) -> None:
        """Record an inclusive 1-based observed range, ignoring invalid input."""

        if tool not in OBSERVATION_TOOLS or not path:
            return
        if line_start < 1 or line_end < line_start:
            return
        span = line_end - line_start + 1
        # A silently dropped range would later look like a fabricated citation,
        # so refuse the whole range and mark the record incomplete instead.
        if self._recorded + span > self.max_lines:
            self.truncated = True
            return
        by_tool = self._lines_by_path.setdefault(path, {})
        observed = by_tool.setdefault(tool, set())
        before = len(observed)
        observed.update(range(line_start, line_end + 1))
        self._recorded += len(observed) - before

    def sources_for(self, path: str, line_start: int, line_end: int) -> tuple[str, ...]:
        """Return Tools that observed every line of the range, in stable order."""

        if not path or line_start < 1 or line_end < line_start:
            return ()
        by_tool = self._lines_by_path.get(path)
        if not by_tool:
            return ()
        wanted = set(range(line_start, line_end + 1))
        return tuple(
            tool
            for tool in sorted(by_tool)
            if wanted.issubset(by_tool[tool])
        )

    def summary(self) -> dict[str, object]:
        """Return counts only; paths and text never enter the measurement output."""

        observed_lines = {
            tool: sum(len(by_tool.get(tool, ())) for by_tool in self._lines_by_path.values())
            for tool in OBSERVATION_TOOLS
        }
        return {
            "observed_lines": {tool: count for tool, count in observed_lines.items() if count},
            "observed_paths": len(self._lines_by_path),
            "truncated": self.truncated,
            "search_calls": self.search_calls,
            "search_zero_hit_calls": self.search_zero_hit_calls,
            # None, not 0.0: a run that never searched is not a run that
            # searched perfectly.
            "search_zero_hit_ratio": (
                self.search_zero_hit_calls / self.search_calls if self.search_calls else None
            ),
        }


def _field(item: object, name: str) -> object:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def evidence_sources(
    evidence: Iterable[object], provenance: ObservationProvenance
) -> list[dict[str, object]]:
    """Attribute each positive Evidence to the Tools that observed its lines.

    An empty source list means the Agent cited lines it never opened in this run.
    Absence Evidence carries no line coordinates and is skipped.
    """

    attribution: list[dict[str, object]] = []
    for item in evidence:
        path = _field(item, "path")
        start = _field(item, "line_start")
        end = _field(item, "line_end")
        if not isinstance(path, str) or not isinstance(start, int) or not isinstance(end, int):
            continue
        identifier = _field(item, "id")
        attribution.append(
            {
                "id": identifier if isinstance(identifier, str) else None,
                "sources": list(provenance.sources_for(path, start, end)),
            }
        )
    return attribution
