from __future__ import annotations

from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import statistics
from typing import Any, Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .binance_derivatives import (
    DAY_MS,
    DEFAULT_INTERVALS,
    DEFAULT_MODE,
    DERIVATIVES_SYNC_CONTRACT_VERSION,
    LOOKBACK_DAYS,
    _coverage_days_between,
    _json_write,
    _merge_rows_into_store,
    _read_partition_rows,
    _requested_start_gap_days,
    as_of_sync_summary_path,
    canonical_interval,
    interval_manifest_path,
    interval_root,
    interval_to_ms,
    latest_sync_summary_path,
    load_derivatives_rows,
    resolve_external_derivatives_root,
)


PROVIDER = "coinglass"
EXCHANGE = "binance"
MARKET_TYPE = "usdm_perp"
COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com/api/futures"
SUPPORTED_EXCHANGE_PAIRS_URL = f"{COINGLASS_BASE_URL}/supported-exchange-pairs"
FUNDING_RATE_HISTORY_URL = f"{COINGLASS_BASE_URL}/funding-rate/history"
OPEN_INTEREST_HISTORY_URL = f"{COINGLASS_BASE_URL}/open-interest/history"
PRICE_HISTORY_URL = f"{COINGLASS_BASE_URL}/price/history"
TAKER_BUY_SELL_VOLUME_HISTORY_URL = f"{COINGLASS_BASE_URL}/v2/taker-buy-sell-volume/history"
DEFAULT_EXCHANGE_NAME = "Binance"
DEFAULT_LIMIT = 1000
API_KEY_ENV_NAMES = ("CoinglassAPI", "COINGLASS_API_KEY", "COINGLASSAPI")
ROOT = Path(__file__).resolve().parents[3]


def has_coinglass_api_key(base_env: dict[str, str] | None = None) -> bool:
    return bool(resolve_coinglass_api_key(base_env=base_env))


def resolve_coinglass_api_key(*, base_env: dict[str, str] | None = None) -> str:
    env = os.environ if base_env is None else base_env
    for key in API_KEY_ENV_NAMES:
        candidate = str(env.get(key) or "").strip()
        if candidate:
            return candidate
    return ""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _as_of_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    as_of_end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, 59, tzinfo=UTC)
    return int(as_of_end.timestamp() * 1000)


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_supported_pairs(*, exchange: str, http_get_json_fn: Callable[[str], Any]) -> set[str]:
    payload = http_get_json_fn(f"{SUPPORTED_EXCHANGE_PAIRS_URL}?{urlencode({'exchange': exchange})}")
    data = list(dict(payload or {}).get("data") or [])
    supported: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        instruments = list(item.get(exchange) or [])
        for instrument in instruments:
            if not isinstance(instrument, dict):
                continue
            instrument_id = str(instrument.get("instrument_id") or "").strip().upper()
            if instrument_id:
                supported.add(instrument_id)
    return supported


def sync_coinglass_derivatives_history(
    *,
    symbols: Iterable[str],
    intervals: Iterable[str] = DEFAULT_INTERVALS,
    mode: str = DEFAULT_MODE,
    as_of: str | None = None,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    if mode not in {"bootstrap", "refresh"}:
        raise ValueError("mode must be one of: bootstrap, refresh")
    resolved_root = resolve_external_derivatives_root(external_root=external_root, base_env=base_env)
    resolved_symbols = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
    resolved_intervals = tuple(canonical_interval(item) for item in intervals)
    http_get_json = http_get_json_fn or _http_get_json
    supported_pairs = _load_supported_pairs(exchange=DEFAULT_EXCHANGE_NAME, http_get_json_fn=http_get_json)
    sync_results: list[dict[str, Any]] = []
    for symbol in resolved_symbols:
        if supported_pairs and symbol not in supported_pairs:
            sync_results.append(
                {
                    "symbol": symbol,
                    "interval": ",".join(resolved_intervals),
                    "status": "error",
                    "error": f"unsupported Coinglass futures instrument for {DEFAULT_EXCHANGE_NAME}: {symbol}",
                    "provider": PROVIDER,
                }
            )
            continue
        for interval in resolved_intervals:
            try:
                sync_results.append(
                    _sync_symbol_interval(
                        external_root=resolved_root,
                        symbol=symbol,
                        interval=interval,
                        mode=mode,
                        http_get_json_fn=http_get_json,
                    )
                )
            except Exception as exc:
                sync_results.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "status": "error",
                        "error": str(exc),
                        "provider": PROVIDER,
                    }
                )
    summary = _build_sync_summary_payload(
        external_root=resolved_root,
        mode=mode,
        summary_scope="latest",
        symbols=resolved_symbols,
        intervals=resolved_intervals,
        sync_results=sync_results,
        as_of=as_of,
        window_end_ms=max(
            (
                int((item.get("requested_window") or {}).get("end_time_ms"))
                for item in sync_results
                if isinstance(item, dict) and (item.get("requested_window") or {}).get("end_time_ms") is not None
            ),
            default=None,
        ),
        required_symbols=resolved_symbols,
        required_intervals=resolved_intervals,
    )
    _json_write(latest_sync_summary_path(external_root=resolved_root), summary)
    if as_of is not None:
        archived_summary, archived_path = write_coinglass_derivatives_sync_summary_for_as_of(
            as_of=as_of,
            symbols=resolved_symbols,
            intervals=resolved_intervals,
            external_root=resolved_root,
            mode=mode,
        )
        summary["by_as_of_summary_path"] = str(archived_path)
        summary["by_as_of_warning_count"] = int(archived_summary.get("warning_count", 0) or 0)
        _json_write(latest_sync_summary_path(external_root=resolved_root), summary)
    return summary


def write_coinglass_derivatives_sync_summary_for_as_of(
    *,
    as_of: str,
    symbols: Iterable[str],
    intervals: Iterable[str] = DEFAULT_INTERVALS,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    mode: str = "evidence_rebuild",
) -> tuple[dict[str, Any], Path]:
    resolved_root = resolve_external_derivatives_root(external_root=external_root, base_env=base_env)
    resolved_symbols = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
    if not resolved_symbols:
        raise ValueError("at least one required symbol is needed to build as_of derivatives evidence")
    resolved_intervals = tuple(canonical_interval(item) for item in intervals)
    if not resolved_intervals:
        raise ValueError("at least one derivatives interval is required")
    as_of_end_ms = _as_of_end_ms(as_of)
    sync_results: list[dict[str, Any]] = []
    missing_pairs: list[str] = []
    for symbol in resolved_symbols:
        for interval in resolved_intervals:
            requested_window = {
                "start_time_ms": as_of_end_ms - (LOOKBACK_DAYS[interval] * DAY_MS),
                "end_time_ms": as_of_end_ms,
                "lookback_days": float(LOOKBACK_DAYS[interval]),
            }
            rows = load_derivatives_rows(
                external_root=resolved_root,
                symbol=symbol,
                interval=interval,
                start_time_ms=int(requested_window["start_time_ms"]),
            )
            rows = [row for row in rows if int(row["open_time_ms"]) <= as_of_end_ms]
            if not rows:
                missing_pairs.append(f"{symbol}:{interval}")
                continue
            sync_results.append(
                _sync_result_from_stored_rows(
                    external_root=resolved_root,
                    symbol=symbol,
                    interval=interval,
                    requested_window=requested_window,
                    rows=rows,
                )
            )
    if missing_pairs:
        raise RuntimeError(
            f"missing derivatives rows before as_of={as_of} for required symbol/interval pairs: {', '.join(missing_pairs)}"
        )
    summary = _build_sync_summary_payload(
        external_root=resolved_root,
        mode=mode,
        summary_scope="by_as_of",
        symbols=resolved_symbols,
        intervals=resolved_intervals,
        sync_results=sync_results,
        as_of=as_of,
        window_end_ms=as_of_end_ms,
        required_symbols=resolved_symbols,
        required_intervals=resolved_intervals,
    )
    summary_path = as_of_sync_summary_path(external_root=resolved_root, as_of=as_of)
    _json_write(summary_path, summary)
    return summary, summary_path


def _sync_symbol_interval(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    mode: str,
    http_get_json_fn: Callable[[str], Any],
) -> dict[str, Any]:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    existing_rows = load_derivatives_rows(external_root=external_root, symbol=symbol, interval=interval)
    if existing_rows and mode == "refresh":
        start_time_ms = int(existing_rows[-1]["open_time_ms"]) + interval_to_ms(interval)
    else:
        start_time_ms = now_ms - (LOOKBACK_DAYS[interval] * DAY_MS)
    requested_window = {
        "start_time_ms": start_time_ms,
        "end_time_ms": now_ms,
        "lookback_days": round(max(0, now_ms - start_time_ms) / DAY_MS, 3),
    }
    funding_bars = _fetch_ohlc_history(
        url=FUNDING_RATE_HISTORY_URL,
        exchange=DEFAULT_EXCHANGE_NAME,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        http_get_json_fn=http_get_json_fn,
    )
    open_interest_coin_bars = _fetch_ohlc_history(
        url=OPEN_INTEREST_HISTORY_URL,
        exchange=DEFAULT_EXCHANGE_NAME,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        extra_params={"unit": "coin"},
        http_get_json_fn=http_get_json_fn,
    )
    open_interest_usd_bars = _fetch_ohlc_history(
        url=OPEN_INTEREST_HISTORY_URL,
        exchange=DEFAULT_EXCHANGE_NAME,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        extra_params={"unit": "usd"},
        http_get_json_fn=http_get_json_fn,
    )
    price_bars = _fetch_ohlc_history(
        url=PRICE_HISTORY_URL,
        exchange=DEFAULT_EXCHANGE_NAME,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        http_get_json_fn=http_get_json_fn,
    )
    volume_bars = _fetch_taker_buy_sell_volume_history(
        exchange=DEFAULT_EXCHANGE_NAME,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        http_get_json_fn=http_get_json_fn,
    )
    aggregated_rows = _aggregate_derivatives_rows(
        symbol=symbol,
        interval=interval,
        funding_bars=funding_bars,
        open_interest_coin_bars=open_interest_coin_bars,
        open_interest_usd_bars=open_interest_usd_bars,
        price_bars=price_bars,
        volume_bars=volume_bars,
    )
    if aggregated_rows:
        _merge_rows_into_store(
            external_root=external_root,
            symbol=symbol,
            interval=interval,
            rows=aggregated_rows,
        )
    field_coverage = _build_field_coverage(
        requested_window=requested_window,
        interval=interval,
        rows=aggregated_rows,
    )
    coverage_validation = _build_coverage_validation(field_coverage=field_coverage)
    manifest = _rebuild_manifest(
        external_root=external_root,
        symbol=symbol,
        interval=interval,
        requested_window=requested_window,
        field_coverage=field_coverage,
        coverage_validation=coverage_validation,
    )
    return {
        "status": "success",
        "provider": PROVIDER,
        "symbol": symbol,
        "interval": interval,
        "funding_event_count": int((field_coverage.get("funding_rate") or {}).get("event_count", 0) or 0),
        "open_interest_event_count": int((field_coverage.get("open_interest") or {}).get("event_count", 0) or 0),
        "stored_row_count": manifest.get("total_rows", 0),
        "coverage_days": manifest.get("coverage_days", 0.0),
        "requested_window": requested_window,
        "field_coverage": field_coverage,
        "coverage_validation": coverage_validation,
        "manifest_path": str(interval_manifest_path(external_root=external_root, symbol=symbol, interval=interval)),
    }


def _fetch_ohlc_history(
    *,
    url: str,
    exchange: str,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Backward-pagination from end_time. CoinGlass returns at most ~4500 records
    per call ending at end_time, so we walk end_time back until we cover [start, end]."""
    interval_ms = interval_to_ms(interval)
    per_call_limit = 4500
    cur_end = end_time_ms
    bars: list[dict[str, Any]] = []
    max_pages = 64  # safety cap
    for _ in range(max_pages):
        if cur_end <= start_time_ms:
            break
        # Provide a window hint that's wider than per_call_limit can fill, so the API
        # returns the most recent per_call_limit records ending at cur_end.
        window_hint_ms = max(per_call_limit * interval_ms * 2, interval_ms * 1000)
        cur_start = max(start_time_ms, cur_end - window_hint_ms)
        params = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "limit": per_call_limit,
            "start_time": cur_start,
            "end_time": cur_end,
        }
        params.update(dict(extra_params or {}))
        try:
            payload = http_get_json_fn(f"{url}?{urlencode(params)}")
        except HTTPError as exc:
            if exc.code == 400:
                break
            raise
        data = list(dict(payload or {}).get("data") or [])
        if not data:
            break
        normalized = []
        for item in data:
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
            break  # no progress backward
        cur_end = oldest_time - interval_ms
    deduped: dict[int, dict[str, Any]] = {}
    for item in bars:
        deduped[int(item["time"])] = item
    return [deduped[key] for key in sorted(deduped)]


def _fetch_taker_buy_sell_volume_history(
    *,
    exchange: str,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    """Backward-pagination wrapper for taker buy/sell volume endpoint."""
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
        params = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "limit": per_call_limit,
            "start_time": cur_start,
            "end_time": cur_end,
        }
        try:
            payload = http_get_json_fn(f"{TAKER_BUY_SELL_VOLUME_HISTORY_URL}?{urlencode(params)}")
        except HTTPError as exc:
            if exc.code == 400:
                break
            raise
        data = list(dict(payload or {}).get("data") or [])
        if not data:
            break
        normalized: list[dict[str, Any]] = []
        for item in data:
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


def _aggregate_derivatives_rows(
    *,
    symbol: str,
    interval: str,
    funding_bars: list[dict[str, Any]],
    open_interest_coin_bars: list[dict[str, Any]],
    open_interest_usd_bars: list[dict[str, Any]],
    price_bars: list[dict[str, Any]],
    volume_bars: list[dict[str, Any]],
) -> list[dict[str, str]]:
    by_time: dict[int, dict[str, Any]] = {}
    for item in funding_bars:
        by_time.setdefault(int(item["time"]), {})["funding_rate"] = item
    for item in open_interest_coin_bars:
        by_time.setdefault(int(item["time"]), {})["open_interest_coin"] = item
    for item in open_interest_usd_bars:
        by_time.setdefault(int(item["time"]), {})["open_interest_usd"] = item
    for item in price_bars:
        by_time.setdefault(int(item["time"]), {})["price"] = item
    for item in volume_bars:
        by_time.setdefault(int(item["time"]), {})["taker_volume"] = item
    rows: list[dict[str, str]] = []
    for bucket_time in sorted(by_time):
        bucket = by_time[bucket_time]
        funding_rate = _coinglass_bar_close(dict(bucket.get("funding_rate") or {}))
        open_interest = _coinglass_bar_close(dict(bucket.get("open_interest_coin") or {}))
        open_interest_value = _coinglass_bar_close(dict(bucket.get("open_interest_usd") or {}))
        perp_close = _coinglass_bar_close(dict(bucket.get("price") or {}))
        perp_quote_volume_usd = _coinglass_taker_volume_usd(dict(bucket.get("taker_volume") or {}))
        rows.append(
            {
                "exchange": EXCHANGE,
                "market_type": MARKET_TYPE,
                "symbol": symbol,
                "interval": interval,
                "open_time_ms": str(bucket_time),
                "close_time_ms": str(bucket_time + interval_to_ms(interval) - 1),
                "funding_rate": "" if funding_rate is None else f"{funding_rate:.10f}",
                "funding_sample_count": "1" if funding_rate is not None else "0",
                "open_interest": "" if open_interest is None else f"{open_interest:.10f}",
                "open_interest_value": "" if open_interest_value is None else f"{open_interest_value:.10f}",
                "perp_close": "" if perp_close is None else f"{perp_close:.10f}",
                "perp_quote_volume_usd": "" if perp_quote_volume_usd is None else f"{perp_quote_volume_usd:.10f}",
                "source": "coinglass_rest",
            }
        )
    return rows


def _coinglass_bar_close(payload: dict[str, Any]) -> float | None:
    raw = payload.get("close")
    if raw is None:
        raw = payload.get("close_basis")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coinglass_taker_volume_usd(payload: dict[str, Any]) -> float | None:
    candidates = (
        ("taker_buy_volume_usd", "taker_sell_volume_usd"),
        ("buy_volume_usd", "sell_volume_usd"),
        ("buy_usd", "sell_usd"),
        ("buy", "sell"),
    )
    for buy_key, sell_key in candidates:
        if buy_key not in payload and sell_key not in payload:
            continue
        try:
            buy_value = float(payload.get(buy_key) or 0.0)
            sell_value = float(payload.get(sell_key) or 0.0)
        except (TypeError, ValueError):
            continue
        total = buy_value + sell_value
        if total > 0.0:
            return total
    return None


def _row_has_open_interest(row: dict[str, str]) -> bool:
    try:
        open_interest = float(row.get("open_interest", 0.0) or 0.0)
        open_interest_value = float(row.get("open_interest_value", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    return bool(open_interest or open_interest_value)


def _build_field_coverage(
    *,
    requested_window: dict[str, Any],
    interval: str,
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    requested_start_time_ms = int(requested_window["start_time_ms"])
    interval_tolerance_days = interval_to_ms(interval) / DAY_MS
    funding_rows = [row for row in rows if int(row.get("funding_sample_count", 0) or 0) > 0]
    funding_first_timestamp_ms = int(funding_rows[0]["open_time_ms"]) if funding_rows else None
    funding_last_timestamp_ms = int(funding_rows[-1]["close_time_ms"]) if funding_rows else None
    raw_funding_requested_gap_days = _requested_start_gap_days(
        requested_start_time_ms=requested_start_time_ms,
        first_timestamp_ms=funding_first_timestamp_ms,
    )
    funding_requested_gap_days = 0.0 if raw_funding_requested_gap_days <= interval_tolerance_days else raw_funding_requested_gap_days
    funding_shortfall_reason = "provider_data_start_after_requested_window" if funding_requested_gap_days > 0.0 else None
    open_interest_rows = [row for row in rows if _row_has_open_interest(row)]
    open_interest_first_timestamp_ms = int(open_interest_rows[0]["open_time_ms"]) if open_interest_rows else None
    open_interest_last_timestamp_ms = int(open_interest_rows[-1]["close_time_ms"]) if open_interest_rows else None
    raw_open_interest_gap_days = _requested_start_gap_days(
        requested_start_time_ms=requested_start_time_ms,
        first_timestamp_ms=open_interest_first_timestamp_ms,
    )
    open_interest_requested_gap_days = 0.0 if raw_open_interest_gap_days <= interval_tolerance_days else raw_open_interest_gap_days
    open_interest_shortfall_reason = (
        "provider_data_start_after_requested_window"
        if open_interest_requested_gap_days > 0.0
        else None
    )
    return {
        "funding_rate": {
            "event_count": sum(int(row.get("funding_sample_count", 0) or 0) for row in funding_rows),
            "first_timestamp_ms": funding_first_timestamp_ms,
            "last_timestamp_ms": funding_last_timestamp_ms,
            "coverage_days": _coverage_days_between(funding_first_timestamp_ms, funding_last_timestamp_ms),
            "requested_start_gap_days": funding_requested_gap_days,
            "shortfall_reason": funding_shortfall_reason,
        },
        "open_interest": {
            "event_count": len(open_interest_rows),
            "first_timestamp_ms": open_interest_first_timestamp_ms,
            "last_timestamp_ms": open_interest_last_timestamp_ms,
            "coverage_days": _coverage_days_between(open_interest_first_timestamp_ms, open_interest_last_timestamp_ms),
            "requested_start_gap_days": open_interest_requested_gap_days,
            "shortfall_reason": open_interest_shortfall_reason,
            "provider_latest_window_days": None,
            "provider_latest_window_documented": None,
            "provider_capped": False,
        },
    }


def _build_coverage_validation(*, field_coverage: dict[str, Any]) -> dict[str, Any]:
    funding_coverage = dict(field_coverage.get("funding_rate") or {})
    open_interest_coverage = dict(field_coverage.get("open_interest") or {})
    warning_codes: list[str] = []
    if str(funding_coverage.get("shortfall_reason") or "").strip():
        warning_codes.append("funding_rate_provider_data_start_after_requested_window")
    if str(open_interest_coverage.get("shortfall_reason") or "").strip():
        warning_codes.append("open_interest_provider_data_start_after_requested_window")
    summary_parts: list[str] = []
    if "funding_rate_provider_data_start_after_requested_window" in warning_codes:
        summary_parts.append(
            "funding_rate started after the requested window "
            f"(gap_days={funding_coverage.get('requested_start_gap_days', 0.0)})"
        )
    if "open_interest_provider_data_start_after_requested_window" in warning_codes:
        summary_parts.append(
            "open_interest started after the requested window "
            f"(gap_days={open_interest_coverage.get('requested_start_gap_days', 0.0)})"
        )
    return {
        "status": "warning" if warning_codes else "ok",
        "warning_codes": warning_codes,
        "summary_text": (
            "; ".join(summary_parts)
            if summary_parts
            else "funding_rate and open_interest coverage match the requested window"
        ),
    }


def _sync_result_from_stored_rows(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    requested_window: dict[str, Any],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    field_coverage = _build_field_coverage(
        requested_window=requested_window,
        interval=interval,
        rows=rows,
    )
    coverage_validation = _build_coverage_validation(field_coverage=field_coverage)
    return {
        "status": "success",
        "provider": PROVIDER,
        "symbol": symbol,
        "interval": interval,
        "funding_event_count": int((field_coverage.get("funding_rate") or {}).get("event_count", 0) or 0),
        "open_interest_event_count": int((field_coverage.get("open_interest") or {}).get("event_count", 0) or 0),
        "stored_row_count": len(rows),
        "coverage_days": _coverage_days_between(
            int(rows[0]["open_time_ms"]) if rows else None,
            int(rows[-1]["close_time_ms"]) if rows else None,
        ),
        "requested_window": requested_window,
        "field_coverage": field_coverage,
        "coverage_validation": coverage_validation,
        "manifest_path": str(interval_manifest_path(external_root=external_root, symbol=symbol, interval=interval)),
    }


def _rebuild_manifest(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    requested_window: dict[str, Any],
    field_coverage: dict[str, Any],
    coverage_validation: dict[str, Any],
) -> dict[str, Any]:
    root = interval_root(external_root=external_root, symbol=symbol, interval=interval)
    partitions = sorted(root.glob("*.csv.gz"))
    total_rows = 0
    min_open_time_ms: int | None = None
    max_close_time_ms: int | None = None
    for partition in partitions:
        rows = _read_partition_rows(partition)
        if not rows:
            continue
        total_rows += len(rows)
        partition_min = int(rows[0]["open_time_ms"])
        partition_max = int(rows[-1]["close_time_ms"])
        min_open_time_ms = partition_min if min_open_time_ms is None else min(min_open_time_ms, partition_min)
        max_close_time_ms = partition_max if max_close_time_ms is None else max(max_close_time_ms, partition_max)
    coverage_days = _coverage_days_between(min_open_time_ms, max_close_time_ms)
    manifest = {
        "generated_at_utc": _utc_now(),
        "provider": PROVIDER,
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "symbol": symbol,
        "interval": interval,
        "total_rows": total_rows,
        "coverage_days": coverage_days,
        "min_open_time_ms": min_open_time_ms,
        "max_close_time_ms": max_close_time_ms,
        "partitions": [partition.name for partition in partitions],
        "requested_window": requested_window,
        "field_coverage": field_coverage,
        "coverage_validation": coverage_validation,
    }
    _json_write(interval_manifest_path(external_root=external_root, symbol=symbol, interval=interval), manifest)
    return manifest


def _build_sync_summary_payload(
    *,
    external_root: Path,
    mode: str,
    summary_scope: str,
    symbols: list[str],
    intervals: tuple[str, ...],
    sync_results: list[dict[str, Any]],
    as_of: str | None,
    window_end_ms: int | None,
    required_symbols: Iterable[str],
    required_intervals: Iterable[str],
) -> dict[str, Any]:
    warning_codes = sorted(
        {
            str(code)
            for item in sync_results
            for code in list((item.get("coverage_validation") or {}).get("warning_codes") or [])
            if str(code).strip()
        }
    )
    warning_count = sum(
        1
        for item in sync_results
        if isinstance(item, dict) and str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
    )
    payload: dict[str, Any] = {
        "status": "success" if all(item.get("status", "success") == "success" for item in sync_results) else "partial",
        "success": all(item.get("status", "success") == "success" for item in sync_results),
        "generated_at_utc": _utc_now(),
        "provider": PROVIDER,
        "exchange": EXCHANGE,
        "external_root": str(external_root),
        "mode": mode,
        "summary_scope": summary_scope,
        "symbols": list(symbols),
        "intervals": list(intervals),
        "required_symbols": sorted({str(item).strip().upper() for item in required_symbols if str(item).strip()}),
        "required_intervals": [canonical_interval(str(item)) for item in required_intervals if str(item).strip()],
        "sync_results": sync_results,
        "coverage_validation": {
            "status": "warning" if warning_count else "ok",
            "warning_count": warning_count,
            "warning_codes": warning_codes,
        },
        "warning_count": warning_count,
        "provider_cap_summary": _build_provider_cap_summary(sync_results),
        "interval_highlights": _build_interval_highlights(sync_results),
        "input_watermarks": {
            "symbol_count": len(list(symbols)),
        },
        "upstream_versions": {
            "supported_intervals": list(intervals),
            "lookback_days": dict(LOOKBACK_DAYS),
            "api_base_url": COINGLASS_BASE_URL,
        },
    }
    if as_of is not None:
        payload["as_of"] = as_of
    if window_end_ms is not None:
        payload["window_end_ms"] = int(window_end_ms)
    return with_evidence_metadata(
        payload,
        evidence_family="quant_derivatives_sync",
        contract_version=DERIVATIVES_SYNC_CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )


def _build_provider_cap_summary(sync_results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in sync_results:
        if not isinstance(item, dict) or str(item.get("status")) != "success":
            continue
        interval = str(item.get("interval", "")).strip()
        if not interval:
            continue
        grouped.setdefault(interval, []).append(item)
    summary: dict[str, Any] = {}
    for interval, items in grouped.items():
        funding_coverages = [
            float(((item.get("field_coverage") or {}).get("funding_rate") or {}).get("coverage_days", 0.0) or 0.0)
            for item in items
        ]
        open_interest_coverages = [
            float(((item.get("field_coverage") or {}).get("open_interest") or {}).get("coverage_days", 0.0) or 0.0)
            for item in items
        ]
        warning_codes = sorted(
            {
                str(code)
                for item in items
                for code in list((item.get("coverage_validation") or {}).get("warning_codes") or [])
                if str(code).strip()
            }
        )
        summary[interval] = {
            "requested_lookback_days": max(
                float((item.get("requested_window") or {}).get("lookback_days", 0.0) or 0.0)
                for item in items
            ),
            "symbol_count": len(items),
            "warning_count": sum(
                1
                for item in items
                if str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
            ),
            "funding_median_coverage_days": round(statistics.median(funding_coverages), 3) if funding_coverages else 0.0,
            "open_interest_median_coverage_days": (
                round(statistics.median(open_interest_coverages), 3) if open_interest_coverages else 0.0
            ),
            "open_interest_provider_capped_symbol_count": 0,
            "warning_codes": warning_codes,
        }
    return summary


def _build_interval_highlights(sync_results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in sync_results:
        if not isinstance(item, dict):
            continue
        interval = str(item.get("interval", "")).strip()
        if not interval:
            continue
        grouped.setdefault(interval, []).append(item)
    highlights: dict[str, Any] = {}
    for interval, items in grouped.items():
        coverage_days = [float(item.get("coverage_days", 0.0) or 0.0) for item in items if item.get("status") == "success"]
        highlights[interval] = {
            "symbol_count": len(items),
            "success_count": sum(1 for item in items if str(item.get("status")) == "success"),
            "warning_count": sum(
                1
                for item in items
                if str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
            ),
            "requested_lookback_days": max(
                float((item.get("requested_window") or {}).get("lookback_days", 0.0) or 0.0)
                for item in items
                if isinstance(item, dict)
            ),
            "median_stored_coverage_days": round(statistics.median(coverage_days), 3) if coverage_days else 0.0,
        }
    return highlights
