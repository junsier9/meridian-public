"""SP-L Stage 0: orderbook / inventory risk transfer event study."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_extended import (  # noqa: E402
    load_extended_rows,
    resolve_extended_external_root,
)
from enhengclaw.quant_research.features import (  # noqa: E402
    build_cross_sectional_feature_bundle,
    xs_alpha_ontology_v6_h10d_score,
)
from enhengclaw.quant_research.lab import _apply_liquid_perp_core_20  # noqa: E402


CONTRACT_VERSION = "quant_sp_l_orderbook_inventory_event_study.v1"
DEFAULT_HORIZONS = (3, 5, 10)
DEFAULT_MAJOR_SUBJECTS = ("BTC", "ETH")
DEFAULT_MIN_LISTING_AGE_DAYS = 60

PUMP_SIGMA_THRESHOLD = 2.0
PUMP_RANGE_Z_THRESHOLD = 1.0
PUMP_QV_EXPANSION_THRESHOLD = 1.5
DOWNSIDE_SIGMA_THRESHOLD = -2.0
DOWNSIDE_LIQ_IMB_MIN = 0.15

MIN_HOURLY_BARS_PER_DAY = 16
BID_DEPTH_Z_LOW = -0.50
TOTAL_DEPTH_Z_LOW = -0.50
BID_DEPTH_Z_HIGH = 0.50
ASK_HEAVY_SHARE_MIN = 0.60
BID_HEAVY_SHARE_MIN = 0.60
OB_IMB_MEAN_NEG_MAX = -0.05
OB_IMB_MEAN_POS_MIN = 0.05
BID_REPLENISHMENT_RATIO_MAX = 0.95
NET_TAKER_TO_DEPTH_Z_MIN = 0.50


def _discover_latest_daily_features_artifact(features_root: Path, *, as_of: str) -> Path:
    pattern = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-cross-sectional-daily-1d-features-v1$")
    candidates: list[tuple[str, Path]] = []
    for child in features_root.iterdir():
        if not child.is_dir():
            continue
        match = pattern.match(child.name)
        if not match:
            continue
        date_text = match.group("date")
        if date_text > as_of:
            continue
        artifact = child / "features.csv.gz"
        if artifact.exists():
            candidates.append((date_text, artifact))
    if not candidates:
        raise FileNotFoundError(
            f"no daily features artifact matching '*-cross-sectional-daily-1d-features-v1' under {features_root}"
        )
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _t_stat(values: pd.Series) -> float:
    series = pd.to_numeric(values, errors="coerce").dropna()
    if len(series) < 2:
        return 0.0
    std = float(series.std())
    if std <= 0:
        return 0.0
    return float(series.mean() * np.sqrt(len(series)) / std)


def _require_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise RuntimeError(f"required columns missing from artifact: {missing}")


def _load_daily_panel(
    features_artifact: Path,
    *,
    horizons: Iterable[int],
    min_listing_age_days: int,
) -> pd.DataFrame:
    frame = pd.read_csv(features_artifact, compression="gzip")
    _require_columns(
        frame,
        (
            "subject",
            "timestamp_ms",
            "date_utc",
            "liquidity_bucket",
            "spot_close",
            "return_1",
            "realized_volatility_20",
            "abnormal_range_z_60",
            "quote_volume_expansion",
            "funding_zscore_20",
            "oi_change_5",
            "coinglass_liquidation_imbalance_24h",
            "coinglass_taker_imbalance_5d_sum",
            "perp_execution_eligible",
            "listing_age_days_as_of",
            "perp_quote_volume_usd",
        ),
    )
    numeric_columns = (
        "spot_close",
        "return_1",
        "realized_volatility_20",
        "abnormal_range_z_60",
        "quote_volume_expansion",
        "funding_zscore_20",
        "oi_change_5",
        "coinglass_liquidation_imbalance_24h",
        "coinglass_taker_imbalance_5d_sum",
        "distance_to_high_5",
        "perp_quote_volume_usd",
    )
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    eligible = frame["perp_execution_eligible"].fillna(False).astype(bool)
    if min_listing_age_days > 0:
        eligible &= frame["listing_age_days_as_of"].fillna(0).ge(min_listing_age_days)
    eligible &= frame["spot_close"].fillna(0).gt(0)
    frame = frame.loc[eligible].copy()
    frame = frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    frame["pump_return_sigma"] = frame["return_1"] / frame["realized_volatility_20"].replace(0.0, np.nan)
    for horizon in horizons:
        frame[f"forward_{horizon}d_log_return"] = frame.groupby("subject")["spot_close"].transform(
            lambda close: np.log(close.shift(-horizon) / close)
        )
    return frame


def _build_risk_frame(panel: pd.DataFrame, *, horizons: Iterable[int]) -> pd.DataFrame:
    max_horizon = max(int(h) for h in horizons)
    features = build_cross_sectional_feature_bundle(panel, target_shift_bars=max_horizon)["dataframe"].copy()
    features = features.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    for horizon in horizons:
        features[f"forward_{horizon}d_log_return"] = features.groupby("subject")["spot_close"].transform(
            lambda close: np.log(close.shift(-horizon) / close)
        )
    return _apply_liquid_perp_core_20(features)


def _resolve_subject_to_coinglass_symbol(subjects: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    root = resolve_extended_external_root()
    available = {path.name for path in root.iterdir() if path.is_dir()} if root.exists() else set()
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for subject in sorted({str(item) for item in subjects}):
        exact = f"{subject}USDT"
        if exact in available:
            mapping[subject] = exact
            continue
        if subject in available:
            mapping[subject] = subject
            continue
        pattern = re.compile(rf"^(?:1000)?{re.escape(subject)}USDT$")
        matches = sorted(name for name in available if pattern.match(name))
        if len(matches) == 1:
            mapping[subject] = matches[0]
            continue
        if exact in matches:
            mapping[subject] = exact
            continue
        missing.append(subject)
    return mapping, missing


def _zscore_vs_history(current: pd.Series, *, window: int, min_periods: int) -> pd.Series:
    baseline_mean = current.rolling(window, min_periods=min_periods).mean().shift(1)
    baseline_std = current.rolling(window, min_periods=min_periods).std().shift(1)
    z = (current - baseline_mean) / baseline_std.replace(0.0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan)


def _build_subject_orderbook_state(subject: str, symbol: str) -> pd.DataFrame:
    rows = load_extended_rows(symbol=symbol, interval="1h")
    if not rows:
        return pd.DataFrame()
    records: list[dict[str, float | int | str]] = []
    for raw in rows:
        try:
            ts = int(raw.get("open_time_ms", 0))
        except (TypeError, ValueError):
            continue

        def _f(name: str) -> float:
            value = raw.get(name)
            text = str(value or "").strip()
            if not text:
                return float("nan")
            try:
                return float(text)
            except ValueError:
                return float("nan")

        records.append(
            {
                "subject": subject,
                "timestamp_ms": ts,
                "date_utc": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat(),
                "orderbook_bids_usd": _f("orderbook_bids_usd"),
                "orderbook_asks_usd": _f("orderbook_asks_usd"),
                "orderbook_bids_quantity": _f("orderbook_bids_quantity"),
                "orderbook_asks_quantity": _f("orderbook_asks_quantity"),
                "taker_buy_volume_usd": _f("taker_buy_volume_usd"),
                "taker_sell_volume_usd": _f("taker_sell_volume_usd"),
                "long_liquidation_usd": _f("long_liquidation_usd"),
                "short_liquidation_usd": _f("short_liquidation_usd"),
            }
        )
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame
    frame = frame.sort_values("timestamp_ms").reset_index(drop=True)
    eps = 1e-9
    frame["ob_total_depth_usd"] = frame["orderbook_bids_usd"].fillna(0.0) + frame["orderbook_asks_usd"].fillna(0.0)
    frame["ob_total_depth_quantity"] = (
        frame["orderbook_bids_quantity"].fillna(0.0) + frame["orderbook_asks_quantity"].fillna(0.0)
    )
    frame["ob_imb_1h"] = (
        frame["orderbook_bids_usd"].fillna(0.0) - frame["orderbook_asks_usd"].fillna(0.0)
    ) / (frame["ob_total_depth_usd"] + eps)
    frame["taker_net_usd"] = frame["taker_buy_volume_usd"].fillna(0.0) - frame["taker_sell_volume_usd"].fillna(0.0)
    frame["taker_imb_1h"] = frame["taker_net_usd"] / (
        frame["taker_buy_volume_usd"].fillna(0.0) + frame["taker_sell_volume_usd"].fillna(0.0) + eps
    )
    frame["taker_net_to_depth_1h"] = frame["taker_net_usd"] / (frame["ob_total_depth_usd"] + eps)
    frame["day_open_ms"] = (frame["timestamp_ms"] // 86_400_000) * 86_400_000

    daily = frame.groupby("day_open_ms").agg(
        date_utc=("date_utc", "last"),
        hourly_bar_count=("timestamp_ms", "size"),
        ob_bid_depth_mean_24h=("orderbook_bids_usd", "mean"),
        ob_ask_depth_mean_24h=("orderbook_asks_usd", "mean"),
        ob_total_depth_mean_24h=("ob_total_depth_usd", "mean"),
        ob_total_depth_min_24h=("ob_total_depth_usd", "min"),
        ob_imb_mean_24h=("ob_imb_1h", "mean"),
        ob_imb_last_24h=("ob_imb_1h", "last"),
        ob_bid_heavy_share_24h=("ob_imb_1h", lambda s: float((pd.to_numeric(s, errors="coerce") > 0).mean())),
        ob_ask_heavy_share_24h=("ob_imb_1h", lambda s: float((pd.to_numeric(s, errors="coerce") < 0).mean())),
        taker_buy_sum_24h=("taker_buy_volume_usd", "sum"),
        taker_sell_sum_24h=("taker_sell_volume_usd", "sum"),
        taker_net_sum_24h=("taker_net_usd", "sum"),
        taker_net_to_depth_mean_24h=("taker_net_to_depth_1h", "mean"),
        long_liquidation_sum_24h=("long_liquidation_usd", "sum"),
        short_liquidation_sum_24h=("short_liquidation_usd", "sum"),
    ).reset_index()

    daily = daily.rename(columns={"day_open_ms": "timestamp_ms"})
    daily["subject"] = subject
    daily = daily.sort_values("timestamp_ms").reset_index(drop=True)
    daily["ob_bid_depth_mean_z30"] = _zscore_vs_history(daily["ob_bid_depth_mean_24h"], window=30, min_periods=10)
    daily["ob_total_depth_mean_z30"] = _zscore_vs_history(
        daily["ob_total_depth_mean_24h"], window=30, min_periods=10
    )
    daily["taker_net_to_depth_mean_z30"] = _zscore_vs_history(
        daily["taker_net_to_depth_mean_24h"], window=30, min_periods=10
    )
    daily["ob_bid_replenishment_ratio_1d"] = daily["ob_bid_depth_mean_24h"] / daily[
        "ob_bid_depth_mean_24h"
    ].shift(1).replace(0.0, np.nan)
    daily["ob_total_depth_replenishment_ratio_1d"] = daily["ob_total_depth_mean_24h"] / daily[
        "ob_total_depth_mean_24h"
    ].shift(1).replace(0.0, np.nan)
    daily["ob_buy_to_depth_24h"] = daily["taker_buy_sum_24h"] / daily["ob_total_depth_mean_24h"].replace(0.0, np.nan)
    daily["ob_sell_to_depth_24h"] = daily["taker_sell_sum_24h"] / daily["ob_total_depth_mean_24h"].replace(0.0, np.nan)
    daily["ob_net_taker_to_depth_24h"] = daily["taker_net_sum_24h"] / daily[
        "ob_total_depth_mean_24h"
    ].replace(0.0, np.nan)
    return daily


def _build_orderbook_state_panel(subjects: Iterable[str]) -> tuple[pd.DataFrame, dict[str, object]]:
    subject_to_symbol, missing_subjects = _resolve_subject_to_coinglass_symbol(subjects)
    frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []
    for subject in sorted(subject_to_symbol):
        symbol = subject_to_symbol[subject]
        state = _build_subject_orderbook_state(subject=subject, symbol=symbol)
        if state.empty:
            coverage_rows.append({"subject": subject, "symbol": symbol, "status": "empty"})
            continue
        coverage_rows.append(
            {
                "subject": subject,
                "symbol": symbol,
                "status": "ok",
                "n_days": int(len(state)),
                "date_min": str(state["date_utc"].min()),
                "date_max": str(state["date_utc"].max()),
                "coverage_ge_16h_fraction": float((state["hourly_bar_count"] >= MIN_HOURLY_BARS_PER_DAY).mean()),
            }
        )
        frames.append(state)
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    summary = {
        "mapped_subject_count": int(len(subject_to_symbol)),
        "missing_subjects": missing_subjects,
        "covered_subject_count": int(panel["subject"].nunique()) if not panel.empty else 0,
        "coverage_rows": coverage_rows,
    }
    return panel, summary


def _attach_baseline_short_boundary(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["baseline_score"] = xs_alpha_ontology_v6_h10d_score(out)
    out = out.sort_values(["timestamp_ms", "baseline_score", "subject"], ascending=[True, True, True]).reset_index(
        drop=True
    )
    out["baseline_short_rank"] = out.groupby("timestamp_ms").cumcount() + 1
    out["is_baseline_bottom3"] = out["baseline_short_rank"].le(3)
    out["is_baseline_bottom6"] = out["baseline_short_rank"].le(6)
    out["is_boundary_candidate"] = out["baseline_short_rank"].between(4, 6)
    return out


def _build_event_rules(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    coverage_ok = frame["hourly_bar_count"].fillna(0).ge(MIN_HOURLY_BARS_PER_DAY)
    pump_core = (
        coverage_ok
        & frame["pump_return_sigma"].gt(PUMP_SIGMA_THRESHOLD)
        & frame["abnormal_range_z_60"].gt(PUMP_RANGE_Z_THRESHOLD)
        & frame["quote_volume_expansion"].gt(PUMP_QV_EXPANSION_THRESHOLD)
    )
    downside_shock = (
        coverage_ok
        & frame["pump_return_sigma"].lt(DOWNSIDE_SIGMA_THRESHOLD)
        & frame["coinglass_liquidation_imbalance_24h"].gt(DOWNSIDE_LIQ_IMB_MIN)
    )
    pump_bid_replenishment_failure = (
        pump_core
        & frame["ob_bid_depth_mean_z30"].lt(BID_DEPTH_Z_LOW)
        & frame["ob_bid_replenishment_ratio_1d"].lt(BID_REPLENISHMENT_RATIO_MAX)
    )
    pump_ask_pressure_persistence = (
        pump_core
        & frame["ob_ask_heavy_share_24h"].gt(ASK_HEAVY_SHARE_MIN)
        & frame["ob_imb_mean_24h"].lt(OB_IMB_MEAN_NEG_MAX)
    )
    thin_book_taker_exhaustion = (
        pump_core
        & frame["ob_total_depth_mean_z30"].lt(TOTAL_DEPTH_Z_LOW)
        & frame["taker_net_to_depth_mean_z30"].gt(NET_TAKER_TO_DEPTH_Z_MIN)
    )
    cascade_bid_absorption_rebound = (
        downside_shock
        & frame["ob_bid_depth_mean_z30"].gt(BID_DEPTH_Z_HIGH)
        & frame["ob_bid_heavy_share_24h"].gt(BID_HEAVY_SHARE_MIN)
        & frame["ob_imb_mean_24h"].gt(OB_IMB_MEAN_POS_MIN)
    )
    boundary_fragile_orderbook = (
        coverage_ok
        & frame["is_boundary_candidate"]
        & (
            (
                frame["ob_bid_depth_mean_z30"].lt(BID_DEPTH_Z_LOW)
                & frame["ob_bid_replenishment_ratio_1d"].lt(BID_REPLENISHMENT_RATIO_MAX)
            )
            | (
                frame["ob_ask_heavy_share_24h"].gt(ASK_HEAVY_SHARE_MIN)
                & frame["ob_imb_mean_24h"].lt(OB_IMB_MEAN_NEG_MAX)
            )
        )
    )
    selected_short_supportive_replenishment = (
        coverage_ok
        & frame["is_baseline_bottom3"]
        & frame["ob_bid_depth_mean_z30"].gt(BID_DEPTH_Z_HIGH)
        & frame["ob_bid_heavy_share_24h"].gt(BID_HEAVY_SHARE_MIN)
        & frame["ob_imb_mean_24h"].gt(OB_IMB_MEAN_POS_MIN)
    )
    return {
        "pump_core": {
            "expected_forward_sign": "negative",
            "definition": (
                "coverage_ok AND pump_return_sigma > 2.0 AND abnormal_range_z_60 > 1.0 "
                "AND quote_volume_expansion > 1.5"
            ),
            "mask": pump_core.fillna(False),
        },
        "pump_bid_replenishment_failure": {
            "expected_forward_sign": "negative",
            "definition": (
                "pump_core AND ob_bid_depth_mean_z30 < -0.5 AND ob_bid_replenishment_ratio_1d < 0.95"
            ),
            "mask": pump_bid_replenishment_failure.fillna(False),
        },
        "pump_ask_pressure_persistence": {
            "expected_forward_sign": "negative",
            "definition": (
                "pump_core AND ob_ask_heavy_share_24h > 0.60 AND ob_imb_mean_24h < -0.05"
            ),
            "mask": pump_ask_pressure_persistence.fillna(False),
        },
        "thin_book_taker_exhaustion": {
            "expected_forward_sign": "negative",
            "definition": (
                "pump_core AND ob_total_depth_mean_z30 < -0.5 AND taker_net_to_depth_mean_z30 > 0.5"
            ),
            "mask": thin_book_taker_exhaustion.fillna(False),
        },
        "cascade_bid_absorption_rebound": {
            "expected_forward_sign": "positive",
            "definition": (
                "downside_shock AND ob_bid_depth_mean_z30 > 0.5 AND ob_bid_heavy_share_24h > 0.60 "
                "AND ob_imb_mean_24h > 0.05"
            ),
            "mask": cascade_bid_absorption_rebound.fillna(False),
        },
        "boundary_fragile_orderbook": {
            "expected_forward_sign": "negative",
            "definition": (
                "is_boundary_candidate AND ((weak bid replenishment) OR (persistent ask pressure))"
            ),
            "mask": boundary_fragile_orderbook.fillna(False),
        },
        "selected_short_supportive_replenishment": {
            "expected_forward_sign": "positive",
            "definition": (
                "is_baseline_bottom3 AND ob_bid_depth_mean_z30 > 0.5 AND ob_bid_heavy_share_24h > 0.60 "
                "AND ob_imb_mean_24h > 0.05"
            ),
            "mask": selected_short_supportive_replenishment.fillna(False),
        },
    }


def _build_cohort_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    ex_majors = ~frame["subject"].isin(DEFAULT_MAJOR_SUBJECTS)
    top = frame["liquidity_bucket"].eq("top_liquidity")
    mid = frame["liquidity_bucket"].eq("mid_liquidity")
    return {
        "all_core20": pd.Series(True, index=frame.index),
        "ex_majors": ex_majors,
        "top_liquidity_ex_majors": top & ex_majors,
        "mid_liquidity": mid,
        "mid_liquidity_ex_majors": mid & ex_majors,
        "baseline_bottom6_pool": frame["is_baseline_bottom6"].fillna(False),
        "boundary_candidates": frame["is_boundary_candidate"].fillna(False),
        "baseline_bottom3_shorts": frame["is_baseline_bottom3"].fillna(False),
    }


def _event_stats_for_horizon(
    frame: pd.DataFrame,
    *,
    event_mask: pd.Series,
    cohort_mask: pd.Series,
    horizon: int,
    expected_forward_sign: str,
) -> dict[str, object]:
    forward_column = f"forward_{horizon}d_log_return"
    eligible = cohort_mask & frame[forward_column].notna()
    events = eligible & event_mask
    if int(events.sum()) == 0:
        return {"status": "no_events", "n_events": 0}
    event_rows = frame.loc[events, ["subject", "timestamp_ms", forward_column]].copy()
    raw_returns = pd.to_numeric(event_rows[forward_column], errors="coerce").dropna()
    if raw_returns.empty:
        return {"status": "no_forward_returns", "n_events": int(events.sum())}
    non_events = eligible & ~event_mask
    subject_baseline = (
        frame.loc[non_events, ["subject", forward_column]]
        .dropna(subset=[forward_column])
        .groupby("subject")[forward_column]
        .mean()
    )
    event_rows["subject_baseline"] = event_rows["subject"].map(subject_baseline)
    event_rows["subject_abnormal"] = event_rows[forward_column] - event_rows["subject_baseline"]
    abnormal = pd.to_numeric(event_rows["subject_abnormal"], errors="coerce").dropna()
    date_means = (
        frame.loc[eligible, ["timestamp_ms", forward_column]]
        .dropna(subset=[forward_column])
        .groupby("timestamp_ms")[forward_column]
        .mean()
    )
    event_rows["same_day_cohort_mean"] = event_rows["timestamp_ms"].map(date_means)
    event_rows["same_day_excess"] = event_rows[forward_column] - event_rows["same_day_cohort_mean"]
    same_day_excess = pd.to_numeric(event_rows["same_day_excess"], errors="coerce").dropna()
    expected_sign = -1.0 if expected_forward_sign == "negative" else 1.0
    signed_trade_return = expected_sign * raw_returns
    signed_abnormal = expected_sign * abnormal if len(abnormal) else abnormal
    subject_event_counts = frame.loc[events, "subject"].value_counts().head(10).to_dict()
    return {
        "status": "ok",
        "n_events": int(raw_returns.shape[0]),
        "n_subjects": int(frame.loc[events, "subject"].nunique()),
        "event_rate_within_cohort": float(raw_returns.shape[0] / max(int(eligible.sum()), 1)),
        "expected_forward_sign": expected_forward_sign,
        "raw_forward_return": {
            "mean": float(raw_returns.mean()),
            "median": float(raw_returns.median()),
            "std": float(raw_returns.std()) if len(raw_returns) > 1 else 0.0,
            "t_stat": _t_stat(raw_returns),
            "negative_rate": float((raw_returns < 0).mean()),
            "positive_rate": float((raw_returns > 0).mean()),
            "p10": float(raw_returns.quantile(0.10)),
            "p90": float(raw_returns.quantile(0.90)),
        },
        "signed_trade_view": {
            "mean": float(signed_trade_return.mean()),
            "median": float(signed_trade_return.median()),
            "t_stat": _t_stat(signed_trade_return),
            "expected_direction_rate": float((signed_trade_return > 0).mean()),
        },
        "subject_abnormal_return": {
            "n_events_with_baseline": int(abnormal.shape[0]),
            "mean": float(abnormal.mean()) if len(abnormal) else 0.0,
            "median": float(abnormal.median()) if len(abnormal) else 0.0,
            "t_stat": _t_stat(abnormal),
        },
        "signed_subject_abnormal_view": {
            "n_events_with_baseline": int(signed_abnormal.shape[0]) if len(abnormal) else 0,
            "mean": float(signed_abnormal.mean()) if len(abnormal) else 0.0,
            "median": float(signed_abnormal.median()) if len(abnormal) else 0.0,
            "t_stat": _t_stat(signed_abnormal) if len(abnormal) else 0.0,
            "expected_direction_rate": float((signed_abnormal > 0).mean()) if len(abnormal) else 0.0,
        },
        "same_day_cohort_excess_return": {
            "n_events_with_baseline": int(same_day_excess.shape[0]),
            "mean": float(same_day_excess.mean()) if len(same_day_excess) else 0.0,
            "median": float(same_day_excess.median()) if len(same_day_excess) else 0.0,
            "t_stat": _t_stat(same_day_excess),
        },
        "top_subject_event_counts": {str(k): int(v) for k, v in subject_event_counts.items()},
    }


def _build_summary(
    frame: pd.DataFrame,
    *,
    event_rules: dict[str, dict[str, object]],
    cohort_masks: dict[str, pd.Series],
    horizons: Iterable[int],
) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for rule_name, rule in event_rules.items():
        event_mask = pd.Series(rule["mask"], index=frame.index).fillna(False)
        out[rule_name] = {
            "definition": str(rule["definition"]),
            "expected_forward_sign": str(rule["expected_forward_sign"]),
            "total_event_rows": int(event_mask.sum()),
            "cohorts": {},
        }
        for cohort_name, cohort_mask in cohort_masks.items():
            cohort_summary: dict[str, object] = {}
            for horizon in horizons:
                cohort_summary[f"h{horizon}d"] = _event_stats_for_horizon(
                    frame,
                    event_mask=event_mask,
                    cohort_mask=cohort_mask,
                    horizon=horizon,
                    expected_forward_sign=str(rule["expected_forward_sign"]),
                )
            out[rule_name]["cohorts"][cohort_name] = cohort_summary
    return out


def _build_event_rows_export(
    frame: pd.DataFrame,
    *,
    event_rules: dict[str, dict[str, object]],
) -> pd.DataFrame:
    export_columns = [
        "date_utc",
        "timestamp_ms",
        "subject",
        "liquidity_bucket",
        "baseline_short_rank",
        "is_baseline_bottom3",
        "is_baseline_bottom6",
        "is_boundary_candidate",
        "return_1",
        "pump_return_sigma",
        "abnormal_range_z_60",
        "quote_volume_expansion",
        "coinglass_liquidation_imbalance_24h",
        "coinglass_taker_imbalance_5d_sum",
        "ob_bid_depth_mean_24h",
        "ob_ask_depth_mean_24h",
        "ob_total_depth_mean_24h",
        "ob_total_depth_min_24h",
        "ob_imb_mean_24h",
        "ob_imb_last_24h",
        "ob_bid_heavy_share_24h",
        "ob_ask_heavy_share_24h",
        "ob_bid_depth_mean_z30",
        "ob_total_depth_mean_z30",
        "ob_bid_replenishment_ratio_1d",
        "taker_net_to_depth_mean_24h",
        "taker_net_to_depth_mean_z30",
        "forward_3d_log_return",
        "forward_5d_log_return",
        "forward_10d_log_return",
    ]
    rows: list[pd.DataFrame] = []
    for rule_name, rule in event_rules.items():
        mask = pd.Series(rule["mask"], index=frame.index).fillna(False)
        event_rows = frame.loc[mask, export_columns].copy()
        if event_rows.empty:
            continue
        event_rows.insert(0, "expected_forward_sign", str(rule["expected_forward_sign"]))
        event_rows.insert(0, "event_rule", rule_name)
        rows.append(event_rows)
    if not rows:
        return pd.DataFrame(columns=["event_rule", "expected_forward_sign", *export_columns])
    return pd.concat(rows, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-L Stage 0 orderbook inventory event study.")
    parser.add_argument("--as-of", default=datetime.now(tz=timezone.utc).date().isoformat())
    parser.add_argument("--features", type=Path, default=None)
    parser.add_argument(
        "--features-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "features",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    parser.add_argument("--min-listing-age-days", type=int, default=DEFAULT_MIN_LISTING_AGE_DAYS)
    args = parser.parse_args(argv)

    features_artifact = (
        args.features.expanduser().resolve()
        if args.features is not None
        else _discover_latest_daily_features_artifact(
            args.features_root.expanduser().resolve(),
            as_of=str(args.as_of),
        )
    )
    horizons = list(DEFAULT_HORIZONS)

    print(f"=== SP-L Stage 0: loading daily features from {features_artifact}")
    panel = _load_daily_panel(
        features_artifact,
        horizons=horizons,
        min_listing_age_days=args.min_listing_age_days,
    )
    print(f"  eligible daily panel rows: {len(panel)}")
    print(f"  subjects: {panel['subject'].nunique()}")
    print(f"  date range: {panel['date_utc'].min()} -> {panel['date_utc'].max()}")
    print()

    risk_frame = _build_risk_frame(panel, horizons=horizons)
    print("=== Baseline risk frame (liquid_perp_core_20) ===")
    print(f"  rows: {len(risk_frame)}")
    print(f"  subjects ever selected: {risk_frame['subject'].nunique()}")
    print(f"  date range: {risk_frame['date_utc'].min()} -> {risk_frame['date_utc'].max()}")
    print()

    subjects = tuple(sorted(risk_frame["subject"].astype(str).unique()))
    print("=== Loading 1h orderbook state panel ===")
    orderbook_panel, orderbook_summary = _build_orderbook_state_panel(subjects)
    print(f"  mapped subjects: {orderbook_summary['mapped_subject_count']}")
    print(f"  covered subjects: {orderbook_summary['covered_subject_count']}")
    print(f"  missing subjects: {len(orderbook_summary['missing_subjects'])}")
    if orderbook_summary["missing_subjects"]:
        print(f"  missing list: {', '.join(orderbook_summary['missing_subjects'])}")
    print()

    if orderbook_panel.empty:
        raise RuntimeError("orderbook state panel is empty; cannot run MF-01 study")

    state_columns = [
        "subject",
        "timestamp_ms",
        "date_utc",
        "hourly_bar_count",
        "ob_bid_depth_mean_24h",
        "ob_ask_depth_mean_24h",
        "ob_total_depth_mean_24h",
        "ob_total_depth_min_24h",
        "ob_imb_mean_24h",
        "ob_imb_last_24h",
        "ob_bid_heavy_share_24h",
        "ob_ask_heavy_share_24h",
        "taker_buy_sum_24h",
        "taker_sell_sum_24h",
        "taker_net_sum_24h",
        "taker_net_to_depth_mean_24h",
        "long_liquidation_sum_24h",
        "short_liquidation_sum_24h",
        "ob_bid_depth_mean_z30",
        "ob_total_depth_mean_z30",
        "taker_net_to_depth_mean_z30",
        "ob_bid_replenishment_ratio_1d",
        "ob_total_depth_replenishment_ratio_1d",
        "ob_buy_to_depth_24h",
        "ob_sell_to_depth_24h",
        "ob_net_taker_to_depth_24h",
    ]
    study_frame = risk_frame.merge(orderbook_panel[state_columns], on=["subject", "timestamp_ms", "date_utc"], how="left")
    study_frame = _attach_baseline_short_boundary(study_frame)

    event_rules = _build_event_rules(study_frame)
    cohort_masks = _build_cohort_masks(study_frame)
    summary = _build_summary(
        study_frame,
        event_rules=event_rules,
        cohort_masks=cohort_masks,
        horizons=horizons,
    )

    print("=== Event counts by rule ===")
    for rule_name, rule in event_rules.items():
        count = int(pd.Series(rule["mask"], index=study_frame.index).fillna(False).sum())
        print(f"  {rule_name:36s} {count:5d}")
    print()

    print("=== Key Stage 0 readout ===")
    key_pairs = [
        ("pump_bid_replenishment_failure", "all_core20"),
        ("pump_ask_pressure_persistence", "all_core20"),
        ("thin_book_taker_exhaustion", "all_core20"),
        ("boundary_fragile_orderbook", "boundary_candidates"),
        ("selected_short_supportive_replenishment", "baseline_bottom3_shorts"),
        ("cascade_bid_absorption_rebound", "baseline_bottom3_shorts"),
    ]
    for rule_name, cohort_name in key_pairs:
        block = summary.get(rule_name, {}).get("cohorts", {}).get(cohort_name, {})
        line = [f"{rule_name:36s}", f"cohort={cohort_name}"]
        for horizon in horizons:
            item = block.get(f"h{horizon}d", {})
            if item.get("status") != "ok":
                line.append(f"h{horizon}=NA")
                continue
            raw = item["raw_forward_return"]
            signed = item["signed_trade_view"]
            line.append(
                f"h{horizon}: n={item['n_events']} raw={raw['mean']:+.4f} exp={signed['mean']:+.4f} hit={signed['expected_direction_rate']:.3f}"
            )
        print("  " + "  ".join(line))

    out_dir = args.output_dir / str(args.as_of)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "orderbook_inventory_event_study.json"
    events_path = out_dir / "orderbook_inventory_event_rows.csv"
    state_path = out_dir / "orderbook_inventory_daily_state.csv"

    output_payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "features_artifact": str(features_artifact),
        "major_subjects": list(DEFAULT_MAJOR_SUBJECTS),
        "thresholds": {
            "min_listing_age_days": int(args.min_listing_age_days),
            "pump_sigma_threshold": PUMP_SIGMA_THRESHOLD,
            "pump_range_z_threshold": PUMP_RANGE_Z_THRESHOLD,
            "pump_quote_volume_expansion_threshold": PUMP_QV_EXPANSION_THRESHOLD,
            "downside_sigma_threshold": DOWNSIDE_SIGMA_THRESHOLD,
            "downside_liq_imbalance_min": DOWNSIDE_LIQ_IMB_MIN,
            "min_hourly_bars_per_day": MIN_HOURLY_BARS_PER_DAY,
            "bid_depth_z_low": BID_DEPTH_Z_LOW,
            "total_depth_z_low": TOTAL_DEPTH_Z_LOW,
            "bid_depth_z_high": BID_DEPTH_Z_HIGH,
            "ask_heavy_share_min": ASK_HEAVY_SHARE_MIN,
            "bid_heavy_share_min": BID_HEAVY_SHARE_MIN,
            "orderbook_imb_mean_negative_max": OB_IMB_MEAN_NEG_MAX,
            "orderbook_imb_mean_positive_min": OB_IMB_MEAN_POS_MIN,
            "bid_replenishment_ratio_max": BID_REPLENISHMENT_RATIO_MAX,
            "net_taker_to_depth_z_min": NET_TAKER_TO_DEPTH_Z_MIN,
        },
        "universe": {
            "risk_frame_rows": int(len(study_frame)),
            "risk_frame_subjects": int(study_frame["subject"].nunique()),
            "risk_frame_dates": int(study_frame["timestamp_ms"].nunique()),
        },
        "orderbook_coverage": orderbook_summary,
        "event_rule_definitions": {
            rule_name: {
                "expected_forward_sign": str(rule["expected_forward_sign"]),
                "definition": str(rule["definition"]),
            }
            for rule_name, rule in event_rules.items()
        },
        "cohorts": list(cohort_masks.keys()),
        "horizons_days": horizons,
        "summary": summary,
    }
    summary_path.write_text(json.dumps(output_payload, indent=2, sort_keys=True), encoding="utf-8")
    _build_event_rows_export(study_frame, event_rules=event_rules).to_csv(events_path, index=False)
    orderbook_panel.to_csv(state_path, index=False)

    print()
    print(f"=== Wrote summary to {summary_path}")
    print(f"=== Wrote event rows to {events_path}")
    print(f"=== Wrote state panel to {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
