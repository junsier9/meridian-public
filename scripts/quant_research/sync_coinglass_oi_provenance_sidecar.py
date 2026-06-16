from __future__ import annotations

import argparse
import csv
from datetime import UTC, date, datetime
import gzip
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.quant_research.coinglass_derivatives import OPEN_INTEREST_HISTORY_URL, resolve_coinglass_api_key
from enhengclaw.quant_research.contracts import utc_now


UNIVERSE_PATH = ROOT / "artifacts" / "quant_research" / "_quant_inputs" / "pit-liquidity-top100-2026-05-04.quant_universe.json"
JSON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_oi_provenance_sidecar_sync_2026-05-04.json"
REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_oi_provenance_sidecar_sync_2026-05-04.md"
DEFAULT_EXCHANGE = "Binance"
MARKET_TYPE = "usdm_perp"
PROVIDER = "coinglass"
BINANCE_USDM_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
DAY_MS = 86_400_000
INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
FORMULA_REL_THRESHOLD = 0.01
CSV_HEADERS = (
    "exchange",
    "market_type",
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "open_interest_value",
    "open_interest_value_native_usd",
    "open_interest_coin",
    "binance_perp_close",
    "open_interest_value_derived_usd",
    "derived_native_rel_diff",
    "derived_native_formula_status",
    "oi_value_provenance",
    "price_source_for_derived_value",
    "source",
)


def resolve_external_root(external_root: Path | None = None) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    localappdata = str(os.environ.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history" / "coinglass_oi_provenance"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history" / "coinglass_oi_provenance"


def _as_of_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    as_of_end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 0, 0, tzinfo=UTC)
    return int(as_of_end.timestamp() * 1000)


def _utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _interval_to_ms(interval: str) -> int:
    try:
        return INTERVAL_MS[interval]
    except KeyError as exc:
        raise ValueError(f"unsupported interval for OI sidecar: {interval}") from exc


def _load_executable_symbols(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    symbols: list[str] = []
    for candidate in list(payload.get("candidates") or []):
        if not candidate.get("usdm_symbol") or not candidate.get("first_perp_bar_utc"):
            continue
        symbols.append(str(candidate["usdm_symbol"]).upper())
    return sorted(set(symbols))


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("unreachable CoinGlass request state")


def _fetch_oi_history(
    *,
    symbol: str,
    unit: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
) -> list[dict[str, Any]]:
    interval_ms = _interval_to_ms(interval)
    per_call_limit = 4500
    cur_end = end_time_ms
    rows: list[dict[str, Any]] = []
    for _ in range(64):
        if cur_end <= start_time_ms:
            break
        cur_start = max(start_time_ms, cur_end - per_call_limit * interval_ms * 2)
        params = {
            "exchange": DEFAULT_EXCHANGE,
            "symbol": symbol,
            "interval": interval,
            "unit": unit,
            "start_time": cur_start,
            "end_time": cur_end,
            "limit": per_call_limit,
        }
        try:
            payload = _http_get_json(f"{OPEN_INTEREST_HISTORY_URL}?{urlencode(params)}")
        except HTTPError as exc:
            if exc.code == 400:
                break
            raise
        data = [item for item in list(dict(payload or {}).get("data") or []) if isinstance(item, dict)]
        normalized: list[dict[str, Any]] = []
        for item in data:
            try:
                time_ms = int(item.get("time"))
                close_value = float(item.get("close"))
            except (TypeError, ValueError):
                continue
            if time_ms < start_time_ms or time_ms > cur_end:
                continue
            normalized.append({"time_ms": time_ms, "close": close_value})
        if not normalized:
            break
        normalized.sort(key=lambda item: int(item["time_ms"]))
        rows.extend(normalized)
        oldest_time = int(normalized[0]["time_ms"])
        if oldest_time <= start_time_ms or oldest_time >= cur_end:
            break
        cur_end = oldest_time - interval_ms
    deduped = {int(item["time_ms"]): item for item in rows}
    return [deduped[key] for key in sorted(deduped)]


def _fetch_binance_perp_closes(
    *,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
) -> dict[int, float]:
    interval_ms = _interval_to_ms(interval)
    cursor = start_time_ms
    closes: dict[int, float] = {}
    while cursor <= end_time_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_time_ms,
            "limit": 1000,
        }
        url = f"{BINANCE_USDM_KLINES_URL}?{urlencode(params)}"
        payload = None
        for attempt in range(3):
            try:
                with urlopen(url, timeout=30.0) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except (URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(1.0 + attempt)
                    continue
                raise
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            try:
                closes[int(item[0])] = float(item[4])
            except (TypeError, ValueError, IndexError):
                continue
        latest = int(payload[-1][0])
        next_cursor = latest + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(payload) < 1000:
            break
    return closes


def _month_partition_path(*, external_root: Path, symbol: str, interval: str, month_key: str) -> Path:
    return external_root / MARKET_TYPE / symbol / interval / f"{month_key}.csv.gz"


def _manifest_path(*, external_root: Path, symbol: str, interval: str) -> Path:
    return external_root / MARKET_TYPE / symbol / interval / "manifest.json"


def _month_key(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m")


def _read_partition(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_partition(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: str(row.get(key, "")) for key in CSV_HEADERS})


def _merge_rows(*, external_root: Path, symbol: str, interval: str, rows: Iterable[dict[str, str]]) -> None:
    by_month: dict[str, dict[int, dict[str, str]]] = {}
    for row in rows:
        ts = int(row["open_time_ms"])
        by_month.setdefault(_month_key(ts), {})[ts] = row
    for month_key, month_rows in by_month.items():
        path = _month_partition_path(external_root=external_root, symbol=symbol, interval=interval, month_key=month_key)
        merged: dict[int, dict[str, str]] = {}
        for existing in _read_partition(path):
            try:
                merged[int(existing["open_time_ms"])] = existing
            except (KeyError, TypeError, ValueError):
                continue
        merged.update(month_rows)
        _write_partition(path, [merged[key] for key in sorted(merged)])


def _build_sidecar_rows(
    *,
    symbol: str,
    interval: str,
    native_usd_rows: list[dict[str, Any]],
    coin_rows: list[dict[str, Any]],
    binance_closes: dict[int, float],
) -> list[dict[str, str]]:
    interval_ms = _interval_to_ms(interval)
    native_by_time = {int(item["time_ms"]): float(item["close"]) for item in native_usd_rows}
    coin_by_time = {int(item["time_ms"]): float(item["close"]) for item in coin_rows}
    times = sorted(set(native_by_time) | set(coin_by_time))
    rows: list[dict[str, str]] = []
    for ts in times:
        native_value = native_by_time.get(ts)
        coin_value = coin_by_time.get(ts)
        price = binance_closes.get(ts)
        derived_value = None if coin_value is None or price is None else coin_value * price
        rel_diff = (
            None
            if native_value is None or derived_value is None
            else abs(derived_value - native_value) / max(abs(native_value), 1e-12)
        )
        formula_status = ""
        if rel_diff is not None:
            formula_status = "pass" if rel_diff <= FORMULA_REL_THRESHOLD else "fail"
        if native_value is not None:
            selected_value = native_value
            provenance = "native_usd"
        elif derived_value is not None:
            selected_value = derived_value
            provenance = "derived_coin_x_binance_perp_close"
        else:
            selected_value = None
            provenance = "missing"
        rows.append(
            {
                "exchange": "binance",
                "market_type": MARKET_TYPE,
                "symbol": symbol,
                "interval": interval,
                "open_time_ms": str(ts),
                "close_time_ms": str(ts + interval_ms - 1),
                "open_interest_value": "" if selected_value is None else f"{selected_value:.10f}",
                "open_interest_value_native_usd": "" if native_value is None else f"{native_value:.10f}",
                "open_interest_coin": "" if coin_value is None else f"{coin_value:.10f}",
                "binance_perp_close": "" if price is None else f"{price:.10f}",
                "open_interest_value_derived_usd": "" if derived_value is None else f"{derived_value:.10f}",
                "derived_native_rel_diff": "" if rel_diff is None else f"{rel_diff:.10f}",
                "derived_native_formula_status": formula_status,
                "oi_value_provenance": provenance,
                "price_source_for_derived_value": "binance_usdm_perp_ohlcv" if price is not None else "",
                "source": "coinglass_open_interest_history",
            }
        )
    return rows


def _row_rel_diff(row: dict[str, str]) -> float | None:
    raw = row.get("derived_native_rel_diff")
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
    return values[index]


def sync_sidecar(
    *,
    as_of: str,
    universe_path: Path = UNIVERSE_PATH,
    interval: str = "1h",
    lookback_days: int = 180,
    external_root: Path | None = None,
    max_symbols: int | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_external_root(external_root)
    symbols = _load_executable_symbols(universe_path)
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    end_ms = _as_of_end_ms(as_of)
    start_ms = end_ms - lookback_days * DAY_MS
    sync_results: list[dict[str, Any]] = []
    for symbol in symbols:
        try:
            native_usd = _fetch_oi_history(symbol=symbol, unit="usd", interval=interval, start_time_ms=start_ms, end_time_ms=end_ms)
            coin = _fetch_oi_history(symbol=symbol, unit="coin", interval=interval, start_time_ms=start_ms, end_time_ms=end_ms)
            closes = _fetch_binance_perp_closes(symbol=symbol, interval=interval, start_time_ms=start_ms, end_time_ms=end_ms)
            rows = _build_sidecar_rows(
                symbol=symbol,
                interval=interval,
                native_usd_rows=native_usd,
                coin_rows=coin,
                binance_closes=closes,
            )
            if rows:
                _merge_rows(external_root=resolved_root, symbol=symbol, interval=interval, rows=rows)
            rel_diffs = [value for value in (_row_rel_diff(row) for row in rows) if value is not None]
            formula_fail_count = sum(1 for row in rows if row.get("derived_native_formula_status") == "fail")
            provenance_counts: dict[str, int] = {}
            for row in rows:
                key = str(row.get("oi_value_provenance") or "missing")
                provenance_counts[key] = provenance_counts.get(key, 0) + 1
            manifest = {
                "generated_at_utc": utc_now(),
                "provider": PROVIDER,
                "exchange": "binance",
                "market_type": MARKET_TYPE,
                "symbol": symbol,
                "interval": interval,
                "as_of": as_of,
                "lookback_days": lookback_days,
                "start_time_ms": start_ms,
                "end_time_ms": end_ms,
                "start_time_utc": _utc(start_ms),
                "end_time_utc": _utc(end_ms),
                "total_rows": len(rows),
                "native_usd_rows": len(native_usd),
                "coin_rows": len(coin),
                "binance_close_rows": len(closes),
                "provenance_counts": provenance_counts,
                "formula_threshold": FORMULA_REL_THRESHOLD,
                "formula_fail_count": formula_fail_count,
                "formula_max_rel_diff": max(rel_diffs, default=None),
                "formula_p95_rel_diff": _percentile(rel_diffs, 0.95),
                "formula_median_rel_diff": statistics.median(rel_diffs) if rel_diffs else None,
                "schema": list(CSV_HEADERS),
            }
            _manifest_path(external_root=resolved_root, symbol=symbol, interval=interval).write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            status = "success" if rows and len(native_usd) > 0 else "warning"
            if formula_fail_count:
                status = "formula_warning"
            sync_results.append({"symbol": symbol, "status": status, "manifest_path": str(_manifest_path(external_root=resolved_root, symbol=symbol, interval=interval)), **manifest})
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            sync_results.append({"symbol": symbol, "status": "error", "error": str(exc)[:300]})
    formula_fail_symbols = [item["symbol"] for item in sync_results if int(item.get("formula_fail_count") or 0) > 0]
    data_success_count = sum(1 for item in sync_results if item.get("status") in {"success", "formula_warning"})
    formula_clean_count = sum(1 for item in sync_results if item.get("status") == "success")
    payload = with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "artifact_family": "coinglass_oi_provenance_sidecar_sync",
            "as_of": as_of,
            "external_root": str(resolved_root),
            "universe_path": str(universe_path),
            "interval": interval,
            "lookback_days": lookback_days,
            "symbol_count": len(sync_results),
            "success_count": formula_clean_count,
            "data_success_count": data_success_count,
            "formula_clean_count": formula_clean_count,
            "formula_warning_count": sum(1 for item in sync_results if item.get("status") == "formula_warning"),
            "error_count": sum(1 for item in sync_results if item.get("status") == "error"),
            "formula_fail_symbols": formula_fail_symbols,
            "native_oi_policy": "prefer native USD OI for open_interest_value when available",
            "derived_oi_policy": "derive from coin OI only as fallback and only with binance_usdm_perp_ohlcv price source",
            "alpha_interpretation_allowed": False,
            "sync_results": sync_results,
        },
        evidence_family="coinglass_oi_provenance_sidecar_sync",
        contract_version="coinglass_oi_provenance_sidecar_sync.v1",
        repo_root=ROOT,
    )
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.write_text(_render_report(payload), encoding="utf-8")
    (resolved_root / "last_sync_summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass OI Provenance Sidecar Sync 2026-05-04",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Native OI policy: `{payload['native_oi_policy']}`.",
        f"- Derived OI policy: `{payload['derived_oi_policy']}`.",
        f"- Alpha interpretation allowed: `{payload['alpha_interpretation_allowed']}`.",
        f"- Data-written symbols: `{payload['data_success_count']}` / `{payload['symbol_count']}`.",
        f"- Formula-clean symbols: `{payload['formula_clean_count']}`.",
        f"- Formula warning symbols: `{payload['formula_warning_count']}`.",
        f"- Error symbols: `{payload['error_count']}`.",
        f"- Formula fail symbols: `{', '.join(payload['formula_fail_symbols']) if payload['formula_fail_symbols'] else 'none'}`.",
        "",
        "## Symbol Summary",
        "",
        "| symbol | status | rows | native rows | coin rows | formula fails | max rel diff | p95 rel diff | provenance |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload["sync_results"]:
        lines.append(
            f"| {item['symbol']} | {item.get('status')} | {item.get('total_rows', 0)} | {item.get('native_usd_rows', 0)} | "
            f"{item.get('coin_rows', 0)} | {item.get('formula_fail_count', 0)} | {item.get('formula_max_rel_diff')} | "
            f"{item.get('formula_p95_rel_diff')} | {item.get('provenance_counts', {})} |"
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            "Do not use derived OI value for symbols with formula warnings unless a symbol-level waiver explains the native/derived mismatch. Native USD OI remains the selected value whenever present.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync CoinGlass OI provenance sidecars for executable perps.")
    parser.add_argument("--as-of", default="2026-05-04")
    parser.add_argument("--universe-path", type=Path, default=UNIVERSE_PATH)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--max-symbols", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = sync_sidecar(
        as_of=args.as_of,
        universe_path=args.universe_path,
        interval=args.interval,
        lookback_days=args.lookback_days,
        external_root=args.external_root,
        max_symbols=args.max_symbols,
    )
    print(
        json.dumps(
            {
                "report": str(REPORT_PATH),
                "json": str(JSON_PATH),
                "external_root": payload["external_root"],
                "success_count": payload["success_count"],
                "data_success_count": payload["data_success_count"],
                "formula_clean_count": payload["formula_clean_count"],
                "formula_warning_count": payload["formula_warning_count"],
                "error_count": payload["error_count"],
                "formula_fail_symbols": payload["formula_fail_symbols"],
            },
            indent=2,
        )
    )
    return 0 if payload["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
