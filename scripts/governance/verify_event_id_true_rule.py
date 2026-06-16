from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


PROBE_NAME = "event_id_true_rule_verification"
SAMPLE_LIMIT = 20
REQUIRED_FIELDS = {"provider_id", "event_type", "raw_payload", "event_id"}


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

    stable_hash, import_error = _load_stable_hash()
    if stable_hash is None:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note=f"failed to import stable_hash: {import_error}",
        )

    summary = _scan(input_root, stable_hash)
    exit_code = _exit_code_for_status(summary["status"])
    summary["exit_code"] = exit_code
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


def _parse_args(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input-root")
    parser.add_argument("--ack-replay-lossless-assumption", action="store_true")
    return parser.parse_known_args(argv)


def _load_stable_hash() -> tuple[Callable[[object], str] | None, str | None]:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    try:
        from enhengclaw.infra.shared.hashing import stable_hash
    except Exception as exc:  # pragma: no cover - reported as JSON infrastructure failure.
        return None, f"{type(exc).__name__}: {exc}"
    return stable_hash, None


def _scan(input_root: Path, stable_hash: Callable[[object], str]) -> dict[str, Any]:
    semantic_errors = {
        "actual_expected_event_id_mismatch_count": 0,
        "event_type_method_mismatch_count": 0,
        "unsupported_provider_event_type_count": 0,
        "true_generator_input_rebuild_error_count": 0,
    }
    representation_errors = {
        "json_parse_error_count": 0,
        "missing_required_field_count": 0,
        "malformed_event_id_prefix_count": 0,
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
        "rebuild_seconds": 0.0,
        "stable_hash_seconds": 0.0,
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

                actual_event_id = record["event_id"]
                if not isinstance(actual_event_id, str) or not actual_event_id.startswith("sha256:"):
                    representation_errors["malformed_event_id_prefix_count"] += 1
                    _append_sample(samples["representation_errors"], lambda: f"{location}:malformed_event_id_prefix")
                    continue

                phase_started = time.perf_counter()
                try:
                    true_generator_input = _rebuild_true_generator_input(record)
                except UnsupportedProviderEventType as exc:
                    phase_timings["rebuild_seconds"] += time.perf_counter() - phase_started
                    semantic_errors["unsupported_provider_event_type_count"] += 1
                    _append_sample(samples["rebuild_errors"], lambda: f"{location}:unsupported_provider_event_type:{exc}")
                    continue
                except RebuildError as exc:
                    phase_timings["rebuild_seconds"] += time.perf_counter() - phase_started
                    semantic_errors["true_generator_input_rebuild_error_count"] += 1
                    _append_sample(samples["rebuild_errors"], lambda: f"{location}:rebuild_error:{exc}")
                    continue
                phase_timings["rebuild_seconds"] += time.perf_counter() - phase_started

                if (
                    str(record["provider_id"]).startswith("alchemy.")
                    and _mapping(record["raw_payload"]).get("method") != record["event_type"]
                ):
                    semantic_errors["event_type_method_mismatch_count"] += 1
                    _append_sample(samples["mismatches"], lambda: f"{location}:event_type_method_mismatch")
                    continue

                phase_started = time.perf_counter()
                expected_event_id = f"sha256:{stable_hash(true_generator_input)}"
                phase_timings["stable_hash_seconds"] += time.perf_counter() - phase_started
                records_checked += 1
                phase_started = time.perf_counter()
                if actual_event_id != expected_event_id:
                    semantic_errors["actual_expected_event_id_mismatch_count"] += 1
                    _append_sample(
                        samples["mismatches"],
                        lambda: f"{location}:actual={actual_event_id}:expected={expected_event_id}",
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
        "generator_rule_verified": status == "passed",
        "owner_review_blocked": status != "passed",
        "samples": samples,
        "notes": [],
    }


def _rebuild_true_generator_input(record: dict[str, Any]) -> dict[str, Any]:
    provider_id = record["provider_id"]
    event_type = record["event_type"]
    if provider_id == "binance.spot.ws" and event_type == "trade":
        return _rebuild_binance_trade(record)
    if str(provider_id).startswith("alchemy.") and event_type in {
        "eth_blockNumber",
        "eth_getBlockByNumber",
        "getblockcount",
        "getblock",
        "getSlot",
        "getBlock",
    }:
        return _rebuild_alchemy_rpc(record)
    raise UnsupportedProviderEventType(f"{provider_id}:{event_type}")


def _rebuild_binance_trade(record: dict[str, Any]) -> dict[str, Any]:
    raw_payload = _mapping(record["raw_payload"])
    raw_data = raw_payload.get("data", raw_payload)
    data = _mapping(raw_data)
    symbol = _non_empty_string(data.get("s"), "data.s").upper()
    trade_id = _int_like(data.get("t"), "data.t")
    event_time = _int_like(data.get("E"), "data.E")
    _numeric_like(data.get("p"), "data.p")
    _numeric_like(data.get("q"), "data.q")
    return {
        "provider_id": "binance.spot.ws",
        "event_type": "trade",
        "symbol": symbol,
        "trade_id": trade_id,
        "event_time": event_time,
        "price": str(data.get("p")),
        "quantity": str(data.get("q")),
    }


def _rebuild_alchemy_rpc(record: dict[str, Any]) -> dict[str, Any]:
    raw_payload = _mapping(record["raw_payload"])
    method = _non_empty_string(raw_payload.get("method"), "raw_payload.method")
    response = _mapping(raw_payload.get("response"))
    if "id" not in response:
        raise RebuildError("raw_payload.response.id is required")
    if "result" not in response:
        raise RebuildError("raw_payload.response.result is required")
    return {
        "provider_id": record["provider_id"],
        "event_type": method,
        "id": response["id"],
        "result": response["result"],
    }


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


def _numeric_like(value: object, field: str) -> None:
    try:
        float(value)
    except (TypeError, ValueError) as exc:
        raise RebuildError(f"{field} must be numeric") from exc


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
            "actual_expected_event_id_mismatch_count": 0,
            "event_type_method_mismatch_count": 0,
            "unsupported_provider_event_type_count": 0,
            "true_generator_input_rebuild_error_count": 0,
        },
        "representation_errors": {
            "json_parse_error_count": 0,
            "missing_required_field_count": 0,
            "malformed_event_id_prefix_count": 0,
        },
        "assumptions": {
            "replay_lossless_assumption_acknowledged": False,
            "replay_record_provider_id_lossless": "explicit_assumption",
            "replay_record_event_type_lossless": "explicit_assumption",
            "replay_record_raw_payload_lossless": "explicit_assumption",
        },
        "rule_verified": False,
        "generator_rule_verified": False,
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
