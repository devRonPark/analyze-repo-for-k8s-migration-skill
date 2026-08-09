"""Dependency-free static MCP JSON-RPC schemas and response helpers."""
from __future__ import annotations

import json
from typing import Any

from .stage_contracts import (
    candidate_exclusion_contract,
    relationship_edge_contract,
    report_state_contract,
    workload_unit_contract,
)
from .validation import CLIENT_STAGE_FIELDS

SERVER_INFO = {"name": "trusted-analysis-pipeline", "version": "0.2.0"}
STAGES = ("discovery", "execution", "relationships", "boundaries", "contracts")
STAGE_TOOL_BY_STAGE = {stage: f"submit_{stage}" for stage in STAGES}
TOOL_ORDER = (
    "start_analysis",
    "read_evidence",
    "list_target_paths",
    "locate_evidence",
    "get_target_git_metadata",
    "submit_discovery",
    "submit_execution",
    "submit_relationships",
    "submit_boundaries",
    "submit_contracts",
    "reopen_analysis",
    "finalize_analysis",
)

ERROR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "retryable", "issues"],
    "properties": {
        "code": {"type": "string"},
        "retryable": {"type": "boolean"},
        "issues": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 300}},
    },
}
_IDENTIFIER = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"}

# A stage-bounded survey observation: server-issued, redacted, and either a
# present finding (with a safe path:line reference) or a scoped absence
# marker for a category with no match. See "survey" in HANDOFF_SCHEMA below
# and docs/superpowers/specs/2026-08-09-bounded-stage-surveys-design.md.
_SURVEY_OBSERVATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["observation_ref", "status", "category"],
    "properties": {
        "observation_ref": _IDENTIFIER,
        "status": {"type": "string", "enum": ["confirmed", "unknown"]},
        "category": {"type": "string"},
        "reference": {"type": "string"},
    },
}
_SURVEY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["stage", "surveyed", "categories", "observations"],
    "properties": {
        "stage": {"type": "string", "enum": list(STAGES)},
        "surveyed": {"const": True},
        "categories": {"type": "object"},
        "observations": {"type": "array", "maxItems": 12, "items": _SURVEY_OBSERVATION_SCHEMA},
    },
}
_BUDGET_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["precision_calls_remaining", "submit_rejections_remaining"],
    "properties": {
        "precision_calls_remaining": {"type": "integer", "minimum": 0},
        "submit_rejections_remaining": {"type": "integer", "minimum": 0},
    },
}

HANDOFF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "analysis_id", "mode", "completed_stage", "revision", "transition_token", "next_skill", "accepted_output", "stage_input"],
    "properties": {
        "status": {"const": "accepted"},
        "analysis_id": {"type": "string", "pattern": "^an_[A-Za-z0-9_-]{8,}$"},
        "mode": {"type": "string", "enum": ["summary", "detailed"]},
        "completed_stage": {"type": ["string", "null"], "enum": [None, *STAGES]},
        "revision": {"type": "integer", "minimum": 0},
        "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"},
        "next_skill": {"type": "string"},
        "accepted_output": {"type": "object"},
        # stage_input's other keys vary per stage, so this stays open
        # (no additionalProperties:False); survey/budget are constrained
        # because every non-finalize stage_input carries them in this shape.
        "stage_input": {
            "type": "object",
            "properties": {"survey": _SURVEY_SCHEMA, "budget": _BUDGET_SCHEMA},
        },
    },
}


def _tool(name: str, description: str, required: list[str], properties: dict[str, Any], *, read_only: bool = False) -> dict[str, Any]:
    value = {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        },
        "outputSchema": {"oneOf": [HANDOFF_SCHEMA, ERROR_SCHEMA, {"type": "object"}]},
    }
    if read_only:
        value["annotations"] = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
    return value


_ENVELOPE = {
    "analysis_id": {"type": "string", "pattern": "^an_[A-Za-z0-9_-]{8,}$"},
    "revision": {"type": "integer", "minimum": 0},
    "transition_token": {"type": "string", "pattern": "^tr_[A-Za-z0-9_-]{8,}$"},
}

_IDENTIFIER_LIST = {"type": "array", "items": _IDENTIFIER}
_EVIDENCE_DECLARATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["alias", "observation_ref"],
    "properties": {"alias": _IDENTIFIER, "observation_ref": _IDENTIFIER},
}
_CLAIM_DECLARATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "status", "evidence_aliases"],
    "properties": {
        "id": _IDENTIFIER,
        "status": {"type": "string", "enum": ["confirmed", "inferred", "unknown", "conflicted", "not_applicable"]},
        "evidence_aliases": _IDENTIFIER_LIST,
        "scope": {"type": "string"},
        "blocked_decision": _IDENTIFIER,
    },
}
_RULE_APPLICATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rule_id", "evidence_aliases", "process_or_candidate_ids", "decision_id"],
    "properties": {
        "rule_id": _IDENTIFIER,
        "evidence_aliases": _IDENTIFIER_LIST,
        "process_or_candidate_ids": _IDENTIFIER_LIST,
        "decision_id": _IDENTIFIER,
    },
}


def _contract_value_schema(value: Any) -> dict[str, Any]:
    """Translate an executable contract field into its public JSON Schema."""
    if isinstance(value, list):
        return {"type": "array", "items": _IDENTIFIER}
    if value == "boolean":
        return {"type": "boolean"}
    if value in {"identifier", "identifier|unknown"} or isinstance(value, str) and value.endswith(" identifier"):
        return _IDENTIFIER
    if isinstance(value, str) and "|" in value:
        return {"type": "string", "enum": value.split("|")}
    raise ValueError("invalid public stage payload contract")


def _contract_object_schema(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(contract),
        "properties": {field: _contract_value_schema(value) for field, value in contract.items()},
    }


def _stage_payload_schema(stage: str) -> dict[str, Any]:
    """Expose the stage-specific client payload contract in the MCP catalog."""
    properties: dict[str, Any] = {
        "schema_version": {"const": 1},
        "stage": {"const": stage},
        "evidence": {"type": "array", "items": _EVIDENCE_DECLARATION},
        "claims": {"type": "array", "items": _CLAIM_DECLARATION},
        "rule_applications": {"type": "array", "items": _RULE_APPLICATION},
    }
    for field in sorted(CLIENT_STAGE_FIELDS[stage] - set(properties)):
        properties[field] = _IDENTIFIER_LIST
    if stage == "relationships":
        properties["graph_edges"] = {
            "type": "array",
            "items": _contract_object_schema(relationship_edge_contract()),
        }
    if stage == "boundaries":
        properties["workload_units"] = {
            "type": "array",
            "items": _contract_object_schema(workload_unit_contract()),
        }
        properties["candidate_exclusions"] = {
            "type": "array",
            "items": _contract_object_schema(candidate_exclusion_contract()),
        }
    if stage == "contracts":
        properties["report_slots"] = {
            "type": "array",
            "items": _contract_object_schema(report_state_contract()["report_slot"]),
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(CLIENT_STAGE_FIELDS[stage]),
        "properties": properties,
    }

TOOLS = [
    _tool(
        "start_analysis",
        "Start a read-only local Git analysis for the selected target path and mode.",
        ["target_path", "mode"],
        {"target_path": {"type": "string", "minLength": 1}, "mode": {"type": "string", "enum": ["summary", "detailed"]}},
    ),
    _tool("read_evidence", "Read bounded redacted evidence from the active target.", ["path"], {"path": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, read_only=True),
    _tool("list_target_paths", "List bounded paths from the active target.", ["pattern"], {"pattern": {"type": "string"}, "path": {"type": "string"}}, read_only=True),
    _tool("locate_evidence", "Locate redacted evidence or a scoped absence in the active target.", ["glob"], {"glob": {"type": "string"}, "path": {"type": "string"}, "pattern": {"type": "string"}}, read_only=True),
    _tool("get_target_git_metadata", "Get the active target Git revision metadata.", [], {}, read_only=True),
]
TOOLS.extend(
    _tool(
        STAGE_TOOL_BY_STAGE[stage],
        (
            "Checkpoint: this is the only valid completion of the current Discovery Vertical Slice. "
            "Copy the incoming handoff envelope unchanged; submit the payload required by this tool schema using observation aliases, never raw repository evidence. "
            "Each payload.evidence observation_ref must be issued in this current stage; incoming *_fact_refs are accepted facts, never observation refs. "
            "Do not draft a user-facing report before an accepted response."
            if stage == "discovery"
            else (
                "Checkpoint: this is the only valid completion of the current Execution Vertical Slice after grounding build, runtime, startup, image, or port claims. "
                "Copy the incoming handoff envelope unchanged; submit the payload required by this tool schema using observation aliases, never raw repository evidence. "
                "Each payload.evidence observation_ref must be issued in this current stage; incoming *_fact_refs are accepted facts, never observation refs. "
                "Do not draft a user-facing report before an accepted response."
                if stage == "execution"
                else (
                    "Checkpoint: this is the only valid completion of the current Relationships Vertical Slice after grounding dependency and external runtime claims. "
                    "Copy the incoming handoff envelope unchanged; submit the payload required by this tool schema using observation aliases, never raw repository evidence. "
                    "Each payload.evidence observation_ref must be issued in this current stage; incoming *_fact_refs are accepted facts, never observation refs. "
                    "Do not draft a user-facing report before an accepted response."
                    if stage == "relationships"
                else (
                    "Checkpoint: this is the only valid completion of the current Workload Boundary Vertical Slice after grounding unit and lifecycle claims. "
                    "Copy the incoming handoff envelope unchanged; submit the payload required by this tool schema using observation aliases, never raw repository evidence. "
                    "Each payload.evidence observation_ref must be issued in this current stage; incoming *_fact_refs are accepted facts, never observation refs. "
                    "Do not draft a user-facing report before an accepted response."
                    if stage == "boundaries"
                    else "Checkpoint: this is the only valid completion of the current Gap Analysis Quality Gate after every server-selected report slot has an accepted fact reference or scoped evidence claim. "
                    "Copy the incoming handoff envelope unchanged; submit the payload required by this tool schema using observation aliases, never raw repository evidence. "
                    "Each payload.evidence observation_ref must be issued in this current stage; incoming *_fact_refs are accepted facts, never observation refs. "
                    "Do not draft a user-facing report before an accepted response."
                )
                )
            )
        ),
        [*list(_ENVELOPE), "payload"],
        {**_ENVELOPE, "payload": _stage_payload_schema(stage)},
    )
    for stage in STAGES
)
TOOLS.extend(
    [
        _tool("reopen_analysis", "Reopen an accepted earlier stage after new evidence invalidates it.", ["analysis_id", "revision", "transition_token", "stage", "reason"], {"analysis_id": _ENVELOPE["analysis_id"], "revision": _ENVELOPE["revision"], "transition_token": _ENVELOPE["transition_token"], "stage": {"type": "string", "enum": list(STAGES)}, "reason": {"type": "string", "minLength": 3, "maxLength": 500}}),
        _tool("finalize_analysis", "Finalize accepted report state and return canonical Markdown.", ["analysis_id", "revision", "transition_token"], {key: _ENVELOPE[key] for key in ("analysis_id", "revision", "transition_token")}),
    ]
)
assert tuple(tool["name"] for tool in TOOLS) == TOOL_ORDER


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    structured = value if isinstance(value, dict) else {"value": value}
    text = value if isinstance(value, str) else json.dumps(structured, ensure_ascii=False, sort_keys=True)
    result = {"content": [{"type": "text", "text": text[:24_000]}], "structuredContent": structured}
    if is_error:
        result["isError"] = True
    return result


def markdown_result(markdown: str, structured: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": markdown}], "structuredContent": structured}
