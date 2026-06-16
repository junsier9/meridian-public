from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.orchestration.shadow_acceptance import (
    DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS,
    REAL_24H_DURATION_SECONDS,
    REAL_24H_MIN_PERMIT_MARGIN_SECONDS,
    PreflightConfig,
    _required_permit_margin_seconds,
    build_controlled_agent_slices_summary,
    evaluate_real_24h_rerun_verdict,
    run_real_24h_preflight_only,
)
from enhengclaw.orchestration.shadow_ingestion_providers import build_legacy_provider_payloads
from scripts.verify import run_real_24h_shadow_bundle as bundle_script


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _green_preflight_payload() -> dict[str, object]:
    return {
        "status": "passed",
        "failures": [],
        "checks": {
            "permit": {"minimum_required_seconds": REAL_24H_MIN_PERMIT_MARGIN_SECONDS},
            "provider_binance": {"status": "passed"},
            "provider_alchemy": {"status": "passed"},
        },
    }


def _green_verdict_evidence(artifacts_root: Path, label: str) -> None:
    evidence_root = artifacts_root / "soak_runs" / label
    expected_slice_ids = build_controlled_agent_slices_summary()["enabled_slice_ids"]
    _write_json(
        evidence_root / "go_no_go.json",
        {
            "READY_FOR_REAL_24H_SHADOW": True,
            "READY_FOR_AGENT_LAYER": True,
            "READY_FOR_BROAD_AGENT_LAYER": True,
            "hard_failures": [],
            "soft_failures": [],
            "broad_blockers": [],
            "agent_layer_governance": {
                "status": "enabled",
                "blockers": [],
                "current_controlled_slice_ids": expected_slice_ids,
                "registered_pending_promotion_controlled_slice_ids": [],
            },
        },
    )
    _write_json(evidence_root / "soak_summary.json", {"violations": []})
    _write_json(evidence_root / "provider_health_snapshot.json", {"status": "present"})
    _write_json(evidence_root / "audit_record.json", {"status": "completed"})


def _preflight_config(*, min_permit_margin_seconds: float, duration_seconds: int, simulation_profile: str) -> PreflightConfig:
    return PreflightConfig(
        execution_permit_path=Path("C:/permits/execution_permit.json"),
        artifacts_root=Path("C:/artifacts"),
        soak_root=Path("C:/artifacts/soak"),
        audit_root=Path("C:/artifacts/audit"),
        duration_seconds=duration_seconds,
        simulation_profile=simulation_profile,
        binance_websocket_url="wss://stream.binance.com:9443/ws",
        alchemy_endpoint_url="https://eth-mainnet.g.alchemy.com/v2/test",
        alchemy_include_block_details=False,
        clock_reference_url="https://api.binance.com/api/v3/time",
        min_free_disk_mb=128,
        max_total_log_bytes=1024,
        clock_skew_threshold_seconds=30.0,
        provider_probe_timeout_seconds=10.0,
        min_permit_margin_seconds=min_permit_margin_seconds,
        require_explicit_real_permit=True,
        providers=tuple(
            build_legacy_provider_payloads(
                binance_websocket_url="wss://stream.binance.com:9443/ws",
                binance_receive_timeout_seconds=20.0,
                binance_initial_backoff_seconds=1.0,
                binance_max_backoff_seconds=5.0,
                binance_max_reconnect_attempts=None,
                alchemy_poll_interval_seconds=5.0,
                alchemy_request_timeout_seconds=10.0,
                alchemy_initial_backoff_seconds=1.0,
                alchemy_max_backoff_seconds=20.0,
                alchemy_max_retry_attempts=5,
                alchemy_degraded_after_failures=3,
                disable_eth_get_block_by_number=True,
                alchemy_endpoint_url="https://eth-mainnet.g.alchemy.com/v2/test",
            )
        ),
    )


class Real24hShadowBundleTests(unittest.TestCase):
    def test_real_24h_required_margin_uses_real_24h_floor_not_non_real_default(self) -> None:
        config = _preflight_config(
            min_permit_margin_seconds=DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS,
            duration_seconds=REAL_24H_DURATION_SECONDS,
            simulation_profile="real",
        )

        self.assertEqual(_required_permit_margin_seconds(config), REAL_24H_MIN_PERMIT_MARGIN_SECONDS)

    def test_preflight_only_writes_fixed_evidence_bundle_and_all_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir()
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            trust_root_dir = root / "trust"
            allowed_signers = trust_root_dir / "allowed_signers"
            allowed_signers.parent.mkdir(parents=True, exist_ok=True)
            allowed_signers.write_text("ok\n", encoding="utf-8")

            with (
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.run_preflight",
                    return_value=_green_preflight_payload(),
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.build_provider_health_snapshot",
                    return_value={"status": "present"},
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.resolve_allowed_signers_path",
                    return_value=allowed_signers,
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.tempfile.gettempdir",
                    return_value=str(root / "system-temp"),
                ),
            ):
                result = run_real_24h_preflight_only(
                    repo_root=repo_root,
                    execution_permit_path=permit_path,
                    artifacts_root=root / "artifacts",
                    label="preflight-green",
                    trust_root_dir=trust_root_dir,
                )

            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["all_green"])
            evidence_root = Path(result["evidence_root"])
            self.assertTrue((evidence_root / "run_config.json").exists())
            self.assertTrue((evidence_root / "preflight_result.json").exists())
            self.assertTrue((evidence_root / "provider_health_snapshot.json").exists())
            self.assertTrue((evidence_root / "preflight_assertions.json").exists())
            preflight_assertions = json.loads((evidence_root / "preflight_assertions.json").read_text(encoding="utf-8"))
            self.assertEqual(preflight_assertions["evidence_family"], "real_24h_preflight")
            self.assertEqual(preflight_assertions["contract_version"], "real_24h_preflight.v1")
            self.assertTrue(preflight_assertions["produced_at_utc"])

    def test_preflight_only_fails_closed_when_preflight_not_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir()
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            trust_root_dir = root / "trust"
            allowed_signers = trust_root_dir / "allowed_signers"
            allowed_signers.parent.mkdir(parents=True, exist_ok=True)
            allowed_signers.write_text("ok\n", encoding="utf-8")

            failing_preflight = {
                "status": "failed",
                "failures": ["provider preflight failed"],
                "checks": {
                    "permit": {"minimum_required_seconds": REAL_24H_MIN_PERMIT_MARGIN_SECONDS},
                    "provider_binance": {"status": "failed"},
                    "provider_alchemy": {"status": "passed"},
                },
            }
            with (
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.run_preflight",
                    return_value=failing_preflight,
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.build_provider_health_snapshot",
                    return_value={"status": "present"},
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.resolve_allowed_signers_path",
                    return_value=allowed_signers,
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.tempfile.gettempdir",
                    return_value=str(root / "system-temp"),
                ),
            ):
                result = run_real_24h_preflight_only(
                    repo_root=repo_root,
                    execution_permit_path=permit_path,
                    artifacts_root=root / "artifacts",
                    label="preflight-red",
                    trust_root_dir=trust_root_dir,
                )

            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["all_green"])

    def test_preflight_only_fails_closed_when_trust_root_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir()
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            trust_root_dir = root / "trust"

            with (
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.run_preflight",
                    return_value=_green_preflight_payload(),
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.build_provider_health_snapshot",
                    return_value={"status": "present"},
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.resolve_allowed_signers_path",
                    side_effect=RuntimeError("trust root secure check failed"),
                ),
                mock.patch(
                    "enhengclaw.orchestration.shadow_acceptance.tempfile.gettempdir",
                    return_value=str(root / "system-temp"),
                ),
            ):
                result = run_real_24h_preflight_only(
                    repo_root=repo_root,
                    execution_permit_path=permit_path,
                    artifacts_root=root / "artifacts",
                    label="preflight-trust-red",
                    trust_root_dir=trust_root_dir,
                )

            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["all_green"])
            self.assertFalse(result["assertions"]["trust_root_ok"])
            self.assertEqual(result["details"]["trust_root_error"], "trust root secure check failed")

    def test_rerun_verdict_passes_when_current_state_is_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            _green_verdict_evidence(artifacts_root, "rerun-green")
            verdict = evaluate_real_24h_rerun_verdict(
                artifacts_root=artifacts_root,
                rerun_label="rerun-green",
                preflight_label="preflight-green",
            )
            self.assertEqual(verdict["status"], "passed")
            self.assertTrue(verdict["READY_FOR_REAL_24H_SHADOW"])
            self.assertTrue(verdict["READY_FOR_BROAD_AGENT_LAYER"])

    def test_rerun_verdict_fails_when_required_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            _green_verdict_evidence(artifacts_root, "rerun-missing")
            (artifacts_root / "soak_runs" / "rerun-missing" / "audit_record.json").unlink()
            with self.assertRaises(FileNotFoundError):
                evaluate_real_24h_rerun_verdict(
                    artifacts_root=artifacts_root,
                    rerun_label="rerun-missing",
                    preflight_label="preflight-green",
                )

    def test_rerun_verdict_fails_when_broad_ready_is_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            _green_verdict_evidence(artifacts_root, "rerun-broad-red")
            go_no_go_path = artifacts_root / "soak_runs" / "rerun-broad-red" / "go_no_go.json"
            payload = json.loads(go_no_go_path.read_text(encoding="utf-8"))
            payload["READY_FOR_BROAD_AGENT_LAYER"] = False
            _write_json(go_no_go_path, payload)
            verdict = evaluate_real_24h_rerun_verdict(
                artifacts_root=artifacts_root,
                rerun_label="rerun-broad-red",
                preflight_label="preflight-green",
            )
            self.assertEqual(verdict["status"], "failed")
            self.assertIn("READY_FOR_BROAD_AGENT_LAYER is not true", verdict["failures"])

    def test_rerun_verdict_fails_when_real_24h_ready_is_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            _green_verdict_evidence(artifacts_root, "rerun-real24h-red")
            go_no_go_path = artifacts_root / "soak_runs" / "rerun-real24h-red" / "go_no_go.json"
            payload = json.loads(go_no_go_path.read_text(encoding="utf-8"))
            payload["READY_FOR_REAL_24H_SHADOW"] = False
            _write_json(go_no_go_path, payload)
            verdict = evaluate_real_24h_rerun_verdict(
                artifacts_root=artifacts_root,
                rerun_label="rerun-real24h-red",
                preflight_label="preflight-green",
            )
            self.assertEqual(verdict["status"], "failed")
            self.assertIn("READY_FOR_REAL_24H_SHADOW is not true", verdict["failures"])

    def test_rerun_verdict_fails_when_slice_ids_do_not_match_checked_in_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            _green_verdict_evidence(artifacts_root, "rerun-slice-mismatch")
            go_no_go_path = artifacts_root / "soak_runs" / "rerun-slice-mismatch" / "go_no_go.json"
            payload = json.loads(go_no_go_path.read_text(encoding="utf-8"))
            payload["agent_layer_governance"]["current_controlled_slice_ids"] = ["market_observer"]
            _write_json(go_no_go_path, payload)
            verdict = evaluate_real_24h_rerun_verdict(
                artifacts_root=artifacts_root,
                rerun_label="rerun-slice-mismatch",
                preflight_label="preflight-green",
            )
            self.assertEqual(verdict["status"], "failed")
            self.assertIn("current_controlled_slice_ids does not match the shipped 8-slice list", verdict["failures"])

    def test_rerun_verdict_fails_when_soft_failures_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            _green_verdict_evidence(artifacts_root, "rerun-soft-failure")
            go_no_go_path = artifacts_root / "soak_runs" / "rerun-soft-failure" / "go_no_go.json"
            payload = json.loads(go_no_go_path.read_text(encoding="utf-8"))
            payload["soft_failures"] = ["runtime window too short"]
            _write_json(go_no_go_path, payload)
            verdict = evaluate_real_24h_rerun_verdict(
                artifacts_root=artifacts_root,
                rerun_label="rerun-soft-failure",
                preflight_label="preflight-green",
            )
            self.assertEqual(verdict["status"], "failed")
            self.assertIn("soft_failures is not empty", verdict["failures"])

    def test_bundle_does_not_start_rerun_when_preflight_is_not_all_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            preflight_result = {
                "status": "failed",
                "preflight_status": "failed",
                "evidence_root": str((root / "artifacts" / "preflight_only" / "preflight-red").resolve()),
                "run_config_path": str((root / "artifacts" / "preflight_only" / "preflight-red" / "run_config.json").resolve()),
                "preflight_result_path": str((root / "artifacts" / "preflight_only" / "preflight-red" / "preflight_result.json").resolve()),
                "provider_health_snapshot_path": str((root / "artifacts" / "preflight_only" / "preflight-red" / "provider_health_snapshot.json").resolve()),
                "preflight_assertions_path": str((root / "artifacts" / "preflight_only" / "preflight-red" / "preflight_assertions.json").resolve()),
                "all_green": False,
                "assertions": {},
                "details": {},
            }
            with (
                mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False),
                mock.patch.object(bundle_script, "run_real_24h_preflight_only", return_value=preflight_result),
                mock.patch.object(bundle_script.subprocess, "run") as rerun_call,
            ):
                exit_code = bundle_script.main(
                    [
                        "--execution-permit",
                        str(permit_path),
                        "--artifacts-root",
                        str(root / "artifacts"),
                        "--preflight-label",
                        "preflight-red",
                        "--rerun-label",
                        "rerun-red",
                    ]
                )

            self.assertEqual(exit_code, 1)
            rerun_call.assert_not_called()
            bundle_summary = json.loads(
                (root / "artifacts" / "real_24h_bundles" / "rerun-red" / "bundle_summary.json").read_text(encoding="utf-8")
            )
            self.assertFalse(bundle_summary["rerun_started"])
            self.assertEqual(bundle_summary["failing_stage"], "preflight")

    def test_bundle_fails_closed_when_labels_collide(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            exit_code = bundle_script.main(
                [
                    "--execution-permit",
                    str(permit_path),
                    "--artifacts-root",
                    str(root / "artifacts"),
                    "--preflight-label",
                    "same-label",
                    "--rerun-label",
                    "same-label",
                ]
            )
            self.assertEqual(exit_code, 1)
            bundle_root = root / "artifacts" / "real_24h_bundles" / "same-label"
            self.assertTrue((bundle_root / "preflight_stage.json").exists())
            self.assertTrue((bundle_root / "rerun_stage.json").exists())
            self.assertTrue((bundle_root / "verdict_stage.json").exists())

    def test_bundle_fails_closed_when_rerun_evidence_dir_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            (root / "artifacts" / "soak_runs" / "rerun-exists").mkdir(parents=True, exist_ok=True)
            exit_code = bundle_script.main(
                [
                    "--execution-permit",
                    str(permit_path),
                    "--artifacts-root",
                    str(root / "artifacts"),
                    "--preflight-label",
                    "preflight-green",
                    "--rerun-label",
                    "rerun-exists",
                ]
            )
            self.assertEqual(exit_code, 1)
            bundle_summary = json.loads(
                (root / "artifacts" / "real_24h_bundles" / "rerun-exists" / "bundle_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(bundle_summary["failing_stage"], "preflight")

    def test_bundle_writes_stage_summaries_on_green_mocked_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            preflight_result = {
                "status": "passed",
                "preflight_status": "passed",
                "evidence_root": str((root / "artifacts" / "preflight_only" / "preflight-green").resolve()),
                "run_config_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "run_config.json").resolve()),
                "preflight_result_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "preflight_result.json").resolve()),
                "provider_health_snapshot_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "provider_health_snapshot.json").resolve()),
                "preflight_assertions_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "preflight_assertions.json").resolve()),
                "all_green": True,
                "assertions": {},
                "details": {},
            }
            verdict_result = {
                "status": "passed",
                "READY_FOR_REAL_24H_SHADOW": True,
                "READY_FOR_AGENT_LAYER": True,
                "READY_FOR_BROAD_AGENT_LAYER": True,
                "failures": [],
            }
            with (
                mock.patch.object(bundle_script, "run_real_24h_preflight_only", return_value=preflight_result),
                mock.patch.object(
                    bundle_script.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        args=["powershell"],
                        returncode=0,
                        stdout="RERUN_LABEL=rerun-green\n",
                        stderr="",
                    ),
                ),
                mock.patch.object(bundle_script, "evaluate_real_24h_rerun_verdict", return_value=verdict_result),
            ):
                exit_code = bundle_script.main(
                    [
                        "--execution-permit",
                        str(permit_path),
                        "--artifacts-root",
                        str(root / "artifacts"),
                        "--preflight-label",
                        "preflight-green",
                        "--rerun-label",
                        "rerun-green",
                    ]
                )

            self.assertEqual(exit_code, 0)
            bundle_root = root / "artifacts" / "real_24h_bundles" / "rerun-green"
            self.assertTrue((bundle_root / "bundle_summary.json").exists())
            self.assertTrue((bundle_root / "preflight_stage.json").exists())
            self.assertTrue((bundle_root / "rerun_stage.json").exists())
            self.assertTrue((bundle_root / "verdict_stage.json").exists())
            bundle_summary = json.loads((bundle_root / "bundle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle_summary["evidence_family"], "real_24h_bundle")
            self.assertEqual(bundle_summary["contract_version"], "real_24h_bundle.v1")
            self.assertTrue(bundle_summary["produced_at_utc"])

    def test_bundle_does_not_pass_on_exit_code_zero_without_green_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            permit_path = root / "external" / "execution_permit.json"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            preflight_result = {
                "status": "passed",
                "preflight_status": "passed",
                "evidence_root": str((root / "artifacts" / "preflight_only" / "preflight-green").resolve()),
                "run_config_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "run_config.json").resolve()),
                "preflight_result_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "preflight_result.json").resolve()),
                "provider_health_snapshot_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "provider_health_snapshot.json").resolve()),
                "preflight_assertions_path": str((root / "artifacts" / "preflight_only" / "preflight-green" / "preflight_assertions.json").resolve()),
                "all_green": True,
                "assertions": {},
                "details": {},
            }
            verdict_result = {
                "status": "failed",
                "READY_FOR_REAL_24H_SHADOW": True,
                "READY_FOR_AGENT_LAYER": False,
                "READY_FOR_BROAD_AGENT_LAYER": False,
                "failures": ["READY_FOR_BROAD_AGENT_LAYER is not true"],
            }
            with (
                mock.patch.object(bundle_script, "run_real_24h_preflight_only", return_value=preflight_result),
                mock.patch.object(
                    bundle_script.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        args=["powershell"],
                        returncode=0,
                        stdout="RERUN_LABEL=rerun-verdict-red\n",
                        stderr="",
                    ),
                ),
                mock.patch.object(bundle_script, "evaluate_real_24h_rerun_verdict", return_value=verdict_result),
            ):
                exit_code = bundle_script.main(
                    [
                        "--execution-permit",
                        str(permit_path),
                        "--artifacts-root",
                        str(root / "artifacts"),
                        "--preflight-label",
                        "preflight-green",
                        "--rerun-label",
                        "rerun-verdict-red",
                    ]
                )

            self.assertEqual(exit_code, 1)
            bundle_summary = json.loads(
                (root / "artifacts" / "real_24h_bundles" / "rerun-verdict-red" / "bundle_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(bundle_summary["evidence_family"], "real_24h_bundle")
            self.assertEqual(bundle_summary["contract_version"], "real_24h_bundle.v1")
            self.assertTrue(bundle_summary["produced_at_utc"])
            self.assertEqual(bundle_summary["failing_stage"], "verdict")
            self.assertEqual(bundle_summary["rerun_exit_code"], 0)
            self.assertEqual(bundle_summary["rerun_verdict"], "failed")


if __name__ == "__main__":
    unittest.main()
