"""intraday_liquidation_features — SP-A: Liquidation cascade impulse-response.

Per alpha ontology doc §H.4 M3.4 + §E.12: CoinGlass 1h liquidation flow
(`long_liquidation_usd` + `short_liquidation_usd`) identifies cascade
events; the post-cascade 24-72h window has documented mean-reversion. We
ship this ahead of the doc Day 61-90 schedule because the data is already
on disk under `market_history/coinglass_extended/<SYM>USDT/1h/` (17k rows
× 93 subjects × 720 days, see `docs/quant_research/01_data_foundation/market_data_inventory.md`
§1.1 + `data_utilization_roadmap.md` SP-A).

Doc §E.12 falsification: post-cascade 24h abnormal return t-stat < 2.5σ
→ reject mechanism. Tested in
`scripts/quant_research/compute_liquidation_cascade_factor_report.py`.

Factor design.
  Per-subject 1h-grain inputs:
    liq_total[t]    = long_liquidation_usd[t] + short_liquidation_usd[t]
    liq_to_oi[t]    = liq_total[t] / open_interest_value[t]
    (binance_derivatives 1h has open_interest_value, aligned to coinglass
     timestamps)

  Rolling-720h (~30d) per-subject z-score of liq_to_oi captures "is this
  hour anomalously cascade-heavy for THIS asset" (asset-relative, since
  BTC/ETH OI scale differs from alt OI by 1000x).

  Daily aggregation (output panel, per (subject, date_utc)):
    liq_cascade_max_z_24h         — peak hourly z-score that day (single
                                    biggest cascade burst)
    liq_cascade_count_24h_z25     — count of hours that day with z > 2.5
                                    (multi-burst day count)
    liq_cascade_signed_intensity_24h — sum_h (z[h] * sign(long_liq[h]-short_liq[h]))
                                    where z>1, capped at z<10. Captures
                                    direction of cascade pressure (long
                                    liq dominant → negative; short liq
                                    dominant → positive).
    liq_cascade_recency_score_5d  — exponential-decay 5-day recency of
                                    cascade events (cascade today=1.0,
                                    1 day ago=0.5, etc.) — captures
                                    "am I in a post-cascade recovery
                                    window".

Cross-sectional sign hypothesis:
  - max_z_24h: + (cascade just happened → mean revert up → forward + ).
    But could also be - (asset under stress → deeper drawdown coming).
  - signed_intensity_24h: + when long-side cascade (capitulation) → mean
    revert up.
  - recency_5d: + (recently cascaded asset is bouncing back).

Per-subject time-series sign: the doc-prescribed direction is +
(post-cascade mean reversion 24-72h).

Output.
  Long-format panel CSV at
    artifacts/quant_research/intraday/liquidation_cascade_panel_1d.csv
"""

from __future__ import annotations

import glob
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

LIQUIDATION_CASCADE_CONTRACT_VERSION = "quant_liquidation_cascade.v1"

CASCADE_ROLLING_HOURS = 720          # 30 days at 1h grain
CASCADE_Z_THRESHOLD = 2.5            # doc §E.12 threshold
CASCADE_Z_FLOOR_FOR_SIGNED = 1.0     # only sum signed intensity for hours > z=1
CASCADE_Z_CAP = 10.0                 # cap extreme z to avoid single-event dominance
CASCADE_RECENCY_DECAY_DAYS = 5       # exponential-decay window for recency score

DEFAULT_OUTPUT_PATH = (
    ROOT / "artifacts" / "quant_research" / "intraday" / "liquidation_cascade_panel_1d.csv"
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


def _load_subject_1h_liq_oi(symbol: str) -> pd.DataFrame:
    """Load 1h `long_liquidation_usd` + `short_liquidation_usd` from coinglass
    and `open_interest_value` from binance_derivatives, aligned by open_time_ms.
    """
    root = _resolve_market_history_root()
    cg_paths = sorted(
        glob.glob(str(root / "coinglass_extended" / f"{symbol}USDT" / "1h" / "*.csv.gz"))
    )
    dv_paths = sorted(
        glob.glob(str(root / "binance_derivatives" / f"{symbol}USDT" / "1h" / "*.csv.gz"))
    )
    if not cg_paths or not dv_paths:
        return pd.DataFrame()
    cg = pd.concat([pd.read_csv(p, compression="gzip") for p in cg_paths], ignore_index=True)
    dv = pd.concat([pd.read_csv(p, compression="gzip") for p in dv_paths], ignore_index=True)
    cg = cg[["open_time_ms", "long_liquidation_usd", "short_liquidation_usd"]]
    dv = dv[["open_time_ms", "open_interest_value"]]
    merged = cg.merge(dv, on="open_time_ms", how="inner")
    merged = merged.sort_values("open_time_ms").drop_duplicates("open_time_ms").reset_index(drop=True)
    for col in ("long_liquidation_usd", "short_liquidation_usd", "open_interest_value"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    return merged


def _compute_per_subject_cascade_panel(
    symbol: str,
    *,
    rolling_hours: int = CASCADE_ROLLING_HOURS,
    z_threshold: float = CASCADE_Z_THRESHOLD,
    z_floor_for_signed: float = CASCADE_Z_FLOOR_FOR_SIGNED,
    z_cap: float = CASCADE_Z_CAP,
    recency_decay_days: float = CASCADE_RECENCY_DECAY_DAYS,
) -> pd.DataFrame:
    """For one subject, produce a daily-grain panel of cascade features."""
    bars = _load_subject_1h_liq_oi(symbol)
    if bars.empty or len(bars) < rolling_hours + 24:
        return pd.DataFrame()

    bars["liq_total"] = bars["long_liquidation_usd"].fillna(0.0) + bars["short_liquidation_usd"].fillna(0.0)
    bars["liq_to_oi"] = bars["liq_total"] / bars["open_interest_value"].replace(0.0, np.nan)
    bars["signed_liq_imbalance"] = (
        bars["long_liquidation_usd"].fillna(0.0) - bars["short_liquidation_usd"].fillna(0.0)
    ) / bars["liq_total"].replace(0.0, np.nan)
    # Rolling z-score on liq_to_oi
    rolling_mean = bars["liq_to_oi"].rolling(rolling_hours, min_periods=rolling_hours // 4).mean()
    rolling_std = bars["liq_to_oi"].rolling(rolling_hours, min_periods=rolling_hours // 4).std()
    bars["liq_z"] = (
        (bars["liq_to_oi"] - rolling_mean) / rolling_std.replace(0.0, np.nan)
    ).clip(upper=z_cap, lower=-z_cap)
    # Signed intensity: z * (-1 if long-cascade dominant else +1)
    # long_liq dominant means longs got wiped → mean revert UP → factor sign +
    # short_liq dominant means shorts got squeezed → mean revert DOWN → factor sign -
    # signed_liq_imbalance = (long-short)/total: +ve = long-dominant; -ve = short-dominant
    # We want long-dominant cascade → +ve factor (mean revert up)
    bars["signed_z"] = bars["liq_z"].where(
        bars["liq_z"] > z_floor_for_signed, 0.0
    ) * np.sign(bars["signed_liq_imbalance"].fillna(0.0))

    # Aggregate to per-day: max z, count above threshold, sum signed intensity
    bars["date_utc"] = bars["open_time_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    daily = bars.groupby("date_utc").agg(
        liq_cascade_max_z_24h=("liq_z", "max"),
        liq_cascade_count_24h_z25=("liq_z", lambda s: int((s > z_threshold).sum())),
        liq_cascade_signed_intensity_24h=("signed_z", "sum"),
    ).reset_index()
    daily["timestamp_ms"] = daily["date_utc"].apply(
        lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    )
    daily = daily.sort_values("timestamp_ms").reset_index(drop=True)

    # Recency score: exponential decay of yesterday's max_z, with TODAY's max_z
    # injected; window of recency_decay_days. half-life = recency_decay_days.
    decay_lambda = np.log(2.0) / max(recency_decay_days, 0.5)
    rec = []
    state = 0.0
    for _, row in daily.iterrows():
        # Decay yesterday's state by 1 day
        state = state * np.exp(-decay_lambda)
        # Inject today's signal if it crossed threshold
        if row["liq_cascade_max_z_24h"] > z_threshold:
            state = state + float(row["liq_cascade_max_z_24h"])
        rec.append(state)
    daily["liq_cascade_recency_score_5d"] = rec
    daily["subject"] = symbol

    return daily[
        [
            "subject",
            "timestamp_ms",
            "date_utc",
            "liq_cascade_max_z_24h",
            "liq_cascade_count_24h_z25",
            "liq_cascade_signed_intensity_24h",
            "liq_cascade_recency_score_5d",
        ]
    ]


def compute_liquidation_cascade_panel(
    *,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    rolling_hours: int = CASCADE_ROLLING_HOURS,
) -> pd.DataFrame:
    """Build long-format liquidation-cascade panel across all subjects."""
    rows: list[pd.DataFrame] = []
    for subject in subjects:
        sub_panel = _compute_per_subject_cascade_panel(subject, rolling_hours=rolling_hours)
        if not sub_panel.empty:
            rows.append(sub_panel)
    if not rows:
        raise RuntimeError(
            "no 1h liquidation+OI overlap found for any subject; ensure both "
            "coinglass_extended/<SYM>USDT/1h and binance_derivatives/<SYM>USDT/1h "
            "are synced."
        )
    return pd.concat(rows, ignore_index=True)


def write_liquidation_cascade_panel_csv(
    *,
    output_path: Path | None = None,
    subjects: tuple[str, ...] | list[str] = DEFAULT_TOP30_SUBJECTS,
    rolling_hours: int = CASCADE_ROLLING_HOURS,
) -> Path:
    panel = compute_liquidation_cascade_panel(subjects=subjects, rolling_hours=rolling_hours)
    target = output_path or DEFAULT_OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(target, index=False)
    return target


def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SP-A liquidation cascade panel builder.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--rolling-hours", type=int, default=CASCADE_ROLLING_HOURS)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    target = write_liquidation_cascade_panel_csv(
        output_path=args.output, rolling_hours=args.rolling_hours
    )
    print(f"wrote {target}")
    if args.print_summary:
        df = pd.read_csv(target)
        print(f"  rows: {len(df)}, n_subjects: {df['subject'].nunique()}, n_dates: {df['date_utc'].nunique()}")
        print(f"  date range: {df['date_utc'].min()} -> {df['date_utc'].max()}")
        for col in [
            "liq_cascade_max_z_24h",
            "liq_cascade_count_24h_z25",
            "liq_cascade_signed_intensity_24h",
            "liq_cascade_recency_score_5d",
        ]:
            s = df[col].dropna()
            print(
                f"  {col}: mean={s.mean():+.4f} median={s.median():+.4f} "
                f"p95={s.quantile(0.95):+.4f} max={s.max():+.4f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
