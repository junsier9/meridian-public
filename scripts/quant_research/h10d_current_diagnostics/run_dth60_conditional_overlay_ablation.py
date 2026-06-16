from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_v5_rw_baseline_rebalance_phase_sensitivity as v5_phase  # noqa: E402
import run_multiphase_factor_drawdown_ablation as factor_ablation  # noqa: E402
import run_portfolio_construction_experiment as portfolio_diag  # noqa: E402

from enhengclaw.quant_research.execution_backtest import backtest_cross_sectional, filter_cross_sectional_execution_frame  # noqa: E402
from enhengclaw.quant_research.horizon_metrics import SHARPE_METRIC_CONVENTION_VERSION  # noqa: E402
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, _apply_universe_filter, _experiment_directory_name, _resolved_execution_cost_models  # noqa: E402
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import resolve_split_realization_contract  # noqa: E402
from enhengclaw.quant_research.validation_contract import execution_capacity_limits, validation_contract_reference_capital_usd  # noqa: E402


BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d"
EFFECTIVE_BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve"
BASELINE_EXPERIMENT_ID = "2026-04-29-xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
H10D_VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
TARGET_FACTOR = "distance_to_high_60"
BASELINE_VARIANT_LABEL = "baseline_no_factor_overlay"
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-06-03"
    / "v5_rw_dth60_conditional_overlay_ablation_2024_10_31_2024_11_25"
)


OVERLAY_VARIANTS: list[dict[str, Any]] = [
    {
        "label": BASELINE_VARIANT_LABEL,
        "kind": "baseline",
        "condition": "none",
        "target_multiplier": 1.0,
        "description": "No score-layer factor overlay.",
    },
    {
        "label": "dth60_static_half",
        "kind": "static_downweight",
        "condition": "all_rows",
        "target_multiplier": 0.5,
        "description": "Always cut distance_to_high_60 contribution by 50%.",
    },
    {
        "label": "dth60_static_zero",
        "kind": "static_downweight",
        "condition": "all_rows",
        "target_multiplier": 0.0,
        "description": "Always remove distance_to_high_60 contribution.",
    },
    {
        "label": "dth60_shock_cluster_q75_half",
        "kind": "macro_regime_overlay",
        "condition": "shock_cluster_q75",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% when shock_co_occurrence_index or co_jump_count_3d is above train q75.",
    },
    {
        "label": "dth60_shock_cluster_q75_zero",
        "kind": "macro_regime_overlay",
        "condition": "shock_cluster_q75",
        "target_multiplier": 0.0,
        "description": "Remove the factor when shock_co_occurrence_index or co_jump_count_3d is above train q75.",
    },
    {
        "label": "dth60_shock_cluster_q90_half",
        "kind": "macro_regime_overlay",
        "condition": "shock_cluster_q90",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% when shock_co_occurrence_index or co_jump_count_3d is above train q90.",
    },
    {
        "label": "dth60_shock_cluster_q90_zero",
        "kind": "macro_regime_overlay",
        "condition": "shock_cluster_q90",
        "target_multiplier": 0.0,
        "description": "Remove the factor when shock_co_occurrence_index or co_jump_count_3d is above train q90.",
    },
    {
        "label": "dth60_high_vol_q75_half",
        "kind": "macro_regime_overlay",
        "condition": "high_vol_q75",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% when cross-sectional median realized/intraday vol is above train q75.",
    },
    {
        "label": "dth60_high_vol_q75_zero",
        "kind": "macro_regime_overlay",
        "condition": "high_vol_q75",
        "target_multiplier": 0.0,
        "description": "Remove the factor when cross-sectional median realized/intraday vol is above train q75.",
    },
    {
        "label": "dth60_high_vol_q90_half",
        "kind": "macro_regime_overlay",
        "condition": "high_vol_q90",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% when cross-sectional median realized/intraday vol is above train q90.",
    },
    {
        "label": "dth60_high_vol_q90_zero",
        "kind": "macro_regime_overlay",
        "condition": "high_vol_q90",
        "target_multiplier": 0.0,
        "description": "Remove the factor when cross-sectional median realized/intraday vol is above train q90.",
    },
    {
        "label": "dth60_near_high_crowded_half",
        "kind": "row_level_overlay",
        "condition": "near_high_top_trader_top25",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% only for coins near 60d highs and top-trader-long crowded.",
    },
    {
        "label": "dth60_near_high_crowded_zero",
        "kind": "row_level_overlay",
        "condition": "near_high_top_trader_top25",
        "target_multiplier": 0.0,
        "description": "Remove the factor only for coins near 60d highs and top-trader-long crowded.",
    },
    {
        "label": "dth60_near_high_quality_funding_half",
        "kind": "row_level_overlay",
        "condition": "near_high_quality_funding_top25",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% for near-high coins with high quality_funding_oi.",
    },
    {
        "label": "dth60_hybrid_shock_or_crowded_half",
        "kind": "hybrid_overlay",
        "condition": "shock_cluster_q75_or_near_high_top_trader_top25",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% when either macro shock clustering or near-high crowding fires.",
    },
    {
        "label": "dth60_hybrid_shock_or_crowded_zero",
        "kind": "hybrid_overlay",
        "condition": "shock_cluster_q75_or_near_high_top_trader_top25",
        "target_multiplier": 0.0,
        "description": "Remove the factor when either macro shock clustering or near-high crowding fires.",
    },
    {
        "label": "dth60_hybrid_shock_q90_or_crowded_half",
        "kind": "hybrid_overlay",
        "condition": "shock_cluster_q90_or_near_high_top_trader_top25",
        "target_multiplier": 0.5,
        "description": "Cut the factor by 50% when q90 macro shock clustering or near-high crowding fires.",
    },
    {
        "label": "dth60_hybrid_shock_q90_or_crowded_zero",
        "kind": "hybrid_overlay",
        "condition": "shock_cluster_q90_or_near_high_top_trader_top25",
        "target_multiplier": 0.0,
        "description": "Remove the factor when q90 macro shock clustering or near-high crowding fires.",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run score-layer conditional downweight overlays for distance_to_high_60 "
            "under the current v5_rw 10-sleeve research-baseline engine."
        )
    )
    parser.add_argument("--episode-start", default="2024-10-31")
    parser.add_argument("--episode-end", default="2024-11-25")
    parser.add_argument("--baseline-experiment-id", default=BASELINE_EXPERIMENT_ID)
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--validation-contract", type=Path, default=H10D_VALIDATION_CONTRACT_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    return factor_ablation.json_safe(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    factor_ablation.write_json(path, payload)


def _safe_quantile(series: pd.Series, quantile: float, default: float) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if cleaned.empty:
        return float(default)
    value = float(cleaned.quantile(float(quantile)))
    return value if math.isfinite(value) else float(default)


def _timestamp_first(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns or frame.empty:
        return pd.Series(dtype="float64")
    return (
        pd.to_numeric(frame[column], errors="coerce")
        .groupby(pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("int64"))
        .first()
        .sort_index()
        .astype("float64")
    )


def _timestamp_median(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns or frame.empty:
        return pd.Series(dtype="float64")
    return (
        pd.to_numeric(frame[column], errors="coerce")
        .groupby(pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("int64"))
        .median()
        .sort_index()
        .astype("float64")
    )


def overlay_thresholds(train_df: pd.DataFrame) -> dict[str, float]:
    shock = _timestamp_first(train_df, "shock_co_occurrence_index")
    co_jump = _timestamp_first(train_df, "co_jump_count_3d")
    realized_vol = _timestamp_median(train_df, "realized_volatility_5")
    intraday_vol = _timestamp_median(train_df, "intraday_realized_vol_4h_to_1d_smooth_60")
    dispersion = _timestamp_first(train_df, "dispersion_of_returns")
    return {
        "shock_co_occurrence_index_q75": _safe_quantile(shock, 0.75, 0.05),
        "shock_co_occurrence_index_q90": _safe_quantile(shock, 0.90, 0.10),
        "co_jump_count_3d_q75": _safe_quantile(co_jump, 0.75, 10.0),
        "co_jump_count_3d_q90": _safe_quantile(co_jump, 0.90, 20.0),
        "realized_volatility_5_median_q75": _safe_quantile(realized_vol, 0.75, 0.06),
        "realized_volatility_5_median_q90": _safe_quantile(realized_vol, 0.90, 0.09),
        "intraday_realized_vol_4h_to_1d_smooth_60_median_q75": _safe_quantile(intraday_vol, 0.75, 0.02),
        "intraday_realized_vol_4h_to_1d_smooth_60_median_q90": _safe_quantile(intraday_vol, 0.90, 0.025),
        "dispersion_of_returns_q25": _safe_quantile(dispersion, 0.25, 0.03),
    }


def _broadcast_timestamp_condition(frame: pd.DataFrame, condition_by_timestamp: pd.Series) -> pd.Series:
    timestamps = pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("int64")
    mapped = timestamps.map(condition_by_timestamp.astype(bool).to_dict()).fillna(False)
    return mapped.astype(bool)


def _rank_pct(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.5, index=frame.index, dtype="float64")
    packed = pd.DataFrame(
        {
            "timestamp_ms": pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("int64").values,
            "value": pd.to_numeric(frame[column], errors="coerce").values,
        },
        index=frame.index,
    )
    return packed.groupby("timestamp_ms")["value"].rank(pct=True).fillna(0.5).astype("float64")


def overlay_trigger_mask(
    frame: pd.DataFrame,
    *,
    condition: str,
    thresholds: dict[str, float],
) -> pd.Series:
    if condition == "none":
        return pd.Series(False, index=frame.index, dtype="bool")
    if condition == "all_rows":
        return pd.Series(True, index=frame.index, dtype="bool")

    shock = _timestamp_first(frame, "shock_co_occurrence_index")
    co_jump = _timestamp_first(frame, "co_jump_count_3d")
    shock_cluster_ts = shock.ge(float(thresholds["shock_co_occurrence_index_q75"])) | co_jump.ge(
        float(thresholds["co_jump_count_3d_q75"])
    )
    shock_cluster = _broadcast_timestamp_condition(frame, shock_cluster_ts)
    shock_cluster_q90_ts = shock.ge(float(thresholds["shock_co_occurrence_index_q90"])) | co_jump.ge(
        float(thresholds["co_jump_count_3d_q90"])
    )
    shock_cluster_q90 = _broadcast_timestamp_condition(frame, shock_cluster_q90_ts)

    realized_vol = _timestamp_median(frame, "realized_volatility_5")
    intraday_vol = _timestamp_median(frame, "intraday_realized_vol_4h_to_1d_smooth_60")
    high_vol_ts = realized_vol.ge(float(thresholds["realized_volatility_5_median_q75"])) | intraday_vol.ge(
        float(thresholds["intraday_realized_vol_4h_to_1d_smooth_60_median_q75"])
    )
    high_vol = _broadcast_timestamp_condition(frame, high_vol_ts)
    high_vol_q90_ts = realized_vol.ge(float(thresholds["realized_volatility_5_median_q90"])) | intraday_vol.ge(
        float(thresholds["intraday_realized_vol_4h_to_1d_smooth_60_median_q90"])
    )
    high_vol_q90 = _broadcast_timestamp_condition(frame, high_vol_q90_ts)

    near_high = _rank_pct(frame, TARGET_FACTOR).ge(0.75)
    crowded = _rank_pct(frame, "coinglass_top_trader_long_pct_smooth_5").ge(0.75)
    quality_funding = _rank_pct(frame, "quality_funding_oi").ge(0.75)
    near_high_crowded = near_high & crowded
    near_high_quality_funding = near_high & quality_funding

    if condition == "shock_cluster_q75":
        return shock_cluster
    if condition == "shock_cluster_q90":
        return shock_cluster_q90
    if condition == "high_vol_q75":
        return high_vol
    if condition == "high_vol_q90":
        return high_vol_q90
    if condition == "near_high_top_trader_top25":
        return near_high_crowded
    if condition == "near_high_quality_funding_top25":
        return near_high_quality_funding
    if condition == "shock_cluster_q75_or_near_high_top_trader_top25":
        return shock_cluster | near_high_crowded
    if condition == "shock_cluster_q90_or_near_high_top_trader_top25":
        return shock_cluster_q90 | near_high_crowded
    raise ValueError(f"unknown overlay condition: {condition}")


def score_frame_with_dth60_overlay(
    frame: pd.DataFrame,
    *,
    factor_weights: dict[str, float],
    variant: dict[str, Any],
    thresholds: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    scored = frame.copy()
    timestamps = scored["timestamp_ms"]
    trigger = overlay_trigger_mask(scored, condition=str(variant["condition"]), thresholds=thresholds)
    row_multiplier = pd.Series(1.0, index=scored.index, dtype="float64")
    row_multiplier.loc[trigger] = float(variant["target_multiplier"])

    raw_score = pd.Series(0.0, index=scored.index, dtype="float64")
    for column, weight in factor_weights.items():
        if column not in scored.columns:
            continue
        values = pd.to_numeric(scored[column], errors="coerce")
        if not values.notna().any():
            continue
        zscore = v5_phase.lab._timestamp_cross_section_zscore(values, timestamps)
        if column == TARGET_FACTOR:
            raw_score = raw_score + float(weight) * zscore * row_multiplier
        else:
            raw_score = raw_score + float(weight) * zscore
    centered_rank = v5_phase.lab._timestamp_cross_section_percentile_rank(raw_score, timestamps) - 0.5
    scored["score"] = np.tanh(centered_rank * 1.80).astype("float64")
    scored["dth60_overlay_triggered"] = trigger.astype(int)
    scored["dth60_overlay_multiplier"] = row_multiplier.astype("float64")

    timestamp_trigger = (
        pd.DataFrame(
            {
                "timestamp_ms": pd.to_numeric(scored["timestamp_ms"], errors="coerce").astype("int64"),
                "trigger": trigger.astype(int),
            }
        )
        .groupby("timestamp_ms")["trigger"]
        .max()
    )
    return scored, {
        "overlay_test_row_count": int(len(scored)),
        "overlay_triggered_row_count": int(trigger.sum()),
        "overlay_triggered_row_fraction": float(trigger.mean()) if len(trigger) else 0.0,
        "overlay_test_timestamp_count": int(timestamp_trigger.shape[0]),
        "overlay_triggered_timestamp_count": int((timestamp_trigger > 0).sum()),
        "overlay_triggered_timestamp_fraction": float((timestamp_trigger > 0).mean())
        if timestamp_trigger.shape[0]
        else 0.0,
        "overlay_average_factor_multiplier": float(row_multiplier.mean()) if len(row_multiplier) else 1.0,
        "overlay_target_multiplier": float(variant["target_multiplier"]),
    }


def full_metrics(periods: pd.DataFrame, *, split_contract: dict[str, Any]) -> dict[str, Any]:
    out = factor_ablation.full_oos_metrics(periods, split_contract=split_contract)
    if periods.empty:
        out.update(
            {
                "loss_period_fraction": 0.0,
                "mean_period_return": 0.0,
                "turnover_total": 0.0,
                "max_trade_participation_rate": 0.0,
                "max_inventory_participation_rate": 0.0,
                "capacity_breach_count": 0,
            }
        )
        return out
    out.update(
        {
            "loss_period_fraction": float((pd.to_numeric(periods["net_period_return"], errors="coerce") < 0.0).mean()),
            "mean_period_return": float(pd.to_numeric(periods["net_period_return"], errors="coerce").fillna(0.0).mean()),
            "turnover_total": float(pd.to_numeric(periods.get("turnover"), errors="coerce").fillna(0.0).sum()),
            "max_trade_participation_rate": float(
                pd.to_numeric(periods.get("trade_participation_rate"), errors="coerce").fillna(0.0).max()
            ),
            "max_inventory_participation_rate": float(
                pd.to_numeric(periods.get("inventory_participation_rate"), errors="coerce").fillna(0.0).max()
            ),
            "capacity_breach_count": int(pd.to_numeric(periods.get("capacity_breach_count"), errors="coerce").fillna(0).sum()),
        }
    )
    return out


def _sum_window_stat(window_rows: pd.DataFrame, label: str, column: str) -> float:
    if window_rows.empty or column not in window_rows.columns:
        return 0.0
    return float(pd.to_numeric(window_rows.loc[window_rows["label"].eq(label), column], errors="coerce").fillna(0.0).sum())


def build_summary(
    *,
    definitions: list[dict[str, Any]],
    periods_by_label: dict[str, pd.DataFrame],
    window_rows: pd.DataFrame,
    split_contract: dict[str, Any],
    episode_start: str,
    episode_end: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    by_label = {str(item["label"]): item for item in definitions}
    for label, definition in by_label.items():
        periods = periods_by_label.get(label, pd.DataFrame())
        primary = factor_ablation.window_metrics(
            periods,
            start_date=episode_start,
            end_date=episode_end,
            include_start=False,
        )
        inclusive = factor_ablation.window_metrics(
            periods,
            start_date=episode_start,
            end_date=episode_end,
            include_start=True,
        )
        full = full_metrics(periods, split_contract=split_contract)
        row_count = _sum_window_stat(window_rows, label, "overlay_test_row_count")
        trigger_count = _sum_window_stat(window_rows, label, "overlay_triggered_row_count")
        timestamp_count = _sum_window_stat(window_rows, label, "overlay_test_timestamp_count")
        trigger_timestamp_count = _sum_window_stat(window_rows, label, "overlay_triggered_timestamp_count")
        rows.append(
            {
                "label": label,
                "kind": str(definition["kind"]),
                "condition": str(definition["condition"]),
                "target_multiplier": float(definition["target_multiplier"]),
                "description": str(definition.get("description") or ""),
                "primary_period_count": int(primary["period_count"]),
                "primary_compounded_return": float(primary["compounded_return"]),
                "primary_max_drawdown": float(primary["max_drawdown"]),
                "primary_loss_period_fraction": float(primary["loss_period_fraction"]),
                "primary_worst_period_return": float(primary["worst_period_return"]),
                "primary_worst_period_date_utc": primary["worst_period_date_utc"],
                "primary_turnover_total": float(primary["turnover_total"]),
                "inclusive_compounded_return": float(inclusive["compounded_return"]),
                "inclusive_max_drawdown": float(inclusive["max_drawdown"]),
                "full_oos_period_count": int(full["period_count"]),
                "full_oos_overlap_adjusted_periods_per_year": float(full["overlap_adjusted_periods_per_year"]),
                "full_oos_independent_period_bars": int(full["independent_period_bars"]),
                "full_oos_observed_frequency_periods_per_year_deprecated": int(full["observed_frequency_periods_per_year_deprecated"]),
                "full_oos_cumulative_return": float(full["cumulative_return"]),
                "full_oos_h10d_equivalent_sharpe": float(full["h10d_equivalent_sharpe"]),
                "full_oos_observed_frequency_sharpe_deprecated": float(full["observed_frequency_sharpe_deprecated"]),
                "full_oos_max_drawdown": float(full["max_drawdown"]),
                "full_oos_loss_period_fraction": float(full["loss_period_fraction"]),
                "full_oos_mean_period_return": float(full["mean_period_return"]),
                "full_oos_turnover_total": float(full["turnover_total"]),
                "full_oos_max_trade_participation_rate": float(full["max_trade_participation_rate"]),
                "full_oos_max_inventory_participation_rate": float(full["max_inventory_participation_rate"]),
                "full_oos_capacity_breach_count": int(full["capacity_breach_count"]),
                "overlay_test_row_count": int(row_count),
                "overlay_triggered_row_count": int(trigger_count),
                "overlay_triggered_row_fraction": float(trigger_count / row_count) if row_count > 0 else 0.0,
                "overlay_test_timestamp_count": int(timestamp_count),
                "overlay_triggered_timestamp_count": int(trigger_timestamp_count),
                "overlay_triggered_timestamp_fraction": float(trigger_timestamp_count / timestamp_count)
                if timestamp_count > 0
                else 0.0,
            }
        )
    summary = pd.DataFrame(rows)
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0]
    for metric in (
        "primary_compounded_return",
        "primary_max_drawdown",
        "inclusive_compounded_return",
        "inclusive_max_drawdown",
        "full_oos_cumulative_return",
        "full_oos_h10d_equivalent_sharpe",
        "full_oos_max_drawdown",
        "full_oos_turnover_total",
        "full_oos_max_trade_participation_rate",
        "full_oos_max_inventory_participation_rate",
    ):
        summary[f"delta_{metric}_vs_baseline"] = pd.to_numeric(summary[metric], errors="coerce") - float(baseline[metric])
    summary["episode_interpretation"] = np.select(
        [
            summary["delta_primary_compounded_return_vs_baseline"].gt(0.005),
            summary["delta_primary_compounded_return_vs_baseline"].lt(-0.005),
        ],
        ["overlay_relieves_episode_drawdown", "overlay_worsens_episode_drawdown"],
        default="near_neutral",
    )
    summary["full_oos_interpretation"] = np.select(
        [
            summary["delta_full_oos_cumulative_return_vs_baseline"].gt(0.01)
            & summary["delta_full_oos_h10d_equivalent_sharpe_vs_baseline"].gt(0.05),
            summary["delta_full_oos_cumulative_return_vs_baseline"].lt(-0.01)
            | summary["delta_full_oos_h10d_equivalent_sharpe_vs_baseline"].lt(-0.05),
        ],
        ["full_oos_improves", "full_oos_degrades"],
        default="full_oos_near_neutral",
    )
    return summary.sort_values(
        ["delta_primary_compounded_return_vs_baseline", "delta_full_oos_cumulative_return_vs_baseline"],
        ascending=[False, False],
    ).reset_index(drop=True)


def render_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0].to_dict()
    ranked = summary.sort_values("delta_primary_compounded_return_vs_baseline", ascending=False)
    full_ranked = summary.sort_values("delta_full_oos_cumulative_return_vs_baseline", ascending=False)
    lines = [
        "# Distance-to-High-60 Conditional Overlay Ablation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Effective research baseline: `{payload['effective_research_baseline']}`",
        f"- Target factor: `{TARGET_FACTOR}`",
        f"- Drawdown episode: `{payload['episode_start']}` to `{payload['episode_end']}`",
        "- Engine: `multiphase_equal_sleeve`, 10 sleeves, same score parent and base execution cost model.",
        "- Overlay layer: score-level factor contribution multiplier; non-target factors are unchanged.",
        "",
        "## Baseline",
        "",
        f"- episode return: `{baseline['primary_compounded_return']}`",
        f"- episode max DD: `{baseline['primary_max_drawdown']}`",
        f"- full OOS cumulative return: `{baseline['full_oos_cumulative_return']}`",
        f"- full OOS h10d-equivalent Sharpe: `{baseline['full_oos_h10d_equivalent_sharpe']}`",
        f"- deprecated observed-frequency Sharpe: `{baseline['full_oos_observed_frequency_sharpe_deprecated']}`",
        f"- full OOS max DD: `{baseline['full_oos_max_drawdown']}`",
        "",
        "## Episode Relief Ranking",
        "",
        "| variant | condition | multiplier | trigger rows | episode ret | delta ret | episode DD | full OOS ret | h10d-eq Sharpe | full OOS DD | interpretation |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in ranked.iterrows():
        lines.append(
            "| `{label}` | `{condition}` | {mult:.2f} | {trigger:.3f} | {ret:.6f} | {delta:.6f} | {dd:.6f} | {full_ret:.6f} | {sharpe:.6f} | {full_dd:.6f} | {interp} |".format(
                label=row["label"],
                condition=row["condition"],
                mult=float(row["target_multiplier"]),
                trigger=float(row["overlay_triggered_row_fraction"]),
                ret=float(row["primary_compounded_return"]),
                delta=float(row["delta_primary_compounded_return_vs_baseline"]),
                dd=float(row["primary_max_drawdown"]),
                full_ret=float(row["full_oos_cumulative_return"]),
                sharpe=float(row["full_oos_h10d_equivalent_sharpe"]),
                full_dd=float(row["full_oos_max_drawdown"]),
                interp=row["episode_interpretation"],
            )
        )
    lines.extend(
        [
            "",
            "## Full OOS Ranking",
            "",
            "| variant | full OOS ret | delta ret | h10d-eq Sharpe | delta Sharpe | max DD | delta DD | turnover | max trade part. | breaches |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in full_ranked.iterrows():
        lines.append(
            "| `{label}` | {full_ret:.6f} | {delta_ret:.6f} | {sharpe:.6f} | {delta_sharpe:.6f} | {dd:.6f} | {delta_dd:.6f} | {turnover:.6f} | {max_trade:.6f} | {breaches} |".format(
                label=row["label"],
                full_ret=float(row["full_oos_cumulative_return"]),
                delta_ret=float(row["delta_full_oos_cumulative_return_vs_baseline"]),
                sharpe=float(row["full_oos_h10d_equivalent_sharpe"]),
                delta_sharpe=float(row["delta_full_oos_h10d_equivalent_sharpe_vs_baseline"]),
                dd=float(row["full_oos_max_drawdown"]),
                delta_dd=float(row["delta_full_oos_max_drawdown_vs_baseline"]),
                turnover=float(row["full_oos_turnover_total"]),
                max_trade=float(row["full_oos_max_trade_participation_rate"]),
                breaches=int(row["full_oos_capacity_breach_count"]),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a score-layer overlay ablation. Thresholds are estimated inside each WFO train window, "
            "then applied to that window's test rows. It is research evidence only and does not modify live trading.",
            "",
            "Sharpe convention: headline Sharpe is overlap-adjusted h10d-equivalent Sharpe, annualized by "
            "`max(target_horizon_bars, realization_step_bars)`, not by the observed daily aggregate count. "
            "The observed-frequency Sharpe is deprecated and retained only for audit comparison.",
            "",
            "## Artifacts",
            "",
        ]
    )
    for key, value in sorted(dict(payload.get("artifacts") or {}).items()):
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    experiment_root = Path(args.artifacts_root).resolve() / "experiments" / _experiment_directory_name(
        str(args.baseline_experiment_id)
    )
    spec = dict(portfolio_diag.read_json(experiment_root / "experiment_spec.json"))
    feature_manifest = dict(portfolio_diag.read_json(portfolio_diag._resolve(Path(str(spec["feature_manifest_path"])))))
    feature_path = portfolio_diag._resolve(Path(str(feature_manifest["features_path"])))
    validation_contract = dict(portfolio_diag.read_json(portfolio_diag._resolve(args.validation_contract)))
    base_execution_cost_model, _ = _resolved_execution_cost_models()
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    capacity_limits = execution_capacity_limits(validation_contract)
    split_contract = resolve_split_realization_contract(
        contract=dict(spec["split_realization_contract"]),
        shape="cross_sectional",
    )
    constraints = dict(spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(spec.get("strategy_profile") or "")
    inventory_cap = float(capacity_limits["max_inventory_participation_rate_max"])
    trade_cap = float(capacity_limits["max_trade_participation_rate_max"])

    raw_frame = pd.read_csv(feature_path, low_memory=False)
    frame = _apply_universe_filter(raw_frame, universe_filter=spec.get("universe_filter"))
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if frame.empty:
        raise RuntimeError("no execution-eligible rows")
    feature_columns = list(spec.get("feature_columns") or [])
    missing_features = [column for column in feature_columns if column not in frame.columns]
    if missing_features:
        raise RuntimeError(f"missing feature columns: {missing_features}")
    active_factor_columns = factor_ablation.active_v5_factor_columns(feature_columns)
    if TARGET_FACTOR not in active_factor_columns:
        raise RuntimeError(f"{TARGET_FACTOR} not active in v5 factor map")
    daily_ic_by_factor = v5_phase.build_daily_ic_by_factor(frame, feature_columns=feature_columns)

    definitions = [dict(item) for item in OVERLAY_VARIANTS]
    phase_periods_by_label: dict[str, list[pd.DataFrame]] = {str(item["label"]): [] for item in definitions}
    weight_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    all_period_frames: list[pd.DataFrame] = []

    for phase in portfolio_diag.MULTIPHASE_PHASES:
        phase_data, phase_audit = portfolio_diag._phase_frame(frame, phase_offset_days=phase)
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
                split_realization_contract=split_contract,
            )
            current_anchor += timedelta(days=30)
            if train_df.empty or validation_df.empty or test_df.empty:
                continue

            train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
            weights = v5_phase.weights_for_train_end(
                daily_ic_by_factor=daily_ic_by_factor,
                train_end_ms=train_end_ms,
            )
            thresholds = overlay_thresholds(train_df)
            threshold_rows.append(
                {
                    "phase_offset_days": int(phase),
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    **thresholds,
                }
            )
            test_times = pd.to_datetime(test_df["timestamp_ms"], unit="ms", utc=True)
            for definition in definitions:
                label = str(definition["label"])
                scored_test, overlay_stats = score_frame_with_dth60_overlay(
                    test_df,
                    factor_weights=weights,
                    variant=definition,
                    thresholds=thresholds,
                )
                for factor, weight in sorted(weights.items()):
                    effective = float(weight)
                    if factor == TARGET_FACTOR:
                        effective = float(weight) * float(overlay_stats["overlay_average_factor_multiplier"])
                    weight_rows.append(
                        {
                            "label": label,
                            "kind": str(definition["kind"]),
                            "condition": str(definition["condition"]),
                            "phase_offset_days": int(phase),
                            "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                            "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                            "factor": factor,
                            "base_weight": float(weight),
                            "average_effective_weight": effective,
                            "target_factor": factor == TARGET_FACTOR,
                            "overlay_average_factor_multiplier": float(overlay_stats["overlay_average_factor_multiplier"])
                            if factor == TARGET_FACTOR
                            else 1.0,
                        }
                    )
                metrics = backtest_cross_sectional(
                    frame=scored_test,
                    constraints=constraints,
                    split_realization_contract=split_contract,
                    execution_cost_model=base_execution_cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=capacity_limits,
                    include_periods=True,
                )
                phase_periods = factor_ablation.period_frame_from_metrics(label=label, phase=phase, metrics=metrics)
                if not phase_periods.empty:
                    phase_periods_by_label[label].append(phase_periods)
                window_rows.append(
                    {
                        "label": label,
                        "kind": str(definition["kind"]),
                        "condition": str(definition["condition"]),
                        "target_multiplier": float(definition["target_multiplier"]),
                        "phase_offset_days": int(phase),
                        "phase_start_date_utc": phase_audit.get("start_date_utc"),
                        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                        "test_start_utc": test_times.min().isoformat().replace("+00:00", "Z"),
                        "test_end_utc": test_times.max().isoformat().replace("+00:00", "Z"),
                        "net_return": float(metrics.get("net_return", 0.0) or 0.0),
                        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
                        "turnover": float(metrics.get("turnover", 0.0) or 0.0),
                        "period_count": int(len(metrics.get("periods") or [])),
                        **overlay_stats,
                    }
                )

    periods_by_label: dict[str, pd.DataFrame] = {}
    for definition in definitions:
        label = str(definition["label"])
        periods = factor_ablation.aggregate_variant_periods(
            label=label,
            sleeve_periods=phase_periods_by_label[label],
            trade_participation_cap=trade_cap,
            inventory_participation_cap=inventory_cap,
        )
        periods_by_label[label] = periods
        if not periods.empty:
            all_period_frames.append(periods.assign(overlay_kind=str(definition["kind"])))

    window_rows_frame = pd.DataFrame(window_rows)
    summary = build_summary(
        definitions=definitions,
        periods_by_label=periods_by_label,
        window_rows=window_rows_frame,
        split_contract=split_contract,
        episode_start=str(args.episode_start),
        episode_end=str(args.episode_end),
    )

    summary_csv = output_root / "overlay_summary.csv"
    period_returns_csv = output_root / "overlay_period_returns_long.csv"
    weights_csv = output_root / "overlay_factor_weights_long.csv"
    windows_csv = output_root / "overlay_windows.csv"
    thresholds_csv = output_root / "overlay_train_thresholds.csv"
    definitions_json = output_root / "overlay_definitions.json"
    summary.to_csv(summary_csv, index=False)
    pd.concat(all_period_frames, ignore_index=True).to_csv(period_returns_csv, index=False)
    pd.DataFrame(weight_rows).to_csv(weights_csv, index=False)
    window_rows_frame.to_csv(windows_csv, index=False)
    pd.DataFrame(threshold_rows).to_csv(thresholds_csv, index=False)
    write_json(definitions_json, {"definitions": definitions, "target_factor": TARGET_FACTOR})

    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0]
    payload = {
        "status": "computed",
        "generated_at_utc": utc_now_iso(),
        "score_parent_label": BASELINE_LABEL,
        "effective_research_baseline": EFFECTIVE_BASELINE_LABEL,
        "target_factor": TARGET_FACTOR,
        "baseline_variant_label": BASELINE_VARIANT_LABEL,
        "baseline_experiment_id": str(args.baseline_experiment_id),
        "feature_path": str(feature_path),
        "episode_start": str(args.episode_start),
        "episode_end": str(args.episode_end),
        "primary_window_rule": "timestamp date > episode_start and <= episode_end",
        "sharpe_metric_convention": {
            "version": SHARPE_METRIC_CONVENTION_VERSION,
            "headline_field": "full_oos_h10d_equivalent_sharpe",
            "deprecated_field": "full_oos_observed_frequency_sharpe_deprecated",
            "rule": "annualize overlapping h10d booking returns by max(target_horizon_bars, realization_step_bars), not by observed daily aggregate count",
        },
        "construction": {
            "target_engine": "multiphase_equal_sleeve",
            "phase_offsets_days": list(portfolio_diag.MULTIPHASE_PHASES),
            "sleeve_weight": portfolio_diag.MULTIPHASE_SLEEVE_WEIGHT,
            "rebalance_step_bars": int(split_contract["realization_step_bars"]),
            "target_horizon_bars": int(split_contract["target_horizon_bars"]),
        },
        "diagnostics": {
            "execution_eligible_row_count": int(len(frame)),
            "execution_eligible_subject_count": int(frame["subject"].nunique()),
            "variant_count": int(len(definitions)),
            "window_count": int(len(window_rows)),
            "baseline_primary_compounded_return": float(baseline["primary_compounded_return"]),
            "baseline_primary_max_drawdown": float(baseline["primary_max_drawdown"]),
            "baseline_full_oos_cumulative_return": float(baseline["full_oos_cumulative_return"]),
            "baseline_full_oos_h10d_equivalent_sharpe": float(baseline["full_oos_h10d_equivalent_sharpe"]),
            "baseline_full_oos_observed_frequency_sharpe_deprecated": float(
                baseline["full_oos_observed_frequency_sharpe_deprecated"]
            ),
            "baseline_full_oos_max_drawdown": float(baseline["full_oos_max_drawdown"]),
        },
        "top_episode_relief": json_safe(summary.head(8).to_dict(orient="records")),
        "top_full_oos": json_safe(
            summary.sort_values("delta_full_oos_cumulative_return_vs_baseline", ascending=False)
            .head(8)
            .to_dict(orient="records")
        ),
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "summary_md": str(output_root / "summary.md"),
            "overlay_summary_csv": str(summary_csv),
            "overlay_period_returns_long_csv": str(period_returns_csv),
            "overlay_factor_weights_long_csv": str(weights_csv),
            "overlay_windows_csv": str(windows_csv),
            "overlay_train_thresholds_csv": str(thresholds_csv),
            "overlay_definitions_json": str(definitions_json),
        },
        "interpretation_boundary": (
            "Score-layer conditional factor downweight ablation. Each WFO window estimates regime "
            "thresholds using train rows only, then applies the overlay to test rows. This is research "
            "diagnostic evidence only and does not update live trading."
        ),
    }
    write_json(output_root / "summary.json", payload)
    render_markdown(output_root / "summary.md", payload, summary)
    print(json.dumps(json_safe({"status": "computed", "summary_json": str(output_root / "summary.json")}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
