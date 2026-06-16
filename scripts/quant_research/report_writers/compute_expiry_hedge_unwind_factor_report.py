"""compute_expiry_hedge_unwind_factor_report.py — SP-H admission +
doc §E.15 falsification audit.

Doc §E.15: BTC/ETH monthly options expiry calendar is public knowledge;
gamma window 3-5 days before expiry creates dealer hedge unwind pressure.
Don't need OI by strike for the event-study version — just the calendar.

Doc §E.15 falsification: KS-test of expiry-window 5d return distribution
vs normal 5d distribution, p > 0.05 → reject mechanism.

Three factor candidates:
  H1 — time_to_btc_expiry (days until next BTC monthly expiry)
       Universe-wide gauge — constant within timestamp → trivial G1 fail
       in cross-section. Reported for diagnostic / overlay use.

  H2 — expiry_window_indicator_5d (binary: 1 if within 5d of expiry, else 0)
       Universe-wide. Same G1 issue as H1.

  H3 — expiry_window × asset_realized_vol interaction (per-asset)
       Cross-sectional variation: assets respond differently to gamma
       window depending on their realized vol. Tested as score factor.

Admission audit: doc §E.15 KS-test + G1+G3+G6 vs:
  - lsk3 11-factor baseline
  - lsk3 + F-cascade + F08 (current v6_h10d / v9 baseline)

Tests at h5d AND h10d horizons per SP-C h10d-preference finding.

Output: artifacts/quant_research/factor_reports/<as-of>/expiry_hedge_unwind_factor_report_card.json

Roadmap §C SP-H warning: "G6 success probability MEDIUM as overlay
component; UNCLEAR as score factor."
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scistats

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
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_expiry_hedge_unwind.v1"
G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02
DOC_E15_KS_P_THRESHOLD = 0.05  # p > 0.05 → reject

# BTC monthly options expiry: last Friday of each month, 08:00 UTC (Deribit standard)
EXPIRY_WINDOW_DAYS = 5

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
F08_COLUMN = "funding_term_skew_60"
F_CASCADE_COLUMN = "liq_cascade_recency_score_5d"


def last_friday_of_month(year: int, month: int) -> date:
    """Last Friday of (year, month)."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    # Friday weekday() == 4
    days_back = (last_day.weekday() - 4) % 7
    return last_day - timedelta(days=days_back)


def build_btc_monthly_expiry_calendar(start_year: int, end_year: int) -> list[date]:
    """List of last-Friday-of-month dates for BTC monthly options expiry."""
    expiries = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            expiries.append(last_friday_of_month(year, month))
    return expiries


def days_to_next_expiry(d: date, expiries: list[date]) -> int:
    """Days from d to next expiry (inclusive). Returns >= 0; 0 means d == expiry."""
    future_expiries = [e for e in expiries if e >= d]
    if not future_expiries:
        return 999  # sentinel — beyond calendar
    return (future_expiries[0] - d).days


def in_expiry_window(d: date, expiries: list[date], window_days: int) -> bool:
    """True if d is within `window_days` BEFORE next expiry (inclusive)."""
    dte = days_to_next_expiry(d, expiries)
    return 0 <= dte <= window_days


def doc_e15_falsification(panel: pd.DataFrame, expiries: list[date]) -> dict:
    """KS-test: BTC 5d-fwd-log-return distribution in expiry-window vs out.
    p > 0.05 → REJECT mechanism per doc §E.15.

    Tests on BTC subject only (the canonical "BTC monthly expiry" anchor).
    """
    btc = panel[panel["subject"] == "BTC"].sort_values("timestamp_ms").reset_index(drop=True)
    if btc.empty or len(btc) < 30:
        return {"status": "insufficient_btc_history", "n": int(len(btc))}

    # Per-row 5d forward log return on spot_close
    btc["fwd_5d_log_ret"] = np.log(btc["spot_close"].shift(-5) / btc["spot_close"])
    # Date-typed
    btc["date"] = btc["date_utc"].apply(lambda s: date.fromisoformat(s))
    btc["dte"] = btc["date"].apply(lambda d: days_to_next_expiry(d, expiries))
    btc["in_window"] = btc["dte"].between(0, EXPIRY_WINDOW_DAYS)

    in_win = btc[btc["in_window"]].dropna(subset=["fwd_5d_log_ret"])["fwd_5d_log_ret"].values
    out_win = btc[~btc["in_window"]].dropna(subset=["fwd_5d_log_ret"])["fwd_5d_log_ret"].values
    if len(in_win) < 20 or len(out_win) < 20:
        return {
            "status": "insufficient_window_samples",
            "n_in_window": int(len(in_win)),
            "n_out_window": int(len(out_win)),
        }

    ks_stat, ks_p = scistats.ks_2samp(in_win, out_win)
    # Means t-test (informative, not gating)
    mean_in = float(np.mean(in_win))
    mean_out = float(np.mean(out_win))
    std_in = float(np.std(in_win))
    std_out = float(np.std(out_win))
    # Welch's t-test
    t_stat, t_p = scistats.ttest_ind(in_win, out_win, equal_var=False)

    return {
        "status": "ok",
        "n_in_window": int(len(in_win)),
        "n_out_window": int(len(out_win)),
        "expiry_window_days": EXPIRY_WINDOW_DAYS,
        "n_unique_expiries_covered": int(
            len(set(e for e in expiries if btc["date"].min() <= e <= btc["date"].max()))
        ),
        "in_window_mean_5d_log_ret": mean_in,
        "out_window_mean_5d_log_ret": mean_out,
        "in_window_std_5d_log_ret": std_in,
        "out_window_std_5d_log_ret": std_out,
        "ks_statistic": float(ks_stat),
        "ks_p_value": float(ks_p),
        "welch_t_stat": float(t_stat),
        "welch_t_p_value": float(t_p),
        "doc_threshold_ks_p": DOC_E15_KS_P_THRESHOLD,
        "doc_e15_passes": ks_p < DOC_E15_KS_P_THRESHOLD,
    }


def build_h_factors(panel: pd.DataFrame, expiries: list[date]) -> pd.DataFrame:
    """Build H1 / H2 / H3 factors and merge onto panel by (subject, date_utc)."""
    df = panel.copy()
    df["date"] = df["date_utc"].apply(lambda s: date.fromisoformat(s))
    df["time_to_btc_expiry"] = df["date"].apply(
        lambda d: float(days_to_next_expiry(d, expiries))
    )
    df["expiry_window_indicator_5d"] = (
        df["time_to_btc_expiry"].between(0, EXPIRY_WINDOW_DAYS).astype("float64")
    )
    # H3: cross-asset variation — multiply window indicator by asset's
    # realized_volatility_20 (high-vol assets bear more dealer hedge pressure)
    rv20 = pd.to_numeric(df.get("realized_volatility_20"), errors="coerce").fillna(0.0)
    df["expiry_window_x_rv20"] = df["expiry_window_indicator_5d"] * rv20
    return df[
        [
            "subject",
            "timestamp_ms",
            "date_utc",
            "time_to_btc_expiry",
            "expiry_window_indicator_5d",
            "expiry_window_x_rv20",
        ]
    ]


def audit_factor(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    baseline: pd.DataFrame,
    regime_label: pd.Series,
) -> dict:
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
        "g6": {
            "residual_ic_mean": rm,
            "residual_t_stat": rt,
            "abs_residual_ic": abs(rm),
            "abs_pass": abs(rm) >= G6_ABS_MIN,
        },
    }


def _build_h10d_target(features: pd.DataFrame) -> pd.Series:
    out = pd.Series(np.nan, index=features.index, dtype="float64")
    for _, sub in features.groupby("subject"):
        sub = sub.sort_values("timestamp_ms")
        log_ret = np.log(sub["spot_close"].shift(-10) / sub["spot_close"])
        out.loc[sub.index] = log_ret
    return out


def cross_sectional_admission_audit(panel: pd.DataFrame, h_factors: pd.DataFrame) -> dict:
    merged = panel.merge(
        h_factors.drop(columns=["date_utc"]),
        on=["subject", "timestamp_ms"],
        how="left",
    )
    ts = merged["timestamp_ms"]
    baseline_lsk3 = merged[list(LSK3_BASELINE)].apply(pd.to_numeric, errors="coerce")
    baseline_full = merged[list(LSK3_BASELINE) + [F08_COLUMN, F_CASCADE_COLUMN]].apply(
        pd.to_numeric, errors="coerce"
    )
    regime_label = build_regime_by_ts(merged)

    target_h5d = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    target_h10d = _build_h10d_target(merged)

    factor_cols = [
        "time_to_btc_expiry",
        "expiry_window_indicator_5d",
        "expiry_window_x_rv20",
    ]

    cards: dict[str, dict] = {}
    for col in factor_cols:
        if col not in merged.columns:
            cards[col] = {"status": "missing"}
            continue
        cards[col] = {
            "h5d_vs_lsk3": audit_factor(merged[col], target_h5d, ts, baseline_lsk3, regime_label),
            "h5d_vs_lsk3_f08_fcascade": audit_factor(
                merged[col], target_h5d, ts, baseline_full, regime_label
            ),
            "h10d_vs_lsk3": audit_factor(merged[col], target_h10d, ts, baseline_lsk3, regime_label),
            "h10d_vs_lsk3_f08_fcascade": audit_factor(
                merged[col], target_h10d, ts, baseline_full, regime_label
            ),
        }
    return cards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-H expiry hedge unwind factor audit.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_ARTIFACT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== SP-H: loading panel from {args.features}")
    raw_panel = pd.read_csv(args.features, compression="gzip")
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 columns to materialize lsk3 + F08 + F-cascade...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    if F08_COLUMN not in panel.columns or F_CASCADE_COLUMN not in panel.columns:
        raise RuntimeError(f"baseline columns {F08_COLUMN}, {F_CASCADE_COLUMN} missing in rebuilt panel")
    print()

    print("=== Building BTC monthly expiry calendar (last Friday of each month) ===")
    expiries = build_btc_monthly_expiry_calendar(2022, 2026)
    print(f"  total expiries 2022-2026: {len(expiries)}")
    print(f"  first 3: {expiries[:3]}")
    print(f"  last 3:  {expiries[-3:]}")
    print()

    print("=== Doc §E.15 falsification (KS-test BTC 5d fwd-return: in-window vs out) ===")
    e15 = doc_e15_falsification(panel, expiries)
    print(json.dumps(e15, indent=2, sort_keys=True, default=str))
    print()

    print("=== Building H1 / H2 / H3 factors ===")
    h_factors = build_h_factors(panel, expiries)
    print(f"  H factor rows: {len(h_factors)}")
    print()

    print("=== Cross-sectional G1+G3+G6 admission audit (h5d + h10d, lsk3 + lsk3+F08+F-cascade) ===")
    cs_cards = cross_sectional_admission_audit(panel, h_factors)
    for fid, card in cs_cards.items():
        if "status" in card:
            print(f"  {fid}: {card['status']}")
            continue
        for variant, label in [
            ("h5d_vs_lsk3", "h5d  vs lsk3        "),
            ("h5d_vs_lsk3_f08_fcascade", "h5d  vs lsk3+F08+F-c"),
            ("h10d_vs_lsk3", "h10d vs lsk3        "),
            ("h10d_vs_lsk3_f08_fcascade", "h10d vs lsk3+F08+F-c"),
        ]:
            v = card[variant]
            if "status" in v:
                print(f"  {fid:32s} [{label}] {v['status']} (n={v.get('n_ts','?')})")
                continue
            g1 = v["g1"]
            g3 = v["g3"]
            g6 = v["g6"]
            print(
                f"  {fid:32s} [{label}]  G1 ic={g1['ic_mean']:+.4f} t={g1['t_stat']:+.2f} "
                f"(n={v['n_ts']})  G3 same={g3['same_sign_fraction']:.2f}  "
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
            "doc_e15_ks_p_threshold": DOC_E15_KS_P_THRESHOLD,
            "expiry_window_days": EXPIRY_WINDOW_DAYS,
        },
        "expiry_calendar_year_range": [2022, 2026],
        "expiry_count": len(expiries),
        "doc_e15_falsification": e15,
        "cross_sectional_admission": cs_cards,
        "lsk3_baseline": list(LSK3_BASELINE),
        "lsk3_full_baseline": list(LSK3_BASELINE) + [F08_COLUMN, F_CASCADE_COLUMN],
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "expiry_hedge_unwind_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== Done. Card at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
