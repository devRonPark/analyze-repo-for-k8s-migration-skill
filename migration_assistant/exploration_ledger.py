"""Secret-safe per-question exploration coverage ledger.

Records only that a migration question was *touched* by an observation --
the observing Tool name, a bounded observed line count, and a positive
Evidence count. It never retains a raw path, excerpt, or Secret value.
Coverage recorded here is measurement only: it never promotes a value into
a grounded Evidence or Finding by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_MAX_LINES_PER_OBSERVATION = 10


@dataclass
class QuestionCoverage:
    status: str = "observed"
    observation_count: int = 0
    observed_line_count: int = 0
    positive_evidence_count: int = 0
    tool_names: tuple[str, ...] = ()

    def summary(self) -> dict[str, object]:
        return {
            "status": self.status,
            "observation_count": self.observation_count,
            "observed_line_count": self.observed_line_count,
            "positive_evidence_count": self.positive_evidence_count,
            "tool_names": list(self.tool_names),
        }


@dataclass
class ExplorationLedger:
    """Per-question coverage tracker, Secret-safe by construction."""

    _questions: dict[str, QuestionCoverage] = field(default_factory=dict)

    def record_observation(
        self,
        question_id: str,
        tool_name: str,
        path: str | None,
        line_start: int | None,
        line_end: int | None,
        *,
        positive: bool = False,
    ) -> None:
        """Record that `tool_name` produced an observation for `question_id`.

        `path` only confirms an observation happened; it is never stored.
        Line counts are bounded per call so a single huge read cannot
        misrepresent how much was actually reviewed.
        """

        coverage = self._questions.setdefault(question_id, QuestionCoverage())
        coverage.observation_count += 1
        if isinstance(line_start, int) and isinstance(line_end, int) and line_end >= line_start:
            coverage.observed_line_count += min(line_end - line_start + 1, _MAX_LINES_PER_OBSERVATION)
        if tool_name not in coverage.tool_names:
            coverage.tool_names = coverage.tool_names + (tool_name,)
        if positive:
            coverage.positive_evidence_count += 1

    def summary(self) -> dict[str, object]:
        return {"questions": {question_id: coverage.summary() for question_id, coverage in self._questions.items()}}
