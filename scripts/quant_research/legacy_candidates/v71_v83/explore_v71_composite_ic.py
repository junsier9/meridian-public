"""
v71 composite IC test for 4 near-gate cross-sectional factors.

Inputs (sign-aligned so all expected to predict positive forward return):
  +1 * cumulative_taker_imbalance_5d_xs_zscore   (raw IC_5d = +0.041)
  +1 * retail_long_xs_rank_inverse               (raw IC_5d = +0.037)
  -1 * liquidation_imbalance_xs_zscore           (raw IC_5d = -0.038)
  -1 * top_trader_long_xs_demean                 (raw IC_5d = -0.031)

Composite gate: |mean_IC| >= 0.06 at v64 5d horizon AND pairwise |corr| < 0.40.
Output: artifacts/quant_research/v71_exploration/composite_ic.json
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

NEAR_GATE_FACTORS = (
    ("cumulative_taker_imbalance_5d_xs_zscore", +1.0),
    ("retail_long_xs_rank_inverse",             +1.0),
    ("liquidation_imbalance_xs_zscore",         -1.0),
    ("top_trader_long_xs_demean",               -1.0),
)


def _to_float(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _select_top_universe(target_n: int) -> list[dict[str, str | int]]:
    payload = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") or []
    candidates = [c for c in candidates if c.get("usdm_symbol")]
    candidates.sort(key=lambda c: int(c.get("selection_rank") or 9_999))
    chosen: list[dict[str, str | int]] = []
    extended_root = resolve_extended_external_root()
    for c in candidates:
        usdm = str(c["usdm_symbol"])
        sym_dir = extended_root / usdm / INTERVAL
        if not sym_dir.exists():
            continue
        if len(sorted(sym_dir.glob("*.csv.gz"))) < 12:
            continue
        chosen.append({"subject": str(c["subject"]), "usdm_symbol": usdm, "selection_rank": int(c["selection_rank"])})
        if len(chosen) >= target_n:
            break
    return chosen


def _load_extended_daily(symbol: str) -> pd.DataFrame:
    rows = load_extended_rows(external_root=resolve_extended_external_root(), symbol=symbol, interval=INTERVAL)
    if not rows:
        return pd.DataFrame()
    records = [
        {
            "open_time_ms": int(r["open_time_ms"]),
            "long_liquidation_usd": _to_float(r.get("long_liquidation_usd", "")),
            "short_liquidation_usd": _to_float(r.get("short_liquidation_usd", "")),
            "global_account_long_pct": _to_float(r.get("global_account_long_pct", "")),
            "top_trader_long_pct": _to_float(r.get("top_trader_long_pct", "")),
            "taker_buy_volume_usd": _to_float(r.get("taker_buy_volume_usd", "")),
            "taker_sell_volume_usd": _to_float(r.get("taker_sell_volume_usd", "")),
        }
        for r in rows
    ]
    return pd.DataFrame.from_records(records).drop_duplicates("open_time_ms").sort_values("open_time_ms").reset_index(drop=True)


def _load_derivatives_daily(symbol: str) -> pd.DataFrame:
    rows = load_derivatives_rows(external_root=resolve_external_derivatives_root(), symbol=symbol, interval=INTERVAL)
    if not rows:
        return pd.DataFrame()
    records = [
        {"open_time_ms": int(r["open_time_ms"]), "perp_close": _to_float(r.get("perp_close", ""))}
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
    df["taker_imbalance"] = (df["taker_buy_volume_usd"] - df["taker_sell_volume_usd"]) / (
        df["taker_buy_volume_usd"] + df["taker_sell_volume_usd"] + eps
    )
    df["cumulative_taker_imbalance_5d"] = df["taker_imbalance"].rolling(5, min_periods=2).sum()
    for horizon in HORIZONS_TO_TEST:
        df[f"forward_return_{horizon}d"] = df["perp_close"].shift(-horizon) / df["perp_close"] - 1.0
    df["date"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).dt.floor("D")
    return df


def _xs_zscore(group: pd.Series) -> pd.Series:
    mean = group.mean()
    std = group.std(ddof=0)
    if not std or std != std:
        return group * 0.0
    return (group - mean) / std


def _xs_rank(group: pd.Series) -> pd.Series:
    return group.rank(method="average", pct=True)


def _add_xs_features(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.sort_values(["date", "subject"]).reset_index(drop=True).copy()
    g = out.groupby("date", sort=False)
    out["top_trader_long_xs_demean"] = g["top_trader_long_pct"].transform(lambda s: s - s.median())
    out["liquidation_imbalance_xs_zscore"] = g["liquidation_imbalance_24h"].transform(_xs_zscore)
    out["cumulative_taker_imbalance_5d_xs_zscore"] = g["cumulative_taker_imbalance_5d"].transform(_xs_zscore)
    out["retail_long_xs_rank_inverse"] = -g["global_account_long_pct"].transform(_xs_rank)
    return out


def _add_aligned_factors(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for name, sign in NEAR_GATE_FACTORS:
        out[f"{name}__aligned"] = sign * out[name]
    return out


def _add_xs_zscore_versions(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.sort_values(["date", "subject"]).reset_index(drop=True).copy()
    g = out.groupby("date", sort=False)
    for name, _ in NEAR_GATE_FACTORS:
        col = f"{name}__aligned"
        out[f"{col}__xz"] = g[col].transform(_xs_zscore)
    return out


def _add_composites(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    aligned_xz_cols = [f"{name}__aligned__xz" for name, _ in NEAR_GATE_FACTORS]
    out["composite_unweighted"] = out[aligned_xz_cols].mean(axis=1, skipna=True)
    weights = {
        "cumulative_taker_imbalance_5d_xs_zscore__aligned__xz": 0.041,
        "retail_long_xs_rank_inverse__aligned__xz":             0.037,
        "liquidation_imbalance_xs_zscore__aligned__xz":         0.038,
        "top_trader_long_xs_demean__aligned__xz":               0.031,
    }
    weight_sum = sum(weights.values())
    weighted = pd.Series(0.0, index=out.index)
    for col, w in weights.items():
        weighted = weighted + (w / weight_sum) * out[col].fillna(0.0)
    out["composite_ic_weighted"] = weighted
    return out


def _xs_correlation_matrix(panel: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    n = len(columns)
    accum = np.zeros((n, n), dtype="float64")
    counts = np.zeros((n, n), dtype="int64")
    for _, group in panel.groupby("date"):
        sub = group[columns].dropna()
        if len(sub) < 8:
            continue
        c = sub.rank(method="average").corr(method="pearson").reindex(index=columns, columns=columns).values
        mask = ~np.isnan(c)
        accum[mask] += c[mask]
        counts[mask] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_corr = np.where(counts > 0, accum / np.maximum(counts, 1), np.nan)
    return pd.DataFrame(mean_corr, index=columns, columns=columns)


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
        "ic_ir": float(arr.mean() / arr.std(ddof=0)) if arr.std(ddof=0) > 0 else float("nan"),
    }


def main() -> int:
    universe = _select_top_universe(TARGET_N)
    print(f"universe size: {len(universe)} ({', '.join(c['subject'] for c in universe)})")
    frames = []
    for entry in universe:
        df = _build_per_symbol_raw(entry["usdm_symbol"])
        if df.empty:
            continue
        df["subject"] = entry["subject"]
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    panel = _add_xs_features(panel)
    panel = _add_aligned_factors(panel)
    panel = _add_xs_zscore_versions(panel)
    panel = _add_composites(panel)

    aligned_xz_cols = [f"{name}__aligned__xz" for name, _ in NEAR_GATE_FACTORS]
    short_label_map = {
        "cumulative_taker_imbalance_5d_xs_zscore__aligned__xz": "+taker_5d",
        "retail_long_xs_rank_inverse__aligned__xz":             "+retail_inv",
        "liquidation_imbalance_xs_zscore__aligned__xz":         "-liq_imb",
        "top_trader_long_xs_demean__aligned__xz":               "-top_trader",
    }

    corr = _xs_correlation_matrix(panel, aligned_xz_cols)
    short_corr = corr.rename(index=short_label_map, columns=short_label_map)

    ic_targets = list(aligned_xz_cols) + ["composite_unweighted", "composite_ic_weighted"]
    ic_results: dict[str, dict[str, dict[str, float | int]]] = {}
    for feature in ic_targets:
        ic_results[feature] = {f"horizon_{h}d": _cross_sectional_rank_ic(panel, feature, h) for h in HORIZONS_TO_TEST}

    out_root = REPO_ROOT / "artifacts" / "quant_research" / "v71_exploration"
    out_root.mkdir(parents=True, exist_ok=True)
    output_path = out_root / "composite_ic.json"
    output_path.write_text(
        json.dumps(
            {
                "produced_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "universe": universe,
                "interval": INTERVAL,
                "horizons_tested_days": list(HORIZONS_TO_TEST),
                "panel_total_rows": int(len(panel)),
                "near_gate_factors_with_signs": [{"name": n, "sign": s} for n, s in NEAR_GATE_FACTORS],
                "pairwise_xs_rank_correlation": short_corr.fillna(np.nan).to_dict(orient="index"),
                "ic_results": ic_results,
            },
            indent=2,
            sort_keys=True,
            default=lambda v: None if (isinstance(v, float) and math.isnan(v)) else v,
        ),
        encoding="utf-8",
    )

    print(f"\nWritten: {output_path}\n")
    print("Pairwise cross-sectional rank correlation (mean across days):")
    print(short_corr.round(3).to_string())
    print()
    max_abs_off_diag = 0.0
    for i in range(len(aligned_xz_cols)):
        for j in range(i + 1, len(aligned_xz_cols)):
            v = abs(corr.iloc[i, j])
            if v == v and v > max_abs_off_diag:
                max_abs_off_diag = v
    print(f"max |off-diag corr| = {max_abs_off_diag:.3f} (gate: < 0.40)")
    print()

    print("IC by feature & composite:")
    headers = "  {:<28}".format("target")
    for h in HORIZONS_TO_TEST:
        headers += " {:>10} {:>7} {:>7}".format(f"IC_{h}d", f"pos_{h}d", f"IR_{h}d")
    print(headers)
    rows = []
    for feature in ic_targets:
        cells = []
        for h in HORIZONS_TO_TEST:
            stats = ic_results[feature][f"horizon_{h}d"]
            cells.append((stats["mean_ic"], stats["positive_day_rate"], stats["ic_ir"]))
        rows.append((feature, cells))
    label_map = {**short_label_map, "composite_unweighted": "COMPOSITE(eq)", "composite_ic_weighted": "COMPOSITE(IC-w)"}
    for feature, cells in rows:
        line = f"  {label_map.get(feature, feature):<28}"
        for ic, pos, ir in cells:
            line += f" {ic:>+10.4f} {pos:>7.3f} {ir:>+7.3f}"
        print(line)
    print()

    factor_gate = 0.05
    composite_gate = 0.06
    print(f"Gates: single-factor |IC_5d| >= {factor_gate}, composite |IC_5d| >= {composite_gate}, max |corr| < 0.40")
    composite_eq_5d = ic_results["composite_unweighted"]["horizon_5d"]["mean_ic"]
    composite_ic_5d = ic_results["composite_ic_weighted"]["horizon_5d"]["mean_ic"]
    composite_eq_5d_pass = abs(composite_eq_5d) >= composite_gate if composite_eq_5d == composite_eq_5d else False
    composite_ic_5d_pass = abs(composite_ic_5d) >= composite_gate if composite_ic_5d == composite_ic_5d else False
    corr_pass = max_abs_off_diag < 0.40
    print(f"  COMPOSITE(eq)    IC_5d = {composite_eq_5d:+.4f}  pass={composite_eq_5d_pass}")
    print(f"  COMPOSITE(IC-w)  IC_5d = {composite_ic_5d:+.4f}  pass={composite_ic_5d_pass}")
    print(f"  pairwise corr OK = {corr_pass} (max abs = {max_abs_off_diag:.3f})")
    overall_pass = (composite_eq_5d_pass or composite_ic_5d_pass) and corr_pass
    print(f"\n=== Overall: composite GATE PASS = {overall_pass} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
