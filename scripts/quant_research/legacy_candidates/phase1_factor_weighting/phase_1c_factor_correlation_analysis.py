"""Phase 1c factor de-correlation analysis.

Loads the v90 feature panel, computes per-timestamp z-scores of the 17
candidate factors, then reports:
  - pairwise correlation matrix (averaged across timestamps)
  - per-factor train-segment rank IC vs target_forward_return
  - PCA: cumulative variance explained, leading eigenvectors
  - VIF (variance inflation factor) per factor
  - Suggested reduction: factors to drop / PCs to retain for v91 score
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _ts_zscore(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    g = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    mu = g.groupby("t")["v"].transform("mean")
    sd = g.groupby("t")["v"].transform("std").replace(0, np.nan)
    return ((g["v"] - mu) / sd).fillna(0.0)


DEFAULT_FACTORS = [
    # v91-evaluated (Phase 1c run 2026-04-26)
    "realized_volatility_5", "realized_volatility_20", "realized_volatility_60",
    "intraday_realized_vol_4h_to_1d_smooth_5", "intraday_realized_vol_4h_to_1d_smooth_20", "intraday_realized_vol_4h_to_1d_smooth_60",
    "distance_to_high_5", "distance_to_high_20", "distance_to_high_60",
    "coinglass_top_trader_long_pct_smooth_5", "coinglass_top_trader_long_pct_smooth_20", "coinglass_top_trader_long_pct_smooth_60",
    "momentum_decay_5_20",
    "quality_funding_oi",
    "liquidity_stress_qv_iv",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "funding_crowding_basis",
    # B-batch alternative candidates (added 2026-04-28; first appearance in v92 panel)
    "stress_liq_conc_iv",
    "crowd_obi_abs_funding",
    "crowd_tt_signal",
    "disp_taker_imb_xs",
    "unwind_liq_dh",
    "crowd_basis_oi_signed",
    "crowd_abs_basis_oi",
    "stress_abs_basis_qv",
    "crowd_funding_obi_signed",
    "disagree_tt_retail",
    "unwind_liq_imb_xs",
]

DEFAULT_PANEL = (
    ROOT / "artifacts" / "quant_research" / "features"
    / "2026-04-26-cross-sectional-daily-1d-h5d-features-v90" / "features.csv.gz"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 1c factor de-correlation analysis.")
    parser.add_argument(
        "--panel", default=None,
        help=f"Path to features.csv.gz panel (default: {DEFAULT_PANEL.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--factors", default=None,
        help="Comma-separated factor column names (default: built-in 28-item DEFAULT_FACTORS).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON path (default: shadow_oos/phase_1c_factor_analysis_<panel_dir>.json).",
    )
    return parser.parse_args()


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    panel_path = Path(args.panel) if args.panel else DEFAULT_PANEL
    factors = (
        [c.strip() for c in args.factors.split(",") if c.strip()]
        if args.factors else list(DEFAULT_FACTORS)
    )

    print(f"=== Loading panel: {panel_path}")
    print(f"=== Factor universe size: {len(factors)}")

    panel = pd.read_csv(panel_path)
    panel["timestamp_ms"] = panel["timestamp_ms"].astype("int64")
    panel["date_utc"] = pd.to_datetime(panel["timestamp_ms"], unit="ms", utc=True)

    panel = panel.dropna(subset=["target_forward_return", "subject"]).copy()
    panel = panel[panel["selection_rank"] <= 20].copy()
    panel = panel[panel["liquidity_bucket"].isin(["top_liquidity", "mid_liquidity"])].copy()

    print(f"=== Panel after liquid_perp_core_20 filter: {len(panel)} rows, {panel['subject'].nunique()} subjects, {panel['date_utc'].min()} -> {panel['date_utc'].max()}")

    available = [c for c in factors if c in panel.columns]
    missing = [c for c in factors if c not in panel.columns]
    if missing:
        print(f"Missing factor columns (will skip): {missing}")
    print(f"Factors available: {len(available)}")

    z_panel = panel[["timestamp_ms", "subject", "target_forward_return"]].copy()
    for col in available:
        series = pd.to_numeric(panel[col], errors="coerce")
        if series.notna().any():
            fill = series.median()
            z_panel[col] = _ts_zscore(series.fillna(fill), panel["timestamp_ms"])
        else:
            z_panel[col] = 0.0

    print("\n=== Per-factor full-panel rank IC (Spearman) vs 5d forward return ===")
    ic_records = []
    for col in available:
        daily_ics = []
        for ts, group in z_panel.groupby("timestamp_ms"):
            scores = group[col]
            rets = group["target_forward_return"]
            valid = scores.notna() & rets.notna()
            if valid.sum() < 3 or scores[valid].std() == 0 or rets[valid].std() == 0:
                continue
            rho, _ = spearmanr(scores[valid], rets[valid])
            if not np.isnan(rho):
                daily_ics.append(rho)
        if daily_ics:
            ic_records.append({
                "factor": col,
                "ic_mean": float(np.mean(daily_ics)),
                "ic_std": float(np.std(daily_ics)),
                "ic_t_stat": float(np.mean(daily_ics) / (np.std(daily_ics) / np.sqrt(len(daily_ics)))) if np.std(daily_ics) > 0 else 0.0,
                "n_days": len(daily_ics),
                "ic_positive_rate": float(np.mean([1 if d > 0 else 0 for d in daily_ics])),
            })
    ic_df = pd.DataFrame(ic_records).sort_values("ic_mean", key=abs, ascending=False)
    print(ic_df.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print("\n=== Pairwise correlation of z-score factors (full panel) ===")
    factor_matrix = z_panel[available].fillna(0.0)
    corr_matrix = factor_matrix.corr()

    high_corr_pairs = []
    for i, f1 in enumerate(available):
        for j, f2 in enumerate(available):
            if i >= j:
                continue
            r = corr_matrix.loc[f1, f2]
            if abs(r) > 0.70:
                high_corr_pairs.append((f1, f2, float(r)))
    high_corr_pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    print(f"Pairs with |corr| > 0.70 (sorted by |corr|, n={len(high_corr_pairs)}):")
    for f1, f2, r in high_corr_pairs[:30]:
        print(f"  {r:+.3f}  {f1:50s} <-> {f2}")

    print("\n=== PCA on z-score factor matrix ===")
    centered = factor_matrix - factor_matrix.mean(axis=0)
    cov_matrix = centered.cov()
    eigvals, eigvecs = np.linalg.eigh(cov_matrix.values)
    eigvals = eigvals[::-1]
    eigvecs = eigvecs[:, ::-1]
    explained = eigvals / eigvals.sum()
    cum_explained = np.cumsum(explained)
    print(f"Eigenvalues (top 10) and cumulative variance explained:")
    for i in range(min(10, len(eigvals))):
        print(f"  PC{i+1:02d}  eigval={eigvals[i]:8.4f}  explained={explained[i]:6.2%}  cumulative={cum_explained[i]:6.2%}")
    n_pc_for_80 = int(np.searchsorted(cum_explained, 0.80) + 1)
    n_pc_for_90 = int(np.searchsorted(cum_explained, 0.90) + 1)
    print(f"\nPCs needed for 80% cumulative variance: {n_pc_for_80}")
    print(f"PCs needed for 90% cumulative variance: {n_pc_for_90}")

    print(f"\n=== Top {min(5, n_pc_for_80)} PC compositions (factor loadings) ===")
    for i in range(min(5, n_pc_for_80)):
        loadings = pd.Series(eigvecs[:, i], index=available)
        sorted_loadings = loadings.reindex(loadings.abs().sort_values(ascending=False).index)
        print(f"PC{i+1:02d}  (explains {explained[i]:.2%}):")
        for factor, load in sorted_loadings.head(6).items():
            print(f"    {load:+.3f}  {factor}")

    print(f"\n=== VIF (variance inflation factor) per factor ===")
    vif_records = []
    for i, col in enumerate(available):
        y = factor_matrix[col].values
        X = factor_matrix.drop(columns=[col]).values
        if X.shape[1] == 0 or len(y) < 10:
            vif = float("nan")
        else:
            try:
                beta, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
                y_hat = X @ beta
                ss_res = np.sum((y - y_hat) ** 2)
                ss_tot = np.sum((y - y.mean()) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                vif = 1 / (1 - r2) if r2 < 0.999 else float("inf")
            except np.linalg.LinAlgError:
                vif = float("nan")
        vif_records.append({"factor": col, "vif": vif})
    vif_df = pd.DataFrame(vif_records).sort_values("vif", ascending=False)
    print(vif_df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print("\n=== Suggested factor reduction (heuristic) ===")
    high_vif = vif_df[vif_df["vif"] > 5.0]["factor"].tolist()
    print(f"Factors with VIF > 5 (highly redundant, candidates to drop): {len(high_vif)}")
    for f in high_vif:
        print(f"  {f}")

    output = {
        "panel_rows": int(len(panel)),
        "subject_count": int(panel["subject"].nunique()),
        "factors_evaluated": available,
        "missing_factors": missing,
        "ic_table": ic_df.to_dict(orient="records"),
        "high_correlation_pairs": [{"factor_a": a, "factor_b": b, "correlation": r} for a, b, r in high_corr_pairs],
        "pca_explained_variance": [float(x) for x in explained],
        "pca_cumulative_variance": [float(x) for x in cum_explained],
        "pcs_for_80_pct": int(n_pc_for_80),
        "pcs_for_90_pct": int(n_pc_for_90),
        "pc_loadings": [
            {"pc": f"PC{i+1:02d}", "explained_variance": float(explained[i]), "loadings": {f: float(eigvecs[idx, i]) for idx, f in enumerate(available)}}
            for i in range(min(5, n_pc_for_80))
        ],
        "vif_table": vif_df.to_dict(orient="records"),
        "high_vif_factors": high_vif,
    }
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = ROOT / "artifacts" / "quant_research" / "shadow_oos" / f"phase_1c_factor_analysis_{panel_path.parent.name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
        f.write("\n")
    print(f"\n=== Output written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
