from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ._binance_canonical_risk_columns import BINANCE_RISK_BRAKE_COLUMNS


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _frame_or_empty(value: Any) -> pd.DataFrame:
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _write_universe_membership(scored_frame: pd.DataFrame, path: Path) -> None:
    columns = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "usdm_symbol",
        "universe_active",
        "binance_decision_eligible",
        "binance_pit_data_eligible",
        "binance_pit_top_long_eligible",
        "binance_pit_mid_short_eligible",
        "binance_pit_active_long_eligible",
        "universe_rank",
        "liquidity_bucket",
        "pit_recent_valid_day_count",
        "pit_recent_coverage_ratio",
        "pit_recent_consecutive_valid_day_count",
        "pit_recent_active_day_count",
        "pit_recent_top_bucket_day_count",
        "pit_recent_mid_bucket_day_count",
        "pit_lifetime_valid_day_count",
        "pit_lifetime_gap_rate",
        "universe_coverage_ratio_lookback",
        "universe_median_quote_volume_usd_lookback",
        "universe_selection_rule",
        *BINANCE_RISK_BRAKE_COLUMNS,
    ]
    available = [column for column in columns if column in scored_frame.columns]
    if available:
        sort_columns = [column for column in ("timestamp_ms", "subject") if column in available]
        scored_frame.loc[:, available].sort_values(sort_columns).to_csv(path, index=False)
    else:
        pd.DataFrame(columns=columns).to_csv(path, index=False)
