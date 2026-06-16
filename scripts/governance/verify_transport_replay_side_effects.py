from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
OUTPUT_ROOT = REPO_ROOT / "artifacts" / "runtime_evidence" / "day3" / "transport_replay_side_effects"
PYTHON = sys.executable


class TrackingReplayWriter:
    def __init__(self, root: Path, phase: Callable[[], str], on_write: Callable[[], None] | None = None) -> None:
        from enhengclaw.ingress.live_replay_writer import LiveReplayWriter

        self.root = root
        self.phase = phase
        self.on_write = on_write
        self.inner = LiveReplayWriter(root)
        self.writes: list[dict[str, Any]] = []

    def write(self, *, event: Any) -> Any:
        before = count_jsonl(self.root)
        current_phase = self.phase()
        result = self.inner.write(event=event)
        after = count_jsonl(self.root)
        self.writes.append(
            {
                "phase": current_phase,
                "provider_id": event.provider_id,
                "event_type": event.event_type,
                "event_id": event.event_id,
                "replay_count_before_write": before,
                "replay_count_after_write": after,
            }
        )
        if self.on_write is not None:
            self.on_write()
        return result


def main() -> int:
    sys.path.insert(0, str(SRC_ROOT))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary = {
        "cases": [
            run_alchemy_http_400(),
            run_alchemy_http_429(),
            run_binance_receive_timeout_reconnect(),
        ]
    }
    summary["governance_summary"] = summarize_governance(summary["cases"])
    write_json(OUTPUT_ROOT / "transport_replay_side_effects_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def run_alchemy_http_400() -> dict[str, Any]:
    return run_alchemy_case(
        case_id="alchemy_http_400",
        http_code=400,
        expected_write_phases=set(),
        expected_observed_classification="fatal_no_retry_no_replay",
    )


def run_alchemy_http_429() -> dict[str, Any]:
    return run_alchemy_case(
        case_id="alchemy_http_429",
        http_code=429,
        expected_write_phases={"recovered_success_response"},
        expected_observed_classification="retryable_recovered_write_after_success",
    )


def run_alchemy_case(
    *,
    case_id: str,
    http_code: int,
    expected_write_phases: set[str],
    expected_observed_classification: str,
) -> dict[str, Any]:
    from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter
    from enhengclaw.providers import alchemy_shadow_provider as alchemy_mod
    from enhengclaw.providers.alchemy_shadow_provider import AlchemyEthShadowConfig, AlchemyEthShadowProvider
    from enhengclaw.providers.shadow_common import ExponentialBackoffConfig, FatalTransportError

    run_root = prepare_run_root(OUTPUT_ROOT / case_id)
    artifacts_root = run_root / "artifacts"
    stdout_log, stderr_log = log_paths(run_root)
    stdout_log.write_text("", encoding="utf-8")
    phase_state = {"value": "initial"}
    checkpoints: list[dict[str, Any]] = []
    replay_root = artifacts_root / "live_replay"
    replay_writer = TrackingReplayWriter(replay_root, lambda: phase_state["value"])
    logger, handler = file_logger(f"transport_side_effects.{case_id}", stderr_log)
    os.environ["ALCHEMY_API_KEY"] = "side-effect-alchemy-sentinel"
    write_case_config(run_root, artifacts_root, case_id, "transport_replay_side_effects")

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
        if http_code == 429 and calls["count"] == 1:
            phase_state["value"] = "retryable_failure_before_retry"
            checkpoints.append({"phase": phase_state["value"], "replay_count": count_jsonl(replay_root)})
            raise urllib_error.HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"rate limit"}'),
            )
        if http_code == 400:
            phase_state["value"] = "fatal_failure"
            checkpoints.append({"phase": phase_state["value"], "replay_count": count_jsonl(replay_root)})
            raise urllib_error.HTTPError(
                req.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"bad request"}'),
            )
        phase_state["value"] = "recovered_success_response"
        checkpoints.append({"phase": phase_state["value"], "replay_count": count_jsonl(replay_root)})
        payload = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"jsonrpc": "2.0", "id": payload["id"], "result": "0x1"})

    config = AlchemyEthShadowConfig(
        retry_backoff=ExponentialBackoffConfig(
            initial_delay_seconds=0.1,
            max_delay_seconds=1.0,
            multiplier=2.0,
            max_attempts=2,
        ),
        include_block_details=False,
    )
    provider = AlchemyEthShadowProvider(
        config=config,
        replay_writer=replay_writer,  # type: ignore[arg-type]
        quarantine_writer=LiveQuarantineWriter(artifacts_root / "live_quarantine"),
        logger=logger,
    )
    replay_write_count_before = count_jsonl(replay_root)
    exit_code = 0
    observed_classification = expected_observed_classification
    alchemy_mod.urllib_request.urlopen = fake_urlopen
    try:
        try:
            asyncio.run(provider.poll_once())
            if http_code == 400:
                observed_classification = "unexpected_success"
                exit_code = 1
            logger.info("Case %s completed classification=%s", case_id, observed_classification)
        except FatalTransportError as exc:
            if http_code == 400:
                observed_classification = "fatal_no_retry_no_replay"
                logger.error("Case %s observed fatal transport error without replay write: %s", case_id, exc)
            else:
                observed_classification = f"unexpected_fatal:{exc}"
                exit_code = 1
    except Exception as exc:
        observed_classification = f"unexpected_exception:{type(exc).__name__}"
        logger.exception("Case %s failed unexpectedly", case_id)
        exit_code = 1
    finally:
        alchemy_mod.urllib_request.urlopen = original_urlopen
        logger.removeHandler(handler)
        handler.close()

    replay_write_count_after = count_jsonl(replay_root)
    write_exit_status(run_root, exit_code)
    write_watchdog(run_root, exit_code, reason=f"{case_id}_side_effect_validation_completed")
    collector = run_collector(run_root)
    error_write_count = sum(1 for item in replay_writer.writes if item["phase"] not in expected_write_phases)
    result = {
        "case_id": case_id,
        "exit_code": exit_code,
        "http_code": http_code,
        "urlopen_call_count": calls["count"],
        "replay_write_count_before": replay_write_count_before,
        "replay_write_count_after": replay_write_count_after,
        "replay_writes": replay_writer.writes,
        "checkpoints": checkpoints,
        "error_replay_exists": error_write_count > 0,
        "retry_during_error_replay_write_count": sum(
            1 for item in replay_writer.writes if item["phase"] == "retryable_failure_before_retry"
        ),
        "observed_classification": observed_classification,
        "collector_classification": collector["classifications"],
        "collector_status": collector["status"],
        "collector_infrastructure_errors": collector["infrastructure_errors"],
        "retry_count": collector["metrics"]["retry"]["alchemy_retry_count"],
        "delay_sequence": collector["metrics"]["retry"]["delay_sequence"],
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "side_effect_summary.json", result)
    return result


def run_binance_receive_timeout_reconnect() -> dict[str, Any]:
    from enhengclaw.health.data_health_monitor import DataHealthMonitor
    from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter
    from enhengclaw.providers.binance_shadow_provider import BinanceTradeShadowConfig, BinanceTradeShadowProvider
    from enhengclaw.providers.shadow_common import ExponentialBackoffConfig

    case_id = "binance_receive_timeout_reconnect"
    run_root = prepare_run_root(OUTPUT_ROOT / case_id)
    artifacts_root = run_root / "artifacts"
    stdout_log, stderr_log = log_paths(run_root)
    stdout_log.write_text("", encoding="utf-8")
    phase_state = {"value": "initial"}
    checkpoints: list[dict[str, Any]] = []
    replay_root = artifacts_root / "live_replay"
    stop_event_holder: dict[str, asyncio.Event] = {}
    replay_writer = TrackingReplayWriter(
        replay_root,
        lambda: phase_state["value"],
        on_write=lambda: stop_event_holder["stop_event"].set(),
    )
    logger, handler = file_logger(f"transport_side_effects.{case_id}", stderr_log)
    os.environ["BINANCE_API_KEY"] = "side-effect-binance-sentinel"
    write_case_config(run_root, artifacts_root, case_id, "transport_replay_side_effects")

    session_count = {"value": 0}
    recv_count = {"value": 0}

    class FakeWebSocket:
        def __init__(self, session_id: int) -> None:
            self.session_id = session_id

        async def __aenter__(self) -> FakeWebSocket:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        async def send(self, payload: str) -> None:
            return None

        async def recv(self) -> str:
            recv_count["value"] += 1
            if self.session_id == 1:
                phase_state["value"] = "reconnect_failure"
                checkpoints.append({"phase": phase_state["value"], "replay_count": count_jsonl(replay_root)})
                raise asyncio.TimeoutError()
            phase_state["value"] = "recovered_message"
            checkpoints.append({"phase": phase_state["value"], "replay_count": count_jsonl(replay_root)})
            return json.dumps(
                {
                    "stream": "btcusdt@trade",
                    "data": {
                        "e": "trade",
                        "E": 1712534400000,
                        "s": "BTCUSDT",
                        "t": 123456,
                        "p": "68750.10",
                        "q": "0.005",
                        "T": 1712534400001,
                    },
                },
                separators=(",", ":"),
            )

    def websocket_connect(*args: Any, **kwargs: Any) -> FakeWebSocket:
        session_count["value"] += 1
        return FakeWebSocket(session_count["value"])

    async def run_case() -> None:
        stop_event = asyncio.Event()
        stop_event_holder["stop_event"] = stop_event
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
            replay_writer=replay_writer,  # type: ignore[arg-type]
            quarantine_writer=LiveQuarantineWriter(artifacts_root / "live_quarantine"),
            health_monitor=DataHealthMonitor(),
            logger=logger,
            websocket_connect=websocket_connect,
        )
        await asyncio.wait_for(provider.run(stop_event), timeout=3.0)

    replay_write_count_before = count_jsonl(replay_root)
    exit_code = 0
    observed_classification = "receive_timeout_reconnect_recovered_write"
    try:
        asyncio.run(run_case())
        logger.info("Case %s completed classification=%s", case_id, observed_classification)
    except Exception as exc:
        observed_classification = f"unexpected_exception:{type(exc).__name__}"
        logger.exception("Case %s failed unexpectedly", case_id)
        exit_code = 1
    finally:
        logger.removeHandler(handler)
        handler.close()

    replay_write_count_after = count_jsonl(replay_root)
    write_exit_status(run_root, exit_code)
    write_watchdog(run_root, exit_code, reason=f"{case_id}_side_effect_validation_completed")
    collector = run_collector(run_root)
    error_write_count = sum(1 for item in replay_writer.writes if item["phase"] != "recovered_message")
    result = {
        "case_id": case_id,
        "exit_code": exit_code,
        "session_count": session_count["value"],
        "recv_count": recv_count["value"],
        "replay_write_count_before": replay_write_count_before,
        "replay_write_count_after": replay_write_count_after,
        "replay_writes": replay_writer.writes,
        "checkpoints": checkpoints,
        "error_replay_exists": error_write_count > 0,
        "reconnect_during_error_replay_write_count": sum(
            1 for item in replay_writer.writes if item["phase"] == "reconnect_failure"
        ),
        "observed_classification": observed_classification,
        "collector_classification": collector["classifications"],
        "collector_status": collector["status"],
        "collector_infrastructure_errors": collector["infrastructure_errors"],
        "retry_count": collector["metrics"]["retry"]["binance_reconnect_count"],
        "delay_sequence": collector["metrics"]["retry"]["delay_sequence"],
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "side_effect_summary.json", result)
    return result


def summarize_governance(cases: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [
        case["case_id"]
        for case in cases
        if case["exit_code"] != 0
        or case["error_replay_exists"]
        or case["collector_infrastructure_errors"]
    ]
    return {
        "errors_transport_status": "eligible_for_owner_review" if not failed else "blocked",
        "replay_pollution_risk_detected": bool(failed),
        "blocking_cases": failed,
        "reason": (
            "fatal, retryable, and reconnect side-effect cases produced no error-phase replay writes"
            if not failed
            else "one or more side-effect cases failed or produced error-phase replay writes"
        ),
    }


def write_case_config(run_root: Path, artifacts_root: Path, case_id: str, kind: str) -> None:
    stdout_log, stderr_log = log_paths(run_root)
    write_json(
        run_root / "run_config.json",
        {
            "launched_at_utc": utc_now(),
            "repo_root": str(REPO_ROOT),
            "artifacts_root": str(artifacts_root.resolve()),
            "run_root": str(run_root.resolve()),
            "command": "python-inline-transport-side-effect-harness",
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
    return run_root


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


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
