from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback

from enhengclaw.core.execution_control import (
    CAP_RUNTIME_EXECUTE,
    RUNTIME_WORKER_ENTRYPOINT,
    WORKER_LEASE_HEARTBEAT_SECONDS,
    WORKER_LEASE_ID_ENV,
    WORKER_MODE_ENV,
    WORKER_PERMIT_PATH_ENV,
    acquire_execution_lease,
    clear_worker_interrupted,
    heartbeat_execution_lease,
    load_execution_permit,
    mark_worker_interrupted,
    release_execution_lease,
    require_active_worker_lease,
)
from enhengclaw.core.session import FileObjectStore
from enhengclaw.orchestration.provider_snapshot_runner import (
    execute_provider_snapshot_request,
    provider_snapshot_run_request_from_record,
    provider_snapshot_run_result_to_record,
)
from enhengclaw.orchestration.runtime_runner import (
    RuntimeOrchestrator,
    runtime_result_to_record,
    runtime_run_request_from_record,
)
from enhengclaw.orchestration.worker_operations import (
    WORKER_REQUEST_SCHEMA_VERSION,
    WorkerRequestSchemaError,
    append_audit_event,
    format_utc_timestamp,
    heartbeat_task_lock,
    load_worker_request_envelope,
    prepare_run_root,
    release_task_lock,
    utc_now,
    update_audit_record,
)
from enhengclaw.orchestration.worker_test_hooks import WorkerTestHooks, emit_test_stream_output


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_requested_scope(method: str, request_payload: dict[str, object], permit_scope: str) -> str:
    if method == "run_batch":
        return permit_scope
    if method == "run_provider_snapshot":
        request = provider_snapshot_run_request_from_record(request_payload)
        return request.scope
    request = runtime_run_request_from_record(request_payload)
    if method == "run_new":
        if request.scope is None:
            raise ValueError("runtime worker run_new requires request.scope")
        return request.scope
    if method == "continue_existing":
        session = FileObjectStore().load(request.object_id)
        return session.research_object.scope
    raise ValueError(f"unsupported runtime worker method: {method}")


def _dispatch(method: str, request_payload: dict[str, object], *, permit) -> dict[str, object]:
    orchestrator = RuntimeOrchestrator(execution_permit=permit)
    if method == "run_new":
        request = runtime_run_request_from_record(request_payload)
        if request.object_type is None or request.scope is None:
            raise ValueError("runtime worker run_new requires object_type and scope")
        if request.execution_profile is not None:
            orchestrator = RuntimeOrchestrator(
                execution_permit=permit,
                execution_profile=request.execution_profile,
            )
        result = orchestrator.run_new(
            object_id=request.object_id,
            object_type=request.object_type,
            scope=request.scope,
            signals=request.signals,
        )
        return runtime_result_to_record(result)
    if method == "continue_existing":
        request = runtime_run_request_from_record(request_payload)
        if request.execution_profile is not None:
            orchestrator = RuntimeOrchestrator(
                execution_permit=permit,
                execution_profile=request.execution_profile,
            )
        result = orchestrator.continue_existing(
            object_id=request.object_id,
            signals=request.signals,
        )
        return runtime_result_to_record(result)
    if method == "run_provider_snapshot":
        request = provider_snapshot_run_request_from_record(request_payload)
        result = execute_provider_snapshot_request(
            request,
            runtime=RuntimeOrchestrator(
                execution_permit=permit,
                execution_profile=request.execution_profile,
            ),
            execution_permit=permit,
        )
        return provider_snapshot_run_result_to_record(result)
    if method == "run_batch":
        requests = [runtime_run_request_from_record(dict(item)) for item in request_payload.get("requests", [])]
        business_request_id = str(request_payload.get("business_request_id", "")).strip()
        results = orchestrator.run_batch(requests, business_request_id=business_request_id)
        return {"results": [runtime_result_to_record(result) for result in results]}
    raise ValueError(f"unsupported runtime worker method: {method}")


def _heartbeat(
    stop_event: threading.Event,
    *,
    lease,
    run_root: Path,
    task_lock_path: Path,
    controller_pid: int,
) -> None:
    while not stop_event.wait(WORKER_LEASE_HEARTBEAT_SECONDS):
        try:
            heartbeat_execution_lease(lease)
            require_active_worker_lease(
                operation="runtime.worker.heartbeat",
                required_capabilities={CAP_RUNTIME_EXECUTE},
                requested_scope=lease.requested_scope,
                allowed_entrypoints={RUNTIME_WORKER_ENTRYPOINT},
            )
            append_audit_event(
                run_root,
                "lease.heartbeat",
                component="runtime_worker",
                lease_id=lease.lease_id,
                requested_scope=lease.requested_scope,
            )
            heartbeat_task_lock(
                task_lock_path,
                controller_pid=controller_pid,
                worker_pid=os.getpid(),
                lease_id=lease.lease_id,
            )
        except Exception as exc:
            mark_worker_interrupted(str(exc))
            append_audit_event(
                run_root,
                "lease.heartbeat_failed",
                component="runtime_worker",
                lease_id=lease.lease_id,
                error=str(exc),
            )
            stop_event.set()
            return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute runtime kernel work inside the isolated worker boundary.")
    parser.add_argument("--method", required=True, choices=("run_new", "continue_existing", "run_batch", "run_provider_snapshot"))
    parser.add_argument("--permit", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    hooks = WorkerTestHooks.from_env()
    permit_path = args.permit.resolve()
    request_path = args.request.resolve()
    response_path = args.response.resolve()

    os.environ[WORKER_MODE_ENV] = "1"
    os.environ[WORKER_PERMIT_PATH_ENV] = str(permit_path)
    clear_worker_interrupted()

    lease = None
    stop_event = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    run_root = None
    task_lock_path = None
    final_status = "failed"
    failure_category = "worker_startup"
    try:
        envelope = load_worker_request_envelope(request_path, expected_kind="runtime")
        run_root = prepare_run_root(envelope.audit_root, envelope.run_id)
        task_lock_path = Path(envelope.task_lock_path)
        emit_test_stream_output(hooks)
        append_audit_event(
            run_root,
            "worker.request_loaded",
            component="runtime_worker",
            request_schema_version=WORKER_REQUEST_SCHEMA_VERSION,
            request_kind=envelope.request_kind,
        )
        update_audit_record(
            run_root,
            status="worker_bootstrap",
            worker_pid=os.getpid(),
            started_at_utc=envelope.created_at_utc,
        )
        heartbeat_task_lock(
            task_lock_path,
            controller_pid=envelope.controller_pid,
            worker_pid=os.getpid(),
        )
        if hooks.fail_before_permit:
            raise RuntimeError("runtime worker test hook fail_before_permit")
        permit = load_execution_permit(permit_path)
        append_audit_event(
            run_root,
            "lease.permit_loaded",
            component="runtime_worker",
            permit_id=permit.permit_id,
        )
        if hooks.fail_after_permit:
            raise RuntimeError("runtime worker test hook fail_after_permit")
        request_payload = dict(envelope.payload)
        requested_scope = _resolve_requested_scope(args.method, request_payload, permit.scope)
        lease = acquire_execution_lease(
            permit,
            permit_path=permit_path,
            operation=f"runtime.worker.{args.method}",
            requested_scope=requested_scope,
            required_capabilities={CAP_RUNTIME_EXECUTE},
        )
        os.environ[WORKER_LEASE_ID_ENV] = lease.lease_id
        append_audit_event(
            run_root,
            "lease.acquired",
            component="runtime_worker",
            lease_id=lease.lease_id,
            operation=lease.operation,
            requested_scope=lease.requested_scope,
            worker_pid=lease.worker_pid,
        )
        update_audit_record(
            run_root,
            status="running",
            worker_pid=os.getpid(),
            lease_id=lease.lease_id,
            operation=lease.operation,
            requested_scope=lease.requested_scope,
        )
        heartbeat_task_lock(
            task_lock_path,
            controller_pid=envelope.controller_pid,
            worker_pid=os.getpid(),
            lease_id=lease.lease_id,
        )
        if hooks.crash_after_lease:
            append_audit_event(
                run_root,
                "worker.test_hook_crash_after_lease",
                component="runtime_worker",
            )
            os._exit(97)
        if not hooks.disable_heartbeat:
            heartbeat_thread = threading.Thread(
                target=_heartbeat,
                args=(stop_event,),
                kwargs={
                    "lease": lease,
                    "run_root": run_root,
                    "task_lock_path": task_lock_path,
                    "controller_pid": envelope.controller_pid,
                },
                name="runtime-worker-heartbeat",
                daemon=True,
            )
            heartbeat_thread.start()
        if hooks.sleep_after_lease_seconds > 0:
            append_audit_event(
                run_root,
                "worker.test_hook_sleep_after_lease",
                component="runtime_worker",
                sleep_seconds=hooks.sleep_after_lease_seconds,
            )
            time.sleep(hooks.sleep_after_lease_seconds)
        response_payload = _dispatch(args.method, request_payload, permit=permit)
        response_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")
        release_execution_lease(lease, status="completed")
        append_audit_event(
            run_root,
            "lease.released",
            component="runtime_worker",
            lease_id=lease.lease_id,
            release_status="completed",
        )
        final_status = "completed"
        failure_category = None
        update_audit_record(
            run_root,
            status="completed",
            exit_code=0,
            failure_category=None,
            interruption_reason=None,
        )
        return 0
    except WorkerRequestSchemaError as exc:
        if run_root is not None:
            append_audit_event(
                run_root,
                "worker.request_schema_error",
                component="runtime_worker",
                error=str(exc),
            )
            update_audit_record(
                run_root,
                status="failed",
                exit_code=1,
                failure_category="request_schema",
                interruption_reason=str(exc),
            )
        traceback.print_exc(file=sys.stderr)
        return 1
    except Exception as exc:
        if run_root is not None:
            append_audit_event(
                run_root,
                "worker.failed",
                component="runtime_worker",
                error=str(exc),
            )
        if lease is not None:
            status = "interrupted" if stop_event.is_set() else "failed"
            try:
                release_execution_lease(lease, status=status)
                if run_root is not None:
                    append_audit_event(
                        run_root,
                        "lease.released",
                        component="runtime_worker",
                        lease_id=lease.lease_id,
                        release_status=status,
                    )
            except Exception:
                pass
            final_status = status
            failure_category = "lease_interrupted" if status == "interrupted" else "worker_failed"
        if run_root is not None:
            update_audit_record(
                run_root,
                status=final_status,
                exit_code=1,
                failure_category=failure_category,
                interruption_reason=str(exc),
            )
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        stop_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=WORKER_LEASE_HEARTBEAT_SECONDS + 0.5)
        if task_lock_path is not None:
            release_task_lock(
                task_lock_path,
                status=final_status,
                failure_category=failure_category,
                extra_fields={
                    "worker_pid": os.getpid(),
                    "lease_id": None if lease is None else lease.lease_id,
                },
            )
        if run_root is not None:
            update_audit_record(
                run_root,
                ended_at_utc=format_utc_timestamp(utc_now()),
            )
        os.environ.pop(WORKER_LEASE_ID_ENV, None)
        os.environ.pop(WORKER_PERMIT_PATH_ENV, None)
        os.environ.pop(WORKER_MODE_ENV, None)
        clear_worker_interrupted()


if __name__ == "__main__":
    raise SystemExit(main())
