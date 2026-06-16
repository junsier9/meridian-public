"""compute_multi_horizon_factor_audit.py — SP-C: multi-horizon factor re-test.

Per `data_utilization_roadmap.md` SP-C + alpha ontology doc §I challenge #3
("5d horizon is given as universal — but factors may peak at 1d/3d/10d").

For each candidate factor (mostly idle factors that failed G6 at 5d, plus
score-integrated factors for confirmation), compute cross-sectional rank IC
+ residual IC vs the selected baseline at 4 horizons:
  h1d: forward 1-day log return
  h3d: forward 3-day log return
  h5d: forward 5-day log return (= existing target_forward_return, confirmation)
  h10d: forward 10-day log return

Identify horizon-specific G6 winners (residual IC ≥ 0.02 at the horizon
where the factor's signal is strongest).

Output: artifacts/quant_research/factor_reports/<as-of>/multi_horizon_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
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
    orthogonalize,
    per_timestamp_rank_ic,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_multi_horizon_factor_audit.v1"
G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02

LSK3_BASELINE = (
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
)

LIVE_HV_BALANCED_BASELINE = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "downside_upside_vol_ratio_30",
)

RESEARCH_V5_RW_BRIDGE_NO_OVERLAY_H10D_BASELINE = (
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
    "settlement_cycle_premium_60d",
)

BASELINE_PRESETS: dict[str, tuple[str, ...]] = {
    "lsk3": LSK3_BASELINE,
    "live_hv_balanced": LIVE_HV_BALANCED_BASELINE,
    "research_v5_rw_bridge_no_overlay_h10d": RESEARCH_V5_RW_BRIDGE_NO_OVERLAY_H10D_BASELINE,
}

# 28 candidate factors organized by family
CANDIDATES: dict[str, str] = {
    # === lsk3 / score-integrated (confirmation tier) ===
    "funding_basis_residual_implied_repo_30": "F12 (lsk3)",
    "downside_upside_vol_ratio_30": "F33 (lsk3)",
    "settlement_cycle_premium_60d": "F62 (M2.3, in v5)",
    "liq_cascade_recency_score_5d": "F-cascade (SP-A, in v6)",
    "contagion_in_degree": "F29 (in v_alpha_v2)",
    # === W1.1 leftovers (G6-failed at 5d) ===
    "funding_basis_residual_20": "F09 raw (W1.1)",
    "basis_velocity_3d_xs_z": "F11 (W1.1)",
    "basis_carry_convexity_3d": "F13 (W1.1)",
    "qv_acceleration_residual_xs": "F16 (W1.1)",
    "flow_persistence_against_price_20": "F18 (W1.1)",
    "absorption_score_20": "F19 (W1.1)",
    "capitulation_amplification_event": "F20 (W1.1)",
    "realized_skew_20_xs_z": "F31 (W1.1)",
    "realized_kurt_20_xs_z": "F32 (W1.1)",
    "vol_of_vol_60": "F35 (W1.1)",
    "abnormal_range_z_60": "F36 (W1.1)",
    # === W3.1 state-machine idle ===
    "vol_shock_impulse_phase": "F46 (W3.1)",
    "funding_flip_decay_phase": "F47 (W3.1)",
    "oi_shock_decay_phase": "F48 (W3.1)",
    # === W3.2 contagion idle ===
    "lead_lag_beta_btc": "F27 (W3.2)",
    "lead_lag_residual_strength": "F28 (W3.2)",
    # === W3.3 rotation idle ===
    "quote_share_change_30d": "F41 (W3.3)",
    "universe_rank_velocity_10": "F42 (W3.3)",
    "idiosyncratic_share": "F45 (W3.3)",
    # === M2 leftovers (G6-failed) ===
    "triangle_residual_60d": "M2.4 triangle",
    "funding_term_kurt_60": "M2.2 funding_kurt",
    # === SP-B sibling ===
    "top_trader_velocity_1h_abs_24h": "B3a (SP-B)",
}


def _parse_columns(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(col.strip() for col in raw.split(",") if col.strip())


def _build_candidate_map(
    *,
    baseline_cols: tuple[str, ...],
    candidate_preset: str,
    custom_cols: tuple[str, ...],
) -> dict[str, str]:
    candidates: dict[str, str] = {}
    if candidate_preset in {"baseline", "baseline_plus_spc"}:
        for col in baseline_cols:
            label = "baseline feature"
            if col in CANDIDATES:
                label = f"{label}; {CANDIDATES[col]}"
            candidates[col] = label
    if candidate_preset in {"spc", "baseline_plus_spc"}:
        for col, label in CANDIDATES.items():
            candidates.setdefault(col, label)
    for col in custom_cols:
        candidates[col] = "custom"
    return candidates


def _build_forward_returns(features: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    """For each horizon H, compute fwd_log_ret_<H>d per subject by shifting.

    Returns features with new columns `fwd_log_ret_{H}d` for each H.
    Forward log return at row t for asset s: sum of return_1 over t+1 .. t+H.
    """
    out = features.copy()
    if "return_1" not in out.columns:
        return out
    out = out.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    for h in horizons:
        # Sum of next H bars of return_1, per subject.
        # forward sum: shift(-1) is "next bar", rolling sum of H bars
        out[f"fwd_log_ret_{h}d"] = (
            out.groupby("subject", sort=False)["return_1"]
            .transform(lambda s: s.shift(-1).rolling(h).sum().shift(-(h - 1)))
        )
    return out


def _audit_factor_at_horizon(
    features: pd.DataFrame,
    factor_col: str,
    target_col: str,
    baseline_df: pd.DataFrame,
    regime_label: pd.Series,
) -> dict:
    factor = pd.to_numeric(features[factor_col], errors="coerce").fillna(0.0)
    target = pd.to_numeric(features[target_col], errors="coerce")
    ts = features["timestamp_ms"]
    ic = per_timestamp_rank_ic(factor, target, ts).dropna()
    n = int(len(ic))
    if n < 30:
        return {"status": "insufficient", "n_ts": n}
    mean = float(ic.mean())
    std = float(ic.std())
    t = float(mean * (n ** 0.5) / std) if std > 0 else 0.0
    aligned = regime_label.reindex(ic.index)
    df_g3 = pd.DataFrame({"ic": ic, "regime": aligned}).dropna()
    rs_per_regime = {
        str(r): float(g["ic"].mean()) for r, g in df_g3.groupby("regime") if len(g) >= 30
    }
    signs = [1 if v > 0 else -1 if v < 0 else 0 for v in rs_per_regime.values()]
    same_sign = max(signs.count(1), signs.count(-1)) / len(signs) if signs else 0.0
    residual_baseline = baseline_df.drop(columns=[factor_col], errors="ignore")
    residual = orthogonalize(factor, residual_baseline)
    rs_ic = per_timestamp_rank_ic(residual, target, ts).dropna()
    rm = float(rs_ic.mean()) if len(rs_ic) > 0 else 0.0
    rstd = float(rs_ic.std()) if len(rs_ic) > 1 else 0.0
    rt = float(rm * (len(rs_ic) ** 0.5) / rstd) if rstd > 0 else 0.0
    return {
        "n_ts": n,
        "raw_ic": mean,
        "raw_t": t,
        "g3_same_sign": same_sign,
        "residual_ic_vs_baseline": rm,
        "residual_ic_vs_lsk3": rm,
        "residual_t": rt,
        "g1_pass": abs(mean) >= G1_ABS_MIN,
        "g3_pass": same_sign >= G3_SAME_SIGN_MIN,
        "g6_pass": abs(rm) >= G6_ABS_MIN,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SP-C multi-horizon factor audit.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--features",
        type=Path,
        default=DEFAULT_FEATURES_ARTIFACT,
        help="Feature artifact to rebuild from (default: current committed daily v1 panel).",
    )
    parser.add_argument(
        "--horizons",
        default="1,3,5,10",
        help="Comma-separated forward-return horizons in days (default: 1,3,5,10).",
    )
    parser.add_argument(
        "--baseline-preset",
        choices=sorted(BASELINE_PRESETS),
        default="lsk3",
        help=(
            "Baseline feature set used for residual IC. "
            "Use live_hv_balanced for the current remote live baseline and "
            "research_v5_rw_bridge_no_overlay_h10d for the follow-on research baseline."
        ),
    )
    parser.add_argument(
        "--baseline-columns",
        default="",
        help="Comma-separated baseline columns; overrides --baseline-preset when supplied.",
    )
    parser.add_argument(
        "--baseline-label",
        default="",
        help="Human-readable baseline label written into the artifact.",
    )
    parser.add_argument(
        "--candidate-preset",
        choices=("baseline", "spc", "baseline_plus_spc"),
        default="baseline_plus_spc",
        help="Candidate universe to audit.",
    )
    parser.add_argument(
        "--candidate-columns",
        default="",
        help="Comma-separated extra candidate columns to audit.",
    )
    parser.add_argument(
        "--run-label",
        default="",
        help="Optional subdirectory under <output-dir>/<as-of> to avoid overwriting runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args()

    horizons = tuple(int(h) for h in args.horizons.split(",") if h.strip())
    baseline_cols = _parse_columns(args.baseline_columns) or BASELINE_PRESETS[args.baseline_preset]
    baseline_label = args.baseline_label.strip() or args.baseline_preset
    candidate_cols = _parse_columns(args.candidate_columns)
    candidates = _build_candidate_map(
        baseline_cols=baseline_cols,
        candidate_preset=args.candidate_preset,
        custom_cols=candidate_cols,
    )
    print(f"=== SP-C multi-horizon audit: horizons {horizons}d ===")
    print(f"=== Baseline: {baseline_label} ({len(baseline_cols)} columns) ===")
    print(f"=== Loading panel + rebuilding features ===")
    panel = _load_panel(args.features)
    features = _rebuild_features_with_w3_columns(panel)
    features = _build_forward_returns(features, horizons)
    available_baseline_cols = tuple(col for col in baseline_cols if col in features.columns)
    missing_baseline_cols = tuple(col for col in baseline_cols if col not in features.columns)
    if not available_baseline_cols:
        raise RuntimeError(
            "none of the requested baseline columns were found after feature rebuild: "
            + ", ".join(baseline_cols)
        )
    if missing_baseline_cols:
        print(
            "=== WARNING: missing baseline columns: "
            + ", ".join(missing_baseline_cols)
            + " ==="
        )
    baseline = features[list(available_baseline_cols)].apply(pd.to_numeric, errors="coerce")
    regime_label = build_regime_by_ts(features)

    results: dict[str, dict] = {}
    for col, label in candidates.items():
        if col not in features.columns:
            results[col] = {"label": label, "status": "missing_from_panel"}
            continue
        per_horizon: dict[str, dict] = {}
        for h in horizons:
            target_col = f"fwd_log_ret_{h}d"
            if target_col not in features.columns:
                continue
            per_horizon[f"h{h}d"] = _audit_factor_at_horizon(
                features, col, target_col, baseline, regime_label
            )
        results[col] = {"label": label, "horizons": per_horizon}

    # Output JSON
    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "horizons_days": list(horizons),
        "features_artifact": str(args.features),
        "baseline_label": baseline_label,
        "baseline_preset": args.baseline_preset,
        "baseline_columns_requested": list(baseline_cols),
        "baseline_columns_available": list(available_baseline_cols),
        "baseline_columns_missing": list(missing_baseline_cols),
        "candidate_preset": args.candidate_preset,
        "candidate_columns": list(candidates),
        "thresholds": {
            "g1_abs_min": G1_ABS_MIN,
            "g3_same_sign_min": G3_SAME_SIGN_MIN,
            "g6_abs_min": G6_ABS_MIN,
        },
        "factors": results,
    }
    out_dir = args.output_dir / args.as_of
    if args.run_label.strip():
        out_dir = out_dir / args.run_label.strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "multi_horizon_audit.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote {out_path}")

    # Console summary table
    print()
    print("=" * 120)
    print(f'{"factor":<48s} {"label":<25s} ' + " ".join(f'h{h}d_resid_t' for h in horizons))
    print("=" * 120)
    for col, info in results.items():
        if "status" in info:
            print(f"  {col:<48s} {info.get('label', ''):<25s} {info['status']}")
            continue
        per_horizon = info["horizons"]
        cells = []
        best_h = None
        best_t = 0.0
        for h in horizons:
            cell = per_horizon.get(f"h{h}d", {})
            rt = cell.get("residual_t", 0.0) if isinstance(cell, dict) else 0.0
            cells.append(f"{rt:+7.2f}" if rt != 0 else "  N/A  ")
            if abs(rt) > abs(best_t):
                best_t = rt
                best_h = h
        flag = ""
        if best_h is not None and best_h != 5:
            best_cell = per_horizon[f"h{best_h}d"]
            if best_cell.get("g6_pass") and best_cell.get("g3_pass"):
                flag = f" [best at h{best_h}d, G6 PASS]"
            elif best_cell.get("g6_pass"):
                flag = f" [best at h{best_h}d, G6 only]"
        print(f"  {col:<48s} {info['label']:<25s} {' '.join(cells)}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
