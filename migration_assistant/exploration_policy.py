"""Declarative Kubernetes migration exploration registry.

This registry supplies observation priority and search hints only. It never
resolves a domain value -- every positive value in `AnalysisResult` must
come from an actual file observation the Agent made, carrying its own
Evidence reference. Deleting an entry here must never break exploration:
callers fall back to an empty rule set for any question or ecosystem this
policy does not cover, and the Agent proceeds generically.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import StrEnum


class QuestionImportance(StrEnum):
    REQUIRED = "required"
    CONDITIONAL = "conditional"
    OPTIONAL = "optional"


@dataclass(frozen=True, slots=True)
class ExplorationQuestion:
    """One Kubernetes migration question the Agent must dispose of."""

    question_id: str
    importance: QuestionImportance
    description: str
    depends_on_question_id: str | None = None


@dataclass(frozen=True, slots=True)
class SignalRule:
    """A declarative hint about where a strong observation tends to live.

    Carries priority, file globs, and search patterns only -- never a
    resolved port, image, command, or workload value.
    """

    key: str
    question_ids: tuple[str, ...]
    priority: int
    file_globs: tuple[str, ...]
    search_patterns: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ExplorationPolicy:
    """Ordered registry of migration questions and signal rules."""

    questions: tuple[ExplorationQuestion, ...]
    rules: tuple[SignalRule, ...]

    def question_ids(self) -> tuple[str, ...]:
        return tuple(question.question_id for question in self.questions)

    def question(self, question_id: str) -> ExplorationQuestion | None:
        for question in self.questions:
            if question.question_id == question_id:
                return question
        return None

    def rules_for(self, question_id: str) -> tuple[SignalRule, ...]:
        """Rules touching `question_id`, ordered by descending priority.

        Returns an empty tuple for any question_id this policy does not
        recognize -- treat that as "use the generic path", not an error.
        """

        matches = [rule for rule in self.rules if question_id in rule.question_ids]
        return tuple(sorted(matches, key=lambda rule: rule.priority, reverse=True))


def match_rules(policy: ExplorationPolicy, *, path: str | None = None, text: str | None = None) -> tuple[SignalRule, ...]:
    """Rules whose file_globs match `path` or whose search_patterns appear in `text`.

    This matches only what was actually observed -- an already-seen path or
    an already-seen line of text -- never a guessed name. An unmatched
    observation simply returns an empty tuple; that is the generic fallback,
    not an error.
    """

    if path is None and text is None:
        return ()
    basename = path.rsplit("/", 1)[-1] if path else None
    matched = []
    for rule in policy.rules:
        path_hit = path is not None and any(
            fnmatch.fnmatch(path, glob) or (basename is not None and fnmatch.fnmatch(basename, glob))
            for glob in rule.file_globs
        )
        text_hit = text is not None and any(pattern.casefold() in text.casefold() for pattern in rule.search_patterns)
        if path_hit or text_hit:
            matched.append(rule)
    return tuple(sorted(matched, key=lambda rule: rule.priority, reverse=True))


DEFAULT_MIGRATION_POLICY = ExplorationPolicy(
    questions=(
        ExplorationQuestion(
            question_id="workload_deployment_unit",
            importance=QuestionImportance.REQUIRED,
            description="Kubernetes에 배포할 최소 단위(component)가 무엇인가",
        ),
        ExplorationQuestion(
            question_id="production_startup",
            importance=QuestionImportance.REQUIRED,
            description="프로덕션 기동 명령이 무엇인가",
        ),
        ExplorationQuestion(
            question_id="build_stage",
            importance=QuestionImportance.REQUIRED,
            description="의존성 설치, 애플리케이션 빌드, image 빌드 단계가 무엇인가",
        ),
        ExplorationQuestion(
            question_id="receiving_port",
            importance=QuestionImportance.REQUIRED,
            description="애플리케이션이 수신하는 port가 무엇인가",
        ),
        ExplorationQuestion(
            question_id="runtime_config_and_secret_names",
            importance=QuestionImportance.REQUIRED,
            description="런타임 환경변수와 Secret의 이름이 무엇인가",
        ),
        ExplorationQuestion(
            question_id="external_dependency",
            importance=QuestionImportance.CONDITIONAL,
            description="외부 DB, broker, API 의존성이 있는가",
            depends_on_question_id="runtime_config_and_secret_names",
        ),
        ExplorationQuestion(
            question_id="writable_state_path",
            importance=QuestionImportance.OPTIONAL,
            description="컨테이너가 기록해야 하는 writable path가 있는가",
        ),
    ),
    rules=(
        SignalRule(
            key="container_or_process_descriptor",
            question_ids=("production_startup", "receiving_port", "build_stage"),
            priority=10,
            file_globs=("Dockerfile*", "compose*.yml", "compose*.yaml", "docker-compose*.yml"),
            search_patterns=("ENTRYPOINT", "CMD", "EXPOSE"),
            reason="컨테이너/프로세스 기동 서술이 프로덕션 기동과 port에 가장 직접적인 신호다.",
        ),
        SignalRule(
            key="build_or_package_manifest",
            question_ids=("build_stage", "workload_deployment_unit"),
            priority=9,
            file_globs=("pom.xml", "build.gradle*", "package.json", "go.mod", "requirements*.txt", "pyproject.toml"),
            search_patterns=("<build>", "scripts", "main", "entrypoint"),
            reason="build/package manifest는 빌드 단계와 배포 단위 후보를 드러낸다.",
        ),
        SignalRule(
            key="config_and_deployment_descriptor",
            question_ids=("runtime_config_and_secret_names", "external_dependency", "receiving_port"),
            priority=8,
            file_globs=("application*.yml", "application*.properties", ".env*", "config/*.yml"),
            search_patterns=("PORT", "DATABASE_URL", "SECRET", "HOST"),
            reason="설정 파일은 환경변수/Secret 이름과 외부 의존성 후보를 드러낸다.",
        ),
        SignalRule(
            key="writable_path_descriptor",
            question_ids=("writable_state_path",),
            priority=5,
            file_globs=("Dockerfile*", "docker-compose*.yml"),
            search_patterns=("VOLUME", "mount"),
            reason="VOLUME, mount 선언이 쓰기 경로 후보를 드러낸다.",
        ),
    ),
)
