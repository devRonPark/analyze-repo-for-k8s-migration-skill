"""Bounded, server-computed per-stage evidence surveys.

Walks a fixed high-signal path/pattern allowlist per stage in a stable order
and issues at most SURVEY_OBSERVATION_CAP observations through the same
ObservationRegistry the generic evidence tools use, so a stage always starts
with grounded evidence already in its handoff instead of having to search for
it. See docs/superpowers/specs/2026-08-09-bounded-stage-surveys-design.md.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .read import redact_text
from .safe_paths import safe_path

SURVEY_OBSERVATION_CAP = 12

# stage -> ordered categories -> ordered (glob, content_pattern_or_None)
# candidates. Every candidate in a category is checked; each match issues its
# own present observation (a category can surface more than one file). A
# category with zero matches issues exactly one absence observation, never
# one per missing candidate name.
_STAGE_ALLOWLIST: dict[str, tuple[tuple[str, tuple[tuple[str, str | None], ...]], ...]] = {
    "discovery": (
        (
            "build/package manifests",
            (
                ("pom.xml", None),
                ("build.gradle", None),
                ("build.gradle.kts", None),
                ("package.json", None),
                ("requirements.txt", None),
                ("pyproject.toml", None),
                ("go.mod", None),
            ),
        ),
        (
            "container and orchestration declarations",
            (
                ("Dockerfile", None),
                ("docker-compose.yml", None),
                ("docker-compose.yaml", None),
                ("**/*.k8s.yaml", None),
                ("**/*.k8s.yml", None),
            ),
        ),
        (
            "startup descriptors",
            (
                ("web.xml", None),
                ("**/web.xml", None),
                ("applicationContext.xml", None),
                ("**/applicationContext.xml", None),
                ("Procfile", None),
            ),
        ),
        (
            "runtime configuration",
            (
                (".env", None),
                (".env.example", None),
                ("**/application.properties", None),
                ("**/application.yml", None),
                ("**/application.yaml", None),
            ),
        ),
    ),
    "execution": (
        (
            "build commands",
            (
                ("Dockerfile", r"^\s*RUN\s"),
                ("mvnw", None),
                ("gradlew", None),
                ("Makefile", None),
            ),
        ),
        (
            "image definitions",
            (
                ("Dockerfile", r"^\s*FROM\s"),
                ("docker-compose.yml", r"image\s*:"),
                ("docker-compose.yaml", r"image\s*:"),
            ),
        ),
        (
            "entrypoints",
            (
                ("Dockerfile", r"^\s*(ENTRYPOINT|CMD)\s"),
                ("docker-compose.yml", r"command\s*:"),
                ("docker-compose.yaml", r"command\s*:"),
                ("Procfile", None),
            ),
        ),
        (
            "listening ports",
            (
                ("Dockerfile", r"^\s*EXPOSE\s"),
                ("docker-compose.yml", r"ports\s*:"),
                ("docker-compose.yaml", r"ports\s*:"),
            ),
        ),
        (
            "runtime launch configuration",
            (
                ("docker-compose.yml", r"environment\s*:"),
                ("docker-compose.yaml", r"environment\s*:"),
                (".env", None),
            ),
        ),
    ),
    "relationships": (
        (
            "declared dependencies",
            (
                ("pom.xml", r"<dependency>"),
                ("package.json", r'"dependencies"'),
                ("requirements.txt", None),
                ("go.mod", r"require"),
            ),
        ),
        (
            "connection settings",
            (
                ("docker-compose.yml", r"(?i)(database_url|db_host|host\s*:)"),
                ("docker-compose.yaml", r"(?i)(database_url|db_host|host\s*:)"),
                ("**/application.properties", r"(?i)(url|host)"),
                ("**/application.yml", r"(?i)(url|host)"),
            ),
        ),
        (
            "brokers, queues, caches",
            (
                ("docker-compose.yml", r"(?i)(redis|rabbitmq|kafka|activemq)"),
                ("docker-compose.yaml", r"(?i)(redis|rabbitmq|kafka|activemq)"),
                ("**/application.properties", r"(?i)(redis|rabbitmq|kafka)"),
            ),
        ),
        (
            "identity and external service configuration",
            (
                ("docker-compose.yml", r"(?i)(oauth|auth|api_key)"),
                (".env", r"(?i)(oauth|auth|api)"),
            ),
        ),
    ),
    "boundaries": (
        (
            "independent start definitions",
            (
                ("docker-compose.yml", r"^\s*\S+\s*:\s*$"),
                ("docker-compose.yaml", r"^\s*\S+\s*:\s*$"),
                ("Procfile", None),
            ),
        ),
        (
            "worker or schedule declarations",
            (
                ("docker-compose.yml", r"(?i)(worker|celery|cron|scheduler)"),
                ("docker-compose.yaml", r"(?i)(worker|celery|cron|scheduler)"),
                ("Procfile", r"(?i)worker"),
            ),
        ),
        (
            "lifecycle signals",
            (
                ("Dockerfile", r"(?i)healthcheck"),
                ("docker-compose.yml", r"(?i)healthcheck"),
                ("docker-compose.yaml", r"(?i)healthcheck"),
            ),
        ),
        (
            "persistent writable locations",
            (
                ("docker-compose.yml", r"volumes\s*:"),
                ("docker-compose.yaml", r"volumes\s*:"),
            ),
        ),
    ),
    "contracts": (
        (
            "configuration timing",
            (
                ("Dockerfile", r"^\s*ENV\s"),
                ("docker-compose.yml", r"environment\s*:"),
                ("docker-compose.yaml", r"environment\s*:"),
            ),
        ),
        (
            "credentials markers",
            (
                (".env", None),
                (".env.example", None),
                ("docker-compose.yml", r"(?i)(secret|password|_key)"),
            ),
        ),
        (
            "health or readiness signals",
            (
                ("Dockerfile", r"(?i)healthcheck"),
                ("docker-compose.yml", r"(?i)healthcheck"),
                ("docker-compose.yaml", r"(?i)healthcheck"),
            ),
        ),
        (
            "observability configuration",
            (
                ("docker-compose.yml", r"(?i)(logging\s*:|log_level)"),
                ("docker-compose.yaml", r"(?i)(logging\s*:|log_level)"),
            ),
        ),
    ),
}


def _safe_matches(root: Path, glob: str) -> list[Path]:
    try:
        candidates = sorted(x for x in root.glob(glob) if x.is_file())
    except (OSError, ValueError):
        return []
    safe: list[Path] = []
    for candidate in candidates:
        try:
            safe.append(safe_path(root, candidate.resolve().relative_to(root.resolve())))
        except ValueError:
            continue
    return safe


def _select_line(path: Path, pattern: str | None) -> tuple[int, str] | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    matcher = re.compile(pattern) if pattern else None
    for index, line in enumerate(lines, 1):
        if matcher is not None and not matcher.search(line):
            continue
        stripped = line.strip()
        if not stripped:
            continue
        return index, redact_text(stripped, path.suffix)
    return None


def _issue_present(
    registry: Any, stage: str, root: Path, match: Path, line_number: int, text: str, category: str
) -> dict[str, Any]:
    issued = registry.issue_present(stage, match, line_number, line_number, text)
    return {
        "observation_ref": issued["observation_ref"],
        "status": "confirmed",
        "category": category,
        "reference": f"{match.relative_to(root.resolve()).as_posix()}:{line_number}",
    }


def _find_unused_match(
    root: Path, candidates: tuple[tuple[str, str | None], ...], used_locations: set[tuple[str, int]]
) -> tuple[Path, int, str] | None:
    for glob, pattern in candidates:
        for match in _safe_matches(root, glob):
            selection = _select_line(match, pattern)
            if selection is None:
                continue
            line_number, text = selection
            location = (match.relative_to(root.resolve()).as_posix(), line_number)
            if location in used_locations:
                continue
            return match, line_number, text
    return None


def _slots_needing_fresh_evidence(required_slots: list[str], fact_statuses: Any) -> list[str]:
    """Report slots with no unclaimed predecessor fact from an allowed stage."""
    from ..stage_contracts import assign_report_slot_facts

    assignment = assign_report_slot_facts(required_slots, dict(fact_statuses or {}))
    return [slot_id for slot_id, fact_ref in assignment.items() if fact_ref is None]


def compute_survey(
    root: Path,
    stage: str,
    registry: Any,
    *,
    required_report_slots: list[str] | None = None,
    fact_statuses: Any = None,
) -> dict[str, Any]:
    """Compute the bounded, redacted evidence set the given stage starts with.

    For Contracts, also supplies one distinct observation per required report
    slot that has no eligible predecessor fact to reuse (see
    stage_contracts.py's "report slot evidence duplicate" rule, which forbids
    two slots from sharing evidence), so routine report-slot grounding does
    not require additional target reads.
    """
    categories = _STAGE_ALLOWLIST.get(stage, ())
    observations: list[dict[str, Any]] = []
    coverage: dict[str, bool] = {}
    used_locations: set[tuple[str, int]] = set()
    for category_name, candidates in categories:
        if len(observations) >= SURVEY_OBSERVATION_CAP:
            coverage[category_name] = False
            continue
        category_hit = False
        for glob, pattern in candidates:
            if len(observations) >= SURVEY_OBSERVATION_CAP:
                break
            for match in _safe_matches(root, glob):
                if len(observations) >= SURVEY_OBSERVATION_CAP:
                    break
                selection = _select_line(match, pattern)
                if selection is None:
                    continue
                line_number, text = selection
                location = (match.relative_to(root.resolve()).as_posix(), line_number)
                observations.append(_issue_present(registry, stage, root, match, line_number, text, category_name))
                used_locations.add(location)
                category_hit = True
        if not category_hit:
            issued = registry.issue_absence(
                stage, category_name, "|".join(glob for glob, _ in candidates), None
            )
            observations.append(
                {
                    "observation_ref": issued["observation_ref"],
                    "status": "unknown",
                    "category": category_name,
                }
            )
        coverage[category_name] = category_hit

    if stage == "contracts" and required_report_slots:
        all_candidates = tuple(candidate for _, candidates in categories for candidate in candidates)
        for slot_id in _slots_needing_fresh_evidence(required_report_slots, fact_statuses or {}):
            if len(observations) >= SURVEY_OBSERVATION_CAP:
                break
            found = _find_unused_match(root, all_candidates, used_locations)
            if found is None:
                issued = registry.issue_absence(stage, f"report_slot:{slot_id}", "|".join(glob for glob, _ in all_candidates), None)
                observations.append(
                    {"observation_ref": issued["observation_ref"], "status": "unknown", "category": f"report_slot:{slot_id}"}
                )
                continue
            match, line_number, text = found
            location = (match.relative_to(root.resolve()).as_posix(), line_number)
            observations.append(_issue_present(registry, stage, root, match, line_number, text, f"report_slot:{slot_id}"))
            used_locations.add(location)

    return {
        "stage": stage,
        "surveyed": True,
        "categories": coverage,
        "observations": observations,
    }
