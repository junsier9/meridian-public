from __future__ import annotations

import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import (
    CAP_CLI_SHADOW_INGEST,
    CAP_PROVIDER_FETCH,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    CAP_RUNTIME_EXECUTE,
    LEASE_REGISTRY_PATH_ENV,
    WORKER_LEASE_STALE_SECONDS,
    cleanup_orphan_execution_leases,
    clear_global_freeze,
    default_lease_registry_path,
    list_execution_leases,
    process_exists,
    snapshot_execution_lease_registry,
    trigger_global_freeze,
)
from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator
from enhengclaw.orchestration.shadow_ingestion_runner import INGESTION_TASK_KEY
from enhengclaw.orchestration.worker_operations import (
    TASK_LOCK_STALE_SECONDS,
    _lock_is_active,
    acquire_task_lock,
    build_worker_request_envelope,
    default_ingestion_audit_root,
    default_runtime_audit_root,
    initialize_audit_record,
    prepare_run_root,
    read_audit_record,
    sanitize_fragment,
    task_lock_path_for,
)
from enhengclaw.orchestration.worker_test_hooks import WORKER_TEST_HOOK_ENV
from enhengclaw.testing.execution_testbed import execution_testbed, sample_signals


class GovernanceOperationalReadinessTests(unittest.TestCase):
    def test_checked_in_governance_reports_all_promoted_controlled_slices(self) -> None:
        governance = evaluate_agent_layer_governance()
        self.assertEqual(governance["status"], "enabled")
        self.assertEqual(governance["blockers"], [])
        self.assertEqual(
            governance["current_controlled_slice_ids"],
            [
                "market_observer",
                "attention_allocator",
                "evidence_agent",
                "research_lead",
                "research_synthesizer",
                "risk_governance_agent",
                "risk_signal_agent",
                "validation_agent",
            ],
        )
        self.assertEqual(
            governance["admitted_controlled_slice_ids"],
            [
                "market_observer",
                "evidence_agent",
                "risk_signal_agent",
                "risk_governance_agent",
                "validation_agent",
                "attention_allocator",
                "research_synthesizer",
                "research_lead",
            ],
        )
        self.assertEqual(
            governance["registered_pending_promotion_controlled_slice_ids"],
            [],
        )
        self.assertIn("risk_signal_agent", governance["promotion_eligible_controlled_slice_ids"])
        self.assertIn("risk_governance_agent", governance["promotion_eligible_controlled_slice_ids"])
        self.assertIn("validation_agent", governance["promotion_eligible_controlled_slice_ids"])
        self.assertIn("attention_allocator", governance["promotion_eligible_controlled_slice_ids"])
        self.assertIn("research_synthesizer", governance["promotion_eligible_controlled_slice_ids"])
        self.assertIn("research_lead", governance["promotion_eligible_controlled_slice_ids"])
        self.assertTrue(governance["broad_agent_layer_ready"])
        self.assertFalse(governance["broad_agent_layer_enabled"])
        self.assertEqual(governance["broad_blockers"], [])
        self.assertNotIn("risk_signal_agent", governance["registered_pending_promotion_controlled_slice_ids"])


class ExecutionControlOperationalReadinessTests(unittest.TestCase):
    def test_process_exists_reports_terminated_child_as_not_alive(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "print('done')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        child.communicate(timeout=10)
        _wait_until(lambda: not process_exists(child.pid), timeout=5.0, label="terminated child not alive")
        self.assertFalse(process_exists(child.pid))

    def test_task_lock_is_active_for_fresh_live_process(self) -> None:
        payload = {
            "status": "active",
            "controller_pid": os.getpid(),
            "worker_pid": None,
            "updated_at_utc": _iso_now(),
        }
        self.assertTrue(_lock_is_active(payload, stale_after_seconds=TASK_LOCK_STALE_SECONDS))

    def test_reclaiming_long_task_lock_writes_orphan_record_without_windows_path_overflow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task_lock_reclaim_long_path_") as tmpdir:
            audit_root = (
                Path(tmpdir)
                / ("research_workbench_" + ("x" * 35))
                / ("eth_conservative_20260420_" + ("y" * 8))
                / "operational_audit"
                / "runtime"
            )
            task_key = "runtime.continue_existing.eth-conservative-20260420"
            lock_path = task_lock_path_for(audit_root, task_key)
            stale_record = {
                "task_key": task_key,
                "run_id": "old-run",
                "status": "active",
                "controller_pid": 999999,
                "worker_pid": 999999,
                "lease_id": None,
                "created_at_utc": "2026-04-20T00:00:00Z",
                "updated_at_utc": "2026-04-20T00:00:00Z",
                "failure_category": None,
            }
            lock_path.write_text(json.dumps(stale_record, indent=2, sort_keys=True), encoding="utf-8")

            old_orphan_path = (
                lock_path.parent
                / "orphaned"
                / f"{sanitize_fragment(task_key)}-reclaimed-abcdef123456.json"
            )
            old_temp_path = old_orphan_path.with_name(f"{old_orphan_path.name}.{'f' * 32}.tmp")
            self.assertGreater(len(str(old_temp_path)), 260)

            _, orphaned = acquire_task_lock(
                audit_root=audit_root,
                task_key=task_key,
                run_id="new-run",
                controller_pid=os.getpid(),
                stale_after_seconds=0.0,
            )

            self.assertIsNotNone(orphaned)
            reclaim_records = list((lock_path.parent / "orphaned").glob("*.json"))
            self.assertTrue(reclaim_records)
            latest_reclaim = json.loads(max(reclaim_records, key=lambda path: path.stat().st_mtime).read_text(encoding="utf-8"))
            self.assertEqual(latest_reclaim["run_id"], "old-run")
            self.assertIn("reclaim_reason", latest_reclaim)

    def test_task_lock_is_inactive_when_pids_are_dead(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "print('done')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        child.communicate(timeout=10)
        payload = {
            "status": "active",
            "controller_pid": child.pid,
            "worker_pid": None,
            "updated_at_utc": _iso_now(),
        }
        self.assertFalse(_lock_is_active(payload, stale_after_seconds=TASK_LOCK_STALE_SECONDS))


class OperationalReadinessScriptTests(unittest.TestCase):
    def test_build_child_env_scrubs_stateful_overrides(self) -> None:
        module = _load_script_module("run_operational_readiness.py", "operational_readiness_verify_env")
        with tempfile.TemporaryDirectory() as tmpdir:
            attempt_root = Path(tmpdir)
            env = module.build_child_env(
                attempt_root=attempt_root,
                base_env={
                    "PYTHONPATH": "parent-path",
                    "UNCHANGED": "yes",
                    "ENHENGCLAW_TEST_REVIEW_OVERRIDE": '{"forced":"override"}',
                    "ENHENGCLAW_WORKER_TEST_HOOK_JSON": '{"crash_after_lease": true}',
                    "ENHENGCLAW_LEASE_REGISTRY_PATH": "stale-registry.sqlite3",
                    "ENHENGCLAW_OPERATIONAL_AUDIT_ROOT": "stale-audit-root",
                    "ENHENGCLAW_TRUST_ROOT_DIR": "stale-trust-root",
                    "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT": "1",
                    "ENHENGCLAW_RUNTIME_SESSION_ROOT": "stale-runtime-sessions",
                    "ENHENGCLAW_WORKER_MODE": "1",
                    "ENHENGCLAW_WORKER_LEASE_ID": "lease-id",
                    "ENHENGCLAW_WORKER_PERMIT_PATH": "permit.json",
                },
            )
        self.assertEqual(env["UNCHANGED"], "yes")
        self.assertIn(str(SRC), env["PYTHONPATH"])
        self.assertIn("parent-path", env["PYTHONPATH"])
        self.assertEqual(env["ENHENGCLAW_LEASE_REGISTRY_PATH"], str(attempt_root / "state" / "execution-leases.sqlite3"))
        self.assertEqual(env["ENHENGCLAW_OPERATIONAL_AUDIT_ROOT"], str(attempt_root / "state" / "operational_audit"))
        self.assertEqual(env["ENHENGCLAW_RUNTIME_SESSION_ROOT"], str(attempt_root / "state" / "runtime_sessions"))
        self.assertNotIn("ENHENGCLAW_TEST_REVIEW_OVERRIDE", env)
        self.assertNotIn("ENHENGCLAW_WORKER_TEST_HOOK_JSON", env)
        self.assertNotIn("ENHENGCLAW_TRUST_ROOT_DIR", env)
        self.assertNotIn("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", env)
        self.assertNotIn("ENHENGCLAW_WORKER_MODE", env)
        self.assertNotIn("ENHENGCLAW_WORKER_LEASE_ID", env)
        self.assertNotIn("ENHENGCLAW_WORKER_PERMIT_PATH", env)

    def test_run_operational_readiness_success_generates_attempt_evidence(self) -> None:
        module = _load_script_module("run_operational_readiness.py", "operational_readiness_verify_success")
        calls: list[str] = []

        def _fake_run_logged_command(*, label, command, cwd, env, output_root):
            output_root.mkdir(parents=True, exist_ok=True)
            stdout_path = output_root / "stdout.log"
            stderr_path = output_root / "stderr.log"
            result_path = output_root / "result.json"
            stdout_path.write_text("ok\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            result_path.write_text(json.dumps({"label": label, "returncode": 0}), encoding="utf-8")
            calls.append(label)
            return module.CommandResult(
                label=label,
                command=command,
                returncode=0,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                result_path=str(result_path),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            with mock.patch.object(module, "_run_logged_command", side_effect=_fake_run_logged_command):
                result = module.run_operational_readiness(
                    attempts=1,
                    retain_root=retain_root,
                    base_env={"PYTHONPATH": "parent"},
                )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.attempts_completed, 1)
            self.assertEqual(
                calls,
                [
                    "forced_kill_recovery_repeat_1",
                    "forced_kill_recovery_repeat_2",
                    "forced_kill_recovery_repeat_3",
                    "heartbeat_loss_repeat_1",
                    "heartbeat_loss_repeat_2",
                    "heartbeat_loss_repeat_3",
                    "tests_test_operational_readiness",
                    "short_soak",
                ],
            )
            attempt_dir = retain_root / "attempt-1"
            self.assertTrue((attempt_dir / "attempt_context.json").exists())
            self.assertTrue((attempt_dir / "attempt_summary.json").exists())
            self.assertTrue((retain_root / "operational_readiness_summary.json").exists())
            attempt_context = json.loads((attempt_dir / "attempt_context.json").read_text(encoding="utf-8"))
            summary = json.loads((retain_root / "operational_readiness_summary.json").read_text(encoding="utf-8"))
            self.assertIn("lease_registry_path", attempt_context)
            self.assertIn("operational_audit_root", attempt_context)
            self.assertIn("runtime_session_root", attempt_context)
            self.assertEqual(summary["evidence_family"], "operational_readiness")
            self.assertEqual(summary["contract_version"], "operational_readiness.v1")
            self.assertTrue(summary["produced_at_utc"])

    def test_run_operational_readiness_fail_fast_retains_attempt_roots(self) -> None:
        module = _load_script_module("run_operational_readiness.py", "operational_readiness_verify_fail_fast")
        calls: list[str] = []

        def _fake_run_logged_command(*, label, command, cwd, env, output_root):
            output_root.mkdir(parents=True, exist_ok=True)
            stdout_path = output_root / "stdout.log"
            stderr_path = output_root / "stderr.log"
            result_path = output_root / "result.json"
            returncode = 9 if len(calls) == 8 else 0
            stdout_path.write_text(f"{label}\n", encoding="utf-8")
            stderr_path.write_text("" if returncode == 0 else "failed\n", encoding="utf-8")
            result_path.write_text(json.dumps({"label": label, "returncode": returncode}), encoding="utf-8")
            calls.append(label)
            return module.CommandResult(
                label=label,
                command=command,
                returncode=returncode,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                result_path=str(result_path),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            with mock.patch.object(module, "_run_logged_command", side_effect=_fake_run_logged_command):
                result = module.run_operational_readiness(
                    attempts=3,
                    retain_root=retain_root,
                    base_env={},
                )

            self.assertEqual(result.exit_code, 9)
            self.assertEqual(result.attempts_completed, 2)
            self.assertTrue((retain_root / "attempt-1" / "attempt_summary.json").exists())
            self.assertTrue((retain_root / "attempt-2" / "attempt_summary.json").exists())
            self.assertFalse((retain_root / "attempt-3").exists())
            self.assertTrue((retain_root / "attempt-2" / "failure_snapshot.json").exists())
            summary = json.loads((retain_root / "operational_readiness_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["attempts_completed"], 2)
            self.assertEqual(summary["attempts"][-1]["failure_snapshot_path"], str(retain_root / "attempt-2" / "failure_snapshot.json"))
            self.assertEqual(summary["evidence_family"], "operational_readiness")
            self.assertEqual(summary["contract_version"], "operational_readiness.v1")
            self.assertTrue(summary["produced_at_utc"])
            self.assertEqual(len(calls), 9)

    def test_run_operational_readiness_attempts_use_distinct_state_roots(self) -> None:
        module = _load_script_module("run_operational_readiness.py", "operational_readiness_verify_distinct_roots")

        def _fake_run_logged_command(*, label, command, cwd, env, output_root):
            output_root.mkdir(parents=True, exist_ok=True)
            stdout_path = output_root / "stdout.log"
            stderr_path = output_root / "stderr.log"
            result_path = output_root / "result.json"
            stdout_path.write_text("ok\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            result_path.write_text(json.dumps({"label": label, "returncode": 0}), encoding="utf-8")
            return module.CommandResult(
                label=label,
                command=command,
                returncode=0,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                result_path=str(result_path),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            with mock.patch.object(module, "_run_logged_command", side_effect=_fake_run_logged_command):
                result = module.run_operational_readiness(
                    attempts=3,
                    retain_root=retain_root,
                    base_env={},
                )

            self.assertEqual(result.exit_code, 0)
            contexts = [
                json.loads((retain_root / f"attempt-{index}" / "attempt_context.json").read_text(encoding="utf-8"))
                for index in range(1, 4)
            ]
            self.assertEqual(
                len({context["lease_registry_path"] for context in contexts}),
                3,
            )
            self.assertEqual(
                len({context["operational_audit_root"] for context in contexts}),
                3,
            )
            self.assertEqual(
                len({context["runtime_session_root"] for context in contexts}),
                3,
            )

    def test_broad_bundle_uses_three_attempt_operational_readiness_gate(self) -> None:
        module = _load_script_module("run_broad_agent_layer_readiness.py", "broad_readiness_verify_script")
        commands: list[list[str]] = []

        def _fake_subprocess_run(command, check, cwd, env):
            commands.append(list(command))
            return subprocess.CompletedProcess(command, 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False),
                mock.patch.object(module.subprocess, "run", side_effect=_fake_subprocess_run),
                mock.patch.object(
                    module,
                    "evaluate_project_state_evidence_freshness",
                    return_value={
                        "status": "passed",
                        "references": [
                            {"status": "passed", "evidence_family": "openclaw_deployment_gate"},
                            {"status": "passed", "evidence_family": "real_shadow_verify"},
                            {"status": "passed", "evidence_family": "real_24h_preflight"},
                            {"status": "passed", "evidence_family": "real_24h_bundle"},
                        ],
                        "blockers": [],
                    },
                ),
            ):
                exit_code = module.main(["--retain-root", str(Path(tmpdir) / "broad-retain")])

        self.assertEqual(exit_code, 0)
        matching = [command for command in commands if "run_operational_readiness.py" in " ".join(command)]
        self.assertEqual(len(matching), 1)
        self.assertIn("--attempts", matching[0])
        self.assertIn("3", matching[0])

    def test_broad_bundle_writes_unlock_evaluation_with_metadata(self) -> None:
        module = _load_script_module("run_broad_agent_layer_readiness.py", "broad_readiness_verify_metadata")

        def _fake_subprocess_run(command, check, cwd, env):
            return subprocess.CompletedProcess(command, 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            retain_root = Path(tmpdir) / "broad-retain"
            with (
                mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False),
                mock.patch.object(module.subprocess, "run", side_effect=_fake_subprocess_run),
                mock.patch.object(
                    module,
                    "evaluate_project_state_evidence_freshness",
                    return_value={
                        "status": "passed",
                        "references": [
                            {"status": "passed", "evidence_family": "openclaw_deployment_gate"},
                            {"status": "passed", "evidence_family": "real_shadow_verify"},
                            {"status": "passed", "evidence_family": "real_24h_preflight"},
                            {"status": "passed", "evidence_family": "real_24h_bundle"},
                        ],
                        "blockers": [],
                    },
                ),
            ):
                exit_code = module.main(["--retain-root", str(retain_root)])

            self.assertEqual(exit_code, 0)
            unlock = json.loads((retain_root / "broad_unlock_evaluation.json").read_text(encoding="utf-8"))
            summary = json.loads((retain_root / "broad_readiness_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(unlock["status"], "eligible_for_manual_unlock")
            self.assertTrue(unlock["manual_manifest_unlock_required"])
            self.assertEqual(unlock["evidence_family"], "broad_agent_layer_readiness")
            self.assertEqual(summary["evidence_family"], "broad_agent_layer_readiness")
            self.assertEqual(summary["contract_version"], "broad_agent_layer_unlock.v1")
            self.assertTrue(summary["produced_at_utc"])

    def test_broad_bundle_env_scrubs_stateful_overrides_without_injecting_shared_state_paths(self) -> None:
        module = _load_script_module("run_broad_agent_layer_readiness.py", "broad_readiness_verify_env")
        env = module._build_env(retain_root=Path(tempfile.mkdtemp(prefix="broad-env-")))
        self.assertIn(str(SRC), env["PYTHONPATH"])
        self.assertNotIn("ENHENGCLAW_TEST_REVIEW_OVERRIDE", env)
        self.assertNotIn("ENHENGCLAW_LEASE_REGISTRY_PATH", env)
        self.assertNotIn("ENHENGCLAW_OPERATIONAL_AUDIT_ROOT", env)
        self.assertNotIn("ENHENGCLAW_RUNTIME_SESSION_ROOT", env)

    def test_broad_bundle_reports_failing_operational_attempt_context(self) -> None:
        module = _load_script_module("run_broad_agent_layer_readiness.py", "broad_readiness_verify_failure_context")

        def _fake_subprocess_run(command, check, cwd, env):
            if "run_operational_readiness.py" in " ".join(command):
                return subprocess.CompletedProcess(command, 1)
            return subprocess.CompletedProcess(command, 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            retain_root = Path(tmpdir) / "broad-retain"
            operational_root = retain_root / "operational_readiness"
            operational_root.mkdir(parents=True, exist_ok=True)
            (operational_root / "operational_readiness_summary.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "attempts": [
                            {
                                "attempt_root": str(operational_root / "attempt-2"),
                                "status": "failed",
                                "failure_snapshot_path": str(operational_root / "attempt-2" / "failure_snapshot.json"),
                                "step_results": [
                                    {
                                        "label": "heartbeat_loss_repeat_2",
                                        "returncode": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False),
                mock.patch.object(module.subprocess, "run", side_effect=_fake_subprocess_run),
                redirect_stdout(stdout),
            ):
                exit_code = module.main(["--retain-root", str(retain_root)])

        self.assertEqual(exit_code, 1)
        output = stdout.getvalue()
        self.assertIn("failing_operational_attempt_root=", output)
        self.assertIn("failing_operational_step=heartbeat_loss_repeat_2", output)
        self.assertIn("failing_operational_snapshot=", output)

    def test_task_lock_is_inactive_when_stale_even_if_process_is_alive(self) -> None:
        payload = {
            "status": "active",
            "controller_pid": os.getpid(),
            "worker_pid": None,
            "updated_at_utc": _iso_seconds_ago(TASK_LOCK_STALE_SECONDS + 30.0),
        }
        self.assertFalse(_lock_is_active(payload, stale_after_seconds=TASK_LOCK_STALE_SECONDS))


class RuntimeOperationalReadinessTests(unittest.TestCase):
    def test_runtime_worker_startup_failure_and_stream_anomaly_fail_closed(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-startup-failure",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
                allowed_operations=["runtime.*", "provider.*"],
            )
            with _temp_worker_hooks(
                {
                    "fail_before_permit": True,
                    "stdout_text": "runtime worker startup probe",
                    "stderr_text": "runtime worker startup error",
                    "stdout_nul": True,
                    "stderr_nul": True,
                }
            ):
                with self.assertRaises(RuntimeBoundaryError):
                    RuntimeOrchestrator(execution_permit=permit).run_new(
                        object_id="runtime-startup-failure",
                        object_type=ObjectType.ASSET,
                        scope="spot+perp",
                        signals=sample_signals("runtime-startup"),
                    )

            run_root = _latest_run_root(default_runtime_audit_root())
            audit = read_audit_record(run_root)
            self.assertEqual(audit["status"], "failed")
            self.assertEqual(audit["failure_category"], "worker_startup")
            self.assertIsNone(audit["lease_id"])
            self.assertTrue(audit["stdout"]["contains_nul"])
            self.assertTrue(audit["stderr"]["contains_nul"])
            self.assertFalse((bed.session_root / "runtime-startup-failure.json").exists())
            self.assertEqual(list_execution_leases(status="active"), [])

    def test_runtime_worker_crash_after_lease_is_fail_closed_and_orphan_cleanup_recovers(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-crash-after-lease",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
                allowed_operations=["runtime.*", "provider.*"],
            )
            with _temp_worker_hooks({"crash_after_lease": True}):
                with self.assertRaises(RuntimeBoundaryError):
                    RuntimeOrchestrator(execution_permit=permit).run_new(
                        object_id="runtime-crash-after-lease",
                        object_type=ObjectType.ASSET,
                        scope="spot+perp",
                        signals=sample_signals("runtime-crash"),
                    )

            active_leases = list_execution_leases(status="active")
            self.assertEqual(len(active_leases), 1, active_leases)
            cleanup = cleanup_orphan_execution_leases()
            self.assertEqual(len(cleanup), 1, cleanup)
            self.assertEqual(cleanup[0]["cleanup_reason"], "worker_pid_not_alive")
            run_root = _latest_run_root(default_runtime_audit_root())
            audit = read_audit_record(run_root)
            self.assertEqual(audit["status"], "failed")
            self.assertEqual(audit["worker_pid"], cleanup[0]["worker_pid"])

    def test_runtime_worker_request_schema_version_mismatch_fails_closed(self) -> None:
        with execution_testbed() as bed:
            permit_path, _ = bed.issue_permit(
                slug="runtime-schema-mismatch",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                request_root = Path(tmpdir)
                run_root = prepare_run_root(request_root / "audit", "runtime-schema")
                initialize_audit_record(
                    run_root,
                    component="runtime_controller",
                    run_id="runtime-schema",
                    task_key="runtime.schema",
                    controller_pid=os.getpid(),
                    request_path=run_root / "request.json",
                    request_kind="runtime",
                    request_schema_version="worker-request.v999",
                )
                request_path = request_root / "request.json"
                response_path = request_root / "response.json"
                envelope = build_worker_request_envelope(
                    request_kind="runtime",
                    run_id="runtime-schema",
                    task_key="runtime.schema",
                    audit_root=request_root / "audit",
                    task_lock_path=request_root / "audit" / "locks" / "runtime.schema.json",
                    payload={"mode": "create", "object_id": "bad-runtime", "signals": []},
                )
                envelope["schema_version"] = "worker-request.v999"
                request_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "enhengclaw.orchestration.runtime_worker",
                        "--method",
                        "run_new",
                        "--permit",
                        str(permit_path),
                        "--request",
                        str(request_path),
                        "--response",
                        str(response_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=_pythonpath_env(),
                    cwd=ROOT,
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn("schema version mismatch", completed.stderr)
                self.assertFalse(response_path.exists())
                self.assertFalse((bed.session_root / "bad-runtime.json").exists())


class IngestionOperationalReadinessTests(unittest.TestCase):
    def test_ingestion_worker_startup_failure_fail_closed_and_audited(self) -> None:
        with execution_testbed() as bed:
            artifacts_root = Path(tempfile.mkdtemp(prefix="ingestion_startup_failure_"))
            permit_path, _ = bed.issue_permit(
                slug="ingestion-startup-failure",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            completed = subprocess.run(
                _ingestion_command(artifacts_root=artifacts_root, permit_path=permit_path, run_seconds=5),
                check=False,
                capture_output=True,
                text=True,
                env=_pythonpath_env(
                    {
                        WORKER_TEST_HOOK_ENV: json.dumps(
                            {
                                "fail_before_permit": True,
                                "stdout_text": "ingestion startup probe",
                                "stderr_text": "ingestion startup failure",
                            }
                        )
                    }
                ),
                cwd=ROOT,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            run_root = _latest_run_root(default_ingestion_audit_root(artifacts_root))
            audit = read_audit_record(run_root)
            self.assertEqual(audit["status"], "failed")
            self.assertEqual(audit["failure_category"], "worker_startup")
            self.assertIsNone(audit["lease_id"])
            self.assertFalse((artifacts_root / "live_replay").exists())
            self.assertFalse((artifacts_root / "live_quarantine").exists())

    def test_ingestion_controller_crash_preserves_worker_isolation_and_duplicate_launch_is_rejected(self) -> None:
        with execution_testbed() as bed:
            artifacts_root = Path(tempfile.mkdtemp(prefix="ingestion_controller_crash_"))
            permit_path, _ = bed.issue_permit(
                slug="ingestion-controller-crash",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            duplicate_permit_path, _ = bed.issue_permit(
                slug="ingestion-controller-crash-duplicate",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            controller = _launch_ingestion_controller(
                artifacts_root=artifacts_root,
                permit_path=permit_path,
                run_seconds=30,
            )
            self.addCleanup(_safe_kill_pid, controller.pid)
            lock_record = _wait_for_lock_record(default_ingestion_audit_root(artifacts_root))
            worker_pid = int(lock_record["worker_pid"])
            self.assertTrue(process_exists(worker_pid))

            _safe_kill_pid(controller.pid)
            _wait_until(lambda: controller.poll() is not None, timeout=10, label="controller exit after forced kill")
            self.assertTrue(process_exists(worker_pid))

            duplicate = subprocess.run(
                _ingestion_command(artifacts_root=artifacts_root, permit_path=duplicate_permit_path, run_seconds=2),
                check=False,
                capture_output=True,
                text=True,
                env=_pythonpath_env(),
                cwd=ROOT,
            )
            self.assertEqual(duplicate.returncode, 1, duplicate.stdout + duplicate.stderr)

            _safe_kill_pid(worker_pid)
            cleanup = cleanup_orphan_execution_leases()
            self.assertTrue(any(item["worker_pid"] == worker_pid for item in cleanup), cleanup)

    def test_ingestion_worker_forced_kill_allows_orphan_cleanup_and_restart(self) -> None:
        with execution_testbed() as bed:
            artifacts_root = Path(tempfile.mkdtemp(prefix="ingestion_kill_restart_"))
            permit_path, _ = bed.issue_permit(
                slug="ingestion-kill-restart",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            recovery_permit_path, _ = bed.issue_permit(
                slug="ingestion-kill-restart-recovery",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            controller = _launch_ingestion_controller(
                artifacts_root=artifacts_root,
                permit_path=permit_path,
                run_seconds=30,
            )
            lock_record = _wait_for_lock_record(default_ingestion_audit_root(artifacts_root))
            worker_pid = int(lock_record["worker_pid"])
            _safe_kill_pid(worker_pid)
            cleanup: list[dict[str, object]] = []

            def _worker_cleanup_observed() -> bool:
                nonlocal cleanup
                cleanup = cleanup_orphan_execution_leases()
                return any(item["worker_pid"] == worker_pid for item in cleanup)

            _wait_until(_worker_cleanup_observed, timeout=10.0, label="forced-kill orphan cleanup")
            self.assertTrue(any(item["worker_pid"] == worker_pid for item in cleanup), cleanup)
            recoverable_lock = _wait_for_recoverable_lock(
                default_ingestion_audit_root(artifacts_root),
                timeout=15.0,
            )
            if recoverable_lock is not None:
                self.assertFalse(
                    _lock_is_active(recoverable_lock, stale_after_seconds=TASK_LOCK_STALE_SECONDS),
                    recoverable_lock,
                )

            recovered = subprocess.run(
                _ingestion_command(artifacts_root=artifacts_root, permit_path=recovery_permit_path, run_seconds=2),
                check=False,
                capture_output=True,
                text=True,
                env=_pythonpath_env(),
                cwd=ROOT,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            _wait_until(lambda: controller.poll() is not None, timeout=15.0, label="controller exit after recovery")

            orphaned_dir = task_lock_path_for(default_ingestion_audit_root(artifacts_root), INGESTION_TASK_KEY).parent / "orphaned"
            reclaim_records = list(orphaned_dir.glob("*.json"))
            self.assertTrue(reclaim_records, orphaned_dir)
            latest_reclaim = json.loads(max(reclaim_records, key=lambda path: path.stat().st_mtime).read_text(encoding="utf-8"))
            self.assertIn("reclaim_reason", latest_reclaim)
            self.assertIn("worker_pid_state", latest_reclaim)
            self.assertIn("controller_pid_state", latest_reclaim)

    def test_ingestion_heartbeat_loss_fail_closed(self) -> None:
        with execution_testbed() as bed:
            artifacts_root = Path(tempfile.mkdtemp(prefix="ingestion_heartbeat_loss_"))
            permit_path, permit = bed.issue_permit(
                slug="ingestion-heartbeat-loss",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            audit_root = default_ingestion_audit_root(artifacts_root)
            lock_path = task_lock_path_for(audit_root, INGESTION_TASK_KEY)
            controller = _launch_ingestion_controller(
                artifacts_root=artifacts_root,
                permit_path=permit_path,
                run_seconds=30,
                extra_env={WORKER_TEST_HOOK_ENV: json.dumps({"disable_heartbeat": True})},
            )
            self.addCleanup(_safe_kill_pid, controller.pid)
            _wait_for_lock_record(audit_root)
            time.sleep(WORKER_LEASE_STALE_SECONDS + 1.5)
            cleanup: list[dict[str, object]] = []
            recent_cleanup_reasons: list[str] = []
            observation: dict[str, object] = {}

            def _cleanup_has_heartbeat_stale() -> bool:
                nonlocal cleanup
                nonlocal recent_cleanup_reasons
                nonlocal observation
                cleanup = cleanup_orphan_execution_leases()
                recent_cleanup_reasons = [
                    str(item.get("cleanup_reason"))
                    for item in cleanup
                    if item.get("cleanup_reason") is not None
                ]
                lease_snapshot = snapshot_execution_lease_registry(
                    registry_path=os.getenv(LEASE_REGISTRY_PATH_ENV) or default_lease_registry_path()
                )
                matching_lease = next(
                    (
                        row
                        for row in lease_snapshot["leases"]
                        if row.get("permit_id") == permit.permit_id
                    ),
                    None,
                )
                latest_audit = _latest_audit_details(audit_root)
                cleanup_events = []
                latest_audit_record = None
                if latest_audit is not None:
                    cleanup_events = [
                        event
                        for event in latest_audit["events"]
                        if event.get("event") == "lease.cleanup"
                    ]
                    latest_audit_record = latest_audit["audit"]
                observation = {
                    "lock_payload": _read_json_or_none(lock_path),
                    "lease_rows": lease_snapshot["leases"],
                    "latest_audit_run_root": None if latest_audit is None else latest_audit["run_root"],
                    "latest_audit_status": None if latest_audit_record is None else latest_audit_record.get("status"),
                    "latest_audit_failure_category": None
                    if latest_audit_record is None
                    else latest_audit_record.get("failure_category"),
                    "latest_audit_interruption_reason": None
                    if latest_audit_record is None
                    else latest_audit_record.get("interruption_reason"),
                    "recent_cleanup_reasons": recent_cleanup_reasons,
                }
                if any(item["cleanup_reason"] == "heartbeat_stale" for item in cleanup):
                    return True
                if any(event.get("cleanup_reason") == "heartbeat_stale" for event in cleanup_events):
                    return True
                return bool(
                    matching_lease is not None
                    and matching_lease.get("status") == "orphaned"
                    and latest_audit_record is not None
                    and "heartbeat" in str(latest_audit_record.get("interruption_reason", "")).lower()
                )

            try:
                _wait_until(_cleanup_has_heartbeat_stale, timeout=10.0, label="heartbeat-stale orphan cleanup")
            except AssertionError as exc:
                self.fail(f"{exc}; observation={json.dumps(observation, sort_keys=True)}")
            self.assertIn("heartbeat_stale", recent_cleanup_reasons + [
                str(event.get("cleanup_reason"))
                for event in (_latest_audit_details(audit_root) or {}).get("events", [])
                if isinstance(event, dict) and event.get("event") == "lease.cleanup"
            ])
            controller.wait(timeout=15)
            self.assertNotEqual(controller.returncode, 0)
            run_root = _latest_run_root(audit_root)
            audit = read_audit_record(run_root)
            self.assertEqual(audit["status"], "interrupted")

    def test_ingestion_freeze_and_expiry_interrupt_running_worker(self) -> None:
        with execution_testbed() as bed:
            freeze_path = bed.root / "global_freeze.json"
            freeze_artifacts_root = Path(tempfile.mkdtemp(prefix="ingestion_freeze_"))
            freeze_permit_path, _ = bed.issue_permit(
                slug="ingestion-freeze",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
                global_freeze_path=freeze_path,
            )
            controller = _launch_ingestion_controller(
                artifacts_root=freeze_artifacts_root,
                permit_path=freeze_permit_path,
                run_seconds=30,
            )
            _wait_for_lock_record(default_ingestion_audit_root(freeze_artifacts_root))
            trigger_global_freeze(reason="operational freeze test", freeze_path=freeze_path)
            try:
                controller.wait(timeout=15)
            finally:
                clear_global_freeze(freeze_path)
            self.assertNotEqual(controller.returncode, 0)
            freeze_audit = read_audit_record(_latest_run_root(default_ingestion_audit_root(freeze_artifacts_root)))
            self.assertEqual(freeze_audit["status"], "interrupted")
            self.assertIn("freeze", str(freeze_audit["interruption_reason"]).lower())

            expiry_artifacts_root = Path(tempfile.mkdtemp(prefix="ingestion_expiry_"))
            expiry_permit_path, _ = bed.issue_permit(
                slug="ingestion-expiry",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
                expires_after=timedelta(seconds=4),
            )
            expiry_controller = _launch_ingestion_controller(
                artifacts_root=expiry_artifacts_root,
                permit_path=expiry_permit_path,
                run_seconds=30,
            )
            _wait_for_lock_record(default_ingestion_audit_root(expiry_artifacts_root))
            expiry_controller.wait(timeout=15)
            self.assertNotEqual(expiry_controller.returncode, 0)
            expiry_audit = read_audit_record(_latest_run_root(default_ingestion_audit_root(expiry_artifacts_root)))
            self.assertEqual(expiry_audit["status"], "interrupted")
            self.assertIn("expired", str(expiry_audit["interruption_reason"]).lower())

    def test_ingestion_request_schema_version_mismatch_fails_closed(self) -> None:
        with execution_testbed() as bed:
            permit_path, _ = bed.issue_permit(
                slug="ingestion-schema-mismatch",
                scope="shadow_ingestion",
                capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
                allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                request_root = Path(tmpdir)
                artifacts_root = request_root / "artifacts"
                request_path = request_root / "request.json"
                envelope = build_worker_request_envelope(
                    request_kind="ingestion",
                    run_id="ingestion-schema",
                    task_key=INGESTION_TASK_KEY,
                    audit_root=default_ingestion_audit_root(artifacts_root),
                    task_lock_path=task_lock_path_for(default_ingestion_audit_root(artifacts_root), INGESTION_TASK_KEY),
                    payload={
                        "artifacts_root": str(artifacts_root),
                        "run_seconds": 0.1,
                        "log_level": "INFO",
                        "simulation_profile": "synthetic",
                        "synthetic_event_interval_seconds": 0.1,
                        "synthetic_quarantine_every": 0,
                        "binance_receive_timeout_seconds": 60.0,
                        "binance_initial_backoff_seconds": 1.0,
                        "binance_max_backoff_seconds": 30.0,
                        "binance_max_reconnect_attempts": None,
                        "alchemy_poll_interval_seconds": 5.0,
                        "alchemy_request_timeout_seconds": 10.0,
                        "alchemy_initial_backoff_seconds": 1.0,
                        "alchemy_max_backoff_seconds": 20.0,
                        "alchemy_max_retry_attempts": 5,
                        "alchemy_degraded_after_failures": 3,
                        "disable_eth_get_block_by_number": False,
                    },
                )
                envelope["schema_version"] = "worker-request.v999"
                request_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "enhengclaw.orchestration.ingestion_worker",
                        "--permit",
                        str(permit_path),
                        "--request",
                        str(request_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=_pythonpath_env(),
                    cwd=ROOT,
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn("schema version mismatch", completed.stderr)
                self.assertFalse((artifacts_root / "live_replay").exists())
                self.assertFalse((artifacts_root / "live_quarantine").exists())


def _pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


def _latest_run_root(audit_root: Path) -> Path:
    run_root = audit_root / "runs"
    candidates = [path for path in run_root.iterdir() if path.is_dir()]
    if not candidates:
        raise AssertionError(f"no run roots found in {run_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_audit_details(audit_root: Path) -> dict[str, Any] | None:
    run_root = audit_root / "runs"
    if not run_root.exists():
        return None
    candidates = [path for path in run_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return {
        "run_root": str(latest),
        "audit": read_audit_record(latest),
        "events": _read_jsonl(latest / "events.jsonl"),
    }


def _iso_now() -> str:
    return _iso_seconds_ago(0.0)


def _iso_seconds_ago(seconds: float) -> str:
    return datetime.fromtimestamp(time.time() - seconds, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _wait_until(predicate, *, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {label}")


def _wait_for_lock_record(audit_root: Path, *, timeout: float = 15.0) -> dict[str, object]:
    lock_path = task_lock_path_for(audit_root, INGESTION_TASK_KEY)

    def _load() -> dict[str, object] | None:
        if not lock_path.exists():
            return None
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError):
            return None
        if isinstance(payload, dict) and payload.get("worker_pid"):
            return payload
        return None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = _load()
        if payload is not None:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for ingestion worker lock at {lock_path}")


def _read_json_or_none(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                entries.append(payload)
    except (json.JSONDecodeError, OSError):
        return []
    return entries


def _wait_for_recoverable_lock(audit_root: Path, *, timeout: float = 15.0) -> dict[str, object] | None:
    lock_path = task_lock_path_for(audit_root, INGESTION_TASK_KEY)
    payload_holder: dict[str, object] | None = None

    def _recoverable() -> bool:
        nonlocal payload_holder
        if not lock_path.exists():
            payload_holder = None
            return True
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError):
            return False
        if not isinstance(payload, dict):
            return False
        payload_holder = payload
        return not _lock_is_active(payload, stale_after_seconds=TASK_LOCK_STALE_SECONDS)

    _wait_until(_recoverable, timeout=timeout, label=f"recoverable ingestion lock at {lock_path}")
    return payload_holder


def _launch_ingestion_controller(
    *,
    artifacts_root: Path,
    permit_path: Path,
    run_seconds: float,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        _ingestion_command(
            artifacts_root=artifacts_root,
            permit_path=permit_path,
            run_seconds=run_seconds,
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        env=_pythonpath_env(extra_env),
        cwd=ROOT,
    )


def _ingestion_command(*, artifacts_root: Path, permit_path: Path, run_seconds: float) -> list[str]:
    return [
        sys.executable,
        "-m",
        "enhengclaw.orchestration.shadow_ingestion_runner",
        "--artifacts-root",
        str(artifacts_root),
        "--execution-permit",
        str(permit_path),
        "--run-seconds",
        str(run_seconds),
        "--simulation-profile",
        "synthetic",
        "--synthetic-event-interval-seconds",
        "0.2",
        "--synthetic-quarantine-every",
        "5",
    ]


def _safe_kill_pid(pid: int | None) -> None:
    if pid is None or pid <= 0 or not process_exists(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True, text=True)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not process_exists(pid):
                return
            time.sleep(0.1)
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


class _temp_worker_hooks:
    def __init__(self, hooks: dict[str, object]) -> None:
        self.hooks = hooks
        self.saved = os.getenv(WORKER_TEST_HOOK_ENV)

    def __enter__(self) -> None:
        os.environ[WORKER_TEST_HOOK_ENV] = json.dumps(self.hooks)
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.saved is None:
            os.environ.pop(WORKER_TEST_HOOK_ENV, None)
        else:
            os.environ[WORKER_TEST_HOOK_ENV] = self.saved


def _load_script_module(script_name: str, module_name: str):
    script_path = ROOT / "scripts" / "verify" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load script module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
