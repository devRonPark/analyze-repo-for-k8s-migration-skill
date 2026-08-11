"""D14 tests for the one-shot OpenCode host-activation guard."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from analysis_pipeline.host_activation_state import write_host_activation_state


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "host_owned_skill_guard.js"


class HostActivationOwnershipTests(unittest.TestCase):
    def run_guard(self, state: Path) -> dict[str, object]:
        bun = shutil.which("bun")
        if bun is None:
            self.skipTest("bun is required to exercise the OpenCode plugin seam")
        script = """
import fs from 'node:fs'
const { HostOwnedSkillGuard } = await import(process.argv[1])
const statePath = process.argv[2]
const hooks = await HostOwnedSkillGuard()
const definition = { jsonSchema: { type: 'object', properties: { name: { type: 'string', description: 'Skill name' } } } }
await hooks['tool.definition']({ toolID: 'skill' }, definition)
const unrelated = { args: { name: 'optional-capability' } }
await hooks['tool.execute.before']({ tool: 'skill' }, unrelated)
const duplicate = { args: { name: 'analyze-k8s-execution' } }
await hooks['tool.execute.before']({ tool: 'skill' }, duplicate)
const afterDuplicate = JSON.parse(fs.readFileSync(statePath, 'utf8'))
await hooks['tool.execute.before']({ tool: 'analysis_read_evidence' }, { args: { path: 'Dockerfile' } })
const afterAction = JSON.parse(fs.readFileSync(statePath, 'utf8'))
const stale = { args: { name: 'analyze-k8s-execution' } }
await hooks['tool.execute.before']({ tool: 'skill' }, stale)
console.log(JSON.stringify({ definition, unrelated, duplicate, afterDuplicate, afterAction, stale }))
"""
        environment = os.environ | {"ANALYSIS_HOST_ACTIVATION_STATE": str(state)}
        result = subprocess.run(
            [bun, "--eval", script, str(GUARD), str(state)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        if result.returncode:
            self.fail(result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_host_guard_suppresses_only_the_current_successor_then_expires(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "host-activation.json"
            write_host_activation_state(
                state,
                analysis_id="an_d14",
                revision=2,
                transition_token="tr_d14",
                next_skill="analyze-k8s-execution",
            )
            observed = self.run_guard(state)

        name_schema = observed["definition"]["jsonSchema"]["properties"]["name"]
        self.assertEqual(name_schema["not"], {"const": "analyze-k8s-execution"})
        self.assertEqual(observed["unrelated"]["args"]["name"], "optional-capability")
        self.assertEqual(observed["duplicate"]["args"]["name"], "__host_owned_duplicate_skill_blocked__")
        self.assertEqual(observed["afterDuplicate"]["state"], "pending")
        self.assertEqual(observed["afterDuplicate"]["duplicate_blocked_attempts"], 1)
        self.assertEqual(observed["afterAction"]["state"], "consumed")
        self.assertEqual(observed["stale"]["args"]["name"], "analyze-k8s-execution")


if __name__ == "__main__":
    unittest.main()
