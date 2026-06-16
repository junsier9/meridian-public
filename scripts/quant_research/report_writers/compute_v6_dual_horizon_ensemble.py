"""compute_v6_dual_horizon_ensemble.py — v_alpha_v6 dual-horizon
ensemble portfolio analysis.

Two production candidates exist:
  - v_alpha_v6_lsk3_g_v2 (h5d, active_alternative): walk-forward median +2.373
  - v_alpha_v6_lsk3_g_v2_h10d (h10d, active_alternative): walk-forward median +2.832

Both ship as `active_alternative`. Owner-side question: does an ensemble
portfolio (50/50 capital split between the two) materially outperform
either standalone? If yes, ship as new active_alternative ensemble. If
no (cycle metrics dominated by v6_h10d), defer.

Methodology:
  Step 1: Load per-window OOS net_return + sharpe arrays from both cycles
          (32 windows each, ~30-day OOS window-by-window).
  Step 2: Calendar-align windows (h5d windows start ~5d before h10d
          windows; align by sequence index).
  Step 3: Compute per-window correlation:
            corr(h5d_returns, h10d_returns) — diversification potential
  Step 4: Construct ensemble portfolio:
            ensemble_return[i] = 0.5 × h5d_return[i] + 0.5 × h10d_return[i]
            ensemble_sharpe = (mean / std) × sqrt(252 / window_days)
  Step 5: Per-regime decomposition:
            for each regime calendar window, compute h5d / h10d / ensemble
            window-level metrics.
  Step 6: Decision: promote if ensemble sharpe > max(individual) by
          material margin AND regime metrics preserved; else defer.

Output:
  artifacts/quant_research/factor_reports/<as-of>/v6_dual_horizon_ensemble.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, date
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]


CARD_CONTRACT_VERSION = "quant_v6_dual_horizon_ensemble.v1"

DEFAULT_AS_OF = "2026-04-29"
DEFAULT_H5D_REPORT = (
    ROOT / "artifacts" / "quant_research" / "experiments"
    / f"{DEFAULT_AS_OF}-xs_alpha_ontology_v6_lsk3_g_v2_h5d" / "validation_report.json"
)
DEFAULT_H10D_REPORT = (
    ROOT / "artifacts" / "quant_research" / "experiments"
    / f"{DEFAULT_AS_OF}-xs_alpha_ontology_v6_lsk3_g_v2_h10d" / "validation_report.json"
)

REGIME_WINDOWS = {
    "trend_up_2025h2": (date(2025, 8, 1), date(2025, 10, 31)),
    "rotation_high_vol_2025q4": (date(2025, 11, 1), date(2026, 1, 31)),
    "drawdown_rebound_2026ytd": (date(2026, 2, 1), date(2026, 4, 30)),
}


def _load_windows(report_path: Path) -> list[dict]:
    """Load walk_forward.windows from validation_report.json. Each window
    has test_start_utc, test_end_utc, net_return, sharpe (frictional)."""
    vr = json.loads(report_path.read_text(encoding="utf-8"))
    return list(vr["walk_forward"]["windows"])


def _parse_iso_date(s: str) -> date:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


def step1_load_and_summarize(h5d_path: Path, h10d_path: Path) -> dict:
    """Load per-window arrays from both cycles."""
    h5d_windows = _load_windows(h5d_path)
    h10d_windows = _load_windows(h10d_path)
    n_h5d, n_h10d = len(h5d_windows), len(h10d_windows)
    print(f"  v6_h5d:  {n_h5d} windows")
    print(f"  v6_h10d: {n_h10d} windows")
    if n_h5d != n_h10d:
        print(f"  WARNING: window counts differ ({n_h5d} vs {n_h10d}); will align by min")

    n_align = min(n_h5d, n_h10d)
    # Align by index — both cycles start at same "first OOS month" with 5d offset
    aligned = []
    for i in range(n_align):
        w5 = h5d_windows[i]
        w10 = h10d_windows[i]
        aligned.append({
            "window_index": i,
            "h5d_test_start": w5["test_start_utc"],
            "h5d_test_end": w5["test_end_utc"],
            "h10d_test_start": w10["test_start_utc"],
            "h10d_test_end": w10["test_end_utc"],
            "h5d_net_return": float(w5["net_return"]),
            "h10d_net_return": float(w10["net_return"]),
            "h5d_sharpe": float(w5["sharpe"]),
            "h10d_sharpe": float(w10["sharpe"]),
            "h5d_max_drawdown": float(w5["max_drawdown"]),
            "h10d_max_drawdown": float(w10["max_drawdown"]),
            "h5d_turnover": float(w5["turnover"]),
            "h10d_turnover": float(w10["turnover"]),
        })
    return {
        "n_aligned_windows": n_align,
        "aligned_windows": aligned,
    }


def step2_per_window_correlation(aligned: list[dict]) -> dict:
    """Per-window correlation between h5d and h10d returns / sharpes."""
    h5d_rets = np.array([w["h5d_net_return"] for w in aligned])
    h10d_rets = np.array([w["h10d_net_return"] for w in aligned])
    h5d_sharpes = np.array([w["h5d_sharpe"] for w in aligned])
    h10d_sharpes = np.array([w["h10d_sharpe"] for w in aligned])

    pearson_returns = float(np.corrcoef(h5d_rets, h10d_rets)[0, 1])
    pearson_sharpes = float(np.corrcoef(h5d_sharpes, h10d_sharpes)[0, 1])
    spearman_returns = float(pd.Series(h5d_rets).corr(pd.Series(h10d_rets), method="spearman"))
    spearman_sharpes = float(pd.Series(h5d_sharpes).corr(pd.Series(h10d_sharpes), method="spearman"))

    # Win/loss alignment
    h5d_wins = h5d_rets > 0
    h10d_wins = h10d_rets > 0
    same_sign = (h5d_wins == h10d_wins).mean()
    both_positive = (h5d_wins & h10d_wins).mean()
    both_negative = ((~h5d_wins) & (~h10d_wins)).mean()
    h5d_only_positive = (h5d_wins & ~h10d_wins).mean()
    h10d_only_positive = (~h5d_wins & h10d_wins).mean()

    return {
        "pearson_corr_net_returns": pearson_returns,
        "pearson_corr_sharpes": pearson_sharpes,
        "spearman_corr_net_returns": spearman_returns,
        "spearman_corr_sharpes": spearman_sharpes,
        "same_sign_fraction": float(same_sign),
        "both_positive_fraction": float(both_positive),
        "both_negative_fraction": float(both_negative),
        "h5d_only_positive_fraction": float(h5d_only_positive),
        "h10d_only_positive_fraction": float(h10d_only_positive),
        "diversification_score_from_correlation": (
            "high (low corr → big diversification)"
            if pearson_returns < 0.5
            else "moderate"
            if pearson_returns < 0.8
            else "low (high corr → minimal diversification)"
        ),
    }


def _sharpe_from_returns(returns: np.ndarray, periods_per_year: float) -> float:
    """Compute sharpe from per-window returns. periods_per_year ~12 for
    monthly windows (32 windows over ~32 months).
    """
    if len(returns) < 2:
        return float("nan")
    m = float(np.mean(returns))
    s = float(np.std(returns, ddof=1))
    if s <= 0:
        return float("nan")
    return float(m / s * np.sqrt(periods_per_year))


def _median_sharpe_per_window(window_sharpes: np.ndarray) -> float:
    """Median of per-window sharpes (matches the validation contract metric)."""
    arr = np.asarray(window_sharpes, dtype="float64")
    return float(np.median(arr[~np.isnan(arr)])) if len(arr) > 0 else float("nan")


def step3_construct_ensemble(aligned: list[dict]) -> dict:
    """50/50 capital split ensemble portfolio."""
    h5d_rets = np.array([w["h5d_net_return"] for w in aligned])
    h10d_rets = np.array([w["h10d_net_return"] for w in aligned])
    h5d_sharpes = np.array([w["h5d_sharpe"] for w in aligned])
    h10d_sharpes = np.array([w["h10d_sharpe"] for w in aligned])

    ensemble_rets = 0.5 * h5d_rets + 0.5 * h10d_rets
    # Per-window ensemble sharpe — assuming 50/50 capital + average frictionless sharpe
    # is a reasonable proxy for "blended portfolio" within the same window.
    # NOTE: true sharpe of the ensemble portfolio would require per-day return
    # series; we approximate using mean of per-window sharpes (acceptable for
    # the validation contract's median_oos_sharpe metric).
    ensemble_sharpes = 0.5 * h5d_sharpes + 0.5 * h10d_sharpes

    # Median-of-window-sharpes (matches validation contract)
    h5d_median_sharpe = _median_sharpe_per_window(h5d_sharpes)
    h10d_median_sharpe = _median_sharpe_per_window(h10d_sharpes)
    ensemble_median_sharpe = _median_sharpe_per_window(ensemble_sharpes)

    # Loss window fraction
    h5d_loss_fraction = float(np.mean(h5d_rets < 0))
    h10d_loss_fraction = float(np.mean(h10d_rets < 0))
    ensemble_loss_fraction = float(np.mean(ensemble_rets < 0))

    # Annualized sharpe from windows (proxy)
    # 32 windows over ~32 months → ~12 windows/year
    PERIODS_PER_YEAR = 12.0
    h5d_total_sharpe = _sharpe_from_returns(h5d_rets, PERIODS_PER_YEAR)
    h10d_total_sharpe = _sharpe_from_returns(h10d_rets, PERIODS_PER_YEAR)
    ensemble_total_sharpe = _sharpe_from_returns(ensemble_rets, PERIODS_PER_YEAR)

    # Cumulative compound return
    h5d_cum = float(np.prod(1 + h5d_rets) - 1)
    h10d_cum = float(np.prod(1 + h10d_rets) - 1)
    ensemble_cum = float(np.prod(1 + ensemble_rets) - 1)

    # Max drawdown (per-window, averaged)
    h5d_avg_mdd = float(np.mean([w["h5d_max_drawdown"] for w in aligned]))
    h10d_avg_mdd = float(np.mean([w["h10d_max_drawdown"] for w in aligned]))
    # Ensemble MDD is harder to compute exactly without per-day series; use
    # arithmetic mean as proxy (will be conservative — true MDD typically lower)
    ensemble_avg_mdd = 0.5 * h5d_avg_mdd + 0.5 * h10d_avg_mdd

    return {
        "median_window_sharpe": {
            "v6_h5d": h5d_median_sharpe,
            "v6_h10d": h10d_median_sharpe,
            "ensemble_50_50": ensemble_median_sharpe,
            "delta_ensemble_vs_max_individual": ensemble_median_sharpe - max(
                h5d_median_sharpe, h10d_median_sharpe
            ),
        },
        "loss_window_fraction": {
            "v6_h5d": h5d_loss_fraction,
            "v6_h10d": h10d_loss_fraction,
            "ensemble_50_50": ensemble_loss_fraction,
            "delta_ensemble_vs_min_individual": ensemble_loss_fraction - min(
                h5d_loss_fraction, h10d_loss_fraction
            ),
        },
        "annualized_sharpe_from_returns": {
            "v6_h5d": h5d_total_sharpe,
            "v6_h10d": h10d_total_sharpe,
            "ensemble_50_50": ensemble_total_sharpe,
            "delta_ensemble_vs_max_individual": ensemble_total_sharpe - max(
                h5d_total_sharpe, h10d_total_sharpe
            ),
            "method_note": "Sharpe from monthly window net_returns × sqrt(12). Approximation; true daily-bar sharpe likely ~25-50% higher.",
        },
        "cumulative_compound_return": {
            "v6_h5d": h5d_cum,
            "v6_h10d": h10d_cum,
            "ensemble_50_50": ensemble_cum,
        },
        "average_max_drawdown_per_window": {
            "v6_h5d": h5d_avg_mdd,
            "v6_h10d": h10d_avg_mdd,
            "ensemble_50_50_proxy": ensemble_avg_mdd,
            "note": "Ensemble MDD is arithmetic-mean proxy. True ensemble MDD would require per-day blended series; typically lower than mean of individuals.",
        },
    }


def step4_per_regime_decomposition(aligned: list[dict]) -> dict:
    """For each regime calendar window, compute h5d / h10d / ensemble
    window metrics.
    """
    out = {}
    for regime_name, (start, end) in REGIME_WINDOWS.items():
        regime_windows = []
        for w in aligned:
            ts = _parse_iso_date(w["h5d_test_start"])
            te = _parse_iso_date(w["h5d_test_end"])
            # Window is "in regime" if midpoint falls in regime range
            mid = ts + (te - ts) / 2
            if start <= mid <= end:
                regime_windows.append(w)
        if not regime_windows:
            out[regime_name] = {"status": "no_overlap", "n_windows": 0}
            continue

        h5d_r = np.array([w["h5d_net_return"] for w in regime_windows])
        h10d_r = np.array([w["h10d_net_return"] for w in regime_windows])
        h5d_s = np.array([w["h5d_sharpe"] for w in regime_windows])
        h10d_s = np.array([w["h10d_sharpe"] for w in regime_windows])
        ensemble_r = 0.5 * h5d_r + 0.5 * h10d_r
        ensemble_s = 0.5 * h5d_s + 0.5 * h10d_s

        out[regime_name] = {
            "n_windows_in_regime": int(len(regime_windows)),
            "v6_h5d_median_sharpe": _median_sharpe_per_window(h5d_s),
            "v6_h10d_median_sharpe": _median_sharpe_per_window(h10d_s),
            "ensemble_median_sharpe": _median_sharpe_per_window(ensemble_s),
            "v6_h5d_mean_return": float(h5d_r.mean()),
            "v6_h10d_mean_return": float(h10d_r.mean()),
            "ensemble_mean_return": float(ensemble_r.mean()),
            "regime_window_list": [
                {
                    "h5d_test_start": w["h5d_test_start"],
                    "h5d_net_return": w["h5d_net_return"],
                    "h10d_net_return": w["h10d_net_return"],
                    "h5d_sharpe": w["h5d_sharpe"],
                    "h10d_sharpe": w["h10d_sharpe"],
                }
                for w in regime_windows
            ],
        }
    return out


def step5_decision(step3: dict, step4: dict) -> dict:
    """Final decision: promote / defer / decline ensemble."""
    median_sharpe_delta = step3["median_window_sharpe"]["delta_ensemble_vs_max_individual"]
    loss_window_delta = step3["loss_window_fraction"]["delta_ensemble_vs_min_individual"]
    annualized_delta = step3["annualized_sharpe_from_returns"]["delta_ensemble_vs_max_individual"]

    # Decision criteria (tunable):
    PROMOTE_MEDIAN_SHARPE_DELTA_MIN = 0.10
    PROMOTE_LOSS_WINDOW_FRACTION_DELTA_MAX = 0.02
    PROMOTE_ANNUALIZED_DELTA_MIN = 0.20

    # Per-regime — ensemble must not break any regime
    regime_breaks = []
    for regime, v in step4.items():
        if "status" in v:
            continue
        if v["ensemble_median_sharpe"] < min(v["v6_h5d_median_sharpe"], v["v6_h10d_median_sharpe"]) - 0.5:
            regime_breaks.append({
                "regime": regime,
                "ensemble_sharpe": v["ensemble_median_sharpe"],
                "h5d_sharpe": v["v6_h5d_median_sharpe"],
                "h10d_sharpe": v["v6_h10d_median_sharpe"],
            })

    decision_inputs = {
        "median_sharpe_delta": median_sharpe_delta,
        "median_sharpe_delta_threshold": PROMOTE_MEDIAN_SHARPE_DELTA_MIN,
        "loss_window_fraction_delta": loss_window_delta,
        "loss_window_fraction_delta_max": PROMOTE_LOSS_WINDOW_FRACTION_DELTA_MAX,
        "annualized_delta": annualized_delta,
        "annualized_delta_threshold": PROMOTE_ANNUALIZED_DELTA_MIN,
        "regime_breaks": regime_breaks,
    }

    if (
        median_sharpe_delta >= PROMOTE_MEDIAN_SHARPE_DELTA_MIN
        and loss_window_delta <= PROMOTE_LOSS_WINDOW_FRACTION_DELTA_MAX
        and annualized_delta >= PROMOTE_ANNUALIZED_DELTA_MIN
        and not regime_breaks
    ):
        verdict = "PROMOTE — ensemble materially outperforms both standalone candidates"
        action = "build new manifest cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_ensemble_lsk3_g_v2.json"
    elif (
        median_sharpe_delta >= 0
        and loss_window_delta <= PROMOTE_LOSS_WINDOW_FRACTION_DELTA_MAX
        and not regime_breaks
    ):
        verdict = "DEFER — ensemble is at-par, no material upside; preserve as analytical option"
        action = "do NOT promote; keep v6_h5d + v6_h10d as separate active_alternative"
    else:
        verdict = "DECLINE — ensemble degrades on at least one criterion"
        action = "do NOT promote; v6_h10d remains the strongest single-horizon candidate"

    return {
        "decision_inputs": decision_inputs,
        "verdict": verdict,
        "recommended_action": action,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v_alpha_v6 dual-horizon ensemble portfolio analysis.")
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--h5d-report", type=Path, default=DEFAULT_H5D_REPORT)
    parser.add_argument("--h10d-report", type=Path, default=DEFAULT_H10D_REPORT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== v6 dual-horizon ensemble analysis (as-of {args.as_of}) ===")
    print(f"  h5d report:  {args.h5d_report}")
    print(f"  h10d report: {args.h10d_report}")
    print()

    print("=== Step 1: Load + align per-window arrays ===")
    s1 = step1_load_and_summarize(args.h5d_report, args.h10d_report)
    print()

    print("=== Step 2: Per-window correlation ===")
    s2 = step2_per_window_correlation(s1["aligned_windows"])
    print(f"  Pearson corr(net_returns):       {s2['pearson_corr_net_returns']:+.3f}")
    print(f"  Pearson corr(per-window sharpe): {s2['pearson_corr_sharpes']:+.3f}")
    print(f"  Spearman corr(net_returns):      {s2['spearman_corr_net_returns']:+.3f}")
    print(f"  Same-sign fraction:              {s2['same_sign_fraction']:.2%}")
    print(f"    both positive:  {s2['both_positive_fraction']:.2%}")
    print(f"    both negative:  {s2['both_negative_fraction']:.2%}")
    print(f"    h5d-only positive: {s2['h5d_only_positive_fraction']:.2%}")
    print(f"    h10d-only positive: {s2['h10d_only_positive_fraction']:.2%}")
    print(f"  Diversification score: {s2['diversification_score_from_correlation']}")
    print()

    print("=== Step 3: Ensemble portfolio (50/50 capital split) ===")
    s3 = step3_construct_ensemble(s1["aligned_windows"])
    msh = s3["median_window_sharpe"]
    print(f"  Median window sharpe (matches validation contract metric):")
    print(f"    v6_h5d:           {msh['v6_h5d']:+.3f}")
    print(f"    v6_h10d:          {msh['v6_h10d']:+.3f}")
    print(f"    ensemble (50/50): {msh['ensemble_50_50']:+.3f}  (delta vs max: {msh['delta_ensemble_vs_max_individual']:+.3f})")
    lwf = s3["loss_window_fraction"]
    print(f"  Loss window fraction:")
    print(f"    v6_h5d:           {lwf['v6_h5d']:.3f}")
    print(f"    v6_h10d:          {lwf['v6_h10d']:.3f}")
    print(f"    ensemble (50/50): {lwf['ensemble_50_50']:.3f}  (delta vs min: {lwf['delta_ensemble_vs_min_individual']:+.3f})")
    asn = s3["annualized_sharpe_from_returns"]
    print(f"  Annualized sharpe (from monthly returns):")
    print(f"    v6_h5d:           {asn['v6_h5d']:+.3f}")
    print(f"    v6_h10d:          {asn['v6_h10d']:+.3f}")
    print(f"    ensemble (50/50): {asn['ensemble_50_50']:+.3f}  (delta vs max: {asn['delta_ensemble_vs_max_individual']:+.3f})")
    cum = s3["cumulative_compound_return"]
    print(f"  Cumulative compound return:")
    print(f"    v6_h5d:           {cum['v6_h5d']:+.4f}  (i.e., {cum['v6_h5d']*100:+.2f}%)")
    print(f"    v6_h10d:          {cum['v6_h10d']:+.4f}  (i.e., {cum['v6_h10d']*100:+.2f}%)")
    print(f"    ensemble (50/50): {cum['ensemble_50_50']:+.4f}  (i.e., {cum['ensemble_50_50']*100:+.2f}%)")
    print()

    print("=== Step 4: Per-regime decomposition ===")
    s4 = step4_per_regime_decomposition(s1["aligned_windows"])
    for regime, v in s4.items():
        if "status" in v:
            print(f"  {regime}: {v['status']}")
            continue
        print(f"  {regime} (n_windows={v['n_windows_in_regime']}):")
        print(f"    h5d:      median_sharpe={v['v6_h5d_median_sharpe']:+.3f}  mean_return={v['v6_h5d_mean_return']:+.4f}")
        print(f"    h10d:     median_sharpe={v['v6_h10d_median_sharpe']:+.3f}  mean_return={v['v6_h10d_mean_return']:+.4f}")
        print(f"    ensemble: median_sharpe={v['ensemble_median_sharpe']:+.3f}  mean_return={v['ensemble_mean_return']:+.4f}")
    print()

    print("=== Step 5: Decision ===")
    s5 = step5_decision(s3, s4)
    print(f"  Decision inputs:")
    di = s5["decision_inputs"]
    print(f"    median_sharpe_delta:        {di['median_sharpe_delta']:+.3f}  (threshold ≥ {di['median_sharpe_delta_threshold']:+.3f})")
    print(f"    loss_window_delta:          {di['loss_window_fraction_delta']:+.3f}  (max ≤ {di['loss_window_fraction_delta_max']:+.3f})")
    print(f"    annualized_sharpe_delta:    {di['annualized_delta']:+.3f}  (threshold ≥ {di['annualized_delta_threshold']:+.3f})")
    print(f"    regime_breaks:              {len(di['regime_breaks'])}")
    print(f"  VERDICT: {s5['verdict']}")
    print(f"  Action:  {s5['recommended_action']}")
    print()

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "h5d_report_path": str(args.h5d_report),
        "h10d_report_path": str(args.h10d_report),
        "step1_load_summary": {
            "n_aligned_windows": s1["n_aligned_windows"],
            "h5d_first_test_start": s1["aligned_windows"][0]["h5d_test_start"] if s1["aligned_windows"] else None,
            "h5d_last_test_end": s1["aligned_windows"][-1]["h5d_test_end"] if s1["aligned_windows"] else None,
        },
        "step2_correlation": s2,
        "step3_ensemble_portfolio": s3,
        "step4_per_regime_decomposition": s4,
        "step5_decision": s5,
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "v6_dual_horizon_ensemble.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== Done. Analysis at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
