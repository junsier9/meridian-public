from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path
import statistics
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_spot_ohlcv import resolve_external_history_root as resolve_coinglass_root
from enhengclaw.quant_research.contracts import utc_now
from scripts.market_data.binance_ohlcv import interval_to_ms, resolve_external_history_root as resolve_binance_root


JSON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_strict_concordance_2026-05-04.json"
REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_spot_strict_concordance_2026-05-04.md"
OHLC_FIELDS = ("open", "high", "low", "close")
DEFAULT_WATCHLIST = ("SYRUPUSDT", "SUNUSDT", "LUNCUSDT", "WIFUSDT")


def _load_rows(root: Path, *, symbol: str, interval: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = root / "spot" / symbol / interval
    for partition in sorted(path.glob("*.csv.gz")):
        with gzip.open(partition, "rt", newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["open_time_ms"]))
    return rows


def _rel_diff(left: float, right: float) -> float:
    return abs(left - right) / max(abs(right), 1e-12)


def _utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def validate_strict_concordance(
    *,
    summary_path: Path,
    coinglass_root: Path | None = None,
    binance_root: Path | None = None,
    interval: str = "1h",
    exclude_tail_hours: int = 24,
    rel_threshold: float = 0.001,
    watchlist: tuple[str, ...] = DEFAULT_WATCHLIST,
) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    resolved_coinglass_root = coinglass_root or resolve_coinglass_root()
    resolved_binance_root = binance_root or resolve_binance_root()
    interval_ms = interval_to_ms(interval)
    tail_cutoff_delta = int(exclude_tail_hours * 3_600_000)
    results: list[dict[str, Any]] = []
    for symbol in summary.get("requested_symbols", []):
        symbol = str(symbol)
        cg_rows = _load_rows(resolved_coinglass_root, symbol=symbol, interval=interval)
        bn_rows = _load_rows(resolved_binance_root, symbol=symbol, interval=interval)
        if cg_rows:
            max_cg_open_time = max(int(row["open_time_ms"]) for row in cg_rows)
            cutoff_open_time = max_cg_open_time - tail_cutoff_delta
        else:
            max_cg_open_time = None
            cutoff_open_time = None
        bn_by_ts = {int(row["open_time_ms"]): row for row in bn_rows}
        comparable_rows = 0
        missing_binance_rows = 0
        field_stats: dict[str, dict[str, Any]] = {}
        material_examples: list[dict[str, Any]] = []
        for field in OHLC_FIELDS:
            field_stats[field] = {
                "max_abs_diff": None,
                "max_rel_diff": None,
                "median_rel_diff": None,
                "material_diff_count": 0,
            }
        rels_by_field: dict[str, list[float]] = {field: [] for field in OHLC_FIELDS}
        abs_by_field: dict[str, list[float]] = {field: [] for field in OHLC_FIELDS}
        for row in cg_rows:
            ts = int(row["open_time_ms"])
            if cutoff_open_time is not None and ts > cutoff_open_time:
                continue
            other = bn_by_ts.get(ts)
            if other is None:
                missing_binance_rows += 1
                continue
            comparable_rows += 1
            for field in OHLC_FIELDS:
                cg_value = float(row[field])
                bn_value = float(other[field])
                abs_diff = abs(cg_value - bn_value)
                rel_diff = _rel_diff(cg_value, bn_value)
                rels_by_field[field].append(rel_diff)
                abs_by_field[field].append(abs_diff)
                if rel_diff > rel_threshold:
                    field_stats[field]["material_diff_count"] += 1
                    if len(material_examples) < 12:
                        material_examples.append(
                            {
                                "open_time_ms": ts,
                                "open_time_utc": _utc(ts),
                                "field": field,
                                "coinglass_value": cg_value,
                                "binance_value": bn_value,
                                "abs_diff": abs_diff,
                                "rel_diff": rel_diff,
                            }
                        )
        material_diff_count = 0
        max_rel_diff = 0.0
        for field in OHLC_FIELDS:
            rels = rels_by_field[field]
            abs_diffs = abs_by_field[field]
            if rels:
                field_stats[field]["max_abs_diff"] = max(abs_diffs)
                field_stats[field]["max_rel_diff"] = max(rels)
                field_stats[field]["median_rel_diff"] = statistics.median(rels)
                max_rel_diff = max(max_rel_diff, max(rels))
            material_diff_count += int(field_stats[field]["material_diff_count"])
        expected_comparable = sum(
            1
            for row in cg_rows
            if cutoff_open_time is None or int(row["open_time_ms"]) <= cutoff_open_time
        )
        status = "pass"
        if comparable_rows == 0:
            status = "no_comparable_rows"
        elif missing_binance_rows > 0:
            status = "missing_binance_rows"
        elif material_diff_count > 0:
            status = "material_ohlc_mismatch"
        results.append(
            {
                "symbol": symbol,
                "status": status,
                "watchlist": symbol in set(watchlist),
                "coinglass_row_count": len(cg_rows),
                "binance_row_count": len(bn_rows),
                "excluded_tail_hours": exclude_tail_hours,
                "max_coinglass_open_time_ms": max_cg_open_time,
                "max_coinglass_open_time_utc": _utc(max_cg_open_time),
                "comparison_cutoff_open_time_ms": cutoff_open_time,
                "comparison_cutoff_open_time_utc": _utc(cutoff_open_time),
                "expected_comparable_rows": expected_comparable,
                "comparable_rows": comparable_rows,
                "missing_binance_rows": missing_binance_rows,
                "material_diff_count": material_diff_count,
                "max_rel_diff": max_rel_diff if comparable_rows else None,
                "field_stats": field_stats,
                "material_examples": material_examples,
                "expected_interval_ms": interval_ms,
            }
        )
    status_counts: dict[str, int] = {}
    for item in results:
        status_counts[str(item["status"])] = status_counts.get(str(item["status"]), 0) + 1
    payload = {
        "generated_at_utc": utc_now(),
        "source_summary_path": str(summary_path),
        "coinglass_root": str(resolved_coinglass_root),
        "binance_root": str(resolved_binance_root),
        "interval": interval,
        "exclude_tail_hours": exclude_tail_hours,
        "rel_threshold": rel_threshold,
        "ohlc_fields": list(OHLC_FIELDS),
        "symbol_count": len(results),
        "pass_symbol_count": sum(1 for item in results if item["status"] == "pass"),
        "fail_symbol_count": sum(1 for item in results if item["status"] != "pass"),
        "status_counts": status_counts,
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
        "# CoinGlass Spot Strict Concordance",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        f"- symbols: `{payload['symbol_count']}`",
        f"- pass symbols: `{payload['pass_symbol_count']}`",
        f"- fail symbols: `{payload['fail_symbol_count']}`",
        f"- excluded tail hours: `{payload['exclude_tail_hours']}`",
        f"- OHLC relative threshold: `{payload['rel_threshold']}`",
        f"- status counts: `{payload['status_counts']}`",
        "- alpha interpretation: blocked unless every strategy-scope symbol passes this report and CG-2 OI provenance.",
        "",
        "| symbol | status | comparable | missing bn | material diffs | max rel diff | cutoff utc | watchlist |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in payload["results"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["symbol"]),
                    str(item["status"]),
                    str(item["comparable_rows"]),
                    str(item["missing_binance_rows"]),
                    str(item["material_diff_count"]),
                    "" if item["max_rel_diff"] is None else f"{float(item['max_rel_diff']):.8g}",
                    str(item["comparison_cutoff_open_time_utc"]),
                    str(item["watchlist"]),
                ]
            )
            + " |"
        )
    watchlist = [item for item in payload["results"] if item.get("watchlist")]
    lines.extend(["", "## Watchlist Detail", ""])
    for item in watchlist:
        lines.extend(
            [
                f"### `{item['symbol']}`",
                "",
                f"- status: `{item['status']}`",
                f"- comparable rows: `{item['comparable_rows']}`",
                f"- missing Binance rows: `{item['missing_binance_rows']}`",
                f"- material diffs: `{item['material_diff_count']}`",
                "",
            ]
        )
        if item["material_examples"]:
            lines.extend(["| utc | field | coinglass | binance | rel diff |", "| --- | --- | ---: | ---: | ---: |"])
            for example in item["material_examples"][:8]:
                lines.append(
                    f"| {example['open_time_utc']} | {example['field']} | {example['coinglass_value']} | "
                    f"{example['binance_value']} | {example['rel_diff']} |"
                )
            lines.append("")
    lines.extend(["## Stop Rule", "", "Fail closed: this report must pass after excluding unstable tail bars before CoinGlass spot can be used as an alpha rerun input.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare CoinGlass spot OHLC against local Binance baseline over closed bars.")
    parser.add_argument("--summary-path", type=Path, default=Path(resolve_coinglass_root()) / "last_sync_summary.json")
    parser.add_argument("--coinglass-root", type=Path, default=None)
    parser.add_argument("--binance-root", type=Path, default=None)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--exclude-tail-hours", type=int, default=24)
    parser.add_argument("--rel-threshold", type=float, default=0.001)
    parser.add_argument("--watchlist", nargs="*", default=list(DEFAULT_WATCHLIST))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate_strict_concordance(
        summary_path=args.summary_path,
        coinglass_root=args.coinglass_root,
        binance_root=args.binance_root,
        interval=args.interval,
        exclude_tail_hours=args.exclude_tail_hours,
        rel_threshold=args.rel_threshold,
        watchlist=tuple(str(item).upper() for item in args.watchlist),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["fail_symbol_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
