"""compute_correlation_dvol_overlay_diagnostic.py — SP-E + SP-G overlay
diagnostic.

Two doc-anchored regime-gate candidates feed regime_gating_v3:

  SP-E (doc §E.17): BTC-ETH 30d realized correlation regime switch.
    Falsification: cross-section IC in low-correlation regime (corr < 0.5)
    not 1.2× baseline → reject as gate.

  SP-G: DVOL OHLC extensions.
    G1 dvol_intraday_range_z90 = (dvol_high - dvol_low) / dvol_close, z90.
    G2 dvol_cross_pair_ratio = btc_dvol_close / eth_dvol_close, divergence
       from rolling-30d median.
    Diagnostic only (no doc test) — overlay-layer enrichment.

Outputs:
  artifacts/quant_research/factor_reports/<as-of>/correlation_dvol_overlay_diagnostic.json

Key thresholds:
  SP-E low-corr threshold        = 0.5
  SP-E high-corr threshold       = 0.7
  SP-E doc §E.17 falsification   = mean_ic_low_corr / mean_ic_high_corr ≥ 1.2
  SP-G dvol_range_z anomaly      = z > 2.0
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
    per_timestamp_rank_ic,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_overlay_diagnostic_correlation_dvol.v1"

# SP-E thresholds
CORR_WINDOW_DAYS = 30
LOW_CORR_THRESHOLD = 0.5
HIGH_CORR_THRESHOLD = 0.7
E17_IC_RATIO_FLOOR = 1.2

# SP-G thresholds
DVOL_RANGE_Z_WINDOW_DAYS = 90
DVOL_RATIO_MEDIAN_WINDOW_DAYS = 30

# DVOL CSV paths
BTC_DVOL_PATH = ROOT / "artifacts" / "external_market_data" / "deribit_dvol" / "btc_dvol_daily.csv"
ETH_DVOL_PATH = ROOT / "artifacts" / "external_market_data" / "deribit_dvol" / "eth_dvol_daily.csv"

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


def _ts_to_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date().isoformat()


# ====================================================================
# SP-E: BTC-ETH 30d realized correlation
# ====================================================================


def build_btc_eth_realized_corr(features: pd.DataFrame) -> pd.DataFrame:
    """Returns DataFrame indexed by timestamp_ms with column btc_eth_corr_30d."""
    btc = features[features["subject"] == "BTC"][["timestamp_ms", "return_1"]].sort_values("timestamp_ms")
    eth = features[features["subject"] == "ETH"][["timestamp_ms", "return_1"]].sort_values("timestamp_ms")
    if btc.empty or eth.empty:
        return pd.DataFrame()
    merged = btc.merge(eth, on="timestamp_ms", suffixes=("_btc", "_eth"), how="inner")
    merged = merged.set_index("timestamp_ms").sort_index()
    merged["btc_eth_corr_30d"] = (
        merged["return_1_btc"]
        .rolling(CORR_WINDOW_DAYS, min_periods=15)
        .corr(merged["return_1_eth"])
    )
    return merged[["btc_eth_corr_30d"]].reset_index()


def lsk3_score_per_row(frame: pd.DataFrame) -> pd.Series:
    """Compute the canonical lsk3 11-factor signed-z score per row.

    Uses the same coefficient pattern as xs_alpha_ontology_v1_score: each
    factor z-scored cross-sectionally then weighted, then summed.
    Output is a per-row score (NOT tanh-mapped — we want raw IC).
    """
    weights = {
        "intraday_realized_vol_4h_to_1d_smooth_60": -0.20,
        "realized_volatility_5": -0.10,
        "distance_to_high_60": +0.18,
        "distance_to_high_5": +0.15,
        "coinglass_top_trader_long_pct_smooth_5": -0.07,
        "liquidity_stress_qv_iv": -0.10,
        "momentum_decay_5_20": -0.06,
        "coinglass_taker_imb_intraday_dispersion_24h": +0.05,
        "quality_funding_oi": -0.05,
        "downside_upside_vol_ratio_30": +0.10,
        "funding_basis_residual_implied_repo_30": +0.07,
    }
    score = pd.Series(0.0, index=frame.index, dtype="float64")
    ts = frame["timestamp_ms"]
    for col, w in weights.items():
        if col not in frame.columns:
            continue
        x = pd.to_numeric(frame[col], errors="coerce")
        # Cross-sectional z per timestamp
        gmean = x.groupby(ts).transform("mean")
        gstd = x.groupby(ts).transform("std").replace(0.0, np.nan)
        zx = (x - gmean) / gstd
        score = score + w * zx.fillna(0.0)
    return score


def _build_h10d_target(features: pd.DataFrame) -> pd.Series:
    """Per-(subject, timestamp_ms) forward log return at 10d horizon."""
    out = pd.Series(np.nan, index=features.index, dtype="float64")
    for _, sub in features.groupby("subject"):
        sub = sub.sort_values("timestamp_ms")
        log_ret = np.log(sub["spot_close"].shift(-10) / sub["spot_close"])
        out.loc[sub.index] = log_ret
    return out


def e17_falsification(features: pd.DataFrame, corr_df: pd.DataFrame) -> dict:
    """Compute mean per-timestamp rank IC of lsk3 score, partitioned by
    btc_eth_corr_30d regime. Doc §E.17 PASS if IC_low_corr / IC_high_corr ≥ 1.2.

    Tests at BOTH h5d (panel target_forward_return) and h10d (computed),
    with BOTH absolute-threshold split (0.5 / 0.7) and TERTILE split for
    statistical power.
    """
    score = lsk3_score_per_row(features)
    ts = features["timestamp_ms"]

    targets = {
        "h5d": pd.to_numeric(features["target_forward_return"], errors="coerce"),
        "h10d": _build_h10d_target(features),
    }
    corr_indexed = corr_df.set_index("timestamp_ms")["btc_eth_corr_30d"]

    def _stats(g: pd.DataFrame) -> dict:
        if g.empty:
            return {"n": 0, "mean": float("nan"), "median": float("nan"), "abs_mean": float("nan")}
        return {
            "n": int(len(g)),
            "mean": float(g["ic"].mean()),
            "median": float(g["ic"].median()),
            "abs_mean": float(g["ic"].abs().mean()),
        }

    horizon_results = {}
    for horizon, target in targets.items():
        ic = per_timestamp_rank_ic(score, target, ts).dropna()
        aligned_corr = corr_indexed.reindex(ic.index)
        df = pd.DataFrame({"ic": ic, "corr": aligned_corr}).dropna()
        if df.empty:
            horizon_results[horizon] = {"status": "no_overlap"}
            continue

        # === Absolute-threshold split (per roadmap) ===
        low_abs = df[df["corr"] < LOW_CORR_THRESHOLD]
        high_abs = df[df["corr"] >= HIGH_CORR_THRESHOLD]
        mid_abs = df[(df["corr"] >= LOW_CORR_THRESHOLD) & (df["corr"] < HIGH_CORR_THRESHOLD)]
        low_stats_abs = _stats(low_abs)
        high_stats_abs = _stats(high_abs)
        mid_stats_abs = _stats(mid_abs)
        overall_stats = _stats(df)
        ratio_abs = (
            low_stats_abs["abs_mean"] / high_stats_abs["abs_mean"]
            if (high_stats_abs["n"] > 0 and high_stats_abs["abs_mean"] > 0 and not np.isnan(high_stats_abs["abs_mean"]))
            else float("nan")
        )

        # === Tertile split (for statistical power; n_tertile ≈ 1103/3 ≈ 370) ===
        df_sorted = df.sort_values("corr").reset_index(drop=True)
        n_total = len(df_sorted)
        t1_end = n_total // 3
        t2_end = 2 * n_total // 3
        bottom = df_sorted.iloc[:t1_end]
        middle = df_sorted.iloc[t1_end:t2_end]
        top = df_sorted.iloc[t2_end:]
        tertile_corr_breaks = {
            "low_max_corr": float(bottom["corr"].max()) if len(bottom) > 0 else float("nan"),
            "mid_min_corr": float(middle["corr"].min()) if len(middle) > 0 else float("nan"),
            "mid_max_corr": float(middle["corr"].max()) if len(middle) > 0 else float("nan"),
            "high_min_corr": float(top["corr"].min()) if len(top) > 0 else float("nan"),
        }
        bottom_stats = _stats(bottom)
        middle_stats = _stats(middle)
        top_stats = _stats(top)
        ratio_tert = (
            bottom_stats["abs_mean"] / top_stats["abs_mean"]
            if (top_stats["n"] > 0 and top_stats["abs_mean"] > 0 and not np.isnan(top_stats["abs_mean"]))
            else float("nan")
        )

        passes_abs = (
            not np.isnan(ratio_abs) and ratio_abs >= E17_IC_RATIO_FLOOR
        )
        passes_tert = (
            not np.isnan(ratio_tert) and ratio_tert >= E17_IC_RATIO_FLOOR
        )

        horizon_results[horizon] = {
            "status": "ok",
            "n_total_timestamps": int(len(df)),
            "abs_threshold_split": {
                "low_corr_threshold": LOW_CORR_THRESHOLD,
                "high_corr_threshold": HIGH_CORR_THRESHOLD,
                "low_corr_regime": low_stats_abs,
                "mid_corr_regime": mid_stats_abs,
                "high_corr_regime": high_stats_abs,
                "abs_ic_ratio_low_over_high": ratio_abs,
                "doc_e17_passes": passes_abs,
            },
            "tertile_split": {
                "tertile_corr_breaks": tertile_corr_breaks,
                "bottom_tertile_low_corr": bottom_stats,
                "middle_tertile_mid_corr": middle_stats,
                "top_tertile_high_corr": top_stats,
                "abs_ic_ratio_bottom_over_top": ratio_tert,
                "doc_e17_passes_tertile": passes_tert,
            },
            "overall": overall_stats,
        }

    return {
        "corr_window_days": CORR_WINDOW_DAYS,
        "doc_e17_threshold_ratio": E17_IC_RATIO_FLOOR,
        "by_horizon": horizon_results,
    }


# ====================================================================
# SP-G: DVOL OHLC extensions
# ====================================================================


def build_dvol_features() -> pd.DataFrame:
    """Returns DataFrame indexed by date_utc with columns:
    btc_dvol_close, btc_dvol_high, btc_dvol_low,
    eth_dvol_close, eth_dvol_high, eth_dvol_low,
    btc_dvol_range_z90, eth_dvol_range_z90,
    btc_dvol_eth_dvol_ratio, btc_dvol_eth_dvol_ratio_z30
    """
    btc = pd.read_csv(BTC_DVOL_PATH)
    eth = pd.read_csv(ETH_DVOL_PATH)
    btc = btc[["date_utc", "dvol_close", "dvol_high", "dvol_low"]].rename(
        columns={"dvol_close": "btc_dvol_close", "dvol_high": "btc_dvol_high", "dvol_low": "btc_dvol_low"}
    )
    eth = eth[["date_utc", "dvol_close", "dvol_high", "dvol_low"]].rename(
        columns={"dvol_close": "eth_dvol_close", "dvol_high": "eth_dvol_high", "dvol_low": "eth_dvol_low"}
    )
    df = btc.merge(eth, on="date_utc", how="inner").sort_values("date_utc").reset_index(drop=True)

    # G1: per-currency intraday range / close, z90
    for prefix in ("btc", "eth"):
        rng = (df[f"{prefix}_dvol_high"] - df[f"{prefix}_dvol_low"]) / df[f"{prefix}_dvol_close"]
        df[f"{prefix}_dvol_intraday_range"] = rng
        rolling_mean = rng.rolling(DVOL_RANGE_Z_WINDOW_DAYS, min_periods=20).mean()
        rolling_std = rng.rolling(DVOL_RANGE_Z_WINDOW_DAYS, min_periods=20).std()
        df[f"{prefix}_dvol_range_z90"] = (rng - rolling_mean) / rolling_std.replace(0.0, np.nan)

    # G3: BTC/ETH DVOL cross-pair ratio + 30d median deviation
    df["btc_dvol_eth_dvol_ratio"] = df["btc_dvol_close"] / df["eth_dvol_close"].replace(0.0, np.nan)
    median = df["btc_dvol_eth_dvol_ratio"].rolling(DVOL_RATIO_MEDIAN_WINDOW_DAYS, min_periods=10).median()
    df["btc_dvol_eth_dvol_ratio_dev"] = df["btc_dvol_eth_dvol_ratio"] - median

    return df


def dvol_regime_diagnostic(dvol_df: pd.DataFrame) -> dict:
    """Diagnostic stats: how often does each DVOL regime fire? What does the
    distribution look like?"""
    if dvol_df.empty:
        return {"status": "no_data"}
    n = int(len(dvol_df))

    def _stats(col: str, anomaly_thresh: float | None = None) -> dict:
        s = pd.to_numeric(dvol_df[col], errors="coerce").dropna()
        if s.empty:
            return {"n": 0}
        out = {
            "n": int(len(s)),
            "mean": float(s.mean()),
            "std": float(s.std()),
            "p10": float(s.quantile(0.1)),
            "p50": float(s.quantile(0.5)),
            "p90": float(s.quantile(0.9)),
            "p95": float(s.quantile(0.95)),
        }
        if anomaly_thresh is not None:
            out["fraction_above_thresh"] = float((s > anomaly_thresh).mean())
            out["thresh"] = anomaly_thresh
        return out

    return {
        "status": "ok",
        "n_dvol_days": n,
        "dvol_range_z_window_days": DVOL_RANGE_Z_WINDOW_DAYS,
        "dvol_ratio_median_window_days": DVOL_RATIO_MEDIAN_WINDOW_DAYS,
        "btc_dvol_range_z90": _stats("btc_dvol_range_z90", anomaly_thresh=2.0),
        "eth_dvol_range_z90": _stats("eth_dvol_range_z90", anomaly_thresh=2.0),
        "btc_dvol_eth_dvol_ratio": _stats("btc_dvol_eth_dvol_ratio"),
        "btc_dvol_eth_dvol_ratio_dev": _stats("btc_dvol_eth_dvol_ratio_dev"),
    }


# ====================================================================
# Main
# ====================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-E + SP-G overlay diagnostic.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--features",
        type=Path,
        default=DEFAULT_FEATURES_ARTIFACT,
        help="Path to features.csv.gz panel.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== SP-E+G: loading panel from {args.features}")
    raw_panel = pd.read_csv(args.features, compression="gzip")
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 columns to materialize lsk3 baseline...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    print()

    print("=== SP-E: building BTC-ETH 30d realized correlation ===")
    corr_df = build_btc_eth_realized_corr(panel)
    print(f"  corr rows: {len(corr_df)}")
    if not corr_df.empty:
        s = corr_df["btc_eth_corr_30d"].dropna()
        print(f"  corr stats: mean={s.mean():.3f} median={s.median():.3f} "
              f"p10={s.quantile(0.1):.3f} p90={s.quantile(0.9):.3f}")
        print(f"  fraction in low-corr regime (<{LOW_CORR_THRESHOLD}): {(s<LOW_CORR_THRESHOLD).mean():.3f}")
        print(f"  fraction in high-corr regime (>={HIGH_CORR_THRESHOLD}): {(s>=HIGH_CORR_THRESHOLD).mean():.3f}")
    print()

    print("=== Doc §E.17 falsification: lsk3 IC ratio low-corr / high-corr ===")
    e17 = e17_falsification(panel, corr_df)
    print(json.dumps(e17, indent=2, sort_keys=True))
    print()

    print("=== SP-G: building DVOL OHLC features ===")
    dvol_df = build_dvol_features()
    print(f"  DVOL rows: {len(dvol_df)}")
    print()

    print("=== SP-G regime diagnostic ===")
    spg = dvol_regime_diagnostic(dvol_df)
    print(json.dumps(spg, indent=2, sort_keys=True))
    print()

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(args.features),
        "thresholds": {
            "corr_window_days": CORR_WINDOW_DAYS,
            "low_corr_threshold": LOW_CORR_THRESHOLD,
            "high_corr_threshold": HIGH_CORR_THRESHOLD,
            "doc_e17_ic_ratio_floor": E17_IC_RATIO_FLOOR,
            "dvol_range_z_window_days": DVOL_RANGE_Z_WINDOW_DAYS,
            "dvol_ratio_median_window_days": DVOL_RATIO_MEDIAN_WINDOW_DAYS,
        },
        "sp_e_e17_falsification": e17,
        "sp_g_dvol_diagnostic": spg,
        "lsk3_baseline": list(LSK3_BASELINE),
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "correlation_dvol_overlay_diagnostic.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Done. Card at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
