"""
v71 exploration: time-series IC of CoinGlass-extended derived features
on BTC/ETH/SOL vs forward 5d returns.

Standalone — does not import lab.py/hypothesis_batch.py and does not edit any
v64 baseline state. Output: artifacts/quant_research/v71_exploration/extended_features_ic.json
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))

from enhengclaw.quant_research.binance_derivatives import (  # noqa: E402
    load_derivatives_rows,
    resolve_external_derivatives_root,
)
from enhengclaw.quant_research.coinglass_extended import (  # noqa: E402
    load_extended_rows,
    resolve_extended_external_root,
)


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
INTERVAL = "1h"
FORWARD_HORIZON_DAYS = 5
ROLLING_WINDOW_HOURS = 24 * 20

DERIVED_FEATURE_NAMES = (
    "liquidation_imbalance_24h",
    "liquidation_intensity_24h_log",
    "smart_vs_retail_long",
    "top_trader_long_zscore_20d",
    "taker_aggression_imbalance_24h",
    "orderbook_imbalance",
    "orderbook_depth_log",
    "funding_rate_1h_zscore_20d",
)


def _to_float(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _load_extended_frame(symbol: str) -> pd.DataFrame:
    rows = load_extended_rows(
        external_root=resolve_extended_external_root(),
        symbol=symbol,
        interval=INTERVAL,
    )
    if not rows:
        return pd.DataFrame()
    records: list[dict[str, float | int]] = []
    for row in rows:
        records.append(
            {
                "open_time_ms": int(row["open_time_ms"]),
                "long_liquidation_usd": _to_float(row.get("long_liquidation_usd", "")),
                "short_liquidation_usd": _to_float(row.get("short_liquidation_usd", "")),
                "global_account_long_pct": _to_float(row.get("global_account_long_pct", "")),
                "global_account_short_pct": _to_float(row.get("global_account_short_pct", "")),
                "top_trader_long_pct": _to_float(row.get("top_trader_long_pct", "")),
                "top_trader_short_pct": _to_float(row.get("top_trader_short_pct", "")),
                "orderbook_bids_usd": _to_float(row.get("orderbook_bids_usd", "")),
                "orderbook_asks_usd": _to_float(row.get("orderbook_asks_usd", "")),
                "taker_buy_volume_usd": _to_float(row.get("taker_buy_volume_usd", "")),
                "taker_sell_volume_usd": _to_float(row.get("taker_sell_volume_usd", "")),
            }
        )
    df = pd.DataFrame.from_records(records).drop_duplicates(subset=["open_time_ms"]).sort_values("open_time_ms")
    df = df.reset_index(drop=True)
    return df


def _load_derivatives_frame(symbol: str) -> pd.DataFrame:
    rows = load_derivatives_rows(
        external_root=resolve_external_derivatives_root(),
        symbol=symbol,
        interval=INTERVAL,
    )
    if not rows:
        return pd.DataFrame()
    records: list[dict[str, float | int]] = []
    for row in rows:
        records.append(
            {
                "open_time_ms": int(row["open_time_ms"]),
                "funding_rate": _to_float(row.get("funding_rate", "")),
                "perp_close": _to_float(row.get("perp_close", "")),
            }
        )
    df = pd.DataFrame.from_records(records).drop_duplicates(subset=["open_time_ms"]).sort_values("open_time_ms")
    df = df.reset_index(drop=True)
    return df


def _build_hourly_frame(symbol: str) -> pd.DataFrame:
    extended = _load_extended_frame(symbol)
    derivatives = _load_derivatives_frame(symbol)
    if extended.empty or derivatives.empty:
        return pd.DataFrame()
    merged = pd.merge(extended, derivatives, on="open_time_ms", how="inner")
    merged = merged.sort_values("open_time_ms").reset_index(drop=True)
    return merged


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(8, window // 4)).mean()
    std = series.rolling(window, min_periods=max(8, window // 4)).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def _build_hourly_features(hourly: pd.DataFrame) -> pd.DataFrame:
    df = hourly.copy()
    eps = 1e-9
    df["funding_rate_1h_zscore_20d"] = _rolling_zscore(df["funding_rate"], ROLLING_WINDOW_HOURS)
    df["top_trader_long_zscore_20d"] = _rolling_zscore(df["top_trader_long_pct"], ROLLING_WINDOW_HOURS)
    df["smart_vs_retail_long"] = df["top_trader_long_pct"] - df["global_account_long_pct"]
    df["orderbook_imbalance"] = (df["orderbook_bids_usd"] - df["orderbook_asks_usd"]) / (
        df["orderbook_bids_usd"] + df["orderbook_asks_usd"] + eps
    )
    df["orderbook_depth_log"] = np.log(df["orderbook_bids_usd"].clip(lower=0) + df["orderbook_asks_usd"].clip(lower=0) + 1.0)
    return df


def _aggregate_to_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    df = hourly.copy()
    df["timestamp"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True)
    df["date"] = df["timestamp"].dt.floor("D")
    eps = 1e-9
    grouped = df.groupby("date")
    daily = pd.DataFrame(
        {
            "long_liq_24h": grouped["long_liquidation_usd"].sum(min_count=1),
            "short_liq_24h": grouped["short_liquidation_usd"].sum(min_count=1),
            "taker_buy_24h": grouped["taker_buy_volume_usd"].sum(min_count=1),
            "taker_sell_24h": grouped["taker_sell_volume_usd"].sum(min_count=1),
            "orderbook_imbalance_eod": grouped["orderbook_imbalance"].last(),
            "orderbook_depth_log_eod": grouped["orderbook_depth_log"].last(),
            "smart_vs_retail_long_eod": grouped["smart_vs_retail_long"].last(),
            "top_trader_long_zscore_20d_eod": grouped["top_trader_long_zscore_20d"].last(),
            "funding_rate_1h_zscore_20d_eod": grouped["funding_rate_1h_zscore_20d"].last(),
            "perp_close_eod": grouped["perp_close"].last(),
        }
    ).reset_index()

    daily["liquidation_imbalance_24h"] = (daily["long_liq_24h"] - daily["short_liq_24h"]) / (
        daily["long_liq_24h"] + daily["short_liq_24h"] + eps
    )
    daily["liquidation_intensity_24h_log"] = np.log(
        daily["long_liq_24h"].clip(lower=0) + daily["short_liq_24h"].clip(lower=0) + 1.0
    )
    daily["taker_aggression_imbalance_24h"] = (daily["taker_buy_24h"] - daily["taker_sell_24h"]) / (
        daily["taker_buy_24h"] + daily["taker_sell_24h"] + eps
    )
    daily["orderbook_imbalance"] = daily["orderbook_imbalance_eod"]
    daily["orderbook_depth_log"] = daily["orderbook_depth_log_eod"]
    daily["smart_vs_retail_long"] = daily["smart_vs_retail_long_eod"]
    daily["top_trader_long_zscore_20d"] = daily["top_trader_long_zscore_20d_eod"]
    daily["funding_rate_1h_zscore_20d"] = daily["funding_rate_1h_zscore_20d_eod"]

    daily["forward_return"] = (
        daily["perp_close_eod"].shift(-FORWARD_HORIZON_DAYS) / daily["perp_close_eod"] - 1.0
    )
    daily = daily.dropna(subset=["perp_close_eod"]).reset_index(drop=True)
    return daily


def _compute_ic(daily: pd.DataFrame, feature_name: str) -> dict[str, float | int]:
    sub = daily[[feature_name, "forward_return"]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 60:
        return {"n": int(len(sub)), "spearman": float("nan"), "pearson": float("nan"), "hit_rate": float("nan")}
    rho, _ = spearmanr(sub[feature_name], sub["forward_return"])
    pearson = float(sub[feature_name].corr(sub["forward_return"]))
    feat_sign = np.sign(sub[feature_name].values)
    ret_sign = np.sign(sub["forward_return"].values)
    nonzero = (feat_sign != 0) & (ret_sign != 0)
    hit_rate = float(np.mean(feat_sign[nonzero] == ret_sign[nonzero])) if nonzero.any() else float("nan")
    return {
        "n": int(len(sub)),
        "spearman": float(rho) if rho == rho else float("nan"),
        "pearson": pearson if pearson == pearson else float("nan"),
        "hit_rate": hit_rate,
    }


def _summarize_per_feature(per_symbol: dict[str, dict[str, float | int]]) -> dict[str, float | int]:
    spearmans = [stats["spearman"] for stats in per_symbol.values() if stats["spearman"] == stats["spearman"]]
    abs_mean = float(np.mean([abs(s) for s in spearmans])) if spearmans else float("nan")
    signed_mean = float(np.mean(spearmans)) if spearmans else float("nan")
    sign_consistent = bool(spearmans) and (all(s > 0 for s in spearmans) or all(s < 0 for s in spearmans))
    return {
        "abs_spearman_mean": abs_mean,
        "signed_spearman_mean": signed_mean,
        "sign_consistent_across_symbols": sign_consistent,
        "n_symbols_with_data": len(spearmans),
    }


def main() -> int:
    out_root = REPO_ROOT / "artifacts" / "quant_research" / "v71_exploration"
    out_root.mkdir(parents=True, exist_ok=True)

    per_symbol_results: dict[str, dict[str, dict[str, float | int]]] = {}
    daily_diagnostics: dict[str, dict[str, int]] = {}

    for symbol in SYMBOLS:
        hourly = _build_hourly_frame(symbol)
        if hourly.empty:
            print(f"[{symbol}] no data merged from extended + derivatives — skipping")
            continue
        hourly = _build_hourly_features(hourly)
        daily = _aggregate_to_daily(hourly)
        daily_diagnostics[symbol] = {
            "hourly_rows": int(len(hourly)),
            "daily_rows": int(len(daily)),
            "first_date": pd.Timestamp(daily["date"].iloc[0]).strftime("%Y-%m-%d") if len(daily) else "",
            "last_date": pd.Timestamp(daily["date"].iloc[-1]).strftime("%Y-%m-%d") if len(daily) else "",
        }
        per_symbol_results[symbol] = {
            feature: _compute_ic(daily, feature) for feature in DERIVED_FEATURE_NAMES
        }

    feature_summaries: dict[str, dict[str, object]] = {}
    for feature in DERIVED_FEATURE_NAMES:
        per_symbol = {symbol: stats[feature] for symbol, stats in per_symbol_results.items()}
        feature_summaries[feature] = {
            "per_symbol": per_symbol,
            "summary": _summarize_per_feature(per_symbol),
        }

    report = {
        "produced_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "symbols": list(SYMBOLS),
        "interval": INTERVAL,
        "forward_horizon_days": FORWARD_HORIZON_DAYS,
        "rolling_window_hours": ROLLING_WINDOW_HOURS,
        "derived_feature_names": list(DERIVED_FEATURE_NAMES),
        "daily_diagnostics": daily_diagnostics,
        "feature_results": feature_summaries,
    }

    output_path = out_root / "extended_features_ic.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"\nWritten: {output_path}\n")
    print("Per-feature summary (sorted by |IC| mean across BTC/ETH/SOL):")
    print(f"  {'feature':<36}  {'|IC|':>7}  {'signed':>7}  {'consistent':>10}  {'n_sym':>5}")
    rows = []
    for feature, payload in feature_summaries.items():
        s = payload["summary"]
        rows.append((feature, s["abs_spearman_mean"], s["signed_spearman_mean"], s["sign_consistent_across_symbols"], s["n_symbols_with_data"]))
    rows.sort(key=lambda x: -x[1] if not math.isnan(x[1]) else -1.0)
    for feature, abs_ic, signed_ic, consistent, n in rows:
        print(f"  {feature:<36}  {abs_ic:>7.4f}  {signed_ic:>+7.4f}  {str(consistent):>10}  {n:>5}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
