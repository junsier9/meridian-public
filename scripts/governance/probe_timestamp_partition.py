from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROBE_NAME = "timestamp_partition_probe"
SAMPLE_LIMIT = 20
BINANCE_FUTURE_SKEW_SECONDS = 60.0
ALCHEMY_FUTURE_SKEW_SECONDS = 900.0
DEFAULT_FUTURE_SKEW_SECONDS = 900.0


def main(argv: list[str] | None = None) -> int:
    args, unknown_args = _parse_args(argv)
    if unknown_args:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note=f"unknown arguments: {' '.join(unknown_args)}",
        )
    if not args.input_root:
        return _emit_infrastructure_failure(
            input_root=None,
            note="--input-root is required",
        )
    if not args.verify_timestamp_rule:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note="--verify-timestamp-rule is required",
        )

    input_root = Path(args.input_root)
    if not input_root.exists() or not input_root.is_dir():
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note="input_root does not exist or is not a directory",
        )

    summary = _scan(input_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["status"] == "passed":
        return 0
    if summary["status"] == "insufficient_evidence":
        return 3
    return 1


def _parse_args(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input-root")
    parser.add_argument("--verify-timestamp-rule", action="store_true")
    return parser.parse_known_args(argv)


def _scan(input_root: Path) -> dict[str, Any]:
    semantic_errors = {
        "source_timestamp_future_skew_count": 0,
        "source_timestamp_unreasonable_backfill_count": 0,
        "subject_partition_mismatch_count": 0,
    }
    representation_errors = {
        "json_parse_error_count": 0,
        "missing_ingest_timestamp_count": 0,
        "ingest_timestamp_parse_error_count": 0,
        "source_timestamp_parse_error_count": 0,
        "hourly_partition_mismatch_count": 0,
        "malformed_partition_path_count": 0,
    }
    samples: dict[str, list[str]] = {
        "semantic_errors": [],
        "representation_errors": [],
    }

    files_scanned = 0
    records_scanned = 0
    for path in sorted(input_root.rglob("*.jsonl")):
        files_scanned += 1
        partition = _parse_partition(input_root, path)
        if partition is None:
            representation_errors["malformed_partition_path_count"] += 1
            _append_sample(samples["representation_errors"], f"{path}:0:malformed_partition_path")

        try:
            handle = path.open("r", encoding="utf-8")
        except OSError as exc:
            representation_errors["json_parse_error_count"] += 1
            _append_sample(samples["representation_errors"], f"{path}:0:read_error:{exc}")
            continue
        with handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                records_scanned += 1
                location = f"{path}:{line_number}"
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    representation_errors["json_parse_error_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:json_parse_error:{exc.msg}")
                    continue
                if not isinstance(record, dict):
                    representation_errors["missing_ingest_timestamp_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:record_not_object")
                    continue

                subject_key = record.get("subject_key")
                ingest_raw = record.get("ingest_timestamp_utc")
                if not ingest_raw:
                    representation_errors["missing_ingest_timestamp_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:missing_ingest_timestamp")
                    continue

                try:
                    ingest_ts = _parse_utc_timestamp(ingest_raw)
                except (TypeError, ValueError) as exc:
                    representation_errors["ingest_timestamp_parse_error_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:ingest_timestamp_parse_error:{exc}")
                    continue

                if partition is not None:
                    path_subject, path_date, path_hour = partition
                    if path_subject != subject_key:
                        semantic_errors["subject_partition_mismatch_count"] += 1
                        _append_sample(
                            samples["semantic_errors"],
                            f"{location}:subject_partition_mismatch:path={path_subject}:record={subject_key}",
                        )
                    if path_date != ingest_ts.strftime("%Y-%m-%d") or path_hour != ingest_ts.strftime("%H"):
                        representation_errors["hourly_partition_mismatch_count"] += 1
                        _append_sample(
                            samples["representation_errors"],
                            (
                                f"{location}:hourly_partition_mismatch:"
                                f"path={path_date}/{path_hour}:ingest={ingest_ts.strftime('%Y-%m-%d/%H')}"
                            ),
                        )

                source_raw = record.get("source_timestamp")
                if source_raw is None:
                    continue
                try:
                    source_ts = _parse_utc_timestamp(source_raw)
                except (TypeError, ValueError) as exc:
                    representation_errors["source_timestamp_parse_error_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:source_timestamp_parse_error:{exc}")
                    continue

                future_skew = (source_ts - ingest_ts).total_seconds()
                if future_skew > _allowed_future_skew_seconds(subject_key):
                    semantic_errors["source_timestamp_future_skew_count"] += 1
                    _append_sample(
                        samples["semantic_errors"],
                        f"{location}:source_timestamp_future_skew_seconds={future_skew:.3f}",
                    )

    severity = _severity(semantic_errors, representation_errors, records_scanned)
    status = _status_from_severity(severity)
    return {
        "probe_name": PROBE_NAME,
        "input_root": str(input_root.resolve()),
        "status": status,
        "files_scanned": files_scanned,
        "records_scanned": records_scanned,
        "semantic_errors": semantic_errors,
        "representation_errors": representation_errors,
        "samples": samples,
        "owner_review_blocked": status != "passed",
        "severity": severity,
        "timestamp_rule_verified": False,
        "notes": [
            "需先核对真实 timestamp 生成规则",
            "source_timestamp_unreasonable_backfill_count is reported as 0 because no numeric backfill threshold is defined",
        ],
    }


def _parse_partition(input_root: Path, path: Path) -> tuple[str, str, str] | None:
    relative_parts = path.relative_to(input_root).parts
    if len(relative_parts) < 3:
        return None
    subject_key, date_part, file_name = relative_parts[-3], relative_parts[-2], relative_parts[-1]
    if not file_name.endswith(".jsonl"):
        return None
    hour_part = Path(file_name).stem
    if len(date_part) != 10 or len(hour_part) != 2 or not hour_part.isdigit():
        return None
    return subject_key, date_part, hour_part


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


def _allowed_future_skew_seconds(subject_key: object) -> float:
    subject = "" if subject_key is None else str(subject_key)
    if ".binance." in subject:
        return BINANCE_FUTURE_SKEW_SECONDS
    if ".alchemy." in subject:
        return ALCHEMY_FUTURE_SKEW_SECONDS
    return DEFAULT_FUTURE_SKEW_SECONDS


def _severity(
    semantic_errors: dict[str, int],
    representation_errors: dict[str, int],
    records_scanned: int,
) -> str:
    if (
        representation_errors["json_parse_error_count"] > 0
        or semantic_errors["subject_partition_mismatch_count"] > 0
    ):
        return "P0"
    if records_scanned == 0:
        return "insufficient_evidence"
    if (
        representation_errors["missing_ingest_timestamp_count"] > 0
        or representation_errors["ingest_timestamp_parse_error_count"] > 0
        or representation_errors["source_timestamp_parse_error_count"] > 0
        or representation_errors["hourly_partition_mismatch_count"] > 0
        or representation_errors["malformed_partition_path_count"] > 0
        or semantic_errors["source_timestamp_future_skew_count"] > 0
    ):
        return "P1"
    if semantic_errors["source_timestamp_unreasonable_backfill_count"] > 0:
        return "P2"
    return "none"


def _status_from_severity(severity: str) -> str:
    if severity == "none":
        return "passed"
    if severity == "insufficient_evidence":
        return "insufficient_evidence"
    return "failed"


def _emit_infrastructure_failure(input_root: str | None, note: str) -> int:
    summary = {
        "probe_name": PROBE_NAME,
        "input_root": input_root,
        "status": "failed",
        "files_scanned": 0,
        "records_scanned": 0,
        "semantic_errors": {
            "source_timestamp_future_skew_count": 0,
            "source_timestamp_unreasonable_backfill_count": 0,
            "subject_partition_mismatch_count": 0,
        },
        "representation_errors": {
            "json_parse_error_count": 0,
            "missing_ingest_timestamp_count": 0,
            "ingest_timestamp_parse_error_count": 0,
            "source_timestamp_parse_error_count": 0,
            "hourly_partition_mismatch_count": 0,
            "malformed_partition_path_count": 0,
        },
        "samples": {
            "semantic_errors": [],
            "representation_errors": [],
        },
        "owner_review_blocked": True,
        "severity": "P1",
        "timestamp_rule_verified": False,
        "notes": [note, "需先核对真实 timestamp 生成规则"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 2


def _append_sample(samples: list[str], value: str) -> None:
    if len(samples) < SAMPLE_LIMIT:
        samples.append(value)


if __name__ == "__main__":
    raise SystemExit(main())
