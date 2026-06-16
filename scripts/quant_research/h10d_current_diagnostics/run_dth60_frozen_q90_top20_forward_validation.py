from __future__ import annotations

import argparse
import json
import sys
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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_v5_rw_baseline_rebalance_phase_sensitivity as v5_phase  # noqa: E402
import run_dth60_overlay_robustness_validation as robust  # noqa: E402
import run_multiphase_factor_drawdown_ablation as factor_ablation  # noqa: E402
import run_portfolio_construction_experiment as portfolio_diag  # noqa: E402

from enhengclaw.quant_research.execution_backtest import backtest_cross_sectional, filter_cross_sectional_execution_frame  # noqa: E402
from enhengclaw.quant_research.horizon_metrics import SHARPE_METRIC_CONVENTION_VERSION  # noqa: E402
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, _apply_universe_filter, _experiment_directory_name, _resolved_execution_cost_models  # noqa: E402
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import resolve_split_realization_contract  # noqa: E402
from enhengclaw.quant_research.validation_contract import execution_capacity_limits, validation_contract_reference_capital_usd  # noqa: E402


BASELINE_LABEL = robust.BASELINE_LABEL
EFFECTIVE_BASELINE_LABEL = robust.EFFECTIVE_BASELINE_LABEL
BASELINE_EXPERIMENT_ID = robust.BASELINE_EXPERIMENT_ID
BASELINE_VARIANT_LABEL = robust.BASELINE_VARIANT_LABEL
FROZEN_LABEL = "dth60_hybrid_shock_q90_or_crowded_top20_zero"
H10D_VALIDATION_CONTRACT_PATH = robust.H10D_VALIDATION_CONTRACT_PATH
TARGET_FACTOR = robust.TARGET_FACTOR
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-06-03"
    / "v5_rw_dth60_frozen_q90_top20_forward_validation_2025_10_01"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run no-tuning forward-style validation for the preregistered "
            "distance_to_high_60 q90/top20 hybrid overlay candidate."
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


def build_definitions() -> list[dict[str, Any]]:
    return [
        {
            "label": BASELINE_VARIANT_LABEL,
            "kind": "baseline",
            "condition": "none",
            "shock_quantile": None,
            "crowded_top_fraction": None,
            "target_multiplier": 1.0,
            "description": "No score-layer factor overlay.",
        },
        {
            "label": FROZEN_LABEL,
            "kind": "frozen_preregistered_overlay",
            "condition": "shock_quantile_or_near_high_top_trader_crowded",
            "shock_quantile": 0.90,
            "crowded_top_fraction": 0.20,
            "target_multiplier": 0.0,
            "description": (
                "Frozen preregistered candidate: remove distance_to_high_60 when train-window "
                "shock/co-jump q90 fires or near-high rows are top-trader crowded at top20."
            ),
        },
    ]


def pass_checks(slice_summary: pd.DataFrame) -> dict[str, Any]:
    holdout = slice_summary.loc[slice_summary["label"].eq(FROZEN_LABEL) & slice_summary["slice"].eq("untouched_holdout")]
    full = slice_summary.loc[slice_summary["label"].eq(FROZEN_LABEL) & slice_summary["slice"].eq("full_oos")]
    if holdout.empty or full.empty:
        return {"status": "blocked", "reasons": ["missing frozen candidate summary rows"]}
    holdout_row = holdout.iloc[0]
    full_row = full.iloc[0]
    checks = {
        "holdout_return_delta_positive": bool(float(holdout_row["delta_cumulative_return_vs_baseline"]) > 0.0),
        "holdout_sharpe_delta_positive": bool(float(holdout_row["delta_h10d_equivalent_sharpe_vs_baseline"]) > 0.0),
        "holdout_max_drawdown_not_worse": bool(float(holdout_row["delta_max_drawdown_vs_baseline"]) <= 0.0),
        "full_oos_max_drawdown_not_worse": bool(float(full_row["delta_max_drawdown_vs_baseline"]) <= 0.0),
        "holdout_capacity_breach_zero": bool(int(holdout_row["capacity_breach_count"]) == 0),
        "full_oos_capacity_breach_zero": bool(int(full_row["capacity_breach_count"]) == 0),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "research_pass_for_paper_watch" if not failed else "research_fail_or_watch_only",
        "checks": checks,
        "failed_checks": failed,
    }


def render_markdown(path: Path, payload: dict[str, Any], slice_summary: pd.DataFrame) -> None:
    lines = [
        "# Frozen DTH60 Q90 Top20 Forward-Style Validation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Effective research baseline: `{payload['effective_research_baseline']}`",
        f"- Frozen candidate: `{FROZEN_LABEL}`",
        f"- Holdout start: `{payload['holdout_start']}`",
        "- Boundary: no parameter grid, no tuning, no live/paper/remote mutation.",
        f"- Result status: `{payload['pass_checks']['status']}`",
        "- Sharpe convention: `quant_h10d_overlap_adjusted_sharpe.v1` h10d-equivalent Sharpe.",
        "",
        "## Frozen Rule",
        "",
        "- shock/co-jump threshold: train-window q90",
        "- near-high threshold: `rank_pct(distance_to_high_60) >= 0.75`",
        "- crowded threshold: `rank_pct(coinglass_top_trader_long_pct_smooth_5) >= 0.80`",
        "- target factor multiplier when triggered: `0.0`",
        "",
        "## Key Metrics",
        "",
        "| label | slice | periods | cum ret | delta ret | h10d-eq Sharpe | delta Sharpe | max DD | delta DD | breaches |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label in (BASELINE_VARIANT_LABEL, FROZEN_LABEL):
        for slice_name in ("selection_ex_episode_pre_holdout", "untouched_holdout", "full_oos", "episode"):
            row = slice_summary.loc[slice_summary["label"].eq(label) & slice_summary["slice"].eq(slice_name)]
            if row.empty:
                continue
            item = row.iloc[0]
            lines.append(
                "| `{label}` | `{slice}` | {n} | {ret:.6f} | {dret:.6f} | {sharpe:.6f} | {dsharpe:.6f} | {dd:.6f} | {ddd:.6f} | {breaches} |".format(
                    label=label,
                    slice=slice_name,
                    n=int(item["period_count"]),
                    ret=float(item["cumulative_return"]),
                    dret=float(item["delta_cumulative_return_vs_baseline"]),
                    sharpe=float(item["h10d_equivalent_sharpe"]),
                    dsharpe=float(item["delta_h10d_equivalent_sharpe_vs_baseline"]),
                    dd=float(item["max_drawdown"]),
                    ddd=float(item["delta_max_drawdown_vs_baseline"]),
                    breaches=int(item["capacity_breach_count"]),
                )
            )
    lines.extend(
        [
            "",
            "## Pass Checks",
            "",
        ]
    )
    for name, passed in sorted(dict(payload["pass_checks"].get("checks") or {}).items()):
        lines.append(f"- `{name}`: `{passed}`")
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
    labels = [str(item["label"]) for item in definitions]
    phase_periods_by_label: dict[str, list[pd.DataFrame]] = {label: [] for label in labels}
    window_rows: list[dict[str, Any]] = []
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
            thresholds = robust.robustness_thresholds(train_df)
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
                scored, overlay_stats = robust.score_frame_with_robust_overlay(
                    test_df,
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
                period_frame = factor_ablation.period_frame_from_metrics(label=label, phase=phase, metrics=metrics)
                if not period_frame.empty:
                    phase_periods_by_label[label].append(period_frame)
                window_rows.append(
                    {
                        "label": label,
                        "kind": str(definition["kind"]),
                        "condition": str(definition["condition"]),
                        "shock_quantile": definition.get("shock_quantile"),
                        "crowded_top_fraction": definition.get("crowded_top_fraction"),
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
    period_frames: list[pd.DataFrame] = []
    for label in labels:
        periods = factor_ablation.aggregate_variant_periods(
            label=label,
            sleeve_periods=phase_periods_by_label[label],
            trade_participation_cap=trade_cap,
            inventory_participation_cap=inventory_cap,
        )
        periods_by_label[label] = periods
        if not periods.empty:
            period_frames.append(periods)

    slice_summary = robust.build_slice_summary(
        labels=labels,
        periods_by_label=periods_by_label,
        split_contract=split_contract,
        episode_start=str(args.episode_start),
        episode_end=str(args.episode_end),
        holdout_start=str(args.holdout_start),
    )
    checks = pass_checks(slice_summary)

    definitions_json = output_root / "forward_definitions.json"
    threshold_csv = output_root / "forward_train_thresholds.csv"
    window_csv = output_root / "forward_test_windows.csv"
    slice_summary_csv = output_root / "forward_slice_summary.csv"
    period_returns_csv = output_root / "period_returns_long.csv"
    write_json(definitions_json, {"definitions": definitions, "target_factor": TARGET_FACTOR})
    pd.DataFrame(threshold_rows).to_csv(threshold_csv, index=False)
    pd.DataFrame(window_rows).to_csv(window_csv, index=False)
    slice_summary.to_csv(slice_summary_csv, index=False)
    pd.concat(period_frames, ignore_index=True).to_csv(period_returns_csv, index=False)

    payload = {
        "status": "computed",
        "generated_at_utc": utc_now_iso(),
        "score_parent_label": BASELINE_LABEL,
        "effective_research_baseline": EFFECTIVE_BASELINE_LABEL,
        "target_factor": TARGET_FACTOR,
        "baseline_variant_label": BASELINE_VARIANT_LABEL,
        "frozen_candidate_label": FROZEN_LABEL,
        "baseline_experiment_id": str(args.baseline_experiment_id),
        "feature_path": str(feature_path),
        "episode_start": str(args.episode_start),
        "episode_end": str(args.episode_end),
        "holdout_start": str(args.holdout_start),
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
            "variant_count": int(len(definitions)),
            "test_window_row_count": int(len(window_rows)),
        },
        "pass_checks": json_safe(checks),
        "slice_summary": json_safe(slice_summary.to_dict(orient="records")),
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "summary_md": str(output_root / "summary.md"),
            "forward_definitions_json": str(definitions_json),
            "forward_slice_summary_csv": str(slice_summary_csv),
            "forward_test_windows_csv": str(window_csv),
            "forward_train_thresholds_csv": str(threshold_csv),
            "period_returns_long_csv": str(period_returns_csv),
        },
        "interpretation_boundary": (
            "No-tuning forward-style validation for the preregistered q90/top20 overlay. "
            "Only baseline and the frozen candidate are evaluated. Passing this packet is "
            "research evidence for paper-watch status only; it is not live approval."
        ),
    }
    write_json(output_root / "summary.json", payload)
    render_markdown(output_root / "summary.md", payload, slice_summary)
    print(json.dumps(json_safe({"status": "computed", "summary_json": str(output_root / "summary.json")}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
