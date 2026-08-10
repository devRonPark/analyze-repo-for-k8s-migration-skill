"""Provider-free smoke test for the sealed, installed static MCP bundle."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime" / "python"))

from scripts.build_dist import build
from scripts.install_distribution import PROJECT_ID, install_bundle
from analysis_pipeline.stage_contracts import assign_report_slot_facts


CLIENT_CONFIGS = ("opencode-mcp.json", "claude-code-mcp.json", "gemini-cli-mcp.json")
_CHILD_ENVIRONMENT_NAMES = ("SystemRoot", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP")
_NETWORK_GUARD = """
import runpy
import socket
import sys

def network_disabled(*args, **kwargs):
    raise RuntimeError("network_disabled")

for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    if hasattr(socket, name):
        setattr(socket, name, network_disabled)

def deny_network_audit(event, arguments):
    if event.startswith("socket.") or event in {"urllib.Request", "http.client.connect"}:
        raise RuntimeError("network_disabled")

sys.addaudithook(deny_network_audit)
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def isolated_runtime_environment() -> dict[str, str]:
    """Return the minimum child environment for the no-install smoke runtime."""
    environment = {
        name: os.environ[name]
        for name in _CHILD_ENVIRONMENT_NAMES
        if os.environ.get(name)
    }
    environment.update({"PIP_NO_INDEX": "1", "PYTHONUTF8": "1"})
    return environment


def isolated_launcher_command(command: list[str]) -> list[str]:
    """Run the template-selected launcher with no site packages or network."""
    assert len(command) == 2 and all(isinstance(item, str) and item for item in command)
    return [command[0], "-I", "-S", "-X", "utf8", "-c", _NETWORK_GUARD, command[1]]


def envelope(handoff: dict[str, Any]) -> dict[str, Any]:
    return {key: handoff[key] for key in ("analysis_id", "revision", "transition_token")}


def discovery_payload(observation_ref: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stage": "discovery",
        "evidence": [{"alias": "container", "observation_ref": observation_ref}],
        "claims": [{"id": "claim-container", "status": "confirmed", "evidence_aliases": ["container"]}],
        "rule_applications": [],
        "signals": ["container-runtime"],
        "candidate_ids": ["candidate-web"],
        "decisions": ["decision-runtime"],
    }


def execution_payload(observation_ref: str, discovery_fact_refs: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stage": "execution",
        "evidence": [{"alias": "runtime", "observation_ref": observation_ref}],
        "claims": [{"id": "claim-process", "status": "confirmed", "evidence_aliases": ["runtime"]}],
        "rule_applications": [],
        "discovery_fact_refs": discovery_fact_refs,
        "process_ids": ["process-web"],
    }


def relationships_payload(
    observation_ref: str,
    discovery_fact_refs: list[str],
    execution_fact_refs: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stage": "relationships",
        "evidence": [{"alias": "dependency", "observation_ref": observation_ref}],
        "claims": [{"id": "claim-api-db", "status": "confirmed", "evidence_aliases": ["dependency"]}],
        "rule_applications": [],
        "discovery_fact_refs": discovery_fact_refs,
        "execution_fact_refs": execution_fact_refs,
        "graph_edges": [{
            "id": "edge-api-db",
            "source_process_id": "process-web",
            "target_id": "external-db",
            "target_kind": "external_system",
            "dependency_type": "data_store",
            "mechanism": "postgres",
            "endpoint_name": "database-url",
            "required_for_function": "confirmed",
            "startup_use": "unknown",
            "management_boundary": "externally_managed",
            "timing": "runtime",
            "execution_location": "server_process",
            "claim_ids": ["claim-api-db"],
            "status": "confirmed",
        }],
    }


def boundaries_payload(observation_ref: str, handoff: dict[str, Any]) -> dict[str, Any]:
    stage_input = handoff["stage_input"]
    return {
        "schema_version": 1,
        "stage": "boundaries",
        "evidence": [{"alias": "boundary", "observation_ref": observation_ref}],
        "claims": [
            {"id": "claim-web-boundary", "status": "confirmed", "evidence_aliases": ["boundary"]},
            {"id": "claim-web-lifecycle", "status": "confirmed", "evidence_aliases": ["boundary"]},
            {"id": "claim-web-state", "status": "confirmed", "evidence_aliases": ["boundary"]},
            {"id": "claim-web-deployability", "status": "confirmed", "evidence_aliases": ["boundary"]},
        ],
        "rule_applications": [],
        "discovery_fact_refs": stage_input["discovery_fact_refs"],
        "execution_fact_refs": stage_input["execution_fact_refs"],
        "relationship_fact_refs": stage_input["relationship_fact_refs"],
        "workload_units": [{
            "id": "unit-web",
            "process_ids": ["process-web"],
            "candidate_ids": ["candidate-web"],
            "start_definition_status": "confirmed",
            "independent_lifecycle_status": "confirmed",
            "boundary_status": "confirmed",
            "lifecycle": "continuous",
            "state_decision": "externalized",
            "deployable": True,
            "deployability_status": "confirmed",
            "boundary_claim_ids": ["claim-web-boundary"],
            "lifecycle_claim_ids": ["claim-web-lifecycle"],
            "state_claim_ids": ["claim-web-state"],
            "deployability_claim_ids": ["claim-web-deployability"],
        }],
        "candidate_exclusions": [],
    }


def contracts_payload(handoff: dict[str, Any]) -> dict[str, Any]:
    """Build a valid contracts payload from the handoff's pushed survey.

    Report slots either reuse a predecessor fact (assign_report_slot_facts,
    the same greedy exclusive assignment the server's survey uses to decide
    which slots need fresh evidence) or ground a fresh Contracts claim from
    the survey's per-slot observation (stage_input.survey.observations,
    tagged category="report_slot:<slot_id>"). No independent read_evidence
    call is needed: the one-call precision budget is reserved for a
    genuinely blocked decision, not routine per-slot grounding.
    """
    slots = (
        "deployment_targets", "build_image_start", "reachable_port_or_path",
        "runtime_dependencies_state", "execution_conflicts", "credential_exposure",
        "minimum_design_inputs",
    )
    stage_input = handoff["stage_input"]
    assignment = assign_report_slot_facts(list(slots), stage_input["fact_statuses"])
    survey_observations = {
        observation["category"].split(":", 1)[1]: observation["observation_ref"]
        for observation in stage_input["survey"]["observations"]
        if observation["category"].startswith("report_slot:")
    }
    claim_slots = [slot_id for slot_id in slots if assignment[slot_id] is None]
    return {
        "schema_version": 1,
        "stage": "contracts",
        "evidence": [
            {"alias": f"slot-{slot_id}", "observation_ref": survey_observations[slot_id]}
            for slot_id in claim_slots
        ],
        "claims": [
            {"id": f"claim-{slot_id}", "status": "confirmed", "evidence_aliases": [f"slot-{slot_id}"]}
            for slot_id in claim_slots
        ],
        "rule_applications": [],
        "discovery_fact_refs": stage_input["discovery_fact_refs"],
        "execution_fact_refs": stage_input["execution_fact_refs"],
        "relationship_fact_refs": stage_input["relationship_fact_refs"],
        "boundaries_fact_refs": stage_input["boundaries_fact_refs"],
        "report_slots": [
            {
                "id": slot_id,
                "status": "confirmed",
                "fact_refs": [assignment[slot_id]] if assignment[slot_id] is not None else [],
                "claim_ids": [f"claim-{slot_id}"] if slot_id in claim_slots else [],
            }
            for slot_id in slots
        ],
    }


class StdioClient:
    def __init__(self, command: list[str], command_directory: Path) -> None:
        self.process = subprocess.Popen(
            isolated_launcher_command(command),
            cwd=command_directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=isolated_runtime_environment(),
        )
        self.request_id = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.request_id += 1
        request = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params or {}}
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            assert self.process.stderr is not None
            raise AssertionError(f"MCP launcher exited before responding: {self.process.stderr.read()}")
        response = json.loads(line)
        if "error" in response:
            raise AssertionError(f"MCP protocol error: {response['error']}")
        return response["result"]

    def tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        assert self.process.stdin is not None and self.process.stdout is not None and self.process.stderr is not None
        self.process.stdin.close()
        self.process.wait(timeout=20)
        stdout, stderr = self.process.stdout.read(), self.process.stderr.read()
        assert self.process.returncode == 0, stderr or stdout
        assert not stdout, f"unexpected MCP stdout after request responses: {stdout}"
        assert not stderr, f"MCP diagnostics must use no stderr on success: {stderr}"


def result_value(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("structuredContent")
    assert isinstance(value, dict), result
    return value


def accepted(result: dict[str, Any]) -> dict[str, Any]:
    assert not result.get("isError"), result
    value = result_value(result)
    assert value.get("status") == "accepted", value
    return value


def read_observation(client: StdioClient, path: str) -> str:
    value = result_value(client.tool("read_evidence", {"path": path}))
    observation_ref = value.get("observation_ref")
    assert isinstance(observation_ref, str), value
    return observation_ref


def template_command(template: Path, launcher: Path) -> list[str]:
    config = json.loads(template.read_text(encoding="utf-8"))
    server = config.get("mcp", {}).get("analysis") or config["mcpServers"]["analysis"]
    assert isinstance(server, dict) and "cwd" not in server
    command = server["command"] if isinstance(server["command"], list) else [server["command"]]
    values = {
        "ANALYSIS_PIPELINE_PYTHON": sys.executable,
        "ANALYSIS_PIPELINE_LAUNCHER": str(launcher),
    }
    rendered = []
    for item in [*command, *server.get("args", [])]:
        assert isinstance(item, str)
        for name, value in values.items():
            item = item.replace(f"{{env:{name}}}", value).replace(f"${{{name}}}", value)
        rendered.append(item)
    assert rendered == [sys.executable, str(launcher)], rendered
    assert "apiKey" not in json.dumps(server, sort_keys=True)
    return rendered


def make_external_fixture(directory: Path) -> Path:
    target = directory / "external-target"
    target.mkdir()
    (target / "Dockerfile").write_text('FROM python:3.13\nCMD ["python", "app.py"]\n', encoding="utf-8")
    (target / "app.py").write_text("print('ready')\n", encoding="utf-8")
    for command in (
        ["git", "init"],
        ["git", "add", "."],
        ["git", "-c", "user.name=Smoke", "-c", "user.email=smoke@example.invalid", "commit", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=target, check=True, capture_output=True, text=True, encoding="utf-8")
    return target


def git_status(target: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(target), "status", "--short", "--branch"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def exercise_installed_server(template: Path, launcher: Path, target: Path) -> None:
    client = StdioClient(template_command(template, launcher), target)
    try:
        initialized = client.request("initialize", {})
        assert "listChanged" not in initialized["capabilities"]["tools"]
        initial_catalog = client.request("tools/list", {})["tools"]
        assert len(initial_catalog) == 12
        assert all("inputSchema" in tool and "outputSchema" in tool for tool in initial_catalog)

        started = accepted(client.tool("start_analysis", {"target_path": ".", "mode": "summary"}))
        rejected = client.tool("submit_execution", {**envelope(started), "payload": {}})
        assert rejected.get("isError") is True
        assert result_value(rejected).get("code") == "stage_order"

        discovery = accepted(client.tool(
            "submit_discovery",
            {**envelope(started), "payload": discovery_payload(read_observation(client, "Dockerfile"))},
        ))
        execution = accepted(client.tool(
            "submit_execution",
            {**envelope(discovery), "payload": execution_payload(
                read_observation(client, "app.py"), discovery["stage_input"]["discovery_fact_refs"],
            )},
        ))
        relationships = accepted(client.tool(
            "submit_relationships",
            {**envelope(execution), "payload": relationships_payload(
                read_observation(client, "app.py"),
                execution["stage_input"]["discovery_fact_refs"],
                execution["stage_input"]["execution_fact_refs"],
            )},
        ))
        boundaries = accepted(client.tool(
            "submit_boundaries",
            {**envelope(relationships), "payload": boundaries_payload(read_observation(client, "app.py"), relationships)},
        ))
        contracts = accepted(client.tool(
            "submit_contracts",
            {**envelope(boundaries), "payload": contracts_payload(boundaries)},
        ))
        final = client.tool("finalize_analysis", envelope(contracts))
        assert not final.get("isError"), final
        assert final["content"][0]["text"].startswith("# Kubernetes 설계 입력 요약")
        assert result_value(final)["status"] == "finalized"
        restarted = accepted(client.tool("start_analysis", {"target_path": ".", "mode": "summary"}))
        assert restarted["completed_stage"] is None

        repeated_catalog = client.request("tools/list", {})["tools"]
        assert json.dumps(initial_catalog, ensure_ascii=False, separators=(",", ":")) == json.dumps(
            repeated_catalog, ensure_ascii=False, separators=(",", ":"),
        )
    finally:
        client.close()


def run_smoke(config_root: Path, templates: tuple[str, ...]) -> None:
    config_root = config_root.resolve()
    config_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".portable-mcp-bundle-", dir=config_root.parent) as temporary:
        bundle = build(ROOT, Path(temporary) / "bundle")
        install_bundle(bundle, config_root)
        launcher = config_root / PROJECT_ID / "runtime" / "python" / "launch_mcp.py"
        assert launcher.is_file()
        fragment = json.loads((config_root / PROJECT_ID / "opencode-mcp.json").read_text(encoding="utf-8"))
        assert fragment == {"mcp": {"analysis": {"type": "local", "command": [sys.executable, str(launcher.resolve())], "enabled": True}}}

        with tempfile.TemporaryDirectory(prefix="portable-mcp-target-") as target_directory:
            target = make_external_fixture(Path(target_directory))
            before = git_status(target)
            for name in templates:
                exercise_installed_server(bundle / "configs" / name, launcher, target)
            assert git_status(target) == before


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the installed Python static MCP bundle.")
    parser.add_argument("--config-root", type=Path)
    parser.add_argument("--all-clients", action="store_true")
    parser.add_argument("--static-catalog", action="store_true")
    args = parser.parse_args()
    templates = CLIENT_CONFIGS if args.all_clients else ("opencode-mcp.json",)
    if args.config_root is None:
        with tempfile.TemporaryDirectory(prefix="portable-mcp-config-") as directory:
            run_smoke(Path(directory) / "config", templates)
    else:
        run_smoke(args.config_root, templates)
    print("MCP smoke: PASS [" + ", ".join(templates) + "]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
