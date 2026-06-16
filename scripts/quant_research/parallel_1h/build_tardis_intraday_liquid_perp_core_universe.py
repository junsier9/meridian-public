from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_VERSION = "quant_tardis_intraday_liquid_perp_core_universe.v1"
RESEARCH_ID = "tardis_intraday_liquid_perp_core_universe_v1"
DEFAULT_AS_OF = "2026-06-16-intraday-liquid-perp-core-v1"
DEFAULT_EXCHANGE = "binance-futures"
DEFAULT_PROOF_FROM_DATE = "2026-06-01"
DEFAULT_PROOF_TO_DATE = "2026-06-13"
DEFAULT_DATA_TYPES = (
    "trades",
    "liquidations",
    "book_ticker",
    "book_snapshot_5",
    "derivative_ticker",
)
DEFAULT_OUTPUT_SUBDIR = "intraday_liquid_perp_core_universe"
DEFAULT_BUCKET_TARGETS = "top_liquidity=8,mid_liquidity=8,tail_liquidity=4"
ANCHOR_SYMBOLS = ("BTCUSDT", "ETHUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze a PIT liquid-perp core universe for Tardis-backed intraday "
            "research. This writes universe/proof-scope artifacts only and does "
            "not download data, run Stage A, compute strategy PnL, or create "
            "trading actions."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--source-universe", type=Path, default=None)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--proof-from-date", default=DEFAULT_PROOF_FROM_DATE)
    parser.add_argument("--proof-to-date", default=DEFAULT_PROOF_TO_DATE)
    parser.add_argument("--target-symbols", type=int, default=20)
    parser.add_argument("--min-symbols", type=int, default=12)
    parser.add_argument("--min-non-btc-eth-symbols", type=int, default=8)
    parser.add_argument("--min-liquidity-buckets", type=int, default=3)
    parser.add_argument("--distinct-months-min", type=int, default=18)
    parser.add_argument("--min-listing-age-days", type=int, default=180)
    parser.add_argument("--bucket-targets", default=DEFAULT_BUCKET_TARGETS)
    parser.add_argument("--raw-root", default="/data/meridian/hot_stage/tardis_intraday_liquidity_shock")
    parser.add_argument(
        "--normalized-root",
        default="/data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar",
    )
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_date(text: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {text!r}") from exc


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def latest_source_universe() -> Path:
    root = ROOT / "artifacts" / "quant_research" / "_quant_inputs"
    candidates = sorted(root.glob("pit-liquidity-top100-*.quant_universe.json"))
    if candidates:
        return candidates[-1]
    return root / "pit-liquidity-top100-2026-05-31.quant_universe.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def finite_float(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def normalize_symbol(value: Any) -> str | None:
    if value is None:
        return None
    symbol = str(value).strip().upper()
    if not symbol:
        return None
    return symbol if symbol.endswith("USDT") else f"{symbol}USDT"


def parse_timestamp_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def parse_bucket_targets(text: str) -> dict[str, int]:
    targets: dict[str, int] = {}
    for item in str(text).split(","):
        token = item.strip()
        if not token:
            continue
        if "=" not in token:
            raise argparse.ArgumentTypeError(f"invalid bucket target token: {token!r}")
        key, value = token.split("=", 1)
        bucket = key.strip()
        count = int(value.strip())
        if not bucket or count < 0:
            raise argparse.ArgumentTypeError(f"invalid bucket target token: {token!r}")
        targets[bucket] = count
    if not targets:
        raise argparse.ArgumentTypeError("--bucket-targets must not be empty")
    return targets


def selection_rank(candidate: dict[str, Any]) -> int:
    try:
        return int(candidate.get("selection_rank"))
    except (TypeError, ValueError):
        return 1_000_000


def sort_key(candidate: dict[str, Any]) -> tuple[int, float, str]:
    median = finite_float(candidate.get("rolling_median_quote_volume_usd_30d")) or 0.0
    symbol = normalize_symbol(candidate.get("usdm_symbol")) or normalize_symbol(candidate.get("spot_symbol")) or ""
    return (selection_rank(candidate), -median, symbol)


def candidate_symbol(candidate: dict[str, Any]) -> str | None:
    return normalize_symbol(candidate.get("usdm_symbol"))


def display_symbol(candidate: dict[str, Any]) -> str | None:
    return (
        candidate_symbol(candidate)
        or normalize_symbol(candidate.get("spot_symbol"))
        or normalize_symbol(candidate.get("subject"))
    )


def candidate_bucket(candidate: dict[str, Any]) -> str:
    return str(candidate.get("liquidity_bucket") or "unbucketed")


def candidate_exclusion_reason(
    candidate: dict[str, Any],
    *,
    proof_from_date: date,
    min_listing_age_days: int,
) -> str | None:
    symbol = candidate_symbol(candidate)
    if bool(candidate.get("is_stablecoin")):
        return "stablecoin"
    if bool(candidate.get("is_pegged_asset")):
        return "pegged_asset"
    if symbol is None:
        return "missing_usdm_symbol"
    if not symbol.endswith("USDT"):
        return "non_usdt_perp"
    listing_age = finite_float(candidate.get("listing_age_days_as_of"))
    if listing_age is None or listing_age < min_listing_age_days:
        return "listing_age_below_minimum"
    median = finite_float(candidate.get("rolling_median_quote_volume_usd_30d"))
    if median is None or median <= 0:
        return "missing_or_nonpositive_liquidity_metric"
    first_perp_date = parse_timestamp_date(candidate.get("first_perp_bar_utc"))
    if first_perp_date is None:
        return "missing_first_perp_bar"
    if first_perp_date > proof_from_date:
        return "first_perp_after_proof_start"
    return None


def select_universe(
    candidates: list[dict[str, Any]],
    *,
    proof_from_date: date,
    target_symbols: int,
    min_listing_age_days: int,
    bucket_targets: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for candidate in sorted(candidates, key=sort_key):
        reason = candidate_exclusion_reason(
            candidate,
            proof_from_date=proof_from_date,
            min_listing_age_days=min_listing_age_days,
        )
        symbol = candidate_symbol(candidate)
        audit_symbol = display_symbol(candidate)
        if symbol and symbol in seen_symbols:
            reason = reason or "duplicate_usdm_symbol"
        if reason:
            excluded.append({"candidate": candidate, "symbol": audit_symbol, "exclude_reason": reason})
            if symbol:
                seen_symbols.add(symbol)
            continue
        assert symbol is not None
        seen_symbols.add(symbol)
        eligible.append(candidate)

    selected_by_symbol: dict[str, dict[str, Any]] = {}
    include_reasons: dict[str, str] = {}

    def add_candidate(candidate: dict[str, Any], reason: str) -> None:
        symbol = candidate_symbol(candidate)
        if symbol is None or symbol in selected_by_symbol:
            return
        if len(selected_by_symbol) >= target_symbols:
            return
        selected_by_symbol[symbol] = candidate
        include_reasons[symbol] = reason

    for anchor in ANCHOR_SYMBOLS:
        for candidate in eligible:
            if candidate_symbol(candidate) == anchor:
                add_candidate(candidate, "required_anchor_symbol")
                break

    for bucket, target in bucket_targets.items():
        while sum(1 for item in selected_by_symbol.values() if candidate_bucket(item) == bucket) < target:
            before = len(selected_by_symbol)
            for candidate in eligible:
                if candidate_bucket(candidate) != bucket:
                    continue
                add_candidate(candidate, f"bucket_target_{bucket}")
                if len(selected_by_symbol) != before:
                    break
            if len(selected_by_symbol) == before:
                break

    for candidate in eligible:
        if len(selected_by_symbol) >= target_symbols:
            break
        add_candidate(candidate, "ranked_fill_after_bucket_targets")

    selected: list[dict[str, Any]] = []
    selected_symbols = set(selected_by_symbol)
    for candidate in sorted(selected_by_symbol.values(), key=sort_key):
        symbol = candidate_symbol(candidate)
        assert symbol is not None
        selected.append(
            {
                "symbol": symbol,
                "subject": str(candidate.get("subject") or symbol.replace("USDT", "")),
                "spot_symbol": normalize_symbol(candidate.get("spot_symbol")),
                "usdm_symbol": symbol,
                "selection_rank": selection_rank(candidate),
                "liquidity_bucket": candidate_bucket(candidate),
                "rolling_median_quote_volume_usd_30d": finite_float(
                    candidate.get("rolling_median_quote_volume_usd_30d")
                ),
                "rolling_mean_quote_volume_usd_30d": finite_float(
                    candidate.get("rolling_mean_quote_volume_usd_30d")
                ),
                "listing_age_days_as_of": finite_float(candidate.get("listing_age_days_as_of")),
                "first_perp_bar_utc": candidate.get("first_perp_bar_utc"),
                "selection_window_start_utc": candidate.get("selection_window_start_utc"),
                "selection_window_end_utc": candidate.get("selection_window_end_utc"),
                "include_reason": include_reasons.get(symbol, "selected"),
                "field_provenance": candidate.get("field_provenance"),
            }
        )

    selected_candidate_ids = {candidate_symbol(candidate) for candidate in selected_by_symbol.values()}
    for candidate in eligible:
        symbol = candidate_symbol(candidate)
        if symbol not in selected_candidate_ids:
            excluded.append(
                {
                    "candidate": candidate,
                    "symbol": display_symbol(candidate),
                    "exclude_reason": "eligible_ranked_beyond_target",
                }
            )
    return selected, eligible, excluded


def distinct_months(dates: list[date]) -> list[str]:
    return sorted({f"{current:%Y-%m}" for current in dates})


def build_staging_plan(
    *,
    selected: list[dict[str, Any]],
    exchange: str,
    dates: list[date],
    data_types: tuple[str, ...],
    raw_root: str,
    normalized_root: str,
) -> dict[str, Any]:
    symbols = [item["symbol"] for item in selected]
    months = distinct_months(dates)
    anchor_count = len([symbol for symbol in symbols if symbol in ANCHOR_SYMBOLS])
    expected_raw = len(symbols) * len(data_types) * len(dates)
    expected_columnar = len(symbols) * len(dates)
    by_symbol = {
        symbol: {
            "expected_raw_partitions": len(data_types) * len(dates),
            "expected_columnar_partitions": len(dates),
            "is_anchor_symbol": symbol in ANCHOR_SYMBOLS,
        }
        for symbol in symbols
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "exchange": exchange,
        "symbols": symbols,
        "data_types": list(data_types),
        "from_date": dates[0].isoformat() if dates else None,
        "to_date": dates[-1].isoformat() if dates else None,
        "calendar_day_count": len(dates),
        "distinct_months": months,
        "distinct_month_count": len(months),
        "raw_root": raw_root,
        "normalized_root": normalized_root,
        "raw_partition_template": (
            f"{raw_root}/raw/{exchange}/{{data_type}}/{{YYYY}}/{{MM}}/{{DD}}/{{symbol}}.csv.gz"
        ),
        "normalized_partition_template": (
            f"{normalized_root}/bar_features/exchange={exchange}/symbol={{symbol}}/"
            "year={YYYY}/month={MM}/date={YYYY}-{MM}-{DD}.parquet"
        ),
        "expected_raw_partition_count": expected_raw,
        "expected_columnar_partition_count": expected_columnar,
        "expected_partition_counts_by_symbol": by_symbol,
        "tier0_anchor_symbols_included": [symbol for symbol in symbols if symbol in ANCHOR_SYMBOLS],
        "expected_tier0_anchor_raw_partitions_for_same_window": anchor_count * len(data_types) * len(dates),
        "expected_incremental_raw_partitions_beyond_btc_eth": (
            max(0, len(symbols) - anchor_count) * len(data_types) * len(dates)
        ),
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
    }


def write_selected_csv(path: Path, selected: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "subject",
        "spot_symbol",
        "usdm_symbol",
        "selection_rank",
        "liquidity_bucket",
        "rolling_median_quote_volume_usd_30d",
        "rolling_mean_quote_volume_usd_30d",
        "listing_age_days_as_of",
        "first_perp_bar_utc",
        "selection_window_start_utc",
        "selection_window_end_utc",
        "include_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in selected:
            writer.writerow({key: item.get(key) for key in fieldnames})


def source_as_of_date(payload: dict[str, Any]) -> date | None:
    return parse_timestamp_date(payload.get("as_of"))


def gate_report(
    *,
    selected: list[dict[str, Any]],
    source_payload: dict[str, Any],
    proof_from_date: date,
    proof_months: list[str],
    min_symbols: int,
    min_non_btc_eth_symbols: int,
    min_liquidity_buckets: int,
    distinct_months_min: int,
) -> dict[str, Any]:
    symbols = [item["symbol"] for item in selected]
    non_btc_eth = [symbol for symbol in symbols if symbol not in ANCHOR_SYMBOLS]
    buckets = sorted({str(item["liquidity_bucket"]) for item in selected})
    source_date = source_as_of_date(source_payload)
    source_before_proof = source_date is not None and source_date < proof_from_date
    gates = {
        "symbols_total_min": {
            "passed": len(symbols) >= min_symbols,
            "observed": len(symbols),
            "required": min_symbols,
        },
        "non_btc_eth_symbols_min": {
            "passed": len(non_btc_eth) >= min_non_btc_eth_symbols,
            "observed": len(non_btc_eth),
            "required": min_non_btc_eth_symbols,
        },
        "distinct_liquidity_buckets_min": {
            "passed": len(buckets) >= min_liquidity_buckets,
            "observed": len(buckets),
            "required": min_liquidity_buckets,
            "buckets": buckets,
        },
        "anchor_symbols_present": {
            "passed": all(anchor in symbols for anchor in ANCHOR_SYMBOLS),
            "observed": [anchor for anchor in ANCHOR_SYMBOLS if anchor in symbols],
            "required": list(ANCHOR_SYMBOLS),
        },
        "source_universe_before_proof_start": {
            "passed": source_before_proof,
            "observed": source_payload.get("as_of"),
            "required": f"< {proof_from_date.isoformat()}",
        },
        "distinct_months_with_planned_staging_min": {
            "passed": len(proof_months) >= distinct_months_min,
            "observed": len(proof_months),
            "required": distinct_months_min,
            "months": proof_months,
        },
        "source_universe_candidate_pool_complete": {
            "passed": bool(source_payload.get("top100_complete", True)),
            "observed": source_payload.get("top100_complete"),
            "required": True,
            "warning_only": True,
        },
    }
    universe_blockers = [
        name
        for name in (
            "symbols_total_min",
            "non_btc_eth_symbols_min",
            "distinct_liquidity_buckets_min",
            "anchor_symbols_present",
        )
        if not gates[name]["passed"]
    ]
    historical_stage_a_blockers = [
        name
        for name in (
            "source_universe_before_proof_start",
            "distinct_months_with_planned_staging_min",
        )
        if not gates[name]["passed"]
    ]
    return {
        "gates": gates,
        "universe_contract_blockers": universe_blockers,
        "historical_stage_a_scope_blockers": historical_stage_a_blockers,
        "warning_only_blockers": [
            name for name, payload in gates.items() if payload.get("warning_only") and not payload["passed"]
        ],
    }


def main() -> int:
    args = parse_args()
    proof_from_date = parse_iso_date(args.proof_from_date)
    proof_to_date = parse_iso_date(args.proof_to_date)
    if proof_to_date < proof_from_date:
        raise SystemExit("--proof-to-date must be >= --proof-from-date")
    if args.target_symbols < 1:
        raise SystemExit("--target-symbols must be positive")
    if args.min_symbols < 1:
        raise SystemExit("--min-symbols must be positive")
    if args.min_symbols > args.target_symbols:
        raise SystemExit("--min-symbols must be <= --target-symbols")

    source_path = args.source_universe.expanduser().resolve() if args.source_universe else latest_source_universe()
    if not source_path.exists():
        raise SystemExit(f"source universe not found: {source_path}")
    source_payload = load_json(source_path)
    source_sha256 = sha256_file(source_path)
    source_candidates = list(source_payload.get("candidates") or [])
    bucket_targets = parse_bucket_targets(args.bucket_targets)

    selected, eligible, excluded = select_universe(
        source_candidates,
        proof_from_date=proof_from_date,
        target_symbols=int(args.target_symbols),
        min_listing_age_days=int(args.min_listing_age_days),
        bucket_targets=bucket_targets,
    )
    dates = date_range(proof_from_date, proof_to_date)
    proof_months = distinct_months(dates)
    report = gate_report(
        selected=selected,
        source_payload=source_payload,
        proof_from_date=proof_from_date,
        proof_months=proof_months,
        min_symbols=int(args.min_symbols),
        min_non_btc_eth_symbols=int(args.min_non_btc_eth_symbols),
        min_liquidity_buckets=int(args.min_liquidity_buckets),
        distinct_months_min=int(args.distinct_months_min),
    )

    universe_blockers = report["universe_contract_blockers"]
    historical_blockers = report["historical_stage_a_scope_blockers"]
    if universe_blockers:
        status = "frozen_failed_universe_contract"
    elif historical_blockers:
        status = "frozen_scope_passed_historical_stage_a_blocked"
    else:
        status = "frozen_scope_passed_stage_a_ready"

    output_root = args.output_root
    if output_root is None:
        output_root = (
            ROOT
            / "artifacts"
            / "quant_research"
            / "factor_reports"
            / str(args.as_of)
            / DEFAULT_OUTPUT_SUBDIR
        )
    output_root.mkdir(parents=True, exist_ok=True)

    selection_path = output_root / "intraday_liquid_perp_core_universe_selection.json"
    symbols_csv_path = output_root / "intraday_liquid_perp_core_universe_symbols.csv"
    staging_plan_path = output_root / "intraday_liquid_perp_core_universe_staging_plan.json"
    summary_path = output_root / "intraday_liquid_perp_core_universe_summary.json"

    staging_plan = build_staging_plan(
        selected=selected,
        exchange=str(args.exchange),
        dates=dates,
        data_types=DEFAULT_DATA_TYPES,
        raw_root=str(args.raw_root).rstrip("/"),
        normalized_root=str(args.normalized_root).rstrip("/"),
    )
    selection_payload = {
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "exchange": str(args.exchange),
        "source_universe_path": str(source_path),
        "source_universe_sha256": source_sha256,
        "source_universe_as_of": source_payload.get("as_of"),
        "source_universe_contract_version": source_payload.get("contract_version"),
        "source_universe_definition_id": source_payload.get("universe_definition_id"),
        "source_universe_top100_complete": source_payload.get("top100_complete"),
        "selection_policy": {
            "input_source": "retained_pit_liquidity_universe",
            "target_symbols": int(args.target_symbols),
            "min_symbols": int(args.min_symbols),
            "min_non_btc_eth_symbols": int(args.min_non_btc_eth_symbols),
            "min_liquidity_buckets": int(args.min_liquidity_buckets),
            "min_listing_age_days": int(args.min_listing_age_days),
            "bucket_targets": bucket_targets,
            "required_anchor_symbols": list(ANCHOR_SYMBOLS),
            "forbidden_inputs": [
                "forward_returns",
                "event_labels",
                "strategy_outcomes",
                "post_event_response_variables",
            ],
        },
        "proof_window": {
            "from_date": proof_from_date.isoformat(),
            "to_date": proof_to_date.isoformat(),
            "distinct_months": proof_months,
        },
        "selected": selected,
        "eligible_count": len(eligible),
        "excluded": excluded,
        "gate_report": report,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
    }
    write_json(selection_path, selection_payload)
    write_selected_csv(symbols_csv_path, selected)
    write_json(staging_plan_path, staging_plan)

    artifacts = {
        "selection_json": str(selection_path),
        "symbols_csv": str(symbols_csv_path),
        "staging_plan_json": str(staging_plan_path),
        "summary_json": str(summary_path),
    }
    symbols = [item["symbol"] for item in selected]
    summary = {
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "status": status,
        "result_scope": "pit_frozen_universe_and_staging_plan_only",
        "exchange": str(args.exchange),
        "source_universe_path": str(source_path),
        "source_universe_sha256": source_sha256,
        "source_universe_as_of": source_payload.get("as_of"),
        "selected_symbol_count": len(symbols),
        "selected_symbols": symbols,
        "non_btc_eth_symbol_count": len([symbol for symbol in symbols if symbol not in ANCHOR_SYMBOLS]),
        "liquidity_buckets": sorted({str(item["liquidity_bucket"]) for item in selected}),
        "proof_window": {
            "from_date": proof_from_date.isoformat(),
            "to_date": proof_to_date.isoformat(),
            "distinct_month_count": len(proof_months),
            "distinct_months": proof_months,
        },
        "stage_a_universe_scope_ready": not bool(universe_blockers),
        "historical_stage_a_scope_ready": not bool(universe_blockers or historical_blockers),
        "generalized_intraday_baseline_allowed": False,
        "proof_allowed": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
        "remote_runner_use_authorized": False,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
        "universe_contract_blockers": universe_blockers,
        "historical_stage_a_scope_blockers": historical_blockers,
        "warning_only_blockers": report["warning_only_blockers"],
        "gate_report": report,
        "staging_plan": {
            "expected_raw_partition_count": staging_plan["expected_raw_partition_count"],
            "expected_columnar_partition_count": staging_plan["expected_columnar_partition_count"],
            "expected_incremental_raw_partitions_beyond_btc_eth": staging_plan[
                "expected_incremental_raw_partitions_beyond_btc_eth"
            ],
            "data_types": staging_plan["data_types"],
            "calendar_day_count": staging_plan["calendar_day_count"],
        },
        "artifacts": artifacts,
    }
    write_json(summary_path, summary)
    print(
        json.dumps(
            {
                "status": status,
                "selected_symbol_count": len(symbols),
                "selected_symbols": symbols,
                "stage_a_universe_scope_ready": summary["stage_a_universe_scope_ready"],
                "historical_stage_a_scope_ready": summary["historical_stage_a_scope_ready"],
                "proof_allowed": False,
                "stage_a_proof_computed": False,
                "stage_b_return_ablation_allowed": False,
                "strategy_pnl_computed": False,
                "trading_action_authorized": False,
                "downloads_executed_by_runner": False,
                "raw_scan_executed_by_runner": False,
                "blockers": universe_blockers + historical_blockers,
                "summary_json": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
