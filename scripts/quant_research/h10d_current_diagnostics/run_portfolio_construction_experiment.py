from __future__ import annotations

import argparse
import json
import math
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
QUANT_SCRIPT_DIR = ROOT / "scripts" / "quant_research"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(QUANT_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(QUANT_SCRIPT_DIR))

import analyze_v5_rw_baseline_rebalance_phase_sensitivity as v5_phase  # noqa: E402
from enhengclaw.quant_research.contracts import portable_path, read_json, write_json
from enhengclaw.quant_research.execution_backtest import backtest_cross_sectional, filter_cross_sectional_execution_frame
from enhengclaw.quant_research.fixed_set_comparison import extract_period_frame, performance_summary
from enhengclaw.quant_research.horizon_metrics import (
    SHARPE_METRIC_CONVENTION_VERSION,
    overlap_adjusted_performance_summary,
    overlap_adjusted_periods_per_year,
)
from enhengclaw.quant_research.lab import (
    QUANT_ARTIFACTS_ROOT,
    _apply_universe_filter,
    _experiment_directory_name,
    _resolved_execution_cost_models,
)
from enhengclaw.quant_research.overlap_integrity import (
    evaluate_overlap_integrity,
    walk_forward_split_with_purge,
)
from enhengclaw.quant_research.split_realization_contract import (
    expected_rebalance_count,
    realization_step_bars as split_contract_realization_step_bars,
    resolve_split_realization_contract,
    split_boundary_contamination_total,
)
from enhengclaw.quant_research.validation_contract import (
    build_regime_holdout_section,
    execution_capacity_limits,
    validation_contract_reference_capital_usd,
)


BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d"
EFFECTIVE_RESEARCH_BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve"
BASELINE_EXPERIMENT_ID = "2026-04-29-xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
H10D_VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
CURRENT_BASELINE_CONSTRUCTION = {
    "target_engine": "multiphase_equal_sleeve",
    "phase_offsets_days": list(range(10)),
    "sleeve_weight": 0.1,
    "rebalance_interval_days_per_sleeve": 10,
}
MULTIPHASE_PHASES = tuple(range(10))
MULTIPHASE_SLEEVE_WEIGHT = 1.0 / float(len(MULTIPHASE_PHASES))
CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL = "multiphase_top3_bottom3_10sleeve_cap005_gross100"


DEFAULT_VARIANTS: list[dict[str, Any]] = [
    {
        "label": "top3_bottom3_step10_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top5_bottom5_step10_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "top5_bottom5",
        "top_k": 5,
        "bottom_k": 5,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "quintile_proxy_k4_step10_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "quintile_spread_proxy_fixed_k4",
        "top_k": 4,
        "bottom_k": 4,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top3_bottom3_step5_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 5,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top3_bottom3_step15_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 15,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top3_bottom3_step20_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 20,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top5_bottom5_step20_cap005_gross100",
        "target_engine": "single_phase",
        "construction": "top5_bottom5",
        "top_k": 5,
        "bottom_k": 5,
        "rebalance_step_bars": 20,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top3_bottom3_step10_cap001_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.001,
    },
    {
        "label": "top3_bottom3_step10_cap0025_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.0025,
    },
    {
        "label": "top3_bottom3_step10_cap010_gross100",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.010,
    },
    {
        "label": "top3_bottom3_step10_cap005_gross075",
        "target_engine": "single_phase",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 0.75,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "top5_bottom5_step10_cap005_gross075",
        "target_engine": "single_phase",
        "construction": "top5_bottom5",
        "top_k": 5,
        "bottom_k": 5,
        "rebalance_step_bars": 10,
        "gross_multiplier": 0.75,
        "trade_participation_cap": 0.005,
    },
    {
        "label": CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL,
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_step5_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 5,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_step7_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 7,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_step15_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 15,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_step20_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 20,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_step30_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 30,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_quintile_proxy_k4_10sleeve_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "quintile_spread_proxy_fixed_k4",
        "top_k": 4,
        "bottom_k": 4,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top5_bottom5_10sleeve_cap005_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top5_bottom5",
        "top_k": 5,
        "bottom_k": 5,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.005,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_cap0025_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.0025,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_cap001_gross100",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 1.0,
        "trade_participation_cap": 0.001,
    },
    {
        "label": "multiphase_top3_bottom3_10sleeve_cap005_gross075",
        "target_engine": "multiphase_equal_sleeve",
        "construction": "top3_bottom3",
        "top_k": 3,
        "bottom_k": 3,
        "rebalance_step_bars": 10,
        "gross_multiplier": 0.75,
        "trade_participation_cap": 0.005,
    },
]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (ROOT / path).resolve()


def _variant_constraints(base_constraints: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    constraints = deepcopy(base_constraints)
    constraints["top_long_count"] = int(variant["top_k"])
    constraints["bottom_short_count"] = int(variant["bottom_k"])
    gross_multiplier = float(variant.get("gross_multiplier", 1.0) or 1.0)
    constraints["long_leverage"] = float(base_constraints.get("long_leverage", 0.5) or 0.5) * gross_multiplier
    constraints["short_leverage"] = float(base_constraints.get("short_leverage", 0.5) or 0.5) * gross_multiplier
    constraints["max_gross_leverage"] = float(base_constraints.get("max_gross_leverage", 1.0) or 1.0) * gross_multiplier
    constraints.pop("position_multiplier_overlay_id", None)
    return constraints


def _variant_split_contract(base_contract: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    contract = deepcopy(base_contract)
    contract["realization_step_bars"] = int(variant["rebalance_step_bars"])
    return resolve_split_realization_contract(contract=contract, shape="cross_sectional")


def _variant_capacity_limits(base_limits: dict[str, float], variant: dict[str, Any]) -> dict[str, float]:
    limits = dict(base_limits)
    trade_cap = float(variant.get("trade_participation_cap", limits.get("max_trade_participation_rate_max", 0.005)))
    limits["max_trade_participation_rate_max"] = trade_cap
    # Keep inventory cap fixed unless explicitly overridden; h10d promotion guard
    # treats trade participation and inventory participation as separate blockers.
    if variant.get("inventory_participation_cap") is not None:
        limits["max_inventory_participation_rate_max"] = float(variant["inventory_participation_cap"])
    limits["max_participation_rate_max"] = max(
        float(limits.get("max_trade_participation_rate_max", 0.0) or 0.0),
        float(limits.get("max_inventory_participation_rate_max", 0.0) or 0.0),
    )
    return limits


def _periods_from_window_metrics(*, label: str, windows: list[dict[str, Any]], stress: bool = False) -> pd.DataFrame:
    if not stress:
        return extract_period_frame(candidate_label=label, walk_forward={"windows": windows})
    rows: list[dict[str, Any]] = []
    for window_index, window in enumerate(windows):
        for period in list(window.get("stress_periods") or []):
            timestamp_ms = int(period["timestamp_ms"])
            rows.append(
                {
                    "candidate_label": label,
                    "window_index": int(window_index),
                    "timestamp_ms": timestamp_ms,
                    "timestamp_utc": pd.to_datetime(timestamp_ms, unit="ms", utc=True)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "net_period_return": float(period["net_period_return"]),
                    "gross_return_before_costs": float(period["gross_return_before_costs"]),
                    "fee_cost_return": float(period["fee_cost_return"]),
                    "slippage_cost_return": float(period["slippage_cost_return"]),
                    "funding_cost_return": float(period["funding_cost_return"]),
                    "borrow_cost_return": float(period["borrow_cost_return"]),
                    "turnover": float(period["turnover"]),
                    "trade_participation_rate": float(period["trade_participation_rate"]),
                    "inventory_participation_rate": float(period["inventory_participation_rate"]),
                    "max_participation_rate": float(period["max_participation_rate"]),
                    "capacity_breach_count": int(period["capacity_breach_count"]),
                }
            )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame.from_records(rows).sort_values(["timestamp_ms", "window_index"]).reset_index(drop=True)
    if frame["timestamp_ms"].duplicated().any():
        frame = (
            frame.groupby("timestamp_ms", as_index=False)
            .agg(
                {
                    "candidate_label": "first",
                    "window_index": "min",
                    "timestamp_utc": "first",
                    "net_period_return": "mean",
                    "gross_return_before_costs": "mean",
                    "fee_cost_return": "mean",
                    "slippage_cost_return": "mean",
                    "funding_cost_return": "mean",
                    "borrow_cost_return": "mean",
                    "turnover": "mean",
                    "trade_participation_rate": "max",
                    "inventory_participation_rate": "max",
                    "max_participation_rate": "max",
                    "capacity_breach_count": "sum",
                }
            )
            .sort_values("timestamp_ms")
            .reset_index(drop=True)
        )
    return frame


def _phase_frame(frame: pd.DataFrame, *, phase_offset_days: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return frame.iloc[0:0].copy(), {
            "phase_offset_days": int(phase_offset_days),
            "status": "empty_or_missing_timestamp_ms",
        }
    timestamps = sorted(int(item) for item in frame["timestamp_ms"].drop_duplicates().tolist())
    phase = int(phase_offset_days)
    if phase < 0:
        raise ValueError(f"phase_offset_days must be >= 0: {phase}")
    if phase >= len(timestamps):
        return frame.iloc[0:0].copy(), {
            "phase_offset_days": phase,
            "status": "phase_after_available_history",
            "available_timestamp_count": int(len(timestamps)),
        }
    start_ms = int(timestamps[phase])
    output = frame.loc[pd.to_numeric(frame["timestamp_ms"], errors="coerce").ge(start_ms)].copy()
    return output, {
        "phase_offset_days": phase,
        "status": "ok",
        "start_timestamp_ms": start_ms,
        "start_date_utc": pd.to_datetime(start_ms, unit="ms", utc=True).date().isoformat(),
        "row_count": int(len(output)),
        "timestamp_count": int(output["timestamp_ms"].nunique()),
    }


def _scale_sleeve_periods(periods: pd.DataFrame, *, phase: int, sleeve_weight: float) -> pd.DataFrame:
    if periods.empty:
        return periods.copy()
    scaled = periods.copy()
    scaled["phase_offset_days"] = int(phase)
    scaled["sleeve_weight"] = float(sleeve_weight)
    for column in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "borrow_cost_return",
        "turnover",
        "trade_notional_usd",
        "trade_participation_rate",
        "inventory_participation_rate",
        "max_participation_rate",
    ):
        if column in scaled.columns:
            scaled[column] = pd.to_numeric(scaled[column], errors="coerce").fillna(0.0) * float(sleeve_weight)
    if "available_quote_volume_usd" in scaled.columns:
        scaled["available_quote_volume_usd"] = pd.to_numeric(
            scaled["available_quote_volume_usd"],
            errors="coerce",
        ).fillna(0.0) * float(sleeve_weight)
    scaled["capacity_breach_count"] = 0
    return scaled


def _aggregate_multiphase_periods(
    *,
    label: str,
    sleeve_periods: pd.DataFrame,
    trade_participation_cap: float,
    inventory_participation_cap: float,
) -> pd.DataFrame:
    if sleeve_periods.empty:
        return pd.DataFrame()
    working = sleeve_periods.copy()
    working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce")
    working = working.dropna(subset=["timestamp_ms"]).copy()
    working["timestamp_ms"] = working["timestamp_ms"].astype("int64")
    for column in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "borrow_cost_return",
        "turnover",
        "trade_notional_usd",
        "trade_participation_rate",
        "inventory_participation_rate",
        "max_participation_rate",
        "available_quote_volume_usd",
    ):
        if column not in working.columns:
            working[column] = 0.0
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0)
    grouped = (
        working.groupby("timestamp_ms", sort=True)
        .agg(
            candidate_label=("candidate_label", "first"),
            window_index=("window_index", "min"),
            active_sleeve_count=("phase_offset_days", "nunique"),
            contributing_sleeve_period_count=("phase_offset_days", "count"),
            net_period_return=("net_period_return", "sum"),
            gross_return_before_costs=("gross_return_before_costs", "sum"),
            fee_cost_return=("fee_cost_return", "sum"),
            slippage_cost_return=("slippage_cost_return", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            borrow_cost_return=("borrow_cost_return", "sum"),
            turnover=("turnover", "sum"),
            trade_notional_usd=("trade_notional_usd", "sum"),
            trade_participation_rate=("trade_participation_rate", "sum"),
            inventory_participation_rate=("inventory_participation_rate", "sum"),
            available_quote_volume_usd=("available_quote_volume_usd", "sum"),
        )
        .reset_index()
    )
    grouped["candidate_label"] = str(label)
    grouped["timestamp_utc"] = pd.to_datetime(grouped["timestamp_ms"], unit="ms", utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    grouped["max_participation_rate"] = grouped[["trade_participation_rate", "inventory_participation_rate"]].max(axis=1)
    grouped["capacity_breach_count"] = (
        grouped["trade_participation_rate"].gt(float(trade_participation_cap))
        | grouped["inventory_participation_rate"].gt(float(inventory_participation_cap))
    ).astype(int)
    return grouped.sort_values("timestamp_ms").reset_index(drop=True)


def _fast_score_test_frame(
    *,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    daily_ic_by_factor: dict[str, pd.Series],
) -> pd.DataFrame:
    train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
    weights = v5_phase.weights_for_train_end(
        daily_ic_by_factor=daily_ic_by_factor,
        train_end_ms=train_end_ms,
    )
    return v5_phase.score_frame(test_df, factor_weights=weights)


def _empirical_periods_per_year(periods: pd.DataFrame, *, default: int = 365) -> int:
    if periods.empty or "timestamp_ms" not in periods.columns or len(periods) < 2:
        return int(default)
    timestamps = pd.to_numeric(periods["timestamp_ms"], errors="coerce").dropna().astype("int64")
    if len(timestamps) < 2:
        return int(default)
    span_days = max((int(timestamps.max()) - int(timestamps.min())) / 86_400_000.0, 1.0)
    years = span_days / 365.25
    if years <= 0.0:
        return int(default)
    return max(int(round(float(len(timestamps)) / years)), 1)


def _summary_windows_from_periods(periods: pd.DataFrame, *, periods_per_year_value: int) -> list[dict[str, Any]]:
    if periods.empty:
        return []
    working = periods.copy()
    working["timestamp_dt"] = pd.to_datetime(working["timestamp_ms"], unit="ms", utc=True)
    working = working.sort_values("timestamp_dt").reset_index(drop=True)
    first = working["timestamp_dt"].min()
    if pd.isna(first):
        return []
    day_offset = (working["timestamp_dt"] - first).dt.days.fillna(0).astype(int)
    working["summary_window_index"] = (day_offset // 30).astype(int)
    rows: list[dict[str, Any]] = []
    for window_index, group in working.groupby("summary_window_index", sort=True):
        returns = pd.to_numeric(group["net_period_return"], errors="coerce").fillna(0.0)
        perf = performance_summary(returns, periods_per_year=periods_per_year_value)
        rows.append(
            {
                "window_index": int(window_index),
                "test_start_utc": group["timestamp_dt"].min().isoformat().replace("+00:00", "Z"),
                "test_end_utc": group["timestamp_dt"].max().isoformat().replace("+00:00", "Z"),
                "validation_end_utc": group["timestamp_dt"].min().isoformat().replace("+00:00", "Z"),
                "sharpe": float(perf["sharpe"]),
                "net_return": float(perf["net_return"]),
                "max_drawdown": float(perf["max_drawdown"]),
            }
        )
    return rows


def _walk_forward_summary(*, windows: list[dict[str, Any]], split_contract: dict[str, Any]) -> dict[str, Any]:
    sharpes = [float(item.get("sharpe", 0.0) or 0.0) for item in windows]
    net_returns = [float(item.get("net_return", 0.0) or 0.0) for item in windows]
    loss_fraction = float(sum(1 for value in net_returns if value < 0.0) / len(net_returns)) if net_returns else 0.0
    return {
        "median_oos_sharpe": float(pd.Series(sharpes).median()) if sharpes else 0.0,
        "mean_oos_sharpe": float(pd.Series(sharpes).mean()) if sharpes else 0.0,
        "window_count": int(len(windows)),
        "loss_window_fraction": loss_fraction,
        "split_realization_contract": split_contract,
        "windows": windows,
    }


def _variant_summary(
    *,
    variant: dict[str, Any],
    windows: list[dict[str, Any]],
    periods: pd.DataFrame,
    stress_periods: pd.DataFrame,
    split_contract: dict[str, Any],
    validation_contract: dict[str, Any],
    baseline_perf: dict[str, float] | None,
) -> dict[str, Any]:
    period_count = int(len(periods))
    annualization = float(
        variant.get("summary_periods_per_year")
        or overlap_adjusted_periods_per_year(
            bar_interval_ms=int(split_contract["bar_interval_ms"]),
            target_horizon_bars=int(split_contract["target_horizon_bars"]),
            realization_step_bars=int(split_contract["realization_step_bars"]),
        )
    )
    if period_count:
        perf = overlap_adjusted_performance_summary(
            periods["net_period_return"],
            bar_interval_ms=int(split_contract["bar_interval_ms"]),
            target_horizon_bars=int(split_contract["target_horizon_bars"]),
            realization_step_bars=int(split_contract["realization_step_bars"]),
        )
    else:
        perf = {
            "net_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "overlap_adjusted_periods_per_year": annualization,
            "independent_period_bars": max(
                int(split_contract["target_horizon_bars"]),
                int(split_contract["realization_step_bars"]),
            ),
        }
    stress_perf = (
        overlap_adjusted_performance_summary(
            stress_periods["net_period_return"],
            bar_interval_ms=int(split_contract["bar_interval_ms"]),
            target_horizon_bars=int(split_contract["target_horizon_bars"]),
            realization_step_bars=int(split_contract["realization_step_bars"]),
        )
        if not stress_periods.empty
        else {"net_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    )
    walk_forward = _walk_forward_summary(windows=windows, split_contract=split_contract)
    regime_holdout = build_regime_holdout_section(walk_forward=walk_forward, contract=validation_contract)
    base_net = float(baseline_perf.get("net_return", 0.0)) if baseline_perf else float(perf["net_return"])
    base_sharpe = float(baseline_perf.get("sharpe", 0.0)) if baseline_perf else float(perf["sharpe"])
    return {
        "label": str(variant["label"]),
        "target_engine": str(variant.get("target_engine") or "single_phase"),
        "construction": str(variant["construction"]),
        "top_k": int(variant["top_k"]),
        "bottom_k": int(variant["bottom_k"]),
        "rebalance_step_bars": int(variant["rebalance_step_bars"]),
        "target_horizon_bars": int(split_contract["target_horizon_bars"]),
        "phase_count": int(variant.get("phase_count", 1) or 1),
        "sleeve_weight": float(variant.get("sleeve_weight", 1.0) or 1.0),
        "is_current_effective_baseline": str(variant["label"]) == CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL,
        "gross_multiplier": float(variant.get("gross_multiplier", 1.0) or 1.0),
        "trade_participation_cap": float(variant["trade_participation_cap"]),
        "inventory_participation_cap": float(
            variant.get("inventory_participation_cap", execution_capacity_limits(validation_contract)["max_inventory_participation_rate_max"])
        ),
        "sharpe_metric_convention": SHARPE_METRIC_CONVENTION_VERSION,
        "periods_per_year": float(perf.get("overlap_adjusted_periods_per_year", annualization)),
        "independent_period_bars": int(perf.get("independent_period_bars", 0) or 0),
        "period_count": period_count,
        "start_utc": str(periods["timestamp_utc"].iloc[0]) if period_count else None,
        "end_utc": str(periods["timestamp_utc"].iloc[-1]) if period_count else None,
        "full_oos_cumulative_net_return": float(perf["net_return"]),
        "full_oos_h10d_equivalent_sharpe": float(perf["sharpe"]),
        "full_oos_period_sharpe": float(perf["sharpe"]),
        "full_oos_max_drawdown": float(perf["max_drawdown"]),
        "full_oos_loss_period_fraction": float((periods["net_period_return"] < 0.0).mean()) if period_count else 0.0,
        "full_oos_mean_period_return": float(periods["net_period_return"].mean()) if period_count else 0.0,
        "full_oos_turnover_total": float(periods["turnover"].sum()) if period_count else 0.0,
        "full_oos_trade_count_proxy": int(sum(int(item.get("trade_count", 0) or 0) for item in windows)),
        "full_oos_rebalance_count": int(sum(int(item.get("rebalance_count", 0) or 0) for item in windows)),
        "full_oos_max_trade_participation_rate": float(periods["trade_participation_rate"].max()) if period_count else 0.0,
        "full_oos_max_inventory_participation_rate": float(periods["inventory_participation_rate"].max()) if period_count else 0.0,
        "full_oos_capacity_breach_count": int(periods["capacity_breach_count"].sum()) if period_count else 0,
        "stress_cumulative_net_return": float(stress_perf["net_return"]),
        "stress_period_sharpe": float(stress_perf["sharpe"]),
        "stress_max_drawdown": float(stress_perf["max_drawdown"]),
        "stress_max_trade_participation_rate": float(stress_periods["trade_participation_rate"].max()) if not stress_periods.empty else 0.0,
        "stress_max_inventory_participation_rate": float(stress_periods["inventory_participation_rate"].max()) if not stress_periods.empty else 0.0,
        "stress_capacity_breach_count": int(stress_periods["capacity_breach_count"].sum()) if not stress_periods.empty else 0,
        "walk_forward_median_oos_sharpe": float(walk_forward["median_oos_sharpe"]),
        "walk_forward_window_count": int(walk_forward["window_count"]),
        "walk_forward_loss_window_fraction": float(walk_forward["loss_window_fraction"]),
        "regime_holdout_passed": bool(regime_holdout.get("passed")),
        "worst_regime_median_oos_sharpe": float(regime_holdout.get("worst_regime_median_oos_sharpe", 0.0) or 0.0),
        "positive_regime_fraction": float(regime_holdout.get("positive_regime_fraction", 0.0) or 0.0),
        "delta_cumulative_net_return_vs_baseline": float(perf["net_return"]) - base_net,
        "delta_period_sharpe_vs_baseline": float(perf["sharpe"]) - base_sharpe,
        "capacity_gate_passed": (
            (float(periods["trade_participation_rate"].max()) if period_count else 0.0) <= float(variant["trade_participation_cap"])
            and (float(periods["inventory_participation_rate"].max()) if period_count else 0.0)
            <= float(variant.get("inventory_participation_cap", execution_capacity_limits(validation_contract)["max_inventory_participation_rate_max"]))
        ),
    }


def _window_zero_payload(
    *,
    train_end: datetime,
    validation_end: datetime,
    test_df: pd.DataFrame,
    split_integrity: dict[str, Any],
    split_boundary_contamination: int,
) -> dict[str, Any]:
    test_start = (
        pd.to_datetime(test_df["timestamp_ms"].min(), unit="ms", utc=True).isoformat().replace("+00:00", "Z")
        if not test_df.empty
        else None
    )
    test_end = (
        pd.to_datetime(test_df["timestamp_ms"].max(), unit="ms", utc=True).isoformat().replace("+00:00", "Z")
        if not test_df.empty
        else None
    )
    return {
        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
        "test_start_utc": test_start,
        "test_end_utc": test_end,
        "contract_passed": False,
        "split_boundary_contamination_total": int(split_boundary_contamination),
        "split_boundary_contamination_counts": dict(split_integrity.get("split_boundary_contamination_counts") or {}),
        "backtest_realization_mismatch": dict(split_integrity.get("backtest_horizon_mismatch") or {}),
        "sharpe": 0.0,
        "net_return": 0.0,
        "max_drawdown": 0.0,
        "turnover": 0.0,
        "trade_count": 0,
        "rebalance_count": 0,
        "max_trade_participation_rate": 0.0,
        "max_inventory_participation_rate": 0.0,
        "capacity_breach_count": 0,
        "stress_sharpe": 0.0,
        "stress_net_return": 0.0,
        "stress_max_drawdown": 0.0,
        "stress_max_trade_participation_rate": 0.0,
        "stress_max_inventory_participation_rate": 0.0,
        "stress_capacity_breach_count": 0,
        "periods": [],
        "stress_periods": [],
    }


def _format_float(value: Any, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if math.isnan(number):
        return "n/a"
    return f"{number:.{digits}f}"


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    rows = list(payload.get("variant_summaries") or [])
    rows_sorted = sorted(rows, key=lambda item: float(item["full_oos_cumulative_net_return"]), reverse=True)
    lines: list[str] = []
    lines.append("# H10D Portfolio Construction Experiment")
    lines.append("")
    lines.append(f"- Score parent: `{payload['score_parent_label']}`")
    lines.append(f"- Effective research baseline: `{payload['effective_research_baseline_label']}`")
    lines.append(f"- This run construction status: `{payload['this_run_construction_status']}`")
    lines.append(f"- Current effective baseline variant: `{payload['current_effective_baseline_variant_label']}`")
    lines.append(f"- Status: `{payload['status']}`")
    lines.append(f"- Experiment id: `{payload['baseline_experiment_id']}`")
    lines.append(f"- Variant count: `{len(rows)}`")
    lines.append(f"- Score reused across variants: `{payload['score_reused_across_variants']}`")
    lines.append(f"- Sharpe convention: `{payload['sharpe_metric_convention']['version']}`")
    lines.append(
        "- Headline Sharpe is overlap-adjusted h10d-equivalent Sharpe; do not annualize overlapping "
        "10-sleeve booking returns by observed daily aggregate count."
    )
    lines.append("")
    lines.append("## Ranked Variants")
    lines.append("")
    lines.append("| Rank | Variant | Engine | K | Step | Gross | Cap | CumRet | h10d-eq Sharpe | Max DD | Turnover | Max Trade Part. | Breaches | Delta CumRet |")
    lines.append("| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for index, row in enumerate(rows_sorted, start=1):
        lines.append(
            "| {rank} | `{label}` | `{engine}` | {k} | {step} | {gross} | {cap} | {cum} | {sharpe} | {dd} | {turnover} | {max_trade} | {breaches} | {delta} |".format(
                rank=index,
                label=row["label"],
                engine=row.get("target_engine", "single_phase"),
                k=f"{row['top_k']}/{row['bottom_k']}",
                step=row["rebalance_step_bars"],
                gross=_format_float(row["gross_multiplier"], 2),
                cap=_format_float(row["trade_participation_cap"], 4),
                cum=_format_float(row["full_oos_cumulative_net_return"], 3),
                sharpe=_format_float(row["full_oos_period_sharpe"], 3),
                dd=_format_float(row["full_oos_max_drawdown"], 3),
                turnover=_format_float(row["full_oos_turnover_total"], 2),
                max_trade=_format_float(row["full_oos_max_trade_participation_rate"], 4),
                breaches=row["full_oos_capacity_breach_count"],
                delta=_format_float(row["delta_cumulative_net_return_vs_baseline"], 3),
            )
        )
    lines.append("")
    lines.append("## Capacity Gate Sweep")
    lines.append("")
    lines.append("| Variant | Cap | Max Trade Part. | Max Inventory Part. | Gate | Breaches |")
    lines.append("| --- | ---: | ---: | ---: | --- | ---: |")
    for row in rows:
        if row["construction"] == "top3_bottom3" and row["rebalance_step_bars"] == 10 and row["gross_multiplier"] == 1.0:
            lines.append(
                "| `{label}` | {cap} | {max_trade} | {max_inv} | `{gate}` | {breaches} |".format(
                    label=row["label"],
                    cap=_format_float(row["trade_participation_cap"], 4),
                    max_trade=_format_float(row["full_oos_max_trade_participation_rate"], 4),
                    max_inv=_format_float(row["full_oos_max_inventory_participation_rate"], 4),
                    gate=row["capacity_gate_passed"],
                    breaches=row["full_oos_capacity_breach_count"],
                )
            )
    lines.append("")
    lines.append("## Interpretation Boundary")
    lines.append("")
    lines.append(
        "This diagnostic now includes both historical single-phase sweeps and true 10-phase "
        "equal-sleeve variants. It reuses the score/model path and changes only construction parameters. "
        "Participation-cap rows change gate thresholds only; they do not impose a sizing clamp."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run h10d portfolio construction diagnostics for the research baseline.")
    parser.add_argument("--baseline-label", default=BASELINE_LABEL)
    parser.add_argument("--effective-baseline-label", default=EFFECTIVE_RESEARCH_BASELINE_LABEL)
    parser.add_argument("--baseline-experiment-id", default=BASELINE_EXPERIMENT_ID)
    parser.add_argument(
        "--variant-labels",
        default="",
        help="Optional comma-separated subset of variant labels to run.",
    )
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--validation-contract", type=Path, default=H10D_VALIDATION_CONTRACT_PATH)
    parser.add_argument("--run-label", default="2026-06-03-research-v5-rw-bridge-no-overlay-h10d-portfolio-construction")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports" / "2026-06-03",
    )
    args = parser.parse_args(argv)

    artifacts_root = _resolve(args.artifacts_root)
    experiment_root = artifacts_root / "experiments" / _experiment_directory_name(str(args.baseline_experiment_id))
    spec = dict(read_json(experiment_root / "experiment_spec.json"))
    feature_manifest = dict(read_json(_resolve(Path(str(spec["feature_manifest_path"])))))
    feature_path = _resolve(Path(str(feature_manifest["features_path"])))
    validation_contract = dict(read_json(_resolve(args.validation_contract)))
    base_execution_cost_model, stress_execution_cost_model = _resolved_execution_cost_models()
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    base_capacity_limits = execution_capacity_limits(validation_contract)
    base_split_contract = resolve_split_realization_contract(
        contract=dict(spec["split_realization_contract"]),
        shape="cross_sectional",
    )
    base_constraints = dict(spec.get("profile_constraints") or {})
    base_constraints["strategy_profile"] = str(spec.get("strategy_profile") or "")

    raw_frame = pd.read_csv(feature_path, low_memory=False)
    frame = _apply_universe_filter(raw_frame, universe_filter=spec.get("universe_filter"))
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=base_constraints)
    if frame.empty:
        raise RuntimeError("portfolio construction experiment has no execution-eligible rows")
    feature_columns = list(spec.get("feature_columns") or [])
    daily_ic_by_factor = v5_phase.build_daily_ic_by_factor(frame, feature_columns=feature_columns)

    time_index = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    start_anchor = time_index.min() + timedelta(days=120)
    final_anchor = time_index.max() - timedelta(days=30)
    variants = [dict(item) for item in DEFAULT_VARIANTS]
    requested_variant_labels = {
        item.strip()
        for item in str(args.variant_labels or "").split(",")
        if item.strip()
    }
    if requested_variant_labels:
        available = {str(item["label"]) for item in variants}
        missing = sorted(requested_variant_labels - available)
        if missing:
            raise ValueError(f"Unknown variant labels: {missing}")
        variants = [item for item in variants if str(item["label"]) in requested_variant_labels]
        if CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL not in requested_variant_labels:
            raise ValueError(
                f"--variant-labels must include current effective baseline {CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL!r}"
            )
    variant_state: dict[str, dict[str, Any]] = {
        str(variant["label"]): {
            "variant": variant,
            "constraints": _variant_constraints(base_constraints, variant),
            "split_contract": _variant_split_contract(base_split_contract, variant),
            "capacity_limits": _variant_capacity_limits(base_capacity_limits, variant),
            "windows": [],
            "phase_windows": {int(phase): [] for phase in MULTIPHASE_PHASES},
            "phase_audits": [],
        }
        for variant in variants
    }
    single_labels = [
        str(variant["label"])
        for variant in variants
        if str(variant.get("target_engine") or "single_phase") == "single_phase"
    ]
    multiphase_labels = [
        str(variant["label"])
        for variant in variants
        if str(variant.get("target_engine") or "single_phase") == "multiphase_equal_sleeve"
    ]

    current_anchor = start_anchor
    scored_window_count = 0
    split_skipped_window_count = 0
    while current_anchor <= final_anchor:
        train_end = current_anchor - timedelta(days=30)
        validation_end = current_anchor
        test_end = current_anchor + timedelta(days=30)
        train_df, validation_df, test_df = walk_forward_split_with_purge(
            frame=frame,
            time_col="timestamp_ms",
            train_end=train_end,
            validation_end=validation_end,
            test_end=test_end,
            split_realization_contract=base_split_contract,
        )
        if train_df.empty or validation_df.empty or test_df.empty:
            current_anchor = current_anchor + timedelta(days=30)
            continue
        scored: dict[str, Any] | None = None
        for label in single_labels:
            state = variant_state[label]
            split_contract = dict(state["split_contract"])
            expected_count = expected_rebalance_count(frame=test_df, contract=split_contract)
            split_integrity = evaluate_overlap_integrity(
                train_df=train_df,
                validation_df=validation_df,
                test_df=test_df,
                evaluation_step_bars=split_contract_realization_step_bars(split_contract),
                prediction_count=int(len(test_df)),
                rebalance_count=expected_count,
                split_realization_contract=split_contract,
            )
            contamination_total = split_boundary_contamination_total(
                counts=dict(split_integrity.get("split_boundary_contamination_counts") or {})
            )
            if not bool(split_integrity.get("passed")):
                split_skipped_window_count += 1
                state["windows"].append(
                    _window_zero_payload(
                        train_end=train_end,
                        validation_end=validation_end,
                        test_df=test_df,
                        split_integrity=split_integrity,
                        split_boundary_contamination=contamination_total,
                    )
                )
                continue
            if scored is None:
                scored = {
                    "test": _fast_score_test_frame(
                        train_df=train_df,
                        test_df=test_df,
                        daily_ic_by_factor=daily_ic_by_factor,
                    )
                }
                scored_window_count += 1
            metrics = backtest_cross_sectional(
                frame=scored["test"].copy(),
                constraints=dict(state["constraints"]),
                split_realization_contract=split_contract,
                execution_cost_model=base_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=dict(state["capacity_limits"]),
                include_periods=True,
            )
            stress_metrics = backtest_cross_sectional(
                frame=scored["test"].copy(),
                constraints=dict(state["constraints"]),
                split_realization_contract=split_contract,
                execution_cost_model=stress_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=dict(state["capacity_limits"]),
                include_periods=True,
            )
            test_start_utc = pd.to_datetime(scored["test"]["timestamp_ms"].min(), unit="ms", utc=True).isoformat().replace("+00:00", "Z")
            test_end_utc = pd.to_datetime(scored["test"]["timestamp_ms"].max(), unit="ms", utc=True).isoformat().replace("+00:00", "Z")
            state["windows"].append(
                {
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    "test_start_utc": test_start_utc,
                    "test_end_utc": test_end_utc,
                    "contract_passed": True,
                    "split_boundary_contamination_total": int(contamination_total),
                    "split_boundary_contamination_counts": dict(split_integrity.get("split_boundary_contamination_counts") or {}),
                    "backtest_realization_mismatch": dict(split_integrity.get("backtest_horizon_mismatch") or {}),
                    "sharpe": float(metrics["sharpe"]),
                    "net_return": float(metrics["net_return"]),
                    "max_drawdown": float(metrics["max_drawdown"]),
                    "turnover": float(metrics["turnover"]),
                    "trade_count": int(metrics["trade_count"]),
                    "rebalance_count": int(metrics["rebalance_count"]),
                    "max_trade_participation_rate": float(metrics["max_trade_participation_rate"]),
                    "max_inventory_participation_rate": float(metrics["max_inventory_participation_rate"]),
                    "capacity_breach_count": int(metrics["capacity_breach_count"]),
                    "stress_sharpe": float(stress_metrics["sharpe"]),
                    "stress_net_return": float(stress_metrics["net_return"]),
                    "stress_max_drawdown": float(stress_metrics["max_drawdown"]),
                    "stress_max_trade_participation_rate": float(stress_metrics["max_trade_participation_rate"]),
                    "stress_max_inventory_participation_rate": float(stress_metrics["max_inventory_participation_rate"]),
                    "stress_capacity_breach_count": int(stress_metrics["capacity_breach_count"]),
                    "periods": [dict(item) for item in list(metrics.get("periods") or [])],
                    "stress_periods": [dict(item) for item in list(stress_metrics.get("periods") or [])],
                }
            )
        current_anchor = current_anchor + timedelta(days=30)

    multiphase_scored_window_count = 0
    multiphase_split_skipped_window_count = 0
    for phase in MULTIPHASE_PHASES:
        phase_data, phase_audit = _phase_frame(frame, phase_offset_days=phase)
        for label in multiphase_labels:
            variant_state[label]["phase_audits"].append(dict(phase_audit))
        if phase_data.empty:
            continue
        phase_time_index = pd.to_datetime(phase_data["timestamp_ms"], unit="ms", utc=True)
        current_anchor = phase_time_index.min() + timedelta(days=120)
        final_anchor = phase_time_index.max() - timedelta(days=30)
        while current_anchor <= final_anchor:
            train_end = current_anchor - timedelta(days=30)
            validation_end = current_anchor
            test_end = current_anchor + timedelta(days=30)
            train_df, validation_df, test_df = walk_forward_split_with_purge(
                frame=phase_data,
                time_col="timestamp_ms",
                train_end=train_end,
                validation_end=validation_end,
                test_end=test_end,
                split_realization_contract=base_split_contract,
            )
            if train_df.empty or validation_df.empty or test_df.empty:
                current_anchor = current_anchor + timedelta(days=30)
                continue
            scored: dict[str, Any] | None = None
            for label in multiphase_labels:
                state = variant_state[label]
                split_contract = dict(state["split_contract"])
                expected_count = expected_rebalance_count(frame=test_df, contract=split_contract)
                split_integrity = evaluate_overlap_integrity(
                    train_df=train_df,
                    validation_df=validation_df,
                    test_df=test_df,
                    evaluation_step_bars=split_contract_realization_step_bars(split_contract),
                    prediction_count=int(len(test_df)),
                    rebalance_count=expected_count,
                    split_realization_contract=split_contract,
                )
                contamination_total = split_boundary_contamination_total(
                    counts=dict(split_integrity.get("split_boundary_contamination_counts") or {})
                )
                if not bool(split_integrity.get("passed")):
                    multiphase_split_skipped_window_count += 1
                    state["phase_windows"][int(phase)].append(
                        _window_zero_payload(
                            train_end=train_end,
                            validation_end=validation_end,
                            test_df=test_df,
                            split_integrity=split_integrity,
                            split_boundary_contamination=contamination_total,
                        )
                    )
                    continue
                if scored is None:
                    scored = {
                        "test": _fast_score_test_frame(
                            train_df=train_df,
                            test_df=test_df,
                            daily_ic_by_factor=daily_ic_by_factor,
                        )
                    }
                    multiphase_scored_window_count += 1
                metrics = backtest_cross_sectional(
                    frame=scored["test"].copy(),
                    constraints=dict(state["constraints"]),
                    split_realization_contract=split_contract,
                    execution_cost_model=base_execution_cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=dict(state["capacity_limits"]),
                    include_periods=True,
                )
                stress_metrics = backtest_cross_sectional(
                    frame=scored["test"].copy(),
                    constraints=dict(state["constraints"]),
                    split_realization_contract=split_contract,
                    execution_cost_model=stress_execution_cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=dict(state["capacity_limits"]),
                    include_periods=True,
                )
                test_start_utc = pd.to_datetime(scored["test"]["timestamp_ms"].min(), unit="ms", utc=True).isoformat().replace("+00:00", "Z")
                test_end_utc = pd.to_datetime(scored["test"]["timestamp_ms"].max(), unit="ms", utc=True).isoformat().replace("+00:00", "Z")
                state["phase_windows"][int(phase)].append(
                    {
                        "phase_offset_days": int(phase),
                        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                        "test_start_utc": test_start_utc,
                        "test_end_utc": test_end_utc,
                        "contract_passed": True,
                        "split_boundary_contamination_total": int(contamination_total),
                        "split_boundary_contamination_counts": dict(split_integrity.get("split_boundary_contamination_counts") or {}),
                        "backtest_realization_mismatch": dict(split_integrity.get("backtest_horizon_mismatch") or {}),
                        "sharpe": float(metrics["sharpe"]),
                        "net_return": float(metrics["net_return"]),
                        "max_drawdown": float(metrics["max_drawdown"]),
                        "turnover": float(metrics["turnover"]),
                        "trade_count": int(metrics["trade_count"]),
                        "rebalance_count": int(metrics["rebalance_count"]),
                        "max_trade_participation_rate": float(metrics["max_trade_participation_rate"]),
                        "max_inventory_participation_rate": float(metrics["max_inventory_participation_rate"]),
                        "capacity_breach_count": int(metrics["capacity_breach_count"]),
                        "stress_sharpe": float(stress_metrics["sharpe"]),
                        "stress_net_return": float(stress_metrics["net_return"]),
                        "stress_max_drawdown": float(stress_metrics["max_drawdown"]),
                        "stress_max_trade_participation_rate": float(stress_metrics["max_trade_participation_rate"]),
                        "stress_max_inventory_participation_rate": float(stress_metrics["max_inventory_participation_rate"]),
                        "stress_capacity_breach_count": int(stress_metrics["capacity_breach_count"]),
                        "periods": [dict(item) for item in list(metrics.get("periods") or [])],
                        "stress_periods": [dict(item) for item in list(stress_metrics.get("periods") or [])],
                    }
                )
            current_anchor = current_anchor + timedelta(days=30)

    output_root = _resolve(args.output_root) / str(args.run_label)
    output_root.mkdir(parents=True, exist_ok=True)
    variant_summaries: list[dict[str, Any]] = []
    period_frames: list[pd.DataFrame] = []
    periods_by_label: dict[str, pd.DataFrame] = {}
    stress_periods_by_label: dict[str, pd.DataFrame] = {}
    windows_by_label: dict[str, list[dict[str, Any]]] = {}
    variant_for_summary_by_label: dict[str, dict[str, Any]] = {}

    for label, state in variant_state.items():
        variant = dict(state["variant"])
        target_engine = str(variant.get("target_engine") or "single_phase")
        if target_engine == "multiphase_equal_sleeve":
            sleeve_frames: list[pd.DataFrame] = []
            stress_sleeve_frames: list[pd.DataFrame] = []
            for phase in MULTIPHASE_PHASES:
                phase_windows = list(state["phase_windows"].get(int(phase), []))
                phase_periods = _periods_from_window_metrics(label=label, windows=phase_windows)
                phase_stress_periods = _periods_from_window_metrics(label=label, windows=phase_windows, stress=True)
                if not phase_periods.empty:
                    sleeve_frames.append(
                        _scale_sleeve_periods(
                            phase_periods,
                            phase=int(phase),
                            sleeve_weight=MULTIPHASE_SLEEVE_WEIGHT,
                        )
                    )
                if not phase_stress_periods.empty:
                    stress_sleeve_frames.append(
                        _scale_sleeve_periods(
                            phase_stress_periods,
                            phase=int(phase),
                            sleeve_weight=MULTIPHASE_SLEEVE_WEIGHT,
                        )
                    )
            inventory_cap = float(
                variant.get(
                    "inventory_participation_cap",
                    execution_capacity_limits(validation_contract)["max_inventory_participation_rate_max"],
                )
            )
            periods = _aggregate_multiphase_periods(
                label=label,
                sleeve_periods=pd.concat(sleeve_frames, ignore_index=True) if sleeve_frames else pd.DataFrame(),
                trade_participation_cap=float(variant["trade_participation_cap"]),
                inventory_participation_cap=inventory_cap,
            )
            stress_periods = _aggregate_multiphase_periods(
                label=label,
                sleeve_periods=pd.concat(stress_sleeve_frames, ignore_index=True) if stress_sleeve_frames else pd.DataFrame(),
                trade_participation_cap=float(variant["trade_participation_cap"]),
                inventory_participation_cap=inventory_cap,
            )
            multiphase_periods_per_year = overlap_adjusted_periods_per_year(
                bar_interval_ms=int(state["split_contract"]["bar_interval_ms"]),
                target_horizon_bars=int(state["split_contract"]["target_horizon_bars"]),
                realization_step_bars=int(state["split_contract"]["realization_step_bars"]),
            )
            summary_windows = _summary_windows_from_periods(
                periods,
                periods_per_year_value=multiphase_periods_per_year,
            )
            variant["summary_periods_per_year"] = multiphase_periods_per_year
            variant["phase_count"] = len(MULTIPHASE_PHASES)
            variant["sleeve_weight"] = MULTIPHASE_SLEEVE_WEIGHT
            windows = summary_windows
        else:
            periods = _periods_from_window_metrics(label=label, windows=list(state["windows"]))
            stress_periods = _periods_from_window_metrics(label=label, windows=list(state["windows"]), stress=True)
            windows = list(state["windows"])
            variant["phase_count"] = 1
            variant["sleeve_weight"] = 1.0
        periods_by_label[label] = periods
        stress_periods_by_label[label] = stress_periods
        windows_by_label[label] = windows
        variant_for_summary_by_label[label] = variant

    baseline_periods = periods_by_label.get(CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL, pd.DataFrame())
    baseline_state = variant_state[CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL]
    baseline_split_contract = dict(baseline_state["split_contract"])
    baseline_periods_per_year = overlap_adjusted_periods_per_year(
        bar_interval_ms=int(baseline_split_contract["bar_interval_ms"]),
        target_horizon_bars=int(baseline_split_contract["target_horizon_bars"]),
        realization_step_bars=int(baseline_split_contract["realization_step_bars"]),
    )
    baseline_perf = overlap_adjusted_performance_summary(
        baseline_periods["net_period_return"] if not baseline_periods.empty else pd.Series(dtype="float64"),
        bar_interval_ms=int(baseline_split_contract["bar_interval_ms"]),
        target_horizon_bars=int(baseline_split_contract["target_horizon_bars"]),
        realization_step_bars=int(baseline_split_contract["realization_step_bars"]),
    )

    for label, state in variant_state.items():
        periods = periods_by_label[label]
        stress_periods = stress_periods_by_label[label]
        summary = _variant_summary(
            variant=dict(variant_for_summary_by_label[label]),
            windows=list(windows_by_label[label]),
            periods=periods,
            stress_periods=stress_periods,
            split_contract=dict(state["split_contract"]),
            validation_contract=validation_contract,
            baseline_perf=baseline_perf,
        )
        variant_summaries.append(summary)
        if not periods.empty:
            frame_for_csv = periods.copy()
            frame_for_csv["variant_label"] = label
            frame_for_csv["target_engine"] = str(variant_for_summary_by_label[label].get("target_engine") or "single_phase")
            period_frames.append(frame_for_csv)

    summary_csv = output_root / "variant_summary.csv"
    periods_csv = output_root / "period_returns_long.csv"
    pd.DataFrame.from_records(variant_summaries).to_csv(summary_csv, index=False)
    if period_frames:
        pd.concat(period_frames, ignore_index=True).to_csv(periods_csv, index=False)
    else:
        pd.DataFrame().to_csv(periods_csv, index=False)

    payload = {
        "status": "computed",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "score_parent_label": str(args.baseline_label),
        "effective_research_baseline_label": str(args.effective_baseline_label),
        "this_run_construction_status": "includes_current_multiphase_baseline_and_single_phase_comparators",
        "current_effective_baseline_variant_label": CURRENT_EFFECTIVE_BASELINE_VARIANT_LABEL,
        "current_baseline_construction": dict(CURRENT_BASELINE_CONSTRUCTION),
        "baseline_label": str(args.baseline_label),
        "baseline_experiment_id": str(args.baseline_experiment_id),
        "diagnostic_contract": "h10d_portfolio_construction_experiment.v1",
        "score_reused_across_variants": True,
        "formal_promotion_use": "not_a_promotion_gate",
        "sharpe_metric_convention": {
            "version": SHARPE_METRIC_CONVENTION_VERSION,
            "headline_field": "full_oos_h10d_equivalent_sharpe",
            "compatibility_alias": "full_oos_period_sharpe",
            "rule": "annualize overlapping h10d booking returns by max(target_horizon_bars, realization_step_bars), not by observed daily aggregate count",
        },
        "inputs": {
            "experiment_root": portable_path(experiment_root, repo_root=ROOT),
            "feature_manifest": portable_path(_resolve(Path(str(spec["feature_manifest_path"]))), repo_root=ROOT),
            "features_path": portable_path(feature_path, repo_root=ROOT),
            "validation_contract": portable_path(_resolve(args.validation_contract), repo_root=ROOT),
        },
        "base_constraints": base_constraints,
        "base_split_realization_contract": base_split_contract,
        "base_capacity_limits": base_capacity_limits,
        "execution_context": {
            "reference_capital_usd": float(reference_capital_usd),
            "base_execution_cost_model": base_execution_cost_model,
            "stress_execution_cost_model": stress_execution_cost_model,
        },
        "diagnostics": {
            "execution_eligible_row_count": int(len(frame)),
            "execution_eligible_subject_count": int(frame["subject"].nunique()),
            "single_phase_scored_window_count": int(scored_window_count),
            "single_phase_split_skipped_window_count": int(split_skipped_window_count),
            "multiphase_scored_window_count": int(multiphase_scored_window_count),
            "multiphase_split_skipped_window_count": int(multiphase_split_skipped_window_count),
            "baseline_recomputed_cumulative_net_return": float(baseline_perf["net_return"]),
            "baseline_recomputed_h10d_equivalent_sharpe": float(baseline_perf["sharpe"]),
            "baseline_recomputed_period_sharpe": float(baseline_perf["sharpe"]),
            "baseline_recomputed_max_drawdown": float(baseline_perf["max_drawdown"]),
            "baseline_periods_per_year": float(baseline_periods_per_year),
        },
        "variant_summaries": variant_summaries,
        "artifacts": {
            "summary_json": portable_path(output_root / "summary.json", repo_root=ROOT),
            "summary_md": portable_path(output_root / "summary.md", repo_root=ROOT),
            "variant_summary_csv": portable_path(summary_csv, repo_root=ROOT),
            "period_returns_long_csv": portable_path(periods_csv, repo_root=ROOT),
        },
        "interpretation_boundary": (
            "Portfolio-construction diagnostic only. This run includes true 10-phase equal-sleeve variants "
            "for the current research baseline and historical single-phase comparators. Participation-cap "
            "rows change gate thresholds only; they do not impose a trade sizing clamp. No score, manifest, "
            "or live configuration is mutated."
        ),
    }
    write_json(output_root / "summary.json", payload)
    _write_markdown(output_root / "summary.md", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
