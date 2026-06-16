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
from enhengclaw.utils.binance_http import binance_get_json
from scripts.market_data.binance_ohlcv import SPOT_EXCHANGE_INFO_URL, resolve_external_history_root as resolve_binance_root


STRICT_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_strict_concordance_2026-05-04.json"
JSON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_concordance_quarantine_2026-05-04.json"
REPORT_PATH = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_spot_concordance_quarantine_2026-05-04.md"
OHLC_FIELDS = ("open", "high", "low", "close")
MICRO_TICK_MULTIPLIER = 2.0


def _load_rows(root: Path, *, symbol: str, interval: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = root / "spot" / symbol / interval
    for partition in sorted(path.glob("*.csv.gz")):
        with gzip.open(partition, "rt", newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["open_time_ms"]))
    return rows


def _utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _rel_diff(left: float, right: float) -> float:
    return abs(left - right) / max(abs(right), 1e-12)


def _tick_sizes() -> dict[str, float]:
    payload = binance_get_json(SPOT_EXCHANGE_INFO_URL, timeout_seconds=30.0)
    ticks: dict[str, float] = {}
    for item in list(dict(payload or {}).get("symbols") or []):
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        for filt in list(item.get("filters") or []):
            if str(filt.get("filterType") or "") != "PRICE_FILTER":
                continue
            try:
                tick = float(filt.get("tickSize"))
            except (TypeError, ValueError):
                continue
            if tick > 0:
                ticks[symbol] = tick
    return ticks


def _diff_summary(
    *,
    symbol: str,
    coinglass_root: Path,
    binance_root: Path,
    interval: str,
    cutoff_open_time_ms: int | None,
    rel_threshold: float,
    tick_size: float | None,
) -> dict[str, Any]:
    cg_rows = _load_rows(coinglass_root, symbol=symbol, interval=interval)
    bn_rows = _load_rows(binance_root, symbol=symbol, interval=interval)
    bn_by_ts = {int(row["open_time_ms"]): row for row in bn_rows}
    material: list[dict[str, Any]] = []
    field_counts = {field: 0 for field in OHLC_FIELDS}
    close_material_count = 0
    for row in cg_rows:
        ts = int(row["open_time_ms"])
        if cutoff_open_time_ms is not None and ts > cutoff_open_time_ms:
            continue
        other = bn_by_ts.get(ts)
        if other is None:
            continue
        for field in OHLC_FIELDS:
            cg_value = float(row[field])
            bn_value = float(other[field])
            rel = _rel_diff(cg_value, bn_value)
            if rel <= rel_threshold:
                continue
            abs_diff = abs(cg_value - bn_value)
            tick_diff = None if not tick_size else abs_diff / tick_size
            material.append(
                {
                    "open_time_ms": ts,
                    "open_time_utc": _utc(ts),
                    "field": field,
                    "coinglass_value": cg_value,
                    "binance_value": bn_value,
                    "abs_diff": abs_diff,
                    "rel_diff": rel,
                    "tick_diff": tick_diff,
                }
            )
            field_counts[field] += 1
            if field == "close":
                close_material_count += 1
    abs_diffs = [float(item["abs_diff"]) for item in material]
    rel_diffs = [float(item["rel_diff"]) for item in material]
    tick_diffs = [float(item["tick_diff"]) for item in material if item.get("tick_diff") is not None]
    max_tick_diff = max(tick_diffs, default=None)
    max_abs_diff = max(abs_diffs, default=0.0)
    max_rel_diff = max(rel_diffs, default=0.0)
    classification = "pass"
    if material:
        if tick_size is not None and max_abs_diff <= (MICRO_TICK_MULTIPLIER * tick_size):
            classification = "micro_tick_rounding"
        else:
            classification = "true_historical_conflict"
    examples = sorted(material, key=lambda item: float(item["rel_diff"]), reverse=True)[:8]
    return {
        "symbol": symbol,
        "classification": classification,
        "tick_size": tick_size,
        "micro_tick_threshold_abs": None if tick_size is None else MICRO_TICK_MULTIPLIER * tick_size,
        "material_diff_count": len(material),
        "close_material_diff_count": close_material_count,
        "field_material_counts": field_counts,
        "max_abs_diff": max_abs_diff,
        "max_rel_diff": max_rel_diff,
        "max_tick_diff": max_tick_diff,
        "median_rel_diff_over_material": statistics.median(rel_diffs) if rel_diffs else 0.0,
        "examples": examples,
    }


def build_quarantine(
    *,
    strict_path: Path = STRICT_PATH,
    coinglass_root: Path | None = None,
    binance_root: Path | None = None,
) -> dict[str, Any]:
    strict = json.loads(strict_path.read_text(encoding="utf-8"))
    resolved_coinglass_root = coinglass_root or resolve_coinglass_root()
    resolved_binance_root = binance_root or resolve_binance_root()
    ticks = _tick_sizes()
    interval = str(strict.get("interval") or "1h")
    rel_threshold = float(strict.get("rel_threshold") or 0.001)
    rows: list[dict[str, Any]] = []
    for item in list(strict.get("results") or []):
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        if item.get("status") == "pass":
            rows.append(
                {
                    "symbol": symbol,
                    "classification": "pass",
                    "tick_size": ticks.get(symbol),
                    "material_diff_count": 0,
                    "close_material_diff_count": 0,
                    "field_material_counts": {field: 0 for field in OHLC_FIELDS},
                    "max_abs_diff": 0.0,
                    "max_rel_diff": float(item.get("max_rel_diff") or 0.0),
                    "max_tick_diff": 0.0,
                    "median_rel_diff_over_material": 0.0,
                    "examples": [],
                }
            )
            continue
        rows.append(
            _diff_summary(
                symbol=symbol,
                coinglass_root=resolved_coinglass_root,
                binance_root=resolved_binance_root,
                interval=interval,
                cutoff_open_time_ms=item.get("comparison_cutoff_open_time_ms"),
                rel_threshold=rel_threshold,
                tick_size=ticks.get(symbol),
            )
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    fail_rows = [row for row in rows if row["classification"] != "pass"]
    payload = {
        "generated_at_utc": utc_now(),
        "source_strict_concordance_path": str(strict_path),
        "coinglass_root": str(resolved_coinglass_root),
        "binance_root": str(resolved_binance_root),
        "interval": interval,
        "rel_threshold": rel_threshold,
        "micro_tick_rule": f"all material OHLC diffs must be <= {MICRO_TICK_MULTIPLIER} * current Binance PRICE_FILTER.tickSize",
        "canonical_price_source": "binance_spot_ohlcv",
        "coinglass_spot_ohlc_policy": "quarantined_not_canonical",
        "alpha_interpretation_allowed": False,
        "symbol_count": len(rows),
        "fail_symbol_count": len(fail_rows),
        "classification_counts": counts,
        "results": sorted(
            rows,
            key=lambda item: (
                0 if item["classification"] == "true_historical_conflict" else 1 if item["classification"] == "micro_tick_rounding" else 2,
                -float(item.get("max_rel_diff") or 0.0),
                str(item["symbol"]),
            ),
        ),
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.write_text(_render_report(payload), encoding="utf-8")
    return payload


def _render_report(payload: dict[str, Any]) -> str:
    rows = list(payload["results"])
    conflicts = [item for item in rows if item["classification"] == "true_historical_conflict"]
    micro = [item for item in rows if item["classification"] == "micro_tick_rounding"]
    lines = [
        "# CoinGlass Spot Concordance Quarantine 2026-05-04",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Canonical OHLC source: `{payload['canonical_price_source']}`.",
        f"- CoinGlass spot OHLC policy: `{payload['coinglass_spot_ohlc_policy']}`.",
        f"- Alpha interpretation allowed: `{payload['alpha_interpretation_allowed']}`.",
        f"- Classification counts: `{payload['classification_counts']}`.",
        f"- Micro rule: `{payload['micro_tick_rule']}`.",
        "",
        "CoinGlass spot OHLC must not replace Binance OHLC for returns, volatility, breakout, drawdown, or bar-level labels. CoinGlass may remain a sidecar provider only after field-specific provenance checks.",
        "",
        "## True Historical Conflicts",
        "",
        "| symbol | material diffs | close diffs | max rel diff | max tick diff | tick size |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in conflicts:
        lines.append(
            f"| {item['symbol']} | {item['material_diff_count']} | {item['close_material_diff_count']} | "
            f"{item['max_rel_diff']} | {item['max_tick_diff']} | {item['tick_size']} |"
        )
    if not conflicts:
        lines.append("| none | 0 | 0 | 0 | 0 |  |")
    lines.extend(
        [
            "",
            "## Micro Tick/Rounding",
            "",
            "| symbol | material diffs | close diffs | max rel diff | max tick diff | tick size |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in micro:
        lines.append(
            f"| {item['symbol']} | {item['material_diff_count']} | {item['close_material_diff_count']} | "
            f"{item['max_rel_diff']} | {item['max_tick_diff']} | {item['tick_size']} |"
        )
    if not micro:
        lines.append("| none | 0 | 0 | 0 | 0 |  |")
    lines.extend(
        [
            "",
            "## Top Conflict Examples",
            "",
            "| symbol | utc | field | CoinGlass | Binance | rel diff | tick diff |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    example_count = 0
    for item in conflicts[:12]:
        for example in item["examples"][:2]:
            lines.append(
                f"| {item['symbol']} | {example['open_time_utc']} | {example['field']} | "
                f"{example['coinglass_value']} | {example['binance_value']} | {example['rel_diff']} | {example['tick_diff']} |"
            )
            example_count += 1
    if example_count == 0:
        lines.append("| none |  |  | 0 | 0 | 0 | 0 |")
    lines.extend(
        [
            "",
            "## Quarantine Contract",
            "",
            "- `pass`: may be used as sanity/reference only; Binance remains canonical.",
            "- `micro_tick_rounding`: known precision/tick artifact; do not fail the provider globally, but do not use CoinGlass spot OHLC as canonical.",
            "- `true_historical_conflict`: hard quarantine for CoinGlass spot OHLC on that symbol; use Binance OHLC only.",
            "",
            "## Next Step",
            "",
            "Proceed to CG-2 with native USD OI preferred. If only coin-denominated OI is present, derive USD value from Binance canonical perp close and store an explicit derived provenance flag.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Split CoinGlass spot strict concordance failures into micro tick versus true conflicts.")
    parser.add_argument("--strict-path", type=Path, default=STRICT_PATH)
    parser.add_argument("--coinglass-root", type=Path, default=None)
    parser.add_argument("--binance-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_quarantine(
        strict_path=args.strict_path,
        coinglass_root=args.coinglass_root,
        binance_root=args.binance_root,
    )
    print(json.dumps({"report": str(REPORT_PATH), "json": str(JSON_PATH), "classification_counts": payload["classification_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
