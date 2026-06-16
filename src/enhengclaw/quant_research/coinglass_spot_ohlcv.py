from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import csv
import gzip
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from scripts.market_data.binance_ohlcv import CSV_HEADERS, interval_to_ms

from .contracts import QuantUniverseCandidate, QuantUniverseInput, read_json, utc_now
from .coinglass_derivatives import resolve_coinglass_api_key
from .runtime_support import QUANT_INPUT_ROOT, resolve_quant_input_path


ROOT = Path(__file__).resolve().parents[3]
PROVIDER = "coinglass"
EXCHANGE = "Binance"
MARKET_TYPE = "spot"
COINGLASS_SPOT_BASE_URL = "https://open-api-v4.coinglass.com/api/spot"
SPOT_PRICE_HISTORY_URL = f"{COINGLASS_SPOT_BASE_URL}/price/history"
DEFAULT_EXTERNAL_ROOT_NAME = "market_history\\coinglass_spot_ohlcv"
DEFAULT_INTERVALS = ("1h",)
DEFAULT_LOOKBACK_DAYS = {"1h": 180, "4h": 365, "1d": 700}
DEFAULT_LIMIT = 1000
TOP_MID_BUCKETS = {"top_liquidity", "mid_liquidity"}
ARTIFACT_FAMILY = "quant_coinglass_spot_sync"
CONTRACT_VERSION = "quant_coinglass_spot_sync.v1"
REPO_SUMMARY_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_backfill_summary.json"
REPO_REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_spot_backfill_summary.md"


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


def interval_root(*, external_root: Path, symbol: str, interval: str) -> Path:
    return external_root / MARKET_TYPE / symbol / interval


def interval_manifest_path(*, external_root: Path, symbol: str, interval: str) -> Path:
    return interval_root(external_root=external_root, symbol=symbol, interval=interval) / "manifest.json"


def month_partition_path(*, external_root: Path, symbol: str, interval: str, month_key: str) -> Path:
    return interval_root(external_root=external_root, symbol=symbol, interval=interval) / f"{month_key}.csv.gz"


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _float_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.10f}"


def _read_partition_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_partition_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_HEADERS))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: str(row.get(key, "")) for key in CSV_HEADERS})


def load_spot_rows(*, external_root: Path, symbol: str, interval: str) -> list[dict[str, str]]:
    root = interval_root(external_root=external_root, symbol=symbol, interval=interval)
    rows: list[dict[str, str]] = []
    for path in sorted(root.glob("*.csv.gz")):
        rows.extend(_read_partition_rows(path))
    rows.sort(key=lambda row: int(row["open_time_ms"]))
    return rows


def _merge_rows_into_store(*, external_root: Path, symbol: str, interval: str, rows: Iterable[dict[str, str]]) -> None:
    by_month: dict[str, dict[int, dict[str, str]]] = {}
    for row in rows:
        try:
            open_time_ms = int(row["open_time_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        month_key = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC).strftime("%Y-%m")
        by_month.setdefault(month_key, {})[open_time_ms] = row
    for month_key, month_rows in by_month.items():
        partition = month_partition_path(external_root=external_root, symbol=symbol, interval=interval, month_key=month_key)
        merged: dict[int, dict[str, str]] = {}
        for row in _read_partition_rows(partition):
            try:
                merged[int(row["open_time_ms"])] = row
            except (KeyError, TypeError, ValueError):
                continue
        merged.update(month_rows)
        _write_partition_rows(partition, [merged[key] for key in sorted(merged)])


def _normalize_ohlcv_row(*, item: dict[str, Any], symbol: str, interval: str) -> dict[str, str]:
    open_time_ms = int(item["time"])
    close_time_ms = open_time_ms + interval_to_ms(interval) - 1
    return {
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "symbol": symbol,
        "interval": interval,
        "open_time_ms": str(open_time_ms),
        "close_time_ms": str(close_time_ms),
        "open": _float_text(item.get("open")),
        "high": _float_text(item.get("high")),
        "low": _float_text(item.get("low")),
        "close": _float_text(item.get("close")),
        "volume": "",
        "quote_volume": _float_text(item.get("volume_usd")),
        "trade_count": "",
        "taker_buy_base_volume": "",
        "taker_buy_quote_volume": "",
        "source": "coinglass_spot_price_history",
    }


def _fetch_price_history(
    *,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    http_get_json_fn: Callable[[str], Any],
) -> list[dict[str, str]]:
    interval_ms = interval_to_ms(interval)
    cur_start = int(start_time_ms)
    rows: list[dict[str, str]] = []
    max_pages = 512
    for _ in range(max_pages):
        if cur_start >= end_time_ms:
            break
        params = {
            "exchange": EXCHANGE,
            "symbol": symbol,
            "interval": interval,
            "limit": DEFAULT_LIMIT,
            "start_time": cur_start,
            "end_time": end_time_ms,
        }
        try:
            payload = http_get_json_fn(f"{SPOT_PRICE_HISTORY_URL}?{urlencode(params)}")
        except HTTPError as exc:
            if exc.code == 400:
                break
            raise
        data = list(dict(payload or {}).get("data") or [])
        page_rows: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict) or item.get("time") is None:
                continue
            try:
                time_ms = int(item["time"])
            except (TypeError, ValueError):
                continue
            if time_ms < start_time_ms or time_ms >= end_time_ms:
                continue
            page_rows.append(_normalize_ohlcv_row(item=dict(item), symbol=symbol, interval=interval))
        if not page_rows:
            break
        page_rows.sort(key=lambda row: int(row["open_time_ms"]))
        rows.extend(page_rows)
        next_start = int(page_rows[-1]["open_time_ms"]) + interval_ms
        if next_start <= cur_start:
            break
        cur_start = next_start
        if len(page_rows) < DEFAULT_LIMIT:
            break
    deduped: dict[int, dict[str, str]] = {}
    for row in rows:
        deduped[int(row["open_time_ms"])] = row
    return [deduped[key] for key in sorted(deduped)]


def _rebuild_manifest(
    *,
    external_root: Path,
    symbol: str,
    interval: str,
    requested_window: dict[str, Any],
) -> dict[str, Any]:
    rows = load_spot_rows(external_root=external_root, symbol=symbol, interval=interval)
    expected_rows = _expected_row_count(requested_window=requested_window, interval=interval)
    duplicate_count = max(0, len(rows) - len({int(row["open_time_ms"]) for row in rows}))
    gap_count = _gap_count(rows=rows, interval=interval)
    observed_rows = [
        row
        for row in rows
        if int(requested_window["start_time_ms"]) <= int(row["open_time_ms"]) < int(requested_window["end_time_ms"])
    ]
    observed_expected_rows = _expected_row_count(requested_window=requested_window, interval=interval)
    observed_completeness = (len(observed_rows) / observed_expected_rows) if observed_expected_rows else 0.0
    min_open_time_ms = int(rows[0]["open_time_ms"]) if rows else None
    max_close_time_ms = int(rows[-1]["close_time_ms"]) if rows else None
    manifest = {
        "generated_at_utc": _utc_now(),
        "provider": PROVIDER,
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "symbol": symbol,
        "interval": interval,
        "source": "coinglass_spot_price_history",
        "total_rows": len(rows),
        "requested_window": requested_window,
        "requested_expected_rows": expected_rows,
        "requested_observed_rows": len(observed_rows),
        "requested_completeness": round(observed_completeness, 6),
        "duplicate_open_time_count": duplicate_count,
        "gap_count": gap_count,
        "min_open_time_ms": min_open_time_ms,
        "max_close_time_ms": max_close_time_ms,
        "min_open_time_utc": _ms_to_utc(min_open_time_ms),
        "max_close_time_utc": _ms_to_utc(max_close_time_ms),
        "partitions": [path.name for path in sorted(interval_root(external_root=external_root, symbol=symbol, interval=interval).glob("*.csv.gz"))],
        "schema_mapping": {
            "quote_volume": "volume_usd",
            "volume": None,
            "trade_count": None,
            "taker_buy_base_volume": None,
            "taker_buy_quote_volume": None,
        },
    }
    interval_manifest_path(external_root=external_root, symbol=symbol, interval=interval).write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def _expected_row_count(*, requested_window: dict[str, Any], interval: str) -> int:
    start_ms = int(requested_window["start_time_ms"])
    end_ms = int(requested_window["end_time_ms"])
    return max(0, (end_ms - start_ms) // interval_to_ms(interval))


def _gap_count(*, rows: list[dict[str, str]], interval: str) -> int:
    if len(rows) < 2:
        return 0
    interval_ms = interval_to_ms(interval)
    gaps = 0
    prev = int(rows[0]["open_time_ms"])
    for row in rows[1:]:
        cur = int(row["open_time_ms"])
        if cur - prev != interval_ms:
            gaps += 1
        prev = cur
    return gaps


def _ms_to_utc(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _window_for_as_of(*, as_of: str, lookback_days: int, interval: str) -> dict[str, Any]:
    as_of_date = date.fromisoformat(as_of)
    end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC) + timedelta(days=1)
    start = end - timedelta(days=max(int(lookback_days), 1))
    interval_ms = interval_to_ms(interval)
    start_ms = (int(start.timestamp() * 1000) // interval_ms) * interval_ms
    end_ms = (int(end.timestamp() * 1000) // interval_ms) * interval_ms
    return {
        "start_time_ms": start_ms,
        "end_time_ms": end_ms,
        "start_time_utc": _ms_to_utc(start_ms),
        "end_time_utc": _ms_to_utc(end_ms),
        "lookback_days": lookback_days,
    }


def _selected_strategy_candidates(quant_input: QuantUniverseInput, *, max_symbols: int | None) -> tuple[QuantUniverseCandidate, ...]:
    candidates = [
        candidate
        for candidate in quant_input.selected_candidates()
        if candidate.liquidity_bucket in TOP_MID_BUCKETS and candidate.has_perp_as_of and not candidate.is_stablecoin and not candidate.is_pegged_asset
    ]
    if max_symbols is not None:
        candidates = candidates[: max(int(max_symbols), 0)]
    return tuple(candidates)


def sync_coinglass_spot_ohlcv(
    *,
    as_of: str,
    intervals: Iterable[str] = DEFAULT_INTERVALS,
    mode: str = "bootstrap",
    quant_input_root: Path | None = None,
    external_root: Path | None = None,
    lookback_days: int | None = None,
    max_symbols: int | None = None,
    symbols: Iterable[str] | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
    write_repo_artifacts: bool = True,
) -> dict[str, Any]:
    if mode not in {"bootstrap", "refresh"}:
        raise ValueError("mode must be one of: bootstrap, refresh")
    resolved_root = resolve_external_history_root(external_root=external_root)
    resolved_intervals = tuple(str(item).strip() for item in intervals if str(item).strip())
    for interval in resolved_intervals:
        interval_to_ms(interval)
    quant_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=(quant_input_root or QUANT_INPUT_ROOT))
    quant_input = QuantUniverseInput.from_payload(read_json(quant_input_path))
    explicit_symbols = sorted({str(item).strip().upper() for item in (symbols or []) if str(item).strip()})
    if explicit_symbols:
        candidates = tuple(candidate for candidate in quant_input.selected_candidates() if candidate.spot_symbol in explicit_symbols)
    else:
        candidates = _selected_strategy_candidates(quant_input, max_symbols=max_symbols)
    if not candidates:
        raise ValueError("no CoinGlass spot candidates selected")
    http_get = http_get_json_fn or _http_get_json
    sync_results: list[dict[str, Any]] = []
    for candidate in candidates:
        for interval in resolved_intervals:
            resolved_lookback = int(lookback_days or DEFAULT_LOOKBACK_DAYS.get(interval, 180))
            requested_window = _window_for_as_of(as_of=as_of, lookback_days=min(resolved_lookback, candidate.listing_age_days), interval=interval)
            try:
                rows = _fetch_price_history(
                    symbol=candidate.spot_symbol,
                    interval=interval,
                    start_time_ms=int(requested_window["start_time_ms"]),
                    end_time_ms=int(requested_window["end_time_ms"]),
                    http_get_json_fn=http_get,
                )
                if rows:
                    _merge_rows_into_store(external_root=resolved_root, symbol=candidate.spot_symbol, interval=interval, rows=rows)
                manifest = _rebuild_manifest(
                    external_root=resolved_root,
                    symbol=candidate.spot_symbol,
                    interval=interval,
                    requested_window=requested_window,
                )
                status = "success" if float(manifest["requested_completeness"]) >= 0.95 and int(manifest["duplicate_open_time_count"]) == 0 else "warning"
                sync_results.append(
                    {
                        "status": status,
                        "symbol": candidate.spot_symbol,
                        "subject": candidate.subject,
                        "interval": interval,
                        "liquidity_bucket": candidate.liquidity_bucket,
                        "fetched_row_count": len(rows),
                        "requested_observed_rows": manifest["requested_observed_rows"],
                        "requested_expected_rows": manifest["requested_expected_rows"],
                        "requested_completeness": manifest["requested_completeness"],
                        "duplicate_open_time_count": manifest["duplicate_open_time_count"],
                        "gap_count": manifest["gap_count"],
                        "manifest_path": str(interval_manifest_path(external_root=resolved_root, symbol=candidate.spot_symbol, interval=interval)),
                    }
                )
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
                sync_results.append(
                    {
                        "status": "error",
                        "symbol": candidate.spot_symbol,
                        "subject": candidate.subject,
                        "interval": interval,
                        "liquidity_bucket": candidate.liquidity_bucket,
                        "error": str(exc)[:300],
                    }
                )
    summary = _build_summary(
        as_of=as_of,
        quant_input_path=quant_input_path,
        external_root=resolved_root,
        intervals=resolved_intervals,
        candidates=candidates,
        sync_results=sync_results,
        mode=mode,
    )
    summary_path = resolved_root / "last_sync_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if write_repo_artifacts:
        write_spot_backfill_summary_artifacts(summary)
    return summary


def write_spot_backfill_summary_artifacts(summary: dict[str, Any]) -> tuple[Path, Path]:
    REPO_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPO_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPO_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    REPO_REPORT_PATH.write_text(_render_spot_backfill_report(summary), encoding="utf-8")
    return REPO_SUMMARY_PATH, REPO_REPORT_PATH


def _render_spot_backfill_report(summary: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass Spot Backfill Summary",
        "",
        f"`Generated at UTC: {summary.get('generated_at_utc')}`",
        "",
        "## Scope",
        "",
        f"- as_of: `{summary.get('as_of')}`",
        f"- provider: `{summary.get('provider')}`",
        f"- source: `{summary.get('source')}`",
        f"- intervals: `{','.join(str(item) for item in summary.get('intervals', []))}`",
        f"- requested symbols: `{summary.get('requested_symbol_count')}`",
        f"- external root: `{summary.get('external_root')}`",
        "",
        "## Gates",
        "",
        f"- status: `{summary.get('status')}`",
        f"- success_count: `{summary.get('success_count')}`",
        f"- warning_count: `{summary.get('warning_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- min_requested_completeness: `{summary.get('min_requested_completeness')}`",
        "- alpha interpretation: blocked; this artifact is data-readiness evidence only.",
        "",
        "## Symbol Coverage",
        "",
        "| symbol | bucket | expected | observed | completeness | gaps | duplicates | status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary.get("sync_results", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("symbol")),
                    str(item.get("liquidity_bucket")),
                    str(item.get("requested_expected_rows")),
                    str(item.get("requested_observed_rows")),
                    str(item.get("requested_completeness")),
                    str(item.get("gap_count")),
                    str(item.get("duplicate_open_time_count")),
                    str(item.get("status")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Stop Rule", "", "Do not promote alpha from this coverage artifact. Run provider overlap, dataset rebuild, and falsification gates first.", ""])
    return "\n".join(lines)


def _build_summary(
    *,
    as_of: str,
    quant_input_path: Path,
    external_root: Path,
    intervals: tuple[str, ...],
    candidates: tuple[QuantUniverseCandidate, ...],
    sync_results: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    warning_count = sum(1 for item in sync_results if item.get("status") == "warning")
    error_count = sum(1 for item in sync_results if item.get("status") == "error")
    min_completeness = min(
        (float(item.get("requested_completeness", 0.0) or 0.0) for item in sync_results if item.get("status") != "error"),
        default=0.0,
    )
    payload = {
        "status": "success" if error_count == 0 and warning_count == 0 else ("partial" if error_count else "warning"),
        "success": error_count == 0,
        "generated_at_utc": utc_now(),
        "provider": PROVIDER,
        "source": "coinglass_spot_price_history",
        "as_of": as_of,
        "mode": mode,
        "quant_input_path": str(quant_input_path),
        "external_root": str(external_root),
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "intervals": list(intervals),
        "requested_symbol_count": len(candidates),
        "requested_symbols": [candidate.spot_symbol for candidate in candidates],
        "success_count": sum(1 for item in sync_results if item.get("status") == "success"),
        "warning_count": warning_count,
        "error_count": error_count,
        "min_requested_completeness": round(min_completeness, 6),
        "sync_results": sync_results,
        "validation_gates": {
            "minimum_requested_completeness": 0.95,
            "duplicate_open_time_count": 0,
            "missing_quote_volume_policy": "quote_volume maps to CoinGlass volume_usd; base volume remains null.",
            "alpha_interpretation_allowed": False,
        },
        "input_watermarks": {
            "candidate_count": len(candidates),
            "top_mid_executable_perp_symbol_count": len(candidates),
        },
        "upstream_versions": {
            "api_base_url": COINGLASS_SPOT_BASE_URL,
            "contract_version": CONTRACT_VERSION,
        },
    }
    return with_evidence_metadata(
        payload,
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
    )
