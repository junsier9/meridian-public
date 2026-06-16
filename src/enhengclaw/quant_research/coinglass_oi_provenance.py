from __future__ import annotations

import csv
from datetime import UTC, datetime
import gzip
import os
from pathlib import Path
from typing import Any

import pandas as pd


EXCHANGE = "binance"
MARKET_TYPE = "usdm_perp"
DEFAULT_EXTERNAL_ROOT_NAME = "market_history\\coinglass_oi_provenance"
SUPPORTED_INTERVALS = ("1h", "4h", "1d")
SOURCE_INTERVAL = "1h"
CSV_HEADERS = (
    "exchange",
    "market_type",
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "open_interest_value",
    "open_interest_value_native_usd",
    "open_interest_coin",
    "binance_perp_close",
    "open_interest_value_derived_usd",
    "derived_native_rel_diff",
    "derived_native_formula_status",
    "oi_value_provenance",
    "price_source_for_derived_value",
    "source",
)


def resolve_external_oi_provenance_root(
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


def load_oi_provenance_rows(
    *,
    external_root: Path | None = None,
    symbol: str,
    interval: str,
    base_env: dict[str, str] | None = None,
    start_time_ms: int | None = None,
) -> list[dict[str, str]]:
    resolved_root = resolve_external_oi_provenance_root(external_root=external_root, base_env=base_env)
    root = _interval_root(external_root=resolved_root, symbol=symbol, interval=interval)
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for partition_path in sorted(root.glob("*.csv.gz")):
        rows.extend(_read_partition(partition_path))
    if start_time_ms is not None:
        rows = [row for row in rows if int(row["open_time_ms"]) >= int(start_time_ms)]
    rows.sort(key=lambda item: int(item["open_time_ms"]))
    return rows


def load_oi_provenance_frame(
    *,
    symbol: str,
    interval: str,
    external_root: Path | None = None,
    end_time_ms: int,
    base_env: dict[str, str] | None = None,
    start_time_ms: int | None = None,
) -> pd.DataFrame:
    resolved_interval = _canonical_interval(interval)
    rows = load_oi_provenance_rows(
        external_root=external_root,
        symbol=symbol,
        interval=resolved_interval,
        base_env=base_env,
        start_time_ms=start_time_ms,
    )
    source_interval = resolved_interval
    if not rows and resolved_interval != SOURCE_INTERVAL:
        rows = load_oi_provenance_rows(
            external_root=external_root,
            symbol=symbol,
            interval=SOURCE_INTERVAL,
            base_env=base_env,
            start_time_ms=start_time_ms,
        )
        source_interval = SOURCE_INTERVAL
    if not rows:
        return pd.DataFrame()
    frame = _normalize_frame(pd.DataFrame(rows), source_interval=source_interval)
    frame = frame.loc[frame["open_time_ms"] <= int(end_time_ms)].copy()
    if frame.empty:
        return frame
    if source_interval != resolved_interval:
        frame = _aggregate_native_value_frame(
            frame=frame,
            target_interval=resolved_interval,
            source_interval=source_interval,
        )
        frame = frame.loc[frame["open_time_ms"] <= int(end_time_ms)].copy()
    frame.sort_values("open_time_ms", inplace=True)
    return frame.reset_index(drop=True)


def _interval_root(*, external_root: Path, symbol: str, interval: str) -> Path:
    return external_root / MARKET_TYPE / str(symbol).strip().upper() / _canonical_interval(interval)


def _read_partition(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _canonical_interval(interval: str) -> str:
    normalized = str(interval).strip()
    if normalized not in SUPPORTED_INTERVALS:
        raise ValueError(f"unsupported CoinGlass OI provenance interval: {interval}")
    return normalized


def _interval_to_ms(interval: str) -> int:
    canonical = _canonical_interval(interval)
    if canonical == "1h":
        return 3_600_000
    if canonical == "4h":
        return 14_400_000
    return 86_400_000


def _normalize_frame(frame: pd.DataFrame, *, source_interval: str) -> pd.DataFrame:
    working = frame.copy()
    for column in (
        "open_time_ms",
        "close_time_ms",
        "open_interest_value",
        "open_interest_value_native_usd",
        "open_interest_coin",
        "binance_perp_close",
        "open_interest_value_derived_usd",
        "derived_native_rel_diff",
    ):
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")
    if "open_interest_value_native_usd" not in working.columns:
        working["open_interest_value_native_usd"] = pd.NA
    if "open_interest_value" not in working.columns:
        working["open_interest_value"] = pd.NA
    provenance = (
        working["oi_value_provenance"].astype("string")
        if "oi_value_provenance" in working.columns
        else pd.Series("", index=working.index, dtype="string")
    )
    native_value = pd.to_numeric(working["open_interest_value_native_usd"], errors="coerce")
    legacy_native_value = pd.to_numeric(working["open_interest_value"], errors="coerce").where(
        provenance.eq("native_usd")
    )
    working["open_interest_value_native_usd"] = native_value.combine_first(legacy_native_value)
    working["open_interest_value"] = working["open_interest_value_native_usd"]
    working["open_interest_value_provider"] = "coinglass_native_usd"
    working["open_interest_value_source"] = "coinglass_oi_provenance_sidecar"
    working["open_interest_value_source_interval"] = str(source_interval)
    working["open_interest_value_canonical_policy"] = "native_usd_only"
    working["open_interest_value_sample_count"] = working["open_interest_value"].notna().astype("int64")
    working["source"] = (
        working["source"].where(working["source"].astype("string").str.len().gt(0), "coinglass_open_interest_history")
        if "source" in working.columns
        else "coinglass_open_interest_history"
    )
    return working


def _aggregate_native_value_frame(
    *,
    frame: pd.DataFrame,
    target_interval: str,
    source_interval: str,
) -> pd.DataFrame:
    target_ms = _interval_to_ms(target_interval)
    working = frame.copy()
    working["bucket_open_ms"] = (working["open_time_ms"].astype("int64") // target_ms) * target_ms
    records: list[dict[str, Any]] = []
    for bucket_open_ms, group in working.groupby("bucket_open_ms", sort=True):
        group = group.sort_values("open_time_ms")
        valid = group.loc[pd.to_numeric(group["open_interest_value"], errors="coerce").notna()].copy()
        selected = valid.iloc[-1] if not valid.empty else group.iloc[-1]
        formula_statuses = {
            str(item)
            for item in group.get("derived_native_formula_status", pd.Series(dtype="object")).dropna().tolist()
            if str(item).strip()
        }
        if "fail" in formula_statuses:
            formula_status = "fail"
        elif "pass" in formula_statuses:
            formula_status = "pass"
        else:
            formula_status = ""
        max_rel_diff = pd.to_numeric(group.get("derived_native_rel_diff"), errors="coerce").max()
        record = selected.to_dict()
        record["open_time_ms"] = int(bucket_open_ms)
        record["close_time_ms"] = int(bucket_open_ms) + target_ms - 1
        record["interval"] = target_interval
        record["open_interest_value"] = selected.get("open_interest_value")
        record["open_interest_value_native_usd"] = selected.get("open_interest_value_native_usd")
        record["open_interest_value_source_interval"] = source_interval
        record["open_interest_value_sample_count"] = int(len(valid))
        record["derived_native_formula_status"] = formula_status
        record["derived_native_rel_diff"] = None if pd.isna(max_rel_diff) else float(max_rel_diff)
        records.append(record)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame.from_records(records)


def utc_from_ms(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")
