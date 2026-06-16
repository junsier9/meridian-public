from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import portable_path, write_json
from enhengclaw.quant_research.fixed_set_comparison import performance_summary, periods_per_year
from enhengclaw.quant_research.regime_gating import (
    REGIME_GATING_CONTRACT_VERSION,
    regime_gating_component_frame,
)


BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d"
EFFECTIVE_RESEARCH_BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve"
DEFAULT_FEATURES_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)
DEFAULT_LATEST_FEATURES_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-05-31-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)
DEFAULT_PERIOD_RETURNS_CSV = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-02-no-overlay-formal-alpha_ontology_h10d_overlay_ablation-v5_rw_bridge_no_overlay_h10d"
    / "aligned_period_returns.csv"
)

COMPONENTS: list[dict[str, str]] = [
    {
        "label": "shock_fraction_f49",
        "regime": "shock_co_occurrence",
        "multiplier_col": "m_shock_fraction_f49",
        "gauge_col": "f49_shock_co_occurrence_index",
    },
    {
        "label": "shock_cluster_f26",
        "regime": "shock_cluster_3d",
        "multiplier_col": "m_shock_cluster_f26",
        "gauge_col": "f26_relative_cluster_intensity",
    },
    {
        "label": "low_dispersion_f44",
        "regime": "low_cross_sectional_dispersion",
        "multiplier_col": "m_low_dispersion_f44",
        "gauge_col": "f44_dispersion_of_returns",
    },
    {
        "label": "btc_vol_regime_f55",
        "regime": "btc_realized_vol_quantile",
        "multiplier_col": "m_btc_vol_regime_f55",
        "gauge_col": "f55_btc_vol_regime_quantile",
    },
    {
        "label": "slow_grind_trailing_return",
        "regime": "negative_trailing_universe_return",
        "multiplier_col": "m_trailing_universe_return",
        "gauge_col": "trailing_universe_mean_return_30d",
    },
    {
        "label": "btc_dvol_range",
        "regime": "btc_options_vol_of_vol",
        "multiplier_col": "m_btc_dvol_range",
        "gauge_col": "btc_dvol_range_z90",
    },
    {
        "label": "eth_dvol_range",
        "regime": "eth_options_vol_of_vol",
        "multiplier_col": "m_eth_dvol_range",
        "gauge_col": "eth_dvol_range_z90",
    },
    {
        "label": "regime_gating_v1_combined",
        "regime": "combined_v1_f49_f26_f44",
        "multiplier_col": "multiplier_v1",
        "gauge_col": "multiplier_v1",
    },
    {
        "label": "regime_gating_v2_combined",
        "regime": "combined_v2_v1_f55_trailing",
        "multiplier_col": "multiplier_v2",
        "gauge_col": "multiplier_v2",
    },
    {
        "label": "regime_gating_v3_combined",
        "regime": "combined_v3_v2_dvol",
        "multiplier_col": "multiplier_v3",
        "gauge_col": "multiplier_v3",
    },
]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (ROOT / path).resolve()


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return out


def _distribution_summary(
    components: pd.DataFrame,
    *,
    active_threshold: float,
    strong_threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in COMPONENTS:
        col = item["multiplier_col"]
        if col not in components.columns:
            continue
        series = pd.to_numeric(components[col], errors="coerce").dropna()
        if series.empty:
            continue
        rows.append(
            {
                "label": item["label"],
                "regime": item["regime"],
                "multiplier_col": col,
                "gauge_col": item["gauge_col"],
                "n_dates": int(series.shape[0]),
                "active_fraction": float((series < active_threshold).mean()),
                "strong_throttle_fraction": float((series < strong_threshold).mean()),
                "mean_multiplier": float(series.mean()),
                "median_multiplier": float(series.median()),
                "min_multiplier": float(series.min()),
                "last_date_utc": str(components["date_utc"].iloc[-1]),
                "last_multiplier": _float(series.iloc[-1]),
            }
        )
    return rows


def _load_period_returns(path: Path, *, baseline_label: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    base_col = f"{baseline_label}__no_overlay"
    if base_col not in frame.columns:
        raise ValueError(f"period returns missing base column {base_col!r}: {path}")
    frame["timestamp_ms"] = pd.to_numeric(frame["timestamp_ms"], errors="raise").astype("int64")
    frame[base_col] = pd.to_numeric(frame[base_col], errors="coerce").fillna(0.0)
    return frame.sort_values("timestamp_ms").reset_index(drop=True)


def _whole_overlay_summary(
    periods: pd.DataFrame,
    *,
    baseline_label: str,
    periods_per_year_value: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_col = f"{baseline_label}__no_overlay"
    base_perf = performance_summary(periods[base_col], periods_per_year=periods_per_year_value)
    for col in [c for c in periods.columns if c.startswith(f"{baseline_label}__")]:
        overlay_label = col.split("__", 1)[1]
        perf = performance_summary(periods[col], periods_per_year=periods_per_year_value)
        rows.append(
            {
                "overlay_label": overlay_label,
                "period_count": int(periods[col].shape[0]),
                "cumulative_net_return": float(perf["net_return"]),
                "period_sharpe": float(perf["sharpe"]),
                "max_drawdown": float(perf["max_drawdown"]),
                "delta_cumulative_net_return_vs_no_overlay": float(
                    perf["net_return"] - base_perf["net_return"]
                ),
                "delta_period_sharpe_vs_no_overlay": float(perf["sharpe"] - base_perf["sharpe"]),
                "sum_period_return_delta_vs_no_overlay": float((periods[col] - periods[base_col]).sum()),
            }
        )
    return rows


def _recommendation(
    *,
    active_periods: int,
    min_active_periods: int,
    active_mean_return: float | None,
    inactive_mean_return: float | None,
    estimated_delta_sum: float,
    protection_hit_rate: float | None,
) -> str:
    if active_periods < min_active_periods:
        return "insufficient_sample"
    if active_mean_return is None or inactive_mean_return is None:
        return "insufficient_sample"
    if estimated_delta_sum > 0.0 and active_mean_return < inactive_mean_return:
        return "supports_throttle"
    if estimated_delta_sum > 0.0 and (protection_hit_rate or 0.0) >= 0.55:
        return "weak_support"
    if estimated_delta_sum < 0.0 and active_mean_return >= 0.0:
        return "do_not_throttle"
    return "mixed"


def _component_attribution(
    periods: pd.DataFrame,
    components: pd.DataFrame,
    *,
    baseline_label: str,
    active_threshold: float,
    strong_threshold: float,
    min_active_periods: int,
    periods_per_year_value: int,
) -> list[dict[str, Any]]:
    base_col = f"{baseline_label}__no_overlay"
    merged = periods.merge(components, on="timestamp_ms", how="left", suffixes=("", "_component"))
    rows: list[dict[str, Any]] = []
    for item in COMPONENTS:
        col = item["multiplier_col"]
        if col not in merged.columns:
            continue
        multiplier = pd.to_numeric(merged[col], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
        base_return = pd.to_numeric(merged[base_col], errors="coerce").fillna(0.0)
        active = multiplier < active_threshold
        inactive = ~active
        active_returns = base_return[active]
        inactive_returns = base_return[inactive]
        approx_return = base_return * multiplier
        approx_delta = approx_return - base_return
        active_delta = approx_delta[active]
        active_perf = performance_summary(active_returns, periods_per_year=periods_per_year_value)
        inactive_perf = performance_summary(inactive_returns, periods_per_year=periods_per_year_value)
        active_periods = int(active.sum())
        protection_hit_rate = (
            float((active_delta > 0.0).mean()) if active_periods > 0 else None
        )
        active_mean_return = float(active_returns.mean()) if active_periods > 0 else None
        inactive_mean_return = float(inactive_returns.mean()) if int(inactive.sum()) > 0 else None
        estimated_delta_sum = float(active_delta.sum()) if active_periods > 0 else 0.0
        rows.append(
            {
                "label": item["label"],
                "regime": item["regime"],
                "multiplier_col": col,
                "gauge_col": item["gauge_col"],
                "period_count": int(merged.shape[0]),
                "active_periods": active_periods,
                "active_fraction": float(active.mean()),
                "strong_throttle_periods": int((multiplier < strong_threshold).sum()),
                "active_mean_multiplier": float(multiplier[active].mean()) if active_periods > 0 else None,
                "active_min_multiplier": float(multiplier[active].min()) if active_periods > 0 else None,
                "active_mean_no_overlay_period_return": active_mean_return,
                "inactive_mean_no_overlay_period_return": inactive_mean_return,
                "active_no_overlay_cumulative_return": float(active_perf["net_return"]),
                "inactive_no_overlay_cumulative_return": float(inactive_perf["net_return"]),
                "active_no_overlay_sharpe": float(active_perf["sharpe"]),
                "inactive_no_overlay_sharpe": float(inactive_perf["sharpe"]),
                "estimated_linear_delta_sum_vs_no_overlay": estimated_delta_sum,
                "estimated_linear_delta_mean_vs_no_overlay": (
                    float(active_delta.mean()) if active_periods > 0 else None
                ),
                "protection_hit_rate": protection_hit_rate,
                "drag_hit_rate": (
                    float((active_delta < 0.0).mean()) if active_periods > 0 else None
                ),
                "recommendation": _recommendation(
                    active_periods=active_periods,
                    min_active_periods=min_active_periods,
                    active_mean_return=active_mean_return,
                    inactive_mean_return=inactive_mean_return,
                    estimated_delta_sum=estimated_delta_sum,
                    protection_hit_rate=protection_hit_rate,
                ),
            }
        )
    return rows


def _format_float(value: Any, digits: int = 3) -> str:
    number = _float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Regime Overlay Component Ablation")
    lines.append("")
    lines.append(f"- Score parent: `{payload['score_parent_label']}`")
    lines.append(f"- Effective research baseline: `{payload['effective_research_baseline_label']}`")
    lines.append(f"- Performance stream status: `{payload['performance_stream_status']}`")
    lines.append(f"- Status: `{payload['status']}`")
    lines.append(f"- Contract: `{payload['regime_gating_contract_version']}`")
    lines.append(f"- Performance period returns: `{payload['inputs']['period_returns_csv']}`")
    lines.append(f"- Performance features: `{payload['inputs']['features_artifact']}`")
    lines.append(f"- Latest distribution features: `{payload['inputs']['latest_features_artifact']}`")
    lines.append("")
    lines.append("## Whole Overlay")
    lines.append("")
    lines.append("| Overlay | N | CumRet | Sharpe | Max DD | CumRet Delta | Sharpe Delta |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in payload["whole_overlay_summary"]:
        lines.append(
            "| {label} | {n} | {cum} | {sharpe} | {dd} | {dcum} | {dsharpe} |".format(
                label=row["overlay_label"],
                n=row["period_count"],
                cum=_format_float(row["cumulative_net_return"], 3),
                sharpe=_format_float(row["period_sharpe"], 3),
                dd=_format_float(row["max_drawdown"], 3),
                dcum=_format_float(row["delta_cumulative_net_return_vs_no_overlay"], 3),
                dsharpe=_format_float(row["delta_period_sharpe_vs_no_overlay"], 3),
            )
        )
    lines.append("")
    lines.append("## Component Attribution")
    lines.append("")
    lines.append("| Component | Active N | Active Mean M | Active Base Mean | Inactive Base Mean | Est Delta Sum | Protect Hit | Recommendation |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in payload["component_attribution"]:
        lines.append(
            "| {label} | {n} | {m} | {amean} | {imean} | {delta} | {hit} | `{rec}` |".format(
                label=row["label"],
                n=row["active_periods"],
                m=_format_float(row["active_mean_multiplier"], 3),
                amean=_format_float(row["active_mean_no_overlay_period_return"], 4),
                imean=_format_float(row["inactive_mean_no_overlay_period_return"], 4),
                delta=_format_float(row["estimated_linear_delta_sum_vs_no_overlay"], 4),
                hit=_format_float(row["protection_hit_rate"], 3),
                rec=row["recommendation"],
            )
        )
    lines.append("")
    lines.append("## Latest Multiplier Distribution")
    lines.append("")
    lines.append("| Component | Active Frac | Strong Frac | Mean M | Min M | Last Date | Last M |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- | ---: |")
    for row in payload["latest_distribution_summary"]:
        lines.append(
            "| {label} | {af} | {sf} | {mean} | {minv} | {date} | {last} |".format(
                label=row["label"],
                af=_format_float(row["active_fraction"], 3),
                sf=_format_float(row["strong_throttle_fraction"], 3),
                mean=_format_float(row["mean_multiplier"], 3),
                minv=_format_float(row["min_multiplier"], 3),
                date=row["last_date_utc"],
                last=_format_float(row["last_multiplier"], 3),
            )
        )
    lines.append("")
    lines.append("## Interpretation Boundary")
    lines.append("")
    lines.append(
        "Component attribution is a linear sizing diagnostic on no-overlay period returns. "
        "The default period-return stream is the historical single-phase formal artifact, "
        "not the current 10-phase equal-sleeve research baseline. It is not a promotion gate "
        "and does not update score, manifests, or live config."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Component-level regime overlay ablation for the h10d baseline.")
    parser.add_argument("--baseline-label", default=BASELINE_LABEL)
    parser.add_argument("--effective-baseline-label", default=EFFECTIVE_RESEARCH_BASELINE_LABEL)
    parser.add_argument("--features-artifact", type=Path, default=DEFAULT_FEATURES_ARTIFACT)
    parser.add_argument("--latest-features-artifact", type=Path, default=DEFAULT_LATEST_FEATURES_ARTIFACT)
    parser.add_argument("--period-returns-csv", type=Path, default=DEFAULT_PERIOD_RETURNS_CSV)
    parser.add_argument("--active-threshold", type=float, default=0.999)
    parser.add_argument("--strong-threshold", type=float, default=0.75)
    parser.add_argument("--min-active-periods", type=int, default=6)
    parser.add_argument("--run-label", default="2026-06-03-research-v5-rw-bridge-no-overlay-h10d-regime-overlay-component-ablation")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports" / "2026-06-03",
    )
    args = parser.parse_args(argv)

    features_artifact = _resolve(args.features_artifact)
    latest_features_artifact = _resolve(args.latest_features_artifact)
    period_returns_csv = _resolve(args.period_returns_csv)
    output_root = _resolve(args.output_root) / str(args.run_label)
    output_root.mkdir(parents=True, exist_ok=True)

    perf_components = regime_gating_component_frame(features_artifact, include_v3=True)
    latest_components = regime_gating_component_frame(latest_features_artifact, include_v3=True)
    periods = _load_period_returns(period_returns_csv, baseline_label=str(args.baseline_label))
    annualization = periods_per_year(bar_interval_ms=86400000, evaluation_step_bars=10)

    payload = {
        "status": "computed",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "score_parent_label": str(args.baseline_label),
        "effective_research_baseline_label": str(args.effective_baseline_label),
        "performance_stream_status": "single_phase_no_overlay_stream_not_current_multiphase_baseline",
        "baseline_label": str(args.baseline_label),
        "regime_gating_contract_version": REGIME_GATING_CONTRACT_VERSION,
        "diagnostic_contract": "regime_overlay_component_ablation.v1",
        "thresholds": {
            "active_threshold": float(args.active_threshold),
            "strong_threshold": float(args.strong_threshold),
            "min_active_periods": int(args.min_active_periods),
            "periods_per_year": int(annualization),
        },
        "inputs": {
            "features_artifact": portable_path(features_artifact, repo_root=ROOT),
            "latest_features_artifact": portable_path(latest_features_artifact, repo_root=ROOT),
            "period_returns_csv": portable_path(period_returns_csv, repo_root=ROOT),
        },
        "whole_overlay_summary": _whole_overlay_summary(
            periods,
            baseline_label=str(args.baseline_label),
            periods_per_year_value=int(annualization),
        ),
        "performance_feature_distribution_summary": _distribution_summary(
            perf_components,
            active_threshold=float(args.active_threshold),
            strong_threshold=float(args.strong_threshold),
        ),
        "latest_distribution_summary": _distribution_summary(
            latest_components,
            active_threshold=float(args.active_threshold),
            strong_threshold=float(args.strong_threshold),
        ),
        "component_attribution": _component_attribution(
            periods,
            perf_components,
            baseline_label=str(args.baseline_label),
            active_threshold=float(args.active_threshold),
            strong_threshold=float(args.strong_threshold),
            min_active_periods=int(args.min_active_periods),
            periods_per_year_value=int(annualization),
        ),
        "artifacts": {
            "summary_json": portable_path(output_root / "summary.json", repo_root=ROOT),
            "summary_md": portable_path(output_root / "summary.md", repo_root=ROOT),
            "component_multipliers_csv": portable_path(output_root / "component_multipliers.csv", repo_root=ROOT),
            "latest_component_multipliers_csv": portable_path(output_root / "latest_component_multipliers.csv", repo_root=ROOT),
        },
    }

    perf_components.to_csv(output_root / "component_multipliers.csv", index=False)
    latest_components.to_csv(output_root / "latest_component_multipliers.csv", index=False)
    write_json(output_root / "summary.json", payload)
    _write_markdown(output_root / "summary.md", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
