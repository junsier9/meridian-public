from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.quant_research.coinglass_oi_provenance import resolve_external_oi_provenance_root
from enhengclaw.quant_research.contracts import read_json, utc_now
from enhengclaw.quant_research.market_data import load_derivatives_frame


AS_OF = "2026-05-04"
UNIVERSE_PATH = ROOT / "artifacts" / "quant_research" / "_quant_inputs" / f"pit-liquidity-top100-{AS_OF}.quant_universe.json"
JSON_OUT = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_oi_compiler_integration_2026-05-04.json"
REPORT_OUT = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_oi_compiler_integration_2026-05-04.md"


def _as_of_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    as_of_end = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 0, 0, tzinfo=UTC)
    return int(as_of_end.timestamp() * 1000)


def _load_executable_symbols(path: Path) -> list[str]:
    payload = read_json(path)
    symbols: list[str] = []
    for candidate in list(payload.get("candidates") or []):
        if not candidate.get("usdm_symbol") or not candidate.get("first_perp_bar_utc"):
            continue
        symbols.append(str(candidate["usdm_symbol"]).strip().upper())
    return sorted({symbol for symbol in symbols if symbol})


def build_payload(
    *,
    as_of: str,
    universe_path: Path,
    oi_provenance_external_root: Path | None,
    intervals: tuple[str, ...],
    max_symbols: int | None,
) -> dict[str, Any]:
    resolved_sidecar_root = resolve_external_oi_provenance_root(external_root=oi_provenance_external_root)
    symbols = _load_executable_symbols(universe_path)
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    as_of_end_ms = _as_of_end_ms(as_of)
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        for interval in intervals:
            frame = load_derivatives_frame(
                symbol=symbol,
                interval=interval,
                external_root=None,
                oi_provenance_external_root=resolved_sidecar_root,
                end_time_ms=as_of_end_ms,
            )
            native_rows = (
                int(frame["open_interest_value_native_usd"].notna().sum())
                if "open_interest_value_native_usd" in frame.columns
                else 0
            )
            selected_rows = (
                int(frame["open_interest_value"].notna().sum()) if "open_interest_value" in frame.columns else 0
            )
            source_values = (
                sorted(
                    {
                        str(item)
                        for item in frame["open_interest_value_source"].dropna().tolist()
                        if str(item).strip()
                    }
                )
                if "open_interest_value_source" in frame.columns
                else []
            )
            source_intervals = (
                sorted(
                    {
                        str(item)
                        for item in frame["open_interest_value_source_interval"].dropna().tolist()
                        if str(item).strip()
                    }
                )
                if "open_interest_value_source_interval" in frame.columns
                else []
            )
            derived_status_counts: dict[str, int] = {}
            if "derived_native_formula_status" in frame.columns:
                for value in frame["derived_native_formula_status"].dropna().tolist():
                    key = str(value).strip()
                    if key:
                        derived_status_counts[key] = derived_status_counts.get(key, 0) + 1
            bad_selected_policy = False
            if "open_interest_value_canonical_policy" in frame.columns and native_rows:
                policies = {
                    str(item)
                    for item in frame.loc[frame["open_interest_value_native_usd"].notna(), "open_interest_value_canonical_policy"]
                    .dropna()
                    .tolist()
                    if str(item).strip()
                }
                bad_selected_policy = policies != {"native_usd_only"}
            results.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "row_count": int(len(frame)),
                    "native_usd_row_count": native_rows,
                    "selected_oi_value_row_count": selected_rows,
                    "source_values": source_values,
                    "source_intervals": source_intervals,
                    "derived_native_formula_status_counts": derived_status_counts,
                    "bad_selected_policy": bad_selected_policy,
                }
            )
    interval_summary: dict[str, dict[str, Any]] = {}
    for interval in intervals:
        scoped = [item for item in results if item["interval"] == interval]
        interval_summary[interval] = {
            "symbol_count": len(scoped),
            "symbols_with_native_usd_oi": sum(1 for item in scoped if int(item["native_usd_row_count"]) > 0),
            "total_native_usd_rows": sum(int(item["native_usd_row_count"]) for item in scoped),
            "total_selected_oi_value_rows": sum(int(item["selected_oi_value_row_count"]) for item in scoped),
            "bad_selected_policy_count": sum(1 for item in scoped if bool(item["bad_selected_policy"])),
            "symbols_with_formula_fail_rows": sum(
                1 for item in scoped if int((item["derived_native_formula_status_counts"] or {}).get("fail", 0)) > 0
            ),
        }
    status = "pass"
    if any(item["bad_selected_policy"] for item in results):
        status = "fail"
    if any(summary["symbols_with_native_usd_oi"] == 0 for summary in interval_summary.values()):
        status = "fail"
    return with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "artifact_family": "coinglass_oi_compiler_integration",
            "status": status,
            "as_of": as_of,
            "universe_path": str(universe_path),
            "oi_provenance_external_root": str(resolved_sidecar_root),
            "symbol_count": len(symbols),
            "intervals": list(intervals),
            "integration_policy": {
                "selected_oi_value": "open_interest_value uses CoinGlass native USD sidecar when present",
                "coin_oi_policy": "open_interest_coin is metadata only; it is not promoted into open_interest",
                "derived_oi_policy": "open_interest_value_derived_usd remains quarantine metadata",
                "spot_ohlc_policy": "no CoinGlass spot OHLC is consumed by this loader",
            },
            "interval_summary": interval_summary,
            "results": results,
        },
        evidence_family="coinglass_oi_compiler_integration",
        contract_version="coinglass_oi_compiler_integration.v1",
        repo_root=ROOT,
    )


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# CoinGlass OI Compiler Integration 2026-05-04",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Status: `{payload['status']}`.",
        f"- Symbols: `{payload['symbol_count']}`.",
        f"- Sidecar root: `{payload['oi_provenance_external_root']}`.",
        f"- Selected OI policy: `{payload['integration_policy']['selected_oi_value']}`.",
        f"- Derived OI policy: `{payload['integration_policy']['derived_oi_policy']}`.",
        f"- Coin OI policy: `{payload['integration_policy']['coin_oi_policy']}`.",
        f"- Spot OHLC policy: `{payload['integration_policy']['spot_ohlc_policy']}`.",
        "",
        "## Interval Summary",
        "",
        "| interval | symbols | symbols with native USD OI | native rows | selected OI rows | bad policy | symbols with formula fail rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for interval, item in dict(payload["interval_summary"]).items():
        lines.append(
            f"| {interval} | {item['symbol_count']} | {item['symbols_with_native_usd_oi']} | "
            f"{item['total_native_usd_rows']} | {item['total_selected_oi_value_rows']} | "
            f"{item['bad_selected_policy_count']} | {item['symbols_with_formula_fail_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            "This is a compiler-loader integration check only. It does not override the strict spot OHLC provider concordance failure and does not authorize alpha reruns.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit native USD OI sidecar visibility from the dataset compiler loader.")
    parser.add_argument("--as-of", default=AS_OF)
    parser.add_argument("--universe-path", type=Path, default=UNIVERSE_PATH)
    parser.add_argument("--oi-provenance-external-root", type=Path, default=None)
    parser.add_argument("--intervals", nargs="+", default=["1h", "4h", "1d"])
    parser.add_argument("--max-symbols", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_payload(
        as_of=args.as_of,
        universe_path=args.universe_path,
        oi_provenance_external_root=args.oi_provenance_external_root,
        intervals=tuple(args.intervals),
        max_symbols=args.max_symbols,
    )
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_OUT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"json": str(JSON_OUT), "report": str(REPORT_OUT), "status": payload["status"]}, indent=2))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
