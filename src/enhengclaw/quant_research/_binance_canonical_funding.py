from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from enhengclaw.utils.binance_http import binance_get_json


DEFAULT_FUNDING_COST_ROOT = Path("E:/EnhengClawData/market_history/binance_funding_cost_only")
DEFAULT_MARKET_TYPE = "usdm_perp"


def _funding_columns() -> list[str]:
    return ["exchange", "market_type", "symbol", "funding_time_ms", "funding_rate", "source"]


def funding_symbol_root(funding_root: Path, *, symbol: str) -> Path:
    return Path(funding_root) / str(symbol).strip().upper()


def funding_partition_path(funding_root: Path, *, symbol: str, month: str) -> Path:
    return funding_symbol_root(funding_root, symbol=symbol) / f"{month}.csv.gz"


def funding_symbol_manifest_path(funding_root: Path, *, symbol: str) -> Path:
    return funding_symbol_root(funding_root, symbol=symbol) / "manifest.json"


def funding_sync_summary_path(funding_root: Path) -> Path:
    return Path(funding_root) / "last_sync_summary.json"


def _read_funding_partition(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    frame = pd.read_csv(path, compression="gzip")
    return frame.to_dict(orient="records")


def _dedupe_funding_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[int, dict[str, Any]] = {}
    for row in rows:
        funding_time = int(row["funding_time_ms"])
        deduped[funding_time] = {
            "exchange": str(row.get("exchange") or "binance"),
            "market_type": str(row.get("market_type") or DEFAULT_MARKET_TYPE),
            "symbol": str(row.get("symbol") or "").upper(),
            "funding_time_ms": funding_time,
            "funding_rate": float(row.get("funding_rate", 0.0) or 0.0),
            "source": str(row.get("source") or "binance_fapi_fundingRate"),
        }
    return [deduped[key] for key in sorted(deduped)]


def _http_get_json(url: str) -> Any:
    return binance_get_json(url, timeout_seconds=30.0)


def _resolve_funding_root(*, config: dict[str, Any], funding_root: Path | None) -> Path:
    if funding_root is not None:
        return Path(funding_root)
    configured = str(config.get("funding_cost_root") or "").strip()
    return Path(configured) if configured else DEFAULT_FUNDING_COST_ROOT


def _month_key_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC).strftime("%Y-%m")


def _month_start_ms(month: str) -> int:
    year, month_int = [int(item) for item in str(month).split("-")]
    return int(datetime(year, month_int, 1, tzinfo=UTC).timestamp() * 1000)


def _month_end_ms(month: str) -> int:
    year, month_int = [int(item) for item in str(month).split("-")]
    if month_int == 12:
        next_dt = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        next_dt = datetime(year, month_int + 1, 1, tzinfo=UTC)
    return int(next_dt.timestamp() * 1000) - 1
