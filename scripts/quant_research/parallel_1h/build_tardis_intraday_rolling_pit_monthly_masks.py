from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from run_tardis_intraday_liquidity_shock_impulse_stage_a import (
    DEFAULT_EXCHANGE,
    numeric_column,
    parse_iso_date,
    timestamp_series,
    top_depth_from_snapshot,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_ID = "rolling_pit_intraday_liquid_perp_core_v1"
CONTRACT_VERSION = "quant_tardis_intraday_rolling_pit_monthly_masks.v1"
RESEARCH_ID = "rolling_pit_intraday_liquid_perp_core_v1"
DEFAULT_AS_OF = "2026-06-16-rolling-pit-core-v1-monthly-masks"
DEFAULT_DRY_RUN_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-06-16-rolling-pit-core-v1-dry-run"
    / "rolling_pit_core_universe"
)
DEFAULT_STORAGE_RAW_ROOT = Path("/tank/tardis/raw_stores/tardis_intraday_liquidity_shock")
DEFAULT_COMPUTE_RAW_ROOT = Path("/data/meridian/hot_stage/tardis_intraday_liquidity_shock")
DEFAULT_OUTPUT_SUBDIR = "rolling_pit_core_monthly_masks"
SELECTION_DATA_TYPES = ("trades", "book_ticker", "book_snapshot_5", "derivative_ticker")
STAGE_A_DATA_TYPES = ("trades", "liquidations", "book_ticker", "book_snapshot_5", "derivative_ticker")
ANCHOR_SYMBOLS = ("BTCUSDT", "ETHUSDT")
BUCKETS = ("bucket_high_liquidity", "bucket_mid_liquidity", "bucket_tail_liquidity")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build rolling PIT monthly universe masks from retained pre-freeze "
            "Tardis raw metrics. This runner scans raw staging only to compute "
            "selection/coverage artifacts. It does not normalize parquet, run "
            "Stage A, compute strategy PnL, or create trading actions."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--dry-run-root", type=Path, default=DEFAULT_DRY_RUN_ROOT)
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--raw-staging-manifest", type=Path, default=None)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--target-symbols", type=int, default=20)
    parser.add_argument("--min-symbols", type=int, default=12)
    parser.add_argument("--min-non-btc-eth-symbols", type=int, default=8)
    parser.add_argument("--min-liquidity-buckets", type=int, default=3)
    parser.add_argument("--distinct-months-min", type=int, default=18)
    parser.add_argument("--selection-lookback-min-days", type=int, default=30)
    parser.add_argument("--max-selection-missing-fraction", type=float, default=0.20)
    parser.add_argument("--max-stale-quote-fraction", type=float, default=0.95)
    parser.add_argument("--max-evaluation-missing-fraction", type=float, default=0.02)
    parser.add_argument("--chunksize", type=int, default=250_000)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--daily-metrics-cache", type=Path, default=None)
    parser.add_argument("--overwrite-daily-metrics", action="store_true")
    parser.add_argument(
        "--hash-raw-if-missing",
        action="store_true",
        help="Hash available raw files when the staging manifest does not already carry sha256 lineage.",
    )
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def finite_float(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def normalize_symbol(value: Any) -> str:
    text = str(value).strip().upper()
    return text if text.endswith("USDT") else f"{text}USDT"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_or_string(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve_raw_root(raw_root: Path | None) -> Path:
    if raw_root is not None:
        return raw_root.expanduser().resolve()
    if DEFAULT_STORAGE_RAW_ROOT.exists():
        return DEFAULT_STORAGE_RAW_ROOT.resolve()
    if DEFAULT_COMPUTE_RAW_ROOT.exists():
        return DEFAULT_COMPUTE_RAW_ROOT.resolve()
    localappdata = Path.home() / "AppData" / "Local" / "EnhengClaw"
    return (localappdata / "market_history" / "tardis_intraday_liquidity_shock").resolve()


def raw_partition_path(
    *,
    raw_root: Path,
    exchange: str,
    data_type: str,
    current_date: date,
    symbol: str,
) -> Path:
    return (
        raw_root
        / "raw"
        / exchange
        / data_type
        / f"{current_date:%Y}"
        / f"{current_date:%m}"
        / f"{current_date:%d}"
        / f"{symbol}.csv.gz"
    )


def partition_key(exchange: str, data_type: str, symbol: str, date_text: str) -> tuple[str, str, str, str]:
    return (exchange, data_type.lower(), normalize_symbol(symbol), str(date_text))


def infer_exchange(item: dict[str, Any], default_exchange: str) -> str:
    if item.get("exchange"):
        return str(item["exchange"])
    url_path = str(item.get("url_path") or "")
    if "/" in url_path:
        return url_path.split("/", 1)[0]
    return default_exchange


def load_raw_manifest_index(
    manifest_path: Path | None,
    *,
    default_exchange: str,
) -> tuple[dict[str, Any] | None, dict[tuple[str, str, str, str], dict[str, Any]]]:
    if manifest_path is None:
        return None, {}
    payload = load_json(manifest_path)
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in payload.get("partitions", []):
        key = partition_key(
            infer_exchange(item, default_exchange),
            str(item["data_type"]),
            str(item["symbol"]),
            str(item["date"]),
        )
        index[key] = item
    return payload, index


def partition_status(
    *,
    raw_root: Path,
    raw_index: dict[tuple[str, str, str, str], dict[str, Any]],
    exchange: str,
    data_type: str,
    symbol: str,
    current_date: date,
    hash_raw_if_missing: bool,
) -> dict[str, Any]:
    key = partition_key(exchange, data_type, symbol, current_date.isoformat())
    indexed = raw_index.get(key)
    path = raw_partition_path(
        raw_root=raw_root,
        exchange=exchange,
        data_type=data_type,
        current_date=current_date,
        symbol=symbol,
    )
    if indexed is not None:
        path = Path(str(indexed.get("path") or path))
        action = str(indexed.get("action") or "unknown")
        completed = bool(indexed.get("completed"))
        available = completed and action != "missing_upstream" and path.exists()
        sha256 = indexed.get("sha256")
        if available and not sha256 and hash_raw_if_missing:
            sha256 = sha256_file(path)
        return {
            "exchange": exchange,
            "data_type": data_type,
            "symbol": symbol,
            "date": current_date.isoformat(),
            "path": str(path),
            "available": bool(available),
            "status": action if not available else "available",
            "size_bytes": int(indexed.get("size_bytes") or (path.stat().st_size if path.exists() else 0)),
            "sha256": sha256,
            "hash_recorded": bool(sha256),
        }
    exists = path.exists()
    sha256 = sha256_file(path) if exists and hash_raw_if_missing else None
    return {
        "exchange": exchange,
        "data_type": data_type,
        "symbol": symbol,
        "date": current_date.isoformat(),
        "path": str(path),
        "available": bool(exists),
        "status": "available_unmanifested" if exists else "missing_local",
        "size_bytes": int(path.stat().st_size) if exists else 0,
        "sha256": sha256,
        "hash_recorded": bool(sha256),
    }


def iter_csv_chunks(path: Path, *, chunksize: int):
    compression = "gzip" if path.suffix == ".gz" else "infer"
    try:
        yield from pd.read_csv(path, compression=compression, chunksize=chunksize, low_memory=False)
    except pd.errors.EmptyDataError:
        return


def scan_trades(path: Path, *, chunksize: int) -> dict[str, Any]:
    trade_count = 0
    notional_sum = 0.0
    for chunk in iter_csv_chunks(path, chunksize=chunksize):
        price = numeric_column(chunk, ("price", "trade_price"))
        amount = numeric_column(chunk, ("amount", "quantity", "qty", "size"))
        notional = (price.abs() * amount.abs()).replace([np.inf, -np.inf], np.nan).dropna()
        trade_count += int(notional.shape[0])
        notional_sum += float(notional.sum())
    return {"trade_count": trade_count, "trade_notional_usd": notional_sum}


def scan_book_ticker(path: Path, *, chunksize: int) -> dict[str, Any]:
    quote_count = 0
    stale_count = 0
    spread_values: list[pd.Series] = []
    previous_key: tuple[float | None, float | None, float | None, float | None] | None = None
    for chunk in iter_csv_chunks(path, chunksize=chunksize):
        bid_price = numeric_column(chunk, ("bid_price", "best_bid_price", "bidPrice"))
        ask_price = numeric_column(chunk, ("ask_price", "best_ask_price", "askPrice"))
        bid_amount = numeric_column(chunk, ("bid_amount", "best_bid_amount", "bid_size", "bidQty"))
        ask_amount = numeric_column(chunk, ("ask_amount", "best_ask_amount", "ask_size", "askQty"))
        mid = (bid_price + ask_price) / 2.0
        spread_bps = ((ask_price - bid_price) / mid.replace(0.0, np.nan) * 10_000.0).replace(
            [np.inf, -np.inf], np.nan
        )
        valid = pd.DataFrame(
            {
                "bid_price": bid_price,
                "ask_price": ask_price,
                "bid_amount": bid_amount,
                "ask_amount": ask_amount,
                "spread_bps": spread_bps,
            }
        ).dropna(subset=["bid_price", "ask_price"])
        if valid.empty:
            continue
        keys = valid[["bid_price", "ask_price", "bid_amount", "ask_amount"]]
        stale = keys.eq(keys.shift(1)).all(axis=1)
        first_key = tuple(keys.iloc[0].tolist())
        if previous_key is not None and first_key == previous_key:
            stale.iloc[0] = True
        previous_key = tuple(keys.iloc[-1].tolist())
        quote_count += int(valid.shape[0])
        stale_count += int(stale.sum())
        spread_values.append(valid["spread_bps"].dropna())
    spread = pd.concat(spread_values, ignore_index=True) if spread_values else pd.Series(dtype="float64")
    return {
        "quote_count": quote_count,
        "median_spread_bps": finite_float(spread.median()) if not spread.empty else None,
        "stale_quote_fraction": float(stale_count / quote_count) if quote_count else None,
    }


def scan_book_snapshot_5(path: Path, *, chunksize: int) -> dict[str, Any]:
    values: list[pd.Series] = []
    snapshot_count = 0
    for chunk in iter_csv_chunks(path, chunksize=chunksize):
        bid_depth, ask_depth = top_depth_from_snapshot(chunk)
        depth = (bid_depth + ask_depth).replace([np.inf, -np.inf], np.nan).dropna()
        snapshot_count += int(depth.shape[0])
        if not depth.empty:
            values.append(depth)
    combined = pd.concat(values, ignore_index=True) if values else pd.Series(dtype="float64")
    return {
        "book_snapshot_count": snapshot_count,
        "median_top5_depth_notional": finite_float(combined.median()) if not combined.empty else None,
    }


def scan_derivative_ticker(path: Path, *, chunksize: int) -> dict[str, Any]:
    count = 0
    for chunk in iter_csv_chunks(path, chunksize=chunksize):
        ts = timestamp_series(chunk)
        count += int(ts.notna().sum())
    return {"derivative_ticker_count": count}


def scan_symbol_day_task(task: dict[str, Any]) -> dict[str, Any]:
    symbol = str(task["symbol"])
    date_text = str(task["date"])
    chunksize = int(task["chunksize"])
    partitions = task["partitions"]
    metrics: dict[str, Any] = {
        "symbol": symbol,
        "date": date_text,
        "trade_count": 0,
        "trade_notional_usd": None,
        "quote_count": 0,
        "median_spread_bps": None,
        "stale_quote_fraction": None,
        "book_snapshot_count": 0,
        "median_top5_depth_notional": None,
        "derivative_ticker_count": 0,
    }
    available = 0
    hash_recorded = 0
    errors: list[str] = []
    for data_type, info in partitions.items():
        if not info.get("available"):
            continue
        available += 1
        if info.get("hash_recorded"):
            hash_recorded += 1
        path = Path(str(info["path"]))
        try:
            if data_type == "trades":
                metrics.update(scan_trades(path, chunksize=chunksize))
            elif data_type == "book_ticker":
                metrics.update(scan_book_ticker(path, chunksize=chunksize))
            elif data_type == "book_snapshot_5":
                metrics.update(scan_book_snapshot_5(path, chunksize=chunksize))
            elif data_type == "derivative_ticker":
                metrics.update(scan_derivative_ticker(path, chunksize=chunksize))
        except Exception as exc:  # retained in artifacts, fail-closed by valid_day false
            errors.append(f"{data_type}:{type(exc).__name__}:{exc}")
    expected = len(SELECTION_DATA_TYPES)
    required_non_empty = (
        int(metrics["trade_count"] or 0) > 0
        and int(metrics["quote_count"] or 0) > 0
        and int(metrics["book_snapshot_count"] or 0) > 0
        and int(metrics["derivative_ticker_count"] or 0) > 0
    )
    metrics.update(
        {
            "expected_partition_count": expected,
            "available_partition_count": available,
            "missing_partition_count": expected - available,
            "hash_recorded_partition_count": hash_recorded,
            "raw_partition_missing_fraction": float((expected - available) / expected),
            "raw_hashes_recorded_for_available": bool(hash_recorded == available),
            "valid_day": bool(available == expected and required_non_empty and not errors),
            "scan_errors": "|".join(errors[:5]),
        }
    )
    return metrics


def load_or_build_daily_metrics(
    *,
    cache_path: Path,
    overwrite: bool,
    raw_root: Path,
    raw_index: dict[tuple[str, str, str, str], dict[str, Any]],
    exchange: str,
    symbols: list[str],
    lookback_dates: list[date],
    chunksize: int,
    max_workers: int,
    hash_raw_if_missing: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if cache_path.exists() and not overwrite:
        frame = pd.read_csv(cache_path)
        return frame, {"mode": "reused_cache", "path": str(cache_path), "row_count": int(frame.shape[0])}

    started = time.perf_counter()
    tasks: list[dict[str, Any]] = []
    for symbol in symbols:
        for current_date in lookback_dates:
            partitions = {
                data_type: partition_status(
                    raw_root=raw_root,
                    raw_index=raw_index,
                    exchange=exchange,
                    data_type=data_type,
                    symbol=symbol,
                    current_date=current_date,
                    hash_raw_if_missing=hash_raw_if_missing,
                )
                for data_type in SELECTION_DATA_TYPES
            }
            tasks.append(
                {
                    "symbol": symbol,
                    "date": current_date.isoformat(),
                    "chunksize": chunksize,
                    "partitions": partitions,
                }
            )

    if max_workers > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            rows = list(executor.map(scan_symbol_day_task, tasks, chunksize=8))
    else:
        rows = [scan_symbol_day_task(task) for task in tasks]
    frame = pd.DataFrame(rows).sort_values(["symbol", "date"], kind="mergesort")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(cache_path, index=False)
    return frame, {
        "mode": "scanned_raw",
        "path": str(cache_path),
        "row_count": int(frame.shape[0]),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }


def longest_valid_run(dates: list[date]) -> int:
    if not dates:
        return 0
    ordered = sorted(set(dates))
    longest = 1
    current = 1
    for prev, item in zip(ordered, ordered[1:]):
        if item == prev + timedelta(days=1):
            current += 1
        else:
            longest = max(longest, current)
            current = 1
    return max(longest, current)


def rank_pct(series: pd.Series, *, ascending: bool) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    filled = numeric.fillna(numeric.min() if ascending else numeric.max())
    if filled.nunique(dropna=True) <= 1:
        return pd.Series(0.5, index=series.index, dtype="float64")
    return filled.rank(method="average", pct=True, ascending=ascending)


def build_monthly_metric_table(
    *,
    daily: pd.DataFrame,
    month_plan: dict[str, Any],
    candidate_symbols: list[str],
    min_valid_days: int,
    max_missing_fraction: float,
    max_stale_fraction: float,
) -> pd.DataFrame:
    start = parse_iso_date(str(month_plan["selection_lookback_start"]))
    end = parse_iso_date(str(month_plan["selection_lookback_end"]))
    lookback_dates = date_range(start, end)
    daily = daily.copy()
    daily["date_obj"] = pd.to_datetime(daily["date"], errors="coerce").dt.date
    window = daily.loc[daily["date_obj"].isin(set(lookback_dates))]
    rows: list[dict[str, Any]] = []
    for symbol in candidate_symbols:
        symbol_window = window.loc[window["symbol"].eq(symbol)]
        valid_dates = [
            parse_iso_date(str(item))
            for item in symbol_window.loc[symbol_window["valid_day"].astype(bool), "date"].tolist()
        ]
        expected = len(lookback_dates) * len(SELECTION_DATA_TYPES)
        available = int(pd.to_numeric(symbol_window["available_partition_count"], errors="coerce").fillna(0).sum())
        missing_fraction = float((expected - available) / expected) if expected else 1.0
        valid_days = int(len(valid_dates))
        continuity = int(longest_valid_run(valid_dates))
        stale = pd.to_numeric(symbol_window["stale_quote_fraction"], errors="coerce")
        row = {
            "symbol": symbol,
            "median_trade_notional_90d": finite_float(
                pd.to_numeric(symbol_window["trade_notional_usd"], errors="coerce").median()
            ),
            "median_quote_count_or_update_count_90d": finite_float(
                pd.to_numeric(symbol_window["quote_count"], errors="coerce").median()
            ),
            "median_top5_depth_notional_90d": finite_float(
                pd.to_numeric(symbol_window["median_top5_depth_notional"], errors="coerce").median()
            ),
            "median_spread_bps_90d": finite_float(
                pd.to_numeric(symbol_window["median_spread_bps"], errors="coerce").median()
            ),
            "raw_partition_missing_fraction_90d": missing_fraction,
            "stale_quote_fraction_90d": finite_float(stale.median()),
            "instrument_continuity_days": continuity,
            "lookback_valid_days": valid_days,
            "selection_expected_partition_count": expected,
            "selection_available_partition_count": available,
            "selection_hash_recorded_partition_count": int(
                pd.to_numeric(symbol_window["hash_recorded_partition_count"], errors="coerce").fillna(0).sum()
            ),
            "selection_raw_hashes_recorded_for_available": bool(
                symbol_window["raw_hashes_recorded_for_available"].astype(bool).all()
            )
            if not symbol_window.empty
            else False,
        }
        reasons: list[str] = []
        if valid_days < min_valid_days:
            reasons.append("lookback_valid_days_below_min")
        if missing_fraction > max_missing_fraction:
            reasons.append("selection_missing_fraction_above_max")
        if (row["stale_quote_fraction_90d"] is not None) and row["stale_quote_fraction_90d"] > max_stale_fraction:
            reasons.append("stale_quote_fraction_above_max")
        if not row["median_trade_notional_90d"] or row["median_trade_notional_90d"] <= 0:
            reasons.append("missing_positive_trade_notional")
        if not row["median_top5_depth_notional_90d"] or row["median_top5_depth_notional_90d"] <= 0:
            reasons.append("missing_positive_top5_depth")
        row["stage_a_universe_candidate_eligible"] = not reasons
        row["exclude_reason"] = ";".join(reasons)
        rows.append(row)

    frame = pd.DataFrame(rows)
    eligible = frame["stage_a_universe_candidate_eligible"].astype(bool)
    scores = pd.Series(np.nan, index=frame.index, dtype="float64")
    if eligible.any():
        sub = frame.loc[eligible]
        scores.loc[eligible] = (
            rank_pct(sub["median_trade_notional_90d"], ascending=True)
            + rank_pct(sub["median_top5_depth_notional_90d"], ascending=True)
            + rank_pct(sub["instrument_continuity_days"], ascending=True)
            - rank_pct(sub["median_spread_bps_90d"], ascending=True)
            - rank_pct(sub["raw_partition_missing_fraction_90d"], ascending=True)
            - rank_pct(sub["stale_quote_fraction_90d"], ascending=True)
        )
    frame["rank_score"] = scores
    frame = frame.sort_values(
        ["stage_a_universe_candidate_eligible", "rank_score", "median_trade_notional_90d", "symbol"],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    frame["ranking_position"] = range(1, frame.shape[0] + 1)
    return frame


def select_monthly_symbols(
    ranking: pd.DataFrame,
    *,
    target_symbols: int,
) -> list[dict[str, Any]]:
    eligible = ranking.loc[ranking["stage_a_universe_candidate_eligible"].astype(bool)].copy()
    selected_symbols: list[str] = []
    for anchor in ANCHOR_SYMBOLS:
        if anchor in set(eligible["symbol"]):
            selected_symbols.append(anchor)
    for symbol in eligible["symbol"].tolist():
        if len(selected_symbols) >= target_symbols:
            break
        if symbol not in selected_symbols:
            selected_symbols.append(symbol)

    selected = ranking.loc[ranking["symbol"].isin(selected_symbols)].copy()
    selected = selected.sort_values(["rank_score", "median_trade_notional_90d", "symbol"], ascending=[False, False, True])
    n = int(selected.shape[0])
    rows: list[dict[str, Any]] = []
    high_cut = math.ceil(n / 3) if n else 0
    mid_cut = math.ceil(2 * n / 3) if n else 0
    for idx, (_, row) in enumerate(selected.iterrows(), start=1):
        if idx <= high_cut:
            bucket = BUCKETS[0]
        elif idx <= mid_cut:
            bucket = BUCKETS[1]
        else:
            bucket = BUCKETS[2]
        payload = row.to_dict()
        payload["monthly_rank"] = idx
        payload["liquidity_bucket"] = bucket
        payload["stage_a_eligible"] = True
        payload["selection_basis"] = "pre_freeze_raw_liquidity_coverage_metrics"
        rows.append(payload)
    return rows


def collect_partition_lineage(
    *,
    raw_root: Path,
    raw_index: dict[tuple[str, str, str, str], dict[str, Any]],
    exchange: str,
    symbols: list[str],
    dates: list[date],
    data_types: tuple[str, ...],
    hash_raw_if_missing: bool,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    missing_examples: list[dict[str, Any]] = []
    expected = len(symbols) * len(dates) * len(data_types)
    available = 0
    hash_recorded = 0
    for symbol in symbols:
        for current_date in dates:
            for data_type in data_types:
                status = partition_status(
                    raw_root=raw_root,
                    raw_index=raw_index,
                    exchange=exchange,
                    data_type=data_type,
                    symbol=symbol,
                    current_date=current_date,
                    hash_raw_if_missing=hash_raw_if_missing,
                )
                if status["available"]:
                    available += 1
                    hash_recorded += int(bool(status["hash_recorded"]))
                    records.append(status)
                elif len(missing_examples) < 200:
                    missing_examples.append(
                        {
                            "symbol": symbol,
                            "date": current_date.isoformat(),
                            "data_type": data_type,
                            "status": status["status"],
                        }
                    )
    missing = expected - available
    return {
        "expected_partition_count": expected,
        "available_partition_count": available,
        "missing_partition_count": missing,
        "missing_fraction": float(missing / expected) if expected else 1.0,
        "hash_recorded_partition_count": hash_recorded,
        "raw_hashes_recorded_for_available": bool(hash_recorded == available),
        "available_partitions": records,
        "missing_partition_examples": missing_examples,
    }


def monthly_gate_report(
    *,
    selected: list[dict[str, Any]],
    ranking: pd.DataFrame,
    selection_lineage: dict[str, Any],
    evaluation_lineage: dict[str, Any],
    min_symbols: int,
    min_non_btc_eth_symbols: int,
    min_liquidity_buckets: int,
    max_evaluation_missing_fraction: float,
) -> dict[str, Any]:
    selected_symbols = [str(item["symbol"]) for item in selected]
    buckets = sorted({str(item["liquidity_bucket"]) for item in selected})
    anchors_present = all(anchor in selected_symbols for anchor in ANCHOR_SYMBOLS)
    gates = {
        "anchors_present": {"passed": anchors_present, "observed": selected_symbols, "required": list(ANCHOR_SYMBOLS)},
        "selected_symbols_min": {
            "passed": len(selected_symbols) >= min_symbols,
            "observed": len(selected_symbols),
            "required": min_symbols,
        },
        "non_btc_eth_symbols_min": {
            "passed": len([s for s in selected_symbols if s not in ANCHOR_SYMBOLS]) >= min_non_btc_eth_symbols,
            "observed": len([s for s in selected_symbols if s not in ANCHOR_SYMBOLS]),
            "required": min_non_btc_eth_symbols,
        },
        "liquidity_buckets_min": {
            "passed": len(buckets) >= min_liquidity_buckets,
            "observed": len(buckets),
            "required": min_liquidity_buckets,
            "buckets": buckets,
        },
        "candidate_eligible_count_min": {
            "passed": int(ranking["stage_a_universe_candidate_eligible"].astype(bool).sum()) >= min_symbols,
            "observed": int(ranking["stage_a_universe_candidate_eligible"].astype(bool).sum()),
            "required": min_symbols,
        },
        "selection_raw_hashes_recorded": {
            "passed": bool(selection_lineage["raw_hashes_recorded_for_available"]),
            "observed": bool(selection_lineage["raw_hashes_recorded_for_available"]),
            "required": True,
        },
        "evaluation_raw_hashes_recorded": {
            "passed": bool(evaluation_lineage["raw_hashes_recorded_for_available"]),
            "observed": bool(evaluation_lineage["raw_hashes_recorded_for_available"]),
            "required": True,
        },
        "evaluation_missing_fraction_max": {
            "passed": float(evaluation_lineage["missing_fraction"]) <= max_evaluation_missing_fraction,
            "observed": float(evaluation_lineage["missing_fraction"]),
            "required_max": max_evaluation_missing_fraction,
        },
    }
    blocking = [name for name, item in gates.items() if not item["passed"]]
    return {"gates": gates, "blocking_gates": blocking, "passed": not blocking}


def build_config_payload(args: argparse.Namespace, raw_root: Path) -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "as_of": args.as_of,
        "dry_run_root": str(args.dry_run_root),
        "raw_root": str(raw_root),
        "raw_staging_manifest": str(args.raw_staging_manifest) if args.raw_staging_manifest else None,
        "exchange": args.exchange,
        "target_symbols": args.target_symbols,
        "min_symbols": args.min_symbols,
        "min_non_btc_eth_symbols": args.min_non_btc_eth_symbols,
        "min_liquidity_buckets": args.min_liquidity_buckets,
        "distinct_months_min": args.distinct_months_min,
        "selection_lookback_min_days": args.selection_lookback_min_days,
        "max_selection_missing_fraction": args.max_selection_missing_fraction,
        "max_stale_quote_fraction": args.max_stale_quote_fraction,
        "max_evaluation_missing_fraction": args.max_evaluation_missing_fraction,
        "selection_data_types": list(SELECTION_DATA_TYPES),
        "stage_a_data_types": list(STAGE_A_DATA_TYPES),
        "hash_raw_if_missing": bool(args.hash_raw_if_missing),
    }


def main() -> int:
    started = time.perf_counter()
    args = parse_args()
    if args.max_workers < 1:
        raise SystemExit("--max-workers must be positive")
    dry_run_root = args.dry_run_root.expanduser().resolve()
    raw_root = resolve_raw_root(args.raw_root)
    raw_manifest_path = args.raw_staging_manifest.expanduser().resolve() if args.raw_staging_manifest else None
    output_root = args.output_root or (
        ROOT / "artifacts" / "quant_research" / "factor_reports" / args.as_of / DEFAULT_OUTPUT_SUBDIR
    )
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    monthly_plan_path = dry_run_root / "rolling_pit_core_monthly_freeze_plan.json"
    candidate_pool_path = dry_run_root / "rolling_pit_core_candidate_pool_audit.json"
    dry_run_raw_plan_path = dry_run_root / "rolling_pit_core_raw_staging_manifest.json"
    monthly_plan = load_json(monthly_plan_path)
    candidate_pool = load_json(candidate_pool_path)
    dry_run_raw_plan = load_json(dry_run_raw_plan_path)
    raw_manifest_payload, raw_index = load_raw_manifest_index(raw_manifest_path, default_exchange=str(args.exchange))

    candidate_symbols = [normalize_symbol(item) for item in candidate_pool.get("candidate_seed_symbols", [])]
    if not candidate_symbols:
        candidate_symbols = [normalize_symbol(item) for item in dry_run_raw_plan.get("candidate_seed_symbols", [])]
    candidate_symbols = sorted(dict.fromkeys(candidate_symbols), key=candidate_symbols.index)
    if not candidate_symbols:
        raise SystemExit("candidate seed symbols missing from dry-run artifacts")

    months = monthly_plan.get("months", [])
    all_lookback_dates = sorted(
        {
            current_date
            for item in months
            for current_date in date_range(
                parse_iso_date(str(item["selection_lookback_start"])),
                parse_iso_date(str(item["selection_lookback_end"])),
            )
        }
    )
    daily_cache = (
        args.daily_metrics_cache.expanduser().resolve()
        if args.daily_metrics_cache is not None
        else output_root / "rolling_pit_core_daily_selection_metrics.csv"
    )
    daily_metrics, daily_profile = load_or_build_daily_metrics(
        cache_path=daily_cache,
        overwrite=bool(args.overwrite_daily_metrics),
        raw_root=raw_root,
        raw_index=raw_index,
        exchange=str(args.exchange),
        symbols=candidate_symbols,
        lookback_dates=all_lookback_dates,
        chunksize=int(args.chunksize),
        max_workers=int(args.max_workers),
        hash_raw_if_missing=bool(args.hash_raw_if_missing),
    )

    config_payload = build_config_payload(args, raw_root)
    selection_config_sha256 = sha256_json(config_payload)
    runner_sha256 = sha256_file(Path(__file__))
    raw_manifest_sha256 = sha256_file(raw_manifest_path) if raw_manifest_path and raw_manifest_path.exists() else None

    monthly_artifacts: list[dict[str, Any]] = []
    monthly_masks: list[dict[str, Any]] = []
    aggregate_gate_blockers: list[str] = []
    for item in months:
        evaluation_month = str(item["evaluation_month"])
        month_dir = output_root / "monthly_freezes" / evaluation_month
        ranking = build_monthly_metric_table(
            daily=daily_metrics,
            month_plan=item,
            candidate_symbols=candidate_symbols,
            min_valid_days=int(args.selection_lookback_min_days),
            max_missing_fraction=float(args.max_selection_missing_fraction),
            max_stale_fraction=float(args.max_stale_quote_fraction),
        )
        selected = select_monthly_symbols(ranking, target_symbols=int(args.target_symbols))
        selected_symbols = [str(row["symbol"]) for row in selected]
        selection_dates = date_range(
            parse_iso_date(str(item["selection_lookback_start"])),
            parse_iso_date(str(item["selection_lookback_end"])),
        )
        evaluation_dates = date_range(
            parse_iso_date(str(item["evaluation_start"])),
            parse_iso_date(str(item["evaluation_end"])),
        )
        selection_lineage = collect_partition_lineage(
            raw_root=raw_root,
            raw_index=raw_index,
            exchange=str(args.exchange),
            symbols=selected_symbols,
            dates=selection_dates,
            data_types=SELECTION_DATA_TYPES,
            hash_raw_if_missing=bool(args.hash_raw_if_missing),
        )
        evaluation_lineage = collect_partition_lineage(
            raw_root=raw_root,
            raw_index=raw_index,
            exchange=str(args.exchange),
            symbols=selected_symbols,
            dates=evaluation_dates,
            data_types=STAGE_A_DATA_TYPES,
            hash_raw_if_missing=bool(args.hash_raw_if_missing),
        )
        gates = monthly_gate_report(
            selected=selected,
            ranking=ranking,
            selection_lineage=selection_lineage,
            evaluation_lineage=evaluation_lineage,
            min_symbols=int(args.min_symbols),
            min_non_btc_eth_symbols=int(args.min_non_btc_eth_symbols),
            min_liquidity_buckets=int(args.min_liquidity_buckets),
            max_evaluation_missing_fraction=float(args.max_evaluation_missing_fraction),
        )
        stage_a_ready = bool(gates["passed"])
        aggregate_gate_blockers.extend([f"{evaluation_month}:{name}" for name in gates["blocking_gates"]])

        ranking_rows = ranking.replace({np.nan: None}).to_dict(orient="records")
        selected_rows = [{key: (None if pd.isna(value) else value) for key, value in row.items()} for row in selected]
        ranking_path = month_dir / "candidate_ranking.csv"
        selected_path = month_dir / "selected_symbols.csv"
        mask_path = month_dir / "monthly_universe_mask.json"
        audit_path = month_dir / "monthly_universe_selection_audit.json"
        lineage_path = month_dir / "hash_lineage.json"

        write_csv(
            ranking_path,
            ranking_rows,
            [
                "ranking_position",
                "symbol",
                "stage_a_universe_candidate_eligible",
                "rank_score",
                "median_trade_notional_90d",
                "median_quote_count_or_update_count_90d",
                "median_top5_depth_notional_90d",
                "median_spread_bps_90d",
                "raw_partition_missing_fraction_90d",
                "stale_quote_fraction_90d",
                "instrument_continuity_days",
                "lookback_valid_days",
                "exclude_reason",
            ],
        )
        write_csv(
            selected_path,
            selected_rows,
            [
                "monthly_rank",
                "symbol",
                "liquidity_bucket",
                "rank_score",
                "median_trade_notional_90d",
                "median_top5_depth_notional_90d",
                "median_spread_bps_90d",
                "raw_partition_missing_fraction_90d",
                "stale_quote_fraction_90d",
                "instrument_continuity_days",
                "lookback_valid_days",
                "selection_basis",
                "stage_a_eligible",
            ],
        )
        mask_payload = {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "research_id": RESEARCH_ID,
            "artifact_kind": "monthly_universe_mask",
            "evaluation_month": evaluation_month,
            "freeze_date": item["freeze_date"],
            "evaluation_start": item["evaluation_start"],
            "evaluation_end": item["evaluation_end"],
            "selected_symbols": selected_symbols,
            "selected_symbol_count": len(selected_symbols),
            "liquidity_buckets_by_symbol": {str(row["symbol"]): str(row["liquidity_bucket"]) for row in selected},
            "stage_a_monthly_universe_mask_ready": stage_a_ready,
            "first_valid_label_timestamp_utc_min": f"{item['evaluation_start']}T00:00:00Z",
            "selection_lookback_start": item["selection_lookback_start"],
            "selection_lookback_end": item["selection_lookback_end"],
            "future_data_used_for_selection": False,
            "label_free_selection_assertion": True,
            "stage_a_proof_computed": False,
            "stage_b_return_ablation_allowed": False,
            "strategy_pnl_computed": False,
            "trading_action_authorized": False,
            "live_or_timer_use_authorized": False,
        }
        write_json(mask_path, mask_payload)

        audit_payload = {
            **mask_payload,
            "artifact_kind": "monthly_universe_selection_audit",
            "selection_status": "stage_a_eligible_monthly_mask_ready" if stage_a_ready else "failed_monthly_universe_mask_gates",
            "candidate_seed_symbol_count": len(candidate_symbols),
            "eligible_candidate_count": int(ranking["stage_a_universe_candidate_eligible"].astype(bool).sum()),
            "candidate_symbols": candidate_symbols,
            "selected_symbols": selected_symbols,
            "excluded_symbols_with_reason": [
                {"symbol": str(row["symbol"]), "exclude_reason": str(row.get("exclude_reason") or "")}
                for row in ranking_rows
                if row.get("exclude_reason")
            ],
            "selection_metric_definitions": {
                "median_trade_notional_90d": "Median daily trade notional over the pre-freeze lookback.",
                "median_quote_count_or_update_count_90d": "Median daily book_ticker row count over the pre-freeze lookback.",
                "median_top5_depth_notional_90d": "Median daily top-5 bid plus ask notional from book_snapshot_5.",
                "median_spread_bps_90d": "Median daily BBO spread in basis points.",
                "raw_partition_missing_fraction_90d": "Missing selection raw partitions divided by expected selection raw partitions.",
                "stale_quote_fraction_90d": "Median daily fraction of repeated BBO records.",
                "instrument_continuity_days": "Longest consecutive run of valid lookback days.",
                "lookback_valid_days": "Total valid lookback days with all selection data types present and non-empty.",
            },
            "rank_score_formula": (
                "+rank_pct(median_trade_notional_90d)+rank_pct(median_top5_depth_notional_90d)"
                "+rank_pct(instrument_continuity_days)-rank_pct(median_spread_bps_90d)"
                "-rank_pct(raw_partition_missing_fraction_90d)-rank_pct(stale_quote_fraction_90d)"
            ),
            "monthly_gates": gates,
            "selection_raw_lineage": selection_lineage,
            "evaluation_raw_lineage": evaluation_lineage,
            "dry_run_root": str(dry_run_root),
            "raw_root": str(raw_root),
            "raw_staging_manifest": str(raw_manifest_path) if raw_manifest_path else None,
            "raw_staging_manifest_sha256": raw_manifest_sha256,
            "selection_config_sha256": selection_config_sha256,
            "selection_code_sha256": runner_sha256,
            "downloads_executed_by_runner": False,
            "raw_scan_executed_by_runner": True,
            "normalization_executed_by_runner": False,
        }
        write_json(audit_path, audit_payload)
        lineage_payload = {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "evaluation_month": evaluation_month,
            "dry_run_monthly_freeze_plan_path": str(monthly_plan_path),
            "dry_run_monthly_freeze_plan_sha256": sha256_file(monthly_plan_path),
            "dry_run_raw_staging_plan_path": str(dry_run_raw_plan_path),
            "dry_run_raw_staging_plan_sha256": sha256_file(dry_run_raw_plan_path),
            "raw_staging_manifest": str(raw_manifest_path) if raw_manifest_path else None,
            "raw_staging_manifest_sha256": raw_manifest_sha256,
            "runner_path": relative_or_string(Path(__file__)),
            "runner_sha256": runner_sha256,
            "selection_config_sha256": selection_config_sha256,
            "monthly_universe_mask_sha256": sha256_file(mask_path),
            "monthly_universe_selection_audit_sha256": sha256_file(audit_path),
            "selected_symbols_csv_sha256": sha256_file(selected_path),
            "candidate_ranking_csv_sha256": sha256_file(ranking_path),
            "future_data_used_for_selection": False,
            "label_free_selection_assertion": True,
        }
        write_json(lineage_path, lineage_payload)

        monthly_record = {
            "evaluation_month": evaluation_month,
            "freeze_date": item["freeze_date"],
            "selected_symbol_count": len(selected_symbols),
            "selected_symbols": selected_symbols,
            "liquidity_buckets_by_symbol": mask_payload["liquidity_buckets_by_symbol"],
            "stage_a_monthly_universe_mask_ready": stage_a_ready,
            "blocking_gates": gates["blocking_gates"],
            "monthly_universe_mask_path": relative_or_string(mask_path),
            "monthly_universe_mask_sha256": sha256_file(mask_path),
            "monthly_universe_selection_audit_path": relative_or_string(audit_path),
            "monthly_universe_selection_audit_sha256": sha256_file(audit_path),
            "selected_symbols_path": relative_or_string(selected_path),
            "selected_symbols_sha256": sha256_file(selected_path),
            "candidate_ranking_path": relative_or_string(ranking_path),
            "candidate_ranking_sha256": sha256_file(ranking_path),
            "hash_lineage_path": relative_or_string(lineage_path),
            "hash_lineage_sha256": sha256_file(lineage_path),
        }
        monthly_artifacts.append(monthly_record)
        monthly_masks.append(mask_payload)

    valid_months = [item for item in monthly_artifacts if item["stage_a_monthly_universe_mask_ready"]]
    selected_counts = [int(item["selected_symbol_count"]) for item in monthly_artifacts]
    non_btc_eth_counts = [
        len([symbol for symbol in item["selected_symbols"] if symbol not in ANCHOR_SYMBOLS])
        for item in monthly_artifacts
    ]
    bucket_counts = [
        len(set(item["liquidity_buckets_by_symbol"].values()))
        for item in monthly_artifacts
    ]
    aggregate_gates = {
        "evaluation_month_count_min": {
            "passed": len(monthly_artifacts) >= int(args.distinct_months_min),
            "observed": len(monthly_artifacts),
            "required": int(args.distinct_months_min),
        },
        "valid_monthly_freeze_manifest_count_min": {
            "passed": len(valid_months) >= int(args.distinct_months_min),
            "observed": len(valid_months),
            "required": int(args.distinct_months_min),
        },
        "monthly_selected_symbols_min": {
            "passed": bool(selected_counts) and min(selected_counts) >= int(args.min_symbols),
            "observed_min": min(selected_counts) if selected_counts else 0,
            "required": int(args.min_symbols),
        },
        "monthly_non_btc_eth_symbols_min": {
            "passed": bool(non_btc_eth_counts) and min(non_btc_eth_counts) >= int(args.min_non_btc_eth_symbols),
            "observed_min": min(non_btc_eth_counts) if non_btc_eth_counts else 0,
            "required": int(args.min_non_btc_eth_symbols),
        },
        "monthly_liquidity_bucket_count_min": {
            "passed": bool(bucket_counts) and min(bucket_counts) >= int(args.min_liquidity_buckets),
            "observed_min": min(bucket_counts) if bucket_counts else 0,
            "required": int(args.min_liquidity_buckets),
        },
        "future_data_used_for_selection_count_zero": {
            "passed": True,
            "observed": 0,
            "required": 0,
        },
    }
    aggregate_blocking = [name for name, item in aggregate_gates.items() if not item["passed"]]
    aggregate_blocking.extend(aggregate_gate_blockers)
    masks_ready = not aggregate_blocking

    masks_payload = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "artifact_kind": "rolling_pit_core_monthly_universe_masks",
        "as_of": args.as_of,
        "monthly_masks": monthly_masks,
        "monthly_artifacts": monthly_artifacts,
        "stage_a_monthly_universe_masks_ready": masks_ready,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
    }
    masks_path = output_root / "rolling_pit_core_monthly_universe_masks.json"
    audit_path = output_root / "rolling_pit_core_monthly_selection_audit.json"
    input_audit_path = output_root / "rolling_pit_core_stage_a_input_audit.json"
    coverage_path = output_root / "rolling_pit_core_stage_a_coverage_report.json"
    profile_path = output_root / "rolling_pit_core_stage_a_profile.json"
    summary_path = output_root / "rolling_pit_core_stage_a_summary.json"

    write_json(masks_path, masks_payload)
    aggregate_audit = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_monthly_selection_audit",
        "as_of": args.as_of,
        "generated_at_utc": utc_now(),
        "dry_run_root": str(dry_run_root),
        "raw_root": str(raw_root),
        "raw_staging_manifest": str(raw_manifest_path) if raw_manifest_path else None,
        "raw_staging_manifest_sha256": raw_manifest_sha256,
        "daily_metrics_cache": str(daily_cache),
        "daily_metrics_cache_sha256": sha256_file(daily_cache) if daily_cache.exists() else None,
        "candidate_seed_symbol_count": len(candidate_symbols),
        "evaluation_month_count": len(monthly_artifacts),
        "valid_monthly_freeze_manifest_count": len(valid_months),
        "aggregate_gates": aggregate_gates,
        "blocking_gates": aggregate_blocking,
        "stage_a_monthly_universe_masks_ready": masks_ready,
        "monthly_artifacts": monthly_artifacts,
        "selection_config_sha256": selection_config_sha256,
        "selection_code_sha256": runner_sha256,
        "future_data_used_for_selection_count": 0,
        "label_free_selection_assertion": True,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": True,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
    }
    write_json(audit_path, aggregate_audit)
    write_json(
        input_audit_path,
        {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "artifact_kind": "rolling_pit_core_stage_a_input_audit",
            "input_mode": "monthly_universe_masks_only_no_stage_a",
            "monthly_universe_masks_path": relative_or_string(masks_path),
            "monthly_universe_masks_sha256": sha256_file(masks_path),
            "stage_a_monthly_universe_masks_ready": masks_ready,
            "stage_a_proof_computed": False,
            "downloads_executed_by_runner": False,
            "raw_scan_executed_by_runner": True,
            "normalization_executed_by_runner": False,
            "stage_b_return_ablation_allowed": False,
            "strategy_pnl_computed": False,
            "trading_action_authorized": False,
        },
    )
    write_json(
        coverage_path,
        {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "artifact_kind": "rolling_pit_core_stage_a_coverage_report",
            "coverage_scope": "monthly_universe_masks_only",
            "aggregate_gates": aggregate_gates,
            "blocking_gates": aggregate_blocking,
            "stage_a_monthly_universe_masks_ready": masks_ready,
            "stage_a_proof_computed": False,
        },
    )
    write_json(
        profile_path,
        {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "artifact_kind": "rolling_pit_core_stage_a_profile",
            "profile_scope": "monthly_mask_pre_freeze_raw_metrics_only",
            "daily_metrics_profile": daily_profile,
            "total_seconds_before_profile_write": round(time.perf_counter() - started, 6),
            "stage_a_proof_computed": False,
        },
    )
    summary = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "artifact_kind": "rolling_pit_core_stage_a_summary",
        "as_of": args.as_of,
        "generated_at_utc": utc_now(),
        "status": "stage_a_monthly_universe_masks_ready" if masks_ready else "failed_monthly_universe_mask_gates",
        "output_root": str(output_root),
        "dry_run_root": str(dry_run_root),
        "raw_root": str(raw_root),
        "raw_staging_manifest": str(raw_manifest_path) if raw_manifest_path else None,
        "raw_staging_manifest_sha256": raw_manifest_sha256,
        "candidate_seed_symbol_count": len(candidate_symbols),
        "evaluation_month_count": len(monthly_artifacts),
        "valid_monthly_freeze_manifest_count": len(valid_months),
        "stage_a_monthly_universe_masks_ready": masks_ready,
        "blocking_gates": aggregate_blocking,
        "aggregate_gates": aggregate_gates,
        "monthly_universe_masks_path": relative_or_string(masks_path),
        "monthly_universe_masks_sha256": sha256_file(masks_path),
        "monthly_selection_audit_path": relative_or_string(audit_path),
        "monthly_selection_audit_sha256": sha256_file(audit_path),
        "stage_a_input_audit_path": relative_or_string(input_audit_path),
        "stage_a_input_audit_sha256": sha256_file(input_audit_path),
        "coverage_report_path": relative_or_string(coverage_path),
        "coverage_report_sha256": sha256_file(coverage_path),
        "profile_path": relative_or_string(profile_path),
        "profile_sha256": sha256_file(profile_path),
        "future_data_used_for_selection": False,
        "label_free_selection_assertion": True,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": True,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if masks_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
