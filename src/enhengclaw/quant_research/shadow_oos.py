"""Shadow OOS retrospective for stateless cross-sectional alpha candidates.

Replays a stateless score function day-by-day over an existing feature panel
and records per-day rank IC, long-only top-K simulated PnL, and structural-break
diagnostics. Intended for candidates whose `score = f(per-day cross-section)`
contains no learned parameters, so applying f to a historical panel is a
faithful reconstruction of what the strategy would have published live.

Output artifacts (under `<artifacts_root>/shadow_oos/<candidate_id>/<as_of>/`):
- daily_metrics.csv      one row per timestamp: rank_ic, top5_minus_bottom5,
                         long_only_top5_realized_5d_return, n_subjects
- shadow_summary.json    rolled-up metrics and inflection diagnostics
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .features import EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN


@dataclass(frozen=True)
class ShadowOOSConfig:
    candidate_id: str
    score_fn_name: str
    as_of: str
    feature_set_id: str
    feature_panel_path: Path
    target_horizon_bars: int
    top_k: int = 5
    forward_return_column: str = EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN
    universe_filter_subjects: tuple[str, ...] | None = None
    universe_max_selection_rank: int | None = None
    universe_allowed_liquidity_buckets: tuple[str, ...] | None = None


def _ensure_forward_return_column(
    panel: pd.DataFrame,
    *,
    target_horizon_bars: int,
    forward_return_column: str,
) -> pd.DataFrame:
    resolved_forward_return_column = str(forward_return_column or "").strip()
    if not resolved_forward_return_column or resolved_forward_return_column in panel.columns:
        return panel
    if resolved_forward_return_column != EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN:
        raise KeyError(f"forward return column not found on panel: {resolved_forward_return_column}")
    if "spot_close" not in panel.columns:
        raise KeyError(
            f"cannot synthesize {resolved_forward_return_column} without spot_close on the feature panel"
        )
    ordered = panel.sort_values(["subject", "timestamp_ms"]).copy()
    close = pd.to_numeric(ordered["spot_close"], errors="coerce")
    grouped_subjects = ordered["subject"].astype(str)
    execution_entry_close = close.groupby(grouped_subjects).shift(-1)
    execution_exit_close = close.groupby(grouped_subjects).shift(-(int(target_horizon_bars) + 1))
    ordered[resolved_forward_return_column] = execution_exit_close / execution_entry_close - 1.0
    return ordered.sort_index()


def _ts_zscore(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    grouped = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    mu = grouped.groupby("t")["v"].transform("mean")
    sd = grouped.groupby("t")["v"].transform("std").replace(0, np.nan)
    return ((grouped["v"] - mu) / sd).fillna(0.0)


def _ts_percentile_rank(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    grouped = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    return grouped.groupby("t")["v"].rank(method="average", pct=True).fillna(0.5)


def xs_minimal_v3_replay(frame: pd.DataFrame) -> pd.Series:
    """Stateless replay of the v83 (xs_minimal_v3) score on a feature panel."""
    rv = frame["realized_volatility_20"]
    iv = frame["intraday_realized_vol_4h_to_1d"]
    dh = frame["distance_to_high_20"]
    tt = frame["coinglass_top_trader_long_pct"]
    timestamps = frame["timestamp_ms"]

    z_rv = _ts_zscore(rv, timestamps)
    z_iv = _ts_zscore(iv, timestamps)
    z_dh = _ts_zscore(dh, timestamps)
    tt_filled = tt.fillna(tt.median() if tt.notna().any() else 50.0)
    z_tt = _ts_zscore(tt_filled, timestamps)

    raw = (-0.30 * z_rv) + (-0.25 * z_iv) + (0.25 * z_dh) + (-0.20 * z_tt)
    centered_rank = _ts_percentile_rank(raw, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


SCORE_REPLAYS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "xs_minimal_v3": xs_minimal_v3_replay,
}


def _per_day_rank_ic(scores: pd.Series, returns: pd.Series) -> float | None:
    valid = scores.notna() & returns.notna()
    if valid.sum() < 3 or scores[valid].std() == 0 or returns[valid].std() == 0:
        return None
    score_rank = scores[valid].rank(method="average")
    return_rank = returns[valid].rank(method="average")
    if score_rank.nunique(dropna=True) < 2 or return_rank.nunique(dropna=True) < 2:
        return None
    rho = score_rank.corr(return_rank)
    return None if math.isnan(float(rho)) else float(rho)


def _long_only_top_k_5d_return(
    *, scores: pd.Series, returns: pd.Series, top_k: int
) -> tuple[float, int]:
    valid = scores.notna() & returns.notna()
    if valid.sum() < top_k:
        return 0.0, int(valid.sum())
    df = pd.DataFrame({"score": scores[valid], "ret": returns[valid]})
    top = df.nlargest(top_k, "score")
    return float(top["ret"].mean()), int(valid.sum())


def _top_minus_bottom(
    *, scores: pd.Series, returns: pd.Series, top_k: int
) -> float:
    valid = scores.notna() & returns.notna()
    if valid.sum() < top_k * 2:
        return 0.0
    df = pd.DataFrame({"score": scores[valid], "ret": returns[valid]}).sort_values("score")
    return float(df.tail(top_k)["ret"].mean() - df.head(top_k)["ret"].mean())


def _long_short_top_bottom_k(
    *, scores: pd.Series, returns: pd.Series, top_k: int
) -> float:
    return _top_minus_bottom(scores=scores, returns=returns, top_k=top_k)


def _vol_weighted_top_k(
    *, scores: pd.Series, returns: pd.Series, vol: pd.Series, top_k: int
) -> float:
    valid = scores.notna() & returns.notna() & vol.notna() & (vol > 0)
    if valid.sum() < top_k:
        return 0.0
    df = pd.DataFrame({"score": scores[valid], "ret": returns[valid], "vol": vol[valid]})
    top = df.nlargest(top_k, "score").copy()
    weights = 1.0 / top["vol"]
    weights = weights / weights.sum()
    return float((top["ret"] * weights).sum())


def _quintile_spread(
    *, scores: pd.Series, returns: pd.Series, quintile: float = 0.20
) -> float:
    valid = scores.notna() & returns.notna()
    n = int(valid.sum())
    bucket_size = max(1, int(round(n * quintile)))
    if n < bucket_size * 2:
        return 0.0
    df = pd.DataFrame({"score": scores[valid], "ret": returns[valid]}).sort_values("score")
    return float(df.tail(bucket_size)["ret"].mean() - df.head(bucket_size)["ret"].mean())


def _required_feature_columns(score_fn_name: str) -> tuple[str, ...]:
    if score_fn_name == "xs_minimal_v3":
        return (
            "realized_volatility_20",
            "intraday_realized_vol_4h_to_1d",
            "distance_to_high_20",
            "coinglass_top_trader_long_pct",
        )
    raise ValueError(f"unsupported score_fn_name: {score_fn_name}")


def run_shadow_oos_retrospective(config: ShadowOOSConfig) -> dict[str, object]:
    if config.score_fn_name not in SCORE_REPLAYS:
        raise ValueError(f"unsupported score replay: {config.score_fn_name}")

    panel = pd.read_csv(config.feature_panel_path)
    panel["timestamp_ms"] = panel["timestamp_ms"].astype("int64")
    panel["date_utc"] = pd.to_datetime(panel["timestamp_ms"], unit="ms", utc=True)
    panel = _ensure_forward_return_column(
        panel,
        target_horizon_bars=config.target_horizon_bars,
        forward_return_column=config.forward_return_column,
    )
    forward_return_column = str(config.forward_return_column or EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN).strip()

    required_cols = list(_required_feature_columns(config.score_fn_name))
    needed = required_cols + [forward_return_column, "subject"]
    panel = panel.dropna(subset=needed).copy()

    if config.universe_filter_subjects:
        panel = panel[panel["subject"].isin(config.universe_filter_subjects)].copy()
    if config.universe_max_selection_rank is not None and "selection_rank" in panel.columns:
        panel = panel[panel["selection_rank"] <= config.universe_max_selection_rank].copy()
    if config.universe_allowed_liquidity_buckets and "liquidity_bucket" in panel.columns:
        panel = panel[panel["liquidity_bucket"].isin(config.universe_allowed_liquidity_buckets)].copy()

    score_fn = SCORE_REPLAYS[config.score_fn_name]
    panel["score"] = score_fn(panel)

    daily_rows: list[dict[str, object]] = []
    for ts, group in panel.groupby("timestamp_ms"):
        rank_ic = _per_day_rank_ic(group["score"], group[forward_return_column])
        top_long_5d, n_subjects = _long_only_top_k_5d_return(
            scores=group["score"], returns=group[forward_return_column], top_k=config.top_k
        )
        tmb = _top_minus_bottom(
            scores=group["score"], returns=group[forward_return_column], top_k=config.top_k
        )
        long_only_top_10, _ = _long_only_top_k_5d_return(
            scores=group["score"], returns=group[forward_return_column], top_k=10
        )
        long_short_5_5 = _long_short_top_bottom_k(
            scores=group["score"], returns=group[forward_return_column], top_k=5
        )
        long_short_10_10 = _long_short_top_bottom_k(
            scores=group["score"], returns=group[forward_return_column], top_k=10
        )
        vol_series = group.get("realized_volatility_20")
        vol_weighted_top_5 = (
            _vol_weighted_top_k(
                scores=group["score"],
                returns=group[forward_return_column],
                vol=vol_series,
                top_k=5,
            )
            if vol_series is not None
            else 0.0
        )
        quintile_20pct = _quintile_spread(
            scores=group["score"], returns=group[forward_return_column], quintile=0.20
        )
        daily_rows.append(
            {
                "timestamp_ms": int(ts),
                "date_utc": pd.Timestamp(ts, unit="ms", tz="UTC").isoformat(),
                "rank_ic": rank_ic,
                "top_minus_bottom_5d_return": tmb,
                "long_only_top_k_5d_return": top_long_5d,
                "long_only_top_10_5d_return": long_only_top_10,
                "long_short_top5_bottom5_5d_return": long_short_5_5,
                "long_short_top10_bottom10_5d_return": long_short_10_10,
                "vol_weighted_top_5_5d_return": vol_weighted_top_5,
                "quintile_spread_20pct_5d_return": quintile_20pct,
                "n_subjects": n_subjects,
            }
        )
    daily_df = pd.DataFrame(daily_rows).sort_values("timestamp_ms").reset_index(drop=True)

    rolling_30 = daily_df["rank_ic"].rolling(30, min_periods=10).mean()
    rolling_90 = daily_df["rank_ic"].rolling(90, min_periods=30).mean()
    daily_df["rank_ic_rolling_30d_mean"] = rolling_30
    daily_df["rank_ic_rolling_90d_mean"] = rolling_90

    valid_rolling = daily_df.dropna(subset=["rank_ic_rolling_90d_mean"])
    inflection_date_utc: str | None = None
    if not valid_rolling.empty:
        first_negative = valid_rolling[valid_rolling["rank_ic_rolling_90d_mean"] < 0]
        if not first_negative.empty:
            inflection_date_utc = first_negative.iloc[0]["date_utc"]

    cumulative_top_long = float(daily_df["long_only_top_k_5d_return"].sum() / max(config.target_horizon_bars, 1))
    cumulative_tmb = float(daily_df["top_minus_bottom_5d_return"].sum() / max(config.target_horizon_bars, 1))

    portfolio_constructions = {
        "long_only_top_5": "long_only_top_k_5d_return",
        "long_only_top_10": "long_only_top_10_5d_return",
        "long_short_top5_bottom5": "long_short_top5_bottom5_5d_return",
        "long_short_top10_bottom10": "long_short_top10_bottom10_5d_return",
        "vol_weighted_top_5": "vol_weighted_top_5_5d_return",
        "quintile_spread_20pct": "quintile_spread_20pct_5d_return",
    }
    construction_stats = _construction_stats_full_period(daily_df, portfolio_constructions, config.target_horizon_bars)
    construction_regime_stats = _construction_regime_stats(daily_df, portfolio_constructions)

    summary = {
        "candidate_id": config.candidate_id,
        "score_fn_name": config.score_fn_name,
        "as_of": config.as_of,
        "feature_set_id": config.feature_set_id,
        "forward_return_column": forward_return_column,
        "target_horizon_bars": config.target_horizon_bars,
        "top_k": config.top_k,
        "panel_date_range_utc": [
            daily_df["date_utc"].iloc[0] if len(daily_df) else None,
            daily_df["date_utc"].iloc[-1] if len(daily_df) else None,
        ],
        "active_day_count": int(len(daily_df)),
        "subject_count": int(panel["subject"].nunique()),
        "rank_ic_full_panel_mean": float(daily_df["rank_ic"].mean(skipna=True)),
        "rank_ic_full_panel_pos_rate": float((daily_df["rank_ic"] > 0).mean()),
        "rank_ic_first_negative_90d_rolling_date_utc": inflection_date_utc,
        "long_only_top_k_period_return_approx": cumulative_top_long,
        "top_minus_bottom_period_return_approx": cumulative_tmb,
        "structural_break_band_summary": _band_summary(daily_df),
        "portfolio_construction_full_period_stats": construction_stats,
        "portfolio_construction_regime_window_stats": construction_regime_stats,
    }

    output_root = config.feature_panel_path.parents[2] / "shadow_oos" / config.candidate_id / config.as_of
    output_root.mkdir(parents=True, exist_ok=True)
    daily_path = output_root / "daily_metrics.csv"
    summary_path = output_root / "shadow_summary.json"
    daily_df.to_csv(daily_path, index=False)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    summary["artifact_paths"] = {
        "daily_metrics_path": str(daily_path),
        "shadow_summary_path": str(summary_path),
    }
    return summary


def run_cycle_equivalent_shadow(
    config: ShadowOOSConfig,
    *,
    initial_warmup_days: int = 120,
    final_buffer_days: int = 30,
    window_stride_days: int = 30,
    test_window_days: int = 30,
    evaluation_step_bars: int = 5,
) -> dict[str, object]:
    """Replicate the cycle's walk-forward + regime_holdout sparse-window sharpe
    measurement on a stateless score function panel, evaluated under multiple
    portfolio constructions in parallel."""
    if config.score_fn_name not in SCORE_REPLAYS:
        raise ValueError(f"unsupported score replay: {config.score_fn_name}")

    panel = pd.read_csv(config.feature_panel_path)
    panel["timestamp_ms"] = panel["timestamp_ms"].astype("int64")
    panel["date_utc"] = pd.to_datetime(panel["timestamp_ms"], unit="ms", utc=True)
    panel = _ensure_forward_return_column(
        panel,
        target_horizon_bars=config.target_horizon_bars,
        forward_return_column=config.forward_return_column,
    )
    forward_return_column = str(config.forward_return_column or EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN).strip()

    required_cols = list(_required_feature_columns(config.score_fn_name))
    needed = required_cols + [forward_return_column, "subject", "realized_volatility_20"]
    panel = panel.dropna(subset=needed).copy()

    if config.universe_filter_subjects:
        panel = panel[panel["subject"].isin(config.universe_filter_subjects)].copy()
    if config.universe_max_selection_rank is not None and "selection_rank" in panel.columns:
        panel = panel[panel["selection_rank"] <= config.universe_max_selection_rank].copy()
    if config.universe_allowed_liquidity_buckets and "liquidity_bucket" in panel.columns:
        panel = panel[panel["liquidity_bucket"].isin(config.universe_allowed_liquidity_buckets)].copy()

    score_fn = SCORE_REPLAYS[config.score_fn_name]
    panel["score"] = score_fn(panel)

    timestamps_sorted = sorted(int(t) for t in panel["timestamp_ms"].drop_duplicates())
    if not timestamps_sorted:
        return {"error": "panel empty after filters"}
    panel_min = pd.Timestamp(timestamps_sorted[0], unit="ms", tz="UTC")
    panel_max = pd.Timestamp(timestamps_sorted[-1], unit="ms", tz="UTC")

    start_anchor = panel_min + pd.Timedelta(days=initial_warmup_days)
    final_anchor = panel_max - pd.Timedelta(days=final_buffer_days)

    by_ts = {ts: g for ts, g in panel.groupby("timestamp_ms")}

    constructions = ["top3_equal", "top5_equal", "top10_equal", "vol_weighted_top5", "vol_weighted_top3"]
    window_records: list[dict[str, object]] = []
    anchor = start_anchor
    while anchor <= final_anchor:
        test_start = anchor
        test_end = anchor + pd.Timedelta(days=test_window_days)
        ts_in_window = [t for t in timestamps_sorted if test_start <= pd.Timestamp(t, unit="ms", tz="UTC") < test_end]
        if len(ts_in_window) < evaluation_step_bars * 2:
            anchor = anchor + pd.Timedelta(days=window_stride_days)
            continue
        decision_ts_list = ts_in_window[::evaluation_step_bars]
        per_decision_returns: dict[str, list[float]] = {c: [] for c in constructions}
        for ts in decision_ts_list:
            group = by_ts.get(ts)
            if group is None or group.empty:
                continue
            scored = group[["subject", "score", forward_return_column, "realized_volatility_20"]].dropna(
                subset=["score", forward_return_column]
            )
            if scored.empty:
                continue
            ordered = scored.sort_values("score", ascending=False)
            for label in constructions:
                if label == "top3_equal":
                    sel = ordered.head(min(3, len(ordered)))
                    if sel.empty:
                        continue
                    per_decision_returns[label].append(float(sel[forward_return_column].mean()))
                elif label == "top5_equal":
                    sel = ordered.head(min(5, len(ordered)))
                    if sel.empty:
                        continue
                    per_decision_returns[label].append(float(sel[forward_return_column].mean()))
                elif label == "top10_equal":
                    sel = ordered.head(min(10, len(ordered)))
                    if sel.empty:
                        continue
                    per_decision_returns[label].append(float(sel[forward_return_column].mean()))
                elif label in ("vol_weighted_top5", "vol_weighted_top3"):
                    k = 5 if label == "vol_weighted_top5" else 3
                    sel = ordered.head(min(k, len(ordered))).copy()
                    if sel.empty:
                        continue
                    vol = pd.to_numeric(sel["realized_volatility_20"], errors="coerce").fillna(0.005).clip(lower=0.005)
                    inv = 1.0 / vol
                    weights = inv / inv.sum() if float(inv.sum()) > 0 else pd.Series([1.0 / len(sel)] * len(sel), index=sel.index)
                    per_decision_returns[label].append(float((sel[forward_return_column] * weights).sum()))
        record: dict[str, object] = {
            "test_start_utc": test_start.isoformat(),
            "test_end_utc": test_end.isoformat(),
            "decision_count": len(decision_ts_list),
        }
        periods_per_year = 365.25 / float(evaluation_step_bars)
        for label in constructions:
            returns = per_decision_returns[label]
            if len(returns) < 2:
                record[f"{label}_sharpe"] = None
                record[f"{label}_net_return"] = 0.0
                record[f"{label}_n_periods"] = len(returns)
                continue
            arr = np.array(returns, dtype="float64")
            mean = float(arr.mean())
            std = float(arr.std())
            sharpe = float(mean / std * math.sqrt(periods_per_year)) if std > 0 else None
            net_return = float(arr.sum())
            record[f"{label}_sharpe"] = sharpe
            record[f"{label}_net_return"] = net_return
            record[f"{label}_n_periods"] = len(returns)
        window_records.append(record)
        anchor = anchor + pd.Timedelta(days=window_stride_days)

    walk_forward_summary: dict[str, dict[str, object]] = {}
    for label in constructions:
        sharpes = [w[f"{label}_sharpe"] for w in window_records if w.get(f"{label}_sharpe") is not None]
        nets = [float(w[f"{label}_net_return"]) for w in window_records if w.get(f"{label}_net_return") is not None]
        if sharpes:
            median_sharpe = float(np.median(sharpes))
            loss_window_fraction = float(np.mean([1.0 if s < 0 else 0.0 for s in sharpes]))
            mean_net = float(np.mean(nets))
        else:
            median_sharpe = None
            loss_window_fraction = None
            mean_net = 0.0
        walk_forward_summary[label] = {
            "window_count": len(sharpes),
            "median_oos_sharpe": median_sharpe,
            "loss_window_fraction": loss_window_fraction,
            "mean_window_net_return": mean_net,
        }

    regime_summary: dict[str, dict[str, dict[str, object]]] = {}
    for regime_id, regime_start, regime_end in _REGIME_WINDOWS_UTC:
        regime_start_ts = pd.Timestamp(regime_start)
        regime_end_ts = pd.Timestamp(regime_end)
        regime_block: dict[str, dict[str, object]] = {}
        regime_window_indices = [
            i for i, w in enumerate(window_records)
            if pd.Timestamp(w["test_start_utc"]) <= regime_end_ts
            and pd.Timestamp(w["test_end_utc"]) >= regime_start_ts
        ]
        for label in constructions:
            sharpes = [
                window_records[i][f"{label}_sharpe"]
                for i in regime_window_indices
                if window_records[i].get(f"{label}_sharpe") is not None
            ]
            if sharpes:
                regime_block[label] = {
                    "window_count": len(sharpes),
                    "median_oos_sharpe": float(np.median(sharpes)),
                    "loss_window_fraction": float(np.mean([1.0 if s < 0 else 0.0 for s in sharpes])),
                }
            else:
                regime_block[label] = {"window_count": 0, "median_oos_sharpe": None, "loss_window_fraction": None}
        regime_summary[regime_id] = regime_block

    summary = {
        "candidate_id": config.candidate_id,
        "score_fn_name": config.score_fn_name,
        "as_of": config.as_of,
        "forward_return_column": forward_return_column,
        "method": "cycle_equivalent_walk_forward",
        "window_count": len(window_records),
        "evaluation_step_bars": evaluation_step_bars,
        "test_window_days": test_window_days,
        "window_stride_days": window_stride_days,
        "constructions": constructions,
        "walk_forward_summary_by_construction": walk_forward_summary,
        "regime_summary_by_construction": regime_summary,
    }

    output_root = config.feature_panel_path.parents[2] / "shadow_oos" / config.candidate_id / config.as_of
    output_root.mkdir(parents=True, exist_ok=True)
    cycle_eq_path = output_root / "cycle_equivalent_summary.json"
    cycle_eq_windows_path = output_root / "cycle_equivalent_windows.json"
    with cycle_eq_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    with cycle_eq_windows_path.open("w", encoding="utf-8") as f:
        json.dump(window_records, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    summary["artifact_paths"] = {
        "cycle_equivalent_summary_path": str(cycle_eq_path),
        "cycle_equivalent_windows_path": str(cycle_eq_windows_path),
    }
    return summary


def _construction_stats_full_period(
    daily_df: pd.DataFrame,
    constructions: dict[str, str],
    target_horizon_bars: int,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for label, column in constructions.items():
        if column not in daily_df.columns:
            continue
        series = daily_df[column].dropna()
        n = int(len(series))
        if n < 2:
            out[label] = {
                "n_days": n,
                "daily_5d_return_mean": float("nan"),
                "daily_5d_return_std": float("nan"),
                "daily_5d_sharpe": float("nan"),
                "annualized_sharpe_approx": float("nan"),
                "period_cumulative_return_approx": 0.0,
                "negative_day_fraction": float("nan"),
            }
            continue
        mean = float(series.mean())
        std = float(series.std())
        daily_sharpe = float(mean / std) if std > 0 else float("nan")
        annualized = (
            float(daily_sharpe * math.sqrt(252.0 / max(target_horizon_bars, 1)))
            if std > 0
            else float("nan")
        )
        cum = float(series.sum() / max(target_horizon_bars, 1))
        neg_frac = float((series < 0).mean())
        out[label] = {
            "n_days": n,
            "daily_5d_return_mean": mean,
            "daily_5d_return_std": std,
            "daily_5d_sharpe": daily_sharpe,
            "annualized_sharpe_approx": annualized,
            "period_cumulative_return_approx": cum,
            "negative_day_fraction": neg_frac,
        }
    return out


_REGIME_WINDOWS_UTC: tuple[tuple[str, str, str], ...] = (
    ("trend_up_2025h2", "2025-08-01T00:00:00+00:00", "2025-10-31T23:59:59+00:00"),
    ("rotation_high_vol_2025q4", "2025-11-01T00:00:00+00:00", "2026-01-31T23:59:59+00:00"),
    ("drawdown_rebound_2026ytd", "2026-02-01T00:00:00+00:00", "2026-04-30T23:59:59+00:00"),
)


def _construction_regime_stats(
    daily_df: pd.DataFrame,
    constructions: dict[str, str],
) -> dict[str, dict[str, dict[str, float]]]:
    if daily_df.empty:
        return {}
    df = daily_df.copy()
    df["ts"] = pd.to_datetime(df["date_utc"])
    out: dict[str, dict[str, dict[str, float]]] = {}
    for regime_id, start, end in _REGIME_WINDOWS_UTC:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        regime_slice = df[(df["ts"] >= start_ts) & (df["ts"] <= end_ts)]
        regime_block: dict[str, dict[str, float]] = {}
        for label, column in constructions.items():
            if column not in regime_slice.columns:
                continue
            series = regime_slice[column].dropna()
            n = int(len(series))
            if n < 2:
                regime_block[label] = {
                    "n_days": n,
                    "daily_5d_return_mean": float("nan"),
                    "daily_5d_sharpe": float("nan"),
                    "negative_day_fraction": float("nan"),
                }
                continue
            mean = float(series.mean())
            std = float(series.std())
            sharpe = float(mean / std) if std > 0 else float("nan")
            neg_frac = float((series < 0).mean())
            regime_block[label] = {
                "n_days": n,
                "daily_5d_return_mean": mean,
                "daily_5d_sharpe": sharpe,
                "negative_day_fraction": neg_frac,
            }
        out[regime_id] = regime_block
    return out


def _band_summary(daily_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Slice daily IC by year-quarter to make the structural break visible."""
    if daily_df.empty:
        return {}
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date_utc"]).dt.tz_convert(None)
    df["yq"] = df["date"].dt.to_period("Q").astype(str)
    out: dict[str, dict[str, float]] = {}
    for yq, g in df.groupby("yq"):
        ic_mean = float(g["rank_ic"].mean(skipna=True))
        ic_pos_rate = float((g["rank_ic"] > 0).mean())
        long_top = float(g["long_only_top_k_5d_return"].mean(skipna=True))
        out[yq] = {
            "n_days": int(len(g)),
            "rank_ic_mean": ic_mean,
            "rank_ic_positive_rate": ic_pos_rate,
            "avg_daily_long_only_top_k_5d_return": long_top,
        }
    return out
