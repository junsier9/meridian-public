"""factor_report_card.py — 11-gate factor report card.

Implements the standard report card defined in
docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §G.4 against the 11
admission gates declared in §G.2 (G1 IC mean, G2 IC stability, G3 regime
sign-consistency, G4 concentration, G5 VIF, G6 orthogonal residual IC, G7
turnover, G8 capacity-aware IC, G9 crowding, G10 out-of-universe robustness,
G11 falsification trigger).

Default behaviour:
  * Re-build the cross-sectional feature panel via build_cross_sectional_feature_bundle
    using the panel inputs of the 2026-04-29 features artifact, so that W1.1
    factor columns are present alongside the v91 baseline columns.
  * Score the 13 W1.1 candidates and the 9 v91 baseline factors (22 total).
  * Use the 9 v91 factors as the "admitted baseline" for G5 / G6, with a
    self-exclusion when scoring a v91 factor against itself.
  * Use (funding_zscore_20, momentum_20, realized_volatility_20) as the
    "public factors" for G9.
  * Use BTC realized_volatility_20 tertiles as the G3 regime classifier.
  * Use rolling_median_quote_volume_usd_30d as the G8 / G10 capacity proxy.
  * Write per-factor JSON + per-factor text card to
    artifacts/quant_research/factor_reports/<report_date>/.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.features import (  # noqa: E402
    EXECUTION_ALIGNED_LABEL_CONTRACT_ID,
    build_cross_sectional_feature_bundle,
)
from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    FEATURE_ADMISSION_V2_CONTRACT_VERSION,
    evaluate_admission_v2,
    gate_g1_ic_mean,
    gate_g2_ic_stability,
    gate_g3_regime_consistency,
    gate_g4_concentration,
    gate_g5_vif,
    gate_g6_residual_ic,
    gate_g7_turnover,
    gate_g8_capacity_ic,
    gate_g9_crowding,
    gate_g10_out_of_universe,
    gate_g11_falsification,
    load_feature_admission_v2_contract,
    per_timestamp_rank_ic,
    sanitize_for_json,
)
from enhengclaw.quant_research.feature_quality import (  # noqa: E402
    build_feature_quality_frame,
    summarize_feature_quality,
)


DEFAULT_PANEL_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)
DEFAULT_REPORT_DATE = "2026-04-29"
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "factor_reports"

W11_CANDIDATES: tuple[tuple[str, str, str, str], ...] = (
    # (column, factor_id, mechanism_family, falsification_trigger)
    ("funding_basis_residual_20", "F09_funding_basis_residual", "MF-04",
     "rolling 60d residual IC < 0.02 for 90d → retire; OR rolling 60d corr(funding_rate, basis_proxy) < 0.10 for 60d → mechanism falsified"),
    ("funding_basis_residual_implied_repo_30", "F12_basis_funding_implied_repo", "MF-04",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("basis_velocity_3d_xs_z", "F11_perp_spot_basis_velocity", "MF-04",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("basis_carry_convexity_3d", "F13_basis_carry_convexity", "MF-04",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("qv_acceleration_residual_xs", "F16_qv_acceleration_residual", "MF-06",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("flow_persistence_against_price_20", "F18_flow_persistence_against_price", "MF-06",
     "rolling 60d residual IC < 0.02 for 90d → retire; OR coinglass_taker_imbalance source quality < 0.85 for 60d → suspend"),
    ("absorption_score_20", "F19_absorption_score", "MF-06",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("capitulation_amplification_event", "F20_capitulation_amplification", "MF-06",
     "sparse-event factor (event days only); rolling 90d residual IC on event subset < 0.02 → retire; evaluate quarterly"),
    ("realized_skew_20_xs_z", "F31_realized_skew_20", "MF-10",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("realized_kurt_20_xs_z", "F32_realized_kurt_20", "MF-10",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("downside_upside_vol_ratio_30", "F33_downside_upside_vol_ratio", "MF-10",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
    ("vol_of_vol_60", "F35_vol_of_vol", "MF-10",
     "rolling 60d residual IC < 0.02 for 90d → retire (slow-variable; evaluate every 30 days)"),
    ("abnormal_range_z_60", "F36_abnormal_range_z", "MF-10",
     "rolling 60d residual IC < 0.02 for 90d → retire"),
)

V91_BASELINE: tuple[tuple[str, str, str, str], ...] = (
    ("intraday_realized_vol_4h_to_1d_smooth_60", "v91_iv_smooth_60", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("realized_volatility_5", "v91_rv_5", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("distance_to_high_60", "v91_dh_60", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("distance_to_high_5", "v91_dh_5", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("coinglass_top_trader_long_pct_smooth_5", "v91_tt_long_smooth_5", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("liquidity_stress_qv_iv", "v91_liquidity_stress_qv_iv", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("momentum_decay_5_20", "v91_momentum_decay_5_20", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("coinglass_taker_imb_intraday_dispersion_24h", "v91_taker_imb_dispersion", "v91_baseline",
     "already in v91 baseline (sign-flipped at v91); retire if rolling 60d residual IC stays < 0.02 for 90d"),
    ("quality_funding_oi", "v91_quality_funding_oi", "v91_baseline",
     "already in v91 baseline; retire if rolling 60d residual IC stays < 0.02 for 90d"),
)

V91_BASELINE_COLUMNS = tuple(c for c, _, _, _ in V91_BASELINE)
PUBLIC_CROWDING_FACTORS = ("funding_zscore_20", "momentum_20", "realized_volatility_20")
PANEL_INPUT_COLUMNS = (
    "subject", "timestamp_ms", "liquidity_bucket", "usdm_symbol",
    "spot_open", "spot_high", "spot_low", "spot_close",
    "spot_volume", "spot_quote_volume", "rolling_median_quote_volume_usd_30d",
    "funding_rate", "basis_proxy", "open_interest", "open_interest_value",
    "intraday_realized_vol_4h_to_1d",
    "coinglass_top_trader_long_pct",
    "coinglass_taker_imbalance_5d_sum",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "coinglass_top_trader_intraday_volatility_24h",
    "coinglass_orderbook_imb_persistence_24h",
    "coinglass_liquidation_imbalance_24h",
    "coinglass_liq_intraday_concentration_24h",
    "coinglass_global_account_long_pct",
)


# Helper primitives (per_timestamp_rank_ic, orthogonalize, autocorr_per_subject,
# gate_g1_ic_mean ... gate_g11_falsification, sanitize_for_json) are imported from
# enhengclaw.quant_research.feature_admission_v2 above (W3.4 refactor).


def build_panel(panel_path: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_path, compression="gzip")
    keep = [c for c in PANEL_INPUT_COLUMNS if c in df.columns]
    return df[keep].copy()


def build_regime_by_ts(features: pd.DataFrame, anchor_subject: str) -> pd.Series:
    btc = features[features["subject"] == anchor_subject]
    if btc.empty or "realized_volatility_20" not in btc.columns:
        available = sorted(features["subject"].dropna().unique().tolist())
        raise RuntimeError(
            f"anchor_subject={anchor_subject!r} not found or has no realized_volatility_20; "
            f"available subjects: {available[:10]}{'...' if len(available) > 10 else ''}"
        )
    rv = btc.set_index("timestamp_ms")["realized_volatility_20"]
    rv = pd.to_numeric(rv, errors="coerce").replace(0.0, np.nan).dropna()
    if rv.empty:
        return pd.Series("unknown", index=features["timestamp_ms"].drop_duplicates())
    q_lo, q_hi = rv.quantile([1.0 / 3, 2.0 / 3]).tolist()

    def _tag(x: float) -> str:
        if pd.isna(x):
            return "unknown"
        if x < q_lo:
            return "low_vol"
        if x > q_hi:
            return "high_vol"
        return "mid_vol"

    return rv.apply(_tag)


def evaluate_factor(
    *,
    factor_id: str,
    column: str,
    kind: str,
    falsification: str,
    features: pd.DataFrame,
    target_col: str,
    baseline_df: pd.DataFrame,
    public_df: pd.DataFrame,
    capacity_score: pd.Series,
    regime_by_ts: pd.Series,
    feature_quality: dict | None = None,
    admission_contract: dict | None = None,
) -> dict:
    if column not in features.columns:
        return {
            "factor_id": factor_id,
            "column": column,
            "kind": kind,
            "error": "column_not_in_features",
        }
    factor = pd.to_numeric(features[column], errors="coerce")
    target = pd.to_numeric(features[target_col], errors="coerce")
    timestamps = features["timestamp_ms"]
    subjects = features["subject"]

    admission = evaluate_admission_v2(
        factor=factor,
        target=target,
        timestamps=timestamps,
        subjects=subjects,
        baseline_df=baseline_df,
        public_df=public_df,
        capacity_score=capacity_score,
        regime_by_ts=regime_by_ts,
        falsification=falsification,
        contract=admission_contract,
        self_exclusion_column=column,
    )
    valid_mask = ~factor.isna() & ~target.isna()
    return {
        "factor_id": factor_id,
        "column": column,
        "kind": kind,
        "n_observations": int(valid_mask.sum()),
        "n_unique_timestamps": int(timestamps[valid_mask].nunique()),
        "n_unique_subjects": int(subjects[valid_mask].nunique()),
        "feature_quality": dict(feature_quality or {}),
        "gates": admission["gates"],
        "gate_pass_count": admission["gate_pass_count"],
        "gate_total": admission["gate_total"],
        "all_passed": admission["all_passed"],
        "verdict": admission["verdict"],
        "g6_strict_pass": admission["g6_strict_pass"],
        "g3_strict_pass": admission["g3_strict_pass"],
    }


def render_text_card(
    result: dict,
    period_start: str,
    period_end: str,
    period_days: int,
    universe_label: str,
) -> str:
    if result.get("error"):
        return (
            f"factor_id: {result['factor_id']}  (column: {result['column']})\n"
            f"  ERROR: {result['error']}\n"
        )
    g = result["gates"]

    def fmt(v, p=3, sign=False) -> str:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "n/a"
        return f"{v:+.{p}f}" if sign else f"{v:.{p}f}"

    def pct(v, p=1) -> str:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "n/a"
        return f"{v * 100:.{p}f}%"

    g1 = g["G1_ic_mean"]
    g2 = g["G2_ic_stability"]
    g3 = g["G3_regime_consistency"]
    g4 = g["G4_concentration"]
    g5 = g["G5_vif"]
    g6 = g["G6_orthogonal_residual_ic"]
    g7 = g["G7_turnover"]
    g8 = g["G8_capacity_aware_ic"]
    g9 = g["G9_crowding"]
    g10 = g["G10_out_of_universe"]
    g11 = g["G11_falsification"]
    q = dict(result.get("feature_quality") or {})

    regime_str = "  ".join(
        f"{k}={fmt(v, 3, True)}" for k, v in (g3.get("regime_ic") or {}).items()
    )
    lines = [
        f"factor_id: {result['factor_id']}  (column: {result['column']}, kind: {result['kind']})",
        f"period: {period_start} → {period_end} ({period_days} days)",
        f"universe: {universe_label}",
        f"observations: {result['n_observations']}  timestamps: {result['n_unique_timestamps']}  subjects: {result['n_unique_subjects']}",
        f"source_rows: {pct(q.get('row_source_fraction'))}  ready_rows: {pct(q.get('row_ready_fraction'))}  source_subjects: {q.get('source_subject_count', 'n/a')}  ready_subjects: {q.get('ready_subject_count', 'n/a')}",
        "",
        f"[G1 IC]                mean={fmt(g1.get('value'), 3, True)}  std={fmt(g1.get('std'), 3)}  IR={fmt(g1.get('ir'), 3, True)}  pos_day_rate={pct(g1.get('pos_day_rate'))}  PASS={g1['passed']}",
        f"[G2 Stability]         rolling_60d_pos%={pct(g2.get('value'))}  max_drop={fmt(g2.get('max_drop'), 3, True)}  PASS={g2['passed']}",
        f"[G3 Regime IC]         {regime_str}  same_sign_frac={pct(g3.get('value'))}  PASS={g3['passed']}",
        f"[G4 Concentration]     top1_share={pct(g4.get('value'))}  top_subject={g4.get('top_subject', 'n/a')}  PASS={g4['passed']}",
        f"[G5 VIF vs baseline]   vif={fmt(g5.get('value'), 2)}  r2={fmt(g5.get('r2'), 3)}  PASS={g5['passed']}",
        f"[G6 Residual IC]       residual_ic={fmt(g6.get('value'), 3, True)}  PASS={g6['passed']}",
        f"[G7 Turnover]          turnover_30d={pct(g7.get('value'))}  mean_ac_lag30={fmt(g7.get('mean_autocorr_lag30'), 3, True)}  PASS={g7['passed']}",
        f"[G8 Capacity-aware IC] retention_ratio={pct(g8.get('value'))}  full_ic={fmt(g8.get('full_ic'), 3, True)}  cap_ic={fmt(g8.get('capacity_ic'), 3, True)}  PASS={g8['passed']}",
        f"[G9 Crowding]          residual_ic vs (funding_z, momentum_20, rv_20)={fmt(g9.get('value'), 3, True)}  PASS={g9['passed']}",
        f"[G10 Mid-cap subset]   ic={fmt(g10.get('value'), 3, True)}  PASS={g10['passed']}",
        f"[G11 Falsification]    {g11.get('value', 'MISSING')}  PASS={g11['passed']}",
        "",
        f"summary: {result['gate_pass_count']}/{result['gate_total']} gates PASS  all_passed={result['all_passed']}",
    ]
    return "\n".join(lines) + "\n"


# sanitize_for_json is imported from enhengclaw.quant_research.feature_admission_v2.


def main(argv=None):
    parser = argparse.ArgumentParser(description="11-gate factor report card per alpha_ontology §G.4")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_ARTIFACT))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--report-date", default=DEFAULT_REPORT_DATE)
    parser.add_argument("--target-shift-bars", type=int, default=5)
    parser.add_argument("--label-contract-id", default=EXECUTION_ALIGNED_LABEL_CONTRACT_ID)
    parser.add_argument("--anchor-subject", default="BTC")
    parser.add_argument("--universe-label", default="liquid_perp_core_20")
    args = parser.parse_args(argv)

    panel_path = Path(args.panel).resolve()
    out_dir = Path(args.out_root).resolve() / args.report_date
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[load] panel: {panel_path}")
    panel = build_panel(panel_path)
    print(f"[load] panel shape: {panel.shape}, subjects: {panel['subject'].nunique()}")

    print(
        "[features] rebuilding via build_cross_sectional_feature_bundle "
        f"(target_shift_bars={args.target_shift_bars}, label_contract_id={args.label_contract_id})"
    )
    bundle = build_cross_sectional_feature_bundle(
        panel,
        target_shift_bars=args.target_shift_bars,
        label_contract_id=args.label_contract_id,
    )
    features = bundle["dataframe"].sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)
    target_col = bundle["forward_return_column"]
    print(f"[features] features shape: {features.shape}, target_col={target_col}")

    timestamps = features["timestamp_ms"]
    period_start = pd.Timestamp(int(timestamps.min()), unit="ms", tz="UTC").strftime("%Y-%m-%d")
    period_end = pd.Timestamp(int(timestamps.max()), unit="ms", tz="UTC").strftime("%Y-%m-%d")
    period_days = int(timestamps.nunique())

    missing_baseline = [c for c in V91_BASELINE_COLUMNS if c not in features.columns]
    if missing_baseline:
        raise RuntimeError(f"v91 baseline columns missing from features: {missing_baseline}")
    baseline_df = features[list(V91_BASELINE_COLUMNS)].copy()

    missing_public = [c for c in PUBLIC_CROWDING_FACTORS if c not in features.columns]
    if missing_public:
        raise RuntimeError(f"public crowding factors missing from features: {missing_public}")
    public_df = features[list(PUBLIC_CROWDING_FACTORS)].copy()

    capacity_col = "rolling_median_quote_volume_usd_30d"
    if capacity_col in features.columns:
        capacity_score = pd.to_numeric(features[capacity_col], errors="coerce")
    else:
        capacity_score = pd.to_numeric(features.get("spot_quote_volume", pd.Series(0.0, index=features.index)), errors="coerce")
    if capacity_score.isna().all() or (capacity_score.fillna(0.0) == 0.0).all():
        capacity_score = pd.to_numeric(features.get("spot_quote_volume", pd.Series(0.0, index=features.index)), errors="coerce")

    print(f"[regime] BTC realised-vol tertile classifier (anchor={args.anchor_subject})")
    regime_by_ts = build_regime_by_ts(features, args.anchor_subject)

    print(f"[contract] loading {FEATURE_ADMISSION_V2_CONTRACT_VERSION}")
    admission_contract = load_feature_admission_v2_contract()

    rows = list(W11_CANDIDATES) + list(V91_BASELINE)
    feature_quality = summarize_feature_quality(
        feature_quality_frame=build_feature_quality_frame(
            feature_frame=features,
            tracked_feature_columns=[column for column, *_ in rows],
            derivatives_quality_frame=bundle["quality_frame"],
        ),
        tracked_feature_columns=[column for column, *_ in rows],
    )
    print(f"[score] evaluating {len(rows)} factors → {out_dir}")

    summary_records = []
    for column, factor_id, kind, falsification in rows:
        print(f"  - {factor_id} ({column})")
        result = evaluate_factor(
            factor_id=factor_id,
            column=column,
            kind=kind,
            falsification=falsification,
            features=features,
            target_col=target_col,
            baseline_df=baseline_df,
            public_df=public_df,
            capacity_score=capacity_score,
            regime_by_ts=regime_by_ts,
            feature_quality=dict(dict(feature_quality.get("features") or {}).get(column) or {}),
            admission_contract=admission_contract,
        )
        result["report_date"] = args.report_date
        result["period_start"] = period_start
        result["period_end"] = period_end
        result["period_days"] = period_days
        result["universe"] = args.universe_label
        result["target_horizon_bars"] = int(args.target_shift_bars)
        result["panel_artifact"] = str(panel_path)

        json_path = out_dir / f"{factor_id}.json"
        text_path = out_dir / f"{factor_id}.txt"
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(sanitize_for_json(result), fh, indent=2)
        with text_path.open("w", encoding="utf-8") as fh:
            fh.write(render_text_card(result, period_start, period_end, period_days, args.universe_label))

        if "error" not in result:
            g = result["gates"]
            summary_records.append(
                {
                    "factor_id": factor_id,
                    "column": column,
                    "kind": kind,
                    "n_observations": result["n_observations"],
                    "row_source_fraction": dict(result.get("feature_quality") or {}).get("row_source_fraction"),
                    "row_ready_fraction": dict(result.get("feature_quality") or {}).get("row_ready_fraction"),
                    "ic_mean": g["G1_ic_mean"].get("value"),
                    "ic_ir": g["G1_ic_mean"].get("ir"),
                    "rolling_pos_frac": g["G2_ic_stability"].get("value"),
                    "regime_same_sign": g["G3_regime_consistency"].get("value"),
                    "top1_share": g["G4_concentration"].get("value"),
                    "vif": g["G5_vif"].get("value"),
                    "residual_ic_baseline": g["G6_orthogonal_residual_ic"].get("value"),
                    "turnover_30d": g["G7_turnover"].get("value"),
                    "capacity_retention": g["G8_capacity_aware_ic"].get("value"),
                    "residual_ic_public": g["G9_crowding"].get("value"),
                    "midcap_ic": g["G10_out_of_universe"].get("value"),
                    "gate_pass_count": result["gate_pass_count"],
                    "all_passed": result["all_passed"],
                    "verdict": result.get("verdict"),
                    "g6_strict_pass": result.get("g6_strict_pass"),
                    "g3_strict_pass": result.get("g3_strict_pass"),
                }
            )

    summary_df = pd.DataFrame(summary_records)
    summary_csv = out_dir / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    summary_meta = {
        "report_date": args.report_date,
        "panel_artifact": str(panel_path),
        "feature_admission_v2_contract_version": FEATURE_ADMISSION_V2_CONTRACT_VERSION,
        "features_rows": int(features.shape[0]),
        "period_start": period_start,
        "period_end": period_end,
        "period_days": period_days,
        "universe_label": args.universe_label,
        "target_horizon_bars": int(args.target_shift_bars),
        "anchor_subject": args.anchor_subject,
        "baseline_columns": list(V91_BASELINE_COLUMNS),
        "public_crowding_factors": list(PUBLIC_CROWDING_FACTORS),
        "n_factors_evaluated": int(len(rows)),
        "n_factors_pass_all_gates": int(summary_df["all_passed"].sum()) if not summary_df.empty else 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(sanitize_for_json(summary_meta), fh, indent=2)

    print(f"[done] wrote {len(rows)} cards to {out_dir}")
    print(f"[done] summary csv: {summary_csv}")


if __name__ == "__main__":
    main()
