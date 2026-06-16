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
from typing import Any
from urllib import error as urllib_error


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
PHASE2_ROOT = REPO_ROOT / "artifacts" / "runtime_evidence" / "day3" / "phase2"
PYTHON = sys.executable


def main() -> int:
    PHASE2_ROOT.mkdir(parents=True, exist_ok=True)
    summary = {
        "env_fail_fast": [
            run_env_case("missing_binance", "missing_binance"),
            run_env_case("missing_alchemy", "missing_alchemy"),
            run_env_case("blank_binance", "blank_binance"),
            run_env_case("blank_alchemy", "blank_alchemy"),
        ],
        "transport_injection": [
            run_transport_case("alchemy_http_429", 429),
            run_transport_case("alchemy_http_400", 400),
        ],
    }
    write_json(PHASE2_ROOT / "phase2_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def run_env_case(case_id: str, mutation: str) -> dict[str, Any]:
    run_root = PHASE2_ROOT / "env_fail_fast" / case_id
    artifacts_root = prepare_run_root(run_root)
    stdout_log = run_root / "shadow_ingest.stdout.log"
    stderr_log = run_root / "shadow_ingest.stderr.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    sentinel_values: list[str] = []
    sentinel_binance = "phase2-binance-sentinel"
    sentinel_alchemy = "phase2-alchemy-sentinel"
    if mutation == "missing_binance":
        env.pop("BINANCE_API_KEY", None)
        env["ALCHEMY_API_KEY"] = sentinel_alchemy
        sentinel_values.append(sentinel_alchemy)
    elif mutation == "missing_alchemy":
        env["BINANCE_API_KEY"] = sentinel_binance
        env.pop("ALCHEMY_API_KEY", None)
        sentinel_values.append(sentinel_binance)
    elif mutation == "blank_binance":
        env["BINANCE_API_KEY"] = ""
        env["ALCHEMY_API_KEY"] = sentinel_alchemy
        sentinel_values.append(sentinel_alchemy)
    elif mutation == "blank_alchemy":
        env["BINANCE_API_KEY"] = sentinel_binance
        env["ALCHEMY_API_KEY"] = ""
        sentinel_values.append(sentinel_binance)
    else:
        raise ValueError(mutation)

    command = [
        PYTHON,
        "-m",
        "enhengclaw.orchestration.shadow_ingestion_runner",
        "--artifacts-root",
        str(artifacts_root),
        "--run-seconds",
        "30",
        "--log-level",
        "INFO",
    ]
    started = utc_now()
    write_json(
        run_root / "run_config.json",
        {
            "launched_at_utc": started,
            "repo_root": str(REPO_ROOT),
            "artifacts_root": str(artifacts_root.resolve()),
            "run_root": str(run_root.resolve()),
            "command": " ".join(command),
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
            "case_id": case_id,
            "fault_injection": {"enabled": True, "type": "env_fail_fast", "mutation": mutation},
        },
    )
    with stdout_log.open("w", encoding="utf-8") as out, stderr_log.open("w", encoding="utf-8") as err:
        result = subprocess.run(command, cwd=REPO_ROOT, env=env, stdout=out, stderr=err, text=True, timeout=60)
    ended = utc_now()
    write_json(
        run_root / "exit_status.json",
        {
            "started_at_utc": started,
            "ended_at_utc": ended,
            "exit_code": result.returncode,
            "process_id": None,
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
        },
    )
    write_watchdog(run_root, 0, reason="env_fail_fast_case_completed")
    collector = run_collector(run_root)
    combined_logs = read_text(stdout_log) + "\n" + read_text(stderr_log)
    summary = {
        "case_id": case_id,
        "exit_code": result.returncode,
        "live_replay_write_count": count_jsonl(artifacts_root / "live_replay"),
        "secret_leak_count": secret_leak_count(combined_logs, sentinel_values),
        "runtime_start_marker_count": combined_logs.count("Starting shadow ingestion into"),
        "collector_status": collector["status"],
        "collector_classifications": collector["classifications"],
        "collector_infrastructure_errors": collector["infrastructure_errors"],
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "env_case_summary.json", summary)
    return summary


def run_transport_case(case_id: str, http_code: int) -> dict[str, Any]:
    run_root = PHASE2_ROOT / "transport_injection" / case_id
    artifacts_root = prepare_run_root(run_root)
    stdout_log = run_root / "shadow_ingest.stdout.log"
    stderr_log = run_root / "shadow_ingest.stderr.log"
    stdout_log.write_text("", encoding="utf-8")
    started = utc_now()
    write_json(
        run_root / "run_config.json",
        {
            "launched_at_utc": started,
            "repo_root": str(REPO_ROOT),
            "artifacts_root": str(artifacts_root.resolve()),
            "run_root": str(run_root.resolve()),
            "command": "python-inline-transport-harness",
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
            "case_id": case_id,
            "fault_injection": {"enabled": True, "type": "transport", "http_code": http_code},
        },
    )

    sys.path.insert(0, str(SRC_ROOT))
    from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
    from enhengclaw.providers import alchemy_shadow_provider as alchemy_mod
    from enhengclaw.providers.alchemy_shadow_provider import AlchemyEthShadowConfig, AlchemyEthShadowProvider
    from enhengclaw.providers.shadow_common import ExponentialBackoffConfig, FatalTransportError

    os.environ["ALCHEMY_API_KEY"] = "phase2-alchemy-sentinel"
    logger = logging.getLogger(f"transport.{case_id}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(stderr_log, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(handler)

    original_urlopen = alchemy_mod.urllib_request.urlopen
    calls = {"count": 0}
    observed_classification = None
    expected_classification = "retryable" if http_code == 429 else "fatal"

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
            raise urllib_error.HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"rate limit"}'),
            )
        if http_code == 400:
            raise urllib_error.HTTPError(
                req.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"bad request"}'),
            )
        payload = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"jsonrpc": "2.0", "id": payload["id"], "result": "0x1"})

    config = AlchemyEthShadowConfig(
        retry_backoff=ExponentialBackoffConfig(
            initial_delay_seconds=1.0,
            max_delay_seconds=2.0,
            multiplier=2.0,
            max_attempts=2,
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
    try:
        try:
            asyncio.run(provider.poll_once())
            observed_classification = "retryable_recovered" if http_code == 429 else "unexpected_success"
            logger.info("Transport injection case %s completed classification=%s", case_id, observed_classification)
        except FatalTransportError as exc:
            observed_classification = "fatal_no_retry"
            logger.error("Transport injection case %s observed fatal transport error without retry: %s", case_id, exc)
        except Exception as exc:
            observed_classification = f"unexpected_exception:{type(exc).__name__}"
            logger.exception("Transport injection case %s failed unexpectedly", case_id)
            exit_code = 1
    finally:
        alchemy_mod.urllib_request.urlopen = original_urlopen
        logger.removeHandler(handler)
        handler.close()

    ended = utc_now()
    write_json(
        run_root / "exit_status.json",
        {
            "started_at_utc": started,
            "ended_at_utc": ended,
            "exit_code": exit_code,
            "process_id": None,
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
        },
    )
    write_watchdog(run_root, exit_code, reason="transport_injection_case_completed")
    collector = run_collector(run_root)
    summary = {
        "case_id": case_id,
        "http_code": http_code,
        "exit_code": exit_code,
        "expected_classification": expected_classification,
        "observed_classification": observed_classification,
        "urlopen_call_count": calls["count"],
        "live_replay_write_count": count_jsonl(artifacts_root / "live_replay"),
        "collector_status": collector["status"],
        "collector_infrastructure_errors": collector["infrastructure_errors"],
        "collector_classifications": collector["classifications"],
        "retry_count": collector["metrics"]["retry"]["alchemy_retry_count"],
        "delay_sequence": collector["metrics"]["retry"]["delay_sequence"],
        "run_root": str(run_root.resolve()),
    }
    write_json(run_root / "transport_case_summary.json", summary)
    return summary


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


def write_watchdog(run_root: Path, exit_code: int, *, reason: str) -> None:
    events = run_root / "watchdog_events.jsonl"
    append_jsonl(
        events,
        {
            "generated_at_utc": utc_now(),
            "severity": "P3",
            "segment_id": run_root.name,
            "check_name": "process_liveness",
            "action": "observe",
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
            "p0_count": 0,
            "p1_count": 0,
            "p2_count": 0,
            "p3_count": 1,
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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def secret_leak_count(log_text: str, values: list[str]) -> int:
    return sum(log_text.count(value) for value in values if value)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
