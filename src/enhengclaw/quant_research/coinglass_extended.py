"""
CoinGlass extended endpoints: liquidation history, long-short ratios, top trader
position ratios, and orderbook depth time series.

Stores data under:
    LOCALAPPDATA/EnhengClaw/market_history/coinglass_extended/<SYMBOL>/<INTERVAL>/<MONTH>.csv.gz

Schema:
    open_time_ms, close_time_ms,
    long_liquidation_usd, short_liquidation_usd,
    global_account_long_pct, global_account_short_pct,
    top_trader_long_pct, top_trader_short_pct,
    orderbook_bids_usd, orderbook_asks_usd,
    taker_buy_volume_usd, taker_sell_volume_usd,
    source

Designed to be additive to binance_derivatives storage; does not modify the
existing schema.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
import gzip
import io
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .binance_derivatives import (
    DAY_MS,
    canonical_interval,
    interval_to_ms,
)
from .coinglass_derivatives import (
    COINGLASS_BASE_URL,
    DEFAULT_EXCHANGE_NAME,
    DEFAULT_LIMIT,
    PROVIDER,
    TAKER_BUY_SELL_VOLUME_HISTORY_URL,
    resolve_coinglass_api_key,
)


EXCHANGE = "binance"
EXTENDED_EXTERNAL_ROOT_NAME = "market_history\\coinglass_extended"
LIQUIDATION_HISTORY_URL = f"{COINGLASS_BASE_URL}/liquidation/history"
GLOBAL_LONG_SHORT_URL = f"{COINGLASS_BASE_URL}/global-long-short-account-ratio/history"
TOP_TRADER_POSITION_URL = f"{COINGLASS_BASE_URL}/top-long-short-position-ratio/history"
ORDERBOOK_HISTORY_URL = f"{COINGLASS_BASE_URL}/orderbook/ask-bids-history"
DEFAULT_INTERVALS = ("1h",)
SUPPORTED_INTERVALS = ("15m", "1h", "4h", "1d")
DEFAULT_LOOKBACK_DAYS = {"15m": 90, "1h": 187, "4h": 365, "1d": 730}

EXTENDED_CSV_HEADERS = (
    "exchange",
    "market_type",
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "long_liquidation_usd",
    "short_liquidation_usd",
    "global_account_long_pct",
    "global_account_short_pct",
    "global_account_long_short_ratio",
    "top_trader_long_pct",
    "top_trader_short_pct",
    "top_trader_long_short_ratio",
    "orderbook_bids_usd",
    "orderbook_asks_usd",
    "orderbook_bids_quantity",
    "orderbook_asks_quantity",
    "taker_buy_volume_usd",
    "taker_sell_volume_usd",
    "source",
)


def resolve_extended_external_root(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    env = os.environ if base_env is None else base_env
    localappdata = str(env.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / EXTENDED_EXTERNAL_ROOT_NAME).resolve()
    return (Path.home() / ".local" / "share" / "EnhengClaw" / EXTENDED_EXTERNAL_ROOT_NAME).resolve()


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def interval_root(*, external_root: Path, symbol: str, interval: str) -> Path:
    return external_root / symbol / canonical_interval(interval)


def interval_manifest_path(*, external_root: Path, symbol: str, interval: str) -> Path:
    return interval_root(external_root=external_root, symbol=symbol, interval=interval) / "manifest.json"


def month_partition_path(*, external_root: Path, symbol: str, interval: str, month_key: str) -> Path:
    return interval_root(external_root=external_root, symbol=symbol, interval=interval) / f"{month_key}.csv.gz"


def _month_key_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _fetch_paginated_history(
    *,
    url: str,
    params_base: dict[str, Any],
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    """Backward pagination: walk end_time back until [start_time_ms, end_time_ms] is covered."""
    interval_ms = interval_to_ms(interval)
    per_call_limit = 4500
    cur_end = end_time_ms
    bars: list[dict[str, Any]] = []
    max_pages = 64
    for _ in range(max_pages):
        if cur_end <= start_time_ms:
            break
        window_hint_ms = max(per_call_limit * interval_ms * 2, interval_ms * 1000)
        cur_start = max(start_time_ms, cur_end - window_hint_ms)
        params = dict(params_base)
        params.update({
            "interval": interval,
            "limit": per_call_limit,
            "start_time": cur_start,
            "end_time": cur_end,
        })
        try:
            payload = http_get_json_fn(f"{url}?{urlencode(params)}")
        except HTTPError as exc:
            if exc.code == 400:
                break
            raise
        if not isinstance(payload, dict):
            break
        data = list(payload.get("data") or [])
        if not data:
            break
        normalized: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                time_ms = int(item.get("time"))
            except (TypeError, ValueError):
                continue
            if time_ms < start_time_ms or time_ms > cur_end:
                continue
            normalized.append({"time": time_ms, **dict(item)})
        if not normalized:
            break
        normalized.sort(key=lambda item: int(item["time"]))
        bars.extend(normalized)
        oldest_time = int(normalized[0]["time"])
        if oldest_time <= start_time_ms:
            break
        if oldest_time >= cur_end:
            break
        cur_end = oldest_time - interval_ms
    deduped: dict[int, dict[str, Any]] = {}
    for item in bars:
        deduped[int(item["time"])] = item
    return [deduped[key] for key in sorted(deduped)]


def _read_partition_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_partition_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.open(buffer, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(EXTENDED_CSV_HEADERS))
        writer.writeheader()
        for row in rows:
            normalized = {key: str(row.get(key, "")) for key in EXTENDED_CSV_HEADERS}
            writer.writerow(normalized)
    path.write_bytes(buffer.getvalue())


def _merge_rows_into_store(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    rows: list[dict[str, str]],
) -> None:
    by_month: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        try:
            ts = int(row["open_time_ms"])
        except (TypeError, ValueError, KeyError):
            continue
        month_key = _month_key_from_ms(ts)
        by_month.setdefault(month_key, []).append(row)
    for month_key, month_rows in by_month.items():
        partition = month_partition_path(external_root=external_root, symbol=symbol, interval=interval, month_key=month_key)
        existing = _read_partition_rows(partition)
        merged: dict[int, dict[str, str]] = {}
        for row in existing:
            try:
                merged[int(row["open_time_ms"])] = row
            except (TypeError, ValueError, KeyError):
                continue
        for row in month_rows:
            try:
                merged[int(row["open_time_ms"])] = row
            except (TypeError, ValueError, KeyError):
                continue
        ordered = [merged[key] for key in sorted(merged)]
        _write_partition_rows(partition, ordered)


def _fnum(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            try:
                return f"{float(payload[key]):.10f}"
            except (TypeError, ValueError):
                continue
    return ""


def _aggregate_extended_rows(
    *,
    symbol: str,
    interval: str,
    liquidation_bars: list[dict[str, Any]],
    long_short_bars: list[dict[str, Any]],
    top_trader_bars: list[dict[str, Any]],
    orderbook_bars: list[dict[str, Any]],
    taker_volume_bars: list[dict[str, Any]],
) -> list[dict[str, str]]:
    by_time: dict[int, dict[str, dict[str, Any]]] = {}
    for source, bars in [
        ("liquidation", liquidation_bars),
        ("long_short", long_short_bars),
        ("top_trader", top_trader_bars),
        ("orderbook", orderbook_bars),
        ("taker", taker_volume_bars),
    ]:
        for item in bars:
            t = int(item["time"])
            by_time.setdefault(t, {})[source] = item
    rows: list[dict[str, str]] = []
    for bucket_time in sorted(by_time):
        b = by_time[bucket_time]
        liq = b.get("liquidation", {})
        ls = b.get("long_short", {})
        tt = b.get("top_trader", {})
        ob = b.get("orderbook", {})
        tv = b.get("taker", {})
        rows.append({
            "exchange": EXCHANGE,
            "market_type": "usdm_perp",
            "symbol": symbol,
            "interval": interval,
            "open_time_ms": str(bucket_time),
            "close_time_ms": str(bucket_time + interval_to_ms(interval) - 1),
            "long_liquidation_usd": _fnum(liq, "long_liquidation_usd", "longLiquidationUsd"),
            "short_liquidation_usd": _fnum(liq, "short_liquidation_usd", "shortLiquidationUsd"),
            "global_account_long_pct": _fnum(ls, "global_account_long_percent"),
            "global_account_short_pct": _fnum(ls, "global_account_short_percent"),
            "global_account_long_short_ratio": _fnum(ls, "global_account_long_short_ratio"),
            "top_trader_long_pct": _fnum(tt, "top_position_long_percent"),
            "top_trader_short_pct": _fnum(tt, "top_position_short_percent"),
            "top_trader_long_short_ratio": _fnum(tt, "top_position_long_short_ratio"),
            "orderbook_bids_usd": _fnum(ob, "bids_usd"),
            "orderbook_asks_usd": _fnum(ob, "asks_usd"),
            "orderbook_bids_quantity": _fnum(ob, "bids_quantity"),
            "orderbook_asks_quantity": _fnum(ob, "asks_quantity"),
            "taker_buy_volume_usd": _fnum(tv, "taker_buy_volume_usd", "buy_volume_usd", "buy"),
            "taker_sell_volume_usd": _fnum(tv, "taker_sell_volume_usd", "sell_volume_usd", "sell"),
            "source": "coinglass_extended",
        })
    return rows


def _row_count_for(symbol: str, interval: str, external_root: Path) -> int:
    root = interval_root(external_root=external_root, symbol=symbol, interval=interval)
    if not root.exists():
        return 0
    n = 0
    for p in root.glob("*.csv.gz"):
        n += len(_read_partition_rows(p))
    return n


def sync_coinglass_extended_history(
    *,
    symbols: Iterable[str],
    intervals: Iterable[str] = DEFAULT_INTERVALS,
    mode: str = "bootstrap",
    as_of: str | None = None,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
    lookback_days: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Sync extended CoinGlass derivatives data (liquidation, long-short ratio, top trader ratio, orderbook depth, taker volume) for given symbols/intervals."""
    if mode not in {"bootstrap", "refresh"}:
        raise ValueError("mode must be one of: bootstrap, refresh")
    resolved_root = resolve_extended_external_root(external_root=external_root, base_env=base_env)
    resolved_symbols = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
    resolved_intervals = tuple(canonical_interval(item) for item in intervals)
    resolved_lookback = dict(DEFAULT_LOOKBACK_DAYS)
    resolved_lookback.update(dict(lookback_days or {}))
    http_get = http_get_json_fn or _http_get_json

    sync_results: list[dict[str, Any]] = []
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    for symbol in resolved_symbols:
        for interval in resolved_intervals:
            try:
                if mode == "refresh" and _row_count_for(symbol, interval, resolved_root) > 0:
                    rows_existing = _read_partition_rows_for_all(resolved_root, symbol, interval)
                    last_ms = max((int(r["open_time_ms"]) for r in rows_existing if r.get("open_time_ms")), default=None)
                    start_time_ms = (last_ms + interval_to_ms(interval)) if last_ms else (now_ms - resolved_lookback[interval] * DAY_MS)
                else:
                    start_time_ms = now_ms - resolved_lookback[interval] * DAY_MS
                end_time_ms = now_ms

                params_base_pair = {"exchange": DEFAULT_EXCHANGE_NAME, "symbol": symbol}

                liquidation_bars = _fetch_paginated_history(
                    url=LIQUIDATION_HISTORY_URL,
                    params_base=params_base_pair,
                    interval=interval, start_time_ms=start_time_ms, end_time_ms=end_time_ms,
                    http_get_json_fn=http_get,
                )
                long_short_bars = _fetch_paginated_history(
                    url=GLOBAL_LONG_SHORT_URL,
                    params_base=params_base_pair,
                    interval=interval, start_time_ms=start_time_ms, end_time_ms=end_time_ms,
                    http_get_json_fn=http_get,
                )
                top_trader_bars = _fetch_paginated_history(
                    url=TOP_TRADER_POSITION_URL,
                    params_base=params_base_pair,
                    interval=interval, start_time_ms=start_time_ms, end_time_ms=end_time_ms,
                    http_get_json_fn=http_get,
                )
                orderbook_bars = _fetch_paginated_history(
                    url=ORDERBOOK_HISTORY_URL,
                    params_base=params_base_pair,
                    interval=interval, start_time_ms=start_time_ms, end_time_ms=end_time_ms,
                    http_get_json_fn=http_get,
                )
                taker_volume_bars = _fetch_paginated_history(
                    url=TAKER_BUY_SELL_VOLUME_HISTORY_URL,
                    params_base=params_base_pair,
                    interval=interval, start_time_ms=start_time_ms, end_time_ms=end_time_ms,
                    http_get_json_fn=http_get,
                )

                rows = _aggregate_extended_rows(
                    symbol=symbol, interval=interval,
                    liquidation_bars=liquidation_bars,
                    long_short_bars=long_short_bars,
                    top_trader_bars=top_trader_bars,
                    orderbook_bars=orderbook_bars,
                    taker_volume_bars=taker_volume_bars,
                )
                if rows:
                    _merge_rows_into_store(external_root=resolved_root, symbol=symbol, interval=interval, rows=rows)

                stored_rows = _row_count_for(symbol, interval, resolved_root)
                sync_results.append({
                    "status": "success",
                    "provider": PROVIDER,
                    "symbol": symbol,
                    "interval": interval,
                    "liquidation_event_count": len(liquidation_bars),
                    "long_short_event_count": len(long_short_bars),
                    "top_trader_event_count": len(top_trader_bars),
                    "orderbook_event_count": len(orderbook_bars),
                    "taker_volume_event_count": len(taker_volume_bars),
                    "fetched_row_count": len(rows),
                    "stored_row_count": stored_rows,
                    "manifest_path": str(interval_manifest_path(external_root=resolved_root, symbol=symbol, interval=interval)),
                    "requested_start_ms": start_time_ms,
                    "requested_end_ms": end_time_ms,
                })
            except Exception as exc:
                sync_results.append({
                    "status": "error",
                    "provider": PROVIDER,
                    "symbol": symbol,
                    "interval": interval,
                    "error": str(exc)[:200],
                })

    overall_status = "success" if all(r.get("status") == "success" for r in sync_results) else "partial"
    summary = {
        "provider": PROVIDER,
        "overall_status": overall_status,
        "as_of": as_of,
        "produced_at_utc": _utc_now(),
        "symbols": resolved_symbols,
        "intervals": list(resolved_intervals),
        "sync_results": sync_results,
    }
    summary_path = resolved_root / "last_sync_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def _read_partition_rows_for_all(external_root: Path, symbol: str, interval: str) -> list[dict[str, str]]:
    root = interval_root(external_root=external_root, symbol=symbol, interval=interval)
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for p in sorted(root.glob("*.csv.gz")):
        rows.extend(_read_partition_rows(p))
    return rows


def load_extended_rows(
    *,
    external_root: Path | None = None,
    symbol: str,
    interval: str,
    base_env: dict[str, str] | None = None,
    start_time_ms: int | None = None,
) -> list[dict[str, str]]:
    resolved_root = resolve_extended_external_root(external_root=external_root, base_env=base_env)
    rows = _read_partition_rows_for_all(resolved_root, symbol, interval)
    if start_time_ms is not None:
        rows = [r for r in rows if int(r.get("open_time_ms", 0)) >= start_time_ms]
    rows.sort(key=lambda r: int(r["open_time_ms"]))
    return rows
