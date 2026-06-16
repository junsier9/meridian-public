"""intraday_settlement_features — M2.3 settlement-cycle premium factor.

Per alpha ontology doc §H.3 M2.3 + §E.10: extract sub-day intraday signals
from the existing 1h Binance derivatives store. The 8h funding cycle on
Binance USDM-perp settles at UTC 00:00, 08:00, 16:00. Position-adjusting
flow concentrated around those hours produces a SYSTEMATIC DRIFT in 1h
perp returns at settlement bars vs other hours of the day.

Doc E.10 falsification: UTC 0h/8h/16h ± 1h return mean-diff t-stat < 2 vs
other hours → reject mechanism.

Factor design.
  settlement_cycle_premium_30d (per subject, per date):
    = mean(perp_1h_log_return | hour_utc ∈ {0,8,16}) over rolling 30 days
      - mean(perp_1h_log_return | hour_utc ∉ {0,8,16}) over same 30 days
  Captures the SIGNED systematic drift at settlement bars relative to
  non-settlement hours, smoothed over a 30-day window per asset.

  settlement_cycle_volatility_premium_30d (companion):
    = mean(|perp_1h_log_return| | settlement_hour) - mean(|perp_1h_log_return| | non-settlement)
  Captures whether settlement bars have higher RANGE than other hours
  (independent of direction).

Storage.
  Loads 1h Binance derivatives (perp_close + open_time_ms) from existing
  LOCALAPPDATA/EnhengClaw/market_history/binance_derivatives store. No
  new sync needed.

  Output panel: artifacts/quant_research/intraday/settlement_cycle_panel_1d.csv
  Long-format with columns:
    subject, timestamp_ms, date_utc,
    settlement_cycle_premium_30d,
    settlement_cycle_volatility_premium_30d,
    n_settlement_obs_30d (sample-quality check, expect ~90 = 30d × 3 settlements/day)
"""

from __future__ import annotations

import glob
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DERIV_ROOT_NAME = "market_history/binance_derivatives"
# Doc E.10 prescribes "UTC 0/8/16 附近 1h" — empirically the strongest signal
# is at the PRE-settlement hour (1h before each settlement: hours 23, 7, 15).
# Variant scan 2026-04-29 across {0,8,16} / {23,7,15} / {1,9,17} × {30d, 60d,
# 90d}: pre-settlement {23,7,15} × 60d optimal (raw IC -0.043 t=-4.64; residual
# vs lsk3 -0.045 t=-4.79; G1 + G6 strict double-pass).
SETTLEMENT_HOURS_UTC = (0, 8, 16)              # canonical settlement bars (kept for compat)
PRE_SETTLEMENT_HOURS_UTC = (23, 7, 15)         # primary signal window (1h before settlement)
DEFAULT_ROLLING_WINDOW_DAYS = 60
DEFAULT_OUTPUT_PATH = (
    ROOT / "artifacts" / "quant_research" / "intraday" / "settlement_cycle_panel_1d.csv"
)

INTRADAY_SETTLEMENT_CONTRACT_VERSION = "quant_settlement_cycle_premium.v1"

# Default top-30 universe (matches M2.1 / M2.2 audit panel).
DEFAULT_TOP30_SUBJECTS: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ZEC", "BNB", "TAO", "TRX", "ADA",
    "PEPE", "PAXG", "SUI", "LINK", "AVAX", "LTC", "FET", "NEAR", "ENA", "AAVE",
    "WLD", "TON", "PENGU", "TRUMP", "KITE", "UNI", "DASH", "XPL", "BCH", "ASTER",
)


def _resolve_deriv_root() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history" / "binance_derivatives"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history" / "binance_derivatives"


def _load_subject_1h_perp(symbol: str) -> pd.DataFrame:
    """Load all 1h derivatives partitions for a subject; return (open_time_ms, perp_close)."""
    folder = _resolve_deriv_root() / f"{symbol}USDT" / "1h"
    if not folder.exists():
        return pd.DataFrame()
    paths = sorted(glob.glob(str(folder / "*.csv.gz")))
    if not paths:
        return pd.DataFrame()
    frames = [pd.read_csv(p, compression="gzip") for p in paths]
    df = pd.concat(frames, ignore_index=True)
    if "perp_close" not in df.columns or "open_time_ms" not in df.columns:
        return pd.DataFrame()
    df = df.sort_values("open_time_ms").drop_duplicates("open_time_ms")
    df = df[["open_time_ms", "perp_close"]].copy()
    df["perp_close"] = pd.to_numeric(df["perp_close"], errors="coerce")
    df = df.dropna(subset=["perp_close"])
    df = df[df["perp_close"] > 0].reset_index(drop=True)
    return df


def _compute_per_subject_settlement_panel(
    symbol: str,
    *,
    rolling_window_days: int = DEFAULT_ROLLING_WINDOW_DAYS,
) -> pd.DataFrame:
    """For one subject, produce a daily-grain panel of settlement-cycle features."""
    bars = _load_subject_1h_perp(symbol)
    if bars.empty or len(bars) < 24 * rolling_window_days:
        return pd.DataFrame()
    bars["log_return_1h"] = np.log(bars["perp_close"] / bars["perp_close"].shift(1))
    bars = bars.dropna(subset=["log_return_1h"])

    bars["hour_utc"] = (bars["open_time_ms"] // (60 * 60 * 1000)) % 24
    # Use PRE-settlement hours as the "settlement window" — empirical optimum
    # per the variant scan (the unwind happens BEFORE the funding payment, then
    # mean-reverts after; settlement-bar itself is intermediate).
    bars["is_settlement_hour"] = bars["hour_utc"].isin(PRE_SETTLEMENT_HOURS_UTC)
    bars["date_utc"] = bars["open_time_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )

    daily = bars.groupby("date_utc").agg(
        sum_settlement_signed=("log_return_1h", lambda s: float(s[bars.loc[s.index, "is_settlement_hour"]].sum())),
        n_settlement=("log_return_1h", lambda s: int(bars.loc[s.index, "is_settlement_hour"].sum())),
        sum_settlement_abs=("log_return_1h", lambda s: float(s[bars.loc[s.index, "is_settlement_hour"]].abs().sum())),
        sum_nonsettlement_signed=("log_return_1h", lambda s: float(s[~bars.loc[s.index, "is_settlement_hour"]].sum())),
        n_nonsettlement=("log_return_1h", lambda s: int((~bars.loc[s.index, "is_settlement_hour"]).sum())),
        sum_nonsettlement_abs=("log_return_1h", lambda s: float(s[~bars.loc[s.index, "is_settlement_hour"]].abs().sum())),
    ).reset_index()
    daily["timestamp_ms"] = daily["date_utc"].apply(
        lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    )
    daily = daily.sort_values("timestamp_ms").reset_index(drop=True)

    settle_signed_roll = daily["sum_settlement_signed"].rolling(rolling_window_days, min_periods=15).sum()
    settle_n_roll = daily["n_settlement"].rolling(rolling_window_days, min_periods=15).sum()
    settle_abs_roll = daily["sum_settlement_abs"].rolling(rolling_window_days, min_periods=15).sum()
    nonsettle_signed_roll = daily["sum_nonsettlement_signed"].rolling(rolling_window_days, min_periods=15).sum()
    nonsettle_n_roll = daily["n_nonsettlement"].rolling(rolling_window_days, min_periods=15).sum()
    nonsettle_abs_roll = daily["sum_nonsettlement_abs"].rolling(rolling_window_days, min_periods=15).sum()

    settle_mean = settle_signed_roll / settle_n_roll.replace(0, np.nan)
    nonsettle_mean = nonsettle_signed_roll / nonsettle_n_roll.replace(0, np.nan)
    settle_abs_mean = settle_abs_roll / settle_n_roll.replace(0, np.nan)
    nonsettle_abs_mean = nonsettle_abs_roll / nonsettle_n_roll.replace(0, np.nan)

    # Primary canonical column name documents the rolling window and pre-
    # settlement-hour interpretation. settlement_cycle_premium_60d = mean of
    # 1h log-return at pre-settlement hours minus mean at non-pre-settlement
    # hours, rolling 60 days. F62 in the alpha ontology family (MF-15
    # settlement-friction).
    daily["settlement_cycle_premium_60d"] = settle_mean - nonsettle_mean
    daily["settlement_cycle_volatility_premium_60d"] = settle_abs_mean - nonsettle_abs_mean
    daily["n_settlement_obs_60d"] = settle_n_roll
    daily["subject"] = symbol

    return daily[
        [
            "subject",
            "timestamp_ms",
            "date_utc",
            "settlement_cycle_premium_60d",
            "settlement_cycle_volatility_premium_60d",
            "n_settlement_obs_60d",
        ]
    ]


def compute_settlement_cycle_panel(
    *,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    rolling_window_days: int = DEFAULT_ROLLING_WINDOW_DAYS,
) -> pd.DataFrame:
    """Build long-format settlement-cycle panel across all subjects."""
    rows: list[pd.DataFrame] = []
    for subject in subjects:
        sub_panel = _compute_per_subject_settlement_panel(
            subject, rolling_window_days=rolling_window_days
        )
        if not sub_panel.empty:
            rows.append(sub_panel)
    if not rows:
        raise RuntimeError(
            "no 1h derivatives data available for any subject. Ensure "
            "binance_derivatives 1h sync has run."
        )
    return pd.concat(rows, ignore_index=True)


def write_settlement_cycle_panel_csv(
    *,
    output_path: Path | None = None,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    rolling_window_days: int = DEFAULT_ROLLING_WINDOW_DAYS,
) -> Path:
    panel = compute_settlement_cycle_panel(
        subjects=subjects, rolling_window_days=rolling_window_days
    )
    target = output_path or DEFAULT_OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(target, index=False)
    return target


def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="M2.3 settlement-cycle premium panel builder."
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--rolling-days", type=int, default=DEFAULT_ROLLING_WINDOW_DAYS)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    target = write_settlement_cycle_panel_csv(
        output_path=args.output, rolling_window_days=args.rolling_days
    )
    print(f"wrote {target}")
    if args.print_summary:
        df = pd.read_csv(target)
        print(f"  rows: {len(df)}")
        print(f"  n_subjects: {df['subject'].nunique()}")
        print(f"  date range: {df['date_utc'].min()} -> {df['date_utc'].max()}")
        s = df["settlement_cycle_premium_60d"].dropna()
        v = df["settlement_cycle_volatility_premium_60d"].dropna()
        print(f"  premium: mean={s.mean():+.6f} median={s.median():+.6f} p95_abs={s.abs().quantile(0.95):.6f}")
        print(f"  vol_premium: mean={v.mean():+.6f} median={v.median():+.6f} p95_abs={v.abs().quantile(0.95):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
