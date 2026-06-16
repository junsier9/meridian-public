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
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0 as cooldown_eval  # noqa: E402


CONTRACT_VERSION = "parallel_1h_post_pump_bid_replenishment_failure_stage0.v1"
RESEARCH_ID = "post_pump_bid_replenishment_failure_stage0_1h"
FLAG_COLUMN = "post_pump_bid_replenishment_failure_entry_flag"
DEFAULT_HORIZONS = trap_eval.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = 200


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 1h evaluator for post-pump bid replenishment failure. "
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


def _rolling_quantile_by_symbol(
    grouped: pd.core.groupby.generic.DataFrameGroupBy,
    column: str,
    q: float,
) -> pd.Series:
    return grouped[column].transform(lambda s: trap_eval._rolling_quantile(s, q))


def _rolling_prior_sum_by_symbol(
    grouped: pd.core.groupby.generic.DataFrameGroupBy,
    column: str,
    window: int,
) -> pd.Series:
    return grouped[column].transform(
        lambda s: s.fillna(False).astype(bool).shift(1).rolling(window, min_periods=1).sum()
    )


def _rolling_prior_max_by_symbol(
    grouped: pd.core.groupby.generic.DataFrameGroupBy,
    column: str,
    window: int,
) -> pd.Series:
    return grouped[column].transform(
        lambda s: pd.to_numeric(s, errors="coerce").shift(1).rolling(window, min_periods=1).max()
    )


def _add_bid_replenishment_failure_state(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["subject", "open_time_ms"]).copy()
    grouped = out.groupby("subject", group_keys=False, sort=False)

    close = pd.to_numeric(out["perp_close"], errors="coerce")
    bids = pd.to_numeric(out["orderbook_bids_usd"], errors="coerce")
    orderbook_imbalance = pd.to_numeric(out["orderbook_imbalance"], errors="coerce")
    bid_change_6h = pd.to_numeric(out["bid_depth_log_change_6h"], errors="coerce")
    taker_imbalance = pd.to_numeric(out["taker_imbalance"], errors="coerce")
    oi_change_6h = pd.to_numeric(out["oi_log_change_6h"], errors="coerce")

    out["orderbook_imbalance_q40"] = _rolling_quantile_by_symbol(grouped, "orderbook_imbalance", 0.40)
    out["bid_depth_log_change_6h_q25"] = _rolling_quantile_by_symbol(
        grouped, "bid_depth_log_change_6h", 0.25
    )
    out["taker_imbalance_q40"] = _rolling_quantile_by_symbol(grouped, "taker_imbalance", 0.40)
    out["taker_imbalance_6h_ago"] = grouped["taker_imbalance"].shift(6)
    out["prior_6h_high_close"] = _rolling_prior_max_by_symbol(grouped, "perp_close", 6)
    out["prior_24h_bid_depth_max"] = _rolling_prior_max_by_symbol(grouped, "orderbook_bids_usd", 24)
    out["prior_24h_bid_support_count"] = _rolling_prior_sum_by_symbol(
        grouped, "orderbook_bid_support_flag", 24
    )
    out["prior_24h_taker_buy_count"] = _rolling_prior_sum_by_symbol(
        grouped, "taker_buy_dominance_flag", 24
    )
    out["prior_bid_or_taker_support_flag"] = (
        out["prior_24h_bid_support_count"].gt(0) | out["prior_24h_taker_buy_count"].gt(0)
    ).fillna(False)

    out["bid_depth_drawdown_from_prior_24h_flag"] = (
        bids.le(0.60 * out["prior_24h_bid_depth_max"]) & out["prior_24h_bid_depth_max"].gt(0.0)
    ).fillna(False)
    out["book_pressure_deterioration_flag"] = (
        orderbook_imbalance.le(out["orderbook_imbalance_q40"])
        | bid_change_6h.le(np.minimum(out["bid_depth_log_change_6h_q25"], -0.01))
        | out["bid_depth_drawdown_from_prior_24h_flag"]
    ).fillna(False)
    out["taker_buy_exhaustion_flag"] = (
        taker_imbalance.le(out["taker_imbalance_q40"])
        | (taker_imbalance - pd.to_numeric(out["taker_imbalance_6h_ago"], errors="coerce")).le(-0.05)
    ).fillna(False)
    out["price_unable_to_make_new_high_flag"] = (
        close.le(0.995 * pd.to_numeric(out["prior_6h_high_close"], errors="coerce"))
    ).fillna(False)
    out["oi_falling_or_collapse_flag"] = (
        oi_change_6h.le(0.0) | out["oi_collapse_confirmed_flag"].fillna(False).astype(bool)
    ).fillna(False)
    out["current_bid_support_absent_flag"] = (
        ~out["orderbook_bid_support_flag"].fillna(False).astype(bool)
    ).fillna(False)
    out["current_taker_buy_absent_flag"] = (
        ~out["taker_buy_dominance_flag"].fillna(False).astype(bool)
    ).fillna(False)
    out["bid_replenishment_failure_score"] = (
        out["prior_bid_or_taker_support_flag"].astype(int)
        + out["book_pressure_deterioration_flag"].astype(int)
        + out["taker_buy_exhaustion_flag"].astype(int)
        + out["price_unable_to_make_new_high_flag"].astype(int)
        + out["oi_falling_or_collapse_flag"].astype(int)
        + out["current_bid_support_absent_flag"].astype(int)
        + out["current_taker_buy_absent_flag"].astype(int)
    )
    out[FLAG_COLUMN] = (
        out["post_pump_short_candidate_flag"].fillna(False).astype(bool)
        & out["prior_bid_or_taker_support_flag"]
        & out["book_pressure_deterioration_flag"]
        & out["price_unable_to_make_new_high_flag"]
        & out["bid_replenishment_failure_score"].ge(5)
    ).fillna(False)
    return out


def _mask_summary(frame: pd.DataFrame, mask: pd.Series, horizons: tuple[int, ...]) -> dict[str, Any]:
    return cooldown_eval._mask_summary(frame, mask, horizons)


def _forward_return_table(frame: pd.DataFrame, horizons: tuple[int, ...]) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    entry = frame[FLAG_COLUMN].fillna(False).astype(bool)
    support = frame["prior_bid_or_taker_support_flag"].fillna(False).astype(bool)
    book_fail = frame["book_pressure_deterioration_flag"].fillna(False).astype(bool)
    taker_fail = frame["taker_buy_exhaustion_flag"].fillna(False).astype(bool)
    return {
        "post_pump_bid_replenishment_failure_entry_rows": _mask_summary(
            frame, candidates & entry, horizons
        ),
        "candidate_control_rows": _mask_summary(frame, candidates & ~entry, horizons),
        "prior_bid_or_taker_support_rows": _mask_summary(frame, candidates & support, horizons),
        "book_pressure_deterioration_rows": _mask_summary(frame, candidates & book_fail, horizons),
        "taker_buy_exhaustion_rows": _mask_summary(frame, candidates & taker_fail, horizons),
        "all_post_pump_short_candidates": _mask_summary(frame, candidates, horizons),
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
            "entry_count": 0,
            "control_count": 0,
            "short_return_delta": None,
        }
    flag = event_frame[flag_column].fillna(False).astype(bool)
    short_ret = pd.to_numeric(event_frame[f"forward_{horizon}h_short_return"], errors="coerce")
    long_ret = pd.to_numeric(event_frame[f"forward_{horizon}h_log_return"], errors="coerce")
    entry_ret = short_ret.loc[flag].dropna()
    control_ret = short_ret.loc[~flag].dropna()
    if entry_ret.empty or control_ret.empty:
        return {
            "status": "insufficient",
            "entry_count": int(len(entry_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    entry_long = long_ret.loc[flag].dropna()
    control_long = long_ret.loc[~flag].dropna()
    return {
        "status": "ok",
        "entry_count": int(len(entry_ret)),
        "control_count": int(len(control_ret)),
        "entry_short_return_mean": float(entry_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(entry_ret.mean() - control_ret.mean()),
        "entry_adverse_squeeze_gt_5pct_fraction": float((entry_long > 0.05).mean())
        if len(entry_long)
        else None,
        "control_adverse_squeeze_gt_5pct_fraction": float((control_long > 0.05).mean())
        if len(control_long)
        else None,
        "adverse_squeeze_gt_5pct_delta": float(
            (entry_long > 0.05).mean() - (control_long > 0.05).mean()
        )
        if len(entry_long) and len(control_long)
        else None,
        "interpretation": "positive_delta_means_bid_replenishment_failure_rows_are_better_shorts_than_control",
    }


def _cohort_after_delay(
    frame: pd.DataFrame,
    *,
    mask: pd.Series,
    delay_h: int,
    columns: list[str],
) -> pd.DataFrame:
    return cooldown_eval._cohort_after_delay(frame, mask=mask, delay_h=delay_h, columns=columns)


def _delayed_effect(frame: pd.DataFrame, *, delay_h: int, horizon: int = 24) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    entry = frame[FLAG_COLUMN].fillna(False).astype(bool)
    columns = [
        f"forward_{horizon}h_short_return",
        f"forward_{horizon}h_log_return",
        "capacity_proxy_usd",
        "funding_rate_state",
        "slippage_or_capacity_proxy",
    ]
    entry_delayed = _cohort_after_delay(frame, mask=candidates & entry, delay_h=delay_h, columns=columns)
    control_delayed = _cohort_after_delay(
        frame, mask=candidates & ~entry, delay_h=delay_h, columns=columns
    )
    if entry_delayed.empty or control_delayed.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "entry_count": int(len(entry_delayed)),
            "control_count": int(len(control_delayed)),
            "short_return_delta": None,
        }
    entry_ret = pd.to_numeric(entry_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    control_ret = pd.to_numeric(
        control_delayed[f"forward_{horizon}h_short_return"], errors="coerce"
    ).dropna()
    if entry_ret.empty or control_ret.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "entry_count": int(len(entry_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "delay_h": int(delay_h),
        "status": "ok",
        "entry_count": int(len(entry_ret)),
        "control_count": int(len(control_ret)),
        "entry_short_return_mean": float(entry_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(entry_ret.mean() - control_ret.mean()),
    }


def _shuffle_summary_positive(arr: np.ndarray, observed_delta: float, iterations: int) -> dict[str, Any]:
    if arr.size == 0:
        return {"passed": False, "iterations": int(iterations), "valid_iterations": 0}
    observed_upper_tail_quantile = float((arr >= observed_delta).mean())
    return {
        "passed": bool(observed_delta > 0.0 and observed_upper_tail_quantile <= 0.10),
        "iterations": int(iterations),
        "valid_iterations": int(arr.size),
        "observed_short_return_delta": float(observed_delta),
        "shuffle_mean_delta": float(np.nanmean(arr)),
        "shuffle_p50_delta": float(np.nanpercentile(arr, 50)),
        "shuffle_p95_delta": float(np.nanpercentile(arr, 95)),
        "observed_upper_tail_quantile": observed_upper_tail_quantile,
        "pass_rule": "observed delta must be positive and in top 10pct of shuffled deltas",
    }


def _shuffle_tests(frame: pd.DataFrame, *, iterations: int, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, flag_column=FLAG_COLUMN, horizon=horizon)
    observed_delta = observed.get("short_return_delta")
    if observed_delta is None:
        return {"status": "insufficient", "observed": observed, "tests": {}, "passed": False}
    rng = np.random.default_rng(20260513)
    tests: dict[str, Any] = {}
    base_flags = events[FLAG_COLUMN].to_numpy(dtype=bool)
    base_short = pd.to_numeric(
        events[f"forward_{horizon}h_short_return"], errors="coerce"
    ).to_numpy(dtype="float64")
    timestamp_groups = cooldown_eval._position_groups(events["open_time_ms"])
    symbol_groups = cooldown_eval._symbol_position_groups(events)

    shuffled_deltas: list[float] = []
    for _ in range(iterations):
        shuffled_flags = base_flags.copy()
        for positions in timestamp_groups:
            shuffled_flags[positions] = rng.permutation(shuffled_flags[positions])
        delta = cooldown_eval._delta_from_arrays(base_short, shuffled_flags)
        if delta is not None:
            shuffled_deltas.append(float(delta))
    tests["same_timestamp_feature_shuffle"] = _shuffle_summary_positive(
        np.asarray(shuffled_deltas, dtype="float64"), float(observed_delta), iterations
    )

    shifted_deltas: list[float] = []
    for _ in range(iterations):
        shifted_flags = base_flags.copy()
        for positions in symbol_groups:
            if len(positions) < 2:
                continue
            offset = int(rng.integers(1, len(positions)))
            shifted_flags[positions] = np.roll(shifted_flags[positions], offset)
        delta = cooldown_eval._delta_from_arrays(base_short, shifted_flags)
        if delta is not None:
            shifted_deltas.append(float(delta))
    tests["symbol_time_shift_shuffle"] = _shuffle_summary_positive(
        np.asarray(shifted_deltas, dtype="float64"), float(observed_delta), iterations
    )

    label_deltas: list[float] = []
    for _ in range(iterations):
        shuffled_short = base_short.copy()
        for positions in timestamp_groups:
            shuffled_short[positions] = rng.permutation(shuffled_short[positions])
        delta = cooldown_eval._delta_from_arrays(shuffled_short, base_flags)
        if delta is not None:
            label_deltas.append(float(delta))
    tests["same_timestamp_label_shuffle"] = _shuffle_summary_positive(
        np.asarray(label_deltas, dtype="float64"), float(observed_delta), iterations
    )

    return {
        "status": "ok",
        "horizon": f"h{horizon}",
        "observed": observed,
        "tests": tests,
        "passed": bool(observed_delta > 0.0 and all(test.get("passed") for test in tests.values())),
    }


def _symbol_holdout(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    observed = _effect_delta(events, flag_column=FLAG_COLUMN, horizon=horizon)
    rows: dict[str, Any] = {}
    for subject, group in events.groupby("subject"):
        local = _effect_delta(group, flag_column=FLAG_COLUMN, horizon=horizon)
        if int(local.get("entry_count") or 0) >= 3 and int(local.get("control_count") or 0) >= 3:
            rows[str(subject)] = local
    leave_one_out: dict[str, Any] = {}
    for subject in sorted(events["subject"].astype(str).unique()):
        local = events.loc[events["subject"].astype(str).ne(subject)]
        leave_one_out[subject] = _effect_delta(local, flag_column=FLAG_COLUMN, horizon=horizon)
    eligible = [row for row in rows.values() if row.get("short_return_delta") is not None]
    sign_consistent = [float(row["short_return_delta"]) > 0.0 for row in eligible]
    entry_counts = events.loc[events[FLAG_COLUMN].fillna(False).astype(bool)].groupby("subject").size()
    total_entry = int(entry_counts.sum())
    top_share = float(entry_counts.max() / total_entry) if total_entry else 1.0
    leave_one_deltas = [
        row.get("short_return_delta")
        for row in leave_one_out.values()
        if row.get("short_return_delta") is not None
    ]
    leave_one_pass = bool(leave_one_deltas and all(float(delta) > 0.0 for delta in leave_one_deltas))
    sign_fraction = float(np.mean(sign_consistent)) if sign_consistent else 0.0
    passed = bool(
        observed.get("short_return_delta") is not None
        and float(observed["short_return_delta"]) > 0.0
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
        "top_entry_symbol_event_share": top_share,
        "by_symbol": rows,
        "leave_one_symbol_out": leave_one_out,
        "passed": passed,
    }


def _liquidity_bucket_consistency(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    rows: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        rows[str(bucket)] = _effect_delta(group, flag_column=FLAG_COLUMN, horizon=horizon)
    eligible = [
        row
        for row in rows.values()
        if int(row.get("entry_count") or 0) >= 10
        and int(row.get("control_count") or 0) >= 10
        and row.get("short_return_delta") is not None
    ]
    passed = bool(len(eligible) >= 2 and all(float(row["short_return_delta"]) > 0.0 for row in eligible))
    return {
        "horizon": f"h{horizon}",
        "bucket_results": rows,
        "eligible_bucket_count": int(len(eligible)),
        "passed": passed,
        "pass_rule": "at least two buckets with >=10 entry/control observations and positive short-return delta",
    }


def _delay_robustness(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    scenarios = {
        f"delay_{delay}h": _delayed_effect(frame, delay_h=delay, horizon=horizon)
        for delay in (0, 1, 6, 24)
    }
    stress = [
        row for label, row in scenarios.items() if label in {"delay_1h", "delay_6h", "delay_24h"}
    ]
    passed = bool(
        stress
        and all(
            row.get("short_return_delta") is not None
            and float(row["short_return_delta"]) > 0.0
            and int(row.get("entry_count") or 0) >= 10
            and int(row.get("control_count") or 0) >= 10
            for row in stress
        )
    )
    return {"horizon": f"h{horizon}", "scenarios": scenarios, "passed": passed}


def _funding_drag_summary(frame: pd.DataFrame, horizons: tuple[int, ...]) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    entry = frame[FLAG_COLUMN].fillna(False).astype(bool)
    out: dict[str, Any] = {}
    for cohort_name, mask in {
        "post_pump_bid_replenishment_failure_entry_rows": candidates & entry,
        "candidate_control_rows": candidates & ~entry,
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
    out["provider_semantics_note"] = "Uses local binance_derivatives funding_rate as stored."
    return out


def _capacity_summary_for_subset(subset: pd.DataFrame) -> dict[str, Any]:
    capacity = pd.to_numeric(subset.get("capacity_proxy_usd"), errors="coerce").dropna()
    slippage = pd.to_numeric(subset.get("slippage_or_capacity_proxy"), errors="coerce").dropna()
    score = pd.to_numeric(subset.get("bid_replenishment_failure_score"), errors="coerce").dropna()
    bids = pd.to_numeric(subset.get("orderbook_bids_usd"), errors="coerce").dropna()
    bid_drawdown = subset.get("bid_depth_drawdown_from_prior_24h_flag", pd.Series(dtype=bool))
    return {
        "row_count": int(len(subset)),
        "capacity_proxy_usd_mean": float(capacity.mean()) if len(capacity) else None,
        "capacity_proxy_usd_median": float(capacity.median()) if len(capacity) else None,
        "capacity_proxy_usd_p10": float(capacity.quantile(0.10)) if len(capacity) else None,
        "slippage_proxy_mean": float(slippage.mean()) if len(slippage) else None,
        "slippage_proxy_p90": float(slippage.quantile(0.90)) if len(slippage) else None,
        "bid_replenishment_failure_score_mean": float(score.mean()) if len(score) else None,
        "orderbook_bids_usd_median": float(bids.median()) if len(bids) else None,
        "bid_depth_drawdown_from_prior_24h_fraction": float(
            bid_drawdown.fillna(False).astype(bool).mean()
        )
        if len(subset)
        else None,
    }


def _capacity_summary(frame: pd.DataFrame) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    entry = frame[FLAG_COLUMN].fillna(False).astype(bool)
    return {
        "post_pump_bid_replenishment_failure_entry_rows": _capacity_summary_for_subset(
            frame.loc[candidates & entry]
        ),
        "candidate_control_rows": _capacity_summary_for_subset(frame.loc[candidates & ~entry]),
        "proxy_notes": [
            "capacity_proxy_usd is min(0.5% of current 1h quote volume, 2% of OI value).",
            "slippage proxy is absolute 1h log return scaled by inverse square-root quote volume.",
            "This run uses native 1h orderbook/taker/OI fields only; no venue concentration sidecar is used.",
        ],
    }


def _event_count_by_symbol(frame: pd.DataFrame) -> dict[str, int]:
    events = frame.loc[frame[FLAG_COLUMN].fillna(False).astype(bool)]
    counts = events.groupby("subject").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _event_count_by_liquidity_bucket(frame: pd.DataFrame) -> dict[str, int]:
    events = frame.loc[frame[FLAG_COLUMN].fillna(False).astype(bool)]
    counts = events.groupby("liquidity_bucket").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _selected_short_changed_rows_equivalent(frame: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    events = frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()
    entry = events[FLAG_COLUMN].fillna(False).astype(bool)
    effect = _effect_delta(events, flag_column=FLAG_COLUMN, horizon=horizon)
    return {
        "interaction_type": "selected_short_delayed_entry_equivalent",
        "candidate_short_rows": int(len(events)),
        "changed_rows": int(entry.sum()),
        "changed_fraction": float(entry.mean()) if len(events) else 0.0,
        "primary_horizon": f"h{horizon}",
        "effect": effect,
        "note": (
            "There is no canonical 1h parent portfolio yet, so changed_rows means post-pump "
            "short candidates where failed bid replenishment would allow delayed short entry."
        ),
    }


def _feature_definitions() -> dict[str, Any]:
    return {
        "post_pump_short_candidate_flag": (
            "Inherited from the parallel 1h base frame: recent pump and mid/tail liquidity proxy."
        ),
        "prior_bid_or_taker_support_flag": (
            "Prior 24h had at least one shifted orderbook_bid_support_flag or taker_buy_dominance_flag."
        ),
        "book_pressure_deterioration_flag": (
            "orderbook_imbalance <= shifted rolling q40 OR bid_depth_log_change_6h <= min(q25, -0.01) "
            "OR current bid depth <= 60pct of shifted prior-24h max bid depth."
        ),
        "taker_buy_exhaustion_flag": (
            "taker_imbalance <= shifted rolling q40 OR 6h taker imbalance change <= -0.05."
        ),
        "price_unable_to_make_new_high_flag": (
            "perp_close <= 99.5pct of the shifted prior-6h high close."
        ),
        "oi_falling_or_collapse_flag": "oi_log_change_6h <= 0 OR inherited oi_collapse_confirmed_flag.",
        "bid_replenishment_failure_score": (
            "Sum of shifted prior support, book deterioration, taker exhaustion, price high failure, "
            "OI fall/collapse, current bid support absent, and current taker-buy dominance absent."
        ),
        FLAG_COLUMN: (
            "post-pump candidate AND prior support AND book deterioration AND price high failure "
            "AND bid_replenishment_failure_score >= 5. Expected use shape is delayed short entry, "
            "so positive short-return delta is required."
        ),
        "pit_rule": "rolling thresholds and prior-window features are shifted one bar; forward returns are labels only.",
        "provider_boundary": "Uses local 1h orderbook/taker/OI fields; coverage is not treated as alpha validation.",
    }


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
            "Returns use perp_close from binance_derivatives.",
            "Orderbook/taker/OI fields are used as local research inputs, not provider-verified truth.",
            "This run does not use venue concentration or exchange-flow sidecars.",
        ],
        "loaded_symbol_count": int(len(loaded)),
        "symbol_status": meta.get("symbol_status", {}),
    }
    if frame.empty:
        payload.update({"row_count": 0, "status": "empty"})
        return payload
    core_columns = [
        "perp_close",
        "open_interest_value",
        "oi_log_change_6h",
        "orderbook_bids_usd",
        "orderbook_imbalance",
        "bid_depth_log_change_6h",
        "taker_imbalance",
        "perp_quote_volume_usd",
    ]
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
                for column in core_columns
            },
        }
    )
    return payload


def _pass_fail_decision(
    *,
    frame: pd.DataFrame,
    shuffle_tests: dict[str, Any],
    symbol_holdout: dict[str, Any],
    liquidity_bucket_consistency: dict[str, Any],
    delay_robustness: dict[str, Any],
) -> dict[str, Any]:
    candidates = (
        frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
        if not frame.empty
        else pd.Series(dtype=bool)
    )
    entry = frame[FLAG_COLUMN].fillna(False).astype(bool) if not frame.empty else pd.Series(dtype=bool)
    candidate_count = int(candidates.sum()) if not frame.empty else 0
    entry_count = int((candidates & entry).sum()) if not frame.empty else 0
    blockers: list[str] = []
    if frame.empty:
        blockers.append("no_research_frame")
    if frame["subject"].nunique() < 10 if not frame.empty else True:
        blockers.append("loaded_symbol_count_below_10")
    if candidate_count < 100:
        blockers.append("post_pump_candidate_count_below_100")
    if entry_count < 30:
        blockers.append("bid_replenishment_failure_event_count_below_30")

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
        "post_pump_bid_replenishment_failure_event_count": entry_count,
        "decision_rule": (
            "pass only if data minimums clear and positive-delta shuffle, symbol holdout, "
            "liquidity bucket, and +1h/+6h/+24h delay robustness all pass"
        ),
    }


def _next_landing_shape(decision: dict[str, Any]) -> dict[str, Any]:
    if decision.get("label") == "pass":
        return {
            "recommended_shape": "delayed_short_entry_parent_interaction",
            "next_step": (
                "Build a quarantined 1h parent interaction simulator with delayed-entry variants; "
                "do not bridge to h10d yet."
            ),
        }
    if decision.get("label") == "blocked":
        return {
            "recommended_shape": "data_quality_or_event_count_repair",
            "next_step": "Repair blockers before interpreting alpha.",
        }
    return {
        "recommended_shape": "fail_closed_or_redefine_bid_failure_state",
        "next_step": "Do not promote. Inspect failed shuffle/holdout/bucket/delay gates before rerunning.",
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
    shuffle_tests = (
        _shuffle_tests(frame, iterations=shuffle_iterations, horizon=24)
        if not frame.empty
        else {"passed": False}
    )
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
        "event_count_by_liquidity_bucket": _event_count_by_liquidity_bucket(frame)
        if not frame.empty
        else {},
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": _forward_return_table(frame, horizons)
        if not frame.empty
        else {},
        "selected_short_changed_rows_equivalent": _selected_short_changed_rows_equivalent(
            frame, horizon=24
        )
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
    root = trap_eval._resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / f"{RESEARCH_ID}.json"
    horizons = tuple(DEFAULT_HORIZONS)
    symbols = trap_eval._discover_symbols(root, requested=str(args.symbols), limit=int(args.symbol_limit))
    frame, meta = trap_eval._load_research_frame(root, symbols, horizons)
    if not frame.empty:
        frame = _add_bid_replenishment_failure_state(frame)
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
        "post_pump_bid_replenishment_failure_event_count": report["pass_fail_decision"].get(
            "post_pump_bid_replenishment_failure_event_count"
        ),
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
