from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    build_regime_by_ts,
    evaluate_admission_v2,
    load_feature_admission_v2_contract,
    sanitize_for_json,
)


DEFAULT_FEATURE_PANEL = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-05-02-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)
DEFAULT_M3_2_PANEL = ROOT / "artifacts" / "quant_research" / "onchain" / "m3_2_feature_panel_1d.csv"
DEFAULT_REPORT_DIR = ROOT / "artifacts" / "quant_research" / "factor_reports"
BASELINE_COLUMNS = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
    "liq_cascade_recency_score_5d",
]
PUBLIC_COLUMNS = [
    "funding_zscore_20",
    "momentum_20",
    "realized_volatility_20",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run first-pass MF-13 / MF-14 admission on fused M3.2 panel.")
    parser.add_argument("--feature-panel", type=Path, default=DEFAULT_FEATURE_PANEL)
    parser.add_argument("--m3-panel", type=Path, default=DEFAULT_M3_2_PANEL)
    parser.add_argument("--report-date", default=datetime.now().astimezone().date().isoformat())
    parser.add_argument("--threshold", type=float, default=0.75)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    features = pd.read_csv(args.feature_panel, compression="gzip")
    m3_panel = pd.read_csv(args.m3_panel)
    if features.empty:
        raise RuntimeError(f"feature panel is empty: {args.feature_panel}")
    if m3_panel.empty:
        raise RuntimeError(f"m3_2 panel is empty: {args.m3_panel}")

    features = features.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    features["target_forward_return_h5d"] = _forward_return(features, 5)
    features["target_forward_return_h10d"] = _forward_return(features, 10)

    join_columns = [
        "decision_date_utc",
        "m3_2_panel_ready",
        "m3_2_stable_supply_impulse_state",
        "m3_2_stable_dry_powder_state",
        "m3_2_stable_btc_flow_asymmetry_state",
        "m3_2_btc_sell_pressure_state",
        "m3_2_reflexive_rebound_state",
        "m3_2_tron_flow_impulse_state",
        "m3_2_tron_flow_quality_state",
        "m3_2_tron_speculative_heat_state",
    ]
    merged = features.merge(
        m3_panel[join_columns],
        left_on="date_utc",
        right_on="decision_date_utc",
        how="left",
    )
    merged["m3_2_panel_ready"] = _as_bool(merged["m3_2_panel_ready"])
    merged = merged[merged["m3_2_panel_ready"]].copy()
    if merged.empty:
        raise RuntimeError("no overlap between cross-sectional panel and m3_2 decision dates")

    _build_candidates(merged, threshold=float(args.threshold))

    regime_by_ts = build_regime_by_ts(merged, anchor_subject="BTC")
    contract = load_feature_admission_v2_contract()
    baseline_df = merged[[column for column in BASELINE_COLUMNS if column in merged.columns]].apply(
        pd.to_numeric,
        errors="coerce",
    )
    public_df = merged[[column for column in PUBLIC_COLUMNS if column in merged.columns]].apply(
        pd.to_numeric,
        errors="coerce",
    )
    capacity_score = pd.to_numeric(merged["rolling_median_quote_volume_usd_30d"], errors="coerce")
    timestamps = merged["timestamp_ms"]
    subjects = merged["subject"]

    candidates = [
        {
            "factor_id": "MF13_supply_beta_gate_v1",
            "column": "mf13_supply_beta_gate_v1",
            "family": "MF-13",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR stable supply impulse state loses regime sign consistency",
        },
        {
            "factor_id": "MF13_flow_rotation_gate_v1",
            "column": "mf13_flow_rotation_gate_v1",
            "family": "MF-13",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR stable/BTC flow asymmetry stops rewarding rotation winners",
        },
        {
            "factor_id": "MF13_flow_idio_gate_v1",
            "column": "mf13_flow_idio_gate_v1",
            "family": "MF-13",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR flow asymmetry stops rewarding idiosyncratic names",
        },
        {
            "factor_id": "MF13_tron_flow_impulse_defensive_beta_gate_v1",
            "column": "mf13_tron_flow_impulse_defensive_beta_gate_v1",
            "family": "MF-13",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR USDT_TRX flow impulse stops rewarding defensive beta on trigger days",
        },
        {
            "factor_id": "MF13_tron_flow_impulse_idio_gate_v1",
            "column": "mf13_tron_flow_impulse_idio_gate_v1",
            "family": "MF-13",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR USDT_TRX flow impulse stops rewarding idiosyncratic names on trigger days",
        },
        {
            "factor_id": "MF13_tron_speculative_heat_defensive_beta_gate_v1",
            "column": "mf13_tron_speculative_heat_defensive_beta_gate_v1",
            "family": "MF-13",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR extreme USDT_TRX speculative heat stops rewarding defensive beta on trigger days",
        },
        {
            "factor_id": "MF14_sell_pressure_defensive_gate_v1",
            "column": "mf14_sell_pressure_defensive_gate_v1",
            "family": "MF-14",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR exchange-flow sell pressure stops favoring defensive beta",
        },
        {
            "factor_id": "MF14_capitulation_rebound_idio_gate_v1",
            "column": "mf14_capitulation_rebound_idio_gate_v1",
            "family": "MF-14",
            "falsification": "active-day G6 residual IC < 0.02 for 90d OR capitulation-rebound windows stop rewarding idiosyncratic rebound names",
        },
    ]

    report_dir = DEFAULT_REPORT_DIR / args.report_date
    report_dir.mkdir(parents=True, exist_ok=True)
    candidate_export_path = report_dir / "m3_2_admission_candidate_scores.csv.gz"
    merged[
        [
            "date_utc",
            "timestamp_ms",
            "subject",
            "mf13_supply_beta_gate_v1",
            "mf13_flow_rotation_gate_v1",
            "mf13_flow_idio_gate_v1",
            "mf13_tron_flow_impulse_defensive_beta_gate_v1",
            "mf13_tron_flow_impulse_idio_gate_v1",
            "mf13_tron_speculative_heat_defensive_beta_gate_v1",
            "mf14_sell_pressure_defensive_gate_v1",
            "mf14_capitulation_rebound_idio_gate_v1",
        ]
    ].to_csv(candidate_export_path, index=False, compression="gzip")

    results: list[dict[str, object]] = []
    for horizon_column in ("target_forward_return_h5d", "target_forward_return_h10d"):
        target = pd.to_numeric(merged[horizon_column], errors="coerce")
        for candidate in candidates:
            factor = pd.to_numeric(merged[candidate["column"]], errors="coerce")
            admission = evaluate_admission_v2(
                factor=factor,
                target=target,
                timestamps=timestamps,
                subjects=subjects,
                baseline_df=baseline_df,
                public_df=public_df,
                capacity_score=capacity_score,
                regime_by_ts=regime_by_ts,
                falsification=str(candidate["falsification"]),
                contract=contract,
            )
            active_mask = factor.notna() & target.notna()
            results.append(
                {
                    "factor_id": candidate["factor_id"],
                    "family": candidate["family"],
                    "column": candidate["column"],
                    "target_horizon": horizon_column,
                    "active_rows": int(active_mask.sum()),
                    "active_timestamps": int(merged.loc[active_mask, "timestamp_ms"].nunique()),
                    "active_subjects": int(merged.loc[active_mask, "subject"].nunique()),
                    "gates": admission["gates"],
                    "verdict": admission["verdict"],
                    "gate_pass_count": admission["gate_pass_count"],
                    "gate_total": admission["gate_total"],
                    "g6_strict_pass": admission["g6_strict_pass"],
                    "g3_strict_pass": admission["g3_strict_pass"],
                }
            )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "feature_panel_path": str(args.feature_panel.resolve()),
        "m3_panel_path": str(args.m3_panel.resolve()),
        "candidate_export_path": str(candidate_export_path),
        "threshold": float(args.threshold),
        "study_start_date_utc": str(merged["date_utc"].min()),
        "study_end_date_utc": str(merged["date_utc"].max()),
        "study_row_count": int(merged.shape[0]),
        "study_subject_count": int(merged["subject"].nunique()),
        "study_timestamp_count": int(merged["timestamp_ms"].nunique()),
        "results": results,
    }
    report_path = report_dir / "m3_2_mf13_mf14_admission_report.json"
    report_path.write_text(
        json.dumps(sanitize_for_json(summary), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(str(report_path))
    return 0


def _forward_return(frame: pd.DataFrame, horizon: int) -> pd.Series:
    close = pd.to_numeric(frame["spot_close"], errors="coerce").replace(0.0, pd.NA)
    return close.groupby(frame["subject"]).shift(-horizon) / close - 1.0


def _as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _build_candidates(frame: pd.DataFrame, *, threshold: float) -> None:
    beta = pd.to_numeric(frame["lead_lag_beta_btc"], errors="coerce")
    rotation = pd.to_numeric(frame["quote_share_change_30d"], errors="coerce")
    idio = pd.to_numeric(frame["idiosyncratic_share"], errors="coerce")
    state_supply = pd.to_numeric(frame["m3_2_stable_supply_impulse_state"], errors="coerce")
    state_flow = pd.to_numeric(frame["m3_2_stable_btc_flow_asymmetry_state"], errors="coerce")
    state_sell = pd.to_numeric(frame["m3_2_btc_sell_pressure_state"], errors="coerce")
    state_rebound = pd.to_numeric(frame["m3_2_reflexive_rebound_state"], errors="coerce")
    state_tron_impulse = pd.to_numeric(frame["m3_2_tron_flow_impulse_state"], errors="coerce")
    state_tron_heat = pd.to_numeric(frame["m3_2_tron_speculative_heat_state"], errors="coerce")
    tron_hard_threshold = max(float(threshold), 1.0)

    frame["mf13_supply_beta_gate_v1"] = beta.where(state_supply > threshold)
    frame["mf13_flow_rotation_gate_v1"] = rotation.where(state_flow > threshold)
    frame["mf13_flow_idio_gate_v1"] = idio.where(state_flow > threshold)
    frame["mf13_tron_flow_impulse_defensive_beta_gate_v1"] = (-beta).where(
        state_tron_impulse > tron_hard_threshold
    )
    frame["mf13_tron_flow_impulse_idio_gate_v1"] = idio.where(
        state_tron_impulse > tron_hard_threshold
    )
    frame["mf13_tron_speculative_heat_defensive_beta_gate_v1"] = (-beta).where(
        state_tron_heat > tron_hard_threshold
    )
    frame["mf14_sell_pressure_defensive_gate_v1"] = (-beta).where(state_sell > threshold)
    frame["mf14_capitulation_rebound_idio_gate_v1"] = idio.where(state_rebound > threshold)


if __name__ == "__main__":
    raise SystemExit(main())
