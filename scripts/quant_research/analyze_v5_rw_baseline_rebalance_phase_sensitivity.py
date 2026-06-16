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
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import run_coinglass_h10d_parent_frozen_reset_strict as strict_helpers  # noqa: E402
from enhengclaw.quant_research import hypothesis_batch as hb  # noqa: E402
from enhengclaw.quant_research import lab  # noqa: E402
from enhengclaw.quant_research.data_readiness import load_data_readiness_contract  # noqa: E402
from enhengclaw.quant_research.derivatives_quality import summarize_feature_derivatives_quality  # noqa: E402
from enhengclaw.quant_research.execution_backtest import (  # noqa: E402
    backtest_cross_sectional,
    filter_cross_sectional_execution_frame,
)
from enhengclaw.quant_research.execution_cost_model import (  # noqa: E402
    load_execution_cost_model,
    resolve_execution_cost_model,
)
from enhengclaw.quant_research.fixed_set_comparison import (  # noqa: E402
    extract_period_frame,
    performance_summary,
    periods_per_year,
)
from enhengclaw.quant_research.overlap_integrity import (  # noqa: E402
    chronological_split_with_purge,
    walk_forward_split_with_purge,
)
from enhengclaw.quant_research.split_realization_contract import (  # noqa: E402
    resolve_split_realization_contract,
)
from enhengclaw.quant_research.validation_contract import (  # noqa: E402
    execution_capacity_limits,
    load_validation_contract,
    validation_contract_reference_capital_usd,
)


BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d"
BASELINE_STRATEGY_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
DEFAULT_PHASES = tuple(range(10))
DEFAULT_MANIFEST = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json"
)
DEFAULT_EXPERIMENT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "experiments"
    / "2026-04-29-xs_alpha_ontology_v5_rw_bridg-6054571c70ef"
)
DEFAULT_FEATURES_PATH = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91"
    / "features.csv.gz"
)
DEFAULT_FEATURE_MANIFEST = DEFAULT_FEATURES_PATH.with_name("feature_manifest.json")
DEFAULT_FIXED_SET_RETURNS = DEFAULT_EXPERIMENT_ROOT / "fixed_set_aligned_period_returns.csv"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "v5_rw_baseline_rebalance_phase_sensitivity_20260521"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "v5_rw_baseline_12factor_rebalance_phase_sensitivity_2026_05_21.md"
)
DEFAULT_MIN_NET_RETURN_RATIO_VS_PHASE0 = 0.50
DEFAULT_MIN_SHARPE = 0.75
DEFAULT_MAX_DD_ABS = 0.45
DEFAULT_MAX_DD_DELTA_VS_PHASE0 = 0.10
BASE_COLUMNS = {
    "timestamp_ms",
    "timestamp_utc",
    "date_utc",
    "subject",
    "liquidity_bucket",
    "has_perp_as_of",
    "usdm_symbol",
    "perp_execution_eligible",
    "perp_executable_start_ms",
    "perp_close",
    "perp_volume",
    "perp_quote_volume_usd",
    "open_interest_value",
    "funding_rate",
    "funding_sample_count",
    "target_execution_up",
    "target_execution_forward_return",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run 10d rebalance phase sensitivity for the original 12-factor "
            "v5_rw_bridge_no_overlay_h10d research baseline. The strategy spec, "
            "feature matrix, WFO shape, costs, and factor formula are held fixed; "
            "only the first eligible daily timestamp is shifted by 0..9 days."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--experiment-root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--feature-manifest", type=Path, default=DEFAULT_FEATURE_MANIFEST)
    parser.add_argument("--fixed-set-returns", type=Path, default=DEFAULT_FIXED_SET_RETURNS)
    parser.add_argument("--phases", nargs="+", type=int, default=list(DEFAULT_PHASES))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--baseline-tolerance", type=float, default=1e-10)
    parser.add_argument("--min-net-return-ratio-vs-phase0", type=float, default=DEFAULT_MIN_NET_RETURN_RATIO_VS_PHASE0)
    parser.add_argument("--min-sharpe", type=float, default=DEFAULT_MIN_SHARPE)
    parser.add_argument("--max-dd-abs", type=float, default=DEFAULT_MAX_DD_ABS)
    parser.add_argument("--max-dd-delta-vs-phase0", type=float, default=DEFAULT_MAX_DD_DELTA_VS_PHASE0)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def load_strategy(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(manifest.get("entries") or [])
    if len(entries) != 1:
        raise ValueError(f"expected one baseline manifest entry, found {len(entries)}")
    strategy = hb._materialize_strict_strategy_entry(dict(entries[0]))
    if str(strategy.get("strategy_id") or "") != BASELINE_STRATEGY_ID:
        raise ValueError(f"unexpected strategy_id: {strategy.get('strategy_id')!r}")
    return strategy


def read_experiment_spec(experiment_root: Path) -> dict[str, Any]:
    spec = json.loads((experiment_root / "experiment_spec.json").read_text(encoding="utf-8"))
    if str(spec.get("strategy_id") or "") != BASELINE_STRATEGY_ID:
        raise ValueError(f"unexpected experiment spec strategy_id: {spec.get('strategy_id')!r}")
    return spec


def read_filtered_frame(
    *,
    features_path: Path,
    strategy: dict[str, Any],
    spec: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    feature_columns = list(spec.get("feature_columns") or strategy.get("required_feature_columns") or [])
    use_columns = set(BASE_COLUMNS)
    use_columns.update(feature_columns)
    frame = pd.read_csv(features_path, compression="gzip", usecols=lambda column: column in use_columns, low_memory=False)
    derivatives_quality_frame = strict_helpers._build_derivatives_quality_frame(frame)
    derivatives_feature_quality = summarize_feature_derivatives_quality(
        quality_frame=derivatives_quality_frame,
        interval="1d",
    )
    constraints = dict(spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(spec.get("strategy_profile") or "")
    filtered = lab._apply_universe_filter(frame, universe_filter=dict(spec.get("universe_filter") or {}))
    filtered = filter_cross_sectional_execution_frame(frame=filtered, constraints=constraints)
    split = chronological_split_with_purge(
        filtered,
        time_col="timestamp_ms",
        split_realization_contract=contract,
    )
    if split is None:
        raise ValueError("baseline frame could not be chronologically split before derivatives readiness")
    filtered, _, filtered_split, derivatives_strategy_quality = (
        lab._filter_cross_sectional_subject_panel_for_derivatives_readiness(
            frame=filtered,
            derivatives_quality_frame=derivatives_quality_frame,
            feature_columns=feature_columns,
            derivatives_feature_quality=derivatives_feature_quality,
            strategy_entry=strategy,
            split=split,
            split_realization_contract=contract,
            data_readiness_contract=load_data_readiness_contract(),
        )
    )
    if filtered_split is None:
        raise ValueError("baseline frame lost split after derivatives readiness filtering")
    return filtered.sort_values(["timestamp_ms", "subject"]).reset_index(drop=True), derivatives_strategy_quality


def spearman_group(group: pd.DataFrame) -> float:
    cleaned = group.dropna()
    if len(cleaned) < 3:
        return float("nan")
    left = cleaned["z"].rank(method="average")
    right = cleaned["forward_return"].rank(method="average")
    if float(left.std(ddof=0)) <= 0.0 or float(right.std(ddof=0)) <= 0.0:
        return float("nan")
    value = float(left.corr(right))
    return value if math.isfinite(value) else float("nan")


def build_daily_ic_by_factor(frame: pd.DataFrame, *, feature_columns: list[str]) -> dict[str, pd.Series]:
    forward_return = pd.to_numeric(frame["target_execution_forward_return"], errors="coerce").astype("float64")
    daily: dict[str, pd.Series] = {}
    for column in lab._normalized_factor_weight_map(lab.ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS):
        if column not in feature_columns or column not in frame.columns:
            daily[column] = pd.Series(dtype="float64")
            continue
        zscore = lab._timestamp_cross_section_zscore(
            pd.to_numeric(frame[column], errors="coerce"),
            frame["timestamp_ms"],
        )
        packed = pd.DataFrame(
            {
                "timestamp_ms": pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("int64").values,
                "z": zscore.values,
                "forward_return": forward_return.values,
            }
        )
        daily[column] = (
            packed.groupby("timestamp_ms", sort=True)
            .apply(spearman_group, include_groups=False)
            .dropna()
            .astype("float64")
        )
    return daily


def weights_for_train_end(
    *,
    daily_ic_by_factor: dict[str, pd.Series],
    train_end_ms: int,
) -> dict[str, float]:
    static_weights = lab._normalized_factor_weight_map(lab.ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS)
    diagnostics: dict[str, tuple[float, float]] = {}
    abs_ir_sum = 0.0
    for column, static_weight in static_weights.items():
        daily_ic = daily_ic_by_factor.get(column, pd.Series(dtype="float64"))
        values = daily_ic.loc[daily_ic.index <= int(train_end_ms)].to_numpy(dtype="float64")
        mean_ic = float(values.mean()) if values.size else 0.0
        ic_std = float(values.std(ddof=0)) if values.size > 1 else 0.0
        ir = float(mean_ic / ic_std) if values.size >= 30 and ic_std > 1e-12 else 0.0
        diagnostics[column] = (mean_ic, ir)
        abs_ir_sum += abs(ir)
    if abs_ir_sum <= 1e-12:
        return dict(static_weights)
    weights: dict[str, float] = {}
    for column, static_weight in static_weights.items():
        mean_ic, ir = diagnostics[column]
        if mean_ic > 0.0:
            sign = 1.0
        elif mean_ic < 0.0:
            sign = -1.0
        else:
            sign = 1.0 if static_weight >= 0.0 else -1.0
        weights[column] = float(sign * abs(ir) / abs_ir_sum)
    return weights


def score_frame(frame: pd.DataFrame, *, factor_weights: dict[str, float]) -> pd.DataFrame:
    scored = frame.copy()
    scored["score"] = lab._alpha_ontology_linear_score_from_weights(scored, factor_weights=factor_weights)
    return scored


def phase_frame(frame: pd.DataFrame, *, phase_offset_days: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    timestamps = sorted(int(item) for item in frame["timestamp_ms"].drop_duplicates().tolist())
    phase = int(phase_offset_days)
    if phase < 0:
        raise ValueError(f"phase must be >= 0: {phase}")
    if phase >= len(timestamps):
        return frame.iloc[0:0].copy(), {
            "phase_offset_days": phase,
            "status": "phase_after_history",
            "available_timestamp_count": len(timestamps),
        }
    start_ms = int(timestamps[phase])
    out = frame.loc[pd.to_numeric(frame["timestamp_ms"], errors="coerce").ge(start_ms)].copy()
    return out, {
        "phase_offset_days": phase,
        "status": "ok",
        "start_timestamp_ms": start_ms,
        "start_date_utc": pd.to_datetime(start_ms, unit="ms", utc=True).date().isoformat(),
        "row_count": int(len(out)),
        "timestamp_count": int(out["timestamp_ms"].nunique()),
    }


def run_phase(
    *,
    phase: int,
    frame: pd.DataFrame,
    daily_ic_by_factor: dict[str, pd.Series],
    spec: dict[str, Any],
    contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float,
    capacity_limits: dict[str, float],
) -> tuple[dict[str, Any], pd.DataFrame]:
    phase_data, phase_audit = phase_frame(frame, phase_offset_days=phase)
    if phase_data.empty:
        return {
            "phase_offset_days": int(phase),
            "phase_status": phase_audit.get("status"),
            "window_count": 0,
            "period_count": 0,
        }, pd.DataFrame()
    constraints = dict(spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(spec.get("strategy_profile") or "")
    time_index = pd.to_datetime(phase_data["timestamp_ms"], unit="ms", utc=True)
    current_anchor = time_index.min() + timedelta(days=120)
    final_anchor = time_index.max() - timedelta(days=30)
    windows: list[dict[str, Any]] = []
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
            split_realization_contract=contract,
        )
        if not train_df.empty and not validation_df.empty and not test_df.empty:
            train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
            weights = weights_for_train_end(
                daily_ic_by_factor=daily_ic_by_factor,
                train_end_ms=train_end_ms,
            )
            scored_test = score_frame(test_df, factor_weights=weights)
            metrics = backtest_cross_sectional(
                frame=scored_test,
                constraints=constraints,
                split_realization_contract=contract,
                execution_cost_model=execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
                include_periods=True,
            )
            windows.append(
                {
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    "test_end_utc": test_end.isoformat().replace("+00:00", "Z"),
                    "periods": list(metrics.get("periods") or []),
                    **{key: value for key, value in metrics.items() if key != "periods"},
                }
            )
        current_anchor += timedelta(days=30)
    periods = extract_period_frame(candidate_label=BASELINE_LABEL, walk_forward={"windows": windows})
    annual_periods = periods_per_year(
        bar_interval_ms=int(contract["bar_interval_ms"]),
        evaluation_step_bars=int(contract["realization_step_bars"]),
    )
    perf = performance_summary(periods["net_period_return"] if not periods.empty else pd.Series(dtype="float64"), periods_per_year=annual_periods)
    sharpes = [float(window.get("sharpe", 0.0) or 0.0) for window in windows]
    data_gap_blockers = sorted(
        {
            str(item)
            for window in windows
            for item in list(window.get("data_gap_blockers") or [])
            if str(item)
        }
    )
    summary = {
        "phase_offset_days": int(phase),
        "phase_status": phase_audit.get("status"),
        "start_date_utc": phase_audit.get("start_date_utc"),
        "start_timestamp_ms": phase_audit.get("start_timestamp_ms"),
        "window_count": int(len(windows)),
        "period_count": int(len(periods)),
        "walk_forward_median_oos_sharpe": float(np.median(sharpes)) if sharpes else 0.0,
        "net_return": float(perf["net_return"]),
        "sharpe": float(perf["sharpe"]),
        "max_drawdown": float(perf["max_drawdown"]),
        "loss_period_fraction": float((periods["net_period_return"] < 0.0).mean()) if not periods.empty else 0.0,
        "mean_period_return": float(periods["net_period_return"].mean()) if not periods.empty else 0.0,
        "worst_period_return": float(periods["net_period_return"].min()) if not periods.empty else 0.0,
        "best_period_return": float(periods["net_period_return"].max()) if not periods.empty else 0.0,
        "turnover_total": float(periods["turnover"].sum()) if "turnover" in periods else 0.0,
        "max_trade_participation_rate": float(periods["trade_participation_rate"].max()) if "trade_participation_rate" in periods and not periods.empty else 0.0,
        "data_gap_blockers": data_gap_blockers,
        "data_gap_blocker_count": int(len(data_gap_blockers)),
    }
    return summary, periods.assign(phase_offset_days=int(phase))


def reconcile_phase0(
    *,
    periods: pd.DataFrame,
    fixed_set_returns_path: Path,
    tolerance: float,
) -> dict[str, Any]:
    if periods.empty:
        return {"status": "failed", "reason": "phase0_periods_empty"}
    fixed = pd.read_csv(fixed_set_returns_path)
    if BASELINE_LABEL not in fixed.columns:
        return {"status": "failed", "reason": "baseline_column_missing"}
    phase0 = periods.loc[periods["phase_offset_days"].eq(0)].copy()
    if phase0.empty:
        return {"status": "failed", "reason": "phase0_missing"}
    merged = phase0[["timestamp_ms", "net_period_return"]].merge(
        fixed[["timestamp_ms", BASELINE_LABEL]],
        on="timestamp_ms",
        how="outer",
        indicator=True,
    )
    if not merged["_merge"].eq("both").all():
        return {
            "status": "failed",
            "reason": "timestamp_set_mismatch",
            "left_only_count": int(merged["_merge"].eq("left_only").sum()),
            "right_only_count": int(merged["_merge"].eq("right_only").sum()),
        }
    diff = (
        pd.to_numeric(merged["net_period_return"], errors="coerce")
        - pd.to_numeric(merged[BASELINE_LABEL], errors="coerce")
    ).abs()
    max_abs_diff = float(diff.max()) if not diff.empty else 0.0
    return {
        "status": "passed" if max_abs_diff <= float(tolerance) else "failed",
        "period_count": int(len(merged)),
        "max_abs_period_return_diff": max_abs_diff,
        "tolerance": float(tolerance),
    }


def evaluate_robustness(metrics: pd.DataFrame, args: argparse.Namespace) -> dict[str, Any]:
    if metrics.empty:
        return {"status": "blocked", "failures": [{"code": "empty_phase_metrics"}]}
    baseline_rows = metrics.loc[metrics["phase_offset_days"].eq(0)]
    if baseline_rows.empty:
        return {"status": "blocked", "failures": [{"code": "missing_phase0"}]}
    phase0 = baseline_rows.iloc[0].to_dict()
    base_net = float(phase0.get("net_return", 0.0) or 0.0)
    base_dd = float(phase0.get("max_drawdown", 0.0) or 0.0)
    thresholds = {
        "min_net_return_ratio_vs_phase0": float(args.min_net_return_ratio_vs_phase0),
        "min_sharpe": float(args.min_sharpe),
        "max_dd_abs": float(args.max_dd_abs),
        "max_dd_delta_vs_phase0": float(args.max_dd_delta_vs_phase0),
    }
    failures: list[dict[str, Any]] = []
    phase_summaries: list[dict[str, Any]] = []
    for _, row in metrics.sort_values("phase_offset_days").iterrows():
        phase = int(row["phase_offset_days"])
        net_return = float(row.get("net_return", 0.0) or 0.0)
        sharpe = float(row.get("sharpe", 0.0) or 0.0)
        max_dd = float(row.get("max_drawdown", 0.0) or 0.0)
        ratio = None if abs(base_net) <= 1e-12 else net_return / base_net
        summary = {
            "phase_offset_days": phase,
            "net_return": net_return,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "net_return_ratio_vs_phase0": ratio,
            "max_drawdown_delta_vs_phase0": max_dd - base_dd,
        }
        phase_summaries.append(summary)
        if phase == 0:
            continue
        if int(row.get("data_gap_blocker_count", 0) or 0) > 0:
            failures.append({"code": "phase_data_gap_blocker", **summary})
        if net_return <= 0.0:
            failures.append({"code": "phase_non_positive_net_return", **summary})
        if ratio is not None and ratio < thresholds["min_net_return_ratio_vs_phase0"]:
            failures.append({"code": "phase_net_return_ratio_too_low", **summary})
        if sharpe < thresholds["min_sharpe"]:
            failures.append({"code": "phase_sharpe_too_low", **summary})
        if max_dd > thresholds["max_dd_abs"]:
            failures.append({"code": "phase_max_drawdown_abs_too_high", **summary})
        if max_dd - base_dd > thresholds["max_dd_delta_vs_phase0"]:
            failures.append({"code": "phase_max_drawdown_delta_too_high", **summary})
    nonzero = [item for item in phase_summaries if int(item["phase_offset_days"]) != 0]
    return {
        "status": "passed" if not failures else "failed",
        "thresholds": thresholds,
        "failure_count": int(len(failures)),
        "failures": failures,
        "phase_summaries": phase_summaries,
        "worst_nonzero_phase_by_net": min(nonzero, key=lambda item: item["net_return"]) if nonzero else None,
        "best_nonzero_phase_by_net": max(nonzero, key=lambda item: item["net_return"]) if nonzero else None,
    }


def render_markdown(payload: dict[str, Any], metrics: pd.DataFrame) -> str:
    robustness = dict(payload.get("robustness") or {})
    reconciliation = dict(payload.get("phase0_reconciliation") or {})
    lines = [
        "# v5_rw_bridge_no_overlay_h10d 12-factor 10d phase sensitivity",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- baseline_label: `{BASELINE_LABEL}`",
        f"- strategy_id: `{BASELINE_STRATEGY_ID}`",
        f"- source_features: `{payload['inputs']['features_path']}`",
        f"- phase0_reconciliation: `{reconciliation.get('status')}` max_abs_diff=`{reconciliation.get('max_abs_period_return_diff')}`",
        f"- robustness_status: `{robustness.get('status')}`",
        "",
        "## Interpretation",
        "",
    ]
    if robustness.get("status") == "passed":
        lines.append("The original 12-factor 10d baseline is robust to 0..9 day rebalance-anchor shifts under this gate.")
    else:
        lines.append("The original 12-factor 10d baseline is not robust to all 0..9 day rebalance-anchor shifts under this gate.")
    worst = robustness.get("worst_nonzero_phase_by_net")
    if isinstance(worst, dict):
        lines.append(
            "Worst non-zero phase by net return is phase `{phase}` with net `{net:.6f}`, sharpe `{sharpe:.6f}`, max DD `{dd:.6f}`, ratio vs phase0 `{ratio}`.".format(
                phase=worst.get("phase_offset_days"),
                net=float(worst.get("net_return", 0.0) or 0.0),
                sharpe=float(worst.get("sharpe", 0.0) or 0.0),
                dd=float(worst.get("max_drawdown", 0.0) or 0.0),
                ratio=worst.get("net_return_ratio_vs_phase0"),
            )
        )
    lines.extend(
        [
            "",
            "## Phase Metrics",
            "",
            "| Phase | Start | Periods | Net | Ratio vs phase0 | Sharpe | Max DD | WF median | Loss frac |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in metrics.sort_values("phase_offset_days").iterrows():
        ratio = row.get("net_return_ratio_vs_phase0")
        ratio_text = "" if pd.isna(ratio) else f"{float(ratio):.3f}"
        lines.append(
            f"| {int(row['phase_offset_days'])} | {row.get('start_date_utc', '')} | {int(row.get('period_count', 0) or 0)} | "
            f"{float(row.get('net_return', 0.0) or 0.0):.6f} | {ratio_text} | "
            f"{float(row.get('sharpe', 0.0) or 0.0):.6f} | {float(row.get('max_drawdown', 0.0) or 0.0):.6f} | "
            f"{float(row.get('walk_forward_median_oos_sharpe', 0.0) or 0.0):.6f} | "
            f"{float(row.get('loss_period_fraction', 0.0) or 0.0):.3f} |"
        )
    failures = list(robustness.get("failures") or [])
    lines.extend(["", "## Gate Failures", ""])
    if not failures:
        lines.append("- None.")
    else:
        for item in failures[:30]:
            lines.append(
                f"- `{item.get('code')}` phase=`{item.get('phase_offset_days')}` "
                f"net=`{item.get('net_return')}` sharpe=`{item.get('sharpe')}` "
                f"max_dd=`{item.get('max_drawdown')}` ratio=`{item.get('net_return_ratio_vs_phase0')}`"
            )
        if len(failures) > 30:
            lines.append(f"- ... truncated `{len(failures) - 30}` additional failures; see JSON.")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- summary_json: `{payload['artifacts']['summary_json']}`",
            f"- phase_metrics_csv: `{payload['artifacts']['phase_metrics_csv']}`",
            f"- phase_period_returns_csv: `{payload['artifacts']['phase_period_returns_csv']}`",
            "",
            "## Method Notes",
            "",
            "- This is a research replay only; it does not touch live trading code or Binance APIs.",
            "- The runner holds the original experiment spec, 12 factor list, train-only signed-IR weight formula, WFO shape, execution cost model, and `liquid_perp_core_20` universe fixed.",
            "- Phase means the first eligible daily timestamp is shifted by `phase_offset_days`; subsequent WFO anchors follow from that shifted start.",
            "- Phase0 is reconciled to the archived fixed-set aligned period returns before interpreting the sweep.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.expanduser().resolve()
    experiment_root = args.experiment_root.expanduser().resolve()
    features_path = args.features.expanduser().resolve()
    feature_manifest_path = args.feature_manifest.expanduser().resolve()
    fixed_set_returns_path = args.fixed_set_returns.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    doc_path = args.doc_path.expanduser().resolve()

    strategy = load_strategy(manifest_path)
    spec = read_experiment_spec(experiment_root)
    feature_manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
    contract = resolve_split_realization_contract(
        contract=dict(spec.get("split_realization_contract") or feature_manifest.get("split_realization_contract") or {}),
        shape=str(spec.get("shape") or "cross_sectional"),
        bar_interval_ms=int(spec.get("bar_interval_ms") or 86_400_000),
    )
    frame, derivatives_strategy_quality = read_filtered_frame(
        features_path=features_path,
        strategy=strategy,
        spec=spec,
        contract=contract,
    )
    feature_columns = list(spec.get("feature_columns") or strategy.get("required_feature_columns") or [])
    daily_ic_by_factor = build_daily_ic_by_factor(frame, feature_columns=feature_columns)
    validation_contract = load_validation_contract()
    execution_cost_model = resolve_execution_cost_model(contract=load_execution_cost_model(), scenario="base")
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    capacity_limits = execution_capacity_limits(validation_contract)

    phase_rows: list[dict[str, Any]] = []
    period_frames: list[pd.DataFrame] = []
    for phase in [int(item) for item in args.phases]:
        row, periods = run_phase(
            phase=phase,
            frame=frame,
            daily_ic_by_factor=daily_ic_by_factor,
            spec=spec,
            contract=contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        phase_rows.append(row)
        if not periods.empty:
            period_frames.append(periods)
    phase_metrics = pd.DataFrame(phase_rows).sort_values("phase_offset_days").reset_index(drop=True)
    phase0_net = float(
        phase_metrics.loc[phase_metrics["phase_offset_days"].eq(0), "net_return"].iloc[0]
    ) if bool(phase_metrics["phase_offset_days"].eq(0).any()) else 0.0
    if abs(phase0_net) > 1e-12:
        phase_metrics["net_return_ratio_vs_phase0"] = pd.to_numeric(
            phase_metrics["net_return"],
            errors="coerce",
        ) / phase0_net
    else:
        phase_metrics["net_return_ratio_vs_phase0"] = np.nan
    periods_all = pd.concat(period_frames, ignore_index=True) if period_frames else pd.DataFrame()
    reconciliation = reconcile_phase0(
        periods=periods_all,
        fixed_set_returns_path=fixed_set_returns_path,
        tolerance=float(args.baseline_tolerance),
    )
    robustness = evaluate_robustness(phase_metrics, args)
    if reconciliation.get("status") != "passed":
        robustness = dict(robustness)
        robustness["status"] = "blocked"
        robustness.setdefault("failures", [])
        robustness["failures"] = [
            {"code": "phase0_reconciliation_failed", **reconciliation},
            *list(robustness.get("failures") or []),
        ]
        robustness["failure_count"] = int(len(robustness["failures"]))

    output_root.mkdir(parents=True, exist_ok=True)
    phase_metrics_csv = output_root / "phase_metrics.csv"
    phase_periods_csv = output_root / "phase_period_returns.csv"
    summary_json = output_root / "summary.json"
    phase_metrics.to_csv(phase_metrics_csv, index=False)
    periods_all.to_csv(phase_periods_csv, index=False)
    payload = {
        "schema": "v5_rw_baseline_rebalance_phase_sensitivity.v1",
        "generated_at_utc": utc_now_iso(),
        "baseline_label": BASELINE_LABEL,
        "strategy_id": BASELINE_STRATEGY_ID,
        "inputs": {
            "manifest_path": str(manifest_path),
            "experiment_root": str(experiment_root),
            "features_path": str(features_path),
            "feature_manifest_path": str(feature_manifest_path),
            "fixed_set_returns_path": str(fixed_set_returns_path),
            "feature_hash": feature_manifest.get("feature_hash"),
            "dataset_fingerprint": feature_manifest.get("dataset_fingerprint"),
        },
        "filtered_frame": {
            "row_count": int(len(frame)),
            "subject_count": int(frame["subject"].nunique()),
            "timestamp_count": int(frame["timestamp_ms"].nunique()),
            "min_timestamp_utc": pd.to_datetime(int(frame["timestamp_ms"].min()), unit="ms", utc=True).isoformat().replace("+00:00", "Z"),
            "max_timestamp_utc": pd.to_datetime(int(frame["timestamp_ms"].max()), unit="ms", utc=True).isoformat().replace("+00:00", "Z"),
            "derivatives_strategy_quality": derivatives_strategy_quality,
        },
        "contract": {
            "split_realization_contract": contract,
            "execution_cost_model": execution_cost_model,
            "reference_capital_usd": reference_capital_usd,
            "capacity_limits": capacity_limits,
        },
        "phase0_reconciliation": reconciliation,
        "robustness": robustness,
        "artifacts": {
            "summary_json": str(summary_json),
            "phase_metrics_csv": str(phase_metrics_csv),
            "phase_period_returns_csv": str(phase_periods_csv),
            "doc_path": str(doc_path),
        },
        "phase_metrics": phase_metrics.to_dict(orient="records"),
    }
    write_json(summary_json, json_safe(payload))
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_markdown(payload, phase_metrics), encoding="utf-8")
    print(json.dumps(json_safe(payload), ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if robustness.get("status") in {"passed", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
