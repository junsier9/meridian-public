"""Phase 1d step 1: dynamic factor weight schedule generator.

For each rebalance date (default quarterly), compute per-factor rolling IR
(mean IC / std IC over expanding lookback ending 5 trading days before the
rebalance — PIT-correct) and produce sign-aware softmax weights with a
±20% relative rate limit per rebalance.

Output JSON: list of {rebalance_date, weights_per_factor, diagnostics}, used
by xs_minimal_v13_score (Phase 1d step 2) at backtest time.

Algorithm:
  1. Read panel, compute per-day per-factor Spearman IC vs target_forward_return.
  2. Determine rebalance dates (quarter starts within panel range).
  3. For each rebalance date:
       lookback_end = rebalance_date - 5 trading days  (PIT-correct lag)
       lookback = all panel dates before lookback_end
       For each factor f:
           ic_series = per-day IC restricted to lookback
           ir_f = mean(ic_series) / std(ic_series)
           sign_f = sign(mean(ic_series))
       magnitudes = softmax(|IR| / temperature)  # sum to 1.0
       signed_weights = {f: sign_f * magnitudes[f] for f in factors}
       Apply rate limit: each weight |delta| <= 0.20 * |prev_weight|
       Save {rebalance_date, signed_weights, diagnostics}.

  Bootstrap (first rebalance): use v97 hand-tuned weights normalized to |sum|=1.0
  (no prior IC data available; v94 + v97 weights are empirically-evolved per the
  v95+v96 lessons).

Run:
    python scripts/quant_research/phase_1d_dynamic_weight_schedule.py
    python scripts/quant_research/phase_1d_dynamic_weight_schedule.py \\
        --panel artifacts/.../features.csv.gz --temperature 0.5

Output:
    artifacts/quant_research/shadow_oos/dynamic_weight_schedule_<panel_dir>.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]

DEFAULT_PANEL = (
    ROOT / "artifacts" / "quant_research" / "features"
    / "2026-04-26-cross-sectional-daily-1d-h5d-features-v91" / "features.csv.gz"
)

# v97 (xs_minimal_v12_score) factor list and hand-tuned weights, used as bootstrap
# for the first rebalance when no prior IC history is available.
V97_FACTORS_AND_WEIGHTS: OrderedDict[str, float] = OrderedDict([
    ("intraday_realized_vol_4h_to_1d_smooth_20", -0.20),
    ("realized_volatility_5",                    -0.10),
    ("distance_to_high_60",                      +0.11),
    ("distance_to_high_5",                       +0.10),
    ("distance_to_high_20",                      +0.13),
    ("coinglass_top_trader_long_pct_smooth_5",   -0.07),
    ("liquidity_stress_qv_iv",                   -0.10),
    ("momentum_decay_5_20",                      -0.06),
    ("coinglass_taker_imb_intraday_dispersion_24h", +0.05),
    ("quality_funding_oi",                       -0.05),
    ("stress_liq_conc_iv",                       -0.11),
])

PIT_LAG_TRADING_DAYS = 5  # weight at rebalance t uses IC data ending t - 5 trading days


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 1d step 1: dynamic factor weight schedule generator")
    p.add_argument("--panel", type=Path, default=DEFAULT_PANEL,
                   help=f"Panel CSV path (default: {DEFAULT_PANEL.relative_to(ROOT)})")
    p.add_argument("--rebalance-period", default="quarter",
                   choices=["quarter", "month", "60days"],
                   help="Rebalance frequency (default: quarter)")
    p.add_argument("--temperature", type=float, default=1.0,
                   help="Softmax temperature; lower = more concentrated weights (default 1.0)")
    p.add_argument("--max-relative-change", type=float, default=0.20,
                   help="Max relative change per weight per rebalance (default 0.20 = 20%%)")
    p.add_argument("--min-lookback-days", type=int, default=180,
                   help="Min lookback days for IR computation; falls back to bootstrap weights below (default 180)")
    p.add_argument("--output-dir", type=Path,
                   default=ROOT / "artifacts" / "quant_research" / "shadow_oos",
                   help="Output directory")
    return p.parse_args()


def _ts_zscore(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    g = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    mu = g.groupby("t")["v"].transform("mean")
    sd = g.groupby("t")["v"].transform("std").replace(0, np.nan)
    return ((g["v"] - mu) / sd).fillna(0.0)


def _per_day_ic(panel: pd.DataFrame, factor: str) -> pd.Series:
    """Returns Series indexed by date_utc of per-day Spearman IC of factor vs target_forward_return."""
    if factor not in panel.columns:
        return pd.Series(dtype="float64")
    series = pd.to_numeric(panel[factor], errors="coerce")
    if not series.notna().any():
        return pd.Series(dtype="float64")
    fill = series.median()
    z = _ts_zscore(series.fillna(fill), panel["timestamp_ms"])
    rows = []
    for ts, group in panel.groupby("timestamp_ms"):
        scores = z.loc[group.index]
        rets = group["target_forward_return"]
        valid = scores.notna() & rets.notna()
        if valid.sum() < 3 or scores[valid].std() == 0 or rets[valid].std() == 0:
            continue
        rho, _ = spearmanr(scores[valid], rets[valid])
        if not np.isnan(rho):
            date = pd.Timestamp(int(ts), unit="ms", tz="UTC").normalize()
            rows.append((date, float(rho)))
    if not rows:
        return pd.Series(dtype="float64")
    return pd.Series({d: ic for d, ic in rows}).sort_index()


def _build_rebalance_dates(date_min: pd.Timestamp, date_max: pd.Timestamp, period: str) -> list[pd.Timestamp]:
    if period == "quarter":
        # Quarter starts: Jan 1, Apr 1, Jul 1, Oct 1
        dates = pd.date_range(start=date_min, end=date_max, freq="QS-JAN", tz="UTC")
    elif period == "month":
        dates = pd.date_range(start=date_min, end=date_max, freq="MS", tz="UTC")
    elif period == "60days":
        dates = pd.date_range(start=date_min, end=date_max, freq="60D", tz="UTC")
    else:
        raise ValueError(f"unknown rebalance_period: {period}")
    return [d for d in dates if d > date_min and d <= date_max]


def _normalized_v97_bootstrap() -> OrderedDict[str, float]:
    abs_sum = sum(abs(w) for w in V97_FACTORS_AND_WEIGHTS.values())
    return OrderedDict((f, w / abs_sum) for f, w in V97_FACTORS_AND_WEIGHTS.items())


def _signed_softmax_weights(
    *,
    irs: dict[str, float],
    mean_ics: dict[str, float],
    temperature: float,
) -> OrderedDict[str, float]:
    """Sign-aware softmax: magnitude = softmax(|IR|/temp), sign = sign(mean IC)."""
    factors = list(irs.keys())
    abs_irs = np.array([abs(irs[f]) if not math.isnan(irs[f]) else 0.0 for f in factors], dtype="float64")
    if abs_irs.max() == 0.0:
        # No signal at all — uniform magnitudes
        magnitudes = np.full(len(factors), 1.0 / len(factors))
    else:
        scaled = abs_irs / max(temperature, 1e-9)
        # Numerical-stable softmax
        scaled = scaled - scaled.max()
        exp = np.exp(scaled)
        magnitudes = exp / exp.sum()
    out: OrderedDict[str, float] = OrderedDict()
    for f, mag in zip(factors, magnitudes):
        sign = 1.0 if mean_ics[f] >= 0 else -1.0
        out[f] = float(sign * mag)
    return out


def _rate_limit(prev: dict[str, float], new: dict[str, float], max_rel_change: float) -> tuple[OrderedDict[str, float], int]:
    """Limit each weight's |delta| to max_rel_change * |prev_weight|. Returns (limited_weights, n_clipped)."""
    out: OrderedDict[str, float] = OrderedDict()
    n_clipped = 0
    for f, n_w in new.items():
        p_w = prev.get(f, 0.0)
        if abs(p_w) < 1e-12:
            # Bootstrap or zero previous: accept new fully (no prior to limit against)
            out[f] = n_w
            continue
        max_delta = max_rel_change * abs(p_w)
        delta = n_w - p_w
        clipped_delta = max(-max_delta, min(max_delta, delta))
        if abs(clipped_delta - delta) > 1e-9:
            n_clipped += 1
        out[f] = p_w + clipped_delta
    return out, n_clipped


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
    print(f"=== Panel rows: {len(panel)}, range {panel['date_utc'].min().date()} -> {panel['date_utc'].max().date()}")

    factors = list(V97_FACTORS_AND_WEIGHTS.keys())
    bootstrap_weights = _normalized_v97_bootstrap()
    print(f"=== Factors: {len(factors)}; bootstrap weights normalized so abs sum = {sum(abs(w) for w in bootstrap_weights.values()):.3f}")

    print("=== Computing per-day per-factor IC time series (one pass)...")
    ic_per_factor: dict[str, pd.Series] = {}
    for f in factors:
        ic_per_factor[f] = _per_day_ic(panel, f)
        if ic_per_factor[f].empty:
            print(f"  WARN: factor {f} produced empty IC series; will treat as zero")

    panel_dates = sorted(panel["date_utc"].drop_duplicates())
    panel_min, panel_max = panel_dates[0], panel_dates[-1]
    rebalance_dates = _build_rebalance_dates(panel_min, panel_max, args.rebalance_period)
    print(f"=== Rebalance dates ({args.rebalance_period}): {len(rebalance_dates)}, "
          f"first {rebalance_dates[0].date() if rebalance_dates else None}, "
          f"last {rebalance_dates[-1].date() if rebalance_dates else None}")

    schedule: list[dict] = []
    prev_weights: dict[str, float] = {}
    for r_date in rebalance_dates:
        # Lookback ends PIT_LAG_TRADING_DAYS before rebalance
        lookback_end = r_date - pd.Timedelta(days=PIT_LAG_TRADING_DAYS + 2)  # ~5 trading days = 7 calendar days conservative
        lookback_days = (lookback_end - panel_min).days
        if lookback_days < args.min_lookback_days:
            # Bootstrap with v97 weights
            schedule.append({
                "rebalance_date": r_date.date().isoformat(),
                "weights": dict(bootstrap_weights),
                "diagnostics": {
                    "mode": "bootstrap_v97",
                    "lookback_days": int(lookback_days),
                    "n_clipped_by_rate_limit": 0,
                },
            })
            prev_weights = dict(bootstrap_weights)
            print(f"  {r_date.date()}  bootstrap (lookback {lookback_days}d < {args.min_lookback_days})")
            continue

        irs: dict[str, float] = {}
        mean_ics: dict[str, float] = {}
        n_obs: dict[str, int] = {}
        for f in factors:
            ic_s = ic_per_factor[f]
            mask = ic_s.index <= lookback_end
            window = ic_s[mask]
            if len(window) < 30 or window.std() == 0:
                irs[f] = 0.0
                mean_ics[f] = 0.0
                n_obs[f] = int(len(window))
                continue
            ir = float(window.mean() / window.std())
            irs[f] = ir
            mean_ics[f] = float(window.mean())
            n_obs[f] = int(len(window))

        new_weights = _signed_softmax_weights(irs=irs, mean_ics=mean_ics, temperature=args.temperature)
        limited_weights, n_clipped = _rate_limit(prev_weights, new_weights, args.max_relative_change)

        schedule.append({
            "rebalance_date": r_date.date().isoformat(),
            "weights": dict(limited_weights),
            "diagnostics": {
                "mode": "rolling_ir_softmax",
                "lookback_days": int(lookback_days),
                "lookback_end": lookback_end.date().isoformat(),
                "ir_per_factor": irs,
                "mean_ic_per_factor": mean_ics,
                "n_ic_obs_per_factor": n_obs,
                "softmax_temperature": args.temperature,
                "max_relative_change": args.max_relative_change,
                "n_clipped_by_rate_limit": int(n_clipped),
            },
        })
        prev_weights = dict(limited_weights)

    print("\n=== Weight schedule summary ===")
    print(f"  {'date':<12s}  {'mode':<22s}  {'top-3 by |w|':<60s}  {'clipped':>8s}")
    for entry in schedule:
        weights_sorted = sorted(entry["weights"].items(), key=lambda kv: -abs(kv[1]))[:3]
        top3_str = ", ".join(f"{f.split('_')[-2] if '_' in f else f}({w:+.3f})" for f, w in weights_sorted)
        n_clipped = entry["diagnostics"].get("n_clipped_by_rate_limit", 0)
        mode = entry["diagnostics"]["mode"]
        print(f"  {entry['rebalance_date']:<12s}  {mode:<22s}  {top3_str:<60s}  {n_clipped:>8d}")

    panel_stem = args.panel.parent.name
    out_path = out_dir / f"dynamic_weight_schedule_{panel_stem}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "panel_path": str(args.panel),
        "factors": factors,
        "bootstrap_weights": dict(bootstrap_weights),
        "params": {
            "rebalance_period": args.rebalance_period,
            "softmax_temperature": args.temperature,
            "max_relative_change": args.max_relative_change,
            "pit_lag_trading_days": PIT_LAG_TRADING_DAYS,
            "min_lookback_days": args.min_lookback_days,
        },
        "schedule": schedule,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
        f.write("\n")
    print(f"\n=== Output written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
