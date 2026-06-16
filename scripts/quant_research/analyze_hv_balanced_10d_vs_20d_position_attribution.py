from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import enhengclaw.quant_research.binance_canonical_h10d as h10d  # noqa: E402
from enhengclaw.quant_research.binance_canonical_h10d import _run_backtest  # noqa: E402
from enhengclaw.quant_research.execution_backtest import (  # noqa: E402
    _cross_sectional_target_weights,
    _drawdown_throttle_multiplier,
    _next_fill_offset,
    _price_path_return,
    _scale_cross_sectional_turnover,
    _trade_costs,
    filter_cross_sectional_execution_frame,
)


SENSITIVITY_SCRIPT = SCRIPT_DIR / "analyze_hv_balanced_rebalance_interval_sensitivity.py"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "hv_balanced_10d_vs_20d_attribution_20260518"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "hv_balanced_10d_vs_20d_position_attribution_2026_05_18.md"
)
INTERVALS = (10, 20)
CONTRIBUTION_COLUMNS = (
    "gross_contribution",
    "funding_cost_return",
    "net_before_trade_cost_contribution",
)
COUNT_COLUMNS = ("position_count", "rebalance_count")
MEAN_COLUMNS = ("mean_underlying_forward_return", "mean_abs_weight", "profitable_position_rate")


def parse_args() -> argparse.Namespace:
    defaults = _load_sensitivity_module()
    parser = argparse.ArgumentParser(
        description=(
            "Attribute hv_balanced 20d rebalance outperformance versus frozen 10d control by "
            "year, symbol, and long/short side."
        )
    )
    parser.add_argument("--config", type=Path, default=defaults.DEFAULT_HV_BALANCED_CONFIG_PATH)
    parser.add_argument("--store-root", type=Path, default=None)
    parser.add_argument("--funding-root", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--scenario", choices=["base", "stress"], default="base")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--baseline-report", type=Path, default=defaults.DEFAULT_FROZEN_REPORT)
    parser.add_argument("--frozen-row-membership", type=Path, default=defaults.DEFAULT_FROZEN_ROW_MEMBERSHIP)
    parser.add_argument("--no-frozen-row-alignment", action="store_true")
    parser.add_argument("--baseline-tolerance", type=float, default=1e-8)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    return parser.parse_args()


def _load_sensitivity_module() -> Any:
    spec = importlib.util.spec_from_file_location("hv_rebalance_sensitivity", SENSITIVITY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import sensitivity runner from {SENSITIVITY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else (ROOT / path).resolve()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
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
    if pd.isna(value) if not isinstance(value, (str, bytes, dict, list, tuple)) else False:
        return None
    return value


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    sensitivity = _load_sensitivity_module()
    output_root = resolve_repo_path(args.output_root)
    doc_path = resolve_repo_path(args.doc_path)
    baseline_report = resolve_repo_path(args.baseline_report)
    store_root = (
        Path(args.store_root).resolve()
        if args.store_root
        else sensitivity.default_store_root_from_baseline(baseline_report)
    )
    partition_path_compatibility = sensitivity.install_symbol_partition_compatibility_patch()
    frozen_row_alignment = sensitivity.install_frozen_feature_row_alignment_patch(
        args.frozen_row_membership,
        disabled=bool(args.no_frozen_row_alignment),
    )
    fixed = sensitivity.load_fixed_scored_frame(args, store_root=store_root)
    scored_frame = fixed["scored_frame"]
    base_config = fixed["config"]
    if scored_frame.empty:
        raise RuntimeError("scored_frame is empty; cannot run 10d vs 20d attribution")

    runs: dict[int, dict[str, Any]] = {}
    for interval in INTERVALS:
        run_config = sensitivity.interval_config(base_config, interval)
        metrics = _run_backtest(scored_frame, config=run_config, scenario=args.scenario, include_periods=True)
        fast_attribution = build_fast_interval_attribution(scored_frame, config=run_config, scenario=args.scenario)
        runs[interval] = {
            "config": run_config,
            "metrics": metrics,
            "positions": fast_attribution["positions"],
            "attribution_summary": fast_attribution["summary"],
            "ledger": fast_attribution["ledger"],
            "ledger_summary": fast_attribution["ledger_summary"],
            "fast_periods": fast_attribution["periods"],
            "periods": pd.DataFrame(metrics.get("periods") or []),
        }

    comparisons = build_comparisons(runs)
    baseline_reproduction = sensitivity.compare_baseline(
        ten_day_metrics=runs[10]["metrics"],
        baseline_report_path=baseline_report,
        tolerance=float(args.baseline_tolerance),
    )
    dataset_reproduction = sensitivity.compare_dataset_reproduction(
        current_manifest=fixed["dataset_manifest"],
        baseline_report_path=baseline_report,
    )
    blockers = list(fixed.get("blockers") or [])
    for interval in INTERVALS:
        gaps = list(runs[interval]["metrics"].get("data_gap_blockers") or [])
        if gaps:
            blockers.append(
                {
                    "code": "interval_execution_data_gap_blockers",
                    "interval_days": int(interval),
                    "data_gap_blocker_count": len(gaps),
                    "sample": gaps[:10],
                }
            )
    if baseline_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_10d_baseline_reproduction_failed", "detail": baseline_reproduction})
    if dataset_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_dataset_reproduction_failed", "detail": dataset_reproduction})
    fast_reconciliation = comparisons["fast_period_reconciliation"]
    if str(fast_reconciliation.get("status")) != "passed":
        blockers.append({"code": "fast_attribution_period_reconciliation_failed", "detail": fast_reconciliation})

    artifact_paths = {
        "summary_json": str(output_root / "summary.json"),
        "position_attribution_h10d_csv": str(output_root / "position_attribution_h10d.csv"),
        "position_attribution_h20d_csv": str(output_root / "position_attribution_h20d.csv"),
        "paper_shadow_ledger_h10d_csv": str(output_root / "paper_shadow_ledger_h10d.csv"),
        "paper_shadow_ledger_h20d_csv": str(output_root / "paper_shadow_ledger_h20d.csv"),
        "period_comparison_by_year_csv": str(output_root / "period_comparison_by_year.csv"),
        "position_comparison_by_year_side_csv": str(output_root / "position_comparison_by_year_side.csv"),
        "position_comparison_by_symbol_side_csv": str(output_root / "position_comparison_by_symbol_side.csv"),
        "position_comparison_by_symbol_year_side_csv": str(output_root / "position_comparison_by_symbol_year_side.csv"),
        "top_20d_advantage_symbol_year_side_csv": str(output_root / "top_20d_advantage_symbol_year_side.csv"),
        "top_10d_advantage_symbol_year_side_csv": str(output_root / "top_10d_advantage_symbol_year_side.csv"),
        "execution_cost_comparison_by_side_csv": str(output_root / "execution_cost_comparison_by_side.csv"),
        "paired_mtm_10d_20d_csv": str(output_root / "paired_mtm_10d_20d.csv"),
        "markdown_report": str(doc_path),
    }
    summary = {
        "schema": "hv_balanced_10d_vs_20d_position_attribution.v1",
        "generated_at_utc": utc_now_iso(),
        "status": "passed" if not blockers else "blocked",
        "scenario": args.scenario,
        "method": (
            "Rebuild frozen hv_balanced scored frame once, sweep only target_horizon_bars=10/20, "
            "then compare held-position gross plus funding-cost attribution by year/symbol/side. "
            "Fee and slippage are reconciled separately from paper-shadow ledgers."
        ),
        "config_path": fixed["config_path"],
        "as_of": fixed["as_of"],
        "funding_root": fixed["funding_root"],
        "score_frame_reused_across_intervals": True,
        "scored_row_count": int(len(scored_frame)),
        "dataset_manifest": fixed["dataset_manifest"],
        "partition_path_compatibility": partition_path_compatibility,
        "frozen_row_alignment": frozen_row_alignment,
        "dataset_reproduction": dataset_reproduction,
        "baseline_reproduction": baseline_reproduction,
        "metric_bridge_20d_minus_10d": comparisons["metric_bridge"],
        "position_reconciliation": comparisons["position_reconciliation"],
        "fast_period_reconciliation": fast_reconciliation,
        "top_20d_advantage_by_year_side": _records(
            comparisons["year_side"].sort_values("net_before_trade_cost_contribution_delta_20d_minus_10d", ascending=False).head(8)
        ),
        "top_20d_advantage_by_symbol_side": _records(
            comparisons["symbol_side"].sort_values("net_before_trade_cost_contribution_delta_20d_minus_10d", ascending=False).head(12)
        ),
        "top_20d_advantage_by_symbol_year_side": _records(comparisons["top_20d_advantage"]),
        "top_10d_advantage_by_symbol_year_side": _records(comparisons["top_10d_advantage"]),
        "blockers": blockers,
        "artifact_paths": artifact_paths,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    runs[10]["positions"].to_csv(output_root / "position_attribution_h10d.csv", index=False)
    runs[20]["positions"].to_csv(output_root / "position_attribution_h20d.csv", index=False)
    runs[10]["ledger"].to_csv(output_root / "paper_shadow_ledger_h10d.csv", index=False)
    runs[20]["ledger"].to_csv(output_root / "paper_shadow_ledger_h20d.csv", index=False)
    comparisons["period_year"].to_csv(output_root / "period_comparison_by_year.csv", index=False)
    comparisons["year_side"].to_csv(output_root / "position_comparison_by_year_side.csv", index=False)
    comparisons["symbol_side"].to_csv(output_root / "position_comparison_by_symbol_side.csv", index=False)
    comparisons["symbol_year_side"].to_csv(output_root / "position_comparison_by_symbol_year_side.csv", index=False)
    comparisons["top_20d_advantage"].to_csv(output_root / "top_20d_advantage_symbol_year_side.csv", index=False)
    comparisons["top_10d_advantage"].to_csv(output_root / "top_10d_advantage_symbol_year_side.csv", index=False)
    comparisons["execution_cost_side"].to_csv(output_root / "execution_cost_comparison_by_side.csv", index=False)
    comparisons["paired_mtm"].to_csv(output_root / "paired_mtm_10d_20d.csv", index=False)
    write_json(output_root / "summary.json", summary)
    write_report(doc_path=doc_path, summary=summary, comparisons=comparisons)
    return summary


def build_comparisons(runs: dict[int, dict[str, Any]]) -> dict[str, Any]:
    metrics10 = dict(runs[10]["metrics"])
    metrics20 = dict(runs[20]["metrics"])
    metric_bridge = {
        "net_return_h10d": float(metrics10.get("net_return", 0.0) or 0.0),
        "net_return_h20d": float(metrics20.get("net_return", 0.0) or 0.0),
        "net_return_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "net_return"),
        "gross_return_before_costs_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "gross_return_before_costs"),
        "fee_cost_return_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "fee_cost_return"),
        "slippage_cost_return_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "slippage_cost_return"),
        "funding_cost_return_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "funding_cost_return"),
        "turnover_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "turnover"),
        "trade_count_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "trade_count"),
        "rebalance_count_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "rebalance_count"),
        "max_drawdown_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "max_drawdown"),
        "sharpe_delta_20d_minus_10d": _metric_delta(metrics20, metrics10, "sharpe"),
    }
    metric_bridge["arithmetic_gross_minus_cost_delta_20d_minus_10d"] = (
        metric_bridge["gross_return_before_costs_delta_20d_minus_10d"]
        - metric_bridge["fee_cost_return_delta_20d_minus_10d"]
        - metric_bridge["slippage_cost_return_delta_20d_minus_10d"]
        - metric_bridge["funding_cost_return_delta_20d_minus_10d"]
    )

    pos10 = runs[10]["positions"]
    pos20 = runs[20]["positions"]
    year_side = compare_attribution(pos10, pos20, ["year", "side"])
    symbol_side = compare_attribution(pos10, pos20, ["subject", "usdm_symbol", "side"])
    symbol_year_side = compare_attribution(pos10, pos20, ["year", "subject", "usdm_symbol", "side"])
    top_20d = symbol_year_side.sort_values(
        "net_before_trade_cost_contribution_delta_20d_minus_10d",
        ascending=False,
    ).head(30)
    top_10d = symbol_year_side.sort_values(
        "net_before_trade_cost_contribution_delta_20d_minus_10d",
        ascending=True,
    ).head(30)

    period_year = compare_period_year(runs[10]["periods"], runs[20]["periods"])
    execution_cost_side = compare_execution_costs(runs[10]["ledger"], runs[20]["ledger"])
    paired_mtm = build_paired_mtm(runs[10]["periods"], runs[20]["periods"])
    position_reconciliation = build_position_reconciliation(runs, metric_bridge)
    fast_period_reconciliation = build_fast_period_reconciliation(runs)
    return {
        "metric_bridge": metric_bridge,
        "position_reconciliation": position_reconciliation,
        "fast_period_reconciliation": fast_period_reconciliation,
        "year_side": year_side,
        "symbol_side": symbol_side,
        "symbol_year_side": symbol_year_side,
        "top_20d_advantage": top_20d,
        "top_10d_advantage": top_10d,
        "period_year": period_year,
        "execution_cost_side": execution_cost_side,
        "paired_mtm": paired_mtm,
    }


def build_fast_period_reconciliation(runs: dict[int, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    status = "passed"
    tolerance = 1e-10
    for interval in INTERVALS:
        official = runs[interval]["periods"].copy()
        fast = runs[interval]["fast_periods"].copy()
        if official.empty or fast.empty:
            status = "blocked"
            rows.append({"interval_days": interval, "status": "missing_periods"})
            continue
        official["timestamp_ms"] = pd.to_numeric(official["timestamp_ms"], errors="coerce").astype("Int64")
        fast["timestamp_ms"] = pd.to_numeric(fast["timestamp_ms"], errors="coerce").astype("Int64")
        merged = official.merge(fast, on="timestamp_ms", how="outer", suffixes=("_official", "_fast"))
        row: dict[str, Any] = {
            "interval_days": int(interval),
            "official_period_count": int(len(official)),
            "fast_period_count": int(len(fast)),
            "merged_period_count": int(len(merged)),
        }
        for metric in (
            "net_period_return",
            "gross_return_before_costs",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "turnover",
        ):
            left = pd.to_numeric(merged.get(f"{metric}_official"), errors="coerce").fillna(0.0)
            right = pd.to_numeric(merged.get(f"{metric}_fast"), errors="coerce").fillna(0.0)
            delta = right - left
            row[f"{metric}_sum_delta_fast_minus_official"] = float(delta.sum())
            row[f"{metric}_max_abs_delta_fast_minus_official"] = float(delta.abs().max()) if not delta.empty else 0.0
        if (
            row["official_period_count"] != row["fast_period_count"]
            or row["net_period_return_max_abs_delta_fast_minus_official"] > tolerance
            or row["gross_return_before_costs_max_abs_delta_fast_minus_official"] > tolerance
            or row["funding_cost_return_max_abs_delta_fast_minus_official"] > tolerance
        ):
            row["status"] = "blocked"
            status = "blocked"
        else:
            row["status"] = "passed"
        rows.append(row)
    return {"status": status, "tolerance": tolerance, "intervals": rows}


def build_fast_interval_attribution(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any],
    scenario: str,
) -> dict[str, Any]:
    constraints = dict(config.get("strategy_profile") or {})
    cost_model = h10d.resolve_execution_cost_model(scenario=scenario)
    cost_model["require_perp_inventory_open_interest"] = False
    execution_venue = str(constraints.get("execution_venue") or ("spot" if constraints.get("spot_only") else "perp"))
    reference_capital_usd = float(config.get("reference_capital_usd", 1_000_000.0) or 1_000_000.0)
    capacity_limits = dict(config.get("capacity_limits") or {})
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return {
            "positions": pd.DataFrame(),
            "ledger": pd.DataFrame(),
            "periods": pd.DataFrame(),
            "summary": {"status": "empty"},
            "ledger_summary": {"status": "empty"},
        }
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    split_contract = h10d._split_contract(config)
    evaluation_step_bars = max(int(split_contract.get("realization_step_bars", 0) or 0), 1)
    if "realization_step_bars" not in split_contract:
        target_horizon = int(split_contract.get("target_horizon_bars", 10) or 10)
        evaluation_step_bars = max(target_horizon, 1)
    timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
    decision_timestamp_indices = list(range(0, len(timestamps), evaluation_step_bars))
    latency_bars = int(cost_model["latency_bars"])
    grouped = {timestamp: group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}
    row_maps = {
        timestamp: {str(row["subject"]): row for _, row in group.iterrows()}
        for timestamp, group in grouped.items()
    }
    funding_index = build_funding_index(ordered)

    dd_throttle_enabled = bool(constraints.get("drawdown_throttle_enabled", False))
    dd_window_days = int(constraints.get("dd_throttle_window_days", 30) or 30)
    equity = 1.0
    equity_history: list[tuple[int, float]] = []
    previous_weights: dict[str, float] = {}
    position_records: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []
    period_records: list[dict[str, Any]] = []
    data_gap_blockers: set[str] = set()

    for decision_offset, timestamp_offset in enumerate(decision_timestamp_indices):
        fill_offset = timestamp_offset + latency_bars
        if fill_offset >= len(timestamps):
            break
        decision_timestamp = int(timestamps[timestamp_offset])
        fill_timestamp = int(timestamps[fill_offset])
        next_fill_offset = _next_fill_offset(
            timestamp_count=len(timestamps),
            decision_timestamp_indices=decision_timestamp_indices,
            decision_offset=decision_offset,
            latency_bars=latency_bars,
        )
        exit_timestamp = int(timestamps[next_fill_offset]) if next_fill_offset is not None else int(timestamps[-1])
        decision_group = grouped[decision_timestamp]
        raw_target_weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints=constraints,
            previous_weights=previous_weights,
        )
        raw_target_weights = h10d._apply_short_position_multiplier(
            raw_target_weights=raw_target_weights,
            decision_group=decision_group,
            constraints=constraints,
        )
        external_throttle_multiplier: float | None = None
        throttle_drawdown = 0.0
        if dd_throttle_enabled and equity_history:
            cutoff_ms = decision_timestamp - dd_window_days * 86_400_000
            recent_equity = [eq for ts, eq in equity_history if ts >= cutoff_ms]
            if recent_equity:
                running_max = max(recent_equity)
                if running_max > 0.0:
                    throttle_drawdown = max(float((running_max - equity) / running_max), 0.0)
                    external_throttle_multiplier = _drawdown_throttle_multiplier(
                        current_drawdown=throttle_drawdown,
                        constraints=constraints,
                    )
        if external_throttle_multiplier is not None and external_throttle_multiplier < 1.0 and raw_target_weights:
            raw_target_weights = {
                subject: float(weight) * float(external_throttle_multiplier)
                for subject, weight in raw_target_weights.items()
            }
        actual_weights = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
            turnover_mode=str(constraints.get("pair_turnover_mode") or constraints.get("turnover_mode") or "").strip().lower() or None,
        )
        fill_rows = row_maps.get(fill_timestamp, {})
        exit_rows = row_maps.get(exit_timestamp, {})
        decision_rank = h10d._decision_rank_by_subject(decision_group)
        period_totals = {
            "gross_return_before_costs": 0.0,
            "fee_cost_return": 0.0,
            "slippage_cost_return": 0.0,
            "funding_cost_return": 0.0,
            "borrow_cost_return": 0.0,
            "trade_notional_usd": 0.0,
            "turnover": 0.0,
        }
        current_weights: dict[str, float] = {}
        ledger_subjects = sorted(set(previous_weights) | set(actual_weights))
        for subject in ledger_subjects:
            target_weight = float(actual_weights.get(subject, 0.0) or 0.0)
            previous_weight = float(previous_weights.get(subject, 0.0) or 0.0)
            delta_weight = target_weight - previous_weight
            if abs(delta_weight) <= 1e-12 and abs(target_weight) <= 1e-12:
                continue
            fill_row = fill_rows.get(subject)
            exit_row = exit_rows.get(subject)
            row_blockers: set[str] = set()
            trade_costs = {
                "fee_cost_return": 0.0,
                "slippage_cost_return": 0.0,
                "trade_notional_usd": 0.0,
                "trade_participation_rate": 0.0,
                "inventory_participation_rate": 0.0,
                "max_participation_rate": 0.0,
                "capacity_breach_count": 0,
                "liquidity_volume_proxy_usd": 0.0,
                "data_gap_blockers": [],
            }
            if fill_row is None:
                if abs(delta_weight) > 1e-12 or abs(target_weight) > 1e-12:
                    data_gap_blockers.add(f"{subject}: missing fill row for fast attribution")
                    continue
            else:
                trade_costs = _trade_costs(
                    row=fill_row,
                    delta_weight=delta_weight,
                    target_weight=target_weight,
                    execution_venue=execution_venue,
                    execution_cost_model=cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=capacity_limits,
                    subject=subject,
                )
                row_blockers.update(str(item) for item in list(trade_costs.get("data_gap_blockers") or []))

            gross_contribution = 0.0
            if abs(target_weight) > 1e-12:
                if exit_row is None:
                    row_blockers.add(f"{subject}: missing exit row for fast attribution")
                elif fill_row is not None:
                    gross_contribution = _price_path_return(
                        entry_row=fill_row,
                        exit_row=exit_row,
                        weight=target_weight,
                        execution_venue=execution_venue,
                        subject=subject,
                        data_gap_blockers=row_blockers,
                    )
            funding_cost_return = funding_cost_between(
                funding_index=funding_index,
                subject=subject,
                fill_timestamp=fill_timestamp,
                exit_timestamp=exit_timestamp,
                weight=target_weight,
                execution_venue=execution_venue,
            )
            borrow_cost_return = h10d._borrow_cost_return(
                entry_timestamp_ms=fill_timestamp,
                exit_timestamp_ms=exit_timestamp,
                weight=target_weight,
                execution_venue=execution_venue,
                execution_cost_model=cost_model,
            )
            fee_cost_return = float(trade_costs.get("fee_cost_return", 0.0) or 0.0)
            slippage_cost_return = float(trade_costs.get("slippage_cost_return", 0.0) or 0.0)
            period_totals["gross_return_before_costs"] += gross_contribution
            period_totals["fee_cost_return"] += fee_cost_return
            period_totals["slippage_cost_return"] += slippage_cost_return
            period_totals["funding_cost_return"] += funding_cost_return
            period_totals["borrow_cost_return"] += borrow_cost_return
            period_totals["trade_notional_usd"] += float(trade_costs.get("trade_notional_usd", 0.0) or 0.0)
            period_totals["turnover"] += abs(delta_weight)
            decision_info = decision_rank.get(subject, {})
            price_field = "spot_close" if execution_venue == "spot" else "perp_close"
            entry_price = row_float(fill_row, price_field)
            exit_price = row_float(exit_row, price_field)
            underlying_forward_return = (
                (exit_price / entry_price - 1.0)
                if entry_price > 0.0 and exit_price > 0.0
                else 0.0
            )
            action = h10d._paper_shadow_action(previous_weight=previous_weight, target_weight=target_weight)
            ledger_records.append(
                {
                    "ledger_schema": "binance_fast_10d20d_attribution_ledger.v1",
                    "decision_timestamp_ms": decision_timestamp,
                    "fill_timestamp_ms": fill_timestamp,
                    "exit_timestamp_ms": exit_timestamp,
                    "decision_date_utc": ms_to_date(decision_timestamp),
                    "fill_date_utc": ms_to_date(fill_timestamp),
                    "exit_date_utc": ms_to_date(exit_timestamp),
                    "year": int(pd.to_datetime(fill_timestamp, unit="ms", utc=True).year),
                    "subject": subject,
                    "usdm_symbol": str((fill_row.get("usdm_symbol") if fill_row is not None else None) or f"{subject}USDT"),
                    "action": action,
                    "side": "long" if target_weight > 0.0 else ("short" if target_weight < 0.0 else "flat"),
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "delta_weight": delta_weight,
                    "target_notional_usd": float(reference_capital_usd * abs(target_weight)),
                    "delta_notional_usd": float(reference_capital_usd * abs(delta_weight)),
                    "score_at_decision": float(decision_info.get("score", 0.0) or 0.0),
                    "score_rank_desc": int(decision_info.get("score_rank_desc", 0) or 0),
                    "liquidity_bucket": str(
                        decision_info.get("liquidity_bucket")
                        or (fill_row.get("liquidity_bucket") if fill_row is not None else "")
                        or ""
                    ),
                    "universe_rank": decision_info.get("universe_rank"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "underlying_forward_return": float(underlying_forward_return),
                    "gross_contribution": float(gross_contribution),
                    "fee_cost_return": fee_cost_return,
                    "slippage_cost_return": slippage_cost_return,
                    "funding_cost_return": float(funding_cost_return),
                    "borrow_cost_return": float(borrow_cost_return),
                    "net_contribution": float(
                        gross_contribution
                        - fee_cost_return
                        - slippage_cost_return
                        - funding_cost_return
                        - borrow_cost_return
                    ),
                    "trade_notional_usd": float(trade_costs.get("trade_notional_usd", 0.0) or 0.0),
                    "trade_participation_rate": float(trade_costs.get("trade_participation_rate", 0.0) or 0.0),
                    "inventory_participation_rate": float(trade_costs.get("inventory_participation_rate", 0.0) or 0.0),
                    "max_participation_rate": float(trade_costs.get("max_participation_rate", 0.0) or 0.0),
                    "capacity_breach_count": int(trade_costs.get("capacity_breach_count", 0) or 0),
                    "liquidity_volume_proxy_usd": float(trade_costs.get("liquidity_volume_proxy_usd", 0.0) or 0.0),
                    "portfolio_throttle_multiplier": float(
                        external_throttle_multiplier if external_throttle_multiplier is not None else 1.0
                    ),
                    "portfolio_throttle_drawdown": float(throttle_drawdown),
                    "data_gap_blockers": ";".join(sorted(row_blockers)),
                }
                )
            if abs(target_weight) > 1e-12 and fill_row is not None and exit_row is not None:
                position_records.append(
                    {
                        "decision_timestamp_ms": decision_timestamp,
                        "fill_timestamp_ms": fill_timestamp,
                        "exit_timestamp_ms": exit_timestamp,
                        "fill_date_utc": ms_to_date(fill_timestamp),
                        "exit_date_utc": ms_to_date(exit_timestamp),
                        "year": int(pd.to_datetime(fill_timestamp, unit="ms", utc=True).year),
                        "subject": subject,
                        "usdm_symbol": str(fill_row.get("usdm_symbol") or f"{subject}USDT"),
                        "side": "long" if target_weight > 0.0 else "short",
                        "weight": target_weight,
                        "score_at_decision": float(decision_info.get("score", 0.0) or 0.0),
                        "score_rank_desc": int(decision_info.get("score_rank_desc", 0) or 0),
                        "liquidity_bucket": str(decision_info.get("liquidity_bucket") or fill_row.get("liquidity_bucket") or ""),
                        "universe_rank": decision_info.get("universe_rank"),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "underlying_forward_return": float(underlying_forward_return),
                        "gross_contribution": float(gross_contribution),
                        "funding_cost_return": float(funding_cost_return),
                        "net_before_trade_cost_contribution": float(gross_contribution - funding_cost_return),
                        "portfolio_throttle_multiplier": float(
                            external_throttle_multiplier if external_throttle_multiplier is not None else 1.0
                        ),
                        "portfolio_throttle_drawdown": float(throttle_drawdown),
                    }
                )
            if abs(target_weight) > 1e-12:
                current_weights[subject] = target_weight
            data_gap_blockers.update(row_blockers)
        net_period_return = (
            period_totals["gross_return_before_costs"]
            - period_totals["fee_cost_return"]
            - period_totals["slippage_cost_return"]
            - period_totals["funding_cost_return"]
            - period_totals["borrow_cost_return"]
        )
        period_records.append(
            {
                "timestamp_ms": fill_timestamp,
                "gross_return_before_costs": float(period_totals["gross_return_before_costs"]),
                "net_period_return": float(net_period_return),
                "fee_cost_return": float(period_totals["fee_cost_return"]),
                "slippage_cost_return": float(period_totals["slippage_cost_return"]),
                "funding_cost_return": float(period_totals["funding_cost_return"]),
                "borrow_cost_return": float(period_totals["borrow_cost_return"]),
                "trade_notional_usd": float(period_totals["trade_notional_usd"]),
                "turnover": float(period_totals["turnover"]),
                "portfolio_throttle_multiplier": float(
                    external_throttle_multiplier if external_throttle_multiplier is not None else 1.0
                ),
                "portfolio_throttle_drawdown": float(throttle_drawdown),
            }
        )
        if dd_throttle_enabled:
            equity = equity * (1.0 + net_period_return)
            equity_history.append((decision_timestamp, equity))
        previous_weights = current_weights

    positions = pd.DataFrame(position_records)
    ledger = pd.DataFrame(ledger_records)
    periods = pd.DataFrame(period_records)
    return {
        "positions": positions,
        "ledger": ledger,
        "periods": periods,
        "summary": summarize_fast_positions(positions, data_gap_blockers=data_gap_blockers),
        "ledger_summary": summarize_fast_ledger(ledger, data_gap_blockers=data_gap_blockers),
    }


def build_funding_index(ordered: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    index: dict[str, dict[str, np.ndarray]] = {}
    if ordered.empty:
        return index
    working = ordered[["subject", "timestamp_ms"]].copy()
    funding_rate = (
        pd.to_numeric(ordered["funding_rate"], errors="coerce").fillna(0.0)
        if "funding_rate" in ordered.columns
        else pd.Series(0.0, index=ordered.index, dtype="float64")
    )
    funding_sample_count = (
        pd.to_numeric(ordered["funding_sample_count"], errors="coerce").fillna(0.0)
        if "funding_sample_count" in ordered.columns
        else pd.Series(0.0, index=ordered.index, dtype="float64")
    )
    working["funding_rate_x_count"] = (
        funding_rate
        * funding_sample_count
    )
    for subject, group in working.groupby("subject", sort=False):
        sorted_group = group.sort_values("timestamp_ms")
        timestamps = pd.to_numeric(sorted_group["timestamp_ms"], errors="coerce").fillna(0).astype("int64").to_numpy()
        values = pd.to_numeric(sorted_group["funding_rate_x_count"], errors="coerce").fillna(0.0).to_numpy(dtype="float64")
        prefix = np.concatenate([[0.0], np.cumsum(values)])
        index[str(subject)] = {"timestamps": timestamps, "prefix": prefix}
    return index


def funding_cost_between(
    *,
    funding_index: dict[str, dict[str, np.ndarray]],
    subject: str,
    fill_timestamp: int,
    exit_timestamp: int,
    weight: float,
    execution_venue: str,
) -> float:
    if execution_venue != "perp" or abs(float(weight)) <= 0.0:
        return 0.0
    entry = funding_index.get(str(subject))
    if not entry:
        return 0.0
    timestamps = entry["timestamps"]
    prefix = entry["prefix"]
    start = int(np.searchsorted(timestamps, int(fill_timestamp), side="left"))
    end = int(np.searchsorted(timestamps, int(exit_timestamp), side="left"))
    return float(float(weight) * (prefix[end] - prefix[start]))


def summarize_fast_positions(positions: pd.DataFrame, *, data_gap_blockers: set[str]) -> dict[str, Any]:
    if positions.empty:
        return {"status": "empty", "position_row_count": 0, "data_gap_blockers": sorted(data_gap_blockers)}
    side_summary = aggregate_positions(positions, group_columns=["side"], prefix="summary")
    return {
        "status": "ok",
        "note": "Fast held-leg attribution: gross contribution minus funding cost; fee/slippage reconciled from fast execution ledger.",
        "position_row_count": int(len(positions)),
        "data_gap_blockers": sorted(data_gap_blockers),
        "side_summary": _records(side_summary),
    }


def summarize_fast_ledger(ledger: pd.DataFrame, *, data_gap_blockers: set[str]) -> dict[str, Any]:
    if ledger.empty:
        return {"status": "empty", "ledger_row_count": 0, "data_gap_blockers": sorted(data_gap_blockers)}
    return {
        "status": "ok",
        "ledger_schema": "binance_fast_10d20d_attribution_ledger.v1",
        "ledger_row_count": int(len(ledger)),
        "net_contribution": float(pd.to_numeric(ledger["net_contribution"], errors="coerce").fillna(0.0).sum()),
        "gross_contribution": float(pd.to_numeric(ledger["gross_contribution"], errors="coerce").fillna(0.0).sum()),
        "fee_cost_return": float(pd.to_numeric(ledger["fee_cost_return"], errors="coerce").fillna(0.0).sum()),
        "slippage_cost_return": float(pd.to_numeric(ledger["slippage_cost_return"], errors="coerce").fillna(0.0).sum()),
        "funding_cost_return": float(pd.to_numeric(ledger["funding_cost_return"], errors="coerce").fillna(0.0).sum()),
        "borrow_cost_return": float(pd.to_numeric(ledger["borrow_cost_return"], errors="coerce").fillna(0.0).sum()),
        "turnover": float(pd.to_numeric(ledger["delta_weight"], errors="coerce").fillna(0.0).abs().sum()),
        "data_gap_blockers": sorted(data_gap_blockers),
    }


def row_float(row: pd.Series | None, field_name: str) -> float:
    if row is None:
        return 0.0
    value = pd.to_numeric(pd.Series([row.get(field_name)]), errors="coerce").replace([np.inf, -np.inf], np.nan)
    if value.empty or pd.isna(value.iloc[0]):
        return 0.0
    return float(value.iloc[0])


def ms_to_date(timestamp_ms: int) -> str:
    return pd.to_datetime(int(timestamp_ms), unit="ms", utc=True).date().isoformat()


def _metric_delta(left: dict[str, Any], right: dict[str, Any], key: str) -> float:
    return float(left.get(key, 0.0) or 0.0) - float(right.get(key, 0.0) or 0.0)


def compare_attribution(pos10: pd.DataFrame, pos20: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    base = aggregate_positions(pos10, group_columns=group_columns, prefix="h10d")
    alt = aggregate_positions(pos20, group_columns=group_columns, prefix="h20d")
    merged = base.merge(alt, on=group_columns, how="outer")
    numeric_columns = [column for column in merged.columns if column not in group_columns]
    for column in numeric_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    for column in (*CONTRIBUTION_COLUMNS, *COUNT_COLUMNS, *MEAN_COLUMNS):
        left = f"h20d_{column}"
        right = f"h10d_{column}"
        if left in merged.columns and right in merged.columns:
            merged[f"{column}_delta_20d_minus_10d"] = merged[left] - merged[right]
    sort_columns = [column for column in ("year", "subject", "side") if column in merged.columns]
    if sort_columns:
        merged = merged.sort_values(sort_columns).reset_index(drop=True)
    return merged


def aggregate_positions(positions: pd.DataFrame, *, group_columns: list[str], prefix: str) -> pd.DataFrame:
    output_columns = [
        *group_columns,
        *[f"{prefix}_{column}" for column in (*COUNT_COLUMNS, *CONTRIBUTION_COLUMNS, *MEAN_COLUMNS)],
    ]
    if positions.empty:
        return pd.DataFrame(columns=output_columns)
    working = positions.copy()
    missing = [column for column in group_columns if column not in working.columns]
    if missing:
        return pd.DataFrame(columns=output_columns)
    for column in (
        "gross_contribution",
        "funding_cost_return",
        "net_before_trade_cost_contribution",
        "underlying_forward_return",
        "weight",
    ):
        source = working[column] if column in working.columns else pd.Series(0.0, index=working.index, dtype="float64")
        working[column] = pd.to_numeric(source, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    grouped = (
        working.groupby(group_columns, dropna=False, sort=True)
        .agg(
            position_count=("subject", "count"),
            rebalance_count=("fill_timestamp_ms", "nunique"),
            gross_contribution=("gross_contribution", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            net_before_trade_cost_contribution=("net_before_trade_cost_contribution", "sum"),
            mean_underlying_forward_return=("underlying_forward_return", "mean"),
            mean_abs_weight=("weight", lambda item: float(pd.to_numeric(item, errors="coerce").abs().mean())),
            profitable_position_rate=(
                "gross_contribution",
                lambda item: float(pd.to_numeric(item, errors="coerce").fillna(0.0).gt(0.0).mean()),
            ),
        )
        .reset_index()
    )
    return grouped.rename(columns={column: f"{prefix}_{column}" for column in (*COUNT_COLUMNS, *CONTRIBUTION_COLUMNS, *MEAN_COLUMNS)})


def compare_period_year(periods10: pd.DataFrame, periods20: pd.DataFrame) -> pd.DataFrame:
    ten = aggregate_periods_by_year(periods10, prefix="h10d")
    twenty = aggregate_periods_by_year(periods20, prefix="h20d")
    merged = ten.merge(twenty, on="year", how="outer")
    numeric_columns = [column for column in merged.columns if column != "year"]
    for column in numeric_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    for metric in (
        "period_count",
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "turnover",
    ):
        merged[f"{metric}_delta_20d_minus_10d"] = merged[f"h20d_{metric}"] - merged[f"h10d_{metric}"]
    return merged.sort_values("year").reset_index(drop=True)


def aggregate_periods_by_year(periods: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    columns = [
        "year",
        f"{prefix}_period_count",
        f"{prefix}_net_period_return",
        f"{prefix}_gross_return_before_costs",
        f"{prefix}_fee_cost_return",
        f"{prefix}_slippage_cost_return",
        f"{prefix}_funding_cost_return",
        f"{prefix}_turnover",
    ]
    if periods.empty or "timestamp_ms" not in periods.columns:
        return pd.DataFrame(columns=columns)
    working = periods.copy()
    working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce")
    working = working.dropna(subset=["timestamp_ms"]).copy()
    working["year"] = pd.to_datetime(working["timestamp_ms"].astype("int64"), unit="ms", utc=True).dt.year
    for column in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "turnover",
    ):
        source = working[column] if column in working.columns else pd.Series(0.0, index=working.index, dtype="float64")
        working[column] = pd.to_numeric(source, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    grouped = (
        working.groupby("year", sort=True)
        .agg(
            period_count=("timestamp_ms", "count"),
            net_period_return=("net_period_return", "sum"),
            gross_return_before_costs=("gross_return_before_costs", "sum"),
            fee_cost_return=("fee_cost_return", "sum"),
            slippage_cost_return=("slippage_cost_return", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            turnover=("turnover", "sum"),
        )
        .reset_index()
    )
    return grouped.rename(
        columns={
            "period_count": f"{prefix}_period_count",
            "net_period_return": f"{prefix}_net_period_return",
            "gross_return_before_costs": f"{prefix}_gross_return_before_costs",
            "fee_cost_return": f"{prefix}_fee_cost_return",
            "slippage_cost_return": f"{prefix}_slippage_cost_return",
            "funding_cost_return": f"{prefix}_funding_cost_return",
            "turnover": f"{prefix}_turnover",
        }
    )


def compare_execution_costs(ledger10: pd.DataFrame, ledger20: pd.DataFrame) -> pd.DataFrame:
    ten = aggregate_execution_costs(ledger10, prefix="h10d")
    twenty = aggregate_execution_costs(ledger20, prefix="h20d")
    merged = ten.merge(twenty, on="effective_side", how="outer")
    numeric_columns = [column for column in merged.columns if column != "effective_side"]
    for column in numeric_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    for metric in ("fee_cost_return", "slippage_cost_return", "trade_notional_usd", "turnover_proxy"):
        merged[f"{metric}_delta_20d_minus_10d"] = merged[f"h20d_{metric}"] - merged[f"h10d_{metric}"]
    return merged.sort_values("effective_side").reset_index(drop=True)


def aggregate_execution_costs(ledger: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    columns = [
        "effective_side",
        f"{prefix}_fee_cost_return",
        f"{prefix}_slippage_cost_return",
        f"{prefix}_trade_notional_usd",
        f"{prefix}_turnover_proxy",
    ]
    if ledger.empty:
        return pd.DataFrame(columns=columns)
    working = ledger.copy()
    working["effective_side"] = working.apply(_effective_cost_side, axis=1)
    for column in ("fee_cost_return", "slippage_cost_return", "trade_notional_usd", "delta_weight"):
        source = working[column] if column in working.columns else pd.Series(0.0, index=working.index, dtype="float64")
        working[column] = pd.to_numeric(source, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    grouped = (
        working.groupby("effective_side", sort=True)
        .agg(
            fee_cost_return=("fee_cost_return", "sum"),
            slippage_cost_return=("slippage_cost_return", "sum"),
            trade_notional_usd=("trade_notional_usd", "sum"),
            turnover_proxy=("delta_weight", lambda item: float(pd.to_numeric(item, errors="coerce").abs().sum())),
        )
        .reset_index()
    )
    return grouped.rename(
        columns={
            "fee_cost_return": f"{prefix}_fee_cost_return",
            "slippage_cost_return": f"{prefix}_slippage_cost_return",
            "trade_notional_usd": f"{prefix}_trade_notional_usd",
            "turnover_proxy": f"{prefix}_turnover_proxy",
        }
    )


def _effective_cost_side(row: pd.Series) -> str:
    side = str(row.get("side") or "").strip().lower()
    action = str(row.get("action") or "").strip().lower()
    previous = float(pd.to_numeric(pd.Series([row.get("previous_weight")]), errors="coerce").fillna(0.0).iloc[0])
    target = float(pd.to_numeric(pd.Series([row.get("target_weight")]), errors="coerce").fillna(0.0).iloc[0])
    if side in {"long", "short"}:
        return side
    if "close_long" in action or (abs(target) <= 1e-12 and previous > 0.0):
        return "long"
    if "close_short" in action or (abs(target) <= 1e-12 and previous < 0.0):
        return "short"
    return side or "unknown"


def build_paired_mtm(periods10: pd.DataFrame, periods20: pd.DataFrame) -> pd.DataFrame:
    curves = []
    for interval, periods in ((10, periods10), (20, periods20)):
        curve = period_equity_curve(periods, interval=interval)
        curves.append(curve)
    if not curves:
        return pd.DataFrame(columns=["date_utc"])
    wide = curves[0]
    for curve in curves[1:]:
        wide = wide.merge(curve, on="date_utc", how="outer")
    wide = wide.sort_values("date_utc").reset_index(drop=True)
    for interval in INTERVALS:
        equity_col = f"equity_h{interval}d"
        if equity_col in wide.columns:
            wide[equity_col] = pd.to_numeric(wide[equity_col], errors="coerce").ffill().fillna(1.0)
            prior = wide[equity_col].shift(1).fillna(1.0)
            wide[f"mtm_return_h{interval}d"] = (wide[equity_col] / prior.replace(0.0, np.nan) - 1.0).fillna(0.0)
    if "equity_h10d" in wide.columns and "equity_h20d" in wide.columns:
        wide["equity_delta_h20d_minus_h10d"] = wide["equity_h20d"] - wide["equity_h10d"]
        wide["mtm_return_delta_h20d_minus_h10d"] = wide["mtm_return_h20d"] - wide["mtm_return_h10d"]
    return wide


def period_equity_curve(periods: pd.DataFrame, *, interval: int) -> pd.DataFrame:
    if periods.empty:
        return pd.DataFrame(columns=["date_utc", f"equity_h{interval}d"])
    working = periods.copy()
    working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce")
    working = working.dropna(subset=["timestamp_ms"]).copy()
    working = working.sort_values("timestamp_ms")
    returns = pd.to_numeric(working.get("net_period_return"), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    working[f"equity_h{interval}d"] = (1.0 + returns).cumprod()
    working["date_utc"] = pd.to_datetime(working["timestamp_ms"].astype("int64"), unit="ms", utc=True).dt.date.astype(str)
    return working[["date_utc", f"equity_h{interval}d"]].copy()


def build_position_reconciliation(runs: dict[int, dict[str, Any]], metric_bridge: dict[str, float]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for interval in INTERVALS:
        metrics = dict(runs[interval]["metrics"])
        positions = runs[interval]["positions"]
        gross_position = float(pd.to_numeric(positions.get("gross_contribution"), errors="coerce").fillna(0.0).sum()) if not positions.empty else 0.0
        funding_position = float(pd.to_numeric(positions.get("funding_cost_return"), errors="coerce").fillna(0.0).sum()) if not positions.empty else 0.0
        net_before_trade_cost_position = (
            float(pd.to_numeric(positions.get("net_before_trade_cost_contribution"), errors="coerce").fillna(0.0).sum())
            if not positions.empty
            else 0.0
        )
        output[f"h{interval}d"] = {
            "position_gross_contribution_sum": gross_position,
            "metric_gross_return_before_costs": float(metrics.get("gross_return_before_costs", 0.0) or 0.0),
            "position_funding_cost_sum": funding_position,
            "metric_funding_cost_return": float(metrics.get("funding_cost_return", 0.0) or 0.0),
            "position_net_before_trade_cost_sum": net_before_trade_cost_position,
            "metric_gross_minus_funding": float(metrics.get("gross_return_before_costs", 0.0) or 0.0)
            - float(metrics.get("funding_cost_return", 0.0) or 0.0),
        }
    pos_delta = (
        output["h20d"]["position_net_before_trade_cost_sum"]
        - output["h10d"]["position_net_before_trade_cost_sum"]
    )
    output["delta_20d_minus_10d"] = {
        "position_net_before_trade_cost_delta": pos_delta,
        "metric_gross_minus_funding_delta": (
            metric_bridge["gross_return_before_costs_delta_20d_minus_10d"]
            - metric_bridge["funding_cost_return_delta_20d_minus_10d"]
        ),
        "net_return_delta_after_fee_slippage": metric_bridge["net_return_delta_20d_minus_10d"],
        "fee_slippage_delta_subtracted": (
            metric_bridge["fee_cost_return_delta_20d_minus_10d"]
            + metric_bridge["slippage_cost_return_delta_20d_minus_10d"]
        ),
    }
    return output


def write_report(*, doc_path: Path, summary: dict[str, Any], comparisons: dict[str, Any]) -> None:
    metric = summary["metric_bridge_20d_minus_10d"]
    reconciliation = summary["position_reconciliation"]["delta_20d_minus_10d"]
    top_year_side = comparisons["year_side"].sort_values(
        "net_before_trade_cost_contribution_delta_20d_minus_10d",
        ascending=False,
    )
    top_symbol_side = comparisons["symbol_side"].sort_values(
        "net_before_trade_cost_contribution_delta_20d_minus_10d",
        ascending=False,
    )
    top_symbol_year_side = comparisons["top_20d_advantage"]
    negative_symbol_year_side = comparisons["top_10d_advantage"]
    period_year = comparisons["period_year"].sort_values("net_period_return_delta_20d_minus_10d", ascending=False)
    blockers = summary.get("blockers") or []
    blocker_lines = "\n".join(f"- `{item.get('code', 'blocker')}`: {item}" for item in blockers) or "- none"
    lines = [
        "# hv_balanced 10d vs 20d position attribution",
        "",
        f"- generated_at_utc: `{summary['generated_at_utc']}`",
        f"- hard_status: `{summary['status']}`",
        f"- scenario: `{summary['scenario']}`",
        f"- frozen_10d_baseline_reproduction_status: `{summary['baseline_reproduction'].get('status')}`",
        f"- dataset_reproduction_status: `{summary['dataset_reproduction'].get('status')}`",
        f"- scored_row_count: `{summary['scored_row_count']}`",
        "",
        "## Net bridge",
        "",
        "| item | value |",
        "| --- | ---: |",
        f"| 10d net return | {metric['net_return_h10d']:.6f} |",
        f"| 20d net return | {metric['net_return_h20d']:.6f} |",
        f"| 20d - 10d net return | {metric['net_return_delta_20d_minus_10d']:.6f} |",
        f"| gross return delta | {metric['gross_return_before_costs_delta_20d_minus_10d']:.6f} |",
        f"| funding cost delta | {metric['funding_cost_return_delta_20d_minus_10d']:.6f} |",
        f"| fee + slippage cost delta | {(metric['fee_cost_return_delta_20d_minus_10d'] + metric['slippage_cost_return_delta_20d_minus_10d']):.6f} |",
        f"| position net-before-trade-cost delta | {reconciliation['position_net_before_trade_cost_delta']:.6f} |",
        f"| turnover delta | {metric['turnover_delta_20d_minus_10d']:.6f} |",
        f"| trade count delta | {metric['trade_count_delta_20d_minus_10d']:.0f} |",
        f"| max drawdown delta | {metric['max_drawdown_delta_20d_minus_10d']:.6f} |",
        f"| fast period reconciliation | {summary['fast_period_reconciliation'].get('status')} |",
        "",
        "## Best year/side contributors",
        "",
        dataframe_to_markdown(
            top_year_side.head(10),
            [
                "year",
                "side",
                "h10d_net_before_trade_cost_contribution",
                "h20d_net_before_trade_cost_contribution",
                "net_before_trade_cost_contribution_delta_20d_minus_10d",
                "position_count_delta_20d_minus_10d",
            ],
        ),
        "",
        "## Best symbol/side contributors",
        "",
        dataframe_to_markdown(
            top_symbol_side.head(15),
            [
                "subject",
                "usdm_symbol",
                "side",
                "h10d_net_before_trade_cost_contribution",
                "h20d_net_before_trade_cost_contribution",
                "net_before_trade_cost_contribution_delta_20d_minus_10d",
                "h10d_position_count",
                "h20d_position_count",
            ],
        ),
        "",
        "## Best symbol/year/side contributors",
        "",
        dataframe_to_markdown(
            top_symbol_year_side.head(15),
            [
                "year",
                "subject",
                "usdm_symbol",
                "side",
                "h10d_net_before_trade_cost_contribution",
                "h20d_net_before_trade_cost_contribution",
                "net_before_trade_cost_contribution_delta_20d_minus_10d",
                "h10d_position_count",
                "h20d_position_count",
            ],
        ),
        "",
        "## Where 10d was better",
        "",
        dataframe_to_markdown(
            negative_symbol_year_side.head(15),
            [
                "year",
                "subject",
                "usdm_symbol",
                "side",
                "h10d_net_before_trade_cost_contribution",
                "h20d_net_before_trade_cost_contribution",
                "net_before_trade_cost_contribution_delta_20d_minus_10d",
                "h10d_position_count",
                "h20d_position_count",
            ],
        ),
        "",
        "## Net period by year",
        "",
        dataframe_to_markdown(
            period_year,
            [
                "year",
                "h10d_net_period_return",
                "h20d_net_period_return",
                "net_period_return_delta_20d_minus_10d",
                "h10d_turnover",
                "h20d_turnover",
                "turnover_delta_20d_minus_10d",
            ],
        ),
        "",
        "## Notes",
        "",
        "- Position attribution uses held-leg gross contribution minus funding cost. Fee and slippage are assigned from the paper-shadow execution ledger and reconciled in the net bridge.",
        "- Headline net return is compounded equity return; year/symbol/side attribution rows are simple held-leg return contributions, so they explain direction and concentration rather than add exactly to compounded net-return delta.",
        "- This runner keeps alpha, universe, cost model, PIT eligibility, frozen row alignment, and reference capital fixed; only `target_horizon_bars` changes from 10 to 20.",
        "- The 30d blocker from the broader sensitivity sweep is not part of this 10d/20d attribution contract.",
        "",
        "## Blockers",
        "",
        blocker_lines,
        "",
        "## Artifacts",
        "",
    ]
    for key, value in (summary.get("artifact_paths") or {}).items():
        lines.append(f"- {key}: `{value}`")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dataframe_to_markdown(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, [column for column in columns if column in frame.columns]].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.6f}")
    headers = list(display.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in display.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in headers) + " |")
    return "\n".join(lines)


def _frame_or_empty(value: Any) -> pd.DataFrame:
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))


def main() -> int:
    args = parse_args()
    summary = run_analysis(args)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "metric_bridge_20d_minus_10d": summary["metric_bridge_20d_minus_10d"],
                "top_20d_advantage_by_year_side": summary["top_20d_advantage_by_year_side"][:6],
                "artifact_paths": summary["artifact_paths"],
                "blocker_count": len(summary.get("blockers") or []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
