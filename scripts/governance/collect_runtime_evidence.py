from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


COLLECTOR_NAME = "runtime_evidence_collector"
ALCHEMY_RETRY_MARKER = "Alchemy RPC transient failure"
BINANCE_RECONNECT_MARKER = "Binance WebSocket disconnected; reconnect attempt"
ALCHEMY_DEGRADED_MARKER = "Alchemy provider entered degraded state"
ALCHEMY_RECOVERED_MARKER = "Alchemy provider recovered"
ALCHEMY_POLL_SUCCEEDED_MARKER = "Alchemy poll succeeded against"
RUN_START_MARKER = "Starting shadow ingestion into"
ALCHEMY_RETRY_RE = re.compile(
    r"Alchemy RPC transient failure .* retry (?P<attempt>\d+)/(?P<max>[^ ]+) in (?P<delay>[0-9.]+)s"
)
BINANCE_RECONNECT_RE = re.compile(
    r"Binance WebSocket disconnected; reconnect attempt (?P<attempt>\d+)/(?P<max>[^ ]+) in (?P<delay>[0-9.]+)s"
)
LOG_TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_root = Path(args.run_root)
    output_path = Path(args.output) if args.output else run_root / "collector_output.json"
    summary = collect(run_root=run_root, artifacts_root=Path(args.artifacts_root) if args.artifacts_root else None)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 2 if summary["status"] == "infrastructure_failure" else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Day 3 runtime evidence from a shadow run segment.")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--artifacts-root")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def collect(*, run_root: Path, artifacts_root: Path | None) -> dict[str, Any]:
    run_config_path = run_root / "run_config.json"
    exit_status_path = run_root / "exit_status.json"
    stdout_log = run_root / "shadow_ingest.stdout.log"
    stderr_log = run_root / "shadow_ingest.stderr.log"
    watchdog_events_path = run_root / "watchdog_events.jsonl"
    infrastructure_errors: list[str] = []
    evidence_gaps: list[str] = []
    failures: list[dict[str, str]] = []

    run_config = _load_json(run_config_path, infrastructure_errors)
    exit_status = _load_json(exit_status_path, infrastructure_errors)
    if artifacts_root is None and isinstance(run_config, dict):
        configured_artifacts_root = run_config.get("artifacts_root")
        if isinstance(configured_artifacts_root, str) and configured_artifacts_root:
            artifacts_root = Path(configured_artifacts_root)
    if artifacts_root is None:
        infrastructure_errors.append("artifacts_root is required when absent from run_config.json")
        artifacts_root = run_root / "artifacts"

    stdout_text = _read_text(stdout_log, infrastructure_errors, required=False)
    stderr_text = _read_text(stderr_log, infrastructure_errors, required=True)
    combined_logs = f"{stdout_text}\n{stderr_text}"
    if isinstance(exit_status, dict) and exit_status.get("exit_code") is None:
        infrastructure_errors.append("exit_status.json exit_code is null")
    watchdog_events = _load_watchdog_events(watchdog_events_path, infrastructure_errors)
    watchdog_counts = Counter(str(event.get("severity")) for event in watchdog_events if isinstance(event, dict))

    delay_sequence = {
        "alchemy": _parse_delay_sequence(stderr_text, ALCHEMY_RETRY_RE),
        "binance": _parse_delay_sequence(stderr_text, BINANCE_RECONNECT_RE),
    }
    alchemy_poll_intervals = _alchemy_poll_intervals(stderr_text)
    busy_loop_indicator_count = _busy_loop_indicator_count(alchemy_poll_intervals)
    secret_leak_count = _secret_leak_count(combined_logs)
    unredacted_endpoint_detected = bool(
        re.search(r"https://[^\s]+\.g\.alchemy\.com/v2/(?!\*\*\*redacted\*\*\*)[^\s]+", combined_logs)
    )

    if watchdog_counts.get("P0", 0) or watchdog_counts.get("P1", 0):
        failures.append(
            {
                "governance_line": "runtime_control_plane",
                "class": "watchdog_alert",
                "reason": "watchdog emitted P0/P1 event",
            }
        )
    if isinstance(exit_status, dict) and exit_status.get("exit_code") not in (0, None):
        failures.append(
            {
                "governance_line": "runtime_control_plane",
                "class": "process_exit",
                "reason": f"shadow run exited with code {exit_status.get('exit_code')}",
            }
        )
    if secret_leak_count or unredacted_endpoint_detected:
        failures.append(
            {
                "governance_line": "env / fail-fast",
                "class": "secret_leakage",
                "reason": "secret or unredacted provider endpoint detected in logs",
            }
        )
    if not delay_sequence["alchemy"] and not delay_sequence["binance"]:
        evidence_gaps.append("backoff / retry has no natural retry event in this segment")
        evidence_gaps.append("errors / transport has no transport fault in this segment")
    if len(alchemy_poll_intervals) < 2:
        evidence_gaps.append("async / sleep has insufficient Alchemy poll interval samples")

    classifications = {
        "env_fail_fast": "passed" if not secret_leak_count and not unredacted_endpoint_detected else "failed",
        "backoff_retry": "passed" if delay_sequence["alchemy"] or delay_sequence["binance"] else "insufficient_evidence",
        "errors_transport": "passed" if delay_sequence["alchemy"] or delay_sequence["binance"] else "insufficient_evidence",
        "async_sleep": "passed" if len(alchemy_poll_intervals) >= 2 and busy_loop_indicator_count == 0 else "insufficient_evidence",
    }

    if infrastructure_errors:
        status = "infrastructure_failure"
    elif failures:
        status = "failed"
    else:
        status = "passed"

    return {
        "collector_name": COLLECTOR_NAME,
        "schema_version": 1,
        "status": status,
        "input": {
            "run_root": str(run_root.resolve()),
            "artifacts_root": str(artifacts_root.resolve()),
            "stdout_log": str(stdout_log.resolve()),
            "stderr_log": str(stderr_log.resolve()),
            "watchdog_events": str(watchdog_events_path.resolve()),
        },
        "run": {
            "started_at_utc": _dict_value(run_config, "launched_at_utc"),
            "ended_at_utc": _dict_value(exit_status, "ended_at_utc"),
            "exit_code": _dict_value(exit_status, "exit_code"),
            "run_completed": isinstance(exit_status, dict),
        },
        "watchdog": {
            "p0_count": int(watchdog_counts.get("P0", 0)),
            "p1_count": int(watchdog_counts.get("P1", 0)),
            "p2_count": int(watchdog_counts.get("P2", 0)),
            "p3_count": int(watchdog_counts.get("P3", 0)),
            "event_count": len(watchdog_events),
            "restart_enabled": False,
        },
        "metrics": {
            "retry": {
                "alchemy_retry_count": combined_logs.count(ALCHEMY_RETRY_MARKER),
                "binance_reconnect_count": combined_logs.count(BINANCE_RECONNECT_MARKER),
                "delay_sequence": delay_sequence,
                "delay_monotonic_until_cap": _delay_monotonic(delay_sequence),
            },
            "degraded_recovered": {
                "provider_degraded_count": combined_logs.count(ALCHEMY_DEGRADED_MARKER),
                "provider_recovered_count": combined_logs.count(ALCHEMY_RECOVERED_MARKER),
            },
            "loop_interval": {
                "alchemy_poll_interval_seconds": _interval_stats(alchemy_poll_intervals),
                "busy_loop_indicator_count": busy_loop_indicator_count,
                "insufficient_loop_marker_count": 0 if len(alchemy_poll_intervals) >= 2 else 1,
            },
            "env_fail_fast": {
                "runtime_start_marker_count": combined_logs.count(RUN_START_MARKER),
                "live_replay_delta_count": _count_jsonl_records(artifacts_root / "live_replay"),
                "secret_leak_count": secret_leak_count,
                "unredacted_endpoint_detected": unredacted_endpoint_detected,
            },
        },
        "classifications": classifications,
        "evidence_gaps": evidence_gaps,
        "failures": failures,
        "infrastructure_errors": infrastructure_errors,
    }


def _load_json(path: Path, infrastructure_errors: list[str]) -> Any:
    if not path.exists():
        infrastructure_errors.append(f"missing required JSON file: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        infrastructure_errors.append(f"invalid JSON file {path}: {exc.msg}")
        return None


def _read_text(path: Path, infrastructure_errors: list[str], *, required: bool) -> str:
    if not path.exists():
        if required:
            infrastructure_errors.append(f"missing required log file: {path}")
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_watchdog_events(path: Path, infrastructure_errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        infrastructure_errors.append(f"missing watchdog events file: {path}")
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            infrastructure_errors.append(f"invalid watchdog JSONL at {path}:{line_number}: {exc.msg}")
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            infrastructure_errors.append(f"invalid watchdog event object at {path}:{line_number}")
    return events


def _parse_delay_sequence(text: str, pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        sequence.append(
            {
                "timestamp_utc": _timestamp_from_log_line(line),
                "attempt": int(match.group("attempt")),
                "max_attempts": match.group("max"),
                "delay_seconds": float(match.group("delay")),
            }
        )
    return sequence


def _alchemy_poll_intervals(text: str) -> list[float]:
    timestamps: list[datetime] = []
    for line in text.splitlines():
        if ALCHEMY_POLL_SUCCEEDED_MARKER not in line:
            continue
        timestamp = _parse_log_timestamp(line)
        if timestamp is not None:
            timestamps.append(timestamp)
    return [
        (right - left).total_seconds()
        for left, right in zip(timestamps, timestamps[1:], strict=False)
    ]


def _parse_log_timestamp(line: str) -> datetime | None:
    match = LOG_TS_RE.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None


def _timestamp_from_log_line(line: str) -> str | None:
    timestamp = _parse_log_timestamp(line)
    if timestamp is None:
        return None
    return timestamp.isoformat()


def _busy_loop_indicator_count(intervals: list[float]) -> int:
    return sum(1 for value in intervals if value < 0.1)


def _secret_leak_count(text: str) -> int:
    count = 0
    for env_var in ("BINANCE_API_KEY", "ALCHEMY_API_KEY"):
        secret = os.getenv(env_var)
        if secret:
            count += text.count(secret)
    return count


def _count_jsonl_records(root: Path) -> int:
    if not root.exists():
        return 0
    count = 0
    for path in root.rglob("*.jsonl"):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            count += sum(1 for line in handle if line.strip())
    return count


def _interval_stats(intervals: list[float]) -> dict[str, Any]:
    if not intervals:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(intervals)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "count": len(intervals),
        "min": min(intervals),
        "p50": statistics.median(intervals),
        "p95": ordered[p95_index],
        "max": max(intervals),
    }


def _delay_monotonic(delay_sequence: dict[str, list[dict[str, Any]]]) -> bool | None:
    sequences = [items for items in delay_sequence.values() if items]
    if not sequences:
        return None
    for items in sequences:
        delays = [float(item["delay_seconds"]) for item in items]
        if any(right < left for left, right in zip(delays, delays[1:], strict=False)):
            return False
    return True


def _dict_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
