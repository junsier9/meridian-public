from __future__ import annotations

import argparse
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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import analyze_hv_balanced_10d_vs_20d_position_attribution as interval_attribution  # noqa: E402
import analyze_hv_balanced_rebalance_interval_sensitivity as interval_sensitivity  # noqa: E402
import analyze_hv_balanced_rebalance_phase_sensitivity as phase_sensitivity  # noqa: E402
from enhengclaw.quant_research.binance_canonical_h10d import _run_backtest  # noqa: E402


DEFAULT_PHASE = 7
DEFAULT_BASELINE_PHASE = 0
DEFAULT_HORIZON_DAYS = 10
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "rebalance_phase7_failure_attribution_20260521"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "hv_balanced_phase7_failure_attribution_2026_05_21.md"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose the weak hv_balanced 10d rebalance phase by rebuilding the "
            "frozen scored frame, slicing the phase start, and exporting period, "
            "ledger, and symbol/side attribution."
        )
    )
    parser.add_argument("--config", type=Path, default=interval_sensitivity.DEFAULT_HV_BALANCED_CONFIG_PATH)
    parser.add_argument("--store-root", type=Path, default=None)
    parser.add_argument("--funding-root", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--scenario", choices=["base", "stress"], default="base")
    parser.add_argument("--phase", type=int, default=DEFAULT_PHASE)
    parser.add_argument("--baseline-phase", type=int, default=DEFAULT_BASELINE_PHASE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--baseline-report", type=Path, default=interval_sensitivity.DEFAULT_FROZEN_REPORT)
    parser.add_argument("--frozen-row-membership", type=Path, default=interval_sensitivity.DEFAULT_FROZEN_ROW_MEMBERSHIP)
    parser.add_argument("--no-frozen-row-alignment", action="store_true")
    parser.add_argument("--baseline-tolerance", type=float, default=1e-8)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    return interval_sensitivity.json_safe(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    interval_sensitivity.write_json(path, payload)


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))


def ensure_datetime_columns(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in ("fill_timestamp_ms", "exit_timestamp_ms", "timestamp_ms"):
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").astype("Int64")
    if "fill_date_utc" not in output.columns and "fill_timestamp_ms" in output.columns:
        output["fill_date_utc"] = pd.to_datetime(output["fill_timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    if "exit_date_utc" not in output.columns and "exit_timestamp_ms" in output.columns:
        output["exit_date_utc"] = pd.to_datetime(output["exit_timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    return output


def reconcile_periods(official: pd.DataFrame, fast: pd.DataFrame) -> dict[str, Any]:
    if official.empty or fast.empty:
        return {"status": "blocked", "reason": "missing_periods", "official_period_count": len(official), "fast_period_count": len(fast)}
    left = official.copy()
    right = fast.copy()
    left["timestamp_ms"] = pd.to_numeric(left["timestamp_ms"], errors="coerce").astype("Int64")
    right["timestamp_ms"] = pd.to_numeric(right["timestamp_ms"], errors="coerce").astype("Int64")
    merged = left.merge(right, on="timestamp_ms", how="outer", suffixes=("_official", "_fast"))
    row: dict[str, Any] = {
        "status": "passed",
        "official_period_count": int(len(left)),
        "fast_period_count": int(len(right)),
        "merged_period_count": int(len(merged)),
        "tolerance": 1e-10,
    }
    for metric in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "turnover",
    ):
        official_series = pd.to_numeric(merged.get(f"{metric}_official"), errors="coerce").fillna(0.0)
        fast_series = pd.to_numeric(merged.get(f"{metric}_fast"), errors="coerce").fillna(0.0)
        delta = fast_series - official_series
        row[f"{metric}_sum_delta_fast_minus_official"] = float(delta.sum())
        row[f"{metric}_max_abs_delta_fast_minus_official"] = float(delta.abs().max()) if not delta.empty else 0.0
    if (
        row["official_period_count"] != row["fast_period_count"]
        or row["net_period_return_max_abs_delta_fast_minus_official"] > row["tolerance"]
        or row["gross_return_before_costs_max_abs_delta_fast_minus_official"] > row["tolerance"]
        or row["funding_cost_return_max_abs_delta_fast_minus_official"] > row["tolerance"]
    ):
        row["status"] = "blocked"
    return row


def aggregate_positions(positions: pd.DataFrame, *, group_columns: list[str], prefix: str = "") -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=group_columns)
    frame = positions.copy()
    for column in ("net_before_trade_cost_contribution", "gross_contribution", "funding_cost_return", "weight"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce").fillna(0.0)
    grouped = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            position_count=("subject", "count"),
            long_count=("side", lambda values: int((values.astype(str) == "long").sum())),
            short_count=("side", lambda values: int((values.astype(str) == "short").sum())),
            gross_contribution=("gross_contribution", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            net_before_trade_cost_contribution=("net_before_trade_cost_contribution", "sum"),
            mean_abs_weight=("weight", lambda values: float(pd.to_numeric(values, errors="coerce").abs().mean())),
        )
        .reset_index()
    )
    if prefix:
        rename = {
            column: f"{prefix}_{column}"
            for column in grouped.columns
            if column not in group_columns
        }
        grouped = grouped.rename(columns=rename)
    return grouped


def compare_aggregates(
    baseline: pd.DataFrame,
    phase: pd.DataFrame,
    *,
    group_columns: list[str],
) -> pd.DataFrame:
    left = aggregate_positions(baseline, group_columns=group_columns, prefix="phase0")
    right = aggregate_positions(phase, group_columns=group_columns, prefix=f"phase{DEFAULT_PHASE}")
    merged = left.merge(right, on=group_columns, how="outer").fillna(0.0)
    for metric in ("net_before_trade_cost_contribution", "gross_contribution", "funding_cost_return", "position_count"):
        phase_col = f"phase{DEFAULT_PHASE}_{metric}"
        baseline_col = f"phase0_{metric}"
        if phase_col in merged.columns and baseline_col in merged.columns:
            merged[f"{metric}_delta_phase{DEFAULT_PHASE}_minus_phase0"] = (
                pd.to_numeric(merged[phase_col], errors="coerce").fillna(0.0)
                - pd.to_numeric(merged[baseline_col], errors="coerce").fillna(0.0)
            )
    sort_col = f"net_before_trade_cost_contribution_delta_phase{DEFAULT_PHASE}_minus_phase0"
    if sort_col in merged.columns:
        merged = merged.sort_values(sort_col).reset_index(drop=True)
    return merged


def period_position_summary(
    *,
    phase: int,
    official_periods: pd.DataFrame,
    fast_periods: pd.DataFrame,
    positions: pd.DataFrame,
    ledger: pd.DataFrame,
) -> pd.DataFrame:
    official = official_periods.copy()
    official["timestamp_ms"] = pd.to_numeric(official["timestamp_ms"], errors="coerce").astype("Int64")
    fast = fast_periods.copy()
    fast["timestamp_ms"] = pd.to_numeric(fast["timestamp_ms"], errors="coerce").astype("Int64")
    merged = official.merge(fast, on="timestamp_ms", how="left", suffixes=("", "_fast"))
    positions = ensure_datetime_columns(positions)
    ledger = ensure_datetime_columns(ledger)
    rows: list[dict[str, Any]] = []
    for _, period in merged.iterrows():
        timestamp_ms = int(period["timestamp_ms"])
        pos = positions.loc[pd.to_numeric(positions.get("fill_timestamp_ms"), errors="coerce").eq(timestamp_ms)].copy()
        led = ledger.loc[pd.to_numeric(ledger.get("fill_timestamp_ms"), errors="coerce").eq(timestamp_ms)].copy()
        for frame in (pos, led):
            for column in ("net_before_trade_cost_contribution", "net_contribution", "gross_contribution", "funding_cost_return"):
                if column in frame.columns:
                    frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        top_negative = []
        top_positive = []
        if not pos.empty:
            neg_cols = [
                "subject",
                "side",
                "weight",
                "underlying_forward_return",
                "net_before_trade_cost_contribution",
                "gross_contribution",
                "funding_cost_return",
            ]
            top_negative = records(pos.sort_values("net_before_trade_cost_contribution").head(6)[neg_cols])
            top_positive = records(pos.sort_values("net_before_trade_cost_contribution", ascending=False).head(4)[neg_cols])
        row = {
            "phase_offset_days": int(phase),
            "timestamp_ms": timestamp_ms,
            "fill_date_utc": str(pos["fill_date_utc"].iloc[0]) if not pos.empty else str(pd.to_datetime(timestamp_ms, unit="ms", utc=True).date()),
            "exit_date_utc": str(pos["exit_date_utc"].iloc[0]) if not pos.empty else "",
            "net_period_return": float(period.get("net_period_return", 0.0) or 0.0),
            "gross_return_before_costs": float(period.get("gross_return_before_costs", 0.0) or 0.0),
            "fee_cost_return": float(period.get("fee_cost_return", 0.0) or 0.0),
            "slippage_cost_return": float(period.get("slippage_cost_return", 0.0) or 0.0),
            "funding_cost_return": float(period.get("funding_cost_return", 0.0) or 0.0),
            "turnover": float(period.get("turnover", 0.0) or 0.0),
            "portfolio_throttle_multiplier": float(period.get("portfolio_throttle_multiplier", 1.0) or 1.0),
            "portfolio_throttle_drawdown": float(period.get("portfolio_throttle_drawdown", 0.0) or 0.0),
            "held_position_count": int(len(pos)),
            "long_count": int((pos.get("side", pd.Series(dtype=str)).astype(str) == "long").sum()) if not pos.empty else 0,
            "short_count": int((pos.get("side", pd.Series(dtype=str)).astype(str) == "short").sum()) if not pos.empty else 0,
            "ledger_row_count": int(len(led)),
            "held_position_net_before_trade_cost": float(pd.to_numeric(pos.get("net_before_trade_cost_contribution"), errors="coerce").fillna(0.0).sum()) if not pos.empty else 0.0,
            "ledger_net_contribution": float(pd.to_numeric(led.get("net_contribution"), errors="coerce").fillna(0.0).sum()) if not led.empty else 0.0,
            "top_negative_legs_json": json.dumps(json_safe(top_negative), ensure_ascii=False),
            "top_positive_legs_json": json.dumps(json_safe(top_positive), ensure_ascii=False),
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values("net_period_return").reset_index(drop=True)


def build_overlap_compare(phase_periods: pd.DataFrame, baseline_periods: pd.DataFrame) -> pd.DataFrame:
    if phase_periods.empty or baseline_periods.empty:
        return pd.DataFrame()
    phase = phase_periods.copy()
    base = baseline_periods.copy()
    for frame in (phase, base):
        frame["fill_ts"] = pd.to_datetime(frame["fill_date_utc"], utc=True, errors="coerce")
        frame["exit_ts"] = pd.to_datetime(frame["exit_date_utc"], utc=True, errors="coerce")
        valid = frame["fill_ts"].notna() & frame["exit_ts"].notna() & frame["exit_ts"].gt(frame["fill_ts"])
        frame.drop(index=frame.index[~valid], inplace=True)
    if phase.empty or base.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, p in phase.iterrows():
        best: dict[str, Any] | None = None
        for _, b in base.iterrows():
            start = max(p["fill_ts"], b["fill_ts"])
            end = min(p["exit_ts"], b["exit_ts"])
            overlap_days = max(float((end - start).total_seconds() / 86_400.0), 0.0) if pd.notna(start) and pd.notna(end) else 0.0
            if overlap_days <= 0.0:
                continue
            if best is None or overlap_days > float(best["overlap_days"]):
                best = {
                    "phase_fill_date_utc": p["fill_date_utc"],
                    "phase_exit_date_utc": p["exit_date_utc"],
                    "phase_net_period_return": p["net_period_return"],
                    "baseline_fill_date_utc": b["fill_date_utc"],
                    "baseline_exit_date_utc": b["exit_date_utc"],
                    "baseline_net_period_return": b["net_period_return"],
                    "overlap_days": overlap_days,
                    "net_period_return_delta_phase_minus_baseline": float(p["net_period_return"]) - float(b["net_period_return"]),
                }
        if best is not None:
            rows.append(best)
    return pd.DataFrame(rows).sort_values("phase_net_period_return").reset_index(drop=True)


def compact_top_legs(periods: pd.DataFrame, *, count: int = 6) -> list[dict[str, Any]]:
    if periods.empty:
        return []
    output: list[dict[str, Any]] = []
    for _, row in periods.head(count).iterrows():
        legs = json.loads(str(row.get("top_negative_legs_json") or "[]"))
        output.append(
            {
                "fill_date_utc": row.get("fill_date_utc"),
                "exit_date_utc": row.get("exit_date_utc"),
                "net_period_return": row.get("net_period_return"),
                "top_negative_legs": legs[:4],
            }
        )
    return output


def dataframe_to_markdown(frame: pd.DataFrame, columns: list[str], *, max_rows: int = 12) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, [column for column in columns if column in frame.columns]].head(max_rows).copy()
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


def write_report(
    *,
    doc_path: Path,
    summary: dict[str, Any],
    worst_periods: pd.DataFrame,
    symbol_side_delta: pd.DataFrame,
    year_side_delta: pd.DataFrame,
    overlap_compare: pd.DataFrame,
    artifact_paths: dict[str, str],
) -> None:
    blocker_lines = "\n".join(f"- `{item.get('code', 'blocker')}`: {item}" for item in summary.get("blockers") or []) or "- none"
    worst_table = dataframe_to_markdown(
        worst_periods,
        [
            "fill_date_utc",
            "exit_date_utc",
            "net_period_return",
            "gross_return_before_costs",
            "funding_cost_return",
            "turnover",
            "held_position_count",
            "long_count",
            "short_count",
            "portfolio_throttle_multiplier",
        ],
    )
    symbol_table = dataframe_to_markdown(
        symbol_side_delta,
        [
            "subject",
            "side",
            "phase7_net_before_trade_cost_contribution",
            "phase0_net_before_trade_cost_contribution",
            "net_before_trade_cost_contribution_delta_phase7_minus_phase0",
            "phase7_position_count",
            "phase0_position_count",
        ],
    )
    year_side_table = dataframe_to_markdown(
        year_side_delta,
        [
            "year",
            "side",
            "phase7_net_before_trade_cost_contribution",
            "phase0_net_before_trade_cost_contribution",
            "net_before_trade_cost_contribution_delta_phase7_minus_phase0",
        ],
    )
    overlap_table = dataframe_to_markdown(
        overlap_compare,
        [
            "phase_fill_date_utc",
            "phase_exit_date_utc",
            "phase_net_period_return",
            "baseline_fill_date_utc",
            "baseline_exit_date_utc",
            "baseline_net_period_return",
            "overlap_days",
            "net_period_return_delta_phase_minus_baseline",
        ],
    )
    lines = [
        "# hv_balanced phase 7 failure attribution",
        "",
        f"- generated_at_utc: `{summary['generated_at_utc']}`",
        f"- status: `{summary['status']}`",
        f"- scenario: `{summary['scenario']}`",
        f"- baseline_phase: `{summary['baseline_phase']}`",
        f"- diagnosed_phase: `{summary['diagnosed_phase']}`",
        f"- phase0_net_return: `{summary['phase0_metrics'].get('net_return')}`",
        f"- phase7_net_return: `{summary['phase_metrics'].get('net_return')}`",
        f"- phase7_vs_phase0_net_ratio: `{summary['phase7_vs_phase0_net_ratio']}`",
        f"- fast_period_reconciliation_status_phase0: `{summary['phase0_fast_period_reconciliation'].get('status')}`",
        f"- fast_period_reconciliation_status_phase7: `{summary['phase_fast_period_reconciliation'].get('status')}`",
        "",
        "## Worst phase 7 periods",
        "",
        worst_table,
        "",
        "## Worst symbol/side deltas vs phase 0",
        "",
        symbol_table,
        "",
        "## Worst year/side deltas vs phase 0",
        "",
        year_side_table,
        "",
        "## Calendar-overlap comparison",
        "",
        overlap_table,
        "",
        "## Diagnosis",
        "",
        f"- worst_5_phase7_period_return_sum: `{summary['worst_5_phase7_period_return_sum']}`",
        f"- phase7_negative_period_count: `{summary['phase7_negative_period_count']}`",
        f"- phase7_median_period_return: `{summary['phase7_median_period_return']}`",
        f"- recommended_response: `{summary['recommended_response']}`",
        "",
        "## Guardrails",
        "",
        "- This diagnostic does not change live trading state and does not submit orders.",
        "- Fast ledger attribution is reconciled against official period returns before interpretation.",
        "- Position rows explain concentration and direction; headline net return remains compounded at the portfolio period level.",
        "",
        "## Blockers",
        "",
        blocker_lines,
        "",
        "## Artifacts",
        "",
    ]
    for key, value in artifact_paths.items():
        lines.append(f"- {key}: `{value}`")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if int(args.phase) != DEFAULT_PHASE:
        raise SystemExit(f"Refusing non-contract phase={args.phase}; required={DEFAULT_PHASE}")
    if int(args.baseline_phase) != DEFAULT_BASELINE_PHASE:
        raise SystemExit(f"Refusing non-contract baseline_phase={args.baseline_phase}; required={DEFAULT_BASELINE_PHASE}")

    output_root = interval_sensitivity.resolve_repo_path(args.output_root)
    doc_path = interval_sensitivity.resolve_repo_path(args.doc_path)
    baseline_report = interval_sensitivity.resolve_repo_path(args.baseline_report)
    store_root = Path(args.store_root).resolve() if args.store_root else interval_sensitivity.default_store_root_from_baseline(baseline_report)
    partition_path_compatibility = interval_sensitivity.install_symbol_partition_compatibility_patch()
    frozen_row_alignment = interval_sensitivity.install_frozen_feature_row_alignment_patch(
        args.frozen_row_membership,
        disabled=bool(args.no_frozen_row_alignment),
    )
    fixed = interval_sensitivity.load_fixed_scored_frame(args, store_root=store_root)
    scored_frame = fixed["scored_frame"]
    if scored_frame.empty:
        raise RuntimeError("scored_frame is empty; cannot diagnose phase 7")
    base_config = fixed["config"]
    run_config = interval_sensitivity.interval_config(base_config, DEFAULT_HORIZON_DAYS)

    phase0_frame, phase0_audit = phase_sensitivity.phase_frame(scored_frame, phase_offset_days=DEFAULT_BASELINE_PHASE)
    phase_frame, phase_audit = phase_sensitivity.phase_frame(scored_frame, phase_offset_days=DEFAULT_PHASE)
    phase0_metrics = _run_backtest(phase0_frame, config=run_config, scenario=args.scenario, include_periods=True)
    phase_metrics = _run_backtest(phase_frame, config=run_config, scenario=args.scenario, include_periods=True)
    phase0_fast = interval_attribution.build_fast_interval_attribution(phase0_frame, config=run_config, scenario=args.scenario)
    phase_fast = interval_attribution.build_fast_interval_attribution(phase_frame, config=run_config, scenario=args.scenario)

    phase0_official_periods = pd.DataFrame(phase0_metrics.get("periods") or [])
    phase_official_periods = pd.DataFrame(phase_metrics.get("periods") or [])
    phase0_reconciliation = reconcile_periods(phase0_official_periods, phase0_fast["periods"])
    phase_reconciliation = reconcile_periods(phase_official_periods, phase_fast["periods"])

    phase0_positions = phase0_fast["positions"].copy()
    phase_positions = phase_fast["positions"].copy()
    phase0_ledger = phase0_fast["ledger"].copy()
    phase_ledger = phase_fast["ledger"].copy()
    phase0_period_summary = period_position_summary(
        phase=DEFAULT_BASELINE_PHASE,
        official_periods=phase0_official_periods,
        fast_periods=phase0_fast["periods"],
        positions=phase0_positions,
        ledger=phase0_ledger,
    )
    phase_period_summary = period_position_summary(
        phase=DEFAULT_PHASE,
        official_periods=phase_official_periods,
        fast_periods=phase_fast["periods"],
        positions=phase_positions,
        ledger=phase_ledger,
    )
    symbol_side_delta = compare_aggregates(phase0_positions, phase_positions, group_columns=["subject", "side"])
    year_side_delta = compare_aggregates(phase0_positions, phase_positions, group_columns=["year", "side"])
    symbol_year_side_delta = compare_aggregates(phase0_positions, phase_positions, group_columns=["subject", "year", "side"])
    overlap_compare = build_overlap_compare(phase_period_summary, phase0_period_summary)

    baseline_reproduction = interval_sensitivity.compare_baseline(
        ten_day_metrics=phase0_metrics,
        baseline_report_path=baseline_report,
        tolerance=float(args.baseline_tolerance),
    )
    dataset_reproduction = interval_sensitivity.compare_dataset_reproduction(
        current_manifest=fixed["dataset_manifest"],
        baseline_report_path=baseline_report,
    )
    blockers = list(fixed.get("blockers") or [])
    for label, metrics in (("phase0", phase0_metrics), ("phase7", phase_metrics)):
        gaps = list(metrics.get("data_gap_blockers") or [])
        if gaps:
            blockers.append(
                {
                    "code": f"{label}_execution_data_gap_blockers",
                    "data_gap_blocker_count": len(gaps),
                    "sample": gaps[:10],
                }
            )
    for label, reconciliation in (("phase0", phase0_reconciliation), ("phase7", phase_reconciliation)):
        if str(reconciliation.get("status")) != "passed":
            blockers.append({"code": f"{label}_fast_period_reconciliation_failed", "detail": reconciliation})
    if baseline_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_phase0_baseline_reproduction_failed", "detail": baseline_reproduction})
    if dataset_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_dataset_reproduction_failed", "detail": dataset_reproduction})

    net0 = float(phase0_metrics.get("net_return", 0.0) or 0.0)
    net7 = float(phase_metrics.get("net_return", 0.0) or 0.0)
    worst_periods = phase_period_summary.sort_values("net_period_return").reset_index(drop=True)
    negative_returns = pd.to_numeric(phase_period_summary.get("net_period_return"), errors="coerce").fillna(0.0)
    worst5_sum = float(worst_periods.head(5)["net_period_return"].sum()) if not worst_periods.empty else 0.0
    median_period = float(negative_returns.median()) if not negative_returns.empty else 0.0
    phase7_negative_period_count = int(negative_returns.lt(0.0).sum())
    recommended_response = (
        "prefer_multi_phase_or_staggered_sleeves_over_anchor_selection"
        if net7 > 0.0 and net0 > 0.0
        else "pause_promotion_until_phase_failure_repaired"
    )

    artifact_paths = {
        "summary_json": str(output_root / "summary.json"),
        "phase0_position_attribution_csv": str(output_root / "position_attribution_phase0.csv"),
        "phase7_position_attribution_csv": str(output_root / "position_attribution_phase7.csv"),
        "phase0_paper_shadow_ledger_csv": str(output_root / "paper_shadow_ledger_phase0.csv"),
        "phase7_paper_shadow_ledger_csv": str(output_root / "paper_shadow_ledger_phase7.csv"),
        "phase0_period_summary_csv": str(output_root / "period_summary_phase0.csv"),
        "phase7_period_summary_csv": str(output_root / "period_summary_phase7.csv"),
        "worst_phase7_periods_csv": str(output_root / "worst_phase7_periods.csv"),
        "symbol_side_delta_csv": str(output_root / "symbol_side_delta_phase7_minus_phase0.csv"),
        "year_side_delta_csv": str(output_root / "year_side_delta_phase7_minus_phase0.csv"),
        "symbol_year_side_delta_csv": str(output_root / "symbol_year_side_delta_phase7_minus_phase0.csv"),
        "calendar_overlap_compare_csv": str(output_root / "calendar_overlap_compare.csv"),
        "markdown_report": str(doc_path),
    }
    summary = {
        "schema": "hv_balanced_phase7_failure_attribution.v1",
        "generated_at_utc": utc_now_iso(),
        "status": "passed" if not blockers else "blocked",
        "scenario": args.scenario,
        "baseline_phase": DEFAULT_BASELINE_PHASE,
        "diagnosed_phase": DEFAULT_PHASE,
        "config_path": fixed["config_path"],
        "as_of": fixed["as_of"],
        "funding_root": fixed["funding_root"],
        "phase0_audit": phase0_audit,
        "phase_audit": phase_audit,
        "phase0_metrics": {key: phase0_metrics.get(key) for key in ("net_return", "sharpe", "max_drawdown", "turnover", "trade_count", "rebalance_count")},
        "phase_metrics": {key: phase_metrics.get(key) for key in ("net_return", "sharpe", "max_drawdown", "turnover", "trade_count", "rebalance_count")},
        "phase7_vs_phase0_net_ratio": (net7 / net0 if abs(net0) > 1e-12 else None),
        "phase0_fast_period_reconciliation": phase0_reconciliation,
        "phase_fast_period_reconciliation": phase_reconciliation,
        "dataset_reproduction": dataset_reproduction,
        "baseline_reproduction": baseline_reproduction,
        "partition_path_compatibility": partition_path_compatibility,
        "frozen_row_alignment": frozen_row_alignment,
        "phase0_attribution_summary": phase0_fast["summary"],
        "phase_attribution_summary": phase_fast["summary"],
        "phase0_ledger_summary": phase0_fast["ledger_summary"],
        "phase_ledger_summary": phase_fast["ledger_summary"],
        "worst_5_phase7_period_return_sum": worst5_sum,
        "phase7_negative_period_count": phase7_negative_period_count,
        "phase7_median_period_return": median_period,
        "top_worst_phase7_periods": records(worst_periods.head(12)),
        "top_worst_phase7_period_legs": compact_top_legs(worst_periods, count=8),
        "top_bad_symbol_side_delta": records(symbol_side_delta.head(12)),
        "top_bad_symbol_year_side_delta": records(symbol_year_side_delta.head(15)),
        "top_bad_year_side_delta": records(year_side_delta.head(10)),
        "recommended_response": recommended_response,
        "blockers": blockers,
        "artifact_paths": artifact_paths,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    phase0_positions.to_csv(output_root / "position_attribution_phase0.csv", index=False)
    phase_positions.to_csv(output_root / "position_attribution_phase7.csv", index=False)
    phase0_ledger.to_csv(output_root / "paper_shadow_ledger_phase0.csv", index=False)
    phase_ledger.to_csv(output_root / "paper_shadow_ledger_phase7.csv", index=False)
    phase0_period_summary.to_csv(output_root / "period_summary_phase0.csv", index=False)
    phase_period_summary.to_csv(output_root / "period_summary_phase7.csv", index=False)
    worst_periods.to_csv(output_root / "worst_phase7_periods.csv", index=False)
    symbol_side_delta.to_csv(output_root / "symbol_side_delta_phase7_minus_phase0.csv", index=False)
    year_side_delta.to_csv(output_root / "year_side_delta_phase7_minus_phase0.csv", index=False)
    symbol_year_side_delta.to_csv(output_root / "symbol_year_side_delta_phase7_minus_phase0.csv", index=False)
    overlap_compare.to_csv(output_root / "calendar_overlap_compare.csv", index=False)
    write_json(output_root / "summary.json", summary)
    write_report(
        doc_path=doc_path,
        summary=summary,
        worst_periods=worst_periods,
        symbol_side_delta=symbol_side_delta,
        year_side_delta=year_side_delta,
        overlap_compare=overlap_compare,
        artifact_paths=artifact_paths,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "phase7_vs_phase0_net_ratio": summary["phase7_vs_phase0_net_ratio"],
                "phase7_negative_period_count": phase7_negative_period_count,
                "worst_5_phase7_period_return_sum": worst5_sum,
                "recommended_response": recommended_response,
                "top_worst_phase7_periods": json_safe(summary["top_worst_phase7_periods"][:8]),
                "top_bad_symbol_side_delta": json_safe(summary["top_bad_symbol_side_delta"][:8]),
                "artifact_paths": artifact_paths,
                "blocker_count": len(blockers),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
