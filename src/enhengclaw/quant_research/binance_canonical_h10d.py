from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, timedelta
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

import numpy as np
import pandas as pd

from ._binance_canonical_archive import (
    KLINE_FLOAT_COLUMNS,
    KLINE_INT_COLUMNS,
    _coerce_kline_frame,
    _read_kline_path,
    _summarize_symbol_audits,
    symbol_to_subject,
)
from ._binance_canonical_artifacts import _frame_or_empty, _write_json, _write_universe_membership
from ._binance_canonical_funding import (
    DEFAULT_FUNDING_COST_ROOT,
    _dedupe_funding_rows,
    _funding_columns,
    _http_get_json,
    _month_end_ms,
    _month_key_from_ms,
    _month_start_ms,
    _read_funding_partition,
    _resolve_funding_root,
    funding_partition_path,
    funding_symbol_manifest_path,
    funding_symbol_root,
    funding_sync_summary_path,
)
from ._binance_canonical_identity import _stable_hash, _stable_int
from ._binance_canonical_normalization import _timestamp_percentile_rank, _timestamp_zscore
from ._binance_canonical_reporting import _metric_row, _render_markdown_report
from ._binance_canonical_risk_columns import BINANCE_RISK_BRAKE_COLUMNS
from ._binance_canonical_run_metadata import _default_run_id, _today_compact, utc_now
from ._binance_canonical_time import _date_to_ms, _date_utc_series, _ms_to_date, _parse_date
from .execution_backtest import (
    _cross_sectional_target_weights,
    _borrow_cost_return,
    _funding_cost_return,
    _next_fill_offset,
    _price_path_return,
    _scale_cross_sectional_turnover,
    _trade_costs,
    backtest_cross_sectional,
    filter_cross_sectional_execution_frame,
)
from .execution_cost_model import resolve_execution_cost_model
from .split_realization_contract import build_split_realization_contract


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = ROOT / "config" / "quant_research" / "binance_canonical_h10d.json"
DEFAULT_STORE_ROOT = Path("E:/EnhengClawData/market_history/binance_1m_five_year")
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "binance_canonical_h10d"
DEFAULT_REPORT_ROOT = ROOT / "docs" / "quant_research" / "02_binance_pit_h10d"

STRATEGY_LABEL = "v5_binance_ohlcv_core_h10d"
PIT_TOP_MID_STRATEGY_LABEL = "v5_binance_pit_top_mid_h10d"
PARENT_LABEL = "v5_rw_bridge_no_overlay_h10d"
MARKET_TYPE = "usdm_perp"
INTERVAL_1M = "1m"
USDM_BASE_URL = "https://fapi.binance.com"
FUNDING_RATE_URL = f"{USDM_BASE_URL}/fapi/v1/fundingRate"
FUNDING_LIMIT = 1000

ALLOWED_ALPHA_FEATURES: tuple[str, ...] = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "downside_upside_vol_ratio_30",
    "settlement_cycle_premium_60d",
)

BINANCE_OHLCV_CORE_WEIGHTS: dict[str, float] = {
    "intraday_realized_vol_4h_to_1d_smooth_60": -0.20,
    "realized_volatility_5": -0.10,
    "distance_to_high_60": 0.18,
    "distance_to_high_5": 0.15,
    "liquidity_stress_qv_iv": -0.10,
    "momentum_decay_5_20": -0.06,
    "downside_upside_vol_ratio_30": 0.10,
    "settlement_cycle_premium_60d": -0.08,
}

REFERENCE_CORE20_SUBJECTS: tuple[str, ...] = (
    "AAVE",
    "ADA",
    "AVAX",
    "BCH",
    "BNB",
    "BTC",
    "CRV",
    "DOGE",
    "DOT",
    "ENJ",
    "ETH",
    "FIL",
    "LINK",
    "LTC",
    "NEAR",
    "SOL",
    "TRX",
    "UNI",
    "XRP",
    "ZEC",
)

FORBIDDEN_ALPHA_PATTERNS: tuple[str, ...] = (
    r"^coinglass_",
    r"open_interest",
    r"^oi_",
    r"funding",
    r"basis",
    r"liquidation",
    r"orderbook",
    r"top_trader",
    r"taker",
)

INTERVAL_MS = {
    "1m": 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


@dataclass(frozen=True)
class BinanceCanonicalDataset:
    panel: pd.DataFrame
    dataset_manifest: dict[str, Any]
    gap_audit: dict[str, Any]
    feature_manifest: dict[str, Any]


def load_strategy_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    return default_strategy_config()


def default_strategy_config() -> dict[str, Any]:
    return {
        "strategy_label": STRATEGY_LABEL,
        "parent_label": PARENT_LABEL,
        "dataset_profile": "binance_canonical_daily_1m_to_1d",
        "label_contract_id": "forward_return_execution_aligned.v1",
        "allowed_alpha_sources": ["binance_public_archive_1m_ohlcv"],
        "excluded_source_patterns": list(FORBIDDEN_ALPHA_PATTERNS),
        "feature_columns": list(ALLOWED_ALPHA_FEATURES),
        "feature_weights": dict(BINANCE_OHLCV_CORE_WEIGHTS),
        "funding_cost_root": str(DEFAULT_FUNDING_COST_ROOT),
        "reference_capital_usd": 1_000_000.0,
        "strategy_profile": {
            "spot_only": False,
            "short_allowed": True,
            "execution_venue": "perp",
            "max_gross_leverage": 1.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "max_turnover_per_rebalance": 1.0,
            "top_long_count": 3,
            "bottom_short_count": 3,
            "decision_eligible_column": "binance_decision_eligible",
        },
        "universe_policy": {
            "preset": "binance_ohlcv_core20",
            "selection_mode": "frozen_asof",
            "market_type": MARKET_TYPE,
            "top_n": 20,
            "reference_core20_subjects": list(REFERENCE_CORE20_SUBJECTS),
            "coverage_threshold": 0.85,
            "lookback_days": 30,
            "freeze_as_of": "2026-04-30",
        },
        "split_realization": {"interval": "1d", "target_horizon_bars": 10},
        "capacity_limits": {"max_trade_participation_rate_max": 0.005},
        "execution_gap_policy": {
            "mode": "drop_selected_path_gap_symbols",
            "max_iterations": 5,
        },
        "pit_data_eligibility_policy": {
            "mode": "disabled",
        },
        "diagnostic_ablations": {
            "enable_reference_core20_filters": True,
        },
        "validation_gates": {
            "min_oos_periods": 60,
            "max_trade_participation_rate_max": 0.005,
            "liquidity_positive_bucket_count_min": 2,
            "stratified_holdout_repeat_count": 8,
            "stratified_holdout_min_positive_fraction": 0.75,
            "stratified_holdout_require_gap_free": True,
            "legacy_symbol_holdout_hard_gate": False,
            "require_base_positive_return": True,
            "require_stress_positive_return": True,
            "require_holdout_positive_return": True,
        },
    }


def discover_usdm_perp_symbols(store_root: Path) -> list[str]:
    market_root = Path(store_root) / "data" / MARKET_TYPE
    if not market_root.exists():
        return []
    return sorted(item.name.upper() for item in market_root.iterdir() if item.is_dir())


def validate_alpha_feature_columns(
    feature_columns: Iterable[str],
    *,
    allowed_columns: Iterable[str] = ALLOWED_ALPHA_FEATURES,
    forbidden_patterns: Iterable[str] = FORBIDDEN_ALPHA_PATTERNS,
    require_all_allowed: bool = True,
) -> dict[str, Any]:
    features = [str(item).strip() for item in feature_columns if str(item).strip()]
    allowed = {str(item) for item in allowed_columns}
    compiled = [re.compile(str(pattern), flags=re.IGNORECASE) for pattern in forbidden_patterns]
    forbidden: list[str] = []
    for column in features:
        normalized = column.lower()
        if any(pattern.search(normalized) for pattern in compiled):
            forbidden.append(column)
    unexpected = [column for column in features if column not in allowed]
    missing = [column for column in allowed_columns if str(column) not in features]
    return {
        "passed": not forbidden and not unexpected and (not missing or not require_all_allowed),
        "feature_columns": features,
        "allowed_columns": list(allowed_columns),
        "forbidden_columns": sorted(set(forbidden)),
        "unexpected_columns": sorted(set(unexpected)),
        "missing_columns": list(missing),
        "require_all_allowed": bool(require_all_allowed),
        "excluded_source_patterns": list(forbidden_patterns),
    }


def assert_alpha_feature_purity(feature_columns: Iterable[str]) -> None:
    result = validate_alpha_feature_columns(feature_columns)
    if not result["passed"]:
        raise ValueError(f"Binance-canonical feature purity failed: {result}")


def assert_alpha_feature_subset_purity(feature_columns: Iterable[str]) -> None:
    result = validate_alpha_feature_columns(feature_columns)
    if result["forbidden_columns"] or result["unexpected_columns"]:
        raise ValueError(f"Binance-canonical feature subset purity failed: {result}")


def _allow_feature_subset(config: dict[str, Any]) -> bool:
    policy = dict(config.get("feature_subset_policy") or {})
    return bool(policy.get("allow_pruned_subset", False))


def aggregate_1m_klines(
    frame: pd.DataFrame,
    *,
    interval: str,
    drop_incomplete: bool = True,
) -> pd.DataFrame:
    interval = str(interval)
    if interval not in {"1h", "4h", "1d"}:
        raise ValueError(f"unsupported aggregation interval: {interval}")
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    _coerce_kline_frame(working)
    working = working.dropna(subset=["open_time_ms"]).sort_values("open_time_ms").copy()
    if working.empty:
        return working
    interval_ms = INTERVAL_MS[interval]
    expected_minutes = interval_ms // INTERVAL_MS["1m"]
    working["bucket_open_time_ms"] = (working["open_time_ms"].astype("int64") // interval_ms) * interval_ms
    group_columns = [column for column in ("exchange", "market_type", "symbol") if column in working.columns]
    group_columns.append("bucket_open_time_ms")
    aggregated = (
        working.groupby(group_columns, dropna=False, sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            quote_volume=("quote_volume", "sum"),
            trade_count=("trade_count", "sum"),
            taker_buy_base_volume=("taker_buy_base_volume", "sum"),
            taker_buy_quote_volume=("taker_buy_quote_volume", "sum"),
            observed_minute_row_count=("open_time_ms", "count"),
            unique_open_time_count=("open_time_ms", "nunique"),
            first_open_time_ms=("open_time_ms", "min"),
            last_open_time_ms=("open_time_ms", "max"),
        )
        .reset_index()
    )
    aggregated.rename(columns={"bucket_open_time_ms": "open_time_ms"}, inplace=True)
    aggregated["close_time_ms"] = aggregated["open_time_ms"].astype("int64") + interval_ms - 1
    aggregated["interval"] = interval
    aggregated["expected_minute_count"] = int(expected_minutes)
    aggregated["bar_complete"] = (
        aggregated["observed_minute_row_count"].eq(expected_minutes)
        & aggregated["unique_open_time_count"].eq(expected_minutes)
    )
    output_columns = [
        *(column for column in ("exchange", "market_type", "symbol") if column in aggregated.columns),
        "interval",
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "expected_minute_count",
        "observed_minute_row_count",
        "unique_open_time_count",
        "bar_complete",
        "first_open_time_ms",
        "last_open_time_ms",
    ]
    aggregated = aggregated[[column for column in output_columns if column in aggregated.columns]].copy()
    if drop_incomplete:
        aggregated = aggregated.loc[aggregated["bar_complete"]].copy()
    return aggregated.sort_values([column for column in ("symbol", "open_time_ms") if column in aggregated.columns]).reset_index(drop=True)


def build_binance_canonical_dataset(
    *,
    store_root: Path = DEFAULT_STORE_ROOT,
    as_of: str | date = "2026-04-30",
    config: dict[str, Any] | None = None,
    funding_root: Path | None = None,
    symbols: Iterable[str] | None = None,
    max_symbols: int | None = None,
    top_n: int | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
) -> BinanceCanonicalDataset:
    resolved_config = dict(config or load_strategy_config())
    as_of_date = _parse_date(as_of)
    universe_policy = dict(resolved_config.get("universe_policy") or {})
    resolved_top_n = int(top_n if top_n is not None else universe_policy.get("top_n", 20))
    coverage_threshold = float(universe_policy.get("coverage_threshold", 0.85) or 0.85)
    lookback_days = int(universe_policy.get("lookback_days", 30) or 30)
    symbol_list = [str(item).strip().upper() for item in (symbols or discover_usdm_perp_symbols(Path(store_root))) if str(item).strip()]
    if max_symbols is not None:
        symbol_list = symbol_list[: max(0, int(max_symbols))]

    frames: list[pd.DataFrame] = []
    symbol_audits: list[dict[str, Any]] = []
    for symbol in symbol_list:
        frame, audit = build_symbol_feature_frame(
            store_root=Path(store_root),
            symbol=symbol,
            as_of=as_of_date,
            start_month=start_month,
            end_month=end_month,
        )
        symbol_audits.append(audit)
        if not frame.empty:
            frames.append(frame)

    all_panel = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    universe_mode = str(universe_policy.get("selection_mode") or universe_policy.get("mode") or "frozen_asof").strip().lower()
    if universe_mode in {"rolling", "rolling_quote_volume", "point_in_time", "pit_rolling_quote_volume"}:
        panel, universe = apply_point_in_time_rolling_universe(
            all_panel,
            as_of=as_of_date,
            top_n=resolved_top_n,
            coverage_threshold=coverage_threshold,
            lookback_days=lookback_days,
        )
        resolved_universe_mode = "pit_rolling_quote_volume"
    else:
        universe = freeze_binance_ohlcv_universe(
            all_panel,
            as_of=as_of_date,
            top_n=resolved_top_n,
            coverage_threshold=coverage_threshold,
            lookback_days=lookback_days,
        )
        universe_subjects = {str(item["subject"]) for item in universe}
        panel = all_panel.loc[all_panel["subject"].astype(str).isin(universe_subjects)].copy() if not all_panel.empty else all_panel
        bucket_by_subject = {str(item["subject"]): str(item["liquidity_bucket"]) for item in universe}
        rank_by_subject = {str(item["subject"]): int(item["rank"]) for item in universe}
        if not panel.empty:
            panel["liquidity_bucket"] = panel["subject"].map(bucket_by_subject).fillna("unselected")
            panel["universe_rank"] = panel["subject"].map(rank_by_subject)
            panel["universe_active"] = True
            panel["universe_selection_rule"] = "binance_perp_quote_volume_only"
        resolved_universe_mode = "frozen_asof"
    if not panel.empty:
        panel.sort_values(["timestamp_ms", "subject"], inplace=True)
        panel = attach_funding_cost_to_panel(
            panel,
            funding_root=_resolve_funding_root(config=resolved_config, funding_root=funding_root),
        )

    blockers: list[dict[str, Any]] = []
    if len(universe) < resolved_top_n:
        blockers.append(
            {
                "code": "universe_core20_insufficient_symbols",
                "message": f"Selected {len(universe)} symbols, expected {resolved_top_n}.",
            }
        )
    if panel.empty:
        blockers.append({"code": "empty_binance_canonical_panel", "message": "No valid Binance-canonical rows."})

    dataset_manifest = {
        "generated_at_utc": utc_now(),
        "strategy_label": str(resolved_config.get("strategy_label") or STRATEGY_LABEL),
        "parent_label": str(resolved_config.get("parent_label") or PARENT_LABEL),
        "dataset_profile": str(resolved_config.get("dataset_profile") or "binance_canonical_daily_1m_to_1d"),
        "store_root": str(Path(store_root)),
        "market_type": MARKET_TYPE,
        "as_of": as_of_date.isoformat(),
        "source": "Binance public archive 1m klines",
        "cost_only_source": "Binance USD-M fundingRate",
        "funding_cost_root": str(_resolve_funding_root(config=resolved_config, funding_root=funding_root)),
        "source_interval": "1m",
        "derived_intervals": ["1h", "4h", "1d"],
        "symbol_scan_count": len(symbol_list),
        "universe_selection_mode": resolved_universe_mode,
        "selected_universe_count": len(universe),
        "selected_universe": universe,
        "row_count": int(len(panel)),
        "timestamp_count": int(panel["timestamp_ms"].nunique()) if not panel.empty else 0,
        "start_timestamp_ms": int(panel["timestamp_ms"].min()) if not panel.empty else None,
        "end_timestamp_ms": int(panel["timestamp_ms"].max()) if not panel.empty else None,
        "gap_policy": dict(resolved_config.get("gap_policy") or {}),
        "pit_data_eligibility_policy": dict(resolved_config.get("pit_data_eligibility_policy") or {}),
        "strategy_profile": dict(resolved_config.get("strategy_profile") or {}),
        "blockers": blockers,
    }
    gap_audit = {
        "generated_at_utc": utc_now(),
        "store_root": str(Path(store_root)),
        "as_of": as_of_date.isoformat(),
        "symbol_audits": symbol_audits,
        "summary": _summarize_symbol_audits(symbol_audits),
    }
    feature_manifest = build_feature_manifest(config=resolved_config)
    return BinanceCanonicalDataset(
        panel=panel.reset_index(drop=True),
        dataset_manifest=dataset_manifest,
        gap_audit=gap_audit,
        feature_manifest=feature_manifest,
    )


def build_symbol_feature_frame(
    *,
    store_root: Path,
    symbol: str,
    as_of: str | date,
    start_month: str | None = None,
    end_month: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    symbol = str(symbol).strip().upper()
    as_of_date = _parse_date(as_of)
    paths = _symbol_partition_paths(store_root=store_root, symbol=symbol, start_month=start_month, end_month=end_month)
    audit: dict[str, Any] = {
        "symbol": symbol,
        "subject": symbol_to_subject(symbol),
        "partition_count": len(paths),
        "status": "missing_partitions" if not paths else "ok",
    }
    if not paths:
        return pd.DataFrame(), audit
    frames = []
    for path in paths:
        frame = _read_kline_path(path)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        audit["status"] = "empty_partitions"
        return pd.DataFrame(), audit
    minute_frame = pd.concat(frames, ignore_index=True, sort=False)
    _coerce_kline_frame(minute_frame)
    as_of_end_ms = _date_to_ms(as_of_date + timedelta(days=1))
    minute_frame = minute_frame.loc[pd.to_numeric(minute_frame["open_time_ms"], errors="coerce").lt(as_of_end_ms)].copy()
    if minute_frame.empty:
        audit["status"] = "empty_after_as_of_filter"
        return pd.DataFrame(), audit

    one_h = aggregate_1m_klines(minute_frame, interval="1h", drop_incomplete=False)
    four_h = aggregate_1m_klines(minute_frame, interval="4h", drop_incomplete=False)
    daily = aggregate_1m_klines(minute_frame, interval="1d", drop_incomplete=False)
    valid_daily = daily.loc[daily["bar_complete"]].copy()
    valid_four_h = four_h.loc[four_h["bar_complete"]].copy()
    valid_one_h = one_h.loc[one_h["bar_complete"]].copy()
    audit.update(
        {
            "minute_row_count": int(len(minute_frame)),
            "daily_bucket_count": int(len(daily)),
            "valid_daily_bucket_count": int(len(valid_daily)),
            "invalid_daily_bucket_count": int((~daily["bar_complete"]).sum()) if not daily.empty else 0,
            "valid_4h_bucket_count": int(len(valid_four_h)),
            "invalid_4h_bucket_count": int((~four_h["bar_complete"]).sum()) if not four_h.empty else 0,
            "valid_1h_bucket_count": int(len(valid_one_h)),
            "invalid_1h_bucket_count": int((~one_h["bar_complete"]).sum()) if not one_h.empty else 0,
        }
    )
    if valid_daily.empty:
        audit["status"] = "no_complete_daily_bars"
        return pd.DataFrame(), audit
    panel = _daily_bars_to_feature_panel(
        daily=valid_daily,
        four_h=valid_four_h,
        one_h=valid_one_h,
        symbol=symbol,
    )
    audit["feature_row_count"] = int(len(panel))
    audit["status"] = "ok" if not panel.empty else "empty_feature_panel"
    return panel, audit


def freeze_binance_ohlcv_universe(
    panel: pd.DataFrame,
    *,
    as_of: str | date,
    top_n: int = 20,
    coverage_threshold: float = 0.85,
    lookback_days: int = 30,
) -> list[dict[str, Any]]:
    if panel.empty:
        return []
    as_of_date = _parse_date(as_of)
    as_of_end_ms = _date_to_ms(as_of_date + timedelta(days=1))
    eligible = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").lt(as_of_end_ms)].copy()
    if eligible.empty:
        return []
    min_date = _ms_to_date(int(eligible["timestamp_ms"].min()))
    expected_days = max((as_of_date - min_date).days + 1, 1)
    lookback_start_ms = _date_to_ms(as_of_date - timedelta(days=max(int(lookback_days), 1) - 1))
    records: list[dict[str, Any]] = []
    for subject, group in eligible.groupby("subject", sort=True):
        symbol = str(group["usdm_symbol"].iloc[0]) if "usdm_symbol" in group.columns else str(subject)
        valid = group.loc[
            pd.to_numeric(group.get("perp_close"), errors="coerce").gt(0.0)
            & pd.to_numeric(group.get("perp_quote_volume_usd"), errors="coerce").gt(0.0)
        ].copy()
        coverage_ratio = float(valid["timestamp_ms"].nunique()) / float(expected_days)
        lookback = valid.loc[pd.to_numeric(valid["timestamp_ms"], errors="coerce").ge(lookback_start_ms)]
        median_qv = float(pd.to_numeric(lookback["perp_quote_volume_usd"], errors="coerce").median()) if not lookback.empty else 0.0
        if coverage_ratio >= coverage_threshold and median_qv > 0.0:
            records.append(
                {
                    "symbol": symbol,
                    "subject": str(subject),
                    "coverage_ratio": coverage_ratio,
                    "valid_daily_count": int(valid["timestamp_ms"].nunique()),
                    "expected_daily_count": int(expected_days),
                    "median_quote_volume_usd_lookback": median_qv,
                }
            )
    records.sort(key=lambda item: (-float(item["median_quote_volume_usd_lookback"]), str(item["symbol"])))
    selected = records[: max(int(top_n), 0)]
    for index, item in enumerate(selected, start=1):
        item["rank"] = index
        item["liquidity_bucket"] = "top_liquidity" if index <= max(min(10, len(selected)), 1) else "mid_liquidity"
        item["selection_rule"] = "binance_perp_quote_volume_only"
    return selected


def apply_point_in_time_rolling_universe(
    panel: pd.DataFrame,
    *,
    as_of: str | date,
    top_n: int = 20,
    coverage_threshold: float = 0.85,
    lookback_days: int = 30,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if panel.empty:
        return panel.copy(), []
    as_of_date = _parse_date(as_of)
    as_of_end_ms = _date_to_ms(as_of_date + timedelta(days=1))
    working = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").lt(as_of_end_ms)].copy()
    if working.empty:
        return working, []
    resolved_top_n = max(int(top_n), 0)
    resolved_lookback_days = max(int(lookback_days), 1)
    working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce")
    working = working.dropna(subset=["timestamp_ms", "subject"]).copy()
    if working.empty or resolved_top_n <= 0:
        return working.iloc[0:0].copy(), []
    working["timestamp_ms"] = working["timestamp_ms"].astype("int64")
    valid_mask = (
        pd.to_numeric(working.get("perp_close"), errors="coerce").gt(0.0)
        & pd.to_numeric(working.get("perp_quote_volume_usd"), errors="coerce").gt(0.0)
    )
    working["_pit_valid_row"] = valid_mask.astype("float64")
    working["_pit_quote_volume"] = pd.to_numeric(working["perp_quote_volume_usd"], errors="coerce").where(valid_mask)
    ranked_frames: list[pd.DataFrame] = []
    for _, group in working.sort_values(["subject", "timestamp_ms"]).groupby("subject", sort=True):
        frame = group.copy()
        frame["_pit_datetime"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
        indexed = frame.set_index("_pit_datetime", drop=False).sort_index()
        rolling_valid_count = indexed["_pit_valid_row"].rolling(f"{resolved_lookback_days}D", min_periods=1).sum()
        rolling_median_qv = indexed["_pit_quote_volume"].rolling(f"{resolved_lookback_days}D", min_periods=1).median()
        frame = indexed.reset_index(drop=True)
        frame["universe_valid_daily_count_lookback"] = rolling_valid_count.to_numpy(dtype="float64")
        frame["universe_coverage_ratio_lookback"] = frame["universe_valid_daily_count_lookback"] / float(resolved_lookback_days)
        frame["universe_median_quote_volume_usd_lookback"] = rolling_median_qv.to_numpy(dtype="float64")
        ranked_frames.append(frame)
    ranked = pd.concat(ranked_frames, ignore_index=True, sort=False) if ranked_frames else working.iloc[0:0].copy()
    eligible = ranked.loc[
        ranked["universe_coverage_ratio_lookback"].ge(float(coverage_threshold))
        & pd.to_numeric(ranked["universe_median_quote_volume_usd_lookback"], errors="coerce").gt(0.0)
    ].copy()
    if eligible.empty:
        return eligible, []

    ranked["universe_active"] = False
    ranked["universe_rank"] = np.nan
    ranked["universe_selection_rule"] = "binance_perp_pit_rolling_quote_volume_only"
    for _, group in eligible.groupby("timestamp_ms", sort=True):
        ordered = group.sort_values(
            ["universe_median_quote_volume_usd_lookback", "subject"],
            ascending=[False, True],
        ).head(resolved_top_n).copy()
        ranked.loc[ordered.index, "universe_rank"] = np.arange(1, len(ordered) + 1, dtype="int64")
        ranked.loc[ordered.index, "universe_active"] = True
    ranked["liquidity_bucket"] = np.where(
        pd.to_numeric(ranked["universe_rank"], errors="coerce").le(10),
        "top_liquidity",
        np.where(pd.to_numeric(ranked["universe_rank"], errors="coerce").notna(), "mid_liquidity", "not_in_universe"),
    )
    ranked.drop(
        columns=["_pit_valid_row", "_pit_quote_volume", "_pit_datetime"],
        errors="ignore",
        inplace=True,
    )
    selected_panel = ranked.loc[ranked["universe_active"]].copy()
    if selected_panel.empty:
        return ranked.sort_values(["timestamp_ms", "subject"]).reset_index(drop=True), []
    membership_counts = selected_panel.groupby("timestamp_ms", sort=True)["subject"].nunique()
    universe_summary: list[dict[str, Any]] = []
    for subject, group in selected_panel.groupby("subject", sort=True):
        ranks = pd.to_numeric(group["universe_rank"], errors="coerce")
        timestamps = pd.to_numeric(group["timestamp_ms"], errors="coerce").dropna().astype("int64")
        symbol = str(group["usdm_symbol"].iloc[0]) if "usdm_symbol" in group.columns else str(subject)
        universe_summary.append(
            {
                "symbol": symbol,
                "subject": str(subject),
                "selected_day_count": int(group["timestamp_ms"].nunique()),
                "first_selected_date": _ms_to_date(int(timestamps.min())).isoformat() if not timestamps.empty else None,
                "last_selected_date": _ms_to_date(int(timestamps.max())).isoformat() if not timestamps.empty else None,
                "median_rank": float(ranks.median()) if ranks.notna().any() else None,
                "min_rank": int(ranks.min()) if ranks.notna().any() else None,
                "max_rank": int(ranks.max()) if ranks.notna().any() else None,
                "latest_rank": int(ranks.iloc[-1]) if ranks.notna().any() else None,
                "selection_rule": "binance_perp_pit_rolling_quote_volume_only",
            }
        )
    universe_summary.sort(key=lambda item: (-int(item["selected_day_count"]), str(item["symbol"])))
    for item in universe_summary:
        item["timestamp_count"] = int(len(membership_counts))
        item["min_selected_count_per_timestamp"] = int(membership_counts.min()) if not membership_counts.empty else 0
        item["median_selected_count_per_timestamp"] = float(membership_counts.median()) if not membership_counts.empty else 0.0
        item["max_selected_count_per_timestamp"] = int(membership_counts.max()) if not membership_counts.empty else 0
    return ranked.sort_values(["timestamp_ms", "subject"]).reset_index(drop=True), universe_summary


def sync_funding_cost_history(
    *,
    symbols: Iterable[str],
    start: str | date,
    end: str | date,
    funding_root: Path = DEFAULT_FUNDING_COST_ROOT,
    force: bool = False,
    http_get_json_fn: Any | None = None,
) -> dict[str, Any]:
    resolved_symbols = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if end_date < start_date:
        raise ValueError("funding end date must be on or after start date")
    start_ms = _date_to_ms(start_date)
    end_ms = _date_to_ms(end_date + timedelta(days=1)) - 1
    http_get_json = http_get_json_fn or _http_get_json
    results: list[dict[str, Any]] = []
    for symbol in resolved_symbols:
        try:
            rows = fetch_funding_rate_rows(
                symbol=symbol,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
                http_get_json_fn=http_get_json,
            )
            result = write_funding_cost_rows(
                funding_root=funding_root,
                symbol=symbol,
                rows=rows,
                force=force,
            )
            results.append(
                {
                    "symbol": symbol,
                    "status": "success",
                    "row_count": int(len(rows)),
                    **result,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"symbol": symbol, "status": "error", "error": str(exc), "row_count": 0})
    summary = {
        "generated_at_utc": utc_now(),
        "status": "success" if all(item["status"] == "success" for item in results) else "partial",
        "success": all(item["status"] == "success" for item in results),
        "funding_root": str(Path(funding_root)),
        "source": "Binance USD-M /fapi/v1/fundingRate",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "symbol_count": len(resolved_symbols),
        "symbols": resolved_symbols,
        "row_count": sum(int(item.get("row_count", 0) or 0) for item in results),
        "results": results,
    }
    _write_json(funding_sync_summary_path(funding_root), summary)
    return summary


def fetch_funding_rate_rows(
    *,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Any | None = None,
) -> list[dict[str, Any]]:
    http_get_json = http_get_json_fn or _http_get_json
    symbol = str(symbol).strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    cursor = int(start_time_ms)
    rows: list[dict[str, Any]] = []
    seen_times: set[int] = set()
    while cursor <= int(end_time_ms):
        params = {
            "symbol": symbol,
            "startTime": int(cursor),
            "endTime": int(end_time_ms),
            "limit": FUNDING_LIMIT,
        }
        payload = http_get_json(f"{FUNDING_RATE_URL}?{urlencode(params)}")
        if not isinstance(payload, list) or not payload:
            break
        max_seen = cursor
        for item in payload:
            funding_time = int(item["fundingTime"])
            max_seen = max(max_seen, funding_time)
            if funding_time < int(start_time_ms) or funding_time > int(end_time_ms) or funding_time in seen_times:
                continue
            seen_times.add(funding_time)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": MARKET_TYPE,
                    "symbol": symbol,
                    "funding_time_ms": funding_time,
                    "funding_rate": float(item.get("fundingRate", 0.0) or 0.0),
                    "source": "binance_fapi_fundingRate",
                }
            )
        if len(payload) < FUNDING_LIMIT:
            break
        next_cursor = max_seen + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
    rows.sort(key=lambda item: int(item["funding_time_ms"]))
    return rows


def write_funding_cost_rows(
    *,
    funding_root: Path,
    symbol: str,
    rows: list[dict[str, Any]],
    force: bool = False,
) -> dict[str, Any]:
    symbol = str(symbol).strip().upper()
    partitions: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        month = _month_key_from_ms(int(row["funding_time_ms"]))
        partitions.setdefault(month, []).append(row)
    written_paths: list[str] = []
    for month, month_rows in sorted(partitions.items()):
        path = funding_partition_path(funding_root, symbol=symbol, month=month)
        if path.exists() and not force:
            existing = _read_funding_partition(path)
            combined = _dedupe_funding_rows([*existing, *month_rows])
        else:
            combined = _dedupe_funding_rows(month_rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(combined, columns=_funding_columns()).to_csv(path, index=False, compression="gzip")
        written_paths.append(str(path))
    manifest = {
        "generated_at_utc": utc_now(),
        "symbol": symbol,
        "source": "Binance USD-M /fapi/v1/fundingRate",
        "partition_count": len(partitions),
        "row_count": int(len(rows)),
        "first_funding_time_ms": int(rows[0]["funding_time_ms"]) if rows else None,
        "last_funding_time_ms": int(rows[-1]["funding_time_ms"]) if rows else None,
        "partitions": written_paths,
    }
    _write_json(funding_symbol_manifest_path(funding_root, symbol=symbol), manifest)
    return {"partition_count": len(partitions), "manifest_path": str(funding_symbol_manifest_path(funding_root, symbol=symbol))}


def load_funding_cost_daily(
    *,
    funding_root: Path,
    symbols: Iterable[str],
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in sorted({str(item).strip().upper() for item in symbols if str(item).strip()}):
        root = funding_symbol_root(funding_root, symbol=symbol)
        if not root.exists():
            continue
        for path in sorted(root.glob("*.csv.gz")):
            month = _partition_month(path)
            if start_time_ms is not None and month is not None and _month_end_ms(month) < start_time_ms:
                continue
            if end_time_ms is not None and month is not None and _month_start_ms(month) > end_time_ms:
                continue
            frame = pd.read_csv(path, compression="gzip")
            if not frame.empty:
                frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["usdm_symbol", "date_utc", "funding_rate", "funding_sample_count"])
    frame = pd.concat(frames, ignore_index=True, sort=False)
    frame["funding_time_ms"] = pd.to_numeric(frame["funding_time_ms"], errors="coerce")
    frame = frame.dropna(subset=["funding_time_ms"]).copy()
    if start_time_ms is not None:
        frame = frame.loc[frame["funding_time_ms"].ge(int(start_time_ms))]
    if end_time_ms is not None:
        frame = frame.loc[frame["funding_time_ms"].le(int(end_time_ms))]
    if frame.empty:
        return pd.DataFrame(columns=["usdm_symbol", "date_utc", "funding_rate", "funding_sample_count"])
    frame["usdm_symbol"] = frame["symbol"].astype(str).str.upper()
    frame["date_utc"] = _date_utc_series(frame["funding_time_ms"])
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="coerce")
    return (
        frame.groupby(["usdm_symbol", "date_utc"], sort=True)
        .agg(
            funding_rate=("funding_rate", "mean"),
            funding_sample_count=("funding_rate", "count"),
        )
        .reset_index()
    )


def attach_funding_cost_to_panel(panel: pd.DataFrame, *, funding_root: Path) -> pd.DataFrame:
    output = panel.copy()
    if output.empty:
        return output
    if "usdm_symbol" not in output.columns or "date_utc" not in output.columns:
        output["funding_rate"] = np.nan
        output["funding_sample_count"] = 0.0
        return output
    symbols = sorted(str(item).strip().upper() for item in output["usdm_symbol"].dropna().unique() if str(item).strip())
    start_ms = int(pd.to_numeric(output["timestamp_ms"], errors="coerce").min())
    end_ms = int(pd.to_numeric(output["timestamp_ms"], errors="coerce").max()) + INTERVAL_MS["1d"] - 1
    daily = load_funding_cost_daily(
        funding_root=funding_root,
        symbols=symbols,
        start_time_ms=start_ms,
        end_time_ms=end_ms,
    )
    output.drop(columns=["funding_rate", "funding_sample_count"], errors="ignore", inplace=True)
    if daily.empty:
        output["funding_rate"] = np.nan
        output["funding_sample_count"] = 0.0
        return output
    output = output.merge(daily, on=["usdm_symbol", "date_utc"], how="left")
    output["funding_rate"] = pd.to_numeric(output["funding_rate"], errors="coerce")
    output["funding_sample_count"] = pd.to_numeric(output["funding_sample_count"], errors="coerce").fillna(0.0)
    return output


def build_feature_manifest(*, config: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_config = dict(config or load_strategy_config())
    features = [str(item) for item in resolved_config.get("feature_columns", ALLOWED_ALPHA_FEATURES)]
    allow_feature_subset = _allow_feature_subset(resolved_config)
    purity = validate_alpha_feature_columns(
        features,
        allowed_columns=ALLOWED_ALPHA_FEATURES,
        forbidden_patterns=resolved_config.get("excluded_source_patterns", FORBIDDEN_ALPHA_PATTERNS),
        require_all_allowed=not allow_feature_subset,
    )
    weights = dict(resolved_config.get("feature_weights") or BINANCE_OHLCV_CORE_WEIGHTS)
    abs_sum = sum(abs(float(weights.get(column, 0.0))) for column in features)
    normalized_weights = {
        column: (float(weights.get(column, 0.0)) / abs_sum if abs_sum > 0.0 else 0.0)
        for column in features
    }
    hash_payload = {
        "strategy_label": str(resolved_config.get("strategy_label") or STRATEGY_LABEL),
        "feature_columns": features,
        "feature_weights": normalized_weights,
        "feature_subset_policy": dict(resolved_config.get("feature_subset_policy") or {}),
        "allowed_alpha_sources": list(resolved_config.get("allowed_alpha_sources") or []),
        "excluded_source_patterns": list(resolved_config.get("excluded_source_patterns") or FORBIDDEN_ALPHA_PATTERNS),
    }
    return {
        "generated_at_utc": utc_now(),
        "strategy_label": str(resolved_config.get("strategy_label") or STRATEGY_LABEL),
        "parent_label": str(resolved_config.get("parent_label") or PARENT_LABEL),
        "feature_columns": features,
        "feature_weights": normalized_weights,
        "raw_parent_weight_subset": {column: float(weights.get(column, 0.0)) for column in features},
        "feature_subset_policy": dict(resolved_config.get("feature_subset_policy") or {}),
        "allowed_alpha_sources": list(resolved_config.get("allowed_alpha_sources") or []),
        "excluded_source_patterns": list(resolved_config.get("excluded_source_patterns") or FORBIDDEN_ALPHA_PATTERNS),
        "purity_check": purity,
        "feature_manifest_hash": _stable_hash(hash_payload),
    }


def score_binance_ohlcv_core(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] = ALLOWED_ALPHA_FEATURES,
    feature_weights: dict[str, float] | None = None,
    require_complete_feature_set: bool = True,
    enforce_alpha_purity: bool = True,
    contribution_multipliers: dict[str, pd.Series] | None = None,
) -> pd.Series:
    features = [str(item) for item in feature_columns]
    # enforce_alpha_purity defaults True: the OHLCV-only safety boundary is unchanged for
    # every existing caller. The frozen 12-factor frontier sets it False *only* because its
    # admissible column set is pinned and hash-verified by the frozen frontier contract
    # (frozen_frontier_contract.validate_frontier_contract), NOT by the OHLCV pattern
    # allow-list. That is a strictly tighter boundary (an exact 12-column hash match) applied
    # upstream, so skipping the pattern asserts here does not widen what can be scored live.
    if enforce_alpha_purity:
        if require_complete_feature_set:
            assert_alpha_feature_purity(features)
        else:
            assert_alpha_feature_subset_purity(features)
    missing = [column for column in features if column not in frame.columns]
    if missing:
        raise ValueError(f"missing Binance-canonical feature columns: {missing}")
    weights = dict(feature_weights or BINANCE_OHLCV_CORE_WEIGHTS)
    abs_sum = sum(abs(float(weights.get(column, 0.0))) for column in features)
    normalized_weights = {
        column: (float(weights.get(column, 0.0)) / abs_sum if abs_sum > 0.0 else 0.0)
        for column in features
    }
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]
    multipliers = dict(contribution_multipliers or {})
    raw_score = pd.Series(0.0, index=frame.index, dtype="float64")
    for column in features:
        term = normalized_weights[column] * _timestamp_zscore(
            pd.to_numeric(frame[column], errors="coerce"),
            timestamps,
        )
        if column in multipliers:
            # Frozen risk-overlay contribution mask. Cross-sectional standardization above
            # is computed over the FULL panel (unchanged); only this one factor's
            # post-standardization contribution is scaled per-row. A missing/non-finite
            # multiplier falls back to 1.0 (no mask): callers MUST fail closed upstream on
            # missing overlay gauges, so this fallback is a defensive no-op, never a silent
            # risk-off that could mask the rest of the cross-section.
            mult = (
                pd.to_numeric(multipliers[column], errors="coerce")
                .reindex(frame.index)
                .replace([np.inf, -np.inf], np.nan)
                .fillna(1.0)
                .astype("float64")
            )
            term = term * mult
        raw_score = raw_score + term
    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return pd.Series(np.tanh(centered_rank * 1.80), index=frame.index, dtype="float64")


def prepare_scored_backtest_frame(
    panel: pd.DataFrame,
    *,
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    resolved_config = dict(config or load_strategy_config())
    feature_columns = [str(item) for item in resolved_config.get("feature_columns", ALLOWED_ALPHA_FEATURES)]
    allow_feature_subset = _allow_feature_subset(resolved_config)
    purity = validate_alpha_feature_columns(
        feature_columns,
        allowed_columns=ALLOWED_ALPHA_FEATURES,
        forbidden_patterns=resolved_config.get("excluded_source_patterns", FORBIDDEN_ALPHA_PATTERNS),
        require_all_allowed=not allow_feature_subset,
    )
    if not purity["passed"]:
        return pd.DataFrame(), {"purity_check": purity, "blockers": [{"code": "sidecar_alpha_contamination", "detail": purity}]}
    if panel.empty:
        return panel.copy(), {"purity_check": purity, "blockers": [{"code": "empty_panel"}]}
    missing = [column for column in feature_columns if column not in panel.columns]
    if missing:
        return pd.DataFrame(), {"purity_check": purity, "blockers": [{"code": "missing_feature_columns", "columns": missing}]}
    scored = panel.copy()
    if "universe_active" not in scored.columns:
        scored["universe_active"] = True
    universe_active = _truthy_series(scored["universe_active"])
    price_valid_mask = pd.Series(True, index=scored.index, dtype="bool")
    for column in ("timestamp_ms", "perp_close", "perp_quote_volume_usd"):
        if column not in scored.columns:
            price_valid_mask &= False
        else:
            price_valid_mask &= pd.to_numeric(scored[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()
    price_valid_mask &= scored["subject"].notna() if "subject" in scored.columns else False
    feature_valid_mask = pd.Series(True, index=scored.index, dtype="bool")
    for column in feature_columns:
        feature_valid_mask &= pd.to_numeric(scored[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()
    scored["score"] = 0.0
    score_mask = universe_active & feature_valid_mask & price_valid_mask
    if bool(score_mask.any()):
        scored.loc[score_mask, "score"] = score_binance_ohlcv_core(
            scored.loc[score_mask].copy(),
            feature_columns=feature_columns,
            feature_weights=dict(resolved_config.get("feature_weights") or BINANCE_OHLCV_CORE_WEIGHTS),
            require_complete_feature_set=not allow_feature_subset,
        )
    label_valid_mask = (
        pd.to_numeric(scored.get("target_execution_forward_return"), errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .notna()
        if "target_execution_forward_return" in scored.columns
        else pd.Series(False, index=scored.index, dtype="bool")
    )
    scored["binance_decision_eligible"] = score_mask & label_valid_mask
    scored = scored.loc[price_valid_mask].copy()
    if "funding_rate" not in scored.columns:
        scored["funding_rate"] = np.nan
    if "funding_sample_count" not in scored.columns:
        scored["funding_sample_count"] = 0.0
    scored = add_pit_strategy_eligibility(scored, config=resolved_config)
    scored = add_binance_risk_brake_columns(scored, config=resolved_config)
    scored["has_perp"] = True
    scored["perp_execution_eligible"] = True
    scored["perp_executable_start_ms"] = scored.groupby("subject")["timestamp_ms"].transform("min")
    support_columns = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "usdm_symbol",
        "liquidity_bucket",
        "universe_active",
        "binance_decision_eligible",
        "binance_pit_data_eligible",
        "binance_pit_top_long_eligible",
        "binance_pit_mid_short_eligible",
        "binance_pit_active_long_eligible",
        "pit_recent_valid_day_count",
        "pit_recent_coverage_ratio",
        "pit_recent_consecutive_valid_day_count",
        "pit_recent_active_day_count",
        "pit_recent_top_bucket_day_count",
        "pit_recent_mid_bucket_day_count",
        "pit_lifetime_valid_day_count",
        "pit_lifetime_gap_rate",
        "universe_rank",
        "universe_selection_rule",
        "universe_valid_daily_count_lookback",
        "universe_coverage_ratio_lookback",
        "universe_median_quote_volume_usd_lookback",
        "score",
        "target_forward_return",
        "target_up",
        "target_execution_forward_return",
        "target_execution_up",
        "spot_open",
        "spot_high",
        "spot_low",
        "spot_close",
        "spot_volume",
        "spot_quote_volume",
        "perp_open",
        "perp_high",
        "perp_low",
        "perp_close",
        "perp_volume",
        "perp_quote_volume_usd",
        "has_perp",
        "perp_execution_eligible",
        "perp_executable_start_ms",
        "funding_rate",
        "funding_sample_count",
        *BINANCE_RISK_BRAKE_COLUMNS,
    ]
    keep_columns = [column for column in [*support_columns, *feature_columns] if column in scored.columns]
    scored = scored.loc[:, list(dict.fromkeys(keep_columns))].copy()
    return scored.reset_index(drop=True), {"purity_check": purity, "blockers": []}


def add_pit_strategy_eligibility(frame: pd.DataFrame, *, config: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return output
    base_eligible = (
        _truthy_series(output["binance_decision_eligible"])
        if "binance_decision_eligible" in output.columns
        else pd.Series(True, index=output.index, dtype="bool")
    )
    pit_data_eligible, audit_columns = _pit_recent_data_eligible(output, config=config)
    for column, values in audit_columns.items():
        output[column] = values
    output["binance_pit_data_eligible"] = pit_data_eligible.astype("bool")
    if "liquidity_bucket" in output.columns:
        bucket = output["liquidity_bucket"].astype(str)
    else:
        bucket = pd.Series("", index=output.index, dtype="object")
    if "universe_active" in output.columns:
        universe_active = _truthy_series(output["universe_active"])
    else:
        universe_active = pd.Series(True, index=output.index, dtype="bool")
    eligible = base_eligible & output["binance_pit_data_eligible"] & universe_active
    policy = dict(config.get("pit_data_eligibility_policy") or {})
    min_same_bucket_days = max(int(policy.get("min_same_bucket_days", 0) or 0), 0)
    if min_same_bucket_days > 0:
        min_same_bucket = float(min_same_bucket_days)
        recent_active_ok = pd.to_numeric(
            output.get("pit_recent_active_day_count", pd.Series(0.0, index=output.index)),
            errors="coerce",
        ).fillna(0.0).ge(min_same_bucket)
        recent_top_ok = pd.to_numeric(
            output.get("pit_recent_top_bucket_day_count", pd.Series(0.0, index=output.index)),
            errors="coerce",
        ).fillna(0.0).ge(min_same_bucket)
        recent_mid_ok = pd.to_numeric(
            output.get("pit_recent_mid_bucket_day_count", pd.Series(0.0, index=output.index)),
            errors="coerce",
        ).fillna(0.0).ge(min_same_bucket)
    else:
        recent_active_ok = pd.Series(True, index=output.index, dtype="bool")
        recent_top_ok = pd.Series(True, index=output.index, dtype="bool")
        recent_mid_ok = pd.Series(True, index=output.index, dtype="bool")
    rank = pd.to_numeric(
        output.get("universe_rank", pd.Series(np.nan, index=output.index)),
        errors="coerce",
    )
    long_max_rank_raw = policy.get("long_max_universe_rank")
    short_max_rank_raw = policy.get("short_max_universe_rank", policy.get("max_mid_short_universe_rank"))
    long_rank_ok = (
        rank.le(float(long_max_rank_raw))
        if long_max_rank_raw is not None
        else pd.Series(True, index=output.index, dtype="bool")
    )
    short_rank_ok = (
        rank.le(float(short_max_rank_raw))
        if short_max_rank_raw is not None
        else pd.Series(True, index=output.index, dtype="bool")
    )
    output["binance_pit_top_long_eligible"] = (eligible & bucket.eq("top_liquidity") & recent_top_ok & long_rank_ok).astype("bool")
    output["binance_pit_mid_short_eligible"] = (eligible & bucket.eq("mid_liquidity") & recent_mid_ok & short_rank_ok).astype("bool")
    output["binance_pit_active_long_eligible"] = (eligible & recent_active_ok).astype("bool")
    return output


def _pit_recent_data_eligible(frame: pd.DataFrame, *, config: dict[str, Any]) -> tuple[pd.Series, dict[str, pd.Series]]:
    policy = dict(config.get("pit_data_eligibility_policy") or {})
    mode = str(policy.get("mode") or "disabled").strip().lower()
    index = frame.index
    if mode in {"", "none", "disabled", "off"}:
        return (
            pd.Series(True, index=index, dtype="bool"),
            {
                "pit_recent_valid_day_count": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_recent_coverage_ratio": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_recent_consecutive_valid_day_count": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_recent_active_day_count": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_recent_top_bucket_day_count": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_recent_mid_bucket_day_count": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_lifetime_valid_day_count": pd.Series(np.nan, index=index, dtype="float64"),
                "pit_lifetime_gap_rate": pd.Series(np.nan, index=index, dtype="float64"),
            },
        )
    lookback_days = max(int(policy.get("lookback_days", 30) or 30), 1)
    min_coverage_ratio = float(policy.get("min_coverage_ratio", 0.95) or 0.95)
    min_consecutive_valid_days = max(int(policy.get("min_consecutive_valid_days", 10) or 10), 1)
    min_lifetime_valid_days = max(int(policy.get("min_lifetime_valid_days", 0) or 0), 0)
    max_lifetime_gap_rate_raw = policy.get("max_lifetime_gap_rate")
    max_lifetime_gap_rate = (
        float(max_lifetime_gap_rate_raw) if max_lifetime_gap_rate_raw is not None else None
    )
    require_current_funding_sample = bool(policy.get("require_current_funding_sample", False))
    min_funding_sample_count = float(policy.get("min_funding_sample_count", 1.0) or 1.0)

    recent_valid = pd.Series(0.0, index=index, dtype="float64")
    recent_consecutive = pd.Series(0.0, index=index, dtype="float64")
    recent_active = pd.Series(0.0, index=index, dtype="float64")
    recent_top_bucket = pd.Series(0.0, index=index, dtype="float64")
    recent_mid_bucket = pd.Series(0.0, index=index, dtype="float64")
    lifetime_valid = pd.Series(0.0, index=index, dtype="float64")
    lifetime_gap_rate = pd.Series(np.nan, index=index, dtype="float64")
    working = frame.loc[
        :, [column for column in ("subject", "timestamp_ms", "universe_active", "liquidity_bucket") if column in frame.columns]
    ].copy()
    if {"subject", "timestamp_ms"}.issubset(working.columns):
        if "universe_active" not in working.columns:
            working["universe_active"] = True
        if "liquidity_bucket" not in working.columns:
            working["liquidity_bucket"] = ""
        working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce")
        working = working.dropna(subset=["subject", "timestamp_ms"]).copy()
        if not working.empty:
            working["timestamp_ms"] = working["timestamp_ms"].astype("int64")
            for _, group in working.sort_values(["subject", "timestamp_ms"]).groupby("subject", sort=True):
                dates = pd.to_datetime(group["timestamp_ms"], unit="ms", utc=True)
                ones = pd.Series(1.0, index=dates)
                active = _truthy_series(group["universe_active"])
                bucket = group["liquidity_bucket"].astype(str)
                recent_valid.loc[group.index] = ones.rolling(f"{lookback_days}D", min_periods=1).sum().to_numpy(dtype="float64")
                recent_consecutive.loc[group.index] = (
                    ones.rolling(f"{min_consecutive_valid_days}D", min_periods=1).sum().to_numpy(dtype="float64")
                )
                recent_active.loc[group.index] = (
                    pd.Series(active.astype("float64").to_numpy(), index=dates)
                    .rolling(f"{lookback_days}D", min_periods=1)
                    .sum()
                    .to_numpy(dtype="float64")
                )
                recent_top_bucket.loc[group.index] = (
                    pd.Series((active & bucket.eq("top_liquidity")).astype("float64").to_numpy(), index=dates)
                    .rolling(f"{lookback_days}D", min_periods=1)
                    .sum()
                    .to_numpy(dtype="float64")
                )
                recent_mid_bucket.loc[group.index] = (
                    pd.Series((active & bucket.eq("mid_liquidity")).astype("float64").to_numpy(), index=dates)
                    .rolling(f"{lookback_days}D", min_periods=1)
                    .sum()
                    .to_numpy(dtype="float64")
                )
                valid_count = pd.Series(np.arange(1, len(group) + 1, dtype="float64"), index=group.index)
                age_days = (
                    ((dates - dates.iloc[0]) / pd.Timedelta(days=1))
                    .astype("float64")
                    .add(1.0)
                    .clip(lower=1.0)
                )
                lifetime_valid.loc[group.index] = valid_count
                lifetime_gap_rate.loc[group.index] = np.clip(
                    1.0 - (valid_count.to_numpy(dtype="float64") / age_days.to_numpy(dtype="float64")),
                    0.0,
                    1.0,
                )
    coverage_ratio = (recent_valid / float(lookback_days)).clip(lower=0.0, upper=1.0)
    eligible = coverage_ratio.ge(min_coverage_ratio) & recent_consecutive.ge(float(min_consecutive_valid_days))
    if min_lifetime_valid_days > 0:
        eligible &= lifetime_valid.ge(float(min_lifetime_valid_days))
    if max_lifetime_gap_rate is not None:
        eligible &= lifetime_gap_rate.fillna(1.0).le(max_lifetime_gap_rate)
    if require_current_funding_sample:
        if "funding_sample_count" in frame.columns:
            funding_sample_count = pd.to_numeric(frame["funding_sample_count"], errors="coerce").fillna(0.0)
        else:
            funding_sample_count = pd.Series(0.0, index=index, dtype="float64")
        eligible &= funding_sample_count.ge(min_funding_sample_count)
    return (
        eligible.astype("bool"),
        {
            "pit_recent_valid_day_count": recent_valid,
            "pit_recent_coverage_ratio": coverage_ratio,
            "pit_recent_consecutive_valid_day_count": recent_consecutive,
            "pit_recent_active_day_count": recent_active,
            "pit_recent_top_bucket_day_count": recent_top_bucket,
            "pit_recent_mid_bucket_day_count": recent_mid_bucket,
            "pit_lifetime_valid_day_count": lifetime_valid,
            "pit_lifetime_gap_rate": lifetime_gap_rate,
        },
    )


def run_binance_canonical_validation(
    *,
    store_root: Path = DEFAULT_STORE_ROOT,
    as_of: str | date = "2026-04-30",
    strategy_label: str = STRATEGY_LABEL,
    config_path: Path | None = None,
    funding_root: Path | None = None,
    backfill_funding: bool = False,
    force_funding: bool = False,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    report_root: Path = DEFAULT_REPORT_ROOT,
    symbols: Iterable[str] | None = None,
    max_symbols: int | None = None,
    top_n: int | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    run_id: str | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    config = load_strategy_config(config_path)
    config["strategy_label"] = str(strategy_label or config.get("strategy_label") or STRATEGY_LABEL)
    strategy_profile = dict(config.get("strategy_profile") or {})
    strategy_profile.setdefault("decision_eligible_column", "binance_decision_eligible")
    config["strategy_profile"] = strategy_profile
    resolved_funding_root = _resolve_funding_root(config=config, funding_root=funding_root)
    dataset = build_binance_canonical_dataset(
        store_root=Path(store_root),
        as_of=as_of,
        config=config,
        funding_root=resolved_funding_root,
        symbols=symbols,
        max_symbols=max_symbols,
        top_n=top_n,
        start_month=start_month,
        end_month=end_month,
    )
    funding_sync_summary: dict[str, Any] | None = None
    if backfill_funding and dataset.dataset_manifest.get("selected_universe"):
        universe_symbols = [str(item["symbol"]) for item in dataset.dataset_manifest["selected_universe"]]
        start_dt = _ms_to_date(int(dataset.dataset_manifest["start_timestamp_ms"]))
        end_dt = _parse_date(as_of)
        funding_sync_summary = sync_funding_cost_history(
            symbols=universe_symbols,
            start=start_dt,
            end=end_dt,
            funding_root=resolved_funding_root,
            force=force_funding,
        )
        dataset = BinanceCanonicalDataset(
            panel=attach_funding_cost_to_panel(dataset.panel, funding_root=resolved_funding_root),
            dataset_manifest={
                **dataset.dataset_manifest,
                "funding_cost_sync_summary": funding_sync_summary,
            },
            gap_audit=dataset.gap_audit,
            feature_manifest=dataset.feature_manifest,
        )
    scored_frame, scoring_audit = prepare_scored_backtest_frame(dataset.panel, config=config)
    blockers: list[dict[str, Any]] = list(dataset.dataset_manifest.get("blockers") or [])
    blockers.extend(scoring_audit.get("blockers") or [])
    execution_gap_policy_audit: dict[str, Any] = {"mode": "none", "applied": False}
    if not scored_frame.empty:
        scored_frame, execution_gap_policy_audit = apply_selected_path_gap_symbol_exclusion(
            scored_frame,
            config=config,
        )
        dataset.dataset_manifest["execution_gap_policy"] = execution_gap_policy_audit

    metrics: dict[str, Any] = {}
    falsification: dict[str, Any] = {}
    attribution = _empty_position_attribution()
    ablations: dict[str, Any] = {}
    factor_attribution = _empty_factor_leave_one_out()
    paper_shadow_execution = _empty_paper_shadow_execution_ledger()
    base_periods: list[dict[str, Any]] = []
    if scored_frame.empty:
        blockers.append({"code": "empty_scored_backtest_frame", "message": "No rows survived feature and label gates."})
    else:
        split_contract = _split_contract(config)
        base_metrics = _run_backtest(scored_frame, config=config, scenario="base", include_periods=True)
        stress_metrics = _run_backtest(scored_frame, config=config, scenario="stress", include_periods=True)
        base_periods = list(base_metrics.get("periods") or [])
        metrics = {
            "base": _strip_periods(base_metrics),
            "stress": _strip_periods(stress_metrics),
            "split_realization_contract": split_contract,
            "rank_ic": _rank_ic_summary(
                scored_frame,
                score_column="score",
                target_column="target_execution_forward_return",
            ),
        }
        falsification = _run_falsification_suite(scored_frame, config=config)
        attribution = compute_position_attribution(scored_frame, config=config)
        factor_attribution = compute_factor_leave_one_out_attribution(scored_frame, config=config)
        paper_shadow_execution = build_paper_shadow_execution_ledger(scored_frame, config=config)
        ablations = run_binance_core_ablations(scored_frame, config=config)
        execution_data_gap_blockers = sorted(
            {
                str(item)
                for payload in (base_metrics, stress_metrics)
                for item in list(payload.get("data_gap_blockers") or [])
            }
        )
        if execution_data_gap_blockers:
            blockers.append(
                {
                    "code": "execution_data_gap_blockers",
                    "message": "Fill/exit prices were unavailable for at least one selected holding.",
                    "data_gap_blockers": execution_data_gap_blockers,
                }
            )
        if int(base_metrics.get("rebalance_count", 0) or 0) < int(config.get("min_oos_periods", 60) or 60):
            blockers.append(
                {
                    "code": "oos_period_count_below_gate",
                    "observed": int(base_metrics.get("rebalance_count", 0) or 0),
                    "required": int(config.get("min_oos_periods", 60) or 60),
                }
            )
        if _funding_cost_status(scored_frame)["status"] != "ok":
            blockers.append(_funding_cost_status(scored_frame))

    status, gate_results = _validation_status(metrics=metrics, falsification=falsification, blockers=blockers, config=config)
    validation_report = {
        "generated_at_utc": utc_now(),
        "strategy_label": config["strategy_label"],
        "parent_label": str(config.get("parent_label") or PARENT_LABEL),
        "status": status,
        "blockers": blockers,
        "metrics": metrics,
        "falsification": falsification,
        "attribution": attribution["summary"],
        "factor_attribution": factor_attribution["summary"],
        "paper_shadow_execution": paper_shadow_execution["summary"],
        "ablations": ablations.get("summary", {}),
        "gate_results": gate_results,
        "dataset_manifest": dataset.dataset_manifest,
        "feature_manifest": dataset.feature_manifest,
        "scored_row_count": int(len(scored_frame)),
        "funding_cost_status": _funding_cost_status(scored_frame),
        "funding_cost_sync_summary": funding_sync_summary,
        "execution_gap_policy": execution_gap_policy_audit,
        "risk_overlay_policy": dict(config.get("risk_overlay_policy") or {}),
        "sidecar_policy": {
            "sidecars_allowed_in_core_alpha": False,
            "sidecars_allowed_later_as": ["realtime_gate", "risk_veto", "explanatory_variable"],
        },
    }
    paths: dict[str, str] = {}
    if write_outputs:
        resolved_run_id = run_id or _default_run_id(strategy_label=config["strategy_label"])
        paths = write_validation_artifacts(
            run_root=Path(output_root) / resolved_run_id,
            report_root=Path(report_root),
            dataset_manifest=dataset.dataset_manifest,
            gap_audit=dataset.gap_audit,
            feature_manifest=dataset.feature_manifest,
            validation_report=validation_report,
            scored_frame=scored_frame,
            base_periods=base_periods,
            attribution=attribution,
            factor_attribution=factor_attribution,
            paper_shadow_execution=paper_shadow_execution,
            ablations=ablations,
        )
    return {**validation_report, "artifact_paths": paths}


def write_validation_artifacts(
    *,
    run_root: Path,
    report_root: Path,
    dataset_manifest: dict[str, Any],
    gap_audit: dict[str, Any],
    feature_manifest: dict[str, Any],
    validation_report: dict[str, Any],
    scored_frame: pd.DataFrame,
    base_periods: Any = None,
    attribution: dict[str, Any] | None = None,
    factor_attribution: dict[str, Any] | None = None,
    paper_shadow_execution: dict[str, Any] | None = None,
    ablations: dict[str, Any] | None = None,
) -> dict[str, str]:
    run_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "dataset_manifest": run_root / "dataset_manifest.json",
        "gap_audit": run_root / "gap_audit.json",
        "feature_manifest": run_root / "feature_manifest.json",
        "validation_report": run_root / "validation_report.json",
        "aligned_period_returns": run_root / "aligned_period_returns.csv",
        "universe_membership": run_root / "universe_membership.csv",
        "position_attribution": run_root / "position_attribution.csv",
        "attribution_by_side_year": run_root / "attribution_by_side_year.csv",
        "attribution_by_symbol_year": run_root / "attribution_by_symbol_year.csv",
        "attribution_summary": run_root / "attribution_summary.json",
        "factor_leave_one_out": run_root / "factor_leave_one_out.csv",
        "factor_leave_one_out_summary": run_root / "factor_leave_one_out_summary.json",
        "factor_leave_one_out_by_side": run_root / "factor_leave_one_out_by_side.csv",
        "factor_leave_one_out_by_year": run_root / "factor_leave_one_out_by_year.csv",
        "factor_leave_one_out_by_side_year": run_root / "factor_leave_one_out_by_side_year.csv",
        "paper_shadow_execution_ledger": run_root / "paper_shadow_execution_ledger.csv",
        "paper_shadow_execution_summary": run_root / "paper_shadow_execution_summary.json",
        "ablation_summary": run_root / "ablation_summary.json",
        "ablation_period_returns": run_root / "ablation_period_returns.csv",
    }
    _write_json(paths["dataset_manifest"], dataset_manifest)
    _write_json(paths["gap_audit"], gap_audit)
    _write_json(paths["feature_manifest"], feature_manifest)
    report_payload = dict(validation_report)
    report_payload["metrics"] = _drop_periods_from_metrics(report_payload.get("metrics") or {})
    _write_json(paths["validation_report"], report_payload)
    periods = base_periods if isinstance(base_periods, list) else None
    if periods is None and validation_report.get("metrics", {}).get("base", {}).get("periods"):
        periods = validation_report["metrics"]["base"]["periods"]
    if periods:
        pd.DataFrame(periods).to_csv(paths["aligned_period_returns"], index=False)
    else:
        pd.DataFrame(columns=["timestamp_ms", "net_period_return"]).to_csv(paths["aligned_period_returns"], index=False)
    _write_universe_membership(scored_frame, paths["universe_membership"])
    resolved_attribution = attribution or _empty_position_attribution()
    _write_json(paths["attribution_summary"], resolved_attribution.get("summary") or {})
    _frame_or_empty(resolved_attribution.get("position_attribution")).to_csv(paths["position_attribution"], index=False)
    _frame_or_empty(resolved_attribution.get("by_side_year")).to_csv(paths["attribution_by_side_year"], index=False)
    _frame_or_empty(resolved_attribution.get("by_symbol_year")).to_csv(paths["attribution_by_symbol_year"], index=False)
    resolved_factor_attribution = factor_attribution or _empty_factor_leave_one_out()
    _write_json(paths["factor_leave_one_out_summary"], resolved_factor_attribution.get("summary") or {})
    _frame_or_empty(resolved_factor_attribution.get("leave_one_out")).to_csv(paths["factor_leave_one_out"], index=False)
    _frame_or_empty(resolved_factor_attribution.get("by_side")).to_csv(paths["factor_leave_one_out_by_side"], index=False)
    _frame_or_empty(resolved_factor_attribution.get("by_year")).to_csv(paths["factor_leave_one_out_by_year"], index=False)
    _frame_or_empty(resolved_factor_attribution.get("by_side_year")).to_csv(paths["factor_leave_one_out_by_side_year"], index=False)
    resolved_paper_shadow = paper_shadow_execution or _empty_paper_shadow_execution_ledger()
    _write_json(paths["paper_shadow_execution_summary"], resolved_paper_shadow.get("summary") or {})
    _frame_or_empty(resolved_paper_shadow.get("ledger")).to_csv(paths["paper_shadow_execution_ledger"], index=False)
    resolved_ablations = ablations or {"summary": {}, "period_returns": pd.DataFrame()}
    _write_json(paths["ablation_summary"], resolved_ablations.get("summary") or {})
    _frame_or_empty(resolved_ablations.get("period_returns")).to_csv(paths["ablation_period_returns"], index=False)

    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / f"binance_canonical_h10d_validation_{_today_compact()}.md"
    report_path.write_text(_render_markdown_report(validation_report, paths), encoding="utf-8")
    paths["markdown_report"] = report_path
    return {key: str(path) for key, path in paths.items()}


def _daily_bars_to_feature_panel(
    *,
    daily: pd.DataFrame,
    four_h: pd.DataFrame,
    one_h: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    subject = symbol_to_subject(symbol)
    output = daily.sort_values("open_time_ms").copy()
    output["timestamp_ms"] = output["open_time_ms"].astype("int64")
    output["date_utc"] = _date_utc_series(output["timestamp_ms"])
    output["subject"] = subject
    output["usdm_symbol"] = symbol
    output["spot_open"] = output["open"]
    output["spot_high"] = output["high"]
    output["spot_low"] = output["low"]
    output["spot_close"] = output["close"]
    output["spot_volume"] = output["volume"]
    output["spot_quote_volume"] = output["quote_volume"]
    output["perp_open"] = output["open"]
    output["perp_high"] = output["high"]
    output["perp_low"] = output["low"]
    output["perp_close"] = output["close"]
    output["perp_volume"] = output["volume"]
    output["perp_quote_volume_usd"] = output["quote_volume"]
    output["has_perp"] = True
    output["perp_execution_eligible"] = True
    output["perp_executable_start_ms"] = int(output["timestamp_ms"].min())
    iv_by_day = _intraday_realized_vol_by_day(four_h)
    settle_by_day = _settlement_premium_by_day(one_h)
    output = output.merge(iv_by_day, on="date_utc", how="left")
    output = output.merge(settle_by_day, on="date_utc", how="left")
    return add_binance_ohlcv_core_features(output)


def add_binance_ohlcv_core_features(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    frames = []
    for _, group in panel.groupby("subject", sort=True):
        frame = group.sort_values("timestamp_ms").copy()
        close = pd.to_numeric(frame["perp_close"], errors="coerce").replace(0.0, np.nan)
        high = pd.to_numeric(frame["perp_high"], errors="coerce")
        returns = close.pct_change(fill_method=None)
        frame["return_1"] = returns
        frame["realized_volatility_5"] = returns.rolling(5).std()
        high_60 = high.rolling(60).max()
        high_5 = high.rolling(5).max()
        frame["distance_to_high_60"] = close / high_60.replace(0.0, np.nan) - 1.0
        frame["distance_to_high_5"] = close / high_5.replace(0.0, np.nan) - 1.0
        quote_volume = pd.to_numeric(frame["perp_quote_volume_usd"], errors="coerce")
        qv_mean_20 = quote_volume.rolling(20).mean()
        frame["quote_volume_expansion"] = quote_volume / qv_mean_20.replace(0.0, np.nan)
        momentum_5 = close.pct_change(5, fill_method=None)
        momentum_20 = close.pct_change(20, fill_method=None)
        frame["momentum_5"] = momentum_5
        frame["momentum_20"] = momentum_20
        frame["momentum_decay_5_20"] = momentum_5 - momentum_20
        iv = pd.to_numeric(frame["intraday_realized_vol_4h_to_1d"], errors="coerce")
        frame["intraday_realized_vol_4h_to_1d_smooth_60"] = iv.rolling(60).mean()
        frame["liquidity_stress_qv_iv"] = frame["quote_volume_expansion"] * iv
        ret_neg = returns.where(returns < 0)
        ret_pos = returns.where(returns > 0)
        neg_std = ret_neg.rolling(30, min_periods=5).std()
        pos_std = ret_pos.rolling(30, min_periods=5).std()
        frame["downside_upside_vol_ratio_30"] = neg_std / pos_std.replace(0.0, np.nan)
        frame["target_forward_return"] = close.shift(-10) / close - 1.0
        frame["target_up"] = (frame["target_forward_return"] > 0.0).astype("int64")
        entry_close = close.shift(-1)
        exit_close = close.shift(-11)
        frame["target_execution_forward_return"] = exit_close / entry_close - 1.0
        frame["target_execution_up"] = (frame["target_execution_forward_return"] > 0.0).astype("int64")
        frames.append(frame)
    output = pd.concat(frames, ignore_index=True, sort=False)
    with pd.option_context("future.no_silent_downcasting", True):
        output = output.replace([np.inf, -np.inf], np.nan)
    return output


def _intraday_realized_vol_by_day(four_h: pd.DataFrame) -> pd.DataFrame:
    if four_h.empty:
        return pd.DataFrame(columns=["date_utc", "intraday_realized_vol_4h_to_1d"])
    frame = four_h.sort_values("open_time_ms").copy()
    frame["date_utc"] = _date_utc_series(frame["open_time_ms"])
    close = pd.to_numeric(frame["close"], errors="coerce").replace(0.0, np.nan)
    frame["log_return_4h"] = np.log(close / close.shift(1))

    def _rv(group: pd.DataFrame) -> float:
        returns = pd.to_numeric(group["log_return_4h"], errors="coerce").dropna()
        if len(group) != 6 or len(returns) != 6:
            return float("nan")
        return float(math.sqrt(float(np.square(returns).sum())))

    return (
        frame.groupby("date_utc", sort=True)
        .apply(_rv, include_groups=False)
        .rename("intraday_realized_vol_4h_to_1d")
        .reset_index()
    )


def _settlement_premium_by_day(one_h: pd.DataFrame) -> pd.DataFrame:
    if one_h.empty:
        return pd.DataFrame(columns=["date_utc", "settlement_cycle_premium_60d"])
    frame = one_h.sort_values("open_time_ms").copy()
    frame["date_utc"] = _date_utc_series(frame["open_time_ms"])
    frame["hour_utc"] = pd.to_datetime(frame["open_time_ms"].astype("int64"), unit="ms", utc=True).dt.hour
    close = pd.to_numeric(frame["close"], errors="coerce").replace(0.0, np.nan)
    frame["log_return_1h"] = np.log(close / close.shift(1))

    def _daily_premium(group: pd.DataFrame) -> float:
        returns = pd.to_numeric(group["log_return_1h"], errors="coerce")
        if len(group) != 24 or returns.notna().sum() != 24:
            return float("nan")
        pre = returns.loc[group["hour_utc"].isin({7, 15, 23})]
        other = returns.loc[~group["hour_utc"].isin({7, 15, 23})]
        if len(pre) != 3 or len(other) != 21:
            return float("nan")
        return float(pre.mean() - other.mean())

    raw = (
        frame.groupby("date_utc", sort=True)
        .apply(_daily_premium, include_groups=False)
        .rename("settlement_cycle_premium_raw")
        .reset_index()
    )
    raw["settlement_cycle_premium_60d"] = raw["settlement_cycle_premium_raw"].rolling(60, min_periods=60).mean()
    return raw[["date_utc", "settlement_cycle_premium_60d"]].copy()


def _run_backtest(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any],
    scenario: str,
    include_periods: bool = False,
) -> dict[str, Any]:
    cost_model = resolve_execution_cost_model(scenario=scenario)
    cost_model["require_perp_inventory_open_interest"] = False
    return backtest_cross_sectional(
        frame=frame,
        constraints=dict(config.get("strategy_profile") or {}),
        split_realization_contract=_split_contract(config),
        execution_cost_model=cost_model,
        reference_capital_usd=float(config.get("reference_capital_usd", 1_000_000.0) or 1_000_000.0),
        capacity_limits=dict(config.get("capacity_limits") or {}),
        include_periods=include_periods,
    )


def apply_selected_path_gap_symbol_exclusion(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    policy = dict(config.get("execution_gap_policy") or {})
    mode = str(policy.get("mode") or "none").strip().lower()
    if mode in {"pit_recent_completeness", "pit_recent_completeness_only"}:
        return frame.copy(), {
            "mode": mode,
            "applied": False,
            "selection_rule": "no future fill/exit path exclusion; eligibility is based on point-in-time recent completeness columns",
            "future_label_usage": False,
            "alpha_source_usage": False,
            "row_count_before": int(len(frame)),
            "row_count_after": int(len(frame)),
            "residual_data_gap_blockers": [],
            "status": "pit_eligibility_only",
        }
    if mode not in {"drop_selected_path_gap_symbols", "drop_gap_symbols"}:
        return frame.copy(), {
            "mode": mode or "none",
            "applied": False,
            "row_count_before": int(len(frame)),
            "row_count_after": int(len(frame)),
        }
    max_iterations = max(int(policy.get("max_iterations", 5) or 5), 1)
    working = frame.copy()
    excluded_subjects: list[str] = []
    iterations: list[dict[str, Any]] = []
    for iteration in range(1, max_iterations + 1):
        gaps = _execution_data_gap_blockers_for_frame(working, config=config)
        gap_subjects = sorted(set(_subjects_from_data_gap_blockers(gaps)) - set(excluded_subjects))
        iterations.append(
            {
                "iteration": iteration,
                "row_count_before": int(len(working)),
                "data_gap_blockers": gaps,
                "gap_subjects": gap_subjects,
            }
        )
        if not gap_subjects:
            break
        excluded_subjects.extend(gap_subjects)
        working = working.loc[~working["subject"].astype(str).isin(gap_subjects)].copy()
    residual_gaps = _execution_data_gap_blockers_for_frame(working, config=config)
    audit = {
        "mode": "drop_selected_path_gap_symbols",
        "applied": True,
        "selection_rule": "exclude entire symbols after any selected holding lacks fill/exit execution prices in this historical validation",
        "future_label_usage": False,
        "alpha_source_usage": False,
        "max_iterations": max_iterations,
        "iteration_count": int(len(iterations)),
        "excluded_subjects": sorted(set(excluded_subjects)),
        "excluded_symbols": [f"{subject}USDT" for subject in sorted(set(excluded_subjects))],
        "row_count_before": int(len(frame)),
        "row_count_after": int(len(working)),
        "residual_data_gap_blockers": residual_gaps,
        "status": "ok" if not residual_gaps else "residual_gap_blockers",
        "iterations": iterations,
    }
    return working.reset_index(drop=True), audit


def _execution_data_gap_blockers_for_frame(frame: pd.DataFrame, *, config: dict[str, Any]) -> list[str]:
    if frame.empty:
        return []
    blockers: set[str] = set()
    for scenario in ("base", "stress"):
        metrics = _run_backtest(frame, config=config, scenario=scenario, include_periods=False)
        blockers.update(str(item) for item in list(metrics.get("data_gap_blockers") or []))
    return sorted(blockers)


def _subjects_from_data_gap_blockers(blockers: Iterable[str]) -> list[str]:
    subjects: list[str] = []
    for item in blockers:
        text = str(item)
        if ": missing " not in text:
            continue
        subject = text.split(":", 1)[0].strip()
        if subject:
            subjects.append(subject)
    return subjects


def compute_position_attribution(frame: pd.DataFrame, *, config: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return _empty_position_attribution()
    constraints = dict(config.get("strategy_profile") or {})
    cost_model = resolve_execution_cost_model(scenario="base")
    cost_model["require_perp_inventory_open_interest"] = False
    execution_venue = str(constraints.get("execution_venue") or ("spot" if constraints.get("spot_only") else "perp"))
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return _empty_position_attribution()
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    split_contract = _split_contract(config)
    evaluation_step_bars = max(int(split_contract.get("realization_step_bars", 0) or 0), 1)
    if "realization_step_bars" not in split_contract:
        target_horizon = int(split_contract.get("target_horizon_bars", 10) or 10)
        evaluation_step_bars = max(target_horizon, 1)
    timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
    decision_timestamp_indices = list(range(0, len(timestamps), evaluation_step_bars))
    latency_bars = int(cost_model["latency_bars"])
    grouped = {timestamp: group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}
    previous_weights: dict[str, float] = {}
    records: list[dict[str, Any]] = []
    data_gap_blockers: set[str] = set()
    for decision_offset, timestamp_offset in enumerate(decision_timestamp_indices):
        fill_offset = timestamp_offset + latency_bars
        if fill_offset >= len(timestamps):
            break
        decision_timestamp = int(timestamps[timestamp_offset])
        fill_timestamp = int(timestamps[fill_offset])
        next_fill_offset = _next_fill_offset(
            timestamp_count=len(timestamps),
            decision_timestamp_indices=decision_timestamp_indices,
            decision_offset=decision_offset,
            latency_bars=latency_bars,
        )
        exit_timestamp = int(timestamps[next_fill_offset]) if next_fill_offset is not None else int(timestamps[-1])
        decision_group = grouped[decision_timestamp]
        raw_target_weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints=constraints,
            previous_weights=previous_weights,
        )
        raw_target_weights = _apply_short_position_multiplier(
            raw_target_weights=raw_target_weights,
            decision_group=decision_group,
            constraints=constraints,
        )
        actual_weights = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
            turnover_mode=str(constraints.get("pair_turnover_mode") or constraints.get("turnover_mode") or "").strip().lower() or None,
        )
        fill_rows = {str(row["subject"]): row for _, row in grouped[fill_timestamp].iterrows()}
        exit_rows = {str(row["subject"]): row for _, row in grouped[exit_timestamp].iterrows()}
        hold_slice = ordered.loc[
            (ordered["timestamp_ms"] >= fill_timestamp)
            & (ordered["timestamp_ms"] < exit_timestamp)
        ].copy()
        funding_rows_by_subject = {
            str(subject): group.copy()
            for subject, group in hold_slice.groupby("subject")
        }
        decision_rank = _decision_rank_by_subject(decision_group)
        for subject, weight in sorted(actual_weights.items()):
            resolved_weight = float(weight)
            if abs(resolved_weight) <= 0.0:
                continue
            fill_row = fill_rows.get(str(subject))
            exit_row = exit_rows.get(str(subject))
            if fill_row is None:
                data_gap_blockers.add(f"{subject}: missing fill row for attribution")
                continue
            if exit_row is None:
                data_gap_blockers.add(f"{subject}: missing exit row for attribution")
                continue
            blockers: set[str] = set()
            gross_contribution = _price_path_return(
                entry_row=fill_row,
                exit_row=exit_row,
                weight=resolved_weight,
                execution_venue=execution_venue,
                subject=str(subject),
                data_gap_blockers=blockers,
            )
            data_gap_blockers.update(blockers)
            price_field = "spot_close" if execution_venue == "spot" else "perp_close"
            entry_price = float(pd.to_numeric(pd.Series([fill_row.get(price_field)]), errors="coerce").fillna(0.0).iloc[0])
            exit_price = float(pd.to_numeric(pd.Series([exit_row.get(price_field)]), errors="coerce").fillna(0.0).iloc[0])
            underlying_forward_return = (exit_price / entry_price - 1.0) if entry_price > 0.0 and exit_price > 0.0 else 0.0
            funding_cost_return = _funding_cost_return(
                hold_slice=funding_rows_by_subject.get(str(subject), pd.DataFrame()),
                weight=resolved_weight,
                execution_venue=execution_venue,
            )
            decision_info = decision_rank.get(str(subject), {})
            records.append(
                {
                    "decision_timestamp_ms": decision_timestamp,
                    "fill_timestamp_ms": fill_timestamp,
                    "exit_timestamp_ms": exit_timestamp,
                    "fill_date_utc": _ms_to_date(fill_timestamp).isoformat(),
                    "exit_date_utc": _ms_to_date(exit_timestamp).isoformat(),
                    "year": int(_ms_to_date(fill_timestamp).year),
                    "subject": str(subject),
                    "usdm_symbol": str(fill_row.get("usdm_symbol") or f"{subject}USDT"),
                    "side": "long" if resolved_weight > 0.0 else "short",
                    "weight": resolved_weight,
                    "score_at_decision": float(decision_info.get("score", 0.0) or 0.0),
                    "score_rank_desc": int(decision_info.get("score_rank_desc", 0) or 0),
                    "liquidity_bucket": str(decision_info.get("liquidity_bucket") or fill_row.get("liquidity_bucket") or ""),
                    "universe_rank": decision_info.get("universe_rank"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "underlying_forward_return": float(underlying_forward_return),
                    "gross_contribution": float(gross_contribution),
                    "funding_cost_return": float(funding_cost_return),
                    "net_before_trade_cost_contribution": float(gross_contribution - funding_cost_return),
                }
            )
        previous_weights = actual_weights
    attribution_frame = pd.DataFrame(records)
    by_side_year, by_symbol_year, side_summary = _summarize_position_attribution(attribution_frame)
    summary = {
        "status": "ok" if not attribution_frame.empty else "empty",
        "note": "Position attribution is gross plus funding-cost-only by held leg; fee and slippage remain portfolio-level in validation metrics.",
        "position_row_count": int(len(attribution_frame)),
        "data_gap_blockers": sorted(data_gap_blockers),
        "side_summary": _records(side_summary),
        "worst_symbol_years": _records(by_symbol_year.sort_values("net_before_trade_cost_contribution", ascending=True).head(10))
        if not by_symbol_year.empty
        else [],
        "best_symbol_years": _records(by_symbol_year.sort_values("net_before_trade_cost_contribution", ascending=False).head(10))
        if not by_symbol_year.empty
        else [],
    }
    return {
        "summary": summary,
        "position_attribution": attribution_frame,
        "by_side_year": by_side_year,
        "by_symbol_year": by_symbol_year,
    }


def compute_factor_leave_one_out_attribution(frame: pd.DataFrame, *, config: dict[str, Any]) -> dict[str, Any]:
    features = [str(item) for item in config.get("feature_columns", ALLOWED_ALPHA_FEATURES)]
    if frame.empty or not features:
        return _empty_factor_leave_one_out()
    weights = dict(config.get("feature_weights") or BINANCE_OHLCV_CORE_WEIGHTS)
    abs_sum = sum(abs(float(weights.get(column, 0.0) or 0.0)) for column in features)
    base_metrics = _strip_periods(_run_backtest(frame, config=config, scenario="base", include_periods=False))
    stress_metrics = _strip_periods(_run_backtest(frame, config=config, scenario="stress", include_periods=False))
    base_rank_ic = _rank_ic_summary(
        frame,
        score_column="score",
        target_column="target_execution_forward_return",
    )
    base_position_rows = _frame_or_empty(compute_position_attribution(frame, config=config).get("position_attribution"))
    rows: list[dict[str, Any]] = []
    side_rows: list[pd.DataFrame] = []
    year_rows: list[pd.DataFrame] = []
    side_year_rows: list[pd.DataFrame] = []
    base_net = float(base_metrics.get("net_return", 0.0) or 0.0)
    base_sharpe = float(base_metrics.get("sharpe", 0.0) or 0.0)
    stress_net = float(stress_metrics.get("net_return", 0.0) or 0.0)
    base_rank_ic_mean = float(base_rank_ic.get("mean_rank_ic", 0.0) or 0.0)
    for feature in features:
        remaining_features = [column for column in features if column != feature]
        variant_frame = _rescore_for_feature_subset(
            frame,
            config=config,
            feature_columns=remaining_features,
        )
        variant_base = _strip_periods(_run_backtest(variant_frame, config=config, scenario="base", include_periods=False))
        variant_stress = _strip_periods(_run_backtest(variant_frame, config=config, scenario="stress", include_periods=False))
        variant_rank_ic = _rank_ic_summary(
            variant_frame,
            score_column="score",
            target_column="target_execution_forward_return",
        )
        variant_position_rows = _frame_or_empty(
            compute_position_attribution(variant_frame, config=config).get("position_attribution")
        )
        loo_net = float(variant_base.get("net_return", 0.0) or 0.0)
        loo_sharpe = float(variant_base.get("sharpe", 0.0) or 0.0)
        loo_stress_net = float(variant_stress.get("net_return", 0.0) or 0.0)
        loo_rank_ic = float(variant_rank_ic.get("mean_rank_ic", 0.0) or 0.0)
        raw_weight = float(weights.get(feature, 0.0) or 0.0)
        rows.append(
            {
                "feature": feature,
                "raw_weight": raw_weight,
                "normalized_weight": raw_weight / abs_sum if abs_sum > 0.0 else 0.0,
                "absolute_weight_share": abs(raw_weight) / abs_sum if abs_sum > 0.0 else 0.0,
                "removed_feature_count": 1,
                "remaining_feature_count": int(len(remaining_features)),
                "base_net_return": base_net,
                "loo_net_return": loo_net,
                "net_return_delta_baseline_minus_loo": float(base_net - loo_net),
                "base_sharpe": base_sharpe,
                "loo_sharpe": loo_sharpe,
                "sharpe_delta_baseline_minus_loo": float(base_sharpe - loo_sharpe),
                "stress_net_return": stress_net,
                "loo_stress_net_return": loo_stress_net,
                "stress_net_delta_baseline_minus_loo": float(stress_net - loo_stress_net),
                "rank_ic_mean": base_rank_ic_mean,
                "loo_rank_ic_mean": loo_rank_ic,
                "rank_ic_delta_baseline_minus_loo": float(base_rank_ic_mean - loo_rank_ic),
                "loo_max_drawdown": float(variant_base.get("max_drawdown", 0.0) or 0.0),
                "loo_data_gap_blocker_count": int(len(variant_base.get("data_gap_blockers") or [])),
            }
        )
        side_rows.append(
            _factor_position_delta(
                base_position_rows,
                variant_position_rows,
                feature=feature,
                group_columns=["side"],
                remaining_feature_count=len(remaining_features),
            )
        )
        year_rows.append(
            _factor_position_delta(
                base_position_rows,
                variant_position_rows,
                feature=feature,
                group_columns=["year"],
                remaining_feature_count=len(remaining_features),
            )
        )
        side_year_rows.append(
            _factor_position_delta(
                base_position_rows,
                variant_position_rows,
                feature=feature,
                group_columns=["year", "side"],
                remaining_feature_count=len(remaining_features),
            )
        )
    attribution_frame = pd.DataFrame(rows)
    if not attribution_frame.empty:
        attribution_frame = attribution_frame.sort_values(
            "net_return_delta_baseline_minus_loo",
            ascending=False,
        ).reset_index(drop=True)
    side_frame = pd.concat(side_rows, ignore_index=True) if side_rows else pd.DataFrame()
    year_frame = pd.concat(year_rows, ignore_index=True) if year_rows else pd.DataFrame()
    side_year_frame = pd.concat(side_year_rows, ignore_index=True) if side_year_rows else pd.DataFrame()
    summary = {
        "status": "ok",
        "method": "leave_one_out_rescore_full_portfolio",
        "interpretation": "Positive delta means removing the feature reduced portfolio performance; negative delta means removing it improved performance.",
        "feature_count": int(len(features)),
        "baseline": {
            "base": base_metrics,
            "stress": stress_metrics,
            "rank_ic": base_rank_ic,
        },
        "top_positive_contributors": _records(attribution_frame.head(5)) if not attribution_frame.empty else [],
        "negative_contributors": _records(
            attribution_frame.loc[
                pd.to_numeric(attribution_frame["net_return_delta_baseline_minus_loo"], errors="coerce").lt(0.0)
            ].sort_values("net_return_delta_baseline_minus_loo")
        )
        if not attribution_frame.empty
        else [],
    }
    return {
        "summary": summary,
        "leave_one_out": attribution_frame,
        "by_side": side_frame,
        "by_year": year_frame,
        "by_side_year": side_year_frame,
    }


def build_paper_shadow_execution_ledger(frame: pd.DataFrame, *, config: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return _empty_paper_shadow_execution_ledger()
    constraints = dict(config.get("strategy_profile") or {})
    cost_model = resolve_execution_cost_model(scenario="base")
    cost_model["require_perp_inventory_open_interest"] = False
    execution_venue = str(constraints.get("execution_venue") or ("spot" if constraints.get("spot_only") else "perp"))
    reference_capital_usd = float(config.get("reference_capital_usd", 1_000_000.0) or 1_000_000.0)
    capacity_limits = dict(config.get("capacity_limits") or {})
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return _empty_paper_shadow_execution_ledger()
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    split_contract = _split_contract(config)
    evaluation_step_bars = max(int(split_contract.get("realization_step_bars", 0) or 0), 1)
    if "realization_step_bars" not in split_contract:
        target_horizon = int(split_contract.get("target_horizon_bars", 10) or 10)
        evaluation_step_bars = max(target_horizon, 1)
    timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
    decision_timestamp_indices = list(range(0, len(timestamps), evaluation_step_bars))
    latency_bars = int(cost_model["latency_bars"])
    grouped = {timestamp: group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}
    previous_weights: dict[str, float] = {}
    records: list[dict[str, Any]] = []
    data_gap_blockers: set[str] = set()
    for decision_offset, timestamp_offset in enumerate(decision_timestamp_indices):
        fill_offset = timestamp_offset + latency_bars
        if fill_offset >= len(timestamps):
            break
        decision_timestamp = int(timestamps[timestamp_offset])
        fill_timestamp = int(timestamps[fill_offset])
        next_fill_offset = _next_fill_offset(
            timestamp_count=len(timestamps),
            decision_timestamp_indices=decision_timestamp_indices,
            decision_offset=decision_offset,
            latency_bars=latency_bars,
        )
        exit_timestamp = int(timestamps[next_fill_offset]) if next_fill_offset is not None else int(timestamps[-1])
        decision_group = grouped[decision_timestamp]
        raw_target_weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints=constraints,
            previous_weights=previous_weights,
        )
        raw_target_weights = _apply_short_position_multiplier(
            raw_target_weights=raw_target_weights,
            decision_group=decision_group,
            constraints=constraints,
        )
        actual_weights = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
            turnover_mode=str(constraints.get("pair_turnover_mode") or constraints.get("turnover_mode") or "").strip().lower() or None,
        )
        fill_rows = {str(row["subject"]): row for _, row in grouped[fill_timestamp].iterrows()}
        exit_rows = {str(row["subject"]): row for _, row in grouped[exit_timestamp].iterrows()}
        hold_slice = ordered.loc[
            (ordered["timestamp_ms"] >= fill_timestamp)
            & (ordered["timestamp_ms"] < exit_timestamp)
        ].copy()
        funding_rows_by_subject = {
            str(subject): group.copy()
            for subject, group in hold_slice.groupby("subject")
        }
        decision_rank = _decision_rank_by_subject(decision_group)
        ledger_subjects = sorted(set(previous_weights) | set(actual_weights))
        for subject in ledger_subjects:
            target_weight = float(actual_weights.get(subject, 0.0) or 0.0)
            previous_weight = float(previous_weights.get(subject, 0.0) or 0.0)
            delta_weight = target_weight - previous_weight
            if abs(delta_weight) <= 1e-12 and abs(target_weight) <= 1e-12:
                continue
            fill_row = fill_rows.get(subject)
            exit_row = exit_rows.get(subject)
            row_blockers: set[str] = set()
            trade_costs = {
                "fee_cost_return": 0.0,
                "slippage_cost_return": 0.0,
                "trade_notional_usd": 0.0,
                "trade_participation_rate": 0.0,
                "inventory_participation_rate": 0.0,
                "max_participation_rate": 0.0,
                "capacity_breach_count": 0,
                "liquidity_volume_proxy_usd": 0.0,
                "data_gap_blockers": [],
            }
            if fill_row is None:
                if abs(delta_weight) > 1e-12 or abs(target_weight) > 1e-12:
                    row_blockers.add(f"{subject}: missing fill row for paper shadow ledger")
            else:
                trade_costs = _trade_costs(
                    row=fill_row,
                    delta_weight=delta_weight,
                    target_weight=target_weight,
                    execution_venue=execution_venue,
                    execution_cost_model=cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=capacity_limits,
                    subject=subject,
                )
                row_blockers.update(str(item) for item in list(trade_costs.get("data_gap_blockers") or []))
            gross_contribution = 0.0
            if abs(target_weight) > 1e-12:
                if exit_row is None:
                    row_blockers.add(f"{subject}: missing exit row for paper shadow ledger")
                elif fill_row is not None:
                    gross_contribution = _price_path_return(
                        entry_row=fill_row,
                        exit_row=exit_row,
                        weight=target_weight,
                        execution_venue=execution_venue,
                        subject=subject,
                        data_gap_blockers=row_blockers,
                    )
            funding_cost_return = _funding_cost_return(
                hold_slice=funding_rows_by_subject.get(subject, pd.DataFrame()),
                weight=target_weight,
                execution_venue=execution_venue,
            )
            borrow_cost_return = _borrow_cost_return(
                entry_timestamp_ms=fill_timestamp,
                exit_timestamp_ms=exit_timestamp,
                weight=target_weight,
                execution_venue=execution_venue,
                execution_cost_model=cost_model,
            )
            fee_cost_return = float(trade_costs.get("fee_cost_return", 0.0) or 0.0)
            slippage_cost_return = float(trade_costs.get("slippage_cost_return", 0.0) or 0.0)
            net_contribution = (
                gross_contribution
                - fee_cost_return
                - slippage_cost_return
                - funding_cost_return
                - borrow_cost_return
            )
            decision_info = decision_rank.get(subject, {})
            price_field = "spot_close" if execution_venue == "spot" else "perp_close"
            entry_price = _row_float(fill_row, price_field) if fill_row is not None else 0.0
            exit_price = _row_float(exit_row, price_field) if exit_row is not None else 0.0
            records.append(
                {
                    "ledger_schema": "binance_paper_shadow_execution_ledger.v1",
                    "execution_mode": "paper_shadow_no_live_orders",
                    "decision_timestamp_ms": decision_timestamp,
                    "fill_timestamp_ms": fill_timestamp,
                    "exit_timestamp_ms": exit_timestamp,
                    "decision_date_utc": _ms_to_date(decision_timestamp).isoformat(),
                    "fill_date_utc": _ms_to_date(fill_timestamp).isoformat(),
                    "exit_date_utc": _ms_to_date(exit_timestamp).isoformat(),
                    "subject": subject,
                    "usdm_symbol": str((fill_row.get("usdm_symbol") if fill_row is not None else None) or f"{subject}USDT"),
                    "action": _paper_shadow_action(previous_weight=previous_weight, target_weight=target_weight),
                    "side": "long" if target_weight > 0.0 else ("short" if target_weight < 0.0 else "flat"),
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "delta_weight": delta_weight,
                    "target_notional_usd": float(reference_capital_usd * abs(target_weight)),
                    "delta_notional_usd": float(reference_capital_usd * abs(delta_weight)),
                    "score_at_decision": float(decision_info.get("score", 0.0) or 0.0),
                    "score_rank_desc": int(decision_info.get("score_rank_desc", 0) or 0),
                    "liquidity_bucket": str(decision_info.get("liquidity_bucket") or (fill_row.get("liquidity_bucket") if fill_row is not None else "") or ""),
                    "universe_rank": decision_info.get("universe_rank"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_contribution": float(gross_contribution),
                    "fee_cost_return": fee_cost_return,
                    "slippage_cost_return": slippage_cost_return,
                    "funding_cost_return": float(funding_cost_return),
                    "borrow_cost_return": float(borrow_cost_return),
                    "net_contribution": float(net_contribution),
                    "trade_notional_usd": float(trade_costs.get("trade_notional_usd", 0.0) or 0.0),
                    "trade_participation_rate": float(trade_costs.get("trade_participation_rate", 0.0) or 0.0),
                    "inventory_participation_rate": float(trade_costs.get("inventory_participation_rate", 0.0) or 0.0),
                    "max_participation_rate": float(trade_costs.get("max_participation_rate", 0.0) or 0.0),
                    "capacity_breach_count": int(trade_costs.get("capacity_breach_count", 0) or 0),
                    "liquidity_volume_proxy_usd": float(trade_costs.get("liquidity_volume_proxy_usd", 0.0) or 0.0),
                    "data_gap_blockers": ";".join(sorted(row_blockers)),
                }
            )
            data_gap_blockers.update(row_blockers)
        previous_weights = actual_weights
    ledger_frame = pd.DataFrame(records)
    summary = _summarize_paper_shadow_ledger(ledger_frame, data_gap_blockers=data_gap_blockers)
    return {"summary": summary, "ledger": ledger_frame}


def run_binance_core_ablations(frame: pd.DataFrame, *, config: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return {"summary": {}, "period_returns": pd.DataFrame()}
    variants: list[tuple[str, dict[str, Any], pd.DataFrame, str]] = []
    base_profile = dict(config.get("strategy_profile") or {})

    long_only_config = copy.deepcopy(config)
    long_only_profile = dict(base_profile)
    long_only_profile.update(
        {
            "short_allowed": False,
            "short_leverage": 0.0,
            "bottom_short_count": 0,
            "long_leverage": 1.0,
            "max_gross_leverage": 1.0,
        }
    )
    long_only_config["strategy_profile"] = long_only_profile
    variants.append(("long_only_gross_1x", long_only_config, frame, "Top-3 long only, scaled to 1.0 gross."))

    short_disabled_config = copy.deepcopy(config)
    short_disabled_profile = dict(base_profile)
    short_disabled_profile.update(
        {
            "short_allowed": False,
            "short_leverage": 0.0,
            "bottom_short_count": 0,
            "long_leverage": float(base_profile.get("long_leverage", 0.5) or 0.5),
        }
    )
    short_disabled_config["strategy_profile"] = short_disabled_profile
    variants.append(("short_disabled_cash_half", short_disabled_config, frame, "Original 0.5 long sleeve, short sleeve held in cash."))

    veto_frame = add_short_squeeze_veto_multiplier(frame)
    short_veto_config = copy.deepcopy(config)
    short_veto_profile = dict(base_profile)
    short_veto_profile["short_position_weight_multiplier_column"] = "binance_short_squeeze_veto_multiplier"
    short_veto_config["strategy_profile"] = short_veto_profile
    variants.append(
        (
            "short_veto_ohlcv_squeeze_guard",
            short_veto_config,
            veto_frame,
            "OHLCV-only short veto: skip shorts with high 5d volatility and close-to-5d-high behavior.",
        )
    )

    diagnostic_ablations = dict(config.get("diagnostic_ablations") or {})
    if bool(diagnostic_ablations.get("enable_reference_core20_filters", True)):
        core20_frame = add_core20_ablation_eligibility(frame, config=config)
        core20_long_noncore_mid_short_config = copy.deepcopy(config)
        core20_long_noncore_mid_short_profile = dict(base_profile)
        core20_long_noncore_mid_short_profile.update(
            {
                "long_decision_eligible_column": "binance_core20_long_eligible",
                "short_decision_eligible_column": "binance_noncore_mid_short_eligible",
            }
        )
        core20_long_noncore_mid_short_config["strategy_profile"] = core20_long_noncore_mid_short_profile
        variants.append(
            (
                "core20_long_noncore_mid_short",
                core20_long_noncore_mid_short_config,
                core20_frame,
                "Long sleeve restricted to the frozen core20 reference set; short sleeve restricted to non-core mid-liquidity names.",
            )
        )

        core20_short_disabled_config = copy.deepcopy(config)
        core20_short_disabled_profile = dict(base_profile)
        core20_short_disabled_profile["short_decision_eligible_column"] = "binance_noncore_short_eligible"
        core20_short_disabled_config["strategy_profile"] = core20_short_disabled_profile
        variants.append(
            (
                "core20_short_disabled",
                core20_short_disabled_config,
                core20_frame,
                "Core20 reference names are disabled for shorts; the long sleeve and non-core short sleeve stay otherwise unchanged.",
            )
        )

    summary: dict[str, Any] = {}
    period_frames: list[pd.DataFrame] = []
    for name, variant_config, variant_frame, note in variants:
        base_metrics = _run_backtest(variant_frame, config=variant_config, scenario="base", include_periods=True)
        stress_metrics = _run_backtest(variant_frame, config=variant_config, scenario="stress", include_periods=False)
        summary[name] = {
            "note": note,
            "base": _strip_periods(base_metrics),
            "stress": _strip_periods(stress_metrics),
        }
        periods = list(base_metrics.get("periods") or [])
        if periods:
            period_frame = pd.DataFrame(periods)
            period_frame.insert(0, "ablation", name)
            period_frames.append(period_frame)
    return {
        "summary": summary,
        "period_returns": pd.concat(period_frames, ignore_index=True, sort=False) if period_frames else pd.DataFrame(),
    }


def add_short_squeeze_veto_multiplier(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    timestamps = output["timestamp_ms"] if "timestamp_ms" in output.columns else pd.Series(index=output.index, dtype="float64")
    realized_vol = pd.to_numeric(output.get("realized_volatility_5"), errors="coerce")
    distance_to_high_5 = pd.to_numeric(output.get("distance_to_high_5"), errors="coerce")
    vol_rank = realized_vol.groupby(timestamps).rank(pct=True, method="average")
    high_rank = distance_to_high_5.groupby(timestamps).rank(pct=True, method="average")
    veto_mask = vol_rank.ge(0.75) & high_rank.ge(0.50) & distance_to_high_5.ge(-0.05)
    output["binance_short_squeeze_veto_multiplier"] = np.where(veto_mask.fillna(False), 0.0, 1.0)
    output["binance_short_squeeze_veto_flag"] = veto_mask.fillna(False).astype("bool")
    return output


def add_binance_risk_brake_columns(frame: pd.DataFrame, *, config: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return output
    profile = dict(config.get("strategy_profile") or {})
    policy = dict(config.get("risk_overlay_policy") or {})
    short_multiplier_column = str(profile.get("short_position_weight_multiplier_column") or "").strip()
    should_apply = bool(policy.get("enabled", False)) or short_multiplier_column == "binance_risk_brake_short_multiplier"
    if not should_apply:
        return output

    for column in BINANCE_RISK_BRAKE_COLUMNS:
        if column.endswith("_flag"):
            output[column] = False
        elif column.endswith("_multiplier"):
            output[column] = 1.0
        else:
            output[column] = np.nan

    if bool(dict(policy.get("short_squeeze_brake") or {}).get("enabled", True)):
        output = add_short_squeeze_veto_multiplier(output)

    rebound_policy = dict(policy.get("high_vol_rebound_short_brake") or {})
    if bool(rebound_policy.get("enabled", True)):
        output = _add_high_vol_rebound_short_brake(output, policy=rebound_policy)

    squeeze_multiplier = pd.to_numeric(
        output.get("binance_short_squeeze_veto_multiplier", pd.Series(1.0, index=output.index)),
        errors="coerce",
    ).fillna(1.0)
    rebound_multiplier = pd.to_numeric(
        output.get("binance_high_vol_rebound_short_multiplier", pd.Series(1.0, index=output.index)),
        errors="coerce",
    ).fillna(1.0)
    output["binance_risk_brake_short_multiplier"] = np.minimum(
        squeeze_multiplier.clip(lower=0.0, upper=1.0),
        rebound_multiplier.clip(lower=0.0, upper=1.0),
    )
    return output


def _add_high_vol_rebound_short_brake(frame: pd.DataFrame, *, policy: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    if "timestamp_ms" not in output.columns:
        return output
    timestamps = pd.to_numeric(output["timestamp_ms"], errors="coerce")
    if "universe_active" in output.columns:
        active = _truthy_series(output["universe_active"])
    else:
        active = pd.Series(True, index=output.index, dtype="bool")
    if "binance_decision_eligible" in output.columns:
        active &= _truthy_series(output["binance_decision_eligible"])

    required_columns = {"realized_volatility_5", "momentum_20", "distance_to_high_5"}
    if not required_columns.issubset(output.columns):
        return output

    working = output.loc[active & timestamps.notna(), ["timestamp_ms", *sorted(required_columns)]].copy()
    if working.empty:
        return output
    working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce").astype("int64")
    working["realized_volatility_5"] = pd.to_numeric(working["realized_volatility_5"], errors="coerce")
    working["momentum_20"] = pd.to_numeric(working["momentum_20"], errors="coerce")
    working["distance_to_high_5"] = pd.to_numeric(working["distance_to_high_5"], errors="coerce")
    close_to_high_threshold = float(policy.get("close_to_high_threshold", -0.05) or -0.05)

    def _timestamp_state(group: pd.DataFrame) -> pd.Series:
        momentum = pd.to_numeric(group["momentum_20"], errors="coerce")
        distance = pd.to_numeric(group["distance_to_high_5"], errors="coerce")
        return pd.Series(
            {
                "binance_market_realized_vol_5_median": float(
                    pd.to_numeric(group["realized_volatility_5"], errors="coerce").median()
                ),
                "binance_market_momentum_20_median": float(momentum.median()),
                "binance_market_positive_momentum_share_20": float(momentum.gt(0.0).mean()),
                "binance_market_close_to_high_share_5": float(distance.ge(close_to_high_threshold).mean()),
            }
        )

    market_state = working.groupby("timestamp_ms", sort=True).apply(_timestamp_state, include_groups=False)
    lookback_decisions = max(int(policy.get("lookback_decisions", 120) or 120), 1)
    min_periods = max(int(policy.get("min_periods", 20) or 20), 1)
    vol_quantile = min(max(float(policy.get("vol_quantile", 0.60) or 0.60), 0.0), 1.0)
    market_state["binance_market_realized_vol_5_threshold"] = (
        market_state["binance_market_realized_vol_5_median"]
        .rolling(lookback_decisions, min_periods=min_periods)
        .quantile(vol_quantile)
        .shift(1)
    )
    base_flag = (
        market_state["binance_market_realized_vol_5_median"].gt(market_state["binance_market_realized_vol_5_threshold"])
        & market_state["binance_market_momentum_20_median"].ge(float(policy.get("min_median_momentum_20", 0.03) or 0.03))
        & market_state["binance_market_positive_momentum_share_20"].ge(
            float(policy.get("min_positive_momentum_share", 0.60) or 0.60)
        )
        & market_state["binance_market_close_to_high_share_5"].ge(float(policy.get("min_close_to_high_share", 0.40) or 0.40))
    )
    severe_flag = (
        base_flag
        & market_state["binance_market_momentum_20_median"].ge(float(policy.get("severe_min_median_momentum_20", 0.08) or 0.08))
        & market_state["binance_market_positive_momentum_share_20"].ge(
            float(policy.get("severe_min_positive_momentum_share", 0.70) or 0.70)
        )
        & market_state["binance_market_close_to_high_share_5"].ge(
            float(policy.get("severe_min_close_to_high_share", 0.50) or 0.50)
        )
    )
    base_multiplier = float(policy.get("short_multiplier", 0.50) or 0.50)
    severe_multiplier = float(policy.get("severe_short_multiplier", 0.25) or 0.25)
    market_state["binance_high_vol_rebound_flag"] = base_flag.fillna(False).astype("bool")
    market_state["binance_high_vol_rebound_severe_flag"] = severe_flag.fillna(False).astype("bool")
    market_state["binance_high_vol_rebound_short_multiplier"] = 1.0
    market_state.loc[market_state["binance_high_vol_rebound_flag"], "binance_high_vol_rebound_short_multiplier"] = base_multiplier
    market_state.loc[market_state["binance_high_vol_rebound_severe_flag"], "binance_high_vol_rebound_short_multiplier"] = severe_multiplier

    columns = [
        "binance_high_vol_rebound_short_multiplier",
        "binance_high_vol_rebound_flag",
        "binance_high_vol_rebound_severe_flag",
        "binance_market_realized_vol_5_median",
        "binance_market_realized_vol_5_threshold",
        "binance_market_momentum_20_median",
        "binance_market_positive_momentum_share_20",
        "binance_market_close_to_high_share_5",
    ]
    merged = output[["timestamp_ms"]].merge(market_state[columns].reset_index(), on="timestamp_ms", how="left")
    for column in columns:
        if column.endswith("_flag"):
            output[column] = merged[column].astype("boolean").fillna(False).astype("bool").to_numpy()
        elif column.endswith("_multiplier"):
            output[column] = pd.to_numeric(merged[column], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0).to_numpy()
        else:
            output[column] = pd.to_numeric(merged[column], errors="coerce").to_numpy()
    return output


def add_core20_ablation_eligibility(frame: pd.DataFrame, *, config: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    core20_subjects = _reference_core20_subjects(config)
    if "subject" in output.columns:
        subject = output["subject"].astype(str)
        in_core20 = subject.isin(core20_subjects)
    else:
        in_core20 = pd.Series(False, index=output.index, dtype="bool")
    if "binance_decision_eligible" in output.columns:
        base_eligible = _truthy_series(output["binance_decision_eligible"])
    else:
        base_eligible = pd.Series(True, index=output.index, dtype="bool")
    if "liquidity_bucket" in output.columns:
        mid_liquidity = output["liquidity_bucket"].astype(str).eq("mid_liquidity")
    else:
        mid_liquidity = pd.Series(False, index=output.index, dtype="bool")
    output["binance_core20_long_eligible"] = (base_eligible & in_core20).astype("bool")
    output["binance_noncore_short_eligible"] = (base_eligible & ~in_core20).astype("bool")
    output["binance_noncore_mid_short_eligible"] = (base_eligible & ~in_core20 & mid_liquidity).astype("bool")
    return output


def _reference_core20_subjects(config: dict[str, Any]) -> set[str]:
    universe_policy = dict(config.get("universe_policy") or {})
    raw_subjects = (
        universe_policy.get("reference_core20_subjects")
        or config.get("reference_core20_subjects")
        or REFERENCE_CORE20_SUBJECTS
    )
    return {str(subject).strip() for subject in raw_subjects if str(subject).strip()}


def _empty_position_attribution() -> dict[str, Any]:
    empty = pd.DataFrame()
    return {
        "summary": {
            "status": "empty",
            "position_row_count": 0,
            "side_summary": [],
            "worst_symbol_years": [],
            "best_symbol_years": [],
            "data_gap_blockers": [],
        },
        "position_attribution": empty,
        "by_side_year": empty,
        "by_symbol_year": empty,
    }


def _empty_factor_leave_one_out() -> dict[str, Any]:
    return {
        "summary": {
            "status": "empty",
            "method": "leave_one_out_rescore_full_portfolio",
            "feature_count": 0,
            "baseline": {},
            "top_positive_contributors": [],
            "negative_contributors": [],
        },
        "leave_one_out": pd.DataFrame(),
        "by_side": pd.DataFrame(),
        "by_year": pd.DataFrame(),
        "by_side_year": pd.DataFrame(),
    }


def _empty_paper_shadow_execution_ledger() -> dict[str, Any]:
    return {
        "summary": {
            "status": "empty",
            "ledger_schema": "binance_paper_shadow_execution_ledger.v1",
            "execution_mode": "paper_shadow_no_live_orders",
            "ledger_row_count": 0,
            "order_row_count": 0,
            "position_row_count": 0,
            "data_gap_blockers": [],
        },
        "ledger": pd.DataFrame(),
    }


def _rescore_for_feature_subset(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any],
    feature_columns: list[str],
) -> pd.DataFrame:
    output = frame.copy()
    output["score"] = 0.0
    if not feature_columns:
        return output
    assert_alpha_feature_subset_purity(feature_columns)
    missing = [column for column in feature_columns if column not in output.columns]
    if missing:
        raise ValueError(f"missing Binance-canonical feature columns for leave-one-out: {missing}")
    if "universe_active" in output.columns:
        universe_active = _truthy_series(output["universe_active"])
    else:
        universe_active = pd.Series(True, index=output.index, dtype="bool")
    price_valid_mask = pd.Series(True, index=output.index, dtype="bool")
    for column in ("timestamp_ms", "perp_close", "perp_quote_volume_usd"):
        if column not in output.columns:
            price_valid_mask &= False
        else:
            price_valid_mask &= pd.to_numeric(output[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()
    price_valid_mask &= output["subject"].notna() if "subject" in output.columns else False
    feature_valid_mask = pd.Series(True, index=output.index, dtype="bool")
    for column in feature_columns:
        feature_valid_mask &= pd.to_numeric(output[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()
    score_mask = universe_active & feature_valid_mask & price_valid_mask
    if bool(score_mask.any()):
        output.loc[score_mask, "score"] = score_binance_ohlcv_core(
            output.loc[score_mask].copy(),
            feature_columns=feature_columns,
            feature_weights=dict(config.get("feature_weights") or BINANCE_OHLCV_CORE_WEIGHTS),
            require_complete_feature_set=False,
        )
    return output


def _row_float(row: pd.Series | None, field_name: str) -> float:
    if row is None:
        return 0.0
    value = pd.to_numeric(pd.Series([row.get(field_name)]), errors="coerce").replace([np.inf, -np.inf], np.nan)
    if value.empty or pd.isna(value.iloc[0]):
        return 0.0
    return float(value.iloc[0])


def _paper_shadow_action(*, previous_weight: float, target_weight: float) -> str:
    previous = float(previous_weight)
    target = float(target_weight)
    if abs(previous) <= 1e-12 and target > 0.0:
        return "open_long"
    if abs(previous) <= 1e-12 and target < 0.0:
        return "open_short"
    if previous > 0.0 and abs(target) <= 1e-12:
        return "close_long"
    if previous < 0.0 and abs(target) <= 1e-12:
        return "close_short"
    if previous * target < 0.0:
        return "flip_to_long" if target > 0.0 else "flip_to_short"
    if target > 0.0 and abs(target) > abs(previous):
        return "increase_long"
    if target > 0.0:
        return "reduce_long"
    if target < 0.0 and abs(target) > abs(previous):
        return "increase_short"
    if target < 0.0:
        return "reduce_short"
    return "hold"


def _summarize_paper_shadow_ledger(
    ledger_frame: pd.DataFrame,
    *,
    data_gap_blockers: set[str],
) -> dict[str, Any]:
    if ledger_frame.empty:
        return _empty_paper_shadow_execution_ledger()["summary"]
    delta = pd.to_numeric(ledger_frame.get("delta_weight"), errors="coerce").fillna(0.0)
    target = pd.to_numeric(ledger_frame.get("target_weight"), errors="coerce").fillna(0.0)
    side_summary: list[dict[str, Any]] = []
    for side, group in ledger_frame.groupby("side", sort=True):
        side_summary.append(
            {
                "side": str(side),
                "row_count": int(len(group)),
                "net_contribution": float(pd.to_numeric(group["net_contribution"], errors="coerce").fillna(0.0).sum()),
                "gross_contribution": float(pd.to_numeric(group["gross_contribution"], errors="coerce").fillna(0.0).sum()),
                "fee_cost_return": float(pd.to_numeric(group["fee_cost_return"], errors="coerce").fillna(0.0).sum()),
                "slippage_cost_return": float(pd.to_numeric(group["slippage_cost_return"], errors="coerce").fillna(0.0).sum()),
                "funding_cost_return": float(pd.to_numeric(group["funding_cost_return"], errors="coerce").fillna(0.0).sum()),
            }
        )
    return {
        "status": "ok",
        "ledger_schema": "binance_paper_shadow_execution_ledger.v1",
        "execution_mode": "paper_shadow_no_live_orders",
        "ledger_row_count": int(len(ledger_frame)),
        "period_count": int(ledger_frame["decision_timestamp_ms"].nunique()) if "decision_timestamp_ms" in ledger_frame.columns else 0,
        "order_row_count": int(delta.abs().gt(1e-12).sum()),
        "position_row_count": int(target.abs().gt(1e-12).sum()),
        "net_contribution": float(pd.to_numeric(ledger_frame["net_contribution"], errors="coerce").fillna(0.0).sum()),
        "gross_contribution": float(pd.to_numeric(ledger_frame["gross_contribution"], errors="coerce").fillna(0.0).sum()),
        "fee_cost_return": float(pd.to_numeric(ledger_frame["fee_cost_return"], errors="coerce").fillna(0.0).sum()),
        "slippage_cost_return": float(pd.to_numeric(ledger_frame["slippage_cost_return"], errors="coerce").fillna(0.0).sum()),
        "funding_cost_return": float(pd.to_numeric(ledger_frame["funding_cost_return"], errors="coerce").fillna(0.0).sum()),
        "borrow_cost_return": float(pd.to_numeric(ledger_frame["borrow_cost_return"], errors="coerce").fillna(0.0).sum()),
        "trade_notional_usd_total": float(pd.to_numeric(ledger_frame["trade_notional_usd"], errors="coerce").fillna(0.0).sum()),
        "turnover": float(delta.abs().sum()),
        "max_trade_participation_rate": float(pd.to_numeric(ledger_frame["trade_participation_rate"], errors="coerce").fillna(0.0).max()),
        "capacity_breach_count": int(pd.to_numeric(ledger_frame["capacity_breach_count"], errors="coerce").fillna(0).sum()),
        "data_gap_blockers": sorted(data_gap_blockers),
        "side_summary": side_summary,
    }


def _apply_short_position_multiplier(
    *,
    raw_target_weights: dict[str, float],
    decision_group: pd.DataFrame,
    constraints: dict[str, Any],
) -> dict[str, float]:
    short_multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
    if not short_multiplier_column or not raw_target_weights or decision_group.empty or short_multiplier_column not in decision_group.columns:
        return raw_target_weights
    multiplier_series = pd.to_numeric(decision_group[short_multiplier_column], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    multiplier_by_subject = {
        str(subject): float(multiplier)
        for subject, multiplier in zip(decision_group["subject"], multiplier_series)
    }
    adjusted_weights: dict[str, float] = {}
    for subject, weight in raw_target_weights.items():
        resolved = float(weight)
        if resolved < 0.0:
            resolved *= float(multiplier_by_subject.get(str(subject), 1.0))
        if abs(resolved) > 1e-12:
            adjusted_weights[str(subject)] = resolved
    return adjusted_weights


def _decision_rank_by_subject(decision_group: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if decision_group.empty:
        return {}
    frame = decision_group.copy()
    if "score" not in frame.columns:
        frame["score"] = 0.0
    frame["_score_rank_desc"] = pd.to_numeric(frame["score"], errors="coerce").rank(ascending=False, method="first")
    output: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        subject = str(row.get("subject") or "")
        if not subject:
            continue
        universe_rank = row.get("universe_rank")
        if pd.isna(universe_rank):
            universe_rank = None
        output[subject] = {
            "score": float(row.get("score", 0.0) or 0.0),
            "score_rank_desc": int(row.get("_score_rank_desc", 0) or 0),
            "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
            "universe_rank": int(universe_rank) if universe_rank is not None else None,
        }
    return output


def _summarize_position_attribution(attribution_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if attribution_frame.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def _hit_rate(values: pd.Series) -> float:
        return float(pd.to_numeric(values, errors="coerce").gt(0.0).mean()) if len(values) else 0.0

    aggregations = {
        "position_count": ("subject", "count"),
        "rebalance_count": ("fill_timestamp_ms", "nunique"),
        "gross_contribution": ("gross_contribution", "sum"),
        "funding_cost_return": ("funding_cost_return", "sum"),
        "net_before_trade_cost_contribution": ("net_before_trade_cost_contribution", "sum"),
        "mean_underlying_forward_return": ("underlying_forward_return", "mean"),
        "mean_abs_weight": ("weight", lambda item: float(pd.to_numeric(item, errors="coerce").abs().mean())),
        "profitable_position_rate": ("gross_contribution", _hit_rate),
    }
    side_summary = attribution_frame.groupby("side", sort=True).agg(**aggregations).reset_index()
    by_side_year = attribution_frame.groupby(["year", "side"], sort=True).agg(**aggregations).reset_index()
    by_symbol_year = (
        attribution_frame.groupby(["year", "subject", "usdm_symbol", "side"], sort=True)
        .agg(**aggregations)
        .reset_index()
    )
    return by_side_year, by_symbol_year, side_summary


def _factor_position_delta(
    base_positions: pd.DataFrame,
    loo_positions: pd.DataFrame,
    *,
    feature: str,
    group_columns: list[str],
    remaining_feature_count: int,
) -> pd.DataFrame:
    base = _aggregate_position_contribution(base_positions, group_columns=group_columns, prefix="baseline")
    loo = _aggregate_position_contribution(loo_positions, group_columns=group_columns, prefix="loo")
    if base.empty and loo.empty:
        return pd.DataFrame(columns=["feature", "removed_feature_count", "remaining_feature_count", *group_columns])
    merged = base.merge(loo, on=group_columns, how="outer")
    numeric_columns = [column for column in merged.columns if column not in group_columns]
    for column in numeric_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    for metric in (
        "position_count",
        "rebalance_count",
        "gross_contribution",
        "funding_cost_return",
        "net_before_trade_cost_contribution",
        "mean_underlying_forward_return",
        "mean_abs_weight",
    ):
        baseline_column = f"baseline_{metric}"
        loo_column = f"loo_{metric}"
        if baseline_column not in merged.columns:
            merged[baseline_column] = 0.0
        if loo_column not in merged.columns:
            merged[loo_column] = 0.0
        merged[f"{metric}_delta_baseline_minus_loo"] = merged[baseline_column] - merged[loo_column]
    merged.insert(0, "remaining_feature_count", int(remaining_feature_count))
    merged.insert(0, "removed_feature_count", 1)
    merged.insert(0, "feature", str(feature))
    return merged.sort_values([*group_columns, "feature"]).reset_index(drop=True)


def _aggregate_position_contribution(
    positions: pd.DataFrame,
    *,
    group_columns: list[str],
    prefix: str,
) -> pd.DataFrame:
    output_columns = [
        *group_columns,
        f"{prefix}_position_count",
        f"{prefix}_rebalance_count",
        f"{prefix}_gross_contribution",
        f"{prefix}_funding_cost_return",
        f"{prefix}_net_before_trade_cost_contribution",
        f"{prefix}_mean_underlying_forward_return",
        f"{prefix}_mean_abs_weight",
    ]
    if positions.empty or not set(group_columns).issubset(positions.columns):
        return pd.DataFrame(columns=output_columns)
    working = positions.copy()
    for column in (
        "gross_contribution",
        "funding_cost_return",
        "net_before_trade_cost_contribution",
        "underlying_forward_return",
        "weight",
    ):
        if column not in working.columns:
            working[column] = 0.0
        else:
            working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0)
    grouped = (
        working.groupby(group_columns, dropna=False, sort=True)
        .agg(
            position_count=("subject", "count"),
            rebalance_count=("fill_timestamp_ms", "nunique"),
            gross_contribution=("gross_contribution", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            net_before_trade_cost_contribution=("net_before_trade_cost_contribution", "sum"),
            mean_underlying_forward_return=("underlying_forward_return", "mean"),
            mean_abs_weight=("weight", lambda item: float(pd.to_numeric(item, errors="coerce").abs().mean())),
        )
        .reset_index()
    )
    return grouped.rename(
        columns={
            "position_count": f"{prefix}_position_count",
            "rebalance_count": f"{prefix}_rebalance_count",
            "gross_contribution": f"{prefix}_gross_contribution",
            "funding_cost_return": f"{prefix}_funding_cost_return",
            "net_before_trade_cost_contribution": f"{prefix}_net_before_trade_cost_contribution",
            "mean_underlying_forward_return": f"{prefix}_mean_underlying_forward_return",
            "mean_abs_weight": f"{prefix}_mean_abs_weight",
        }
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))


def _truthy_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype("bool")
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"1", "true", "yes", "y"})


def _run_falsification_suite(frame: pd.DataFrame, *, config: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return {}
    rng = np.random.default_rng(20260510)
    shuffled_time = frame.copy()
    shuffled_values: list[pd.Series] = []
    for _, group in shuffled_time.groupby("subject", sort=True):
        values = group["score"].to_numpy(dtype="float64")
        shuffled_values.append(pd.Series(rng.permutation(values), index=group.index))
    if shuffled_values:
        shuffled_time.loc[:, "score"] = pd.concat(shuffled_values).sort_index()
    time_shuffle_metrics = _strip_periods(_run_backtest(shuffled_time, config=config, scenario="base", include_periods=False))

    label_columns = ["timestamp_ms", "score", "target_execution_forward_return"]
    if "binance_decision_eligible" in frame.columns:
        label_columns.append("binance_decision_eligible")
    label_shuffle_frame = frame[label_columns].copy()
    label_shuffle_frame["target_execution_forward_return"] = rng.permutation(
        label_shuffle_frame["target_execution_forward_return"].to_numpy(dtype="float64")
    )
    label_shuffle_ic = _rank_ic_summary(
        label_shuffle_frame,
        score_column="score",
        target_column="target_execution_forward_return",
    )

    subjects = sorted(str(item) for item in frame["subject"].dropna().unique())
    holdout_results: dict[str, Any] = {}
    for bucket in ("holdout_a", "holdout_b"):
        selected = [
            subject
            for subject in subjects
            if (_stable_int(subject) % 2 == 0) == (bucket == "holdout_a")
        ]
        subset = frame.loc[frame["subject"].isin(selected)].copy()
        holdout_results[bucket] = {
            "role": "diagnostic",
            "subjects": selected,
            "metrics": _strip_periods(_run_backtest(subset, config=config, scenario="base", include_periods=False))
            if not subset.empty
            else {},
        }
    stratified_holdout = _run_stratified_repeated_symbol_holdout(frame, config=config)

    liquidity_bucket_results: dict[str, Any] = {}
    if "liquidity_bucket" in frame.columns:
        for bucket in sorted(str(item) for item in frame["liquidity_bucket"].dropna().unique()):
            bucket_frame, bucket_config = _decision_time_liquidity_bucket_frame(
                frame,
                config=config,
                liquidity_bucket=bucket,
            )
            metrics = _strip_periods(_run_backtest(bucket_frame, config=bucket_config, scenario="base", include_periods=False))
            metrics["decision_time_liquidity_bucket"] = str(bucket)
            metrics["bucket_path_policy"] = "decision_time_bucket_full_execution_path"
            liquidity_bucket_results[str(bucket)] = metrics
    return {
        "time_shuffle": {"metrics": time_shuffle_metrics},
        "label_shuffle": {"rank_ic": label_shuffle_ic},
        "symbol_holdout": holdout_results,
        "symbol_holdout_role": "diagnostic",
        "stratified_repeated_symbol_holdout": stratified_holdout,
        "liquidity_bucket": liquidity_bucket_results,
        "cost_stress": {"metrics": _strip_periods(_run_backtest(frame, config=config, scenario="stress", include_periods=False))},
    }


def _decision_time_liquidity_bucket_frame(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any],
    liquidity_bucket: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    output = frame.copy()
    profile = dict(config.get("strategy_profile") or {})
    base_decision_column = str(profile.get("decision_eligible_column") or "").strip()
    if base_decision_column and base_decision_column in output.columns:
        base_eligible = _truthy_series(output[base_decision_column])
    else:
        base_eligible = pd.Series(True, index=output.index, dtype="bool")
    bucket = output.get("liquidity_bucket", pd.Series("", index=output.index)).astype(str)
    column = "__binance_liquidity_bucket_decision_eligible"
    output[column] = (base_eligible & bucket.eq(str(liquidity_bucket))).astype("bool")

    bucket_config = copy.deepcopy(config)
    bucket_profile = dict(bucket_config.get("strategy_profile") or {})
    bucket_profile["decision_eligible_column"] = column
    bucket_config["strategy_profile"] = bucket_profile
    return output, bucket_config


def _run_stratified_repeated_symbol_holdout(frame: pd.DataFrame, *, config: dict[str, Any]) -> dict[str, Any]:
    policy = _stratified_holdout_policy(config)
    repeat_count = int(policy["repeat_count"])
    if frame.empty or "subject" not in frame.columns or repeat_count <= 0:
        return {
            "policy": policy,
            "summary": {
                "status": "disabled_or_empty",
                "repeat_count": repeat_count,
                "fold_count": 0,
                "positive_fold_count": 0,
                "gap_free_fold_count": 0,
                "positive_fraction": 0.0,
                "gap_free_fraction": 0.0,
            },
            "folds": [],
            "strata": [],
        }
    subject_strata = _symbol_stratification_frame(frame)
    if subject_strata.empty:
        return {
            "policy": policy,
            "summary": {
                "status": "no_subjects",
                "repeat_count": repeat_count,
                "fold_count": 0,
                "positive_fold_count": 0,
                "gap_free_fold_count": 0,
                "positive_fraction": 0.0,
                "gap_free_fraction": 0.0,
            },
            "folds": [],
            "strata": [],
        }
    subject_text = frame["subject"].astype(str)
    folds: list[dict[str, Any]] = []
    for repeat in range(repeat_count):
        split = _stratified_two_way_subject_split(
            subject_strata,
            seed=int(policy["seed"]) + repeat,
        )
        for fold_name in ("a", "b"):
            selected = sorted(split.get(fold_name, []))
            subset = frame.loc[subject_text.isin(selected)].copy()
            metrics = (
                _strip_periods(_run_backtest(subset, config=config, scenario="base", include_periods=False))
                if selected and not subset.empty
                else {}
            )
            data_gap_blockers = list(dict(metrics).get("data_gap_blockers") or [])
            net_return = float(dict(metrics).get("net_return", 0.0) or 0.0)
            folds.append(
                {
                    "repeat": int(repeat),
                    "fold": fold_name,
                    "subjects": selected,
                    "subject_count": int(len(selected)),
                    "stratum_counts": _stratum_counts(subject_strata.loc[subject_strata["subject"].isin(selected)]),
                    "metrics": metrics,
                    "positive": bool(net_return > 0.0),
                    "gap_free": bool(len(data_gap_blockers) == 0),
                }
            )
    net_returns = [float(dict(item.get("metrics") or {}).get("net_return", 0.0) or 0.0) for item in folds]
    positive_count = sum(1 for item in folds if bool(item.get("positive")))
    gap_free_count = sum(1 for item in folds if bool(item.get("gap_free")))
    fold_count = len(folds)
    summary = {
        "status": "ok",
        "repeat_count": repeat_count,
        "fold_count": fold_count,
        "positive_fold_count": int(positive_count),
        "gap_free_fold_count": int(gap_free_count),
        "positive_fraction": float(positive_count / fold_count) if fold_count else 0.0,
        "gap_free_fraction": float(gap_free_count / fold_count) if fold_count else 0.0,
        "min_net_return": float(min(net_returns)) if net_returns else 0.0,
        "median_net_return": float(np.median(net_returns)) if net_returns else 0.0,
        "max_net_return": float(max(net_returns)) if net_returns else 0.0,
    }
    return {
        "policy": policy,
        "summary": summary,
        "folds": folds,
        "strata": _records(subject_strata.sort_values(["stratum", "subject"]).reset_index(drop=True)),
    }


def _stratified_holdout_policy(config: dict[str, Any]) -> dict[str, Any]:
    gates = dict(config.get("validation_gates") or {})
    policy = dict(config.get("stratified_symbol_holdout") or {})
    return {
        "repeat_count": max(int(policy.get("repeat_count", gates.get("stratified_holdout_repeat_count", 8)) or 8), 0),
        "seed": int(policy.get("seed", gates.get("stratified_holdout_seed", 20260511)) or 20260511),
        "min_positive_fraction": float(
            policy.get("min_positive_fraction", gates.get("stratified_holdout_min_positive_fraction", 0.75)) or 0.75
        ),
        "require_gap_free": bool(
            policy.get("require_gap_free", gates.get("stratified_holdout_require_gap_free", True))
        ),
        "stratification_columns": [
            "primary_liquidity_bucket",
            "major_bucket",
            "listing_age_bucket",
            "quote_volume_bucket",
        ],
    }


def _symbol_stratification_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "subject" not in frame.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    subject_frame = frame.copy()
    subject_frame["subject"] = subject_frame["subject"].astype(str)
    if "timestamp_ms" in subject_frame.columns:
        subject_frame["timestamp_ms"] = pd.to_numeric(subject_frame["timestamp_ms"], errors="coerce")
    if "universe_active" in subject_frame.columns:
        active_mask = _truthy_series(subject_frame["universe_active"])
    else:
        active_mask = pd.Series(True, index=subject_frame.index, dtype="bool")
    major_subjects = {
        "BTC",
        "ETH",
        "BNB",
        "SOL",
        "XRP",
        "ADA",
        "DOGE",
        "TRX",
        "LINK",
        "LTC",
        "BCH",
    }
    for subject, group in subject_frame.groupby("subject", sort=True):
        local_active = active_mask.loc[group.index]
        active_group = group.loc[local_active].copy()
        if active_group.empty:
            active_group = group.copy()
        bucket_series = active_group.get("liquidity_bucket", pd.Series("unknown", index=active_group.index)).astype(str)
        bucket_series = bucket_series.loc[~bucket_series.isin({"", "nan", "None", "not_in_universe"})]
        if bucket_series.empty:
            primary_bucket = "not_in_universe"
        else:
            primary_bucket = str(bucket_series.value_counts().sort_values(ascending=False).index[0])
        volume_source = None
        for column in ("universe_median_quote_volume_usd_lookback", "perp_quote_volume_usd"):
            if column in active_group.columns:
                volume_source = pd.to_numeric(active_group[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
                break
        median_quote_volume = float(volume_source.dropna().median()) if volume_source is not None and not volume_source.dropna().empty else 0.0
        if "pit_lifetime_valid_day_count" in active_group.columns:
            lifetime_days = float(pd.to_numeric(active_group["pit_lifetime_valid_day_count"], errors="coerce").max() or 0.0)
        elif "timestamp_ms" in active_group.columns:
            timestamps = pd.to_numeric(active_group["timestamp_ms"], errors="coerce").dropna()
            lifetime_days = float(((timestamps.max() - timestamps.min()) / 86_400_000.0) + 1.0) if not timestamps.empty else 0.0
        else:
            lifetime_days = float(len(active_group))
        rows.append(
            {
                "subject": str(subject),
                "primary_liquidity_bucket": primary_bucket,
                "major_bucket": "major" if str(subject) in major_subjects else "alt",
                "listing_age_days": lifetime_days,
                "listing_age_bucket": "seasoned" if lifetime_days >= 365.0 else ("seasoning" if lifetime_days >= 90.0 else "new"),
                "median_quote_volume_usd": median_quote_volume,
            }
        )
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    volume = pd.to_numeric(output["median_quote_volume_usd"], errors="coerce").fillna(0.0)
    if volume.nunique(dropna=True) <= 1:
        output["quote_volume_bucket"] = "volume_unknown"
    else:
        pct_rank = volume.rank(pct=True, method="average")
        output["quote_volume_bucket"] = np.select(
            [pct_rank.le(1.0 / 3.0), pct_rank.ge(2.0 / 3.0)],
            ["volume_low", "volume_high"],
            default="volume_mid",
        )
    output["stratum"] = (
        output["primary_liquidity_bucket"].astype(str)
        + "|"
        + output["major_bucket"].astype(str)
        + "|"
        + output["listing_age_bucket"].astype(str)
        + "|"
        + output["quote_volume_bucket"].astype(str)
    )
    return output


def _stratified_two_way_subject_split(subject_strata: pd.DataFrame, *, seed: int) -> dict[str, list[str]]:
    rng = np.random.default_rng(seed)
    folds: dict[str, list[str]] = {"a": [], "b": []}
    if subject_strata.empty:
        return folds
    for _, group in subject_strata.sort_values(["stratum", "subject"]).groupby("stratum", sort=True):
        subjects = [str(item) for item in group["subject"].tolist()]
        rng.shuffle(subjects)
        flip = bool(rng.integers(0, 2))
        for index, subject in enumerate(subjects):
            if len(subjects) == 1:
                if len(folds["a"]) == len(folds["b"]):
                    target = "b" if bool(rng.integers(0, 2)) else "a"
                else:
                    target = "a" if len(folds["a"]) < len(folds["b"]) else "b"
            else:
                target = "b" if (index + int(flip)) % 2 else "a"
            folds[target].append(subject)
    return {key: sorted(values) for key, values in folds.items()}


def _stratum_counts(subject_strata: pd.DataFrame) -> dict[str, int]:
    if subject_strata.empty or "stratum" not in subject_strata.columns:
        return {}
    return {str(key): int(value) for key, value in subject_strata["stratum"].value_counts().sort_index().items()}


def _validation_status(
    *,
    metrics: dict[str, Any],
    falsification: dict[str, Any],
    blockers: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    gates = dict(config.get("validation_gates") or {})
    base = dict(metrics.get("base") or {})
    stress = dict(metrics.get("stress") or {})
    liquidity_results = dict((falsification.get("liquidity_bucket") or {}))
    holdout_results = dict((falsification.get("symbol_holdout") or {}))
    stratified_holdout = dict(falsification.get("stratified_repeated_symbol_holdout") or {})
    stratified_summary = dict(stratified_holdout.get("summary") or {})
    stratified_policy = dict(stratified_holdout.get("policy") or {})
    positive_liquidity_buckets = sum(
        1 for item in liquidity_results.values() if float(dict(item).get("net_return", 0.0) or 0.0) > 0.0
    )
    positive_holdouts = sum(
        1
        for item in holdout_results.values()
        if float(dict(item.get("metrics") or {}).get("net_return", 0.0) or 0.0) > 0.0
    )
    legacy_holdout_positive_gate = positive_holdouts >= 2
    stratified_fold_count = int(stratified_summary.get("fold_count", 0) or 0)
    stratified_positive_count = int(stratified_summary.get("positive_fold_count", 0) or 0)
    stratified_gap_free_count = int(stratified_summary.get("gap_free_fold_count", 0) or 0)
    stratified_positive_fraction = (
        float(stratified_summary.get("positive_fraction", 0.0) or 0.0)
        if stratified_fold_count
        else 0.0
    )
    stratified_min_positive_fraction = float(
        stratified_policy.get(
            "min_positive_fraction",
            gates.get("stratified_holdout_min_positive_fraction", 0.75),
        )
        or 0.75
    )
    stratified_require_gap_free = bool(
        stratified_policy.get(
            "require_gap_free",
            gates.get("stratified_holdout_require_gap_free", True),
        )
    )
    stratified_gap_gate = (not stratified_require_gap_free) or (
        stratified_fold_count > 0 and stratified_gap_free_count == stratified_fold_count
    )
    stratified_holdout_gate = (
        stratified_fold_count > 0
        and stratified_positive_fraction >= stratified_min_positive_fraction
        and stratified_gap_gate
    )
    base_max_drawdown_cap_raw = gates.get("base_max_drawdown_max", gates.get("max_drawdown_max"))
    base_max_drawdown_cap = float(base_max_drawdown_cap_raw) if base_max_drawdown_cap_raw is not None else None
    base_max_drawdown_observed = (
        float(base.get("max_drawdown"))
        if base.get("max_drawdown") is not None
        else math.inf
    )
    base_max_drawdown_under_cap = (
        base_max_drawdown_observed <= base_max_drawdown_cap
        if base_max_drawdown_cap is not None
        else True
    )
    gate_results = {
        "base_positive_return": float(base.get("net_return", 0.0) or 0.0) > 0.0,
        "base_positive_sharpe": float(base.get("sharpe", 0.0) or 0.0) > 0.0,
        "base_max_drawdown_cap": base_max_drawdown_cap,
        "base_max_drawdown_under_cap": base_max_drawdown_under_cap,
        "stress_positive_return": float(stress.get("net_return", 0.0) or 0.0) > 0.0,
        "trade_participation_under_cap": float(base.get("max_trade_participation_rate", 0.0) or 0.0)
        <= float(gates.get("max_trade_participation_rate_max", 0.005) or 0.005),
        "capacity_breach_count_zero": int(base.get("capacity_breach_count", 0) or 0) == 0,
        "liquidity_positive_bucket_count": positive_liquidity_buckets,
        "liquidity_positive_bucket_gate": positive_liquidity_buckets
        >= int(gates.get("liquidity_positive_bucket_count_min", 2) or 2),
        "holdout_gate_role": "diagnostic",
        "legacy_holdout_positive_count": positive_holdouts,
        "legacy_holdout_positive_gate_diagnostic": legacy_holdout_positive_gate,
        "holdout_positive_count": positive_holdouts,
        "holdout_positive_gate": legacy_holdout_positive_gate,
        "stratified_holdout_fold_count": stratified_fold_count,
        "stratified_holdout_positive_count": stratified_positive_count,
        "stratified_holdout_gap_free_count": stratified_gap_free_count,
        "stratified_holdout_positive_fraction": stratified_positive_fraction,
        "stratified_holdout_min_positive_fraction": stratified_min_positive_fraction,
        "stratified_holdout_require_gap_free": stratified_require_gap_free,
        "stratified_holdout_gap_gate": stratified_gap_gate,
        "stratified_holdout_gate": stratified_holdout_gate,
    }
    if blockers:
        return "blocked", gate_results
    if not all(
        bool(gate_results[key])
        for key in (
            "base_positive_return",
            "base_positive_sharpe",
            "base_max_drawdown_under_cap",
            "stress_positive_return",
            "trade_participation_under_cap",
            "capacity_breach_count_zero",
            "liquidity_positive_bucket_gate",
            "stratified_holdout_gate",
        )
    ):
        return "failed", gate_results
    return "passed", gate_results


def _funding_cost_status(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"code": "funding_cost_history_missing", "status": "blocked", "message": "No scored frame."}
    if "funding_rate" not in frame.columns or "funding_sample_count" not in frame.columns:
        return {
            "code": "funding_cost_history_missing",
            "status": "blocked",
            "message": "Binance funding history was not joined as cost-only data.",
        }
    coverage_frame = frame
    coverage_scope = "all_rows"
    if "universe_active" in frame.columns:
        active_frame = frame.loc[_truthy_series(frame["universe_active"])].copy()
        if not active_frame.empty:
            coverage_frame = active_frame
            coverage_scope = "universe_active_rows"
    sample_count = pd.to_numeric(coverage_frame["funding_sample_count"], errors="coerce").fillna(0.0)
    coverage = float(sample_count.gt(0.0).mean()) if len(sample_count) else 0.0
    if coverage < 0.85:
        return {
            "code": "funding_cost_history_missing",
            "status": "blocked",
            "coverage_ratio": coverage,
            "coverage_scope": coverage_scope,
            "coverage_row_count": int(len(sample_count)),
            "message": "Funding cost coverage is below the 0.85 live-readiness gate.",
        }
    return {
        "code": "funding_cost_history_ok",
        "status": "ok",
        "coverage_ratio": coverage,
        "coverage_scope": coverage_scope,
        "coverage_row_count": int(len(sample_count)),
    }


def _rank_ic_summary(frame: pd.DataFrame, *, score_column: str, target_column: str) -> dict[str, Any]:
    if frame.empty or score_column not in frame.columns or target_column not in frame.columns:
        return {"period_count": 0, "mean_rank_ic": 0.0, "std_rank_ic": 0.0, "t_stat": 0.0}
    if "binance_decision_eligible" in frame.columns:
        frame = frame.loc[_truthy_series(frame["binance_decision_eligible"])].copy()
        if frame.empty:
            return {"period_count": 0, "mean_rank_ic": 0.0, "std_rank_ic": 0.0, "t_stat": 0.0}
    values: list[float] = []
    for _, group in frame.groupby("timestamp_ms", sort=True):
        if len(group) < 3:
            continue
        corr = group[[score_column, target_column]].corr(method="spearman").iloc[0, 1]
        if pd.notna(corr):
            values.append(float(corr))
    if not values:
        return {"period_count": 0, "mean_rank_ic": 0.0, "std_rank_ic": 0.0, "t_stat": 0.0}
    series = pd.Series(values, dtype="float64")
    std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    mean = float(series.mean())
    t_stat = mean / (std / math.sqrt(len(series))) if std > 0.0 else 0.0
    return {
        "period_count": int(len(series)),
        "mean_rank_ic": mean,
        "std_rank_ic": std,
        "t_stat": float(t_stat),
    }


def _strip_periods(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dict(metrics or {}).items() if key != "periods"}


def _drop_periods_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for key, value in dict(metrics or {}).items():
        if isinstance(value, dict):
            output[key] = _strip_periods(value)
        else:
            output[key] = value
    return output


def _split_contract(config: dict[str, Any]) -> dict[str, Any]:
    split = dict(config.get("split_realization") or {})
    return build_split_realization_contract(
        shape="cross_sectional",
        interval=str(split.get("interval") or "1d"),
        target_horizon_bars=int(split.get("target_horizon_bars", 10) or 10),
    )


def _symbol_partition_paths(
    *,
    store_root: Path,
    symbol: str,
    start_month: str | None,
    end_month: str | None,
) -> list[Path]:
    root = Path(store_root) / "data" / MARKET_TYPE / symbol.upper() / INTERVAL_1M
    paths = sorted([*root.glob("*.parquet"), *root.glob("*.csv.gz")])
    output: list[Path] = []
    for path in paths:
        month = _partition_month(path)
        if month is None:
            continue
        if start_month and month < start_month:
            continue
        if end_month and month > end_month:
            continue
        output.append(path)
    return output


def _partition_month(path: Path) -> str | None:
    name = path.name
    if len(name) < 7:
        return None
    value = name[:7]
    if re.match(r"^\d{4}-\d{2}$", value):
        return value
    return None
