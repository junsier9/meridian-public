from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROBE_NAME = "source_timestamp_true_rule_verification"
SAMPLE_LIMIT = 20
REQUIRED_FIELDS = {"provider_id", "event_type", "raw_payload", "source_timestamp"}


def main(argv: list[str] | None = None) -> int:
    args, unknown_args = _parse_args(argv)
    if unknown_args:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note=f"unknown arguments: {' '.join(unknown_args)}",
        )
    if not args.input_root:
        return _emit_infrastructure_failure(input_root=None, note="--input-root is required")
    if not args.ack_replay_lossless_assumption:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note="--ack-replay-lossless-assumption is required",
        )

    input_root = Path(args.input_root)
    if not input_root.exists() or not input_root.is_dir():
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note="input_root does not exist or is not a directory",
        )

    isoformat_utc, import_error = _load_isoformat_utc()
    if isoformat_utc is None:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note=f"failed to import isoformat_utc: {import_error}",
        )

    summary = _scan(input_root, isoformat_utc)
    exit_code = _exit_code_for_status(summary["status"])
    summary["exit_code"] = exit_code
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


def _parse_args(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input-root")
    parser.add_argument("--ack-replay-lossless-assumption", action="store_true")
    return parser.parse_known_args(argv)


def _load_isoformat_utc() -> tuple[Callable[[datetime], str] | None, str | None]:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from enhengclaw.infra.shared.time import isoformat_utc
    except Exception as exc:  # pragma: no cover - reported as JSON infrastructure failure.
        return None, f"{type(exc).__name__}: {exc}"
    return isoformat_utc, None


def _scan(input_root: Path, isoformat_utc: Callable[[datetime], str]) -> dict[str, Any]:
    semantic_errors = {
        "source_timestamp_expected_mismatch_count": 0,
        "unsupported_provider_event_type_count": 0,
        "source_timestamp_rebuild_error_count": 0,
    }
    representation_errors = {
        "json_parse_error_count": 0,
        "missing_required_field_count": 0,
        "source_timestamp_parse_error_count": 0,
    }
    samples: dict[str, list[str]] = {
        "mismatches": [],
        "rebuild_errors": [],
        "representation_errors": [],
    }

    paths = sorted(input_root.rglob("*.jsonl"))
    total_files = len(paths)
    scan_started = time.perf_counter()
    phase_timings = {
        "json_loads_seconds": 0.0,
        "source_timestamp_parse_seconds": 0.0,
        "rebuild_seconds": 0.0,
        "compare_seconds": 0.0,
    }
    files_scanned = 0
    records_scanned = 0
    records_checked = 0

    for file_index, path in enumerate(paths, start=1):
        files_scanned += 1
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError as exc:
            representation_errors["json_parse_error_count"] += 1
            _append_sample(samples["representation_errors"], lambda: f"{path}:0:read_error:{exc}")
            _emit_progress(file_index, total_files, path, records_scanned, records_checked, scan_started)
            continue
        with handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                records_scanned += 1
                location = f"{path}:{line_number}"
                phase_started = time.perf_counter()
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    phase_timings["json_loads_seconds"] += time.perf_counter() - phase_started
                    representation_errors["json_parse_error_count"] += 1
                    _append_sample(samples["representation_errors"], lambda: f"{location}:json_parse_error:{exc.msg}")
                    continue
                phase_timings["json_loads_seconds"] += time.perf_counter() - phase_started
                if not isinstance(record, dict) or not REQUIRED_FIELDS.issubset(record):
                    representation_errors["missing_required_field_count"] += 1
                    _append_sample(samples["representation_errors"], lambda: f"{location}:missing_required_field")
                    continue

                actual_source_timestamp = record["source_timestamp"]
                if actual_source_timestamp is not None:
                    phase_started = time.perf_counter()
                    try:
                        _parse_utc_timestamp(actual_source_timestamp)
                    except (TypeError, ValueError) as exc:
                        phase_timings["source_timestamp_parse_seconds"] += time.perf_counter() - phase_started
                        representation_errors["source_timestamp_parse_error_count"] += 1
                        _append_sample(samples["representation_errors"], lambda: f"{location}:source_timestamp_parse_error:{exc}")
                        continue
                    phase_timings["source_timestamp_parse_seconds"] += time.perf_counter() - phase_started

                phase_started = time.perf_counter()
                try:
                    expected_source_timestamp = _rebuild_expected_source_timestamp(record, isoformat_utc)
                except UnsupportedProviderEventType as exc:
                    phase_timings["rebuild_seconds"] += time.perf_counter() - phase_started
                    semantic_errors["unsupported_provider_event_type_count"] += 1
                    _append_sample(samples["rebuild_errors"], lambda: f"{location}:unsupported_provider_event_type:{exc}")
                    continue
                except RebuildError as exc:
                    phase_timings["rebuild_seconds"] += time.perf_counter() - phase_started
                    semantic_errors["source_timestamp_rebuild_error_count"] += 1
                    _append_sample(samples["rebuild_errors"], lambda: f"{location}:rebuild_error:{exc}")
                    continue
                phase_timings["rebuild_seconds"] += time.perf_counter() - phase_started

                records_checked += 1
                phase_started = time.perf_counter()
                if actual_source_timestamp != expected_source_timestamp:
                    semantic_errors["source_timestamp_expected_mismatch_count"] += 1
                    _append_sample(
                        samples["mismatches"],
                        lambda: f"{location}:actual={actual_source_timestamp}:expected={expected_source_timestamp}",
                    )
                phase_timings["compare_seconds"] += time.perf_counter() - phase_started
        _emit_progress(file_index, total_files, path, records_scanned, records_checked, scan_started)
    _emit_performance(phase_timings)

    status = _status(records_scanned, records_checked, semantic_errors, representation_errors)
    return {
        "probe_name": PROBE_NAME,
        "input_root": str(input_root.resolve()),
        "status": status,
        "exit_code": None,
        "files_scanned": files_scanned,
        "records_scanned": records_scanned,
        "records_checked": records_checked,
        "semantic_errors": semantic_errors,
        "representation_errors": representation_errors,
        "assumptions": {
            "replay_lossless_assumption_acknowledged": True,
            "replay_record_provider_id_lossless": "explicit_assumption",
            "replay_record_event_type_lossless": "explicit_assumption",
            "replay_record_raw_payload_lossless": "explicit_assumption",
        },
        "rule_verified": status == "passed",
        "source_timestamp_rule_verified": status == "passed",
        "owner_review_blocked": status != "passed",
        "samples": samples,
        "notes": [],
    }


def _rebuild_expected_source_timestamp(
    record: dict[str, Any],
    isoformat_utc: Callable[[datetime], str],
) -> str | None:
    provider_id = record["provider_id"]
    event_type = record["event_type"]
    if provider_id == "binance.spot.ws" and event_type == "trade":
        return _rebuild_binance_trade_source_timestamp(record, isoformat_utc)
    if str(provider_id).startswith("alchemy.") and event_type in {"eth_blockNumber", "getblockcount", "getSlot"}:
        return None
    if str(provider_id).startswith("alchemy.") and event_type == "eth_getBlockByNumber":
        return _rebuild_alchemy_block_source_timestamp(record, isoformat_utc)
    if str(provider_id).startswith("alchemy.") and event_type == "getblock":
        return _rebuild_alchemy_bitcoin_block_source_timestamp(record, isoformat_utc)
    if str(provider_id).startswith("alchemy.") and event_type == "getBlock":
        return _rebuild_alchemy_solana_block_source_timestamp(record, isoformat_utc)
    raise UnsupportedProviderEventType(f"{provider_id}:{event_type}")


def _rebuild_binance_trade_source_timestamp(
    record: dict[str, Any],
    isoformat_utc: Callable[[datetime], str],
) -> str:
    raw_payload = _mapping(record["raw_payload"])
    raw_data = raw_payload.get("data", raw_payload)
    data = _mapping(raw_data)
    source_ms_value = data.get("T")
    if source_ms_value is None:
        source_ms_value = data.get("E")
    source_ms = _int_like(source_ms_value, "data.T_or_data.E")
    return isoformat_utc(datetime.fromtimestamp(source_ms / 1000, tz=UTC))


def _rebuild_alchemy_block_source_timestamp(
    record: dict[str, Any],
    isoformat_utc: Callable[[datetime], str],
) -> str:
    raw_payload = _mapping(record["raw_payload"])
    response = _mapping(raw_payload.get("response"))
    result = _mapping(response.get("result"))
    timestamp_hex = _non_empty_string(result.get("timestamp"), "raw_payload.response.result.timestamp")
    try:
        timestamp_seconds = int(timestamp_hex, 16)
    except ValueError as exc:
        raise RebuildError("raw_payload.response.result.timestamp must be a hex quantity") from exc
    return isoformat_utc(datetime.fromtimestamp(timestamp_seconds, tz=UTC))


def _rebuild_alchemy_solana_block_source_timestamp(
    record: dict[str, Any],
    isoformat_utc: Callable[[datetime], str],
) -> str | None:
    raw_payload = _mapping(record["raw_payload"])
    response = _mapping(raw_payload.get("response"))
    result = response.get("result")
    if result is None:
        return None
    result_mapping = _mapping(result)
    block_time = result_mapping.get("blockTime")
    if block_time is None:
        return None
    timestamp_seconds = _int_like(block_time, "raw_payload.response.result.blockTime")
    return isoformat_utc(datetime.fromtimestamp(timestamp_seconds, tz=UTC))


def _rebuild_alchemy_bitcoin_block_source_timestamp(
    record: dict[str, Any],
    isoformat_utc: Callable[[datetime], str],
) -> str:
    raw_payload = _mapping(record["raw_payload"])
    response = _mapping(raw_payload.get("response"))
    result = _mapping(response.get("result"))
    timestamp_seconds = _int_like(result.get("time"), "raw_payload.response.result.time")
    return isoformat_utc(datetime.fromtimestamp(timestamp_seconds, tz=UTC))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RebuildError("expected JSON object")
    return value


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RebuildError(f"{field} must be a non-empty string")
    return value.strip()


def _int_like(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise RebuildError(f"{field} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RebuildError(f"{field} must be an integer") from exc


def _parse_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    stripped = value.strip()
    if not (stripped.endswith("Z") or stripped.endswith("+00:00")):
        raise ValueError("timestamp must use UTC Z or +00:00 representation")
    parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _status(
    records_scanned: int,
    records_checked: int,
    semantic_errors: dict[str, int],
    representation_errors: dict[str, int],
) -> str:
    if records_scanned == 0 or records_checked == 0:
        return "insufficient_evidence"
    if records_checked != records_scanned:
        return "failed"
    if any(semantic_errors.values()) or any(representation_errors.values()):
        return "failed"
    return "passed"


def _exit_code_for_status(status: str) -> int:
    if status == "passed":
        return 0
    if status == "failed":
        return 1
    if status == "insufficient_evidence":
        return 3
    return 2


def _emit_infrastructure_failure(input_root: str | None, note: str) -> int:
    summary = {
        "probe_name": PROBE_NAME,
        "input_root": input_root,
        "status": "infrastructure_failure",
        "exit_code": 2,
        "files_scanned": 0,
        "records_scanned": 0,
        "records_checked": 0,
        "semantic_errors": {
            "source_timestamp_expected_mismatch_count": 0,
            "unsupported_provider_event_type_count": 0,
            "source_timestamp_rebuild_error_count": 0,
        },
        "representation_errors": {
            "json_parse_error_count": 0,
            "missing_required_field_count": 0,
            "source_timestamp_parse_error_count": 0,
        },
        "assumptions": {
            "replay_lossless_assumption_acknowledged": False,
            "replay_record_provider_id_lossless": "explicit_assumption",
            "replay_record_event_type_lossless": "explicit_assumption",
            "replay_record_raw_payload_lossless": "explicit_assumption",
        },
        "rule_verified": False,
        "source_timestamp_rule_verified": False,
        "owner_review_blocked": True,
        "samples": {
            "mismatches": [],
            "rebuild_errors": [],
            "representation_errors": [],
        },
        "notes": [note],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 2


def _emit_progress(
    file_index: int,
    total_files: int,
    path: Path,
    records_scanned: int,
    records_checked: int,
    scan_started: float,
) -> None:
    elapsed_seconds = time.perf_counter() - scan_started
    print(
        (
            "progress "
            f"file_index={file_index} total_files={total_files} path={path} "
            f"records_scanned={records_scanned} records_checked={records_checked} "
            f"elapsed_seconds={elapsed_seconds:.3f}"
        ),
        file=sys.stderr,
    )


def _emit_performance(phase_timings: dict[str, float]) -> None:
    print(
        "performance "
        + " ".join(f"{key}={value:.6f}" for key, value in sorted(phase_timings.items())),
        file=sys.stderr,
    )


def _append_sample(samples: list[str], value_factory: Callable[[], str]) -> None:
    if len(samples) < SAMPLE_LIMIT:
        samples.append(value_factory())


class RebuildError(ValueError):
    pass


class UnsupportedProviderEventType(RebuildError):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
