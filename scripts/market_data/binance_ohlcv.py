from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import gzip
import io
import json
import math
import os
from pathlib import Path
from statistics import pstdev
import sys
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.utils.binance_http import binance_get_bytes, binance_get_json


EXCHANGE = "binance"
DEFAULT_EXTERNAL_ROOT_NAME = "market_history\\binance_ohlcv"
DEFAULT_MARKETS = ("spot", "usdm_perp")
DEFAULT_INTERVALS = ("1h", "4h", "1d")
DEFAULT_QUOTE_ASSET = "USDT"
SUPPORTED_INTERVALS = (
    "1s",
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)
CANONICAL_INTERVAL_ALIASES = {"1mo": "1M"}
RESEARCH_INTERVALS = ("1h", "4h", "1d")
RESEARCH_COVERAGE_THRESHOLDS_DAYS = {"1h": 30, "4h": 120, "1d": 180}
BOOTSTRAP_LOOKBACK_DAYS = {"1h": 60, "4h": 240, "1d": 730}
REST_MAX_LIMIT = {"spot": 1000, "usdm_perp": 1500}
SPOT_BASE_URL = "https://api.binance.com"
USDM_BASE_URL = "https://fapi.binance.com"
SPOT_EXCHANGE_INFO_URL = f"{SPOT_BASE_URL}/api/v3/exchangeInfo"
USDM_EXCHANGE_INFO_URL = f"{USDM_BASE_URL}/fapi/v1/exchangeInfo"
MARKET_REST_ENDPOINTS = {
    "spot": f"{SPOT_BASE_URL}/api/v3/klines",
    "usdm_perp": f"{USDM_BASE_URL}/fapi/v1/klines",
}
MARKET_ARCHIVE_PREFIXES = {
    "spot": "data/spot/monthly/klines",
    "usdm_perp": "data/futures/um/monthly/klines",
}
ARCHIVE_BASE_URL = "https://data.binance.vision"
CSV_HEADERS = (
    "exchange",
    "market_type",
    "symbol",
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
    "source",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def resolve_external_history_root(
    *, external_root: Path | None = None, base_env: dict[str, str] | None = None
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
    if not normalized:
        raise ValueError("interval must be non-empty")
    normalized = CANONICAL_INTERVAL_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_INTERVALS:
        raise ValueError(f"unsupported interval: {interval}")
    return normalized


def archive_interval_name(interval: str) -> str:
    canonical = canonical_interval(interval)
    return "1mo" if canonical == "1M" else canonical


def interval_to_ms(interval: str) -> int:
    canonical = canonical_interval(interval)
    mapping = {
        "1s": 1_000,
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "2h": 7_200_000,
        "4h": 14_400_000,
        "6h": 21_600_000,
        "8h": 28_800_000,
        "12h": 43_200_000,
        "1d": 86_400_000,
        "3d": 259_200_000,
        "1w": 604_800_000,
        "1M": 2_592_000_000,
    }
    return mapping[canonical]


def normalize_binance_epoch_to_ms(raw_value: Any) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Binance timestamp: {raw_value}") from exc
    if value > 10_000_000_000_000:
        return value // 1000
    return value


def symbol_catalog_path(*, external_root: Path) -> Path:
    return external_root / "symbol_catalog.json"


def market_root(*, external_root: Path, market_type: str) -> Path:
    return external_root / market_type


def interval_root(*, external_root: Path, market_type: str, symbol: str, interval: str) -> Path:
    return market_root(external_root=external_root, market_type=market_type) / symbol / canonical_interval(interval)


def interval_manifest_path(*, external_root: Path, market_type: str, symbol: str, interval: str) -> Path:
    return interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval) / "manifest.json"


def month_partition_path(*, external_root: Path, market_type: str, symbol: str, interval: str, month_key: str) -> Path:
    return interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval) / f"{month_key}.csv.gz"


def _json_default_writer(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _json_reader(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _default_http_get_json(url: str) -> Any:
    return binance_get_json(url, timeout_seconds=30.0)


def _default_download_bytes(url: str) -> bytes:
    return binance_get_bytes(url, timeout_seconds=60.0)


def refresh_symbol_catalog(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    http_get_json = http_get_json_fn or _default_http_get_json
    spot_exchange_info = http_get_json(SPOT_EXCHANGE_INFO_URL)
    usdm_exchange_info = http_get_json(USDM_EXCHANGE_INFO_URL)
    catalog = {
        "generated_at_utc": _utc_now(),
        "exchange": EXCHANGE,
        "quote_universe": DEFAULT_QUOTE_ASSET,
        "markets": {
            "spot": {"symbols": _extract_spot_symbols(spot_exchange_info)},
            "usdm_perp": {"symbols": _extract_usdm_perp_symbols(usdm_exchange_info)},
        },
    }
    _json_default_writer(symbol_catalog_path(external_root=resolved_root), catalog)
    return catalog


def load_symbol_catalog(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
    refresh_if_missing: bool = True,
) -> dict[str, Any]:
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    path = symbol_catalog_path(external_root=resolved_root)
    if not path.exists():
        if not refresh_if_missing:
            raise FileNotFoundError(f"symbol catalog not found: {path}")
        return refresh_symbol_catalog(
            external_root=resolved_root,
            base_env=base_env,
            http_get_json_fn=http_get_json_fn,
        )
    return _json_reader(path)


def resolve_market_symbols(
    *,
    subject: str,
    scope: str,
    symbol_catalog: dict[str, Any],
    spot_symbol: str | None = None,
    usdm_symbol: str | None = None,
) -> dict[str, Any]:
    normalized_subject = str(subject).strip().upper()
    if not normalized_subject:
        raise ValueError("subject must be non-empty for market symbol resolution")
    spot_symbols = symbol_catalog["markets"]["spot"]["symbols"]
    usdm_symbols = symbol_catalog["markets"]["usdm_perp"]["symbols"]
    inferred_symbol = f"{normalized_subject}{DEFAULT_QUOTE_ASSET}"
    resolved_spot_symbol = _resolve_market_symbol_candidate(
        market_symbols=spot_symbols,
        explicit_symbol=spot_symbol,
        inferred_symbol=inferred_symbol,
        market_type="spot",
    )
    resolved_usdm_symbol = _resolve_market_symbol_candidate(
        market_symbols=usdm_symbols,
        explicit_symbol=usdm_symbol,
        inferred_symbol=inferred_symbol,
        market_type="usdm_perp",
    )
    requires_spot = "spot" in scope
    requires_perp = "perp" in scope
    return {
        "subject": normalized_subject,
        "scope": scope,
        "spot_symbol": resolved_spot_symbol if requires_spot else None,
        "usdm_symbol": resolved_usdm_symbol if requires_perp else None,
        "status": _overall_symbol_resolution_status(
            requires_spot=requires_spot,
            requires_perp=requires_perp,
            spot_symbol=resolved_spot_symbol,
            usdm_symbol=resolved_usdm_symbol,
        ),
    }


def discover_active_market_symbol_pairs(
    *,
    workbench_root: Path,
    symbol_catalog: dict[str, Any],
) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not workbench_root.exists():
        return []

    for thesis_profile_path in sorted(workbench_root.glob("*/thesis_profile.json")):
        try:
            payload = _json_reader(thesis_profile_path)
        except Exception:
            continue
        for market_type, symbol in _extract_market_pairs_from_payload(
            payload=payload,
            symbol_catalog=symbol_catalog,
        ):
            pairs.add((market_type, symbol))

    for snapshot_path in sorted((workbench_root / "_incoming").glob("*.snapshot.json")):
        try:
            payload = _json_reader(snapshot_path)
        except Exception:
            continue
        for market_type, symbol in _extract_market_pairs_from_payload(
            payload=payload,
            symbol_catalog=symbol_catalog,
        ):
            pairs.add((market_type, symbol))

    for market_scan_path in sorted((workbench_root / "_scan_inputs").glob("*.market_scan.json")):
        try:
            payload = _json_reader(market_scan_path)
        except Exception:
            continue
        for candidate in payload.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            try:
                market_symbols = resolve_market_symbols(
                    subject=str(candidate.get("subject", "")),
                    scope=str(candidate.get("scope", "spot+perp")).strip() or "spot+perp",
                    symbol_catalog=symbol_catalog,
                    spot_symbol=_optional_symbol(candidate.get("spot_symbol")),
                    usdm_symbol=_optional_symbol(candidate.get("usdm_symbol")),
                )
            except Exception:
                continue
            for market_type, symbol in _market_symbol_pairs_from_mapping(market_symbols):
                pairs.add((market_type, symbol))
    return sorted(pairs)


def sync_binance_ohlcv(
    *,
    external_root: Path | None = None,
    symbols: Iterable[str] | None = None,
    markets: Iterable[str] = DEFAULT_MARKETS,
    intervals: Iterable[str] = DEFAULT_INTERVALS,
    mode: str = "refresh",
    workbench_root: Path | None = None,
    base_env: dict[str, str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
    download_bytes_fn: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    if mode not in {"bootstrap", "refresh"}:
        raise ValueError("mode must be one of: bootstrap, refresh")
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    resolved_markets = tuple(_require_market_type(item) for item in markets)
    resolved_intervals = tuple(canonical_interval(item) for item in intervals)
    catalog = load_symbol_catalog(
        external_root=resolved_root,
        base_env=base_env,
        http_get_json_fn=http_get_json_fn,
    )
    explicit_symbols = [str(item).strip().upper() for item in (symbols or []) if str(item).strip()]
    if explicit_symbols:
        market_symbol_pairs = [
            (market_type, symbol)
            for market_type in resolved_markets
            for symbol in explicit_symbols
            if symbol in set(catalog["markets"][market_type]["symbols"].keys())
        ]
    elif workbench_root is not None:
        market_symbol_pairs = [
            (market_type, symbol)
            for market_type, symbol in discover_active_market_symbol_pairs(
                workbench_root=workbench_root.expanduser().resolve(),
                symbol_catalog=catalog,
            )
            if market_type in resolved_markets
        ]
    else:
        market_symbol_pairs = []

    http_get_json = http_get_json_fn or _default_http_get_json
    download_bytes = download_bytes_fn or _default_download_bytes
    sync_results: list[dict[str, Any]] = []
    for market_type, symbol in market_symbol_pairs:
        for interval in resolved_intervals:
            if mode == "bootstrap":
                _bootstrap_interval(
                    external_root=resolved_root,
                    market_type=market_type,
                    symbol=symbol,
                    interval=interval,
                    download_bytes_fn=download_bytes,
                )
            sync_results.append(
                _refresh_interval(
                    external_root=resolved_root,
                    market_type=market_type,
                    symbol=symbol,
                    interval=interval,
                    http_get_json_fn=http_get_json,
                )
            )
    summary = with_evidence_metadata(
        {
        "status": "success",
        "success": True,
        "generated_at_utc": _utc_now(),
        "external_root": str(resolved_root),
        "mode": mode,
        "markets": list(resolved_markets),
        "intervals": list(resolved_intervals),
        "symbol_count": len({symbol for _, symbol in market_symbol_pairs}),
        "market_symbol_pairs": [
            {"market_type": market_type, "symbol": symbol}
            for market_type, symbol in market_symbol_pairs
        ],
        "sync_results": sync_results,
        "symbol_catalog_path": str(symbol_catalog_path(external_root=resolved_root)),
        "input_watermarks": {
            "symbol_count": len({symbol for _, symbol in market_symbol_pairs}),
        },
        "upstream_versions": {
            "markets": list(resolved_markets),
            "intervals": list(resolved_intervals),
        },
        },
        evidence_family="binance_ohlcv_sync",
        contract_version="binance_ohlcv_sync.v1",
        repo_root=ROOT,
    )
    _json_default_writer(resolved_root / "last_sync_summary.json", summary)
    return summary


def build_ohlcv_context(
    *,
    external_root: Path | None = None,
    market_symbols: dict[str, Any],
    scope: str,
    intervals: Iterable[str] = RESEARCH_INTERVALS,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_history_root(external_root=external_root, base_env=base_env)
    resolved_intervals = tuple(canonical_interval(item) for item in intervals)
    markets: dict[str, Any] = {}
    all_ready = True
    any_ready = False
    breakout_comparison_ready = False
    for market_type, symbol in _market_symbol_pairs_from_mapping(market_symbols):
        interval_contexts: dict[str, Any] = {}
        for interval in resolved_intervals:
            rows = load_interval_rows(
                external_root=resolved_root,
                market_type=market_type,
                symbol=symbol,
                interval=interval,
            )
            interval_contexts[interval] = _build_interval_context(rows=rows, interval=interval)
        daily_rows = load_interval_rows(
            external_root=resolved_root,
            market_type=market_type,
            symbol=symbol,
            interval="1d",
        )
        breakout_samples = _compute_breakout_samples(daily_rows)
        market_status = _combine_market_status(interval_contexts=interval_contexts)
        breakout_ready_for_market = len(breakout_samples) > 0
        breakout_comparison_ready = breakout_comparison_ready or breakout_ready_for_market
        markets[market_type] = {
            "market_type": market_type,
            "symbol": symbol,
            "status": market_status,
            "intervals": interval_contexts,
            "breakout_samples_1d": breakout_samples[:3],
            "breakout_comparison_ready": breakout_ready_for_market,
        }
        if market_status == "full":
            any_ready = True
        if market_status != "full":
            all_ready = False

    if all_ready and markets:
        overall_status = "full"
    elif any_ready:
        overall_status = "partial"
    else:
        overall_status = "missing"

    history_coverage = {
        "status": overall_status,
        "scope": scope,
        "markets": {
            market_type: {
                "symbol": entry["symbol"],
                "status": entry["status"],
                "intervals": {
                    interval: {
                        "bars": entry["intervals"][interval]["bar_count"],
                        "coverage_days": entry["intervals"][interval]["coverage_days"],
                        "ready": entry["intervals"][interval]["ready"],
                    }
                    for interval in resolved_intervals
                },
            }
            for market_type, entry in markets.items()
        },
        "breakout_comparison_ready": breakout_comparison_ready,
    }
    context = {
        "generated_at_utc": _utc_now(),
        "exchange": EXCHANGE,
        "scope": scope,
        "market_symbols": {
            "spot_symbol": market_symbols.get("spot_symbol"),
            "usdm_symbol": market_symbols.get("usdm_symbol"),
        },
        "history_coverage": history_coverage,
        "markets": markets,
    }
    context["summary_text"] = build_ohlcv_context_text(context)
    return context


def write_ohlcv_context_bundle(
    *,
    context: dict[str, Any],
    json_path: Path,
    markdown_path: Path,
) -> None:
    _json_default_writer(json_path, context)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(build_ohlcv_context_markdown(context) + "\n", encoding="utf-8")


def load_ohlcv_context_from_ref(ref_path: str | None) -> dict[str, Any] | None:
    if not ref_path:
        return None
    path = Path(ref_path)
    if not path.exists():
        return None
    return _json_reader(path)


def build_ohlcv_context_text(context: dict[str, Any]) -> str:
    history_coverage = context.get("history_coverage", {})
    lines = [
        f"history_coverage_status={history_coverage.get('status', 'missing')}",
        f"breakout_comparison_ready={history_coverage.get('breakout_comparison_ready', False)}",
    ]
    for market_type, market_entry in context.get("markets", {}).items():
        lines.append(
            f"{market_type}:{market_entry.get('symbol')} status={market_entry.get('status')} "
            f"breakout_samples={len(market_entry.get('breakout_samples_1d', []))}"
        )
        for interval, interval_entry in market_entry.get("intervals", {}).items():
            lines.append(
                f"{market_type}:{interval} bars={interval_entry.get('bar_count')} "
                f"coverage_days={interval_entry.get('coverage_days')} ready={interval_entry.get('ready')} "
                f"last_close={interval_entry.get('last_close')} rvol20={interval_entry.get('relative_volume_20')} "
                f"rv20={interval_entry.get('realized_volatility_20')}"
            )
    return "\n".join(lines)


def build_ohlcv_context_markdown(context: dict[str, Any]) -> str:
    lines = [
        "# OHLCV Context",
        "",
        f"- Generated at: `{context.get('generated_at_utc')}`",
        f"- Coverage status: `{context.get('history_coverage', {}).get('status', 'missing')}`",
        f"- Breakout comparison ready: `{context.get('history_coverage', {}).get('breakout_comparison_ready', False)}`",
        "",
    ]
    for market_type, market_entry in context.get("markets", {}).items():
        lines.extend(
            [
                f"## {market_type} `{market_entry.get('symbol')}`",
                "",
                f"- Market status: `{market_entry.get('status')}`",
                "",
            ]
        )
        for interval, interval_entry in market_entry.get("intervals", {}).items():
            lines.append(
                f"- `{interval}` bars=`{interval_entry['bar_count']}` "
                f"coverage_days=`{interval_entry['coverage_days']}` "
                f"ready=`{interval_entry['ready']}` "
                f"last_close=`{interval_entry['last_close']}` "
                f"rvol20=`{interval_entry['relative_volume_20']}` "
                f"rv20=`{interval_entry['realized_volatility_20']}`"
            )
        if market_entry.get("breakout_samples_1d"):
            lines.extend(["", "### Recent 1d Breakout Samples", ""])
            for sample in market_entry["breakout_samples_1d"][:3]:
                lines.append(
                    "- `{breakout_open_time_utc}` forward_5d_return_pct=`{forward_5d_return_pct}` "
                    "max_drawdown_10d_pct=`{max_drawdown_10d_pct}`".format(**sample)
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def load_interval_rows(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    start_time_ms: int | None = None,
) -> list[dict[str, str]]:
    root = interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval)
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for partition_path in sorted(root.glob("*.csv.gz")):
        rows.extend(_read_partition_rows(partition_path))
    if start_time_ms is not None:
        rows = [row for row in rows if int(row["open_time_ms"]) >= start_time_ms]
    rows.sort(key=lambda item: int(item["open_time_ms"]))
    return rows


def _bootstrap_interval(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    download_bytes_fn: Callable[[str], bytes],
) -> None:
    now = datetime.now(UTC)
    lookback_days = BOOTSTRAP_LOOKBACK_DAYS.get(interval, 90)
    start_date = (now - timedelta(days=lookback_days)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month = datetime(now.year, now.month, 1, tzinfo=UTC)
    for month_start in _month_range(start_date, current_month):
        month_key = month_start.strftime("%Y-%m")
        partition_path = month_partition_path(
            external_root=external_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            month_key=month_key,
        )
        if partition_path.exists():
            continue
        archive_url = _archive_month_url(
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            year=month_start.year,
            month=month_start.month,
        )
        try:
            archive_bytes = download_bytes_fn(archive_url)
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        except URLError:
            continue
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 404:
                continue
            raise
        rows = _parse_archive_rows(
            archive_bytes=archive_bytes,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            source="archive",
        )
        _merge_rows_into_store(
            external_root=external_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            rows=rows,
        )


def _refresh_interval(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    http_get_json_fn: Callable[[str], Any],
) -> dict[str, Any]:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    existing_rows = load_interval_rows(
        external_root=external_root,
        market_type=market_type,
        symbol=symbol,
        interval=interval,
    )
    interval_ms = interval_to_ms(interval)
    if existing_rows:
        start_time_ms = int(existing_rows[-1]["open_time_ms"]) + interval_ms
    else:
        start_time_ms = now_ms - (BOOTSTRAP_LOOKBACK_DAYS.get(interval, 90) * 86_400_000)

    fetched_rows: list[dict[str, str]] = []
    request_limit = REST_MAX_LIMIT[market_type]
    while start_time_ms < now_ms:
        page_rows = fetch_rest_klines(
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=now_ms,
            limit=request_limit,
            http_get_json_fn=http_get_json_fn,
        )
        if not page_rows:
            break
        fetched_rows.extend(page_rows)
        latest_open_time = int(page_rows[-1]["open_time_ms"])
        if latest_open_time < start_time_ms:
            break
        start_time_ms = latest_open_time + interval_ms
        if len(page_rows) < request_limit:
            break

    if fetched_rows:
        _merge_rows_into_store(
            external_root=external_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            rows=fetched_rows,
        )
    manifest = _rebuild_interval_manifest(
        external_root=external_root,
        market_type=market_type,
        symbol=symbol,
        interval=interval,
    )
    return {
        "market_type": market_type,
        "symbol": symbol,
        "interval": interval,
        "fetched_row_count": len(fetched_rows),
        "manifest_path": str(
            interval_manifest_path(
                external_root=external_root,
                market_type=market_type,
                symbol=symbol,
                interval=interval,
            )
        ),
        "coverage_days": manifest.get("coverage_days", 0.0),
    }


def fetch_rest_klines(
    *,
    market_type: str,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, str]]:
    endpoint = MARKET_REST_ENDPOINTS[_require_market_type(market_type)]
    params = {
        "symbol": symbol,
        "interval": canonical_interval(interval),
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": limit,
    }
    payload = http_get_json_fn(f"{endpoint}?{urlencode(params)}")
    if not isinstance(payload, list):
        raise ValueError(f"unexpected Binance klines payload for {market_type}:{symbol}:{interval}")
    return [
        _normalize_kline_row(
            item=item,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            source="rest",
        )
        for item in payload
    ]


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
        existing_rows = {int(item["open_time_ms"]): item for item in _read_partition_rows(partition_path)}
        for row in month_rows:
            existing_rows[int(row["open_time_ms"])] = row
        _write_partition_rows(
            partition_path=partition_path,
            rows=[existing_rows[key] for key in sorted(existing_rows)],
        )
    _rebuild_interval_manifest(
        external_root=external_root,
        market_type=market_type,
        symbol=symbol,
        interval=interval,
    )


def _rebuild_interval_manifest(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
) -> dict[str, Any]:
    root = interval_root(external_root=external_root, market_type=market_type, symbol=symbol, interval=interval)
    partitions = sorted(root.glob("*.csv.gz"))
    total_rows = 0
    min_open_time_ms: int | None = None
    max_close_time_ms: int | None = None
    for partition in partitions:
        partition_rows = _read_partition_rows(partition)
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
        "exchange": EXCHANGE,
        "market_type": market_type,
        "symbol": symbol,
        "interval": canonical_interval(interval),
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


def _build_interval_context(*, rows: list[dict[str, str]], interval: str) -> dict[str, Any]:
    canonical = canonical_interval(interval)
    threshold_days = RESEARCH_COVERAGE_THRESHOLDS_DAYS.get(canonical, 0)
    if not rows:
        return {
            "interval": canonical,
            "bar_count": 0,
            "coverage_days": 0.0,
            "ready": False,
            "last_open_time_utc": None,
            "last_close_time_utc": None,
            "last_close": None,
            "distance_to_high_pct": {"20": None, "60": None, "120": None},
            "distance_to_low_pct": {"20": None, "60": None, "120": None},
            "relative_volume_20": None,
            "realized_volatility_20": None,
        }
    first_open_ms = int(rows[0]["open_time_ms"])
    last_close_ms = int(rows[-1]["close_time_ms"])
    coverage_days = round((last_close_ms - first_open_ms) / 86_400_000, 3)
    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    last_close = closes[-1]
    distances_high: dict[str, float | None] = {}
    distances_low: dict[str, float | None] = {}
    for window in (20, 60, 120):
        window_high = max(highs[-window:]) if len(highs) >= window else None
        window_low = min(lows[-window:]) if len(lows) >= window else None
        distances_high[str(window)] = (
            round(((last_close / window_high) - 1.0) * 100, 4) if window_high not in (None, 0) else None
        )
        distances_low[str(window)] = (
            round(((last_close / window_low) - 1.0) * 100, 4) if window_low not in (None, 0) else None
        )
    previous_volumes = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
    relative_volume_20 = None
    if previous_volumes:
        average_volume = sum(previous_volumes) / len(previous_volumes)
        if average_volume > 0:
            relative_volume_20 = round(volumes[-1] / average_volume, 4)
    realized_volatility_20 = None
    if len(closes) >= 21:
        returns = [math.log(closes[idx] / closes[idx - 1]) for idx in range(len(closes) - 19, len(closes))]
        if returns:
            realized_volatility_20 = round(pstdev(returns), 6)
    return {
        "interval": canonical,
        "bar_count": len(rows),
        "coverage_days": coverage_days,
        "ready": coverage_days >= threshold_days,
        "last_open_time_utc": datetime.fromtimestamp(int(rows[-1]["open_time_ms"]) / 1000, tz=UTC).isoformat().replace("+00:00", "Z"),
        "last_close_time_utc": datetime.fromtimestamp(last_close_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z"),
        "last_close": row_float_string(rows[-1]["close"]),
        "distance_to_high_pct": distances_high,
        "distance_to_low_pct": distances_low,
        "relative_volume_20": relative_volume_20,
        "realized_volatility_20": realized_volatility_20,
    }


def _compute_breakout_samples(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    if len(rows) < 60:
        return []
    closes = [float(row["close"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    samples: list[dict[str, Any]] = []
    for index in range(21, len(rows) - 10):
        previous_high = max(closes[index - 20:index])
        previous_close = closes[index - 1]
        current_close = closes[index]
        if previous_close <= previous_high and current_close > previous_high:
            forward_slice = closes[index + 1:index + 6]
            drawdown_slice = lows[index + 1:index + 11]
            if not forward_slice or not drawdown_slice:
                continue
            forward_return = ((forward_slice[-1] / current_close) - 1.0) * 100
            max_drawdown = ((min(drawdown_slice) / current_close) - 1.0) * 100
            samples.append(
                {
                    "breakout_open_time_utc": datetime.fromtimestamp(
                        int(rows[index]["open_time_ms"]) / 1000,
                        tz=UTC,
                    ).isoformat().replace("+00:00", "Z"),
                    "forward_5d_return_pct": round(forward_return, 4),
                    "max_drawdown_10d_pct": round(max_drawdown, 4),
                }
            )
    samples.sort(key=lambda item: item["breakout_open_time_utc"], reverse=True)
    return samples[:3]


def _combine_market_status(*, interval_contexts: dict[str, dict[str, Any]]) -> str:
    if not interval_contexts:
        return "missing"
    ready_count = sum(1 for entry in interval_contexts.values() if entry["ready"])
    if ready_count == 0:
        return "missing"
    if ready_count == len(interval_contexts):
        return "full"
    return "partial"


def _extract_spot_symbols(exchange_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    symbols: dict[str, dict[str, Any]] = {}
    for item in exchange_info.get("symbols", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        quote_asset = str(item.get("quoteAsset", "")).strip().upper()
        status = str(item.get("status", "")).strip().upper()
        if not symbol or quote_asset != DEFAULT_QUOTE_ASSET or status != "TRADING":
            continue
        symbols[symbol] = {
            "symbol": symbol,
            "base_asset": str(item.get("baseAsset", "")).strip().upper(),
            "quote_asset": quote_asset,
            "status": status,
        }
    return symbols


def _extract_usdm_perp_symbols(exchange_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    symbols: dict[str, dict[str, Any]] = {}
    for item in exchange_info.get("symbols", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        quote_asset = str(item.get("quoteAsset", "")).strip().upper()
        status = str(item.get("status", "")).strip().upper()
        contract_type = str(item.get("contractType", "")).strip().upper()
        if not symbol or quote_asset != DEFAULT_QUOTE_ASSET or status != "TRADING" or contract_type != "PERPETUAL":
            continue
        symbols[symbol] = {
            "symbol": symbol,
            "base_asset": str(item.get("baseAsset", "")).strip().upper(),
            "quote_asset": quote_asset,
            "status": status,
            "contract_type": contract_type,
        }
    return symbols


def _resolve_market_symbol_candidate(
    *,
    market_symbols: dict[str, Any],
    explicit_symbol: str | None,
    inferred_symbol: str,
    market_type: str,
) -> str | None:
    if explicit_symbol:
        candidate = explicit_symbol.strip().upper()
        if candidate not in market_symbols:
            raise ValueError(f"{market_type} symbol is not present in Binance symbol catalog: {candidate}")
        return candidate
    if inferred_symbol in market_symbols:
        return inferred_symbol
    return None


def _overall_symbol_resolution_status(
    *,
    requires_spot: bool,
    requires_perp: bool,
    spot_symbol: str | None,
    usdm_symbol: str | None,
) -> str:
    required = []
    if requires_spot:
        required.append(bool(spot_symbol))
    if requires_perp:
        required.append(bool(usdm_symbol))
    if not required:
        return "missing"
    if all(required):
        return "full"
    if any(required):
        return "partial"
    return "missing"


def _market_symbol_pairs_from_mapping(mapping: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    spot_symbol = _optional_symbol(mapping.get("spot_symbol"))
    usdm_symbol = _optional_symbol(mapping.get("usdm_symbol"))
    if spot_symbol:
        pairs.append(("spot", spot_symbol))
    if usdm_symbol:
        pairs.append(("usdm_perp", usdm_symbol))
    return pairs


def _extract_market_pairs_from_payload(
    *,
    payload: dict[str, Any],
    symbol_catalog: dict[str, Any],
) -> list[tuple[str, str]]:
    market_symbols = payload.get("market_symbols")
    if isinstance(market_symbols, dict):
        return _market_symbol_pairs_from_mapping(market_symbols)
    subject = str(payload.get("subject", "")).strip()
    if not subject:
        return []
    try:
        mapping = resolve_market_symbols(
            subject=subject,
            scope=str(payload.get("scope", "spot+perp")).strip() or "spot+perp",
            symbol_catalog=symbol_catalog,
            spot_symbol=_optional_symbol(payload.get("spot_symbol")),
            usdm_symbol=_optional_symbol(payload.get("usdm_symbol")),
        )
    except Exception:
        return []
    return _market_symbol_pairs_from_mapping(mapping)


def _archive_month_url(*, market_type: str, symbol: str, interval: str, year: int, month: int) -> str:
    prefix = MARKET_ARCHIVE_PREFIXES[_require_market_type(market_type)]
    archive_interval = archive_interval_name(interval)
    return (
        f"{ARCHIVE_BASE_URL}/{prefix}/{symbol}/{archive_interval}/"
        f"{symbol}-{archive_interval}-{year:04d}-{month:02d}.zip"
    )


def _parse_archive_rows(
    *,
    archive_bytes: bytes,
    market_type: str,
    symbol: str,
    interval: str,
    source: str,
) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_handle:
        csv_names = [name for name in zip_handle.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            return []
        with zip_handle.open(csv_names[0], "r") as raw_handle:
            content = raw_handle.read().decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))
    rows: list[dict[str, str]] = []
    for item in reader:
        if not item:
            continue
        if not str(item[0]).strip().isdigit():
            continue
        rows.append(
            _normalize_kline_row(
                item=item,
                market_type=market_type,
                symbol=symbol,
                interval=interval,
                source=source,
            )
        )
    return rows


def _normalize_kline_row(
    *,
    item: list[Any],
    market_type: str,
    symbol: str,
    interval: str,
    source: str,
) -> dict[str, str]:
    return {
        "exchange": EXCHANGE,
        "market_type": market_type,
        "symbol": symbol,
        "interval": canonical_interval(interval),
        "open_time_ms": str(normalize_binance_epoch_to_ms(item[0])),
        "close_time_ms": str(normalize_binance_epoch_to_ms(item[6])),
        "open": str(item[1]),
        "high": str(item[2]),
        "low": str(item[3]),
        "close": str(item[4]),
        "volume": str(item[5]),
        "quote_volume": str(item[7]),
        "trade_count": str(item[8]),
        "taker_buy_base_volume": str(item[9]),
        "taker_buy_quote_volume": str(item[10]),
        "source": source,
    }


def _read_partition_rows(partition_path: Path) -> list[dict[str, str]]:
    if not partition_path.exists():
        return []
    with gzip.open(partition_path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_partition_rows(*, partition_path: Path, rows: list[dict[str, str]]) -> None:
    partition_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(partition_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _month_range(start_month: datetime, end_month_exclusive: datetime) -> Iterable[datetime]:
    current = datetime(start_month.year, start_month.month, 1, tzinfo=UTC)
    end = datetime(end_month_exclusive.year, end_month_exclusive.month, 1, tzinfo=UTC)
    while current < end:
        yield current
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=UTC)
        else:
            current = datetime(current.year, current.month + 1, 1, tzinfo=UTC)


def _require_market_type(value: str) -> str:
    market_type = str(value).strip()
    if market_type not in DEFAULT_MARKETS:
        raise ValueError(f"unsupported market_type: {value}")
    return market_type


def _optional_symbol(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def row_float_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return f"{float(value):.8f}"
    except (TypeError, ValueError):
        return str(value)
