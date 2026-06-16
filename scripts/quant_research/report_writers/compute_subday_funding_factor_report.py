"""compute_subday_funding_factor_report.py — SP-F admission audit.

Per data_utilization_roadmap.md SP-F: extract sub-day funding
microstructure factors from binance_derivatives 4h funding_rate
(6 obs/day per subject) that F08 funding_term_skew_60 (1d-grain) cannot
see. Three factor candidates:

  F1 — funding_intraday_dispersion_30d
       Per (subject, date) std of the 6 4h funding_rate values within the
       day, then rolling-30d mean. High = unstable intraday carry.

  F2 — funding_sign_flip_count_30d_4h
       Per subject, count sign changes in the 4h funding_rate sequence
       over rolling-30d (180 4h bars). High = noisy / indecisive carry.

  F3 — funding_term_skew_30d_4h
       Per subject, rolling-180-bar (≈30d at 4h grain) skew of 4h
       funding_rate. Sub-day analog of F08. Tested both directly and as
       residual after F08.

Admission audit: G1 (|IC|≥0.04), G3 (regime same-sign≥0.60), G6 vs
lsk3 11-factor baseline AND vs lsk3+F08 baseline (the latter tests
whether SP-F adds anything beyond F08). Tested at h5d and h10d.

Output: artifacts/quant_research/factor_reports/<as-of>/subday_funding_factor_report_card.json

Roadmap §C SP-F warning: "G6 success probability LOW-MEDIUM. F08
already extracts most MF-04 family signal; close cousins likely
G6-fail."
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from enhengclaw.compat.naming import getenv_compat

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
from enhengclaw.quant_research.features import _safe_rolling_skew  # noqa: E402
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_subday_funding.v1"
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
F08_COLUMN = "funding_term_skew_60"

def _default_4h_root() -> Path:
    override = getenv_compat("ENHENGCLAW_BINANCE_DERIVATIVES_ROOT")
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "EnhengClaw" / "market_history" / "binance_derivatives"
    return Path.home() / "AppData" / "Local" / "EnhengClaw" / "market_history" / "binance_derivatives"


# Default 4h derivatives root (host-local cache, NOT in repo).
DEFAULT_4H_ROOT = _default_4h_root()

ROLLING_DAYS = 30
BARS_PER_DAY_4H = 6           # 24/4
ROLLING_BARS_4H = ROLLING_DAYS * BARS_PER_DAY_4H  # 180


def _ts_ms_to_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date().isoformat()


def _load_subject_4h_funding(symbol: str, root: Path) -> pd.DataFrame:
    """Returns DataFrame with columns [open_time_ms, funding_rate, date_utc]
    for a single subject's 4h funding history. Empty if symbol not found."""
    subject_root = root / symbol / "4h"
    if not subject_root.exists():
        return pd.DataFrame()
    paths = sorted(glob.glob(str(subject_root / "*.csv.gz")))
    if not paths:
        return pd.DataFrame()
    df = pd.concat(
        [pd.read_csv(p, compression="gzip", usecols=["open_time_ms", "funding_rate"]) for p in paths],
        ignore_index=True,
    )
    df = df.sort_values("open_time_ms").drop_duplicates("open_time_ms").reset_index(drop=True)
    df["date_utc"] = df["open_time_ms"].apply(_ts_ms_to_date)
    df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
    return df


def build_sp_f_factors(subjects: list[str], root: Path) -> pd.DataFrame:
    """For each subject, build F1/F2/F3 from 4h funding sequence and aggregate
    to (subject, date_utc) panel grain.
    """
    rows: list[dict] = []
    for symbol in subjects:
        df = _load_subject_4h_funding(symbol, root)
        if df.empty or len(df) < ROLLING_BARS_4H + 5:
            continue
        # F1 — within-day std of 4h funding values, then rolling 30d mean
        daily_std = df.groupby("date_utc")["funding_rate"].std()
        f1 = daily_std.rolling(ROLLING_DAYS, min_periods=10).mean()

        # F2 — sign flip count over rolling 180 4h bars (=30d)
        signs = np.sign(df["funding_rate"]).fillna(0)
        # Sign flip indicator: 1 when consecutive bars have different non-zero signs
        prev_sign = signs.shift(1).fillna(0)
        flip = ((signs != prev_sign) & (signs != 0) & (prev_sign != 0)).astype("int")
        df["flip"] = flip
        flip_count_180 = df["flip"].rolling(ROLLING_BARS_4H, min_periods=60).sum()
        # Aggregate to daily: take the LAST 4h bar of each day's flip_count
        df["flip_count_180"] = flip_count_180
        f2 = df.groupby("date_utc")["flip_count_180"].last()

        # F3 — rolling 180-bar skew of 4h funding_rate
        df["skew_180"] = _safe_rolling_skew(df["funding_rate"], ROLLING_BARS_4H, min_periods=60)
        f3 = df.groupby("date_utc")["skew_180"].last()

        # Subject panel naming (symbol = "BTCUSDT" -> subject = "BTC")
        subject = symbol.replace("USDT", "")
        for date_utc in f1.index:
            rows.append({
                "subject": subject,
                "date_utc": date_utc,
                "funding_intraday_dispersion_30d": float(f1.get(date_utc, np.nan)),
                "funding_sign_flip_count_30d_4h": float(f2.get(date_utc, np.nan)),
                "funding_term_skew_30d_4h": float(f3.get(date_utc, np.nan)),
            })

    return pd.DataFrame(rows)


def audit_factor(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    baseline: pd.DataFrame,
    regime_label: pd.Series,
) -> dict:
    """G1 / G3 / G6 verdict for one factor against one baseline."""
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


def cross_sectional_admission_audit(
    panel: pd.DataFrame,
    sp_f_factors: pd.DataFrame,
) -> dict:
    """G1+G3+G6 audit at h5d and h10d for each SP-F factor against:
       (A) lsk3 11-factor baseline
       (B) lsk3 + F08 baseline (the harder test — residual beyond F08)
    """
    # date_utc was added during W3 rebuild — verify presence
    if "date_utc" not in panel.columns:
        panel = panel.copy()
        panel["date_utc"] = panel["timestamp_ms"].apply(_ts_ms_to_date)
    merged = panel.merge(sp_f_factors, on=["subject", "date_utc"], how="left")
    ts = merged["timestamp_ms"]
    baseline_lsk3 = merged[list(LSK3_BASELINE)].apply(pd.to_numeric, errors="coerce")
    baseline_lsk3_f08 = merged[list(LSK3_BASELINE) + [F08_COLUMN]].apply(pd.to_numeric, errors="coerce")
    regime_label = build_regime_by_ts(merged)

    target_h5d = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    target_h10d = _build_h10d_target(merged)

    factor_cols = [
        "funding_intraday_dispersion_30d",
        "funding_sign_flip_count_30d_4h",
        "funding_term_skew_30d_4h",
    ]

    cards: dict[str, dict] = {}
    for col in factor_cols:
        if col not in merged.columns:
            cards[col] = {"status": "missing"}
            continue
        cards[col] = {
            "h5d_vs_lsk3": audit_factor(merged[col], target_h5d, ts, baseline_lsk3, regime_label),
            "h5d_vs_lsk3_f08": audit_factor(merged[col], target_h5d, ts, baseline_lsk3_f08, regime_label),
            "h10d_vs_lsk3": audit_factor(merged[col], target_h10d, ts, baseline_lsk3, regime_label),
            "h10d_vs_lsk3_f08": audit_factor(merged[col], target_h10d, ts, baseline_lsk3_f08, regime_label),
        }
    return cards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-F sub-day funding microstructure factor audit.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--features",
        type=Path,
        default=DEFAULT_FEATURES_ARTIFACT,
    )
    parser.add_argument(
        "--derivatives-4h-root",
        type=Path,
        default=DEFAULT_4H_ROOT,
        help="Root containing <SYMBOL>USDT/4h/*.csv.gz",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== SP-F: loading panel from {args.features}")
    raw_panel = pd.read_csv(args.features, compression="gzip")
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 columns to materialize lsk3 baseline + F08...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    if F08_COLUMN not in panel.columns:
        raise RuntimeError(f"F08 column {F08_COLUMN} not in rebuilt panel — check W3 rebuild")
    print(f"  F08 ({F08_COLUMN}) coverage: {panel[F08_COLUMN].notna().mean():.3f}")
    print()

    # Subjects in panel
    subjects_panel = sorted(panel["subject"].unique())
    # Find 4h derivatives data for each subject (USDT pair)
    available_subjects = []
    for s in subjects_panel:
        subj_root = args.derivatives_4h_root / f"{s}USDT" / "4h"
        if subj_root.exists():
            available_subjects.append(f"{s}USDT")
    print(f"  panel subjects: {len(subjects_panel)}")
    print(f"  4h-data-available USDT subjects: {len(available_subjects)}")
    print()

    print("=== Building SP-F sub-day funding factors ===")
    sp_f_factors = build_sp_f_factors(available_subjects, args.derivatives_4h_root)
    print(f"  SP-F factor rows: {len(sp_f_factors)}")
    print()

    print("=== Cross-sectional G1+G3+G6 admission audit (h5d + h10d, lsk3 + lsk3+F08 baselines) ===")
    cs_cards = cross_sectional_admission_audit(panel, sp_f_factors)
    for fid, card in cs_cards.items():
        if "status" in card:
            print(f"  {fid}: {card['status']}")
            continue
        for variant, label in [
            ("h5d_vs_lsk3", "h5d  vs lsk3   "),
            ("h5d_vs_lsk3_f08", "h5d  vs lsk3+F08"),
            ("h10d_vs_lsk3", "h10d vs lsk3   "),
            ("h10d_vs_lsk3_f08", "h10d vs lsk3+F08"),
        ]:
            v = card[variant]
            if "status" in v:
                print(f"  {fid:36s} [{label}] {v['status']} (n={v.get('n_ts','?')})")
                continue
            g1 = v["g1"]
            g3 = v["g3"]
            g6 = v["g6"]
            print(
                f"  {fid:36s} [{label}]  G1 ic={g1['ic_mean']:+.4f} t={g1['t_stat']:+.2f} "
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
            "rolling_days": ROLLING_DAYS,
            "rolling_bars_4h": ROLLING_BARS_4H,
        },
        "subjects_with_4h_data_count": len(available_subjects),
        "sp_f_factor_row_count": int(len(sp_f_factors)),
        "cross_sectional_admission": cs_cards,
        "lsk3_baseline": list(LSK3_BASELINE),
        "lsk3_f08_baseline": list(LSK3_BASELINE) + [F08_COLUMN],
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "subday_funding_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Done. Card at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
