from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


PROBE_NAME = "event_id_corpus_probe"
SAMPLE_LIMIT = 20
REQUIRED_FIELDS = {
    "subject_key",
    "provider_id",
    "event_type",
    "raw_payload",
    "schema_version",
    "event_id",
}


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
    if not args.verify_generator_rule:
        return _emit_infrastructure_failure(
            input_root=args.input_root,
            note="--verify-generator-rule is required",
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
    parser.add_argument("--verify-generator-rule", action="store_true")
    return parser.parse_known_args(argv)


def _scan(input_root: Path) -> dict[str, Any]:
    semantic_errors = {
        "event_id_mismatch_count": 0,
        "event_id_collision_count": 0,
    }
    representation_errors = {
        "json_parse_error_count": 0,
        "missing_required_field_count": 0,
        "malformed_event_id_prefix_count": 0,
    }
    samples: dict[str, list[str]] = {
        "event_id_mismatch": [],
        "event_id_collision": [],
        "representation_errors": [],
    }
    payload_to_event_ids: dict[str, set[str]] = defaultdict(set)
    event_id_to_payloads: dict[str, set[str]] = defaultdict(set)
    payload_locations: dict[str, list[str]] = defaultdict(list)
    event_id_locations: dict[str, list[str]] = defaultdict(list)

    files_scanned = 0
    records_scanned = 0
    for path in sorted(input_root.rglob("*.jsonl")):
        files_scanned += 1
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
                if not isinstance(record, dict) or not REQUIRED_FIELDS.issubset(record):
                    representation_errors["missing_required_field_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:missing_required_field")
                    continue

                event_id = record["event_id"]
                if not isinstance(event_id, str) or not event_id.startswith("sha256:"):
                    representation_errors["malformed_event_id_prefix_count"] += 1
                    _append_sample(samples["representation_errors"], f"{location}:malformed_event_id_prefix")
                    continue

                payload_key = _canonical_payload_key(record)
                payload_to_event_ids[payload_key].add(event_id)
                event_id_to_payloads[event_id].add(payload_key)
                _append_sample(payload_locations[payload_key], location)
                _append_sample(event_id_locations[event_id], location)

    for payload_key, event_ids in payload_to_event_ids.items():
        if len(event_ids) > 1:
            semantic_errors["event_id_mismatch_count"] += 1
            _append_sample(
                samples["event_id_mismatch"],
                f"{payload_key}:event_ids={sorted(event_ids)}:locations={payload_locations[payload_key]}",
            )

    for event_id, payload_keys in event_id_to_payloads.items():
        if len(payload_keys) > 1:
            semantic_errors["event_id_collision_count"] += 1
            _append_sample(
                samples["event_id_collision"],
                f"{event_id}:payload_keys={sorted(payload_keys)}:locations={event_id_locations[event_id]}",
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
        "generator_rule_verified": False,
        "notes": ["需先核对真实 event_id 生成规则"],
    }


def _canonical_payload_key(record: dict[str, Any]) -> str:
    canonical_payload = json.dumps(
        {
            "provider_id": record["provider_id"],
            "event_type": record["event_type"],
            "raw_payload": record["raw_payload"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _severity(
    semantic_errors: dict[str, int],
    representation_errors: dict[str, int],
    records_scanned: int,
) -> str:
    if (
        semantic_errors["event_id_collision_count"] > 0
        or representation_errors["json_parse_error_count"] > 0
    ):
        return "P0"
    if records_scanned == 0:
        return "insufficient_evidence"
    if (
        semantic_errors["event_id_mismatch_count"] > 0
        or representation_errors["missing_required_field_count"] > 0
        or representation_errors["malformed_event_id_prefix_count"] > 0
    ):
        return "P1"
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
            "event_id_mismatch_count": 0,
            "event_id_collision_count": 0,
        },
        "representation_errors": {
            "json_parse_error_count": 0,
            "missing_required_field_count": 0,
            "malformed_event_id_prefix_count": 0,
        },
        "samples": {
            "event_id_mismatch": [],
            "event_id_collision": [],
            "representation_errors": [],
        },
        "owner_review_blocked": True,
        "severity": "P1",
        "generator_rule_verified": False,
        "notes": [note, "需先核对真实 event_id 生成规则"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 2


def _append_sample(samples: list[str], value: str) -> None:
    if len(samples) < SAMPLE_LIMIT:
        samples.append(value)


if __name__ == "__main__":
    raise SystemExit(main())
