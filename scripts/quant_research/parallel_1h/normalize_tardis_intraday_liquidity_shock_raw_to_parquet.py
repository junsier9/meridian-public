from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from run_tardis_intraday_liquidity_shock_impulse_stage_a import (
    DEFAULT_AS_OF,
    DEFAULT_DATA_TYPES,
    DEFAULT_EVENT_BAR_MINUTES,
    DEFAULT_EXCHANGE,
    DEFAULT_FROM_DATE,
    DEFAULT_SYMBOLS,
    DEFAULT_TO_DATE,
    ROOT,
    aggregate_partitions,
    date_range,
    ensure_outside_repo,
    find_partition,
    load_monthly_universe_mask_scope,
    normalize_symbol_sequence,
    normalized_partition_path,
    parse_iso_date,
    resolve_normalized_root,
    resolve_raw_root,
    sha256_file,
    symbol_list,
    utc_now,
    write_json,
)


CONTRACT_VERSION = "quant_tardis_intraday_liquidity_shock_raw_to_columnar.v1"
RESEARCH_ID = "tardis_intraday_liquidity_shock_impulse_v0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize retained external Tardis raw gzip/CSV partitions into "
            "typed parquet bar features for the intraday liquidity-shock Stage A "
            "proof runner. This script writes data/profiling artifacts only and "
            "does not compute strategy PnL or trading actions."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--to-date", default=DEFAULT_TO_DATE)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument(
        "--raw-staging-manifest",
        type=Path,
        default=None,
        help=(
            "Optional retained raw staging manifest with Tardis source paths and "
            "sha256 lineage. When supplied, the normalizer uses it instead of "
            "rehashing raw gzip partitions for input audit lineage."
        ),
    )
    parser.add_argument(
        "--source-input-audit",
        type=Path,
        default=None,
        help=(
            "Optional retained Stage A raw input audit JSON with source paths and "
            "sha256 hashes. When supplied, the normalizer reuses that lineage "
            "instead of re-hashing every raw gzip partition."
        ),
    )
    parser.add_argument(
        "--monthly-universe-masks",
        type=Path,
        default=None,
        help=(
            "Optional rolling PIT monthly universe masks JSON. When supplied, "
            "only the selected symbol/date pairs in overlapping evaluation "
            "months are normalized."
        ),
    )
    parser.add_argument("--normalized-root", type=Path, default=None)
    parser.add_argument("--event-bar-minutes", type=int, default=DEFAULT_EVENT_BAR_MINUTES)
    parser.add_argument("--chunksize", type=int, default=250_000)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--compression", default="zstd", choices=("zstd", "snappy", "gzip", "brotli", "none"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-partial-days", action="store_true")
    return parser.parse_args()


def _write_frame(path: Path, frame: pd.DataFrame, *, compression: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parquet_compression = None if compression == "none" else compression
    frame.to_parquet(path, index=False, compression=parquet_compression)


def _manifest_paths(normalized_root: Path, as_of: str) -> tuple[Path, Path]:
    manifest_path = normalized_root / "manifests" / f"{as_of}.json"
    latest_path = normalized_root / "latest_manifest.json"
    return manifest_path, latest_path


def _partition_raw_subset(
    found_paths: dict[tuple[str, str, date], Path],
    *,
    symbol: str,
    current_date: date,
) -> dict[tuple[str, str, date], Path]:
    return {
        key: path
        for key, path in found_paths.items()
        if key[0] == symbol and key[2] == current_date
    }


def _raw_types_present(raw_subset: dict[tuple[str, str, date], Path]) -> set[str]:
    return {key[1] for key in raw_subset}


def _required_pairs(symbols: list[str], dates: list[date]) -> list[tuple[str, date]]:
    return [(symbol, current_date) for symbol in symbols for current_date in dates]


def _infer_manifest_exchange(item: dict[str, Any], default_exchange: str) -> str:
    if item.get("exchange"):
        return str(item["exchange"])
    url_path = str(item.get("url_path") or "")
    if "/" in url_path:
        return url_path.split("/", 1)[0]
    return default_exchange


def _empty_raw_audit(
    *,
    exchange: str,
    symbols: list[str],
    dates: list[date],
    required_symbol_dates: list[tuple[str, date]],
) -> dict[str, Any]:
    return {
        "input_kind": "retained_tardis_raw_gzip_csv",
        "exchange": exchange,
        "symbols": symbols,
        "from_date": dates[0].isoformat() if dates else None,
        "to_date": dates[-1].isoformat() if dates else None,
        "required_symbol_date_count": len(required_symbol_dates),
        "expected_partition_count": len(required_symbol_dates) * len(DEFAULT_DATA_TYPES),
        "found_partition_count": 0,
        "missing_partition_count": len(required_symbol_dates) * len(DEFAULT_DATA_TYPES),
        "missing_required_input_fraction": 1.0,
        "found_partitions": [],
        "missing_partition_examples": [],
    }


def _build_raw_input_audit_from_staging_manifest(
    *,
    raw_staging_manifest: Path,
    exchange: str,
    symbols: list[str],
    dates: list[date],
    required_symbol_dates: list[tuple[str, date]],
) -> tuple[dict[str, Any], dict[tuple[str, str, date], Path]]:
    payload = json.loads(raw_staging_manifest.read_text(encoding="utf-8"))
    index: dict[tuple[str, str, date], dict[str, Any]] = {}
    for item in payload.get("partitions", []):
        symbol_values = normalize_symbol_sequence([item.get("symbol")])
        if not symbol_values:
            continue
        try:
            partition_date = parse_iso_date(str(item.get("date")))
        except Exception:
            continue
        data_type = str(item.get("data_type", ""))
        if data_type not in DEFAULT_DATA_TYPES:
            continue
        item_exchange = _infer_manifest_exchange(item, exchange)
        if item_exchange != exchange:
            continue
        index[(symbol_values[0], data_type, partition_date)] = item

    found_paths: dict[tuple[str, str, date], Path] = {}
    found_partitions: list[dict[str, Any]] = []
    missing_examples: list[dict[str, Any]] = []
    for symbol, current_date in required_symbol_dates:
        for data_type in DEFAULT_DATA_TYPES:
            item = index.get((symbol, data_type, current_date))
            path = Path(str(item.get("path"))) if item and item.get("path") else None
            action = str(item.get("action") or "") if item else "missing_from_raw_staging_manifest"
            completed = bool(item.get("completed")) if item else False
            available = bool(
                item
                and completed
                and action != "missing_upstream"
                and path is not None
                and path.exists()
                and path.is_file()
            )
            if available and path is not None:
                found_paths[(symbol, data_type, current_date)] = path
                found_partitions.append(
                    {
                        "exchange": exchange,
                        "symbol": symbol,
                        "data_type": data_type,
                        "date": current_date.isoformat(),
                        "path": str(path),
                        "size_bytes": int(item.get("size_bytes") or path.stat().st_size),
                        "sha256": item.get("sha256"),
                        "source_action": action,
                        "source_manifest": str(raw_staging_manifest),
                    }
                )
            elif len(missing_examples) < 500:
                missing_examples.append(
                    {
                        "symbol": symbol,
                        "data_type": data_type,
                        "date": current_date.isoformat(),
                        "reason": action,
                        "path": str(path) if path is not None else None,
                    }
                )

    expected = len(required_symbol_dates) * len(DEFAULT_DATA_TYPES)
    found = len(found_paths)
    audit = {
        **_empty_raw_audit(
            exchange=exchange,
            symbols=symbols,
            dates=dates,
            required_symbol_dates=required_symbol_dates,
        ),
        "expected_partition_count": expected,
        "found_partition_count": found,
        "missing_partition_count": expected - found,
        "missing_required_input_fraction": float((expected - found) / expected) if expected else 1.0,
        "found_partitions": found_partitions,
        "missing_partition_examples": missing_examples,
        "raw_staging_manifest": str(raw_staging_manifest),
        "raw_staging_manifest_sha256": sha256_file(raw_staging_manifest),
        "raw_source_hashes_reused_from_raw_staging_manifest": True,
        "raw_source_hashes_recorded": bool(found_partitions) and all(
            bool(item.get("sha256")) for item in found_partitions
        ),
    }
    return audit, found_paths


def _build_raw_input_audit_from_raw_root(
    *,
    raw_root: Path,
    exchange: str,
    symbols: list[str],
    dates: list[date],
    required_symbol_dates: list[tuple[str, date]],
) -> tuple[dict[str, Any], dict[tuple[str, str, date], Path]]:
    found_paths: dict[tuple[str, str, date], Path] = {}
    found_partitions: list[dict[str, Any]] = []
    missing_examples: list[dict[str, str]] = []
    for symbol, current_date in required_symbol_dates:
        for data_type in DEFAULT_DATA_TYPES:
            path = find_partition(
                raw_root=raw_root,
                exchange=exchange,
                data_type=data_type,
                symbol=symbol,
                current_date=current_date,
            )
            if path is not None:
                found_paths[(symbol, data_type, current_date)] = path
                stat = path.stat()
                found_partitions.append(
                    {
                        "exchange": exchange,
                        "symbol": symbol,
                        "data_type": data_type,
                        "date": current_date.isoformat(),
                        "path": str(path),
                        "size_bytes": int(stat.st_size),
                        "sha256": sha256_file(path),
                    }
                )
            elif len(missing_examples) < 500:
                missing_examples.append(
                    {
                        "symbol": symbol,
                        "data_type": data_type,
                        "date": current_date.isoformat(),
                    }
                )
    expected = len(required_symbol_dates) * len(DEFAULT_DATA_TYPES)
    found = len(found_paths)
    audit = {
        **_empty_raw_audit(
            exchange=exchange,
            symbols=symbols,
            dates=dates,
            required_symbol_dates=required_symbol_dates,
        ),
        "raw_root": str(raw_root),
        "expected_partition_count": expected,
        "found_partition_count": found,
        "missing_partition_count": expected - found,
        "missing_required_input_fraction": float((expected - found) / expected) if expected else 1.0,
        "found_partitions": found_partitions,
        "missing_partition_examples": missing_examples,
        "raw_source_hashes_reused_from_raw_staging_manifest": False,
        "raw_source_hashes_recorded": bool(found_partitions) and all(
            bool(item.get("sha256")) for item in found_partitions
        ),
    }
    return audit, found_paths


def _normalize_partition_task(task: dict[str, Any]) -> dict[str, Any]:
    symbol = str(task["symbol"])
    current_date = date.fromisoformat(str(task["date"]))
    raw_subset = task["raw_subset"]
    missing_types = list(task["missing_types"])
    partition_path = Path(str(task["partition_path"]))
    allow_partial_days = bool(task["allow_partial_days"])
    overwrite = bool(task["overwrite"])
    compression = str(task["compression"])
    event_bar_minutes = int(task["event_bar_minutes"])
    chunksize = int(task["chunksize"])

    if missing_types and not allow_partial_days:
        return {
            "skipped_partition": {
                "symbol": symbol,
                "date": current_date.isoformat(),
                "reason": "missing_required_raw_types",
                "missing_data_types": missing_types,
            },
            "partition_profile": None,
            "normalized_partition": None,
        }
    if partition_path.exists() and not overwrite:
        stat = partition_path.stat()
        return {
            "normalized_partition": {
                "symbol": symbol,
                "date": current_date.isoformat(),
                "path": str(partition_path),
                "size_bytes": int(stat.st_size),
                "sha256": sha256_file(partition_path),
                "row_count": None,
                "write_mode": "existing_reused",
            },
            "partition_profile": {
                "symbol": symbol,
                "date": current_date.isoformat(),
                "aggregate_seconds": 0.0,
                "write_seconds": 0.0,
                "row_count": None,
                "output_size_bytes": int(stat.st_size),
                "write_mode": "existing_reused",
            },
            "skipped_partition": None,
        }

    partition_started_at = time.perf_counter()
    bars = aggregate_partitions(
        found_paths=raw_subset,
        symbols=[symbol],
        minutes=event_bar_minutes,
        chunksize=chunksize,
    )
    aggregate_seconds = time.perf_counter() - partition_started_at
    if not bars.empty and "bar_start_utc" in bars.columns:
        start_ts = pd.Timestamp(current_date.isoformat(), tz="UTC")
        end_ts = start_ts + pd.Timedelta(days=1)
        bars["bar_start_utc"] = pd.to_datetime(bars["bar_start_utc"], utc=True, errors="coerce")
        bars = bars.loc[
            bars["bar_start_utc"].ge(start_ts) & bars["bar_start_utc"].lt(end_ts)
        ].copy()
        bars = bars.sort_values(["symbol", "bar_start_utc"], kind="mergesort")
        bars = bars.drop_duplicates(["symbol", "bar_start_utc"], keep="last")
    if bars.empty:
        return {
            "skipped_partition": {
                "symbol": symbol,
                "date": current_date.isoformat(),
                "reason": "empty_normalized_bars",
                "missing_data_types": missing_types,
            },
            "partition_profile": {
                "symbol": symbol,
                "date": current_date.isoformat(),
                "aggregate_seconds": round(aggregate_seconds, 6),
                "write_seconds": 0.0,
                "row_count": 0,
            },
            "normalized_partition": None,
        }
    write_started_at = time.perf_counter()
    _write_frame(partition_path, bars, compression=compression)
    write_seconds = time.perf_counter() - write_started_at
    stat = partition_path.stat()
    return {
        "normalized_partition": {
            "symbol": symbol,
            "date": current_date.isoformat(),
            "path": str(partition_path),
            "size_bytes": int(stat.st_size),
            "sha256": sha256_file(partition_path),
            "row_count": int(bars.shape[0]),
            "write_mode": "written",
        },
        "partition_profile": {
            "symbol": symbol,
            "date": current_date.isoformat(),
            "aggregate_seconds": round(aggregate_seconds, 6),
            "write_seconds": round(write_seconds, 6),
            "row_count": int(bars.shape[0]),
            "output_size_bytes": int(stat.st_size),
            "write_mode": "written",
        },
        "skipped_partition": None,
    }


def _load_source_input_audit(
    *,
    source_input_audit: Path,
    exchange: str,
    symbols: list[str],
    dates: list[date],
    required_symbol_dates: list[tuple[str, date]],
) -> tuple[dict[str, Any], dict[tuple[str, str, date], Path]]:
    payload = json.loads(source_input_audit.read_text(encoding="utf-8"))
    required_pair_set = {(symbol, current_date.isoformat()) for symbol, current_date in required_symbol_dates}
    found_paths: dict[tuple[str, str, date], Path] = {}
    found_partitions: list[dict[str, Any]] = []
    missing_or_stale_paths: list[dict[str, str]] = []
    for item in payload.get("found_partitions", []):
        symbol = str(item.get("symbol", "")).upper()
        data_type = str(item.get("data_type", ""))
        partition_date = str(item.get("date", ""))
        if (symbol, partition_date) not in required_pair_set:
            continue
        if data_type not in DEFAULT_DATA_TYPES:
            continue
        path = Path(str(item.get("path", "")))
        if not path.exists():
            missing_or_stale_paths.append(
                {
                    "symbol": symbol,
                    "data_type": data_type,
                    "date": partition_date,
                    "path": str(path),
                }
            )
            continue
        parsed_date = date.fromisoformat(partition_date)
        found_paths[(symbol, data_type, parsed_date)] = path
        found_partitions.append(dict(item))

    expected = len(required_symbol_dates) * len(DEFAULT_DATA_TYPES)
    found = len(found_paths)
    missing_examples: list[dict[str, str]] = []
    for symbol, current_date in required_symbol_dates:
        for data_type in DEFAULT_DATA_TYPES:
            if (symbol, data_type, current_date) not in found_paths and len(missing_examples) < 200:
                missing_examples.append(
                    {
                        "symbol": symbol,
                        "data_type": data_type,
                        "date": current_date.isoformat(),
                    }
                )
    audit = {
        **payload,
        "exchange": exchange,
        "symbols": symbols,
        "from_date": dates[0].isoformat() if dates else None,
        "to_date": dates[-1].isoformat() if dates else None,
        "required_symbol_date_count": len(required_symbol_dates),
        "expected_partition_count": expected,
        "found_partition_count": found,
        "missing_partition_count": expected - found,
        "missing_required_input_fraction": float((expected - found) / expected) if expected else 1.0,
        "found_partitions": found_partitions,
        "missing_partition_examples": missing_examples,
        "missing_or_stale_source_audit_paths": missing_or_stale_paths[:200],
        "source_input_audit_path": str(source_input_audit),
        "source_input_audit_sha256": sha256_file(source_input_audit),
        "raw_source_hashes_reused_from_input_audit": True,
        "raw_source_hashes_recorded": bool(found_partitions) and all(
            bool(item.get("sha256")) for item in found_partitions
        ),
    }
    return audit, found_paths


def main() -> int:
    args = parse_args()
    started_at = time.perf_counter()
    from_date = parse_iso_date(args.from_date)
    to_date = parse_iso_date(args.to_date)
    if to_date < from_date:
        raise SystemExit("--to-date must be >= --from-date")
    if args.event_bar_minutes not in (1, 5, 15):
        raise SystemExit("--event-bar-minutes must be one of 1, 5, 15")

    raw_root = resolve_raw_root(args.raw_root)
    raw_staging_manifest = args.raw_staging_manifest.expanduser().resolve() if args.raw_staging_manifest else None
    source_input_audit = args.source_input_audit.expanduser().resolve() if args.source_input_audit else None
    monthly_universe_masks = args.monthly_universe_masks.expanduser().resolve() if args.monthly_universe_masks else None
    normalized_root = resolve_normalized_root(args.normalized_root)
    ensure_outside_repo(raw_root, label="Tardis raw root")
    if raw_staging_manifest is not None:
        ensure_outside_repo(raw_staging_manifest, label="Tardis raw staging manifest")
    if source_input_audit is not None:
        ensure_outside_repo(source_input_audit, label="Tardis source input audit")
    ensure_outside_repo(normalized_root, label="Tardis normalized parquet root")
    normalized_root.mkdir(parents=True, exist_ok=True)

    monthly_mask_context: dict[str, Any] | None = None
    if monthly_universe_masks is not None:
        (
            monthly_masks_payload,
            required_symbol_dates,
            symbols,
            dates,
            monthly_scope,
        ) = load_monthly_universe_mask_scope(
            monthly_universe_masks,
            from_date=from_date,
            to_date=to_date,
        )
        monthly_mask_context = {
            "monthly_universe_masks_path": str(monthly_universe_masks),
            "monthly_universe_masks_sha256": sha256_file(monthly_universe_masks),
            "monthly_universe_masks_contract_version": monthly_masks_payload.get("contract_version"),
            "monthly_universe_masks_ready": bool(
                monthly_masks_payload.get("stage_a_monthly_universe_masks_ready", True)
            ),
            "monthly_mask_scope": monthly_scope,
            "required_symbol_date_count": len(required_symbol_dates),
            "selected_symbol_count_union": len(symbols),
            "evaluation_month_count": len(monthly_scope),
        }
    else:
        dates = date_range(from_date, to_date)
        symbols = symbol_list(args.symbols)
        required_symbol_dates = _required_pairs(symbols, dates)

    audit_started_at = time.perf_counter()
    if source_input_audit is not None:
        raw_input_audit, found_paths = _load_source_input_audit(
            source_input_audit=source_input_audit,
            exchange=str(args.exchange),
            symbols=symbols,
            dates=dates,
            required_symbol_dates=required_symbol_dates,
        )
    elif raw_staging_manifest is not None:
        raw_input_audit, found_paths = _build_raw_input_audit_from_staging_manifest(
            raw_staging_manifest=raw_staging_manifest,
            exchange=str(args.exchange),
            symbols=symbols,
            dates=dates,
            required_symbol_dates=required_symbol_dates,
        )
    else:
        raw_input_audit, found_paths = _build_raw_input_audit_from_raw_root(
            raw_root=raw_root,
            exchange=str(args.exchange),
            symbols=symbols,
            dates=dates,
            required_symbol_dates=required_symbol_dates,
        )
    raw_input_audit.update(
        {
            "generated_at_utc": utc_now(),
            "as_of": str(args.as_of),
            "raw_scan_executed_by_normalizer": True,
            "raw_source_hashes_reused_from_input_audit": bool(source_input_audit is not None),
            "raw_source_hashes_reused_from_raw_staging_manifest": bool(raw_staging_manifest is not None),
            "monthly_mask_context": monthly_mask_context,
            "downloads_executed_by_normalizer": False,
        }
    )
    audit_seconds = time.perf_counter() - audit_started_at

    normalized_partitions: list[dict[str, Any]] = []
    skipped_partitions: list[dict[str, Any]] = []
    partition_profiles: list[dict[str, Any]] = []
    expected_types = set(DEFAULT_DATA_TYPES)
    normalize_started_at = time.perf_counter()
    tasks: list[dict[str, Any]] = []
    for symbol, current_date in required_symbol_dates:
        raw_subset = _partition_raw_subset(found_paths, symbol=symbol, current_date=current_date)
        types_present = _raw_types_present(raw_subset)
        missing_types = sorted(expected_types - types_present)
        partition_path = normalized_partition_path(
            normalized_root=normalized_root,
            exchange=str(args.exchange),
            symbol=symbol,
            current_date=current_date,
        )
        tasks.append(
            {
                "symbol": symbol,
                "date": current_date.isoformat(),
                "raw_subset": raw_subset,
                "missing_types": missing_types,
                "partition_path": str(partition_path),
                "allow_partial_days": bool(args.allow_partial_days),
                "overwrite": bool(args.overwrite),
                "compression": str(args.compression),
                "event_bar_minutes": int(args.event_bar_minutes),
                "chunksize": int(args.chunksize),
            }
        )
    max_workers = max(1, int(args.max_workers))
    if max_workers == 1:
        results = [_normalize_partition_task(task) for task in tasks]
    else:
        results = []
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_normalize_partition_task, task) for task in tasks]
            for future in as_completed(futures):
                results.append(future.result())
    for result in results:
        normalized_partition = result.get("normalized_partition")
        skipped_partition = result.get("skipped_partition")
        partition_profile = result.get("partition_profile")
        if normalized_partition is not None:
            normalized_partitions.append(normalized_partition)
        if skipped_partition is not None:
            skipped_partitions.append(skipped_partition)
        if partition_profile is not None:
            partition_profiles.append(partition_profile)
    normalized_partitions.sort(key=lambda item: (str(item["symbol"]), str(item["date"])))
    skipped_partitions.sort(key=lambda item: (str(item["symbol"]), str(item["date"]), str(item["reason"])))
    partition_profiles.sort(key=lambda item: (str(item["symbol"]), str(item["date"])))
    normalize_seconds = time.perf_counter() - normalize_started_at

    expected_normalized_count = len(required_symbol_dates)
    manifest_path, latest_path = _manifest_paths(normalized_root, str(args.as_of))
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "input_kind": "retained_tardis_raw_gzip_csv",
        "output_kind": "normalized_parquet_bar_features",
        "raw_root": str(raw_root),
        "raw_staging_manifest": str(raw_staging_manifest) if raw_staging_manifest is not None else None,
        "raw_staging_manifest_sha256": (
            sha256_file(raw_staging_manifest) if raw_staging_manifest is not None and raw_staging_manifest.exists() else None
        ),
        "source_input_audit": str(source_input_audit) if source_input_audit is not None else None,
        "normalized_root": str(normalized_root),
        "exchange": str(args.exchange),
        "symbols": symbols,
        "monthly_mask_context": monthly_mask_context,
        "required_symbol_date_count": len(required_symbol_dates),
        "data_types": list(DEFAULT_DATA_TYPES),
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "effective_from_date": dates[0].isoformat() if dates else None,
        "effective_to_date": dates[-1].isoformat() if dates else None,
        "event_bar_minutes": int(args.event_bar_minutes),
        "max_workers": max_workers,
        "expected_normalized_partition_count": expected_normalized_count,
        "normalized_partition_count": len(normalized_partitions),
        "skipped_normalized_partition_count": len(skipped_partitions),
        "normalized_missing_required_input_fraction": (
            float((expected_normalized_count - len(normalized_partitions)) / expected_normalized_count)
            if expected_normalized_count
            else 1.0
        ),
        "raw_input_audit": raw_input_audit,
        "source_raw_partitions": raw_input_audit["found_partitions"],
        "normalized_partitions": normalized_partitions,
        "skipped_partitions": skipped_partitions[:500],
        "partition_profiles": partition_profiles,
        "profile": {
            "raw_input_audit_seconds": round(audit_seconds, 6),
            "normalize_and_write_seconds": round(normalize_seconds, 6),
            "total_seconds_before_manifest": round(time.perf_counter() - started_at, 6),
            "max_workers": max_workers,
        },
        "raw_source_hashes_reused_from_input_audit": bool(source_input_audit is not None),
        "raw_source_hashes_reused_from_raw_staging_manifest": bool(raw_staging_manifest is not None),
        "downloads_executed_by_normalizer": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
    }
    write_json(manifest_path, manifest)
    latest_payload = {**manifest, "canonical_manifest_path": str(manifest_path)}
    write_json(latest_path, latest_payload)
    print(
        json.dumps(
            {
                "status": "normalized_parquet_written",
                "manifest_json": str(manifest_path),
                "latest_manifest_json": str(latest_path),
                "expected_normalized_partition_count": expected_normalized_count,
                "normalized_partition_count": len(normalized_partitions),
                "skipped_normalized_partition_count": len(skipped_partitions),
                "monthly_mask_mode": monthly_mask_context is not None,
                "required_symbol_date_count": len(required_symbol_dates),
                "max_workers": max_workers,
                "raw_missing_required_input_fraction": raw_input_audit["missing_required_input_fraction"],
                "normalized_missing_required_input_fraction": manifest[
                    "normalized_missing_required_input_fraction"
                ],
                "stage_a_proof_computed": False,
                "stage_b_return_ablation_allowed": False,
                "strategy_pnl_computed": False,
                "trading_action_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
