"""Secret-safe per-question exploration coverage ledger.

Records only that a migration question was *touched* by an observation --
the observing Tool name, a bounded observed line count, a positive/
conflicting Evidence count, and whether a scoped search was ever attempted.
It never retains a raw path, excerpt, search pattern text, or Secret value.
Coverage recorded here is measurement only: it never promotes a value into
a grounded Evidence or Finding by itself.

`stop_decision()` mechanically applies the Task 0 stop-gate truth table
(see tests/test_migration_contract.py and
docs/superpowers/plans/2026-08-06-kubernetes-migration-agent-lesson-learned-and-improvement-plan.md).
A model saying "I couldn't find it" is not enough to grant `unresolved` --
only a ledger-recorded search scope, pattern, and observation count for
that question earns it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exploration_policy import ExplorationPolicy, ExplorationQuestion, QuestionImportance

_MAX_LINES_PER_OBSERVATION = 10


@dataclass
class QuestionCoverage:
    status: str = "observed"
    observation_count: int = 0
    observed_line_count: int = 0
    positive_evidence_count: int = 0
    conflicting_evidence_count: int = 0
    has_search_scope: bool = False
    has_search_pattern: bool = False
    tool_names: tuple[str, ...] = ()

    def summary(self) -> dict[str, object]:
        return {
            "status": self.status,
            "observation_count": self.observation_count,
            "observed_line_count": self.observed_line_count,
            "positive_evidence_count": self.positive_evidence_count,
            "conflicting_evidence_count": self.conflicting_evidence_count,
            "has_search_scope": self.has_search_scope,
            "has_search_pattern": self.has_search_pattern,
            "tool_names": list(self.tool_names),
        }


@dataclass(frozen=True, slots=True)
class StopDecision:
    """A mechanically-derived, Secret-safe verdict -- never a fabricated value."""

    allowed: bool
    reason: str
    allowed_status: tuple[str, ...]
    synthetic_values: dict[str, object]


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
        conflicting: bool = False,
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
        if conflicting:
            coverage.conflicting_evidence_count += 1

    def record_search_attempt(
        self,
        question_id: str,
        tool_name: str,
        scope: str | None,
        pattern: str | None,
    ) -> None:
        """Record that `tool_name` searched `scope` for `pattern` on this question's behalf.

        This is what earns a genuine `unresolved` its ledger backing: an
        actual recorded scope, pattern, and observation count -- not just
        the model's own words. Only whether a scope/pattern was ever used
        is kept, never the literal text.
        """

        coverage = self._questions.setdefault(question_id, QuestionCoverage())
        coverage.observation_count += 1
        if tool_name not in coverage.tool_names:
            coverage.tool_names = coverage.tool_names + (tool_name,)
        if scope:
            coverage.has_search_scope = True
        if pattern:
            coverage.has_search_pattern = True

    def summary(self) -> dict[str, object]:
        return {"questions": {question_id: coverage.summary() for question_id, coverage in self._questions.items()}}

    def disposition(self, question: ExplorationQuestion) -> str:
        """One of confirmed/conflicting/not_applicable/unresolved/rejected.

        `rejected` means the ledger has no record backing any claim yet --
        neither a positive observation nor a genuine search attempt. It is
        not a public Task 0 disposition value; stop_decision() treats it as
        "not yet safe to call unresolved".

        A conditional question is `not_applicable` only when its precondition
        question was never observed at all -- matching Task 0's fixture
        ("conditional 질문의 선행 조건이 관찰되지 않음"). Once the precondition has
        actually been looked at, the conditional question stands on its own
        record instead of being dismissed, since the ledger never stores the
        precondition's resolved value to judge relevance from.
        """

        coverage = self._questions.get(question.question_id)
        if coverage is not None:
            if coverage.conflicting_evidence_count > 0:
                return "conflicting"
            if coverage.positive_evidence_count > 0:
                return "confirmed"
        if question.importance == QuestionImportance.CONDITIONAL and question.depends_on_question_id:
            if question.depends_on_question_id not in self._questions:
                return "not_applicable"
        if coverage is not None and coverage.has_search_scope and coverage.has_search_pattern and coverage.observation_count > 0:
            return "unresolved"
        return "rejected"

    def stop_decision(
        self,
        policy: ExplorationPolicy,
        *,
        total_evidence_count: int,
        positive_without_evidence: bool = False,
        bounded_stop_triggered: bool = False,
    ) -> StopDecision:
        """Mechanically apply the Task 0 stop-gate truth table.

        `synthetic_values` is always empty: this method only ever reports a
        disposition per question_id, never invents a port, image, or any
        other domain value.
        """

        if total_evidence_count == 0:
            return StopDecision(False, "no_evidence: 분석 제출에는 최소 하나의 Evidence가 필요합니다.", (), {})
        if positive_without_evidence:
            return StopDecision(False, "ungrounded_positive_value: positive 값에는 Evidence가 필요합니다.", (), {})
        if bounded_stop_triggered:
            return StopDecision(True, "bounded_stop: duplicate, no-progress, 또는 iteration budget으로 종료합니다.", ("failed", "partial"), {})

        dispositions = {question.question_id: self.disposition(question) for question in policy.questions}
        required_ids = {question.question_id for question in policy.questions if question.importance == QuestionImportance.REQUIRED}

        conflicting_ids = sorted(qid for qid, status in dispositions.items() if status == "conflicting")
        if conflicting_ids:
            return StopDecision(True, f"conflicting_no_auto_select: {', '.join(conflicting_ids)}", ("partial",), {})

        required_rejected = sorted(qid for qid in required_ids if dispositions[qid] == "rejected")
        if required_rejected:
            return StopDecision(
                True,
                f"insufficient_exploration: required 질문을 아직 충분히 탐색하지 않았습니다 ({', '.join(required_rejected)}).",
                ("partial",),
                {},
            )

        required_unresolved = sorted(qid for qid in required_ids if dispositions[qid] == "unresolved")
        if required_unresolved:
            return StopDecision(
                True,
                f"genuine_unresolved: required 질문을 탐색 범위 내에서 확인하지 못했습니다 ({', '.join(required_unresolved)}).",
                ("partial",),
                {},
            )

        other_gaps = sorted(
            qid for qid, status in dispositions.items() if qid not in required_ids and status in ("unresolved", "rejected")
        )
        if other_gaps:
            return StopDecision(
                True,
                f"unresolved: optional 또는 conditional 질문 값을 만들어 내지 않고 미확인으로 남깁니다 ({', '.join(other_gaps)}).",
                ("complete", "partial"),
                {},
            )

        not_applicable_ids = sorted(qid for qid, status in dispositions.items() if status == "not_applicable")
        if not_applicable_ids:
            # not_applicable never blocks submission -- surfaced here only so
            # it is auditable in run_metadata instead of silently vanishing
            # into the same reason as a fully-confirmed run.
            return StopDecision(
                True,
                f"not_applicable_precondition: 선행 조건이 관찰되지 않아 조건부 질문을 not_applicable로 남깁니다 ({', '.join(not_applicable_ids)}).",
                ("complete", "partial"),
                {},
            )

        return StopDecision(True, "confirmed_or_inferred: required 질문이 모두 확인됐습니다.", ("complete", "partial"), {})
