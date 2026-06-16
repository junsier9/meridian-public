from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import gzip
import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import urlencode
from xml.etree import ElementTree

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.utils.binance_http import binance_get_bytes, binance_get_json
from scripts.market_data import binance_ohlcv


ARCHIVE_S3_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DEFAULT_EXTERNAL_ROOT_NAME = "market_history\\binance_1m_five_year"
DEFAULT_MARKETS = ("spot", "usdm_perp")
DEFAULT_INTERVAL = "1m"
DEFAULT_MONTHS = 60
DEFAULT_WORKERS = 8
SUPPORTED_OUTPUT_FORMATS = ("parquet", "csv.gz")
CSV_HEADERS = binance_ohlcv.CSV_HEADERS


@dataclass(frozen=True, slots=True)
class MonthKey:
    year: int
    month: int

    @classmethod
    def parse(cls, value: str) -> "MonthKey":
        parts = str(value).strip().split("-")
        if len(parts) != 2:
            raise ValueError(f"month must be YYYY-MM, got: {value}")
        year = int(parts[0])
        month = int(parts[1])
        if month < 1 or month > 12:
            raise ValueError(f"month must be between 01 and 12, got: {value}")
        return cls(year=year, month=month)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def previous(self) -> "MonthKey":
        if self.month == 1:
            return MonthKey(year=self.year - 1, month=12)
        return MonthKey(year=self.year, month=self.month - 1)

    def next(self) -> "MonthKey":
        if self.month == 12:
            return MonthKey(year=self.year + 1, month=1)
        return MonthKey(year=self.year, month=self.month + 1)

    def to_index(self) -> int:
        return self.year * 12 + self.month


@dataclass(frozen=True, slots=True)
class SymbolArchiveCoverage:
    market_type: str
    symbol: str
    interval: str
    eligible: bool
    required_start_month: str
    required_end_month: str
    required_month_count: int
    available_required_month_count: int
    missing_required_months: tuple[str, ...]
    first_archive_month: str | None
    last_archive_month: str | None
    total_archive_month_count: int
    archive_prefix: str


@dataclass(frozen=True, slots=True)
class PartitionWriteResult:
    market_type: str
    symbol: str
    interval: str
    month: str
    row_count: int
    output_path: str
    status: str
    error: str | None = None
    expected_minute_count: int | None = None
    missing_open_time_count: int | None = None
    duplicate_open_time_count: int | None = None
    outside_month_open_time_count: int | None = None
    first_open_time_ms: int | None = None
    last_open_time_ms: int | None = None


@dataclass(frozen=True, slots=True)
class RestBackfillPartitionResult:
    market_type: str
    symbol: str
    interval: str
    month: str
    output_path: str
    status: str
    existing_row_count: int
    fetched_row_count: int
    written_row_count: int
    missing_open_time_count_before: int
    missing_open_time_count_after: int
    request_count: int
    error: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def resolve_external_root(
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


def previous_complete_month(now: datetime | None = None) -> MonthKey:
    current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    return MonthKey(year=current.year, month=current.month).previous()


def five_year_window(
    *,
    months: int = DEFAULT_MONTHS,
    end_month: str | None = None,
    now: datetime | None = None,
) -> tuple[list[str], str, str]:
    if months <= 0:
        raise ValueError("months must be positive")
    end = MonthKey.parse(end_month) if end_month else previous_complete_month(now)
    start_index = end.to_index() - months + 1
    start = MonthKey(year=(start_index - 1) // 12, month=((start_index - 1) % 12) + 1)
    month_keys = [str(item) for item in month_range(start, end)]
    return month_keys, str(start), str(end)


def month_range(start: MonthKey, end_inclusive: MonthKey) -> Iterable[MonthKey]:
    current = start
    while current.to_index() <= end_inclusive.to_index():
        yield current
        current = current.next()


def discover_five_year_coverage(
    *,
    markets: Iterable[str] = DEFAULT_MARKETS,
    months: int = DEFAULT_MONTHS,
    end_month: str | None = None,
    active_only: bool = True,
    quote_asset: str = binance_ohlcv.DEFAULT_QUOTE_ASSET,
    workers: int = DEFAULT_WORKERS,
    external_root: Path | None = None,
    fetch_text_fn: Callable[[str], str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_root(external_root=external_root)
    resolved_markets = tuple(_require_market_type(item) for item in markets)
    required_months, start_month, resolved_end_month = five_year_window(months=months, end_month=end_month)
    required_set = set(required_months)
    allowed_symbols_by_market = (
        _load_active_symbol_sets(
            resolved_root=resolved_root,
            markets=resolved_markets,
            quote_asset=quote_asset,
            http_get_json_fn=http_get_json_fn,
        )
        if active_only
        else {market: None for market in resolved_markets}
    )

    coverage_entries: list[SymbolArchiveCoverage] = []
    errors: list[dict[str, str]] = []
    for market_type in resolved_markets:
        archive_symbols = list_archive_symbols(market_type=market_type, fetch_text_fn=fetch_text_fn)
        allowed_symbols = allowed_symbols_by_market.get(market_type)
        if allowed_symbols is not None:
            archive_symbols = [symbol for symbol in archive_symbols if symbol in allowed_symbols]
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
            futures = {
                executor.submit(
                    build_symbol_coverage,
                    market_type=market_type,
                    symbol=symbol,
                    required_months=required_months,
                    required_set=required_set,
                    fetch_text_fn=fetch_text_fn,
                ): symbol
                for symbol in archive_symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    coverage_entries.append(future.result())
                except Exception as exc:
                    errors.append({"market_type": market_type, "symbol": symbol, "error": str(exc)})

    coverage_entries.sort(key=lambda item: (item.market_type, item.symbol))
    eligible_entries = [item for item in coverage_entries if item.eligible]
    summary = {
        "status": "success" if not errors else "partial",
        "success": not errors,
        "generated_at_utc": utc_now(),
        "external_root": str(resolved_root),
        "source": "Binance public archive S3 data.binance.vision",
        "interval": DEFAULT_INTERVAL,
        "required_months": required_months,
        "required_start_month": start_month,
        "required_end_month": resolved_end_month,
        "required_month_count": len(required_months),
        "markets": list(resolved_markets),
        "active_only": active_only,
        "quote_asset": quote_asset,
        "coverage_count": len(coverage_entries),
        "eligible_count": len(eligible_entries),
        "eligible_symbols": [
            {"market_type": item.market_type, "symbol": item.symbol}
            for item in eligible_entries
        ],
        "coverage": [_coverage_to_dict(item) for item in coverage_entries],
        "errors": errors,
    }
    write_discovery_summary(external_root=resolved_root, summary=summary)
    return summary


def list_archive_symbols(
    *,
    market_type: str,
    fetch_text_fn: Callable[[str], str] | None = None,
) -> list[str]:
    prefix = f"{binance_ohlcv.MARKET_ARCHIVE_PREFIXES[_require_market_type(market_type)]}/"
    _, common_prefixes = list_s3_prefix(prefix=prefix, delimiter="/", fetch_text_fn=fetch_text_fn)
    symbols = []
    for item in common_prefixes:
        parts = [part for part in item.split("/") if part]
        if parts:
            symbols.append(parts[-1].upper())
    return sorted(set(symbols))


def build_symbol_coverage(
    *,
    market_type: str,
    symbol: str,
    required_months: list[str],
    required_set: set[str],
    fetch_text_fn: Callable[[str], str] | None = None,
) -> SymbolArchiveCoverage:
    prefix = _archive_symbol_interval_prefix(market_type=market_type, symbol=symbol, interval=DEFAULT_INTERVAL)
    keys, _ = list_s3_prefix(prefix=prefix, fetch_text_fn=fetch_text_fn)
    archive_months = sorted(
        {
            month
            for key in keys
            for month in [_month_from_archive_key(key=key, symbol=symbol, interval=DEFAULT_INTERVAL)]
            if month is not None
        }
    )
    available_required = sorted(set(archive_months).intersection(required_set))
    missing_required = tuple(month for month in required_months if month not in available_required)
    return SymbolArchiveCoverage(
        market_type=_require_market_type(market_type),
        symbol=symbol.upper(),
        interval=DEFAULT_INTERVAL,
        eligible=not missing_required,
        required_start_month=required_months[0],
        required_end_month=required_months[-1],
        required_month_count=len(required_months),
        available_required_month_count=len(available_required),
        missing_required_months=missing_required,
        first_archive_month=archive_months[0] if archive_months else None,
        last_archive_month=archive_months[-1] if archive_months else None,
        total_archive_month_count=len(archive_months),
        archive_prefix=prefix,
    )


def list_s3_prefix(
    *,
    prefix: str,
    delimiter: str | None = None,
    fetch_text_fn: Callable[[str], str] | None = None,
) -> tuple[list[str], list[str]]:
    fetch_text = fetch_text_fn or _default_fetch_text
    keys: list[str] = []
    common_prefixes: list[str] = []
    continuation_token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if delimiter is not None:
            params["delimiter"] = delimiter
        if continuation_token:
            params["continuation-token"] = continuation_token
        url = f"{ARCHIVE_S3_URL}?{urlencode(params)}"
        root = ElementTree.fromstring(fetch_text(url))
        keys.extend(_xml_text(child, "Key") for child in _xml_children(root, "Contents") if _xml_text(child, "Key"))
        common_prefixes.extend(
            _xml_text(child, "Prefix")
            for child in _xml_children(root, "CommonPrefixes")
            if _xml_text(child, "Prefix")
        )
        if _xml_text(root, "IsTruncated").lower() != "true":
            break
        continuation_token = _xml_text(root, "NextContinuationToken")
        if not continuation_token:
            break
    return keys, common_prefixes


def download_eligible_1m_archive(
    *,
    discovery_summary: dict[str, Any],
    external_root: Path | None = None,
    symbols: Iterable[str] | None = None,
    markets: Iterable[str] | None = None,
    max_symbols: int | None = None,
    output_format: str = "parquet",
    force: bool = False,
    download_bytes_fn: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_root(external_root=external_root or _path_from_summary(discovery_summary))
    output_format = _require_output_format(output_format)
    eligible_entries = [dict(item) for item in discovery_summary.get("eligible_symbols", [])]
    requested_markets = {item for item in (_require_market_type(market) for market in markets)} if markets else None
    requested_symbols = {str(symbol).strip().upper() for symbol in (symbols or []) if str(symbol).strip()}
    selected_entries = [
        item
        for item in eligible_entries
        if (requested_markets is None or item["market_type"] in requested_markets)
        and (not requested_symbols or item["symbol"] in requested_symbols)
    ]
    if max_symbols is not None:
        selected_entries = selected_entries[: max(0, int(max_symbols))]
    required_months = [str(item) for item in discovery_summary["required_months"]]
    download_bytes = download_bytes_fn or _default_download_bytes
    partition_results: list[PartitionWriteResult] = []

    for entry in selected_entries:
        market_type = _require_market_type(str(entry["market_type"]))
        symbol = str(entry["symbol"]).strip().upper()
        for month in required_months:
            partition_path = data_partition_path(
                external_root=resolved_root,
                market_type=market_type,
                symbol=symbol,
                interval=DEFAULT_INTERVAL,
                month=month,
                output_format=output_format,
            )
            if partition_path.exists() and not force:
                partition_results.append(
                    PartitionWriteResult(
                        market_type=market_type,
                        symbol=symbol,
                        interval=DEFAULT_INTERVAL,
                        month=month,
                        row_count=-1,
                        output_path=str(partition_path),
                        status="skipped_existing",
                    )
                )
                continue
            try:
                year, month_int = [int(part) for part in month.split("-")]
                url = binance_ohlcv._archive_month_url(
                    market_type=market_type,
                    symbol=symbol,
                    interval=DEFAULT_INTERVAL,
                    year=year,
                    month=month_int,
                )
                archive_bytes = download_bytes(url)
                rows = binance_ohlcv._parse_archive_rows(
                    archive_bytes=archive_bytes,
                    market_type=market_type,
                    symbol=symbol,
                    interval=DEFAULT_INTERVAL,
                    source="archive",
                )
                row_count, audit = write_partition(
                    partition_path=partition_path,
                    rows=rows,
                    output_format=output_format,
                    month=month,
                )
                partition_results.append(
                    PartitionWriteResult(
                        market_type=market_type,
                        symbol=symbol,
                        interval=DEFAULT_INTERVAL,
                        month=month,
                        row_count=row_count,
                        output_path=str(partition_path),
                        status="written",
                        **audit,
                    )
                )
            except Exception as exc:
                partition_results.append(
                    PartitionWriteResult(
                        market_type=market_type,
                        symbol=symbol,
                        interval=DEFAULT_INTERVAL,
                        month=month,
                        row_count=0,
                        output_path=str(partition_path),
                        status="error",
                        error=str(exc),
                    )
                )
    summary = build_download_summary(
        external_root=resolved_root,
        discovery_summary=discovery_summary,
        selected_entries=selected_entries,
        output_format=output_format,
        partition_results=partition_results,
    )
    write_download_summary(external_root=resolved_root, summary=summary)
    if output_format == "parquet":
        write_duckdb_view_sql(external_root=resolved_root)
    return summary


def backfill_1m_archive_rest_gaps(
    *,
    external_root: Path,
    symbols: Iterable[str],
    months: Iterable[str],
    markets: Iterable[str] = ("usdm_perp",),
    output_format: str = "parquet",
    force_full_month: bool = False,
    request_sleep_seconds: float = 0.05,
    http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_root(external_root=external_root)
    resolved_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    resolved_months = [str(MonthKey.parse(month)) for month in months]
    resolved_markets = [_require_market_type(market) for market in markets]
    output_format = _require_output_format(output_format)
    http_get_json = http_get_json_fn or _default_http_get_json
    partition_results: list[RestBackfillPartitionResult] = []

    for market_type in resolved_markets:
        for symbol in resolved_symbols:
            for month in resolved_months:
                partition_path = data_partition_path(
                    external_root=resolved_root,
                    market_type=market_type,
                    symbol=symbol,
                    interval=DEFAULT_INTERVAL,
                    month=month,
                    output_format=output_format,
                )
                try:
                    result = _backfill_partition_rest_gaps(
                        partition_path=partition_path,
                        market_type=market_type,
                        symbol=symbol,
                        month=month,
                        output_format=output_format,
                        force_full_month=force_full_month,
                        request_sleep_seconds=request_sleep_seconds,
                        http_get_json_fn=http_get_json,
                    )
                except Exception as exc:
                    existing_rows = _read_partition_rows(partition_path)
                    before_audit = audit_minute_rows(rows=existing_rows, month=month)
                    result = RestBackfillPartitionResult(
                        market_type=market_type,
                        symbol=symbol,
                        interval=DEFAULT_INTERVAL,
                        month=month,
                        output_path=str(partition_path),
                        status="error",
                        existing_row_count=len(existing_rows),
                        fetched_row_count=0,
                        written_row_count=len(existing_rows),
                        missing_open_time_count_before=int(before_audit["missing_open_time_count"] or 0),
                        missing_open_time_count_after=int(before_audit["missing_open_time_count"] or 0),
                        request_count=0,
                        error=str(exc),
                    )
                partition_results.append(result)

    summary = build_rest_backfill_summary(
        external_root=resolved_root,
        symbols=resolved_symbols,
        months=resolved_months,
        markets=resolved_markets,
        output_format=output_format,
        partition_results=partition_results,
    )
    write_rest_backfill_summary(external_root=resolved_root, summary=summary)
    if output_format == "parquet":
        write_duckdb_view_sql(external_root=resolved_root)
    return summary


def _backfill_partition_rest_gaps(
    *,
    partition_path: Path,
    market_type: str,
    symbol: str,
    month: str,
    output_format: str,
    force_full_month: bool,
    request_sleep_seconds: float,
    http_get_json_fn: Callable[[str], Any],
) -> RestBackfillPartitionResult:
    existing_rows = _read_partition_rows(partition_path)
    before_audit = audit_minute_rows(rows=existing_rows, month=month)
    before_missing = int(before_audit["missing_open_time_count"] or 0)
    start_ms, end_ms = _month_window_ms(month)
    request_ranges = [(start_ms, end_ms - 60_000)] if force_full_month else _missing_minute_ranges(existing_rows, month=month)
    if not request_ranges:
        return RestBackfillPartitionResult(
            market_type=market_type,
            symbol=symbol,
            interval=DEFAULT_INTERVAL,
            month=month,
            output_path=str(partition_path),
            status="skipped_complete",
            existing_row_count=len(existing_rows),
            fetched_row_count=0,
            written_row_count=len(existing_rows),
            missing_open_time_count_before=before_missing,
            missing_open_time_count_after=before_missing,
            request_count=0,
        )

    fetched_rows: list[dict[str, str]] = []
    request_count = 0
    for range_start_ms, range_end_ms in request_ranges:
        rows, requests = _fetch_rest_1m_range(
            market_type=market_type,
            symbol=symbol,
            start_time_ms=range_start_ms,
            end_time_ms=range_end_ms,
            http_get_json_fn=http_get_json_fn,
            request_sleep_seconds=request_sleep_seconds,
        )
        fetched_rows.extend(rows)
        request_count += requests

    rows_by_open_time = {int(row["open_time_ms"]): row for row in existing_rows}
    for row in fetched_rows:
        open_time = int(row["open_time_ms"])
        if start_ms <= open_time < end_ms:
            rows_by_open_time[open_time] = row
    merged_rows = [rows_by_open_time[key] for key in sorted(rows_by_open_time)]
    written_row_count, after_audit = write_partition(
        partition_path=partition_path,
        rows=merged_rows,
        output_format=output_format,
        month=month,
    )
    after_missing = int(after_audit["missing_open_time_count"] or 0)
    if after_missing == 0:
        status = "written_complete"
    elif after_missing < before_missing:
        status = "written_partial"
    else:
        status = "unchanged_missing"
    return RestBackfillPartitionResult(
        market_type=market_type,
        symbol=symbol,
        interval=DEFAULT_INTERVAL,
        month=month,
        output_path=str(partition_path),
        status=status,
        existing_row_count=len(existing_rows),
        fetched_row_count=len(fetched_rows),
        written_row_count=written_row_count,
        missing_open_time_count_before=before_missing,
        missing_open_time_count_after=after_missing,
        request_count=request_count,
    )


def _fetch_rest_1m_range(
    *,
    market_type: str,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
    request_sleep_seconds: float,
) -> tuple[list[dict[str, str]], int]:
    interval_ms = binance_ohlcv.interval_to_ms(DEFAULT_INTERVAL)
    request_limit = int(binance_ohlcv.REST_MAX_LIMIT[_require_market_type(market_type)])
    cursor = int(start_time_ms)
    rows: list[dict[str, str]] = []
    request_count = 0
    while cursor <= int(end_time_ms):
        page_rows = binance_ohlcv.fetch_rest_klines(
            market_type=market_type,
            symbol=symbol,
            interval=DEFAULT_INTERVAL,
            start_time_ms=cursor,
            end_time_ms=int(end_time_ms),
            limit=request_limit,
            http_get_json_fn=http_get_json_fn,
        )
        request_count += 1
        if not page_rows:
            break
        rows.extend(page_rows)
        latest_open_time = int(page_rows[-1]["open_time_ms"])
        if latest_open_time < cursor:
            break
        cursor = latest_open_time + interval_ms
        if len(page_rows) < request_limit:
            break
        if request_sleep_seconds > 0:
            time.sleep(float(request_sleep_seconds))
    return rows, request_count


def build_rest_backfill_summary(
    *,
    external_root: Path,
    symbols: list[str],
    months: list[str],
    markets: list[str],
    output_format: str,
    partition_results: list[RestBackfillPartitionResult],
) -> dict[str, Any]:
    errors = [item for item in partition_results if item.status == "error"]
    complete = [item for item in partition_results if item.missing_open_time_count_after == 0]
    improved = [
        item
        for item in partition_results
        if item.missing_open_time_count_after < item.missing_open_time_count_before
    ]
    return {
        "status": "success" if not errors else "partial",
        "success": not errors,
        "generated_at_utc": utc_now(),
        "external_root": str(external_root),
        "source": "Binance USD-M REST fapi/v1/klines",
        "interval": DEFAULT_INTERVAL,
        "markets": markets,
        "symbols": symbols,
        "months": months,
        "output_format": output_format,
        "partition_count": len(partition_results),
        "complete_partition_count": len(complete),
        "improved_partition_count": len(improved),
        "error_partition_count": len(errors),
        "fetched_row_count": sum(int(item.fetched_row_count) for item in partition_results),
        "request_count": sum(int(item.request_count) for item in partition_results),
        "missing_open_time_count_before": sum(int(item.missing_open_time_count_before) for item in partition_results),
        "missing_open_time_count_after": sum(int(item.missing_open_time_count_after) for item in partition_results),
        "partition_results": [asdict(item) for item in partition_results],
    }


def write_partition(
    *,
    partition_path: Path,
    rows: list[dict[str, str]],
    output_format: str,
    month: str,
) -> tuple[int, dict[str, int | None]]:
    output_format = _require_output_format(output_format)
    partition_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=CSV_HEADERS)
    audit = audit_minute_rows(rows=rows, month=month)
    _coerce_kline_frame(frame)
    if output_format == "parquet":
        frame.to_parquet(partition_path, index=False)
    else:
        with gzip.open(partition_path, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
    return len(frame), audit


def _read_partition_rows(partition_path: Path) -> list[dict[str, Any]]:
    if not partition_path.exists():
        return []
    if partition_path.suffix == ".parquet":
        frame = pd.read_parquet(partition_path)
        return _records(frame)
    if partition_path.name.endswith(".csv.gz"):
        with gzip.open(partition_path, "rt", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"unsupported partition format: {partition_path}")


def audit_minute_rows(*, rows: list[dict[str, str]], month: str) -> dict[str, int | None]:
    start_ms, end_ms = _month_window_ms(month)
    expected_count = (end_ms - start_ms) // 60_000
    open_times = []
    for row in rows:
        try:
            open_times.append(int(row["open_time_ms"]))
        except (KeyError, TypeError, ValueError):
            continue
    unique_open_times = set(open_times)
    in_window_open_times = {item for item in unique_open_times if start_ms <= item < end_ms}
    return {
        "expected_minute_count": int(expected_count),
        "missing_open_time_count": int(expected_count - len(in_window_open_times)),
        "duplicate_open_time_count": int(len(open_times) - len(unique_open_times)),
        "outside_month_open_time_count": int(len(unique_open_times) - len(in_window_open_times)),
        "first_open_time_ms": min(open_times) if open_times else None,
        "last_open_time_ms": max(open_times) if open_times else None,
    }


def _missing_minute_ranges(rows: list[dict[str, Any]], *, month: str) -> list[tuple[int, int]]:
    start_ms, end_ms = _month_window_ms(month)
    expected = set(range(start_ms, end_ms, 60_000))
    observed = set()
    for row in rows:
        try:
            value = int(row["open_time_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if start_ms <= value < end_ms:
            observed.add(value)
    return _contiguous_minute_ranges(sorted(expected - observed))


def _contiguous_minute_ranges(open_times: list[int]) -> list[tuple[int, int]]:
    if not open_times:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = int(open_times[0])
    for value in open_times[1:]:
        current = int(value)
        if current == previous + 60_000:
            previous = current
            continue
        ranges.append((start, previous))
        start = previous = current
    ranges.append((start, previous))
    return ranges


def _month_window_ms(month: str) -> tuple[int, int]:
    month_key = MonthKey.parse(month)
    next_month = month_key.next()
    start_ms = int(datetime(month_key.year, month_key.month, 1, tzinfo=UTC).timestamp() * 1000)
    end_ms = int(datetime(next_month.year, next_month.month, 1, tzinfo=UTC).timestamp() * 1000)
    return start_ms, end_ms


def build_download_summary(
    *,
    external_root: Path,
    discovery_summary: dict[str, Any],
    selected_entries: list[dict[str, Any]],
    output_format: str,
    partition_results: list[PartitionWriteResult],
) -> dict[str, Any]:
    errors = [item for item in partition_results if item.status == "error"]
    written = [item for item in partition_results if item.status == "written"]
    skipped = [item for item in partition_results if item.status == "skipped_existing"]
    continuity_checked = [
        item
        for item in partition_results
        if item.status == "written" and item.missing_open_time_count is not None
    ]
    missing_open_time_count = sum(int(item.missing_open_time_count or 0) for item in continuity_checked)
    duplicate_open_time_count = sum(int(item.duplicate_open_time_count or 0) for item in continuity_checked)
    outside_month_open_time_count = sum(int(item.outside_month_open_time_count or 0) for item in continuity_checked)
    return {
        "status": "success" if not errors else "partial",
        "success": not errors,
        "generated_at_utc": utc_now(),
        "external_root": str(external_root),
        "source": discovery_summary.get("source"),
        "interval": DEFAULT_INTERVAL,
        "required_months": discovery_summary.get("required_months", []),
        "required_start_month": discovery_summary.get("required_start_month"),
        "required_end_month": discovery_summary.get("required_end_month"),
        "output_format": output_format,
        "selected_symbol_count": len(selected_entries),
        "selected_symbols": selected_entries,
        "partition_count": len(partition_results),
        "written_partition_count": len(written),
        "skipped_existing_partition_count": len(skipped),
        "error_partition_count": len(errors),
        "written_row_count": sum(item.row_count for item in written),
        "continuity_validation": {
            "checked_partition_count": len(continuity_checked),
            "status": (
                "warning"
                if missing_open_time_count or duplicate_open_time_count or outside_month_open_time_count
                else "ok"
            ),
            "missing_open_time_count": missing_open_time_count,
            "duplicate_open_time_count": duplicate_open_time_count,
            "outside_month_open_time_count": outside_month_open_time_count,
        },
        "partition_results": [asdict(item) for item in partition_results],
    }


def write_duckdb_view_sql(*, external_root: Path) -> Path:
    sql_path = external_root / "duckdb" / "create_binance_1m_view.sql"
    parquet_glob = str((external_root / "data" / "*" / "*" / DEFAULT_INTERVAL / "*.parquet").resolve()).replace("\\", "/")
    sql = (
        "CREATE OR REPLACE VIEW binance_1m_klines AS\n"
        f"SELECT * FROM read_parquet('{parquet_glob}', union_by_name=true);\n"
    )
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(sql, encoding="utf-8")
    return sql_path


def _coverage_to_dict(item: SymbolArchiveCoverage) -> dict[str, Any]:
    payload = asdict(item)
    payload["missing_required_months"] = list(item.missing_required_months)
    return payload


def data_partition_path(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    month: str,
    output_format: str,
) -> Path:
    suffix = ".parquet" if _require_output_format(output_format) == "parquet" else ".csv.gz"
    return (
        external_root
        / "data"
        / _require_market_type(market_type)
        / symbol.upper()
        / binance_ohlcv.canonical_interval(interval)
        / f"{month}{suffix}"
    )


def discovery_summary_path(*, external_root: Path) -> Path:
    return external_root / "discovery" / "latest_five_year_1m_coverage.json"


def discovery_csv_path(*, external_root: Path) -> Path:
    return external_root / "discovery" / "latest_five_year_1m_coverage.csv"


def download_summary_path(*, external_root: Path) -> Path:
    return external_root / "last_download_summary.json"


def write_discovery_summary(*, external_root: Path, summary: dict[str, Any]) -> None:
    path = discovery_summary_path(external_root=external_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = discovery_csv_path(external_root=external_root)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "market_type",
            "symbol",
            "eligible",
            "required_start_month",
            "required_end_month",
            "available_required_month_count",
            "required_month_count",
            "first_archive_month",
            "last_archive_month",
            "total_archive_month_count",
            "missing_required_months",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in summary.get("coverage", []):
            writer.writerow(
                {
                    **{name: item.get(name) for name in fieldnames if name != "missing_required_months"},
                    "missing_required_months": ",".join(item.get("missing_required_months") or []),
                }
            )


def load_discovery_summary(*, external_root: Path) -> dict[str, Any]:
    return json.loads(discovery_summary_path(external_root=external_root).read_text(encoding="utf-8-sig"))


def write_download_summary(*, external_root: Path, summary: dict[str, Any]) -> None:
    path = download_summary_path(external_root=external_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def rest_backfill_summary_path(*, external_root: Path) -> Path:
    return external_root / "last_rest_backfill_summary.json"


def write_rest_backfill_summary(*, external_root: Path, summary: dict[str, Any]) -> None:
    path = rest_backfill_summary_path(external_root=external_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def _load_active_symbol_sets(
    *,
    resolved_root: Path,
    markets: tuple[str, ...],
    quote_asset: str,
    http_get_json_fn: Callable[[str], Any] | None,
) -> dict[str, set[str] | None]:
    catalog = binance_ohlcv.refresh_symbol_catalog(
        external_root=resolved_root / "catalog",
        http_get_json_fn=http_get_json_fn,
    )
    output: dict[str, set[str] | None] = {}
    for market_type in markets:
        symbols = catalog["markets"][market_type]["symbols"]
        output[market_type] = {
            symbol
            for symbol, payload in symbols.items()
            if str(payload.get("quote_asset", "")).upper() == quote_asset.upper()
        }
    return output


def _archive_symbol_interval_prefix(*, market_type: str, symbol: str, interval: str) -> str:
    market_prefix = binance_ohlcv.MARKET_ARCHIVE_PREFIXES[_require_market_type(market_type)]
    archive_interval = binance_ohlcv.archive_interval_name(interval)
    return f"{market_prefix}/{symbol.upper()}/{archive_interval}/"


def _month_from_archive_key(*, key: str, symbol: str, interval: str) -> str | None:
    archive_interval = binance_ohlcv.archive_interval_name(interval)
    name = key.rsplit("/", 1)[-1]
    prefix = f"{symbol.upper()}-{archive_interval}-"
    if not name.startswith(prefix) or not name.endswith(".zip"):
        return None
    month = name[len(prefix) : -4]
    try:
        MonthKey.parse(month)
    except ValueError:
        return None
    return month


def _coerce_kline_frame(frame: pd.DataFrame) -> None:
    int_columns = ("open_time_ms", "close_time_ms", "trade_count")
    float_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    )
    for column in int_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    for column in float_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def _path_from_summary(summary: dict[str, Any]) -> Path | None:
    raw_path = str(summary.get("external_root", "")).strip()
    return Path(raw_path) if raw_path else None


def _require_market_type(value: str) -> str:
    market_type = str(value).strip()
    if market_type not in DEFAULT_MARKETS:
        raise ValueError(f"unsupported market_type: {value}")
    return market_type


def _require_output_format(value: str) -> str:
    output_format = str(value).strip().lower()
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(f"unsupported output format: {value}")
    return output_format


def _default_fetch_text(url: str) -> str:
    return binance_get_bytes(url, timeout_seconds=60.0).decode("utf-8")


def _default_download_bytes(url: str) -> bytes:
    return binance_get_bytes(url, timeout_seconds=120.0)


def _default_http_get_json(url: str) -> Any:
    return binance_get_json(url, timeout_seconds=30.0)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.copy()
    clean = clean.where(pd.notna(clean), None)
    return clean.to_dict(orient="records")


def _xml_children(element: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [child for child in list(element) if _xml_local_name(child.tag) == local_name]


def _xml_text(element: ElementTree.Element, local_name: str) -> str:
    for child in list(element):
        if _xml_local_name(child.tag) == local_name:
            return str(child.text or "")
    return ""


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
