"""Phase 1d (prerequisite): per-factor walk-forward IC stability diagnostic.

For each factor in the input list, computes walk-forward IC across N expanding
windows and classifies the factor based on stability + consistency + decay.

Used as a gating gate before any new factor admission, to prevent v92-style
in-sample IC failures (factors with strong full-panel IC but unstable OOS).

Algorithm:
  - Sort panel by date_utc; build N expanding-train walk-forward windows
    (train = [panel_start, test_start), test = [test_start, test_start+test_days)).
  - Per window per factor: cross-section z-score the factor inside the test
    segment, compute per-day Spearman IC vs target_forward_return, average to
    in-window IC.
  - Per factor across windows aggregate:
      ic_mean / ic_std / ic_t_stat
      sign_consistency = fraction of windows with sign matching mean sign
      abs_ic_above_threshold_fraction = fraction with |IC| above threshold
      decay_coef + decay_p_value = OLS slope of |IC| vs window index
      per_quarter_ic + quarter_consistency = sign agreement across quarters
  - Classification:
      stable           : sign_consistency >= sign_consistency_min AND
                         abs_ic_above_threshold_fraction >= 0.5 AND
                         quarter_consistency >= quarter_consistency_min
      regime-dependent : sign-consistent but quarter-inconsistent (works in
                         some regimes, not others)
      decay-fast       : significant negative |IC| trend across windows
      unstable         : sign_consistency < 0.5 (sign flips frequently)
      weak             : |ic_mean| < ic_stability_threshold (no signal)
      no_data          : zero valid windows

Run:
    python scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1d_wf_ic_stability_diagnostic.py
    python scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1d_wf_ic_stability_diagnostic.py \\
        --factors stress_liq_conc_iv,disagree_tt_retail
    python scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1d_wf_ic_stability_diagnostic.py \\
        --panel artifacts/.../features.csv.gz \\
        --n-windows 24 --train-days 365 --test-days 30

Output:
    artifacts/quant_research/shadow_oos/wf_ic_stability_<panel_dir>.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import linregress, spearmanr

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]

DEFAULT_PANEL = (
    ROOT / "artifacts" / "quant_research" / "features"
    / "2026-04-26-cross-sectional-daily-1d-h5d-features-v91" / "features.csv.gz"
)

# Default coverage: v94 baseline 10 + v91-discarded iv_smooth_60 (for sanity) + v92 B-batch 11.
# Lets us retroactively re-explain why v94 worked but v92 didn't, on a single run.
DEFAULT_FACTORS = [
    # v94 baseline (10)
    "intraday_realized_vol_4h_to_1d_smooth_20",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "distance_to_high_20",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    # v91-baseline (replaced in v94, kept here for sanity / family comparison)
    "intraday_realized_vol_4h_to_1d_smooth_60",
    # v92 B-batch (11; mostly disqualified by v92 cycle, expect 'unstable' / 'weak' here)
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Per-factor walk-forward IC stability diagnostic (v93 priority #2).")
    p.add_argument(
        "--panel", type=Path, default=DEFAULT_PANEL,
        help=f"Panel CSV path (default: {DEFAULT_PANEL.relative_to(ROOT)}).",
    )
    p.add_argument(
        "--factors", default=None,
        help="Comma-separated factor column names (default: built-in 22-item DEFAULT_FACTORS).",
    )
    p.add_argument(
        "--n-windows", type=int, default=32,
        help="Number of expanding-train walk-forward windows (default 32, matching v91 cycle WF count).",
    )
    p.add_argument(
        "--train-days", type=int, default=252,
        help="Initial train window in calendar days (default 252).",
    )
    p.add_argument(
        "--test-days", type=int, default=30,
        help="Per-window test segment in calendar days (default 30).",
    )
    p.add_argument(
        "--ic-stability-threshold", type=float, default=0.05,
        help="Min |IC mean| for non-'weak' classification (default 0.05).",
    )
    p.add_argument(
        "--sign-consistency-min", type=float, default=0.7,
        help="Min fraction of windows with sign matching mean for 'stable' (default 0.7).",
    )
    p.add_argument(
        "--quarter-consistency-min", type=float, default=0.6,
        help="Min fraction of quarters with sign matching mean for 'stable' (default 0.6).",
    )
    p.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "artifacts" / "quant_research" / "shadow_oos",
        help="Output directory.",
    )
    return p.parse_args()


def _ts_zscore(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    g = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    mu = g.groupby("t")["v"].transform("mean")
    sd = g.groupby("t")["v"].transform("std").replace(0, np.nan)
    return ((g["v"] - mu) / sd).fillna(0.0)


def _compute_ic_in_window(panel_window: pd.DataFrame, factor: str) -> tuple[float, int]:
    """Mean per-day Spearman IC of factor vs target_forward_return inside a window."""
    if factor not in panel_window.columns or panel_window.empty:
        return float("nan"), 0
    series = pd.to_numeric(panel_window[factor], errors="coerce")
    if not series.notna().any():
        return float("nan"), 0
    fill = series.median()
    z = _ts_zscore(series.fillna(fill), panel_window["timestamp_ms"])
    daily_ics: list[float] = []
    for ts, group in panel_window.groupby("timestamp_ms"):
        scores = z.loc[group.index]
        rets = group["target_forward_return"]
        valid = scores.notna() & rets.notna()
        if valid.sum() < 3 or scores[valid].std() == 0 or rets[valid].std() == 0:
            continue
        rho, _ = spearmanr(scores[valid], rets[valid])
        if not np.isnan(rho):
            daily_ics.append(float(rho))
    if not daily_ics:
        return float("nan"), 0
    return float(np.mean(daily_ics)), len(daily_ics)


def _build_walk_forward_windows(
    dates: pd.DatetimeIndex, n_windows: int, train_days: int, test_days: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Expanding-train, fixed-test walk-forward window list."""
    if dates.empty:
        return []
    sorted_dates = dates.sort_values()
    panel_start = sorted_dates[0]
    panel_end = sorted_dates[-1]
    total_days = (panel_end - panel_start).days
    if total_days < train_days + test_days:
        return []
    available_test_span = total_days - train_days
    if available_test_span < test_days:
        return []
    step = max(1, (available_test_span - test_days) // max(1, n_windows - 1))
    windows: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    test_start_offset = train_days
    for _ in range(n_windows):
        test_start = panel_start + pd.Timedelta(days=test_start_offset)
        test_end = test_start + pd.Timedelta(days=test_days)
        if test_end > panel_end + pd.Timedelta(days=1):
            break
        windows.append((panel_start, test_start, test_end))
        test_start_offset += step
    return windows


def _classify_factor(
    metrics: dict,
    *,
    ic_stability_threshold: float,
    sign_consistency_min: float,
    quarter_consistency_min: float,
) -> str:
    abs_ic_mean = abs(float(metrics.get("ic_mean", 0.0) or 0.0))
    sign_consistency = float(metrics.get("sign_consistency", 0.0) or 0.0)
    quarter_consistency = float(metrics.get("quarter_consistency", 0.0) or 0.0)
    abs_above_threshold = float(metrics.get("abs_ic_above_threshold_fraction", 0.0) or 0.0)
    decay_coef = float(metrics.get("decay_coef", 0.0) or 0.0)
    decay_p_value = float(metrics.get("decay_p_value", 1.0) or 1.0)

    if abs_ic_mean < ic_stability_threshold:
        return "weak"
    if sign_consistency < 0.5:
        return "unstable"
    if decay_coef < -0.005 and decay_p_value < 0.10:
        return "decay-fast"
    if quarter_consistency < quarter_consistency_min:
        return "regime-dependent"
    if sign_consistency >= sign_consistency_min and abs_above_threshold >= 0.5:
        return "stable"
    return "regime-dependent"


def main(argv: list[str] | None = None) -> int:
    args = parse_args()
    out_dir = Path(args.output_dir).expanduser().resolve()

    print(f"=== Loading panel: {args.panel}")
    panel = pd.read_csv(args.panel)
    panel["timestamp_ms"] = panel["timestamp_ms"].astype("int64")
    panel["date_utc"] = pd.to_datetime(panel["timestamp_ms"], unit="ms", utc=True).dt.normalize()
    panel = panel.dropna(subset=["target_forward_return", "subject"]).copy()
    if "selection_rank" in panel.columns:
        panel = panel[panel["selection_rank"] <= 20].copy()
    if "liquidity_bucket" in panel.columns:
        panel = panel[panel["liquidity_bucket"].isin(["top_liquidity", "mid_liquidity"])].copy()

    print(f"=== Panel rows: {len(panel)}, subjects: {panel['subject'].nunique()}, "
          f"range {panel['date_utc'].min().date()} -> {panel['date_utc'].max().date()}")

    factors = (
        [c.strip() for c in args.factors.split(",") if c.strip()]
        if args.factors else list(DEFAULT_FACTORS)
    )
    available = [c for c in factors if c in panel.columns]
    missing = [c for c in factors if c not in panel.columns]
    if missing:
        print(f"=== Missing factors (skipped): {missing}")
    print(f"=== Factor universe: {len(available)}")

    dates = pd.DatetimeIndex(panel["date_utc"].drop_duplicates())
    windows = _build_walk_forward_windows(dates, args.n_windows, args.train_days, args.test_days)
    print(f"=== Walk-forward windows constructed: {len(windows)} (target {args.n_windows}, "
          f"train_days={args.train_days}, test_days={args.test_days})")
    if not windows:
        print("ERROR: no valid walk-forward windows", file=sys.stderr)
        return 1
    print(f"=== First test window: {windows[0][1].date()} -> {windows[0][2].date()}")
    print(f"=== Last  test window: {windows[-1][1].date()} -> {windows[-1][2].date()}")

    per_factor_results: dict[str, dict] = {}
    for col in available:
        per_window: list[dict] = []
        per_quarter: dict[str, list[float]] = defaultdict(list)
        for (_, test_start, test_end) in windows:
            window_panel = panel[(panel["date_utc"] >= test_start) & (panel["date_utc"] < test_end)]
            ic, n_days = _compute_ic_in_window(window_panel, col)
            if not np.isnan(ic):
                per_window.append({
                    "test_start": test_start.date().isoformat(),
                    "test_end": test_end.date().isoformat(),
                    "ic": ic,
                    "n_days": n_days,
                })
                quarter = f"{test_start.year}Q{(test_start.month - 1) // 3 + 1}"
                per_quarter[quarter].append(ic)

        ics = [w["ic"] for w in per_window]
        if not ics:
            per_factor_results[col] = {"ic_mean": float("nan"), "n_windows": 0, "classification": "no_data"}
            continue

        ic_mean = float(np.mean(ics))
        ic_std = float(np.std(ics))
        ic_t_stat = float(ic_mean / (ic_std / np.sqrt(len(ics)))) if ic_std > 0 else 0.0
        sign_match = sum(1 for ic in ics if (ic > 0) == (ic_mean > 0))
        sign_consistency = sign_match / len(ics)
        abs_above = sum(1 for ic in ics if abs(ic) > args.ic_stability_threshold)
        abs_ic_above_threshold_fraction = abs_above / len(ics)

        abs_ics = [abs(ic) for ic in ics]
        x = np.arange(len(abs_ics), dtype="float64")
        slope_result = linregress(x, abs_ics)
        decay_coef = float(slope_result.slope)
        decay_p_value = float(slope_result.pvalue)

        per_quarter_summary = {q: float(np.mean(qics)) for q, qics in per_quarter.items()}
        if per_quarter_summary:
            mean_sign = 1 if ic_mean > 0 else -1
            quarter_match = sum(
                1 for v in per_quarter_summary.values() if (1 if v > 0 else -1) == mean_sign
            )
            quarter_consistency = quarter_match / len(per_quarter_summary)
        else:
            quarter_consistency = 0.0

        metrics = {
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "ic_t_stat": ic_t_stat,
            "n_windows": len(ics),
            "sign_consistency": sign_consistency,
            "abs_ic_above_threshold_fraction": abs_ic_above_threshold_fraction,
            "decay_coef": decay_coef,
            "decay_p_value": decay_p_value,
            "per_quarter_ic": per_quarter_summary,
            "quarter_consistency": quarter_consistency,
            "per_window_ic": per_window,
        }
        metrics["classification"] = _classify_factor(
            metrics,
            ic_stability_threshold=args.ic_stability_threshold,
            sign_consistency_min=args.sign_consistency_min,
            quarter_consistency_min=args.quarter_consistency_min,
        )
        per_factor_results[col] = metrics

    print("\n=== Per-factor stability summary (sorted by |IC mean|) ===")
    sorted_factors = sorted(
        per_factor_results.items(),
        key=lambda kv: -abs(float(kv[1].get("ic_mean", 0) or 0)),
    )
    print(f"  {'factor':50s} {'IC':>8s} {'sign%':>8s} {'qtr%':>8s} {'decay':>9s} {'pval':>7s} {'class':>17s}")
    for col, m in sorted_factors:
        print(f"  {col:50s} {float(m.get('ic_mean', 0) or 0):+8.4f} "
              f"{float(m.get('sign_consistency', 0) or 0):>8.1%} "
              f"{float(m.get('quarter_consistency', 0) or 0):>8.1%} "
              f"{float(m.get('decay_coef', 0) or 0):+9.4f} "
              f"{float(m.get('decay_p_value', 1) or 1):>7.3f} "
              f"{m.get('classification', 'no_data'):>17s}")

    by_class: dict[str, list[str]] = defaultdict(list)
    for col, m in per_factor_results.items():
        by_class[m.get("classification", "no_data")].append(col)
    print("\n=== Classification summary ===")
    for cls in ["stable", "regime-dependent", "decay-fast", "unstable", "weak", "no_data"]:
        if cls in by_class:
            print(f"  {cls} ({len(by_class[cls])}):")
            for c in by_class[cls]:
                print(f"    - {c}")

    panel_stem = args.panel.parent.name
    out_path = out_dir / f"wf_ic_stability_{panel_stem}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "panel_path": str(args.panel),
        "n_windows": len(windows),
        "train_days": args.train_days,
        "test_days": args.test_days,
        "first_test_window": [str(windows[0][1].date()), str(windows[0][2].date())],
        "last_test_window": [str(windows[-1][1].date()), str(windows[-1][2].date())],
        "thresholds": {
            "ic_stability_threshold": args.ic_stability_threshold,
            "sign_consistency_min": args.sign_consistency_min,
            "quarter_consistency_min": args.quarter_consistency_min,
        },
        "factors": per_factor_results,
        "summary_by_classification": dict(by_class),
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
        f.write("\n")
    print(f"\n=== Output written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
