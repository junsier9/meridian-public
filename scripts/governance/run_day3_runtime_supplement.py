from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SUPPLEMENT_ROOT = REPO_ROOT / "artifacts" / "runtime_evidence" / "day3" / "supplement"
PYTHON = sys.executable


def main() -> int:
    sys.path.insert(0, str(SRC_ROOT))
    SUPPLEMENT_ROOT.mkdir(parents=True, exist_ok=True)
    summary = {
        "async_sleep": run_async_sleep_harness(),
        "transport_retry": [
            run_alchemy_consecutive_retryable(),
            run_binance_receive_timeout_reconnect(),
        ],
    }
    write_json(SUPPLEMENT_ROOT / "supplement_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def run_async_sleep_harness() -> dict[str, Any]:
    from enhengclaw.providers.shadow_common import sleep_or_stop

    run_root = SUPPLEMENT_ROOT / "async_sleep" / "isolated_harness"
    prepare_run_root(run_root)

    async def measure_stop_latency() -> float:
        stop_event = asyncio.Event()
        task = asyncio.create_task(sleep_or_stop(stop_event, 30.0))
        await asyncio.sleep(0.1)
        set_at = time.perf_counter()
        stop_event.set()
        await task
        return time.perf_counter() - set_at

    async def measure_interval_loop() -> list[float]:
        stop_event = asyncio.Event()
        ticks: list[float] = []
        interval_seconds = 0.1
        for _ in range(8):
            ticks.append(time.perf_counter())
            await sleep_or_stop(stop_event, interval_seconds)
        return [right - left for left, right in zip(ticks, ticks[1:], strict=False)]

    graceful_stop_latency_seconds = asyncio.run(measure_stop_latency())
    intervals = asyncio.run(measure_interval_loop())
    interval_stats = interval_summary(intervals)
    busy_loop_indicator_count = sum(1 for value in intervals if value < 0.01)
    expected_interval_seconds = 0.1
    drift_values = [value - expected_interval_seconds for value in intervals]
    drift_stats = interval_summary(drift_values)
    summary = {
        "case_id": "isolated_async_sleep_harness",
        "status": "passed" if graceful_stop_latency_seconds < 1.0 and busy_loop_indicator_count == 0 else "failed",
        "graceful_stop_latency_seconds": graceful_stop_latency_seconds,
        "expected_loop_interval_seconds": expected_interval_seconds,
        "observed_loop_interval_stats": interval_stats,
        "observed_loop_drift_stats": drift_stats,
        "busy_loop_indicator_count": busy_loop_indicator_count,
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "async_sleep_summary.json", summary)
    return summary


def run_alchemy_consecutive_retryable() -> dict[str, Any]:
    from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
    from enhengclaw.providers import alchemy_shadow_provider as alchemy_mod
    from enhengclaw.providers.alchemy_shadow_provider import AlchemyEthShadowConfig, AlchemyEthShadowProvider
    from enhengclaw.providers.shadow_common import ExponentialBackoffConfig

    case_id = "alchemy_consecutive_retryable"
    run_root = SUPPLEMENT_ROOT / "transport_retry" / case_id
    artifacts_root = prepare_run_root(run_root)
    stdout_log, stderr_log = log_paths(run_root)
    write_case_config(run_root, artifacts_root, case_id, "alchemy_consecutive_retryable")
    stdout_log.write_text("", encoding="utf-8")

    os.environ["ALCHEMY_API_KEY"] = "supplement-alchemy-sentinel"
    logger, handler = file_logger(f"transport.{case_id}", stderr_log)
    original_urlopen = alchemy_mod.urllib_request.urlopen
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(req: Any, timeout: float = 0) -> FakeResponse:
        calls["count"] += 1
        if calls["count"] <= 2:
            raise urllib_error.HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"rate limit"}'),
            )
        payload = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"jsonrpc": "2.0", "id": payload["id"], "result": "0x1"})

    config = AlchemyEthShadowConfig(
        retry_backoff=ExponentialBackoffConfig(
            initial_delay_seconds=0.1,
            max_delay_seconds=1.0,
            multiplier=2.0,
            max_attempts=3,
        ),
        include_block_details=False,
    )
    provider = AlchemyEthShadowProvider(
        config=config,
        replay_writer=LiveReplayWriter(artifacts_root / "live_replay"),
        quarantine_writer=LiveQuarantineWriter(artifacts_root / "live_quarantine"),
        logger=logger,
    )
    alchemy_mod.urllib_request.urlopen = fake_urlopen
    exit_code = 0
    observed_classification = "retryable_recovered_after_consecutive_failures"
    try:
        asyncio.run(provider.poll_once())
        logger.info("Transport supplement case %s completed classification=%s", case_id, observed_classification)
    except Exception as exc:
        exit_code = 1
        observed_classification = f"unexpected_exception:{type(exc).__name__}"
        logger.exception("Transport supplement case %s failed unexpectedly", case_id)
    finally:
        alchemy_mod.urllib_request.urlopen = original_urlopen
        logger.removeHandler(handler)
        handler.close()

    write_exit_status(run_root, exit_code)
    write_watchdog(run_root, exit_code, reason="alchemy_consecutive_retryable_completed")
    collector = run_collector(run_root)
    summary = {
        "case_id": case_id,
        "exit_code": exit_code,
        "observed_classification": observed_classification,
        "urlopen_call_count": calls["count"],
        "retry_count": collector["metrics"]["retry"]["alchemy_retry_count"],
        "delay_sequence": collector["metrics"]["retry"]["delay_sequence"],
        "collector_classification": collector["classifications"],
        "collector_status": collector["status"],
        "collector_infrastructure_errors": collector["infrastructure_errors"],
        "live_replay_write_count": count_jsonl(artifacts_root / "live_replay"),
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "transport_case_summary.json", summary)
    return summary


def run_binance_receive_timeout_reconnect() -> dict[str, Any]:
    from enhengclaw.health.data_health_monitor import DataHealthMonitor
    from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
    from enhengclaw.providers.binance_shadow_provider import BinanceTradeShadowConfig, BinanceTradeShadowProvider
    from enhengclaw.providers.shadow_common import ExponentialBackoffConfig

    case_id = "binance_receive_timeout_reconnect"
    run_root = SUPPLEMENT_ROOT / "transport_retry" / case_id
    artifacts_root = prepare_run_root(run_root)
    stdout_log, stderr_log = log_paths(run_root)
    write_case_config(run_root, artifacts_root, case_id, "binance_receive_timeout_reconnect")
    stdout_log.write_text("", encoding="utf-8")

    os.environ["BINANCE_API_KEY"] = "supplement-binance-sentinel"
    logger, handler = file_logger(f"transport.{case_id}", stderr_log)
    recv_attempts = {"count": 0}

    class FakeWebSocket:
        async def __aenter__(self) -> FakeWebSocket:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        async def send(self, payload: str) -> None:
            return None

        async def recv(self) -> str:
            recv_attempts["count"] += 1
            raise asyncio.TimeoutError()

    def websocket_connect(*args: Any, **kwargs: Any) -> FakeWebSocket:
        return FakeWebSocket()

    async def run_case() -> None:
        stop_event = asyncio.Event()
        config = BinanceTradeShadowConfig(
            receive_timeout_seconds=0.05,
            reconnect_backoff=ExponentialBackoffConfig(
                initial_delay_seconds=0.1,
                max_delay_seconds=1.0,
                multiplier=2.0,
                max_attempts=None,
            ),
        )
        provider = BinanceTradeShadowProvider(
            config=config,
            replay_writer=LiveReplayWriter(artifacts_root / "live_replay"),
            quarantine_writer=LiveQuarantineWriter(artifacts_root / "live_quarantine"),
            health_monitor=DataHealthMonitor(),
            logger=logger,
            websocket_connect=websocket_connect,
        )
        task = asyncio.create_task(provider.run(stop_event))
        await asyncio.sleep(0.45)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2.0)

    exit_code = 0
    observed_classification = "receive_timeout_reconnect_path_observed"
    try:
        asyncio.run(run_case())
        logger.info("Transport supplement case %s completed classification=%s", case_id, observed_classification)
    except Exception as exc:
        exit_code = 1
        observed_classification = f"unexpected_exception:{type(exc).__name__}"
        logger.exception("Transport supplement case %s failed unexpectedly", case_id)
    finally:
        logger.removeHandler(handler)
        handler.close()

    write_exit_status(run_root, exit_code)
    write_watchdog(run_root, exit_code, reason="binance_receive_timeout_reconnect_completed")
    collector = run_collector(run_root)
    summary = {
        "case_id": case_id,
        "exit_code": exit_code,
        "observed_classification": observed_classification,
        "recv_attempt_count": recv_attempts["count"],
        "retry_count": collector["metrics"]["retry"]["binance_reconnect_count"],
        "delay_sequence": collector["metrics"]["retry"]["delay_sequence"],
        "collector_classification": collector["classifications"],
        "collector_status": collector["status"],
        "collector_infrastructure_errors": collector["infrastructure_errors"],
        "live_replay_write_count": count_jsonl(artifacts_root / "live_replay"),
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "transport_case_summary.json", summary)
    return summary


def write_case_config(run_root: Path, artifacts_root: Path, case_id: str, kind: str) -> None:
    stdout_log, stderr_log = log_paths(run_root)
    write_json(
        run_root / "run_config.json",
        {
            "launched_at_utc": utc_now(),
            "repo_root": str(REPO_ROOT),
            "artifacts_root": str(artifacts_root.resolve()),
            "run_root": str(run_root.resolve()),
            "command": "python-inline-runtime-supplement-harness",
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
            "case_id": case_id,
            "fault_injection": {"enabled": True, "type": kind},
        },
    )


def write_exit_status(run_root: Path, exit_code: int) -> None:
    stdout_log, stderr_log = log_paths(run_root)
    run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
    write_json(
        run_root / "exit_status.json",
        {
            "started_at_utc": run_config.get("launched_at_utc"),
            "ended_at_utc": utc_now(),
            "exit_code": exit_code,
            "process_id": None,
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
        },
    )


def run_collector(run_root: Path) -> dict[str, Any]:
    output = run_root / "collector_output.json"
    result = subprocess.run(
        [
            PYTHON,
            "scripts/governance/collect_runtime_evidence.py",
            "--run-root",
            str(run_root),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    collector = json.loads(output.read_text(encoding="utf-8"))
    collector["collector_process"] = {"exit_code": result.returncode, "stderr": result.stderr}
    write_json(output, collector)
    return collector


def prepare_run_root(run_root: Path) -> Path:
    if run_root.exists():
        shutil.rmtree(run_root)
    artifacts_root = run_root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    return artifacts_root


def file_logger(name: str, stderr_log: Path) -> tuple[logging.Logger, logging.Handler]:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(stderr_log, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(handler)
    return logger, handler


def log_paths(run_root: Path) -> tuple[Path, Path]:
    return run_root / "shadow_ingest.stdout.log", run_root / "shadow_ingest.stderr.log"


def write_watchdog(run_root: Path, exit_code: int, *, reason: str) -> None:
    events = run_root / "watchdog_events.jsonl"
    append_jsonl(
        events,
        {
            "generated_at_utc": utc_now(),
            "severity": "P3" if exit_code == 0 else "P0",
            "segment_id": run_root.name,
            "check_name": "process_liveness",
            "action": "observe" if exit_code == 0 else "fail",
            "reason": reason,
            "metrics": {"exit_code": exit_code, "restart_enabled": False},
            "process_id": None,
        },
    )
    write_json(
        run_root / "watchdog_summary.json",
        {
            "generated_at_utc": utc_now(),
            "enabled": True,
            "restart_enabled": False,
            "p0_count": 0 if exit_code == 0 else 1,
            "p1_count": 0,
            "p2_count": 0,
            "p3_count": 1 if exit_code == 0 else 0,
            "events_path": str(events.resolve()),
        },
    )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")


def count_jsonl(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*.jsonl"):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            total += sum(1 for line in handle if line.strip())
    return total


def interval_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "count": len(values),
        "min": min(values),
        "p50": statistics.median(values),
        "p95": ordered[p95_index],
        "max": max(values),
    }


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
