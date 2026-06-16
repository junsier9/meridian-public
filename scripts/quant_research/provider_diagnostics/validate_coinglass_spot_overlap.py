from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path
import statistics
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_spot_ohlcv import (
    REPO_SUMMARY_PATH,
    resolve_external_history_root as resolve_coinglass_root,
    write_spot_backfill_summary_artifacts,
)
from enhengclaw.quant_research.contracts import utc_now


REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_spot_overlap_validation.md"
JSON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_overlap_validation.json"


def _default_binance_root() -> Path:
    import os

    localappdata = str(os.environ.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history" / "binance_ohlcv"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history" / "binance_ohlcv"


def _load_rows(root: Path, *, symbol: str, interval: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = root / "spot" / symbol / interval
    for partition in sorted(path.glob("*.csv.gz")):
        with gzip.open(partition, "rt", newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["open_time_ms"]))
    return rows


def validate_overlap(
    *,
    summary_path: Path,
    coinglass_root: Path | None = None,
    binance_root: Path | None = None,
    live_binance_check_fails: bool = False,
    live_binance_sample_count: int = 0,
) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    write_spot_backfill_summary_artifacts(summary)
    resolved_coinglass_root = coinglass_root or resolve_coinglass_root()
    resolved_binance_root = binance_root or _default_binance_root()
    results: list[dict[str, Any]] = []
    for symbol in summary.get("requested_symbols", []):
        cg_rows = _load_rows(resolved_coinglass_root, symbol=str(symbol), interval="1h")
        bn_rows = _load_rows(resolved_binance_root, symbol=str(symbol), interval="1h")
        bn_by_ts = {int(row["open_time_ms"]): row for row in bn_rows}
        diffs: list[float] = []
        rel_diffs: list[float] = []
        for row in cg_rows:
            ts = int(row["open_time_ms"])
            other = bn_by_ts.get(ts)
            if other is None:
                continue
            cg_close = float(row["close"])
            bn_close = float(other["close"])
            diff = abs(cg_close - bn_close)
            diffs.append(diff)
            rel_diffs.append(diff / max(abs(bn_close), 1e-12))
        if diffs:
            max_abs_diff = max(diffs)
            max_rel_diff = max(rel_diffs)
            median_rel_diff = statistics.median(rel_diffs)
            status = "pass" if max_rel_diff <= 0.001 else "fail"
        else:
            max_abs_diff = None
            max_rel_diff = None
            median_rel_diff = None
            status = "no_local_binance_overlap"
        live_checks: list[dict[str, Any]] = []
        if status == "fail" and live_binance_check_fails:
            live_checks = _live_binance_checks(symbol=str(symbol), coinglass_rows=cg_rows, binance_by_ts=bn_by_ts)
            if live_checks and all(item.get("status") == "pass" for item in live_checks):
                status = "local_binance_mismatch_live_binance_pass"
        elif live_binance_sample_count > 0:
            live_checks = _live_binance_sample_checks(
                symbol=str(symbol),
                coinglass_rows=cg_rows,
                sample_count=live_binance_sample_count,
            )
            if live_checks and all(item.get("status") == "pass" for item in live_checks) and status == "no_local_binance_overlap":
                status = "live_binance_sample_pass"
        results.append(
            {
                "symbol": symbol,
                "coinglass_row_count": len(cg_rows),
                "binance_row_count": len(bn_rows),
                "overlap_row_count": len(diffs),
                "max_abs_close_diff": max_abs_diff,
                "max_rel_close_diff": max_rel_diff,
                "median_rel_close_diff": median_rel_diff,
                "status": status,
                "live_binance_checks": live_checks,
            }
        )
    payload = {
        "generated_at_utc": utc_now(),
        "source_summary_path": str(summary_path),
        "coinglass_root": str(resolved_coinglass_root),
        "binance_root": str(resolved_binance_root),
        "symbol_count": len(results),
        "overlap_symbol_count": sum(1 for item in results if item["overlap_row_count"] > 0),
        "pass_symbol_count": sum(1 for item in results if item["status"] == "pass"),
        "fail_symbol_count": sum(1 for item in results if item["status"] == "fail"),
        "local_mismatch_live_pass_symbol_count": sum(
            1 for item in results if item["status"] == "local_binance_mismatch_live_binance_pass"
        ),
        "live_binance_sample_pass_symbol_count": sum(1 for item in results if item["status"] == "live_binance_sample_pass"),
        "no_overlap_symbol_count": sum(1 for item in results if item["status"] == "no_local_binance_overlap"),
        "material_rel_diff_threshold": 0.001,
        "alpha_interpretation_allowed": False,
        "results": results,
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.write_text(_render_report(payload), encoding="utf-8")
    return payload


def _live_binance_checks(
    *,
    symbol: str,
    coinglass_rows: list[dict[str, str]],
    binance_by_ts: dict[int, dict[str, str]],
) -> list[dict[str, Any]]:
    cg_by_ts = {int(row["open_time_ms"]): row for row in coinglass_rows}
    scored: list[tuple[float, int]] = []
    for ts, local_row in binance_by_ts.items():
        cg_row = cg_by_ts.get(ts)
        if cg_row is None:
            continue
        local_close = float(local_row["close"])
        cg_close = float(cg_row["close"])
        rel = abs(cg_close - local_close) / max(abs(local_close), 1e-12)
        scored.append((rel, ts))
    checks: list[dict[str, Any]] = []
    for _, ts in sorted(scored, reverse=True)[:3]:
        cg_close = float(cg_by_ts[ts]["close"])
        live_close = _fetch_binance_close(symbol=symbol, open_time_ms=ts)
        rel = None if live_close is None else abs(cg_close - live_close) / max(abs(live_close), 1e-12)
        checks.append(
            {
                "open_time_ms": ts,
                "coinglass_close": cg_close,
                "live_binance_close": live_close,
                "rel_diff": rel,
                "status": "pass" if rel is not None and rel <= 0.001 else "fail",
            }
        )
    return checks


def _live_binance_sample_checks(
    *,
    symbol: str,
    coinglass_rows: list[dict[str, str]],
    sample_count: int,
) -> list[dict[str, Any]]:
    if not coinglass_rows or sample_count <= 0:
        return []
    if sample_count == 1:
        indexes = [len(coinglass_rows) // 2]
    else:
        indexes = sorted({round(i * (len(coinglass_rows) - 1) / (sample_count - 1)) for i in range(sample_count)})
    checks: list[dict[str, Any]] = []
    for index in indexes:
        row = coinglass_rows[int(index)]
        ts = int(row["open_time_ms"])
        cg_close = float(row["close"])
        try:
            live_close = _fetch_binance_close(symbol=symbol, open_time_ms=ts)
        except Exception as exc:
            checks.append(
                {
                    "open_time_ms": ts,
                    "coinglass_close": cg_close,
                    "live_binance_close": None,
                    "rel_diff": None,
                    "status": "error",
                    "error": str(exc)[:200],
                }
            )
            continue
        rel = None if live_close is None else abs(cg_close - live_close) / max(abs(live_close), 1e-12)
        checks.append(
            {
                "open_time_ms": ts,
                "coinglass_close": cg_close,
                "live_binance_close": live_close,
                "rel_diff": rel,
                "status": "pass" if rel is not None and rel <= 0.001 else "fail",
            }
        )
    return checks


def _fetch_binance_close(*, symbol: str, open_time_ms: int) -> float | None:
    url = "https://api.binance.com/api/v3/klines?" + urlencode(
        {
            "symbol": symbol,
            "interval": "1h",
            "startTime": int(open_time_ms),
            "endTime": int(open_time_ms) + 3_600_000,
            "limit": 1,
        }
    )
    with urlopen(url, timeout=20.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        return None
    return float(payload[0][4])


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass Spot Overlap Validation",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        f"- overlap symbols: `{payload['overlap_symbol_count']}` / `{payload['symbol_count']}`",
        f"- pass symbols: `{payload['pass_symbol_count']}`",
        f"- fail symbols: `{payload['fail_symbol_count']}`",
        f"- local mismatch but live Binance pass symbols: `{payload['local_mismatch_live_pass_symbol_count']}`",
        f"- live Binance sample pass symbols: `{payload['live_binance_sample_pass_symbol_count']}`",
        f"- no local Binance overlap symbols: `{payload['no_overlap_symbol_count']}`",
        "- alpha interpretation: blocked; this is provider concordance evidence only.",
        "",
        "| symbol | cg rows | binance rows | overlap | max rel diff | median rel diff | status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload["results"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["symbol"]),
                    str(item["coinglass_row_count"]),
                    str(item["binance_row_count"]),
                    str(item["overlap_row_count"]),
                    "" if item["max_rel_close_diff"] is None else f"{float(item['max_rel_close_diff']):.8g}",
                    "" if item["median_rel_close_diff"] is None else f"{float(item['median_rel_close_diff']):.8g}",
                    str(item["status"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Stop Rule", "", "A full coverage reset still requires overlap for the remaining strategy-scope symbols via Binance or CoinAPI before alpha reruns.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate CoinGlass spot closes against local Binance spot history where available.")
    parser.add_argument("--summary-path", type=Path, default=Path(resolve_coinglass_root()) / "last_sync_summary.json")
    parser.add_argument("--coinglass-root", type=Path, default=None)
    parser.add_argument("--binance-root", type=Path, default=None)
    parser.add_argument("--live-binance-check-fails", action="store_true")
    parser.add_argument("--live-binance-sample-count", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_overlap(
        summary_path=args.summary_path,
        coinglass_root=args.coinglass_root,
        binance_root=args.binance_root,
        live_binance_check_fails=args.live_binance_check_fails,
        live_binance_sample_count=args.live_binance_sample_count,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["fail_symbol_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
