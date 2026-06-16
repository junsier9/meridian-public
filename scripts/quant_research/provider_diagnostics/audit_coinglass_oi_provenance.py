from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_derivatives import OPEN_INTEREST_HISTORY_URL, resolve_coinglass_api_key
from enhengclaw.quant_research.contracts import utc_now


UNIVERSE_PATH = ROOT / "artifacts" / "quant_research" / "_quant_inputs" / "pit-liquidity-top100-2026-05-04.quant_universe.json"
JSON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_oi_provenance_audit_2026-05-04.json"
REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_oi_provenance_audit_2026-05-04.md"
DEFAULT_EXCHANGE = "Binance"
BINANCE_USDM_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
FORMULA_REL_THRESHOLD = 0.01


def _as_of_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    as_of_end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 0, 0, tzinfo=UTC)
    return int(as_of_end.timestamp() * 1000)


def _utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


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
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_oi(
    *,
    symbol: str,
    unit: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int,
) -> dict[str, Any]:
    params = {
        "exchange": DEFAULT_EXCHANGE,
        "symbol": symbol,
        "interval": interval,
        "unit": unit,
        "start_time": start_time_ms,
        "end_time": end_time_ms,
        "limit": limit,
    }
    url = f"{OPEN_INTEREST_HISTORY_URL}?{urlencode(params)}"
    try:
        payload = _http_get_json(url)
    except HTTPError as exc:
        return {"status": "http_error", "error": f"HTTP {exc.code}", "rows": []}
    except (URLError, TimeoutError, RuntimeError, ValueError) as exc:
        return {"status": "error", "error": str(exc)[:240], "rows": []}
    data = [item for item in list(dict(payload or {}).get("data") or []) if isinstance(item, dict)]
    normalized: list[dict[str, Any]] = []
    for item in data:
        try:
            time_ms = int(item.get("time"))
        except (TypeError, ValueError):
            continue
        close = item.get("close")
        try:
            close_value = None if close in (None, "") else float(close)
        except (TypeError, ValueError):
            close_value = None
        normalized.append(
            {
                "time_ms": time_ms,
                "time_utc": _utc(time_ms),
                "close": close_value,
                "observed_keys": sorted(str(key) for key in item.keys()),
            }
        )
    normalized.sort(key=lambda item: int(item["time_ms"]))
    return {
        "status": "success",
        "rows": normalized,
        "row_count": len(normalized),
        "first_time_ms": normalized[0]["time_ms"] if normalized else None,
        "last_time_ms": normalized[-1]["time_ms"] if normalized else None,
        "first_time_utc": _utc(normalized[0]["time_ms"]) if normalized else None,
        "last_time_utc": _utc(normalized[-1]["time_ms"]) if normalized else None,
        "positive_close_count": sum(1 for item in normalized if (item.get("close") or 0.0) > 0.0),
        "observed_keys": sorted({key for item in normalized for key in item.get("observed_keys", [])}),
        "sample": normalized[:1] + normalized[-1:] if len(normalized) > 1 else normalized,
    }


def _fetch_binance_perp_closes(*, symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> dict[int, float]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": 1000,
    }
    url = f"{BINANCE_USDM_KLINES_URL}?{urlencode(params)}"
    with urlopen(url, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    closes: dict[int, float] = {}
    for item in list(payload or []):
        try:
            closes[int(item[0])] = float(item[4])
        except (TypeError, ValueError, IndexError):
            continue
    return closes


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
    return values[index]


def _formula_check(
    *,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    usd_rows: list[dict[str, Any]],
    coin_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not usd_rows or not coin_rows:
        return {"status": "no_overlap", "overlap_count": 0, "threshold": FORMULA_REL_THRESHOLD}
    coin_by_time = {int(item["time_ms"]): item for item in coin_rows if item.get("close") is not None}
    try:
        closes = _fetch_binance_perp_closes(
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:240], "overlap_count": 0, "threshold": FORMULA_REL_THRESHOLD}
    rel_diffs: list[float] = []
    examples: list[dict[str, Any]] = []
    for usd_row in usd_rows:
        ts = int(usd_row["time_ms"])
        native_value = usd_row.get("close")
        coin_row = coin_by_time.get(ts)
        price = closes.get(ts)
        if native_value is None or coin_row is None or coin_row.get("close") is None or price is None:
            continue
        derived_value = float(coin_row["close"]) * float(price)
        rel = abs(derived_value - float(native_value)) / max(abs(float(native_value)), 1e-12)
        rel_diffs.append(rel)
        if len(examples) < 8:
            examples.append(
                {
                    "time_ms": ts,
                    "time_utc": _utc(ts),
                    "native_usd_oi": native_value,
                    "coin_oi": coin_row["close"],
                    "binance_perp_close": price,
                    "derived_usd_oi": derived_value,
                    "rel_diff": rel,
                }
            )
    max_rel = max(rel_diffs, default=None)
    return {
        "status": "pass" if max_rel is not None and max_rel <= FORMULA_REL_THRESHOLD else "fail",
        "threshold": FORMULA_REL_THRESHOLD,
        "overlap_count": len(rel_diffs),
        "max_rel_diff": max_rel,
        "median_rel_diff": _percentile(rel_diffs, 0.5),
        "p95_rel_diff": _percentile(rel_diffs, 0.95),
        "examples": sorted(examples, key=lambda item: float(item["rel_diff"]), reverse=True)[:5],
    }


def build_audit(
    *,
    as_of: str,
    universe_path: Path = UNIVERSE_PATH,
    interval: str = "1h",
    lookback_hours: int = 48,
    limit: int = 200,
    max_symbols: int | None = None,
) -> dict[str, Any]:
    symbols = _load_executable_symbols(universe_path)
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    end_ms = _as_of_end_ms(as_of)
    start_ms = int((datetime.fromtimestamp(end_ms / 1000, tz=UTC) - timedelta(hours=lookback_hours)).timestamp() * 1000)
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        usd = _fetch_oi(symbol=symbol, unit="usd", interval=interval, start_time_ms=start_ms, end_time_ms=end_ms, limit=limit)
        coin = _fetch_oi(symbol=symbol, unit="coin", interval=interval, start_time_ms=start_ms, end_time_ms=end_ms, limit=limit)
        usd_raw_rows = list(usd.pop("rows", []) or [])
        coin_raw_rows = list(coin.pop("rows", []) or [])
        usd_rows = int(usd.get("row_count") or 0)
        coin_rows = int(coin.get("row_count") or 0)
        if usd_rows > 0:
            status = "native_usd_preferred"
        elif coin_rows > 0:
            status = "derived_usd_required"
        else:
            status = "missing_oi"
        overlap_count = 0
        if usd.get("sample") is not None and coin.get("sample") is not None:
            # Use full time bounds as an availability overlap proxy; the audit is not
            # intended to compare value formulas yet.
            usd_times = {item["time_ms"] for item in usd.get("sample", [])}
            coin_times = {item["time_ms"] for item in coin.get("sample", [])}
            overlap_count = len(usd_times & coin_times)
        formula = _formula_check(
            symbol=symbol,
            interval=interval,
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            usd_rows=usd_raw_rows,
            coin_rows=coin_raw_rows,
        )
        results.append(
            {
                "symbol": symbol,
                "oi_provenance_status": status,
                "native_usd": usd,
                "coin_unit": coin,
                "sample_time_overlap_count": overlap_count,
                "derived_native_formula_check": formula,
                "preferred_oi_value_source": "coinglass_native_usd_oi" if usd_rows > 0 else "derived_from_coin_oi",
                "derived_price_source_required": "binance_usdm_perp_ohlcv",
                "coinglass_price_allowed_for_derivation": False,
            }
        )
    counts: dict[str, int] = {}
    formula_counts: dict[str, int] = {}
    for item in results:
        counts[item["oi_provenance_status"]] = counts.get(item["oi_provenance_status"], 0) + 1
        formula_status = str((item.get("derived_native_formula_check") or {}).get("status") or "unknown")
        formula_counts[formula_status] = formula_counts.get(formula_status, 0) + 1
    payload = {
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "universe_path": str(universe_path),
        "interval": interval,
        "lookback_hours": lookback_hours,
        "start_time_ms": start_ms,
        "end_time_ms": end_ms,
        "start_time_utc": _utc(start_ms),
        "end_time_utc": _utc(end_ms),
        "symbol_count": len(results),
        "provenance_counts": counts,
        "derived_native_formula_counts": formula_counts,
        "canonical_price_source_for_derivation": "binance_usdm_perp_ohlcv",
        "native_oi_policy": "prefer_coinglass_native_usd_oi_when_present",
        "derived_oi_policy": "derive_usd_value_from_coin_oi_only_with_binance_perp_close_and_provenance_flag",
        "alpha_interpretation_allowed": False,
        "results": results,
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.write_text(_render_report(payload), encoding="utf-8")
    return payload


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass OI Provenance Audit 2026-05-04",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Native OI policy: `{payload['native_oi_policy']}`.",
        f"- Derived OI policy: `{payload['derived_oi_policy']}`.",
        f"- Canonical price source for derivation: `{payload['canonical_price_source_for_derivation']}`.",
        f"- Alpha interpretation allowed: `{payload['alpha_interpretation_allowed']}`.",
        f"- Provenance counts: `{payload['provenance_counts']}`.",
        f"- Derived/native formula counts: `{payload['derived_native_formula_counts']}`.",
        "",
        "This audit checks availability/provenance plus a 48h derived/native formula sanity check. It does not promote OI factors or validate full-horizon formula error.",
        "",
        "## Symbol Audit",
        "",
        "| symbol | status | native usd rows | coin rows | formula status | formula max rel | native keys | coin keys |",
        "| --- | --- | ---: | ---: | --- | ---: | --- | --- |",
    ]
    for item in payload["results"]:
        usd = dict(item.get("native_usd") or {})
        coin = dict(item.get("coin_unit") or {})
        lines.append(
            f"| {item['symbol']} | {item['oi_provenance_status']} | {usd.get('row_count', 0)} | {coin.get('row_count', 0)} | "
            f"{(item.get('derived_native_formula_check') or {}).get('status')} | "
            f"{(item.get('derived_native_formula_check') or {}).get('max_rel_diff')} | "
            f"{','.join(usd.get('observed_keys') or [])} | {','.join(coin.get('observed_keys') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            "CG-2 remains incomplete until native USD OI and coin OI are synced into versioned sidecars with explicit `oi_value_provenance`, and derived USD OI formula checks pass over the target historical horizon.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit CoinGlass futures OI native-vs-derived provenance for executable perps.")
    parser.add_argument("--as-of", default="2026-05-04")
    parser.add_argument("--universe-path", type=Path, default=UNIVERSE_PATH)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-symbols", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_audit(
        as_of=args.as_of,
        universe_path=args.universe_path,
        interval=args.interval,
        lookback_hours=args.lookback_hours,
        limit=args.limit,
        max_symbols=args.max_symbols,
    )
    print(
        json.dumps(
            {
                "report": str(REPORT_PATH),
                "json": str(JSON_PATH),
                "provenance_counts": payload["provenance_counts"],
                "derived_native_formula_counts": payload["derived_native_formula_counts"],
            },
            indent=2,
        )
    )
    return 0 if payload["provenance_counts"].get("missing_oi", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
