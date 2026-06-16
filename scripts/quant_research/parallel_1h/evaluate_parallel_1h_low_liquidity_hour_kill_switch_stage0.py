#!/usr/bin/env python
"""Stage 0 evaluator for low-liquidity-hour kill switch on 1h post-pump shorts.

This is an execution-risk selector, not a promoted alpha.  It asks whether
post-pump short candidates that arrive during symbol-specific low-liquidity
hours should be blocked or participation-reduced because forward short returns,
tail squeeze risk, funding drag, and capacity/slippage proxies deteriorate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quant_research.parallel_1h import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0 as cooldown_eval

RESEARCH_ID = "low_liquidity_hour_kill_switch_stage0_1h"
REPORT_SUBDIR = "2026-05-07-parallel-1h-alpha-stage0"
HORIZONS = tuple(trap_eval.DEFAULT_HORIZONS)
FLAG_COLUMN = "low_liquidity_hour_kill_switch_flag"
SCORE_COLUMN = "low_liquidity_hour_kill_switch_score"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(out) or np.isinf(out):
        return None
    return out


def _safe_ratio(num: Any, den: Any) -> float | None:
    num_f = _safe_float(num)
    den_f = _safe_float(den)
    if num_f is None or den_f is None or den_f == 0.0:
        return None
    return num_f / den_f


def _describe_series(values: pd.Series) -> dict[str, Any]:
    vals = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
        }
    return {
        "count": int(vals.count()),
        "mean": _safe_float(vals.mean()),
        "median": _safe_float(vals.median()),
        "p10": _safe_float(vals.quantile(0.10)),
        "p25": _safe_float(vals.quantile(0.25)),
        "p75": _safe_float(vals.quantile(0.75)),
        "p90": _safe_float(vals.quantile(0.90)),
    }


def _rolling_symbol_quantile(series: pd.Series, q: float, window: int = 168, min_periods: int = 48) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.shift(1).rolling(window=window, min_periods=min_periods).quantile(q)


def _rolling_symbol_median(series: pd.Series, window: int = 168, min_periods: int = 48) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.shift(1).rolling(window=window, min_periods=min_periods).median()


def _rolling_symbol_hour_median(series: pd.Series, window: int = 90, min_periods: int = 20) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.shift(1).rolling(window=window, min_periods=min_periods).median()


def _load_base_frame(as_of: str, max_symbols: int | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    market_root = trap_eval._resolve_market_history_root(None)
    symbols = trap_eval._discover_symbols(market_root, requested="", limit=int(max_symbols or 0))
    frame, meta = trap_eval._load_research_frame(market_root, symbols, HORIZONS)
    coverage = {
        "market_history_root": str(market_root),
        "requested_as_of_utc": as_of,
        "symbols_discovered": int(len(symbols)),
        "symbols_loaded": int(frame["subject"].nunique()) if not frame.empty else 0,
        "rows_loaded": int(len(frame)),
        "post_pump_short_candidate_rows": int(frame.get("post_pump_short_candidate_flag", pd.Series(dtype=bool)).sum())
        if not frame.empty
        else 0,
        "horizons": list(HORIZONS),
        "stage0_lane_boundary": "parallel 1h research lane only; h10d canonical parent is comparison-only",
        "loader_meta": meta,
    }
    return frame, coverage


def _add_low_liquidity_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["subject", "open_time_ms"]).copy()
    out["utc_hour"] = out["timestamp_utc"].dt.hour.astype("int64")
    out["utc_dayofweek"] = out["timestamp_utc"].dt.dayofweek.astype("int64")
    out["utc_hour_of_week"] = out["utc_dayofweek"] * 24 + out["utc_hour"]

    group = out.groupby("subject", group_keys=False)
    out["symbol_quote_volume_q20_prior"] = group["perp_quote_volume_usd"].transform(
        lambda s: _rolling_symbol_quantile(s, 0.20)
    )
    out["symbol_quote_volume_median_prior"] = group["perp_quote_volume_usd"].transform(_rolling_symbol_median)
    out["symbol_capacity_q20_prior"] = group["capacity_proxy_usd"].transform(lambda s: _rolling_symbol_quantile(s, 0.20))
    out["symbol_capacity_median_prior"] = group["capacity_proxy_usd"].transform(_rolling_symbol_median)
    out["symbol_slippage_proxy_q80_prior"] = group["slippage_or_capacity_proxy"].transform(
        lambda s: _rolling_symbol_quantile(s, 0.80)
    )

    hour_group = out.groupby(["subject", "utc_hour"], group_keys=False)
    out["symbol_hour_quote_volume_median_prior"] = hour_group["perp_quote_volume_usd"].transform(
        _rolling_symbol_hour_median
    )
    out["symbol_hour_capacity_median_prior"] = hour_group["capacity_proxy_usd"].transform(
        _rolling_symbol_hour_median
    )

    quote_volume = pd.to_numeric(out["perp_quote_volume_usd"], errors="coerce")
    capacity = pd.to_numeric(out["capacity_proxy_usd"], errors="coerce")
    slippage_proxy = pd.to_numeric(out["slippage_or_capacity_proxy"], errors="coerce")

    out["volume_below_symbol_q20_flag"] = quote_volume.le(out["symbol_quote_volume_q20_prior"]) & out[
        "symbol_quote_volume_q20_prior"
    ].notna()
    out["capacity_below_symbol_q20_flag"] = capacity.le(out["symbol_capacity_q20_prior"]) & out[
        "symbol_capacity_q20_prior"
    ].notna()
    out["volume_below_symbol_hour_flag"] = quote_volume.le(0.75 * out["symbol_hour_quote_volume_median_prior"]) & out[
        "symbol_hour_quote_volume_median_prior"
    ].notna()
    out["capacity_below_symbol_hour_flag"] = capacity.le(0.75 * out["symbol_hour_capacity_median_prior"]) & out[
        "symbol_hour_capacity_median_prior"
    ].notna()
    out["slippage_proxy_high_flag"] = slippage_proxy.ge(out["symbol_slippage_proxy_q80_prior"]) & out[
        "symbol_slippage_proxy_q80_prior"
    ].notna()

    out["thin_hour_joint_flag"] = out["volume_below_symbol_hour_flag"] & out["capacity_below_symbol_hour_flag"]
    out["low_capacity_joint_flag"] = out["volume_below_symbol_q20_flag"] & out["capacity_below_symbol_q20_flag"]
    out[SCORE_COLUMN] = (
        out["volume_below_symbol_q20_flag"].astype(int)
        + out["capacity_below_symbol_q20_flag"].astype(int)
        + out["volume_below_symbol_hour_flag"].astype(int)
        + out["capacity_below_symbol_hour_flag"].astype(int)
        + out["slippage_proxy_high_flag"].astype(int)
        + out["thin_hour_joint_flag"].astype(int)
        + out["low_capacity_joint_flag"].astype(int)
    )

    candidate = out["post_pump_short_candidate_flag"].astype(bool)
    out[FLAG_COLUMN] = candidate & (out[SCORE_COLUMN] >= 3) & (
        out["thin_hour_joint_flag"] | out["low_capacity_joint_flag"] | out["capacity_below_symbol_q20_flag"]
    )
    out["selected_short_changed_equivalent"] = out[FLAG_COLUMN]
    return out


def _effect_delta(event_frame: pd.DataFrame, horizon: int = 24) -> dict[str, Any]:
    candidate = event_frame["post_pump_short_candidate_flag"].astype(bool)
    kill = event_frame[FLAG_COLUMN].astype(bool)
    control = candidate & ~kill

    short_col = f"forward_{horizon}h_short_return"
    ret_col = f"forward_{horizon}h_log_return"
    kill_short = pd.to_numeric(event_frame.loc[kill, short_col], errors="coerce").dropna()
    control_short = pd.to_numeric(event_frame.loc[control, short_col], errors="coerce").dropna()
    kill_ret = pd.to_numeric(event_frame.loc[kill, ret_col], errors="coerce").dropna()
    control_ret = pd.to_numeric(event_frame.loc[control, ret_col], errors="coerce").dropna()

    kill_adv = kill_ret.gt(0.05)
    control_adv = control_ret.gt(0.05)
    delta = None
    if not kill_short.empty and not control_short.empty:
        delta = _safe_float(kill_short.mean() - control_short.mean())

    adv_delta = None
    if not kill_adv.empty and not control_adv.empty:
        adv_delta = _safe_float(float(kill_adv.mean()) - float(control_adv.mean()))

    return {
        "horizon": horizon,
        "kill_switch_count": int(kill.sum()),
        "cooldown_count": int(kill.sum()),
        "control_count": int(control.sum()),
        "kill_switch_mean_short_return": _safe_float(kill_short.mean()) if not kill_short.empty else None,
        "control_mean_short_return": _safe_float(control_short.mean()) if not control_short.empty else None,
        "short_return_delta": delta,
        "kill_switch_forward_log_return_gt_5pct_rate": _safe_float(kill_adv.mean()) if not kill_adv.empty else None,
        "control_forward_log_return_gt_5pct_rate": _safe_float(control_adv.mean()) if not control_adv.empty else None,
        "adverse_squeeze_gt_5pct_delta": adv_delta,
    }


def _cohort_after_delay(event_frame: pd.DataFrame, delay_hours: int) -> pd.DataFrame:
    candidates = event_frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    kill = event_frame[FLAG_COLUMN].fillna(False).astype(bool)
    base_columns = [
        "subject",
        "open_time_ms",
        "timestamp_utc",
        "timestamp_utc_text",
        "liquidity_bucket",
        "perp_close",
        "perp_quote_volume_usd",
        "capacity_proxy_usd",
        "slippage_or_capacity_proxy",
        "funding_rate_state",
    ]
    forward_columns = [
        column
        for column in event_frame.columns
        if column.startswith("forward_") or column.startswith("funding_h")
    ]
    columns = [column for column in [*base_columns, *forward_columns] if column in event_frame.columns]
    lookup = event_frame[columns].copy().rename(columns={"open_time_ms": "entry_open_time_ms"})

    delayed_parts: list[pd.DataFrame] = []
    hour_ms = 60 * 60 * 1000
    for flag_value, mask in ((True, candidates & kill), (False, candidates & ~kill)):
        events = event_frame.loc[mask, ["subject", "open_time_ms"]].copy()
        if events.empty:
            continue
        events["source_open_time_ms"] = events["open_time_ms"]
        events["entry_open_time_ms"] = events["open_time_ms"] + int(delay_hours) * hour_ms
        events = events.drop(columns=["open_time_ms"])
        delayed = events.merge(lookup, on=["subject", "entry_open_time_ms"], how="inner")
        if delayed.empty:
            continue
        delayed["post_pump_short_candidate_flag"] = True
        delayed[FLAG_COLUMN] = bool(flag_value)
        delayed_parts.append(delayed)
    if not delayed_parts:
        return pd.DataFrame()
    return pd.concat(delayed_parts, ignore_index=True)


def _forward_return_table(event_frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    masks = {
        "post_pump_candidates_all": event_frame["post_pump_short_candidate_flag"].astype(bool),
        "kill_switch_rows": event_frame[FLAG_COLUMN].astype(bool),
        "candidate_controls_not_kill_switched": event_frame["post_pump_short_candidate_flag"].astype(bool)
        & ~event_frame[FLAG_COLUMN].astype(bool),
        "thin_symbol_hour_rows": event_frame["thin_hour_joint_flag"].astype(bool),
        "low_capacity_joint_rows": event_frame["low_capacity_joint_flag"].astype(bool),
    }
    table: dict[str, dict[str, Any]] = {}
    for name, mask in masks.items():
        section: dict[str, Any] = {"count": int(mask.sum())}
        for h in HORIZONS:
            short_col = f"forward_{h}h_short_return"
            ret_col = f"forward_{h}h_log_return"
            section[f"h{h}_mean_short_return"] = _safe_float(
                pd.to_numeric(event_frame.loc[mask, short_col], errors="coerce").mean()
            )
            section[f"h{h}_median_short_return"] = _safe_float(
                pd.to_numeric(event_frame.loc[mask, short_col], errors="coerce").median()
            )
            section[f"h{h}_adverse_forward_log_return_gt_5pct_rate"] = _safe_float(
                pd.to_numeric(event_frame.loc[mask, ret_col], errors="coerce").gt(0.05).mean()
            )
        table[name] = section
    return table


def _funding_drag_summary(event_frame: pd.DataFrame) -> dict[str, Any]:
    kill = event_frame[FLAG_COLUMN].astype(bool)
    control = event_frame["post_pump_short_candidate_flag"].astype(bool) & ~kill
    summary: dict[str, Any] = {
        "interpretation": "positive funding_h*h_short_pnl_estimate helps shorts; negative values are drag",
        "kill_switch_count": int(kill.sum()),
        "control_count": int(control.sum()),
    }
    for h in (1, 3, 6, 12, 24):
        col = f"funding_h{h}h_short_pnl_estimate"
        if col not in event_frame.columns:
            continue
        kill_values = pd.to_numeric(event_frame.loc[kill, col], errors="coerce").dropna()
        control_values = pd.to_numeric(event_frame.loc[control, col], errors="coerce").dropna()
        summary[f"h{h}"] = {
            "kill_switch_mean": _safe_float(kill_values.mean()) if not kill_values.empty else None,
            "control_mean": _safe_float(control_values.mean()) if not control_values.empty else None,
            "delta": _safe_float(kill_values.mean() - control_values.mean())
            if (not kill_values.empty and not control_values.empty)
            else None,
            "kill_switch_negative_drag_rate": _safe_float(kill_values.lt(0).mean()) if not kill_values.empty else None,
            "control_negative_drag_rate": _safe_float(control_values.lt(0).mean()) if not control_values.empty else None,
        }
    return summary


def _slippage_capacity_proxy_summary(event_frame: pd.DataFrame, primary_effect: dict[str, Any]) -> dict[str, Any]:
    kill = event_frame[FLAG_COLUMN].astype(bool)
    control = event_frame["post_pump_short_candidate_flag"].astype(bool) & ~kill

    metrics = {
        "capacity_proxy_usd": "capacity_proxy_usd",
        "slippage_or_capacity_proxy": "slippage_or_capacity_proxy",
        "perp_quote_volume_usd": "perp_quote_volume_usd",
        SCORE_COLUMN: SCORE_COLUMN,
    }
    by_metric: dict[str, Any] = {}
    for label, col in metrics.items():
        if col not in event_frame.columns:
            continue
        kill_stats = _describe_series(event_frame.loc[kill, col])
        control_stats = _describe_series(event_frame.loc[control, col])
        by_metric[label] = {
            "kill_switch": kill_stats,
            "control": control_stats,
            "kill_switch_to_control_median_ratio": _safe_ratio(kill_stats["median"], control_stats["median"]),
            "kill_switch_to_control_p10_ratio": _safe_ratio(kill_stats["p10"], control_stats["p10"]),
            "kill_switch_to_control_p90_ratio": _safe_ratio(kill_stats["p90"], control_stats["p90"]),
        }

    cap = by_metric.get("capacity_proxy_usd", {})
    slip = by_metric.get("slippage_or_capacity_proxy", {})
    cap_p10_ratio = cap.get("kill_switch_to_control_p10_ratio")
    cap_median_ratio = cap.get("kill_switch_to_control_median_ratio")
    slip_p90_ratio = slip.get("kill_switch_to_control_p90_ratio")
    short_delta = _safe_float(primary_effect.get("short_return_delta"))
    adverse_delta = _safe_float(primary_effect.get("adverse_squeeze_gt_5pct_delta"))

    capacity_worse = cap_p10_ratio is not None and cap_p10_ratio <= 0.80
    capacity_median_worse = cap_median_ratio is not None and cap_median_ratio <= 0.90
    slippage_worse = slip_p90_ratio is not None and slip_p90_ratio >= 1.10
    tail_or_return_worse = (
        (short_delta is not None and short_delta < 0)
        or (adverse_delta is not None and adverse_delta > 0)
    )

    return {
        "by_metric": by_metric,
        "capacity_p10_ratio_threshold": 0.80,
        "capacity_median_ratio_threshold": 0.90,
        "slippage_p90_ratio_threshold": 1.10,
        "capacity_worse": bool(capacity_worse),
        "capacity_median_worse": bool(capacity_median_worse),
        "slippage_worse": bool(slippage_worse),
        "tail_or_return_worse": bool(tail_or_return_worse),
        "passed": bool((capacity_worse or capacity_median_worse or slippage_worse) and tail_or_return_worse),
    }


def _delay_robustness(event_frame: pd.DataFrame) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for delay in (1, 6, 24):
        delayed = _cohort_after_delay(event_frame, delay_hours=delay)
        if delayed.empty or int(delayed[FLAG_COLUMN].sum()) < 20:
            rows[f"delay_{delay}h"] = {
                "count": int(delayed[FLAG_COLUMN].sum()) if not delayed.empty and FLAG_COLUMN in delayed else 0,
                "passed": False,
                "reason": "insufficient delayed kill-switch rows",
            }
            continue
        effect = _effect_delta(delayed, horizon=24)
        rows[f"delay_{delay}h"] = {
            **effect,
            "passed": bool(
                effect.get("short_return_delta") is not None
                and effect.get("adverse_squeeze_gt_5pct_delta") is not None
                and effect["short_return_delta"] < 0
                and effect["adverse_squeeze_gt_5pct_delta"] >= 0
            ),
        }
    return {
        "delays_tested_hours": [1, 6, 24],
        "rows": rows,
        "passed": all(row.get("passed", False) for row in rows.values()),
    }


def _symbol_holdout(event_frame: pd.DataFrame) -> dict[str, Any]:
    kill = event_frame[FLAG_COLUMN].astype(bool)
    rows: list[dict[str, Any]] = []
    candidates = event_frame.loc[event_frame["post_pump_short_candidate_flag"].astype(bool)]
    for subject, group in candidates.groupby("subject", dropna=False):
        row = _effect_delta(group, horizon=24)
        row["subject"] = subject
        rows.append(row)
    per_symbol = pd.DataFrame(rows)
    if per_symbol.empty:
        return {
            "symbols_with_any_kill_switch_rows": int(event_frame.loc[kill, "subject"].nunique()),
            "symbols_with_ge_10_kill_switch_rows": 0,
            "usable_symbol_count": 0,
            "passed_symbol_count": 0,
            "passed_symbol_rate": None,
            "passed": False,
            "top_rows": [],
        }
    usable = per_symbol[
        (pd.to_numeric(per_symbol["kill_switch_count"], errors="coerce") >= 10)
        & (pd.to_numeric(per_symbol["control_count"], errors="coerce") >= 10)
    ].copy()
    usable["passed_direction"] = (
        pd.to_numeric(usable["short_return_delta"], errors="coerce").lt(0)
        & pd.to_numeric(usable["adverse_squeeze_gt_5pct_delta"], errors="coerce").ge(0)
    )
    symbols_with_signal = int((event_frame.loc[kill, "subject"].value_counts() >= 10).sum())
    passed_rate = _safe_float(usable["passed_direction"].mean()) if not usable.empty else None
    return {
        "symbols_with_any_kill_switch_rows": int(event_frame.loc[kill, "subject"].nunique()),
        "symbols_with_ge_10_kill_switch_rows": symbols_with_signal,
        "usable_symbol_count": int(len(usable)),
        "passed_symbol_count": int(usable["passed_direction"].sum()) if not usable.empty else 0,
        "passed_symbol_rate": passed_rate,
        "passed": bool(len(usable) >= 5 and passed_rate is not None and passed_rate >= 0.55),
        "top_rows": usable.sort_values("kill_switch_count", ascending=False).head(25).to_dict(orient="records"),
    }


def _liquidity_bucket_consistency(event_frame: pd.DataFrame) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    passed = True
    candidate = event_frame["post_pump_short_candidate_flag"].astype(bool)
    for bucket, group in event_frame.loc[candidate].groupby("liquidity_bucket", dropna=False):
        effect = _effect_delta(group, horizon=24)
        bucket_passed = bool(
            effect.get("kill_switch_count", 0) >= 20
            and effect.get("control_count", 0) >= 20
            and effect.get("short_return_delta") is not None
            and effect.get("adverse_squeeze_gt_5pct_delta") is not None
            and effect["short_return_delta"] < 0
            and effect["adverse_squeeze_gt_5pct_delta"] >= 0
        )
        rows[str(bucket)] = {**effect, "passed": bucket_passed}
        if effect.get("kill_switch_count", 0) >= 20:
            passed = passed and bucket_passed
    tested = [row for row in rows.values() if row.get("kill_switch_count", 0) >= 20]
    return {"rows": rows, "tested_bucket_count": len(tested), "passed": bool(tested and passed)}


def _shuffle_tests(event_frame: pd.DataFrame) -> dict[str, Any]:
    events = event_frame.loc[event_frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, horizon=24)
    observed_delta = observed.get("short_return_delta")
    if observed_delta is None:
        return {
            "status": "insufficient",
            "observed": observed,
            "tests": {},
            "feature_shuffle_by_symbol": {"passed": False},
            "label_shuffle_by_timestamp": {"passed": False},
            "passed": False,
        }
    iterations = 200
    rng = np.random.default_rng(20260510)
    base_flags = events[FLAG_COLUMN].to_numpy(dtype=bool)
    base_short = pd.to_numeric(events["forward_24h_short_return"], errors="coerce").to_numpy(dtype="float64")
    timestamp_groups = cooldown_eval._position_groups(events["open_time_ms"])
    symbol_groups = cooldown_eval._symbol_position_groups(events)

    feature_deltas: list[float] = []
    for _ in range(iterations):
        shuffled_flags = base_flags.copy()
        for positions in timestamp_groups:
            shuffled_flags[positions] = rng.permutation(shuffled_flags[positions])
        delta = cooldown_eval._delta_from_arrays(base_short, shuffled_flags)
        if delta is not None:
            feature_deltas.append(float(delta))

    shift_deltas: list[float] = []
    for _ in range(iterations):
        shifted_flags = base_flags.copy()
        for positions in symbol_groups:
            if len(positions) < 2:
                continue
            offset = int(rng.integers(1, len(positions)))
            shifted_flags[positions] = np.roll(shifted_flags[positions], offset)
        delta = cooldown_eval._delta_from_arrays(base_short, shifted_flags)
        if delta is not None:
            shift_deltas.append(float(delta))

    label_deltas: list[float] = []
    for _ in range(iterations):
        shuffled_short = base_short.copy()
        for positions in timestamp_groups:
            shuffled_short[positions] = rng.permutation(shuffled_short[positions])
        delta = cooldown_eval._delta_from_arrays(shuffled_short, base_flags)
        if delta is not None:
            label_deltas.append(float(delta))

    tests = {
        "same_timestamp_feature_shuffle": cooldown_eval._shuffle_summary(
            np.asarray(feature_deltas, dtype="float64"), float(observed_delta), iterations
        ),
        "symbol_time_shift_shuffle": cooldown_eval._shuffle_summary(
            np.asarray(shift_deltas, dtype="float64"), float(observed_delta), iterations
        ),
        "same_timestamp_label_shuffle": cooldown_eval._shuffle_summary(
            np.asarray(label_deltas, dtype="float64"), float(observed_delta), iterations
        ),
    }
    return {
        "status": "ok",
        "horizon": "h24",
        "observed": observed,
        "tests": tests,
        "feature_shuffle_by_symbol": tests["same_timestamp_feature_shuffle"],
        "label_shuffle_by_timestamp": tests["same_timestamp_label_shuffle"],
        "passed": bool(observed_delta < 0.0 and all(test.get("passed") for test in tests.values())),
    }


def _selected_short_changed_rows(event_frame: pd.DataFrame, limit: int = 200) -> dict[str, Any]:
    cols = [
        "subject",
        "timestamp_utc_text",
        "liquidity_bucket",
        "perp_close",
        "perp_quote_volume_usd",
        "capacity_proxy_usd",
        "slippage_or_capacity_proxy",
        SCORE_COLUMN,
        "volume_below_symbol_q20_flag",
        "capacity_below_symbol_q20_flag",
        "volume_below_symbol_hour_flag",
        "capacity_below_symbol_hour_flag",
        "slippage_proxy_high_flag",
        "thin_hour_joint_flag",
        "low_capacity_joint_flag",
        "forward_1h_short_return",
        "forward_3h_short_return",
        "forward_6h_short_return",
        "forward_12h_short_return",
        "forward_24h_short_return",
        "forward_24h_log_return",
    ]
    present_cols = [c for c in cols if c in event_frame.columns]
    rows = event_frame.loc[event_frame[FLAG_COLUMN].astype(bool), present_cols].head(limit)
    return {
        "shape": "candidate post-pump short row would be hard-kill or reduce-participation by low-liquidity-hour state",
        "row_count": int(event_frame[FLAG_COLUMN].sum()),
        "sample_limit": limit,
        "rows": rows.to_dict(orient="records"),
    }


def _data_quality_blockers(frame: pd.DataFrame, coverage: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if frame.empty:
        blockers.append("no_loaded_1h_research_rows")
        return blockers
    if coverage["symbols_loaded"] < 10:
        blockers.append("lt_10_symbols_loaded")
    if coverage["post_pump_short_candidate_rows"] < 100:
        blockers.append("lt_100_post_pump_short_candidates")
    required_cols = [
        "perp_quote_volume_usd",
        "capacity_proxy_usd",
        "slippage_or_capacity_proxy",
        "post_pump_short_candidate_flag",
        "forward_24h_short_return",
        "forward_24h_log_return",
    ]
    for col in required_cols:
        if col not in frame.columns:
            blockers.append(f"missing_required_column_{col}")
    return blockers


def _pass_fail_decision(report: dict[str, Any]) -> dict[str, Any]:
    blockers = list(report.get("data_quality_blockers", []))
    primary = report["primary_effect_h24"]
    reasons: list[str] = []

    if primary.get("kill_switch_count", 0) < 30:
        reasons.append("insufficient_kill_switch_events")
    if primary.get("control_count", 0) < 100:
        reasons.append("insufficient_candidate_controls")
    if primary.get("short_return_delta") is None or primary["short_return_delta"] >= 0:
        reasons.append("h24_short_return_not_worse_for_kill_switch_rows")
    if primary.get("adverse_squeeze_gt_5pct_delta") is None or primary["adverse_squeeze_gt_5pct_delta"] < 0:
        reasons.append("adverse_squeeze_tail_not_higher_or_equal")
    if not report["execution_risk_consistency"].get("passed", False):
        reasons.append("execution_risk_consistency_failed")
    if not report["shuffle_tests"]["feature_shuffle_by_symbol"].get("passed", False):
        reasons.append("feature_shuffle_failed")
    if not report["shuffle_tests"]["label_shuffle_by_timestamp"].get("passed", False):
        reasons.append("label_shuffle_failed")
    if not report["symbol_holdout"].get("passed", False):
        reasons.append("symbol_holdout_failed")
    if not report["liquidity_bucket_consistency"].get("passed", False):
        reasons.append("liquidity_bucket_consistency_failed")
    if not report["delay_robustness"].get("passed", False):
        reasons.append("delay_robustness_failed")

    if blockers:
        return {
            "decision": "blocked",
            "status": "blocked_by_data",
            "reasons": blockers + reasons,
            "admission": "fail_closed",
        }
    if reasons:
        return {
            "decision": "fail",
            "status": "fail",
            "reasons": reasons,
            "admission": "fail_closed",
        }
    return {
        "decision": "pass",
        "status": "quarantined_state_evidence",
        "reasons": [],
        "admission": "research_only_candidate_for_reduce_participation_simulator",
    }


def _next_landing_shape(decision: dict[str, Any]) -> dict[str, Any]:
    if decision["decision"] == "pass":
        return {
            "shape": "quarantined reduce-participation/market-order kill-switch simulator",
            "allowed_actions": [
                "rerun on longer trusted 1h panel",
                "size haircut simulation with explicit turnover/funding/slippage costs",
                "never promote until separate strategy interaction and live execution constraints pass",
            ],
            "h10d_parent_change_allowed": False,
        }
    return {
        "shape": "fail-closed execution diagnostic only",
        "allowed_actions": [
            "document failure in 1h roadmap",
            "do not admit as rule",
            "do not bridge into h10d parent or live selectors",
        ],
        "h10d_parent_change_allowed": False,
    }


def build_report(as_of: str, max_symbols: int | None = None) -> dict[str, Any]:
    frame, coverage = _load_base_frame(as_of=as_of, max_symbols=max_symbols)
    blockers = _data_quality_blockers(frame, coverage)
    event_frame = _add_low_liquidity_features(frame) if not frame.empty else frame.copy()
    primary = _effect_delta(event_frame, horizon=24) if not event_frame.empty else {
        "horizon": 24,
        "kill_switch_count": 0,
        "cooldown_count": 0,
        "control_count": 0,
        "short_return_delta": None,
        "adverse_squeeze_gt_5pct_delta": None,
    }
    execution_risk = _slippage_capacity_proxy_summary(event_frame, primary) if not event_frame.empty else {"passed": False}

    report: dict[str, Any] = {
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_sources_and_coverage": coverage,
        "data_quality_blockers": blockers,
        "feature_definitions": {
            "candidate_universe": "1h post_pump_short_candidate_flag from existing repo loader",
            "volume_below_symbol_q20_flag": "current 1h quote volume <= PIT rolling 168h q20 by symbol",
            "capacity_below_symbol_q20_flag": "current capacity_proxy_usd <= PIT rolling 168h q20 by symbol",
            "volume_below_symbol_hour_flag": "current 1h quote volume <= 75% of PIT trailing median for same symbol and UTC hour",
            "capacity_below_symbol_hour_flag": "current capacity_proxy_usd <= 75% of PIT trailing median for same symbol and UTC hour",
            "slippage_proxy_high_flag": "current slippage_or_capacity_proxy >= PIT rolling 168h q80 by symbol",
            SCORE_COLUMN: "sum of five atomic low-liquidity/slippage flags plus thin_hour_joint and low_capacity_joint confirmations",
            FLAG_COLUMN: "post-pump short candidate with score >= 3 and a low-capacity/thin-hour confirmation",
            "use_shape": "do-not-market-order / reduce-short-participation / hard kill-switch candidate",
        },
        "event_count_by_symbol": event_frame.loc[event_frame.get(FLAG_COLUMN, False), "subject"].value_counts().to_dict()
        if not event_frame.empty
        else {},
        "event_count_by_liquidity_bucket": event_frame.loc[
            event_frame.get(FLAG_COLUMN, False), "liquidity_bucket"
        ].value_counts(dropna=False).to_dict()
        if not event_frame.empty
        else {},
        "primary_effect_h24": primary,
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": _forward_return_table(event_frame)
        if not event_frame.empty
        else {},
        "selected_short_changed_rows_equivalent": _selected_short_changed_rows(event_frame)
        if not event_frame.empty
        else {"row_count": 0, "rows": []},
        "funding_drag_summary": _funding_drag_summary(event_frame) if not event_frame.empty else {},
        "slippage_or_capacity_proxy": execution_risk,
        "execution_risk_consistency": execution_risk,
        "shuffle_tests": _shuffle_tests(event_frame) if not event_frame.empty else {},
        "symbol_holdout": _symbol_holdout(event_frame) if not event_frame.empty else {"passed": False},
        "liquidity_bucket_consistency": _liquidity_bucket_consistency(event_frame)
        if not event_frame.empty
        else {"passed": False},
        "delay_robustness": _delay_robustness(event_frame) if not event_frame.empty else {"passed": False},
        "stage0_scope_guardrails": {
            "lane": "parallel_1h_alpha_mining",
            "h10d_canonical_parent_mutated": False,
            "live_trading_allowed": False,
            "provider_truth_claim": "none; uses repo-local 1h market history panel only",
        },
    }
    decision = _pass_fail_decision(report)
    report["pass_fail_decision"] = decision
    report["next_landing_shape"] = _next_landing_shape(decision)
    return report


def _write_report(report: dict[str, Any], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{RESEARCH_ID}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument(
        "--report-dir",
        default=str(REPO_ROOT / "artifacts" / "quant_research" / "factor_reports" / REPORT_SUBDIR),
    )
    args = parser.parse_args()

    report = build_report(as_of=args.as_of, max_symbols=args.max_symbols)
    report_path = _write_report(report, Path(args.report_dir))
    print(
        json.dumps(
            {
                "research_id": report["research_id"],
                "report_path": str(report_path),
                "decision": report["pass_fail_decision"]["decision"],
                "status": report["pass_fail_decision"]["status"],
                "reasons": report["pass_fail_decision"]["reasons"],
                "primary_effect_h24": report["primary_effect_h24"],
                "execution_risk_consistency_passed": report["execution_risk_consistency"].get("passed"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
