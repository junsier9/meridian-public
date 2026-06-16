from __future__ import annotations

import csv
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
from typing import Any, Iterable

from enhengclaw.ops.evidence_contracts import with_evidence_metadata


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_FAMILY = "m3_2_ethereum_address_labels_sync"
CONTRACT_VERSION = "m3_2_ethereum_address_labels_sync.v1"
DEFAULT_EXTERNAL_ROOT_NAME = "onchain_address_labels_ethereum"
DEFAULT_CHAIN = "ethereum"
DEFAULT_SEED_LABEL_PATH = ROOT / "config" / "quant_research" / "onchain_address_labels" / "ethereum_seed_labels.csv"
SUPPORTED_ENTITY_TYPES = ("exchange", "bridge", "treasury", "issuer", "unknown")
SNAPSHOT_HEADERS = (
    "address",
    "chain",
    "entity_type",
    "entity_name",
    "label_source",
    "label_confidence",
    "as_of_date_utc",
)


def resolve_onchain_address_label_root(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    env = os.environ if base_env is None else base_env
    localappdata = str(env.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()
    return (Path.home() / ".local" / "share" / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()


def default_seed_label_path() -> Path:
    return DEFAULT_SEED_LABEL_PATH


def sync_ethereum_address_labels(
    *,
    as_of_date: date | None = None,
    external_root: Path | None = None,
    import_csv_paths: Iterable[Path] | None = None,
    include_seed: bool = True,
    report_path: Path | None = None,
) -> dict[str, Any]:
    target_date = as_of_date or datetime.now(UTC).date()
    resolved_root = resolve_onchain_address_label_root(external_root=external_root)
    resolved_root.mkdir(parents=True, exist_ok=True)

    raw_records: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    if include_seed:
        seed_path = default_seed_label_path()
        if seed_path.exists():
            parsed_rows, parser_summary = _load_records_from_path(
                seed_path,
                fallback_as_of_date=target_date,
                default_label_source="manual_seed",
            )
            raw_records.extend(parsed_rows)
            inputs.append(
                {
                    "path": str(seed_path),
                    "format": parser_summary["format"],
                    "loaded_row_count": len(parsed_rows),
                    "skipped_row_count": int(parser_summary["skipped_row_count"]),
                }
            )
        else:
            inputs.append(
                {
                    "path": str(seed_path),
                    "format": "missing_seed",
                    "loaded_row_count": 0,
                    "skipped_row_count": 0,
                }
            )

    for path_like in import_csv_paths or ():
        import_path = Path(path_like).expanduser().resolve()
        parsed_rows, parser_summary = _load_records_from_path(
            import_path,
            fallback_as_of_date=target_date,
            default_label_source=f"import_csv:{import_path.stem}",
        )
        raw_records.extend(parsed_rows)
        inputs.append(
            {
                "path": str(import_path),
                "format": parser_summary["format"],
                "loaded_row_count": len(parsed_rows),
                "skipped_row_count": int(parser_summary["skipped_row_count"]),
            }
        )

    snapshot_rows = _select_snapshot_rows(records=raw_records, as_of_date=target_date)
    latest_snapshot_path = resolved_root / "latest_snapshot.csv"
    dated_snapshot_path = resolved_root / "snapshots" / f"address_labels_{target_date.isoformat()}.csv"
    _write_snapshot_rows(output_path=latest_snapshot_path, rows=snapshot_rows)
    _write_snapshot_rows(output_path=dated_snapshot_path, rows=snapshot_rows)

    entity_type_counts = _count_values(snapshot_rows, "entity_type")
    label_source_counts = _count_values(snapshot_rows, "label_source")
    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": _utc_now(),
            "external_root": str(resolved_root),
            "as_of_date_utc": target_date.isoformat(),
            "input_count": len(inputs),
            "inputs": inputs,
            "raw_record_count": len(raw_records),
            "snapshot_record_count": len(snapshot_rows),
            "entity_type_counts": entity_type_counts,
            "label_source_counts": label_source_counts,
            "latest_snapshot_path": str(latest_snapshot_path),
            "dated_snapshot_path": str(dated_snapshot_path),
            "upstream_versions": {
                "default_seed_label_path": str(default_seed_label_path()),
                "supported_entity_types": list(SUPPORTED_ENTITY_TYPES),
            },
        },
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    latest_summary_path = resolved_root / "latest_sync_summary.json"
    latest_summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["latest_summary_path"] = str(latest_summary_path)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["report_path"] = str(report_path)
    return summary


def load_address_label_snapshot(
    *,
    as_of_date: date | None = None,
    external_root: Path | None = None,
    snapshot_path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    target_date = as_of_date or datetime.now(UTC).date()
    resolved_root = resolve_onchain_address_label_root(external_root=external_root)
    resolved_path = _resolve_snapshot_path(
        external_root=resolved_root,
        snapshot_path=snapshot_path,
        as_of_date=target_date,
    )
    if resolved_path is None or not resolved_path.exists():
        metadata = {
            "available": False,
            "as_of_date_utc": target_date.isoformat(),
            "snapshot_path": None,
            "record_count": 0,
            "entity_type_counts": {},
            "label_source_counts": {},
        }
        return {}, metadata

    parsed_rows, parser_summary = _load_records_from_path(
        resolved_path,
        fallback_as_of_date=target_date,
        default_label_source=f"snapshot:{resolved_path.stem}",
    )
    snapshot_rows = _select_snapshot_rows(records=parsed_rows, as_of_date=target_date)
    snapshot = {str(row["address"]): dict(row) for row in snapshot_rows}
    metadata = {
        "available": True,
        "as_of_date_utc": target_date.isoformat(),
        "snapshot_path": str(resolved_path),
        "record_count": len(snapshot_rows),
        "entity_type_counts": _count_values(snapshot_rows, "entity_type"),
        "label_source_counts": _count_values(snapshot_rows, "label_source"),
        "format": parser_summary["format"],
    }
    return snapshot, metadata


def _resolve_snapshot_path(
    *,
    external_root: Path,
    snapshot_path: Path | None,
    as_of_date: date,
) -> Path | None:
    if snapshot_path is not None:
        resolved = snapshot_path.expanduser().resolve()
        return resolved if resolved.exists() else None
    snapshots_dir = external_root / "snapshots"
    candidates = sorted(snapshots_dir.glob("address_labels_*.csv")) if snapshots_dir.exists() else []
    selected: Path | None = None
    selected_date: date | None = None
    for candidate in candidates:
        suffix = candidate.stem.replace("address_labels_", "", 1)
        try:
            candidate_date = date.fromisoformat(suffix)
        except ValueError:
            continue
        if candidate_date > as_of_date:
            continue
        if selected_date is None or candidate_date > selected_date:
            selected = candidate
            selected_date = candidate_date
    if selected is not None:
        return selected
    latest_snapshot = external_root / "latest_snapshot.csv"
    return latest_snapshot if latest_snapshot.exists() else None


def _load_records_from_path(
    source_path: Path,
    *,
    fallback_as_of_date: date,
    default_label_source: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not source_path.exists():
        raise FileNotFoundError(f"address-label input does not exist: {source_path}")
    with source_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = {str(name).strip().lower() for name in (reader.fieldnames or []) if name}
        rows = [dict(row) for row in reader]
    if _looks_like_snapshot_schema(fieldnames):
        parsed_rows, skipped = _parse_snapshot_rows(
            rows,
            fallback_as_of_date=fallback_as_of_date,
            default_label_source=default_label_source,
        )
        return parsed_rows, {"format": "snapshot_schema", "skipped_row_count": skipped}
    if _looks_like_etherscan_metadata_schema(fieldnames):
        parsed_rows, skipped = _parse_etherscan_metadata_rows(
            rows,
            fallback_as_of_date=fallback_as_of_date,
            default_label_source=default_label_source,
        )
        return parsed_rows, {"format": "etherscan_metadata_csv", "skipped_row_count": skipped}
    raise ValueError(f"unsupported address-label CSV schema: {source_path}")


def _looks_like_snapshot_schema(fieldnames: set[str]) -> bool:
    required = {"address", "chain", "entity_type", "entity_name"}
    return required.issubset(fieldnames)


def _looks_like_etherscan_metadata_schema(fieldnames: set[str]) -> bool:
    required = {"address", "nametag", "labels"}
    return required.issubset(fieldnames)


def _parse_snapshot_rows(
    rows: list[dict[str, Any]],
    *,
    fallback_as_of_date: date,
    default_label_source: str,
) -> tuple[list[dict[str, Any]], int]:
    parsed_rows: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        address = _canonicalize_address(row.get("address"))
        if not address:
            skipped += 1
            continue
        chain = str(row.get("chain") or DEFAULT_CHAIN).strip().lower() or DEFAULT_CHAIN
        if chain != DEFAULT_CHAIN:
            skipped += 1
            continue
        entity_name = str(row.get("entity_name") or "").strip()
        if not entity_name:
            skipped += 1
            continue
        parsed_rows.append(
            {
                "address": address,
                "chain": chain,
                "entity_type": _normalize_entity_type(row.get("entity_type")),
                "entity_name": entity_name,
                "label_source": str(row.get("label_source") or default_label_source).strip() or default_label_source,
                "label_confidence": _coerce_confidence(row.get("label_confidence"), default_value=0.8),
                "as_of_date_utc": _coerce_as_of_date(row.get("as_of_date_utc"), fallback_as_of_date).isoformat(),
            }
        )
    return parsed_rows, skipped


def _parse_etherscan_metadata_rows(
    rows: list[dict[str, Any]],
    *,
    fallback_as_of_date: date,
    default_label_source: str,
) -> tuple[list[dict[str, Any]], int]:
    parsed_rows: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        address = _canonicalize_address(row.get("address"))
        if not address:
            skipped += 1
            continue
        entity_name = (
            str(row.get("nametag") or "").strip()
            or str(row.get("internal_nametag") or "").strip()
            or address
        )
        entity_type = _infer_entity_type_from_etherscan_row(row)
        label_confidence = 0.9 if entity_type != "unknown" else 0.5
        parsed_rows.append(
            {
                "address": address,
                "chain": DEFAULT_CHAIN,
                "entity_type": entity_type,
                "entity_name": entity_name,
                "label_source": str(row.get("label_source") or default_label_source).strip() or default_label_source,
                "label_confidence": label_confidence,
                "as_of_date_utc": _coerce_etherscan_as_of_date(row, fallback_as_of_date).isoformat(),
            }
        )
    return parsed_rows, skipped


def _select_snapshot_rows(*, records: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in records:
        row_date = _coerce_as_of_date(row.get("as_of_date_utc"), as_of_date)
        if row_date > as_of_date:
            continue
        address = str(row["address"])
        candidate = dict(row)
        candidate["as_of_date_utc"] = row_date.isoformat()
        existing = selected.get(address)
        if existing is None:
            selected[address] = candidate
            continue
        if _record_rank(candidate) > _record_rank(existing):
            selected[address] = candidate
    snapshot_rows = list(selected.values())
    snapshot_rows.sort(key=lambda row: (str(row["entity_type"]), str(row["entity_name"]), str(row["address"])))
    return snapshot_rows


def _record_rank(row: dict[str, Any]) -> tuple[date, float, int]:
    row_date = _coerce_as_of_date(row.get("as_of_date_utc"), datetime.now(UTC).date())
    confidence = _coerce_confidence(row.get("label_confidence"), default_value=0.0)
    known = 0 if str(row.get("entity_type") or "unknown") == "unknown" else 1
    return row_date, confidence, known


def _infer_entity_type_from_etherscan_row(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("nametag") or ""),
        str(row.get("internal_nametag") or ""),
        str(row.get("labels") or ""),
        str(row.get("labels_slug") or ""),
        str(row.get("url") or ""),
    ]
    haystack = " ".join(parts).strip().lower()
    if "bridge" in haystack:
        return "bridge"
    if "exchange" in haystack or any(
        keyword in haystack
        for keyword in ("coinbase", "binance", "kraken", "bybit", "kucoin", "okx", "bitfinex", "htx", "gate")
    ):
        return "exchange"
    if "issuer" in haystack:
        return "issuer"
    if "treasury" in haystack or "foundation" in haystack:
        return "treasury"
    return "unknown"


def _write_snapshot_rows(*, output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in SNAPSHOT_HEADERS})


def _count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "").strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _canonicalize_address(value: Any) -> str | None:
    candidate = str(value or "").strip().lower()
    if not candidate.startswith("0x") or len(candidate) != 42:
        return None
    try:
        int(candidate[2:], 16)
    except ValueError:
        return None
    return candidate


def _normalize_entity_type(value: Any) -> str:
    candidate = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if candidate in SUPPORTED_ENTITY_TYPES:
        return candidate
    if "exchange" in candidate:
        return "exchange"
    if "bridge" in candidate:
        return "bridge"
    if "issuer" in candidate:
        return "issuer"
    if "treasury" in candidate or "foundation" in candidate:
        return "treasury"
    return "unknown"


def _coerce_confidence(value: Any, *, default_value: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default_value
    return max(0.0, min(1.0, confidence))


def _coerce_as_of_date(value: Any, default_value: date) -> date:
    text = str(value or "").strip()
    if not text:
        return default_value
    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return default_value


def _coerce_etherscan_as_of_date(row: dict[str, Any], default_value: date) -> date:
    raw_timestamp = str(row.get("lastupdatedtimestamp") or "").strip()
    if raw_timestamp:
        try:
            return datetime.fromtimestamp(int(raw_timestamp), tz=UTC).date()
        except (TypeError, ValueError, OSError):
            return default_value
    return default_value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
