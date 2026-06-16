from __future__ import annotations

import csv
from datetime import UTC, datetime
import gzip
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.quant_research.contracts import read_json
from scripts.market_data.binance_ohlcv import CSV_HEADERS, interval_to_ms


COINAPI_API_BASE_URL = "https://rest.coinapi.io"
COINAPI_API_KEY_ENV_VAR = "CoinAPI"
DEFAULT_EXTERNAL_ROOT_NAME = "market_history\\coinapi_ohlcv"
DEFAULT_INTERVALS = ("1h", "4h", "1d")
DEFAULT_EXCHANGE_ID = "BINANCE"
DEFAULT_QUOTE_ASSET = "USDT"
DEFAULT_MARKET_TYPE = "spot"
DEFAULT_HISTORY_PAGE_LIMIT = 10_000
BOOTSTRAP_LOOKBACK_DAYS = {"1h": 60, "4h": 240, "1d": 730}
INTERVAL_TO_PERIOD_ID = {
    "1m": "1MIN",
    "5m": "5MIN",
    "15m": "15MIN",
    "30m": "30MIN",
    "1h": "1HRS",
    "2h": "2HRS",
    "4h": "4HRS",
    "6h": "6HRS",
    "8h": "8HRS",
    "12h": "12HRS",
    "1d": "1DAY",
    "3d": "3DAY",
    "1w": "7DAY",
    "1M": "1MTH",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def resolve_external_history_root(
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


def symbol_catalog_path(*, external_root: Path) -> Path:
    return external_root / "symbol_catalog.json"


def exchange_mapping_path(*, external_root: Path) -> Path:
    return external_root / "exchange_mapping.json"


def interval_root(*, external_root: Path, market_type: str, symbol: str, interval: str) -> Path:
    return external_root / market_type / symbol / interval


def interval_manifest_path(*, external_root: Path, market_type: str, symbol: str, interval: str) -> Path:
    return interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval) / "manifest.json"


def month_partition_path(*, external_root: Path, market_type: str, symbol: str, interval: str, month_key: str) -> Path:
    return interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval) / f"{month_key}.csv.gz"


def _json_default_writer(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _require_api_key(*, env_var: str = COINAPI_API_KEY_ENV_VAR) -> str:
    api_key = str(os.environ.get(env_var, "")).strip()
    if not api_key:
        raise RuntimeError(
            f"CoinAPI API key is missing; set environment variable '{env_var}' before calling CoinAPI sync."
        )
    return api_key


def _coinapi_http_get_json(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_attempts: int = 4,
    backoff_seconds: float = 0.5,
    urlopen_fn: Callable[..., Any] | None = None,
    api_key_env_var: str = COINAPI_API_KEY_ENV_VAR,
) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "EnhengClaw/0.1",
        "X-CoinAPI-Key": _require_api_key(env_var=api_key_env_var),
    }
    opener = urlopen if urlopen_fn is None else urlopen_fn
    request = Request(url, headers=request_headers, method="GET")
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with opener(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code in {401, 403}:
                raise RuntimeError(f"CoinAPI request unauthorized for {url}: HTTP {exc.code}") from exc
            if exc.code == 429 or 500 <= exc.code <= 599:
                if attempt >= max_attempts:
                    raise RuntimeError(f"CoinAPI request failed for {url}: HTTP {exc.code}") from exc
                time.sleep(backoff_seconds * attempt)
                continue
            raise RuntimeError(f"CoinAPI request failed for {url}: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise RuntimeError(f"CoinAPI request failed for {url}: {exc}") from exc
            time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"CoinAPI request failed for {url}: {last_error}")


def _period_id_for_interval(interval: str) -> str:
    normalized = str(interval).strip()
    if normalized not in INTERVAL_TO_PERIOD_ID:
        raise ValueError(
            "unsupported CoinAPI interval: "
            f"{interval}; supported intervals are {', '.join(sorted(INTERVAL_TO_PERIOD_ID))}"
        )
    return INTERVAL_TO_PERIOD_ID[normalized]


def _normalize_symbol(value: str) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise ValueError("symbol must be non-empty")
    return normalized


def _normalize_exchange_id(value: str) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise ValueError("exchange_id must be non-empty")
    return normalized


def _isoformat_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_time_value(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) == 10:
        normalized = f"{normalized}T00:00:00+00:00"
    else:
        normalized = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 time value: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _datetime_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _align_time_ms_to_interval(*, value_ms: int, interval: str) -> int:
    interval_ms = interval_to_ms(interval)
    return (int(value_ms) // interval_ms) * interval_ms


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _float_string(value: float) -> str:
    return f"{float(value):.8f}"


def _load_partition_rows(partition_path: Path) -> list[dict[str, str]]:
    if not partition_path.exists():
        return []
    with gzip.open(partition_path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_partition_rows(*, partition_path: Path, rows: list[dict[str, str]]) -> None:
    partition_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(partition_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def load_interval_rows(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
) -> list[dict[str, str]]:
    root = interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval)
    rows: list[dict[str, str]] = []
    for partition_path in sorted(root.glob("*.csv.gz")):
        rows.extend(_load_partition_rows(partition_path))
    rows.sort(key=lambda item: int(item["open_time_ms"]))
    return rows


def _merge_rows_into_store(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    rows: Iterable[dict[str, str]],
) -> None:
    rows_by_month: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        month_key = datetime.fromtimestamp(int(row["open_time_ms"]) / 1000, tz=UTC).strftime("%Y-%m")
        rows_by_month.setdefault(month_key, []).append(row)
    for month_key, month_rows in rows_by_month.items():
        partition_path = month_partition_path(
            external_root=external_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            month_key=month_key,
        )
        existing_rows = {int(item["open_time_ms"]): item for item in _load_partition_rows(partition_path)}
        for row in month_rows:
            existing_rows[int(row["open_time_ms"])] = row
        _write_partition_rows(
            partition_path=partition_path,
            rows=[existing_rows[key] for key in sorted(existing_rows)],
        )


def _rebuild_interval_manifest(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    exchange_id: str,
    coinapi_symbol_id: str,
    source_symbol: str | None,
    quote_volume_mode: str,
) -> dict[str, Any]:
    root = interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval)
    partitions = sorted(root.glob("*.csv.gz"))
    total_rows = 0
    min_open_time_ms: int | None = None
    max_close_time_ms: int | None = None
    for partition_path in partitions:
        partition_rows = _load_partition_rows(partition_path)
        if not partition_rows:
            continue
        total_rows += len(partition_rows)
        partition_min = int(partition_rows[0]["open_time_ms"])
        partition_max = int(partition_rows[-1]["close_time_ms"])
        min_open_time_ms = partition_min if min_open_time_ms is None else min(min_open_time_ms, partition_min)
        max_close_time_ms = partition_max if max_close_time_ms is None else max(max_close_time_ms, partition_max)
    coverage_days = 0.0
    if min_open_time_ms is not None and max_close_time_ms is not None:
        coverage_days = round((max_close_time_ms - min_open_time_ms) / 86_400_000, 3)
    manifest = {
        "generated_at_utc": _utc_now(),
        "provider": "coinapi",
        "provider_exchange_id": exchange_id,
        "exchange": exchange_id.lower(),
        "market_type": market_type,
        "symbol": symbol,
        "interval": interval,
        "coinapi_symbol_id": coinapi_symbol_id,
        "source_symbol": source_symbol,
        "quote_volume_mode": quote_volume_mode,
        "total_rows": total_rows,
        "coverage_days": coverage_days,
        "min_open_time_ms": min_open_time_ms,
        "max_close_time_ms": max_close_time_ms,
        "partitions": [partition.name for partition in partitions],
    }
    _json_default_writer(
        interval_manifest_path(
            external_root=external_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
        ),
        manifest,
    )
    return manifest


def _discover_symbols_from_quant_inputs(*, quant_input_root: Path | None) -> list[str]:
    if quant_input_root is None:
        return []
    root = quant_input_root.expanduser().resolve()
    if not root.exists():
        return []
    candidates: list[tuple[str, Path]] = []
    for path in sorted(root.glob("*.quant_universe.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        as_of = str(payload.get("as_of", "")).strip()
        if not as_of:
            continue
        candidates.append((as_of, path))
    if not candidates:
        return []
    _, latest_path = sorted(candidates, key=lambda item: (item[0], str(item[1])))[-1]
    payload = read_json(latest_path)
    discovered: list[str] = []
    for item in payload.get("candidates", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("spot_symbol", "")).strip().upper()
        if symbol and symbol not in discovered:
            discovered.append(symbol)
    return discovered


def refresh_symbol_catalog(
    *,
    external_root: Path | None = None,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
    quote_asset: str = DEFAULT_QUOTE_ASSET,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    resolved_exchange_id = _normalize_exchange_id(exchange_id)
    resolved_quote_asset = _normalize_symbol(quote_asset)
    http_get_json = http_get_json_fn or _coinapi_http_get_json
    active_symbols_url = f"{COINAPI_API_BASE_URL}/v1/symbols/{quote(resolved_exchange_id)}/active"
    mapping_url = f"{COINAPI_API_BASE_URL}/v1/symbols/map/{quote(resolved_exchange_id)}"
    active_payload = http_get_json(active_symbols_url)
    mapping_payload = http_get_json(mapping_url)
    if not isinstance(active_payload, list):
        raise ValueError(f"unexpected CoinAPI active symbols payload for {resolved_exchange_id}")
    if not isinstance(mapping_payload, list):
        raise ValueError(f"unexpected CoinAPI symbol mapping payload for {resolved_exchange_id}")

    mapping_by_symbol_id: dict[str, dict[str, Any]] = {}
    for item in mapping_payload:
        if not isinstance(item, dict):
            continue
        symbol_id = str(item.get("symbol_id", "")).strip()
        if symbol_id:
            mapping_by_symbol_id[symbol_id] = item

    spot_symbols: dict[str, dict[str, Any]] = {}
    canonical_to_coinapi: dict[str, str] = {}
    coinapi_to_exchange: dict[str, str] = {}

    for item in active_payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol_type", "")).strip().upper() != "SPOT":
            continue
        asset_id_base = str(item.get("asset_id_base", "")).strip().upper()
        asset_id_quote = str(item.get("asset_id_quote", "")).strip().upper()
        symbol_id = str(item.get("symbol_id", "")).strip()
        if not symbol_id or not asset_id_base or asset_id_quote != resolved_quote_asset:
            continue
        canonical_symbol = f"{asset_id_base}{asset_id_quote}"
        mapping = mapping_by_symbol_id.get(symbol_id, {})
        source_symbol = str(mapping.get("symbol_id_exchange") or item.get("symbol_id_exchange") or "").strip() or None
        candidate = {
            "canonical_symbol": canonical_symbol,
            "coinapi_symbol_id": symbol_id,
            "exchange_id": resolved_exchange_id,
            "symbol_type": "SPOT",
            "asset_id_base": asset_id_base,
            "asset_id_quote": asset_id_quote,
            "source_symbol": source_symbol,
            "data_start": item.get("data_start"),
            "data_end": item.get("data_end"),
            "data_quote_start": item.get("data_quote_start"),
            "data_quote_end": item.get("data_quote_end"),
            "data_orderbook_start": item.get("data_orderbook_start"),
            "data_orderbook_end": item.get("data_orderbook_end"),
            "price_precision": mapping.get("price_precision"),
            "size_precision": mapping.get("size_precision"),
        }
        existing = spot_symbols.get(canonical_symbol)
        if existing is None or _candidate_catalog_priority(candidate) > _candidate_catalog_priority(existing):
            spot_symbols[canonical_symbol] = candidate
            canonical_to_coinapi[canonical_symbol] = symbol_id
            if source_symbol:
                coinapi_to_exchange[symbol_id] = source_symbol

    catalog = {
        "generated_at_utc": _utc_now(),
        "provider": "coinapi",
        "provider_api_base_url": COINAPI_API_BASE_URL,
        "exchange_id": resolved_exchange_id,
        "quote_asset": resolved_quote_asset,
        "market_type": DEFAULT_MARKET_TYPE,
        "markets": {
            "spot": {
                "symbols": spot_symbols,
            }
        },
    }
    mapping_payload = {
        "generated_at_utc": catalog["generated_at_utc"],
        "provider": "coinapi",
        "exchange_id": resolved_exchange_id,
        "quote_asset": resolved_quote_asset,
        "canonical_to_coinapi_symbol_id": canonical_to_coinapi,
        "coinapi_symbol_id_to_exchange_symbol": coinapi_to_exchange,
    }
    _json_default_writer(symbol_catalog_path(external_root=resolved_root), catalog)
    _json_default_writer(exchange_mapping_path(external_root=resolved_root), mapping_payload)
    return catalog


def _candidate_catalog_priority(candidate: dict[str, Any]) -> tuple[int, int, str]:
    symbol_id = str(candidate.get("coinapi_symbol_id", ""))
    canonical_symbol = str(candidate.get("canonical_symbol", ""))
    expected_symbol_id = (
        f"{str(candidate.get('exchange_id', '')).upper()}_SPOT_"
        f"{str(candidate.get('asset_id_base', '')).upper()}_{str(candidate.get('asset_id_quote', '')).upper()}"
    )
    has_exact_coinapi_symbol = int(symbol_id == expected_symbol_id)
    has_exchange_symbol = int(bool(candidate.get("source_symbol")))
    return (has_exact_coinapi_symbol, has_exchange_symbol, canonical_symbol)


def load_symbol_catalog(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
    quote_asset: str = DEFAULT_QUOTE_ASSET,
    refresh_if_missing: bool = True,
) -> dict[str, Any]:
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    path = symbol_catalog_path(external_root=resolved_root)
    if not path.exists():
        if not refresh_if_missing:
            raise FileNotFoundError(f"CoinAPI symbol catalog not found: {path}")
        return refresh_symbol_catalog(
            external_root=resolved_root,
            exchange_id=exchange_id,
            quote_asset=quote_asset,
            base_env=base_env,
            http_get_json_fn=http_get_json_fn,
    )
    return read_json(path)


def _build_source_symbol_alias_index(*, known_symbols: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    alias_index: dict[str, dict[str, Any]] = {}
    for metadata in known_symbols.values():
        source_symbol = str(metadata.get("source_symbol") or "").strip().upper()
        if not source_symbol:
            continue
        existing = alias_index.get(source_symbol)
        if existing is None or _candidate_catalog_priority(metadata) > _candidate_catalog_priority(existing):
            alias_index[source_symbol] = metadata
    return alias_index


def sync_coinapi_ohlcv(
    *,
    external_root: Path | None = None,
    symbols: Iterable[str] | None = None,
    intervals: Iterable[str] = DEFAULT_INTERVALS,
    mode: str = "refresh",
    exchange_id: str = DEFAULT_EXCHANGE_ID,
    quote_asset: str = DEFAULT_QUOTE_ASSET,
    quant_input_root: Path | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
    refresh_catalog: bool = False,
) -> dict[str, Any]:
    if mode not in {"bootstrap", "refresh"}:
        raise ValueError("mode must be one of: bootstrap, refresh")
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    resolved_exchange_id = _normalize_exchange_id(exchange_id)
    resolved_quote_asset = _normalize_symbol(quote_asset)
    resolved_intervals = tuple(str(item).strip() for item in intervals if str(item).strip())
    for interval in resolved_intervals:
        _period_id_for_interval(interval)
        interval_to_ms(interval)

    if refresh_catalog:
        catalog = refresh_symbol_catalog(
            external_root=resolved_root,
            exchange_id=resolved_exchange_id,
            quote_asset=resolved_quote_asset,
            base_env=base_env,
            http_get_json_fn=http_get_json_fn,
        )
    else:
        catalog = load_symbol_catalog(
            external_root=resolved_root,
            exchange_id=resolved_exchange_id,
            quote_asset=resolved_quote_asset,
            base_env=base_env,
            http_get_json_fn=http_get_json_fn,
            refresh_if_missing=True,
        )

    explicit_symbols = [_normalize_symbol(item) for item in (symbols or []) if str(item).strip()]
    discovery_source = "explicit_symbols"
    if explicit_symbols:
        requested_symbols = explicit_symbols
    else:
        requested_symbols = _discover_symbols_from_quant_inputs(quant_input_root=quant_input_root)
        discovery_source = "latest_quant_input"

    http_get_json = http_get_json_fn or _coinapi_http_get_json
    known_symbols = catalog["markets"]["spot"]["symbols"]
    source_symbol_alias_index = _build_source_symbol_alias_index(known_symbols=known_symbols)
    missing_symbols = [
        symbol
        for symbol in requested_symbols
        if symbol not in known_symbols and symbol not in source_symbol_alias_index
    ]
    sync_results: list[dict[str, Any]] = []
    skipped_symbols: list[str] = []
    alias_resolved_symbols: list[str] = []
    requested_time_start = _parse_time_value(time_start)
    requested_time_end = _parse_time_value(time_end)

    for symbol in requested_symbols:
        metadata = known_symbols.get(symbol)
        if metadata is None:
            metadata = source_symbol_alias_index.get(symbol)
            if metadata is not None and symbol not in alias_resolved_symbols:
                alias_resolved_symbols.append(symbol)
        if metadata is None:
            skipped_symbols.append(symbol)
            continue
        for interval in resolved_intervals:
            sync_results.append(
                _refresh_interval(
                    external_root=resolved_root,
                    symbol=symbol,
                    interval=interval,
                    metadata=metadata,
                    mode=mode,
                    http_get_json_fn=http_get_json,
                    requested_time_start=requested_time_start,
                    requested_time_end=requested_time_end,
                )
            )

    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": _utc_now(),
            "provider": "coinapi",
            "provider_api_base_url": COINAPI_API_BASE_URL,
            "external_root": str(resolved_root),
            "exchange_id": resolved_exchange_id,
            "quote_asset": resolved_quote_asset,
            "market_type": DEFAULT_MARKET_TYPE,
            "mode": mode,
            "intervals": list(resolved_intervals),
            "requested_symbols": requested_symbols,
            "requested_symbol_count": len(requested_symbols),
            "synced_symbol_count": len({item["symbol"] for item in sync_results}),
            "sync_results": sync_results,
            "skipped_symbols": skipped_symbols,
            "missing_requested_symbols": missing_symbols,
            "symbol_catalog_path": str(symbol_catalog_path(external_root=resolved_root)),
            "exchange_mapping_path": str(exchange_mapping_path(external_root=resolved_root)),
            "discovery_source": discovery_source,
            "alias_resolved_symbols": alias_resolved_symbols,
            "time_start": None if requested_time_start is None else _isoformat_z(requested_time_start),
            "time_end": None if requested_time_end is None else _isoformat_z(requested_time_end),
            "input_watermarks": {
                "requested_symbol_count": len(requested_symbols),
                "symbol_catalog_generated_at_utc": catalog.get("generated_at_utc"),
                "alias_resolution_count": len(alias_resolved_symbols),
            },
            "upstream_versions": {
                "exchange_id": resolved_exchange_id,
                "quote_asset": resolved_quote_asset,
                "intervals": list(resolved_intervals),
            },
        },
        evidence_family="coinapi_ohlcv_sync",
        contract_version="coinapi_ohlcv_sync.v1",
        repo_root=ROOT,
    )
    _json_default_writer(resolved_root / "last_sync_summary.json", summary)
    return summary


def _refresh_interval(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    metadata: dict[str, Any],
    mode: str,
    http_get_json_fn: Callable[[str], Any],
    requested_time_start: datetime | None,
    requested_time_end: datetime | None,
) -> dict[str, Any]:
    interval_ms = interval_to_ms(interval)
    now_utc = datetime.now(UTC)
    current_rows = load_interval_rows(
        external_root=external_root,
        market_type=DEFAULT_MARKET_TYPE,
        symbol=symbol,
        interval=interval,
    )
    if current_rows and mode == "refresh":
        start_time_ms = int(current_rows[-1]["open_time_ms"]) + interval_ms
    elif requested_time_start is not None:
        start_time_ms = _align_time_ms_to_interval(
            value_ms=_datetime_to_ms(requested_time_start),
            interval=interval,
        )
    else:
        lookback_days = BOOTSTRAP_LOOKBACK_DAYS.get(interval, 90)
        start_time_ms = _align_time_ms_to_interval(
            value_ms=_datetime_to_ms(now_utc) - (lookback_days * 86_400_000),
            interval=interval,
        )

    raw_end_time_ms = _datetime_to_ms(requested_time_end) if requested_time_end is not None else _datetime_to_ms(now_utc)
    end_time_ms = _align_time_ms_to_interval(value_ms=raw_end_time_ms, interval=interval)
    fetched_rows: list[dict[str, str]] = []
    request_count = 0
    while start_time_ms < end_time_ms:
        page_rows = fetch_ohlcv_history(
            coinapi_symbol_id=str(metadata["coinapi_symbol_id"]),
            canonical_symbol=symbol,
            exchange_id=str(metadata["exchange_id"]),
            source_symbol=metadata.get("source_symbol"),
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            limit=DEFAULT_HISTORY_PAGE_LIMIT,
            http_get_json_fn=http_get_json_fn,
        )
        request_count += 1
        if not page_rows:
            break
        fetched_rows.extend(page_rows)
        latest_open_time_ms = int(page_rows[-1]["open_time_ms"])
        next_start_time_ms = latest_open_time_ms + interval_ms
        if next_start_time_ms <= start_time_ms:
            break
        start_time_ms = next_start_time_ms
        if len(page_rows) < DEFAULT_HISTORY_PAGE_LIMIT:
            break

    if fetched_rows:
        _merge_rows_into_store(
            external_root=external_root,
            market_type=DEFAULT_MARKET_TYPE,
            symbol=symbol,
            interval=interval,
            rows=fetched_rows,
        )
    manifest = _rebuild_interval_manifest(
        external_root=external_root,
        market_type=DEFAULT_MARKET_TYPE,
        symbol=symbol,
        interval=interval,
        exchange_id=str(metadata["exchange_id"]),
        coinapi_symbol_id=str(metadata["coinapi_symbol_id"]),
        source_symbol=None if metadata.get("source_symbol") is None else str(metadata["source_symbol"]),
        quote_volume_mode="estimated_from_typical_price",
    )
    return {
        "market_type": DEFAULT_MARKET_TYPE,
        "symbol": symbol,
        "interval": interval,
        "coinapi_symbol_id": metadata["coinapi_symbol_id"],
        "source_symbol": metadata.get("source_symbol"),
        "fetched_row_count": len(fetched_rows),
        "request_count": request_count,
        "manifest_path": str(
            interval_manifest_path(
                external_root=external_root,
                market_type=DEFAULT_MARKET_TYPE,
                symbol=symbol,
                interval=interval,
            )
        ),
        "coverage_days": manifest.get("coverage_days", 0.0),
    }


def fetch_ohlcv_history(
    *,
    coinapi_symbol_id: str,
    canonical_symbol: str,
    exchange_id: str,
    source_symbol: str | None,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, str]]:
    url = (
        f"{COINAPI_API_BASE_URL}/v1/ohlcv/{quote(str(coinapi_symbol_id), safe='')}/history?"
        f"{urlencode({'period_id': _period_id_for_interval(interval), 'time_start': _isoformat_z(datetime.fromtimestamp(start_time_ms / 1000, tz=UTC)), 'time_end': _isoformat_z(datetime.fromtimestamp(end_time_ms / 1000, tz=UTC)), 'limit': limit})}"
    )
    payload = http_get_json_fn(url)
    if not isinstance(payload, list):
        raise ValueError(f"unexpected CoinAPI OHLCV payload for {coinapi_symbol_id}:{interval}")
    return [
        _normalize_ohlcv_row(
            item=item,
            canonical_symbol=canonical_symbol,
            coinapi_symbol_id=coinapi_symbol_id,
            exchange_id=exchange_id,
            source_symbol=source_symbol,
            interval=interval,
        )
        for item in payload
        if isinstance(item, dict)
    ]


def _normalize_ohlcv_row(
    *,
    item: dict[str, Any],
    canonical_symbol: str,
    coinapi_symbol_id: str,
    exchange_id: str,
    source_symbol: str | None,
    interval: str,
) -> dict[str, str]:
    time_period_start = _parse_time_value(str(item.get("time_period_start") or "")) or _parse_time_value(
        str(item.get("time_open") or "")
    )
    time_period_end = _parse_time_value(str(item.get("time_period_end") or "")) or _parse_time_value(
        str(item.get("time_close") or "")
    )
    if time_period_start is None or time_period_end is None:
        raise ValueError(f"CoinAPI OHLCV row is missing time bounds for {coinapi_symbol_id}:{interval}")
    open_price = _safe_float(item.get("price_open"))
    high_price = _safe_float(item.get("price_high"))
    low_price = _safe_float(item.get("price_low"))
    close_price = _safe_float(item.get("price_close"))
    base_volume = _safe_float(item.get("volume_traded"))
    trade_count = int(_safe_float(item.get("trades_count")))
    typical_price = max((open_price + high_price + low_price + close_price) / 4.0, 0.0)
    estimated_quote_volume = base_volume * typical_price
    return {
        "exchange": exchange_id.lower(),
        "market_type": DEFAULT_MARKET_TYPE,
        "symbol": canonical_symbol,
        "interval": interval,
        "open_time_ms": str(_datetime_to_ms(time_period_start)),
        "close_time_ms": str(max(_datetime_to_ms(time_period_end) - 1, _datetime_to_ms(time_period_start))),
        "open": _float_string(open_price),
        "high": _float_string(high_price),
        "low": _float_string(low_price),
        "close": _float_string(close_price),
        "volume": _float_string(base_volume),
        "quote_volume": _float_string(estimated_quote_volume),
        "trade_count": str(trade_count),
        "taker_buy_base_volume": _float_string(0.0),
        "taker_buy_quote_volume": _float_string(0.0),
        "source": _source_label(coinapi_symbol_id=coinapi_symbol_id, source_symbol=source_symbol),
    }


def _source_label(*, coinapi_symbol_id: str, source_symbol: str | None) -> str:
    if source_symbol:
        return f"coinapi_rest:{coinapi_symbol_id}:{source_symbol}"
    return f"coinapi_rest:{coinapi_symbol_id}"
