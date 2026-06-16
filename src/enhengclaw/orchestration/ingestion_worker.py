from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from dataclasses import dataclass
import traceback
from typing import Any

from enhengclaw.core.execution_control import (
    CAP_CLI_SHADOW_INGEST,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    DEFAULT_SHADOW_INGEST_SCOPE,
    ExecutionControlError,
    EXECUTION_PERMIT_PATH_ENV,
    INGESTION_WORKER_ENTRYPOINT,
    WORKER_LEASE_HEARTBEAT_SECONDS,
    WORKER_LEASE_ID_ENV,
    WORKER_MODE_ENV,
    WORKER_PERMIT_PATH_ENV,
    acquire_execution_lease,
    clear_worker_interrupted,
    get_worker_interrupt_reason,
    heartbeat_execution_lease,
    load_execution_permit,
    mark_worker_interrupted,
    release_execution_lease,
    require_active_worker_lease,
)
from enhengclaw.health.data_health_monitor import DataHealthMonitor
from enhengclaw.health.downstream_gate import DownstreamBlockedError, DownstreamGate
from enhengclaw.health.downstream_ingress import DownstreamBlockAuditLog, DownstreamIngressGuard
from enhengclaw.health.health_event_log import HealthEventLog
from enhengclaw.health.health_rules import HealthRules
from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
from enhengclaw.ingress.shadow_schema import SHADOW_SCHEMA_VERSION, ValidatedShadowEvent
from enhengclaw.orchestration.shadow_ingestion_providers import (
    ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND,
    ALCHEMY_EVM_BLOCK_PROVIDER_KIND,
    ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND,
    BINANCE_TRADE_PROVIDER_KIND,
    build_legacy_provider_payloads,
    normalize_provider_payload,
    provider_subject_keys,
)
from enhengclaw.providers.alchemy_shadow_provider import (
    AlchemyEthShadowConfig,
    AlchemyEthShadowProvider,
)
from enhengclaw.providers.alchemy_bitcoin_shadow_provider import (
    AlchemyBitcoinShadowConfig,
    AlchemyBitcoinShadowProvider,
)
from enhengclaw.providers.alchemy_solana_shadow_provider import (
    AlchemySolanaShadowConfig,
    AlchemySolanaShadowProvider,
)
from enhengclaw.providers.binance_shadow_provider import (
    BinanceTradeShadowConfig,
    BinanceTradeShadowProvider,
)
from enhengclaw.providers.shadow_common import isoformat_utc, require_env, sleep_or_stop, utc_now
from enhengclaw.orchestration.worker_operations import (
    WORKER_REQUEST_SCHEMA_VERSION,
    WorkerRequestEnvelope,
    WorkerRequestSchemaError,
    append_audit_event,
    format_utc_timestamp,
    heartbeat_task_lock,
    load_worker_request_envelope,
    prepare_run_root,
    release_task_lock,
    update_audit_record,
)
from enhengclaw.orchestration.worker_test_hooks import WorkerTestHooks, emit_test_stream_output
from enhengclaw.utils.subject_keys import SubjectKey


_HEALTH_CHECK_INTERVAL_SECONDS = 30.0
_DOWNSTREAM_PLACEHOLDER_INTERVAL_SECONDS = 30.0
_CONTROLLED_INTERRUPT_MESSAGE_SNIPPETS = (
    "global execution freeze is active",
    "is expired",
    "no longer active",
    "execution was interrupted",
)


@dataclass(frozen=True, slots=True)
class ShadowIngestionEnvironment:
    binance_api_key: str
    alchemy_api_key: str

    @classmethod
    def from_env(cls) -> ShadowIngestionEnvironment:
        return cls(
            binance_api_key=require_env("BINANCE_API_KEY"),
            alchemy_api_key=require_env("ALCHEMY_API_KEY"),
        )


@dataclass(frozen=True, slots=True)
class ShadowIngestionRequest:
    artifacts_root: str
    providers: tuple[dict[str, Any], ...]
    run_seconds: float | None
    log_level: str
    simulation_profile: str
    synthetic_event_interval_seconds: float
    synthetic_quarantine_every: int
    binance_receive_timeout_seconds: float
    binance_initial_backoff_seconds: float
    binance_max_backoff_seconds: float
    binance_max_reconnect_attempts: int | None
    binance_websocket_url: str
    alchemy_poll_interval_seconds: float
    alchemy_request_timeout_seconds: float
    alchemy_initial_backoff_seconds: float
    alchemy_max_backoff_seconds: float
    alchemy_max_retry_attempts: int | None
    alchemy_degraded_after_failures: int
    disable_eth_get_block_by_number: bool
    alchemy_endpoint_url: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ShadowIngestionRequest:
        raw_providers = payload.get("providers")
        if isinstance(raw_providers, list) and raw_providers:
            providers = tuple(normalize_provider_payload(item) for item in raw_providers)
        else:
            providers = tuple(
                build_legacy_provider_payloads(
                    binance_websocket_url=str(payload.get("binance_websocket_url", "wss://stream.binance.com:9443/ws")),
                    binance_receive_timeout_seconds=float(payload["binance_receive_timeout_seconds"]),
                    binance_initial_backoff_seconds=float(payload["binance_initial_backoff_seconds"]),
                    binance_max_backoff_seconds=float(payload["binance_max_backoff_seconds"]),
                    binance_max_reconnect_attempts=None
                    if payload.get("binance_max_reconnect_attempts") is None
                    else int(payload["binance_max_reconnect_attempts"]),
                    alchemy_poll_interval_seconds=float(payload["alchemy_poll_interval_seconds"]),
                    alchemy_request_timeout_seconds=float(payload["alchemy_request_timeout_seconds"]),
                    alchemy_initial_backoff_seconds=float(payload["alchemy_initial_backoff_seconds"]),
                    alchemy_max_backoff_seconds=float(payload["alchemy_max_backoff_seconds"]),
                    alchemy_max_retry_attempts=None
                    if payload.get("alchemy_max_retry_attempts") is None
                    else int(payload["alchemy_max_retry_attempts"]),
                    alchemy_degraded_after_failures=int(payload["alchemy_degraded_after_failures"]),
                    disable_eth_get_block_by_number=bool(payload.get("disable_eth_get_block_by_number", False)),
                    alchemy_endpoint_url=None
                    if payload.get("alchemy_endpoint_url") in {None, ""}
                    else str(payload["alchemy_endpoint_url"]),
                )
            )
        return cls(
            artifacts_root=str(payload["artifacts_root"]),
            providers=providers,
            run_seconds=None if payload.get("run_seconds") is None else float(payload["run_seconds"]),
            log_level=str(payload.get("log_level", "INFO")),
            simulation_profile=str(payload.get("simulation_profile", "real")),
            synthetic_event_interval_seconds=float(payload.get("synthetic_event_interval_seconds", 1.0)),
            synthetic_quarantine_every=int(payload.get("synthetic_quarantine_every", 10)),
            binance_receive_timeout_seconds=float(payload["binance_receive_timeout_seconds"]),
            binance_initial_backoff_seconds=float(payload["binance_initial_backoff_seconds"]),
            binance_max_backoff_seconds=float(payload["binance_max_backoff_seconds"]),
            binance_max_reconnect_attempts=None
            if payload.get("binance_max_reconnect_attempts") is None
            else int(payload["binance_max_reconnect_attempts"]),
            binance_websocket_url=str(payload.get("binance_websocket_url", "wss://stream.binance.com:9443/ws")),
            alchemy_poll_interval_seconds=float(payload["alchemy_poll_interval_seconds"]),
            alchemy_request_timeout_seconds=float(payload["alchemy_request_timeout_seconds"]),
            alchemy_initial_backoff_seconds=float(payload["alchemy_initial_backoff_seconds"]),
            alchemy_max_backoff_seconds=float(payload["alchemy_max_backoff_seconds"]),
            alchemy_max_retry_attempts=None
            if payload.get("alchemy_max_retry_attempts") is None
            else int(payload["alchemy_max_retry_attempts"]),
            alchemy_degraded_after_failures=int(payload["alchemy_degraded_after_failures"]),
            disable_eth_get_block_by_number=bool(payload.get("disable_eth_get_block_by_number", False)),
            alchemy_endpoint_url=None
            if payload.get("alchemy_endpoint_url") in {None, ""}
            else str(payload["alchemy_endpoint_url"]),
        )


def _build_real_shadow_providers(
    *,
    request: ShadowIngestionRequest,
    replay_writer: LiveReplayWriter,
    quarantine_writer: LiveQuarantineWriter,
    health_monitor: DataHealthMonitor,
    provider_state_root: Path,
) -> tuple[Any, ...]:
    providers: list[Any] = []
    for provider in request.providers:
        kind = provider["kind"]
        if kind == BINANCE_TRADE_PROVIDER_KIND:
            providers.append(
                BinanceTradeShadowProvider(
                    config=BinanceTradeShadowConfig(
                        websocket_url=provider["websocket_url"],
                        symbols=(provider["symbol"],),
                        socket_label=provider["symbol"],
                        receive_timeout_seconds=float(provider["receive_timeout_seconds"]),
                        reconnect_backoff=_build_backoff(
                            initial_delay_seconds=float(provider["initial_backoff_seconds"]),
                            max_delay_seconds=float(provider["max_backoff_seconds"]),
                            max_attempts=provider.get("max_reconnect_attempts"),
                        ),
                    ),
                    replay_writer=replay_writer,
                    quarantine_writer=quarantine_writer,
                    health_monitor=health_monitor,
                    state_root=provider_state_root,
                )
            )
            continue
        if kind == ALCHEMY_EVM_BLOCK_PROVIDER_KIND:
            alchemy_state_root = provider_state_root / "alchemy" / provider["symbol"].lower()
            legacy_checkpoint_path = (
                provider_state_root / "alchemy_block_checkpoint.json"
                if provider["provider_id"] == "alchemy.eth.rpc" and provider["symbol"] == "ETH"
                else None
            )
            providers.append(
                AlchemyEthShadowProvider(
                    config=AlchemyEthShadowConfig(
                        provider_id=provider["provider_id"],
                        symbol=provider["symbol"],
                        subject_key=provider["subject_key"],
                        network=provider["network"],
                        endpoint_url=provider.get("endpoint_url"),
                        poll_interval_seconds=float(provider["poll_interval_seconds"]),
                        request_timeout_seconds=float(provider["request_timeout_seconds"]),
                        include_block_details=bool(provider["include_block_details"]),
                        legacy_checkpoint_path=legacy_checkpoint_path,
                        retry_backoff=_build_backoff(
                            initial_delay_seconds=float(provider["initial_backoff_seconds"]),
                            max_delay_seconds=float(provider["max_backoff_seconds"]),
                            max_attempts=provider.get("max_retry_attempts"),
                        ),
                        degraded_after_failures=int(provider["degraded_after_failures"]),
                    ),
                    replay_writer=replay_writer,
                    quarantine_writer=quarantine_writer,
                    state_root=alchemy_state_root,
                )
            )
            continue
        if kind == ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND:
            providers.append(
                AlchemyBitcoinShadowProvider(
                    config=AlchemyBitcoinShadowConfig(
                        provider_id=provider["provider_id"],
                        symbol=provider["symbol"],
                        subject_key=provider["subject_key"],
                        network=provider["network"],
                        endpoint_url=provider.get("endpoint_url"),
                        poll_interval_seconds=float(provider["poll_interval_seconds"]),
                        request_timeout_seconds=float(provider["request_timeout_seconds"]),
                        include_block_details=bool(provider["include_block_details"]),
                        retry_backoff=_build_backoff(
                            initial_delay_seconds=float(provider["initial_backoff_seconds"]),
                            max_delay_seconds=float(provider["max_backoff_seconds"]),
                            max_attempts=provider.get("max_retry_attempts"),
                        ),
                        degraded_after_failures=int(provider["degraded_after_failures"]),
                    ),
                    replay_writer=replay_writer,
                    quarantine_writer=quarantine_writer,
                    state_root=provider_state_root / "alchemy" / provider["symbol"].lower(),
                )
            )
            continue
        if kind == ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND:
            providers.append(
                AlchemySolanaShadowProvider(
                    config=AlchemySolanaShadowConfig(
                        provider_id=provider["provider_id"],
                        symbol=provider["symbol"],
                        subject_key=provider["subject_key"],
                        network=provider["network"],
                        endpoint_url=provider.get("endpoint_url"),
                        poll_interval_seconds=float(provider["poll_interval_seconds"]),
                        request_timeout_seconds=float(provider["request_timeout_seconds"]),
                        include_block_details=bool(provider["include_block_details"]),
                        commitment=provider["commitment"],
                        encoding=provider["encoding"],
                        transaction_details=provider["transaction_details"],
                        retry_backoff=_build_backoff(
                            initial_delay_seconds=float(provider["initial_backoff_seconds"]),
                            max_delay_seconds=float(provider["max_backoff_seconds"]),
                            max_attempts=provider.get("max_retry_attempts"),
                        ),
                        degraded_after_failures=int(provider["degraded_after_failures"]),
                    ),
                    replay_writer=replay_writer,
                    quarantine_writer=quarantine_writer,
                    state_root=provider_state_root / "alchemy" / provider["symbol"].lower(),
                )
            )
            continue
        raise ValueError(f"unsupported shadow provider kind '{kind}'")
    return tuple(providers)


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    flattened: list[BaseException] = []
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop()
        flattened.append(current)
        nested = getattr(current, "exceptions", None)
        if isinstance(nested, tuple):
            stack.extend(reversed([item for item in nested if isinstance(item, BaseException)]))
        if current.__cause__ is not None:
            stack.append(current.__cause__)
        if current.__context__ is not None and current.__context__ is not current.__cause__:
            stack.append(current.__context__)
    return flattened


def _controlled_interrupt_reason(exc: BaseException) -> str | None:
    for candidate in _iter_exception_chain(exc):
        if isinstance(candidate, KeyboardInterrupt):
            return "keyboard interrupt"
        if isinstance(candidate, ExecutionControlError):
            message = str(candidate).strip()
            normalized = message.lower()
            if any(token in normalized for token in _CONTROLLED_INTERRUPT_MESSAGE_SNIPPETS):
                return message or candidate.__class__.__name__
    return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute live shadow ingestion inside the isolated ingestion worker boundary."
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument(
        "--permit",
        default=None,
        help="Optional path to a signed execution permit JSON file. Falls back to ENHENGCLAW_EXECUTION_PERMIT_PATH.",
    )
    return parser


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )


async def run_shadow_ingestion_worker(
    request: ShadowIngestionRequest,
    *,
    permit_path: Path | None,
    envelope: WorkerRequestEnvelope,
) -> None:
    hooks = WorkerTestHooks.from_env()
    clear_worker_interrupted()
    run_root = prepare_run_root(envelope.audit_root, envelope.run_id)
    task_lock_path = Path(envelope.task_lock_path)
    emit_test_stream_output(hooks)
    append_audit_event(
        run_root,
        "worker.request_loaded",
        component="ingestion_worker",
        request_schema_version=WORKER_REQUEST_SCHEMA_VERSION,
        request_kind=envelope.request_kind,
    )
    update_audit_record(
        run_root,
        status="worker_bootstrap",
        worker_pid=os.getpid(),
        started_at_utc=format_utc_timestamp(utc_now()),
    )
    heartbeat_task_lock(
        task_lock_path,
        controller_pid=envelope.controller_pid,
        worker_pid=os.getpid(),
    )
    lease = None
    stop_event = asyncio.Event()
    status = "completed"
    failure_category = "worker_startup"
    try:
        if hooks.fail_before_permit:
            raise RuntimeError("ingestion worker test hook fail_before_permit")
        permit = load_execution_permit(permit_path)
        append_audit_event(
            run_root,
            "lease.permit_loaded",
            component="ingestion_worker",
            permit_id=permit.permit_id,
        )
        if hooks.fail_after_permit:
            raise RuntimeError("ingestion worker test hook fail_after_permit")
        lease = acquire_execution_lease(
            permit,
            permit_path=permit_path or os.getenv(EXECUTION_PERMIT_PATH_ENV) or "",
            operation="cli.shadow_ingest.run",
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            required_capabilities={CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT},
        )
        os.environ[WORKER_MODE_ENV] = "1"
        os.environ[WORKER_LEASE_ID_ENV] = lease.lease_id
        os.environ[WORKER_PERMIT_PATH_ENV] = lease.permit_path
        append_audit_event(
            run_root,
            "lease.acquired",
            component="ingestion_worker",
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
                component="ingestion_worker",
            )
            os._exit(98)
        if hooks.sleep_after_lease_seconds > 0:
            append_audit_event(
                run_root,
                "worker.test_hook_sleep_after_lease",
                component="ingestion_worker",
                sleep_seconds=hooks.sleep_after_lease_seconds,
            )
            await sleep_or_stop(stop_event, hooks.sleep_after_lease_seconds)

        if request.simulation_profile == "real":
            ShadowIngestionEnvironment.from_env()

        logger = logging.getLogger("ingestion_worker")
        artifacts_root = Path(request.artifacts_root).resolve()
        provider_state_root = artifacts_root / "provider_state"
        health_monitor = DataHealthMonitor()
        health_event_log = HealthEventLog(artifacts_root / "health_events", logger=logger)
        downstream_block_audit_log = DownstreamBlockAuditLog(
            artifacts_root / "downstream_blocks",
            logger=logger,
        )
        health_rules = HealthRules()
        downstream_gate = DownstreamGate(
            monitor=health_monitor,
            rules=health_rules,
            event_log=health_event_log,
        )
        downstream_ingress_guard = DownstreamIngressGuard(
            monitor=health_monitor,
            gate=downstream_gate,
            audit_log=downstream_block_audit_log,
        )

        replay_writer = LiveReplayWriter(
            artifacts_root / "live_replay",
            health_monitor=health_monitor,
        )
        quarantine_writer = LiveQuarantineWriter(artifacts_root / "live_quarantine")
        configured_subjects = provider_subject_keys(list(request.providers))
        logger.info(
            "Starting shadow ingestion into %s for subjects %s (profile=%s)",
            artifacts_root,
            ", ".join(configured_subjects),
            request.simulation_profile,
        )

        async with asyncio.TaskGroup() as task_group:
            if request.simulation_profile == "synthetic":
                task_group.create_task(
                    synthetic_shadow_loop(
                        stop_event,
                        replay_writer=replay_writer,
                        quarantine_writer=quarantine_writer,
                        logger=logger,
                        interval_seconds=request.synthetic_event_interval_seconds,
                        quarantine_every=request.synthetic_quarantine_every,
                        run_root=run_root,
                        providers=request.providers,
                    )
                )
            else:
                real_providers = _build_real_shadow_providers(
                    request=request,
                    replay_writer=replay_writer,
                    quarantine_writer=quarantine_writer,
                    health_monitor=health_monitor,
                    provider_state_root=provider_state_root,
                )
                for provider in real_providers:
                    task_group.create_task(provider.run(stop_event))
            if not hooks.disable_heartbeat:
                task_group.create_task(
                    lease_heartbeat_loop(
                        stop_event,
                        lease=lease,
                        logger=logger,
                        run_root=run_root,
                        task_lock_path=task_lock_path,
                        controller_pid=envelope.controller_pid,
                    )
                )
            task_group.create_task(
                health_check_loop(
                    stop_event,
                    monitor=health_monitor,
                    gate=downstream_gate,
                    logger=logger,
                )
            )
            task_group.create_task(
                downstream_placeholder_loop(
                    stop_event,
                    monitor=health_monitor,
                    guard=downstream_ingress_guard,
                    logger=logger,
                )
            )
            if request.run_seconds is not None:
                task_group.create_task(_stop_after(stop_event, request.run_seconds))
            await stop_event.wait()
        failure_category = None
    except BaseException as exc:
        interruption_reason = get_worker_interrupt_reason() or _controlled_interrupt_reason(exc)
        if interruption_reason is not None and get_worker_interrupt_reason() is None:
            mark_worker_interrupted(interruption_reason)
        status = "interrupted" if interruption_reason is not None else "failed"
        if status == "interrupted":
            failure_category = "lease_interrupted" if lease is not None else "worker_interrupted"
        elif lease is not None:
            failure_category = "worker_failed"
        append_audit_event(
            run_root,
            "worker.interrupted" if status == "interrupted" else "worker.failed",
            component="ingestion_worker",
            error=str(exc),
            interruption_reason=interruption_reason,
        )
        raise
    finally:
        stop_event.set()
        if lease is not None:
            try:
                release_execution_lease(lease, status=status)
                append_audit_event(
                    run_root,
                    "lease.released",
                    component="ingestion_worker",
                    lease_id=lease.lease_id,
                    release_status=status,
                )
            except Exception:
                pass
        release_task_lock(
            task_lock_path,
            status=status,
            failure_category=failure_category,
            extra_fields={
                "worker_pid": os.getpid(),
                "lease_id": None if lease is None else lease.lease_id,
            },
        )
        update_audit_record(
            run_root,
            status=status,
            ended_at_utc=format_utc_timestamp(utc_now()),
            failure_category=failure_category,
            interruption_reason=get_worker_interrupt_reason(),
        )
        os.environ.pop(WORKER_LEASE_ID_ENV, None)
        os.environ.pop(WORKER_PERMIT_PATH_ENV, None)
        os.environ.pop(WORKER_MODE_ENV, None)
        clear_worker_interrupted()


async def _stop_after(stop_event: asyncio.Event, run_seconds: float) -> None:
    await asyncio.sleep(run_seconds)
    stop_event.set()


async def lease_heartbeat_loop(
    stop_event: asyncio.Event,
    *,
    lease,
    logger: logging.Logger | None = None,
    run_root: Path,
    task_lock_path: Path,
    controller_pid: int,
) -> None:
    heartbeat_logger = logger or logging.getLogger("ingestion_worker")
    while not stop_event.is_set():
        await sleep_or_stop(stop_event, WORKER_LEASE_HEARTBEAT_SECONDS)
        if stop_event.is_set():
            return
        try:
            heartbeat_execution_lease(lease)
            require_active_worker_lease(
                operation="cli.shadow_ingest.heartbeat",
                required_capabilities={CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT},
                requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
                allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
            )
            append_audit_event(
                run_root,
                "lease.heartbeat",
                component="ingestion_worker",
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
            heartbeat_logger.error("Shadow ingestion worker lease heartbeat failed: %s", exc)
            append_audit_event(
                run_root,
                "lease.heartbeat_failed",
                component="ingestion_worker",
                lease_id=lease.lease_id,
                error=str(exc),
            )
            stop_event.set()
            raise RuntimeError(f"shadow ingestion execution lease heartbeat failed: {exc}") from exc


async def health_check_loop(
    stop_event: asyncio.Event,
    *,
    monitor: DataHealthMonitor,
    gate: DownstreamGate,
    logger: logging.Logger | None = None,
    interval_seconds: float = _HEALTH_CHECK_INTERVAL_SECONDS,
) -> None:
    health_logger = logger or logging.getLogger("ingestion_worker")
    while not stop_event.is_set():
        for subject_key in monitor.get_all_subject_keys():
            try:
                gate.check(subject_key)
            except DownstreamBlockedError as exc:
                health_logger.warning(
                    "Health check blocked downstream for %s: %s",
                    exc.subject_key.as_stable_string(),
                    exc.reason,
                )
        await sleep_or_stop(stop_event, interval_seconds)


async def downstream_placeholder_loop(
    stop_event: asyncio.Event,
    *,
    monitor: DataHealthMonitor,
    guard: DownstreamIngressGuard,
    logger: logging.Logger | None = None,
    interval_seconds: float = _DOWNSTREAM_PLACEHOLDER_INTERVAL_SECONDS,
) -> None:
    downstream_logger = logger or logging.getLogger("ingestion_worker")
    while not stop_event.is_set():
        for subject_key in monitor.get_all_subject_keys():
            state = monitor.get_state(subject_key)
            if (
                state.latest_ingest_timestamp_utc is None
                and not state.contamination
                and not state.replay_write_failure
            ):
                continue
            try:
                guard.guard_downstream_input(
                    subject_key=subject_key,
                    consumer="workflow.placeholder",
                    payload={"subject_key": subject_key.as_stable_string()},
                )
            except DownstreamBlockedError as exc:
                downstream_logger.warning(
                    "Downstream placeholder rejected %s for %s: %s",
                    exc.consumer,
                    exc.subject_key.as_stable_string(),
                    exc.reason,
                )
        await sleep_or_stop(stop_event, interval_seconds)


def _build_backoff(
    *,
    initial_delay_seconds: float,
    max_delay_seconds: float,
    max_attempts: int | None,
):
    from enhengclaw.infra.shared.backoff import ExponentialBackoffConfig

    return ExponentialBackoffConfig(
        initial_delay_seconds=initial_delay_seconds,
        max_delay_seconds=max_delay_seconds,
        multiplier=2.0,
        max_attempts=max_attempts,
    )


async def synthetic_shadow_loop(
    stop_event: asyncio.Event,
    *,
    replay_writer: LiveReplayWriter,
    quarantine_writer: LiveQuarantineWriter,
    logger: logging.Logger,
    interval_seconds: float,
    quarantine_every: int,
    run_root: Path,
    providers: tuple[dict[str, Any], ...],
) -> None:
    if not providers:
        raise ValueError("synthetic shadow loop requires at least one provider")
    counter = 0
    while not stop_event.is_set():
        try:
            require_active_worker_lease(
                operation="cli.shadow_ingest.synthetic_loop",
                required_capabilities={CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT},
                requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
                allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
            )
        except Exception as exc:
            mark_worker_interrupted(str(exc))
            raise
        counter += 1
        observed_at = utc_now()
        provider = providers[(counter - 1) % len(providers)]
        event = _synthetic_event_for_provider(
            provider=provider,
            counter=counter,
            observed_at=observed_at,
        )
        replay_writer.write(event=event)
        append_audit_event(
            run_root,
            "synthetic.event_written",
            component="ingestion_worker",
            subject_key=event.subject_key.as_stable_string(),
            event_id=event.event_id,
            event_type=event.event_type,
        )
        if quarantine_every > 0 and counter % quarantine_every == 0:
            quarantine_provider = providers[0]
            quarantine_subject_key = SubjectKey.build(
                symbol=quarantine_provider["symbol"],
                venue="binance" if quarantine_provider["kind"] == BINANCE_TRADE_PROVIDER_KIND else "alchemy",
                instrument_type="spot" if quarantine_provider["kind"] == BINANCE_TRADE_PROVIDER_KIND else "onchain",
            )
            quarantine_writer.write(
                subject_key=quarantine_subject_key,
                provider_id=quarantine_provider["provider_id"],
                event_type=_synthetic_event_type(quarantine_provider),
                raw_payload={"provider": quarantine_provider["subject_key"], "sequence": counter},
                reason="synthetic quarantine probe",
                schema_version=SHADOW_SCHEMA_VERSION,
            )
            append_audit_event(
                run_root,
                "synthetic.quarantine_written",
                component="ingestion_worker",
                subject_key=quarantine_subject_key.as_stable_string(),
                event_type=_synthetic_event_type(quarantine_provider),
            )
            logger.warning("Synthetic shadow loop wrote quarantine probe at event %s", counter)
        await sleep_or_stop(stop_event, interval_seconds)


def _synthetic_event_for_provider(
    *,
    provider: dict[str, Any],
    counter: int,
    observed_at,
) -> ValidatedShadowEvent:
    kind = provider["kind"]
    subject_key = SubjectKey.build(
        symbol=provider["symbol"],
        venue="binance" if kind == BINANCE_TRADE_PROVIDER_KIND else "alchemy",
        instrument_type="spot" if kind == BINANCE_TRADE_PROVIDER_KIND else "onchain",
    )
    if kind == BINANCE_TRADE_PROVIDER_KIND:
        return ValidatedShadowEvent(
            subject_key=subject_key,
            provider_id=provider["provider_id"],
            event_type="trade",
            source_timestamp=isoformat_utc(observed_at),
            raw_payload={
                "stream": f"{provider['symbol'].lower()}@trade",
                "data": {
                    "e": "trade",
                    "E": int(observed_at.timestamp() * 1000),
                    "s": provider["symbol"],
                    "t": counter,
                    "p": "68000.00" if provider["symbol"] == "BTCUSDT" else "3500.00",
                    "q": "0.0100" if provider["symbol"] == "BTCUSDT" else "0.1000",
                },
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"synthetic-{provider['symbol'].lower()}-{counter}",
        )
    if kind == ALCHEMY_EVM_BLOCK_PROVIDER_KIND:
        return ValidatedShadowEvent(
            subject_key=subject_key,
            provider_id=provider["provider_id"],
            event_type="eth_blockNumber",
            source_timestamp=None,
            raw_payload={
                "method": "eth_blockNumber",
                "response": {
                    "jsonrpc": "2.0",
                    "id": counter,
                    "result": hex(counter),
                },
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"synthetic-{provider['symbol'].lower()}-block-{counter}",
        )
    if kind == ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND:
        return ValidatedShadowEvent(
            subject_key=subject_key,
            provider_id=provider["provider_id"],
            event_type="getblockcount",
            source_timestamp=None,
            raw_payload={
                "method": "getblockcount",
                "response": {
                    "jsonrpc": "2.0",
                    "id": counter,
                    "result": counter,
                },
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"synthetic-{provider['symbol'].lower()}-height-{counter}",
        )
    if kind == ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND:
        return ValidatedShadowEvent(
            subject_key=subject_key,
            provider_id=provider["provider_id"],
            event_type="getSlot",
            source_timestamp=None,
            raw_payload={
                "method": "getSlot",
                "response": {
                    "jsonrpc": "2.0",
                    "id": counter,
                    "result": counter,
                },
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"synthetic-{provider['symbol'].lower()}-slot-{counter}",
        )
    raise ValueError(f"unsupported synthetic provider kind '{kind}'")


def _synthetic_event_type(provider: dict[str, Any]) -> str:
    if provider["kind"] == BINANCE_TRADE_PROVIDER_KIND:
        return "trade"
    if provider["kind"] == ALCHEMY_EVM_BLOCK_PROVIDER_KIND:
        return "eth_blockNumber"
    if provider["kind"] == ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND:
        return "getblockcount"
    if provider["kind"] == ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND:
        return "getSlot"
    raise ValueError(f"unsupported synthetic provider kind '{provider['kind']}'")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    permit_path = None if args.permit is None else Path(args.permit).resolve()
    request_path = args.request.resolve()
    try:
        envelope = load_worker_request_envelope(request_path, expected_kind="ingestion")
        request = ShadowIngestionRequest.from_payload(envelope.payload)
        configure_logging(request.log_level)
        asyncio.run(
            run_shadow_ingestion_worker(
                request,
                permit_path=permit_path,
                envelope=envelope,
            )
        )
    except WorkerRequestSchemaError:
        configure_logging("INFO")
        traceback.print_exc(file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        logging.getLogger("ingestion_worker").info("Shadow ingestion worker stopped by operator")
        return 130
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
