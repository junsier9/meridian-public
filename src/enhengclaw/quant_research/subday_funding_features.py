"""subday_funding_features — SP-F: Sub-day funding microstructure factors.

Per data_utilization_roadmap.md SP-F + alpha ontology doc §D MF-04:
binance_derivatives 4h funding_rate gives 6 sample points per day per
subject vs the 1d-grain `funding_rate` in the cross-sectional panel.
Building factors at 4h grain captures intraday funding dispersion
patterns that F08 (1d-grain skew) cannot see.

Doc-anchored mechanism: F08 funding_term_skew_60 captures skewness of
the daily funding sequence over 60 days. F1 funding_intraday_dispersion
captures within-day VARIATION of the funding sequence — distinct
microstructure dimension.

Factors (daily panel output, per (subject, date_utc)):
  funding_intraday_dispersion_30d    — rolling 30d mean of within-day
                                       std of 6 4h funding values.
                                       High = unstable intraday carry.

  funding_sign_flip_count_30d_4h     — count of 4h-bar sign flips in
                                       rolling 30d window (180 4h bars).
                                       High = noisy / indecisive carry.

  funding_term_skew_30d_4h           — rolling-180-bar skew of 4h
                                       funding_rate. Sub-day analog of
                                       F08. NOTE: empirically collinear
                                       with F08 — kept on the panel for
                                       diagnostic but NOT used in score
                                       (G6 fail).

Admission audit (2026-04-29 panel) finds funding_intraday_dispersion_30d
is the standout: G1 |IC|=0.019 (h10d, below G1 strict 0.04 floor by
construction, since the factor is orthogonal-by-design to lsk3+F08),
G3 same-sign 1.00 (perfect across vol regimes), G6 residual IC vs
lsk3+F08 = +0.0396 t=+7.24 (h10d, STRICT PASS). Sign hypothesis:
NEGATIVE (high dispersion → overheated carry → low forward return).

Output panel CSV at:
  artifacts/quant_research/intraday/subday_funding_panel_1d.csv

Source data: binance_derivatives 4h CSVs at
  market_history/binance_derivatives/<SYM>USDT/4h/<YYYY-MM>.csv.gz
(host-local cache, NOT in repo).
"""

from __future__ import annotations

import glob
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .features import _safe_rolling_skew

ROOT = Path(__file__).resolve().parents[3]

SUBDAY_FUNDING_CONTRACT_VERSION = "quant_subday_funding.v1"

ROLLING_DAYS = 30
BARS_PER_DAY_4H = 6
ROLLING_BARS_4H = ROLLING_DAYS * BARS_PER_DAY_4H  # 180

DEFAULT_OUTPUT_PATH = (
    ROOT / "artifacts" / "quant_research" / "intraday" / "subday_funding_panel_1d.csv"
)


def _resolve_market_history_root() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history"


def _ts_ms_to_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date().isoformat()


def _load_subject_4h_funding(symbol: str) -> pd.DataFrame:
    """Returns DataFrame with [open_time_ms, funding_rate, date_utc] for one
    subject's 4h funding history. Empty if data not on disk."""
    root = _resolve_market_history_root()
    paths = sorted(glob.glob(str(root / "binance_derivatives" / f"{symbol}USDT" / "4h" / "*.csv.gz")))
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


def _compute_per_subject_subday_funding(symbol: str) -> pd.DataFrame:
    """For one subject, build the daily-grain SP-F panel from 4h funding."""
    df = _load_subject_4h_funding(symbol)
    if df.empty or len(df) < ROLLING_BARS_4H + 5:
        return pd.DataFrame()

    # F1: rolling 30d mean of within-day std of 6 4h values
    daily_std = df.groupby("date_utc")["funding_rate"].std()
    f1 = daily_std.rolling(ROLLING_DAYS, min_periods=10).mean()

    # F2: rolling-180-bar count of 4h-bar sign flips
    signs = np.sign(df["funding_rate"]).fillna(0)
    prev_sign = signs.shift(1).fillna(0)
    flip = ((signs != prev_sign) & (signs != 0) & (prev_sign != 0)).astype("int")
    df["flip"] = flip
    flip_count = df["flip"].rolling(ROLLING_BARS_4H, min_periods=60).sum()
    df["flip_count_180"] = flip_count
    f2 = df.groupby("date_utc")["flip_count_180"].last()

    # F3: rolling-180-bar skew of 4h funding_rate (sub-day analog of F08)
    df["skew_180"] = _safe_rolling_skew(df["funding_rate"], ROLLING_BARS_4H, min_periods=60)
    f3 = df.groupby("date_utc")["skew_180"].last()

    # Build daily panel
    subject = symbol.replace("USDT", "")
    out = pd.DataFrame({
        "subject": subject,
        "date_utc": list(f1.index),
        "funding_intraday_dispersion_30d": f1.values,
        "funding_sign_flip_count_30d_4h": f2.reindex(f1.index).values,
        "funding_term_skew_30d_4h": f3.reindex(f1.index).values,
    })
    return out


def _enumerate_subjects() -> list[str]:
    """List bare subject names (e.g. 'BTC' not 'BTCUSDT') with 4h funding
    data on disk. The USDT suffix is appended back inside
    _load_subject_4h_funding when forming the glob path.
    """
    root = _resolve_market_history_root() / "binance_derivatives"
    if not root.exists():
        return []
    subjects = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and entry.name.endswith("USDT"):
            if (entry / "4h").exists():
                # Strip USDT suffix; matches the bare-subject convention used by
                # SP-A's intraday_liquidation_features.
                subjects.append(entry.name.removesuffix("USDT"))
    return subjects


def write_subday_funding_panel_csv(
    subjects: list[str] | None = None,
    output_path: Path | None = None,
) -> Path:
    """Build the SP-F daily panel and write to CSV. Returns the output path.
    If `subjects` is None, enumerate all <SYM>USDT/4h directories on disk.
    """
    target = output_path or DEFAULT_OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    subj_list = subjects if subjects is not None else _enumerate_subjects()
    panels: list[pd.DataFrame] = []
    for symbol in subj_list:
        panel = _compute_per_subject_subday_funding(symbol)
        if not panel.empty:
            panels.append(panel)

    if not panels:
        # write empty panel with schema
        empty = pd.DataFrame(columns=[
            "subject", "date_utc",
            "funding_intraday_dispersion_30d",
            "funding_sign_flip_count_30d_4h",
            "funding_term_skew_30d_4h",
        ])
        empty.to_csv(target, index=False)
        return target

    full = pd.concat(panels, ignore_index=True)
    full.to_csv(target, index=False)
    return target


__all__ = [
    "SUBDAY_FUNDING_CONTRACT_VERSION",
    "DEFAULT_OUTPUT_PATH",
    "ROLLING_DAYS",
    "ROLLING_BARS_4H",
    "write_subday_funding_panel_csv",
    "_compute_per_subject_subday_funding",
    "_enumerate_subjects",
]
