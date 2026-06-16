from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.market_data.binance_ohlcv import (
    EXCHANGE,
    RESEARCH_INTERVALS,
    _build_interval_context,
    _combine_market_status,
    _compute_breakout_samples,
    _market_symbol_pairs_from_mapping,
    build_ohlcv_context,
    build_ohlcv_context_text,
    canonical_interval,
    load_interval_rows,
    resolve_external_history_root,
)

from .binance_derivatives import load_derivatives_rows, resolve_external_derivatives_root
from .coinglass_oi_provenance import (
    load_oi_provenance_frame,
    resolve_external_oi_provenance_root,
)
from .contracts import read_json


def load_ohlcv_frame(
    *,
    symbol: str,
    market_type: str,
    interval: str,
    external_root: Path | None,
    spot_external_root: Path | None = None,
    end_time_ms: int,
) -> pd.DataFrame:
    rows = load_routed_ohlcv_rows(
        symbol=symbol,
        market_type=market_type,
        interval=interval,
        external_root=external_root,
        spot_external_root=spot_external_root,
    )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    numeric_columns = [
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.loc[frame["open_time_ms"] <= end_time_ms].copy()
    frame.sort_values("open_time_ms", inplace=True)
    return frame


def load_routed_ohlcv_rows(
    *,
    symbol: str,
    market_type: str,
    interval: str,
    external_root: Path | None,
    spot_external_root: Path | None = None,
    start_time_ms: int | None = None,
) -> list[dict[str, str]]:
    resolved_fallback_root = resolve_external_history_root(external_root=external_root)
    if market_type == "spot" and spot_external_root is not None:
        resolved_spot_root = resolve_external_history_root(external_root=spot_external_root)
        spot_rows = load_interval_rows(
            external_root=resolved_spot_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
        )
        if spot_rows:
            return spot_rows
    return load_interval_rows(
        external_root=resolved_fallback_root,
        market_type=market_type,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
    )


def load_derivatives_frame(
    *,
    symbol: str,
    interval: str,
    external_root: Path | None,
    end_time_ms: int,
    oi_provenance_external_root: Path | None = None,
    use_oi_provenance_sidecar: bool = True,
) -> pd.DataFrame:
    rows = load_derivatives_rows(
        external_root=resolve_external_derivatives_root(external_root=external_root),
        symbol=symbol,
        interval=interval,
    )
    frame = pd.DataFrame(rows) if rows else pd.DataFrame()
    if use_oi_provenance_sidecar:
        sidecar_root = resolve_external_oi_provenance_root(external_root=oi_provenance_external_root)
        if sidecar_root.exists():
            sidecar = load_oi_provenance_frame(
                symbol=symbol,
                interval=interval,
                external_root=sidecar_root,
                end_time_ms=end_time_ms,
            )
            frame = _overlay_oi_provenance_sidecar(frame=frame, sidecar=sidecar)
    if frame.empty:
        return pd.DataFrame()
    for column in (
        "funding_rate",
        "funding_sample_count",
        "open_interest",
        "open_interest_value",
        "perp_close",
        "perp_quote_volume_usd",
    ):
        if column not in frame.columns:
            frame[column] = pd.NA
    for column in (
        "open_time_ms",
        "close_time_ms",
        "funding_rate",
        "funding_sample_count",
        "open_interest",
        "open_interest_value",
        "perp_close",
        "perp_quote_volume_usd",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.loc[frame["open_time_ms"] <= end_time_ms].copy()
    frame.sort_values("open_time_ms", inplace=True)
    return frame


def _overlay_oi_provenance_sidecar(*, frame: pd.DataFrame, sidecar: pd.DataFrame) -> pd.DataFrame:
    if sidecar.empty:
        return frame
    sidecar = sidecar.copy()
    sidecar["open_time_ms"] = pd.to_numeric(sidecar["open_time_ms"], errors="coerce")
    sidecar = sidecar.loc[sidecar["open_time_ms"].notna()].copy()
    sidecar["open_time_ms"] = sidecar["open_time_ms"].astype("int64")
    if frame.empty:
        merged = sidecar.copy()
        for column in (
            "funding_rate",
            "funding_sample_count",
            "open_interest",
            "perp_close",
            "perp_quote_volume_usd",
        ):
            if column not in merged.columns:
                merged[column] = pd.NA
        return merged
    frame = frame.copy()
    frame["open_time_ms"] = pd.to_numeric(frame["open_time_ms"], errors="coerce")
    frame = frame.loc[frame["open_time_ms"].notna()].copy()
    frame["open_time_ms"] = frame["open_time_ms"].astype("int64")
    sidecar_columns = [
        column
        for column in (
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
            "open_interest_value_provider",
            "open_interest_value_source",
            "open_interest_value_source_interval",
            "open_interest_value_canonical_policy",
            "open_interest_value_sample_count",
            "source",
        )
        if column in sidecar.columns
    ]
    sidecar_for_merge = sidecar[["open_time_ms", *sidecar_columns]].rename(
        columns={column: f"__oi_sidecar_{column}" for column in sidecar_columns}
    )
    merged = frame.merge(sidecar_for_merge, on="open_time_ms", how="outer")
    if "__oi_sidecar_close_time_ms" in merged.columns:
        if "close_time_ms" not in merged.columns:
            merged["close_time_ms"] = pd.NA
        merged["close_time_ms"] = _prefer_sidecar_series(
            sidecar=merged["__oi_sidecar_close_time_ms"],
            base=merged["close_time_ms"],
        )
    if "__oi_sidecar_open_interest_value" in merged.columns:
        if "open_interest_value" not in merged.columns:
            merged["open_interest_value"] = pd.NA
        merged["open_interest_value"] = _prefer_sidecar_series(
            sidecar=merged["__oi_sidecar_open_interest_value"],
            base=merged["open_interest_value"],
        )
    for column in (
        "open_interest_value_native_usd",
        "open_interest_coin",
        "binance_perp_close",
        "open_interest_value_derived_usd",
        "derived_native_rel_diff",
        "derived_native_formula_status",
        "oi_value_provenance",
        "price_source_for_derived_value",
        "open_interest_value_provider",
        "open_interest_value_source",
        "open_interest_value_source_interval",
        "open_interest_value_canonical_policy",
        "open_interest_value_sample_count",
    ):
        sidecar_column = f"__oi_sidecar_{column}"
        if sidecar_column not in merged.columns:
            continue
        if column not in merged.columns:
            merged[column] = pd.NA
        merged[column] = _prefer_sidecar_series(sidecar=merged[sidecar_column], base=merged[column])
    if "__oi_sidecar_source" in merged.columns:
        if "source" not in merged.columns:
            merged["source"] = pd.NA
        merged["source"] = _prefer_sidecar_series(sidecar=merged["source"], base=merged["__oi_sidecar_source"])
    merged.drop(columns=[column for column in merged.columns if column.startswith("__oi_sidecar_")], inplace=True)
    return merged


def _prefer_sidecar_series(*, sidecar: pd.Series, base: pd.Series) -> pd.Series:
    return sidecar.where(sidecar.notna(), base)


def aggregate_1h_to_4h_context(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["bucket_open_ms"] = (working["open_time_ms"] // 14_400_000) * 14_400_000
    working["return_1h"] = working["close"].pct_change()
    output = working.groupby("bucket_open_ms", sort=True).agg(
        intraday_quote_volume_4h=("quote_volume", "sum"),
        intraday_realized_vol_4h=("return_1h", lambda values: float(pd.Series(values).fillna(0.0).std(ddof=0))),
    ).reset_index()
    output.rename(columns={"bucket_open_ms": "open_time_ms"}, inplace=True)
    return output


def aggregate_1h_to_1d_context(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["bucket_open_ms"] = (working["open_time_ms"] // 86_400_000) * 86_400_000
    working["return_1h"] = working["close"].pct_change()
    output = working.groupby("bucket_open_ms", sort=True).agg(
        intraday_quote_volume_1d=("quote_volume", "sum"),
        intraday_realized_vol_1d=("return_1h", lambda values: float(pd.Series(values).fillna(0.0).std(ddof=0))),
    ).reset_index()
    output.rename(columns={"bucket_open_ms": "open_time_ms"}, inplace=True)
    return output


def aggregate_4h_to_1d_context(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["bucket_open_ms"] = (working["open_time_ms"] // 86_400_000) * 86_400_000
    working["return_4h"] = working["close"].pct_change()
    output = working.groupby("bucket_open_ms", sort=True).agg(
        intraday_quote_volume_4h_to_1d=("quote_volume", "sum"),
        intraday_realized_vol_4h_to_1d=("return_4h", lambda values: float(pd.Series(values).fillna(0.0).std(ddof=0))),
    ).reset_index()
    output.rename(columns={"bucket_open_ms": "open_time_ms"}, inplace=True)
    return output


def as_of_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    as_of_end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, 59, tzinfo=UTC)
    return int(as_of_end.timestamp() * 1000)


def load_workbench_thesis_profiles(*, workbench_root: Path) -> list[dict[str, Any]]:
    if not workbench_root.exists():
        return []
    return [read_json(path) for path in sorted(workbench_root.glob("*/thesis_profile.json"))]


def build_history_bundle_for_subject(
    *,
    subject: str,
    scope: str,
    market_symbols: dict[str, Any],
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
) -> dict[str, Any]:
    if spot_ohlcv_external_root is None:
        return build_ohlcv_context(
            external_root=resolve_external_history_root(external_root=ohlcv_external_root),
            market_symbols=market_symbols,
            scope=scope,
        )
    resolved_fallback_root = resolve_external_history_root(external_root=ohlcv_external_root)
    resolved_spot_root = resolve_external_history_root(external_root=spot_ohlcv_external_root)
    resolved_intervals = tuple(canonical_interval(item) for item in RESEARCH_INTERVALS)
    markets: dict[str, Any] = {}
    all_ready = True
    any_ready = False
    breakout_comparison_ready = False
    for market_type, symbol in _market_symbol_pairs_from_mapping(market_symbols):
        interval_contexts: dict[str, Any] = {}
        for interval in resolved_intervals:
            rows = load_routed_ohlcv_rows(
                symbol=symbol,
                market_type=market_type,
                interval=interval,
                external_root=resolved_fallback_root,
                spot_external_root=resolved_spot_root,
            )
            interval_contexts[interval] = _build_interval_context(rows=rows, interval=interval)
        daily_rows = load_routed_ohlcv_rows(
            symbol=symbol,
            market_type=market_type,
            interval="1d",
            external_root=resolved_fallback_root,
            spot_external_root=resolved_spot_root,
        )
        breakout_samples = _compute_breakout_samples(daily_rows)
        market_status = _combine_market_status(interval_contexts=interval_contexts)
        breakout_ready_for_market = len(breakout_samples) > 0
        breakout_comparison_ready = breakout_comparison_ready or breakout_ready_for_market
        markets[market_type] = {
            "market_type": market_type,
            "symbol": symbol,
            "status": market_status,
            "intervals": interval_contexts,
            "breakout_samples_1d": breakout_samples[:3],
            "breakout_comparison_ready": breakout_ready_for_market,
        }
        if market_status == "full":
            any_ready = True
        if market_status != "full":
            all_ready = False
    if all_ready and markets:
        overall_status = "full"
    elif any_ready:
        overall_status = "partial"
    else:
        overall_status = "missing"
    context = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "exchange": EXCHANGE,
        "scope": scope,
        "market_symbols": {
            "spot_symbol": market_symbols.get("spot_symbol"),
            "usdm_symbol": market_symbols.get("usdm_symbol"),
        },
        "history_coverage": {
            "status": overall_status,
            "scope": scope,
            "markets": {
                market_type: {
                    "symbol": entry["symbol"],
                    "status": entry["status"],
                    "intervals": {
                        interval: {
                            "bars": entry["intervals"][interval]["bar_count"],
                            "coverage_days": entry["intervals"][interval]["coverage_days"],
                            "ready": entry["intervals"][interval]["ready"],
                        }
                        for interval in resolved_intervals
                    },
                }
                for market_type, entry in markets.items()
            },
            "breakout_comparison_ready": breakout_comparison_ready,
        },
        "markets": markets,
    }
    context["summary_text"] = build_ohlcv_context_text(context)
    return context
