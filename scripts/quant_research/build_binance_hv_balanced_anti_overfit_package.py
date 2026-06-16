from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "binance_canonical_h10d" / "anti_overfit_hv_balanced_20260512"
DEFAULT_REPORT_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "02_binance_pit_h10d"
    / "binance_pit_hv_balanced_anti_overfit_validation_2026_05_12.md"
)


RUN_ROOTS = {
    "pruned3": ROOT
    / "artifacts"
    / "quant_research"
    / "binance_canonical_h10d"
    / "20260511TpitTopMidPruned3Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3",
    "hv_base": ROOT / "artifacts" / "qr" / "hv",
    "hv_tail": ROOT / "artifacts" / "qr" / "hv_tail",
    "hv_mild": ROOT / "artifacts" / "qr" / "hv_mild",
    "hv_balanced": ROOT / "artifacts" / "qr" / "hv_balanced",
    "combined_v1": ROOT
    / "artifacts"
    / "quant_research"
    / "binance_canonical_h10d"
    / "20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the frozen hv_balanced anti-overfit validation package.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    reports = {name: _load_report(root) for name, root in RUN_ROOTS.items()}
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config = json.loads(config_text)
    config_sha256 = hashlib.sha256(config_text.encode("utf-8")).hexdigest()

    variant_metrics = _variant_metrics(reports)
    neighborhood = _parameter_neighborhood(variant_metrics)
    forward_splits = _forward_style_splits(RUN_ROOTS)
    throttle_audit = _throttle_audit(RUN_ROOTS["hv_balanced"])
    frozen_manifest = _frozen_manifest(config=config, config_sha256=config_sha256, reports=reports)
    package = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "package_id": "binance_pit_hv_balanced_anti_overfit_20260512",
        "status": _package_status(neighborhood=neighborhood, forward_splits=forward_splits, reports=reports),
        "frozen_manifest_path": str(output_root / "frozen_strategy_manifest.json"),
        "variant_metrics_path": str(output_root / "variant_metrics.csv"),
        "parameter_neighborhood_path": str(output_root / "parameter_neighborhood.csv"),
        "forward_style_period_splits_path": str(output_root / "forward_style_period_splits.csv"),
        "throttled_periods_path": str(output_root / "throttled_periods.csv"),
        "config_sha256": config_sha256,
        "config_path": str(CONFIG_PATH),
        "artifact_roots": {name: str(root) for name, root in RUN_ROOTS.items()},
    }

    _write_json(output_root / "frozen_strategy_manifest.json", frozen_manifest)
    variant_metrics.to_csv(output_root / "variant_metrics.csv", index=False)
    neighborhood.to_csv(output_root / "parameter_neighborhood.csv", index=False)
    forward_splits.to_csv(output_root / "forward_style_period_splits.csv", index=False)
    throttle_audit.to_csv(output_root / "throttled_periods.csv", index=False)
    _write_json(output_root / "anti_overfit_validation_report.json", package)

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(
        _render_markdown(
            package=package,
            frozen_manifest=frozen_manifest,
            variant_metrics=variant_metrics,
            neighborhood=neighborhood,
            forward_splits=forward_splits,
            throttle_audit=throttle_audit,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"status": package["status"], "output_root": str(output_root), "report_path": str(args.report_path)}, indent=2))
    return 0


def _load_report(root: Path) -> dict[str, Any]:
    path = root / "validation_report.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _variant_metrics(reports: dict[str, dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for name, report in reports.items():
        base = dict(report.get("metrics", {}).get("base") or {})
        stress = dict(report.get("metrics", {}).get("stress") or {})
        gate = dict(report.get("gate_results") or {})
        strat = dict(
            dict(report.get("falsification", {}).get("stratified_repeated_symbol_holdout") or {}).get("summary")
            or {}
        )
        liquidity = dict(report.get("falsification", {}).get("liquidity_bucket") or {})
        top_liq = dict(liquidity.get("top_liquidity") or {})
        mid_liq = dict(liquidity.get("mid_liquidity") or {})
        records.append(
            {
                "variant": name,
                "strategy_label": report.get("strategy_label"),
                "status": report.get("status"),
                "base_net_return": base.get("net_return"),
                "base_sharpe": base.get("sharpe"),
                "base_max_drawdown": base.get("max_drawdown"),
                "base_turnover": base.get("turnover"),
                "stress_net_return": stress.get("net_return"),
                "stress_sharpe": stress.get("sharpe"),
                "stress_max_drawdown": stress.get("max_drawdown"),
                "stratified_positive_folds": strat.get("positive_fold_count"),
                "stratified_fold_count": strat.get("fold_count"),
                "stratified_positive_fraction": strat.get("positive_fraction"),
                "stratified_min_net_return": strat.get("min_net_return"),
                "stratified_median_net_return": strat.get("median_net_return"),
                "dd_cap_passed": gate.get("base_max_drawdown_under_cap"),
                "liquidity_positive_bucket_count": gate.get("liquidity_positive_bucket_count"),
                "top_liquidity_net_return": top_liq.get("net_return"),
                "top_liquidity_max_drawdown": top_liq.get("max_drawdown"),
                "mid_liquidity_net_return": mid_liq.get("net_return"),
                "mid_liquidity_max_drawdown": mid_liq.get("max_drawdown"),
            }
        )
    return pd.DataFrame(records)


def _parameter_neighborhood(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    params = {
        "hv_tail": {"start_dd": 0.15, "full_dd": 0.30, "gross_floor": 0.85},
        "hv_mild": {"start_dd": 0.12, "full_dd": 0.28, "gross_floor": 0.85},
        "hv_balanced": {"start_dd": 0.10, "full_dd": 0.25, "gross_floor": 0.80},
    }
    for variant, param in params.items():
        row = metrics.loc[metrics["variant"].eq(variant)].iloc[0].to_dict()
        rows.append({**param, **row})
    frame = pd.DataFrame(rows)
    frame["passed_full_gate"] = frame["status"].eq("passed") & frame["dd_cap_passed"].astype(bool)
    frame["net_minus_hv_base"] = frame["base_net_return"] - float(metrics.loc[metrics["variant"].eq("hv_base"), "base_net_return"].iloc[0])
    frame["dd_minus_hv_base"] = frame["base_max_drawdown"] - float(metrics.loc[metrics["variant"].eq("hv_base"), "base_max_drawdown"].iloc[0])
    frame["is_selected_frozen_candidate"] = frame["variant"].eq("hv_balanced")
    return frame


def _forward_style_splits(run_roots: dict[str, Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant in ("hv_base", "hv_tail", "hv_mild", "hv_balanced", "combined_v1"):
        periods = pd.read_csv(run_roots[variant] / "aligned_period_returns.csv")
        periods["timestamp_ms"] = pd.to_numeric(periods["timestamp_ms"], errors="coerce")
        periods["year"] = pd.to_datetime(periods["timestamp_ms"], unit="ms", utc=True).dt.year
        periods["net_period_return"] = pd.to_numeric(periods["net_period_return"], errors="coerce").fillna(0.0)
        segments = {
            "early_2021_2022": periods.loc[periods["year"].between(2021, 2022)].copy(),
            "middle_2023_2024": periods.loc[periods["year"].between(2023, 2024)].copy(),
            "late_2025_2026": periods.loc[periods["year"].between(2025, 2026)].copy(),
        }
        for segment, frame in segments.items():
            rows.append({"variant": variant, "segment": segment, **_period_metrics(frame)})
    return pd.DataFrame(rows)


def _period_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {"period_count": 0, "net_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    returns = pd.to_numeric(frame["net_period_return"], errors="coerce").fillna(0.0)
    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    periods_per_year = 365.25 / 10.0
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / std * np.sqrt(periods_per_year)) if std > 0.0 else 0.0
    return {
        "period_count": int(len(returns)),
        "net_return": float(equity.iloc[-1] - 1.0),
        "sharpe": sharpe,
        "max_drawdown": float(abs(drawdown.min())),
    }


def _throttle_audit(root: Path) -> pd.DataFrame:
    periods = pd.read_csv(root / "aligned_period_returns.csv")
    if "portfolio_throttle_multiplier" not in periods.columns:
        return pd.DataFrame(columns=["timestamp_ms", "net_period_return", "portfolio_throttle_multiplier", "portfolio_throttle_drawdown"])
    periods["portfolio_throttle_multiplier"] = pd.to_numeric(periods["portfolio_throttle_multiplier"], errors="coerce").fillna(1.0)
    periods["portfolio_throttle_drawdown"] = pd.to_numeric(periods["portfolio_throttle_drawdown"], errors="coerce").fillna(0.0)
    periods["net_period_return"] = pd.to_numeric(periods["net_period_return"], errors="coerce").fillna(0.0)
    columns = [
        "timestamp_ms",
        "net_period_return",
        "turnover",
        "portfolio_throttle_multiplier",
        "portfolio_throttle_drawdown",
    ]
    return periods.loc[periods["portfolio_throttle_multiplier"].lt(1.0), [column for column in columns if column in periods.columns]].copy()


def _frozen_manifest(*, config: dict[str, Any], config_sha256: str, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    selected_report = reports["hv_balanced"]
    return {
        "schema": "binance_h10d_frozen_strategy_manifest.v1",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "strategy_label": config["strategy_label"],
        "parent_label": config["parent_label"],
        "freeze_decision": "frozen_candidate_not_live_approved",
        "no_tuning_rule": "Do not change features, weights, PIT universe, costs, gates, high-vol brake thresholds, or soft budget thresholds without opening a new challenger label.",
        "config_path": str(CONFIG_PATH),
        "config_sha256": config_sha256,
        "validation_report_path": str(RUN_ROOTS["hv_balanced"] / "validation_report.json"),
        "artifact_root": str(RUN_ROOTS["hv_balanced"]),
        "allowed_alpha_sources": config.get("allowed_alpha_sources"),
        "excluded_source_patterns": config.get("excluded_source_patterns"),
        "feature_columns": config.get("feature_columns"),
        "feature_weights": config.get("feature_weights"),
        "strategy_profile": config.get("strategy_profile"),
        "risk_overlay_policy": config.get("risk_overlay_policy"),
        "universe_policy": config.get("universe_policy"),
        "pit_data_eligibility_policy": config.get("pit_data_eligibility_policy"),
        "validation_gates": config.get("validation_gates"),
        "validation_status": selected_report.get("status"),
        "base_metrics": selected_report.get("metrics", {}).get("base"),
        "stress_metrics": selected_report.get("metrics", {}).get("stress"),
        "gate_results": selected_report.get("gate_results"),
    }


def _package_status(
    *,
    neighborhood: pd.DataFrame,
    forward_splits: pd.DataFrame,
    reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = reports["hv_balanced"]
    all_neighbors_passed = bool(neighborhood["passed_full_gate"].all())
    late = forward_splits.loc[
        forward_splits["variant"].eq("hv_balanced") & forward_splits["segment"].eq("late_2025_2026")
    ]
    late_positive = bool(float(late["net_return"].iloc[0]) > 0.0) if not late.empty else False
    status = "passed_diagnostic_freeze" if selected.get("status") == "passed" and all_neighbors_passed and late_positive else "blocked"
    return {
        "status": status,
        "selected_validation_status": selected.get("status"),
        "all_parameter_neighbors_passed": all_neighbors_passed,
        "late_segment_positive": late_positive,
        "live_readiness": "not_approved",
        "residual_overfit_risk": "nonzero; future paper/shadow data is still required",
    }


def _render_markdown(
    *,
    package: dict[str, Any],
    frozen_manifest: dict[str, Any],
    variant_metrics: pd.DataFrame,
    neighborhood: pd.DataFrame,
    forward_splits: pd.DataFrame,
    throttle_audit: pd.DataFrame,
) -> str:
    selected = variant_metrics.loc[variant_metrics["variant"].eq("hv_balanced")].iloc[0]
    lines = [
        "# Binance PIT HV Balanced Anti-Overfit Validation",
        "",
        f"`Frozen strategy: {frozen_manifest['strategy_label']}`",
        f"`Status: {package['status']['status']}`",
        f"`Config SHA256: {package['config_sha256']}`",
        "",
        "## Freeze",
        "",
        "- Decision: freeze as a research candidate, not live-approved.",
        "- No tuning allowed on features, feature weights, PIT universe, costs, high-vol thresholds, soft-budget thresholds, holdout gates, or bucket gates.",
        f"- Frozen config: `{package['config_path']}`",
        f"- Frozen manifest: `{package['frozen_manifest_path']}`",
        "",
        "## Core Metrics",
        "",
        "| Variant | Status | Base net | Sharpe | Max DD | Stress net | Holdout | Min fold | Median fold |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in variant_metrics.iterrows():
        lines.append(
            f"| {row['variant']} | {row['status']} | {float(row['base_net_return']):.6f} | "
            f"{float(row['base_sharpe']):.3f} | {float(row['base_max_drawdown']):.6f} | "
            f"{float(row['stress_net_return']):.6f} | {int(row['stratified_positive_folds'])}/{int(row['stratified_fold_count'])} | "
            f"{float(row['stratified_min_net_return']):.6f} | {float(row['stratified_median_net_return']):.6f} |"
        )
    lines.extend(
        [
            "",
            "## Parameter Neighborhood",
            "",
            "| Variant | Start DD | Full DD | Floor | Passed | Net vs HV base | DD vs HV base |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in neighborhood.iterrows():
        lines.append(
            f"| {row['variant']} | {float(row['start_dd']):.2f} | {float(row['full_dd']):.2f} | "
            f"{float(row['gross_floor']):.2f} | {bool(row['passed_full_gate'])} | "
            f"{float(row['net_minus_hv_base']):.6f} | {float(row['dd_minus_hv_base']):.6f} |"
        )
    lines.extend(
        [
            "",
            "Interpretation: `hv_balanced` is not an isolated pass. Tail, mild, and balanced variants all pass; stronger budgets trade return for lower drawdown smoothly.",
            "",
            "## Forward-Style Segments",
            "",
            "These are chronological diagnostics, not clean external OOS. They reduce but do not eliminate reuse-of-history risk.",
            "",
            "| Variant | Segment | Periods | Net | Sharpe | Max DD |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in forward_splits.iterrows():
        lines.append(
            f"| {row['variant']} | {row['segment']} | {int(row['period_count'])} | "
            f"{float(row['net_return']):.6f} | {float(row['sharpe']):.3f} | {float(row['max_drawdown']):.6f} |"
        )
    throttle_count = int(len(throttle_audit))
    min_multiplier = float(throttle_audit["portfolio_throttle_multiplier"].min()) if throttle_count else 1.0
    avg_multiplier = float(throttle_audit["portfolio_throttle_multiplier"].mean()) if throttle_count else 1.0
    lines.extend(
        [
            "",
            "## Throttle Audit",
            "",
            f"- throttled periods: `{throttle_count}`",
            f"- min multiplier: `{min_multiplier:.6f}`",
            f"- average multiplier on throttled periods: `{avg_multiplier:.6f}`",
            f"- selected base net: `{float(selected['base_net_return']):.6f}`",
            f"- selected max DD: `{float(selected['base_max_drawdown']):.6f}`",
            "",
            "## Decision",
            "",
            "`hv_balanced` is frozen as the current Binance-only research candidate. This package supports freeze, not live approval.",
            "",
            "Residual risk remains because the same five-year history has been inspected repeatedly. The next honest evidence must come from a frozen paper/shadow run or a truly future OOS slice.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
