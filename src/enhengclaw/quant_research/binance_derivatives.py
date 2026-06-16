from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
import gzip
import io
import json
import os
from pathlib import Path
import statistics
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.error import HTTPError

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.utils.binance_http import binance_get_json


EXCHANGE = "binance"
MARKET_TYPE = "usdm_perp"
DEFAULT_EXTERNAL_ROOT_NAME = "market_history\\binance_derivatives"
DEFAULT_INTERVALS = ("4h", "1d")
SUPPORTED_INTERVALS = ("15m", "1h", "4h", "1d")
DEFAULT_MODE = "refresh"
DERIVATIVES_SYNC_CONTRACT_VERSION = "quant_derivatives_sync.v2"
USDM_BASE_URL = "https://fapi.binance.com"
FUNDING_RATE_URL = f"{USDM_BASE_URL}/fapi/v1/fundingRate"
OPEN_INTEREST_HIST_URL = f"{USDM_BASE_URL}/futures/data/openInterestHist"
LOOKBACK_DAYS = {"15m": 90, "1h": 365, "4h": 730, "1d": 730}
FUNDING_LIMIT = 1000
OPEN_INTEREST_LIMIT = 500
DAY_MS = 86_400_000
OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DAYS = 29
OPEN_INTEREST_PROVIDER_LATEST_WINDOW_MS = OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DAYS * DAY_MS
OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DOCUMENTED = "latest_1_month"
CSV_HEADERS = (
    "exchange",
    "market_type",
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "funding_rate",
    "funding_sample_count",
    "open_interest",
    "open_interest_value",
    "perp_close",
    "perp_quote_volume_usd",
    "source",
)
ROOT = Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def resolve_external_derivatives_root(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    env = os.environ if base_env is None else base_env
    localappdata = str(env.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()
    return (Path.home() / ".local" / "share" / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()


def canonical_interval(interval: str) -> str:
    normalized = str(interval).strip()
    if normalized not in SUPPORTED_INTERVALS:
        raise ValueError(f"unsupported derivatives interval: {interval}")
    return normalized


def interval_to_ms(interval: str) -> int:
    canonical = canonical_interval(interval)
    if canonical == "15m":
        return 900_000
    if canonical == "1h":
        return 3_600_000
    if canonical == "4h":
        return 14_400_000
    return DAY_MS


def interval_root(*, external_root: Path, symbol: str, interval: str) -> Path:
    return external_root / symbol / canonical_interval(interval)


def interval_manifest_path(*, external_root: Path, symbol: str, interval: str) -> Path:
    return interval_root(external_root=external_root, symbol=symbol, interval=interval) / "manifest.json"


def latest_sync_summary_path(*, external_root: Path) -> Path:
    return external_root / "last_sync_summary.json"


def as_of_sync_summary_path(*, external_root: Path, as_of: str) -> Path:
    return external_root / "summaries" / "by_as_of" / as_of / "sync_summary.json"


def month_partition_path(*, external_root: Path, symbol: str, interval: str, month_key: str) -> Path:
    return interval_root(external_root=external_root, symbol=symbol, interval=interval) / f"{month_key}.csv.gz"


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _json_read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _http_get_json(url: str) -> Any:
    return binance_get_json(url, timeout_seconds=30.0)


def _bucket_open_time(timestamp_ms: int, interval: str) -> int:
    interval_ms = interval_to_ms(interval)
    return (timestamp_ms // interval_ms) * interval_ms


def _as_of_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    as_of_end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, 59, tzinfo=UTC)
    return int(as_of_end.timestamp() * 1000)


def _month_key_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m")


def load_derivatives_rows(
    *,
    external_root: Path | None = None,
    symbol: str,
    interval: str,
    base_env: dict[str, str] | None = None,
    start_time_ms: int | None = None,
) -> list[dict[str, str]]:
    resolved_root = resolve_external_derivatives_root(external_root=external_root, base_env=base_env)
    root = interval_root(external_root=resolved_root, symbol=symbol, interval=interval)
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for partition_path in sorted(root.glob("*.csv.gz")):
        rows.extend(_read_partition_rows(partition_path))
    if start_time_ms is not None:
        rows = [row for row in rows if int(row["open_time_ms"]) >= start_time_ms]
    rows.sort(key=lambda item: int(item["open_time_ms"]))
    return rows


def sync_binance_derivatives_history(
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
    sync_results: list[dict[str, Any]] = []
    for symbol in resolved_symbols:
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
                    }
                )
    overall_status = "success" if all(item.get("status", "success") == "success" for item in sync_results) else "partial"
    warning_entries = [
        item
        for item in sync_results
        if isinstance(item, dict) and str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
    ]
    warning_codes = sorted(
        {
            str(code)
            for item in warning_entries
            for code in list((item.get("coverage_validation") or {}).get("warning_codes") or [])
            if str(code).strip()
        }
    )
    summary = _build_sync_summary_payload(
        external_root=resolved_root,
        mode=mode,
        summary_scope="latest",
        symbols=resolved_symbols,
        intervals=resolved_intervals,
        sync_results=sync_results,
        warning_count=len(warning_entries),
        warning_codes=warning_codes,
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
        archived_summary, archived_path = write_derivatives_sync_summary_for_as_of(
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


def write_derivatives_sync_summary_for_as_of(
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
    warning_entries = [
        item
        for item in sync_results
        if isinstance(item, dict) and str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
    ]
    warning_codes = sorted(
        {
            str(code)
            for item in warning_entries
            for code in list((item.get("coverage_validation") or {}).get("warning_codes") or [])
            if str(code).strip()
        }
    )
    summary = _build_sync_summary_payload(
        external_root=resolved_root,
        mode=mode,
        summary_scope="by_as_of",
        symbols=resolved_symbols,
        intervals=resolved_intervals,
        sync_results=sync_results,
        warning_count=len(warning_entries),
        warning_codes=warning_codes,
        as_of=as_of,
        window_end_ms=as_of_end_ms,
        required_symbols=resolved_symbols,
        required_intervals=resolved_intervals,
    )
    summary_path = as_of_sync_summary_path(external_root=resolved_root, as_of=as_of)
    _json_write(summary_path, summary)
    return summary, summary_path


def _build_sync_summary_payload(
    *,
    external_root: Path,
    mode: str,
    summary_scope: str,
    symbols: list[str],
    intervals: tuple[str, ...],
    sync_results: list[dict[str, Any]],
    warning_count: int,
    warning_codes: list[str],
    as_of: str | None,
    window_end_ms: int | None,
    required_symbols: Iterable[str],
    required_intervals: Iterable[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "success" if all(item.get("status", "success") == "success" for item in sync_results) else "partial",
        "success": all(item.get("status", "success") == "success" for item in sync_results),
        "generated_at_utc": _utc_now(),
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
            "open_interest_provider_latest_window_days": OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DAYS,
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
    funding_events = _fetch_funding_history(
        symbol=symbol,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        http_get_json_fn=http_get_json_fn,
    )
    open_interest_events = _fetch_open_interest_history(
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=now_ms,
        http_get_json_fn=http_get_json_fn,
    )
    aggregated_rows = _aggregate_derivatives_rows(
        symbol=symbol,
        interval=interval,
        funding_events=funding_events,
        open_interest_events=open_interest_events,
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
        funding_events=funding_events,
        open_interest_events=open_interest_events,
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
        "symbol": symbol,
        "interval": interval,
        "funding_event_count": len(funding_events),
        "open_interest_event_count": len(open_interest_events),
        "stored_row_count": manifest.get("total_rows", 0),
        "coverage_days": manifest.get("coverage_days", 0.0),
        "requested_window": requested_window,
        "field_coverage": field_coverage,
        "coverage_validation": coverage_validation,
        "manifest_path": str(interval_manifest_path(external_root=external_root, symbol=symbol, interval=interval)),
    }


def _fetch_funding_history(
    *,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    cursor = start_time_ms
    events: list[dict[str, Any]] = []
    while cursor < end_time_ms:
        params = {
            "symbol": symbol,
            "startTime": cursor,
            "endTime": end_time_ms,
            "limit": FUNDING_LIMIT,
        }
        payload = http_get_json_fn(f"{FUNDING_RATE_URL}?{urlencode(params)}")
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            funding_time = int(item.get("fundingTime"))
            events.append(
                {
                    "timestamp_ms": funding_time,
                    "funding_rate": float(item.get("fundingRate", 0.0)),
                }
            )
        latest_time = int(payload[-1].get("fundingTime"))
        if latest_time <= cursor:
            break
        cursor = latest_time + 1
        if len(payload) < FUNDING_LIMIT:
            break
    return events


def _fetch_open_interest_history(
    *,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    max_lookback_ms = OPEN_INTEREST_PROVIDER_LATEST_WINDOW_MS
    cursor = max(start_time_ms, end_time_ms - max_lookback_ms)
    events: list[dict[str, Any]] = []
    while cursor < end_time_ms:
        params = {
            "symbol": symbol,
            "period": interval,
            "startTime": cursor,
            "endTime": end_time_ms,
            "limit": OPEN_INTEREST_LIMIT,
        }
        try:
            payload = http_get_json_fn(f"{OPEN_INTEREST_HIST_URL}?{urlencode(params)}")
        except HTTPError as exc:
            if exc.code == 400:
                return events
            raise
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            timestamp_ms = int(item.get("timestamp"))
            events.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "open_interest": float(item.get("sumOpenInterest", 0.0)),
                    "open_interest_value": float(item.get("sumOpenInterestValue", 0.0)),
                }
            )
        latest_time = int(payload[-1].get("timestamp"))
        if latest_time <= cursor:
            break
        cursor = latest_time + 1
        if len(payload) < OPEN_INTEREST_LIMIT:
            break
    return events


def _aggregate_derivatives_rows(
    *,
    symbol: str,
    interval: str,
    funding_events: list[dict[str, Any]],
    open_interest_events: list[dict[str, Any]],
) -> list[dict[str, str]]:
    buckets: dict[int, dict[str, Any]] = {}
    for event in funding_events:
        bucket_time = _bucket_open_time(int(event["timestamp_ms"]), interval)
        bucket = buckets.setdefault(
            bucket_time,
            {
                "funding_rates": [],
                "open_interest": None,
                "open_interest_value": None,
            },
        )
        bucket["funding_rates"].append(float(event["funding_rate"]))
    for event in open_interest_events:
        bucket_time = _bucket_open_time(int(event["timestamp_ms"]), interval)
        bucket = buckets.setdefault(
            bucket_time,
            {
                "funding_rates": [],
                "open_interest": None,
                "open_interest_value": None,
            },
        )
        bucket["open_interest"] = float(event["open_interest"])
        bucket["open_interest_value"] = float(event["open_interest_value"])
    rows: list[dict[str, str]] = []
    for bucket_time in sorted(buckets):
        bucket = buckets[bucket_time]
        funding_rates = bucket["funding_rates"]
        funding_rate = sum(funding_rates) / len(funding_rates) if funding_rates else 0.0
        rows.append(
            {
                "exchange": EXCHANGE,
                "market_type": MARKET_TYPE,
                "symbol": symbol,
                "interval": interval,
                "open_time_ms": str(bucket_time),
                "close_time_ms": str(bucket_time + interval_to_ms(interval) - 1),
                "funding_rate": f"{funding_rate:.10f}",
                "funding_sample_count": str(len(funding_rates)),
                "open_interest": f"{float(bucket['open_interest'] or 0.0):.10f}",
                "open_interest_value": f"{float(bucket['open_interest_value'] or 0.0):.10f}",
                "perp_close": "",
                "perp_quote_volume_usd": "",
                "source": "rest",
            }
        )
    return rows


def _merge_rows_into_store(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    rows: Iterable[dict[str, str]],
) -> None:
    rows_by_month: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        rows_by_month.setdefault(_month_key_from_ms(int(row["open_time_ms"])), []).append(row)
    for month_key, month_rows in rows_by_month.items():
        partition_path = month_partition_path(
            external_root=external_root,
            symbol=symbol,
            interval=interval,
            month_key=month_key,
        )
        existing_rows = {int(item["open_time_ms"]): item for item in _read_partition_rows(partition_path)}
        for row in month_rows:
            existing_rows[int(row["open_time_ms"])] = row
        _write_partition_rows(partition_path, [existing_rows[key] for key in sorted(existing_rows)])


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


def _coverage_days_between(start_time_ms: int | None, end_time_ms: int | None) -> float:
    if start_time_ms is None or end_time_ms is None:
        return 0.0
    return round(max(0, end_time_ms - start_time_ms) / DAY_MS, 3)


def _requested_start_gap_days(*, requested_start_time_ms: int, first_timestamp_ms: int | None) -> float:
    if first_timestamp_ms is None or first_timestamp_ms <= requested_start_time_ms:
        return 0.0
    return round((first_timestamp_ms - requested_start_time_ms) / DAY_MS, 3)


def _build_field_coverage(
    *,
    requested_window: dict[str, Any],
    interval: str,
    funding_events: list[dict[str, Any]],
    open_interest_events: list[dict[str, Any]],
) -> dict[str, Any]:
    requested_start_time_ms = int(requested_window["start_time_ms"])
    requested_end_time_ms = int(requested_window["end_time_ms"])
    alignment_tolerance_days = interval_to_ms(interval) / DAY_MS
    funding_timestamps = sorted(int(event["timestamp_ms"]) for event in funding_events if event.get("timestamp_ms") is not None)
    funding_first_timestamp_ms = funding_timestamps[0] if funding_timestamps else None
    funding_last_timestamp_ms = funding_timestamps[-1] if funding_timestamps else None
    raw_funding_requested_gap_days = _requested_start_gap_days(
        requested_start_time_ms=requested_start_time_ms,
        first_timestamp_ms=funding_first_timestamp_ms,
    )
    funding_requested_gap_days = (
        0.0
        if raw_funding_requested_gap_days <= alignment_tolerance_days
        else raw_funding_requested_gap_days
    )
    funding_shortfall_reason = (
        "provider_data_start_after_requested_window"
        if funding_requested_gap_days > 0.0
        else None
    )

    open_interest_timestamps = sorted(
        int(event["timestamp_ms"]) for event in open_interest_events if event.get("timestamp_ms") is not None
    )
    open_interest_first_timestamp_ms = open_interest_timestamps[0] if open_interest_timestamps else None
    open_interest_last_timestamp_ms = open_interest_timestamps[-1] if open_interest_timestamps else None
    provider_window_start_ms = max(requested_start_time_ms, requested_end_time_ms - OPEN_INTEREST_PROVIDER_LATEST_WINDOW_MS)
    open_interest_provider_capped = requested_start_time_ms < (requested_end_time_ms - OPEN_INTEREST_PROVIDER_LATEST_WINDOW_MS)
    open_interest_gap_reference_ms = (
        open_interest_first_timestamp_ms
        if open_interest_first_timestamp_ms is not None
        else provider_window_start_ms
    )
    open_interest_requested_gap_days = _requested_start_gap_days(
        requested_start_time_ms=requested_start_time_ms,
        first_timestamp_ms=open_interest_gap_reference_ms,
    )

    return {
        "funding_rate": {
            "event_count": len(funding_events),
            "first_timestamp_ms": funding_first_timestamp_ms,
            "last_timestamp_ms": funding_last_timestamp_ms,
            "coverage_days": _coverage_days_between(funding_first_timestamp_ms, funding_last_timestamp_ms),
            "requested_start_gap_days": funding_requested_gap_days,
            "shortfall_reason": funding_shortfall_reason,
        },
        "open_interest": {
            "event_count": len(open_interest_events),
            "first_timestamp_ms": open_interest_first_timestamp_ms,
            "last_timestamp_ms": open_interest_last_timestamp_ms,
            "coverage_days": _coverage_days_between(open_interest_first_timestamp_ms, open_interest_last_timestamp_ms),
            "requested_start_gap_days": open_interest_requested_gap_days,
            "shortfall_reason": (
                "provider_latest_window_cap"
                if open_interest_provider_capped
                else None
            ),
            "provider_latest_window_days": OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DAYS,
            "provider_latest_window_documented": OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DOCUMENTED,
            "provider_capped": open_interest_provider_capped,
        },
    }


def _build_coverage_validation(*, field_coverage: dict[str, Any]) -> dict[str, Any]:
    funding_coverage = dict(field_coverage.get("funding_rate") or {})
    open_interest_coverage = dict(field_coverage.get("open_interest") or {})
    warning_codes: list[str] = []
    if str(funding_coverage.get("shortfall_reason") or "").strip():
        warning_codes.append("funding_rate_provider_data_start_after_requested_window")
    if bool(open_interest_coverage.get("provider_capped")):
        warning_codes.append("open_interest_provider_latest_window_cap")
    summary_parts: list[str] = []
    if "funding_rate_provider_data_start_after_requested_window" in warning_codes:
        summary_parts.append(
            "funding_rate started after the requested window "
            f"(gap_days={funding_coverage.get('requested_start_gap_days', 0.0)})"
        )
    if "open_interest_provider_latest_window_cap" in warning_codes:
        summary_parts.append(
            "open_interest is provider-capped to the latest window "
            f"({OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DAYS} days)"
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
    field_coverage = _build_field_coverage_from_rows(
        requested_window=requested_window,
        interval=interval,
        rows=rows,
    )
    coverage_validation = _build_coverage_validation(field_coverage=field_coverage)
    return {
        "status": "success",
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


def _row_has_open_interest(row: dict[str, str]) -> bool:
    try:
        open_interest = float(row.get("open_interest", 0.0) or 0.0)
        open_interest_value = float(row.get("open_interest_value", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    return bool(open_interest or open_interest_value)


def _build_field_coverage_from_rows(
    *,
    requested_window: dict[str, Any],
    interval: str,
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    requested_start_time_ms = int(requested_window["start_time_ms"])
    requested_end_time_ms = int(requested_window["end_time_ms"])
    alignment_tolerance_days = interval_to_ms(interval) / DAY_MS
    funding_rows = [
        row
        for row in rows
        if int(row.get("funding_sample_count", 0) or 0) > 0
    ]
    funding_first_timestamp_ms = int(funding_rows[0]["open_time_ms"]) if funding_rows else None
    funding_last_timestamp_ms = int(funding_rows[-1]["close_time_ms"]) if funding_rows else None
    raw_funding_requested_gap_days = _requested_start_gap_days(
        requested_start_time_ms=requested_start_time_ms,
        first_timestamp_ms=funding_first_timestamp_ms,
    )
    funding_requested_gap_days = (
        0.0
        if raw_funding_requested_gap_days <= alignment_tolerance_days
        else raw_funding_requested_gap_days
    )
    funding_shortfall_reason = (
        "provider_data_start_after_requested_window"
        if funding_requested_gap_days > 0.0
        else None
    )

    open_interest_rows = [row for row in rows if _row_has_open_interest(row)]
    open_interest_first_timestamp_ms = int(open_interest_rows[0]["open_time_ms"]) if open_interest_rows else None
    open_interest_last_timestamp_ms = int(open_interest_rows[-1]["close_time_ms"]) if open_interest_rows else None
    provider_window_start_ms = max(requested_start_time_ms, requested_end_time_ms - OPEN_INTEREST_PROVIDER_LATEST_WINDOW_MS)
    open_interest_provider_capped = requested_start_time_ms < (requested_end_time_ms - OPEN_INTEREST_PROVIDER_LATEST_WINDOW_MS)
    open_interest_gap_reference_ms = (
        open_interest_first_timestamp_ms
        if open_interest_first_timestamp_ms is not None
        else provider_window_start_ms
    )
    open_interest_requested_gap_days = _requested_start_gap_days(
        requested_start_time_ms=requested_start_time_ms,
        first_timestamp_ms=open_interest_gap_reference_ms,
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
            "shortfall_reason": (
                "provider_latest_window_cap"
                if open_interest_provider_capped
                else None
            ),
            "provider_latest_window_days": OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DAYS,
            "provider_latest_window_documented": OPEN_INTEREST_PROVIDER_LATEST_WINDOW_DOCUMENTED,
            "provider_capped": open_interest_provider_capped,
        },
    }


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
            "open_interest_provider_capped_symbol_count": sum(
                1
                for item in items
                if bool(((item.get("field_coverage") or {}).get("open_interest") or {}).get("provider_capped"))
            ),
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
        successful_items = [item for item in items if str(item.get("status")) == "success"]
        coverage_days = [float(item.get("coverage_days", 0.0) or 0.0) for item in successful_items]
        highlights[interval] = {
            "symbol_count": len(items),
            "success_count": len(successful_items),
            "warning_count": sum(
                1
                for item in successful_items
                if str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
            ),
            "requested_lookback_days": max(
                (
                    float((item.get("requested_window") or {}).get("lookback_days", 0.0) or 0.0)
                    for item in successful_items
                ),
                default=0.0,
            ),
            "median_stored_coverage_days": round(statistics.median(coverage_days), 3) if coverage_days else 0.0,
        }
    return highlights


def _read_partition_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _write_partition_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())
