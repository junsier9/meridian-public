"""BTC options surface signal spike — exploration only, NOT in production pipeline.

Tests whether public Deribit DVOL (30d implied volatility index) can serve
as a regime modulator for the v91 cross-sectional baseline. Specifically:

  1. Lead-lag of DVOL z-score vs BTC forward return (does IV regime predict
     anything?).
  2. v91 portfolio (top-3 long-only of inline-reproduced xs_minimal_v6 score)
     conditional on high-vs-low IV regime — does sharpe collapse in high IV
     periods?
  3. Multiplier overlay: throttled portfolio = baseline * (1 - tanh((DVOL_z-1)*2))
     clipped to [0.3, 1.0]. Does worst-quarter sharpe improve materially?

Decision rule for downstream investment:
  - delta worst-quarter sharpe > +0.5 → strong, justify Deribit ingestion
    (Roadmap Phase 4b, ~2 weeks)
  - delta in [+0.2, +0.5] → moderate, further work warranted
  - delta < +0.2 → weak, redirect to event tape (unlock-only first version)

Data sources (all free, no auth):
  - Deribit DVOL daily history: https://www.deribit.com/api/v2/public/
    get_volatility_index_data?currency=BTC
  - v91 panel features.csv.gz (already on disk)

Inline reproduction of xs_minimal_v6_score is used so this script does NOT
import from features.py — keeps the spike out of the production code path.

Caveat: portfolio uses daily 5d-forward returns as observations (overlapping)
rather than 5d non-overlapping rebalance. Annualization uses sqrt(252/5).
Results are directional only; production verification requires a full
hypothesis_batch_cycle on a v92-overlay manifest.

Run:
    python scripts/quant_research/explore_btc_options_signals.py
    python scripts/quant_research/explore_btc_options_signals.py --as-of 2026-04-26
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

DEFAULT_PANEL = (
    ROOT / "artifacts" / "quant_research" / "features"
    / "2026-04-26-cross-sectional-daily-1d-h5d-features-v91" / "features.csv.gz"
)
DERIBIT_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"

# v91 weights — copied verbatim from features.py xs_minimal_v6_score.
# Inline reproduction avoids depending on production features.py.
V91_WEIGHTS = {
    "intraday_realized_vol_4h_to_1d_smooth_60": -0.20,
    "realized_volatility_5":                     -0.10,
    "distance_to_high_60":                       +0.18,
    "distance_to_high_5":                        +0.15,
    "coinglass_top_trader_long_pct_smooth_5":    -0.07,
    "liquidity_stress_qv_iv":                    -0.10,
    "momentum_decay_5_20":                       -0.06,
    "coinglass_taker_imb_intraday_dispersion_24h": +0.05,
    "quality_funding_oi":                        -0.05,
}


def multiplier_m0_baseline_dvol_level(port: pd.DataFrame) -> pd.Series:
    """Original baseline: tanh-shaped throttle on DVOL z90 above +1, floor 0.3."""
    return (1 - np.tanh((port["dvol_z90"].fillna(0.0) - 1.0) * 2.0)).clip(0.3, 1.0)


def multiplier_m1_dvol_change_only(port: pd.DataFrame) -> pd.Series:
    """Throttle only on DVOL_change_5d_z90 (IV shock signal)."""
    return (1 - np.tanh((port["dvol_change_5d_z90"].fillna(0.0) - 1.0) * 2.0)).clip(0.3, 1.0)


def multiplier_m2_max_level_or_change(port: pd.DataFrame) -> pd.Series:
    """Throttle on the larger of DVOL_z90 and DVOL_change_5d_z90 (level OR shock)."""
    z = pd.Series(
        np.maximum(port["dvol_z90"].fillna(0.0).to_numpy(),
                   port["dvol_change_5d_z90"].fillna(0.0).to_numpy()),
        index=port.index, dtype="float64",
    )
    return (1 - np.tanh((z - 1.0) * 2.0)).clip(0.3, 1.0)


def multiplier_m3_piecewise_level(port: pd.DataFrame) -> pd.Series:
    """Discrete piecewise on DVOL_z90: 1.0 / 0.7 / 0.4 / 0.2 by threshold bands."""
    z = port["dvol_z90"].fillna(0.0)
    out = pd.Series(1.0, index=z.index, dtype="float64")
    out[(z >= 0.5) & (z < 1.5)] = 0.7
    out[(z >= 1.5) & (z < 2.5)] = 0.4
    out[z >= 2.5] = 0.2
    return out


def multiplier_m4_piecewise_max_combined(port: pd.DataFrame) -> pd.Series:
    """Piecewise on max(DVOL_z90, DVOL_change_5d_z90) with same bands as m3."""
    z = pd.Series(
        np.maximum(port["dvol_z90"].fillna(0.0).to_numpy(),
                   port["dvol_change_5d_z90"].fillna(0.0).to_numpy()),
        index=port.index, dtype="float64",
    )
    out = pd.Series(1.0, index=z.index, dtype="float64")
    out[(z >= 0.5) & (z < 1.5)] = 0.7
    out[(z >= 1.5) & (z < 2.5)] = 0.4
    out[z >= 2.5] = 0.2
    return out


def multiplier_m5_aggressive_tanh(port: pd.DataFrame) -> pd.Series:
    """Steeper tanh, lower start threshold (z=+0.5), floor 0.2."""
    return (1 - np.tanh((port["dvol_z90"].fillna(0.0) - 0.5) * 3.0)).clip(0.2, 1.0)


def multiplier_m6_lower_floor(port: pd.DataFrame) -> pd.Series:
    """Same as m0 but lower floor 0.1 (allow near-full exit at extreme IV)."""
    return (1 - np.tanh((port["dvol_z90"].fillna(0.0) - 1.0) * 2.0)).clip(0.1, 1.0)


def multiplier_m7_btc_eth_max_aggressive(port: pd.DataFrame) -> pd.Series:
    """m5-form aggressive tanh on max(BTC_DVOL_z90, ETH_DVOL_z90) — multi-asset IV regime."""
    return (1 - np.tanh((port["max_iv_z90"].fillna(0.0) - 0.5) * 3.0)).clip(0.2, 1.0)


def multiplier_m8_iv_spread_modulator(port: pd.DataFrame) -> pd.Series:
    """Throttle when ETH IV unusually high relative to BTC (cross-asset stress proxy)."""
    return (1 - np.tanh((port["iv_spread_z90"].fillna(0.0) - 1.0) * 2.0)).clip(0.3, 1.0)


def multiplier_m9_compound_max_iv_or_spread(port: pd.DataFrame) -> pd.Series:
    """Aggressive tanh on max(max_iv_z90, iv_spread_z90) — combined regime + cross-asset stress."""
    z = pd.Series(
        np.maximum(port["max_iv_z90"].fillna(0.0).to_numpy(),
                   port["iv_spread_z90"].fillna(0.0).to_numpy()),
        index=port.index, dtype="float64",
    )
    return (1 - np.tanh((z - 0.5) * 3.0)).clip(0.2, 1.0)


MULTIPLIERS = {
    "m0_baseline_dvol_level":     multiplier_m0_baseline_dvol_level,
    "m1_dvol_change_only":        multiplier_m1_dvol_change_only,
    "m2_max_level_or_change":     multiplier_m2_max_level_or_change,
    "m3_piecewise_level":         multiplier_m3_piecewise_level,
    "m4_piecewise_max_combined":  multiplier_m4_piecewise_max_combined,
    "m5_aggressive_tanh":         multiplier_m5_aggressive_tanh,
    "m6_lower_floor_0_1":         multiplier_m6_lower_floor,
    "m7_btc_eth_max_aggressive":  multiplier_m7_btc_eth_max_aggressive,
    "m8_iv_spread_modulator":     multiplier_m8_iv_spread_modulator,
    "m9_compound_max_iv_spread":  multiplier_m9_compound_max_iv_or_spread,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BTC options surface regime modulator spike (research only).",
    )
    parser.add_argument(
        "--panel", type=Path, default=DEFAULT_PANEL,
        help=f"Path to v91 panel CSV (default: {DEFAULT_PANEL.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--as-of", default="2026-04-26",
        help="As-of label for the output JSON (default: 2026-04-26).",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "artifacts" / "quant_research" / "shadow_oos",
        help="Output directory for the spike JSON.",
    )
    parser.add_argument(
        "--top-k", type=int, default=3,
        help="Long-only top-K size for portfolio reproduction (default 3, matching v83 baseline).",
    )
    parser.add_argument(
        "--regime-z-threshold", type=float, default=1.0,
        help="DVOL z-score threshold separating high-IV vs low-IV regime (default 1.0).",
    )
    parser.add_argument(
        "--train-fraction", type=float, default=0.7,
        help="Fraction of portfolio observations as train period for holdout selection-bias check (default 0.7).",
    )
    parser.add_argument(
        "--train-from-end", action="store_true",
        help="Reverse holdout: train period from the END of the data (test whether stress-period training generalizes to mild-period test).",
    )
    return parser.parse_args()


def fetch_dvol_history(currency: str, start_ts_ms: int, end_ts_ms: int) -> pd.DataFrame:
    """Fetch DVOL daily history for a currency (BTC or ETH) from Deribit public endpoint. No auth."""
    params = {
        "currency": currency,
        "start_timestamp": int(start_ts_ms),
        "end_timestamp": int(end_ts_ms),
        "resolution": 86400,
    }
    response = requests.get(DERIBIT_DVOL_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "result" not in payload or "data" not in payload["result"]:
        raise RuntimeError(f"unexpected Deribit response shape: {payload!r}")
    rows = payload["result"]["data"]
    if not rows:
        raise RuntimeError("Deribit returned empty DVOL series — check date range and API quota")
    df = pd.DataFrame(rows, columns=["timestamp_ms", "open", "high", "low", "close"])
    df["timestamp_ms"] = df["timestamp_ms"].astype("int64")
    df["date_utc"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True).dt.normalize()
    df["dvol"] = df["close"].astype("float64")
    return df[["timestamp_ms", "date_utc", "dvol"]].sort_values("date_utc").reset_index(drop=True)


def compute_dvol_signals(dvol_df: pd.DataFrame) -> pd.DataFrame:
    """Build candidate options-surface signals from DVOL daily series."""
    df = dvol_df.copy()
    s = df["dvol"]
    df["dvol_z90"] = (s - s.rolling(90).mean()) / s.rolling(90).std()
    df["dvol_change_5d"] = s - s.shift(5)
    chg = df["dvol_change_5d"]
    df["dvol_change_5d_z90"] = (chg - chg.rolling(90).mean()) / chg.rolling(90).std()
    return df[["date_utc", "dvol", "dvol_z90", "dvol_change_5d", "dvol_change_5d_z90"]]


def lead_lag_spearman(signal: pd.Series, target: pd.Series, max_lag: int = 10) -> dict[int, float]:
    """Spearman correlation of signal[t] with target[t+lag]."""
    out: dict[int, float] = {}
    for lag in range(-max_lag, max_lag + 1):
        s = signal
        t = target.shift(-lag)
        valid = s.notna() & t.notna()
        if valid.sum() < 30:
            out[lag] = float("nan")
            continue
        rho, _ = spearmanr(s[valid], t[valid])
        out[lag] = float(rho) if not np.isnan(rho) else float("nan")
    return out


def reproduce_v91_score(panel: pd.DataFrame) -> pd.Series:
    """Inline reproduction of xs_minimal_v6_score per-timestamp z-score combination."""
    raw = pd.Series(0.0, index=panel.index, dtype="float64")
    for col, weight in V91_WEIGHTS.items():
        if col not in panel.columns:
            continue
        series = pd.to_numeric(panel[col], errors="coerce")
        # per-timestamp z-score (cross-section)
        grp = series.groupby(panel["timestamp_ms"])
        mu = grp.transform("mean")
        sd = grp.transform("std").replace(0, np.nan)
        z = ((series - mu) / sd).fillna(0.0)
        raw = raw + weight * z
    return raw


def per_day_top_k_portfolio(panel: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
    """For each timestamp, pick top-K assets by raw_score_v91 and average their
    target_forward_return as the portfolio's realized 5d return."""
    valid = panel.dropna(subset=["raw_score_v91", "target_forward_return"])
    rows = []
    for ts, group in valid.groupby("timestamp_ms"):
        if len(group) < top_k + 1:
            continue
        top = group.nlargest(top_k, "raw_score_v91")
        rows.append({
            "timestamp_ms": int(ts),
            "port_ret": float(top["target_forward_return"].mean()),
            "n_universe": int(len(group)),
        })
    df = pd.DataFrame(rows)
    df["date_utc"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True).dt.normalize()
    return df


def annualized_sharpe(returns: pd.Series, periods_per_year: float = 252.0 / 5.0) -> float:
    if returns.std() == 0 or returns.empty:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


def quarterly_sharpe(df: pd.DataFrame, return_col: str) -> dict[str, float]:
    df = df.copy()
    df["quarter"] = df["date_utc"].dt.to_period("Q").astype(str)
    out: dict[str, float] = {}
    for q, g in df.groupby("quarter"):
        out[q] = annualized_sharpe(g[return_col])
    return out


def regime_split(port_df: pd.DataFrame, threshold: float) -> dict[str, dict[str, float]]:
    aligned = port_df.dropna(subset=["port_ret", "dvol_z90"])
    high = aligned[aligned["dvol_z90"] > threshold]["port_ret"]
    low = aligned[aligned["dvol_z90"] <= threshold]["port_ret"]

    def stats(s: pd.Series) -> dict[str, float]:
        if s.empty:
            return {"n": 0, "mean": 0.0, "std": 0.0, "sharpe": 0.0, "min": 0.0}
        return {
            "n": int(len(s)),
            "mean": float(s.mean()),
            "std": float(s.std()),
            "sharpe": annualized_sharpe(s),
            "min": float(s.min()),
        }

    return {
        "high_iv_z_above_threshold": stats(high),
        "low_iv_z_at_or_below_threshold": stats(low),
        "threshold_z": float(threshold),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args() if argv is None else parse_args()
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

    btc = panel[panel["subject"] == "BTC"].copy().sort_values("timestamp_ms")
    print(f"=== Panel rows: {len(panel)}, subjects: {panel['subject'].nunique()}, "
          f"BTC rows: {len(btc)}, range {btc['date_utc'].min().date()} -> {btc['date_utc'].max().date()}")

    panel_start_ms = int(panel["timestamp_ms"].min())
    panel_end_ms = int(panel["timestamp_ms"].max())
    fetch_start_ms = panel_start_ms - 90 * 86_400_000

    print(f"=== Fetching Deribit BTC + ETH DVOL from {pd.to_datetime(fetch_start_ms, unit='ms').date()} "
          f"to {pd.to_datetime(panel_end_ms, unit='ms').date()}")
    try:
        btc_raw = fetch_dvol_history("BTC", fetch_start_ms, panel_end_ms)
        eth_raw = fetch_dvol_history("ETH", fetch_start_ms, panel_end_ms)
    except requests.RequestException as exc:
        print(f"ERROR: Deribit DVOL fetch failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Deribit DVOL parse failed: {exc}", file=sys.stderr)
        return 1
    print(f"=== BTC DVOL: {len(btc_raw)} obs, "
          f"range {btc_raw['date_utc'].min().date()} -> {btc_raw['date_utc'].max().date()}")
    print(f"=== ETH DVOL: {len(eth_raw)} obs, "
          f"range {eth_raw['date_utc'].min().date()} -> {eth_raw['date_utc'].max().date()}")

    btc_sig = compute_dvol_signals(btc_raw).rename(columns={
        "dvol":               "btc_dvol",
        "dvol_z90":           "btc_dvol_z90",
        "dvol_change_5d":     "btc_dvol_change_5d",
        "dvol_change_5d_z90": "btc_dvol_change_5d_z90",
    })
    eth_sig = compute_dvol_signals(eth_raw).rename(columns={
        "dvol":               "eth_dvol",
        "dvol_z90":           "eth_dvol_z90",
        "dvol_change_5d":     "eth_dvol_change_5d",
        "dvol_change_5d_z90": "eth_dvol_change_5d_z90",
    })
    sig = btc_sig.merge(eth_sig, on="date_utc", how="outer").sort_values("date_utc").reset_index(drop=True)

    sig["max_iv_z90"] = sig[["btc_dvol_z90", "eth_dvol_z90"]].max(axis=1)
    sig["iv_spread"] = sig["eth_dvol"] - sig["btc_dvol"]
    sig["iv_spread_z90"] = (sig["iv_spread"] - sig["iv_spread"].rolling(90).mean()) / sig["iv_spread"].rolling(90).std()

    # Backward-compat aliases for existing m0-m6 multipliers (BTC by default)
    sig["dvol_z90"] = sig["btc_dvol_z90"]
    sig["dvol_change_5d_z90"] = sig["btc_dvol_change_5d_z90"]

    # Downstream JSON output uses BTC-centric metadata
    dvol_raw = btc_raw

    btc_aligned = btc.merge(sig, on="date_utc", how="left")
    leadlag_btc = lead_lag_spearman(btc_aligned["dvol_z90"], btc_aligned["target_forward_return"], max_lag=10)
    leadlag_chg = lead_lag_spearman(btc_aligned["dvol_change_5d_z90"], btc_aligned["target_forward_return"], max_lag=10)

    print("\n=== Lead-lag: DVOL_z90 -> BTC target_forward_return ===")
    for lag in sorted(leadlag_btc):
        print(f"  lag={lag:+3d}d: rho={leadlag_btc[lag]:+.4f}")
    print("\n=== Lead-lag: DVOL_change_5d_z90 -> BTC target_forward_return ===")
    for lag in sorted(leadlag_chg):
        print(f"  lag={lag:+3d}d: rho={leadlag_chg[lag]:+.4f}")

    print("\n=== Reproducing v91 xs_minimal_v6 score on full panel...")
    panel = panel.sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)
    panel["raw_score_v91"] = reproduce_v91_score(panel)
    available_cols = [c for c in V91_WEIGHTS if c in panel.columns]
    missing_cols = [c for c in V91_WEIGHTS if c not in panel.columns]
    print(f"  v91 columns available: {len(available_cols)}/{len(V91_WEIGHTS)}")
    if missing_cols:
        print(f"  missing (treated as zero): {missing_cols}")

    port = per_day_top_k_portfolio(panel, top_k=args.top_k)
    print(f"=== Top-{args.top_k} long-only portfolio: {len(port)} daily observations")

    port = port.merge(sig, on="date_utc", how="left")

    base_full = annualized_sharpe(port["port_ret"])
    base_quarterly = quarterly_sharpe(port, "port_ret")
    base_worst = min(base_quarterly.values()) if base_quarterly else 0.0

    regime = regime_split(port, threshold=args.regime_z_threshold)

    print("\n=== Regime split: top-K v91 portfolio under high vs low IV ===")
    print(f"  high_iv (DVOL_z > {args.regime_z_threshold:+.1f}): "
          f"n={regime['high_iv_z_above_threshold']['n']}, "
          f"mean={regime['high_iv_z_above_threshold']['mean']:+.4f}, "
          f"sharpe={regime['high_iv_z_above_threshold']['sharpe']:+.3f}")
    print(f"  low_iv  (DVOL_z <= {args.regime_z_threshold:+.1f}): "
          f"n={regime['low_iv_z_at_or_below_threshold']['n']}, "
          f"mean={regime['low_iv_z_at_or_below_threshold']['mean']:+.4f}, "
          f"sharpe={regime['low_iv_z_at_or_below_threshold']['sharpe']:+.3f}")

    print(f"\n=== Baseline (no throttle): full sharpe={base_full:+.3f}, "
          f"worst-quarter sharpe={base_worst:+.3f}")

    multiplier_results: dict[str, dict[str, object]] = {}
    for name, fn in MULTIPLIERS.items():
        mul = fn(port).fillna(1.0).astype("float64")
        col_name = f"throttled_{name}"
        port[col_name] = port["port_ret"] * mul
        thr_full_i = annualized_sharpe(port[col_name])
        thr_quarterly_i = quarterly_sharpe(port, col_name)
        thr_worst_i = min(thr_quarterly_i.values()) if thr_quarterly_i else 0.0
        multiplier_results[name] = {
            "full_sharpe": thr_full_i,
            "worst_quarter_sharpe": thr_worst_i,
            "quarterly_sharpe": thr_quarterly_i,
            "delta_full_sharpe": thr_full_i - base_full,
            "delta_worst_quarter_sharpe": thr_worst_i - base_worst,
            "mean_multiplier": float(mul.mean()),
            "min_multiplier": float(mul.min()),
            "fraction_throttled": float((mul < 0.99).mean()),
        }

    ranked = sorted(
        multiplier_results.items(),
        key=lambda kv: -float(kv[1]["delta_worst_quarter_sharpe"]),
    )

    print("\n=== Multiplier comparison (sorted by delta worst-quarter sharpe) ===")
    print(f"  {'name':32s} {'thr_worst':>11s} {'delta_worst':>12s} {'thr_full':>10s} {'delta_full':>11s} {'frac_thr':>9s}")
    for name, r in ranked:
        thr_worst_disp = base_worst + float(r["delta_worst_quarter_sharpe"])
        thr_full_disp = base_full + float(r["delta_full_sharpe"])
        print(f"  {name:32s} {thr_worst_disp:+11.3f} "
              f"{float(r['delta_worst_quarter_sharpe']):+12.3f} "
              f"{thr_full_disp:+10.3f} "
              f"{float(r['delta_full_sharpe']):+11.3f} "
              f"{float(r['fraction_throttled']):>9.2%}")

    best_name, best_metrics = ranked[0]
    best_delta_worst = float(best_metrics["delta_worst_quarter_sharpe"])
    if best_delta_worst > 0.6:
        verdict = (f"STRONG: best multiplier '{best_name}' improves worst-quarter sharpe "
                   f"by {best_delta_worst:+.3f}; Deribit options ingestion (Phase 4b) justified.")
    elif best_delta_worst > 0.4:
        verdict = (f"MODERATE: best multiplier '{best_name}' delta {best_delta_worst:+.3f}; "
                   f"vendor investment for skew/term-slope may push to STRONG.")
    elif best_delta_worst > 0.2:
        verdict = (f"MARGINAL: best multiplier '{best_name}' delta {best_delta_worst:+.3f}; "
                   f"DVOL alone is limited; investigate skew/term or redirect to event-tape.")
    else:
        verdict = (f"WEAK: best multiplier '{best_name}' delta only {best_delta_worst:+.3f}; "
                   f"redirect to event-tape (unlock-only).")
    print(f"\n=== Verdict: {verdict}")

    # Holdout selection-bias check: chronologically split, train-select then test-evaluate.
    train_fraction = float(args.train_fraction)
    n_total = len(port)
    n_train = int(n_total * train_fraction)
    if args.train_from_end:
        train_port = port.iloc[-n_train:].copy().reset_index(drop=True)
        test_port = port.iloc[:n_total - n_train].copy().reset_index(drop=True)
    else:
        train_port = port.iloc[:n_train].copy().reset_index(drop=True)
        test_port = port.iloc[n_train:].copy().reset_index(drop=True)
    train_first = train_port["date_utc"].iloc[0]
    train_last = train_port["date_utc"].iloc[-1]
    test_first = test_port["date_utc"].iloc[0] if len(test_port) > 0 else None
    test_last = test_port["date_utc"].iloc[-1] if len(test_port) > 0 else None
    split_date = test_first

    direction = "train_from_end (REVERSE: train=stress-prone tail, test=earlier mild period)" if args.train_from_end else "train_from_start (default chronological)"
    print(f"\n=== Holdout split [{direction}], train fraction={train_fraction:.2f}: "
          f"train n={n_train} [{train_first.date()} -> {train_last.date()}], "
          f"test n={n_total - n_train} "
          f"[{test_first.date() if test_first is not None else 'N/A'} -> "
          f"{test_last.date() if test_last is not None else 'N/A'}]")

    train_base_quarterly = quarterly_sharpe(train_port, "port_ret")
    train_base_worst = min(train_base_quarterly.values()) if train_base_quarterly else 0.0
    test_base_quarterly = quarterly_sharpe(test_port, "port_ret") if len(test_port) >= 60 else {}
    test_base_worst = min(test_base_quarterly.values()) if test_base_quarterly else 0.0
    print(f"  baseline (no throttle): train worst-quarter={train_base_worst:+.3f}, "
          f"test worst-quarter={test_base_worst:+.3f}")

    holdout_results: dict[str, dict[str, object]] = {}
    for name, fn in MULTIPLIERS.items():
        tr_mul = fn(train_port).fillna(1.0).astype("float64")
        tr_thr = train_port["port_ret"].values * tr_mul.values
        tr_q_df = train_port[["date_utc"]].copy()
        tr_q_df["throttled"] = tr_thr
        tr_q_quarterly = quarterly_sharpe(tr_q_df, "throttled")
        tr_worst = min(tr_q_quarterly.values()) if tr_q_quarterly else 0.0

        te_mul = fn(test_port).fillna(1.0).astype("float64")
        te_thr = test_port["port_ret"].values * te_mul.values
        te_q_df = test_port[["date_utc"]].copy()
        te_q_df["throttled"] = te_thr
        te_q_quarterly = quarterly_sharpe(te_q_df, "throttled") if len(te_q_df) >= 60 else {}
        te_worst = min(te_q_quarterly.values()) if te_q_quarterly else 0.0

        holdout_results[name] = {
            "train_worst_quarter_sharpe": tr_worst,
            "train_delta_worst": tr_worst - train_base_worst,
            "test_worst_quarter_sharpe": te_worst,
            "test_delta_worst": te_worst - test_base_worst,
        }

    ranked_train = sorted(
        holdout_results.items(),
        key=lambda kv: -float(kv[1]["train_delta_worst"]),
    )

    print("\n=== Holdout: train-selection vs test-evaluation (sorted by train delta_worst) ===")
    print(f"  {'name':32s} {'train_dw':>10s} {'test_dw':>10s} {'status':>10s}")
    for name, r in ranked_train:
        te_dw = float(r["test_delta_worst"])
        if te_dw > 0.4:
            status = "OK"
        elif te_dw > 0.2:
            status = "PARTIAL"
        elif te_dw > 0.0:
            status = "WEAK"
        else:
            status = "INVERTED"
        print(f"  {name:32s} {float(r['train_delta_worst']):+10.3f} {te_dw:+10.3f} {status:>10s}")

    train_best_name = ranked_train[0][0]
    train_best_metrics = ranked_train[0][1]
    train_best_train_dw = float(train_best_metrics["train_delta_worst"])
    train_best_test_dw = float(train_best_metrics["test_delta_worst"])
    decay = train_best_train_dw - train_best_test_dw
    decay_pct = (decay / train_best_train_dw * 100) if train_best_train_dw != 0 else 0.0

    print(f"\n=== Selection-bias diagnostic ===")
    print(f"  Train-best multiplier: '{train_best_name}'")
    print(f"  Train delta_worst:  {train_best_train_dw:+.3f}")
    print(f"  Test  delta_worst:  {train_best_test_dw:+.3f}")
    print(f"  In-sample -> OOS decay: {decay:+.3f} ({decay_pct:+.0f}% of train)")

    if train_best_test_dw > 0.4:
        holdout_verdict = (f"PASS: train-selected '{train_best_name}' delivers "
                           f"{train_best_test_dw:+.3f} on holdout (>+0.4); selection bias contained, "
                           f"vendor investment justified.")
    elif train_best_test_dw > 0.2:
        holdout_verdict = (f"PARTIAL: '{train_best_name}' delivers {train_best_test_dw:+.3f} on holdout "
                           f"(between +0.2 and +0.4); signal real but selection bias substantial; "
                           f"vendor investment marginal.")
    elif train_best_test_dw > 0.0:
        holdout_verdict = (f"WEAK: '{train_best_name}' delivers only {train_best_test_dw:+.3f} on holdout; "
                           f"strong selection bias; vendor investment NOT justified by spike alone.")
    else:
        holdout_verdict = (f"FAIL: '{train_best_name}' is NEGATIVE on holdout ({train_best_test_dw:+.3f}); "
                           f"pure selection bias; redirect to event-tape (unlock-only).")

    print(f"\n=== Holdout verdict: {holdout_verdict}")

    out = {
        "as_of": args.as_of,
        "panel_path": str(args.panel),
        "panel_btc_rows": int(len(btc)),
        "dvol_observations": int(len(dvol_raw)),
        "dvol_date_range": [str(dvol_raw["date_utc"].min().date()), str(dvol_raw["date_utc"].max().date())],
        "v91_columns_available": available_cols,
        "v91_columns_missing": missing_cols,
        "leadlag_dvol_z90_btc_forward_return": leadlag_btc,
        "leadlag_dvol_change_5d_z90_btc_forward_return": leadlag_chg,
        "regime_split": regime,
        "regime_z_threshold": float(args.regime_z_threshold),
        "top_k": int(args.top_k),
        "portfolio_observations": int(len(port)),
        "baseline_full_sharpe": base_full,
        "baseline_worst_quarter_sharpe": base_worst,
        "baseline_quarterly_sharpe": base_quarterly,
        "multiplier_comparison": multiplier_results,
        "best_multiplier_name": best_name,
        "best_multiplier_delta_worst_quarter_sharpe": best_delta_worst,
        "verdict": verdict,
        "holdout": {
            "train_fraction": train_fraction,
            "n_train": n_train,
            "n_test": n_total - n_train,
            "train_date_range": [str(train_first.date()), str(train_last.date())],
            "test_date_range": [
                str(split_date.date()) if split_date is not None else None,
                str(test_last.date()) if test_last is not None else None,
            ],
            "train_baseline_worst": train_base_worst,
            "test_baseline_worst": test_base_worst,
            "results": holdout_results,
            "train_best_multiplier": train_best_name,
            "train_best_train_delta_worst": train_best_train_dw,
            "train_best_test_delta_worst": train_best_test_dw,
            "decay": decay,
            "verdict": holdout_verdict,
        },
        "caveat": "daily 5d-overlapping observations; sharpe annualized via sqrt(252/5); production verification requires v92-overlay manifest + hypothesis_batch_cycle",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"btc_options_spike_{args.as_of}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
        f.write("\n")
    print(f"\n=== Output written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
