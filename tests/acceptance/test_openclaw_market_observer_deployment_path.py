from __future__ import annotations

import json
import os
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT, SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.integrations.openclaw.market_observer import OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION
from enhengclaw.testing import execution_testbed


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "market_observer"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))


def _transcript(name: str) -> Path:
    return FIXTURE_ROOT / name / "model_transcript.json"


def assert_market_observer_artifact_chain(testcase: unittest.TestCase, payload: dict[str, object]) -> None:
    final_output_path = payload.get("final_output_path")
    testcase.assertTrue(final_output_path)
    testcase.assertTrue(Path(str(final_output_path)).exists())
    compiler_artifact_paths = payload.get("compiler_artifact_paths") or []
    testcase.assertTrue(compiler_artifact_paths)
    for artifact_path in compiler_artifact_paths:
        testcase.assertTrue(Path(str(artifact_path)).exists(), msg=f"missing artifact: {artifact_path}")
    runtime_session_path = payload.get("runtime_session_path")
    if runtime_session_path not in {None, ""}:
        testcase.assertTrue(Path(str(runtime_session_path)).exists())


class OpenClawMarketObserverDeploymentAcceptanceTests(unittest.TestCase):
    def test_recorded_success_finalizes_governed_runtime_from_openclaw_request(self) -> None:
        payload = self._run_case("success")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["execution_status"], "success")
        self.assertEqual(payload["run_state"], "FINALIZED")
        self.assertTrue(payload["accepted_signal_ids"])
        assert_market_observer_artifact_chain(self, payload)

    def test_recorded_blocked_returns_blocked_without_runtime_mutation(self) -> None:
        payload = self._run_case("blocked")
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["execution_status"], "blocked")
        self.assertEqual(payload["run_state"], "BLOCKED")
        self.assertIsNone(payload["runtime_session_path"])
        assert_market_observer_artifact_chain(self, payload)

    def test_recorded_quarantine_returns_quarantine_without_runtime_mutation(self) -> None:
        payload = self._run_case("quarantine")
        self.assertEqual(payload["status"], "quarantine")
        self.assertEqual(payload["execution_status"], "quarantine")
        self.assertEqual(payload["run_state"], "BLOCKED")
        self.assertIsNone(payload["runtime_session_path"])
        self.assertTrue(any(path.endswith("quarantine.json") for path in payload["compiler_artifact_paths"]))
        assert_market_observer_artifact_chain(self, payload)

    def _run_case(self, name: str) -> dict[str, object]:
        fixture = _load_fixture(name)
        with execution_testbed() as bed:
            tmpdir = tempfile.mkdtemp(prefix="ecoc_accept_")
            self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
            permit_path, _ = bed.issue_permit(
                slug=f"openclaw-market-observer-{name}",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            request_path = Path(tmpdir) / "request.json"
            response_path = Path(tmpdir) / "response.json"
            artifacts_root = Path(tmpdir) / "artifacts"
            request_path.write_text(
                json.dumps(
                    {
                        "contract_version": OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
                        "subject": fixture["subject"],
                        "scope": fixture["scope"],
                        "object_id": fixture["object_id"],
                        "observation_text": fixture["observation_text"],
                        "execution_permit_path": str(permit_path),
                        "input_id": f"{fixture['case_id']}:1",
                        "compiler_backend": "recorded",
                        "recorded_transcript_path": str(_transcript(name)),
                        "artifacts_root": str(artifacts_root),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "enhengclaw.integrations.openclaw.market_observer",
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"adapter failed for case {name}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            assert_market_observer_artifact_chain(self, payload)
            return payload


if __name__ == "__main__":
    unittest.main()
