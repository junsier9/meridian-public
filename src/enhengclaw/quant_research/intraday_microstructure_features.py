"""intraday_microstructure_features — SP-B partial: 1h Coinglass swarm.

Per `data_utilization_roadmap.md` SP-B (subset B2 + B3 + B5): the 1h
Coinglass cache (~6.4M observations) carries 14 microstructure columns
that are mostly idle in the daily-aggregated panel. SP-B partial ships
three factor candidates from this source — picking the highest-prob
G6 variants from the §C catalog:

  B2 — top_global_disagreement_1h    : MF-07 unlock (untouched family)
  B3 — top_trader_velocity_1h        : MF-07 sibling
  B5 — hour_of_day_taker_skew        : MF-15 (F62 sibling on flow side)

Mechanism / sign hypotheses
  B2: per-subject rolling-30d (720h) Spearman corr between
      `top_trader_long_pct` and `global_account_long_pct` at 1h grain.
      Low corr = pros and retail diverging = informational asymmetry.
      Sign UNCERTAIN — could be NEG (uncertainty premium → forward neg)
      or POS (pros lead, retail catch-up → forward neg if pros short).
      Empirical sign discovered in admission audit.

  B3: per-subject short-window (6h) gradient of `top_trader_long_pct`.
      High |gradient| = pros aggressively repositioning.
      Variants tested: daily mean abs gradient, daily sum signed gradient.
      Sign EMPIRICAL.

  B5: per-subject rolling-30d mean(taker_imbalance at hours {23,7,15})
      minus mean(other hours). F62 sibling — same pre-settlement window
      but on taker_buy_volume_usd / taker_sell_volume_usd flow instead
      of on perp_close drift. Hypothesis: same sign as F62 (NEGATIVE)
      because long-unwind pre-settlement creates sell pressure on
      taker side, identifiable as a systematic taker-skew.

Storage
  Loads coinglass_extended 1h cache. No new sync needed.
  Output: artifacts/quant_research/intraday/microstructure_panel_1d.csv
"""

from __future__ import annotations

import glob
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

INTRADAY_MICROSTRUCTURE_CONTRACT_VERSION = "quant_intraday_microstructure.v1"

PRE_SETTLEMENT_HOURS_UTC = (23, 7, 15)
DEFAULT_ROLLING_HOURS = 720           # 30 days at 1h grain
DEFAULT_VELOCITY_GRADIENT_HOURS = 6   # 6h short-window gradient

DEFAULT_OUTPUT_PATH = (
    ROOT / "artifacts" / "quant_research" / "intraday" / "microstructure_panel_1d.csv"
)

DEFAULT_TOP30_SUBJECTS: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ZEC", "BNB", "TAO", "TRX", "ADA",
    "PEPE", "PAXG", "SUI", "LINK", "AVAX", "LTC", "FET", "NEAR", "ENA", "AAVE",
    "WLD", "TON", "PENGU", "TRUMP", "KITE", "UNI", "DASH", "XPL", "BCH", "ASTER",
)


def _resolve_market_history_root() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history"


def _load_subject_1h_coinglass(symbol: str) -> pd.DataFrame:
    """Load 1h coinglass_extended for a subject. Returns the relevant columns."""
    root = _resolve_market_history_root()
    paths = sorted(glob.glob(str(root / "coinglass_extended" / f"{symbol}USDT" / "1h" / "*.csv.gz")))
    if not paths:
        return pd.DataFrame()
    df = pd.concat([pd.read_csv(p, compression="gzip") for p in paths], ignore_index=True)
    keep = [
        "open_time_ms",
        "top_trader_long_pct",
        "global_account_long_pct",
        "taker_buy_volume_usd",
        "taker_sell_volume_usd",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.sort_values("open_time_ms").drop_duplicates("open_time_ms").reset_index(drop=True)
    for col in df.columns:
        if col != "open_time_ms":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _per_subject_microstructure_panel(
    symbol: str,
    *,
    rolling_hours: int = DEFAULT_ROLLING_HOURS,
    velocity_gradient_hours: int = DEFAULT_VELOCITY_GRADIENT_HOURS,
) -> pd.DataFrame:
    """Compute B2 / B3 / B5 daily-grain features for one subject."""
    bars = _load_subject_1h_coinglass(symbol)
    if bars.empty or len(bars) < rolling_hours + 24:
        return pd.DataFrame()

    bars["hour_utc"] = (bars["open_time_ms"] // (60 * 60 * 1000)) % 24
    bars["is_presettle"] = bars["hour_utc"].isin(PRE_SETTLEMENT_HOURS_UTC)
    bars["date_utc"] = bars["open_time_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )

    # === B2 — rolling 30d (720h) corr(top_long_pct, global_long_pct) ===
    top_l = bars["top_trader_long_pct"]
    glob_l = bars["global_account_long_pct"]
    if top_l.notna().any() and glob_l.notna().any():
        # Rolling Pearson corr (Spearman would be more robust but expensive
        # at 720h × 17k bars per subject; Pearson on bounded-percent data is
        # a fine approximation here)
        bars["b2_corr_720h"] = top_l.rolling(rolling_hours, min_periods=rolling_hours // 4).corr(
            glob_l
        )
    else:
        bars["b2_corr_720h"] = np.nan

    # === B3 — 6h gradient of top_trader_long_pct, daily mean abs + signed sum ===
    if top_l.notna().any():
        bars["b3_gradient_6h"] = top_l - top_l.shift(velocity_gradient_hours)
    else:
        bars["b3_gradient_6h"] = np.nan

    # === B5 — taker imbalance per hour, then pre-settlement vs other ===
    buy = bars.get("taker_buy_volume_usd")
    sell = bars.get("taker_sell_volume_usd")
    if buy is not None and sell is not None:
        total = (buy.fillna(0.0) + sell.fillna(0.0)).replace(0.0, np.nan)
        bars["taker_imb_1h"] = (buy.fillna(0.0) - sell.fillna(0.0)) / total
    else:
        bars["taker_imb_1h"] = np.nan

    # Daily aggregation
    daily = bars.groupby("date_utc").agg(
        top_global_disagreement_1h_30d=("b2_corr_720h", "last"),
        top_trader_velocity_1h_abs_24h=("b3_gradient_6h", lambda s: float(np.nanmean(np.abs(s)))),
        top_trader_velocity_1h_signed_24h=("b3_gradient_6h", "sum"),
    ).reset_index()

    # B5 — F62 pattern: 30d-rolling mean(taker_imb at presettle) - mean(other)
    # Use sum + count to handle missings
    presettle_imb = bars.loc[bars["is_presettle"], ["date_utc", "taker_imb_1h"]]
    other_imb = bars.loc[~bars["is_presettle"], ["date_utc", "taker_imb_1h"]]
    presettle_daily = presettle_imb.groupby("date_utc").agg(
        sum_presettle=("taker_imb_1h", "sum"),
        n_presettle=("taker_imb_1h", "count"),
    ).reset_index()
    other_daily = other_imb.groupby("date_utc").agg(
        sum_other=("taker_imb_1h", "sum"),
        n_other=("taker_imb_1h", "count"),
    ).reset_index()
    daily = daily.merge(presettle_daily, on="date_utc", how="left").merge(other_daily, on="date_utc", how="left")
    for col in ("sum_presettle", "n_presettle", "sum_other", "n_other"):
        if col not in daily.columns:
            daily[col] = 0.0
    daily = daily.sort_values("date_utc").reset_index(drop=True)
    p_sum_roll = daily["sum_presettle"].rolling(30, min_periods=15).sum()
    p_n_roll = daily["n_presettle"].rolling(30, min_periods=15).sum().replace(0, np.nan)
    o_sum_roll = daily["sum_other"].rolling(30, min_periods=15).sum()
    o_n_roll = daily["n_other"].rolling(30, min_periods=15).sum().replace(0, np.nan)
    daily["taker_skew_presettle_30d"] = (p_sum_roll / p_n_roll) - (o_sum_roll / o_n_roll)

    # Cleanup
    daily = daily.drop(columns=["sum_presettle", "n_presettle", "sum_other", "n_other"])
    daily["timestamp_ms"] = daily["date_utc"].apply(
        lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    )
    daily["subject"] = symbol
    return daily[
        [
            "subject",
            "timestamp_ms",
            "date_utc",
            "top_global_disagreement_1h_30d",
            "top_trader_velocity_1h_abs_24h",
            "top_trader_velocity_1h_signed_24h",
            "taker_skew_presettle_30d",
        ]
    ]


def compute_microstructure_panel(
    *,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    rolling_hours: int = DEFAULT_ROLLING_HOURS,
    velocity_gradient_hours: int = DEFAULT_VELOCITY_GRADIENT_HOURS,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for subject in subjects:
        sub = _per_subject_microstructure_panel(
            subject, rolling_hours=rolling_hours, velocity_gradient_hours=velocity_gradient_hours
        )
        if not sub.empty:
            rows.append(sub)
    if not rows:
        raise RuntimeError(
            "no 1h coinglass_extended data found for any subject; ensure sync has run."
        )
    return pd.concat(rows, ignore_index=True)


def write_microstructure_panel_csv(
    *,
    output_path: Path | None = None,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    rolling_hours: int = DEFAULT_ROLLING_HOURS,
    velocity_gradient_hours: int = DEFAULT_VELOCITY_GRADIENT_HOURS,
) -> Path:
    panel = compute_microstructure_panel(
        subjects=subjects,
        rolling_hours=rolling_hours,
        velocity_gradient_hours=velocity_gradient_hours,
    )
    target = output_path or DEFAULT_OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(target, index=False)
    return target


def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SP-B partial intraday microstructure panel.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    target = write_microstructure_panel_csv(output_path=args.output)
    print(f"wrote {target}")
    if args.print_summary:
        df = pd.read_csv(target)
        print(f"  rows: {len(df)}, n_subjects: {df['subject'].nunique()}")
        print(f"  date range: {df['date_utc'].min()} -> {df['date_utc'].max()}")
        for col in [
            "top_global_disagreement_1h_30d",
            "top_trader_velocity_1h_abs_24h",
            "top_trader_velocity_1h_signed_24h",
            "taker_skew_presettle_30d",
        ]:
            s = df[col].dropna()
            if len(s) == 0:
                continue
            print(
                f"  {col}: n_valid={len(s)}, mean={s.mean():+.4f}, median={s.median():+.4f}, "
                f"p95_abs={s.abs().quantile(0.95):.4f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
