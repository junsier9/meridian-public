from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
try:
    ROOT = SCRIPT_DIR.parents[2]
except IndexError:
    ROOT = Path.cwd()

CONTRACT_VERSION = "quant_tardis_intraday_liquidity_shock_raw_staging.v1"
DATASET_BASE_URL = "https://datasets.tardis.dev/v1"
DEFAULT_AS_OF = "2026-06-16-intraday-liquid-perp-core-v1-raw"
DEFAULT_EXCHANGE = "binance-futures"
DEFAULT_FROM_DATE = "2026-06-01"
DEFAULT_TO_DATE = "2026-06-13"
DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,SOLUSDT,ZECUSDT,XRPUSDT,DOGEUSDT,BNBUSDT,SUIUSDT,"
    "LTCUSDT,AAVEUSDT,DASHUSDT,UNIUSDT,ENAUSDT,ASTERUSDT,WLDUSDT,FETUSDT,"
    "ALGOUSDT,POLUSDT,ETCUSDT,OPUSDT"
)
DEFAULT_DATA_TYPES = (
    "trades",
    "liquidations",
    "book_ticker",
    "book_snapshot_5",
    "derivative_ticker",
)
DEFAULT_ENV_NAMES = (
    "Tardis_api_key",
    "TARDIS_API_KEY",
    "TARDIS_API",
    "TARDIS_DEV_API_KEY",
    "Tardis_API_KEY",
)
RAW_RETENTION_CONFIRMATION = "I_UNDERSTAND_RAW_TARDIS_INTRADAY_DATA_WILL_BE_RETAINED"
RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage retained Tardis intraday gzip/CSV raw partitions for the "
            "liquidity-shock Stage A lane. This writes raw-data lineage and "
            "manifest artifacts only. It does not normalize parquet, run Stage A, "
            "compute strategy PnL, or create trading actions."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--to-date", default=DEFAULT_TO_DATE)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--data-types", default=",".join(DEFAULT_DATA_TYPES))
    parser.add_argument(
        "--plan-manifest",
        type=Path,
        default=None,
        help=(
            "Optional dry-run rolling PIT raw staging manifest. When supplied, "
            "the runner stages the exact unique partition set described by the "
            "manifest instead of using --from-date/--to-date/--symbols."
        ),
    )
    parser.add_argument(
        "--resume-manifest",
        type=Path,
        default=None,
        help=(
            "Optional prior full raw staging manifest. Completed records from "
            "that manifest are reused without re-hashing; incomplete records "
            "are retried and a new full manifest is written."
        ),
    )
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--manifest-dir", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument(
        "--max-inflight",
        type=int,
        default=0,
        help="Bound submitted download futures. Default is max(32, max_workers * 8).",
    )
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--allow-missing-upstream",
        action="store_true",
        help=(
            "Treat HTTP 404 dataset responses as terminal missing_upstream "
            "partition status. This is intended for rolling PIT candidate-pool "
            "staging where many historical candidate-symbol partitions may be "
            "absent before listing."
        ),
    )
    parser.add_argument(
        "--use-exchange-availability-metadata",
        action="store_true",
        help=(
            "Fetch Tardis exchange metadata once and mark partitions before "
            "datasets.symbols[].availableSince as missing_upstream without "
            "issuing one dataset request per unavailable day."
        ),
    )
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument(
        "--confirm-retain-raw-vendor-data",
        default="",
        help=f"Required with --execute. Exact value: {RAW_RETENTION_CONFIRMATION}",
    )
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


def list_arg(text: str) -> list[str]:
    return sorted({item.strip().upper() for item in str(text).split(",") if item.strip()})


def ensure_outside_repo(path: Path, *, label: str) -> None:
    root = ROOT.resolve()
    try:
        path.expanduser().resolve().relative_to(root)
    except ValueError:
        return
    raise RuntimeError(f"{label} must stay outside the repo checkout: {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_api_key() -> str:
    for name in DEFAULT_ENV_NAMES:
        raw_value = os.environ.get(name, "").strip()
        value = normalize_api_key(raw_value)
        if value:
            return value
    raise RuntimeError(
        "Tardis API key missing; set one of "
        + ", ".join(DEFAULT_ENV_NAMES)
        + " in the process environment."
    )


def normalize_api_key(value: str) -> str:
    resolved = str(value or "").strip()
    if len(resolved) >= 2 and resolved[0] == resolved[-1] and resolved[0] in {"'", '"'}:
        resolved = resolved[1:-1].strip()
    for prefix in ("Bearer ", "bearer "):
        if resolved.startswith(prefix):
            resolved = resolved[len(prefix) :].strip()
            break
    if any(ch.isspace() for ch in resolved):
        resolved = "".join(resolved.split())
    return resolved


def is_missing_upstream_response(*, status_code: int, body_excerpt: str) -> bool:
    if status_code == 404:
        return True
    if status_code != 400:
        return False
    text = str(body_excerpt)
    return (
        '"code": 140' in text
        or '"code":140' in text
        or "Requested dataset is not available" in text
        or "available since" in text
    )


def raw_partition_path(
    *,
    raw_root: Path,
    exchange: str,
    data_type: str,
    current_date: date,
    symbol: str,
) -> Path:
    return (
        raw_root
        / "raw"
        / exchange
        / data_type
        / f"{current_date:%Y}"
        / f"{current_date:%m}"
        / f"{current_date:%d}"
        / f"{symbol}.csv.gz"
    )


def dataset_url(*, exchange: str, data_type: str, current_date: date, symbol: str) -> str:
    return f"{DATASET_BASE_URL}/{exchange}/{data_type}/{current_date:%Y/%m/%d}/{symbol}.csv.gz"


def exchange_metadata_url(*, exchange: str) -> str:
    return f"https://api.tardis.dev/v1/exchanges/{exchange}"


def parse_available_since(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def dataset_data_type(dataset: dict[str, Any]) -> str | None:
    for key in ("id", "dataType", "data_type", "type", "name"):
        value = str(dataset.get(key) or "").strip().lower()
        if value:
            return value
    return None


def symbol_name(symbol_payload: Any) -> str | None:
    if isinstance(symbol_payload, str):
        return symbol_payload.strip().upper() or None
    if not isinstance(symbol_payload, dict):
        return None
    for key in ("id", "symbol", "name"):
        value = str(symbol_payload.get(key) or "").strip().upper()
        if value:
            return value
    return None


def build_exchange_availability_index(
    *,
    api_key: str,
    exchange: str,
    timeout_seconds: float,
) -> tuple[dict[tuple[str, str], date], dict[str, Any]]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for Tardis exchange metadata") from exc

    response = requests.get(
        exchange_metadata_url(exchange=exchange),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_seconds,
    )
    payload: Any = None
    body_excerpt = ""
    try:
        payload = response.json()
    except ValueError:
        body_excerpt = response.text[:500] if response.text else ""
    if response.status_code != 200 or payload is None:
        return (
            {},
            {
                "metadata_fetch_status": "failed",
                "http_status": int(response.status_code),
                "body_excerpt": body_excerpt,
                "symbol_data_type_available_since_count": 0,
            },
        )

    if isinstance(payload, dict):
        datasets = payload.get("datasets") or payload.get("dataTypes") or payload.get("data_types") or []
    elif isinstance(payload, list):
        datasets = payload
    else:
        datasets = []
    index: dict[tuple[str, str], date] = {}

    if isinstance(payload, dict):
        for symbol_payload in payload.get("availableSymbols", []) or []:
            symbol = symbol_name(symbol_payload)
            available_since = None
            if isinstance(symbol_payload, dict):
                available_since = parse_available_since(
                    symbol_payload.get("availableSince")
                    or symbol_payload.get("available_since")
                    or symbol_payload.get("availableFrom")
                )
            if symbol and available_since is not None:
                index[("*", symbol)] = available_since

        dataset_symbols = None
        if isinstance(payload.get("datasets"), dict):
            dataset_symbols = payload["datasets"].get("symbols")
        if isinstance(dataset_symbols, list):
            for symbol_payload in dataset_symbols:
                if not isinstance(symbol_payload, dict):
                    continue
                symbol = symbol_name(symbol_payload)
                available_since = parse_available_since(
                    symbol_payload.get("availableSince")
                    or symbol_payload.get("available_since")
                    or symbol_payload.get("availableFrom")
                )
                data_types = symbol_payload.get("dataTypes") or symbol_payload.get("data_types") or []
                if not symbol or available_since is None or not isinstance(data_types, list):
                    continue
                for data_type in data_types:
                    data_type_text = str(data_type).strip().lower()
                    if data_type_text:
                        index[(data_type_text, symbol)] = available_since

    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        data_type = dataset_data_type(dataset)
        symbols = dataset.get("symbols") or dataset.get("datasets") or []
        if not data_type or not isinstance(symbols, list):
            continue
        for symbol_payload in symbols:
            symbol = symbol_name(symbol_payload)
            available_since = None
            if isinstance(symbol_payload, dict):
                available_since = parse_available_since(
                    symbol_payload.get("availableSince")
                    or symbol_payload.get("available_since")
                    or symbol_payload.get("availableFrom")
                )
            if symbol and available_since is not None:
                index[(data_type, symbol)] = available_since
    return (
        index,
        {
            "metadata_fetch_status": "ok",
            "http_status": int(response.status_code),
            "symbol_data_type_available_since_count": len(index),
        },
    )


def partition_plan(
    *,
    raw_root: Path,
    exchange: str,
    data_type: str,
    current_date: date,
    symbol: str,
) -> dict[str, Any]:
    path = raw_partition_path(
        raw_root=raw_root,
        exchange=exchange,
        data_type=data_type,
        current_date=current_date,
        symbol=symbol,
    )
    stat = path.stat() if path.exists() else None
    return {
        "date": current_date.isoformat(),
        "symbol": symbol,
        "data_type": data_type,
        "url_path": f"{exchange}/{data_type}/{current_date:%Y/%m/%d}/{symbol}.csv.gz",
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": int(stat.st_size) if stat else 0,
        "last_write_time_utc": (
            datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat() if stat else None
        ),
        "action": "planned",
        "completed": False,
        "downloaded": False,
    }


def result_identity(item: dict[str, Any]) -> tuple[str, str, str, str]:
    exchange = str(item.get("exchange") or str(item.get("url_path") or DEFAULT_EXCHANGE).split("/", 1)[0])
    return (
        exchange,
        str(item["data_type"]).strip().lower(),
        str(item["symbol"]).strip().upper(),
        str(item["date"]).strip(),
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild_plan_manifest_partitions(
    *,
    plan_manifest: dict[str, Any],
    raw_root: Path,
    exchange_override: str | None,
) -> list[dict[str, Any]]:
    exchange = str(exchange_override or plan_manifest.get("exchange") or DEFAULT_EXCHANGE)
    symbols = [str(item).strip().upper() for item in plan_manifest.get("candidate_seed_symbols", []) if str(item).strip()]
    if not symbols:
        raise RuntimeError("plan manifest has no candidate_seed_symbols")
    partition_roles: dict[tuple[str, str, str, str], set[str]] = {}

    materialized = plan_manifest.get("partitions") or []
    if materialized:
        for item in materialized:
            data_type = str(item["data_type"]).strip().lower()
            symbol = str(item["symbol"]).strip().upper()
            current_date = str(item["date"]).strip()
            item_exchange = str(item.get("exchange") or exchange)
            roles = {str(role) for role in item.get("usage_roles", [])} or {"plan_manifest"}
            partition_roles.setdefault((item_exchange, data_type, symbol, current_date), set()).update(roles)
    else:
        for month_plan in plan_manifest.get("monthly_plans", []):
            evaluation_month = str(month_plan["evaluation_month"])
            selection_dates = date_range(
                parse_iso_date(str(month_plan["selection_lookback_start"])),
                parse_iso_date(str(month_plan["selection_lookback_end"])),
            )
            evaluation_dates = date_range(
                parse_iso_date(str(month_plan["evaluation_start"])),
                parse_iso_date(str(month_plan["evaluation_end"])),
            )
            selection_data_types = [
                str(item).strip().lower()
                for item in month_plan.get("selection_data_types", [])
                if str(item).strip()
            ]
            stage_a_data_types = [
                str(item).strip().lower()
                for item in month_plan.get("stage_a_data_types", [])
                if str(item).strip()
            ]
            for symbol in symbols:
                for current_date in selection_dates:
                    for data_type in selection_data_types:
                        key = (exchange, data_type, symbol, current_date.isoformat())
                        partition_roles.setdefault(key, set()).add(f"selection_lookback:{evaluation_month}")
                for current_date in evaluation_dates:
                    for data_type in stage_a_data_types:
                        key = (exchange, data_type, symbol, current_date.isoformat())
                        partition_roles.setdefault(key, set()).add(f"evaluation:{evaluation_month}")

    partitions: list[dict[str, Any]] = []
    for item_exchange, data_type, symbol, date_text in sorted(partition_roles):
        partition = partition_plan(
            raw_root=raw_root,
            exchange=item_exchange,
            data_type=data_type,
            current_date=parse_iso_date(date_text),
            symbol=symbol,
        )
        partition["usage_roles"] = sorted(partition_roles[(item_exchange, data_type, symbol, date_text)])
        partitions.append(partition)

    expected = plan_manifest.get("planned_unique_raw_partition_count")
    if expected is not None and int(expected) != len(partitions):
        raise RuntimeError(
            "plan manifest partition count mismatch: "
            f"expected {expected}, rebuilt {len(partitions)}"
        )
    return partitions


def download_partition(
    *,
    api_key: str,
    partition: dict[str, Any],
    timeout_seconds: float,
    force: bool,
    allow_missing_upstream: bool,
    availability_index: dict[tuple[str, str], date] | None,
    max_retries: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    path = Path(str(partition["path"]))
    if path.exists() and not force:
        stat = path.stat()
        return {
            **partition,
            "action": "existing",
            "completed": True,
            "downloaded": False,
            "http_status": None,
            "size_bytes": int(stat.st_size),
            "sha256": sha256_file(path),
        }

    current_date = parse_iso_date(str(partition["date"]))
    data_type = str(partition["data_type"]).strip().lower()
    symbol = str(partition["symbol"]).strip().upper()
    available_since = None
    if availability_index:
        available_since = availability_index.get((data_type, symbol)) or availability_index.get(("*", symbol))
    if (
        allow_missing_upstream
        and available_since is not None
        and current_date < available_since
    ):
        return {
            **partition,
            "action": "missing_upstream",
            "completed": True,
            "downloaded": False,
            "http_status": None,
            "metadata_available_since": available_since.isoformat(),
            "body_excerpt": None,
            "size_bytes": 0,
            "sha256": None,
        }

    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for Tardis raw staging") from exc

    url = dataset_url(
        exchange=str(partition["url_path"]).split("/", 1)[0],
        data_type=data_type,
        current_date=current_date,
        symbol=symbol,
    )
    response = None
    attempt_index = 0
    for attempt_index in range(max_retries + 1):
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Accept-Encoding": "identity"},
                stream=True,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            if attempt_index < max_retries:
                time.sleep(retry_sleep_seconds)
                continue
            return {
                **partition,
                "action": "download_failed",
                "completed": False,
                "downloaded": False,
                "http_status": None,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500],
                "attempt_count": attempt_index + 1,
            }
        if response.status_code == 200:
            break
        excerpt = response.text[:500] if response.text else ""
        status_code = int(response.status_code)
        response.close()
        if allow_missing_upstream and is_missing_upstream_response(
            status_code=status_code,
            body_excerpt=excerpt,
        ):
            return {
                **partition,
                "action": "missing_upstream",
                "completed": True,
                "downloaded": False,
                "http_status": status_code,
                "body_excerpt": excerpt,
                "size_bytes": 0,
                "sha256": None,
                "attempt_count": attempt_index + 1,
            }
        if status_code in RETRYABLE_HTTP_STATUS and attempt_index < max_retries:
            time.sleep(retry_sleep_seconds)
            continue
        return {
            **partition,
            "action": "download_failed",
            "completed": False,
            "downloaded": False,
            "http_status": status_code,
            "body_excerpt": excerpt,
            "attempt_count": attempt_index + 1,
        }
    assert response is not None

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    digest = hashlib.sha256()
    size = 0
    try:
        with temp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        temp_path.replace(path)
    finally:
        response.close()
        if temp_path.exists():
            temp_path.unlink()

    return {
        **partition,
        "action": "downloaded",
        "completed": True,
        "downloaded": True,
        "http_status": response.status_code,
        "size_bytes": int(size),
        "sha256": digest.hexdigest(),
        "attempt_count": attempt_index + 1,
    }


def compact_progress(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": payload["run_id"],
        "success": payload["success"],
        "expected_partition_count": payload["expected_partition_count"],
        "completed_partition_count": payload["completed_partition_count"],
        "downloaded_count": payload["downloaded_count"],
        "existing_count": payload["existing_count"],
        "available_partition_count": payload.get("available_partition_count"),
        "missing_upstream_count": payload.get("missing_upstream_count"),
        "failed_count": payload["failed_count"],
        "distinct_calendar_months_completed": payload["distinct_calendar_months_completed"],
        "manifest_path": payload.get("manifest_path"),
    }


def main() -> int:
    args = parse_args()
    from_date = parse_iso_date(args.from_date)
    to_date = parse_iso_date(args.to_date)
    if to_date < from_date:
        raise SystemExit("--to-date must be >= --from-date")
    if args.max_workers < 1:
        raise SystemExit("--max-workers must be positive")
    if args.max_inflight < 0:
        raise SystemExit("--max-inflight must be non-negative")
    if args.timeout_seconds <= 0 or not math.isfinite(args.timeout_seconds):
        raise SystemExit("--timeout-seconds must be positive and finite")
    if args.max_retries < 0:
        raise SystemExit("--max-retries must be non-negative")
    if args.retry_sleep_seconds < 0 or not math.isfinite(args.retry_sleep_seconds):
        raise SystemExit("--retry-sleep-seconds must be non-negative and finite")
    if args.execute and args.confirm_retain_raw_vendor_data != RAW_RETENTION_CONFIRMATION:
        raise SystemExit(
            "--execute requires --confirm-retain-raw-vendor-data "
            f"{RAW_RETENTION_CONFIRMATION!r}"
        )

    raw_root = args.raw_root.expanduser().resolve()
    ensure_outside_repo(raw_root, label="Tardis raw staging root")
    manifest_dir = (
        args.manifest_dir.expanduser().resolve()
        if args.manifest_dir is not None
        else raw_root / "manifests"
    )
    ensure_outside_repo(manifest_dir, label="Tardis raw staging manifest dir")
    manifest_path = manifest_dir / f"{args.as_of}.json"
    progress_path = manifest_dir / f"{args.as_of}.progress.json"

    source_plan_manifest_path: Path | None = (
        args.plan_manifest.expanduser().resolve() if args.plan_manifest is not None else None
    )
    source_plan_manifest: dict[str, Any] | None = (
        load_json(source_plan_manifest_path) if source_plan_manifest_path is not None else None
    )
    if source_plan_manifest is not None:
        partitions = rebuild_plan_manifest_partitions(
            plan_manifest=source_plan_manifest,
            raw_root=raw_root,
            exchange_override=str(args.exchange),
        )
        symbols = sorted({str(item["symbol"]) for item in partitions})
        data_types = sorted({str(item["data_type"]) for item in partitions})
        dates = sorted({parse_iso_date(str(item["date"])) for item in partitions})
        from_date = dates[0]
        to_date = dates[-1]
    else:
        symbols = list_arg(args.symbols)
        data_types = [item.lower() for item in list_arg(args.data_types)]
        dates = date_range(from_date, to_date)
        partitions = [
            partition_plan(
                raw_root=raw_root,
                exchange=str(args.exchange),
                data_type=data_type,
                current_date=current_date,
                symbol=symbol,
            )
            for current_date in dates
            for symbol in symbols
            for data_type in data_types
        ]

    resume_manifest_path: Path | None = (
        args.resume_manifest.expanduser().resolve() if args.resume_manifest is not None else None
    )
    resume_payload: dict[str, Any] | None = (
        load_json(resume_manifest_path) if resume_manifest_path is not None else None
    )
    resumed_records: list[dict[str, Any]] = []
    resumed_index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    if resume_payload is not None:
        for item in resume_payload.get("partitions", []):
            if not item.get("completed"):
                continue
            resumed_index[result_identity(item)] = item
        partitions_to_run: list[dict[str, Any]] = []
        for partition in partitions:
            prior = resumed_index.get(result_identity(partition))
            if prior is None or args.force:
                partitions_to_run.append(partition)
            else:
                resumed_records.append(prior)
    else:
        partitions_to_run = partitions

    started_at = time.perf_counter()
    api_key = resolve_api_key() if args.execute else None
    availability_index: dict[tuple[str, str], date] | None = None
    availability_metadata: dict[str, Any] | None = None
    if args.execute and args.use_exchange_availability_metadata:
        assert api_key is not None
        availability_index, availability_metadata = build_exchange_availability_index(
            api_key=api_key,
            exchange=str(args.exchange),
            timeout_seconds=float(args.timeout_seconds),
        )
    results: list[dict[str, Any]] = list(resumed_records)
    seen = len(results)

    def write_progress(last_result: dict[str, Any] | None = None) -> None:
        completed = [item for item in results if item.get("completed")]
        failures = [item for item in results if not item.get("completed")]
        completed_months = sorted({str(item["date"])[:7] for item in completed})
        payload = {
            "contract_version": CONTRACT_VERSION,
            "run_id": str(args.as_of),
            "generated_at_utc": utc_now(),
            "last_update_utc": utc_now(),
            "mode": "execute" if args.execute else "plan",
            "exchange": str(args.exchange),
            "symbols": symbols,
            "data_types": data_types,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "raw_root": str(raw_root),
            "exchange_availability_metadata": availability_metadata,
            "seen_partition_count": seen,
            "expected_partition_count": len(partitions),
            "completed_partition_count": len(completed),
            "downloaded_count": sum(1 for item in completed if item.get("downloaded")),
            "existing_count": sum(1 for item in completed if item.get("action") == "existing"),
            "available_partition_count": sum(1 for item in completed if item.get("action") != "missing_upstream"),
            "missing_upstream_count": sum(1 for item in completed if item.get("action") == "missing_upstream"),
            "failed_count": len(failures),
            "distinct_calendar_months_completed": len(completed_months),
            "last_result": last_result,
            "success": False,
            "api_key_logged": False,
            "raw_vendor_data_retained": bool(args.execute),
            "stage_b_return_ablation_allowed": False,
            "strategy_pnl_computed": False,
            "trading_action_authorized": False,
        }
        write_json(progress_path, payload)
        print(json.dumps(compact_progress({**payload, "manifest_path": str(manifest_path)}), sort_keys=True))

    if args.execute:
        assert api_key is not None
        max_inflight = int(args.max_inflight) if args.max_inflight else max(32, int(args.max_workers) * 8)
        partition_iter = iter(partitions_to_run)
        with ThreadPoolExecutor(max_workers=int(args.max_workers)) as executor:
            futures = set()

            def submit_next() -> bool:
                try:
                    partition = next(partition_iter)
                except StopIteration:
                    return False
                futures.add(
                    executor.submit(
                        download_partition,
                        api_key=api_key,
                        partition=partition,
                        timeout_seconds=float(args.timeout_seconds),
                        force=bool(args.force),
                        allow_missing_upstream=bool(args.allow_missing_upstream),
                        availability_index=availability_index,
                        max_retries=int(args.max_retries),
                        retry_sleep_seconds=float(args.retry_sleep_seconds),
                    )
                )
                return True

            for _ in range(min(max_inflight, len(partitions_to_run))):
                if not submit_next():
                    break
            while futures:
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    seen += 1
                    result = future.result()
                    results.append(result)
                    if seen == 1 or seen % max(1, int(args.progress_every)) == 0 or seen == len(partitions):
                        write_progress(result)
                while len(futures) < max_inflight and submit_next():
                    pass
    else:
        for partition in partitions_to_run:
            seen += 1
            action = "existing" if partition["exists"] else "dry_run_download"
            results.append(
                {
                    **partition,
                    "action": action,
                    "completed": bool(partition["exists"]),
                    "downloaded": False,
                    "http_status": None,
                    "sha256": sha256_file(Path(partition["path"])) if partition["exists"] else None,
                }
            )

    completed = [item for item in results if item.get("completed")]
    failures = [item for item in results if not item.get("completed")]
    available = [item for item in completed if item.get("action") != "missing_upstream"]
    missing_upstream = [item for item in completed if item.get("action") == "missing_upstream"]
    completed_months = sorted({str(item["date"])[:7] for item in completed})
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": str(args.as_of),
        "generated_at_utc": utc_now(),
        "last_update_utc": utc_now(),
        "mode": "execute" if args.execute else "plan",
        "exchange": str(args.exchange),
        "symbols": symbols,
        "data_types": data_types,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
            "source_plan_manifest": str(source_plan_manifest_path) if source_plan_manifest_path else None,
            "source_plan_manifest_sha256": (
                sha256_file(source_plan_manifest_path) if source_plan_manifest_path else None
            ),
        "resume_manifest": str(resume_manifest_path) if resume_manifest_path else None,
        "resume_manifest_sha256": sha256_file(resume_manifest_path) if resume_manifest_path else None,
        "resumed_completed_partition_count": len(resumed_records),
        "retried_partition_count": len(partitions_to_run),
        "allow_missing_upstream": bool(args.allow_missing_upstream),
        "exchange_availability_metadata": availability_metadata,
        "target_months": sorted({f"{current:%Y-%m}" for current in dates}),
        "completed_months": completed_months,
        "distinct_calendar_months_completed": len(completed_months),
        "raw_root": str(raw_root),
        "manifest_path": str(manifest_path),
        "expected_partition_count": len(partitions),
        "seen_partition_count": seen,
        "completed_partition_count": len(completed),
        "existing_or_downloaded_count": len(available),
        "downloaded_count": sum(1 for item in completed if item.get("downloaded")),
        "existing_count": sum(1 for item in completed if item.get("action") == "existing"),
        "available_partition_count": len(available),
        "missing_upstream_count": len(missing_upstream),
        "failed_count": len(failures),
        "retained_raw_size_bytes": sum(int(item.get("size_bytes") or 0) for item in available),
        "failures": failures,
        "partitions": sorted(results, key=lambda item: (item["date"], item["symbol"], item["data_type"])),
        "success": not failures and len(completed) == len(partitions),
        "elapsed_seconds": round(time.perf_counter() - started_at, 6),
        "api_key_logged": False,
        "raw_vendor_data_retained": bool(args.execute),
        "stage_a_proof_computed": False,
        "stage_b_return_ablation_allowed": False,
        "strategy_pnl_computed": False,
        "trading_action_authorized": False,
    }
    write_json(manifest_path, summary)
    write_json(progress_path, summary)
    printable = compact_progress(summary) if args.summary_only else summary
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
