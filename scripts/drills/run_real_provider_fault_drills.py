from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import gc
import json
import logging
import os
from pathlib import Path
import shutil
import traceback
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import (
    CAP_CLI_SHADOW_INGEST,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    CAP_RUNTIME_EXECUTE,
    clear_global_freeze,
    cleanup_orphan_execution_leases,
    process_exists,
    trigger_global_freeze,
)
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator, RuntimeRunRequest
from enhengclaw.orchestration.worker_operations import (
    TASK_LOCK_STALE_SECONDS,
    _lock_is_active,
    default_ingestion_audit_root,
    default_runtime_audit_root,
    read_audit_record,
    read_business_intent_record,
    task_lock_path_for,
)
from enhengclaw.orchestration.worker_test_hooks import WORKER_TEST_HOOK_ENV
from enhengclaw.testing.execution_testbed import execution_testbed, sample_signals


@dataclass(frozen=True, slots=True)
class DrillResult:
    name: str
    passed: bool
    detail: str
    evidence_root: str
    observed: dict[str, Any]


_RUNTIME_CONTROLLER_LAUNCHER = r"""
from pathlib import Path
import sys
ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from enhengclaw.testing.execution_testbed import sample_signals
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import load_execution_permit
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
permit = load_execution_permit(Path(sys.argv[2]))
object_id = sys.argv[3]
RuntimeOrchestrator(execution_permit=permit).run_new(
    object_id=object_id,
    object_type=ObjectType.ASSET,
    scope="spot+perp",
    signals=sample_signals(object_id),
)
"""


class AlchemyStubServer:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.request_count = 0
        self.block_number_calls = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> AlchemyStubServer:
        self.server.state = self
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def rpc_url(self) -> str:
        return f"{self.base_url}/v2/local"

    @property
    def time_url(self) -> str:
        return f"{self.base_url}/time"

    def _build_handler(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/time":
                    self.send_error(404)
                    return
                payload = json.dumps(
                    {"serverTime": int(datetime.now(UTC).timestamp() * 1000)},
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:  # noqa: N802
                parent.request_count += 1
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                payload = json.loads(raw or b"{}")
                method = str(payload.get("method", ""))
                if parent.mode == "rate_limit_then_success" and method == "eth_blockNumber":
                    parent.block_number_calls += 1
                    if parent.block_number_calls <= 2:
                        self._write_json(429, {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": 429, "message": "rate limited"}})
                        return
                if parent.mode == "probe_then_rate_limit_then_success" and method == "eth_blockNumber":
                    parent.block_number_calls += 1
                    if 2 <= parent.block_number_calls <= 3:
                        self._write_json(429, {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": 429, "message": "rate limited"}})
                        return
                if method == "eth_blockNumber":
                    self._write_json(200, {"jsonrpc": "2.0", "id": payload.get("id"), "result": "0x10"})
                    return
                if method == "eth_getBlockByNumber":
                    block_number = payload.get("params", ["0x10"])[0]
                    self._write_json(
                        200,
                        {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "result": {"number": block_number, "hash": "0xabc", "timestamp": "0x6612e080"},
                        },
                    )
                    return
                self._write_json(400, {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32601, "message": "unknown method"}})

            def log_message(self, format: str, *args: object) -> None:
                return

            def _write_json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


class BinanceStubServer:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.connection_count = 0
        self._closed_runtime_streams: set[str] = set()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._port = 0

    def __enter__(self) -> BinanceStubServer:
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("Binance stub server did not start")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._loop is not None and self._shutdown_event is not None:
            self._loop.call_soon_threadsafe(self._shutdown_event.set)
        self._thread.join(timeout=10)

    @property
    def websocket_url(self) -> str:
        return f"ws://127.0.0.1:{self._port}"

    def _run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._shutdown_event = asyncio.Event()
        async with websockets.serve(self._handler, "127.0.0.1", 0) as server:
            self._port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await self._shutdown_event.wait()

    async def _handler(self, websocket) -> None:
        try:
            self.connection_count += 1
            raw_subscribe = await websocket.recv()
            subscribed_streams = self._parse_subscribed_streams(raw_subscribe)
            await websocket.send(json.dumps({"result": None, "id": 1}, separators=(",", ":")))
            if self.mode == "silent":
                while not self._stop.is_set():
                    await asyncio.sleep(0.1)
                return
            if self.mode == "probe_then_silent" and self.connection_count >= 2:
                while not self._stop.is_set():
                    await asyncio.sleep(0.1)
                return
            if self.mode == "close_always":
                await websocket.close()
                return
            if self.mode == "close_once_then_healthy" and self.connection_count == 1:
                await websocket.close()
                return
            if not subscribed_streams:
                subscribed_streams = ("btcusdt@trade",)
            close_after_first_live_stream: str | None = None
            if self.mode == "probe_then_close_once" and self.connection_count > 1:
                for stream in subscribed_streams:
                    if stream not in self._closed_runtime_streams:
                        self._closed_runtime_streams.add(stream)
                        close_after_first_live_stream = stream
                        break
            counter = 0
            while not self._stop.is_set():
                counter += 1
                stream = subscribed_streams[(counter - 1) % len(subscribed_streams)]
                symbol = stream.split("@", 1)[0].upper()
                payload = {
                    "stream": stream,
                    "data": {
                        "e": "trade",
                        "E": int(datetime.now(UTC).timestamp() * 1000),
                        "s": symbol,
                        "t": counter,
                        "p": "68000.00" if symbol == "BTCUSDT" else "3500.00",
                        "q": "0.01",
                    },
                }
                await websocket.send(json.dumps(payload, separators=(",", ":")))
                if close_after_first_live_stream == stream:
                    await asyncio.sleep(0.05)
                    await websocket.close()
                    return
                await asyncio.sleep(0.2)
        except websockets.ConnectionClosed:
            return

    @staticmethod
    def _parse_subscribed_streams(raw_payload: str) -> tuple[str, ...]:
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, dict):
            return ()
        params = payload.get("params")
        if not isinstance(params, list):
            return ()
        streams: list[str] = []
        for item in params:
            if isinstance(item, str) and item:
                streams.append(item.lower())
        return tuple(streams)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real-profile shadow fault drills with local provider stubs.")
    parser.add_argument("--artifacts-root", default=ROOT / "artifacts" / "real_provider_fault_drills", type=Path)
    parser.add_argument("--summary-path", default=None, type=Path)
    parser.add_argument("--drill", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.getLogger("websockets").setLevel(logging.CRITICAL)
    logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
    logging.getLogger("websockets.client").setLevel(logging.CRITICAL)
    args = build_parser().parse_args(argv)
    available = {
        "provider_partial_outage_recovery": drill_provider_partial_outage_recovery,
        "provider_timeout_fail_closed": drill_provider_timeout_fail_closed,
        "network_dns_failure_fail_closed": drill_network_dns_failure_fail_closed,
        "transient_connection_reset_recovery": drill_transient_connection_reset_recovery,
        "worker_kill_orphan_cleanup": drill_worker_kill_orphan_cleanup,
        "worker_crash_fail_closed": drill_worker_crash_fail_closed,
        "duplicate_launch_rejection_real_profile": drill_duplicate_launch_rejection_real_profile,
        "controller_restart_duplicate_rejection": drill_controller_restart_duplicate_rejection,
        "runtime_controller_crash_long_running_worker": drill_runtime_controller_crash_long_running_worker,
        "permit_expiry_interrupt": drill_permit_expiry_interrupt,
        "freeze_trigger_interrupt": drill_freeze_trigger_interrupt,
        "disk_pressure_log_threshold": drill_disk_pressure_log_threshold,
        "run_batch_payload_digest_boundary": drill_run_batch_payload_digest_boundary,
    }
    selected = args.drill or list(available.keys())
    results: list[DrillResult] = []
    for name in selected:
        if name not in available:
            raise SystemExit(f"unknown drill: {name}")
        evidence_root = Path(args.artifacts_root).resolve() / name
        _reset_evidence_root(evidence_root)
        try:
            result = available[name](Path(args.artifacts_root).resolve())
        except Exception as exc:  # noqa: BLE001
            result = DrillResult(
                name=name,
                passed=False,
                detail=f"drill raised {type(exc).__name__}: {exc}",
                evidence_root=str(evidence_root),
                observed={
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        _write_drill_result(result)
        results.append(result)
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "all_passed": all(result.passed for result in results),
        "hard_failures": [result.name for result in results if not result.passed],
        "soft_failures": [],
        "results": [asdict(result) for result in results],
    }
    if args.summary_path is None:
        summary_path = Path(args.artifacts_root).resolve() / "fault_drills_summary.json"
    else:
        summary_path = args.summary_path.resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 1


def drill_provider_partial_outage_recovery(root: Path) -> DrillResult:
    evidence_root = root / "provider_partial_outage_recovery"
    with execution_testbed() as bed, AlchemyStubServer("probe_then_rate_limit_then_success") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="partial-outage",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        completed, summary = _run_soak(
            evidence_root=evidence_root,
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--duration-seconds", "4",
                "--binance-websocket-url", binance.websocket_url,
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--clock-reference-url", alchemy.time_url,
                "--alchemy-poll-interval-seconds", "0.5",
                "--alchemy-request-timeout-seconds", "0.5",
            ],
        )
    passed = (
        completed.returncode == 0
        and summary.get("ready") is True
        and int(summary["shadow"]["stability"].get("alchemy_retry_count", 0)) > 0
    )
    return DrillResult(
        "provider_partial_outage_recovery",
        passed,
        f"exit={completed.returncode} retry_count={summary['shadow']['stability'].get('alchemy_retry_count', 0)}",
        str(evidence_root),
        {"summary": summary},
    )


def drill_provider_timeout_fail_closed(root: Path) -> DrillResult:
    evidence_root = root / "provider_timeout_fail_closed"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("probe_then_silent") as binance:
        permit_path, _ = bed.issue_permit(
            slug="provider-timeout",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        completed, summary = _run_soak(
            evidence_root=evidence_root,
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--duration-seconds", "4",
                "--binance-websocket-url", binance.websocket_url,
                "--binance-receive-timeout-seconds", "0.5",
                "--binance-max-reconnect-attempts", "1",
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--clock-reference-url", alchemy.time_url,
                "--alchemy-poll-interval-seconds", "0.5",
            ],
        )
    passed = completed.returncode != 0 and "shadow controller exited with code" in " | ".join(summary.get("violations", []))
    return DrillResult(
        "provider_timeout_fail_closed",
        passed,
        f"exit={completed.returncode}",
        str(evidence_root),
        {"summary": summary},
    )


def drill_network_dns_failure_fail_closed(root: Path) -> DrillResult:
    evidence_root = root / "network_dns_failure_fail_closed"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy:
        permit_path, _ = bed.issue_permit(
            slug="dns-failure",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        completed, summary = _run_soak(
            evidence_root=evidence_root,
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "binance-live-key", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--duration-seconds", "4",
                "--binance-websocket-url", "ws://nonexistent.invalid:65531",
                "--binance-max-reconnect-attempts", "1",
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--clock-reference-url", alchemy.time_url,
                "--alchemy-poll-interval-seconds", "0.5",
            ],
        )
    passed = completed.returncode != 0 and summary["audit"]["audit_record"].get("status") in {"failed", "interrupted", "preflight_failed"}
    return DrillResult(
        "network_dns_failure_fail_closed",
        passed,
        f"exit={completed.returncode}",
        str(evidence_root),
        {"summary": summary},
    )


def drill_transient_connection_reset_recovery(root: Path) -> DrillResult:
    evidence_root = root / "transient_connection_reset_recovery"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("probe_then_close_once") as binance:
        permit_path, _ = bed.issue_permit(
            slug="connection-reset",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        completed, summary = _run_soak(
            evidence_root=evidence_root,
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--duration-seconds", "4",
                "--binance-websocket-url", binance.websocket_url,
                "--binance-max-reconnect-attempts", "2",
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--clock-reference-url", alchemy.time_url,
                "--alchemy-poll-interval-seconds", "0.5",
            ],
        )
    passed = completed.returncode == 0 and int(summary["shadow"]["stability"].get("binance_reconnect_count", 0)) >= 1
    return DrillResult(
        "transient_connection_reset_recovery",
        passed,
        f"exit={completed.returncode} reconnects={summary['shadow']['stability'].get('binance_reconnect_count', 0)}",
        str(evidence_root),
        {"summary": summary},
    )


def drill_worker_kill_orphan_cleanup(root: Path) -> DrillResult:
    evidence_root = root / "worker_kill_orphan_cleanup"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="worker-kill",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        controller = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--run-seconds", "20",
                "--binance-websocket-url", binance.websocket_url,
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--alchemy-poll-interval-seconds", "0.5",
            ],
        )
        worker_pid = _wait_for_worker_pid(
            evidence_root / "artifacts",
            controller_pid=controller.pid,
        )
        cleanup = _kill_worker_and_collect_cleanup(
            worker_pid,
            label="worker-kill-worker",
        )
        controller_exit = _wait_process_exit(controller, timeout_seconds=20, label="worker-kill-controller")
        restart_same_permit = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--run-seconds", "2",
                "--binance-websocket-url", binance.websocket_url,
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--alchemy-poll-interval-seconds", "0.5",
            ],
        )
        restart_same_permit_exit = _wait_process_exit(
            restart_same_permit,
            timeout_seconds=20,
            label="worker-kill-restart-same-permit",
        )
        recoverable_lock = _wait_for_recoverable_ingestion_lock(
            evidence_root / "artifacts",
            timeout_seconds=15.0,
        )
        _reset_provider_state_for_restart(evidence_root / "artifacts")
        fresh_permit_path, _ = bed.issue_permit(
            slug="worker-kill-recovery",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        restart_fresh_permit = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=fresh_permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--run-seconds", "2",
                "--binance-websocket-url", binance.websocket_url,
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--alchemy-poll-interval-seconds", "0.5",
            ],
        )
        restart_fresh_permit_exit = _wait_process_exit(
            restart_fresh_permit,
            timeout_seconds=20,
            label="worker-kill-restart-fresh-permit",
        )
    passed = (
        controller_exit != 0
        and _cleanup_contains_reason(cleanup, "worker_pid_not_alive")
        and restart_same_permit_exit != 0
        and restart_fresh_permit_exit == 0
    )
    return DrillResult(
        "worker_kill_orphan_cleanup",
        passed,
        (
            f"controller_exit={controller_exit} cleanup_count={len(cleanup)} "
            f"same_permit_exit={restart_same_permit_exit} fresh_permit_exit={restart_fresh_permit_exit}"
        ),
        str(evidence_root),
        {
            "cleanup": cleanup,
            "recoverable_lock": recoverable_lock,
            "provider_state_reset_before_recovery": True,
            "same_permit_exit": restart_same_permit_exit,
            "fresh_permit_exit": restart_fresh_permit_exit,
        },
    )


def drill_worker_crash_fail_closed(root: Path) -> DrillResult:
    evidence_root = root / "worker_crash_fail_closed"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="worker-crash",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        controller = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={
                "BINANCE_API_KEY": "dummy-binance",
                "ALCHEMY_API_KEY": "dummy-alchemy",
                "ENHENGCLAW_WORKER_TEST_HOOK_JSON": json.dumps({"crash_after_lease": True}),
            },
            extra_args=[
                "--simulation-profile", "real",
                "--run-seconds", "20",
                "--binance-websocket-url", binance.websocket_url,
                "--alchemy-endpoint-url", alchemy.rpc_url,
            ],
        )
        exit_code = _wait_process_exit(controller, timeout_seconds=20, label="worker-crash-controller")
        cleanup = cleanup_orphan_execution_leases()
    passed = exit_code != 0 and len(cleanup) >= 1
    return DrillResult(
        "worker_crash_fail_closed",
        passed,
        f"controller_exit={exit_code} cleanup_count={len(cleanup)}",
        str(evidence_root),
        {"cleanup": cleanup},
    )


def drill_duplicate_launch_rejection_real_profile(root: Path) -> DrillResult:
    evidence_root = root / "duplicate_launch_rejection_real_profile"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="duplicate-launch",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        controller_one = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=["--simulation-profile", "real", "--run-seconds", "20", "--binance-websocket-url", binance.websocket_url, "--alchemy-endpoint-url", alchemy.rpc_url],
        )
        worker_pid = _wait_for_worker_pid(
            evidence_root / "artifacts",
            controller_pid=controller_one.pid,
        )
        controller_two = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=["--simulation-profile", "real", "--run-seconds", "5", "--binance-websocket-url", binance.websocket_url, "--alchemy-endpoint-url", alchemy.rpc_url],
        )
        duplicate_exit = _wait_process_exit(controller_two, timeout_seconds=15, label="duplicate-launch-controller-two")
        cleanup = _kill_worker_and_collect_cleanup(
            worker_pid,
            label="duplicate-launch-worker",
        )
        _wait_process_exit(controller_one, timeout_seconds=20, label="duplicate-launch-controller-one")
    passed = duplicate_exit != 0 and _cleanup_contains_reason(cleanup, "worker_pid_not_alive")
    return DrillResult(
        "duplicate_launch_rejection_real_profile",
        passed,
        f"duplicate_exit={duplicate_exit} cleanup_count={len(cleanup)}",
        str(evidence_root),
        {"cleanup": cleanup},
    )


def drill_controller_restart_duplicate_rejection(root: Path) -> DrillResult:
    evidence_root = root / "controller_restart_duplicate_rejection"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="controller-restart",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        controller_one = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=["--simulation-profile", "real", "--run-seconds", "20", "--binance-websocket-url", binance.websocket_url, "--alchemy-endpoint-url", alchemy.rpc_url],
        )
        worker_pid = _wait_for_worker_pid(
            evidence_root / "artifacts",
            controller_pid=controller_one.pid,
        )
        _kill_pid(controller_one.pid)
        _wait_process_exit(controller_one, timeout_seconds=10, label="controller-restart-controller-one")
        time.sleep(1.0)
        controller_two = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=["--simulation-profile", "real", "--run-seconds", "5", "--binance-websocket-url", binance.websocket_url, "--alchemy-endpoint-url", alchemy.rpc_url],
        )
        duplicate_exit = _wait_process_exit(controller_two, timeout_seconds=15, label="controller-restart-controller-two")
        duplicate_run_root = _find_ingestion_run_root_by_controller_pid(
            evidence_root / "artifacts",
            controller_pid=controller_two.pid,
        )
        duplicate_audit = (
            read_audit_record(duplicate_run_root)
            if duplicate_run_root is not None
            else {}
        )
        duplicate_events = [] if duplicate_run_root is None else _event_names(duplicate_run_root)
        cleanup = _kill_worker_and_collect_cleanup(
            worker_pid,
            label="controller-restart-worker",
        )
    passed = (
        duplicate_exit != 0
        and _cleanup_contains_reason(cleanup, "worker_pid_not_alive")
        and duplicate_audit.get("failure_category") == "duplicate_task_active"
        and "controller.task_rejected_duplicate" in duplicate_events
    )
    return DrillResult(
        "controller_restart_duplicate_rejection",
        passed,
        (
            f"duplicate_exit={duplicate_exit} cleanup_count={len(cleanup)} "
            f"duplicate_failure_category={duplicate_audit.get('failure_category')}"
        ),
        str(evidence_root),
        {
            "cleanup": cleanup,
            "duplicate_run_root": None if duplicate_run_root is None else str(duplicate_run_root),
            "duplicate_audit": duplicate_audit,
            "duplicate_events": duplicate_events,
        },
    )


def drill_runtime_controller_crash_long_running_worker(root: Path) -> DrillResult:
    evidence_root = root / "runtime_controller_crash_long_running_worker"
    runtime_object_id = "runtime-controller-crash"
    with execution_testbed() as bed:
        permit_path, _ = bed.issue_permit(
            slug="runtime-controller-crash",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        controller = _launch_runtime_controller(
            permit_path=permit_path,
            object_id=runtime_object_id,
            env_extra={
                "ENHENGCLAW_WORKER_TEST_HOOK_JSON": json.dumps({"sleep_after_lease_seconds": 12}),
            },
        )
        worker_pid = _wait_for_runtime_worker_pid(
            runtime_object_id,
            controller_pid=controller.pid,
        )
        _kill_pid(controller.pid)
        controller_exit = _wait_process_exit(
            controller,
            timeout_seconds=10,
            label="runtime-controller-crash-controller",
        )
        del controller
        gc.collect()
        worker_survived = process_exists(worker_pid)

        duplicate_permit_path, _ = bed.issue_permit(
            slug="runtime-controller-crash-duplicate",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        duplicate = _launch_runtime_controller(
            permit_path=duplicate_permit_path,
            object_id=runtime_object_id,
            env_extra={},
        )
        duplicate_exit = _wait_process_exit(
            duplicate,
            timeout_seconds=15,
            label="runtime-controller-crash-duplicate",
        )
        del duplicate
        gc.collect()

        _kill_pid(worker_pid)
        _wait_for_pid_dead(worker_pid, timeout_seconds=10, label="runtime-worker-after-controller-crash")
        cleanup = cleanup_orphan_execution_leases()

        recovery_permit_path, _ = bed.issue_permit(
            slug="runtime-controller-crash-recovery",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        recovery = _launch_runtime_controller(
            permit_path=recovery_permit_path,
            object_id=runtime_object_id,
            env_extra={},
        )
        recovery_exit = _wait_process_exit(
            recovery,
            timeout_seconds=20,
            label="runtime-controller-crash-recovery",
        )
    passed = (
        worker_survived
        and duplicate_exit != 0
        and any(item.get("cleanup_reason") == "worker_pid_not_alive" for item in cleanup)
        and recovery_exit == 0
    )
    return DrillResult(
        "runtime_controller_crash_long_running_worker",
        passed,
        (
            f"controller_exit={controller_exit} worker_survived={worker_survived} "
            f"duplicate_exit={duplicate_exit} cleanup_count={len(cleanup)} recovery_exit={recovery_exit}"
        ),
        str(evidence_root),
        {
            "controller_exit": controller_exit,
            "worker_pid": worker_pid,
            "worker_survived_after_controller_kill": worker_survived,
            "duplicate_exit": duplicate_exit,
            "cleanup": cleanup,
            "recovery_exit": recovery_exit,
        },
    )


def drill_permit_expiry_interrupt(root: Path) -> DrillResult:
    evidence_root = root / "permit_expiry_interrupt"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="permit-expiry",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            expires_after=timedelta(seconds=3),
        )
        controller = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=["--simulation-profile", "real", "--run-seconds", "20", "--binance-websocket-url", binance.websocket_url, "--alchemy-endpoint-url", alchemy.rpc_url, "--alchemy-poll-interval-seconds", "0.5"],
        )
        exit_code = _wait_process_exit(controller, timeout_seconds=20, label="permit-expiry-controller")
        audit_record = _latest_worker_audit(evidence_root / "artifacts")
    passed = exit_code != 0 and audit_record.get("status") == "interrupted"
    return DrillResult(
        "permit_expiry_interrupt",
        passed,
        f"exit={exit_code} status={audit_record.get('status')}",
        str(evidence_root),
        {"audit_record": audit_record},
    )


def drill_freeze_trigger_interrupt(root: Path) -> DrillResult:
    evidence_root = root / "freeze_trigger_interrupt"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        freeze_path = bed.root / "freeze.json"
        permit_path, _ = bed.issue_permit(
            slug="freeze-trigger",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
            global_freeze_path=freeze_path,
        )
        controller = _launch_controller(
            artifacts_root=evidence_root / "artifacts",
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=["--simulation-profile", "real", "--run-seconds", "20", "--binance-websocket-url", binance.websocket_url, "--alchemy-endpoint-url", alchemy.rpc_url, "--alchemy-poll-interval-seconds", "0.5"],
        )
        _wait_for_worker_pid(
            evidence_root / "artifacts",
            controller_pid=controller.pid,
        )
        trigger_global_freeze(reason="fault-drill", freeze_path=freeze_path)
        exit_code = _wait_process_exit(controller, timeout_seconds=20, label="freeze-trigger-controller")
        audit_record = _latest_worker_audit(evidence_root / "artifacts")
        clear_global_freeze(freeze_path)
    passed = exit_code != 0 and audit_record.get("status") == "interrupted"
    return DrillResult(
        "freeze_trigger_interrupt",
        passed,
        f"exit={exit_code} status={audit_record.get('status')}",
        str(evidence_root),
        {"audit_record": audit_record},
    )


def drill_disk_pressure_log_threshold(root: Path) -> DrillResult:
    evidence_root = root / "disk_pressure_log_threshold"
    with execution_testbed() as bed, AlchemyStubServer("healthy") as alchemy, BinanceStubServer("healthy") as binance:
        permit_path, _ = bed.issue_permit(
            slug="disk-threshold",
            scope="shadow_ingestion",
            capabilities=[CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT],
            allowed_operations=["cli.shadow_ingest.*", "provider.*"],
        )
        completed, summary = _run_soak(
            evidence_root=evidence_root,
            permit_path=permit_path,
            env_extra={"BINANCE_API_KEY": "dummy-binance", "ALCHEMY_API_KEY": "dummy-alchemy"},
            extra_args=[
                "--simulation-profile", "real",
                "--duration-seconds", "4",
                "--binance-websocket-url", binance.websocket_url,
                "--alchemy-endpoint-url", alchemy.rpc_url,
                "--clock-reference-url", alchemy.time_url,
                "--max-total-log-bytes", "1",
            ],
        )
    passed = completed.returncode != 0 and any("combined controller/worker logs reached" in item for item in summary.get("violations", []))
    return DrillResult(
        "disk_pressure_log_threshold",
        passed,
        f"exit={completed.returncode}",
        str(evidence_root),
        {"summary": summary},
    )


def drill_run_batch_payload_digest_boundary(root: Path) -> DrillResult:
    evidence_root = root / "run_batch_payload_digest_boundary"
    with execution_testbed() as bed:
        _, permit = bed.issue_permit(
            slug="run-batch-business-idempotency",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        orchestrator = RuntimeOrchestrator(execution_permit=permit)
        requests = [
            RuntimeRunRequest(
                mode="create",
                object_id="batch-one",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=sample_signals("batch-one"),
            ),
            RuntimeRunRequest(
                mode="create",
                object_id="batch-two",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=sample_signals("batch-two"),
            ),
        ]

        replay_business_request_id = "drill-batch-replay"
        first_results = orchestrator.run_batch(requests, business_request_id=replay_business_request_id)
        first_run_root = _latest_runtime_run_root(default_runtime_audit_root())
        first_audit = read_audit_record(first_run_root)

        replay_results = orchestrator.run_batch(requests, business_request_id=replay_business_request_id)
        replay_run_root = _latest_runtime_run_root(default_runtime_audit_root())
        replay_event_names = _event_names(replay_run_root)
        replay_audit = read_audit_record(replay_run_root)
        replay_intent = read_business_intent_record(default_runtime_audit_root(), replay_business_request_id)
        same_business_id_reuses_results = (
            [result.research_object.object_id for result in first_results]
            == [result.research_object.object_id for result in replay_results]
            and "controller.batch_intent_replay" in replay_event_names
            and "controller.worker_dispatch" not in replay_event_names
            and replay_audit.get("replayed_from_run_id") == first_audit.get("run_id")
            and replay_intent.get("completed_run_id") == first_audit.get("run_id")
        )

        conflict_detected = False
        conflict_message = ""
        try:
            orchestrator.run_batch(list(reversed(requests)), business_request_id=replay_business_request_id)
        except RuntimeBoundaryError as exc:
            conflict_message = str(exc)
            conflict_detected = "different batch payload" in conflict_message

        retry_business_request_id = "drill-batch-retry"
        retry_failed_closed = False
        with _temporary_worker_hooks({"crash_after_lease": True}):
            try:
                orchestrator.run_batch(requests, business_request_id=retry_business_request_id)
            except RuntimeBoundaryError:
                retry_failed_closed = True
        cleanup_orphan_execution_leases()
        _, recovery_permit = bed.issue_permit(
            slug="run-batch-business-idempotency-recovery",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        retry_results = RuntimeOrchestrator(execution_permit=recovery_permit).run_batch(
            requests,
            business_request_id=retry_business_request_id,
        )
        retry_run_root = _latest_runtime_run_root(default_runtime_audit_root())
        retry_event_names = _event_names(retry_run_root)
        retry_intent = read_business_intent_record(default_runtime_audit_root(), retry_business_request_id)
        safe_retry_proven = (
            retry_failed_closed
            and len(retry_results) == len(requests)
            and "controller.batch_intent_retry" in retry_event_names
            and retry_intent.get("status") == "completed"
        )

    passed = same_business_id_reuses_results and conflict_detected and safe_retry_proven
    return DrillResult(
        "run_batch_payload_digest_boundary",
        passed,
        (
            "same_business_id_reuses_results="
            f"{same_business_id_reuses_results} conflict_detected={conflict_detected} safe_retry_proven={safe_retry_proven}"
        ),
        str(evidence_root),
        {
            "same_business_id_reuses_results": same_business_id_reuses_results,
            "conflict_detected": conflict_detected,
            "conflict_message": conflict_message,
            "safe_retry_proven": safe_retry_proven,
            "business_idempotency_proven": passed,
            "replay_event_names": replay_event_names,
            "retry_event_names": retry_event_names,
        },
    )


def _latest_runtime_run_root(audit_root: Path) -> Path:
    candidates = [path for path in (Path(audit_root) / "runs").iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"no runtime run roots found in {audit_root}")
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


@contextmanager
def _temporary_worker_hooks(hooks: dict[str, object]) -> Iterator[None]:
    saved = os.getenv(WORKER_TEST_HOOK_ENV)
    os.environ[WORKER_TEST_HOOK_ENV] = json.dumps(hooks)
    try:
        yield None
    finally:
        if saved is None:
            os.environ.pop(WORKER_TEST_HOOK_ENV, None)
        else:
            os.environ[WORKER_TEST_HOOK_ENV] = saved


def _run_soak(
    *,
    evidence_root: Path,
    permit_path: Path,
    env_extra: dict[str, str],
    extra_args: list[str],
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_controlled_shadow_soak.py"),
        "--artifacts-root",
        str(evidence_root),
        "--label",
        "drill",
    ]
    command.extend(extra_args)
    command.extend(["--execution-permit", str(permit_path)])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=_pythonpath_env(env_extra),
    )
    summary_path = evidence_root / "soak_runs" / "drill" / "soak_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    return completed, summary


def _launch_controller(
    *,
    artifacts_root: Path,
    permit_path: Path,
    env_extra: dict[str, str],
    extra_args: list[str],
) -> subprocess.Popen[str]:
    artifacts_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "enhengclaw.orchestration.shadow_ingestion_runner",
        "--artifacts-root",
        str(artifacts_root),
        "--execution-permit",
        str(permit_path),
    ]
    command.extend(extra_args)
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=_pythonpath_env(env_extra),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=False,
    )


def _launch_runtime_controller(
    *,
    permit_path: Path,
    object_id: str,
    env_extra: dict[str, str],
) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-c",
        _RUNTIME_CONTROLLER_LAUNCHER,
        str(ROOT),
        str(permit_path),
        object_id,
    ]
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=_pythonpath_env(env_extra),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=False,
    )


def _wait_for_worker_pid(
    artifacts_root: Path,
    *,
    controller_pid: int | None = None,
    timeout_seconds: float = 15.0,
) -> int:
    audit_root = default_ingestion_audit_root(artifacts_root)
    lock_path = task_lock_path_for(audit_root, "shadow_ingestion.default")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if lock_path.exists():
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            observed_controller_pid = payload.get("controller_pid")
            if controller_pid is not None and observed_controller_pid != controller_pid:
                time.sleep(0.2)
                continue
            worker_pid = payload.get("worker_pid")
            if isinstance(worker_pid, int) and worker_pid > 0 and process_exists(worker_pid):
                return worker_pid
        time.sleep(0.2)
    raise TimeoutError(f"timed out waiting for worker pid in {lock_path}")


def _wait_for_runtime_worker_pid(
    object_id: str,
    *,
    controller_pid: int | None = None,
    timeout_seconds: float = 15.0,
) -> int:
    lock_path = task_lock_path_for(default_runtime_audit_root(), f"runtime.run_new.{object_id}")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if lock_path.exists():
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            observed_controller_pid = payload.get("controller_pid")
            if controller_pid is not None and observed_controller_pid != controller_pid:
                time.sleep(0.2)
                continue
            worker_pid = payload.get("worker_pid")
            if isinstance(worker_pid, int) and worker_pid > 0 and process_exists(worker_pid):
                return worker_pid
        time.sleep(0.2)
    raise TimeoutError(f"timed out waiting for runtime worker pid in {lock_path}")


def _wait_for_recoverable_ingestion_lock(
    artifacts_root: Path,
    *,
    timeout_seconds: float = 15.0,
) -> dict[str, Any] | None:
    lock_path = task_lock_path_for(default_ingestion_audit_root(artifacts_root), "shadow_ingestion.default")
    deadline = time.time() + timeout_seconds
    payload_holder: dict[str, Any] | None = None
    while time.time() < deadline:
        if not lock_path.exists():
            return None
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError):
            time.sleep(0.2)
            continue
        if not isinstance(payload, dict):
            time.sleep(0.2)
            continue
        payload_holder = payload
        if not _lock_is_active(payload, stale_after_seconds=TASK_LOCK_STALE_SECONDS):
            return payload_holder
        time.sleep(0.2)
    raise RuntimeError(f"recoverable ingestion lock did not appear within {timeout_seconds:.1f}s at {lock_path}")


def _latest_worker_audit(artifacts_root: Path) -> dict[str, Any]:
    audit_root = default_ingestion_audit_root(artifacts_root)
    runs_root = audit_root / "runs"
    candidates = [path for path in runs_root.iterdir() if path.is_dir()]
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return json.loads((latest / "audit_record.json").read_text(encoding="utf-8"))


def _find_ingestion_run_root_by_controller_pid(
    artifacts_root: Path,
    *,
    controller_pid: int,
) -> Path | None:
    audit_root = default_ingestion_audit_root(artifacts_root)
    runs_root = audit_root / "runs"
    if not runs_root.exists():
        return None
    matches: list[Path] = []
    for candidate in runs_root.iterdir():
        if not candidate.is_dir():
            continue
        audit = read_audit_record(candidate)
        if int(audit.get("controller_pid") or 0) == controller_pid:
            matches.append(candidate)
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _kill_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
        return
    os.kill(pid, 9)


def _terminate_pid_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
        return
    os.kill(pid, 9)


def _wait_process_exit(process: subprocess.Popen[Any], *, timeout_seconds: float, label: str) -> int:
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_pid_tree(process.pid)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise RuntimeError(f"{label} did not exit within {timeout_seconds:.1f}s") from exc


def _wait_for_pid_dead(pid: int, *, timeout_seconds: float, label: str) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.2)
    raise RuntimeError(f"{label} stayed alive beyond {timeout_seconds:.1f}s")


def _kill_worker_and_collect_cleanup(
    worker_pid: int,
    *,
    label: str,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    _kill_pid(worker_pid)
    _wait_for_pid_dead(worker_pid, timeout_seconds=timeout_seconds, label=label)
    deadline = time.time() + timeout_seconds
    latest_cleanup: list[dict[str, Any]] = []
    while time.time() < deadline:
        latest_cleanup = cleanup_orphan_execution_leases()
        if _cleanup_contains_reason(latest_cleanup, "worker_pid_not_alive"):
            return latest_cleanup
        time.sleep(0.2)
    return latest_cleanup


def _reset_provider_state_for_restart(artifacts_root: Path) -> None:
    provider_state_root = artifacts_root / "provider_state"
    shutil.rmtree(provider_state_root, ignore_errors=True)
    provider_state_root.mkdir(parents=True, exist_ok=True)


def _cleanup_contains_reason(cleanup: list[dict[str, Any]], reason: str) -> bool:
    return any(item.get("cleanup_reason") == reason for item in cleanup)


def _reset_evidence_root(evidence_root: Path) -> None:
    shutil.rmtree(evidence_root, ignore_errors=True)
    evidence_root.mkdir(parents=True, exist_ok=True)


def _pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


def _write_drill_result(result: DrillResult) -> None:
    evidence_root = Path(result.evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "drill_result.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
