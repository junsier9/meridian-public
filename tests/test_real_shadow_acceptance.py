from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr, redirect_stdout
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

from enhengclaw.orchestration.agent_layer_governance import (
    AGENT_LAYER_GOVERNANCE_CONTRACT_VERSION,
    GOVERNED_SLICE_REGISTRY_CONTRACT_VERSION,
    evaluate_agent_layer_governance,
)
from enhengclaw.agents.definitions.risk_signal_agent import RISK_SIGNAL_AGENT
from enhengclaw.orchestration.shadow_acceptance import (
    REAL_SHADOW_EVIDENCE_BUNDLE_VERSION,
    _probe_binance_websocket,
    build_controlled_agent_slices_summary,
    build_go_no_go,
    probe_binance_preflight,
)
from scripts.verify import run_real_shadow_acceptance as verify_wrapper

CURRENT_CONTROLLED_SLICE_IDS = [
    "market_observer",
    "attention_allocator",
    "evidence_agent",
    "research_lead",
    "research_synthesizer",
    "risk_governance_agent",
    "risk_signal_agent",
    "validation_agent",
]
ADMITTED_CONTROLLED_SLICE_IDS = [
    "market_observer",
    "evidence_agent",
    "risk_signal_agent",
    "risk_governance_agent",
    "validation_agent",
    "attention_allocator",
    "research_synthesizer",
    "research_lead",
]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _valid_governance_manifest(
    *,
    enabled: bool,
    allowed_controlled_slice_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "contract_version": AGENT_LAYER_GOVERNANCE_CONTRACT_VERSION,
        "agent_layer_governance_enabled": enabled,
        "allowed_controlled_slice_ids": allowed_controlled_slice_ids or list(ADMITTED_CONTROLLED_SLICE_IDS),
        "broad_agent_layer_enabled": False,
    }


def _valid_governed_slice_registry(
    *,
    admitted_controlled_slice_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "contract_version": GOVERNED_SLICE_REGISTRY_CONTRACT_VERSION,
        "admitted_controlled_slice_ids": admitted_controlled_slice_ids or list(ADMITTED_CONTROLLED_SLICE_IDS),
    }


def _ready_for_real_summary(root: Path) -> dict[str, object]:
    evidence_artifacts: dict[str, str] = {}
    for name in (
        "run_config.json",
        "provider_health_snapshot.json",
        "interruption_failure_evidence.json",
        "audit_record.json",
        "controller.stdout.log",
        "controller.stderr.log",
        "worker.stdout.log",
        "worker.stderr.log",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
        evidence_artifacts[path.stem.replace(".", "_")] = str(path)

    return {
        "controlled_agent_slices": build_controlled_agent_slices_summary(),
        "preflight": {
            "status": "passed",
            "failures": [],
        },
        "shadow": {
            "run": {
                "run_completed": True,
                "exit_code": 0,
                "started_at_utc": "2026-04-14T00:00:00Z",
                "ended_at_utc": "2026-04-14T00:10:00Z",
            },
            "quality": {
                "cross_subject_contamination_count": 0,
                "replay_parse_error_count": 0,
                "replay_write_failure_count": 0,
            },
            "security": {
                "key_leakage_detected": False,
                "unredacted_alchemy_endpoint_detected": False,
            },
            "subjects": {
                "BTCUSDT.binance.spot": {
                    "event_count": 1,
                }
            },
        },
        "audit": {
            "audit_record": {
                "status": "completed",
            },
            "event_counts": {
                "lease.acquired": 1,
                "lease.heartbeat": 1,
                "lease.released": 1,
            },
        },
        "provider_health_snapshot": {
            "preflight_provider_checks": {
                "binance": {
                    "status": "passed",
                    "minimum_permission_model": "public_stream_only",
                },
                "alchemy": {
                    "status": "passed",
                    "minimum_permission_model": "read_only_rpc",
                },
            },
            "provider_anomaly_stats": {
                "provider_degraded_count": 0,
                "provider_recovered_count": 0,
            },
        },
        "interruption_failure_evidence": {
            "active_leases_after_run": [],
        },
        "lease_lifecycle": {
            "lease_acquired_count": 1,
            "lease_released_count": 1,
        },
        "evidence_artifacts": evidence_artifacts,
        "run_config": {
            "evidence_bundle_version": REAL_SHADOW_EVIDENCE_BUNDLE_VERSION,
            "max_total_log_bytes": 128 * 1024 * 1024,
        },
    }


def _run_fault_drills(
    *drills: str,
    artifacts_root: Path | None = None,
) -> tuple[subprocess.CompletedProcess, dict[str, object]]:
    if artifacts_root is None:
        with tempfile.TemporaryDirectory() as tmpdir:
            return _run_fault_drills(
                *drills,
                artifacts_root=Path(tmpdir) / "artifacts",
            )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "drills" / "run_real_provider_fault_drills.py"),
            "--artifacts-root",
            str(Path(artifacts_root)),
            *[item for drill in drills for item in ("--drill", drill)],
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    summary = json.loads(completed.stdout)
    return completed, summary


def _cleanup_reasons(result: dict[str, object]) -> list[str]:
    cleanup = result.get("observed", {}).get("cleanup", [])
    return [str(item.get("cleanup_reason")) for item in cleanup if isinstance(item, dict)]


class RealShadowAcceptanceTests(unittest.TestCase):
    def test_controlled_agent_slice_summary_reflects_all_governed_slices(self) -> None:
        summary = build_controlled_agent_slices_summary()
        self.assertEqual(summary["contract_version"], "controlled_agent_slice.v1")
        self.assertEqual(summary["controlled_slice_count"], len(CURRENT_CONTROLLED_SLICE_IDS))
        self.assertEqual(summary["verified_slice_ids"], CURRENT_CONTROLLED_SLICE_IDS)
        self.assertEqual(summary["enabled_slice_ids"], CURRENT_CONTROLLED_SLICE_IDS)
        self.assertFalse(summary["broad_agent_layer_enabled"])

    def test_binance_preflight_accepts_raw_trade_event_payload(self) -> None:
        class _FakeWebSocket:
            def __init__(self) -> None:
                self._messages = iter(
                    [
                        '{"result":null,"id":1}',
                        '{"e":"trade","E":1775987588152,"s":"BTCUSDT","t":6209187151,"p":"71545.44000000","q":"0.00019000","T":1775987588152,"m":true,"M":true}',
                    ]
                )

            async def send(self, _message: str) -> None:
                return None

            async def recv(self) -> str:
                return next(self._messages)

        class _FakeConnect:
            async def __aenter__(self) -> _FakeWebSocket:
                return _FakeWebSocket()

            async def __aexit__(self, exc_type, exc, tb) -> bool:
                return False

        with mock.patch("enhengclaw.orchestration.shadow_acceptance.websockets.connect", return_value=_FakeConnect()):
            result = asyncio.run(_probe_binance_websocket("wss://stream.binance.com:9443/ws", timeout_seconds=2.0))
        self.assertEqual(result["transport"], "wss")
        self.assertEqual(result["sample_stream"], "btcusdt@trade")
        self.assertEqual(result["sample_symbol"], "BTCUSDT")
        self.assertTrue(result["subscription_acknowledged"])

    def test_binance_preflight_failure_emits_transport_diagnostics(self) -> None:
        with mock.patch.dict(os.environ, {"BINANCE_API_KEY": "real-provider-key"}, clear=False):
            result = probe_binance_preflight(
                websocket_url="ws://127.0.0.1:1/ws",
                timeout_seconds=1.0,
                api_key_env_var="BINANCE_API_KEY",
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["minimum_permission_model"], "public_stream_only")
        self.assertEqual(result["endpoint"], "ws://127.0.0.1:1/ws")
        self.assertEqual(result["transport"], "ws")
        self.assertEqual(result["host"], "127.0.0.1")
        self.assertEqual(result["port"], 1)
        self.assertEqual(result["path"], "/ws")
        self.assertEqual(result["transport_stage"], "connect")
        self.assertTrue(result["failure_category"])
        self.assertTrue(result["exception_type"])
        self.assertTrue(result["exception_message"])
        self.assertIsInstance(result["exception_chain"], list)
        self.assertIn("Binance websocket probe failed:", result["message"])

    def test_real_acceptance_wrapper_real_24h_preflight_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify" / "run_real_shadow_acceptance.py"),
                    "--mode",
                    "real-24h",
                    "--artifacts-root",
                    str(artifacts_root),
                    "--label",
                    "wrapper-preflight-fail",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            soak_root = artifacts_root / "soak_runs" / "wrapper-preflight-fail"
            summary = json.loads((soak_root / "soak_summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["go_no_go"]["READY_FOR_REAL_24H_SHADOW"])
            self.assertFalse(summary["go_no_go"]["READY_FOR_AGENT_LAYER"])
            self.assertTrue(summary["go_no_go"]["agent_layer_governance_enabled"])
            self.assertEqual(summary["go_no_go"]["agent_layer_governance"]["status"], "enabled")
            self.assertEqual(summary["go_no_go"]["agent_layer_governance"]["blockers"], [])
            self.assertEqual(summary["controlled_agent_slices"]["controlled_slice_count"], len(CURRENT_CONTROLLED_SLICE_IDS))
            self.assertEqual(
                summary["go_no_go"]["controlled_agent_slices"]["enabled_slice_ids"],
                CURRENT_CONTROLLED_SLICE_IDS,
            )
            self.assertFalse(
                any("business idempotency" in item for item in summary["go_no_go"]["agent_layer_blockers"])
            )
            self.assertEqual(summary["run_config"]["evidence_bundle_version"], "real-shadow-acceptance.v1")
            self.assertEqual(summary["run_config"]["min_permit_margin_seconds"], 86460.0)

    def test_real_preflight_fail_closed_emits_fixed_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_controlled_shadow_soak.py"),
                    "--artifacts-root",
                    str(artifacts_root),
                    "--label",
                    "preflight-fail",
                    "--simulation-profile",
                    "real",
                    "--duration-seconds",
                    "60",
                    "--require-explicit-real-permit",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            soak_root = artifacts_root / "soak_runs" / "preflight-fail"
            self.assertTrue(soak_root.exists())
            summary = json.loads((soak_root / "soak_summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["go_no_go"]["READY_FOR_REAL_24H_SHADOW"])
            self.assertFalse(summary["go_no_go"]["READY_FOR_AGENT_LAYER"])
            self.assertTrue(summary["go_no_go"]["agent_layer_governance_enabled"])
            self.assertEqual(summary["go_no_go"]["agent_layer_governance"]["status"], "enabled")
            self.assertEqual(summary["go_no_go"]["agent_layer_governance"]["blockers"], [])
            self.assertEqual(
                summary["controlled_agent_slices"]["verified_slice_ids"],
                CURRENT_CONTROLLED_SLICE_IDS,
            )
            self.assertFalse(summary["go_no_go"]["controlled_agent_slices"]["broad_agent_layer_enabled"])
            self.assertFalse(
                any("business idempotency" in item for item in summary["go_no_go"]["agent_layer_blockers"])
            )
            for name in (
                "run_config.json",
                "exit_status.json",
                "soak_summary.json",
                "audit_record.json",
                "events.jsonl",
                "controller.stdout.log",
                "controller.stderr.log",
                "worker.stdout.log",
                "worker.stderr.log",
                "provider_health_snapshot.json",
                "interruption_failure_evidence.json",
                "go_no_go.json",
                "postmortem.md",
            ):
                self.assertTrue((soak_root / name).exists(), name)

    def test_fault_drill_runner_passes_recovery_and_boundary_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "drills" / "run_real_provider_fault_drills.py"),
                    "--artifacts-root",
                    str(Path(tmpdir) / "artifacts"),
                    "--drill",
                    "provider_partial_outage_recovery",
                    "--drill",
                    "transient_connection_reset_recovery",
                    "--drill",
                    "run_batch_payload_digest_boundary",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertTrue(summary["all_passed"], summary)

    def test_fault_drill_runner_passes_runtime_controller_crash_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "drills" / "run_real_provider_fault_drills.py"),
                    "--artifacts-root",
                    str(Path(tmpdir) / "artifacts"),
                    "--drill",
                    "runtime_controller_crash_long_running_worker",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertTrue(summary["all_passed"], summary)
            result = summary["results"][0]
            self.assertEqual(result["name"], "runtime_controller_crash_long_running_worker")
            self.assertTrue(result["observed"]["worker_survived_after_controller_kill"])
            self.assertNotEqual(result["observed"]["duplicate_exit"], 0)
            self.assertEqual(result["observed"]["recovery_exit"], 0)

    def test_fault_drill_runner_passes_worker_kill_orphan_cleanup_standalone(self) -> None:
        completed, summary = _run_fault_drills("worker_kill_orphan_cleanup")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(summary["all_passed"], summary)
        result = summary["results"][0]
        self.assertEqual(result["name"], "worker_kill_orphan_cleanup")
        self.assertIn("worker_pid_not_alive", _cleanup_reasons(result))

    def test_fault_drill_runner_passes_fail_closed_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "drills" / "run_real_provider_fault_drills.py"),
                    "--artifacts-root",
                    str(Path(tmpdir) / "artifacts"),
                    "--drill",
                    "provider_timeout_fail_closed",
                    "--drill",
                    "network_dns_failure_fail_closed",
                    "--drill",
                    "disk_pressure_log_threshold",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertTrue(summary["all_passed"], summary)

    def test_fault_drill_runner_passes_controller_restart_duplicate_rejection_standalone(self) -> None:
        completed, summary = _run_fault_drills("controller_restart_duplicate_rejection")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(summary["all_passed"], summary)
        result = summary["results"][0]
        self.assertEqual(result["name"], "controller_restart_duplicate_rejection")
        self.assertIn("worker_pid_not_alive", _cleanup_reasons(result))
        duplicate_audit = result["observed"]["duplicate_audit"]
        self.assertEqual(duplicate_audit["failure_category"], "duplicate_task_active")
        self.assertIn("controller.task_rejected_duplicate", result["observed"]["duplicate_events"])
        self.assertNotIn("already consumed", str(duplicate_audit.get("interruption_reason", "")).lower())

    def test_fault_drill_runner_passes_ordered_duplicate_rejection_subset(self) -> None:
        completed, summary = _run_fault_drills(
            "duplicate_launch_rejection_real_profile",
            "controller_restart_duplicate_rejection",
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(summary["all_passed"], summary)
        results = {str(item["name"]): item for item in summary["results"]}
        self.assertEqual(
            list(results),
            [
                "duplicate_launch_rejection_real_profile",
                "controller_restart_duplicate_rejection",
            ],
        )
        self.assertIn("worker_pid_not_alive", _cleanup_reasons(results["duplicate_launch_rejection_real_profile"]))
        self.assertIn("worker_pid_not_alive", _cleanup_reasons(results["controller_restart_duplicate_rejection"]))
        self.assertEqual(
            results["controller_restart_duplicate_rejection"]["observed"]["duplicate_audit"]["failure_category"],
            "duplicate_task_active",
        )

    def test_verify_wrapper_retains_child_logs_and_summary_without_leaking_child_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            tests_completed = subprocess.CompletedProcess(
                args=["python", "-m", "unittest", "tests.test_real_shadow_acceptance"],
                returncode=0,
                stdout="",
                stderr="expected nested traceback retained here\nExecutionLeaseError\n",
            )
            drill_summary = {
                "generated_at_utc": "2026-04-18T00:00:00Z",
                "all_passed": True,
                "hard_failures": [],
                "soft_failures": [],
                "results": [],
            }
            fault_drills_completed = subprocess.CompletedProcess(
                args=["python", "scripts/drills/run_real_provider_fault_drills.py"],
                returncode=0,
                stdout=json.dumps(drill_summary),
                stderr="",
            )

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False),
                mock.patch.object(
                    verify_wrapper.subprocess,
                    "run",
                    side_effect=[tests_completed, fault_drills_completed],
                ),
                mock.patch.object(verify_wrapper, "_timestamp_token", return_value="20260418T000000Z"),
                mock.patch.object(verify_wrapper, "_read_json_if_present", return_value=drill_summary),
                redirect_stdout(stdout_buffer),
                redirect_stderr(stderr_buffer),
            ):
                exit_code = verify_wrapper.main(
                    [
                        "--mode",
                        "verify",
                        "--artifacts-root",
                        str(artifacts_root),
                        "--label",
                        "quiet-green",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr_buffer.getvalue(), "")
            summary = json.loads(stdout_buffer.getvalue())
            verify_root = artifacts_root / "verify_runs" / "quiet-green-20260418T000000Z"
            summary_path = verify_root / "verify_summary.json"
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(Path(summary["summary_path"]).resolve(), summary_path.resolve())
            self.assertTrue(summary_path.exists())
            retained_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(retained_summary["evidence_family"], "real_shadow_verify")
            self.assertEqual(retained_summary["contract_version"], "real_shadow_verify.v1")
            self.assertTrue(retained_summary["produced_at_utc"])
            self.assertTrue((verify_root / "tests.stdout.log").exists())
            self.assertTrue((verify_root / "tests.stderr.log").exists())
            self.assertTrue((verify_root / "fault_drills.stdout.log").exists())
            self.assertTrue((verify_root / "fault_drills.stderr.log").exists())
            self.assertIn(
                "ExecutionLeaseError",
                (verify_root / "tests.stderr.log").read_text(encoding="utf-8"),
            )

    def test_fault_drill_runner_reuses_artifacts_root_without_stale_worker_pid_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir) / "artifacts"
            stale_lock = (
                artifacts_root
                / "controller_restart_duplicate_rejection"
                / "artifacts"
                / "operational_audit"
                / "ingestion"
                / "locks"
                / "shadow_ingestion.default.json"
            )
            _write_json(
                stale_lock,
                {
                    "task_key": "shadow_ingestion.default",
                    "run_id": "stale-run",
                    "status": "active",
                    "controller_pid": os.getpid(),
                    "worker_pid": None,
                    "lease_id": None,
                    "created_at_utc": "2026-04-14T00:00:00Z",
                    "updated_at_utc": "2026-04-14T00:00:00Z",
                    "failure_category": None,
                },
            )
            first_completed, first_summary = _run_fault_drills(
                "controller_restart_duplicate_rejection",
                artifacts_root=artifacts_root,
            )
            self.assertEqual(first_completed.returncode, 0, first_completed.stdout + first_completed.stderr)
            self.assertTrue(first_summary["all_passed"], first_summary)

            second_completed, second_summary = _run_fault_drills(
                "controller_restart_duplicate_rejection",
                artifacts_root=artifacts_root,
            )
            self.assertEqual(second_completed.returncode, 0, second_completed.stdout + second_completed.stderr)
            self.assertTrue(second_summary["all_passed"], second_summary)
            self.assertIn("worker_pid_not_alive", _cleanup_reasons(second_summary["results"][0]))

    def test_agent_layer_governance_fail_closed_cases_emit_structured_blockers(self) -> None:
        cases = [
            {
                "name": "missing_manifest",
                "expected_code": "manifest_missing",
            },
            {
                "name": "missing_registry",
                "registry_missing": True,
                "payload": _valid_governance_manifest(enabled=False),
                "expected_code": "governed_slice_registry_missing",
            },
            {
                "name": "invalid_json",
                "raw": "{",
                "expected_code": "manifest_invalid_json",
            },
            {
                "name": "unknown_field",
                "payload": {
                    **_valid_governance_manifest(enabled=False),
                    "unexpected_field": True,
                },
                "expected_code": "manifest_unknown_fields",
            },
            {
                "name": "contract_version_mismatch",
                "payload": {
                    **_valid_governance_manifest(enabled=False),
                    "contract_version": "agent_layer_governance.v0",
                },
                "expected_code": "contract_version_mismatch",
            },
            {
                "name": "enabled_type_error",
                "payload": {
                    **_valid_governance_manifest(enabled=False),
                    "agent_layer_governance_enabled": "true",
                },
                "expected_code": "agent_layer_governance_enabled_type_error",
            },
            {
                "name": "broad_rollout_requested_without_agent_layer_enable",
                "payload": {
                    **_valid_governance_manifest(enabled=False),
                    "broad_agent_layer_enabled": True,
                },
                "expected_code": "broad_agent_layer_requires_agent_layer_governance_enabled",
            },
            {
                "name": "registry_out_of_scope",
                "payload": _valid_governance_manifest(enabled=False),
                "registry_payload": _valid_governed_slice_registry(
                    admitted_controlled_slice_ids=["market_observer", "evidence_agent", "third_agent"]
                ),
                "expected_code": "admitted_controlled_slice_ids_out_of_scope",
            },
            {
                "name": "broad_rollout_requested_before_registry_exact_match",
                "payload": {
                    **_valid_governance_manifest(enabled=True),
                    "broad_agent_layer_enabled": True,
                },
                "registry_payload": _valid_governed_slice_registry(
                    admitted_controlled_slice_ids=["market_observer", "evidence_agent"]
                ),
                "expected_code": "broad_agent_layer_not_ready",
            },
            {
                "name": "slice_out_of_scope",
                "payload": {
                    **_valid_governance_manifest(enabled=True),
                    "allowed_controlled_slice_ids": ["market_observer", "evidence_agent", "third_agent"],
                },
                "expected_code": "allowed_controlled_slice_ids_out_of_scope",
            },
            {
                "name": "registry_mismatch",
                "payload": _valid_governance_manifest(enabled=False),
                "registry_payload": _valid_governed_slice_registry(
                    admitted_controlled_slice_ids=["market_observer"]
                ),
                "expected_code": "current_controlled_slice_ids_not_admitted",
            },
            {
                "name": "slice_mismatch",
                "payload": {
                    **_valid_governance_manifest(enabled=True),
                    "allowed_controlled_slice_ids": ["market_observer"],
                },
                "expected_code": "allowed_controlled_slice_ids_mismatch",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for case in cases:
                with self.subTest(case=case["name"]):
                    manifest_path = root / case["name"] / "manifest.json"
                    registry_path = root / case["name"] / "governed_slice_registry.json"
                    if "payload" in case:
                        _write_json(manifest_path, case["payload"])
                    elif "raw" in case:
                        manifest_path.parent.mkdir(parents=True, exist_ok=True)
                        manifest_path.write_text(str(case["raw"]), encoding="utf-8")
                    if not case.get("registry_missing"):
                        _write_json(registry_path, case.get("registry_payload") or _valid_governed_slice_registry())

                    governance = evaluate_agent_layer_governance(
                        manifest_path=manifest_path,
                        registry_path=registry_path,
                    )
                    go_no_go = build_go_no_go(
                        summary=_ready_for_real_summary(root / case["name"] / "summary"),
                        require_real_24h=False,
                        agent_layer_governance=governance,
                    )
                    blocker_codes = [item["code"] for item in governance["blockers"]]

                    self.assertEqual(governance["status"], "blocked")
                    self.assertFalse(governance["agent_layer_governance_enabled"])
                    self.assertIn(case["expected_code"], blocker_codes)
                    self.assertEqual(
                        governance["current_controlled_slice_ids"],
                        CURRENT_CONTROLLED_SLICE_IDS,
                    )
                    self.assertEqual(
                        governance["all_agent_ids"],
                        [
                            "attention_allocator",
                            "evidence_agent",
                            "market_observer",
                            "research_lead",
                            "research_synthesizer",
                            "risk_signal_agent",
                            "risk_governance_agent",
                            "validation_agent",
                        ],
                    )
                    self.assertEqual(go_no_go["agent_layer_governance"]["status"], "blocked")
                    self.assertFalse(go_no_go["agent_layer_governance_enabled"])
                    self.assertFalse(go_no_go["READY_FOR_AGENT_LAYER"])
                    self.assertTrue(go_no_go["agent_layer_blockers"])

    def test_agent_layer_governance_can_enable_ready_for_agent_layer_with_all_promoted_slices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = root / "manifest.json"
            registry_path = root / "governed_slice_registry.json"
            _write_json(
                registry_path,
                _valid_governed_slice_registry(
                    admitted_controlled_slice_ids=list(ADMITTED_CONTROLLED_SLICE_IDS)
                ),
            )
            _write_json(
                manifest_path,
                _valid_governance_manifest(
                    enabled=True,
                    allowed_controlled_slice_ids=list(ADMITTED_CONTROLLED_SLICE_IDS),
                ),
            )

            governance = evaluate_agent_layer_governance(
                manifest_path=manifest_path,
                registry_path=registry_path,
            )
            go_no_go = build_go_no_go(
                summary=_ready_for_real_summary(root / "summary"),
                require_real_24h=False,
                agent_layer_governance=governance,
            )

            self.assertEqual(governance["status"], "enabled")
            self.assertTrue(governance["agent_layer_governance_enabled"])
            self.assertEqual(governance["blockers"], [])
            self.assertEqual(
                governance["admitted_controlled_slice_ids"],
                ADMITTED_CONTROLLED_SLICE_IDS,
            )
            self.assertEqual(
                governance["allowed_controlled_slice_ids"],
                ADMITTED_CONTROLLED_SLICE_IDS,
            )
            self.assertEqual(
                governance["current_controlled_slice_ids"],
                CURRENT_CONTROLLED_SLICE_IDS,
            )
            self.assertEqual(governance["registered_pending_promotion_controlled_slice_ids"], [])
            self.assertEqual(
                governance["promotion_eligible_controlled_slice_ids"],
                CURRENT_CONTROLLED_SLICE_IDS,
            )
            self.assertTrue(governance["broad_agent_layer_ready"])
            self.assertFalse(governance["broad_agent_layer_enabled"])
            self.assertEqual(governance["broad_blockers"], [])
            self.assertEqual(RISK_SIGNAL_AGENT["status"], "governed_agent_slice")
            self.assertTrue(bool(RISK_SIGNAL_AGENT["enabled_under_current_governance"]))
            self.assertIn("risk_signal_agent", governance["candidate_controlled_slice_ids"])
            self.assertTrue(go_no_go["agent_layer_governance_enabled"])
            self.assertEqual(go_no_go["agent_layer_blockers"], [])
            self.assertEqual(go_no_go["broad_blockers"], [])
            self.assertTrue(go_no_go["READY_FOR_REAL_24H_SHADOW"])
            self.assertTrue(go_no_go["READY_FOR_AGENT_LAYER"])
            self.assertTrue(go_no_go["READY_FOR_BROAD_AGENT_LAYER"])


if __name__ == "__main__":
    unittest.main()
