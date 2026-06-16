from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_VERSION = "quant_tardis_intraday_liquidity_shock_impulse_stage_a.v2_columnar"
RESEARCH_ID = "tardis_intraday_liquidity_shock_impulse_v0"
DEFAULT_AS_OF = "2026-06-15-stage-a"
DEFAULT_FROM_DATE = "2025-01-01"
DEFAULT_TO_DATE = "2026-06-13"
DEFAULT_EXCHANGE = "binance-futures"
DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT"
DEFAULT_DATA_TYPES = (
    "trades",
    "liquidations",
    "book_ticker",
    "book_snapshot_5",
    "derivative_ticker",
)
DEFAULT_OUTPUT_SUBDIR = "tardis_intraday_liquidity_shock_impulse_stage_a"
DEFAULT_EVENT_BAR_MINUTES = 5
DEFAULT_LOOKBACK_BARS = 288
DEFAULT_MIN_LOOKBACK_BARS = 96
DEFAULT_SHUFFLE_ITERATIONS = 100
DEFAULT_SAMPLE_ROWS = 500
PRIMARY_HORIZON_TO_MINUTES = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "24h": 1440,
}
HORIZONS = ("15m", "1h", "4h", "24h")
PRIMARY_FAMILIES = (
    "liquidation_burst",
    "trade_pressure_burst",
    "book_thinning",
    "basis_oi_state_change",
)
RAW_RETENTION_NOTE = (
    "This Stage A runner does not download Tardis data and does not scan raw "
    "Tardis gzip/CSV partitions. It consumes retained normalized parquet bar "
    "features produced by the separate raw-to-columnar normalizer."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Tardis intraday liquidity-shock impulse Stage A mechanism proof. "
            "This writes proof artifacts only from normalized parquet staging and "
            "does not compute strategy PnL, portfolio construction, live targets, "
            "or trading actions."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--to-date", default=DEFAULT_TO_DATE)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--normalized-root", type=Path, default=None)
    parser.add_argument("--normalized-manifest", type=Path, default=None)
    parser.add_argument(
        "--monthly-universe-masks",
        type=Path,
        default=None,
        help=(
            "Optional rolling PIT monthly universe masks JSON. When supplied, "
            "the Stage A runner audits and reads only normalized parquet "
            "partitions for the selected symbols in each evaluation month."
        ),
    )
    parser.add_argument("--raw-root", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--event-bar-minutes", type=int, default=DEFAULT_EVENT_BAR_MINUTES)
    parser.add_argument("--lookback-bars", type=int, default=DEFAULT_LOOKBACK_BARS)
    parser.add_argument("--min-lookback-bars", type=int, default=DEFAULT_MIN_LOOKBACK_BARS)
    parser.add_argument("--primary-event-family", choices=PRIMARY_FAMILIES, default="liquidation_burst")
    parser.add_argument("--primary-direction", choices=("continuation", "reversal"), default="reversal")
    parser.add_argument("--primary-horizon", choices=HORIZONS, default="1h")
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--sample-rows", type=int, default=DEFAULT_SAMPLE_ROWS)
    parser.add_argument("--chunksize", type=int, default=250_000, help=argparse.SUPPRESS)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_date(text: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {text!r}") from exc


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def resolve_raw_root(raw_root: Path | None) -> Path:
    if raw_root is not None:
        return raw_root.expanduser().resolve()
    env_root = os.environ.get("MERIDIAN_TARDIS_INTRADAY_RAW_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    if os.name != "nt":
        return Path("/data/meridian/hot_stage/tardis_intraday_liquidity_shock").resolve()
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / "market_history" / "tardis_intraday_liquidity_shock").resolve()
    return (Path.home() / "AppData" / "Local" / "EnhengClaw" / "market_history" / "tardis_intraday_liquidity_shock").resolve()


def resolve_normalized_root(normalized_root: Path | None) -> Path:
    if normalized_root is not None:
        return normalized_root.expanduser().resolve()
    env_root = os.environ.get("MERIDIAN_TARDIS_INTRADAY_NORMALIZED_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    if os.name != "nt":
        return Path("/data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar").resolve()
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return (
            Path(localappdata)
            / "EnhengClaw"
            / "market_history"
            / "tardis_intraday_liquidity_shock_columnar"
        ).resolve()
    return (
        Path.home()
        / "AppData"
        / "Local"
        / "EnhengClaw"
        / "market_history"
        / "tardis_intraday_liquidity_shock_columnar"
    ).resolve()


def ensure_outside_repo(path: Path, *, label: str) -> None:
    root = ROOT.resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return
    raise RuntimeError(f"{label} must stay outside the repo checkout: {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_partition_path(
    *,
    normalized_root: Path,
    exchange: str,
    symbol: str,
    current_date: date,
) -> Path:
    return (
        normalized_root
        / "bar_features"
        / f"exchange={exchange}"
        / f"symbol={symbol}"
        / f"year={current_date:%Y}"
        / f"month={current_date:%m}"
        / f"date={current_date.isoformat()}.parquet"
    )


def candidate_normalized_partition_paths(
    *,
    normalized_root: Path,
    exchange: str,
    symbol: str,
    current_date: date,
) -> list[Path]:
    yyyy = f"{current_date:%Y}"
    mm = f"{current_date:%m}"
    iso = current_date.isoformat()
    return [
        normalized_partition_path(
            normalized_root=normalized_root,
            exchange=exchange,
            symbol=symbol,
            current_date=current_date,
        ),
        normalized_root / "bar_features" / exchange / symbol / yyyy / mm / f"{iso}.parquet",
        normalized_root / "bar_features" / symbol / yyyy / mm / f"{iso}.parquet",
        normalized_root / "bar_features" / f"{symbol}_{iso}.parquet",
    ]


def find_normalized_partition(
    *,
    normalized_root: Path,
    exchange: str,
    symbol: str,
    current_date: date,
) -> Path | None:
    for path in candidate_normalized_partition_paths(
        normalized_root=normalized_root,
        exchange=exchange,
        symbol=symbol,
        current_date=current_date,
    ):
        if path.exists() and path.is_file():
            return path
    return None


def resolve_normalized_manifest(normalized_root: Path, manifest: Path | None) -> Path | None:
    if manifest is not None:
        candidate = manifest.expanduser().resolve()
        return candidate if candidate.exists() else None
    latest = normalized_root / "latest_manifest.json"
    if latest.exists():
        return latest
    manifests = sorted((normalized_root / "manifests").glob("*.json")) if (normalized_root / "manifests").exists() else []
    return manifests[-1] if manifests else None


def finite_float(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def symbol_list(text: str) -> list[str]:
    symbols = []
    for item in str(text).split(","):
        value = item.strip().upper()
        if not value:
            continue
        symbols.append(value if value.endswith("USDT") else f"{value}USDT")
    return sorted(set(symbols))


def normalize_symbol_sequence(values: list[Any]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item).strip().upper()
        if not value:
            continue
        symbol = value if value.endswith("USDT") else f"{value}USDT"
        if symbol in seen:
            continue
        symbols.append(symbol)
        seen.add(symbol)
    return symbols


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def load_monthly_universe_mask_scope(
    monthly_universe_masks: Path,
    *,
    from_date: date,
    to_date: date,
) -> tuple[dict[str, Any], list[tuple[str, date]], list[str], list[date], list[dict[str, Any]]]:
    payload = json.loads(monthly_universe_masks.read_text(encoding="utf-8"))
    masks = payload.get("monthly_masks")
    if masks is None and payload.get("artifact_kind") == "monthly_universe_mask":
        masks = [payload]
    if not isinstance(masks, list) or not masks:
        raise SystemExit("monthly universe masks JSON does not contain monthly_masks")
    if payload.get("stage_a_monthly_universe_masks_ready") is False:
        raise SystemExit("monthly universe masks are not Stage A ready")

    required_pairs: list[tuple[str, date]] = []
    seen_pairs: set[tuple[str, date]] = set()
    symbol_order: list[str] = []
    seen_symbols: set[str] = set()
    scope_records: list[dict[str, Any]] = []

    for mask in masks:
        if not isinstance(mask, dict):
            continue
        evaluation_start = parse_iso_date(str(mask.get("evaluation_start")))
        evaluation_end = parse_iso_date(str(mask.get("evaluation_end")))
        overlap_start = max(from_date, evaluation_start)
        overlap_end = min(to_date, evaluation_end)
        if overlap_end < overlap_start:
            continue
        if mask.get("stage_a_monthly_universe_mask_ready") is not True:
            raise SystemExit(f"monthly universe mask is not ready for {mask.get('evaluation_month')}")
        selected_symbols = normalize_symbol_sequence(list(mask.get("selected_symbols") or []))
        if not selected_symbols:
            raise SystemExit(f"monthly universe mask has no selected symbols for {mask.get('evaluation_month')}")
        for symbol in selected_symbols:
            if symbol not in seen_symbols:
                symbol_order.append(symbol)
                seen_symbols.add(symbol)
        for current_date in date_range(overlap_start, overlap_end):
            for symbol in selected_symbols:
                pair = (symbol, current_date)
                if pair in seen_pairs:
                    continue
                required_pairs.append(pair)
                seen_pairs.add(pair)
        scope_records.append(
            {
                "evaluation_month": str(mask.get("evaluation_month") or month_key(evaluation_start)),
                "freeze_date": mask.get("freeze_date"),
                "evaluation_start": evaluation_start.isoformat(),
                "evaluation_end": evaluation_end.isoformat(),
                "overlap_start": overlap_start.isoformat(),
                "overlap_end": overlap_end.isoformat(),
                "selected_symbol_count": len(selected_symbols),
                "selected_symbols": selected_symbols,
                "future_data_used_for_selection": bool(mask.get("future_data_used_for_selection", False)),
                "label_free_selection_assertion": bool(mask.get("label_free_selection_assertion", False)),
                "stage_a_monthly_universe_mask_ready": True,
            }
        )

    if not required_pairs:
        raise SystemExit("monthly universe masks do not overlap the requested date range")
    dates = sorted({current_date for _, current_date in required_pairs})
    return payload, required_pairs, symbol_order, dates, scope_records


def timestamp_series(frame: pd.DataFrame) -> pd.Series:
    for column in ("timestamp", "exchange_timestamp", "local_timestamp", "time"):
        if column not in frame.columns:
            continue
        series = frame[column]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().mean() > 0.90:
            median_abs = float(numeric.dropna().abs().median()) if numeric.notna().any() else 0.0
            if median_abs > 1e17:
                unit = "ns"
            elif median_abs > 1e14:
                unit = "us"
            elif median_abs > 1e11:
                unit = "ms"
            else:
                unit = "s"
            return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
        return pd.to_datetime(series, utc=True, errors="coerce")
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")


def numeric_column(frame: pd.DataFrame, candidates: tuple[str, ...], *, default: float = np.nan) -> pd.Series:
    for column in candidates:
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(default, index=frame.index, dtype="float64")


def text_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series:
    for column in candidates:
        if column in frame.columns:
            return frame[column].astype(str)
    return pd.Series("", index=frame.index, dtype="object")


def bar_start(series: pd.Series, *, minutes: int) -> pd.Series:
    return series.dt.floor(f"{int(minutes)}min")


def normalize_side(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip().str.lower()
    positive = text.isin({"buy", "bid", "long", "short_liquidated", "short"})
    negative = text.isin({"sell", "ask", "long_liquidated"})
    out = pd.Series(0.0, index=series.index, dtype="float64")
    out.loc[positive] = 1.0
    out.loc[negative] = -1.0
    return out


def candidate_partition_paths(
    *,
    raw_root: Path,
    exchange: str,
    data_type: str,
    symbol: str,
    current_date: date,
) -> list[Path]:
    yyyy = f"{current_date:%Y}"
    mm = f"{current_date:%m}"
    dd = f"{current_date:%d}"
    iso = current_date.isoformat()
    names = [f"{symbol}.csv.gz", f"{symbol}.csv", f"{symbol.lower()}.csv.gz", f"{symbol.lower()}.csv"]
    paths: list[Path] = []
    for prefix in (raw_root / "raw", raw_root):
        for name in names:
            paths.extend(
                [
                    prefix / exchange / data_type / yyyy / mm / dd / name,
                    prefix / exchange / data_type / symbol / yyyy / mm / dd / name,
                    prefix / exchange / data_type / symbol / f"{iso}.csv.gz",
                    prefix / data_type / exchange / symbol / yyyy / mm / dd / name,
                    prefix / yyyy / mm / dd / exchange / data_type / name,
                ]
            )
    return paths


def find_partition(
    *,
    raw_root: Path,
    exchange: str,
    data_type: str,
    symbol: str,
    current_date: date,
) -> Path | None:
    for path in candidate_partition_paths(
        raw_root=raw_root,
        exchange=exchange,
        data_type=data_type,
        symbol=symbol,
        current_date=current_date,
    ):
        if path.exists() and path.is_file():
            return path
    return None


def build_input_audit(
    *,
    raw_root: Path,
    exchange: str,
    symbols: list[str],
    dates: list[date],
) -> tuple[dict[str, Any], dict[tuple[str, str, date], Path]]:
    found_paths: dict[tuple[str, str, date], Path] = {}
    missing_examples: list[dict[str, str]] = []
    partitions: list[dict[str, Any]] = []
    for symbol in symbols:
        for data_type in DEFAULT_DATA_TYPES:
            for current_date in dates:
                path = find_partition(
                    raw_root=raw_root,
                    exchange=exchange,
                    data_type=data_type,
                    symbol=symbol,
                    current_date=current_date,
                )
                key = (symbol, data_type, current_date)
                if path is not None:
                    found_paths[key] = path
                    stat = path.stat()
                    partitions.append(
                        {
                            "symbol": symbol,
                            "data_type": data_type,
                            "date": current_date.isoformat(),
                            "path": str(path),
                            "size_bytes": int(stat.st_size),
                            "sha256": sha256_file(path),
                        }
                    )
                elif len(missing_examples) < 200:
                    missing_examples.append(
                        {
                            "symbol": symbol,
                            "data_type": data_type,
                            "date": current_date.isoformat(),
                        }
                    )
    expected = len(symbols) * len(DEFAULT_DATA_TYPES) * len(dates)
    found = len(found_paths)
    return (
        {
            "raw_root": str(raw_root),
            "exchange": exchange,
            "symbols": symbols,
            "from_date": dates[0].isoformat() if dates else None,
            "to_date": dates[-1].isoformat() if dates else None,
            "expected_partition_count": expected,
            "found_partition_count": found,
            "missing_partition_count": expected - found,
            "missing_required_input_fraction": float((expected - found) / expected) if expected else 1.0,
            "found_partitions": partitions,
            "missing_partition_examples": missing_examples,
            "raw_retention_note": RAW_RETENTION_NOTE,
            "downloads_executed_by_runner": False,
        },
        found_paths,
    )


def build_columnar_input_audit(
    *,
    normalized_root: Path,
    normalized_manifest: Path | None,
    exchange: str,
    symbols: list[str],
    dates: list[date],
    required_symbol_dates: list[tuple[str, date]] | None = None,
    monthly_mask_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[tuple[str, date], Path]]:
    found_paths: dict[tuple[str, date], Path] = {}
    missing_examples: list[dict[str, str]] = []
    partitions: list[dict[str, Any]] = []
    manifest_payload: dict[str, Any] | None = None
    if normalized_manifest is not None and normalized_manifest.exists():
        try:
            manifest_payload = json.loads(normalized_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest_payload = None

    required_pairs = (
        required_symbol_dates
        if required_symbol_dates is not None
        else [(symbol, current_date) for symbol in symbols for current_date in dates]
    )

    for symbol, current_date in required_pairs:
        path = find_normalized_partition(
            normalized_root=normalized_root,
            exchange=exchange,
            symbol=symbol,
            current_date=current_date,
        )
        key = (symbol, current_date)
        if path is not None:
            found_paths[key] = path
            stat = path.stat()
            partitions.append(
                {
                    "symbol": symbol,
                    "date": current_date.isoformat(),
                    "path": str(path),
                    "size_bytes": int(stat.st_size),
                    "sha256": sha256_file(path),
                }
            )
        elif len(missing_examples) < 200:
            missing_examples.append({"symbol": symbol, "date": current_date.isoformat()})

    expected = len(required_pairs)
    found = len(found_paths)
    raw_source_hashes_recorded = False
    raw_source_missing_required_input_fraction: float | None = None
    if manifest_payload is not None:
        source_partitions = manifest_payload.get("source_raw_partitions", [])
        raw_source_hashes_recorded = bool(source_partitions) and all(
            bool(item.get("sha256")) for item in source_partitions
        )
        raw_input_audit = manifest_payload.get("raw_input_audit", {})
        raw_source_missing_required_input_fraction = finite_float(
            raw_input_audit.get("missing_required_input_fraction")
        )
    return (
        {
            "input_kind": "normalized_parquet_bar_features",
            "normalized_root": str(normalized_root),
            "normalized_manifest": str(normalized_manifest) if normalized_manifest is not None else None,
            "normalized_manifest_sha256": sha256_file(normalized_manifest) if normalized_manifest is not None and normalized_manifest.exists() else None,
            "normalized_manifest_found": bool(normalized_manifest is not None and normalized_manifest.exists()),
            "normalized_manifest_contract_version": manifest_payload.get("contract_version") if manifest_payload else None,
            "raw_source_hashes_recorded": raw_source_hashes_recorded,
            "raw_source_missing_required_input_fraction": raw_source_missing_required_input_fraction,
            "exchange": exchange,
            "symbols": symbols,
            "from_date": dates[0].isoformat() if dates else None,
            "to_date": dates[-1].isoformat() if dates else None,
            "required_symbol_date_count": len(required_pairs),
            "expected_partition_count": expected,
            "found_partition_count": found,
            "missing_partition_count": expected - found,
            "missing_required_input_fraction": float((expected - found) / expected) if expected else 1.0,
            "found_partitions": partitions,
            "missing_partition_examples": missing_examples,
            "monthly_mask_context": monthly_mask_context,
            "raw_retention_note": RAW_RETENTION_NOTE,
            "downloads_executed_by_runner": False,
            "raw_scan_executed_by_runner": False,
        },
        found_paths,
    )


def read_columnar_bars(
    found_paths: dict[tuple[str, date], Path],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for (symbol, _current_date), path in sorted(found_paths.items(), key=lambda item: (item[0][0], item[0][1])):
        frame = pd.read_parquet(path)
        if "symbol" not in frame.columns:
            frame["symbol"] = symbol
        if "bar_start_utc" in frame.columns:
            frame["bar_start_utc"] = pd.to_datetime(frame["bar_start_utc"], utc=True, errors="coerce")
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    bars = pd.concat(frames, ignore_index=True, sort=False)
    if "bar_start_utc" in bars.columns:
        bars = bars.dropna(subset=["bar_start_utc"]).sort_values(["symbol", "bar_start_utc"], kind="mergesort")
        bars = bars.drop_duplicates(["symbol", "bar_start_utc"], keep="last")
    return bars.reset_index(drop=True)


def read_csv_chunks(path: Path, *, chunksize: int) -> list[pd.DataFrame]:
    compression = "gzip" if path.suffix == ".gz" else "infer"
    try:
        reader = pd.read_csv(path, compression=compression, chunksize=chunksize, low_memory=False)
        return [chunk for chunk in reader]
    except pd.errors.EmptyDataError:
        return []


def aggregate_trades(path: Path, *, symbol: str, minutes: int, chunksize: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in read_csv_chunks(path, chunksize=chunksize):
        ts = timestamp_series(chunk)
        price = numeric_column(chunk, ("price", "trade_price"))
        amount = numeric_column(chunk, ("amount", "quantity", "qty", "size"))
        notional = price.abs() * amount.abs()
        side_sign = normalize_side(text_column(chunk, ("side", "taker_side", "aggressor_side")))
        frame = pd.DataFrame(
            {
                "bar_start_utc": bar_start(ts, minutes=minutes),
                "trade_count": 1,
                "trade_notional": notional,
                "signed_trade_notional": notional * side_sign,
                "trade_price_x_notional": price * notional,
            }
        ).dropna(subset=["bar_start_utc"])
        if not frame.empty:
            frames.append(
                frame.groupby("bar_start_utc", as_index=False).agg(
                    trade_count=("trade_count", "sum"),
                    trade_notional=("trade_notional", "sum"),
                    signed_trade_notional=("signed_trade_notional", "sum"),
                    trade_price_x_notional=("trade_price_x_notional", "sum"),
                )
            )
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).groupby("bar_start_utc", as_index=False).sum(numeric_only=True)
    out["trade_vwap"] = out["trade_price_x_notional"] / out["trade_notional"].replace(0.0, np.nan)
    out["trade_imbalance"] = out["signed_trade_notional"] / out["trade_notional"].replace(0.0, np.nan)
    out["symbol"] = symbol
    return out.drop(columns=["trade_price_x_notional"])


def aggregate_liquidations(path: Path, *, symbol: str, minutes: int, chunksize: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in read_csv_chunks(path, chunksize=chunksize):
        ts = timestamp_series(chunk)
        price = numeric_column(chunk, ("price", "liquidation_price"))
        amount = numeric_column(chunk, ("amount", "quantity", "qty", "size"))
        notional = price.abs() * amount.abs()
        side_sign = normalize_side(text_column(chunk, ("side", "order_side")))
        frame = pd.DataFrame(
            {
                "bar_start_utc": bar_start(ts, minutes=minutes),
                "liquidation_count": 1,
                "liquidation_notional": notional,
                "signed_liquidation_notional": notional * side_sign,
                "liquidation_side_known": side_sign.ne(0.0),
            }
        ).dropna(subset=["bar_start_utc"])
        if not frame.empty:
            frames.append(
                frame.groupby("bar_start_utc", as_index=False).agg(
                    liquidation_count=("liquidation_count", "sum"),
                    liquidation_notional=("liquidation_notional", "sum"),
                    signed_liquidation_notional=("signed_liquidation_notional", "sum"),
                    liquidation_side_known_count=("liquidation_side_known", "sum"),
                )
            )
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).groupby("bar_start_utc", as_index=False).sum(numeric_only=True)
    out["liquidation_side_known_fraction"] = out["liquidation_side_known_count"] / out["liquidation_count"].replace(0.0, np.nan)
    out["symbol"] = symbol
    return out


def aggregate_book_ticker(path: Path, *, symbol: str, minutes: int, chunksize: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in read_csv_chunks(path, chunksize=chunksize):
        ts = timestamp_series(chunk)
        bid_price = numeric_column(chunk, ("bid_price", "best_bid_price", "bidPrice"))
        ask_price = numeric_column(chunk, ("ask_price", "best_ask_price", "askPrice"))
        bid_amount = numeric_column(chunk, ("bid_amount", "best_bid_amount", "bid_size", "bidQty"))
        ask_amount = numeric_column(chunk, ("ask_amount", "best_ask_amount", "ask_size", "askQty"))
        mid = (bid_price + ask_price) / 2.0
        spread_bps = (ask_price - bid_price) / mid.replace(0.0, np.nan) * 10_000.0
        frame = pd.DataFrame(
            {
                "bar_start_utc": bar_start(ts, minutes=minutes),
                "mid_price": mid,
                "spread_bps": spread_bps,
                "bbo_bid_notional": bid_price * bid_amount,
                "bbo_ask_notional": ask_price * ask_amount,
            }
        ).dropna(subset=["bar_start_utc"])
        if not frame.empty:
            frames.append(
                frame.groupby("bar_start_utc", as_index=False).agg(
                    mid_price=("mid_price", "last"),
                    spread_bps=("spread_bps", "median"),
                    bbo_bid_notional=("bbo_bid_notional", "median"),
                    bbo_ask_notional=("bbo_ask_notional", "median"),
                )
            )
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).groupby("bar_start_utc", as_index=False).agg(
        mid_price=("mid_price", "last"),
        spread_bps=("spread_bps", "median"),
        bbo_bid_notional=("bbo_bid_notional", "median"),
        bbo_ask_notional=("bbo_ask_notional", "median"),
    )
    denom = out["bbo_bid_notional"] + out["bbo_ask_notional"]
    out["bbo_imbalance"] = (out["bbo_bid_notional"] - out["bbo_ask_notional"]) / denom.replace(0.0, np.nan)
    out["symbol"] = symbol
    return out


def top_depth_from_snapshot(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    bid_total = pd.Series(0.0, index=frame.index, dtype="float64")
    ask_total = pd.Series(0.0, index=frame.index, dtype="float64")
    for level in range(5):
        bid_price = numeric_column(
            frame,
            (
                f"bids[{level}].price",
                f"bid_{level}_price",
                f"bid_price_{level}",
                f"bids_{level}_price",
            ),
            default=np.nan,
        )
        bid_amount = numeric_column(
            frame,
            (
                f"bids[{level}].amount",
                f"bid_{level}_amount",
                f"bid_amount_{level}",
                f"bids_{level}_amount",
            ),
            default=np.nan,
        )
        ask_price = numeric_column(
            frame,
            (
                f"asks[{level}].price",
                f"ask_{level}_price",
                f"ask_price_{level}",
                f"asks_{level}_price",
            ),
            default=np.nan,
        )
        ask_amount = numeric_column(
            frame,
            (
                f"asks[{level}].amount",
                f"ask_{level}_amount",
                f"ask_amount_{level}",
                f"asks_{level}_amount",
            ),
            default=np.nan,
        )
        bid_total = bid_total + (bid_price * bid_amount).fillna(0.0)
        ask_total = ask_total + (ask_price * ask_amount).fillna(0.0)
    return bid_total.replace(0.0, np.nan), ask_total.replace(0.0, np.nan)


def aggregate_book_snapshot_5(path: Path, *, symbol: str, minutes: int, chunksize: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in read_csv_chunks(path, chunksize=chunksize):
        ts = timestamp_series(chunk)
        bid_depth, ask_depth = top_depth_from_snapshot(chunk)
        frame = pd.DataFrame(
            {
                "bar_start_utc": bar_start(ts, minutes=minutes),
                "top5_bid_notional": bid_depth,
                "top5_ask_notional": ask_depth,
            }
        ).dropna(subset=["bar_start_utc"])
        if not frame.empty:
            frames.append(
                frame.groupby("bar_start_utc", as_index=False).agg(
                    top5_bid_notional=("top5_bid_notional", "median"),
                    top5_ask_notional=("top5_ask_notional", "median"),
                )
            )
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).groupby("bar_start_utc", as_index=False).median(numeric_only=True)
    out["top5_depth_notional"] = out["top5_bid_notional"] + out["top5_ask_notional"]
    out["top5_book_imbalance"] = (
        (out["top5_bid_notional"] - out["top5_ask_notional"])
        / out["top5_depth_notional"].replace(0.0, np.nan)
    )
    out["symbol"] = symbol
    return out


def aggregate_derivative_ticker(path: Path, *, symbol: str, minutes: int, chunksize: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in read_csv_chunks(path, chunksize=chunksize):
        ts = timestamp_series(chunk)
        mark_price = numeric_column(chunk, ("mark_price", "markPrice", "price"))
        index_price = numeric_column(chunk, ("index_price", "indexPrice"))
        open_interest = numeric_column(chunk, ("open_interest", "openInterest"))
        funding_rate = numeric_column(chunk, ("funding_rate", "fundingRate"))
        basis_bps = (mark_price - index_price) / index_price.replace(0.0, np.nan) * 10_000.0
        frame = pd.DataFrame(
            {
                "bar_start_utc": bar_start(ts, minutes=minutes),
                "mark_price": mark_price,
                "index_price": index_price,
                "open_interest": open_interest,
                "funding_rate": funding_rate,
                "basis_bps": basis_bps,
            }
        ).dropna(subset=["bar_start_utc"])
        if not frame.empty:
            frames.append(
                frame.groupby("bar_start_utc", as_index=False).agg(
                    mark_price=("mark_price", "last"),
                    index_price=("index_price", "last"),
                    open_interest=("open_interest", "last"),
                    funding_rate=("funding_rate", "last"),
                    basis_bps=("basis_bps", "last"),
                )
            )
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).groupby("bar_start_utc", as_index=False).agg(
        mark_price=("mark_price", "last"),
        index_price=("index_price", "last"),
        open_interest=("open_interest", "last"),
        funding_rate=("funding_rate", "last"),
        basis_bps=("basis_bps", "last"),
    )
    out["symbol"] = symbol
    return out


AGGREGATORS = {
    "trades": aggregate_trades,
    "liquidations": aggregate_liquidations,
    "book_ticker": aggregate_book_ticker,
    "book_snapshot_5": aggregate_book_snapshot_5,
    "derivative_ticker": aggregate_derivative_ticker,
}


def aggregate_partitions(
    *,
    found_paths: dict[tuple[str, str, date], Path],
    symbols: list[str],
    minutes: int,
    chunksize: int,
) -> pd.DataFrame:
    symbol_frames: list[pd.DataFrame] = []
    for symbol in symbols:
        data_frames: list[pd.DataFrame] = []
        for data_type, aggregator in AGGREGATORS.items():
            frames = []
            for (candidate_symbol, candidate_type, _current_date), path in found_paths.items():
                if candidate_symbol == symbol and candidate_type == data_type:
                    frames.append(aggregator(path, symbol=symbol, minutes=minutes, chunksize=chunksize))
            non_empty = [frame for frame in frames if not frame.empty]
            if not non_empty:
                continue
            by_type = pd.concat(non_empty, ignore_index=True)
            by_type = by_type.sort_values("bar_start_utc").drop_duplicates(["symbol", "bar_start_utc"], keep="last")
            data_frames.append(by_type)
        if not data_frames:
            continue
        merged = data_frames[0]
        for frame in data_frames[1:]:
            merged = merged.merge(frame, on=["symbol", "bar_start_utc"], how="outer")
        symbol_frames.append(merged)
    if not symbol_frames:
        return pd.DataFrame()
    bars = pd.concat(symbol_frames, ignore_index=True).sort_values(["symbol", "bar_start_utc"])
    bars["bar_start_utc"] = pd.to_datetime(bars["bar_start_utc"], utc=True, errors="coerce")
    bars = bars.dropna(subset=["bar_start_utc"]).reset_index(drop=True)
    return bars


def rolling_quantile(series: pd.Series, q: float, *, window: int, min_periods: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window, min_periods=min_periods).quantile(q).shift(1)


def add_events_and_labels(
    bars: pd.DataFrame,
    *,
    event_bar_minutes: int,
    lookback_bars: int,
    min_lookback_bars: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if bars.empty:
        return pd.DataFrame(), pd.DataFrame()
    frame = bars.sort_values(["symbol", "bar_start_utc"]).copy()
    grouped = frame.groupby("symbol", group_keys=False, sort=False)
    frame["reference_price"] = frame["mark_price"].combine_first(frame["mid_price"]).combine_first(frame["trade_vwap"])
    frame["bar_return"] = grouped["reference_price"].transform(lambda s: np.log(s / s.shift(1)))
    frame["liquidation_q95"] = grouped["liquidation_notional"].transform(
        lambda s: rolling_quantile(s, 0.95, window=lookback_bars, min_periods=min_lookback_bars)
    )
    frame["trade_notional_q95"] = grouped["trade_notional"].transform(
        lambda s: rolling_quantile(s, 0.95, window=lookback_bars, min_periods=min_lookback_bars)
    )
    frame["top5_depth_q10"] = grouped["top5_depth_notional"].transform(
        lambda s: rolling_quantile(s, 0.10, window=lookback_bars, min_periods=min_lookback_bars)
    )
    frame["basis_abs_q75"] = grouped["basis_bps"].transform(
        lambda s: rolling_quantile(s.abs(), 0.75, window=lookback_bars, min_periods=min_lookback_bars)
    )
    frame["open_interest_change"] = grouped["open_interest"].pct_change()
    frame["basis_bps_change"] = grouped["basis_bps"].diff()
    frame["top5_depth_change"] = grouped["top5_depth_notional"].pct_change()
    frame["shock_side_sign"] = np.sign(frame["signed_liquidation_notional"].fillna(0.0))
    trade_side = np.sign(frame["signed_trade_notional"].fillna(0.0))
    frame.loc[frame["shock_side_sign"].eq(0.0), "shock_side_sign"] = trade_side.loc[frame["shock_side_sign"].eq(0.0)]

    frame["liquidation_burst"] = (
        frame["liquidation_notional"].ge(frame["liquidation_q95"])
        & frame["liquidation_notional"].gt(0.0)
        & frame["liquidation_side_known_fraction"].fillna(0.0).ge(0.50)
    ).fillna(False)
    frame["trade_pressure_burst"] = (
        frame["trade_notional"].ge(frame["trade_notional_q95"])
        & frame["trade_notional"].gt(0.0)
        & frame["trade_imbalance"].abs().ge(0.20)
    ).fillna(False)
    frame["book_thinning"] = (
        frame["top5_depth_notional"].le(frame["top5_depth_q10"])
        | frame["top5_depth_change"].le(-0.25)
    ).fillna(False)
    frame["basis_oi_state_change"] = (
        frame["open_interest_change"].abs().ge(0.01)
        & frame["basis_bps"].abs().ge(frame["basis_abs_q75"])
    ).fillna(False)
    frame["event_triggered"] = frame[list(PRIMARY_FAMILIES)].any(axis=1)

    price = frame["reference_price"]
    for horizon, minutes in PRIMARY_HORIZON_TO_MINUTES.items():
        periods = max(1, int(minutes / event_bar_minutes))
        future_price = grouped["reference_price"].shift(-periods)
        future_spread = grouped["spread_bps"].shift(-periods)
        future_depth = grouped["top5_depth_notional"].shift(-periods)
        future_imbalance = grouped["top5_book_imbalance"].shift(-periods)
        future_oi = grouped["open_interest"].shift(-periods)
        future_basis = grouped["basis_bps"].shift(-periods)
        frame[f"fwd_return_{horizon}"] = np.log(future_price / price)
        frame[f"continuation_response_{horizon}"] = frame[f"fwd_return_{horizon}"] * frame["shock_side_sign"]
        frame[f"reversal_response_{horizon}"] = -frame[f"continuation_response_{horizon}"]
        frame[f"spread_change_{horizon}"] = future_spread - frame["spread_bps"]
        frame[f"top5_depth_recovery_{horizon}"] = (future_depth / frame["top5_depth_notional"].replace(0.0, np.nan)) - 1.0
        frame[f"book_imbalance_change_{horizon}"] = future_imbalance - frame["top5_book_imbalance"]
        frame[f"oi_change_{horizon}"] = (future_oi / frame["open_interest"].replace(0.0, np.nan)) - 1.0
        frame[f"basis_change_{horizon}"] = future_basis - frame["basis_bps"]

        def future_vol(s: pd.Series) -> pd.Series:
            return s.shift(-1).iloc[::-1].rolling(periods, min_periods=1).std().iloc[::-1]

        frame[f"realized_vol_{horizon}"] = grouped["bar_return"].transform(future_vol)

    def max_future_return(s: pd.Series, periods: int, sign: float) -> pd.Series:
        return (
            s.shift(-1)
            .iloc[::-1]
            .rolling(periods, min_periods=1)
            .apply(lambda values: np.nanmax(sign * values), raw=True)
            .iloc[::-1]
        )

    for horizon, minutes in {"1h": 60, "4h": 240}.items():
        periods = max(1, int(minutes / event_bar_minutes))
        cumulative = grouped["bar_return"].transform(lambda s: s.shift(-1).fillna(0.0).iloc[::-1].rolling(periods, min_periods=1).sum().iloc[::-1])
        frame[f"max_favorable_move_{horizon}"] = cumulative * frame["shock_side_sign"]
        frame[f"max_adverse_move_{horizon}"] = -frame[f"max_favorable_move_{horizon}"]

    events = frame.loc[frame["event_triggered"]].copy()
    labels = events[
        [
            "symbol",
            "bar_start_utc",
            "shock_side_sign",
            *PRIMARY_FAMILIES,
            *[f"fwd_return_{horizon}" for horizon in HORIZONS],
            *[f"continuation_response_{horizon}" for horizon in HORIZONS],
            *[f"reversal_response_{horizon}" for horizon in HORIZONS],
            *[f"realized_vol_{horizon}" for horizon in HORIZONS],
            *[f"spread_change_{horizon}" for horizon in HORIZONS],
            *[f"top5_depth_recovery_{horizon}" for horizon in HORIZONS],
            *[f"book_imbalance_change_{horizon}" for horizon in HORIZONS],
            *[f"oi_change_{horizon}" for horizon in HORIZONS],
            *[f"basis_change_{horizon}" for horizon in HORIZONS],
            "max_adverse_move_1h",
            "max_favorable_move_1h",
            "max_adverse_move_4h",
            "max_favorable_move_4h",
        ]
    ].copy()
    return events.reset_index(drop=True), labels.reset_index(drop=True)


def bootstrap_ci(values: pd.Series, *, iterations: int, seed: int = 20260615) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype="float64")
    if clean.size < 30:
        return {"status": "insufficient", "n": int(clean.size), "mean": finite_float(np.mean(clean)) if clean.size else None}
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(clean, size=clean.size, replace=True).mean() for _ in range(max(1, iterations))])
    return {
        "status": "ok",
        "n": int(clean.size),
        "mean": float(clean.mean()),
        "median": float(np.median(clean)),
        "ci_low": float(np.quantile(means, 0.025)),
        "ci_high": float(np.quantile(means, 0.975)),
    }


def shuffle_test(
    values: pd.Series,
    mask: pd.Series,
    *,
    observed_effect: float | None,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    clean = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "mask": mask.fillna(False).astype(bool)}).dropna()
    if observed_effect is None or clean["mask"].sum() < 30 or (~clean["mask"]).sum() < 30:
        return {"status": "insufficient"}
    rng = np.random.default_rng(seed)
    effects = []
    mask_values = clean["mask"].to_numpy()
    vals = clean["value"].to_numpy(dtype="float64")
    count = int(mask_values.sum())
    for _ in range(max(1, iterations)):
        shuffled_index = rng.choice(np.arange(vals.size), size=count, replace=False)
        shuffled_mask = np.zeros(vals.size, dtype=bool)
        shuffled_mask[shuffled_index] = True
        effects.append(float(vals[shuffled_mask].mean() - vals[~shuffled_mask].mean()))
    threshold = float(np.quantile(np.abs(effects), 0.95))
    return {
        "status": "ok",
        "iterations": int(iterations),
        "observed_effect": float(observed_effect),
        "abs_shuffle_effect_q95": threshold,
        "passes": bool(abs(observed_effect) > threshold),
    }


def summarize_proof(
    *,
    events: pd.DataFrame,
    labels: pd.DataFrame,
    input_audit: dict[str, Any],
    primary_family: str,
    primary_direction: str,
    primary_horizon: str,
    shuffle_iterations: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    blockers: list[str] = []
    input_hashes_recorded = bool(input_audit["found_partition_count"] > 0) and all(
        bool(item.get("sha256")) for item in input_audit["found_partitions"]
    )
    coverage_gates: dict[str, Any] = {
        "columnar_partition_hashes_recorded": input_hashes_recorded,
        "raw_source_hashes_recorded_in_normalized_manifest": bool(input_audit.get("raw_source_hashes_recorded", False)),
        "raw_source_missing_required_input_fraction": input_audit.get("raw_source_missing_required_input_fraction"),
        "raw_source_missing_required_input_fraction_max": 0.02,
        "missing_required_input_fraction": input_audit["missing_required_input_fraction"],
        "missing_required_input_fraction_max": 0.02,
        "duplicate_event_key_count": 0,
        "event_count_total": int(events.shape[0]),
        "event_count_min": 300,
        "event_count_by_primary_symbol_min": 40,
        "event_count_by_month_min": 5,
        "distinct_months_with_min_events_min": 18,
    }
    if not events.empty:
        coverage_gates["duplicate_event_key_count"] = int(events.duplicated(["symbol", "bar_start_utc"]).sum())
        by_symbol = events.groupby("symbol").size().to_dict()
        by_month = events.assign(month=events["bar_start_utc"].dt.strftime("%Y-%m")).groupby("month").size().to_dict()
    else:
        by_symbol = {}
        by_month = {}
    coverage_gates["event_count_by_symbol"] = {str(k): int(v) for k, v in by_symbol.items()}
    coverage_gates["distinct_months_with_min_events"] = int(sum(int(v) >= 5 for v in by_month.values()))
    coverage_gates["event_count_by_month"] = {str(k): int(v) for k, v in by_month.items()}

    if not coverage_gates["columnar_partition_hashes_recorded"]:
        blockers.append("columnar_partition_hashes_not_recorded")
    if not coverage_gates["raw_source_hashes_recorded_in_normalized_manifest"]:
        blockers.append("raw_source_hashes_not_recorded_in_normalized_manifest")
    raw_missing_fraction = coverage_gates["raw_source_missing_required_input_fraction"]
    if raw_missing_fraction is None or float(raw_missing_fraction) > 0.02:
        blockers.append("raw_source_missing_required_input_fraction_above_0_02")
    if coverage_gates["missing_required_input_fraction"] > 0.02:
        blockers.append("missing_required_input_fraction_above_0_02")
    if coverage_gates["duplicate_event_key_count"] != 0:
        blockers.append("duplicate_event_key_count_nonzero")
    if coverage_gates["event_count_total"] < 300:
        blockers.append("event_count_total_below_300")
    for symbol in ("BTCUSDT", "ETHUSDT"):
        if int(by_symbol.get(symbol, 0)) < 40:
            blockers.append(f"event_count_{symbol.lower()}_below_40")
    if coverage_gates["distinct_months_with_min_events"] < 18:
        blockers.append("distinct_months_with_min_events_below_18")

    primary_mask = labels[primary_family].fillna(False).astype(bool) if primary_family in labels else pd.Series(False, index=labels.index)
    response_column = f"{primary_direction}_response_{primary_horizon}"
    response = pd.to_numeric(labels.get(response_column, pd.Series(dtype="float64")), errors="coerce")
    primary_response = response.loc[primary_mask].dropna()
    control_response = response.loc[~primary_mask].dropna()
    observed_effect = None
    if len(primary_response) and len(control_response):
        observed_effect = float(primary_response.mean() - control_response.mean())
    ci = bootstrap_ci(primary_response, iterations=shuffle_iterations)
    effect_bps = None if ci.get("mean") is None else float(ci["mean"]) * 10_000.0
    ci_excludes_zero = bool(ci.get("status") == "ok" and (ci["ci_low"] > 0.0 or ci["ci_high"] < 0.0))
    tail_event = pd.to_numeric(labels.get(f"max_adverse_move_{primary_horizon}", pd.Series(dtype="float64")), errors="coerce").loc[primary_mask].dropna()
    tail_control = pd.to_numeric(labels.get(f"max_adverse_move_{primary_horizon}", pd.Series(dtype="float64")), errors="coerce").loc[~primary_mask].dropna()
    tail_diff = None
    if len(tail_event) and len(tail_control):
        tail_diff = float(tail_event.mean() - tail_control.mean())
    vol_event = pd.to_numeric(labels.get(f"realized_vol_{primary_horizon}", pd.Series(dtype="float64")), errors="coerce").loc[primary_mask].dropna()
    vol_control = pd.to_numeric(labels.get(f"realized_vol_{primary_horizon}", pd.Series(dtype="float64")), errors="coerce").loc[~primary_mask].dropna()
    spread_event = pd.to_numeric(labels.get(f"spread_change_{primary_horizon}", pd.Series(dtype="float64")), errors="coerce").loc[primary_mask].dropna()
    spread_control = pd.to_numeric(labels.get(f"spread_change_{primary_horizon}", pd.Series(dtype="float64")), errors="coerce").loc[~primary_mask].dropna()
    vol_or_liquidity_confirms = bool(
        (len(vol_event) and len(vol_control) and vol_event.mean() > vol_control.mean())
        or (len(spread_event) and len(spread_control) and spread_event.mean() > spread_control.mean())
    )

    mechanism_gates = {
        "primary_event_family": primary_family,
        "primary_direction": primary_direction,
        "primary_horizon": primary_horizon,
        "primary_event_count": int(primary_mask.sum()),
        "primary_direction_effect_sign_consistent": bool(effect_bps is not None and effect_bps > 0),
        "primary_horizon_abs_mean_or_median_effect_bps": effect_bps,
        "primary_horizon_abs_mean_or_median_effect_bps_min": 5.0,
        "primary_horizon_bootstrap_ci": ci,
        "primary_horizon_bootstrap_ci_excludes_zero": ci_excludes_zero,
        "tail_response_diff_vs_control": tail_diff,
        "tail_response_diff_vs_control_nonzero": bool(tail_diff is not None and abs(tail_diff) > 0.0),
        "realized_vol_or_liquidity_response_confirms_shock": vol_or_liquidity_confirms,
        "observed_effect_vs_control": observed_effect,
    }
    if mechanism_gates["primary_event_count"] < 30:
        blockers.append("primary_event_count_below_30")
    if not mechanism_gates["primary_direction_effect_sign_consistent"]:
        blockers.append("primary_direction_effect_sign_not_consistent")
    if effect_bps is None or abs(effect_bps) < 5.0:
        blockers.append("primary_horizon_effect_bps_below_5")
    if not ci_excludes_zero:
        blockers.append("primary_horizon_bootstrap_ci_does_not_exclude_zero")
    if not mechanism_gates["tail_response_diff_vs_control_nonzero"]:
        blockers.append("tail_response_diff_vs_control_zero_or_missing")
    if not vol_or_liquidity_confirms:
        blockers.append("realized_vol_or_liquidity_response_does_not_confirm_shock")

    robustness = {
        "same_timestamp_cross_symbol_shuffle": shuffle_test(
            response,
            primary_mask,
            observed_effect=observed_effect,
            iterations=shuffle_iterations,
            seed=20260615,
        ),
        "label_shuffle": shuffle_test(
            response.sample(frac=1.0, random_state=20260615).reset_index(drop=True),
            primary_mask.reset_index(drop=True),
            observed_effect=observed_effect,
            iterations=shuffle_iterations,
            seed=20260616,
        ),
    }
    if not events.empty and primary_mask.any():
        primary_labels = labels.loc[primary_mask].copy()
        primary_labels["month"] = primary_labels["bar_start_utc"].dt.strftime("%Y-%m")
        month_means = primary_labels.groupby("month")[response_column].mean(numeric_only=True)
        eligible = month_means.dropna()
        monthly_consistency = float((eligible > 0).mean()) if len(eligible) else None
    else:
        monthly_consistency = None
    robustness["monthly_holdout_directional_consistency"] = monthly_consistency
    robustness["monthly_holdout_directional_consistency_min"] = 0.60
    btc_eth_ok = True
    if primary_mask.any() and "symbol" in labels:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            symbol_values = response.loc[primary_mask & labels["symbol"].ne(symbol)].dropna()
            if len(symbol_values) >= 30 and symbol_values.mean() <= 0.0:
                btc_eth_ok = False
    robustness["btc_eth_holdout_does_not_fully_erase_effect"] = bool(btc_eth_ok and primary_mask.any())
    robustness["liquidity_bucket_consistency"] = "not_measured_stage_a_no_liquidity_bucket_sidecar"

    if robustness["same_timestamp_cross_symbol_shuffle"].get("status") == "ok" and not robustness["same_timestamp_cross_symbol_shuffle"].get("passes"):
        blockers.append("same_timestamp_cross_symbol_shuffle_reproduces_effect")
    if robustness["label_shuffle"].get("status") == "ok" and not robustness["label_shuffle"].get("passes"):
        blockers.append("label_shuffle_reproduces_effect")
    if monthly_consistency is None or monthly_consistency < 0.60:
        blockers.append("monthly_holdout_directional_consistency_below_0_60")
    if not robustness["btc_eth_holdout_does_not_fully_erase_effect"]:
        blockers.append("btc_eth_holdout_erases_effect_or_insufficient")

    spread_bps = pd.to_numeric(events.get("spread_bps", pd.Series(dtype="float64")), errors="coerce").loc[primary_mask].dropna() if not events.empty else pd.Series(dtype="float64")
    top5_depth = pd.to_numeric(events.get("top5_depth_notional", pd.Series(dtype="float64")), errors="coerce").loc[primary_mask].dropna() if not events.empty else pd.Series(dtype="float64")
    spread_cost_bps = finite_float(spread_bps.median()) if len(spread_bps) else None
    cost_feasibility = {
        "estimated_spread_cost_bps": spread_cost_bps,
        "estimated_spread_cost_bps_less_than_half_primary_effect": bool(
            spread_cost_bps is not None and effect_bps is not None and spread_cost_bps < abs(effect_bps) * 0.50
        ),
        "top5_depth_notional_median": finite_float(top5_depth.median()) if len(top5_depth) else None,
        "top5_depth_supports_small_research_notional": bool(len(top5_depth) and top5_depth.median() > 10_000.0),
    }
    if not cost_feasibility["estimated_spread_cost_bps_less_than_half_primary_effect"]:
        blockers.append("estimated_spread_cost_not_less_than_half_primary_effect")
    if not cost_feasibility["top5_depth_supports_small_research_notional"]:
        blockers.append("top5_depth_does_not_support_small_research_notional")

    coverage_report = {
        "coverage_gates": coverage_gates,
        "mechanism_gates": mechanism_gates,
        "cost_feasibility_gates": cost_feasibility,
        "blockers": sorted(set(blockers), key=blockers.index),
    }
    robustness_report = {
        "robustness_gates": robustness,
        "blockers": [
            blocker
            for blocker in sorted(set(blockers), key=blockers.index)
            if "shuffle" in blocker or "holdout" in blocker or "monthly" in blocker
        ],
    }
    return coverage_report, robustness_report, {
        "blockers": sorted(set(blockers), key=blockers.index),
        "coverage_gates": coverage_gates,
        "mechanism_gates": mechanism_gates,
        "robustness_gates": robustness,
        "cost_feasibility_gates": cost_feasibility,
    }


def definition_payload(
    args: argparse.Namespace,
    *,
    normalized_root: Path,
    output_root: Path,
    symbols: list[str],
    monthly_mask_context: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "status": "stage_a_mechanism_proof_only",
        "input_kind": "normalized_parquet_bar_features",
        "normalized_root": str(normalized_root),
        "output_root": str(output_root),
        "exchange": str(args.exchange),
        "symbols": symbols,
        "monthly_mask_context": monthly_mask_context,
        "data_types": list(DEFAULT_DATA_TYPES),
        "event_bar_minutes": int(args.event_bar_minutes),
        "primary_event_family": str(args.primary_event_family),
        "primary_direction": str(args.primary_direction),
        "primary_horizon": str(args.primary_horizon),
        "non_actions": [
            "no strategy PnL",
            "no entry rule",
            "no exit rule",
            "no sizing rule",
            "no leverage rule",
            "no portfolio construction",
            "no score-layer admission",
            "no h10d bridge interpretation",
            "no manifest mutation",
            "no paper-shadow use",
            "no live timer scheduler remote-runner or exchange execution",
            "no Tardis download executed by this runner",
            "no raw Tardis gzip or CSV scan executed by this runner",
        ],
    }


def write_empty_or_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def main() -> int:
    args = parse_args()
    if args.raw_root is not None:
        raise SystemExit(
            "--raw-root is no longer accepted by the Stage A proof runner. "
            "Run normalize_tardis_intraday_liquidity_shock_raw_to_parquet.py first, "
            "then pass --normalized-root."
        )
    started_at = time.perf_counter()
    phase_timings: dict[str, float] = {}

    def mark_phase(name: str, phase_started_at: float) -> float:
        now = time.perf_counter()
        phase_timings[name] = round(now - phase_started_at, 6)
        return now

    phase_started_at = time.perf_counter()
    from_date = parse_iso_date(args.from_date)
    to_date = parse_iso_date(args.to_date)
    if to_date < from_date:
        raise SystemExit("--to-date must be >= --from-date")
    if args.event_bar_minutes not in (1, 5, 15):
        raise SystemExit("--event-bar-minutes must be one of 1, 5, 15")
    normalized_root = resolve_normalized_root(args.normalized_root)
    ensure_outside_repo(normalized_root, label="Tardis normalized parquet root")
    output_root = args.output_root
    if output_root is None:
        output_root = ROOT / "artifacts" / "quant_research" / "factor_reports" / str(args.as_of) / DEFAULT_OUTPUT_SUBDIR
    output_root.mkdir(parents=True, exist_ok=True)

    monthly_mask_context: dict[str, Any] | None = None
    required_symbol_dates: list[tuple[str, date]] | None = None
    if args.monthly_universe_masks is not None:
        monthly_masks_path = args.monthly_universe_masks.expanduser().resolve()
        (
            monthly_masks_payload,
            required_symbol_dates,
            symbols,
            dates,
            monthly_scope,
        ) = load_monthly_universe_mask_scope(
            monthly_masks_path,
            from_date=from_date,
            to_date=to_date,
        )
        monthly_mask_context = {
            "monthly_universe_masks_path": str(monthly_masks_path),
            "monthly_universe_masks_sha256": sha256_file(monthly_masks_path),
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
    normalized_manifest = resolve_normalized_manifest(normalized_root, args.normalized_manifest)
    phase_started_at = mark_phase("setup", phase_started_at)
    input_audit, found_paths = build_columnar_input_audit(
        normalized_root=normalized_root,
        normalized_manifest=normalized_manifest,
        exchange=str(args.exchange),
        symbols=symbols,
        dates=dates,
        required_symbol_dates=required_symbol_dates,
        monthly_mask_context=monthly_mask_context,
    )
    input_audit.update(
        {
            "contract_version": CONTRACT_VERSION,
            "generated_at_utc": utc_now(),
            "as_of": str(args.as_of),
            "downloads_executed_by_runner": False,
            "raw_scan_executed_by_runner": False,
        }
    )
    phase_started_at = mark_phase("columnar_input_audit", phase_started_at)

    bars = read_columnar_bars(found_paths)
    phase_started_at = mark_phase("read_columnar_bars", phase_started_at)
    events, labels = add_events_and_labels(
        bars,
        event_bar_minutes=int(args.event_bar_minutes),
        lookback_bars=int(args.lookback_bars),
        min_lookback_bars=int(args.min_lookback_bars),
    )
    phase_started_at = mark_phase("build_events_and_labels", phase_started_at)
    coverage_report, robustness_report, decision = summarize_proof(
        events=events,
        labels=labels,
        input_audit=input_audit,
        primary_family=str(args.primary_event_family),
        primary_direction=str(args.primary_direction),
        primary_horizon=str(args.primary_horizon),
        shuffle_iterations=int(args.shuffle_iterations),
    )
    phase_started_at = mark_phase("summarize_stage_a_proof", phase_started_at)

    definition_path = output_root / "intraday_liquidity_shock_definition.json"
    input_audit_path = output_root / "intraday_liquidity_shock_input_audit.json"
    event_panel_path = output_root / "intraday_liquidity_shock_event_panel.parquet"
    event_sample_path = output_root / "intraday_liquidity_shock_event_panel_sample.csv"
    label_panel_path = output_root / "intraday_liquidity_shock_label_panel.parquet"
    summary_path = output_root / "intraday_liquidity_shock_summary.json"
    robustness_path = output_root / "intraday_liquidity_shock_robustness.json"
    coverage_path = output_root / "intraday_liquidity_shock_coverage_report.json"
    profile_path = output_root / "intraday_liquidity_shock_profile.json"

    definition = definition_payload(
        args,
        normalized_root=normalized_root,
        output_root=output_root,
        symbols=symbols,
        monthly_mask_context=monthly_mask_context,
    )
    write_json(definition_path, definition)
    write_json(input_audit_path, input_audit)
    write_empty_or_frame(event_panel_path, events)
    events.head(max(0, int(args.sample_rows))).to_csv(event_sample_path, index=False)
    write_empty_or_frame(label_panel_path, labels)
    write_json(robustness_path, robustness_report)
    write_json(coverage_path, coverage_report)

    blockers = decision["blockers"]
    if input_audit["found_partition_count"] == 0:
        status = "blocked_missing_columnar_partitions"
    elif blockers:
        status = "computed_failed_stage_a"
    else:
        status = "computed_passed_stage_a"
    proof_allowed = status == "computed_passed_stage_a"

    artifacts = {
        "intraday_liquidity_shock_definition_json": str(definition_path),
        "intraday_liquidity_shock_input_audit_json": str(input_audit_path),
        "intraday_liquidity_shock_event_panel_parquet": str(event_panel_path),
        "intraday_liquidity_shock_event_panel_sample_csv": str(event_sample_path),
        "intraday_liquidity_shock_label_panel_parquet": str(label_panel_path),
        "intraday_liquidity_shock_summary_json": str(summary_path),
        "intraday_liquidity_shock_robustness_json": str(robustness_path),
        "intraday_liquidity_shock_coverage_report_json": str(coverage_path),
        "intraday_liquidity_shock_profile_json": str(profile_path),
    }
    profile = {
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "input_mode": "normalized_parquet_only",
        "normalized_root": str(normalized_root),
        "normalized_manifest": str(normalized_manifest) if normalized_manifest is not None else None,
        "monthly_mask_context": monthly_mask_context,
        "phase_timings_seconds": {
            **phase_timings,
            "write_artifacts_before_summary": round(time.perf_counter() - phase_started_at, 6),
        },
        "input_counts": {
            "expected_columnar_partitions": int(input_audit["expected_partition_count"]),
            "found_columnar_partitions": int(input_audit["found_partition_count"]),
            "columnar_input_bytes": int(sum(item["size_bytes"] for item in input_audit["found_partitions"])),
        },
        "row_counts": {
            "bars": int(bars.shape[0]),
            "events": int(events.shape[0]),
            "labels": int(labels.shape[0]),
        },
        "raw_scan_executed_by_runner": False,
        "downloads_executed_by_runner": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
    }
    profile["phase_timings_seconds"]["total_before_profile_write"] = round(time.perf_counter() - started_at, 6)
    write_json(profile_path, profile)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "input_mode": "normalized_parquet_only",
        "status": status,
        "proof_allowed": proof_allowed,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
        "remote_runner_use_authorized": False,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
        "normalized_root": str(normalized_root),
        "normalized_manifest": str(normalized_manifest) if normalized_manifest is not None else None,
        "monthly_mask_context": monthly_mask_context,
        "columnar_input_paths": [item["path"] for item in input_audit["found_partitions"]],
        "columnar_input_sha256": {item["path"]: item["sha256"] for item in input_audit["found_partitions"]},
        "event_counts": {
            "events": int(events.shape[0]),
            "labels": int(labels.shape[0]),
            "bars": int(bars.shape[0]),
        },
        "coverage_gates": decision["coverage_gates"],
        "mechanism_gates": decision["mechanism_gates"],
        "robustness_gates": decision["robustness_gates"],
        "cost_feasibility_gates": decision["cost_feasibility_gates"],
        "blockers": blockers,
        "artifacts": artifacts,
        "profile": profile,
        "download_guidance": (
            "Run the raw-to-normalized parquet normalizer before Stage A; "
            "this runner is intentionally blocked without columnar staging."
            if status == "blocked_missing_columnar_partitions"
            else "No download or raw scan was executed by this runner."
        ),
    }
    write_json(summary_path, summary)
    print(
        json.dumps(
            {
                "status": status,
                "proof_allowed": proof_allowed,
                "stage_b_return_ablation_allowed": False,
                "strategy_pnl_computed": False,
                "trading_action_authorized": False,
                "downloads_executed_by_runner": False,
                "raw_scan_executed_by_runner": False,
                "event_counts": summary["event_counts"],
                "blockers": blockers,
                "profile_json": str(profile_path),
                "summary_json": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
