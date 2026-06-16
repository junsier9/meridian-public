from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

from enhengclaw.core.execution_control import cleanup_orphan_execution_leases
from enhengclaw.orchestration.shadow_ingestion_providers import (
    build_legacy_provider_payloads,
    load_provider_payloads_from_config,
)
from enhengclaw.orchestration.worker_operations import (
    WORKER_REQUEST_SCHEMA_VERSION,
    WorkerTaskActiveError,
    acquire_task_lock,
    append_audit_event,
    audited_subprocess_run,
    build_run_id,
    build_worker_request_envelope,
    copy_request_artifact,
    default_ingestion_audit_root,
    initialize_audit_record,
    prepare_run_root,
    read_audit_record,
    release_task_lock,
    update_audit_record,
)


INGESTION_WORKER_MODULE = "enhengclaw.orchestration.ingestion_worker"
INGESTION_TASK_KEY = "shadow_ingestion.default"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch live shadow ingestion through the isolated ingestion worker boundary."
    )
    parser.add_argument(
        "--artifacts-root",
        default=Path(__file__).resolve().parents[3] / "artifacts",
        type=Path,
        help="Artifacts root. Replay data is written under live_replay/ and invalid payloads under live_quarantine/.",
    )
    parser.add_argument(
        "--execution-permit",
        default=None,
        help="Path to a signed execution permit JSON file.",
    )
    parser.add_argument(
        "--provider-config",
        default=None,
        help="Optional JSON file that defines the expanded shadow provider list.",
    )
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=None,
        help="Optional wall-clock runtime before the runner exits cleanly.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Python logging level.",
    )
    parser.add_argument(
        "--binance-receive-timeout-seconds",
        type=float,
        default=20.0,
        help="Reconnect Binance if no trade payload arrives within this interval.",
    )
    parser.add_argument(
        "--binance-initial-backoff-seconds",
        type=float,
        default=1.0,
        help="Initial Binance reconnect backoff.",
    )
    parser.add_argument(
        "--binance-max-backoff-seconds",
        type=float,
        default=5.0,
        help="Maximum Binance reconnect backoff.",
    )
    parser.add_argument(
        "--binance-max-reconnect-attempts",
        type=int,
        default=None,
        help="Optional cap on Binance reconnect attempts. Omit for unbounded reconnects.",
    )
    parser.add_argument(
        "--binance-websocket-url",
        default="wss://stream.binance.com:9443/ws",
        help="Optional Binance websocket endpoint override used by operational drills and local stubs.",
    )
    parser.add_argument(
        "--alchemy-poll-interval-seconds",
        type=float,
        default=5.0,
        help="Alchemy eth_blockNumber poll interval.",
    )
    parser.add_argument(
        "--alchemy-request-timeout-seconds",
        type=float,
        default=10.0,
        help="Alchemy HTTP request timeout.",
    )
    parser.add_argument(
        "--alchemy-initial-backoff-seconds",
        type=float,
        default=1.0,
        help="Initial Alchemy retry backoff.",
    )
    parser.add_argument(
        "--alchemy-max-backoff-seconds",
        type=float,
        default=20.0,
        help="Maximum Alchemy retry backoff.",
    )
    parser.add_argument(
        "--alchemy-max-retry-attempts",
        type=int,
        default=5,
        help="Maximum Alchemy retry attempts per RPC request.",
    )
    parser.add_argument(
        "--alchemy-degraded-after-failures",
        type=int,
        default=3,
        help="Consecutive failed poll cycles required before logging degraded state.",
    )
    parser.add_argument(
        "--disable-eth-get-block-by-number",
        action="store_true",
        help="Disable the optional eth_getBlockByNumber fetch for newly observed blocks.",
    )
    parser.add_argument(
        "--alchemy-endpoint-url",
        default=None,
        help="Optional Alchemy RPC endpoint override used by operational drills and local stubs.",
    )
    parser.add_argument(
        "--simulation-profile",
        default="real",
        choices=("real", "synthetic"),
        help="Use synthetic ingestion events for operational soak and readiness validation.",
    )
    parser.add_argument(
        "--synthetic-event-interval-seconds",
        type=float,
        default=1.0,
        help="Synthetic mode event interval.",
    )
    parser.add_argument(
        "--synthetic-quarantine-every",
        type=int,
        default=10,
        help="Synthetic mode quarantine cadence. Set 0 to disable quarantine probes.",
    )
    return parser


def shadow_ingestion_request_from_args(args: argparse.Namespace) -> dict[str, Any]:
    provider_config_path = None if args.provider_config in {None, ""} else str(Path(args.provider_config).resolve())
    providers = (
        load_provider_payloads_from_config(provider_config_path)
        if provider_config_path is not None
        else build_legacy_provider_payloads(
            binance_websocket_url=args.binance_websocket_url,
            binance_receive_timeout_seconds=args.binance_receive_timeout_seconds,
            binance_initial_backoff_seconds=args.binance_initial_backoff_seconds,
            binance_max_backoff_seconds=args.binance_max_backoff_seconds,
            binance_max_reconnect_attempts=args.binance_max_reconnect_attempts,
            alchemy_poll_interval_seconds=args.alchemy_poll_interval_seconds,
            alchemy_request_timeout_seconds=args.alchemy_request_timeout_seconds,
            alchemy_initial_backoff_seconds=args.alchemy_initial_backoff_seconds,
            alchemy_max_backoff_seconds=args.alchemy_max_backoff_seconds,
            alchemy_max_retry_attempts=args.alchemy_max_retry_attempts,
            alchemy_degraded_after_failures=args.alchemy_degraded_after_failures,
            disable_eth_get_block_by_number=args.disable_eth_get_block_by_number,
            alchemy_endpoint_url=args.alchemy_endpoint_url,
        )
    )
    return {
        "artifacts_root": str(Path(args.artifacts_root).resolve()),
        "provider_config_path": provider_config_path,
        "providers": providers,
        "run_seconds": args.run_seconds,
        "log_level": args.log_level,
        "simulation_profile": args.simulation_profile,
        "synthetic_event_interval_seconds": args.synthetic_event_interval_seconds,
        "synthetic_quarantine_every": args.synthetic_quarantine_every,
        "binance_receive_timeout_seconds": args.binance_receive_timeout_seconds,
        "binance_initial_backoff_seconds": args.binance_initial_backoff_seconds,
        "binance_max_backoff_seconds": args.binance_max_backoff_seconds,
        "binance_max_reconnect_attempts": args.binance_max_reconnect_attempts,
        "binance_websocket_url": args.binance_websocket_url,
        "alchemy_poll_interval_seconds": args.alchemy_poll_interval_seconds,
        "alchemy_request_timeout_seconds": args.alchemy_request_timeout_seconds,
        "alchemy_initial_backoff_seconds": args.alchemy_initial_backoff_seconds,
        "alchemy_max_backoff_seconds": args.alchemy_max_backoff_seconds,
        "alchemy_max_retry_attempts": args.alchemy_max_retry_attempts,
        "alchemy_degraded_after_failures": args.alchemy_degraded_after_failures,
        "disable_eth_get_block_by_number": args.disable_eth_get_block_by_number,
        "alchemy_endpoint_url": args.alchemy_endpoint_url,
    }


def _serialize_worker_request(payload: dict[str, Any]) -> tuple[Path, Path]:
    request_dir = Path(tempfile.mkdtemp(prefix="enhengclaw_ingestion_request_"))
    request_path = request_dir / "request.json"
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return request_path, request_dir


def _build_worker_command(*, request_path: Path, execution_permit: str | None) -> list[str]:
    command = [
        sys.executable,
        "-m",
        INGESTION_WORKER_MODULE,
        "--request",
        str(request_path),
    ]
    if execution_permit is not None and execution_permit.strip():
        command.extend(["--permit", str(Path(execution_permit).resolve())])
    return command


def _build_worker_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(Path(__file__).resolve().parents[2])]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def dispatch_ingestion_worker(args: argparse.Namespace) -> int:
    artifacts_root = Path(args.artifacts_root).resolve()
    audit_root = default_ingestion_audit_root(artifacts_root)
    run_id = build_run_id("ingestion")
    run_root = prepare_run_root(audit_root, run_id)
    initialize_audit_record(
        run_root,
        component="ingestion_controller",
        run_id=run_id,
        task_key=INGESTION_TASK_KEY,
        controller_pid=os.getpid(),
        request_path=run_root / "request.json",
        request_kind="ingestion",
        request_schema_version=WORKER_REQUEST_SCHEMA_VERSION,
    )
    cleanup_records = cleanup_orphan_execution_leases()
    if cleanup_records:
        update_audit_record(run_root, cleanup=cleanup_records)
        for record in cleanup_records:
            append_audit_event(
                run_root,
                "lease.cleanup",
                component="ingestion_controller",
                lease_id=record["lease_id"],
                cleanup_reason=record["cleanup_reason"],
                cleaned_status=record["status"],
                worker_pid_state=record.get("worker_pid_state"),
                heartbeat_age_seconds=record.get("heartbeat_age_seconds"),
            )
    try:
        task_lock_path, reclaimed_lock = acquire_task_lock(
            audit_root=audit_root,
            task_key=INGESTION_TASK_KEY,
            run_id=run_id,
            controller_pid=os.getpid(),
        )
    except WorkerTaskActiveError:
        append_audit_event(
            run_root,
            "controller.task_rejected_duplicate",
            component="ingestion_controller",
            task_key=INGESTION_TASK_KEY,
        )
        update_audit_record(
            run_root,
            status="failed",
            exit_code=1,
            failure_category="duplicate_task_active",
            interruption_reason=f"task '{INGESTION_TASK_KEY}' is already active",
        )
        return 1
    if reclaimed_lock is not None:
        append_audit_event(
            run_root,
            "task_lock.reclaimed",
            component="ingestion_controller",
            previous_run_id=reclaimed_lock.get("run_id"),
            previous_status=reclaimed_lock.get("status"),
            reclaim_reason=reclaimed_lock.get("reclaim_reason"),
            worker_pid_state=reclaimed_lock.get("worker_pid_state"),
            controller_pid_state=reclaimed_lock.get("controller_pid_state"),
            lock_updated_at_utc=reclaimed_lock.get("lock_updated_at_utc"),
        )
    envelope = build_worker_request_envelope(
        request_kind="ingestion",
        run_id=run_id,
        task_key=INGESTION_TASK_KEY,
        audit_root=audit_root,
        task_lock_path=task_lock_path,
        payload=shadow_ingestion_request_from_args(args),
    )
    request_dir = None
    request_path, request_dir = _serialize_worker_request(envelope)
    copy_request_artifact(request_path, run_root)
    update_audit_record(run_root, request_path=str(request_path.resolve()))
    append_audit_event(
        run_root,
        "controller.request_serialized",
        component="ingestion_controller",
        request_path=str(request_path.resolve()),
    )
    try:
        update_audit_record(run_root, status="controller_dispatch")
        append_audit_event(
            run_root,
            "controller.worker_dispatch",
            component="ingestion_controller",
            worker_module=INGESTION_WORKER_MODULE,
        )
        completed = None
        for attempt in range(1, 3):
            try:
                completed = audited_subprocess_run(
                    _build_worker_command(
                        request_path=request_path,
                        execution_permit=args.execution_permit,
                    ),
                    env=_build_worker_env(),
                    run_root=run_root,
                )
                break
            except OSError as exc:
                append_audit_event(
                    run_root,
                    "controller.worker_spawn_failed",
                    component="ingestion_controller",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt == 1:
                    append_audit_event(
                        run_root,
                        "controller.worker_spawn_retry",
                        component="ingestion_controller",
                        retry_attempt=2,
                    )
                    continue
                update_audit_record(
                    run_root,
                    status="failed",
                    exit_code=1,
                    failure_category="worker_spawn_error",
                    interruption_reason=str(exc),
                )
                release_task_lock(
                    task_lock_path,
                    status="failed",
                    failure_category="worker_spawn_error",
                    extra_fields={"worker_pid": None, "lease_id": None},
                )
                raise
        if completed is None:
            raise RuntimeError("ingestion controller failed to obtain a worker process")
        update_audit_record(
            run_root,
            worker_pid=completed.worker_pid,
            exit_code=completed.returncode,
            stdout=completed.stdout.to_payload(),
            stderr=completed.stderr.to_payload(),
        )
        append_audit_event(
            run_root,
            "controller.worker_exit",
            component="ingestion_controller",
            worker_pid=completed.worker_pid,
            returncode=completed.returncode,
            stdout=completed.stdout.to_payload(),
            stderr=completed.stderr.to_payload(),
        )
        audit_record = read_audit_record(run_root)
        if completed.returncode != 0 and audit_record.get("status") in {None, "controller_dispatch", "worker_bootstrap", "running"}:
            update_audit_record(
                run_root,
                status="failed",
                failure_category=str(audit_record.get("failure_category") or "worker_exit_nonzero"),
            )
        release_task_lock(
            task_lock_path,
            status="completed" if completed.returncode == 0 else "failed",
            failure_category=None if completed.returncode == 0 else str(audit_record.get("failure_category") or "worker_exit_nonzero"),
            extra_fields={
                "worker_pid": completed.worker_pid,
                "lease_id": audit_record.get("lease_id"),
            },
        )
        return completed.returncode
    finally:
        if request_dir is not None:
            shutil.rmtree(request_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return dispatch_ingestion_worker(args)
    except KeyboardInterrupt:
        return 130
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
