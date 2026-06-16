from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_spot_ohlcv import resolve_external_history_root as resolve_coinglass_root
from enhengclaw.quant_research.contracts import utc_now
from enhengclaw.utils.binance_http import binance_get_json
from scripts.market_data.binance_ohlcv import (
    REST_MAX_LIMIT,
    fetch_rest_klines,
    interval_to_ms,
    resolve_external_history_root as resolve_binance_root,
    _merge_rows_into_store,
)


JSON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "binance_spot_concordance_baseline_2026-05-04.json"
REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "binance_spot_concordance_baseline_2026-05-04.md"


def _load_coinglass_rows(root: Path, *, symbol: str, interval: str) -> list[dict[str, str]]:
    import csv
    import gzip

    rows: list[dict[str, str]] = []
    path = root / "spot" / symbol / interval
    for partition in sorted(path.glob("*.csv.gz")):
        with gzip.open(partition, "rt", newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["open_time_ms"]))
    return rows


def sync_baseline(
    *,
    summary_path: Path,
    coinglass_root: Path | None = None,
    binance_root: Path | None = None,
    interval: str = "1h",
    json_path: Path = JSON_PATH,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    resolved_coinglass_root = coinglass_root or resolve_coinglass_root()
    resolved_binance_root = binance_root or resolve_binance_root()
    interval_ms = interval_to_ms(interval)
    results: list[dict[str, Any]] = []
    for symbol in summary.get("requested_symbols", []):
        symbol = str(symbol)
        cg_rows = _load_coinglass_rows(resolved_coinglass_root, symbol=symbol, interval=interval)
        if not cg_rows:
            results.append({"symbol": symbol, "status": "missing_coinglass_rows", "fetched_row_count": 0})
            continue
        start_time_ms = int(cg_rows[0]["open_time_ms"])
        end_time_ms = int(cg_rows[-1]["open_time_ms"]) + interval_ms
        cursor = start_time_ms
        fetched: list[dict[str, str]] = []
        while cursor < end_time_ms:
            page = fetch_rest_klines(
                market_type="spot",
                symbol=symbol,
                interval=interval,
                start_time_ms=cursor,
                end_time_ms=end_time_ms,
                limit=REST_MAX_LIMIT["spot"],
                http_get_json_fn=lambda url: binance_get_json(url, timeout_seconds=30.0),
            )
            if not page:
                break
            fetched.extend(page)
            next_cursor = int(page[-1]["open_time_ms"]) + interval_ms
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(page) < REST_MAX_LIMIT["spot"]:
                break
        if fetched:
            _merge_rows_into_store(
                external_root=resolved_binance_root,
                market_type="spot",
                symbol=symbol,
                interval=interval,
                rows=fetched,
            )
        results.append(
            {
                "symbol": symbol,
                "status": "success" if fetched else "empty_binance_response",
                "coinglass_row_count": len(cg_rows),
                "fetched_row_count": len(fetched),
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            }
        )
    payload = {
        "generated_at_utc": utc_now(),
        "source_summary_path": str(summary_path),
        "coinglass_root": str(resolved_coinglass_root),
        "binance_root": str(resolved_binance_root),
        "interval": interval,
        "symbol_count": len(results),
        "success_count": sum(1 for item in results if item.get("status") == "success"),
        "empty_response_count": sum(1 for item in results if item.get("status") == "empty_binance_response"),
        "missing_coinglass_count": sum(1 for item in results if item.get("status") == "missing_coinglass_rows"),
        "results": results,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(_render_report(payload), encoding="utf-8")
    return payload


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Binance Spot Concordance Baseline",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        f"- symbols: `{payload['symbol_count']}`",
        f"- success: `{payload['success_count']}`",
        f"- empty Binance response: `{payload['empty_response_count']}`",
        f"- missing CoinGlass rows: `{payload['missing_coinglass_count']}`",
        "",
        "| symbol | status | cg rows | fetched rows |",
        "| --- | --- | ---: | ---: |",
    ]
    for item in payload["results"]:
        lines.append(
            f"| {item['symbol']} | {item['status']} | {item.get('coinglass_row_count', 0)} | {item.get('fetched_row_count', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Binance spot baseline over the CoinGlass concordance window.")
    parser.add_argument("--summary-path", type=Path, default=Path(resolve_coinglass_root()) / "last_sync_summary.json")
    parser.add_argument("--coinglass-root", type=Path, default=None)
    parser.add_argument("--binance-root", type=Path, default=None)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--json-out", type=Path, default=JSON_PATH)
    parser.add_argument("--report-out", type=Path, default=REPORT_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = sync_baseline(
        summary_path=args.summary_path,
        coinglass_root=args.coinglass_root,
        binance_root=args.binance_root,
        interval=args.interval,
        json_path=args.json_out,
        report_path=args.report_out,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["empty_response_count"] == 0 and payload["missing_coinglass_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
