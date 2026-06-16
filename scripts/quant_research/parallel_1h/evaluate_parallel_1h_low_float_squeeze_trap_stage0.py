from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


CONTRACT_VERSION = "parallel_1h_low_float_squeeze_trap_stage0.v1"
RESEARCH_ID = "low_float_squeeze_trap_stage0_1h"
DEFAULT_HORIZONS = (1, 3, 6, 12, 24, 48, 72)
DEFAULT_SHUFFLE_ITERATIONS = 200
HOUR_MS = 60 * 60 * 1000

CG_COLUMNS = [
    "open_time_ms",
    "long_liquidation_usd",
    "short_liquidation_usd",
    "global_account_long_pct",
    "top_trader_long_pct",
    "orderbook_bids_usd",
    "orderbook_asks_usd",
    "orderbook_bids_quantity",
    "orderbook_asks_quantity",
    "taker_buy_volume_usd",
    "taker_sell_volume_usd",
]

DV_COLUMNS = [
    "open_time_ms",
    "funding_rate",
    "funding_sample_count",
    "open_interest",
    "open_interest_value",
    "perp_close",
    "perp_quote_volume_usd",
]

CORE_FEATURE_COLUMNS = [
    "perp_close",
    "open_interest_value",
    "funding_rate_state",
    "orderbook_imbalance",
    "taker_imbalance",
    "perp_quote_volume_usd",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 1h evaluator for the parallel low-float squeeze-trap lane. "
            "This is a research diagnostic only and does not touch h10d promotion state."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument(
        "--symbols",
        default="",
        help="Optional comma-separated symbols like BTCUSDT,ETHUSDT. Empty means all local overlap.",
    )
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _resolve_market_history_root(path: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history"


def _subject_from_symbol(symbol: str) -> str:
    text = str(symbol).strip().upper()
    return text[:-4] if text.endswith("USDT") else text


def _discover_symbols(root: Path, requested: str = "", limit: int = 0) -> list[str]:
    if requested.strip():
        symbols = [
            item.strip().upper()
            for item in requested.split(",")
            if item.strip()
        ]
        return [symbol if symbol.endswith("USDT") else f"{symbol}USDT" for symbol in symbols]
    cg_root = root / "coinglass_extended"
    dv_root = root / "binance_derivatives"
    cg_symbols = {
        path.name.upper()
        for path in cg_root.glob("*USDT")
        if (path / "1h").exists() and list((path / "1h").glob("*.csv.gz"))
    }
    dv_symbols = {
        path.name.upper()
        for path in dv_root.glob("*USDT")
        if (path / "1h").exists() and list((path / "1h").glob("*.csv.gz"))
    }
    symbols = sorted(cg_symbols.intersection(dv_symbols))
    if limit and limit > 0:
        symbols = symbols[: int(limit)]
    return symbols


def _read_partitions(path: Path, columns: list[str]) -> pd.DataFrame:
    paths = sorted(glob.glob(str(path / "*.csv.gz")))
    if not paths:
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    wanted = set(columns)
    for item in paths:
        chunk = pd.read_csv(
            item,
            compression="gzip",
            usecols=lambda column: column in wanted,
        )
        frames.append(chunk)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    for column in columns:
        if column not in out.columns:
            out[column] = np.nan
    out = out[columns].copy()
    out["open_time_ms"] = pd.to_numeric(out["open_time_ms"], errors="coerce")
    out = out.dropna(subset=["open_time_ms"])
    out["open_time_ms"] = out["open_time_ms"].astype("int64")
    out = out.sort_values("open_time_ms").drop_duplicates("open_time_ms").reset_index(drop=True)
    for column in columns:
        if column != "open_time_ms":
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _rolling_quantile(series: pd.Series, q: float, *, window: int = 720, min_periods: int = 168) -> pd.Series:
    return series.rolling(window, min_periods=min_periods).quantile(q).shift(1)


def _safe_log_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    valid = num.gt(0.0) & den.gt(0.0)
    out = pd.Series(np.nan, index=num.index, dtype="float64")
    out.loc[valid] = np.log(num.loc[valid] / den.loc[valid])
    return out


def _future_sum(series: pd.Series, horizon: int) -> pd.Series:
    shifted = pd.to_numeric(series, errors="coerce").shift(-1)
    return shifted.iloc[::-1].rolling(int(horizon), min_periods=1).sum().iloc[::-1]


def _future_log_return(close: pd.Series, horizon: int) -> pd.Series:
    return _safe_log_ratio(close.shift(-int(horizon)), close)


def _load_symbol_frame(root: Path, symbol: str, horizons: tuple[int, ...]) -> pd.DataFrame:
    cg_path = root / "coinglass_extended" / symbol / "1h"
    dv_path = root / "binance_derivatives" / symbol / "1h"
    cg = _read_partitions(cg_path, CG_COLUMNS)
    dv = _read_partitions(dv_path, DV_COLUMNS)
    if cg.empty or dv.empty:
        return pd.DataFrame()
    frame = cg.merge(dv, on="open_time_ms", how="inner")
    if frame.empty:
        return pd.DataFrame()
    frame = frame.sort_values("open_time_ms").drop_duplicates("open_time_ms").reset_index(drop=True)
    subject = _subject_from_symbol(symbol)
    frame["symbol"] = symbol
    frame["subject"] = subject
    frame["timestamp_utc"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    frame["timestamp_utc_text"] = frame["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    close = pd.to_numeric(frame["perp_close"], errors="coerce")
    oi = pd.to_numeric(frame["open_interest_value"], errors="coerce")
    volume = pd.to_numeric(frame["perp_quote_volume_usd"], errors="coerce")
    bids = pd.to_numeric(frame["orderbook_bids_usd"], errors="coerce")
    asks = pd.to_numeric(frame["orderbook_asks_usd"], errors="coerce")
    taker_buy = pd.to_numeric(frame["taker_buy_volume_usd"], errors="coerce")
    taker_sell = pd.to_numeric(frame["taker_sell_volume_usd"], errors="coerce")
    funding = pd.to_numeric(frame["funding_rate"], errors="coerce")
    sample_count = pd.to_numeric(frame.get("funding_sample_count"), errors="coerce")

    frame["return_1h_log"] = _safe_log_ratio(close, close.shift(1))
    frame["recent_pump_6h_log_return"] = _safe_log_ratio(close, close.shift(6))
    frame["recent_pump_24h_log_return"] = _safe_log_ratio(close, close.shift(24))
    pump_6h_q95 = _rolling_quantile(frame["recent_pump_6h_log_return"], 0.95)
    pump_24h_q95 = _rolling_quantile(frame["recent_pump_24h_log_return"], 0.95)
    frame["recent_pump_flag"] = (
        frame["recent_pump_6h_log_return"].ge(np.maximum(pump_6h_q95, 0.05))
        | frame["recent_pump_24h_log_return"].ge(np.maximum(pump_24h_q95, 0.10))
    ).fillna(False)

    frame["oi_log_change_6h"] = _safe_log_ratio(oi, oi.shift(6))
    frame["oi_log_change_24h"] = _safe_log_ratio(oi, oi.shift(24))
    oi_6h_q75 = _rolling_quantile(frame["oi_log_change_6h"], 0.75)
    frame["oi_acceleration_positive_flag"] = frame["oi_log_change_6h"].ge(
        np.maximum(oi_6h_q75, 0.0)
    ).fillna(False)
    frame["oi_collapse_confirmed_flag"] = (
        frame["oi_log_change_6h"].le(-0.05) | frame["oi_log_change_24h"].le(-0.10)
    ).fillna(False)

    if sample_count.notna().any():
        known_funding = funding.where(sample_count.fillna(0.0).gt(0.0))
    else:
        known_funding = funding
    frame["funding_rate_state"] = known_funding.ffill(limit=8)
    funding_q20 = _rolling_quantile(frame["funding_rate_state"], 0.20)
    frame["funding_deep_negative_flag"] = (
        frame["funding_rate_state"].lt(0.0)
        & (
            frame["funding_rate_state"].le(funding_q20)
            | frame["funding_rate_state"].le(-0.0001)
        )
    ).fillna(False)

    ob_total = (bids.fillna(0.0) + asks.fillna(0.0)).replace(0.0, np.nan)
    frame["orderbook_imbalance"] = (bids.fillna(0.0) - asks.fillna(0.0)) / ob_total
    frame["bid_depth_log_change_6h"] = _safe_log_ratio(bids, bids.shift(6))
    ob_q60 = _rolling_quantile(frame["orderbook_imbalance"], 0.60)
    bid_change_q75 = _rolling_quantile(frame["bid_depth_log_change_6h"], 0.75)
    frame["orderbook_bid_support_flag"] = (
        frame["orderbook_imbalance"].ge(np.maximum(ob_q60, 0.05))
        | (
            frame["bid_depth_log_change_6h"].ge(np.maximum(bid_change_q75, 0.0))
            & frame["orderbook_imbalance"].gt(0.0)
        )
    ).fillna(False)

    taker_total = (taker_buy.fillna(0.0) + taker_sell.fillna(0.0)).replace(0.0, np.nan)
    frame["taker_imbalance"] = (taker_buy.fillna(0.0) - taker_sell.fillna(0.0)) / taker_total
    taker_q75 = _rolling_quantile(frame["taker_imbalance"], 0.75)
    frame["taker_buy_dominance_flag"] = frame["taker_imbalance"].ge(
        np.maximum(taker_q75, 0.05)
    ).fillna(False)

    frame["liquidation_total_usd"] = (
        pd.to_numeric(frame["long_liquidation_usd"], errors="coerce").fillna(0.0)
        + pd.to_numeric(frame["short_liquidation_usd"], errors="coerce").fillna(0.0)
    )
    frame["short_liq_share"] = (
        pd.to_numeric(frame["short_liquidation_usd"], errors="coerce").fillna(0.0)
        / frame["liquidation_total_usd"].replace(0.0, np.nan)
    )
    frame["quote_volume_24h"] = volume.rolling(24, min_periods=12).sum()
    frame["volume_oi_ratio_24h"] = frame["quote_volume_24h"] / oi.replace(0.0, np.nan)
    frame["volume_oi_ratio_24h_q95"] = _rolling_quantile(frame["volume_oi_ratio_24h"], 0.95)
    frame["fake_liquidity_risk_flag"] = (
        frame["volume_oi_ratio_24h"].ge(frame["volume_oi_ratio_24h_q95"])
        & frame["volume_oi_ratio_24h"].ge(2.0)
    ).fillna(False)
    frame["capacity_trade_005_usd"] = volume * 0.005
    frame["capacity_inventory_002_usd"] = oi * 0.02
    frame["capacity_proxy_usd"] = np.minimum(frame["capacity_trade_005_usd"], frame["capacity_inventory_002_usd"])
    frame["slippage_or_capacity_proxy"] = (
        frame["return_1h_log"].abs()
        / np.sqrt((volume.fillna(0.0).clip(lower=1.0) / 1_000_000.0).clip(lower=1e-9))
    )

    funding_cashflow = pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    if sample_count.notna().any():
        funding_cashflow = funding.where(sample_count.fillna(0.0).gt(0.0), 0.0).fillna(0.0)
    else:
        funding_cashflow = (frame["funding_rate_state"].fillna(0.0) / 8.0)
    for horizon in horizons:
        frame[f"forward_{horizon}h_log_return"] = _future_log_return(close, horizon)
        frame[f"forward_{horizon}h_short_return"] = -frame[f"forward_{horizon}h_log_return"]
        frame[f"funding_h{horizon}h_short_pnl_estimate"] = _future_sum(funding_cashflow, horizon)

    frame["trap_raw_flag"] = (
        frame["recent_pump_flag"]
        & frame["oi_acceleration_positive_flag"]
        & frame["funding_deep_negative_flag"]
        & (frame["orderbook_bid_support_flag"] | frame["taker_buy_dominance_flag"])
        & ~frame["oi_collapse_confirmed_flag"]
    ).fillna(False)
    return frame


def _load_research_frame(root: Path, symbols: list[str], horizons: tuple[int, ...]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[pd.DataFrame] = []
    symbol_status: dict[str, Any] = {}
    for symbol in symbols:
        try:
            frame = _load_symbol_frame(root, symbol, horizons)
            if frame.empty:
                symbol_status[symbol] = {"status": "empty"}
                continue
            rows.append(frame)
            symbol_status[symbol] = {
                "status": "loaded",
                "row_count": int(len(frame)),
                "start_utc": str(frame["timestamp_utc_text"].min()),
                "end_utc": str(frame["timestamp_utc_text"].max()),
            }
        except Exception as exc:  # noqa: BLE001 - research diagnostic should report per-symbol failures.
            symbol_status[symbol] = {"status": "error", "error": str(exc)[:300]}
    if not rows:
        return pd.DataFrame(), {"symbol_status": symbol_status}
    frame = pd.concat(rows, ignore_index=True)
    frame = frame.sort_values(["open_time_ms", "subject"]).reset_index(drop=True)
    liquidity_pct = (
        pd.to_numeric(frame["quote_volume_24h"], errors="coerce")
        .groupby(frame["open_time_ms"])
        .rank(method="average", pct=True)
    )
    frame["liquidity_percentile_1h"] = liquidity_pct
    frame["liquidity_bucket"] = np.select(
        [
            liquidity_pct.ge(0.67),
            liquidity_pct.ge(0.33),
            liquidity_pct.notna(),
        ],
        ["high_liquidity", "mid_liquidity", "tail_liquidity"],
        default="unknown",
    )
    frame["low_float_proxy_flag"] = frame["liquidity_bucket"].isin(["mid_liquidity", "tail_liquidity"])
    frame["post_pump_short_candidate_flag"] = (
        frame["recent_pump_flag"] & frame["low_float_proxy_flag"]
    ).fillna(False)
    frame["low_float_squeeze_trap_flag"] = (
        frame["post_pump_short_candidate_flag"] & frame["trap_raw_flag"]
    ).fillna(False)
    return frame, {"symbol_status": symbol_status}


def _mask_summary(frame: pd.DataFrame, mask: pd.Series, horizons: tuple[int, ...]) -> dict[str, Any]:
    subset = frame.loc[mask].copy()
    if subset.empty:
        return {"row_count": 0}
    payload: dict[str, Any] = {
        "row_count": int(len(subset)),
        "symbol_count": int(subset["subject"].astype(str).nunique()),
        "timestamp_count": int(subset["open_time_ms"].nunique()),
        "start_utc": str(subset["timestamp_utc_text"].min()),
        "end_utc": str(subset["timestamp_utc_text"].max()),
    }
    for horizon in horizons:
        forward = pd.to_numeric(subset[f"forward_{horizon}h_log_return"], errors="coerce").dropna()
        short_ret = -forward
        payload[f"h{horizon}"] = {
            "observation_count": int(len(forward)),
            "mean_long_return": float(forward.mean()) if len(forward) else None,
            "median_long_return": float(forward.median()) if len(forward) else None,
            "mean_short_return": float(short_ret.mean()) if len(short_ret) else None,
            "median_short_return": float(short_ret.median()) if len(short_ret) else None,
            "adverse_squeeze_gt_5pct_fraction": float((forward > 0.05).mean()) if len(forward) else None,
            "adverse_squeeze_gt_10pct_fraction": float((forward > 0.10).mean()) if len(forward) else None,
        }
    return payload


def _forward_return_table(frame: pd.DataFrame, horizons: tuple[int, ...]) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    trap = frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool)
    return {
        "trap_flagged_candidate_rows": _mask_summary(frame, candidates & trap, horizons),
        "candidate_control_rows": _mask_summary(frame, candidates & ~trap, horizons),
        "all_post_pump_candidate_rows": _mask_summary(frame, candidates, horizons),
    }


def _effect_delta(
    event_frame: pd.DataFrame,
    *,
    flag_column: str,
    horizon: int = 24,
) -> dict[str, Any]:
    if event_frame.empty or flag_column not in event_frame.columns:
        return {
            "status": "insufficient",
            "trap_count": 0,
            "control_count": 0,
            "short_return_delta": None,
        }
    flag = event_frame[flag_column].fillna(False).astype(bool)
    short_ret = pd.to_numeric(event_frame[f"forward_{horizon}h_short_return"], errors="coerce")
    trap_ret = short_ret.loc[flag].dropna()
    control_ret = short_ret.loc[~flag].dropna()
    if trap_ret.empty or control_ret.empty:
        return {
            "status": "insufficient",
            "trap_count": int(len(trap_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "status": "ok",
        "trap_count": int(len(trap_ret)),
        "control_count": int(len(control_ret)),
        "trap_short_return_mean": float(trap_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(trap_ret.mean() - control_ret.mean()),
        "interpretation": "negative_delta_means_trap_rows_are_worse_shorts_than_control",
    }


def _cohort_after_delay(
    frame: pd.DataFrame,
    *,
    mask: pd.Series,
    delay_h: int,
    columns: list[str],
) -> pd.DataFrame:
    events = frame.loc[mask, ["subject", "open_time_ms", "liquidity_bucket"]].copy()
    if events.empty:
        return pd.DataFrame()
    events["entry_open_time_ms"] = events["open_time_ms"] + int(delay_h) * HOUR_MS
    lookup_columns = ["subject", "open_time_ms", *columns]
    lookup = frame[lookup_columns].copy()
    lookup = lookup.rename(columns={"open_time_ms": "entry_open_time_ms"})
    merged = events.merge(lookup, on=["subject", "entry_open_time_ms"], how="inner")
    return merged


def _delayed_effect(frame: pd.DataFrame, *, delay_h: int, horizon: int = 24) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    trap = frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool)
    columns = [
        f"forward_{horizon}h_short_return",
        f"forward_{horizon}h_log_return",
        "capacity_proxy_usd",
        "funding_rate_state",
    ]
    trap_delayed = _cohort_after_delay(frame, mask=candidates & trap, delay_h=delay_h, columns=columns)
    control_delayed = _cohort_after_delay(frame, mask=candidates & ~trap, delay_h=delay_h, columns=columns)
    if trap_delayed.empty or control_delayed.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "trap_count": int(len(trap_delayed)),
            "control_count": int(len(control_delayed)),
            "short_return_delta": None,
        }
    trap_ret = pd.to_numeric(trap_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    control_ret = pd.to_numeric(control_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    if trap_ret.empty or control_ret.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "trap_count": int(len(trap_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "delay_h": int(delay_h),
        "status": "ok",
        "trap_count": int(len(trap_ret)),
        "control_count": int(len(control_ret)),
        "trap_short_return_mean": float(trap_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(trap_ret.mean() - control_ret.mean()),
    }


def _shuffle_flags_within_timestamp(events: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    shuffled = pd.Series(False, index=events.index)
    for _, idx in events.groupby("open_time_ms").groups.items():
        values = events.loc[idx, "low_float_squeeze_trap_flag"].to_numpy(dtype=bool)
        shuffled.loc[idx] = rng.permutation(values)
    return shuffled.astype(bool)


def _time_shift_flags_by_symbol(events: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    shifted = pd.Series(False, index=events.index)
    for _, idx in events.sort_values(["subject", "open_time_ms"]).groupby("subject").groups.items():
        ordered_idx = list(idx)
        values = events.loc[ordered_idx, "low_float_squeeze_trap_flag"].to_numpy(dtype=bool)
        if len(values) < 2:
            shifted.loc[ordered_idx] = values
            continue
        offset = int(rng.integers(1, len(values)))
        shifted.loc[ordered_idx] = np.roll(values, offset)
    return shifted.astype(bool)


def _shuffle_tests(frame: pd.DataFrame, *, iterations: int, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, flag_column="low_float_squeeze_trap_flag", horizon=horizon)
    observed_delta = observed.get("short_return_delta")
    if observed_delta is None:
        return {
            "status": "insufficient",
            "observed": observed,
            "tests": {},
            "passed": False,
        }
    rng = np.random.default_rng(20260507)
    tests: dict[str, Any] = {}

    shuffled_deltas: list[float] = []
    for _ in range(iterations):
        local = events.copy()
        local["_shuffle_flag"] = _shuffle_flags_within_timestamp(local, rng)
        delta = _effect_delta(local, flag_column="_shuffle_flag", horizon=horizon).get("short_return_delta")
        if delta is not None:
            shuffled_deltas.append(float(delta))
    arr = np.asarray(shuffled_deltas, dtype="float64")
    tests["same_timestamp_feature_shuffle"] = _shuffle_summary(arr, float(observed_delta), iterations)

    shifted_deltas = []
    for _ in range(iterations):
        local = events.copy()
        local["_shift_flag"] = _time_shift_flags_by_symbol(local, rng)
        delta = _effect_delta(local, flag_column="_shift_flag", horizon=horizon).get("short_return_delta")
        if delta is not None:
            shifted_deltas.append(float(delta))
    arr = np.asarray(shifted_deltas, dtype="float64")
    tests["symbol_time_shift_shuffle"] = _shuffle_summary(arr, float(observed_delta), iterations)

    label_deltas = []
    base_short = events[f"forward_{horizon}h_short_return"].copy()
    for _ in range(iterations):
        local = events.copy()
        shuffled_short = base_short.copy()
        for _, idx in local.groupby("open_time_ms").groups.items():
            values = shuffled_short.loc[idx].to_numpy(dtype="float64")
            shuffled_short.loc[idx] = rng.permutation(values)
        local[f"forward_{horizon}h_short_return"] = shuffled_short
        delta = _effect_delta(local, flag_column="low_float_squeeze_trap_flag", horizon=horizon).get("short_return_delta")
        if delta is not None:
            label_deltas.append(float(delta))
    arr = np.asarray(label_deltas, dtype="float64")
    tests["same_timestamp_label_shuffle"] = _shuffle_summary(arr, float(observed_delta), iterations)

    return {
        "status": "ok",
        "horizon": f"h{horizon}",
        "observed": observed,
        "tests": tests,
        "passed": bool(observed_delta < 0.0 and all(test.get("passed") for test in tests.values())),
    }


def _shuffle_summary(arr: np.ndarray, observed_delta: float, iterations: int) -> dict[str, Any]:
    if arr.size == 0:
        return {"passed": False, "iterations": int(iterations), "valid_iterations": 0}
    observed_lower_tail_quantile = float((arr <= observed_delta).mean())
    return {
        "passed": bool(observed_delta < 0.0 and observed_lower_tail_quantile <= 0.10),
        "iterations": int(iterations),
        "valid_iterations": int(arr.size),
        "observed_short_return_delta": float(observed_delta),
        "shuffle_mean_delta": float(np.nanmean(arr)),
        "shuffle_p05_delta": float(np.nanpercentile(arr, 5)),
        "shuffle_p50_delta": float(np.nanpercentile(arr, 50)),
        "observed_lower_tail_quantile": observed_lower_tail_quantile,
        "pass_rule": "observed delta must be negative and in bottom 10pct of shuffled deltas",
    }


def _symbol_holdout(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, flag_column="low_float_squeeze_trap_flag", horizon=horizon)
    rows: dict[str, Any] = {}
    for subject, group in events.groupby("subject"):
        local = _effect_delta(group, flag_column="low_float_squeeze_trap_flag", horizon=horizon)
        if int(local.get("trap_count") or 0) >= 3 and int(local.get("control_count") or 0) >= 3:
            rows[str(subject)] = local
    leave_one_out: dict[str, Any] = {}
    for subject in sorted(events["subject"].astype(str).unique()):
        local = events.loc[events["subject"].astype(str).ne(subject)]
        leave_one_out[subject] = _effect_delta(local, flag_column="low_float_squeeze_trap_flag", horizon=horizon)
    eligible = [row for row in rows.values() if row.get("short_return_delta") is not None]
    sign_consistent = [
        float(row["short_return_delta"]) < 0.0
        for row in eligible
    ]
    trap_counts = (
        events.loc[events["low_float_squeeze_trap_flag"].fillna(False).astype(bool)]
        .groupby("subject")
        .size()
    )
    total_traps = int(trap_counts.sum())
    top_share = float(trap_counts.max() / total_traps) if total_traps else 1.0
    leave_one_deltas = [
        row.get("short_return_delta")
        for row in leave_one_out.values()
        if row.get("short_return_delta") is not None
    ]
    leave_one_pass = bool(leave_one_deltas and all(float(delta) < 0.0 for delta in leave_one_deltas))
    sign_fraction = float(np.mean(sign_consistent)) if sign_consistent else 0.0
    passed = bool(
        observed.get("short_return_delta") is not None
        and float(observed["short_return_delta"]) < 0.0
        and len(eligible) >= 3
        and sign_fraction >= 0.60
        and top_share <= 0.30
        and leave_one_pass
    )
    return {
        "horizon": f"h{horizon}",
        "observed": observed,
        "eligible_symbol_count": int(len(eligible)),
        "directionally_consistent_symbol_fraction": sign_fraction,
        "top_trap_symbol_event_share": top_share,
        "by_symbol": rows,
        "leave_one_symbol_out": leave_one_out,
        "passed": passed,
    }


def _liquidity_bucket_consistency(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    rows: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        local = _effect_delta(group, flag_column="low_float_squeeze_trap_flag", horizon=horizon)
        rows[str(bucket)] = local
    eligible = [
        row
        for row in rows.values()
        if int(row.get("trap_count") or 0) >= 10
        and int(row.get("control_count") or 0) >= 10
        and row.get("short_return_delta") is not None
    ]
    passed = bool(len(eligible) >= 2 and all(float(row["short_return_delta"]) < 0.0 for row in eligible))
    return {
        "horizon": f"h{horizon}",
        "bucket_results": rows,
        "eligible_bucket_count": int(len(eligible)),
        "passed": passed,
        "pass_rule": "at least two buckets with >=10 trap/control observations and negative short-return delta",
    }


def _delay_robustness(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    scenarios = {
        f"delay_{delay}h": _delayed_effect(frame, delay_h=delay, horizon=horizon)
        for delay in (0, 1, 6, 24)
    }
    stress = [
        row
        for label, row in scenarios.items()
        if label in {"delay_1h", "delay_6h", "delay_24h"}
    ]
    passed = bool(
        stress
        and all(
            row.get("short_return_delta") is not None
            and float(row["short_return_delta"]) < 0.0
            and int(row.get("trap_count") or 0) >= 10
            and int(row.get("control_count") or 0) >= 10
            for row in stress
        )
    )
    return {
        "horizon": f"h{horizon}",
        "scenarios": scenarios,
        "passed": passed,
    }


def _funding_drag_summary(frame: pd.DataFrame, horizons: tuple[int, ...]) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    trap = frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool)
    out: dict[str, Any] = {}
    for cohort_name, mask in {
        "trap_flagged_candidate_rows": candidates & trap,
        "candidate_control_rows": candidates & ~trap,
    }.items():
        subset = frame.loc[mask]
        summary: dict[str, Any] = {"row_count": int(len(subset))}
        for horizon in horizons:
            col = f"funding_h{horizon}h_short_pnl_estimate"
            values = pd.to_numeric(subset.get(col), errors="coerce").dropna()
            summary[f"h{horizon}"] = {
                "observation_count": int(len(values)),
                "mean_short_funding_pnl_estimate": float(values.mean()) if len(values) else None,
                "negative_funding_drag_fraction": float((values < 0.0).mean()) if len(values) else None,
            }
        out[cohort_name] = summary
    return out


def _capacity_summary(frame: pd.DataFrame) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    trap = frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool)
    out: dict[str, Any] = {}
    for cohort_name, mask in {
        "trap_flagged_candidate_rows": candidates & trap,
        "candidate_control_rows": candidates & ~trap,
    }.items():
        subset = frame.loc[mask].copy()
        capacity = pd.to_numeric(subset.get("capacity_proxy_usd"), errors="coerce").dropna()
        vol_oi = pd.to_numeric(subset.get("volume_oi_ratio_24h"), errors="coerce").dropna()
        slippage = pd.to_numeric(subset.get("slippage_or_capacity_proxy"), errors="coerce").dropna()
        out[cohort_name] = {
            "row_count": int(len(subset)),
            "capacity_proxy_usd_mean": float(capacity.mean()) if len(capacity) else None,
            "capacity_proxy_usd_p10": float(capacity.quantile(0.10)) if len(capacity) else None,
            "capacity_proxy_usd_median": float(capacity.median()) if len(capacity) else None,
            "volume_oi_ratio_24h_mean": float(vol_oi.mean()) if len(vol_oi) else None,
            "fake_liquidity_risk_fraction": float(
                subset["fake_liquidity_risk_flag"].fillna(False).astype(bool).mean()
            )
            if len(subset)
            else None,
            "slippage_proxy_mean": float(slippage.mean()) if len(slippage) else None,
            "max_trade_participation_rate": 0.005,
            "max_inventory_participation_rate": 0.02,
        }
    return out


def _event_count_by_symbol(frame: pd.DataFrame) -> dict[str, int]:
    events = frame.loc[frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool)]
    counts = events.groupby("subject").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _event_count_by_liquidity_bucket(frame: pd.DataFrame) -> dict[str, int]:
    events = frame.loc[frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool)]
    counts = events.groupby("liquidity_bucket").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _data_sources_and_coverage(frame: pd.DataFrame, meta: dict[str, Any], root: Path) -> dict[str, Any]:
    loaded = {
        symbol: status
        for symbol, status in dict(meta.get("symbol_status") or {}).items()
        if status.get("status") == "loaded"
    }
    payload: dict[str, Any] = {
        "market_history_root": str(root),
        "sources": {
            "perp_1h": "binance_derivatives/<SYM>USDT/1h",
            "coinglass_extended_1h": "coinglass_extended/<SYM>USDT/1h",
        },
        "provider_trust_notes": [
            "CoinGlass spot coverage is not treated as trust; this evaluator uses perp close from binance_derivatives for returns.",
            "CoinGlass extended orderbook/taker/liquidation fields are research inputs and remain subject to provider-quality audit before promotion.",
            "True low-float metadata is not local; liquidity_bucket is only a proxy.",
        ],
        "loaded_symbol_count": int(len(loaded)),
        "symbol_status": meta.get("symbol_status", {}),
    }
    if frame.empty:
        payload.update({"row_count": 0, "status": "empty"})
        return payload
    payload.update(
        {
            "status": "ok",
            "row_count": int(len(frame)),
            "subject_count": int(frame["subject"].astype(str).nunique()),
            "timestamp_count": int(frame["open_time_ms"].nunique()),
            "start_utc": str(frame["timestamp_utc_text"].min()),
            "end_utc": str(frame["timestamp_utc_text"].max()),
            "core_feature_non_null_fraction": {
                column: float(pd.to_numeric(frame[column], errors="coerce").notna().mean())
                if column in frame.columns
                else 0.0
                for column in CORE_FEATURE_COLUMNS
            },
        }
    )
    return payload


def _feature_definitions() -> dict[str, Any]:
    return {
        "recent_pump_flag": (
            "6h log return >= max(symbol rolling 30d q95, 5%) OR "
            "24h log return >= max(symbol rolling 30d q95, 10%)."
        ),
        "oi_acceleration_positive_flag": "6h OI-value log change >= max(symbol rolling 30d q75, 0).",
        "funding_deep_negative_flag": "latest known funding sample is negative and <= rolling q20 or <= -1bp.",
        "orderbook_bid_support_flag": "bid/ask USD imbalance above rolling q60/5% or bid depth replenishes with positive imbalance.",
        "taker_buy_dominance_flag": "taker buy-sell imbalance above rolling q75/5%.",
        "oi_collapse_confirmed_flag": "6h OI value <= -5% or 24h OI value <= -10%.",
        "low_float_proxy_flag": "1h liquidity bucket is mid_liquidity or tail_liquidity; true float/unlock metadata is not local.",
        "post_pump_short_candidate_flag": "recent_pump_flag and low_float_proxy_flag.",
        "low_float_squeeze_trap_flag": (
            "post_pump_short_candidate_flag AND OI acceleration AND deep negative funding AND "
            "(bid support OR taker-buy dominance) AND NOT OI collapse."
        ),
        "capacity_proxy_usd": "min(0.5% of current 1h quote volume, 2% of OI value).",
        "funding_short_pnl_estimate": "future sum of funding samples over each horizon; negative means short pays funding.",
        "pit_rule": "all thresholds are rolling and shifted one bar; forward returns are used only as labels.",
    }


def _selected_short_changed_rows_equivalent(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    effect = _effect_delta(events, flag_column="low_float_squeeze_trap_flag", horizon=horizon)
    changed = events.loc[events["low_float_squeeze_trap_flag"].fillna(False).astype(bool)]
    return {
        "interaction_type": "selected_short_do_not_short_or_reduce_short_equivalent",
        "candidate_short_rows": int(len(events)),
        "changed_rows": int(len(changed)),
        "changed_fraction": float(len(changed) / max(len(events), 1)),
        "primary_horizon": f"h{horizon}",
        "effect": effect,
        "note": (
            "There is no canonical 1h parent portfolio yet, so changed_rows means "
            "post-pump low-float-proxy short candidates that the trap state would veto or resize."
        ),
    }


def _pass_fail_decision(
    *,
    frame: pd.DataFrame,
    shuffle_tests: dict[str, Any],
    symbol_holdout: dict[str, Any],
    liquidity_bucket_consistency: dict[str, Any],
    delay_robustness: dict[str, Any],
) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool) if not frame.empty else pd.Series(dtype=bool)
    traps = frame["low_float_squeeze_trap_flag"].fillna(False).astype(bool) if not frame.empty else pd.Series(dtype=bool)
    candidate_count = int(candidates.sum()) if not frame.empty else 0
    trap_count = int((candidates & traps).sum()) if not frame.empty else 0
    blockers: list[str] = []
    if frame.empty:
        blockers.append("no_research_frame")
    if frame["subject"].nunique() < 10 if not frame.empty else True:
        blockers.append("loaded_symbol_count_below_10")
    if candidate_count < 100:
        blockers.append("post_pump_candidate_count_below_100")
    if trap_count < 30:
        blockers.append("trap_event_count_below_30")

    failed: list[str] = []
    if not shuffle_tests.get("passed"):
        failed.append("shuffle_tests_failed")
    if not symbol_holdout.get("passed"):
        failed.append("symbol_holdout_failed")
    if not liquidity_bucket_consistency.get("passed"):
        failed.append("liquidity_bucket_consistency_failed")
    if not delay_robustness.get("passed"):
        failed.append("delay_robustness_failed")

    if blockers:
        label = "blocked"
    elif failed:
        label = "fail"
    else:
        label = "pass"
    return {
        "label": label,
        "blockers": blockers,
        "failed_checks": failed,
        "candidate_short_row_count": candidate_count,
        "trap_event_count": trap_count,
        "decision_rule": "pass only if data minimums clear and shuffle, symbol holdout, liquidity bucket, and delay robustness all pass",
    }


def _next_landing_shape(decision: dict[str, Any]) -> dict[str, Any]:
    if decision.get("label") == "pass":
        return {
            "recommended_shape": "selected_short_reduced_exposure_then_veto_ab",
            "next_step": "Build a quarantined 1h parent interaction simulator; do not bridge to h10d yet.",
        }
    if decision.get("label") == "blocked":
        return {
            "recommended_shape": "data_quality_or_coverage_repair",
            "next_step": "Repair blockers before interpreting alpha.",
        }
    return {
        "recommended_shape": "fail_closed_or_redefine_state",
        "next_step": "Do not promote. Inspect failed buckets/symbols before trying post_squeeze_exit_short.",
    }


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    output_path: Path,
    as_of: str,
    horizons: tuple[int, ...],
    shuffle_iterations: int,
) -> dict[str, Any]:
    shuffle_tests = _shuffle_tests(frame, iterations=shuffle_iterations, horizon=24) if not frame.empty else {"passed": False}
    symbol_holdout = _symbol_holdout(frame, horizon=24) if not frame.empty else {"passed": False}
    liquidity_bucket_consistency = (
        _liquidity_bucket_consistency(frame, horizon=24) if not frame.empty else {"passed": False}
    )
    delay_robustness = _delay_robustness(frame, horizon=24) if not frame.empty else {"passed": False}
    decision = _pass_fail_decision(
        frame=frame,
        shuffle_tests=shuffle_tests,
        symbol_holdout=symbol_holdout,
        liquidity_bucket_consistency=liquidity_bucket_consistency,
        delay_robustness=delay_robustness,
    )
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage0",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "data_sources_and_coverage": _data_sources_and_coverage(frame, meta, root),
        "feature_definitions": _feature_definitions(),
        "event_count_by_symbol": _event_count_by_symbol(frame) if not frame.empty else {},
        "event_count_by_liquidity_bucket": _event_count_by_liquidity_bucket(frame) if not frame.empty else {},
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": _forward_return_table(frame, horizons)
        if not frame.empty
        else {},
        "selected_short_changed_rows_equivalent": _selected_short_changed_rows_equivalent(frame, horizon=24)
        if not frame.empty
        else {},
        "funding_drag_summary": _funding_drag_summary(frame, horizons) if not frame.empty else {},
        "slippage_or_capacity_proxy": _capacity_summary(frame) if not frame.empty else {},
        "shuffle_tests": shuffle_tests,
        "symbol_holdout": symbol_holdout,
        "liquidity_bucket_consistency": liquidity_bucket_consistency,
        "delay_robustness": delay_robustness,
        "pass_fail_decision": decision,
        "next_landing_shape": _next_landing_shape(decision),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = _resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "low_float_squeeze_trap_stage0_1h.json"
    horizons = tuple(DEFAULT_HORIZONS)
    symbols = _discover_symbols(root, requested=str(args.symbols), limit=int(args.symbol_limit))
    frame, meta = _load_research_frame(root, symbols, horizons)
    report = _write_report(
        frame=frame,
        meta=meta,
        root=root,
        output_path=output_path,
        as_of=str(args.as_of),
        horizons=horizons,
        shuffle_iterations=int(args.shuffle_iterations),
    )
    compact = {
        "output_path": str(output_path),
        "research_id": report["research_id"],
        "loaded_symbol_count": report["data_sources_and_coverage"].get("loaded_symbol_count"),
        "row_count": report["data_sources_and_coverage"].get("row_count"),
        "candidate_short_row_count": report["pass_fail_decision"].get("candidate_short_row_count"),
        "trap_event_count": report["pass_fail_decision"].get("trap_event_count"),
        "event_count_by_liquidity_bucket": report.get("event_count_by_liquidity_bucket"),
        "primary_effect_h24": report.get("selected_short_changed_rows_equivalent", {}).get("effect"),
        "shuffle_passed": report.get("shuffle_tests", {}).get("passed"),
        "symbol_holdout_passed": report.get("symbol_holdout", {}).get("passed"),
        "liquidity_bucket_consistency_passed": report.get("liquidity_bucket_consistency", {}).get("passed"),
        "delay_robustness_passed": report.get("delay_robustness", {}).get("passed"),
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

