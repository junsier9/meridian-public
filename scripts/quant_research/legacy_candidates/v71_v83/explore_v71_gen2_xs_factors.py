"""
v71 Gen-2 cross-sectional factor exploration.

Gen-1 lesson: per-symbol time-series z-scores (`top_trader_long_zscore_20d`,
`liquidation_imbalance_zscore_20d`) failed cross-sectional IC. Reason: they
encode "this symbol vs its own past", not "this symbol vs other symbols today".

Gen-2 idea: compute every factor via per-timestamp groupby across the universe
(xs_demean / xs_zscore / xs_rank). The v64 framework already does this on
`relative_strength_20`, `momentum_20`. We mirror the same shape for positioning,
liquidation, flow, orderbook signals.

Output: artifacts/quant_research/v71_exploration/gen2_xs_rank_ic.json
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


UNIVERSE_PATH = REPO_ROOT / "artifacts" / "quant_research" / "_quant_inputs" / "pit-liquidity-top100-2026-04-26.quant_universe.json"
TARGET_N = 25
INTERVAL = "1d"
HORIZONS_TO_TEST = (1, 5, 10)


GEN2_FEATURES = (
    "top_trader_long_xs_demean",
    "top_trader_long_xs_zscore",
    "smart_vs_retail_long_xs_zscore",
    "retail_long_xs_rank_inverse",
    "liquidation_imbalance_xs_zscore",
    "liquidation_imbalance_xs_zscore_winsor",
    "liquidation_intensity_xs_rank",
    "taker_imbalance_xs_zscore",
    "cumulative_taker_imbalance_5d_xs_zscore",
    "top_trader_long_change_5d_xs_zscore",
    "orderbook_imbalance_xs_zscore",
    "orderbook_depth_xs_rank",
)


def _to_float(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _select_top_universe(target_n: int) -> list[dict[str, str]]:
    payload = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") or []
    candidates = [c for c in candidates if c.get("usdm_symbol")]
    candidates.sort(key=lambda c: int(c.get("selection_rank") or 9_999))
    chosen: list[dict[str, str]] = []
    extended_root = resolve_extended_external_root()
    for c in candidates:
        usdm = str(c["usdm_symbol"])
        sym_dir = extended_root / usdm / INTERVAL
        if not sym_dir.exists():
            continue
        partitions = sorted(sym_dir.glob("*.csv.gz"))
        if len(partitions) < 12:
            continue
        chosen.append({"subject": str(c["subject"]), "usdm_symbol": usdm, "selection_rank": int(c["selection_rank"])})
        if len(chosen) >= target_n:
            break
    return chosen


def _load_extended_daily(symbol: str) -> pd.DataFrame:
    rows = load_extended_rows(
        external_root=resolve_extended_external_root(),
        symbol=symbol,
        interval=INTERVAL,
    )
    if not rows:
        return pd.DataFrame()
    records = [
        {
            "open_time_ms": int(r["open_time_ms"]),
            "long_liquidation_usd": _to_float(r.get("long_liquidation_usd", "")),
            "short_liquidation_usd": _to_float(r.get("short_liquidation_usd", "")),
            "global_account_long_pct": _to_float(r.get("global_account_long_pct", "")),
            "top_trader_long_pct": _to_float(r.get("top_trader_long_pct", "")),
            "orderbook_bids_usd": _to_float(r.get("orderbook_bids_usd", "")),
            "orderbook_asks_usd": _to_float(r.get("orderbook_asks_usd", "")),
            "taker_buy_volume_usd": _to_float(r.get("taker_buy_volume_usd", "")),
            "taker_sell_volume_usd": _to_float(r.get("taker_sell_volume_usd", "")),
        }
        for r in rows
    ]
    return pd.DataFrame.from_records(records).drop_duplicates("open_time_ms").sort_values("open_time_ms").reset_index(drop=True)


def _load_derivatives_daily(symbol: str) -> pd.DataFrame:
    rows = load_derivatives_rows(
        external_root=resolve_external_derivatives_root(),
        symbol=symbol,
        interval=INTERVAL,
    )
    if not rows:
        return pd.DataFrame()
    records = [
        {
            "open_time_ms": int(r["open_time_ms"]),
            "perp_close": _to_float(r.get("perp_close", "")),
        }
        for r in rows
    ]
    return pd.DataFrame.from_records(records).drop_duplicates("open_time_ms").sort_values("open_time_ms").reset_index(drop=True)


def _build_per_symbol_raw(symbol: str) -> pd.DataFrame:
    ext = _load_extended_daily(symbol)
    deriv = _load_derivatives_daily(symbol)
    if ext.empty or deriv.empty:
        return pd.DataFrame()
    df = pd.merge(ext, deriv, on="open_time_ms", how="inner").sort_values("open_time_ms").reset_index(drop=True)
    if df.empty:
        return df
    eps = 1e-9
    df["liquidation_imbalance_24h"] = (df["long_liquidation_usd"] - df["short_liquidation_usd"]) / (
        df["long_liquidation_usd"] + df["short_liquidation_usd"] + eps
    )
    df["liquidation_intensity_log"] = np.log(
        df["long_liquidation_usd"].clip(lower=0) + df["short_liquidation_usd"].clip(lower=0) + 1.0
    )
    df["smart_vs_retail_long_diff"] = df["top_trader_long_pct"] - df["global_account_long_pct"]
    df["orderbook_imbalance"] = (df["orderbook_bids_usd"] - df["orderbook_asks_usd"]) / (
        df["orderbook_bids_usd"] + df["orderbook_asks_usd"] + eps
    )
    df["orderbook_depth_log"] = np.log(
        df["orderbook_bids_usd"].clip(lower=0) + df["orderbook_asks_usd"].clip(lower=0) + 1.0
    )
    df["taker_imbalance"] = (df["taker_buy_volume_usd"] - df["taker_sell_volume_usd"]) / (
        df["taker_buy_volume_usd"] + df["taker_sell_volume_usd"] + eps
    )
    df["cumulative_taker_imbalance_5d"] = df["taker_imbalance"].rolling(5, min_periods=2).sum()
    df["top_trader_long_change_5d"] = df["top_trader_long_pct"] - df["top_trader_long_pct"].shift(5)

    for horizon in HORIZONS_TO_TEST:
        df[f"forward_return_{horizon}d"] = df["perp_close"].shift(-horizon) / df["perp_close"] - 1.0
    df["date"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).dt.floor("D")
    return df


def _xs_demean(group: pd.Series) -> pd.Series:
    return group - group.median()


def _xs_zscore(group: pd.Series) -> pd.Series:
    mean = group.mean()
    std = group.std(ddof=0)
    if not std or std != std:
        return group * 0.0
    return (group - mean) / std


def _xs_zscore_winsor(group: pd.Series) -> pd.Series:
    z = _xs_zscore(group)
    return z.clip(lower=-3.0, upper=3.0)


def _xs_rank(group: pd.Series) -> pd.Series:
    return group.rank(method="average", pct=True)


def _add_xs_features(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.sort_values(["date", "subject"]).reset_index(drop=True).copy()
    g = out.groupby("date", sort=False)
    out["top_trader_long_xs_demean"] = g["top_trader_long_pct"].transform(_xs_demean)
    out["top_trader_long_xs_zscore"] = g["top_trader_long_pct"].transform(_xs_zscore)
    out["smart_vs_retail_long_xs_zscore"] = g["smart_vs_retail_long_diff"].transform(_xs_zscore)
    out["retail_long_xs_rank_inverse"] = -g["global_account_long_pct"].transform(_xs_rank)
    out["liquidation_imbalance_xs_zscore"] = g["liquidation_imbalance_24h"].transform(_xs_zscore)
    out["liquidation_imbalance_xs_zscore_winsor"] = g["liquidation_imbalance_24h"].transform(_xs_zscore_winsor)
    out["liquidation_intensity_xs_rank"] = g["liquidation_intensity_log"].transform(_xs_rank)
    out["taker_imbalance_xs_zscore"] = g["taker_imbalance"].transform(_xs_zscore)
    out["cumulative_taker_imbalance_5d_xs_zscore"] = g["cumulative_taker_imbalance_5d"].transform(_xs_zscore)
    out["top_trader_long_change_5d_xs_zscore"] = g["top_trader_long_change_5d"].transform(_xs_zscore)
    out["orderbook_imbalance_xs_zscore"] = g["orderbook_imbalance"].transform(_xs_zscore)
    out["orderbook_depth_xs_rank"] = g["orderbook_depth_log"].transform(_xs_rank)
    return out


def _cross_sectional_rank_ic(panel: pd.DataFrame, feature: str, horizon: int) -> dict[str, float | int]:
    return_col = f"forward_return_{horizon}d"
    sub = panel[["date", "subject", feature, return_col]].replace([np.inf, -np.inf], np.nan).dropna()
    if sub.empty:
        return {"mean_ic": float("nan"), "ic_std": float("nan"), "n_days": 0, "positive_day_rate": float("nan")}
    daily_ic: list[float] = []
    for _, group in sub.groupby("date"):
        if len(group) < 8:
            continue
        rho, _ = spearmanr(group[feature], group[return_col])
        if rho == rho:
            daily_ic.append(float(rho))
    if not daily_ic:
        return {"mean_ic": float("nan"), "ic_std": float("nan"), "n_days": 0, "positive_day_rate": float("nan")}
    arr = np.array(daily_ic, dtype="float64")
    return {
        "mean_ic": float(arr.mean()),
        "ic_std": float(arr.std(ddof=0)),
        "n_days": int(len(arr)),
        "positive_day_rate": float((arr > 0).mean()),
    }


def main() -> int:
    universe = _select_top_universe(TARGET_N)
    print(f"universe size: {len(universe)} ({', '.join(c['subject'] for c in universe)})")

    frames: list[pd.DataFrame] = []
    for entry in universe:
        df = _build_per_symbol_raw(entry["usdm_symbol"])
        if df.empty:
            continue
        df["subject"] = entry["subject"]
        frames.append(df)
    if not frames:
        print("no symbols loaded", file=sys.stderr)
        return 1

    panel = pd.concat(frames, ignore_index=True)
    panel = _add_xs_features(panel)

    feature_results: dict[str, dict[str, dict[str, float | int]]] = {}
    for feature in GEN2_FEATURES:
        feature_results[feature] = {
            f"horizon_{h}d": _cross_sectional_rank_ic(panel, feature, h) for h in HORIZONS_TO_TEST
        }

    report = {
        "produced_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "design_note": "Gen-2 factors computed via per-timestamp groupby across universe (xs_demean / xs_zscore / xs_rank), not per-symbol time-series",
        "universe": universe,
        "interval": INTERVAL,
        "horizons_tested_days": list(HORIZONS_TO_TEST),
        "panel_total_rows": int(len(panel)),
        "gen2_feature_names": list(GEN2_FEATURES),
        "feature_results": feature_results,
    }
    out_root = REPO_ROOT / "artifacts" / "quant_research" / "v71_exploration"
    out_root.mkdir(parents=True, exist_ok=True)
    output_path = out_root / "gen2_xs_rank_ic.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"\nWritten: {output_path}\n")
    print(f"Gen-2 cross-sectional rank IC (panel rows={len(panel)}, universe N={len(universe)}):")
    headers = "  {:<46}".format("feature")
    for h in HORIZONS_TO_TEST:
        headers += " {:>10} {:>7}".format(f"IC_{h}d", f"pos_{h}d")
    print(headers)
    rows = []
    for feature, payload in feature_results.items():
        cells = []
        for h in HORIZONS_TO_TEST:
            stats = payload[f"horizon_{h}d"]
            cells.append((stats["mean_ic"], stats["positive_day_rate"]))
        rows.append((feature, cells))
    rows.sort(key=lambda x: -max(abs(c[0]) if not math.isnan(c[0]) else 0.0 for c in x[1]))
    for feature, cells in rows:
        line = f"  {feature:<46}"
        for ic, pos in cells:
            line += f" {ic:>+10.4f} {pos:>7.3f}"
        print(line)
    print()

    gate = 0.05
    print(f"Gate: |mean_IC| >= {gate} on at least one horizon (v64 horizon=5d)")
    pass_5d = []
    pass_any = set()
    for feature, cells in rows:
        for h, (ic, _) in zip(HORIZONS_TO_TEST, cells):
            if not math.isnan(ic) and abs(ic) >= gate:
                pass_any.add(feature)
                if h == 5:
                    pass_5d.append((feature, ic))
                print(f"  PASS  {feature} @ {h}d: {ic:+.4f}")
    print(f"\n=== {len(pass_any)} / {len(GEN2_FEATURES)} features pass on ANY horizon ===")
    print(f"=== {len(pass_5d)} / {len(GEN2_FEATURES)} features pass at v64 5d horizon ===")
    if pass_5d:
        print("\nv71 candidate inject list (5d gate pass):")
        for f, ic in pass_5d:
            print(f"  - {f}: IC_5d = {ic:+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
