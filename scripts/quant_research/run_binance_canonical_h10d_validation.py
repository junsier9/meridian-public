from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.binance_canonical_h10d import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_FUNDING_COST_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_REPORT_ROOT,
    DEFAULT_STORE_ROOT,
    run_binance_canonical_validation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and validate the Binance-canonical H10D challenger. Core alpha is "
            "restricted to Binance public-archive OHLCV-derived features."
        )
    )
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--as-of", default="2026-04-30")
    parser.add_argument("--strategy-label", default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--funding-root", type=Path, default=DEFAULT_FUNDING_COST_ROOT)
    parser.add_argument(
        "--backfill-funding",
        action="store_true",
        help="Backfill Binance USD-M fundingRate history for the selected universe before validation.",
    )
    parser.add_argument(
        "--force-funding",
        action="store_true",
        help="Overwrite/merge funding partitions during --backfill-funding.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument(
        "--reference-capital-usd",
        type=float,
        default=None,
        help="Override reference_capital_usd for capacity/cost sensitivity runs.",
    )
    parser.add_argument(
        "--universe-mode",
        choices=["config", "frozen_asof", "rolling_quote_volume", "pit_rolling_quote_volume"],
        default="config",
        help="Override the configured universe selection mode.",
    )
    parser.add_argument(
        "--pit-min-lifetime-valid-days",
        type=int,
        default=None,
        help="Override pit_data_eligibility_policy.min_lifetime_valid_days for PIT eligibility sensitivity runs.",
    )
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run validation in memory without writing artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config
    if (
        args.universe_mode != "config"
        or args.reference_capital_usd is not None
        or args.pit_min_lifetime_valid_days is not None
    ):
        config_path = _load_config_override(
            config_path,
            universe_mode=None if args.universe_mode == "config" else args.universe_mode,
            reference_capital_usd=args.reference_capital_usd,
            pit_min_lifetime_valid_days=args.pit_min_lifetime_valid_days,
        )
    try:
        report = run_binance_canonical_validation(
            store_root=args.store_root,
            as_of=args.as_of,
            strategy_label=args.strategy_label,
            config_path=config_path,
            funding_root=args.funding_root,
            backfill_funding=args.backfill_funding,
            force_funding=args.force_funding,
            output_root=args.output_root,
            report_root=args.report_root,
            symbols=args.symbols,
            max_symbols=args.max_symbols,
            top_n=args.top_n,
            start_month=args.start_month,
            end_month=args.end_month,
            run_id=args.run_id,
            write_outputs=not args.no_write,
        )
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(_summary(report), indent=2, sort_keys=True))
    return 0


def _load_config_override(
    config_path: Path,
    *,
    universe_mode: str | None = None,
    reference_capital_usd: float | None = None,
    pit_min_lifetime_valid_days: int | None = None,
) -> Path:
    from enhengclaw.quant_research.binance_canonical_h10d import load_strategy_config

    config = load_strategy_config(config_path)
    if universe_mode is not None:
        universe_policy = dict(config.get("universe_policy") or {})
        universe_policy["selection_mode"] = universe_mode
        config["universe_policy"] = universe_policy
    if reference_capital_usd is not None:
        config["reference_capital_usd"] = float(reference_capital_usd)
    if pit_min_lifetime_valid_days is not None:
        pit_policy = dict(config.get("pit_data_eligibility_policy") or {})
        pit_policy["min_lifetime_valid_days"] = int(pit_min_lifetime_valid_days)
        config["pit_data_eligibility_policy"] = pit_policy
    temp_path = Path("artifacts") / "quant_research" / "binance_canonical_h10d" / "_runtime_config_override.json"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    return temp_path


def _summary(report: dict) -> dict:
    return {
        "status": report.get("status"),
        "strategy_label": report.get("strategy_label"),
        "parent_label": report.get("parent_label"),
        "blockers": report.get("blockers", []),
        "scored_row_count": report.get("scored_row_count"),
        "metrics": report.get("metrics", {}),
        "attribution": report.get("attribution", {}),
        "factor_attribution": report.get("factor_attribution", {}),
        "paper_shadow_execution": report.get("paper_shadow_execution", {}),
        "ablations": report.get("ablations", {}),
        "gate_results": report.get("gate_results", {}),
        "funding_cost_status": report.get("funding_cost_status", {}),
        "funding_cost_sync_summary": report.get("funding_cost_sync_summary"),
        "artifact_paths": report.get("artifact_paths", {}),
    }


if __name__ == "__main__":
    raise SystemExit(main())
