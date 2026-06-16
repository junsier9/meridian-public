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
import run_portfolio_construction_experiment as portfolio_diag  # noqa: E402

from enhengclaw.quant_research.execution_backtest import backtest_cross_sectional, filter_cross_sectional_execution_frame  # noqa: E402
from enhengclaw.quant_research.fixed_set_comparison import performance_summary  # noqa: E402
from enhengclaw.quant_research.horizon_metrics import SHARPE_METRIC_CONVENTION_VERSION, overlap_adjusted_performance_summary  # noqa: E402
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, _apply_universe_filter, _experiment_directory_name, _resolved_execution_cost_models  # noqa: E402
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import resolve_split_realization_contract  # noqa: E402
from enhengclaw.quant_research.validation_contract import execution_capacity_limits, validation_contract_reference_capital_usd  # noqa: E402


BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d"
EFFECTIVE_BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve"
BASELINE_VARIANT_LABEL = "baseline_all_factors"
BASELINE_EXPERIMENT_ID = "2026-04-29-xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
H10D_VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-06-03"
    / "v5_rw_multiphase_drawdown_factor_ablation_2024_10_31_2024_11_25"
)

FACTOR_GROUPS: dict[str, list[str]] = {
    "group_volatility": [
        "intraday_realized_vol_4h_to_1d_smooth_60",
        "realized_volatility_5",
        "downside_upside_vol_ratio_30",
    ],
    "group_price_structure_trend": [
        "distance_to_high_60",
        "distance_to_high_5",
        "momentum_decay_5_20",
    ],
    "group_derivatives_crowding_carry": [
        "coinglass_top_trader_long_pct_smooth_5",
        "coinglass_taker_imb_intraday_dispersion_24h",
        "quality_funding_oi",
        "funding_basis_residual_implied_repo_30",
        "settlement_cycle_premium_60d",
    ],
    "group_liquidity_stress": [
        "liquidity_stress_qv_iv",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run factor leave-one-out and group ablation under the current v5_rw "
            "10-sleeve research-baseline construction, restricted to a specified "
            "drawdown episode."
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
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")


def ablation_definitions(feature_columns: list[str]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = [
        {
            "label": BASELINE_VARIANT_LABEL,
            "kind": "baseline",
            "excluded_features": [],
        }
    ]
    for column in feature_columns:
        definitions.append(
            {
                "label": f"loo__{column}",
                "kind": "leave_one_out",
                "excluded_features": [column],
            }
        )
    for label, columns in FACTOR_GROUPS.items():
        included = [column for column in columns if column in feature_columns]
        if included:
            definitions.append(
                {
                    "label": label,
                    "kind": "group_ablation",
                    "excluded_features": included,
                }
            )
    return definitions


def active_v5_factor_columns(feature_columns: list[str]) -> list[str]:
    active_weights = v5_phase.lab._normalized_factor_weight_map(v5_phase.lab.ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS)
    feature_column_set = set(feature_columns)
    return [column for column in active_weights if column in feature_column_set]


def ablated_daily_ic(
    daily_ic_by_factor: dict[str, pd.Series],
    *,
    excluded_features: set[str],
) -> dict[str, pd.Series]:
    return {
        column: (pd.Series(dtype="float64") if column in excluded_features else series)
        for column, series in daily_ic_by_factor.items()
    }


def score_with_ablation(
    *,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    daily_ic_by_factor: dict[str, pd.Series],
    excluded_features: set[str],
) -> tuple[pd.DataFrame, dict[str, float]]:
    train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
    weights = v5_phase.weights_for_train_end(
        daily_ic_by_factor=ablated_daily_ic(daily_ic_by_factor, excluded_features=excluded_features),
        train_end_ms=train_end_ms,
    )
    for column in excluded_features:
        if column in weights:
            weights[column] = 0.0
    return v5_phase.score_frame(test_df, factor_weights=weights), weights


def period_frame_from_metrics(*, label: str, phase: int, metrics: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period in list(metrics.get("periods") or []):
        timestamp_ms = int(period["timestamp_ms"])
        row = {
            "candidate_label": label,
            "window_index": 0,
            "phase_offset_days": int(phase),
            "timestamp_ms": timestamp_ms,
            "timestamp_utc": pd.to_datetime(timestamp_ms, unit="ms", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
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
            row[column] = float(period.get(column, 0.0) or 0.0)
        row["capacity_breach_count"] = int(period.get("capacity_breach_count", 0) or 0)
        rows.append(row)
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["timestamp_ms", "phase_offset_days"]).reset_index(drop=True)


def aggregate_variant_periods(
    *,
    label: str,
    sleeve_periods: list[pd.DataFrame],
    trade_participation_cap: float,
    inventory_participation_cap: float,
) -> pd.DataFrame:
    if not sleeve_periods:
        return pd.DataFrame()
    scaled_frames = [
        portfolio_diag._scale_sleeve_periods(
            periods,
            phase=int(periods["phase_offset_days"].iloc[0]),
            sleeve_weight=portfolio_diag.MULTIPHASE_SLEEVE_WEIGHT,
        )
        for periods in sleeve_periods
        if not periods.empty
    ]
    if not scaled_frames:
        return pd.DataFrame()
    return portfolio_diag._aggregate_multiphase_periods(
        label=label,
        sleeve_periods=pd.concat(scaled_frames, ignore_index=True),
        trade_participation_cap=trade_participation_cap,
        inventory_participation_cap=inventory_participation_cap,
    )


def window_metrics(
    periods: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    include_start: bool,
) -> dict[str, Any]:
    if periods.empty:
        return {
            "period_count": 0,
            "compounded_return": 0.0,
            "max_drawdown": 0.0,
            "loss_period_fraction": 0.0,
            "worst_period_return": 0.0,
            "worst_period_date_utc": None,
        }
    working = periods.copy()
    working["date_utc"] = pd.to_datetime(working["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    if include_start:
        mask = working["date_utc"].ge(start_date) & working["date_utc"].le(end_date)
    else:
        mask = working["date_utc"].gt(start_date) & working["date_utc"].le(end_date)
    subset = working.loc[mask].sort_values("timestamp_ms").copy()
    returns = pd.to_numeric(subset.get("net_period_return"), errors="coerce").fillna(0.0).astype("float64")
    if returns.empty:
        return {
            "period_count": 0,
            "compounded_return": 0.0,
            "max_drawdown": 0.0,
            "loss_period_fraction": 0.0,
            "worst_period_return": 0.0,
            "worst_period_date_utc": None,
        }
    equity = (1.0 + returns).cumprod()
    drawdown = (1.0 - equity / equity.cummax().replace(0.0, np.nan)).fillna(0.0)
    worst_idx = returns.idxmin()
    return {
        "period_count": int(len(returns)),
        "start_date_utc": str(subset["date_utc"].min()),
        "end_date_utc": str(subset["date_utc"].max()),
        "include_start_date": bool(include_start),
        "compounded_return": float(equity.iloc[-1] - 1.0),
        "sum_period_return": float(returns.sum()),
        "mean_period_return": float(returns.mean()),
        "max_drawdown": float(drawdown.max()) if not drawdown.empty else 0.0,
        "loss_period_fraction": float((returns < 0.0).mean()),
        "worst_period_return": float(returns.min()),
        "worst_period_date_utc": str(subset.loc[worst_idx, "date_utc"]),
        "best_period_return": float(returns.max()),
        "turnover_total": float(pd.to_numeric(subset.get("turnover"), errors="coerce").fillna(0.0).sum())
        if "turnover" in subset
        else 0.0,
        "max_trade_participation_rate": float(
            pd.to_numeric(subset.get("trade_participation_rate"), errors="coerce").fillna(0.0).max()
        )
        if "trade_participation_rate" in subset
        else 0.0,
    }


def full_oos_metrics(periods: pd.DataFrame, *, split_contract: dict[str, Any]) -> dict[str, Any]:
    if periods.empty:
        empty_periods_per_year = float(
            overlap_adjusted_performance_summary(
                pd.Series(dtype="float64"),
                bar_interval_ms=int(split_contract["bar_interval_ms"]),
                target_horizon_bars=int(split_contract["target_horizon_bars"]),
                realization_step_bars=int(split_contract["realization_step_bars"]),
            )["overlap_adjusted_periods_per_year"]
        )
        return {
            "period_count": 0,
            "overlap_adjusted_periods_per_year": empty_periods_per_year,
            "independent_period_bars": max(
                int(split_contract["target_horizon_bars"]),
                int(split_contract["realization_step_bars"]),
            ),
            "observed_frequency_periods_per_year_deprecated": 0,
            "cumulative_return": 0.0,
            "h10d_equivalent_sharpe": 0.0,
            "observed_frequency_sharpe_deprecated": 0.0,
            "max_drawdown": 0.0,
        }
    returns = pd.to_numeric(periods["net_period_return"], errors="coerce").fillna(0.0)
    perf = overlap_adjusted_performance_summary(
        returns,
        bar_interval_ms=int(split_contract["bar_interval_ms"]),
        target_horizon_bars=int(split_contract["target_horizon_bars"]),
        realization_step_bars=int(split_contract["realization_step_bars"]),
    )
    deprecated_periods_per_year = portfolio_diag._empirical_periods_per_year(periods, default=365)
    deprecated_perf = performance_summary(
        pd.to_numeric(periods["net_period_return"], errors="coerce").fillna(0.0),
        periods_per_year=deprecated_periods_per_year,
    )
    return {
        "period_count": int(len(periods)),
        "overlap_adjusted_periods_per_year": float(perf["overlap_adjusted_periods_per_year"]),
        "independent_period_bars": int(perf["independent_period_bars"]),
        "observed_frequency_periods_per_year_deprecated": int(deprecated_periods_per_year),
        "cumulative_return": float(perf["net_return"]),
        "h10d_equivalent_sharpe": float(perf["sharpe"]),
        "observed_frequency_sharpe_deprecated": float(deprecated_perf["sharpe"]),
        "max_drawdown": float(perf["max_drawdown"]),
        "turnover_total": float(pd.to_numeric(periods.get("turnover"), errors="coerce").fillna(0.0).sum())
        if "turnover" in periods
        else 0.0,
    }


def render_markdown(path: Path, payload: dict[str, Any], window_summary: pd.DataFrame) -> None:
    primary = window_summary.sort_values("delta_primary_compounded_return_vs_baseline", ascending=False)
    loo = primary.loc[primary["kind"].eq("leave_one_out")].head(12)
    groups = primary.loc[primary["kind"].eq("group_ablation")].head(8)
    baseline = window_summary.loc[window_summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0].to_dict()
    lines = [
        "# V5 RW Multiphase Drawdown Factor Ablation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Effective research baseline: `{payload['effective_research_baseline']}`",
        f"- Drawdown episode: `{payload['episode_start']}` to `{payload['episode_end']}`",
        f"- Primary metric: peak-to-trough after-peak window return, excluding the peak date.",
        "",
        "## Baseline Window",
        "",
        f"- compounded_return: `{baseline['primary_compounded_return']}`",
        f"- max_drawdown: `{baseline['primary_max_drawdown']}`",
        f"- period_count: `{baseline['primary_period_count']}`",
        "",
        "## Leave-One-Out Relief Ranking",
        "",
        "| factor removed | window return | delta vs baseline | max DD | full OOS delta | interpretation |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in loo.iterrows():
        delta = float(row["delta_primary_compounded_return_vs_baseline"])
        if delta > 0.005:
            interpretation = "harmful in episode"
        elif delta < -0.005:
            interpretation = "protective in episode"
        else:
            interpretation = "near neutral"
        factor = ",".join(json.loads(str(row["excluded_features_json"])))
        lines.append(
            f"| `{factor}` | {float(row['primary_compounded_return']):.6f} | {delta:.6f} | "
            f"{float(row['primary_max_drawdown']):.6f} | {float(row['delta_full_oos_cumulative_return_vs_baseline']):.6f} | {interpretation} |"
        )
    lines.extend(
        [
            "",
            "## Group Ablation",
            "",
            "| group removed | window return | delta vs baseline | max DD | full OOS delta |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in groups.iterrows():
        lines.append(
            f"| `{row['label']}` | {float(row['primary_compounded_return']):.6f} | "
            f"{float(row['delta_primary_compounded_return_vs_baseline']):.6f} | "
            f"{float(row['primary_max_drawdown']):.6f} | "
            f"{float(row['delta_full_oos_cumulative_return_vs_baseline']):.6f} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a counterfactual score-ablation diagnostic under the same 10-phase equal-sleeve construction. "
            "It is not causal proof: correlated factors can share or mask episode PnL.",
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
    daily_ic_by_factor = v5_phase.build_daily_ic_by_factor(frame, feature_columns=feature_columns)
    active_factor_columns = active_v5_factor_columns(feature_columns)
    if not active_factor_columns:
        raise RuntimeError("no active v5 factors found in experiment feature columns")
    definitions = ablation_definitions(active_factor_columns)

    episode_start = str(args.episode_start)
    episode_end = str(args.episode_end)
    episode_start_ts = pd.Timestamp(episode_start, tz="UTC")
    episode_end_ts = pd.Timestamp(episode_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    phase_periods_by_label: dict[str, list[pd.DataFrame]] = {str(item["label"]): [] for item in definitions}
    weight_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []

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
            test_times = pd.to_datetime(test_df["timestamp_ms"], unit="ms", utc=True)
            if test_times.max() < episode_start_ts or test_times.min() > episode_end_ts:
                continue
            for definition in definitions:
                label = str(definition["label"])
                excluded = {str(item) for item in list(definition.get("excluded_features") or [])}
                scored_test, weights = score_with_ablation(
                    train_df=train_df,
                    test_df=test_df,
                    daily_ic_by_factor=daily_ic_by_factor,
                    excluded_features=excluded,
                )
                for factor, weight in sorted(weights.items()):
                    weight_rows.append(
                        {
                            "label": label,
                            "kind": definition["kind"],
                            "phase_offset_days": int(phase),
                            "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                            "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                            "factor": factor,
                            "weight": float(weight),
                            "excluded": factor in excluded,
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
                phase_periods = period_frame_from_metrics(label=label, phase=phase, metrics=metrics)
                if not phase_periods.empty:
                    phase_periods_by_label[label].append(phase_periods)
                window_rows.append(
                    {
                        "label": label,
                        "kind": definition["kind"],
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
                    }
                )

    all_period_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    periods_by_label: dict[str, pd.DataFrame] = {}
    for definition in definitions:
        label = str(definition["label"])
        periods = aggregate_variant_periods(
            label=label,
            sleeve_periods=phase_periods_by_label[label],
            trade_participation_cap=trade_cap,
            inventory_participation_cap=inventory_cap,
        )
        periods_by_label[label] = periods
        if not periods.empty:
            all_period_frames.append(periods.assign(ablation_kind=str(definition["kind"])))
        primary = window_metrics(
            periods,
            start_date=episode_start,
            end_date=episode_end,
            include_start=False,
        )
        inclusive = window_metrics(
            periods,
            start_date=episode_start,
            end_date=episode_end,
            include_start=True,
        )
        full = full_oos_metrics(periods, split_contract=split_contract)
        summary_rows.append(
            {
                "label": label,
                "kind": str(definition["kind"]),
                "excluded_features_json": json.dumps(list(definition.get("excluded_features") or []), sort_keys=True),
                "excluded_feature_count": int(len(definition.get("excluded_features") or [])),
                "primary_period_count": primary["period_count"],
                "primary_start_date_utc": primary.get("start_date_utc"),
                "primary_end_date_utc": primary.get("end_date_utc"),
                "primary_compounded_return": primary["compounded_return"],
                "primary_sum_period_return": primary["sum_period_return"],
                "primary_max_drawdown": primary["max_drawdown"],
                "primary_loss_period_fraction": primary["loss_period_fraction"],
                "primary_worst_period_return": primary["worst_period_return"],
                "primary_worst_period_date_utc": primary["worst_period_date_utc"],
                "primary_turnover_total": primary["turnover_total"],
                "inclusive_compounded_return": inclusive["compounded_return"],
                "inclusive_max_drawdown": inclusive["max_drawdown"],
                "full_oos_period_count": full["period_count"],
                "full_oos_overlap_adjusted_periods_per_year": full["overlap_adjusted_periods_per_year"],
                "full_oos_independent_period_bars": full["independent_period_bars"],
                "full_oos_observed_frequency_periods_per_year_deprecated": full["observed_frequency_periods_per_year_deprecated"],
                "full_oos_cumulative_return": full["cumulative_return"],
                "full_oos_h10d_equivalent_sharpe": full["h10d_equivalent_sharpe"],
                "full_oos_observed_frequency_sharpe_deprecated": full["observed_frequency_sharpe_deprecated"],
                "full_oos_max_drawdown": full["max_drawdown"],
                "full_oos_turnover_total": full["turnover_total"],
            }
        )

    summary = pd.DataFrame(summary_rows)
    if BASELINE_VARIANT_LABEL not in set(summary["label"]):
        raise RuntimeError("baseline ablation row missing")
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0]
    summary["delta_primary_compounded_return_vs_baseline"] = (
        pd.to_numeric(summary["primary_compounded_return"], errors="coerce")
        - float(baseline["primary_compounded_return"])
    )
    summary["delta_primary_max_drawdown_vs_baseline"] = (
        pd.to_numeric(summary["primary_max_drawdown"], errors="coerce")
        - float(baseline["primary_max_drawdown"])
    )
    summary["delta_inclusive_compounded_return_vs_baseline"] = (
        pd.to_numeric(summary["inclusive_compounded_return"], errors="coerce")
        - float(baseline["inclusive_compounded_return"])
    )
    summary["delta_full_oos_cumulative_return_vs_baseline"] = (
        pd.to_numeric(summary["full_oos_cumulative_return"], errors="coerce")
        - float(baseline["full_oos_cumulative_return"])
    )
    summary["episode_interpretation"] = np.select(
        [
            summary["delta_primary_compounded_return_vs_baseline"].gt(0.005),
            summary["delta_primary_compounded_return_vs_baseline"].lt(-0.005),
        ],
        [
            "removed_feature_relieves_drawdown",
            "removed_feature_worsens_drawdown",
        ],
        default="near_neutral",
    )
    summary = summary.sort_values("delta_primary_compounded_return_vs_baseline", ascending=False).reset_index(drop=True)

    summary_csv = output_root / "ablation_window_summary.csv"
    summary.to_csv(summary_csv, index=False)
    period_returns_csv = output_root / "ablation_period_returns_long.csv"
    pd.concat(all_period_frames, ignore_index=True).to_csv(period_returns_csv, index=False)
    weights_csv = output_root / "ablation_factor_weights_long.csv"
    pd.DataFrame(weight_rows).to_csv(weights_csv, index=False)
    windows_csv = output_root / "ablation_windows.csv"
    pd.DataFrame(window_rows).to_csv(windows_csv, index=False)
    definitions_json = output_root / "ablation_definitions.json"
    write_json(
        definitions_json,
        {
            "definitions": definitions,
            "active_factor_columns": active_factor_columns,
            "factor_groups": FACTOR_GROUPS,
        },
    )

    payload = {
        "status": "computed",
        "generated_at_utc": utc_now_iso(),
        "score_parent_label": BASELINE_LABEL,
        "effective_research_baseline": EFFECTIVE_BASELINE_LABEL,
        "baseline_variant_label": BASELINE_VARIANT_LABEL,
        "active_factor_columns": active_factor_columns,
        "episode_start": episode_start,
        "episode_end": episode_end,
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
            "ablation_count": int(len(definitions)),
            "window_count": int(len(window_rows)),
            "baseline_primary_compounded_return": float(baseline["primary_compounded_return"]),
            "baseline_primary_max_drawdown": float(baseline["primary_max_drawdown"]),
            "baseline_primary_period_count": int(baseline["primary_period_count"]),
        },
        "top_drawdown_relief_leave_one_out": json_safe(
            summary.loc[summary["kind"].eq("leave_one_out")]
            .head(8)
            .to_dict(orient="records")
        ),
        "top_drawdown_relief_groups": json_safe(
            summary.loc[summary["kind"].eq("group_ablation")]
            .head(8)
            .to_dict(orient="records")
        ),
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "summary_md": str(output_root / "summary.md"),
            "ablation_window_summary_csv": str(summary_csv),
            "ablation_period_returns_long_csv": str(period_returns_csv),
            "ablation_factor_weights_long_csv": str(weights_csv),
            "ablation_windows_csv": str(windows_csv),
            "ablation_definitions_json": str(definitions_json),
        },
        "interpretation_boundary": (
            "Counterfactual score ablation under the same 10-phase equal-sleeve engine. "
            "A positive delta vs baseline means removing that factor/group improves the specified drawdown window. "
            "Correlated factors can share or mask attribution; this is a diagnostic, not causal proof."
        ),
    }
    write_json(output_root / "summary.json", payload)
    render_markdown(output_root / "summary.md", payload, summary)
    print(json.dumps(json_safe({"status": "computed", "summary_json": str(output_root / "summary.json")}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
