from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.parallel_1h import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval  # noqa: E402


CONTRACT_VERSION = "parallel_1h_fake_liquidity_capacity_haircut_stage0.v1"
RESEARCH_ID = "fake_liquidity_capacity_haircut_stage0_1h"
DEFAULT_HORIZONS = trap_eval.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = 200
HOUR_MS = trap_eval.HOUR_MS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 1h evaluator for fake-liquidity capacity haircut. "
            "Research diagnostic only; does not touch h10d promotion state."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _rolling_quantile_by_symbol(
    grouped: pd.core.groupby.generic.DataFrameGroupBy,
    column: str,
    q: float,
) -> pd.Series:
    return grouped[column].transform(lambda s: trap_eval._rolling_quantile(s, q))


def _add_fake_liquidity_capacity_state(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["subject", "open_time_ms"]).copy()
    grouped = out.groupby("subject", group_keys=False, sort=False)

    volume = pd.to_numeric(out["perp_quote_volume_usd"], errors="coerce")
    oi = pd.to_numeric(out["open_interest_value"], errors="coerce")
    bids = pd.to_numeric(out["orderbook_bids_usd"], errors="coerce")
    asks = pd.to_numeric(out["orderbook_asks_usd"], errors="coerce")
    taker_buy = pd.to_numeric(out["taker_buy_volume_usd"], errors="coerce")
    taker_sell = pd.to_numeric(out["taker_sell_volume_usd"], errors="coerce")
    capacity = pd.to_numeric(out["capacity_proxy_usd"], errors="coerce")
    slippage = pd.to_numeric(out["slippage_or_capacity_proxy"], errors="coerce")

    out["orderbook_depth_usd"] = bids.fillna(0.0) + asks.fillna(0.0)
    out["taker_total_volume_usd"] = taker_buy.fillna(0.0) + taker_sell.fillna(0.0)
    out["taker_to_book_ratio_1h"] = (
        out["taker_total_volume_usd"] / out["orderbook_depth_usd"].replace(0.0, np.nan)
    )
    out["book_depth_to_volume_1h"] = out["orderbook_depth_usd"] / volume.replace(0.0, np.nan)
    out["abs_taker_imbalance"] = pd.to_numeric(out["taker_imbalance"], errors="coerce").abs()
    out["abs_orderbook_imbalance"] = pd.to_numeric(out["orderbook_imbalance"], errors="coerce").abs()

    out["capacity_proxy_usd_q25"] = _rolling_quantile_by_symbol(grouped, "capacity_proxy_usd", 0.25)
    out["open_interest_value_q20"] = _rolling_quantile_by_symbol(grouped, "open_interest_value", 0.20)
    out["orderbook_depth_usd_q20"] = _rolling_quantile_by_symbol(grouped, "orderbook_depth_usd", 0.20)
    out["book_depth_to_volume_q20"] = _rolling_quantile_by_symbol(grouped, "book_depth_to_volume_1h", 0.20)
    out["taker_to_book_ratio_q90"] = _rolling_quantile_by_symbol(grouped, "taker_to_book_ratio_1h", 0.90)
    out["abs_taker_imbalance_q75"] = _rolling_quantile_by_symbol(grouped, "abs_taker_imbalance", 0.75)
    out["abs_taker_imbalance_q90"] = _rolling_quantile_by_symbol(grouped, "abs_taker_imbalance", 0.90)
    out["abs_orderbook_imbalance_q90"] = _rolling_quantile_by_symbol(grouped, "abs_orderbook_imbalance", 0.90)
    out["slippage_proxy_q90"] = _rolling_quantile_by_symbol(grouped, "slippage_or_capacity_proxy", 0.90)

    out["volume_oi_brushing_extreme_flag"] = (
        out["fake_liquidity_risk_flag"].fillna(False).astype(bool)
        | (
            pd.to_numeric(out["volume_oi_ratio_24h"], errors="coerce").ge(
                pd.to_numeric(out["volume_oi_ratio_24h_q95"], errors="coerce")
            )
            & pd.to_numeric(out["volume_oi_ratio_24h"], errors="coerce").ge(2.0)
        )
    ).fillna(False)
    out["thin_capacity_flag"] = (
        capacity.le(pd.to_numeric(out["capacity_proxy_usd_q25"], errors="coerce"))
        | oi.le(pd.to_numeric(out["open_interest_value_q20"], errors="coerce"))
    ).fillna(False)
    out["book_thinness_flag"] = (
        out["orderbook_depth_usd"].le(pd.to_numeric(out["orderbook_depth_usd_q20"], errors="coerce"))
        | out["book_depth_to_volume_1h"].le(pd.to_numeric(out["book_depth_to_volume_q20"], errors="coerce"))
    ).fillna(False)
    out["taker_book_dislocation_flag"] = (
        out["taker_to_book_ratio_1h"].ge(np.maximum(out["taker_to_book_ratio_q90"], 1.0))
        | (
            out["abs_taker_imbalance"].ge(out["abs_taker_imbalance_q90"])
            & out["abs_orderbook_imbalance"].ge(out["abs_orderbook_imbalance_q90"])
        )
        | (
            out["book_thinness_flag"]
            & out["abs_taker_imbalance"].ge(out["abs_taker_imbalance_q75"])
        )
    ).fillna(False)
    out["slippage_proxy_extreme_flag"] = slippage.ge(
        pd.to_numeric(out["slippage_proxy_q90"], errors="coerce")
    ).fillna(False)

    out["capacity_haircut_candidate_flag"] = out["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    out["fake_liquidity_capacity_haircut_flag"] = (
        out["capacity_haircut_candidate_flag"]
        & (
            (
                out["volume_oi_brushing_extreme_flag"]
                & (
                    out["thin_capacity_flag"]
                    | out["taker_book_dislocation_flag"]
                    | out["slippage_proxy_extreme_flag"]
                )
            )
            | (
                out["thin_capacity_flag"]
                & out["taker_book_dislocation_flag"]
                & out["slippage_proxy_extreme_flag"]
            )
        )
    ).fillna(False)
    out["capacity_haircut_multiplier"] = np.select(
        [
            out["fake_liquidity_capacity_haircut_flag"],
            out["capacity_haircut_candidate_flag"]
            & (
                out["volume_oi_brushing_extreme_flag"]
                | out["thin_capacity_flag"]
                | out["taker_book_dislocation_flag"]
            ),
        ],
        [0.25, 0.50],
        default=1.0,
    )
    out["capacity_after_haircut_usd"] = (
        pd.to_numeric(out["capacity_proxy_usd"], errors="coerce")
        * pd.to_numeric(out["capacity_haircut_multiplier"], errors="coerce")
    )
    return out


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
            "short_win_fraction": float((short_ret > 0.0).mean()) if len(short_ret) else None,
            "adverse_squeeze_gt_5pct_fraction": float((forward > 0.05).mean()) if len(forward) else None,
            "adverse_squeeze_gt_10pct_fraction": float((forward > 0.10).mean()) if len(forward) else None,
        }
    return payload


def _forward_return_table(frame: pd.DataFrame, horizons: tuple[int, ...]) -> dict[str, Any]:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    haircut = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    return {
        "haircut_rows": _mask_summary(frame, candidates & haircut, horizons),
        "candidate_control_rows": _mask_summary(frame, candidates & ~haircut, horizons),
        "all_capacity_haircut_candidates": _mask_summary(frame, candidates, horizons),
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
            "haircut_count": 0,
            "control_count": 0,
            "short_return_delta": None,
        }
    flag = event_frame[flag_column].fillna(False).astype(bool)
    short_ret = pd.to_numeric(event_frame[f"forward_{horizon}h_short_return"], errors="coerce")
    haircut_ret = short_ret.loc[flag].dropna()
    control_ret = short_ret.loc[~flag].dropna()
    if haircut_ret.empty or control_ret.empty:
        return {
            "status": "insufficient",
            "haircut_count": int(len(haircut_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "status": "ok",
        "haircut_count": int(len(haircut_ret)),
        "control_count": int(len(control_ret)),
        "haircut_short_return_mean": float(haircut_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(haircut_ret.mean() - control_ret.mean()),
        "interpretation": "negative_delta_means_haircut_rows_are_worse_shorts_than_control",
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
    return events.merge(lookup, on=["subject", "entry_open_time_ms"], how="inner")


def _delayed_effect(frame: pd.DataFrame, *, delay_h: int, horizon: int = 24) -> dict[str, Any]:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    haircut = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    columns = [
        f"forward_{horizon}h_short_return",
        f"forward_{horizon}h_log_return",
        "capacity_proxy_usd",
        "slippage_or_capacity_proxy",
    ]
    haircut_delayed = _cohort_after_delay(frame, mask=candidates & haircut, delay_h=delay_h, columns=columns)
    control_delayed = _cohort_after_delay(frame, mask=candidates & ~haircut, delay_h=delay_h, columns=columns)
    if haircut_delayed.empty or control_delayed.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "haircut_count": int(len(haircut_delayed)),
            "control_count": int(len(control_delayed)),
            "short_return_delta": None,
        }
    haircut_ret = pd.to_numeric(haircut_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    control_ret = pd.to_numeric(control_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    if haircut_ret.empty or control_ret.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "haircut_count": int(len(haircut_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "delay_h": int(delay_h),
        "status": "ok",
        "haircut_count": int(len(haircut_ret)),
        "control_count": int(len(control_ret)),
        "haircut_short_return_mean": float(haircut_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(haircut_ret.mean() - control_ret.mean()),
    }


def _shuffle_flags_within_timestamp(events: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    shuffled = pd.Series(False, index=events.index)
    for _, idx in events.groupby("open_time_ms").groups.items():
        values = events.loc[idx, "fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        shuffled.loc[idx] = rng.permutation(values)
    return shuffled.astype(bool)


def _time_shift_flags_by_symbol(events: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    shifted = pd.Series(False, index=events.index)
    for _, idx in events.sort_values(["subject", "open_time_ms"]).groupby("subject").groups.items():
        ordered_idx = list(idx)
        values = events.loc[ordered_idx, "fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        if len(values) < 2:
            shifted.loc[ordered_idx] = values
            continue
        offset = int(rng.integers(1, len(values)))
        shifted.loc[ordered_idx] = np.roll(values, offset)
    return shifted.astype(bool)


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


def _shuffle_tests(frame: pd.DataFrame, *, iterations: int, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, flag_column="fake_liquidity_capacity_haircut_flag", horizon=horizon)
    observed_delta = observed.get("short_return_delta")
    if observed_delta is None:
        return {
            "status": "insufficient",
            "observed": observed,
            "tests": {},
            "passed": False,
        }
    rng = np.random.default_rng(20260509)
    tests: dict[str, Any] = {}

    shuffled_deltas: list[float] = []
    for _ in range(iterations):
        local = events.copy()
        local["_shuffle_flag"] = _shuffle_flags_within_timestamp(local, rng)
        delta = _effect_delta(local, flag_column="_shuffle_flag", horizon=horizon).get("short_return_delta")
        if delta is not None:
            shuffled_deltas.append(float(delta))
    tests["same_timestamp_feature_shuffle"] = _shuffle_summary(
        np.asarray(shuffled_deltas, dtype="float64"), float(observed_delta), iterations
    )

    shifted_deltas: list[float] = []
    for _ in range(iterations):
        local = events.copy()
        local["_shift_flag"] = _time_shift_flags_by_symbol(local, rng)
        delta = _effect_delta(local, flag_column="_shift_flag", horizon=horizon).get("short_return_delta")
        if delta is not None:
            shifted_deltas.append(float(delta))
    tests["symbol_time_shift_shuffle"] = _shuffle_summary(
        np.asarray(shifted_deltas, dtype="float64"), float(observed_delta), iterations
    )

    label_deltas: list[float] = []
    base_short = events[f"forward_{horizon}h_short_return"].copy()
    for _ in range(iterations):
        local = events.copy()
        shuffled_short = base_short.copy()
        for _, idx in local.groupby("open_time_ms").groups.items():
            values = shuffled_short.loc[idx].to_numpy(dtype="float64")
            shuffled_short.loc[idx] = rng.permutation(values)
        local[f"forward_{horizon}h_short_return"] = shuffled_short
        delta = _effect_delta(
            local,
            flag_column="fake_liquidity_capacity_haircut_flag",
            horizon=horizon,
        ).get("short_return_delta")
        if delta is not None:
            label_deltas.append(float(delta))
    tests["same_timestamp_label_shuffle"] = _shuffle_summary(
        np.asarray(label_deltas, dtype="float64"), float(observed_delta), iterations
    )

    return {
        "status": "ok",
        "horizon": f"h{horizon}",
        "observed": observed,
        "tests": tests,
        "passed": bool(observed_delta < 0.0 and all(test.get("passed") for test in tests.values())),
    }


def _symbol_holdout(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, flag_column="fake_liquidity_capacity_haircut_flag", horizon=horizon)
    rows: dict[str, Any] = {}
    for subject, group in events.groupby("subject"):
        local = _effect_delta(group, flag_column="fake_liquidity_capacity_haircut_flag", horizon=horizon)
        if int(local.get("haircut_count") or 0) >= 3 and int(local.get("control_count") or 0) >= 3:
            rows[str(subject)] = local
    leave_one_out: dict[str, Any] = {}
    for subject in sorted(events["subject"].astype(str).unique()):
        local = events.loc[events["subject"].astype(str).ne(subject)]
        leave_one_out[subject] = _effect_delta(
            local,
            flag_column="fake_liquidity_capacity_haircut_flag",
            horizon=horizon,
        )
    eligible = [row for row in rows.values() if row.get("short_return_delta") is not None]
    sign_consistent = [float(row["short_return_delta"]) < 0.0 for row in eligible]
    haircut_counts = (
        events.loc[events["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)]
        .groupby("subject")
        .size()
    )
    total_haircuts = int(haircut_counts.sum())
    top_share = float(haircut_counts.max() / total_haircuts) if total_haircuts else 1.0
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
        "top_haircut_symbol_event_share": top_share,
        "by_symbol": rows,
        "leave_one_symbol_out": leave_one_out,
        "passed": passed,
    }


def _liquidity_bucket_consistency(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    rows: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        rows[str(bucket)] = _effect_delta(
            group,
            flag_column="fake_liquidity_capacity_haircut_flag",
            horizon=horizon,
        )
    eligible = [
        row
        for row in rows.values()
        if int(row.get("haircut_count") or 0) >= 10
        and int(row.get("control_count") or 0) >= 10
        and row.get("short_return_delta") is not None
    ]
    passed = bool(len(eligible) >= 2 and all(float(row["short_return_delta"]) < 0.0 for row in eligible))
    return {
        "horizon": f"h{horizon}",
        "bucket_results": rows,
        "eligible_bucket_count": int(len(eligible)),
        "passed": passed,
        "pass_rule": "at least two buckets with >=10 haircut/control observations and negative short-return delta",
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
            and int(row.get("haircut_count") or 0) >= 10
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
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    haircut = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    out: dict[str, Any] = {}
    for cohort_name, mask in {
        "haircut_rows": candidates & haircut,
        "candidate_control_rows": candidates & ~haircut,
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
    out["provider_semantics_note"] = (
        "Uses local binance_derivatives funding_rate as stored; funding cadence and units need "
        "provider-semantics audit before any live use."
    )
    return out


def _capacity_summary_for_subset(subset: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    capacity = pd.to_numeric(subset.get("capacity_proxy_usd"), errors="coerce").dropna()
    capacity_after = pd.to_numeric(subset.get("capacity_after_haircut_usd"), errors="coerce").dropna()
    slippage = pd.to_numeric(subset.get("slippage_or_capacity_proxy"), errors="coerce").dropna()
    vol_oi = pd.to_numeric(subset.get("volume_oi_ratio_24h"), errors="coerce").dropna()
    forward = pd.to_numeric(subset.get(f"forward_{horizon}h_log_return"), errors="coerce").dropna()
    return {
        "row_count": int(len(subset)),
        "capacity_proxy_usd_mean": float(capacity.mean()) if len(capacity) else None,
        "capacity_proxy_usd_p10": float(capacity.quantile(0.10)) if len(capacity) else None,
        "capacity_proxy_usd_median": float(capacity.median()) if len(capacity) else None,
        "capacity_after_haircut_usd_median": float(capacity_after.median()) if len(capacity_after) else None,
        "slippage_proxy_mean": float(slippage.mean()) if len(slippage) else None,
        "slippage_proxy_p90": float(slippage.quantile(0.90)) if len(slippage) else None,
        "volume_oi_ratio_24h_mean": float(vol_oi.mean()) if len(vol_oi) else None,
        "fake_liquidity_risk_fraction": float(
            subset["volume_oi_brushing_extreme_flag"].fillna(False).astype(bool).mean()
        )
        if len(subset)
        else None,
        "adverse_squeeze_gt_5pct_fraction": float((forward > 0.05).mean()) if len(forward) else None,
        "adverse_squeeze_gt_10pct_fraction": float((forward > 0.10).mean()) if len(forward) else None,
        "max_trade_participation_rate": 0.005,
        "max_inventory_participation_rate": 0.02,
    }


def _capacity_summary(frame: pd.DataFrame) -> dict[str, Any]:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    haircut = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    return {
        "haircut_rows": _capacity_summary_for_subset(frame.loc[candidates & haircut]),
        "candidate_control_rows": _capacity_summary_for_subset(frame.loc[candidates & ~haircut]),
        "all_capacity_haircut_candidates": _capacity_summary_for_subset(frame.loc[candidates]),
    }


def _capacity_haircut_diagnostic(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    haircut = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    haircut_subset = frame.loc[candidates & haircut].copy()
    control_subset = frame.loc[candidates & ~haircut].copy()
    effect = _effect_delta(
        frame.loc[candidates].copy(),
        flag_column="fake_liquidity_capacity_haircut_flag",
        horizon=horizon,
    )
    haircut_summary = _capacity_summary_for_subset(haircut_subset, horizon=horizon)
    control_summary = _capacity_summary_for_subset(control_subset, horizon=horizon)
    changed_fraction = float(len(haircut_subset) / max(int(candidates.sum()), 1))
    haircut_capacity = _to_float(haircut_summary.get("capacity_proxy_usd_median"))
    control_capacity = _to_float(control_summary.get("capacity_proxy_usd_median"))
    haircut_slippage = _to_float(haircut_summary.get("slippage_proxy_mean"))
    control_slippage = _to_float(control_summary.get("slippage_proxy_mean"))
    haircut_adverse = _to_float(haircut_summary.get("adverse_squeeze_gt_5pct_fraction"))
    control_adverse = _to_float(control_summary.get("adverse_squeeze_gt_5pct_fraction"))
    haircut_fake_risk = _to_float(haircut_summary.get("fake_liquidity_risk_fraction"))
    control_fake_risk = _to_float(control_summary.get("fake_liquidity_risk_fraction"))

    capacity_lower = (
        haircut_capacity is not None
        and control_capacity is not None
        and haircut_capacity < control_capacity
    )
    slippage_higher = (
        haircut_slippage is not None
        and control_slippage is not None
        and haircut_slippage > control_slippage
    )
    fake_risk_higher = (
        haircut_fake_risk is not None
        and control_fake_risk is not None
        and haircut_fake_risk > control_fake_risk
    )
    adverse_higher = (
        haircut_adverse is not None
        and control_adverse is not None
        and haircut_adverse > control_adverse
    )
    short_delta = _to_float(effect.get("short_return_delta"))
    passed = bool(
        len(haircut_subset) >= 30
        and len(control_subset) >= 30
        and changed_fraction <= 0.60
        and short_delta is not None
        and short_delta < 0.0
        and adverse_higher
        and (capacity_lower or slippage_higher or fake_risk_higher)
    )
    return {
        "horizon": f"h{horizon}",
        "haircut_summary": haircut_summary,
        "control_summary": control_summary,
        "changed_fraction": changed_fraction,
        "effect": effect,
        "capacity_lower_than_control": capacity_lower,
        "slippage_higher_than_control": slippage_higher,
        "fake_liquidity_risk_higher_than_control": fake_risk_higher,
        "adverse_squeeze_tail_higher_than_control": adverse_higher,
        "passed": passed,
        "pass_rule": (
            "haircut rows must be <=60% of candidates, worse shorts than control, "
            "higher adverse-squeeze tail, and worse capacity/slippage/fake-liquidity proxy"
        ),
    }


def _event_count_by_symbol(frame: pd.DataFrame) -> dict[str, int]:
    events = frame.loc[frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)]
    counts = events.groupby("subject").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _event_count_by_liquidity_bucket(frame: pd.DataFrame) -> dict[str, int]:
    events = frame.loc[frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)]
    counts = events.groupby("liquidity_bucket").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _selected_short_changed_rows_equivalent(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    effect = _effect_delta(events, flag_column="fake_liquidity_capacity_haircut_flag", horizon=horizon)
    changed = events.loc[events["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)]
    return {
        "interaction_type": "capacity_haircut_or_short_eligibility_reduction_equivalent",
        "candidate_short_rows": int(len(events)),
        "haircut_rows": int(len(changed)),
        "changed_fraction": float(len(changed) / max(len(events), 1)),
        "primary_horizon": f"h{horizon}",
        "effect": effect,
        "note": (
            "There is no canonical 1h parent portfolio yet, so changed_rows means "
            "post-pump low-float-proxy short candidates where fake-liquidity state "
            "would reduce capacity or reject market-order participation."
        ),
    }


def _feature_definitions() -> dict[str, Any]:
    return {
        "capacity_haircut_candidate_flag": "post_pump_short_candidate_flag from the low-float trap evaluator.",
        "volume_oi_brushing_extreme_flag": "24h volume/OI at shifted rolling q95 and >=2, or existing fake_liquidity_risk_flag.",
        "thin_capacity_flag": "capacity_proxy_usd <= shifted rolling q25 or OI value <= shifted rolling q20.",
        "book_thinness_flag": "orderbook depth or book-depth/volume ratio <= shifted rolling q20.",
        "taker_book_dislocation_flag": (
            "taker/book ratio >= max(shifted q90, 1), or simultaneous high absolute taker and book imbalance, "
            "or thin book with elevated taker imbalance."
        ),
        "slippage_proxy_extreme_flag": "slippage_or_capacity_proxy >= shifted rolling q90.",
        "fake_liquidity_capacity_haircut_flag": (
            "capacity candidate plus volume/OI brushing with thin capacity, taker/book dislocation, or "
            "slippage extreme; also captures thin capacity + taker/book dislocation + slippage extreme."
        ),
        "capacity_haircut_multiplier": "0.25 for hard fake-liquidity flag, 0.50 for softer component risk, else 1.0.",
        "pit_rule": "all rolling thresholds are shifted one bar; forward returns are labels only.",
        "source_gap": "venue concentration is not available locally, so this Stage 0 uses volume/OI and taker/book proxies only.",
    }


def _data_sources_and_coverage(frame: pd.DataFrame, meta: dict[str, Any], root: Path) -> dict[str, Any]:
    payload = trap_eval._data_sources_and_coverage(frame, meta, root)
    payload["research_lane"] = RESEARCH_ID
    payload["source_reuse_note"] = (
        "Reuses the low_float_squeeze_trap_stage0_1h local 1h loader; h10d state remains untouched."
    )
    payload["provider_gap_note"] = (
        "Venue concentration is unavailable in local 1h caches, so this report cannot validate venue-HHI "
        "fake-liquidity mechanics."
    )
    return payload


def _pass_fail_decision(
    *,
    frame: pd.DataFrame,
    shuffle_tests: dict[str, Any],
    symbol_holdout: dict[str, Any],
    liquidity_bucket_consistency: dict[str, Any],
    delay_robustness: dict[str, Any],
    capacity_haircut_diagnostic: dict[str, Any],
) -> dict[str, Any]:
    if frame.empty:
        return {
            "label": "blocked",
            "blockers": ["no_research_frame"],
            "failed_checks": [],
            "capacity_haircut_candidate_row_count": 0,
            "haircut_event_count": 0,
        }
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    haircut = frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    candidate_count = int(candidates.sum())
    haircut_count = int((candidates & haircut).sum())
    blockers: list[str] = []
    if frame["subject"].nunique() < 10:
        blockers.append("loaded_symbol_count_below_10")
    if candidate_count < 100:
        blockers.append("capacity_haircut_candidate_count_below_100")
    if haircut_count < 30:
        blockers.append("haircut_event_count_below_30")

    failed: list[str] = []
    if not capacity_haircut_diagnostic.get("passed"):
        failed.append("capacity_haircut_diagnostic_failed")
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
        "capacity_haircut_candidate_row_count": candidate_count,
        "haircut_event_count": haircut_count,
        "decision_rule": (
            "pass only if data minimums clear and capacity diagnostic, shuffle, symbol holdout, "
            "liquidity bucket, and +1h/+6h/+24h delay robustness all pass"
        ),
    }


def _next_landing_shape(decision: dict[str, Any]) -> dict[str, Any]:
    if decision.get("label") == "pass":
        return {
            "recommended_shape": "capacity_haircut_participation_cap_kill_switch_input",
            "next_step": "Build a quarantined 1h parent interaction simulator; do not bridge to h10d yet.",
        }
    if decision.get("label") == "blocked":
        return {
            "recommended_shape": "coverage_or_threshold_repair",
            "next_step": "Repair blockers before interpreting capacity-haircut value.",
        }
    return {
        "recommended_shape": "fail_closed_or_redefine_fake_liquidity_state",
        "next_step": "Do not promote. Venue concentration or a stricter capacity simulator is needed before retry.",
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
    capacity_haircut_diagnostic = (
        _capacity_haircut_diagnostic(frame, horizon=24) if not frame.empty else {"passed": False}
    )
    decision = _pass_fail_decision(
        frame=frame,
        shuffle_tests=shuffle_tests,
        symbol_holdout=symbol_holdout,
        liquidity_bucket_consistency=liquidity_bucket_consistency,
        delay_robustness=delay_robustness,
        capacity_haircut_diagnostic=capacity_haircut_diagnostic,
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
        "capacity_haircut_diagnostic": capacity_haircut_diagnostic,
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
    root = trap_eval._resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "fake_liquidity_capacity_haircut_stage0_1h.json"
    horizons = tuple(DEFAULT_HORIZONS)
    symbols = trap_eval._discover_symbols(root, requested=str(args.symbols), limit=int(args.symbol_limit))
    base_frame, meta = trap_eval._load_research_frame(root, symbols, horizons)
    frame = _add_fake_liquidity_capacity_state(base_frame) if not base_frame.empty else base_frame
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
        "capacity_haircut_candidate_row_count": report["pass_fail_decision"].get(
            "capacity_haircut_candidate_row_count"
        ),
        "haircut_event_count": report["pass_fail_decision"].get("haircut_event_count"),
        "event_count_by_liquidity_bucket": report.get("event_count_by_liquidity_bucket"),
        "primary_effect_h24": report.get("selected_short_changed_rows_equivalent", {}).get("effect"),
        "capacity_haircut_diagnostic_passed": report.get("capacity_haircut_diagnostic", {}).get("passed"),
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
