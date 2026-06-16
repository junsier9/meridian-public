from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.market_data.binance_ohlcv import (
    interval_to_ms,
    load_interval_rows as load_binance_interval_rows,
    resolve_external_history_root as resolve_binance_history_root,
)
from scripts.market_data.coinapi_ohlcv import (
    load_interval_rows as load_coinapi_interval_rows,
    resolve_external_history_root as resolve_coinapi_history_root,
    sync_coinapi_ohlcv,
)


DEFAULT_SYMBOLS = ("ETHUSDT", "SUIUSDT", "JTOUSDT", "UNIUSDT")
DEFAULT_INTERVALS = ("1h", "4h", "1d")
LOOKBACK_DAYS_BY_INTERVAL = {"1h": 30, "4h": 120, "1d": 180}
SPOT_MARKET_TYPE = "spot"
BENCHMARK_ROOT = ROOT / "artifacts" / "benchmarks" / "coinapi_vs_binance"
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class BenchmarkWindow:
    symbol: str
    interval: str
    start_time_ms: int
    end_time_ms_exclusive: int
    latest_open_time_ms: int
    expected_step_ms: int
    lookback_days: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark CoinAPI spot OHLCV against the local Binance OHLCV store for the "
            "Quant Research workflow."
        )
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=list(DEFAULT_SYMBOLS),
        help="Canonical spot symbols to benchmark. Defaults to ETHUSDT SUIUSDT JTOUSDT UNIUSDT.",
    )
    parser.add_argument(
        "--intervals",
        default="1h,4h,1d",
        help="Comma-separated intervals to benchmark. Defaults to 1h,4h,1d.",
    )
    parser.add_argument(
        "--binance-root",
        type=Path,
        default=None,
        help="Optional local Binance OHLCV store root.",
    )
    parser.add_argument(
        "--coinapi-root",
        type=Path,
        default=None,
        help="Optional CoinAPI benchmark store root. Defaults to a timestamped artifacts path.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root for the benchmark summary. Defaults to a timestamped artifacts path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_benchmark(
            symbols=tuple(_normalize_symbol(item) for item in (args.symbols or [])),
            intervals=_split_csv(args.intervals, DEFAULT_INTERVALS),
            binance_root=args.binance_root,
            coinapi_root=args.coinapi_root,
            output_root=args.output_root,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def run_benchmark(
    *,
    symbols: tuple[str, ...],
    intervals: tuple[str, ...],
    binance_root: Path | None,
    coinapi_root: Path | None,
    output_root: Path | None,
) -> dict[str, Any]:
    if not symbols:
        raise ValueError("at least one symbol is required")
    if not intervals:
        raise ValueError("at least one interval is required")

    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    resolved_binance_root = resolve_binance_history_root(external_root=binance_root)
    resolved_output_root = (output_root or (BENCHMARK_ROOT / run_stamp)).expanduser().resolve()
    resolved_coinapi_root = (coinapi_root or (resolved_output_root / "coinapi_store")).expanduser().resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    resolved_coinapi_root.mkdir(parents=True, exist_ok=True)

    pair_results: list[dict[str, Any]] = []
    refresh_catalog = True
    for symbol in symbols:
        for interval in intervals:
            window = _resolve_benchmark_window(
                binance_root=resolved_binance_root,
                symbol=symbol,
                interval=interval,
            )
            sync_coinapi_ohlcv(
                external_root=resolved_coinapi_root,
                symbols=(symbol,),
                intervals=(interval,),
                mode="bootstrap",
                time_start=_isoformat_z_ms(window.start_time_ms),
                time_end=_isoformat_z_ms(window.end_time_ms_exclusive),
                refresh_catalog=refresh_catalog,
            )
            refresh_catalog = False
            pair_results.append(
                _benchmark_symbol_interval(
                    binance_root=resolved_binance_root,
                    coinapi_root=resolved_coinapi_root,
                    window=window,
                )
            )

    summary = {
        "generated_at_utc": _utc_now(),
        "status": "success",
        "success": True,
        "symbols": list(symbols),
        "intervals": list(intervals),
        "binance_root": str(resolved_binance_root),
        "coinapi_root": str(resolved_coinapi_root),
        "output_root": str(resolved_output_root),
        "mapping_hit_rate": _mapping_hit_rate(pair_results),
        "pair_results": pair_results,
        "interval_rollups": _interval_rollups(pair_results),
        "overall_rollup": _overall_rollup(pair_results),
    }
    summary_path = resolved_output_root / "benchmark_summary.json"
    markdown_path = resolved_output_root / "benchmark_summary.md"
    summary["benchmark_summary_path"] = str(summary_path)
    summary["benchmark_markdown_path"] = str(markdown_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_build_markdown(summary) + "\n", encoding="utf-8")
    return summary


def _resolve_benchmark_window(*, binance_root: Path, symbol: str, interval: str) -> BenchmarkWindow:
    rows = load_binance_interval_rows(
        external_root=binance_root,
        market_type=SPOT_MARKET_TYPE,
        symbol=symbol,
        interval=interval,
    )
    if not rows:
        raise FileNotFoundError(
            f"Binance OHLCV rows not found for {symbol} {interval} under {binance_root}"
        )
    expected_step_ms = interval_to_ms(interval)
    latest_open_time_ms = int(rows[-1]["open_time_ms"])
    target_lookback_days = LOOKBACK_DAYS_BY_INTERVAL.get(interval)
    if target_lookback_days is None:
        raise ValueError(f"unsupported interval for benchmark lookback: {interval}")
    requested_bar_count = max(int((target_lookback_days * 86_400_000) / expected_step_ms), 1)
    start_index = max(len(rows) - requested_bar_count, 0)
    start_time_ms = int(rows[start_index]["open_time_ms"])
    end_time_ms_exclusive = latest_open_time_ms + expected_step_ms
    return BenchmarkWindow(
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms_exclusive=end_time_ms_exclusive,
        latest_open_time_ms=latest_open_time_ms,
        expected_step_ms=expected_step_ms,
        lookback_days=target_lookback_days,
    )


def _benchmark_symbol_interval(
    *,
    binance_root: Path,
    coinapi_root: Path,
    window: BenchmarkWindow,
) -> dict[str, Any]:
    binance_rows = _filter_window(
        load_binance_interval_rows(
            external_root=binance_root,
            market_type=SPOT_MARKET_TYPE,
            symbol=window.symbol,
            interval=window.interval,
        ),
        start_time_ms=window.start_time_ms,
        end_time_ms_exclusive=window.end_time_ms_exclusive,
    )
    coinapi_rows = _filter_window(
        load_coinapi_interval_rows(
            external_root=coinapi_root,
            market_type=SPOT_MARKET_TYPE,
            symbol=window.symbol,
            interval=window.interval,
        ),
        start_time_ms=window.start_time_ms,
        end_time_ms_exclusive=window.end_time_ms_exclusive,
    )
    binance_by_time = {int(row["open_time_ms"]): row for row in binance_rows}
    coinapi_by_time = {int(row["open_time_ms"]): row for row in coinapi_rows}
    shared_times = sorted(set(binance_by_time) & set(coinapi_by_time))
    binance_only_times = sorted(set(binance_by_time) - set(coinapi_by_time))
    coinapi_only_times = sorted(set(coinapi_by_time) - set(binance_by_time))

    field_metrics = {
        field: _field_metrics(
            shared_times=shared_times,
            left_rows=coinapi_by_time,
            right_rows=binance_by_time,
            field=field,
        )
        for field in ("open", "high", "low", "close", "volume", "quote_volume")
    }
    direction_agreement = _direction_agreement(
        shared_times=shared_times,
        coinapi_rows=coinapi_by_time,
        binance_rows=binance_by_time,
    )
    close_return_agreement = _close_return_agreement(
        shared_times=shared_times,
        coinapi_rows=coinapi_by_time,
        binance_rows=binance_by_time,
    )

    return {
        "symbol": window.symbol,
        "interval": window.interval,
        "window_start_utc": _isoformat_z_ms(window.start_time_ms),
        "window_end_utc_exclusive": _isoformat_z_ms(window.end_time_ms_exclusive),
        "lookback_days_target": window.lookback_days,
        "expected_step_ms": window.expected_step_ms,
        "mapping_hit": len(coinapi_rows) > 0,
        "binance_bar_count": len(binance_rows),
        "coinapi_bar_count": len(coinapi_rows),
        "shared_bar_count": len(shared_times),
        "shared_coverage_ratio_vs_binance": _ratio(len(shared_times), len(binance_rows)),
        "shared_coverage_ratio_vs_coinapi": _ratio(len(shared_times), len(coinapi_rows)),
        "binance_only_bar_count": len(binance_only_times),
        "coinapi_only_bar_count": len(coinapi_only_times),
        "binance_gap_count": _gap_count(binance_rows, expected_step_ms=window.expected_step_ms),
        "coinapi_gap_count": _gap_count(coinapi_rows, expected_step_ms=window.expected_step_ms),
        "field_metrics": field_metrics,
        "direction_agreement": direction_agreement,
        "close_return_sign_agreement": close_return_agreement,
        "binance_sources": sorted({str(row.get("source", "")) for row in binance_rows}),
        "coinapi_sources": sorted({str(row.get("source", "")) for row in coinapi_rows}),
        "binance_manifest_path": str(
            binance_root / SPOT_MARKET_TYPE / window.symbol / window.interval / "manifest.json"
        ),
        "coinapi_manifest_path": str(
            coinapi_root / SPOT_MARKET_TYPE / window.symbol / window.interval / "manifest.json"
        ),
        "sample_shared_rows": _sample_shared_rows(
            shared_times=shared_times,
            coinapi_rows=coinapi_by_time,
            binance_rows=binance_by_time,
        ),
        "notes": [
            "CoinAPI quote_volume is derived in the current sidecar and is not a native exchange quote-volume field.",
            "CoinAPI sidecar currently benchmarks spot history only; Binance derivatives remain outside this comparison.",
        ],
    }


def _field_metrics(
    *,
    shared_times: list[int],
    left_rows: dict[int, dict[str, str]],
    right_rows: dict[int, dict[str, str]],
    field: str,
) -> dict[str, Any]:
    abs_diffs: list[float] = []
    abs_pct_diffs: list[float] = []
    abs_rel_diffs: list[float] = []
    for timestamp in shared_times:
        left_value = float(left_rows[timestamp][field])
        right_value = float(right_rows[timestamp][field])
        abs_diff = abs(left_value - right_value)
        abs_diffs.append(abs_diff)
        denominator = max(abs(right_value), EPSILON)
        abs_pct_diffs.append(abs_diff / denominator)
        abs_rel_diffs.append(abs_diff / max(abs(left_value), abs(right_value), EPSILON))
    if not abs_diffs:
        return {
            "mean_abs_diff": None,
            "median_abs_diff": None,
            "max_abs_diff": None,
            "mean_abs_pct_diff": None,
            "median_abs_pct_diff": None,
            "max_abs_pct_diff": None,
            "mean_abs_rel_diff": None,
            "median_abs_rel_diff": None,
            "max_abs_rel_diff": None,
        }
    return {
        "mean_abs_diff": round(statistics.fmean(abs_diffs), 10),
        "median_abs_diff": round(statistics.median(abs_diffs), 10),
        "max_abs_diff": round(max(abs_diffs), 10),
        "mean_abs_pct_diff": round(statistics.fmean(abs_pct_diffs), 10),
        "median_abs_pct_diff": round(statistics.median(abs_pct_diffs), 10),
        "max_abs_pct_diff": round(max(abs_pct_diffs), 10),
        "mean_abs_rel_diff": round(statistics.fmean(abs_rel_diffs), 10),
        "median_abs_rel_diff": round(statistics.median(abs_rel_diffs), 10),
        "max_abs_rel_diff": round(max(abs_rel_diffs), 10),
    }


def _direction_agreement(
    *,
    shared_times: list[int],
    coinapi_rows: dict[int, dict[str, str]],
    binance_rows: dict[int, dict[str, str]],
) -> dict[str, Any]:
    if not shared_times:
        return {"agreement_count": 0, "agreement_ratio": None}
    agreement_count = 0
    for timestamp in shared_times:
        coin_direction = _sign(float(coinapi_rows[timestamp]["close"]) - float(coinapi_rows[timestamp]["open"]))
        bin_direction = _sign(float(binance_rows[timestamp]["close"]) - float(binance_rows[timestamp]["open"]))
        if coin_direction == bin_direction:
            agreement_count += 1
    return {
        "agreement_count": agreement_count,
        "agreement_ratio": round(agreement_count / len(shared_times), 6),
    }


def _close_return_agreement(
    *,
    shared_times: list[int],
    coinapi_rows: dict[int, dict[str, str]],
    binance_rows: dict[int, dict[str, str]],
) -> dict[str, Any]:
    if len(shared_times) < 2:
        return {"agreement_count": 0, "agreement_ratio": None}
    agreement_count = 0
    comparisons = 0
    for previous_time, current_time in zip(shared_times, shared_times[1:]):
        coin_prev = float(coinapi_rows[previous_time]["close"])
        coin_curr = float(coinapi_rows[current_time]["close"])
        bin_prev = float(binance_rows[previous_time]["close"])
        bin_curr = float(binance_rows[current_time]["close"])
        coin_sign = _sign((coin_curr / max(coin_prev, EPSILON)) - 1.0)
        bin_sign = _sign((bin_curr / max(bin_prev, EPSILON)) - 1.0)
        comparisons += 1
        if coin_sign == bin_sign:
            agreement_count += 1
    return {
        "agreement_count": agreement_count,
        "agreement_ratio": round(agreement_count / comparisons, 6) if comparisons else None,
    }


def _sample_shared_rows(
    *,
    shared_times: list[int],
    coinapi_rows: dict[int, dict[str, str]],
    binance_rows: dict[int, dict[str, str]],
    max_rows: int = 5,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for timestamp in shared_times[:max_rows]:
        samples.append(
            {
                "open_time_utc": _isoformat_z_ms(timestamp),
                "coinapi_close": coinapi_rows[timestamp]["close"],
                "binance_close": binance_rows[timestamp]["close"],
                "coinapi_volume": coinapi_rows[timestamp]["volume"],
                "binance_volume": binance_rows[timestamp]["volume"],
                "coinapi_quote_volume": coinapi_rows[timestamp]["quote_volume"],
                "binance_quote_volume": binance_rows[timestamp]["quote_volume"],
            }
        )
    return samples


def _filter_window(
    rows: list[dict[str, str]],
    *,
    start_time_ms: int,
    end_time_ms_exclusive: int,
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if start_time_ms <= int(row["open_time_ms"]) < end_time_ms_exclusive
    ]


def _gap_count(rows: list[dict[str, str]], *, expected_step_ms: int) -> int:
    if len(rows) < 2:
        return 0
    ordered_times = [int(row["open_time_ms"]) for row in rows]
    return sum(1 for left, right in zip(ordered_times, ordered_times[1:]) if (right - left) != expected_step_ms)


def _mapping_hit_rate(pair_results: list[dict[str, Any]]) -> dict[str, Any]:
    hit_count = sum(1 for item in pair_results if bool(item.get("mapping_hit")))
    total_count = len(pair_results)
    return {
        "hit_count": hit_count,
        "total_count": total_count,
        "hit_ratio": round(hit_count / total_count, 6) if total_count else None,
    }


def _interval_rollups(pair_results: list[dict[str, Any]]) -> dict[str, Any]:
    rollups: dict[str, Any] = {}
    for interval in sorted({str(item["interval"]) for item in pair_results}):
        items = [item for item in pair_results if str(item["interval"]) == interval]
        shared_bars = sum(int(item["shared_bar_count"]) for item in items)
        binance_bars = sum(int(item["binance_bar_count"]) for item in items)
        coinapi_bars = sum(int(item["coinapi_bar_count"]) for item in items)
        rollups[interval] = {
            "pair_count": len(items),
            "shared_bar_count": shared_bars,
            "binance_bar_count": binance_bars,
            "coinapi_bar_count": coinapi_bars,
            "shared_coverage_ratio_vs_binance": _ratio(shared_bars, binance_bars),
            "shared_coverage_ratio_vs_coinapi": _ratio(shared_bars, coinapi_bars),
            "binance_gap_count": sum(int(item["binance_gap_count"]) for item in items),
            "coinapi_gap_count": sum(int(item["coinapi_gap_count"]) for item in items),
            "close_mean_abs_rel_diff_median": _median_metric(
                items,
                path=("field_metrics", "close", "mean_abs_rel_diff"),
            ),
            "volume_mean_abs_rel_diff_median": _median_metric(
                items,
                path=("field_metrics", "volume", "mean_abs_rel_diff"),
            ),
            "direction_agreement_ratio_median": _median_metric(
                items,
                path=("direction_agreement", "agreement_ratio"),
            ),
        }
    return rollups


def _overall_rollup(pair_results: list[dict[str, Any]]) -> dict[str, Any]:
    shared_bars = sum(int(item["shared_bar_count"]) for item in pair_results)
    binance_bars = sum(int(item["binance_bar_count"]) for item in pair_results)
    coinapi_bars = sum(int(item["coinapi_bar_count"]) for item in pair_results)
    return {
        "pair_count": len(pair_results),
        "shared_bar_count": shared_bars,
        "binance_bar_count": binance_bars,
        "coinapi_bar_count": coinapi_bars,
        "shared_coverage_ratio_vs_binance": _ratio(shared_bars, binance_bars),
        "shared_coverage_ratio_vs_coinapi": _ratio(shared_bars, coinapi_bars),
        "binance_gap_count": sum(int(item["binance_gap_count"]) for item in pair_results),
        "coinapi_gap_count": sum(int(item["coinapi_gap_count"]) for item in pair_results),
        "close_mean_abs_rel_diff_median": _median_metric(
            pair_results,
            path=("field_metrics", "close", "mean_abs_rel_diff"),
        ),
        "volume_mean_abs_rel_diff_median": _median_metric(
            pair_results,
            path=("field_metrics", "volume", "mean_abs_rel_diff"),
        ),
        "quote_volume_mean_abs_rel_diff_median": _median_metric(
            pair_results,
            path=("field_metrics", "quote_volume", "mean_abs_rel_diff"),
        ),
    }


def _median_metric(items: list[dict[str, Any]], *, path: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for item in items:
        current: Any = item
        for key in path:
            current = current.get(key) if isinstance(current, dict) else None
        if current is None:
            continue
        values.append(float(current))
    if not values:
        return None
    return round(statistics.median(values), 10)


def _build_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# CoinAPI vs Binance Benchmark",
        "",
        f"- Generated at: `{summary['generated_at_utc']}`",
        f"- Symbols: `{', '.join(summary['symbols'])}`",
        f"- Intervals: `{', '.join(summary['intervals'])}`",
        f"- Binance root: `{summary['binance_root']}`",
        f"- CoinAPI root: `{summary['coinapi_root']}`",
        "",
        "## Overall",
        "",
        f"- Shared coverage vs Binance: `{summary['overall_rollup']['shared_coverage_ratio_vs_binance']}`",
        f"- Shared coverage vs CoinAPI: `{summary['overall_rollup']['shared_coverage_ratio_vs_coinapi']}`",
        f"- Median close mean abs rel diff: `{summary['overall_rollup']['close_mean_abs_rel_diff_median']}`",
        f"- Median volume mean abs rel diff: `{summary['overall_rollup']['volume_mean_abs_rel_diff_median']}`",
        f"- Median quote-volume mean abs rel diff: `{summary['overall_rollup']['quote_volume_mean_abs_rel_diff_median']}`",
        "",
        "## By Interval",
        "",
    ]
    for interval, rollup in summary["interval_rollups"].items():
        lines.extend(
            [
                f"### {interval}",
                "",
                f"- Shared coverage vs Binance: `{rollup['shared_coverage_ratio_vs_binance']}`",
                f"- Shared coverage vs CoinAPI: `{rollup['shared_coverage_ratio_vs_coinapi']}`",
                f"- Median close mean abs rel diff: `{rollup['close_mean_abs_rel_diff_median']}`",
                f"- Median volume mean abs rel diff: `{rollup['volume_mean_abs_rel_diff_median']}`",
                f"- Median candle-direction agreement: `{rollup['direction_agreement_ratio_median']}`",
                "",
            ]
        )
    lines.extend(["## Pair Results", ""])
    for item in summary["pair_results"]:
        lines.extend(
            [
                f"### {item['symbol']} {item['interval']}",
                "",
                f"- Window: `{item['window_start_utc']} -> {item['window_end_utc_exclusive']}`",
                f"- Shared bars: `{item['shared_bar_count']}` / Binance `{item['binance_bar_count']}` / CoinAPI `{item['coinapi_bar_count']}`",
                f"- Shared coverage vs Binance: `{item['shared_coverage_ratio_vs_binance']}`",
                f"- Shared coverage vs CoinAPI: `{item['shared_coverage_ratio_vs_coinapi']}`",
                f"- Close mean abs rel diff: `{item['field_metrics']['close']['mean_abs_rel_diff']}`",
                f"- Volume mean abs rel diff: `{item['field_metrics']['volume']['mean_abs_rel_diff']}`",
                f"- Quote-volume mean abs rel diff: `{item['field_metrics']['quote_volume']['mean_abs_rel_diff']}`",
                f"- Candle-direction agreement: `{item['direction_agreement']['agreement_ratio']}`",
                f"- Close-return sign agreement: `{item['close_return_sign_agreement']['agreement_ratio']}`",
                "",
            ]
        )
    return "\n".join(lines)


def _normalize_symbol(value: str) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise ValueError("symbol must be non-empty")
    return normalized


def _split_csv(raw_value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    return tuple(values) if values else default


def _isoformat_z_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


if __name__ == "__main__":
    raise SystemExit(main())
