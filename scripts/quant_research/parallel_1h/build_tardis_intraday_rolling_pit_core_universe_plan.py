from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_ID = "rolling_pit_intraday_liquid_perp_core_v1"
CONTRACT_VERSION = "quant_tardis_intraday_rolling_pit_core_universe_plan.v1"
RESEARCH_ID = "rolling_pit_intraday_liquid_perp_core_v1"
DEFAULT_AS_OF = "2026-06-16-rolling-pit-core-v1-dry-run"
DEFAULT_EXCHANGE = "binance-futures"
DEFAULT_EVALUATION_FROM_MONTH = "2025-01"
DEFAULT_EVALUATION_TO_MONTH = "2026-06"
DEFAULT_LATEST_PARTIAL_MONTH_END = "2026-06-13"
DEFAULT_SELECTION_LOOKBACK_DAYS = 90
DEFAULT_SELECTION_LOOKBACK_MIN_DAYS = 30
DEFAULT_SELECTION_DATA_TYPES = (
    "trades",
    "book_ticker",
    "book_snapshot_5",
    "derivative_ticker",
)
DEFAULT_STAGE_A_DATA_TYPES = (
    "trades",
    "liquidations",
    "book_ticker",
    "book_snapshot_5",
    "derivative_ticker",
)
DEFAULT_BUCKET_TARGETS = "top_liquidity=8,mid_liquidity=8,tail_liquidity=4"
DEFAULT_STORAGE_RAW_ROOT = "/tank/tardis/raw_stores/tardis_intraday_liquidity_shock"
DEFAULT_COMPUTE_RAW_ROOT = "/data/meridian/hot_stage/tardis_intraday_liquidity_shock"
DEFAULT_NORMALIZED_ROOT = (
    "/data/meridian/hot_stage/"
    "tardis_intraday_liquidity_shock_columnar_rolling_pit_core_v1"
)
DEFAULT_OUTPUT_SUBDIR = "rolling_pit_core_universe"
ANCHOR_SYMBOLS = ("BTCUSDT", "ETHUSDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize rolling PIT monthly freeze artifacts and a dry-run "
            "Tardis staging plan. This runner never downloads Tardis data, "
            "normalizes parquet, runs Stage A, computes strategy PnL, or "
            "creates trading actions."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--source-universe", type=Path, default=None)
    parser.add_argument(
        "--candidate-symbols",
        default="",
        help="Optional comma-separated USDT perp symbols for dry-run candidate seed planning.",
    )
    parser.add_argument("--candidate-seed-limit", type=int, default=100)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--evaluation-from-month", default=DEFAULT_EVALUATION_FROM_MONTH)
    parser.add_argument("--evaluation-to-month", default=DEFAULT_EVALUATION_TO_MONTH)
    parser.add_argument("--latest-partial-month-end", default=DEFAULT_LATEST_PARTIAL_MONTH_END)
    parser.add_argument("--selection-lookback-days", type=int, default=DEFAULT_SELECTION_LOOKBACK_DAYS)
    parser.add_argument(
        "--selection-lookback-min-days",
        type=int,
        default=DEFAULT_SELECTION_LOOKBACK_MIN_DAYS,
    )
    parser.add_argument("--target-symbols", type=int, default=20)
    parser.add_argument("--min-symbols", type=int, default=12)
    parser.add_argument("--min-non-btc-eth-symbols", type=int, default=8)
    parser.add_argument("--min-liquidity-buckets", type=int, default=3)
    parser.add_argument("--distinct-months-min", type=int, default=18)
    parser.add_argument("--bucket-targets", default=DEFAULT_BUCKET_TARGETS)
    parser.add_argument(
        "--selection-data-types",
        default=",".join(DEFAULT_SELECTION_DATA_TYPES),
    )
    parser.add_argument("--stage-a-data-types", default=",".join(DEFAULT_STAGE_A_DATA_TYPES))
    parser.add_argument("--storage-raw-root", default=DEFAULT_STORAGE_RAW_ROOT)
    parser.add_argument("--compute-raw-root", default=DEFAULT_COMPUTE_RAW_ROOT)
    parser.add_argument("--normalized-root", default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument(
        "--partition-plan-detail",
        choices=("summary", "full"),
        default="summary",
        help="summary writes aggregate counts and samples; full materializes every planned partition record.",
    )
    parser.add_argument("--partition-sample-limit", type=int, default=100)
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_date(text: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {text!r}") from exc


def parse_month(text: str) -> tuple[int, int]:
    try:
        year_text, month_text = str(text).split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid YYYY-MM month: {text!r}") from exc
    if month < 1 or month > 12:
        raise argparse.ArgumentTypeError(f"invalid YYYY-MM month: {text!r}")
    return year, month


def month_key(value: date | tuple[int, int]) -> str:
    if isinstance(value, date):
        return f"{value.year:04d}-{value.month:02d}"
    year, month = value
    return f"{year:04d}-{month:02d}"


def month_start(value: tuple[int, int]) -> date:
    return date(value[0], value[1], 1)


def month_end(value: tuple[int, int]) -> date:
    year, month = value
    return date(year, month, calendar.monthrange(year, month)[1])


def next_month(value: tuple[int, int]) -> tuple[int, int]:
    year, month = value
    if month == 12:
        return year + 1, 1
    return year, month + 1


def iter_months(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    if start > end:
        raise argparse.ArgumentTypeError("evaluation-from-month must be <= evaluation-to-month")
    months: list[tuple[int, int]] = []
    current = start
    while current <= end:
        months.append(current)
        current = next_month(current)
    return months


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


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


def split_csv_arg(text: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in str(text).split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("comma-separated argument must not be empty")
    return values


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


def liquidity_bucket_for_rank(rank: int) -> str:
    if rank <= 20:
        return "top_liquidity"
    if rank <= 50:
        return "mid_liquidity"
    return "tail_liquidity"


def candidate_bucket(candidate: dict[str, Any]) -> str:
    bucket = str(candidate.get("liquidity_bucket") or "").strip()
    return bucket or liquidity_bucket_for_rank(selection_rank(candidate))


def candidate_symbol(candidate: dict[str, Any]) -> str | None:
    return normalize_symbol(candidate.get("usdm_symbol"))


def display_symbol(candidate: dict[str, Any]) -> str | None:
    return (
        candidate_symbol(candidate)
        or normalize_symbol(candidate.get("spot_symbol"))
        or normalize_symbol(candidate.get("subject"))
    )


def candidate_subject(candidate: dict[str, Any], symbol: str) -> str:
    subject = str(candidate.get("subject") or "").strip().upper()
    if subject:
        return subject
    return symbol.removesuffix("USDT")


def sort_key(candidate: dict[str, Any]) -> tuple[int, float, str]:
    median = finite_float(candidate.get("rolling_median_quote_volume_usd_30d")) or 0.0
    symbol = display_symbol(candidate) or ""
    return (selection_rank(candidate), -median, symbol)


def synthetic_candidate(symbol: str, rank: int) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    assert normalized is not None
    subject = normalized.removesuffix("USDT")
    return {
        "subject": subject,
        "spot_symbol": normalized,
        "usdm_symbol": normalized,
        "selection_rank": rank,
        "rolling_median_quote_volume_usd_30d": None,
        "rolling_mean_quote_volume_usd_30d": None,
        "liquidity_bucket": liquidity_bucket_for_rank(rank),
        "field_provenance": {"candidate_symbols_arg": True},
    }


def load_candidate_source(args: argparse.Namespace) -> tuple[dict[str, Any], str | None]:
    if args.candidate_symbols.strip():
        symbols = [symbol for symbol in split_csv_arg(args.candidate_symbols)]
        candidates = [synthetic_candidate(symbol, index + 1) for index, symbol in enumerate(symbols)]
        payload = {
            "as_of": args.as_of,
            "contract_version": "manual_candidate_symbol_seed.v1",
            "universe_definition_id": "manual_candidate_symbol_seed",
            "top100_complete": False,
            "input_provenance": {
                "mode": "manual_candidate_symbols_arg",
                "pit_valid_for_historical_monthly_selection": False,
            },
            "candidates": candidates,
        }
        return payload, None

    source_path = args.source_universe or latest_source_universe()
    payload = load_json(source_path)
    return payload, str(source_path)


def build_candidate_seed(
    payload: dict[str, Any],
    *,
    candidate_seed_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in sorted(payload.get("candidates", []), key=sort_key):
        symbol = candidate_symbol(candidate)
        display = display_symbol(candidate)
        reason: str | None = None
        if symbol is None:
            reason = "missing_usdm_symbol"
        elif bool(candidate.get("is_stablecoin")):
            reason = "stablecoin"
        elif bool(candidate.get("is_pegged_asset")):
            reason = "pegged_asset"
        elif symbol in seen:
            reason = "duplicate_usdm_symbol"

        if reason is not None:
            excluded.append(
                {
                    "symbol": display,
                    "exclude_reason": reason,
                    "candidate": candidate,
                }
            )
            continue

        assert symbol is not None
        seen.add(symbol)
        eligible.append(candidate)
        if len(eligible) >= candidate_seed_limit:
            break

    return eligible, excluded


def add_proxy_candidate(
    selected_by_symbol: dict[str, dict[str, Any]],
    include_reasons: dict[str, str],
    candidate: dict[str, Any],
    *,
    reason: str,
    target_symbols: int,
) -> None:
    symbol = candidate_symbol(candidate)
    if symbol is None or symbol in selected_by_symbol or len(selected_by_symbol) >= target_symbols:
        return
    selected_by_symbol[symbol] = candidate
    include_reasons[symbol] = reason


def proxy_select_candidates(
    candidates: list[dict[str, Any]],
    *,
    target_symbols: int,
    bucket_targets: dict[str, int],
) -> list[dict[str, Any]]:
    selected_by_symbol: dict[str, dict[str, Any]] = {}
    include_reasons: dict[str, str] = {}

    for anchor in ANCHOR_SYMBOLS:
        for candidate in candidates:
            if candidate_symbol(candidate) == anchor:
                add_proxy_candidate(
                    selected_by_symbol,
                    include_reasons,
                    candidate,
                    reason="dry_run_proxy_required_anchor_symbol",
                    target_symbols=target_symbols,
                )
                break

    for bucket, target in bucket_targets.items():
        while sum(1 for item in selected_by_symbol.values() if candidate_bucket(item) == bucket) < target:
            before = len(selected_by_symbol)
            for candidate in candidates:
                if candidate_bucket(candidate) != bucket:
                    continue
                add_proxy_candidate(
                    selected_by_symbol,
                    include_reasons,
                    candidate,
                    reason=f"dry_run_proxy_bucket_target_{bucket}",
                    target_symbols=target_symbols,
                )
                if len(selected_by_symbol) != before:
                    break
            if len(selected_by_symbol) == before:
                break

    for candidate in candidates:
        if len(selected_by_symbol) >= target_symbols:
            break
        add_proxy_candidate(
            selected_by_symbol,
            include_reasons,
            candidate,
            reason="dry_run_proxy_ranked_fill_after_bucket_targets",
            target_symbols=target_symbols,
        )

    selected: list[dict[str, Any]] = []
    for candidate in sorted(selected_by_symbol.values(), key=sort_key):
        symbol = candidate_symbol(candidate)
        assert symbol is not None
        selected.append(
            {
                "symbol": symbol,
                "subject": candidate_subject(candidate, symbol),
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
                "selection_basis": "dry_run_proxy_not_stage_a_eligible",
                "stage_a_eligible": False,
                "include_reason": include_reasons.get(symbol, "dry_run_proxy_selected"),
            }
        )
    return selected


def candidate_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        symbol = candidate_symbol(candidate)
        if symbol is None:
            continue
        rows.append(
            {
                "symbol": symbol,
                "subject": candidate_subject(candidate, symbol),
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
                "stage_a_eligible": False,
                "selection_basis": "candidate_seed_for_dry_run_partition_planning",
            }
        )
    return rows


def monthly_plan(
    month: tuple[int, int],
    *,
    latest_partial_month_end: date,
    selection_lookback_days: int,
) -> dict[str, Any]:
    start = month_start(month)
    end = min(month_end(month), latest_partial_month_end) if month_key(month) == month_key(latest_partial_month_end) else month_end(month)
    if end < start:
        raise argparse.ArgumentTypeError(
            f"latest partial month end {latest_partial_month_end} is before evaluation month {month_key(month)}"
        )
    freeze_date = start - timedelta(days=1)
    lookback_start = freeze_date - timedelta(days=selection_lookback_days - 1)
    return {
        "evaluation_month": month_key(month),
        "freeze_date": freeze_date.isoformat(),
        "selection_lookback_start": lookback_start.isoformat(),
        "selection_lookback_end": freeze_date.isoformat(),
        "selection_lookback_day_count": selection_lookback_days,
        "evaluation_start": start.isoformat(),
        "evaluation_end": end.isoformat(),
        "evaluation_day_count": len(date_range(start, end)),
    }


def partition_record(
    *,
    exchange: str,
    data_type: str,
    symbol: str,
    current_date: date,
    storage_raw_root: str,
    compute_raw_root: str,
    roles: list[str],
) -> dict[str, Any]:
    yyyy = f"{current_date.year:04d}"
    mm = f"{current_date.month:02d}"
    dd = f"{current_date.day:02d}"
    rel = f"raw/{exchange}/{data_type}/{yyyy}/{mm}/{dd}/{symbol}.csv.gz"
    source_url = f"https://datasets.tardis.dev/v1/{exchange}/{data_type}/{yyyy}/{mm}/{dd}/{symbol}.csv.gz"
    return {
        "exchange": exchange,
        "data_type": data_type,
        "symbol": symbol,
        "date": current_date.isoformat(),
        "year": yyyy,
        "month": mm,
        "day": dd,
        "storage_path": f"{storage_raw_root.rstrip('/')}/{rel}",
        "compute_path": f"{compute_raw_root.rstrip('/')}/{rel}",
        "source_url_or_dataset_id_without_api_key": source_url,
        "download_status": "planned_not_downloaded",
        "raw_size_bytes": None,
        "raw_sha256": None,
        "usage_roles": sorted(roles),
    }


def add_partition_usage(
    partition_roles: dict[tuple[str, str, str, str], set[str]],
    *,
    exchange: str,
    data_type: str,
    symbol: str,
    current_date: date,
    role: str,
) -> None:
    key = (exchange, data_type, symbol, current_date.isoformat())
    partition_roles.setdefault(key, set()).add(role)


def build_raw_staging_manifest(
    *,
    months: list[dict[str, Any]],
    candidate_seed_symbols: list[str],
    exchange: str,
    selection_data_types: tuple[str, ...],
    stage_a_data_types: tuple[str, ...],
    storage_raw_root: str,
    compute_raw_root: str,
    detail: str,
    sample_limit: int,
) -> dict[str, Any]:
    partition_roles: dict[tuple[str, str, str, str], set[str]] = {}
    monthly_summaries: list[dict[str, Any]] = []
    non_dedup_count = 0

    for item in months:
        evaluation_month = item["evaluation_month"]
        selection_dates = date_range(
            parse_iso_date(item["selection_lookback_start"]),
            parse_iso_date(item["selection_lookback_end"]),
        )
        evaluation_dates = date_range(
            parse_iso_date(item["evaluation_start"]),
            parse_iso_date(item["evaluation_end"]),
        )
        selection_count = len(candidate_seed_symbols) * len(selection_dates) * len(selection_data_types)
        evaluation_count = len(candidate_seed_symbols) * len(evaluation_dates) * len(stage_a_data_types)
        non_dedup_count += selection_count + evaluation_count
        monthly_summaries.append(
            {
                "evaluation_month": evaluation_month,
                "candidate_seed_symbol_count": len(candidate_seed_symbols),
                "selection_lookback_start": item["selection_lookback_start"],
                "selection_lookback_end": item["selection_lookback_end"],
                "selection_data_types": list(selection_data_types),
                "selection_raw_partition_count": selection_count,
                "evaluation_start": item["evaluation_start"],
                "evaluation_end": item["evaluation_end"],
                "stage_a_data_types": list(stage_a_data_types),
                "evaluation_raw_partition_count": evaluation_count,
                "download_status": "planned_not_downloaded",
            }
        )

        for symbol in candidate_seed_symbols:
            for current_date in selection_dates:
                for data_type in selection_data_types:
                    add_partition_usage(
                        partition_roles,
                        exchange=exchange,
                        data_type=data_type,
                        symbol=symbol,
                        current_date=current_date,
                        role=f"selection_lookback:{evaluation_month}",
                    )
            for current_date in evaluation_dates:
                for data_type in stage_a_data_types:
                    add_partition_usage(
                        partition_roles,
                        exchange=exchange,
                        data_type=data_type,
                        symbol=symbol,
                        current_date=current_date,
                        role=f"evaluation:{evaluation_month}",
                    )

    by_data_type: dict[str, int] = {}
    by_symbol: dict[str, int] = {}
    by_month: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    for key, roles in sorted(partition_roles.items()):
        exchange_key, data_type, symbol, date_text = key
        current_date = parse_iso_date(date_text)
        by_data_type[data_type] = by_data_type.get(data_type, 0) + 1
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        by_month[month_key(current_date)] = by_month.get(month_key(current_date), 0) + 1
        if detail == "full" or len(records) < sample_limit:
            records.append(
                partition_record(
                    exchange=exchange_key,
                    data_type=data_type,
                    symbol=symbol,
                    current_date=current_date,
                    storage_raw_root=storage_raw_root,
                    compute_raw_root=compute_raw_root,
                    roles=list(roles),
                )
            )

    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "manifest_kind": "dry_run_raw_staging_plan_no_download",
        "exchange": exchange,
        "storage_raw_root": storage_raw_root,
        "compute_raw_root": compute_raw_root,
        "candidate_seed_symbols": candidate_seed_symbols,
        "candidate_seed_symbol_count": len(candidate_seed_symbols),
        "selection_data_types": list(selection_data_types),
        "stage_a_data_types": list(stage_a_data_types),
        "monthly_plans": monthly_summaries,
        "planned_non_dedup_raw_partition_count": non_dedup_count,
        "planned_unique_raw_partition_count": len(partition_roles),
        "planned_unique_raw_partition_count_by_data_type": dict(sorted(by_data_type.items())),
        "planned_unique_raw_partition_count_by_symbol": dict(sorted(by_symbol.items())),
        "planned_unique_raw_partition_count_by_calendar_month": dict(sorted(by_month.items())),
        "partition_records_materialized": detail == "full",
        "partition_sample_limit": sample_limit,
        "sample_partitions": records if detail == "summary" else records[:sample_limit],
        "partitions": records if detail == "full" else [],
        "raw_partition_template": (
            f"{storage_raw_root.rstrip('/')}/raw/{exchange}"
            "/{data_type}/{YYYY}/{MM}/{DD}/{symbol}.csv.gz"
        ),
        "dataset_url_template_without_api_key": (
            f"https://datasets.tardis.dev/v1/{exchange}"
            "/{data_type}/{YYYY}/{MM}/{DD}/{symbol}.csv.gz"
        ),
        "download_status": "planned_not_downloaded",
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
    }


def build_normalized_manifest_plan(
    *,
    months: list[dict[str, Any]],
    candidate_seed_symbols: list[str],
    proxy_selected_symbols: list[str],
    exchange: str,
    normalized_root: str,
) -> dict[str, Any]:
    monthly_plans: list[dict[str, Any]] = []
    candidate_seed_count = 0
    proxy_selected_count = 0
    for item in months:
        days = int(item["evaluation_day_count"])
        monthly_candidate_count = len(candidate_seed_symbols) * days
        monthly_proxy_count = len(proxy_selected_symbols) * days
        candidate_seed_count += monthly_candidate_count
        proxy_selected_count += monthly_proxy_count
        monthly_plans.append(
            {
                "evaluation_month": item["evaluation_month"],
                "evaluation_start": item["evaluation_start"],
                "evaluation_end": item["evaluation_end"],
                "evaluation_day_count": days,
                "candidate_seed_symbol_count": len(candidate_seed_symbols),
                "dry_run_proxy_selected_symbol_count": len(proxy_selected_symbols),
                "normalized_partition_count_if_candidate_seed_materialized": monthly_candidate_count,
                "normalized_partition_count_if_proxy_selection_materialized": monthly_proxy_count,
                "normalization_status": "planned_not_executed",
            }
        )
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "manifest_kind": "dry_run_normalized_columnar_plan_no_normalization",
        "exchange": exchange,
        "normalized_root": normalized_root,
        "monthly_plans": monthly_plans,
        "normalized_partition_template": (
            f"{normalized_root.rstrip('/')}/bar_features/exchange={exchange}/symbol={{symbol}}/"
            "year={YYYY}/month={MM}/date={YYYY}-{MM}-{DD}.parquet"
        ),
        "planned_candidate_seed_normalized_partition_count": candidate_seed_count,
        "planned_proxy_selected_normalized_partition_count": proxy_selected_count,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
    }


def gate_report(
    *,
    months: list[dict[str, Any]],
    candidate_seed_symbols: list[str],
    proxy_selected: list[dict[str, Any]],
    min_symbols: int,
    min_non_btc_eth_symbols: int,
    min_liquidity_buckets: int,
    distinct_months_min: int,
    selection_lookback_min_days: int,
) -> dict[str, Any]:
    non_btc_eth = [symbol for symbol in candidate_seed_symbols if symbol not in ANCHOR_SYMBOLS]
    buckets = sorted({str(item.get("liquidity_bucket")) for item in proxy_selected if item.get("liquidity_bucket")})
    lookback_days = [int(item["selection_lookback_day_count"]) for item in months]
    gates = {
        "evaluation_distinct_months_min": {
            "passed": len(months) >= distinct_months_min,
            "observed": len(months),
            "required": distinct_months_min,
            "months": [item["evaluation_month"] for item in months],
        },
        "candidate_seed_symbols_total_min": {
            "passed": len(candidate_seed_symbols) >= min_symbols,
            "observed": len(candidate_seed_symbols),
            "required": min_symbols,
        },
        "candidate_seed_non_btc_eth_symbols_min": {
            "passed": len(non_btc_eth) >= min_non_btc_eth_symbols,
            "observed": len(non_btc_eth),
            "required": min_non_btc_eth_symbols,
        },
        "dry_run_proxy_liquidity_buckets_min": {
            "passed": len(buckets) >= min_liquidity_buckets,
            "observed": len(buckets),
            "required": min_liquidity_buckets,
            "buckets": buckets,
        },
        "selection_lookback_days_min": {
            "passed": all(days >= selection_lookback_min_days for days in lookback_days),
            "observed_min": min(lookback_days) if lookback_days else 0,
            "required": selection_lookback_min_days,
        },
        "candidate_seed_pit_valid_for_historical_selection": {
            "passed": False,
            "observed": False,
            "required": True,
            "fail_closed_reason": "dry_run runner has no pre-freeze monthly raw metrics yet",
        },
        "monthly_raw_selection_metrics_present": {
            "passed": False,
            "observed": False,
            "required": True,
            "fail_closed_reason": "no Tardis download or raw scan is performed by this runner",
        },
        "stage_a_monthly_universe_masks_ready": {
            "passed": False,
            "observed": False,
            "required": True,
            "fail_closed_reason": "proxy selections are not Stage A eligible",
        },
    }
    blocking = [name for name, payload in gates.items() if not payload["passed"]]
    scope_only_green = [
        name
        for name, payload in gates.items()
        if payload["passed"] and not name.startswith(("candidate_seed_pit", "monthly_raw", "stage_a"))
    ]
    return {
        "gates": gates,
        "scope_only_green_gates": scope_only_green,
        "blocking_gates": blocking,
        "proof_allowed": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
    }


def relative_or_string(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def build_config_payload(args: argparse.Namespace, selection_data_types: tuple[str, ...], stage_a_data_types: tuple[str, ...]) -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "exchange": args.exchange,
        "evaluation_from_month": args.evaluation_from_month,
        "evaluation_to_month": args.evaluation_to_month,
        "latest_partial_month_end": args.latest_partial_month_end,
        "selection_lookback_days": args.selection_lookback_days,
        "selection_lookback_min_days": args.selection_lookback_min_days,
        "target_symbols": args.target_symbols,
        "min_symbols": args.min_symbols,
        "min_non_btc_eth_symbols": args.min_non_btc_eth_symbols,
        "min_liquidity_buckets": args.min_liquidity_buckets,
        "distinct_months_min": args.distinct_months_min,
        "bucket_targets": args.bucket_targets,
        "selection_data_types": list(selection_data_types),
        "stage_a_data_types": list(stage_a_data_types),
        "partition_plan_detail": args.partition_plan_detail,
        "dry_run_only": True,
    }


def write_monthly_artifacts(
    *,
    output_root: Path,
    months: list[dict[str, Any]],
    candidate_seed: list[dict[str, Any]],
    proxy_selected: list[dict[str, Any]],
    source_universe_path: str | None,
    source_universe_sha256: str | None,
    runner_sha256: str,
    selection_config_sha256: str,
) -> list[dict[str, Any]]:
    monthly_artifacts: list[dict[str, Any]] = []
    candidate_fieldnames = [
        "symbol",
        "subject",
        "spot_symbol",
        "usdm_symbol",
        "selection_rank",
        "liquidity_bucket",
        "rolling_median_quote_volume_usd_30d",
        "rolling_mean_quote_volume_usd_30d",
        "stage_a_eligible",
        "selection_basis",
    ]
    selected_fieldnames = [
        "symbol",
        "subject",
        "spot_symbol",
        "usdm_symbol",
        "selection_rank",
        "liquidity_bucket",
        "rolling_median_quote_volume_usd_30d",
        "rolling_mean_quote_volume_usd_30d",
        "selection_basis",
        "stage_a_eligible",
        "include_reason",
    ]
    candidate_table_rows = candidate_rows(candidate_seed)

    for item in months:
        month_dir = output_root / "monthly_freezes" / item["evaluation_month"]
        selection_audit_path = month_dir / "monthly_universe_selection_audit.json"
        selected_symbols_path = month_dir / "selected_symbols.csv"
        candidate_ranking_path = month_dir / "candidate_ranking.csv"
        hash_lineage_path = month_dir / "hash_lineage.json"
        write_csv(candidate_ranking_path, candidate_table_rows, candidate_fieldnames)
        write_csv(selected_symbols_path, proxy_selected, selected_fieldnames)

        audit_payload = {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "research_id": RESEARCH_ID,
            "artifact_kind": "monthly_universe_selection_audit",
            "evaluation_month": item["evaluation_month"],
            "freeze_date": item["freeze_date"],
            "selection_lookback_start": item["selection_lookback_start"],
            "selection_lookback_end": item["selection_lookback_end"],
            "selection_lookback_day_count": item["selection_lookback_day_count"],
            "evaluation_start": item["evaluation_start"],
            "evaluation_end": item["evaluation_end"],
            "selection_status": "dry_run_proxy_selection_not_pit_valid_pending_monthly_raw_metrics",
            "candidate_seed_symbol_count": len(candidate_table_rows),
            "dry_run_proxy_selected_symbol_count": len(proxy_selected),
            "selected_symbol_count_stage_a_eligible": 0,
            "stage_a_monthly_universe_mask_ready": False,
            "candidate_seed_pit_valid_for_historical_selection": False,
            "monthly_raw_selection_metrics_present": False,
            "dry_run_proxy_selected_symbols": [item["symbol"] for item in proxy_selected],
            "stage_a_eligible_selected_symbols": [],
            "fail_closed_reason": (
                "monthly PIT selection requires retained pre-freeze raw metrics; "
                "this dry-run runner writes plan artifacts only"
            ),
            "source_universe_path": source_universe_path,
            "source_universe_sha256": source_universe_sha256,
            "runner_sha256": runner_sha256,
            "selection_config_sha256": selection_config_sha256,
            "downloads_executed_by_runner": False,
            "raw_scan_executed_by_runner": False,
            "normalization_executed_by_runner": False,
            "stage_a_proof_computed": False,
            "stage_b_return_ablation_allowed": False,
            "strategy_pnl_computed": False,
            "trading_action_authorized": False,
            "live_or_timer_use_authorized": False,
        }
        write_json(selection_audit_path, audit_payload)
        lineage_payload = {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "evaluation_month": item["evaluation_month"],
            "source_universe_path": source_universe_path,
            "source_universe_sha256": source_universe_sha256,
            "runner_path": relative_or_string(Path(__file__)),
            "runner_sha256": runner_sha256,
            "selection_config_sha256": selection_config_sha256,
            "monthly_universe_selection_audit_sha256": sha256_file(selection_audit_path),
            "selected_symbols_csv_sha256": sha256_file(selected_symbols_path),
            "candidate_ranking_csv_sha256": sha256_file(candidate_ranking_path),
            "hash_lineage_self_sha256": None,
            "download_status": "planned_not_downloaded",
        }
        write_json(hash_lineage_path, lineage_payload)
        monthly_artifacts.append(
            {
                "evaluation_month": item["evaluation_month"],
                "freeze_date": item["freeze_date"],
                "selection_audit_path": relative_or_string(selection_audit_path),
                "selection_audit_sha256": sha256_file(selection_audit_path),
                "selected_symbols_path": relative_or_string(selected_symbols_path),
                "selected_symbols_sha256": sha256_file(selected_symbols_path),
                "candidate_ranking_path": relative_or_string(candidate_ranking_path),
                "candidate_ranking_sha256": sha256_file(candidate_ranking_path),
                "hash_lineage_path": relative_or_string(hash_lineage_path),
                "hash_lineage_sha256": sha256_file(hash_lineage_path),
                "selection_status": audit_payload["selection_status"],
                "stage_a_monthly_universe_mask_ready": False,
            }
        )
    return monthly_artifacts


def main() -> int:
    started_at = datetime.now(timezone.utc)
    args = parse_args()
    if args.candidate_seed_limit <= 0:
        raise argparse.ArgumentTypeError("--candidate-seed-limit must be positive")
    if args.selection_lookback_days < args.selection_lookback_min_days:
        raise argparse.ArgumentTypeError("--selection-lookback-days must be >= --selection-lookback-min-days")
    if args.target_symbols <= 0:
        raise argparse.ArgumentTypeError("--target-symbols must be positive")

    selection_data_types = split_csv_arg(args.selection_data_types)
    stage_a_data_types = split_csv_arg(args.stage_a_data_types)
    bucket_targets = parse_bucket_targets(args.bucket_targets)
    latest_partial_month_end = parse_iso_date(args.latest_partial_month_end)
    evaluation_months = iter_months(
        parse_month(args.evaluation_from_month),
        parse_month(args.evaluation_to_month),
    )

    source_payload, source_universe_path = load_candidate_source(args)
    source_universe_sha256 = sha256_file(Path(source_universe_path)) if source_universe_path else None
    candidate_seed, excluded_candidates = build_candidate_seed(
        source_payload,
        candidate_seed_limit=args.candidate_seed_limit,
    )
    proxy_selected = proxy_select_candidates(
        candidate_seed,
        target_symbols=args.target_symbols,
        bucket_targets=bucket_targets,
    )
    candidate_seed_symbols = [candidate_symbol(candidate) for candidate in candidate_seed]
    candidate_seed_symbols = [symbol for symbol in candidate_seed_symbols if symbol is not None]
    proxy_selected_symbols = [item["symbol"] for item in proxy_selected]

    monthly_plans = [
        monthly_plan(
            month,
            latest_partial_month_end=latest_partial_month_end,
            selection_lookback_days=args.selection_lookback_days,
        )
        for month in evaluation_months
    ]

    output_root = args.output_root or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / args.as_of
        / DEFAULT_OUTPUT_SUBDIR
    )
    output_root.mkdir(parents=True, exist_ok=True)

    config_payload = build_config_payload(args, selection_data_types, stage_a_data_types)
    selection_config_sha256 = sha256_json(config_payload)
    runner_sha256 = sha256_file(Path(__file__))

    monthly_artifacts = write_monthly_artifacts(
        output_root=output_root,
        months=monthly_plans,
        candidate_seed=candidate_seed,
        proxy_selected=proxy_selected,
        source_universe_path=source_universe_path,
        source_universe_sha256=source_universe_sha256,
        runner_sha256=runner_sha256,
        selection_config_sha256=selection_config_sha256,
    )

    raw_staging_manifest = build_raw_staging_manifest(
        months=monthly_plans,
        candidate_seed_symbols=candidate_seed_symbols,
        exchange=args.exchange,
        selection_data_types=selection_data_types,
        stage_a_data_types=stage_a_data_types,
        storage_raw_root=args.storage_raw_root,
        compute_raw_root=args.compute_raw_root,
        detail=args.partition_plan_detail,
        sample_limit=args.partition_sample_limit,
    )
    normalized_manifest = build_normalized_manifest_plan(
        months=monthly_plans,
        candidate_seed_symbols=candidate_seed_symbols,
        proxy_selected_symbols=proxy_selected_symbols,
        exchange=args.exchange,
        normalized_root=args.normalized_root,
    )
    gates = gate_report(
        months=monthly_plans,
        candidate_seed_symbols=candidate_seed_symbols,
        proxy_selected=proxy_selected,
        min_symbols=args.min_symbols,
        min_non_btc_eth_symbols=args.min_non_btc_eth_symbols,
        min_liquidity_buckets=args.min_liquidity_buckets,
        distinct_months_min=args.distinct_months_min,
        selection_lookback_min_days=args.selection_lookback_min_days,
    )

    universe_definition = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "artifact_kind": "rolling_pit_core_universe_definition",
        "as_of": args.as_of,
        "generated_at_utc": utc_now(),
        "runner_path": relative_or_string(Path(__file__)),
        "runner_sha256": runner_sha256,
        "selection_config": config_payload,
        "selection_config_sha256": selection_config_sha256,
        "source_universe_path": source_universe_path,
        "source_universe_sha256": source_universe_sha256,
        "candidate_seed_source_as_of": source_payload.get("as_of"),
        "candidate_seed_contract_version": source_payload.get("contract_version"),
        "candidate_seed_pit_valid_for_historical_selection": False,
        "candidate_seed_pit_valid_fail_closed_reason": (
            "the runner has not computed monthly pre-freeze raw metrics; "
            "candidate seed is for dry-run partition planning only"
        ),
        "selection_status": "dry_run_plan_only_pending_monthly_raw_metrics",
        "stage_a_monthly_universe_masks_ready": False,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
    }
    freeze_plan = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_monthly_freeze_plan",
        "months": monthly_plans,
        "evaluation_month_count": len(monthly_plans),
        "selection_lookback_days": args.selection_lookback_days,
        "selection_lookback_min_days": args.selection_lookback_min_days,
        "first_selection_lookback_start": monthly_plans[0]["selection_lookback_start"] if monthly_plans else None,
        "last_evaluation_end": monthly_plans[-1]["evaluation_end"] if monthly_plans else None,
        "dry_run_only": True,
        "downloads_executed_by_runner": False,
    }
    candidate_pool_audit = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_candidate_pool_audit",
        "source_universe_path": source_universe_path,
        "source_universe_sha256": source_universe_sha256,
        "source_universe_as_of": source_payload.get("as_of"),
        "source_universe_top100_complete": source_payload.get("top100_complete"),
        "candidate_seed_symbol_count": len(candidate_seed_symbols),
        "candidate_seed_symbols": candidate_seed_symbols,
        "excluded_candidate_count": len(excluded_candidates),
        "excluded_candidates": excluded_candidates,
        "candidate_seed_pit_valid_for_historical_selection": False,
        "monthly_raw_selection_metrics_present": False,
        "dry_run_proxy_selected_symbol_count": len(proxy_selected_symbols),
        "dry_run_proxy_selected_symbols": proxy_selected_symbols,
    }
    monthly_selection_audit = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_monthly_selection_audit",
        "monthly_artifacts": monthly_artifacts,
        "monthly_artifact_count": len(monthly_artifacts),
        "stage_a_monthly_universe_masks_ready": False,
    }
    stage_a_input_audit = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_stage_a_input_audit",
        "input_mode": "not_run_dry_run_plan_only",
        "stage_a_monthly_universe_masks_ready": False,
        "raw_scan_executed_by_runner": False,
        "downloads_executed_by_runner": False,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
        "fail_closed_reason": (
            "Stage A must wait for monthly PIT selection computed from retained pre-freeze raw metrics"
        ),
    }
    coverage_report = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_stage_a_coverage_report",
        "coverage_status": "not_evaluated_dry_run_plan_only",
        "raw_coverage_scanned": False,
        "normalized_coverage_scanned": False,
        "event_count_total": None,
        "distinct_months_with_min_events": None,
        "proof_allowed": False,
        "stage_a_proof_computed": False,
    }
    elapsed_before_profile = (datetime.now(timezone.utc) - started_at).total_seconds()
    profile = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "rolling_pit_core_stage_a_profile",
        "profile_kind": "dry_run_planning_only",
        "total_seconds_before_profile_write": elapsed_before_profile,
        "candidate_seed_symbol_count": len(candidate_seed_symbols),
        "evaluation_month_count": len(monthly_plans),
        "planned_unique_raw_partition_count": raw_staging_manifest["planned_unique_raw_partition_count"],
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
    }
    summary = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "artifact_kind": "rolling_pit_core_stage_a_summary",
        "as_of": args.as_of,
        "status": "dry_run_plan_written_waiting_for_monthly_raw_selection_metrics",
        "generated_at_utc": utc_now(),
        "output_root": str(output_root),
        "evaluation_from_month": args.evaluation_from_month,
        "evaluation_to_month": args.evaluation_to_month,
        "evaluation_month_count": len(monthly_plans),
        "distinct_evaluation_month_count": len(monthly_plans),
        "first_selection_lookback_start": freeze_plan["first_selection_lookback_start"],
        "last_evaluation_end": freeze_plan["last_evaluation_end"],
        "candidate_seed_symbol_count": len(candidate_seed_symbols),
        "dry_run_proxy_selected_symbol_count": len(proxy_selected_symbols),
        "monthly_freeze_artifact_count": len(monthly_artifacts),
        "planned_unique_raw_partition_count": raw_staging_manifest["planned_unique_raw_partition_count"],
        "planned_non_dedup_raw_partition_count": raw_staging_manifest["planned_non_dedup_raw_partition_count"],
        "planned_candidate_seed_normalized_partition_count": normalized_manifest[
            "planned_candidate_seed_normalized_partition_count"
        ],
        "gates": gates["gates"],
        "blocking_gates": gates["blocking_gates"],
        "proof_allowed": False,
        "stage_a_monthly_universe_masks_ready": False,
        "candidate_seed_pit_valid_for_historical_selection": False,
        "monthly_raw_selection_metrics_present": False,
        "dry_run_only": True,
        "downloads_executed_by_runner": False,
        "raw_scan_executed_by_runner": False,
        "normalization_executed_by_runner": False,
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
        "live_or_timer_use_authorized": False,
        "h10d_bridge_authorized": False,
    }

    artifacts = {
        "rolling_pit_core_universe_definition.json": universe_definition,
        "rolling_pit_core_monthly_freeze_plan.json": freeze_plan,
        "rolling_pit_core_candidate_pool_audit.json": candidate_pool_audit,
        "rolling_pit_core_monthly_selection_audit.json": monthly_selection_audit,
        "rolling_pit_core_raw_staging_manifest.json": raw_staging_manifest,
        "rolling_pit_core_normalized_manifest.json": normalized_manifest,
        "rolling_pit_core_stage_a_input_audit.json": stage_a_input_audit,
        "rolling_pit_core_stage_a_coverage_report.json": coverage_report,
        "rolling_pit_core_stage_a_summary.json": summary,
        "rolling_pit_core_stage_a_profile.json": profile,
    }
    for filename, payload in artifacts.items():
        write_json(output_root / filename, payload)

    print(
        json.dumps(
            {
                "status": summary["status"],
                "output_root": str(output_root),
                "evaluation_month_count": summary["evaluation_month_count"],
                "candidate_seed_symbol_count": summary["candidate_seed_symbol_count"],
                "monthly_freeze_artifact_count": summary["monthly_freeze_artifact_count"],
                "planned_unique_raw_partition_count": summary["planned_unique_raw_partition_count"],
                "downloads_executed_by_runner": False,
                "stage_a_proof_computed": False,
                "trading_action_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
