from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.openclaw import _market_observer_live_inputs as live_inputs
from scripts.verify import run_openclaw_deployment_readiness as deployment_script


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _recorded_result(lane_id: str, retain_root: Path, *, status: str, exit_code: int) -> dict[str, object]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "stdout.log"
    stderr_path = retain_root / "stderr.log"
    result_path = retain_root / "result.json"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    payload = {
        "lane_id": lane_id,
        "label": lane_id,
        "status": status,
        "exit_code": exit_code,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, payload)
    return payload


def _live_result(
    retain_root: Path,
    *,
    status: str,
    exit_code: int,
    failing_stage: str | None,
    live_summary: dict[str, object] | None,
) -> dict[str, object]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "bundle_stdout.log"
    stderr_path = retain_root / "bundle_stderr.log"
    result_path = retain_root / "bundle_result.json"
    summary_path = retain_root / "live_smoke_summary.json"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    if live_summary is not None:
        _write_json(summary_path, live_summary)
    payload = {
        "status": status,
        "exit_code": exit_code,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "live_summary": live_summary,
        "failing_stage": failing_stage,
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, payload)
    return payload


def _archetype_result(
    retain_root: Path,
    *,
    gate_id: str,
    status: str,
    exit_code: int,
    failing_stage: str | None,
    bundle_summary: dict[str, object] | None,
) -> dict[str, object]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "bundle_stdout.log"
    stderr_path = retain_root / "bundle_stderr.log"
    result_path = retain_root / "bundle_result.json"
    summary_path = retain_root / "bundle_summary.json"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    if bundle_summary is not None:
        _write_json(summary_path, bundle_summary)
    payload = {
        "gate_id": gate_id,
        "label": gate_id,
        "status": status,
        "exit_code": exit_code,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "bundle_summary": bundle_summary,
        "failing_stage": failing_stage,
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, payload)
    return payload


class OpenClawDeploymentReadinessBundleTests(unittest.TestCase):
    def test_extract_live_failure_stage_prefers_failed_over_pending(self) -> None:
        live_summary = {
            "overall_status": "failed",
            "stages": {
                "host_live_adapter_smoke": {
                    "label": "host live adapter smoke",
                    "status": "pending",
                    "exit_code": None,
                    "message": None,
                },
                "live_preflight": {
                    "label": "live env preflight",
                    "status": "failed",
                    "exit_code": 1,
                    "message": "missing env",
                },
                "workspace_live_smoke": {
                    "label": "workspace live smoke",
                    "status": "pending",
                    "exit_code": None,
                    "message": None,
                },
            },
        }
        self.assertEqual(
            deployment_script._extract_live_failure_stage(live_summary),
            "live env preflight",
        )

    def test_extract_live_failure_stage_returns_host_failure_when_host_stage_failed(self) -> None:
        live_summary = {
            "overall_status": "failed",
            "stages": {
                "live_preflight": {
                    "label": "live env preflight",
                    "status": "passed",
                    "exit_code": 0,
                },
                "host_live_adapter_smoke": {
                    "label": "host live adapter smoke",
                    "status": "failed",
                    "exit_code": 1,
                },
            },
        }
        self.assertEqual(
            deployment_script._extract_live_failure_stage(live_summary),
            "host live adapter smoke",
        )

    def test_extract_live_failure_stage_returns_none_when_no_failed_stage_exists(self) -> None:
        live_summary = {
            "overall_status": "failed",
            "stages": {
                "live_preflight": {"label": "live env preflight", "status": "passed"},
                "host_live_adapter_smoke": {"label": "host live adapter smoke", "status": "pending"},
            },
        }
        self.assertIsNone(deployment_script._extract_live_failure_stage(live_summary))

    def test_extract_live_failure_stage_returns_none_for_malformed_summary(self) -> None:
        self.assertIsNone(deployment_script._extract_live_failure_stage(None))
        self.assertIsNone(deployment_script._extract_live_failure_stage({}))
        self.assertIsNone(deployment_script._extract_live_failure_stage({"stages": []}))

    def test_missing_execution_permit_fails_directly_and_writes_bundle_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_deploy_bundle_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            with patch.object(deployment_script, "_run_recorded_gate") as run_recorded, patch.object(
                deployment_script, "_run_live_gate"
            ) as run_live, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = deployment_script.main(["--retain-root", str(retain_root)])

            self.assertEqual(exit_code, 2)
            run_recorded.assert_not_called()
            run_live.assert_not_called()
            summary = json.loads((retain_root / "bundle_summary.json").read_text(encoding="utf-8"))
            snapshot = json.loads((retain_root / "failure_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["failing_gate"], "bundle_preflight")
            self.assertEqual(summary["failing_stage"], "execution_permit_required")
            self.assertEqual(summary["evidence_family"], "openclaw_deployment_gate")
            self.assertEqual(summary["contract_version"], "openclaw_deployment_gate.v1")
            self.assertTrue(summary["produced_at_utc"])
            self.assertEqual(snapshot["error"], "OpenClaw deployment readiness requires --execution-permit <WindowsPath>.")

    def test_recorded_gate_failure_sets_failing_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_deploy_bundle_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            permit_path = Path(tmpdir) / "permit.json"
            permit_path.write_text("{}", encoding="utf-8")
            gate_specs = [
                {"lane_id": "market_observer", "label": "market", "command": ["python", "market"]},
                {"lane_id": "evidence_agent", "label": "evidence", "command": ["python", "evidence"]},
            ]

            def recorded_side_effect(*, gate: dict[str, object], retain_root: Path, env: dict[str, str]) -> dict[str, object]:
                if gate["lane_id"] == "market_observer":
                    return _recorded_result("market_observer", retain_root, status="passed", exit_code=0)
                return _recorded_result("evidence_agent", retain_root, status="failed", exit_code=9)

            with patch.object(deployment_script, "_recorded_gate_specs", return_value=gate_specs), patch.object(
                deployment_script,
                "_archetype_live_gate_specs",
                return_value=[],
            ), patch.object(
                deployment_script,
                "_run_recorded_gate",
                side_effect=recorded_side_effect,
            ), patch.object(deployment_script, "_run_live_gate") as run_live, contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(io.StringIO()):
                result = deployment_script.run_openclaw_deployment_readiness(
                    execution_permit=permit_path,
                    retain_root=retain_root,
                )

            run_live.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failing_gate"], "evidence_agent")
            self.assertEqual(result["failing_stage"], "recorded_smoke")
            summary = json.loads((retain_root / "bundle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["failing_gate"], "evidence_agent")
            self.assertEqual(summary["recorded_results"]["market_observer"]["status"], "passed")
            self.assertEqual(summary["recorded_results"]["evidence_agent"]["status"], "failed")

    def test_live_gate_failure_uses_live_summary_as_failure_stage_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_deploy_bundle_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            permit_path = Path(tmpdir) / "permit.json"
            permit_path.write_text("{}", encoding="utf-8")
            live_summary = {
                "overall_status": "failed",
                "stages": {
                    "host_live_adapter_smoke": {
                        "label": "host live adapter smoke",
                        "status": "pending",
                        "exit_code": None,
                        "message": None,
                    },
                    "live_preflight": {
                        "label": "live env preflight",
                        "status": "failed",
                        "exit_code": 1,
                        "message": "missing env",
                    },
                    "recorded_gate": {
                        "label": "recorded gate",
                        "status": "pending",
                        "exit_code": None,
                        "message": None,
                    },
                    "workspace_live_smoke": {
                        "label": "workspace live smoke",
                        "status": "pending",
                        "exit_code": None,
                        "message": None,
                    },
                    "workspace_live_audit": {
                        "label": "workspace live audit",
                        "status": "pending",
                        "exit_code": None,
                        "message": None,
                    },
                },
            }

            with patch.object(
                deployment_script,
                "_recorded_gate_specs",
                return_value=[{"lane_id": "market_observer", "label": "market", "command": ["python", "market"]}],
            ), patch.object(
                deployment_script,
                "_archetype_live_gate_specs",
                return_value=[],
            ), patch.object(
                deployment_script,
                "_run_recorded_gate",
                side_effect=lambda *, gate, retain_root, env: _recorded_result(
                    gate["lane_id"], retain_root, status="passed", exit_code=0
                ),
            ), patch.object(
                deployment_script,
                "_run_live_gate",
                side_effect=lambda *, execution_permit, trust_root_dir, retain_root, env: _live_result(
                    retain_root,
                    status="failed",
                    exit_code=1,
                    failing_stage="host live adapter smoke",
                    live_summary=live_summary,
                ),
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = deployment_script.run_openclaw_deployment_readiness(
                    execution_permit=permit_path,
                    retain_root=retain_root,
                )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failing_gate"], "market_observer_live")
            self.assertEqual(result["failing_stage"], "live env preflight")
            summary = json.loads((retain_root / "bundle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["failing_gate"], "market_observer_live")
            self.assertEqual(summary["failing_stage"], "live env preflight")
            self.assertEqual(summary["live_result"]["overall_status"], "failed")
            self.assertEqual(
                summary["market_observer_live_summary_path"],
                str(retain_root / "market_observer_live" / "live_smoke_summary.json"),
            )

    def test_archetype_gate_failure_sets_failing_gate_and_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_deploy_bundle_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            permit_path = Path(tmpdir) / "permit.json"
            permit_path.write_text("{}", encoding="utf-8")
            continue_existing_summary = {
                "status": "failed",
                "failing_lane": "risk_signal_agent",
                "failing_stage": "workspace live smoke",
            }
            archetype_specs = [
                {
                    "gate_id": "continue_existing_live",
                    "label": "continue-existing live readiness",
                    "command": ["python", "continue-existing"],
                }
            ]

            with patch.object(
                deployment_script,
                "_recorded_gate_specs",
                return_value=[{"lane_id": "market_observer", "label": "market", "command": ["python", "market"]}],
            ), patch.object(
                deployment_script,
                "_run_recorded_gate",
                side_effect=lambda *, gate, retain_root, env: _recorded_result(
                    gate["lane_id"], retain_root, status="passed", exit_code=0
                ),
            ), patch.object(
                deployment_script,
                "_run_live_gate",
                side_effect=lambda *, execution_permit, trust_root_dir, retain_root, env: _live_result(
                    retain_root,
                    status="passed",
                    exit_code=0,
                    failing_stage=None,
                    live_summary={"overall_status": "success", "stages": {}},
                ),
            ), patch.object(
                deployment_script,
                "_archetype_live_gate_specs",
                return_value=archetype_specs,
            ), patch.object(
                deployment_script,
                "_run_archetype_live_gate",
                side_effect=lambda *, gate, execution_permit, trust_root_dir, retain_root, env: _archetype_result(
                    retain_root,
                    gate_id=str(gate["gate_id"]),
                    status="failed",
                    exit_code=7,
                    failing_stage="workspace live smoke",
                    bundle_summary=continue_existing_summary,
                ),
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = deployment_script.run_openclaw_deployment_readiness(
                    execution_permit=permit_path,
                    retain_root=retain_root,
                )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failing_gate"], "continue_existing_live")
            self.assertEqual(result["failing_stage"], "workspace live smoke")
            summary = json.loads((retain_root / "bundle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["continue_existing_live_result"]["failing_lane"], "risk_signal_agent")
            self.assertEqual(summary["failing_gate"], "continue_existing_live")
            self.assertEqual(summary["failing_stage"], "workspace live smoke")

    def test_success_aggregates_live_summary_and_archetype_results(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_deploy_bundle_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            permit_path = Path(tmpdir) / "permit.json"
            permit_path.write_text("{}", encoding="utf-8")
            live_summary = {
                "overall_status": "success",
                "summary_path": str(retain_root / "market_observer_live" / "live_smoke_summary.json"),
                "final_output_path": "C:/tmp/final-output.json",
                "runtime_session_path": "C:/tmp/runtime-session.json",
                "audit_result": "success",
                "stages": {
                    "host_live_adapter_smoke": {"label": "host live adapter smoke", "status": "passed", "exit_code": 0},
                    "workspace_live_smoke": {"label": "workspace live smoke", "status": "passed", "exit_code": 0},
                    "workspace_live_audit": {"label": "workspace live audit", "status": "passed", "exit_code": 0},
                },
            }
            gate_specs = [
                {"lane_id": "market_observer", "label": "market", "command": ["python", "market"]},
                {"lane_id": "evidence_agent", "label": "evidence", "command": ["python", "evidence"]},
            ]
            archetype_specs = [
                {
                    "gate_id": "continue_existing_live",
                    "label": "continue-existing live readiness",
                    "command": ["python", "continue-existing"],
                },
                {
                    "gate_id": "review_gated_live",
                    "label": "review-gated live readiness",
                    "command": ["python", "review-gated"],
                },
            ]
            continue_existing_summary = {
                "status": "success",
                "failing_lane": None,
                "failing_stage": None,
                "lane_results": {"evidence_agent": {"status": "passed"}},
            }
            review_gated_summary = {
                "status": "success",
                "failing_lane": None,
                "failing_stage": None,
                "lane_results": {"risk_governance_agent": {"status": "passed"}},
            }

            def _assert_bundle_env(env: dict[str, str]) -> None:
                for _lane_id, (_base_url_name, _model_name_name, api_key_name) in live_inputs.openclaw_bundle_live_env_specs().items():
                    self.assertEqual(env[api_key_name], "openclaw-secret")

            def _assert_recorded_env(env: dict[str, str]) -> None:
                self.assertNotIn("OPENCLAW", env)
                for _lane_id, (base_url_name, model_name_name, api_key_name) in live_inputs.openclaw_bundle_live_env_specs().items():
                    timeout_name = base_url_name.replace("_BASE_URL", "_TIMEOUT_SECONDS")
                    for name in (base_url_name, model_name_name, api_key_name, timeout_name):
                        self.assertNotIn(name, env)

            with patch.object(deployment_script, "_recorded_gate_specs", return_value=gate_specs), patch.object(
                deployment_script,
                "_run_recorded_gate",
                side_effect=lambda *, gate, retain_root, env: (
                    _assert_recorded_env(env),
                    _recorded_result(str(gate["lane_id"]), retain_root, status="passed", exit_code=0),
                )[1],
            ), patch.object(
                deployment_script,
                "_run_live_gate",
                side_effect=lambda *, execution_permit, trust_root_dir, retain_root, env: (
                    _assert_bundle_env(env),
                    _live_result(
                        retain_root,
                        status="passed",
                        exit_code=0,
                        failing_stage=None,
                        live_summary=live_summary,
                    ),
                )[1],
            ), patch.object(
                deployment_script,
                "_archetype_live_gate_specs",
                return_value=archetype_specs,
            ), patch.object(
                deployment_script,
                "_run_archetype_live_gate",
                side_effect=lambda *, gate, execution_permit, trust_root_dir, retain_root, env: (
                    _assert_bundle_env(env),
                    _archetype_result(
                        retain_root,
                        gate_id=str(gate["gate_id"]),
                        status="passed",
                        exit_code=0,
                        failing_stage=None,
                        bundle_summary=continue_existing_summary
                        if str(gate["gate_id"]) == "continue_existing_live"
                        else review_gated_summary,
                    ),
                )[1],
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = deployment_script.run_openclaw_deployment_readiness(
                    execution_permit=permit_path,
                    retain_root=retain_root,
                    base_env={"OPENCLAW": "openclaw-secret"},
                )

            self.assertEqual(result["status"], "success")
            summary = json.loads((retain_root / "bundle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["live_env_baseline"]["live_env_mode"], "unified_openclaw_baseline")
            self.assertTrue(summary["live_env_baseline"]["openclaw_mapping_used_by_lane"]["market_observer"])
            self.assertTrue(summary["live_env_baseline"]["openclaw_mapping_used_by_lane"]["validation_agent"])
            self.assertTrue(summary["live_env_baseline"]["defaulted_timeout_by_lane"]["market_observer"])
            self.assertEqual(summary["live_env_baseline"]["shared_openclaw_model_timeout_seconds"], "30")
            self.assertEqual(summary["live_result"]["overall_status"], "success")
            self.assertEqual(summary["live_result"]["audit_result"], "success")
            self.assertEqual(summary["continue_existing_live_result"]["status"], "success")
            self.assertEqual(summary["review_gated_live_result"]["status"], "success")
            self.assertEqual(summary["evidence_family"], "openclaw_deployment_gate")
            self.assertEqual(summary["contract_version"], "openclaw_deployment_gate.v1")
            self.assertTrue(summary["produced_at_utc"])
            self.assertTrue((retain_root / "bundle_summary.json").exists())
            self.assertEqual(
                summary["evidence_roots"]["recorded"]["market_observer"],
                str(retain_root / "recorded" / "market_observer"),
            )
            self.assertEqual(
                summary["evidence_roots"]["market_observer_live"],
                str(retain_root / "market_observer_live"),
            )
            self.assertEqual(
                summary["evidence_roots"]["continue_existing_live"],
                str(retain_root / "continue_existing_live"),
            )
            self.assertEqual(
                summary["evidence_roots"]["review_gated_live"],
                str(retain_root / "review_gated_live"),
            )


if __name__ == "__main__":
    unittest.main()
