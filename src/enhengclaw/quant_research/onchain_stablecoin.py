from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.quant_research.onchain_address_labels import (
    load_address_label_snapshot,
    resolve_onchain_address_label_root,
)


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_FAMILY = "m3_2_stablecoin_ethereum_sync"
CONTRACT_VERSION = "m3_2_stablecoin_ethereum_sync.v3"
DEFAULT_EXTERNAL_ROOT_NAME = "onchain_stablecoin_ethereum"
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_SYNC_MODE = "auto"
DEFAULT_REFRESH_OVERLAP_DAYS = 3
DEFAULT_TRANSFER_PROVIDER = "alchemy_transfers"
DEFAULT_PAGE_SIZE = 1_000
DEFAULT_MAX_PAGES_PER_WINDOW = 20
DEFAULT_EXTENDED_MAX_PAGES_FACTOR = 10
DEFAULT_MIN_SPLIT_BLOCK_SPAN = 32
DEFAULT_COARSE_BLOCK_CHUNK_SPAN = 900
DEFAULT_RPC_LOG_BLOCK_CHUNK_SPAN = 256
DEFAULT_WHALE_THRESHOLD = 1_000_000.0
ETHEREUM_AVG_BLOCK_TIME_SEC = 12.0
BLOCK_ESTIMATE_EXPANSION_FLOOR = 2_048
BLOCK_ESTIMATE_EXPANSION_MULTIPLIER = 0.35
DEFAULT_RPC_MAX_ATTEMPTS = 4
DEFAULT_RPC_RETRY_SLEEP_SEC = 1.0
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
TRANSFER_EVENT_TOPIC0 = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
JSONRPC_VERSION = "2.0"
JSON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
ALCHEMY_RPC_TEMPLATE = "https://eth-mainnet.g.alchemy.com/v2/{api_key}"
CSV_HEADERS = (
    "date_utc",
    "token_symbol",
    "contract_address",
    "decimals",
    "transfer_count",
    "transfer_amount",
    "mint_count",
    "mint_amount",
    "burn_count",
    "burn_amount",
    "net_issuance_amount",
    "whale_transfer_count",
    "whale_transfer_amount",
    "exchange_inflow_amount",
    "exchange_outflow_amount",
    "exchange_netflow_amount",
    "whale_to_exchange_amount",
    "exchange_to_whale_amount",
    "issuer_to_exchange_amount",
    "bridge_inflow_amount",
    "bridge_outflow_amount",
    "labeled_transfer_share_amount",
    "unknown_transfer_share_amount",
    "unique_from_count",
    "unique_to_count",
    "coverage_start_utc",
    "coverage_end_utc",
    "is_full_day",
    "fetch_status",
    "source",
)


@dataclass(frozen=True, slots=True)
class StablecoinTokenSpec:
    symbol: str
    contract_address: str
    decimals: int


@dataclass(frozen=True, slots=True)
class StablecoinTransferProviderContext:
    provider_id: str
    source: str
    rpc_endpoint_url: str
    rpc_label: str
    alchemy_api_key: str | None = None


DEFAULT_TOKEN_SPECS: tuple[StablecoinTokenSpec, ...] = (
    StablecoinTokenSpec("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
    StablecoinTokenSpec("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
    StablecoinTokenSpec("DAI", "0x6B175474E89094C44Da98b954EedeAC495271d0F", 18),
)


def resolve_onchain_external_root(
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


def run_m3_2_stablecoin_sync(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    mode: str = DEFAULT_SYNC_MODE,
    refresh_overlap_days: int = DEFAULT_REFRESH_OVERLAP_DAYS,
    transfer_provider: str = DEFAULT_TRANSFER_PROVIDER,
    external_root: Path | None = None,
    token_symbols: Iterable[str] | None = None,
    whale_threshold: float = DEFAULT_WHALE_THRESHOLD,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages_per_window: int = DEFAULT_MAX_PAGES_PER_WINDOW,
    min_split_block_span: int = DEFAULT_MIN_SPLIT_BLOCK_SPAN,
    inter_page_sleep_sec: float = 0.05,
    start_date_override: date | None = None,
    end_date_override: date | None = None,
    address_label_root: Path | None = None,
    address_label_snapshot_path: Path | None = None,
    address_label_as_of_date: date | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    provider_context = _build_transfer_provider_context(transfer_provider)
    resolved_root = resolve_onchain_external_root(external_root=external_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    output_path = resolved_root / "daily_aggregates.csv"
    existing_rows = _read_daily_rows(output_path=output_path)
    selected_tokens = _select_tokens(token_symbols)
    latest_block_number, latest_block_timestamp = _eth_latest_block_snapshot_from_rpc(
        provider_context.rpc_endpoint_url,
        provider_label=provider_context.rpc_label,
    )
    sync_plan = _build_sync_plan(
        selected_tokens=selected_tokens,
        existing_rows=existing_rows,
        requested_mode=mode,
        lookback_days=lookback_days,
        refresh_overlap_days=refresh_overlap_days,
        end_dt=latest_block_timestamp,
        start_date_override=start_date_override,
        end_date_override=end_date_override,
    )
    label_snapshot, label_snapshot_metadata = load_address_label_snapshot(
        as_of_date=address_label_as_of_date or sync_plan["end_date"],
        external_root=resolve_onchain_address_label_root(external_root=address_label_root),
        snapshot_path=address_label_snapshot_path,
    )
    boundary_block_cache: dict[str, int] = {}
    block_timestamp_cache: dict[int, datetime] = {}
    daily_windows = _build_daily_windows(
        rpc_endpoint_url=provider_context.rpc_endpoint_url,
        provider_label=provider_context.rpc_label,
        latest_block_number=latest_block_number,
        latest_block_timestamp=latest_block_timestamp,
        start_date=sync_plan["start_date"],
        end_date=sync_plan["end_date"],
        end_dt=sync_plan["end_dt"],
        boundary_block_cache=boundary_block_cache,
        block_timestamp_cache=block_timestamp_cache,
    )

    daily_rows: list[dict[str, Any]] = []
    token_summaries: list[dict[str, Any]] = []
    overall_status = "success"
    for token in selected_tokens:
        token_pages_fetched = 0
        token_raw_transfer_count = 0
        token_included_transfer_count = 0
        token_leaf_window_count = 0
        token_split_count = 0
        token_residual_truncated_window_count = 0
        token_earliest_included_transfer_utc: str | None = None
        token_latest_included_transfer_utc: str | None = None
        token_window_summaries: list[dict[str, Any]] = []
        token_latest_daily_row: dict[str, Any] | None = None
        for window in daily_windows:
            fetch_summary = _fetch_token_window(
                provider_context=provider_context,
                token=token,
                start_dt=window["window_start_dt"],
                end_dt=window["window_end_dt"],
                from_block=int(window["from_block"]),
                to_block_exclusive=int(window["to_block_exclusive"]),
                page_size=page_size,
                max_pages_per_window=max_pages_per_window,
                min_split_block_span=min_split_block_span,
                inter_page_sleep_sec=inter_page_sleep_sec,
            )
            row = _aggregate_window_row(
                token=token,
                transfers=fetch_summary["included_transfers"],
                start_dt=window["window_start_dt"],
                end_dt=window["window_end_dt"],
                whale_threshold=whale_threshold,
                address_labels=label_snapshot,
                is_full_day=bool(window["is_full_day"]),
                fetch_status="partial" if fetch_summary["residual_truncated_window_count"] else "complete",
                source=provider_context.source,
            )
            daily_rows.append(row)
            token_latest_daily_row = row
            token_pages_fetched += int(fetch_summary["pages_fetched"])
            token_raw_transfer_count += int(fetch_summary["raw_transfer_count"])
            token_included_transfer_count += int(fetch_summary["included_transfer_count"])
            token_leaf_window_count += int(fetch_summary["leaf_window_count"])
            token_split_count += int(fetch_summary["split_count"])
            token_residual_truncated_window_count += int(fetch_summary["residual_truncated_window_count"])
            token_earliest_included_transfer_utc = _min_timestamp_str(
                token_earliest_included_transfer_utc,
                fetch_summary["earliest_included_transfer_utc"],
            )
            token_latest_included_transfer_utc = _max_timestamp_str(
                token_latest_included_transfer_utc,
                fetch_summary["latest_included_transfer_utc"],
            )
            if fetch_summary["residual_truncated_window_count"]:
                overall_status = "partial_success"
            token_window_summaries.append(
                {
                    "date_utc": row["date_utc"],
                    "window_start_utc": row["coverage_start_utc"],
                    "window_end_utc": row["coverage_end_utc"],
                    "is_full_day": bool(window["is_full_day"]),
                    "from_block": int(window["from_block"]),
                    "to_block_exclusive": int(window["to_block_exclusive"]),
                    "pages_fetched": int(fetch_summary["pages_fetched"]),
                    "raw_transfer_count": int(fetch_summary["raw_transfer_count"]),
                    "included_transfer_count": int(fetch_summary["included_transfer_count"]),
                    "leaf_window_count": int(fetch_summary["leaf_window_count"]),
                    "split_count": int(fetch_summary["split_count"]),
                    "residual_truncated_window_count": int(fetch_summary["residual_truncated_window_count"]),
                    "fetch_status": row["fetch_status"],
                }
            )
        token_summary = {
            "symbol": token.symbol,
            "contract_address": token.contract_address,
            "decimals": token.decimals,
            "pages_fetched": token_pages_fetched,
            "raw_transfer_count": token_raw_transfer_count,
            "included_transfer_count": token_included_transfer_count,
            "leaf_window_count": token_leaf_window_count,
            "split_count": token_split_count,
            "residual_truncated_window_count": token_residual_truncated_window_count,
            "earliest_included_transfer_utc": token_earliest_included_transfer_utc,
            "latest_included_transfer_utc": token_latest_included_transfer_utc,
            "daily_row_count": len(daily_windows),
            "daily_windows": token_window_summaries,
        }
        if token_latest_daily_row is not None:
            token_summary["latest_daily_row"] = token_latest_daily_row
        token_summaries.append(token_summary)

    merged_rows = _merge_daily_rows(output_path=output_path, replacement_rows=daily_rows)
    _write_daily_rows(output_path=output_path, rows=merged_rows)

    summary = with_evidence_metadata(
        {
            "status": overall_status,
            "success": True,
            "generated_at_utc": _utc_now(),
            "external_root": str(resolved_root),
            "output_path": str(output_path),
            "requested_mode": str(mode).strip().lower() or DEFAULT_SYNC_MODE,
            "effective_mode": sync_plan["effective_mode"],
            "transfer_provider": provider_context.provider_id,
            "lookback_days": int(lookback_days),
            "refresh_overlap_days": int(refresh_overlap_days),
            "sync_start_date_utc": sync_plan["start_date"].isoformat(),
            "sync_end_date_utc": sync_plan["end_date"].isoformat(),
            "window_start_utc": daily_windows[0]["window_start_dt"].isoformat().replace("+00:00", "Z"),
            "window_end_utc": daily_windows[-1]["window_end_dt"].isoformat().replace("+00:00", "Z"),
            "coverage_day_count": len(daily_windows),
            "selected_token_latest_dates_before_refresh": sync_plan["selected_token_latest_dates"],
            "latest_block_number": int(latest_block_number),
            "latest_block_timestamp_utc": latest_block_timestamp.isoformat().replace("+00:00", "Z"),
            "page_size": int(page_size),
            "max_pages_per_window": int(max_pages_per_window),
            "min_split_block_span": int(min_split_block_span),
            "whale_threshold": float(whale_threshold),
            "address_label_snapshot_path": label_snapshot_metadata.get("snapshot_path"),
            "address_label_snapshot_as_of_date_utc": label_snapshot_metadata.get("as_of_date_utc"),
            "address_label_record_count": int(label_snapshot_metadata.get("record_count", 0) or 0),
            "address_label_entity_type_counts": dict(label_snapshot_metadata.get("entity_type_counts") or {}),
            "token_count": len(selected_tokens),
            "requested_symbols": [token.symbol for token in selected_tokens],
            "written_row_count": len(daily_rows),
            "stored_row_count": len(merged_rows),
            "tokens": token_summaries,
            "input_watermarks": {
                "sync_start_date_utc": sync_plan["start_date"].isoformat(),
                "sync_end_date_utc": sync_plan["end_date"].isoformat(),
                "latest_block_number": int(latest_block_number),
                "latest_block_timestamp_utc": latest_block_timestamp.isoformat().replace("+00:00", "Z"),
            },
            "upstream_versions": {
                "rpc_label": provider_context.rpc_label,
                "source": provider_context.source,
                "default_token_symbols": [token.symbol for token in DEFAULT_TOKEN_SPECS],
                "avg_block_time_sec": ETHEREUM_AVG_BLOCK_TIME_SEC,
                "address_label_root": str(resolve_onchain_address_label_root(external_root=address_label_root)),
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


def _build_sync_plan(
    *,
    selected_tokens: tuple[StablecoinTokenSpec, ...],
    existing_rows: list[dict[str, Any]],
    requested_mode: str,
    lookback_days: int,
    refresh_overlap_days: int,
    end_dt: datetime,
    start_date_override: date | None = None,
    end_date_override: date | None = None,
) -> dict[str, Any]:
    requested = str(requested_mode).strip().lower() or DEFAULT_SYNC_MODE
    if requested not in {"auto", "bootstrap", "refresh"}:
        raise ValueError(f"unsupported M3.2 sync mode: {requested_mode!r}")
    if start_date_override is not None or end_date_override is not None:
        start_date = start_date_override or end_dt.date()
        end_date = end_date_override or end_dt.date()
        if start_date > end_date:
            raise ValueError(
                f"explicit stablecoin sync range is invalid: {start_date.isoformat()} > {end_date.isoformat()}"
            )
        effective_end_dt = end_dt if end_date >= end_dt.date() else datetime(
            end_date.year,
            end_date.month,
            end_date.day,
            23,
            59,
            59,
            tzinfo=UTC,
        ) + timedelta(seconds=1)
        return {
            "effective_mode": "explicit_range",
            "selected_token_latest_dates": {},
            "start_date": start_date,
            "end_date": end_date,
            "end_dt": effective_end_dt,
        }
    latest_dates = _latest_dates_by_token(existing_rows=existing_rows, selected_tokens=selected_tokens)
    effective_mode = requested
    if requested == "auto":
        effective_mode = "refresh" if latest_dates else "bootstrap"
    if effective_mode == "refresh" and not latest_dates:
        effective_mode = "bootstrap"

    if effective_mode == "bootstrap":
        start_date = end_dt.date() - timedelta(days=max(int(lookback_days), 1) - 1)
    else:
        fallback_start = end_dt.date() - timedelta(days=max(int(lookback_days), 1) - 1)
        overlap_days = max(int(refresh_overlap_days), 1)
        anchors = [latest_dates.get(token.symbol, fallback_start) for token in selected_tokens]
        start_date = min(anchors) - timedelta(days=overlap_days - 1)
    if start_date > end_dt.date():
        start_date = end_dt.date()
    return {
        "effective_mode": effective_mode,
        "selected_token_latest_dates": {symbol: value.isoformat() for symbol, value in latest_dates.items()},
        "start_date": start_date,
        "end_date": end_dt.date(),
        "end_dt": end_dt,
    }


def _latest_dates_by_token(
    *,
    existing_rows: list[dict[str, Any]],
    selected_tokens: tuple[StablecoinTokenSpec, ...],
) -> dict[str, date]:
    selected = {token.symbol for token in selected_tokens}
    latest: dict[str, date] = {}
    for row in existing_rows:
        symbol = str(row.get("token_symbol") or "").strip().upper()
        if symbol not in selected:
            continue
        day_text = str(row.get("date_utc") or "").strip()
        if not day_text:
            continue
        try:
            day_value = date.fromisoformat(day_text)
        except ValueError:
            continue
        previous = latest.get(symbol)
        if previous is None or day_value > previous:
            latest[symbol] = day_value
    return latest


def _require_alchemy_api_key() -> str:
    api_key = os.environ.get("ALCHEMY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ALCHEMY_API_KEY is required for M3.2 stablecoin sync")
    return api_key


def _build_transfer_provider_context(transfer_provider: str) -> StablecoinTransferProviderContext:
    provider_id = str(transfer_provider).strip().lower() or DEFAULT_TRANSFER_PROVIDER
    if provider_id == "alchemy_transfers":
        api_key = _require_alchemy_api_key()
        return StablecoinTransferProviderContext(
            provider_id=provider_id,
            source="alchemy_getAssetTransfers",
            rpc_endpoint_url=_alchemy_rpc_url(api_key),
            rpc_label="alchemy_rpc",
            alchemy_api_key=api_key,
        )
    if provider_id == "eth_rpc_logs":
        endpoint_url = _resolve_eth_rpc_url()
        return StablecoinTransferProviderContext(
            provider_id=provider_id,
            source="eth_getLogs",
            rpc_endpoint_url=endpoint_url,
            rpc_label=_rpc_label_from_url(endpoint_url),
            alchemy_api_key=None,
        )
    raise ValueError(f"unsupported M3.2 transfer provider: {transfer_provider!r}")


def _alchemy_rpc_url(api_key: str) -> str:
    return ALCHEMY_RPC_TEMPLATE.format(api_key=api_key)


def _resolve_eth_rpc_url(*, base_env: dict[str, str] | None = None) -> str:
    env = os.environ if base_env is None else base_env
    for name in ("ETH_RPC_URL", "ETHEREUM_RPC_URL", "EVM_ETH_RPC_URL"):
        candidate = str(env.get(name, "")).strip()
        if candidate:
            return candidate
    api_key = str(env.get("ALCHEMY_API_KEY", "")).strip()
    if api_key:
        return _alchemy_rpc_url(api_key)
    raise RuntimeError(
        "ETH_RPC_URL (or ETHEREUM_RPC_URL / EVM_ETH_RPC_URL) is required when transfer_provider=eth_rpc_logs"
    )


def _rpc_label_from_url(endpoint_url: str) -> str:
    host = urlparse(endpoint_url).netloc.lower()
    if "alchemy" in host:
        return "alchemy_rpc"
    if "infura" in host:
        return "infura_rpc"
    if "quicknode" in host:
        return "quicknode_rpc"
    if "ankr" in host:
        return "ankr_rpc"
    return host or "eth_rpc"


def _select_tokens(token_symbols: Iterable[str] | None) -> tuple[StablecoinTokenSpec, ...]:
    if token_symbols is None:
        return DEFAULT_TOKEN_SPECS
    requested = {str(item).strip().upper() for item in token_symbols if str(item).strip()}
    if not requested:
        return DEFAULT_TOKEN_SPECS
    selected = tuple(token for token in DEFAULT_TOKEN_SPECS if token.symbol in requested)
    if not selected:
        raise ValueError(f"no supported stablecoin symbols requested: {sorted(requested)}")
    return selected


def _json_rpc_post(
    endpoint_url: str,
    *,
    provider_label: str,
    method: str,
    params: list[dict[str, Any]] | list[Any],
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "id": 1,
            "method": method,
            "params": params,
        }
    ).encode("utf-8")
    request = Request(endpoint_url, data=payload, headers=JSON_HEADERS, method="POST")
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_RPC_MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
            decoded = json.loads(body)
            if "error" in decoded:
                raise RuntimeError(f"{provider_label} {method} error: {decoded['error']}")
            return decoded
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            should_retry = exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
            last_error = RuntimeError(f"{provider_label} {method} HTTP {exc.code}: {body}")
            if not should_retry or attempt >= DEFAULT_RPC_MAX_ATTEMPTS:
                raise last_error from exc
        except (IncompleteRead, URLError, json.JSONDecodeError, TimeoutError) as exc:
            last_error = exc
            if attempt >= DEFAULT_RPC_MAX_ATTEMPTS:
                raise RuntimeError(f"{provider_label} {method} request failed after retries: {exc}") from exc
        time.sleep(DEFAULT_RPC_RETRY_SLEEP_SEC * attempt)
    raise RuntimeError(f"{provider_label} {method} request failed after retries: {last_error}")


def _alchemy_post(api_key: str, *, method: str, params: list[dict[str, Any]] | list[Any]) -> dict[str, Any]:
    return _json_rpc_post(
        _alchemy_rpc_url(api_key),
        provider_label="alchemy_rpc",
        method=method,
        params=params,
    )


def _eth_latest_block_snapshot_from_rpc(endpoint_url: str, *, provider_label: str) -> tuple[int, datetime]:
    payload = _json_rpc_post(endpoint_url, provider_label=provider_label, method="eth_blockNumber", params=[])
    latest_block_number = int(str(payload["result"]), 16)
    block_payload = _json_rpc_post(
        endpoint_url,
        provider_label=provider_label,
        method="eth_getBlockByNumber",
        params=[hex(latest_block_number), False],
    )
    block_result = dict(block_payload.get("result") or {})
    block_timestamp = datetime.fromtimestamp(int(str(block_result["timestamp"]), 16), tz=UTC)
    return latest_block_number, block_timestamp


def _build_daily_windows(
    *,
    rpc_endpoint_url: str,
    provider_label: str,
    latest_block_number: int,
    latest_block_timestamp: datetime,
    start_date: date,
    end_date: date,
    end_dt: datetime,
    boundary_block_cache: dict[str, int],
    block_timestamp_cache: dict[int, datetime],
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    current = start_date
    while current <= end_date:
        window_start_dt = datetime(current.year, current.month, current.day, tzinfo=UTC)
        next_day = current + timedelta(days=1)
        full_day_end_dt = datetime(next_day.year, next_day.month, next_day.day, tzinfo=UTC)
        is_full_day = current < end_date or end_dt == full_day_end_dt
        window_end_dt = full_day_end_dt if is_full_day else end_dt
        from_block = _boundary_block_at_or_after(
            rpc_endpoint_url=rpc_endpoint_url,
            provider_label=provider_label,
            latest_block_number=latest_block_number,
            latest_block_timestamp=latest_block_timestamp,
            target_dt=window_start_dt,
            boundary_block_cache=boundary_block_cache,
            block_timestamp_cache=block_timestamp_cache,
        )
        if is_full_day:
            to_block_exclusive = _boundary_block_at_or_after(
                rpc_endpoint_url=rpc_endpoint_url,
                provider_label=provider_label,
                latest_block_number=latest_block_number,
                latest_block_timestamp=latest_block_timestamp,
                target_dt=full_day_end_dt,
                boundary_block_cache=boundary_block_cache,
                block_timestamp_cache=block_timestamp_cache,
            )
        else:
            to_block_exclusive = latest_block_number + 1
        windows.append(
            {
                "date_utc": current.isoformat(),
                "window_start_dt": window_start_dt,
                "window_end_dt": window_end_dt,
                "from_block": max(0, int(from_block)),
                "to_block_exclusive": max(int(from_block), int(to_block_exclusive)),
                "is_full_day": is_full_day,
            }
        )
        current = next_day
    return windows


def _boundary_block_at_or_after(
    *,
    rpc_endpoint_url: str,
    provider_label: str,
    latest_block_number: int,
    latest_block_timestamp: datetime,
    target_dt: datetime,
    boundary_block_cache: dict[str, int],
    block_timestamp_cache: dict[int, datetime],
) -> int:
    key = target_dt.isoformat()
    cached = boundary_block_cache.get(key)
    if cached is not None:
        return cached
    located = _locate_block_at_or_after(
        rpc_endpoint_url=rpc_endpoint_url,
        provider_label=provider_label,
        latest_block_number=latest_block_number,
        latest_block_timestamp=latest_block_timestamp,
        target_dt=target_dt,
        block_timestamp_cache=block_timestamp_cache,
    )
    boundary_block_cache[key] = int(located)
    return int(located)


def _locate_block_at_or_after(
    *,
    rpc_endpoint_url: str,
    provider_label: str,
    latest_block_number: int,
    latest_block_timestamp: datetime,
    target_dt: datetime,
    block_timestamp_cache: dict[int, datetime],
) -> int:
    if target_dt > latest_block_timestamp:
        return latest_block_number + 1

    estimate = _estimate_block_number_for_timestamp(
        latest_block_number=latest_block_number,
        latest_block_timestamp=latest_block_timestamp,
        target_dt=target_dt,
    )
    seconds_delta = max(0.0, (latest_block_timestamp - target_dt).total_seconds())
    estimated_block_delta = int(seconds_delta / ETHEREUM_AVG_BLOCK_TIME_SEC)
    expansion = max(
        BLOCK_ESTIMATE_EXPANSION_FLOOR,
        int(estimated_block_delta * BLOCK_ESTIMATE_EXPANSION_MULTIPLIER),
    )
    low = max(0, estimate - expansion)
    high = min(latest_block_number, estimate + expansion)
    low_ts = _eth_block_timestamp_from_rpc(
        rpc_endpoint_url,
        low,
        provider_label=provider_label,
        block_timestamp_cache=block_timestamp_cache,
    )
    while low > 0 and low_ts > target_dt:
        high = low
        low = max(0, low - expansion)
        expansion *= 2
        low_ts = _eth_block_timestamp_from_rpc(
            rpc_endpoint_url,
            low,
            provider_label=provider_label,
            block_timestamp_cache=block_timestamp_cache,
        )
    high_ts = _eth_block_timestamp_from_rpc(
        rpc_endpoint_url,
        high,
        provider_label=provider_label,
        block_timestamp_cache=block_timestamp_cache,
    )
    while high < latest_block_number and high_ts < target_dt:
        low = min(latest_block_number, high + 1)
        high = min(latest_block_number, high + expansion)
        expansion *= 2
        high_ts = _eth_block_timestamp_from_rpc(
            rpc_endpoint_url,
            high,
            provider_label=provider_label,
            block_timestamp_cache=block_timestamp_cache,
        )
    if high == latest_block_number and high_ts < target_dt:
        return latest_block_number + 1

    while low < high:
        mid = (low + high) // 2
        mid_ts = _eth_block_timestamp_from_rpc(
            rpc_endpoint_url,
            mid,
            provider_label=provider_label,
            block_timestamp_cache=block_timestamp_cache,
        )
        if mid_ts < target_dt:
            low = mid + 1
        else:
            high = mid
    return int(low)


def _estimate_block_number_for_timestamp(
    *,
    latest_block_number: int,
    latest_block_timestamp: datetime,
    target_dt: datetime,
) -> int:
    seconds_delta = max(0.0, (latest_block_timestamp - target_dt).total_seconds())
    estimated_blocks_back = int(seconds_delta / ETHEREUM_AVG_BLOCK_TIME_SEC)
    return max(0, int(latest_block_number) - estimated_blocks_back)


def _eth_block_timestamp_from_rpc(
    endpoint_url: str,
    block_number: int,
    *,
    provider_label: str,
    block_timestamp_cache: dict[int, datetime],
) -> datetime:
    cached = block_timestamp_cache.get(int(block_number))
    if cached is not None:
        return cached
    payload = _json_rpc_post(
        endpoint_url,
        provider_label=provider_label,
        method="eth_getBlockByNumber",
        params=[hex(int(block_number)), False],
    )
    block_result = dict(payload.get("result") or {})
    timestamp = datetime.fromtimestamp(int(str(block_result["timestamp"]), 16), tz=UTC)
    block_timestamp_cache[int(block_number)] = timestamp
    return timestamp


def _fetch_token_window(
    *,
    provider_context: StablecoinTransferProviderContext,
    token: StablecoinTokenSpec,
    start_dt: datetime,
    end_dt: datetime,
    from_block: int,
    to_block_exclusive: int,
    page_size: int,
    max_pages_per_window: int,
    min_split_block_span: int,
    inter_page_sleep_sec: float,
) -> dict[str, Any]:
    if to_block_exclusive <= from_block:
        return _empty_fetch_summary()
    if provider_context.provider_id == "alchemy_transfers":
        return _fetch_token_window_alchemy(
            api_key=str(provider_context.alchemy_api_key or ""),
            token=token,
            start_dt=start_dt,
            end_dt=end_dt,
            from_block=from_block,
            to_block_exclusive=to_block_exclusive,
            page_size=page_size,
            max_pages_per_window=max_pages_per_window,
            min_split_block_span=min_split_block_span,
            inter_page_sleep_sec=inter_page_sleep_sec,
        )
    if provider_context.provider_id == "eth_rpc_logs":
        return _fetch_token_window_rpc_logs(
            endpoint_url=provider_context.rpc_endpoint_url,
            provider_label=provider_context.rpc_label,
            token=token,
            start_dt=start_dt,
            end_dt=end_dt,
            from_block=from_block,
            to_block_exclusive=to_block_exclusive,
            min_split_block_span=min_split_block_span,
        )
    raise ValueError(f"unsupported M3.2 transfer provider: {provider_context.provider_id!r}")


def _empty_fetch_summary() -> dict[str, Any]:
    return {
        "pages_fetched": 0,
        "raw_transfer_count": 0,
        "included_transfer_count": 0,
        "included_transfers": [],
        "leaf_window_count": 1,
        "split_count": 0,
        "residual_truncated_window_count": 0,
        "earliest_included_transfer_utc": None,
        "latest_included_transfer_utc": None,
    }


def _fetch_token_window_alchemy(
    *,
    api_key: str,
    token: StablecoinTokenSpec,
    start_dt: datetime,
    end_dt: datetime,
    from_block: int,
    to_block_exclusive: int,
    page_size: int,
    max_pages_per_window: int,
    min_split_block_span: int,
    inter_page_sleep_sec: float,
) -> dict[str, Any]:
    included_transfers: list[dict[str, Any]] = []
    pages_fetched = 0
    raw_transfer_count = 0
    leaf_window_count = 0
    split_count = 0
    residual_truncated_window_count = 0
    for chunk_from, chunk_to_exclusive in _iter_block_chunks(
        from_block=from_block,
        to_block_exclusive=to_block_exclusive,
        chunk_span=max(DEFAULT_COARSE_BLOCK_CHUNK_SPAN, int(min_split_block_span) * 4),
    ):
        recursive = _fetch_token_window_recursive(
            api_key=api_key,
            token=token,
            start_dt=start_dt,
            end_dt=end_dt,
            from_block=chunk_from,
            to_block=chunk_to_exclusive - 1,
            page_size=page_size,
            max_pages_per_window=max_pages_per_window,
            min_split_block_span=min_split_block_span,
            inter_page_sleep_sec=inter_page_sleep_sec,
        )
        included_transfers.extend(recursive["included_transfers"])
        pages_fetched += int(recursive["pages_fetched"])
        raw_transfer_count += int(recursive["raw_transfer_count"])
        leaf_window_count += int(recursive["leaf_window_count"])
        split_count += int(recursive["split_count"])
        residual_truncated_window_count += int(recursive["residual_truncated_window_count"])
    deduped_transfers = _dedupe_transfers(included_transfers)
    earliest_ts: str | None = None
    latest_ts: str | None = None
    for transfer in deduped_transfers:
        transfer_ts = _parse_transfer_timestamp(transfer)
        if transfer_ts is None:
            continue
        iso_value = transfer_ts.isoformat().replace("+00:00", "Z")
        earliest_ts = _min_timestamp_str(earliest_ts, iso_value)
        latest_ts = _max_timestamp_str(latest_ts, iso_value)
    return {
        "pages_fetched": pages_fetched,
        "raw_transfer_count": raw_transfer_count,
        "included_transfer_count": len(deduped_transfers),
        "included_transfers": deduped_transfers,
        "leaf_window_count": leaf_window_count,
        "split_count": split_count,
        "residual_truncated_window_count": residual_truncated_window_count,
        "earliest_included_transfer_utc": earliest_ts,
        "latest_included_transfer_utc": latest_ts,
    }


def _fetch_token_window_rpc_logs(
    *,
    endpoint_url: str,
    provider_label: str,
    token: StablecoinTokenSpec,
    start_dt: datetime,
    end_dt: datetime,
    from_block: int,
    to_block_exclusive: int,
    min_split_block_span: int,
) -> dict[str, Any]:
    if to_block_exclusive <= from_block:
        return _empty_fetch_summary()
    included_transfers: list[dict[str, Any]] = []
    request_count = 0
    raw_transfer_count = 0
    leaf_window_count = 0
    split_count = 0
    chunk_span = max(DEFAULT_RPC_LOG_BLOCK_CHUNK_SPAN, int(min_split_block_span) * 8)
    for chunk_from, chunk_to_exclusive in _iter_block_chunks(
        from_block=from_block,
        to_block_exclusive=to_block_exclusive,
        chunk_span=chunk_span,
    ):
        recursive = _fetch_token_window_rpc_logs_recursive(
            endpoint_url=endpoint_url,
            provider_label=provider_label,
            token=token,
            from_block=chunk_from,
            to_block=chunk_to_exclusive - 1,
            min_split_block_span=min_split_block_span,
        )
        included_transfers.extend(recursive["included_transfers"])
        request_count += int(recursive["pages_fetched"])
        raw_transfer_count += int(recursive["raw_transfer_count"])
        leaf_window_count += int(recursive["leaf_window_count"])
        split_count += int(recursive["split_count"])
    deduped_transfers = _dedupe_transfers(included_transfers)
    return {
        "pages_fetched": request_count,
        "raw_transfer_count": raw_transfer_count,
        "included_transfer_count": len(deduped_transfers),
        "included_transfers": deduped_transfers,
        "leaf_window_count": leaf_window_count,
        "split_count": split_count,
        "residual_truncated_window_count": 0,
        "earliest_included_transfer_utc": start_dt.isoformat().replace("+00:00", "Z"),
        "latest_included_transfer_utc": end_dt.isoformat().replace("+00:00", "Z"),
    }


def _fetch_token_window_rpc_logs_recursive(
    *,
    endpoint_url: str,
    provider_label: str,
    token: StablecoinTokenSpec,
    from_block: int,
    to_block: int,
    min_split_block_span: int,
) -> dict[str, Any]:
    try:
        raw_logs = _eth_get_logs_block_range(
            endpoint_url=endpoint_url,
            provider_label=provider_label,
            contract_address=token.contract_address,
            from_block=from_block,
            to_block=to_block,
        )
        transfers = [
            decoded
            for decoded in (
                _decode_erc20_transfer_log(token=token, raw_log=raw_log)
                for raw_log in raw_logs
            )
            if decoded is not None
        ]
        return {
            "pages_fetched": 1,
            "raw_transfer_count": len(raw_logs),
            "included_transfers": transfers,
            "leaf_window_count": 1,
            "split_count": 0,
        }
    except RuntimeError as exc:
        if (to_block - from_block) <= max(int(min_split_block_span), 0) or not _rpc_error_is_range_too_wide(exc):
            raise
    midpoint = (from_block + to_block) // 2
    left = _fetch_token_window_rpc_logs_recursive(
        endpoint_url=endpoint_url,
        provider_label=provider_label,
        token=token,
        from_block=from_block,
        to_block=midpoint,
        min_split_block_span=min_split_block_span,
    )
    right = _fetch_token_window_rpc_logs_recursive(
        endpoint_url=endpoint_url,
        provider_label=provider_label,
        token=token,
        from_block=midpoint + 1,
        to_block=to_block,
        min_split_block_span=min_split_block_span,
    )
    return {
        "pages_fetched": int(left["pages_fetched"]) + int(right["pages_fetched"]),
        "raw_transfer_count": int(left["raw_transfer_count"]) + int(right["raw_transfer_count"]),
        "included_transfers": list(left["included_transfers"]) + list(right["included_transfers"]),
        "leaf_window_count": int(left["leaf_window_count"]) + int(right["leaf_window_count"]),
        "split_count": 1 + int(left["split_count"]) + int(right["split_count"]),
    }


def _eth_get_logs_block_range(
    *,
    endpoint_url: str,
    provider_label: str,
    contract_address: str,
    from_block: int,
    to_block: int,
) -> list[dict[str, Any]]:
    payload = _json_rpc_post(
        endpoint_url,
        provider_label=provider_label,
        method="eth_getLogs",
        params=[
            {
                "fromBlock": hex(int(from_block)),
                "toBlock": hex(int(to_block)),
                "address": contract_address,
                "topics": [TRANSFER_EVENT_TOPIC0],
            }
        ],
    )
    return list(payload.get("result") or [])


def _decode_erc20_transfer_log(
    *,
    token: StablecoinTokenSpec,
    raw_log: dict[str, Any],
) -> dict[str, Any] | None:
    topics = list(raw_log.get("topics") or [])
    if len(topics) < 3:
        return None
    try:
        raw_value = int(str(raw_log.get("data") or "0x0"), 16)
    except ValueError:
        return None
    return {
        "hash": str(raw_log.get("transactionHash") or "").strip(),
        "transactionHash": str(raw_log.get("transactionHash") or "").strip(),
        "logIndex": str(raw_log.get("logIndex") or "").strip(),
        "blockNumber": str(raw_log.get("blockNumber") or "").strip(),
        "blockHash": str(raw_log.get("blockHash") or "").strip(),
        "from": _topic_to_address(str(topics[1])),
        "to": _topic_to_address(str(topics[2])),
        "value": raw_value / float(10 ** token.decimals),
        "asset": token.symbol,
        "category": "erc20",
        "rawContract": {"address": token.contract_address},
    }


def _topic_to_address(topic_value: str) -> str:
    normalized = str(topic_value).strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    if len(normalized) < 40:
        normalized = normalized.rjust(40, "0")
    return "0x" + normalized[-40:]


def _rpc_error_is_range_too_wide(exc: Exception) -> bool:
    message = str(exc).lower()
    hints = (
        "response size",
        "too many results",
        "query returned more than",
        "limit the query",
        "block range is too wide",
        "result window is too large",
        "exceeds the max limit",
        "timeout",
    )
    return any(hint in message for hint in hints)


def _fetch_token_window_recursive(
    *,
    api_key: str,
    token: StablecoinTokenSpec,
    start_dt: datetime,
    end_dt: datetime,
    from_block: int,
    to_block: int,
    page_size: int,
    max_pages_per_window: int,
    min_split_block_span: int,
    inter_page_sleep_sec: float,
) -> dict[str, Any]:
    initial = _fetch_token_window_pages(
        api_key=api_key,
        token=token,
        start_dt=start_dt,
        end_dt=end_dt,
        from_block=from_block,
        to_block=to_block,
        page_size=page_size,
        max_pages=max_pages_per_window,
        inter_page_sleep_sec=inter_page_sleep_sec,
    )
    if not initial["page_truncated"]:
        return {
            "pages_fetched": int(initial["pages_fetched"]),
            "raw_transfer_count": int(initial["raw_transfer_count"]),
            "included_transfers": list(initial["included_transfers"]),
            "leaf_window_count": 1,
            "split_count": 0,
            "residual_truncated_window_count": 0,
        }

    if (to_block - from_block) <= max(int(min_split_block_span), 0):
        extended = _fetch_token_window_pages(
            api_key=api_key,
            token=token,
            start_dt=start_dt,
            end_dt=end_dt,
            from_block=from_block,
            to_block=to_block,
            page_size=page_size,
            max_pages=max_pages_per_window * DEFAULT_EXTENDED_MAX_PAGES_FACTOR,
            inter_page_sleep_sec=inter_page_sleep_sec,
        )
        return {
            "pages_fetched": int(initial["pages_fetched"]) + int(extended["pages_fetched"]),
            "raw_transfer_count": int(extended["raw_transfer_count"]),
            "included_transfers": list(extended["included_transfers"]),
            "leaf_window_count": 1,
            "split_count": 0,
            "residual_truncated_window_count": 1 if extended["page_truncated"] else 0,
        }

    midpoint = (from_block + to_block) // 2
    right = _fetch_token_window_recursive(
        api_key=api_key,
        token=token,
        start_dt=start_dt,
        end_dt=end_dt,
        from_block=midpoint + 1,
        to_block=to_block,
        page_size=page_size,
        max_pages_per_window=max_pages_per_window,
        min_split_block_span=min_split_block_span,
        inter_page_sleep_sec=inter_page_sleep_sec,
    )
    left = _fetch_token_window_recursive(
        api_key=api_key,
        token=token,
        start_dt=start_dt,
        end_dt=end_dt,
        from_block=from_block,
        to_block=midpoint,
        page_size=page_size,
        max_pages_per_window=max_pages_per_window,
        min_split_block_span=min_split_block_span,
        inter_page_sleep_sec=inter_page_sleep_sec,
    )
    return {
        "pages_fetched": int(initial["pages_fetched"]) + int(left["pages_fetched"]) + int(right["pages_fetched"]),
        "raw_transfer_count": int(left["raw_transfer_count"]) + int(right["raw_transfer_count"]),
        "included_transfers": list(right["included_transfers"]) + list(left["included_transfers"]),
        "leaf_window_count": int(left["leaf_window_count"]) + int(right["leaf_window_count"]),
        "split_count": 1 + int(left["split_count"]) + int(right["split_count"]),
        "residual_truncated_window_count": int(left["residual_truncated_window_count"])
        + int(right["residual_truncated_window_count"]),
    }


def _fetch_token_window_pages(
    *,
    api_key: str,
    token: StablecoinTokenSpec,
    start_dt: datetime,
    end_dt: datetime,
    from_block: int,
    to_block: int,
    page_size: int,
    max_pages: int,
    inter_page_sleep_sec: float,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "fromBlock": hex(int(from_block)),
        "toBlock": hex(int(to_block)),
        "contractAddresses": [token.contract_address],
        "category": ["erc20"],
        "withMetadata": True,
        "excludeZeroValue": False,
        "maxCount": hex(int(page_size)),
        "order": "desc",
    }
    included_transfers: list[dict[str, Any]] = []
    raw_transfer_count = 0
    page_truncated = False
    page_key: str | None = None
    pages_fetched = 0
    while True:
        request_params = dict(params)
        if page_key:
            request_params["pageKey"] = page_key
        payload = _alchemy_post(api_key, method="alchemy_getAssetTransfers", params=[request_params])
        result = dict(payload.get("result") or {})
        page_transfers = list(result.get("transfers") or [])
        raw_transfer_count += len(page_transfers)
        for transfer in page_transfers:
            transfer_ts = _parse_transfer_timestamp(transfer)
            if transfer_ts is None or transfer_ts < start_dt or transfer_ts >= end_dt:
                continue
            included_transfers.append(transfer)
        pages_fetched += 1
        page_key = str(result.get("pageKey") or "").strip() or None
        if not page_key:
            break
        if pages_fetched >= max_pages:
            page_truncated = True
            break
        time.sleep(inter_page_sleep_sec)
    return {
        "pages_fetched": pages_fetched,
        "page_truncated": page_truncated,
        "raw_transfer_count": raw_transfer_count,
        "included_transfers": included_transfers,
    }


def _iter_block_chunks(*, from_block: int, to_block_exclusive: int, chunk_span: int) -> Iterable[tuple[int, int]]:
    current = int(from_block)
    stop = int(to_block_exclusive)
    step = max(int(chunk_span), 1)
    while current < stop:
        chunk_stop = min(stop, current + step)
        yield current, chunk_stop
        current = chunk_stop


def _parse_transfer_timestamp(transfer: dict[str, Any]) -> datetime | None:
    metadata = dict(transfer.get("metadata") or {})
    block_timestamp = str(metadata.get("blockTimestamp") or "").strip()
    if not block_timestamp:
        return None
    return datetime.fromisoformat(block_timestamp.replace("Z", "+00:00")).astimezone(UTC)


def _dedupe_transfers(transfers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for transfer in transfers:
        identity = _transfer_identity(transfer)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(transfer)
    return deduped


def _transfer_identity(transfer: dict[str, Any]) -> str:
    unique_id = str(transfer.get("uniqueId") or "").strip()
    if unique_id:
        return unique_id
    tx_hash = str(transfer.get("hash") or transfer.get("transactionHash") or "").strip().lower()
    log_index = str(transfer.get("logIndex") or "").strip()
    if not log_index:
        raw_contract = dict(transfer.get("rawContract") or {})
        log_index = str(raw_contract.get("logIndex") or "").strip()
    category = str(transfer.get("category") or "").strip().lower()
    asset = str(transfer.get("asset") or "").strip().upper()
    return f"{tx_hash}:{log_index}:{category}:{asset}"


def _aggregate_window_row(
    *,
    token: StablecoinTokenSpec,
    transfers: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
    whale_threshold: float,
    address_labels: dict[str, dict[str, Any]] | None,
    is_full_day: bool,
    fetch_status: str,
    source: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date_utc": start_dt.date().isoformat(),
        "token_symbol": token.symbol,
        "contract_address": token.contract_address,
        "decimals": token.decimals,
        "transfer_count": 0,
        "transfer_amount": 0.0,
        "mint_count": 0,
        "mint_amount": 0.0,
        "burn_count": 0,
        "burn_amount": 0.0,
        "net_issuance_amount": 0.0,
        "whale_transfer_count": 0,
        "whale_transfer_amount": 0.0,
        "exchange_inflow_amount": 0.0,
        "exchange_outflow_amount": 0.0,
        "exchange_netflow_amount": 0.0,
        "whale_to_exchange_amount": 0.0,
        "exchange_to_whale_amount": 0.0,
        "issuer_to_exchange_amount": 0.0,
        "bridge_inflow_amount": 0.0,
        "bridge_outflow_amount": 0.0,
        "labeled_transfer_share_amount": 0.0,
        "unknown_transfer_share_amount": 0.0,
        "unique_from": set(),
        "unique_to": set(),
        "coverage_start_utc": start_dt.isoformat().replace("+00:00", "Z"),
        "coverage_end_utc": end_dt.isoformat().replace("+00:00", "Z"),
        "is_full_day": "true" if is_full_day else "false",
        "fetch_status": fetch_status,
        "source": source,
    }
    for transfer in transfers:
        transfer_ts = _parse_transfer_timestamp(transfer)
        if transfer_ts is not None and (transfer_ts < start_dt or transfer_ts >= end_dt):
            continue
        value = float(transfer.get("value") or 0.0)
        from_address = str(transfer.get("from") or "").lower()
        to_address = str(transfer.get("to") or "").lower()
        from_role = _resolve_address_role(from_address, address_labels)
        to_role = _resolve_address_role(to_address, address_labels)
        row["transfer_count"] += 1
        row["transfer_amount"] += value
        if from_address:
            row["unique_from"].add(from_address)
        if to_address:
            row["unique_to"].add(to_address)
        if bool(from_role.get("is_labeled")) or bool(to_role.get("is_labeled")):
            row["labeled_transfer_share_amount"] += value
        else:
            row["unknown_transfer_share_amount"] += value
        if from_address == ZERO_ADDRESS:
            row["mint_count"] += 1
            row["mint_amount"] += value
        if to_address == ZERO_ADDRESS:
            row["burn_count"] += 1
            row["burn_amount"] += value
        if to_role["entity_type"] == "exchange" and from_role["entity_type"] != "exchange":
            row["exchange_inflow_amount"] += value
        if from_role["entity_type"] == "exchange" and to_role["entity_type"] != "exchange":
            row["exchange_outflow_amount"] += value
        if to_role["entity_type"] == "bridge" and from_role["entity_type"] != "bridge":
            row["bridge_inflow_amount"] += value
        if from_role["entity_type"] == "bridge" and to_role["entity_type"] != "bridge":
            row["bridge_outflow_amount"] += value
        if to_role["entity_type"] == "exchange" and from_role["entity_type"] in {"issuer", "treasury"}:
            row["issuer_to_exchange_amount"] += value
        if value >= whale_threshold:
            row["whale_transfer_count"] += 1
            row["whale_transfer_amount"] += value
            if to_role["entity_type"] == "exchange" and from_role["entity_type"] != "exchange":
                row["whale_to_exchange_amount"] += value
            if from_role["entity_type"] == "exchange" and to_role["entity_type"] != "exchange":
                row["exchange_to_whale_amount"] += value
    row["unique_from_count"] = len(row.pop("unique_from"))
    row["unique_to_count"] = len(row.pop("unique_to"))
    row["net_issuance_amount"] = float(row["mint_amount"]) - float(row["burn_amount"])
    row["exchange_netflow_amount"] = float(row["exchange_inflow_amount"]) - float(row["exchange_outflow_amount"])
    for field in (
        "transfer_amount",
        "mint_amount",
        "burn_amount",
        "net_issuance_amount",
        "whale_transfer_amount",
        "exchange_inflow_amount",
        "exchange_outflow_amount",
        "exchange_netflow_amount",
        "whale_to_exchange_amount",
        "exchange_to_whale_amount",
        "issuer_to_exchange_amount",
        "bridge_inflow_amount",
        "bridge_outflow_amount",
        "labeled_transfer_share_amount",
        "unknown_transfer_share_amount",
    ):
        row[field] = round(float(row[field]), 6)
    return row


def _resolve_address_role(
    address: str,
    address_labels: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    normalized = str(address or "").strip().lower()
    if not normalized:
        return {"entity_type": "unknown", "entity_name": "", "is_labeled": False}
    if normalized == ZERO_ADDRESS:
        return {
            "entity_type": "issuer",
            "entity_name": "Zero Address",
            "is_labeled": True,
        }
    if address_labels:
        row = address_labels.get(normalized)
        if row is not None:
            return {
                "entity_type": str(row.get("entity_type") or "unknown"),
                "entity_name": str(row.get("entity_name") or normalized),
                "is_labeled": True,
            }
    return {"entity_type": "unknown", "entity_name": normalized, "is_labeled": False}


def _merge_daily_rows(*, output_path: Path, replacement_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_rows = _read_daily_rows(output_path=output_path)
    replacement_keys = {
        (str(row["date_utc"]), str(row["token_symbol"]))
        for row in replacement_rows
    }
    preserved_rows = [
        row
        for row in existing_rows
        if (str(row["date_utc"]), str(row["token_symbol"])) not in replacement_keys
    ]
    merged_rows = preserved_rows + replacement_rows
    merged_rows.sort(key=lambda row: (str(row["date_utc"]), str(row["token_symbol"])))
    return merged_rows


def _read_daily_rows(*, output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(dict(row))
    return rows


def _write_daily_rows(*, output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_HEADERS})


def _min_timestamp_str(left: str | None, right: str | None) -> str | None:
    if not right:
        return left
    if not left:
        return right
    return right if right < left else left


def _max_timestamp_str(left: str | None, right: str | None) -> str | None:
    if not right:
        return left
    if not left:
        return right
    return right if right > left else left


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
