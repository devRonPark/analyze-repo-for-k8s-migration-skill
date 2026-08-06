"""Project exploration coverage into Secret-safe next-observation guidance.

Feedback path: Tool result -> ExplorationLedger update -> CoverageSnapshot
-> ContextProjection -> next model context metadata -> Agent chooses an
allowed Tool. The projection never resolves a domain value, never carries a
path, and never forces a specific next Tool call -- it only tells the model
which migration questions are still uncovered and how important they are.
"""

from __future__ import annotations

from dataclasses import dataclass

from .exploration_ledger import ExplorationLedger
from .exploration_policy import DEFAULT_MIGRATION_POLICY, ExplorationPolicy, QuestionImportance

_IMPORTANCE_ORDER = {
    QuestionImportance.REQUIRED.value: 0,
    QuestionImportance.CONDITIONAL.value: 1,
    QuestionImportance.OPTIONAL.value: 2,
}


@dataclass(frozen=True, slots=True)
class CoverageSnapshot:
    """A point-in-time, Secret-safe view of which questions have no observation yet."""

    unresolved_question_ids: tuple[str, ...]


def build_coverage_snapshot(
    ledger: ExplorationLedger, policy: ExplorationPolicy = DEFAULT_MIGRATION_POLICY
) -> CoverageSnapshot:
    """A question is unresolved here only in the sense of "not yet observed".

    The stop-gate truth table (Task 5) makes the final confirmed/inferred/
    unresolved/conflicting/not_applicable determination; this snapshot only
    drives what to look at next.
    """

    observed = ledger.summary()["questions"]
    unresolved = tuple(question.question_id for question in policy.questions if question.question_id not in observed)
    return CoverageSnapshot(unresolved_question_ids=unresolved)


def project_next_observations(
    snapshot: CoverageSnapshot, policy: ExplorationPolicy = DEFAULT_MIGRATION_POLICY
) -> list[dict[str, object]]:
    """Secret-safe compact hints: which questions still need an observation, and why.

    Each entry carries only question_id, importance, and the signal_rule_ids
    that touch it -- never a resolved value, a path, or a forced next Tool.
    Unknown question_ids are skipped rather than raised, matching the
    registry's generic-fallback contract.
    """

    entries: list[dict[str, object]] = []
    for question_id in snapshot.unresolved_question_ids:
        question = policy.question(question_id)
        if question is None:
            continue
        entries.append(
            {
                "question_id": question_id,
                "importance": question.importance.value,
                "signal_rule_ids": [rule.key for rule in policy.rules_for(question_id)],
            }
        )
    entries.sort(key=lambda entry: _IMPORTANCE_ORDER[str(entry["importance"])])
    return entries
