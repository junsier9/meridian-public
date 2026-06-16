from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
DEFAULT_RUN_ROOT = DEFAULT_ARTIFACTS_ROOT / "shadow_24h"
DEFAULT_STDOUT_LOG = DEFAULT_RUN_ROOT / "shadow_ingest.stdout.log"
DEFAULT_STDERR_LOG = DEFAULT_RUN_ROOT / "shadow_ingest.stderr.log"
DEFAULT_RUN_CONFIG = DEFAULT_RUN_ROOT / "run_config.json"
DEFAULT_EXIT_STATUS = DEFAULT_RUN_ROOT / "exit_status.json"

LEGACY_PROVIDERS = (
    {
        "kind": "binance_trade",
        "provider_id": "binance.spot.ws",
        "subject_key": "BTCUSDT.binance.spot",
        "symbol": "BTCUSDT",
    },
    {
        "kind": "binance_trade",
        "provider_id": "binance.spot.ws",
        "subject_key": "ETHUSDT.binance.spot",
        "symbol": "ETHUSDT",
    },
    {
        "kind": "alchemy_evm_block",
        "provider_id": "alchemy.eth.rpc",
        "subject_key": "ETH.alchemy.onchain",
        "symbol": "ETH",
    },
)

BINANCE_RECONNECT_MARKER = "Binance WebSocket disconnected; reconnect attempt"
BINANCE_SUBSCRIPTION_MARKERS = (
    "Binance subscription acknowledged",
    "Binance subscription ack received after reconnect",
)
BINANCE_RECEIVE_TIMEOUT_MARKER = "no Binance messages received within"
BINANCE_WATCHDOG_RECEIVE_GAP_MARKER = "live receive gap exceeded"
BINANCE_WATCHDOG_SOURCE_AGE_MARKER = "live source age exceeded"
ALCHEMY_RETRY_MARKER = "Alchemy RPC transient failure"
ALCHEMY_DEGRADED_MARKER = "Alchemy provider entered degraded state"
ALCHEMY_RECOVERED_MARKER = "Alchemy provider recovered"
RUN_START_MARKER = "Starting shadow ingestion into"
BINANCE_SCHEMA_REJECT_MARKER = "Rejected Binance trade payload"
ALCHEMY_ENDPOINT_RE = re.compile(r"https://[^\\s]+\\.g\\.alchemy\\.com/v2/(?!\\*\\*\\*redacted\\*\\*\\*)[^\\s]+")
REPLAY_WRITE_ERROR_RE = re.compile(
    r"(PermissionError|No space left|disk full|BrokenPipeError|live_replay_writer.*error)",
    re.IGNORECASE,
)
BINANCE_LOGGER_SYMBOL_RE = re.compile(r"\[BinanceTradeShadowProvider\.(?P<symbol>[A-Z0-9_]+)\]")


@dataclass(slots=True)
class SubjectSummary:
    subject_key: str
    event_count: int
    event_type_counts: dict[str, int]
    file_count: int
    total_bytes: int
    hour_files: list[dict[str, Any]]
    missing_hours: list[str]
    latest_ingest_timestamp_utc: str | None
    parse_error_count: int
    contamination_count: int


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    run_config = _load_json(Path(args.run_config)) if args.run_config else None
    exit_status = _load_json(Path(args.exit_status)) if args.exit_status else None
    started_at = _parse_iso(run_config.get("launched_at_utc")) if isinstance(run_config, dict) else None
    ended_at = _parse_iso(exit_status.get("ended_at_utc")) if isinstance(exit_status, dict) else None
    providers = _expected_providers(run_config if isinstance(run_config, dict) else None)
    subjects_to_check = tuple(str(provider["subject_key"]) for provider in providers)
    providers_by_subject = {
        str(provider["subject_key"]): provider
        for provider in providers
    }
    binance_symbols = tuple(
        str(provider["symbol"]).upper()
        for provider in providers
        if provider.get("kind") == "binance_trade"
    )

    replay_root = Path(args.artifacts_root) / "live_replay"
    quarantine_root = Path(args.artifacts_root) / "live_quarantine"

    subjects = {
        subject: _summarize_subject(
            replay_root=replay_root,
            subject=subject,
            provider=providers_by_subject[subject],
            expected_hours=_expected_hours(started_at, ended_at),
            active_run=not isinstance(exit_status, dict),
        )
        for subject in subjects_to_check
    }
    quarantine_summary = _summarize_quarantine(quarantine_root)
    log_summary = _summarize_logs(
        [Path(args.stdout_log), Path(args.stderr_log)],
        secret_env_vars=("BINANCE_API_KEY", "ALCHEMY_API_KEY"),
        binance_socket_symbols=binance_symbols,
    )

    summary = {
        "run": {
            "artifacts_root": str(Path(args.artifacts_root).resolve()),
            "run_root": str(Path(args.run_root).resolve()) if args.run_root else None,
            "started_at_utc": None if started_at is None else _format_iso(started_at),
            "ended_at_utc": None if ended_at is None else _format_iso(ended_at),
            "exit_code": None if not isinstance(exit_status, dict) else exit_status.get("exit_code"),
            "run_completed": isinstance(exit_status, dict),
        },
        "subjects": {subject: _subject_to_dict(summary) for subject, summary in subjects.items()},
        "stability": {
            "binance_reconnect_count": log_summary["binance_reconnect_count"],
            "binance_subscription_ack_count": log_summary["binance_subscription_ack_count"],
            "binance_reconnect_count_by_symbol": log_summary["binance_reconnect_count_by_symbol"],
            "binance_subscription_ack_count_by_symbol": log_summary["binance_subscription_ack_count_by_symbol"],
            "binance_receive_timeout_count_by_symbol": log_summary["binance_receive_timeout_count_by_symbol"],
            "binance_watchdog_receive_gap_count_by_symbol": log_summary["binance_watchdog_receive_gap_count_by_symbol"],
            "binance_watchdog_source_age_count_by_symbol": log_summary["binance_watchdog_source_age_count_by_symbol"],
            "alchemy_retry_count": log_summary["alchemy_retry_count"],
            "provider_degraded_count": log_summary["provider_degraded_count"],
            "provider_recovered_count": log_summary["provider_recovered_count"],
            "process_start_count": log_summary["process_start_count"],
            "process_exit_count": 0 if not isinstance(exit_status, dict) else int(exit_status.get("exit_code", 0) != 0),
        },
        "quality": {
            "quarantine_count": quarantine_summary["record_count"],
            "quarantine_file_count": quarantine_summary["file_count"],
            "schema_rejection_count": quarantine_summary["record_count"] + log_summary["binance_schema_rejection_count"],
            "replay_parse_error_count": sum(item.parse_error_count for item in subjects.values()) + quarantine_summary["parse_error_count"],
            "replay_write_failure_count": log_summary["replay_write_failure_count"],
            "cross_subject_contamination_count": sum(item.contamination_count for item in subjects.values()),
            "quarantine_reason_counts": quarantine_summary["reason_counts"],
        },
        "security": {
            "key_leakage_detected": log_summary["key_leakage_detected"],
            "unredacted_alchemy_endpoint_detected": log_summary["unredacted_alchemy_endpoint_detected"],
        },
    }

    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_text_summary(summary)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize a shadow-ingest run from replay files and stderr/stdout logs."
    )
    parser.add_argument("--artifacts-root", default=DEFAULT_ARTIFACTS_ROOT, type=Path)
    parser.add_argument("--run-root", default=DEFAULT_RUN_ROOT, type=Path)
    parser.add_argument("--stdout-log", default=DEFAULT_STDOUT_LOG, type=Path)
    parser.add_argument("--stderr-log", default=DEFAULT_STDERR_LOG, type=Path)
    parser.add_argument("--run-config", default=DEFAULT_RUN_CONFIG, type=Path)
    parser.add_argument("--exit-status", default=DEFAULT_EXIT_STATUS, type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _summarize_subject(
    *,
    replay_root: Path,
    subject: str,
    provider: dict[str, Any],
    expected_hours: set[str],
    active_run: bool,
) -> SubjectSummary:
    subject_root = replay_root / subject
    event_type_counts: Counter[str] = Counter()
    hour_files: list[dict[str, Any]] = []
    parse_error_count = 0
    contamination_count = 0
    event_count = 0
    total_bytes = 0
    latest_ingest: datetime | None = None
    observed_hours: set[str] = set()

    if subject_root.exists():
        for path in sorted(subject_root.rglob("*.jsonl")):
            total_bytes += path.stat().st_size
            record_count_for_file = 0
            date_fragment = path.parent.name
            hour_fragment = path.stem
            hour_key = f"{date_fragment}T{hour_fragment}"
            observed_hours.add(hour_key)
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError:
                        parse_error_count += 1
                        continue
                    event_count += 1
                    record_count_for_file += 1
                    event_type = str(record.get("event_type", "unknown"))
                    event_type_counts[event_type] += 1
                    ingest_timestamp = _parse_iso(record.get("ingest_timestamp_utc"))
                    if ingest_timestamp is not None and (latest_ingest is None or ingest_timestamp > latest_ingest):
                        latest_ingest = ingest_timestamp
                    contamination_count += _contamination_violations(subject, provider, record)
            hour_files.append(
                {
                    "hour": hour_key,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "record_count": record_count_for_file,
                }
            )

    effective_expected_hours = set(expected_hours)
    if active_run and effective_expected_hours:
        latest_expected = max(effective_expected_hours)
        effective_expected_hours = {item for item in effective_expected_hours if item != latest_expected}

    return SubjectSummary(
        subject_key=subject,
        event_count=event_count,
        event_type_counts=dict(event_type_counts),
        file_count=len(hour_files),
        total_bytes=total_bytes,
        hour_files=hour_files,
        missing_hours=sorted(effective_expected_hours - observed_hours),
        latest_ingest_timestamp_utc=None if latest_ingest is None else _format_iso(latest_ingest),
        parse_error_count=parse_error_count,
        contamination_count=contamination_count,
    )


def _summarize_quarantine(root: Path) -> dict[str, Any]:
    record_count = 0
    file_count = 0
    parse_error_count = 0
    reason_counts: Counter[str] = Counter()
    if root.exists():
        for path in sorted(root.rglob("*.jsonl")):
            file_count += 1
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError:
                        parse_error_count += 1
                        continue
                    record_count += 1
                    reason_counts[str(record.get("reason", "unknown"))] += 1
    return {
        "record_count": record_count,
        "file_count": file_count,
        "parse_error_count": parse_error_count,
        "reason_counts": dict(reason_counts),
    }


def _summarize_logs(
    paths: list[Path],
    *,
    secret_env_vars: tuple[str, ...],
    binance_socket_symbols: tuple[str, ...],
) -> dict[str, Any]:
    text_parts: list[str] = []
    lines: list[str] = []
    for path in paths:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            text_parts.append(text)
            lines.extend(text.splitlines())
    combined = "\n".join(text_parts)
    reconnect_count_by_symbol: Counter[str] = Counter()
    subscription_ack_count_by_symbol: Counter[str] = Counter()
    receive_timeout_count_by_symbol: Counter[str] = Counter()
    watchdog_receive_gap_count_by_symbol: Counter[str] = Counter()
    watchdog_source_age_count_by_symbol: Counter[str] = Counter()

    for line in lines:
        symbol = _extract_binance_logger_symbol(line, binance_socket_symbols=binance_socket_symbols)
        if BINANCE_RECONNECT_MARKER in line:
            if symbol is not None:
                reconnect_count_by_symbol[symbol] += 1
            if BINANCE_RECEIVE_TIMEOUT_MARKER in line and symbol is not None:
                receive_timeout_count_by_symbol[symbol] += 1
        if any(marker in line for marker in BINANCE_SUBSCRIPTION_MARKERS):
            if symbol is not None:
                subscription_ack_count_by_symbol[symbol] += 1
        if (
            "forcing Binance reconnect because" in line
            and BINANCE_RECONNECT_MARKER not in line
            and BINANCE_WATCHDOG_RECEIVE_GAP_MARKER in line
            and symbol is not None
        ):
            watchdog_receive_gap_count_by_symbol[symbol] += 1
        if (
            "forcing Binance reconnect because" in line
            and BINANCE_RECONNECT_MARKER not in line
            and BINANCE_WATCHDOG_SOURCE_AGE_MARKER in line
            and symbol is not None
        ):
            watchdog_source_age_count_by_symbol[symbol] += 1

    key_leakage_detected = False
    for env_var in secret_env_vars:
        secret = os.getenv(env_var)
        if secret and secret in combined:
            key_leakage_detected = True
            break

    return {
        "binance_reconnect_count": combined.count(BINANCE_RECONNECT_MARKER),
        "binance_subscription_ack_count": sum(
            combined.count(marker)
            for marker in BINANCE_SUBSCRIPTION_MARKERS
        ),
        "binance_reconnect_count_by_symbol": _counter_by_symbol(reconnect_count_by_symbol, binance_socket_symbols),
        "binance_subscription_ack_count_by_symbol": _counter_by_symbol(subscription_ack_count_by_symbol, binance_socket_symbols),
        "binance_receive_timeout_count_by_symbol": _counter_by_symbol(receive_timeout_count_by_symbol, binance_socket_symbols),
        "binance_watchdog_receive_gap_count_by_symbol": _counter_by_symbol(watchdog_receive_gap_count_by_symbol, binance_socket_symbols),
        "binance_watchdog_source_age_count_by_symbol": _counter_by_symbol(watchdog_source_age_count_by_symbol, binance_socket_symbols),
        "alchemy_retry_count": combined.count(ALCHEMY_RETRY_MARKER),
        "provider_degraded_count": combined.count(ALCHEMY_DEGRADED_MARKER),
        "provider_recovered_count": combined.count(ALCHEMY_RECOVERED_MARKER),
        "process_start_count": combined.count(RUN_START_MARKER),
        "binance_schema_rejection_count": combined.count(BINANCE_SCHEMA_REJECT_MARKER),
        "replay_write_failure_count": len(REPLAY_WRITE_ERROR_RE.findall(combined)),
        "key_leakage_detected": key_leakage_detected,
        "unredacted_alchemy_endpoint_detected": bool(ALCHEMY_ENDPOINT_RE.search(combined)),
    }


def _extract_binance_logger_symbol(line: str, *, binance_socket_symbols: tuple[str, ...]) -> str | None:
    match = BINANCE_LOGGER_SYMBOL_RE.search(line)
    if match is None:
        return None
    symbol = match.group("symbol")
    if symbol in binance_socket_symbols:
        return symbol
    return None


def _counter_by_symbol(counter: Counter[str], expected_symbols: tuple[str, ...]) -> dict[str, int]:
    return {
        symbol: int(counter.get(symbol, 0))
        for symbol in expected_symbols
    }


def _contamination_violations(subject: str, provider: dict[str, Any], record: dict[str, Any]) -> int:
    violations = 0
    if record.get("subject_key") != subject:
        violations += 1

    provider_id = record.get("provider_id")
    raw_payload = record.get("raw_payload")
    kind = provider.get("kind")
    if kind == "binance_trade":
        if provider_id != provider.get("provider_id"):
            violations += 1
        if isinstance(raw_payload, dict):
            data = raw_payload.get("data", raw_payload)
            if isinstance(data, dict):
                symbol = data.get("s")
                expected_symbol = subject.split(".", maxsplit=1)[0]
                if isinstance(symbol, str) and symbol.upper() != expected_symbol:
                    violations += 1
    elif kind in {"alchemy_evm_block", "alchemy_bitcoin_block", "alchemy_solana_block"}:
        if provider_id != provider.get("provider_id"):
            violations += 1
        if isinstance(raw_payload, dict):
            method = raw_payload.get("method")
            if method != record.get("event_type"):
                violations += 1
    return violations


def _expected_providers(run_config: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if isinstance(run_config, dict):
        raw_providers = run_config.get("providers")
        if isinstance(raw_providers, list) and raw_providers:
            return tuple(provider for provider in raw_providers if isinstance(provider, dict))
    return LEGACY_PROVIDERS


def _expected_hours(started_at: datetime | None, ended_at: datetime | None) -> set[str]:
    if started_at is None:
        return set()
    effective_end = ended_at or datetime.now(UTC)
    cursor = started_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    last = effective_end.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    hours: set[str] = set()
    while cursor <= last:
        hours.add(cursor.strftime("%Y-%m-%dT%H"))
        cursor += timedelta(hours=1)
    return hours


def _subject_to_dict(summary: SubjectSummary) -> dict[str, Any]:
    return {
        "subject_key": summary.subject_key,
        "event_count": summary.event_count,
        "event_type_counts": summary.event_type_counts,
        "file_count": summary.file_count,
        "total_bytes": summary.total_bytes,
        "hour_files": summary.hour_files,
        "missing_hours": summary.missing_hours,
        "latest_ingest_timestamp_utc": summary.latest_ingest_timestamp_utc,
        "parse_error_count": summary.parse_error_count,
        "contamination_count": summary.contamination_count,
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(UTC)
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _print_text_summary(summary: dict[str, Any]) -> None:
    run = summary["run"]
    print("Run")
    print(f"  artifacts_root: {run['artifacts_root']}")
    print(f"  started_at_utc: {run['started_at_utc']}")
    print(f"  ended_at_utc: {run['ended_at_utc']}")
    print(f"  exit_code: {run['exit_code']}")
    print(f"  run_completed: {run['run_completed']}")

    print("Subjects")
    for subject, subject_summary in summary["subjects"].items():
        print(f"  {subject}")
        print(f"    event_count: {subject_summary['event_count']}")
        print(f"    event_type_counts: {subject_summary['event_type_counts']}")
        print(f"    file_count: {subject_summary['file_count']}")
        print(f"    total_bytes: {subject_summary['total_bytes']}")
        print(f"    missing_hours: {subject_summary['missing_hours']}")
        print(f"    latest_ingest_timestamp_utc: {subject_summary['latest_ingest_timestamp_utc']}")
        print(f"    contamination_count: {subject_summary['contamination_count']}")

    print("Stability")
    for key, value in summary["stability"].items():
        print(f"  {key}: {value}")

    print("Quality")
    for key, value in summary["quality"].items():
        print(f"  {key}: {value}")

    print("Security")
    for key, value in summary["security"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
