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

import analyze_hv_balanced_rebalance_interval_sensitivity as interval_sensitivity  # noqa: E402
from enhengclaw.quant_research.binance_canonical_h10d import _run_backtest  # noqa: E402


DEFAULT_PHASES = tuple(range(10))
DEFAULT_HORIZON_DAYS = 10
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "rebalance_phase_sensitivity_20260521"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "hv_balanced_rebalance_phase_sensitivity_2026_05_21.md"
)
DEFAULT_MIN_NET_RETURN_RATIO_VS_PHASE0 = 0.50
DEFAULT_MIN_SHARPE = 0.75
DEFAULT_MAX_DD_ABS = 0.45
DEFAULT_MAX_DD_DELTA_VS_PHASE0 = 0.10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run hv_balanced 10d rebalance phase sensitivity. The frozen scored "
            "frame is reused, target_horizon_bars stays 10, and only the first "
            "decision timestamp is shifted by 0..9 daily bars."
        )
    )
    parser.add_argument("--config", type=Path, default=interval_sensitivity.DEFAULT_HV_BALANCED_CONFIG_PATH)
    parser.add_argument("--store-root", type=Path, default=None)
    parser.add_argument("--funding-root", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--scenario", choices=["base", "stress"], default="base")
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    parser.add_argument("--phases", nargs="+", type=int, default=list(DEFAULT_PHASES))
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
    parser.add_argument("--min-net-return-ratio-vs-phase0", type=float, default=DEFAULT_MIN_NET_RETURN_RATIO_VS_PHASE0)
    parser.add_argument("--min-sharpe", type=float, default=DEFAULT_MIN_SHARPE)
    parser.add_argument("--max-dd-abs", type=float, default=DEFAULT_MAX_DD_ABS)
    parser.add_argument("--max-dd-delta-vs-phase0", type=float, default=DEFAULT_MAX_DD_DELTA_VS_PHASE0)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    return interval_sensitivity.json_safe(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    interval_sensitivity.write_json(path, payload)


def phase_frame(scored_frame: pd.DataFrame, *, phase_offset_days: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    if scored_frame.empty or "timestamp_ms" not in scored_frame.columns:
        return scored_frame.iloc[0:0].copy(), {
            "phase_offset_days": int(phase_offset_days),
            "status": "empty_or_missing_timestamp_ms",
        }
    timestamps = sorted(int(item) for item in scored_frame["timestamp_ms"].drop_duplicates().tolist())
    phase = int(phase_offset_days)
    if phase < 0:
        raise ValueError(f"phase_offset_days must be >= 0: {phase}")
    if phase >= len(timestamps):
        return scored_frame.iloc[0:0].copy(), {
            "phase_offset_days": phase,
            "status": "phase_after_available_history",
            "available_timestamp_count": len(timestamps),
        }
    start_timestamp_ms = int(timestamps[phase])
    output = scored_frame.loc[pd.to_numeric(scored_frame["timestamp_ms"], errors="coerce").ge(start_timestamp_ms)].copy()
    return output, {
        "phase_offset_days": phase,
        "status": "ok",
        "start_timestamp_ms": start_timestamp_ms,
        "start_date_utc": pd.to_datetime(start_timestamp_ms, unit="ms", utc=True).date().isoformat(),
        "row_count": int(len(output)),
        "timestamp_count": int(output["timestamp_ms"].nunique()) if "timestamp_ms" in output.columns else 0,
    }


def phase_metric_row(
    *,
    phase_offset_days: int,
    phase_audit: dict[str, Any],
    metrics: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    row = {
        "phase_offset_days": int(phase_offset_days),
        "start_date_utc": phase_audit.get("start_date_utc"),
        "start_timestamp_ms": phase_audit.get("start_timestamp_ms"),
        "scenario": str(metrics.get("execution_cost_model", {}).get("scenario", "")),
    }
    for key in interval_sensitivity.BASELINE_METRIC_KEYS:
        row[key] = metrics.get(key)
    row["evaluation_step_bars"] = metrics.get("evaluation_step_bars")
    row["latency_bars"] = metrics.get("latency_bars")
    row["execution_venue"] = metrics.get("execution_venue")
    row["trade_notional_usd_total"] = metrics.get("trade_notional_usd_total")
    row["max_trade_participation_rate"] = metrics.get("max_trade_participation_rate")
    row["max_inventory_participation_rate"] = metrics.get("max_inventory_participation_rate")
    row["max_participation_rate"] = metrics.get("max_participation_rate")
    row["capacity_breach_count"] = metrics.get("capacity_breach_count")
    row["data_gap_blocker_count"] = len(metrics.get("data_gap_blockers") or [])
    if baseline:
        for key in ("net_return", "sharpe", "max_drawdown", "turnover", "trade_count", "rebalance_count"):
            current = row.get(key)
            base = baseline.get(key)
            row[f"{key}_delta_vs_phase0"] = None if current is None or base is None else float(current) - float(base)
        current_net = row.get("net_return")
        base_net = baseline.get("net_return")
        if current_net is not None and base_net is not None and abs(float(base_net)) > 1e-12:
            row["net_return_ratio_vs_phase0"] = float(current_net) / float(base_net)
        else:
            row["net_return_ratio_vs_phase0"] = None
    return row


def phase_period_rows(phase_offset_days: int, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = interval_sensitivity.period_rows(DEFAULT_HORIZON_DAYS, metrics)
    for row in rows:
        row.pop("interval_days", None)
        row["phase_offset_days"] = int(phase_offset_days)
    return rows


def build_paired_mtm(periods: pd.DataFrame, phases: list[int]) -> pd.DataFrame:
    if periods.empty:
        return pd.DataFrame(columns=["date_utc"])
    dates = sorted(str(item) for item in periods["date_utc"].dropna().unique().tolist())
    wide = pd.DataFrame({"date_utc": dates})
    for phase in phases:
        group = periods.loc[periods["phase_offset_days"].eq(int(phase))].copy()
        equity_col = f"equity_phase_{phase}"
        return_col = f"mtm_return_phase_{phase}"
        if group.empty:
            wide[equity_col] = 1.0
            wide[return_col] = 0.0
            continue
        curve = (
            group.sort_values(["timestamp_ms", "period_index"])
            .groupby("date_utc", as_index=False)
            .tail(1)[["date_utc", "equity"]]
            .rename(columns={"equity": equity_col})
        )
        wide = wide.merge(curve, on="date_utc", how="left")
        wide[equity_col] = pd.to_numeric(wide[equity_col], errors="coerce").ffill().fillna(1.0)
        prior = wide[equity_col].shift(1).fillna(1.0)
        wide[return_col] = wide[equity_col] / prior.replace(0.0, np.nan) - 1.0
        wide[return_col] = wide[return_col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if 0 in phases and "equity_phase_0" in wide.columns:
        for phase in phases:
            if int(phase) == 0:
                continue
            equity_col = f"equity_phase_{phase}"
            if equity_col in wide.columns:
                wide[f"equity_delta_phase_{phase}_vs_phase_0"] = wide[equity_col] - wide["equity_phase_0"]
    return wide


def build_phase_correlation(paired_mtm: pd.DataFrame, phases: list[int]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline_col = "mtm_return_phase_0"
    if paired_mtm.empty or baseline_col not in paired_mtm.columns:
        return pd.DataFrame(columns=["phase_offset_days", "mtm_return_corr_vs_phase0"])
    baseline = pd.to_numeric(paired_mtm[baseline_col], errors="coerce").fillna(0.0)
    for phase in phases:
        return_col = f"mtm_return_phase_{phase}"
        if return_col not in paired_mtm.columns:
            continue
        current = pd.to_numeric(paired_mtm[return_col], errors="coerce").fillna(0.0)
        corr = None
        if float(baseline.std(ddof=0)) > 0.0 and float(current.std(ddof=0)) > 0.0:
            corr_value = float(baseline.corr(current))
            corr = corr_value if math.isfinite(corr_value) else None
        rows.append({"phase_offset_days": int(phase), "mtm_return_corr_vs_phase0": corr})
    return pd.DataFrame(rows)


def evaluate_robustness(metrics: pd.DataFrame, args: argparse.Namespace) -> dict[str, Any]:
    if metrics.empty:
        return {"status": "blocked", "failures": [{"code": "empty_phase_metrics"}]}
    baseline_rows = metrics.loc[metrics["phase_offset_days"].eq(0)]
    if baseline_rows.empty:
        return {"status": "blocked", "failures": [{"code": "missing_phase0_baseline"}]}
    baseline = baseline_rows.iloc[0].to_dict()
    base_net = float(baseline.get("net_return", 0.0) or 0.0)
    base_dd = float(baseline.get("max_drawdown", 0.0) or 0.0)
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
            failures.append({"code": "phase_data_gap_blockers", **summary})
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
    status = "passed" if not failures else "failed"
    return {
        "status": status,
        "thresholds": thresholds,
        "baseline_phase0": baseline,
        "phase_summaries": phase_summaries,
        "failures": failures,
    }


def dataframe_to_markdown(frame: pd.DataFrame, columns: list[str]) -> str:
    return interval_sensitivity.dataframe_to_markdown(frame, columns)


def write_report(
    *,
    doc_path: Path,
    summary: dict[str, Any],
    metrics: pd.DataFrame,
    correlations: pd.DataFrame,
    artifact_paths: dict[str, str],
) -> None:
    robustness = summary.get("robustness") or {}
    baseline_reproduction = summary.get("baseline_reproduction") or {}
    dataset_reproduction = summary.get("dataset_reproduction") or {}
    diagnostics = summary.get("scored_frame_diagnostics") or {}
    dataset = summary.get("dataset_manifest") or {}
    blockers = summary.get("blockers") or []
    blocker_lines = "\n".join(f"- `{item.get('code', 'blocker')}`: {item}" for item in blockers) or "- none"
    failure_lines = "\n".join(f"- `{item.get('code')}` phase={item.get('phase_offset_days')}: {item}" for item in robustness.get("failures") or []) or "- none"
    metric_table = dataframe_to_markdown(
        metrics,
        [
            "phase_offset_days",
            "start_date_utc",
            "net_return",
            "net_return_ratio_vs_phase0",
            "sharpe",
            "sharpe_delta_vs_phase0",
            "max_drawdown",
            "max_drawdown_delta_vs_phase0",
            "turnover",
            "trade_count",
            "rebalance_count",
            "data_gap_blocker_count",
        ],
    )
    corr_table = dataframe_to_markdown(
        correlations,
        ["phase_offset_days", "mtm_return_corr_vs_phase0"],
    )
    lines = [
        "# hv_balanced 10d rebalance phase sensitivity",
        "",
        f"- generated_at_utc: `{summary['generated_at_utc']}`",
        f"- hard_status: `{summary['status']}`",
        f"- robustness_status: `{robustness.get('status')}`",
        f"- scenario: `{summary['scenario']}`",
        f"- fixed_config: `{summary['config_path']}`",
        f"- horizon_days: `{summary['horizon_days']}`",
        f"- phase_offsets_days: `{summary['phase_offsets_days']}`",
        f"- score_frame_reused_across_phases: `{summary['score_frame_reused_across_phases']}`",
        f"- selected_universe_count: `{dataset.get('selected_universe_count')}`",
        f"- scored_row_count: `{summary['scored_row_count']}`",
        f"- dataset_reproduction_status: `{dataset_reproduction.get('status')}`",
        f"- phase0_frozen_baseline_reproduction_status: `{baseline_reproduction.get('status')}`",
        f"- funding_sample_positive_row_count: `{diagnostics.get('funding_sample_positive_row_count')}`",
        "",
        "## Metric table",
        "",
        metric_table,
        "",
        "## MTM return correlation vs phase 0",
        "",
        corr_table,
        "",
        "## Robustness thresholds",
        "",
        f"- min_net_return_ratio_vs_phase0: `{robustness.get('thresholds', {}).get('min_net_return_ratio_vs_phase0')}`",
        f"- min_sharpe: `{robustness.get('thresholds', {}).get('min_sharpe')}`",
        f"- max_dd_abs: `{robustness.get('thresholds', {}).get('max_dd_abs')}`",
        f"- max_dd_delta_vs_phase0: `{robustness.get('thresholds', {}).get('max_dd_delta_vs_phase0')}`",
        "",
        "## Interpretation guardrails",
        "",
        "- This test keeps alpha score, features, PIT universe policy, eligibility, risk brakes, reference capital, and execution cost scenario fixed.",
        "- The only changed variable is the 10d rebalance phase: phase 0 starts from the original first timestamp; phase 1 starts one daily bar later; ...; phase 9 starts nine daily bars later.",
        "- Each shifted phase uses the remaining available history to mimic choosing a different initial 10d anchor at launch.",
        "- This is a robustness diagnostic, not a live-trading permission gate by itself.",
        "",
        "## Robustness failures",
        "",
        failure_lines,
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
    phases = sorted(dict.fromkeys(int(item) for item in args.phases))
    if phases != list(DEFAULT_PHASES):
        raise SystemExit(f"Refusing non-contract phases: observed={phases}, required={list(DEFAULT_PHASES)}")
    if int(args.horizon_days) != DEFAULT_HORIZON_DAYS:
        raise SystemExit(f"Refusing non-contract horizon_days={args.horizon_days}; required={DEFAULT_HORIZON_DAYS}")

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
    base_config = fixed["config"]
    run_config = interval_sensitivity.interval_config(base_config, DEFAULT_HORIZON_DAYS)
    scored_frame = fixed["scored_frame"]
    phase_audits: list[dict[str, Any]] = []
    metrics_by_phase: dict[int, dict[str, Any]] = {}
    metric_rows: list[dict[str, Any]] = []
    all_period_rows: list[dict[str, Any]] = []
    baseline_metrics: dict[str, Any] | None = None
    if not scored_frame.empty:
        for phase in phases:
            sliced, audit = phase_frame(scored_frame, phase_offset_days=phase)
            phase_audits.append(audit)
            metrics = _run_backtest(sliced, config=run_config, scenario=args.scenario, include_periods=True)
            metrics_by_phase[int(phase)] = metrics
            if phase == 0:
                baseline_metrics = metrics
            metric_rows.append(
                phase_metric_row(
                    phase_offset_days=phase,
                    phase_audit=audit,
                    metrics=metrics,
                    baseline=baseline_metrics,
                )
            )
            all_period_rows.extend(phase_period_rows(phase, metrics))

    metrics_df = pd.DataFrame(metric_rows)
    if metrics_df.empty:
        metrics_df = pd.DataFrame(columns=["phase_offset_days"])
    else:
        metrics_df = metrics_df.sort_values("phase_offset_days").reset_index(drop=True)
    periods_df = pd.DataFrame(all_period_rows)
    if periods_df.empty:
        periods_df = pd.DataFrame(columns=["phase_offset_days", "timestamp_ms", "date_utc"])
    else:
        periods_df = periods_df.sort_values(["phase_offset_days", "timestamp_ms"]).reset_index(drop=True)
    paired_mtm = build_paired_mtm(periods_df, phases)
    correlations = build_phase_correlation(paired_mtm, phases)
    if not correlations.empty and not metrics_df.empty:
        metrics_df = metrics_df.merge(correlations, on="phase_offset_days", how="left")

    baseline_reproduction = interval_sensitivity.compare_baseline(
        ten_day_metrics=metrics_by_phase.get(0),
        baseline_report_path=baseline_report,
        tolerance=float(args.baseline_tolerance),
    )
    dataset_reproduction = interval_sensitivity.compare_dataset_reproduction(
        current_manifest=fixed["dataset_manifest"],
        baseline_report_path=baseline_report,
    )
    blockers = list(fixed["blockers"])
    if dataset_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_dataset_reproduction_failed", "detail": dataset_reproduction})
    if baseline_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_phase0_baseline_reproduction_failed", "detail": baseline_reproduction})
    for phase, metrics in metrics_by_phase.items():
        gaps = list(metrics.get("data_gap_blockers") or [])
        if gaps:
            blockers.append(
                {
                    "code": "phase_execution_data_gap_blockers",
                    "phase_offset_days": int(phase),
                    "data_gap_blocker_count": len(gaps),
                    "sample": gaps[:10],
                }
            )
        if int(metrics.get("rebalance_count", 0) or 0) <= 0:
            blockers.append({"code": "phase_no_rebalances", "phase_offset_days": int(phase)})
        if int(metrics.get("trade_count", 0) or 0) <= 0:
            blockers.append({"code": "phase_no_trades", "phase_offset_days": int(phase)})

    robustness = evaluate_robustness(metrics_df, args)
    status = "blocked" if blockers else str(robustness.get("status") or "blocked")
    artifact_paths = {
        "summary_json": str(output_root / "summary.json"),
        "phase_metrics_csv": str(output_root / "phase_metrics.csv"),
        "period_returns_long_csv": str(output_root / "period_returns_long.csv"),
        "paired_mtm_curve_csv": str(output_root / "paired_mtm_curve.csv"),
        "phase_correlation_csv": str(output_root / "phase_correlation.csv"),
        "scored_frame_diagnostics_json": str(output_root / "scored_frame_diagnostics.json"),
        "markdown_report": str(doc_path),
    }
    summary = {
        "schema": "hv_balanced_rebalance_phase_sensitivity.v1",
        "generated_at_utc": utc_now_iso(),
        "status": status,
        "scenario": args.scenario,
        "horizon_days": DEFAULT_HORIZON_DAYS,
        "phase_offsets_days": phases,
        "config_path": fixed["config_path"],
        "as_of": fixed["as_of"],
        "funding_root": fixed["funding_root"],
        "score_frame_reused_across_phases": True,
        "scored_row_count": int(len(scored_frame)),
        "phase_audits": phase_audits,
        "dataset_manifest": fixed["dataset_manifest"],
        "gap_audit_summary": fixed["gap_audit_summary"],
        "scoring_audit": fixed["scoring_audit"],
        "execution_gap_policy": fixed["execution_gap_policy"],
        "partition_path_compatibility": partition_path_compatibility,
        "frozen_row_alignment": frozen_row_alignment,
        "dataset_reproduction": dataset_reproduction,
        "scored_frame_diagnostics": interval_sensitivity.scored_frame_diagnostics(scored_frame),
        "baseline_reproduction": baseline_reproduction,
        "robustness": robustness,
        "blockers": blockers,
        "artifact_paths": artifact_paths,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    metrics_df.to_csv(output_root / "phase_metrics.csv", index=False)
    periods_df.to_csv(output_root / "period_returns_long.csv", index=False)
    paired_mtm.to_csv(output_root / "paired_mtm_curve.csv", index=False)
    correlations.to_csv(output_root / "phase_correlation.csv", index=False)
    write_json(output_root / "scored_frame_diagnostics.json", summary["scored_frame_diagnostics"])
    write_json(output_root / "summary.json", summary)
    write_report(
        doc_path=doc_path,
        summary=summary,
        metrics=metrics_df,
        correlations=correlations,
        artifact_paths=artifact_paths,
    )
    print(
        json.dumps(
            {
                "status": status,
                "robustness_status": robustness.get("status"),
                "phase_metrics": json_safe(metrics_df.to_dict(orient="records")),
                "robustness_failures": json_safe(robustness.get("failures") or []),
                "artifact_paths": artifact_paths,
                "blocker_count": len(blockers),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
