from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from enhengclaw.ops.evidence_contracts import with_evidence_metadata


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_FAMILY = "m3_2_stablecoin_tron_sync"
CONTRACT_VERSION = "m3_2_stablecoin_tron_sync.v1"
DEFAULT_EXTERNAL_ROOT_NAME = "onchain_stablecoin_tron"
DEFAULT_LOOKBACK_DAYS = 180
DEFAULT_SYNC_MODE = "auto"
DEFAULT_REFRESH_OVERLAP_DAYS = 7
DEFAULT_REQUEST_TIMEOUT_SEC = 30
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_SLEEP_SEC = 1.0
DEFAULT_ANALYSIS_CHUNK_DAYS = 120
TRONSCAN_API_BASE = "https://apilist.tronscanapi.com/api"
JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}
CSV_HEADERS = (
    "date_utc",
    "token_symbol",
    "contract_address",
    "decimals",
    "transfer_count",
    "transfer_amount",
    "transfer_amount_usd",
    "from_count",
    "to_count",
    "active_address_count",
    "holders_count",
    "stats_usdt_transaction_count",
    "stats_active_account_number",
    "stats_total_transaction_count",
    "transfer_count_vs_stats_delta",
    "coverage_start_utc",
    "coverage_end_utc",
    "is_full_day",
    "fetch_status",
    "source",
)


@dataclass(frozen=True, slots=True)
class TronStablecoinTokenSpec:
    symbol: str
    contract_address: str
    decimals: int


DEFAULT_TOKEN_SPECS: tuple[TronStablecoinTokenSpec, ...] = (
    TronStablecoinTokenSpec("USDT_TRX", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", 6),
)


def resolve_onchain_tron_external_root(
    *,
    external_root: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    env = os.environ if base_env is None else base_env
    localappdata = str(env.get("LOCALAPPDATA", "")).strip()
    if localappdata:
        return (Path(localappdata) / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()
    return (Path.home() / ".local" / "share" / "EnhengClaw" / DEFAULT_EXTERNAL_ROOT_NAME).resolve()


def run_m3_2_tron_stablecoin_sync(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    mode: str = DEFAULT_SYNC_MODE,
    refresh_overlap_days: int = DEFAULT_REFRESH_OVERLAP_DAYS,
    analysis_chunk_days: int = DEFAULT_ANALYSIS_CHUNK_DAYS,
    external_root: Path | None = None,
    token_symbols: Iterable[str] | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    resolved_root = resolve_onchain_tron_external_root(external_root=external_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    output_path = resolved_root / "daily_aggregates.csv"
    existing_rows = _read_daily_rows(output_path)
    selected_tokens = _select_tokens(token_symbols)
    sync_end_date = datetime.now(UTC).date() - timedelta(days=1)
    sync_plan = _build_sync_plan(
        selected_tokens=selected_tokens,
        existing_rows=existing_rows,
        requested_mode=mode,
        lookback_days=lookback_days,
        refresh_overlap_days=refresh_overlap_days,
        end_date=sync_end_date,
    )
    stats_rows = _fetch_tronscan_stats_overview(days=max(1, (sync_plan["end_date"] - sync_plan["start_date"]).days + 1))
    stats_by_day = {str(row.get("dateDayStr") or row.get("day") or ""): row for row in stats_rows if str(row.get("dateDayStr") or row.get("day") or "").strip()}

    daily_rows: list[dict[str, Any]] = []
    token_summaries: list[dict[str, Any]] = []
    for token in selected_tokens:
        analysis_rows = _fetch_token_analysis_range(
            token=token,
            start_date=sync_plan["start_date"],
            end_date=sync_plan["end_date"],
            chunk_days=analysis_chunk_days,
        )
        row_count = 0
        matched_stats_count = 0
        missing_days: list[str] = []
        deltas: list[float] = []
        latest_daily_row: dict[str, Any] | None = None
        expected_days = _expected_dates(sync_plan["start_date"], sync_plan["end_date"])
        analysis_by_day = {
            str(row.get("day") or "").strip(): row
            for row in analysis_rows
            if str(row.get("day") or "").strip()
        }
        for day in expected_days:
            analysis = analysis_by_day.get(day)
            if analysis is None:
                missing_days.append(day)
                continue
            stats = stats_by_day.get(day)
            row = _build_daily_row(
                token=token,
                date_utc=day,
                analysis=analysis,
                stats=stats,
            )
            row_count += 1
            if row["stats_usdt_transaction_count"] is not None:
                matched_stats_count += 1
            if row["transfer_count_vs_stats_delta"] is not None:
                deltas.append(float(row["transfer_count_vs_stats_delta"]))
            latest_daily_row = row
            daily_rows.append(row)
        token_summary = {
            "symbol": token.symbol,
            "contract_address": token.contract_address,
            "decimals": token.decimals,
            "daily_row_count": row_count,
            "matched_stats_count": matched_stats_count,
            "missing_day_count": len(missing_days),
            "missing_days_preview": missing_days[:10],
            "mean_transfer_count_vs_stats_delta": (sum(deltas) / len(deltas)) if deltas else None,
            "max_abs_transfer_count_vs_stats_delta": max((abs(value) for value in deltas), default=None),
        }
        if latest_daily_row is not None:
            token_summary["latest_daily_row"] = latest_daily_row
        token_summaries.append(token_summary)

    merged_rows = _merge_daily_rows(output_path=output_path, replacement_rows=daily_rows)
    _write_daily_rows(output_path=output_path, rows=merged_rows)

    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": _utc_now(),
            "external_root": str(resolved_root),
            "output_path": str(output_path),
            "requested_mode": str(mode).strip().lower() or DEFAULT_SYNC_MODE,
            "effective_mode": sync_plan["effective_mode"],
            "lookback_days": int(lookback_days),
            "refresh_overlap_days": int(refresh_overlap_days),
            "analysis_chunk_days": int(analysis_chunk_days),
            "sync_start_date_utc": sync_plan["start_date"].isoformat(),
            "sync_end_date_utc": sync_plan["end_date"].isoformat(),
            "coverage_day_count": (sync_plan["end_date"] - sync_plan["start_date"]).days + 1,
            "selected_token_latest_dates_before_refresh": sync_plan["selected_token_latest_dates"],
            "token_count": len(selected_tokens),
            "requested_symbols": [token.symbol for token in selected_tokens],
            "written_row_count": len(daily_rows),
            "stored_row_count": len(merged_rows),
            "stats_overview_row_count": len(stats_rows),
            "tokens": token_summaries,
            "input_watermarks": {
                "sync_start_date_utc": sync_plan["start_date"].isoformat(),
                "sync_end_date_utc": sync_plan["end_date"].isoformat(),
            },
            "upstream_versions": {
                "api_base": TRONSCAN_API_BASE,
                "default_token_symbols": [token.symbol for token in DEFAULT_TOKEN_SPECS],
                "analysis_endpoint": "/token/analysis",
                "stats_endpoint": "/stats/overview",
            },
        },
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    latest_summary_path = resolved_root / "latest_sync_summary.json"
    latest_summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["latest_summary_path"] = str(latest_summary_path)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["report_path"] = str(report_path)
    return summary


def _resolve_tronscan_api_key(*, base_env: dict[str, str] | None = None) -> str:
    env = os.environ if base_env is None else base_env
    for name in ("TRONSCAN_API_KEY", "TRON_PRO_API_KEY"):
        token = str(env.get(name, "")).strip()
        if token:
            return token
    if os.name == "nt":
        for name in ("TRONSCAN_API_KEY", "TRON_PRO_API_KEY"):
            token = _read_windows_user_env_var(name)
            if token:
                return token
    return ""


def _read_windows_user_env_var(name: str) -> str:
    try:
        import winreg  # type: ignore
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _value_type = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value).strip()


def _select_tokens(token_symbols: Iterable[str] | None) -> tuple[TronStablecoinTokenSpec, ...]:
    if token_symbols is None:
        return DEFAULT_TOKEN_SPECS
    requested = {str(item).strip().upper() for item in token_symbols if str(item).strip()}
    if not requested:
        return DEFAULT_TOKEN_SPECS
    selected = tuple(token for token in DEFAULT_TOKEN_SPECS if token.symbol in requested)
    if selected:
        return selected
    raise ValueError(f"unsupported TRON stablecoin token symbols requested: {sorted(requested)}")


def _build_sync_plan(
    *,
    selected_tokens: tuple[TronStablecoinTokenSpec, ...],
    existing_rows: list[dict[str, Any]],
    requested_mode: str,
    lookback_days: int,
    refresh_overlap_days: int,
    end_date: date,
) -> dict[str, Any]:
    requested = str(requested_mode).strip().lower() or DEFAULT_SYNC_MODE
    if requested not in {"auto", "bootstrap", "refresh"}:
        raise ValueError(f"unsupported TRON stablecoin sync mode: {requested_mode!r}")
    latest_dates = _latest_dates_by_symbol(existing_rows=existing_rows)
    effective_mode = requested
    if requested == "auto":
        effective_mode = "refresh" if all(latest_dates.get(token.symbol) is not None for token in selected_tokens) else "bootstrap"
    if effective_mode == "refresh":
        anchor_candidates = [latest_dates.get(token.symbol) for token in selected_tokens if latest_dates.get(token.symbol) is not None]
        anchor = min(anchor_candidates) if anchor_candidates else None
        start_date = (
            max(anchor - timedelta(days=max(refresh_overlap_days - 1, 0)), end_date - timedelta(days=max(lookback_days - 1, 0)))
            if anchor is not None
            else end_date - timedelta(days=max(lookback_days - 1, 0))
        )
    else:
        start_date = end_date - timedelta(days=max(lookback_days - 1, 0))
    return {
        "effective_mode": effective_mode,
        "start_date": start_date,
        "end_date": end_date,
        "selected_token_latest_dates": {
            token.symbol: latest_dates.get(token.symbol).isoformat() if latest_dates.get(token.symbol) is not None else None
            for token in selected_tokens
        },
    }


def _fetch_token_analysis_range(
    *,
    token: TronStablecoinTokenSpec,
    start_date: date,
    end_date: date,
    chunk_days: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    chunk_span = max(1, int(chunk_days))
    current = start_date
    while current <= end_date:
        chunk_end_inclusive = min(current + timedelta(days=chunk_span - 1), end_date)
        payload = _tronscan_get_json(
            path="/token/analysis",
            params={
                "token": token.contract_address,
                "start_day": current.isoformat(),
                "end_day": (chunk_end_inclusive + timedelta(days=1)).isoformat(),
            },
        )
        rows.extend(list(payload.get("data") or []))
        current = chunk_end_inclusive + timedelta(days=1)
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = str(row.get("day") or "").strip()
        if day:
            dedup[day] = dict(row)
    return [dedup[day] for day in sorted(dedup)]


def _fetch_tronscan_stats_overview(*, days: int) -> list[dict[str, Any]]:
    payload = _tronscan_get_json(
        path="/stats/overview",
        params={"days": max(1, int(days))},
    )
    return list(payload.get("data") or [])


def _tronscan_get_json(*, path: str, params: dict[str, object]) -> dict[str, Any]:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    url = f"{TRONSCAN_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    headers = dict(JSON_HEADERS)
    api_key = _resolve_tronscan_api_key()
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SEC) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError(f"TRONSCAN payload is not an object for path={path}")
                return payload
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"TRONSCAN HTTP {exc.code}: {body}")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == DEFAULT_MAX_ATTEMPTS:
                raise last_error from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == DEFAULT_MAX_ATTEMPTS:
                raise RuntimeError(f"TRONSCAN request failed after {attempt} attempts: {url}") from exc
        time.sleep(DEFAULT_RETRY_SLEEP_SEC * attempt)
    raise RuntimeError(f"TRONSCAN request failed unexpectedly: {url}") from last_error


def _build_daily_row(
    *,
    token: TronStablecoinTokenSpec,
    date_utc: str,
    analysis: dict[str, Any],
    stats: dict[str, Any] | None,
) -> dict[str, Any]:
    transfer_count = _as_int(analysis.get("transfer_count"))
    transfer_amount = _as_float(analysis.get("amount"))
    transfer_amount_usd = _as_float(analysis.get("amount_usd"))
    stats_usdt_transaction_count = _as_int(stats.get("usdt_transaction")) if stats is not None else None
    return {
        "date_utc": date_utc,
        "token_symbol": token.symbol,
        "contract_address": token.contract_address,
        "decimals": token.decimals,
        "transfer_count": transfer_count,
        "transfer_amount": transfer_amount,
        "transfer_amount_usd": transfer_amount_usd,
        "from_count": _as_int(analysis.get("from_count")),
        "to_count": _as_int(analysis.get("to_count")),
        "active_address_count": _as_int(analysis.get("transfer_address_count")),
        "holders_count": _as_int(analysis.get("holders")),
        "stats_usdt_transaction_count": stats_usdt_transaction_count,
        "stats_active_account_number": _as_int(stats.get("active_account_number")) if stats is not None else None,
        "stats_total_transaction_count": _as_int(stats.get("newTransactionSeen")) if stats is not None else None,
        "transfer_count_vs_stats_delta": (
            float(transfer_count - stats_usdt_transaction_count)
            if transfer_count is not None and stats_usdt_transaction_count is not None
            else None
        ),
        "coverage_start_utc": f"{date_utc}T00:00:00Z",
        "coverage_end_utc": f"{date_utc}T23:59:59Z",
        "is_full_day": True,
        "fetch_status": "complete",
        "source": "tronscan_public_api",
    }


def _read_daily_rows(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _latest_dates_by_symbol(*, existing_rows: list[dict[str, Any]]) -> dict[str, date]:
    latest: dict[str, date] = {}
    for row in existing_rows:
        symbol = str(row.get("token_symbol") or "").strip().upper()
        date_text = str(row.get("date_utc") or "").strip()
        if not symbol or not date_text:
            continue
        parsed = date.fromisoformat(date_text)
        if symbol not in latest or parsed > latest[symbol]:
            latest[symbol] = parsed
    return latest


def _merge_daily_rows(*, output_path: Path, replacement_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_rows = _read_daily_rows(output_path)
    keyed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing_rows:
        key = (str(row.get("date_utc") or ""), str(row.get("token_symbol") or ""))
        keyed[key] = row
    for row in replacement_rows:
        key = (str(row.get("date_utc") or ""), str(row.get("token_symbol") or ""))
        keyed[key] = row
    return [keyed[key] for key in sorted(keyed)]


def _write_daily_rows(*, output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header) for header in CSV_HEADERS})


def _expected_dates(start_date: date, end_date: date) -> list[str]:
    days: list[str] = []
    current = start_date
    while current <= end_date:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
