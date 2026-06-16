"""cross_venue_features — multi-venue spot-price-dispersion factors (M2.1).

Per alpha ontology doc §H.3 M2.1 + §D Family MF-04 F14 / F15 + §E.3
"Cross-exchange inventory stress topology": consume the existing
coinapi_spot_sync.py infrastructure (extended to per-exchange root
layout) to build PER-ASSET cross-venue spot-price-dispersion factors
that can enter the score layer as cross-sectional features (not just
the universe-wide gauge of v0).

Scope.
  - Four venues:
      BINANCE   = LOCALAPPDATA/EnhengClaw/market_history/coinapi_ohlcv (default sync)
      COINBASE  = LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_COINBASE
      OKEX      = LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_OKEX
      BYBITSPOT = LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_BYBITSPOT
  - Top 30 universe symbols (USDT pairs); coverage varies per venue.
  - 1d interval only.
  - Coverage window: max(BINANCE start, latest of others) per asset.

Why N venues + per-asset (vs M2.1 v0's 2-venue universe-wide).
  Doc F14 formula `XS_std(price_v) / |XS_mean(price_v)|` requires N≥3
  venues to be non-degenerate. With per-asset dispersion the resulting
  factor is a CROSS-SECTIONAL feature (one value per subject per
  timestamp_ms) and can enter the long-short score layer directly,
  where v0's universe-wide gauge could only serve a beta-tilt overlay.

Output.
  Long-format panel CSV at
    artifacts/quant_research/cross_venue/cross_venue_panel_1d.csv
  with columns:
    subject (str), timestamp_ms (int), date_utc (str),
    n_venues (int 2-4),
    cross_venue_spot_dispersion (std / |mean|, NaN if n_venues<2),
    cross_venue_spot_max_minus_min_over_mean,
    cross_venue_spot_binance_premium (binance - mean(others) / mean_all)
"""

from __future__ import annotations

import glob
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
COINBASE_ROOT_NAME = "coinapi_ohlcv_COINBASE"
OKEX_ROOT_NAME = "coinapi_ohlcv_OKEX"
BYBITSPOT_ROOT_NAME = "coinapi_ohlcv_BYBITSPOT"

CROSS_VENUE_CONTRACT_VERSION = "quant_cross_venue_spot_dispersion.v2"
CROSS_VENUE_DATA_CONTRACT_VERSION_V0 = "quant_cross_venue_spot_stress.v1"

# Top 30 universe targets (matches the panel's top liquidity subjects on
# 2026-04-29). USDT-quoted symbols.
DEFAULT_TOP30_SUBJECTS: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ZEC", "BNB", "TAO", "TRX", "ADA",
    "PEPE", "PAXG", "SUI", "LINK", "AVAX", "LTC", "FET", "NEAR", "ENA", "AAVE",
    "WLD", "TON", "PENGU", "TRUMP", "KITE", "UNI", "DASH", "XPL", "BCH", "ASTER",
)
DEFAULT_INTERVAL = "1d"
DEFAULT_PANEL_OUTPUT_PATH = (
    ROOT / "artifacts" / "quant_research" / "cross_venue" / "cross_venue_panel_1d.csv"
)
# Legacy v0 output path (kept for backward compat with M2.1 v0 audit script)
DEFAULT_OUTPUT_PATH = (
    ROOT / "artifacts" / "quant_research" / "cross_venue" / "cross_venue_spot_stress.csv"
)


def _resolve_localappdata() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw"
    return Path.home() / ".local" / "share" / "EnhengClaw"


def _resolve_venue_root(venue: str) -> Path:
    base = _resolve_localappdata()
    if venue == "BINANCE":
        return base / "market_history" / "coinapi_ohlcv"
    if venue == "COINBASE":
        return base / COINBASE_ROOT_NAME
    if venue == "OKEX":
        return base / OKEX_ROOT_NAME
    if venue == "BYBITSPOT":
        return base / BYBITSPOT_ROOT_NAME
    raise ValueError(f"unknown venue {venue!r}")


# Backward-compat aliases used by M2.1 v0 callers.
def _resolve_binance_root() -> Path:
    return _resolve_venue_root("BINANCE")


def _resolve_coinbase_root() -> Path:
    return _resolve_venue_root("COINBASE")


def _load_partitioned_csvs(
    *, root: Path, market_type: str, symbol: str, interval: str
) -> pd.DataFrame:
    folder = root / market_type / symbol / interval
    if not folder.exists():
        return pd.DataFrame()
    paths = sorted(glob.glob(str(folder / "*.csv.gz")))
    if not paths:
        return pd.DataFrame()
    frames = [pd.read_csv(p, compression="gzip") for p in paths]
    return pd.concat(frames, ignore_index=True)


def _to_close_series(df: pd.DataFrame, *, label: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="float64", name=label)
    return (
        pd.to_numeric(df["close"], errors="coerce")
        .groupby(df["open_time_ms"]).last()
        .sort_index()
        .rename(label)
    )


def _load_anchor_close_pair(symbol: str, interval: str) -> tuple[pd.Series, pd.Series]:
    """v0 backward-compat: returns (binance_close, coinbase_close) tuple."""
    bn = _load_partitioned_csvs(
        root=_resolve_venue_root("BINANCE"), market_type="spot", symbol=symbol, interval=interval
    )
    cb = _load_partitioned_csvs(
        root=_resolve_venue_root("COINBASE"), market_type="spot", symbol=symbol, interval=interval
    )
    return (
        _to_close_series(bn, label=f"binance_close_{symbol}"),
        _to_close_series(cb, label=f"coinbase_close_{symbol}"),
    )


def _load_all_venue_closes(symbol: str, interval: str) -> dict[str, pd.Series]:
    """For a given USDT symbol, return {venue -> close series indexed by open_time_ms}.

    Venues missing the symbol are silently dropped from the dict.
    """
    out: dict[str, pd.Series] = {}
    for venue in ("BINANCE", "COINBASE", "OKEX", "BYBITSPOT"):
        df = _load_partitioned_csvs(
            root=_resolve_venue_root(venue),
            market_type="spot",
            symbol=symbol,
            interval=interval,
        )
        if df.empty:
            continue
        s = _to_close_series(df, label=f"{venue.lower()}_close")
        if not s.empty:
            out[venue] = s
    return out


def _compute_per_asset_dispersion(symbol: str, interval: str) -> pd.DataFrame:
    """Compute per-bar cross-venue dispersion for a single subject.

    Returns dataframe indexed by open_time_ms with columns:
      n_venues: number of venues with valid close at this timestamp (2..4)
      cross_venue_spot_dispersion: std(prices) / |mean(prices)|; NaN if <2
      cross_venue_spot_max_minus_min_over_mean: (max-min)/mean
      cross_venue_spot_binance_premium: (binance - mean(non-binance)) / mean_all
    """
    closes = _load_all_venue_closes(symbol, interval)
    if not closes:
        return pd.DataFrame()
    df = pd.concat(closes.values(), axis=1).rename(
        columns={s.name: v for v, s in zip(closes.keys(), closes.values())}
    )
    df.columns = list(closes.keys())  # ['BINANCE', 'COINBASE', ...]
    n_venues = df.notna().sum(axis=1)
    valid = n_venues >= 2

    out = pd.DataFrame(index=df.index)
    out["n_venues"] = n_venues
    mean = df.mean(axis=1)
    std = df.std(axis=1)
    abs_mean = mean.abs().replace(0.0, np.nan)
    out["cross_venue_spot_dispersion"] = (std / abs_mean).where(valid)
    rng = df.max(axis=1) - df.min(axis=1)
    out["cross_venue_spot_max_minus_min_over_mean"] = (rng / abs_mean).where(valid)

    if "BINANCE" in df.columns:
        non_binance = df.drop(columns=["BINANCE"])
        non_binance_mean = non_binance.mean(axis=1)
        all_mean = mean
        out["cross_venue_spot_binance_premium"] = (
            (df["BINANCE"] - non_binance_mean) / all_mean.replace(0.0, np.nan)
        ).where(valid & non_binance.notna().any(axis=1))
    else:
        out["cross_venue_spot_binance_premium"] = np.nan
    return out


def compute_cross_venue_panel(
    *,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    interval: str = DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """Compute the long-format per-asset cross-venue dispersion panel.

    Each output row is (subject, timestamp_ms) with the dispersion features.
    Subjects whose all venues lack data are silently dropped.
    """
    rows: list[pd.DataFrame] = []
    for subject in subjects:
        sym = f"{subject}USDT"
        per_asset = _compute_per_asset_dispersion(sym, interval)
        if per_asset.empty:
            continue
        per_asset = per_asset.reset_index().rename(columns={"index": "open_time_ms"})
        per_asset["subject"] = subject
        per_asset["timestamp_ms"] = per_asset["open_time_ms"]
        rows.append(per_asset)
    if not rows:
        raise RuntimeError(
            "no cross-venue data found for any subject. Ensure venue coinapi_spot_syncs have run."
        )
    panel = pd.concat(rows, ignore_index=True)
    panel["date_utc"] = panel["timestamp_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    panel = panel[
        [
            "subject",
            "timestamp_ms",
            "date_utc",
            "n_venues",
            "cross_venue_spot_dispersion",
            "cross_venue_spot_max_minus_min_over_mean",
            "cross_venue_spot_binance_premium",
        ]
    ].sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    return panel


def write_cross_venue_panel_csv(
    *,
    output_path: Path | None = None,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    interval: str = DEFAULT_INTERVAL,
) -> Path:
    panel = compute_cross_venue_panel(subjects=subjects, interval=interval)
    target = output_path or DEFAULT_PANEL_OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(target, index=False)
    return target


def load_cross_venue_panel() -> pd.DataFrame:
    if not DEFAULT_PANEL_OUTPUT_PATH.exists():
        write_cross_venue_panel_csv()
    return pd.read_csv(DEFAULT_PANEL_OUTPUT_PATH)


# === v0 universe-wide gauge (kept for backward compat with M2.1 v0 callers) ===


def compute_cross_venue_spot_stress(
    *,
    anchor_pairs: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    interval: str = DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """v0 universe-wide gauge — per-bar abs spot premium between BINANCE and
    COINBASE, averaged across anchor pairs. Kept for M2.1 v0 audit script
    backward compat.
    """
    out: dict[str, pd.Series] = {}
    abs_columns: list[str] = []
    for symbol in anchor_pairs:
        bn, cb = _load_anchor_close_pair(symbol, interval)
        joined = pd.concat([bn, cb], axis=1).dropna()
        if joined.empty:
            continue
        b = joined.iloc[:, 0]
        c = joined.iloc[:, 1]
        mean = (b + c) / 2.0
        premium = ((b - c) / mean.replace(0.0, np.nan)).rename(
            f"cross_venue_spot_premium_{symbol.replace('USDT', '')}"
        )
        out[premium.name] = premium
        abs_columns.append(premium.name)
    if not out:
        raise RuntimeError(
            "no cross-venue data found for any anchor pair. Ensure both BINANCE "
            "and COINBASE coinapi_spot_sync syncs have run."
        )
    df = pd.concat(list(out.values()), axis=1).sort_index()
    df["cross_venue_spot_stress"] = df[abs_columns].abs().mean(axis=1)
    df["cross_venue_spot_stress_z60"] = (
        (df["cross_venue_spot_stress"] - df["cross_venue_spot_stress"].rolling(60, min_periods=20).mean())
        / df["cross_venue_spot_stress"].rolling(60, min_periods=20).std().replace(0.0, np.nan)
    )
    return df.reset_index()


def write_cross_venue_spot_stress_csv(
    *,
    output_path: Path | None = None,
    anchor_pairs: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    interval: str = DEFAULT_INTERVAL,
) -> Path:
    df = compute_cross_venue_spot_stress(anchor_pairs=anchor_pairs, interval=interval)
    target = output_path or DEFAULT_OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)
    return target


def load_cross_venue_spot_stress() -> pd.DataFrame:
    if not DEFAULT_OUTPUT_PATH.exists():
        write_cross_venue_spot_stress_csv()
    return pd.read_csv(DEFAULT_OUTPUT_PATH)


def cross_venue_spot_stress_lookup() -> dict[str, float]:
    df = load_cross_venue_spot_stress()
    if "open_time_ms" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        ts_ms = int(row["open_time_ms"])
        if ts_ms <= 0:
            continue
        date_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
        out[date_str] = float(row.get("cross_venue_spot_stress", np.nan))
    return out


def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Compute cross-venue spot panel (M2.1 v1).")
    parser.add_argument("--mode", choices=("v0_gauge", "v1_panel", "both"), default="both")
    parser.add_argument("--output-panel", type=Path, default=None)
    parser.add_argument("--output-gauge", type=Path, default=None)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    if args.mode in ("v1_panel", "both"):
        panel_path = write_cross_venue_panel_csv(output_path=args.output_panel)
        print(f"wrote {panel_path}")
        if args.print_summary:
            df = pd.read_csv(panel_path)
            print(f"  rows: {len(df)}, n_subjects: {df['subject'].nunique()}, n_dates: {df['date_utc'].nunique()}")
            print(f"  n_venues distribution: {df['n_venues'].value_counts().to_dict()}")
            disp = df["cross_venue_spot_dispersion"].dropna()
            if not disp.empty:
                print(
                    f"  dispersion mean={disp.mean():.6f}, median={disp.median():.6f}, "
                    f"p95={disp.quantile(0.95):.6f}, max={disp.max():.6f}"
                )

    if args.mode in ("v0_gauge", "both"):
        gauge_path = write_cross_venue_spot_stress_csv(output_path=args.output_gauge)
        print(f"wrote {gauge_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
