from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import pandas as pd


KLINE_FLOAT_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)
KLINE_INT_COLUMNS = ("open_time_ms", "close_time_ms", "trade_count")


def _read_kline_path(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.name.endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            return pd.read_csv(handle)
    raise ValueError(f"unsupported Binance archive partition format: {path}")


def _coerce_kline_frame(frame: pd.DataFrame) -> None:
    for column in KLINE_INT_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in KLINE_FLOAT_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def symbol_to_subject(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    return normalized[:-4] if normalized.endswith("USDT") else normalized


def _summarize_symbol_audits(symbol_audits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "symbol_count": len(symbol_audits),
        "ok_symbol_count": sum(1 for item in symbol_audits if item.get("status") == "ok"),
        "missing_or_empty_symbol_count": sum(1 for item in symbol_audits if item.get("status") != "ok"),
        "invalid_daily_bucket_count": sum(int(item.get("invalid_daily_bucket_count", 0) or 0) for item in symbol_audits),
        "invalid_4h_bucket_count": sum(int(item.get("invalid_4h_bucket_count", 0) or 0) for item in symbol_audits),
        "invalid_1h_bucket_count": sum(int(item.get("invalid_1h_bucket_count", 0) or 0) for item in symbol_audits),
    }
