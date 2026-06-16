from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import CAP_RUNTIME_EXECUTE, cleanup_orphan_execution_leases
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator, RuntimeRunRequest
from enhengclaw.orchestration.worker_operations import (
    default_runtime_audit_root,
    read_audit_record,
    read_business_intent_record,
    task_lock_path_for,
)
from enhengclaw.orchestration.worker_test_hooks import WORKER_TEST_HOOK_ENV
from enhengclaw.testing.execution_testbed import execution_testbed, sample_signals


class RuntimeBatchIdempotencyTests(unittest.TestCase):
    def test_run_batch_requires_explicit_business_request_id(self) -> None:
        requests = [self._batch_request(prefix="missing-id", object_id="missing-id-object")]
        with self.assertRaises(TypeError):
            RuntimeOrchestrator().run_batch(requests)

    def test_completed_batch_replay_reuses_persisted_results(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-batch-replay",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            orchestrator = RuntimeOrchestrator(execution_permit=permit)
            requests = self._batch_requests(prefix="replay")

            first = orchestrator.run_batch(requests, business_request_id="batch-replay")
            first_run_root = _latest_run_root(default_runtime_audit_root())
            first_audit = read_audit_record(first_run_root)

            replayed = orchestrator.run_batch(requests, business_request_id="batch-replay")
            replay_run_root = _latest_run_root(default_runtime_audit_root())
            replay_events = _event_names(replay_run_root)
            replay_audit = read_audit_record(replay_run_root)
            intent = read_business_intent_record(default_runtime_audit_root(), "batch-replay")

            self.assertEqual(
                [result.research_object.object_id for result in first],
                [result.research_object.object_id for result in replayed],
            )
            self.assertIn("controller.batch_intent_replay", replay_events)
            self.assertNotIn("controller.worker_dispatch", replay_events)
            self.assertEqual(replay_audit["status"], "completed")
            self.assertEqual(replay_audit["replayed_from_run_id"], first_audit["run_id"])
            self.assertEqual(intent["status"], "completed")
            self.assertEqual(intent["completed_run_id"], first_audit["run_id"])

    def test_same_business_request_id_with_different_payload_fails_closed(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-batch-conflict",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            orchestrator = RuntimeOrchestrator(execution_permit=permit)
            requests = self._batch_requests(prefix="conflict")

            orchestrator.run_batch(requests, business_request_id="batch-conflict")

            with self.assertRaisesRegex(RuntimeBoundaryError, "different batch payload"):
                orchestrator.run_batch(list(reversed(requests)), business_request_id="batch-conflict")

            conflict_run_root = _latest_run_root(default_runtime_audit_root())
            conflict_audit = read_audit_record(conflict_run_root)
            conflict_events = _event_names(conflict_run_root)
            intent = read_business_intent_record(default_runtime_audit_root(), "batch-conflict")

            self.assertEqual(conflict_audit["failure_category"], "business_request_conflict")
            self.assertIn("controller.batch_intent_conflict", conflict_events)
            self.assertEqual(intent["status"], "completed")

    def test_completed_replay_fails_closed_when_response_artifact_is_missing(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-batch-consistency",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            orchestrator = RuntimeOrchestrator(execution_permit=permit)
            requests = self._batch_requests(prefix="consistency")

            orchestrator.run_batch(requests, business_request_id="batch-consistency")
            intent = read_business_intent_record(default_runtime_audit_root(), "batch-consistency")
            Path(intent["response_path"]).unlink()

            with self.assertRaisesRegex(RuntimeBoundaryError, "completed batch replay artifact is missing"):
                orchestrator.run_batch(requests, business_request_id="batch-consistency")

            failed_replay_run_root = _latest_run_root(default_runtime_audit_root())
            failed_replay_audit = read_audit_record(failed_replay_run_root)
            failed_replay_events = _event_names(failed_replay_run_root)

            self.assertEqual(failed_replay_audit["failure_category"], "business_request_consistency_error")
            self.assertIn("controller.batch_intent_replay_inconsistent", failed_replay_events)

    def test_failed_batch_can_retry_with_same_business_request_id(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-batch-retry",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            orchestrator = RuntimeOrchestrator(execution_permit=permit)
            requests = self._batch_requests(prefix="retry")

            with _temp_worker_hooks({"crash_after_lease": True}):
                with self.assertRaises(RuntimeBoundaryError):
                    orchestrator.run_batch(requests, business_request_id="batch-retry")

            intent_after_failure = read_business_intent_record(default_runtime_audit_root(), "batch-retry")
            self.assertEqual(intent_after_failure["status"], "failed")

            cleanup_orphan_execution_leases()
            _, recovery_permit = bed.issue_permit(
                slug="runtime-batch-retry-recovery",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            recovered = RuntimeOrchestrator(execution_permit=recovery_permit).run_batch(
                requests,
                business_request_id="batch-retry",
            )

            retry_run_root = _latest_run_root(default_runtime_audit_root())
            retry_events = _event_names(retry_run_root)
            intent_after_recovery = read_business_intent_record(default_runtime_audit_root(), "batch-retry")

            self.assertEqual(len(recovered), len(requests))
            self.assertIn("controller.batch_intent_retry", retry_events)
            self.assertEqual(intent_after_recovery["status"], "completed")

    def test_inflight_duplicate_batch_is_rejected(self) -> None:
        with execution_testbed() as bed:
            _, permit = bed.issue_permit(
                slug="runtime-batch-active-duplicate",
                scope="spot+perp",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            orchestrator = RuntimeOrchestrator(execution_permit=permit)
            requests = self._batch_requests(prefix="active")
            business_request_id = "batch-active"
            thread_state: dict[str, object] = {}

            def _run_batch() -> None:
                try:
                    thread_state["results"] = orchestrator.run_batch(requests, business_request_id=business_request_id)
                except BaseException as exc:  # noqa: BLE001
                    thread_state["error"] = exc

            with _temp_worker_hooks({"sleep_after_lease_seconds": 3.0}):
                worker = threading.Thread(target=_run_batch, name="runtime-batch-active-duplicate")
                worker.start()
                _wait_for_active_lock(default_runtime_audit_root(), business_request_id)

                with self.assertRaisesRegex(RuntimeBoundaryError, "already active"):
                    orchestrator.run_batch(requests, business_request_id=business_request_id)

                worker.join(timeout=15)

            self.assertFalse(worker.is_alive())
            if "error" in thread_state:
                raise thread_state["error"]  # pragma: no cover - surfaces unexpected thread failure
            self.assertEqual(len(thread_state.get("results", [])), len(requests))

    def _batch_requests(self, *, prefix: str) -> list[RuntimeRunRequest]:
        return [
            self._batch_request(prefix=f"{prefix}-one", object_id=f"{prefix}-one"),
            self._batch_request(prefix=f"{prefix}-two", object_id=f"{prefix}-two"),
        ]

    def _batch_request(self, *, prefix: str, object_id: str) -> RuntimeRunRequest:
        return RuntimeRunRequest(
            mode="create",
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=sample_signals(prefix),
        )


def _latest_run_root(audit_root: Path) -> Path:
    run_root = Path(audit_root) / "runs"
    candidates = [path for path in run_root.iterdir() if path.is_dir()]
    if not candidates:
        raise AssertionError(f"no run roots found in {run_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _event_names(run_root: Path) -> list[str]:
    events_path = run_root / "events.jsonl"
    if not events_path.exists():
        return []
    names: list[str] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        names.append(str(json.loads(line)["event"]))
    return names


def _wait_for_active_lock(audit_root: Path, business_request_id: str, *, timeout: float = 15.0) -> None:
    lock_path = task_lock_path_for(audit_root, f"runtime.run_batch.{business_request_id}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if lock_path.exists():
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("status") == "active":
                return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for active batch lock at {lock_path}")


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


if __name__ == "__main__":
    unittest.main()
