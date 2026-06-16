"""compute_lsk3_decay_deep_dive.py — per-regime + per-quarter deep dive
on the 2 lsk3 factors flagged as TRUE regime-shift by the lsk3 baseline
late-2026 decay diagnostic.

Context. The lsk3-late-2026 decay diagnostic (commit `a340f87`) found:
  - `coinglass_top_trader_long_pct_smooth_5`: early raw IC -0.035 -> late
    raw IC -0.008 (signal weakened to near-zero; bootstrap CI [-0.019,
    +0.003] includes 0).
  - `momentum_decay_5_20`: early raw IC -0.022 -> late raw IC +0.015
    (SIGN FLIPPED; bootstrap CI [-0.008, +0.039] includes 0).

This script provides owner-actionable diagnostic detail at finer
temporal granularity (calendar quarters) and overlays the existing
regime calendar to identify candidate causes of 2025 Q3-Q4 structural
change.

4-step deep dive:
  Step 1: Per-quarter raw IC + t-stat + bootstrap CI
          (10 calendar quarters from 2024-Q2 to 2026-Q2-partial)
  Step 2: Per-regime IC overlay
          (trend_up_2025h2 / rotation_high_vol_2025q4 / drawdown_rebound_2026ytd)
  Step 3: Cross-section dispersion (factor std + p10-p90 spread per quarter)
  Step 4: Per-quarter universe macro stats (mean fwd return, BTC vol
          regime, factor mean cross-sectional level)

Output:
  artifacts/quant_research/factor_reports/<as-of>/lsk3_decay_deep_dive.json
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
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    per_timestamp_rank_ic,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_lsk3_decay_deep_dive.v1"

# Factors under investigation (TRUE regime-shift per a340f87 diagnostic)
TARGET_FACTORS = (
    "coinglass_top_trader_long_pct_smooth_5",
    "momentum_decay_5_20",
)

# Existing regime calendar (per validation_contract regime_holdout)
REGIME_WINDOWS = {
    "trend_up_2025h2": (date(2025, 8, 1), date(2025, 10, 31)),
    "rotation_high_vol_2025q4": (date(2025, 11, 1), date(2026, 1, 31)),
    "drawdown_rebound_2026ytd": (date(2026, 2, 1), date(2026, 4, 30)),
}

BOOTSTRAP_ITERATIONS = 500
RNG_SEED = 20260430


def _ic_with_t_stat(
    factor: pd.Series, target: pd.Series, timestamps: pd.Series
) -> tuple[float, float, int]:
    factor_clean = pd.to_numeric(factor, errors="coerce").fillna(0.0)
    target_clean = pd.to_numeric(target, errors="coerce")
    ic = per_timestamp_rank_ic(factor_clean, target_clean, timestamps).dropna()
    if len(ic) < 5:
        return float("nan"), float("nan"), int(len(ic))
    m = float(ic.mean())
    s = float(ic.std()) if len(ic) > 1 else 0.0
    n = int(len(ic))
    t = float(m * np.sqrt(n) / s) if s > 0 else 0.0
    return m, t, n


def _bootstrap_ic_ci(
    panel: pd.DataFrame, factor_col: str, *, iterations: int = BOOTSTRAP_ITERATIONS
) -> dict:
    """80% timestamp resample bootstrap of raw IC."""
    rng = np.random.default_rng(RNG_SEED)
    unique_ts = panel["timestamp_ms"].unique()
    n_ts = len(unique_ts)
    if n_ts < 30:
        return {"status": "insufficient", "n_ts": int(n_ts)}
    sample_size = max(int(n_ts * 0.8), 20)
    samples = []
    for _ in range(iterations):
        sample_ts = rng.choice(unique_ts, size=sample_size, replace=True)
        sub = panel[panel["timestamp_ms"].isin(sample_ts)]
        m, _, _ = _ic_with_t_stat(
            sub[factor_col], sub["target_forward_return"], sub["timestamp_ms"]
        )
        if not np.isnan(m):
            samples.append(m)
    if not samples:
        return {"status": "no_samples"}
    arr = np.asarray(samples)
    ci_low = float(np.quantile(arr, 0.025))
    ci_high = float(np.quantile(arr, 0.975))
    return {
        "n_iterations": int(len(arr)),
        "bootstrap_mean": float(arr.mean()),
        "bootstrap_std": float(arr.std()),
        "ci_95_low": ci_low,
        "ci_95_high": ci_high,
        "ci_excludes_zero": bool((ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0)),
    }


def _date_to_quarter(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def step1_per_quarter_ic(panel: pd.DataFrame) -> dict:
    """Per-calendar-quarter raw IC + t-stat + bootstrap CI."""
    panel = panel.copy()
    panel["date"] = panel["date_utc"].apply(lambda s: date.fromisoformat(s))
    panel["quarter"] = panel["date"].apply(_date_to_quarter)

    out = {}
    for factor_col in TARGET_FACTORS:
        if factor_col not in panel.columns:
            out[factor_col] = {"status": "missing"}
            continue
        per_q = {}
        quarters = sorted(panel["quarter"].unique())
        for q in quarters:
            sub = panel[panel["quarter"] == q]
            if len(sub["timestamp_ms"].unique()) < 10:
                continue
            m, t, n = _ic_with_t_stat(sub[factor_col], sub["target_forward_return"], sub["timestamp_ms"])
            if np.isnan(m):
                continue
            ci = _bootstrap_ic_ci(sub, factor_col, iterations=300)
            per_q[q] = {
                "ic_mean": m,
                "t_stat": t,
                "n_ts": n,
                "n_rows": int(len(sub)),
                "date_range": [sub["date"].min().isoformat(), sub["date"].max().isoformat()],
                "bootstrap": ci,
            }
        out[factor_col] = per_q
    return out


def step2_per_regime_ic(panel: pd.DataFrame) -> dict:
    """Per-regime IC overlay."""
    panel = panel.copy()
    panel["date"] = panel["date_utc"].apply(lambda s: date.fromisoformat(s))

    regimes_with_pre = dict(REGIME_WINDOWS)
    # Add "pre-regime" early period
    earliest = panel["date"].min()
    pre_end = min(d for d, _ in REGIME_WINDOWS.values())
    regimes_with_pre = {
        "pre_regime_2024_2025h1": (earliest, pre_end - pd.Timedelta(days=1).to_pytimedelta()),
        **REGIME_WINDOWS,
    }

    out = {}
    for factor_col in TARGET_FACTORS:
        if factor_col not in panel.columns:
            out[factor_col] = {"status": "missing"}
            continue
        per_regime = {}
        for regime_name, (start, end) in regimes_with_pre.items():
            mask = (panel["date"] >= start) & (panel["date"] <= end)
            sub = panel[mask]
            if len(sub["timestamp_ms"].unique()) < 10:
                continue
            m, t, n = _ic_with_t_stat(sub[factor_col], sub["target_forward_return"], sub["timestamp_ms"])
            per_regime[regime_name] = {
                "ic_mean": m,
                "t_stat": t,
                "n_ts": n,
                "date_range": [start.isoformat(), end.isoformat()],
            }
        out[factor_col] = per_regime
    return out


def step3_cross_section_dispersion(panel: pd.DataFrame) -> dict:
    """Per-quarter cross-section dispersion of factor + universe-level
    distribution stats. If late-period cross-section converges (low std),
    factor loses ranking power.
    """
    panel = panel.copy()
    panel["date"] = panel["date_utc"].apply(lambda s: date.fromisoformat(s))
    panel["quarter"] = panel["date"].apply(_date_to_quarter)

    out = {}
    for factor_col in TARGET_FACTORS:
        if factor_col not in panel.columns:
            out[factor_col] = {"status": "missing"}
            continue
        per_q = {}
        quarters = sorted(panel["quarter"].unique())
        for q in quarters:
            sub = panel[panel["quarter"] == q]
            x = pd.to_numeric(sub[factor_col], errors="coerce")
            # Per-timestamp cross-sectional std + p90-p10 spread
            ts_groups = sub.groupby("timestamp_ms")[factor_col].agg(
                xs_mean="mean",
                xs_std="std",
                xs_p10=lambda v: np.nanquantile(pd.to_numeric(v, errors="coerce"), 0.10) if v.notna().any() else float("nan"),
                xs_p90=lambda v: np.nanquantile(pd.to_numeric(v, errors="coerce"), 0.90) if v.notna().any() else float("nan"),
                xs_n="size",
            )
            ts_groups["xs_p90_minus_p10"] = ts_groups["xs_p90"] - ts_groups["xs_p10"]
            if ts_groups.empty:
                continue
            per_q[q] = {
                "n_ts": int(len(ts_groups)),
                "mean_xs_std_per_ts": float(ts_groups["xs_std"].mean()),
                "median_xs_std_per_ts": float(ts_groups["xs_std"].median()),
                "mean_xs_p90_minus_p10": float(ts_groups["xs_p90_minus_p10"].mean()),
                "mean_xs_mean_level": float(ts_groups["xs_mean"].mean()),
                "median_xs_n_subjects": float(ts_groups["xs_n"].median()),
            }
        out[factor_col] = per_q
    return out


def step4_per_quarter_universe_macro(panel: pd.DataFrame) -> dict:
    """Per-quarter universe-level macro context: mean fwd return, BTC
    realized_volatility_20 mean, top_trader_long_pct universe mean,
    universe size.
    """
    panel = panel.copy()
    panel["date"] = panel["date_utc"].apply(lambda s: date.fromisoformat(s))
    panel["quarter"] = panel["date"].apply(_date_to_quarter)

    btc = panel[panel["subject"] == "BTC"].set_index("date")
    macro = {}
    quarters = sorted(panel["quarter"].unique())
    for q in quarters:
        sub = panel[panel["quarter"] == q]
        # Universe-aggregated stats
        fwd_mean = float(pd.to_numeric(sub["target_forward_return"], errors="coerce").mean())
        # BTC vol context
        btc_q = btc[btc["quarter"] == q] if "quarter" in btc.columns else None
        if btc_q is None or btc_q.empty:
            btc_subset = pd.to_numeric(
                panel[(panel["subject"] == "BTC") & (panel["quarter"] == q)]["realized_volatility_20"],
                errors="coerce",
            )
            btc_rv_mean = float(btc_subset.mean()) if not btc_subset.empty else float("nan")
        else:
            btc_rv_mean = float(pd.to_numeric(btc_q["realized_volatility_20"], errors="coerce").mean())
        # Universe top_trader_long_pct mean (level proxy)
        if "coinglass_top_trader_long_pct" in sub.columns:
            tt_mean = float(pd.to_numeric(sub["coinglass_top_trader_long_pct"], errors="coerce").mean())
        else:
            tt_mean = float("nan")
        macro[q] = {
            "n_rows": int(len(sub)),
            "n_subjects": int(sub["subject"].nunique()),
            "n_ts": int(sub["timestamp_ms"].nunique()),
            "universe_mean_fwd_return": fwd_mean,
            "btc_realized_vol_20_mean": btc_rv_mean,
            "universe_mean_top_trader_long_pct": tt_mean,
            "date_range": [sub["date"].min().isoformat(), sub["date"].max().isoformat()],
        }
    return macro


def main() -> int:
    parser = argparse.ArgumentParser(description="lsk3 decay deep dive on tt_smooth_5 + momentum_decay_5_20.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_ARTIFACT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args()

    print(f"=== lsk3 decay deep dive (as-of {args.as_of}) ===")
    raw_panel = pd.read_csv(args.features, compression="gzip")
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 columns...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    if "date_utc" not in panel.columns:
        from datetime import timezone as _tz
        panel["date_utc"] = panel["timestamp_ms"].apply(
            lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=_tz.utc).date().isoformat()
        )
    print()

    print("=== Step 1: Per-quarter raw IC + bootstrap CI ===")
    s1 = step1_per_quarter_ic(panel)
    for factor, per_q in s1.items():
        print(f"\n  {factor}:")
        if "status" in per_q:
            print(f"    {per_q['status']}")
            continue
        print(f"    {'quarter':10s}  {'IC':>9s}  {'t-stat':>7s}  {'CI95':>20s}  n_ts")
        for q in sorted(per_q.keys()):
            v = per_q[q]
            ci = v["bootstrap"]
            ci_str = f"[{ci.get('ci_95_low','-'):+.4f},{ci.get('ci_95_high','-'):+.4f}]" if "ci_95_low" in ci else "n/a"
            print(f"    {q:10s}  {v['ic_mean']:+.4f}  {v['t_stat']:+7.2f}  {ci_str:>20s}  {v['n_ts']}")
    print()

    print("=== Step 2: Per-regime IC overlay ===")
    s2 = step2_per_regime_ic(panel)
    for factor, per_regime in s2.items():
        print(f"\n  {factor}:")
        if "status" in per_regime:
            print(f"    {per_regime['status']}")
            continue
        print(f"    {'regime':30s}  {'IC':>9s}  {'t-stat':>7s}  n_ts")
        for r, v in per_regime.items():
            print(f"    {r:30s}  {v['ic_mean']:+.4f}  {v['t_stat']:+7.2f}  {v['n_ts']}")
    print()

    print("=== Step 3: Cross-section dispersion (factor std + p90-p10 per quarter) ===")
    s3 = step3_cross_section_dispersion(panel)
    for factor, per_q in s3.items():
        print(f"\n  {factor}:")
        if "status" in per_q:
            continue
        print(f"    {'quarter':10s}  {'mean_xs_std':>11s}  {'p90-p10':>10s}  {'mean_lvl':>10s}  n_ts")
        for q in sorted(per_q.keys()):
            v = per_q[q]
            print(
                f"    {q:10s}  {v['mean_xs_std_per_ts']:11.4f}  "
                f"{v['mean_xs_p90_minus_p10']:10.4f}  {v['mean_xs_mean_level']:+10.4f}  {v['n_ts']}"
            )
    print()

    print("=== Step 4: Per-quarter universe macro context ===")
    s4 = step4_per_quarter_universe_macro(panel)
    print(f"  {'quarter':10s}  {'mean_fwd_ret':>13s}  {'btc_rv20':>10s}  {'univ_tt_mean':>13s}  n_ts  n_subj")
    for q in sorted(s4.keys()):
        v = s4[q]
        print(
            f"  {q:10s}  {v['universe_mean_fwd_return']:+13.4f}  "
            f"{v['btc_realized_vol_20_mean']:10.4f}  "
            f"{v['universe_mean_top_trader_long_pct']:+13.4f}  "
            f"{v['n_ts']:4d}  {v['n_subjects']:6d}"
        )
    print()

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(args.features),
        "target_factors": list(TARGET_FACTORS),
        "regime_windows": {k: [v[0].isoformat(), v[1].isoformat()] for k, v in REGIME_WINDOWS.items()},
        "step1_per_quarter_ic": s1,
        "step2_per_regime_ic": s2,
        "step3_cross_section_dispersion": s3,
        "step4_per_quarter_universe_macro": s4,
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "lsk3_decay_deep_dive.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== Done. Deep dive at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
