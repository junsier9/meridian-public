"""compute_basis_propagation_factor_report.py — SP-D admission + doc §E.16
falsification audit.

Doc §E.16: BTC basis shock → ALT basis impulse-response in 12-48h via
mechanical arbitrage capital reallocation. Falsification: BTC basis shock
followed by ALT basis 1d-after t-stat < 2 → REJECT.

Three factor candidates:
  D1 — btc_basis_shock_lag1_z60   (universe-wide gauge — broadcast)
  D2 — alt_basis_residual_after_btc_60d  (per-asset, primary candidate)
  D3 — basis_propagation_lag_corr_30d    (per-asset, quality measure)

Note: D1 is universe-wide constant within a date and will trivially fail
G1 (no cross-sectional variation). It is reported for diagnostic /
gating-layer use, NOT as a primary score factor. D2 / D3 are the
admission candidates.

The script tests at BOTH h5d and h10d horizons because SP-C Phase 1
audit found all score-integrated factors peak at h10d. h5d uses the
panel's existing `target_forward_return`; h10d is computed from
`spot_close` per-subject.

Output: artifacts/quant_research/factor_reports/<as-of>/basis_propagation_factor_report_card.json
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
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_basis_propagation.v1"
G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02
DOC_E16_T_STAT_THRESHOLD = 2.0  # doc §E.16 falsification

# BTC basis shock z-score threshold and rolling window
BTC_BASIS_Z_WINDOW = 60
BTC_BASIS_Z_SHOCK_THRESHOLD = 2.0

# Per-asset rolling β window (D2)
ALT_RESIDUAL_BETA_WINDOW = 60

# Per-asset lag-correlation window (D3)
LAG_CORR_WINDOW = 30

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

DEFAULT_FEATURES_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)


# ====================================================================
# Step 1: Build BTC basis_proxy series + z-score
# ====================================================================


def build_btc_basis_z(panel: pd.DataFrame) -> pd.DataFrame:
    """Returns DataFrame with columns [timestamp_ms, btc_basis, btc_basis_z60].

    Rolling 60d z-score of BTC basis_proxy.
    """
    btc = (
        panel[panel["subject"] == "BTC"][["timestamp_ms", "basis_proxy"]]
        .sort_values("timestamp_ms")
        .drop_duplicates("timestamp_ms")
        .reset_index(drop=True)
    )
    btc = btc.rename(columns={"basis_proxy": "btc_basis"})
    rolling_mean = btc["btc_basis"].rolling(BTC_BASIS_Z_WINDOW, min_periods=20).mean()
    rolling_std = btc["btc_basis"].rolling(BTC_BASIS_Z_WINDOW, min_periods=20).std()
    btc["btc_basis_z60"] = (btc["btc_basis"] - rolling_mean) / rolling_std.replace(0.0, np.nan)
    return btc


# ====================================================================
# Step 2: Doc §E.16 falsification — pooled abnormal ALT basis change
# 1-day after BTC basis shock event, sign-aligned with BTC shock direction
# ====================================================================


def doc_e16_falsification(panel: pd.DataFrame, btc_basis: pd.DataFrame) -> dict:
    """Pool 1d-after ALT basis changes around BTC basis shock events,
    sign-aligned. t-test against zero. doc §E.16 says t < 2 → REJECT.
    """
    shocks = btc_basis[btc_basis["btc_basis_z60"].abs() > BTC_BASIS_Z_SHOCK_THRESHOLD][
        ["timestamp_ms", "btc_basis_z60"]
    ].copy()
    shocks["sign"] = np.sign(shocks["btc_basis_z60"])
    shock_ts = set(shocks["timestamp_ms"])

    # For each ALT, build sorted (date, basis) and compute basis[d+1] - basis[d]
    aligned_pool: list[float] = []
    nonevent_pool: list[float] = []
    per_subject_n: dict[str, int] = {}

    for subject, sub in panel[panel["subject"] != "BTC"].groupby("subject"):
        sub = sub[["timestamp_ms", "basis_proxy"]].sort_values("timestamp_ms").reset_index(drop=True)
        if len(sub) < 100:
            continue
        sub["delta_1d"] = sub["basis_proxy"].diff(1).shift(-1)  # basis[t+1] - basis[t]
        sub = sub.dropna(subset=["delta_1d"])
        # Tag event vs non-event
        sub["is_event"] = sub["timestamp_ms"].isin(shock_ts)
        events = sub[sub["is_event"]].merge(
            shocks[["timestamp_ms", "sign"]], on="timestamp_ms", how="left"
        )
        if events.empty:
            continue
        # aligned delta = delta_1d × sign(BTC shock)
        aligned_pool.extend((events["delta_1d"] * events["sign"]).tolist())
        nonevent_pool.extend(sub.loc[~sub["is_event"], "delta_1d"].tolist())
        per_subject_n[subject] = int(len(events))

    if not aligned_pool:
        return {"status": "no_events", "n_events": 0}

    arr = np.asarray(aligned_pool, dtype="float64")
    nonevent_arr = np.asarray(nonevent_pool, dtype="float64") if nonevent_pool else np.array([0.0])
    nonevent_mean = float(nonevent_arr.mean()) if len(nonevent_arr) else 0.0
    centered = arr - nonevent_mean
    mean_ar = float(centered.mean())
    std_ar = float(centered.std())
    n_events = len(centered)
    t_stat = float(mean_ar * np.sqrt(n_events) / std_ar) if std_ar > 0 else 0.0
    return {
        "status": "ok",
        "n_events": n_events,
        "n_subjects_with_events": int(len(per_subject_n)),
        "n_unique_shock_dates": int(len(shocks)),
        "btc_basis_z_shock_threshold": BTC_BASIS_Z_SHOCK_THRESHOLD,
        "btc_basis_z_window_days": BTC_BASIS_Z_WINDOW,
        "nonevent_mean_baseline": nonevent_mean,
        "mean_aligned_delta_1d": mean_ar,
        "std_aligned_delta_1d": std_ar,
        "t_stat": t_stat,
        "doc_threshold_2_sigma": DOC_E16_T_STAT_THRESHOLD,
        "doc_e16_passes": abs(t_stat) >= DOC_E16_T_STAT_THRESHOLD,
        "per_subject_event_counts": per_subject_n,
    }


# ====================================================================
# Step 3: Build D1 / D2 / D3 factors
# ====================================================================


def build_d1_btc_shock_broadcast(panel: pd.DataFrame, btc_basis: pd.DataFrame) -> pd.DataFrame:
    """D1: BTC basis_proxy z60 lagged by 1 day, broadcast to every subject.

    Universe-wide → trivially zero cross-sectional variance per timestamp →
    will fail G1 by construction. Reported for diagnostic / gating use.
    """
    btc_lag = btc_basis[["timestamp_ms", "btc_basis_z60"]].copy()
    btc_lag["btc_basis_shock_lag1_z60"] = btc_lag["btc_basis_z60"].shift(1)
    btc_lag = btc_lag.drop(columns=["btc_basis_z60"])
    return panel[["subject", "timestamp_ms"]].merge(btc_lag, on="timestamp_ms", how="left")


def build_d2_alt_residual(panel: pd.DataFrame, btc_basis: pd.DataFrame) -> pd.DataFrame:
    """D2: per-asset basis residual after rolling 60d β projection on BTC basis.

    For each (subject, t):
      window = trailing 60d of (alt_basis, btc_basis) at SAME dates
      α, β = OLS fit
      residual = alt_basis[t] - α - β × btc_basis[t]

    Cross-sectional dispersion is preserved.
    """
    btc_only = btc_basis[["timestamp_ms", "btc_basis"]].copy()
    rows: list[tuple[str, int, float]] = []
    for subject, sub in panel[panel["subject"] != "BTC"].groupby("subject"):
        sub = (
            sub[["timestamp_ms", "basis_proxy"]]
            .sort_values("timestamp_ms")
            .drop_duplicates("timestamp_ms")
            .merge(btc_only, on="timestamp_ms", how="inner")
        )
        if len(sub) < ALT_RESIDUAL_BETA_WINDOW + 5:
            continue
        sub = sub.dropna(subset=["basis_proxy", "btc_basis"]).reset_index(drop=True)
        # rolling 60d OLS β + α; predict at current row
        bp = sub["basis_proxy"].to_numpy(dtype="float64")
        bb = sub["btc_basis"].to_numpy(dtype="float64")
        n = len(sub)
        residual = np.full(n, np.nan)
        for i in range(ALT_RESIDUAL_BETA_WINDOW, n):
            x = bb[i - ALT_RESIDUAL_BETA_WINDOW : i]
            y = bp[i - ALT_RESIDUAL_BETA_WINDOW : i]
            x_mean = x.mean()
            y_mean = y.mean()
            x_dev = x - x_mean
            y_dev = y - y_mean
            denom = float((x_dev * x_dev).sum())
            if denom <= 0.0:
                continue
            beta = float((x_dev * y_dev).sum() / denom)
            alpha = y_mean - beta * x_mean
            residual[i] = bp[i] - alpha - beta * bb[i]
        for ts, r in zip(sub["timestamp_ms"].tolist(), residual.tolist()):
            if not np.isnan(r):
                rows.append((subject, int(ts), float(r)))

    return pd.DataFrame(rows, columns=["subject", "timestamp_ms", "alt_basis_residual_after_btc_60d"])


def build_d3_lag_corr(panel: pd.DataFrame, btc_basis: pd.DataFrame) -> pd.DataFrame:
    """D3: per-asset rolling 30d corr(alt_basis[t], btc_basis[t-1]).

    High correlation = mechanical follower of BTC basis with 1d lag.
    """
    btc_only = btc_basis[["timestamp_ms", "btc_basis"]].copy()
    btc_only = btc_only.sort_values("timestamp_ms").reset_index(drop=True)
    btc_only["btc_basis_lag1"] = btc_only["btc_basis"].shift(1)
    btc_only = btc_only.drop(columns=["btc_basis"])

    rows: list[tuple[str, int, float]] = []
    for subject, sub in panel[panel["subject"] != "BTC"].groupby("subject"):
        sub = (
            sub[["timestamp_ms", "basis_proxy"]]
            .sort_values("timestamp_ms")
            .drop_duplicates("timestamp_ms")
            .merge(btc_only, on="timestamp_ms", how="inner")
        )
        if len(sub) < LAG_CORR_WINDOW + 5:
            continue
        sub = sub.dropna(subset=["basis_proxy", "btc_basis_lag1"]).reset_index(drop=True)
        bp = sub["basis_proxy"]
        bb_lag = sub["btc_basis_lag1"]
        rolling_corr = bp.rolling(LAG_CORR_WINDOW, min_periods=15).corr(bb_lag)
        for ts, r in zip(sub["timestamp_ms"].tolist(), rolling_corr.tolist()):
            if pd.notna(r):
                rows.append((subject, int(ts), float(r)))

    return pd.DataFrame(rows, columns=["subject", "timestamp_ms", "basis_propagation_lag_corr_30d"])


# ====================================================================
# Step 4: Forward-return targets at h5d and h10d
# ====================================================================


def build_horizon_target(panel: pd.DataFrame, horizon_bars: int) -> pd.Series:
    """Compute per-(subject, timestamp_ms) forward log return at horizon_bars.

    Returns Series indexed by panel.index (aligned to panel rows).
    """
    out = pd.Series(np.nan, index=panel.index, dtype="float64")
    for subject, sub in panel.groupby("subject"):
        sub = sub.sort_values("timestamp_ms")
        log_ret = np.log(sub["spot_close"].shift(-horizon_bars) / sub["spot_close"])
        out.loc[sub.index] = log_ret
    return out


# ====================================================================
# Step 5: G1 / G3 / G6 admission audit
# ====================================================================


def audit_factor(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    baseline: pd.DataFrame,
    regime_label: pd.Series,
) -> dict:
    """Return G1 / G3 / G6 verdict for one factor."""
    factor_clean = pd.to_numeric(factor, errors="coerce").fillna(0.0)
    target_clean = pd.to_numeric(target, errors="coerce")
    ic = per_timestamp_rank_ic(factor_clean, target_clean, timestamps).dropna()
    n = int(len(ic))
    if n < 30:
        return {"status": "insufficient", "n_ts": n}
    m = float(ic.mean())
    s = float(ic.std())
    t = float(m * (n ** 0.5) / s) if s > 0 else 0.0

    aligned = regime_label.reindex(ic.index)
    df_g3 = pd.DataFrame({"ic": ic, "regime": aligned}).dropna()
    regime_ic = {str(r): float(g["ic"].mean()) for r, g in df_g3.groupby("regime") if len(g) >= 20}
    signs = [1 if v > 0 else -1 if v < 0 else 0 for v in regime_ic.values()]
    same_sign = max(signs.count(1), signs.count(-1)) / len(signs) if signs else 0

    residual = orthogonalize(factor_clean, baseline)
    rs = per_timestamp_rank_ic(residual, target_clean, timestamps).dropna()
    rm = float(rs.mean()) if len(rs) > 0 else 0.0
    rstd = float(rs.std()) if len(rs) > 1 else 0.0
    rt = float(rm * (len(rs) ** 0.5) / rstd) if rstd > 0 else 0.0

    return {
        "n_ts": n,
        "g1": {
            "ic_mean": m,
            "ic_std": s,
            "t_stat": t,
            "abs_ic": abs(m),
            "abs_pass": abs(m) >= G1_ABS_MIN,
        },
        "g3": {
            "regime_ic": regime_ic,
            "same_sign_fraction": same_sign,
            "pass": same_sign >= G3_SAME_SIGN_MIN,
        },
        "g6_vs_lsk3": {
            "residual_ic_mean": rm,
            "residual_t_stat": rt,
            "abs_residual_ic": abs(rm),
            "abs_pass": abs(rm) >= G6_ABS_MIN,
        },
    }


def cross_sectional_admission_audit(
    panel: pd.DataFrame,
    d1: pd.DataFrame,
    d2: pd.DataFrame,
    d3: pd.DataFrame,
) -> dict:
    """Run G1 / G3 / G6 at h5d (panel target_forward_return) and h10d
    (computed from spot_close).
    """
    merged = (
        panel.merge(d1, on=["subject", "timestamp_ms"], how="left")
        .merge(d2, on=["subject", "timestamp_ms"], how="left")
        .merge(d3, on=["subject", "timestamp_ms"], how="left")
    )
    ts = merged["timestamp_ms"]
    baseline = merged[list(LSK3_BASELINE)].apply(pd.to_numeric, errors="coerce")
    regime_label = build_regime_by_ts(merged)

    target_h5d = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    target_h10d = build_horizon_target(merged, horizon_bars=10)

    factor_cols = [
        "btc_basis_shock_lag1_z60",
        "alt_basis_residual_after_btc_60d",
        "basis_propagation_lag_corr_30d",
    ]

    cards: dict[str, dict] = {}
    for col in factor_cols:
        if col not in merged.columns:
            cards[col] = {"status": "missing"}
            continue
        cards[col] = {
            "h5d": audit_factor(merged[col], target_h5d, ts, baseline, regime_label),
            "h10d": audit_factor(merged[col], target_h10d, ts, baseline, regime_label),
        }
    return cards


# ====================================================================
# Main
# ====================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-D basis propagation factor report card.")
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

    print(f"=== SP-D: loading panel from {args.features}")
    raw_panel = pd.read_csv(args.features, compression="gzip")
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 columns to materialize lsk3 baseline (downside_upside_vol_ratio_30 etc.)...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    print()

    print("=== SP-D: building BTC basis z-score ===")
    btc_basis = build_btc_basis_z(panel)
    print(f"  BTC basis rows: {len(btc_basis)}")
    n_shock = int((btc_basis["btc_basis_z60"].abs() > BTC_BASIS_Z_SHOCK_THRESHOLD).sum())
    print(f"  BTC shock days (|z|>{BTC_BASIS_Z_SHOCK_THRESHOLD}): {n_shock}")
    print()

    print("=== Doc §E.16 falsification ===")
    e16_result = doc_e16_falsification(panel, btc_basis)
    e16_print = {k: v for k, v in e16_result.items() if k != "per_subject_event_counts"}
    print(json.dumps(e16_print, indent=2, sort_keys=True))
    print()

    print("=== Building D1 / D2 / D3 factors ===")
    d1 = build_d1_btc_shock_broadcast(panel, btc_basis)
    d2 = build_d2_alt_residual(panel, btc_basis)
    d3 = build_d3_lag_corr(panel, btc_basis)
    print(f"  D1 rows: {len(d1)}, D2 rows: {len(d2)}, D3 rows: {len(d3)}")
    print()

    print("=== Cross-sectional G1+G3+G6 admission audit (h5d + h10d) ===")
    cs_cards = cross_sectional_admission_audit(panel, d1, d2, d3)
    for fid, card in cs_cards.items():
        if "status" in card:
            print(f"  {fid}: {card['status']}")
            continue
        for horizon in ("h5d", "h10d"):
            h = card[horizon]
            if "status" in h:
                print(f"  {fid:42s} [{horizon}] {h['status']} (n={h.get('n_ts','?')})")
                continue
            g1 = h["g1"]
            g3 = h["g3"]
            g6 = h["g6_vs_lsk3"]
            print(
                f"  {fid:42s} [{horizon}]  G1 ic={g1['ic_mean']:+.4f} t={g1['t_stat']:+.2f} "
                f"(n={h['n_ts']})  G3 same={g3['same_sign_fraction']:.2f}  "
                f"G6 resid={g6['residual_ic_mean']:+.4f} t={g6['residual_t_stat']:+.2f} "
                f"pass={g6['abs_pass']}"
            )
    print()

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(args.features),
        "thresholds": {
            "g1_abs_min": G1_ABS_MIN,
            "g3_same_sign_min": G3_SAME_SIGN_MIN,
            "g6_abs_min": G6_ABS_MIN,
            "doc_e16_t_stat": DOC_E16_T_STAT_THRESHOLD,
            "btc_basis_z_window_days": BTC_BASIS_Z_WINDOW,
            "btc_basis_z_shock_threshold": BTC_BASIS_Z_SHOCK_THRESHOLD,
            "alt_residual_beta_window_days": ALT_RESIDUAL_BETA_WINDOW,
            "lag_corr_window_days": LAG_CORR_WINDOW,
        },
        "doc_e16_falsification": e16_result,
        "cross_sectional_admission": cs_cards,
        "lsk3_baseline": list(LSK3_BASELINE),
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "basis_propagation_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Done. Card at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
