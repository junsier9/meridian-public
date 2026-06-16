from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT, SRC

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.integrations.openclaw.market_observer import (
    OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
    OpenClawMarketObserverRequest,
    OpenClawMarketObserverResponse,
    main as adapter_main,
)
from enhengclaw.agents.owner_state import OwnerArtifactStore, build_owner_run_id
from enhengclaw.testing import execution_testbed
from scripts.verify import run_openclaw_market_observer_smoke as smoke_script


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "market_observer"


def _fixture_input(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))


def _long_path_io_path(path: str | Path) -> str:
    text = str(path)
    if os.name != "nt" or len(text) < 240:
        return text
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


class OpenClawMarketObserverAdapterTests(unittest.TestCase):
    def test_request_contract_requires_non_empty_execution_permit_path(self) -> None:
        fixture = _fixture_input("success")
        with self.assertRaisesRegex(Exception, "execution_permit_path"):
            OpenClawMarketObserverRequest.from_payload(
                {
                    "contract_version": OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
                    "subject": fixture["subject"],
                    "scope": fixture["scope"],
                    "object_id": fixture["object_id"],
                    "observation_text": fixture["observation_text"],
                    "execution_permit_path": "",
                }
            )

    def test_recorded_backend_requires_recorded_transcript_path(self) -> None:
        fixture = _fixture_input("success")
        with self.assertRaisesRegex(ValueError, "recorded_transcript_path"):
            OpenClawMarketObserverRequest.from_payload(
                {
                    "contract_version": OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
                    "subject": fixture["subject"],
                    "scope": fixture["scope"],
                    "object_id": fixture["object_id"],
                    "observation_text": fixture["observation_text"],
                    "execution_permit_path": "C:/tmp/permit.json",
                    "input_id": f"{fixture['case_id']}:1",
                    "compiler_backend": "recorded",
                }
            )

    def test_recorded_backend_requires_input_id(self) -> None:
        fixture = _fixture_input("success")
        with self.assertRaisesRegex(ValueError, "input_id"):
            OpenClawMarketObserverRequest.from_payload(
                {
                    "contract_version": OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
                    "subject": fixture["subject"],
                    "scope": fixture["scope"],
                    "object_id": fixture["object_id"],
                    "observation_text": fixture["observation_text"],
                    "execution_permit_path": "C:/tmp/permit.json",
                    "compiler_backend": "recorded",
                    "recorded_transcript_path": str(FIXTURE_ROOT / "success" / "model_transcript.json"),
                }
            )

    def test_live_backend_missing_env_fails_closed(self) -> None:
        fixture = _fixture_input("success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug="openclaw-market-observer-live-missing-env",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            request_path = Path(tmpdir) / "request.json"
            response_path = Path(tmpdir) / "response.json"
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
                        "compiler_backend": "live",
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL": "",
                    "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME": "",
                    "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "",
                },
                clear=False,
            ):
                exit_code = adapter_main(["--request", str(request_path), "--response", str(response_path)])
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["run_state"], "FAILED")
            self.assertIn("ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL", payload["error"])

    def test_recorded_success_response_shape_is_fixed(self) -> None:
        fixture = _fixture_input("success")
        transcript_path = FIXTURE_ROOT / "success" / "model_transcript.json"
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug="openclaw-market-observer-shape",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            request_path = Path(tmpdir) / "request.json"
            response_path = Path(tmpdir) / "response.json"
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
                        "recorded_transcript_path": str(transcript_path),
                        "artifacts_root": str(Path(tmpdir) / "artifacts"),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            exit_code = adapter_main(["--request", str(request_path), "--response", str(response_path)])
            payload = json.loads(response_path.read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                set(payload),
                {
                    "accepted_signal_ids",
                    "artifacts_root",
                    "blocked_reason",
                    "compiler_artifact_paths",
                    "contract_version",
                    "error",
                    "execution_status",
                    "final_output_path",
                    "owner_run_id",
                    "quarantine_reason",
                    "run_state",
                    "runtime_session_path",
                    "spec_version",
                    "status",
                },
            )
            self.assertEqual(payload["contract_version"], OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION)
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertIsInstance(payload["compiler_artifact_paths"], list)
            self.assertTrue(payload["compiler_artifact_paths"])
            self.assertTrue(Path(payload["final_output_path"]).exists())
            self.assertTrue(Path(payload["runtime_session_path"]).exists())

    def test_recorded_success_survives_long_artifacts_roots(self) -> None:
        fixture = _fixture_input("success")
        transcript_path = FIXTURE_ROOT / "success" / "model_transcript.json"
        with execution_testbed() as bed:
            tmpdir = Path(tempfile.mkdtemp())
            try:
                permit_path, _ = bed.issue_permit(
                    slug="openclaw-market-observer-long-root",
                    scope=str(fixture["scope"]),
                    capabilities=["runtime.execute"],
                    allowed_operations=["runtime.*"],
                )
                artifacts_root = tmpdir / ("retained_" + ("x" * 95))
                request_path = tmpdir / "request.json"
                response_path = tmpdir / "response.json"
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
                            "recorded_transcript_path": str(transcript_path),
                            "artifacts_root": str(artifacts_root),
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )

                exit_code = adapter_main(["--request", str(request_path), "--response", str(response_path)])
                payload = json.loads(response_path.read_text(encoding="utf-8"))

                self.assertEqual(exit_code, 0)
                self.assertEqual(payload["status"], "success")
                owner_store = OwnerArtifactStore(artifacts_root / "agent_owner")
                run_id = build_owner_run_id(requested_delegate_id="market_observer", object_id=str(fixture["object_id"]))
                delegate_records = owner_store.list_delegate_artifacts(run_id, "market_observer", spec_version=int(payload["spec_version"]))
                self.assertEqual(len(delegate_records), 1)
                delegate_record = delegate_records[0]
                replay_log_paths = list(delegate_record["replay_log_paths"])
                self.assertTrue(replay_log_paths)
                self.assertTrue(any(len(path) > 260 for path in replay_log_paths))
                for path in replay_log_paths:
                    self.assertTrue(Path(_long_path_io_path(path)).exists(), path)
            finally:
                shutil.rmtree(_long_path_io_path(tmpdir), ignore_errors=True)

    def test_response_dataclass_serializes_all_contract_fields(self) -> None:
        payload = OpenClawMarketObserverResponse(
            contract_version=OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
            status="blocked",
            execution_status="blocked",
            run_state="BLOCKED",
            owner_run_id="owner-run-1",
            spec_version=1,
            final_output_path=None,
            runtime_session_path=None,
            compiler_artifact_paths=("a.json", "b.json"),
            accepted_signal_ids=(),
            blocked_reason="blocked",
            quarantine_reason=None,
            error=None,
            artifacts_root="C:/tmp/root",
        ).to_payload()
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["compiler_artifact_paths"], ["a.json", "b.json"])
        self.assertEqual(payload["artifacts_root"], "C:/tmp/root")


class OpenClawMarketObserverSmokeScriptTests(unittest.TestCase):
    def test_live_smoke_requires_execution_permit(self) -> None:
        with patch.object(smoke_script, "_run_recorded_gate", return_value=0) as recorded_gate, patch.object(
            smoke_script, "_run_live_proof"
        ) as live_proof:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = smoke_script.main(["--live-smoke"])
        self.assertEqual(exit_code, 2)
        recorded_gate.assert_not_called()
        live_proof.assert_not_called()

    def test_live_smoke_missing_env_fails_closed_and_retains_evidence(self) -> None:
        fixture = _fixture_input("success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug="openclaw-market-observer-live-smoke-missing-env",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            retain_root = Path(tmpdir) / "retain"
            with patch.dict(
                os.environ,
                {
                    "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL": "",
                    "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME": "",
                    "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "",
                },
                clear=False,
            ):
                with patch.object(smoke_script, "_run_recorded_gate", return_value=0) as recorded_gate:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        exit_code = smoke_script.main(
                            [
                                "--live-smoke",
                                "--execution-permit",
                                str(permit_path),
                                "--retain-root",
                                str(retain_root),
                            ]
                        )

            self.assertEqual(exit_code, 1)
            recorded_gate.assert_not_called()
            self.assertTrue((retain_root / "host_live" / "request.json").exists())
            self.assertTrue((retain_root / "host_live" / "response.json").exists())
            self.assertTrue((retain_root / "host_live" / "artifacts").exists())
            self.assertTrue((retain_root / "wsl_live" / "response.json").exists())
            snapshot = json.loads((retain_root / "failure_snapshot.json").read_text(encoding="utf-8"))
            summary = json.loads((retain_root / "live_smoke_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["stage_label"], "live env preflight")
            self.assertFalse(snapshot["required_live_env"]["ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL"])
            self.assertEqual(summary["overall_status"], "failed")
            self.assertEqual(summary["stages"]["live_preflight"]["status"], "failed")
            response = json.loads((retain_root / "host_live" / "response.json").read_text(encoding="utf-8"))
            self.assertEqual(response["status"], "failed")
            self.assertIn("ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL", response["error"])

    def test_live_smoke_non_convertible_permit_path_fails_closed(self) -> None:
        fixture = _fixture_input("success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug="openclaw-market-observer-live-smoke-bad-path",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            retain_root = Path(tmpdir) / "retain"
            with patch.dict(
                os.environ,
                {
                    "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL": "https://api.openai.com/v1",
                    "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME": "gpt-5.4",
                    "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "fake-key",
                },
                clear=False,
            ), patch.object(smoke_script, "windows_path_to_wsl", side_effect=ValueError("not convertible")), patch.object(
                smoke_script, "_run_recorded_gate", return_value=0
            ) as recorded_gate:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exit_code = smoke_script.main(
                        [
                            "--live-smoke",
                            "--execution-permit",
                            str(permit_path),
                            "--retain-root",
                            str(retain_root),
                        ]
                    )

            self.assertEqual(exit_code, 1)
            recorded_gate.assert_not_called()
            snapshot = json.loads((retain_root / "failure_snapshot.json").read_text(encoding="utf-8"))
            summary = json.loads((retain_root / "live_smoke_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["stage_label"], "live env preflight")
            self.assertEqual(summary["overall_status"], "failed")
            self.assertEqual(summary["stages"]["live_preflight"]["status"], "failed")
            self.assertIn("not convertible", snapshot["error"])


if __name__ == "__main__":
    unittest.main()
