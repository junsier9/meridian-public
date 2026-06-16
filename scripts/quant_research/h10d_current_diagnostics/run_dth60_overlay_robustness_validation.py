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
import run_dth60_conditional_overlay_ablation as overlay_diag  # noqa: E402
import run_multiphase_factor_drawdown_ablation as factor_ablation  # noqa: E402
import run_portfolio_construction_experiment as portfolio_diag  # noqa: E402

from enhengclaw.quant_research.execution_backtest import backtest_cross_sectional, filter_cross_sectional_execution_frame  # noqa: E402
from enhengclaw.quant_research.horizon_metrics import SHARPE_METRIC_CONVENTION_VERSION  # noqa: E402
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, _apply_universe_filter, _experiment_directory_name, _resolved_execution_cost_models  # noqa: E402
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import resolve_split_realization_contract  # noqa: E402
from enhengclaw.quant_research.validation_contract import execution_capacity_limits, validation_contract_reference_capital_usd  # noqa: E402


BASELINE_LABEL = overlay_diag.BASELINE_LABEL
EFFECTIVE_BASELINE_LABEL = overlay_diag.EFFECTIVE_BASELINE_LABEL
BASELINE_EXPERIMENT_ID = overlay_diag.BASELINE_EXPERIMENT_ID
BASELINE_VARIANT_LABEL = overlay_diag.BASELINE_VARIANT_LABEL
H10D_VALIDATION_CONTRACT_PATH = overlay_diag.H10D_VALIDATION_CONTRACT_PATH
TARGET_FACTOR = overlay_diag.TARGET_FACTOR
NESTED_SELECTED_LABEL = "nested_validation_selected"
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-06-03"
    / "v5_rw_dth60_overlay_robustness_validation_2024_10_31_2024_11_25"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run robustness validation for the distance_to_high_60 hybrid conditional overlay "
            "under the v5_rw 10-sleeve h10d research baseline."
        )
    )
    parser.add_argument("--episode-start", default="2024-10-31")
    parser.add_argument("--episode-end", default="2024-11-25")
    parser.add_argument("--holdout-start", default="2025-10-01")
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


def q_tag(quantile: float) -> str:
    return f"q{int(round(float(quantile) * 100.0))}"


def top_tag(top_fraction: float) -> str:
    return f"top{int(round(float(top_fraction) * 100.0))}"


def build_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = [
        {
            "label": BASELINE_VARIANT_LABEL,
            "kind": "baseline",
            "condition": "none",
            "shock_quantile": None,
            "crowded_top_fraction": None,
            "target_multiplier": 1.0,
            "description": "No score-layer factor overlay.",
        }
    ]
    for shock_quantile in (0.85, 0.90, 0.95):
        for crowded_top_fraction in (0.20, 0.25, 0.30):
            definitions.append(
                {
                    "label": (
                        "dth60_hybrid_shock_"
                        f"{q_tag(shock_quantile)}_or_crowded_{top_tag(crowded_top_fraction)}_zero"
                    ),
                    "kind": "hybrid_overlay_robustness_grid",
                    "condition": "shock_quantile_or_near_high_top_trader_crowded",
                    "shock_quantile": float(shock_quantile),
                    "crowded_top_fraction": float(crowded_top_fraction),
                    "target_multiplier": 0.0,
                    "description": (
                        "Remove distance_to_high_60 when train-window shock/co-jump quantile "
                        f"{q_tag(shock_quantile)} fires or when near-high rows are top-trader crowded "
                        f"at {top_tag(crowded_top_fraction)}."
                    ),
                }
            )
    return definitions


def robustness_thresholds(train_df: pd.DataFrame, quantiles: tuple[float, ...] = (0.85, 0.90, 0.95)) -> dict[str, float]:
    shock = overlay_diag._timestamp_first(train_df, "shock_co_occurrence_index")
    co_jump = overlay_diag._timestamp_first(train_df, "co_jump_count_3d")
    thresholds: dict[str, float] = {}
    for quantile in quantiles:
        tag = q_tag(quantile)
        thresholds[f"shock_co_occurrence_index_{tag}"] = overlay_diag._safe_quantile(shock, quantile, 0.10)
        thresholds[f"co_jump_count_3d_{tag}"] = overlay_diag._safe_quantile(co_jump, quantile, 20.0)
    return thresholds


def robust_trigger_mask(frame: pd.DataFrame, *, variant: dict[str, Any], thresholds: dict[str, float]) -> pd.Series:
    if str(variant["label"]) == BASELINE_VARIANT_LABEL:
        return pd.Series(False, index=frame.index, dtype="bool")

    shock_quantile = float(variant["shock_quantile"])
    crowded_top_fraction = float(variant["crowded_top_fraction"])
    tag = q_tag(shock_quantile)
    shock = overlay_diag._timestamp_first(frame, "shock_co_occurrence_index")
    co_jump = overlay_diag._timestamp_first(frame, "co_jump_count_3d")
    shock_cluster_ts = shock.ge(float(thresholds[f"shock_co_occurrence_index_{tag}"])) | co_jump.ge(
        float(thresholds[f"co_jump_count_3d_{tag}"])
    )
    shock_cluster = overlay_diag._broadcast_timestamp_condition(frame, shock_cluster_ts)

    near_high = overlay_diag._rank_pct(frame, TARGET_FACTOR).ge(0.75)
    crowded_cutoff = 1.0 - crowded_top_fraction
    crowded = overlay_diag._rank_pct(frame, "coinglass_top_trader_long_pct_smooth_5").ge(crowded_cutoff)
    return (shock_cluster | (near_high & crowded)).astype(bool)


def score_frame_with_robust_overlay(
    frame: pd.DataFrame,
    *,
    factor_weights: dict[str, float],
    variant: dict[str, Any],
    thresholds: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    scored = frame.copy()
    timestamps = scored["timestamp_ms"]
    trigger = robust_trigger_mask(scored, variant=variant, thresholds=thresholds)
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


def period_timestamp(periods: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(periods["timestamp_utc"], utc=True, errors="coerce")


def episode_mask(periods: pd.DataFrame, *, episode_start: str, episode_end: str) -> pd.Series:
    timestamps = period_timestamp(periods)
    start = pd.Timestamp(episode_start, tz="UTC")
    end = pd.Timestamp(episode_end, tz="UTC")
    return timestamps.gt(start) & timestamps.le(end)


def slice_periods(
    periods: pd.DataFrame,
    *,
    slice_name: str,
    episode_start: str,
    episode_end: str,
    holdout_start: str,
) -> pd.DataFrame:
    if periods.empty:
        return periods.copy()
    timestamps = period_timestamp(periods)
    holdout = pd.Timestamp(holdout_start, tz="UTC")
    ep = episode_mask(periods, episode_start=episode_start, episode_end=episode_end)
    if slice_name == "full_oos":
        return periods.copy()
    if slice_name == "episode":
        return periods.loc[ep].copy()
    if slice_name == "no_episode_full":
        return periods.loc[~ep].copy()
    if slice_name == "selection_ex_episode_pre_holdout":
        return periods.loc[timestamps.lt(holdout) & ~ep].copy()
    if slice_name == "untouched_holdout":
        return periods.loc[timestamps.ge(holdout)].copy()
    raise ValueError(f"unknown slice: {slice_name}")


def metrics_for_periods(periods: pd.DataFrame, *, split_contract: dict[str, Any]) -> dict[str, Any]:
    out = overlay_diag.full_metrics(periods, split_contract=split_contract)
    return {
        "period_count": int(out["period_count"]),
        "cumulative_return": float(out["cumulative_return"]),
        "h10d_equivalent_sharpe": float(out["h10d_equivalent_sharpe"]),
        "max_drawdown": float(out["max_drawdown"]),
        "loss_period_fraction": float(out["loss_period_fraction"]),
        "mean_period_return": float(out["mean_period_return"]),
        "turnover_total": float(out["turnover_total"]),
        "max_trade_participation_rate": float(out["max_trade_participation_rate"]),
        "capacity_breach_count": int(out["capacity_breach_count"]),
    }


def build_slice_summary(
    *,
    labels: list[str],
    periods_by_label: dict[str, pd.DataFrame],
    split_contract: dict[str, Any],
    episode_start: str,
    episode_end: str,
    holdout_start: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    slices = (
        "full_oos",
        "episode",
        "no_episode_full",
        "selection_ex_episode_pre_holdout",
        "untouched_holdout",
    )
    for slice_name in slices:
        baseline_periods = slice_periods(
            periods_by_label[BASELINE_VARIANT_LABEL],
            slice_name=slice_name,
            episode_start=episode_start,
            episode_end=episode_end,
            holdout_start=holdout_start,
        )
        baseline = metrics_for_periods(baseline_periods, split_contract=split_contract)
        for label in labels:
            periods = slice_periods(
                periods_by_label[label],
                slice_name=slice_name,
                episode_start=episode_start,
                episode_end=episode_end,
                holdout_start=holdout_start,
            )
            metrics = metrics_for_periods(periods, split_contract=split_contract)
            rows.append(
                {
                    "label": label,
                    "slice": slice_name,
                    **metrics,
                    "delta_cumulative_return_vs_baseline": float(
                        metrics["cumulative_return"] - baseline["cumulative_return"]
                    ),
                    "delta_h10d_equivalent_sharpe_vs_baseline": float(
                        metrics["h10d_equivalent_sharpe"] - baseline["h10d_equivalent_sharpe"]
                    ),
                    "delta_max_drawdown_vs_baseline": float(metrics["max_drawdown"] - baseline["max_drawdown"]),
                }
            )
    return pd.DataFrame(rows)


def build_window_stability(
    *,
    labels: list[str],
    test_window_rows: pd.DataFrame,
    definitions_by_label: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    base = test_window_rows.loc[test_window_rows["label"].eq(BASELINE_VARIANT_LABEL)].copy()
    base = base[
        [
            "phase_offset_days",
            "test_start_utc",
            "test_end_utc",
            "net_return",
            "max_drawdown",
            "period_count",
        ]
    ].rename(columns={"net_return": "baseline_net_return", "max_drawdown": "baseline_max_drawdown"})
    rows: list[dict[str, Any]] = []
    for label in labels:
        if label == BASELINE_VARIANT_LABEL:
            continue
        current = test_window_rows.loc[test_window_rows["label"].eq(label)].copy()
        merged = base.merge(
            current,
            on=["phase_offset_days", "test_start_utc", "test_end_utc"],
            how="inner",
            suffixes=("", "_variant"),
        )
        if merged.empty:
            continue
        delta_return = pd.to_numeric(merged["net_return"], errors="coerce") - pd.to_numeric(
            merged["baseline_net_return"], errors="coerce"
        )
        delta_dd = pd.to_numeric(merged["max_drawdown"], errors="coerce") - pd.to_numeric(
            merged["baseline_max_drawdown"], errors="coerce"
        )
        definition = definitions_by_label.get(label, {})
        rows.append(
            {
                "label": label,
                "shock_quantile": definition.get("shock_quantile"),
                "crowded_top_fraction": definition.get("crowded_top_fraction"),
                "window_count": int(len(merged)),
                "improve_return_fraction": float(delta_return.gt(0.0).mean()),
                "median_delta_return": float(delta_return.median()),
                "mean_delta_return": float(delta_return.mean()),
                "worst_delta_return": float(delta_return.min()),
                "best_delta_return": float(delta_return.max()),
                "improve_drawdown_fraction": float(delta_dd.lt(0.0).mean()),
                "median_delta_drawdown": float(delta_dd.median()),
                "mean_delta_drawdown": float(delta_dd.mean()),
                "mean_triggered_row_fraction": float(
                    pd.to_numeric(merged["overlay_triggered_row_fraction"], errors="coerce").mean()
                ),
                "zero_trigger_window_count": int(
                    pd.to_numeric(merged["overlay_triggered_row_fraction"], errors="coerce").eq(0.0).sum()
                ),
                "full_trigger_window_count": int(
                    pd.to_numeric(merged["overlay_triggered_row_fraction"], errors="coerce").eq(1.0).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def select_episode_excluded_candidate(slice_summary: pd.DataFrame, *, labels: list[str]) -> dict[str, Any]:
    candidates = slice_summary.loc[
        slice_summary["slice"].eq("selection_ex_episode_pre_holdout")
        & slice_summary["label"].isin([label for label in labels if label != BASELINE_VARIANT_LABEL])
    ].copy()
    if candidates.empty:
        return {"label": BASELINE_VARIANT_LABEL, "selection_score": 0.0}
    dd_penalty = candidates["delta_max_drawdown_vs_baseline"].clip(lower=0.0)
    candidates["selection_score"] = (
        candidates["delta_cumulative_return_vs_baseline"]
        + 0.25 * candidates["delta_h10d_equivalent_sharpe_vs_baseline"]
        - 2.0 * dd_penalty
    )
    candidates = candidates.sort_values(
        [
            "selection_score",
            "delta_cumulative_return_vs_baseline",
            "delta_h10d_equivalent_sharpe_vs_baseline",
            "delta_max_drawdown_vs_baseline",
        ],
        ascending=[False, False, False, True],
    )
    return candidates.iloc[0].to_dict()


def validation_selection_label(validation_rows: list[dict[str, Any]]) -> str:
    frame = pd.DataFrame(validation_rows)
    if frame.empty:
        return BASELINE_VARIANT_LABEL
    baseline = frame.loc[frame["label"].eq(BASELINE_VARIANT_LABEL)]
    if baseline.empty:
        return BASELINE_VARIANT_LABEL
    base_return = float(baseline.iloc[0]["net_return"])
    base_dd = float(baseline.iloc[0]["max_drawdown"])
    frame["delta_validation_return_vs_baseline"] = pd.to_numeric(frame["net_return"], errors="coerce") - base_return
    frame["delta_validation_drawdown_vs_baseline"] = pd.to_numeric(frame["max_drawdown"], errors="coerce") - base_dd
    frame["selection_score"] = frame["delta_validation_return_vs_baseline"] - frame[
        "delta_validation_drawdown_vs_baseline"
    ].clip(lower=0.0)
    frame = frame.sort_values(
        ["selection_score", "delta_validation_return_vs_baseline", "delta_validation_drawdown_vs_baseline"],
        ascending=[False, False, True],
    )
    return str(frame.iloc[0]["label"])


def render_markdown(
    path: Path,
    *,
    payload: dict[str, Any],
    slice_summary: pd.DataFrame,
    window_stability: pd.DataFrame,
    nested_selection_summary: pd.DataFrame,
) -> None:
    original_label = "dth60_hybrid_shock_q90_or_crowded_top25_zero"
    episode_selected = dict(payload["episode_excluded_selection"])

    def row_for(label: str, slice_name: str) -> dict[str, Any]:
        rows = slice_summary.loc[slice_summary["label"].eq(label) & slice_summary["slice"].eq(slice_name)]
        return rows.iloc[0].to_dict() if not rows.empty else {}

    key_labels = [
        BASELINE_VARIANT_LABEL,
        original_label,
        str(episode_selected["label"]),
        NESTED_SELECTED_LABEL,
    ]
    seen: set[str] = set()
    key_labels = [label for label in key_labels if not (label in seen or seen.add(label))]

    lines = [
        "# Distance-to-High-60 Hybrid Overlay Robustness Validation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Effective research baseline: `{payload['effective_research_baseline']}`",
        f"- Target factor: `{TARGET_FACTOR}`",
        f"- Drawdown episode excluded for selection: `{payload['episode_start']}` to `{payload['episode_end']}`",
        f"- Untouched holdout for this validation: `{payload['holdout_start']}` onward",
        "- Engine: `multiphase_equal_sleeve`, 10 sleeves, same score parent and base execution cost model.",
        "- Boundary: research diagnostic only; no manifest, paper, live, or remote config mutation.",
        "- Sharpe convention: `quant_h10d_overlap_adjusted_sharpe.v1` h10d-equivalent Sharpe.",
        "",
        "## Protocol",
        "",
        "- Parameter perturbation: shock/co-jump train quantiles q85/q90/q95 crossed with top-trader crowded top20/top25/top30.",
        "- Episode-excluded selection: choose parameters on pre-holdout periods while excluding the 2024-10-31 to 2024-11-25 drawdown episode.",
        "- Nested WFO: inside each outer test window, choose baseline or one grid variant using only that window's validation slice, then apply the choice to the test slice.",
        "- Holdout: periods from the holdout start date onward are not used by the aggregate episode-excluded selector.",
        "",
        "## Selection Result",
        "",
        f"- episode-excluded selected label: `{episode_selected['label']}`",
        f"- selection score: `{episode_selected['selection_score']}`",
        f"- original investigated label: `{original_label}`",
        "",
        "## Key Metrics",
        "",
        "| label | slice | periods | cum ret | delta ret | h10d-eq Sharpe | delta Sharpe | max DD | delta DD |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label in key_labels:
        for slice_name in ("selection_ex_episode_pre_holdout", "untouched_holdout", "full_oos"):
            row = row_for(label, slice_name)
            if not row:
                continue
            lines.append(
                "| `{label}` | `{slice}` | {n} | {ret:.6f} | {dret:.6f} | {sharpe:.6f} | {dsharpe:.6f} | {dd:.6f} | {ddd:.6f} |".format(
                    label=label,
                    slice=slice_name,
                    n=int(row["period_count"]),
                    ret=float(row["cumulative_return"]),
                    dret=float(row["delta_cumulative_return_vs_baseline"]),
                    sharpe=float(row["h10d_equivalent_sharpe"]),
                    dsharpe=float(row["delta_h10d_equivalent_sharpe_vs_baseline"]),
                    dd=float(row["max_drawdown"]),
                    ddd=float(row["delta_max_drawdown_vs_baseline"]),
                )
            )

    holdout_rank = slice_summary.loc[
        slice_summary["slice"].eq("untouched_holdout")
        & ~slice_summary["label"].isin([BASELINE_VARIANT_LABEL, NESTED_SELECTED_LABEL])
    ].sort_values("delta_cumulative_return_vs_baseline", ascending=False)
    lines.extend(
        [
            "",
            "## Holdout Ranking",
            "",
            "| label | holdout ret | delta ret | h10d-eq Sharpe | delta Sharpe | max DD | delta DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in holdout_rank.head(9).iterrows():
        lines.append(
            "| `{label}` | {ret:.6f} | {dret:.6f} | {sharpe:.6f} | {dsharpe:.6f} | {dd:.6f} | {ddd:.6f} |".format(
                label=row["label"],
                ret=float(row["cumulative_return"]),
                dret=float(row["delta_cumulative_return_vs_baseline"]),
                sharpe=float(row["h10d_equivalent_sharpe"]),
                dsharpe=float(row["delta_h10d_equivalent_sharpe_vs_baseline"]),
                dd=float(row["max_drawdown"]),
                ddd=float(row["delta_max_drawdown_vs_baseline"]),
            )
        )

    lines.extend(
        [
            "",
            "## Window Stability",
            "",
            "| label | improve windows | median delta ret | mean delta ret | worst delta ret | mean trigger rows |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in window_stability.sort_values("mean_delta_return", ascending=False).head(10).iterrows():
        lines.append(
            "| `{label}` | {frac:.3f} | {median:.6f} | {mean:.6f} | {worst:.6f} | {trigger:.3f} |".format(
                label=row["label"],
                frac=float(row["improve_return_fraction"]),
                median=float(row["median_delta_return"]),
                mean=float(row["mean_delta_return"]),
                worst=float(row["worst_delta_return"]),
                trigger=float(row["mean_triggered_row_fraction"]),
            )
        )

    lines.extend(
        [
            "",
            "## Nested WFO Selection Frequency",
            "",
            "| selected label | count | fraction |",
            "| --- | ---: | ---: |",
        ]
    )
    for _, row in nested_selection_summary.iterrows():
        lines.append(
            "| `{label}` | {count} | {frac:.3f} |".format(
                label=row["selected_label"],
                count=int(row["count"]),
                frac=float(row["fraction"]),
            )
        )

    lines.extend(
        [
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

    definitions = build_definitions()
    definitions_by_label = {str(item["label"]): item for item in definitions}
    fixed_labels = [str(item["label"]) for item in definitions]
    all_labels = fixed_labels + [NESTED_SELECTED_LABEL]
    phase_periods_by_label: dict[str, list[pd.DataFrame]] = {label: [] for label in all_labels}
    test_window_rows: list[dict[str, Any]] = []
    validation_window_rows: list[dict[str, Any]] = []
    nested_selection_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []

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
            thresholds = robustness_thresholds(train_df)
            threshold_rows.append(
                {
                    "phase_offset_days": int(phase),
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    **thresholds,
                }
            )

            validation_scores: list[dict[str, Any]] = []
            test_metrics_by_label: dict[str, dict[str, Any]] = {}
            for split_name, split_df, row_sink in (
                ("validation", validation_df, validation_window_rows),
                ("test", test_df, test_window_rows),
            ):
                split_times = pd.to_datetime(split_df["timestamp_ms"], unit="ms", utc=True)
                for definition in definitions:
                    label = str(definition["label"])
                    scored, overlay_stats = score_frame_with_robust_overlay(
                        split_df,
                        factor_weights=weights,
                        variant=definition,
                        thresholds=thresholds,
                    )
                    metrics = backtest_cross_sectional(
                        frame=scored,
                        constraints=constraints,
                        split_realization_contract=split_contract,
                        execution_cost_model=base_execution_cost_model,
                        reference_capital_usd=reference_capital_usd,
                        capacity_limits=capacity_limits,
                        include_periods=True,
                    )
                    row = {
                        "label": label,
                        "kind": str(definition["kind"]),
                        "condition": str(definition["condition"]),
                        "shock_quantile": definition.get("shock_quantile"),
                        "crowded_top_fraction": definition.get("crowded_top_fraction"),
                        "target_multiplier": float(definition["target_multiplier"]),
                        "split": split_name,
                        "phase_offset_days": int(phase),
                        "phase_start_date_utc": phase_audit.get("start_date_utc"),
                        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                        "test_start_utc": split_times.min().isoformat().replace("+00:00", "Z"),
                        "test_end_utc": split_times.max().isoformat().replace("+00:00", "Z"),
                        "net_return": float(metrics.get("net_return", 0.0) or 0.0),
                        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
                        "turnover": float(metrics.get("turnover", 0.0) or 0.0),
                        "period_count": int(len(metrics.get("periods") or [])),
                        **overlay_stats,
                    }
                    row_sink.append(row)
                    if split_name == "validation":
                        validation_scores.append(row)
                    else:
                        test_metrics_by_label[label] = metrics
                        period_frame = factor_ablation.period_frame_from_metrics(
                            label=label,
                            phase=phase,
                            metrics=metrics,
                        )
                        if not period_frame.empty:
                            phase_periods_by_label[label].append(period_frame)

            selected_label = validation_selection_label(validation_scores)
            selected_test_metrics = test_metrics_by_label[selected_label]
            nested_period_frame = factor_ablation.period_frame_from_metrics(
                label=NESTED_SELECTED_LABEL,
                phase=phase,
                metrics=selected_test_metrics,
            )
            if not nested_period_frame.empty:
                phase_periods_by_label[NESTED_SELECTED_LABEL].append(nested_period_frame)
            selected_validation = pd.DataFrame(validation_scores)
            selected_row = selected_validation.loc[selected_validation["label"].eq(selected_label)].iloc[0].to_dict()
            selected_test_times = pd.to_datetime(test_df["timestamp_ms"], unit="ms", utc=True)
            nested_selection_rows.append(
                {
                    "phase_offset_days": int(phase),
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    "selected_validation_start_utc": selected_row["test_start_utc"],
                    "selected_validation_end_utc": selected_row["test_end_utc"],
                    "test_start_utc": selected_test_times.min().isoformat().replace("+00:00", "Z"),
                    "test_end_utc": selected_test_times.max().isoformat().replace("+00:00", "Z"),
                    "selected_label": selected_label,
                    "selected_validation_return": float(selected_row["net_return"]),
                    "selected_validation_max_drawdown": float(selected_row["max_drawdown"]),
                }
            )

    periods_by_label: dict[str, pd.DataFrame] = {}
    period_frames: list[pd.DataFrame] = []
    for label in all_labels:
        periods = factor_ablation.aggregate_variant_periods(
            label=label,
            sleeve_periods=phase_periods_by_label[label],
            trade_participation_cap=trade_cap,
            inventory_participation_cap=inventory_cap,
        )
        periods_by_label[label] = periods
        if not periods.empty:
            period_frames.append(periods)

    test_window_frame = pd.DataFrame(test_window_rows)
    validation_window_frame = pd.DataFrame(validation_window_rows)
    nested_selection_frame = pd.DataFrame(nested_selection_rows)
    nested_frequency = (
        nested_selection_frame["selected_label"]
        .value_counts(dropna=False)
        .rename_axis("selected_label")
        .reset_index(name="count")
    )
    nested_frequency["fraction"] = nested_frequency["count"] / float(nested_frequency["count"].sum())

    slice_summary = build_slice_summary(
        labels=all_labels,
        periods_by_label=periods_by_label,
        split_contract=split_contract,
        episode_start=str(args.episode_start),
        episode_end=str(args.episode_end),
        holdout_start=str(args.holdout_start),
    )
    episode_selected = select_episode_excluded_candidate(slice_summary, labels=fixed_labels)
    window_stability = build_window_stability(
        labels=fixed_labels,
        test_window_rows=test_window_frame,
        definitions_by_label=definitions_by_label,
    )

    definitions_json = output_root / "robustness_definitions.json"
    threshold_csv = output_root / "robustness_train_thresholds.csv"
    test_window_csv = output_root / "robustness_test_windows.csv"
    validation_window_csv = output_root / "robustness_validation_windows.csv"
    nested_selection_csv = output_root / "nested_window_selection.csv"
    nested_frequency_csv = output_root / "nested_selection_frequency.csv"
    slice_summary_csv = output_root / "slice_summary.csv"
    window_stability_csv = output_root / "window_stability.csv"
    period_returns_csv = output_root / "period_returns_long.csv"
    write_json(definitions_json, {"definitions": definitions, "target_factor": TARGET_FACTOR})
    pd.DataFrame(threshold_rows).to_csv(threshold_csv, index=False)
    test_window_frame.to_csv(test_window_csv, index=False)
    validation_window_frame.to_csv(validation_window_csv, index=False)
    nested_selection_frame.to_csv(nested_selection_csv, index=False)
    nested_frequency.to_csv(nested_frequency_csv, index=False)
    slice_summary.to_csv(slice_summary_csv, index=False)
    window_stability.to_csv(window_stability_csv, index=False)
    pd.concat(period_frames, ignore_index=True).to_csv(period_returns_csv, index=False)

    payload = {
        "status": "computed",
        "generated_at_utc": utc_now_iso(),
        "score_parent_label": BASELINE_LABEL,
        "effective_research_baseline": EFFECTIVE_BASELINE_LABEL,
        "target_factor": TARGET_FACTOR,
        "baseline_variant_label": BASELINE_VARIANT_LABEL,
        "nested_selected_label": NESTED_SELECTED_LABEL,
        "baseline_experiment_id": str(args.baseline_experiment_id),
        "feature_path": str(feature_path),
        "episode_start": str(args.episode_start),
        "episode_end": str(args.episode_end),
        "holdout_start": str(args.holdout_start),
        "selection_rule": {
            "slice": "selection_ex_episode_pre_holdout",
            "score": "delta_return + 0.25 * delta_h10d_equivalent_sharpe - 2.0 * positive_delta_max_drawdown",
            "baseline_allowed_in_nested_wfo": True,
        },
        "sharpe_metric_convention": {
            "version": SHARPE_METRIC_CONVENTION_VERSION,
            "headline_field": "h10d_equivalent_sharpe",
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
            "fixed_variant_count": int(len(definitions)),
            "test_window_row_count": int(len(test_window_frame)),
            "validation_window_row_count": int(len(validation_window_frame)),
            "nested_outer_window_count": int(len(nested_selection_frame)),
        },
        "episode_excluded_selection": json_safe(episode_selected),
        "nested_selection_frequency": json_safe(nested_frequency.to_dict(orient="records")),
        "top_holdout": json_safe(
            slice_summary.loc[
                slice_summary["slice"].eq("untouched_holdout")
                & ~slice_summary["label"].isin([BASELINE_VARIANT_LABEL, NESTED_SELECTED_LABEL])
            ]
            .sort_values("delta_cumulative_return_vs_baseline", ascending=False)
            .head(9)
            .to_dict(orient="records")
        ),
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "summary_md": str(output_root / "summary.md"),
            "robustness_definitions_json": str(definitions_json),
            "slice_summary_csv": str(slice_summary_csv),
            "window_stability_csv": str(window_stability_csv),
            "nested_window_selection_csv": str(nested_selection_csv),
            "nested_selection_frequency_csv": str(nested_frequency_csv),
            "robustness_test_windows_csv": str(test_window_csv),
            "robustness_validation_windows_csv": str(validation_window_csv),
            "robustness_train_thresholds_csv": str(threshold_csv),
            "period_returns_long_csv": str(period_returns_csv),
        },
        "interpretation_boundary": (
            "Robustness diagnostic only. Aggregate selector excludes the target drawdown episode and "
            "the holdout period. Nested WFO selector uses only validation slices before each test slice. "
            "No live or paper-shadow promotion is implied."
        ),
    }
    write_json(output_root / "summary.json", payload)
    render_markdown(
        output_root / "summary.md",
        payload=payload,
        slice_summary=slice_summary,
        window_stability=window_stability,
        nested_selection_summary=nested_frequency,
    )
    print(json.dumps(json_safe({"status": "computed", "summary_json": str(output_root / "summary.json")}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
