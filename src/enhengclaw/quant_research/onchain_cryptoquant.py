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
ARTIFACT_FAMILY = "m3_2_cryptoquant_sync"
CONTRACT_VERSION = "m3_2_cryptoquant_sync.v1"
DEFAULT_EXTERNAL_ROOT_NAME = "onchain_cryptoquant"
DEFAULT_SYNC_MODE = "auto"
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_REFRESH_OVERLAP_DAYS = 7
DEFAULT_WINDOW = "day"
DEFAULT_REQUEST_TIMEOUT_SEC = 30
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_SLEEP_SEC = 1.0
DEFAULT_MAX_LIMIT = 100_000
CRYPTOQUANT_API_BASE = "https://api.cryptoquant.com/v1"
JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}
STABLECOIN_SUPPLY_HEADERS = (
    "date_utc",
    "token_id",
    "window",
    "supply_total",
    "supply_circulating",
    "supply_minted",
    "supply_burned",
    "supply_issued",
    "supply_redeemed",
    "tokens_transferred_total",
    "tokens_transferred_mean",
    "addresses_active_count",
    "addresses_active_sender_count",
    "addresses_active_receiver_count",
    "addresses_active_sender_percent",
    "addresses_active_receiver_percent",
    "source",
)
STABLECOIN_EXCHANGE_FLOW_HEADERS = (
    "date_utc",
    "token_id",
    "exchange",
    "window",
    "reserve",
    "inflow_total",
    "inflow_top10",
    "inflow_mean",
    "outflow_total",
    "outflow_top10",
    "outflow_mean",
    "netflow_total",
    "transactions_count_inflow",
    "transactions_count_outflow",
    "addresses_count_inflow",
    "addresses_count_outflow",
    "source",
)
REFLEXIVITY_EXCHANGE_FLOW_HEADERS = (
    "date_utc",
    "asset_id",
    "exchange",
    "window",
    "reserve",
    "reserve_usd",
    "inflow_total",
    "inflow_top10",
    "inflow_mean",
    "outflow_total",
    "outflow_top10",
    "outflow_mean",
    "netflow_total",
    "transactions_count_inflow",
    "transactions_count_outflow",
    "addresses_count_inflow",
    "addresses_count_outflow",
    "source",
)
REFLEXIVITY_MARKET_HEADERS = (
    "date_utc",
    "asset_id",
    "window",
    "sopr",
    "a_sopr",
    "sth_sopr",
    "lth_sopr",
    "sopr_ratio",
    "stablecoin_supply_ratio",
    "realized_price",
    "source",
)


@dataclass(frozen=True, slots=True)
class CryptoQuantStablecoinTokenSpec:
    token_id: str
    flow_exchanges: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class CryptoQuantExchangeScope:
    exchange: str


@dataclass(frozen=True, slots=True)
class CryptoQuantReflexivityAssetSpec:
    asset_id: str
    exchange_flow_namespace: str
    market_indicator_namespace: str | None = None


DEFAULT_STABLECOIN_TOKEN_SPECS: tuple[CryptoQuantStablecoinTokenSpec, ...] = (
    CryptoQuantStablecoinTokenSpec("usdt_eth"),
    CryptoQuantStablecoinTokenSpec("usdc"),
    CryptoQuantStablecoinTokenSpec("dai"),
    CryptoQuantStablecoinTokenSpec("tusd"),
    CryptoQuantStablecoinTokenSpec("usdt_trx", flow_exchanges=()),
    CryptoQuantStablecoinTokenSpec("usdt_omni", flow_exchanges=()),
)
DEFAULT_EXCHANGE_SCOPES: tuple[CryptoQuantExchangeScope, ...] = (
    CryptoQuantExchangeScope("all_exchange"),
    CryptoQuantExchangeScope("spot_exchange"),
    CryptoQuantExchangeScope("derivative_exchange"),
)
DEFAULT_REFLEXIVITY_ASSET_SPECS: tuple[CryptoQuantReflexivityAssetSpec, ...] = (
    CryptoQuantReflexivityAssetSpec("btc", "btc", "btc"),
    CryptoQuantReflexivityAssetSpec("eth", "eth", None),
)


def resolve_onchain_cryptoquant_external_root(
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


def _resolve_cryptoquant_api_token(*, base_env: dict[str, str] | None = None) -> str:
    env = os.environ if base_env is None else base_env
    for name in ("Crypto_Quant_API", "CRYPTOQUANT_API_KEY"):
        token = str(env.get(name, "")).strip()
        if token:
            return token
    if os.name == "nt":
        for name in ("Crypto_Quant_API", "CRYPTOQUANT_API_KEY"):
            token = _read_windows_user_env_var(name)
            if token:
                return token
    raise RuntimeError(
        "Crypto_Quant_API (or CRYPTOQUANT_API_KEY) is required for CryptoQuant M3.2 sync"
    )


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


def _select_stablecoin_tokens(token_ids: Iterable[str] | None) -> tuple[CryptoQuantStablecoinTokenSpec, ...]:
    if token_ids is None:
        return DEFAULT_STABLECOIN_TOKEN_SPECS
    requested = {str(item).strip().lower() for item in token_ids if str(item).strip()}
    if not requested:
        return DEFAULT_STABLECOIN_TOKEN_SPECS
    selected = tuple(token for token in DEFAULT_STABLECOIN_TOKEN_SPECS if token.token_id in requested)
    if selected:
        remainder = sorted(requested - {token.token_id for token in selected})
        if not remainder:
            return selected
        return selected + tuple(CryptoQuantStablecoinTokenSpec(token_id) for token_id in remainder)
    return tuple(CryptoQuantStablecoinTokenSpec(token_id) for token_id in sorted(requested))


def _select_exchange_scopes(exchanges: Iterable[str] | None) -> tuple[CryptoQuantExchangeScope, ...]:
    if exchanges is None:
        return DEFAULT_EXCHANGE_SCOPES
    requested = {str(item).strip().lower() for item in exchanges if str(item).strip()}
    if not requested:
        return DEFAULT_EXCHANGE_SCOPES
    selected = tuple(exchange for exchange in DEFAULT_EXCHANGE_SCOPES if exchange.exchange in requested)
    if not selected:
        return tuple(CryptoQuantExchangeScope(exchange) for exchange in sorted(requested))
    return selected


def _flow_exchange_scopes_for_token(
    token: CryptoQuantStablecoinTokenSpec,
    selected_exchanges: tuple[CryptoQuantExchangeScope, ...],
) -> tuple[CryptoQuantExchangeScope, ...]:
    if token.flow_exchanges is None:
        return selected_exchanges
    allow = {str(item).strip().lower() for item in token.flow_exchanges if str(item).strip()}
    if not allow:
        return ()
    filtered = tuple(exchange for exchange in selected_exchanges if exchange.exchange in allow)
    if filtered:
        return filtered
    return tuple(CryptoQuantExchangeScope(exchange) for exchange in sorted(allow))


def _select_reflexivity_assets(asset_ids: Iterable[str] | None) -> tuple[CryptoQuantReflexivityAssetSpec, ...]:
    if asset_ids is None:
        return DEFAULT_REFLEXIVITY_ASSET_SPECS
    requested = {str(item).strip().lower() for item in asset_ids if str(item).strip()}
    if not requested:
        return DEFAULT_REFLEXIVITY_ASSET_SPECS
    selected = tuple(asset for asset in DEFAULT_REFLEXIVITY_ASSET_SPECS if asset.asset_id in requested)
    if not selected:
        raise ValueError(f"no supported CryptoQuant reflexivity assets requested: {sorted(requested)}")
    return selected


def _build_sync_plan(
    *,
    existing_rows: list[dict[str, Any]],
    requested_mode: str,
    lookback_days: int,
    refresh_overlap_days: int,
    end_date: date,
    key_fields: tuple[str, ...],
) -> dict[str, Any]:
    requested = str(requested_mode).strip().lower() or DEFAULT_SYNC_MODE
    if requested not in {"auto", "bootstrap", "refresh"}:
        raise ValueError(f"unsupported CryptoQuant sync mode: {requested_mode!r}")
    latest_dates = _latest_dates_by_key(existing_rows=existing_rows, key_fields=key_fields)
    effective_mode = requested
    if requested == "auto":
        effective_mode = "refresh" if latest_dates else "bootstrap"
    if effective_mode == "refresh" and not latest_dates:
        effective_mode = "bootstrap"
    if effective_mode == "bootstrap":
        start_date = end_date - timedelta(days=max(int(lookback_days), 1) - 1)
    else:
        anchors = list(latest_dates.values())
        fallback_start = end_date - timedelta(days=max(int(lookback_days), 1) - 1)
        anchor_date = min(anchors) if anchors else fallback_start
        start_date = anchor_date - timedelta(days=max(int(refresh_overlap_days), 1) - 1)
    if start_date > end_date:
        start_date = end_date
    return {
        "effective_mode": effective_mode,
        "start_date": start_date,
        "end_date": end_date,
        "selected_latest_dates": {key: value.isoformat() for key, value in latest_dates.items()},
    }


def _latest_dates_by_key(
    *,
    existing_rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> dict[str, date]:
    latest: dict[str, date] = {}
    for row in existing_rows:
        day_text = str(row.get("date_utc") or "").strip()
        if not day_text:
            continue
        try:
            day_value = date.fromisoformat(day_text)
        except ValueError:
            continue
        key = "|".join(str(row.get(field) or "").strip().lower() for field in key_fields)
        if not key.strip("|"):
            continue
        previous = latest.get(key)
        if previous is None or day_value > previous:
            latest[key] = day_value
    return latest


def _fetch_cryptoquant_series(
    *,
    access_token: str,
    path: str,
    params: dict[str, Any],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    query = dict(params)
    query["window"] = DEFAULT_WINDOW
    query["from"] = start_date.strftime("%Y%m%d")
    query["to"] = end_date.strftime("%Y%m%d")
    query["limit"] = DEFAULT_MAX_LIMIT
    query["format"] = "json"
    payload = _cryptoquant_get_json(access_token=access_token, path=path, params=query)
    result = dict(payload.get("result") or {})
    data = list(result.get("data") or [])
    normalized_rows: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        row_date = date.fromisoformat(_extract_row_date_utc(row))
        if row_date < start_date or row_date > end_date:
            continue
        normalized = {"date_utc": row_date.isoformat()}
        for key, value in row.items():
            if key in {"date", "datetime", "blockheight"}:
                continue
            normalized[key] = _coerce_number_or_text(value)
        normalized_rows.append(normalized)
    return normalized_rows


def _extract_row_date_utc(row: dict[str, Any]) -> str:
    date_text = str(row.get("date") or "").strip()
    if date_text:
        return date_text
    datetime_text = str(row.get("datetime") or "").strip()
    if datetime_text:
        normalized = datetime_text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date().isoformat()
    raise RuntimeError(f"CryptoQuant row missing date/datetime field: {row}")


def _merge_metric_frames(*frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for frame in frames:
        for row in frame:
            day = str(row.get("date_utc") or "").strip()
            if not day:
                continue
            target = merged.setdefault(day, {"date_utc": day})
            for key, value in row.items():
                if key == "date_utc":
                    continue
                target[key] = value
    return [merged[key] for key in sorted(merged)]


def _cryptoquant_get_json(
    *,
    access_token: str,
    path: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    url = f"{CRYPTOQUANT_API_BASE}{path}?{query}"
    headers = dict(JSON_HEADERS)
    headers["Authorization"] = f"Bearer {access_token}"
    request = Request(url, headers=headers, method="GET")
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SEC) as response:
                payload = json.loads(response.read().decode("utf-8"))
            status = dict(payload.get("status") or {})
            if int(status.get("code", 0) or 0) != 200:
                raise RuntimeError(f"CryptoQuant API returned non-success payload: {payload}")
            return payload
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"CryptoQuant HTTP {exc.code}: {body}")
            if exc.code not in {408, 409, 425, 429, 500, 502, 503, 504} or attempt >= DEFAULT_MAX_ATTEMPTS:
                raise last_error from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= DEFAULT_MAX_ATTEMPTS:
                raise RuntimeError(f"CryptoQuant request failed after retries: {exc}") from exc
        time.sleep(DEFAULT_RETRY_SLEEP_SEC * attempt)
    raise RuntimeError(f"CryptoQuant request failed after retries: {last_error}")


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _merge_csv_rows(
    *,
    existing_rows: list[dict[str, Any]],
    replacement_rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in existing_rows:
        key = tuple(str(row.get(field) or "").strip() for field in key_fields)
        if any(not item for item in key):
            continue
        merged[key] = dict(row)
    for row in replacement_rows:
        key = tuple(str(row.get(field) or "").strip() for field in key_fields)
        if any(not item for item in key):
            continue
        merged[key] = dict(row)
    return sorted(
        merged.values(),
        key=lambda row: tuple(str(row.get(field) or "").strip() for field in key_fields),
    )


def _write_csv_rows(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def _coerce_number_or_text(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_cryptoquant_stablecoin_sync(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    mode: str = DEFAULT_SYNC_MODE,
    refresh_overlap_days: int = DEFAULT_REFRESH_OVERLAP_DAYS,
    external_root: Path | None = None,
    token_ids: Iterable[str] | None = None,
    exchanges: Iterable[str] | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    access_token = _resolve_cryptoquant_api_token()
    selected_tokens = _select_stablecoin_tokens(token_ids)
    selected_exchanges = _select_exchange_scopes(exchanges)
    resolved_root = resolve_onchain_cryptoquant_external_root(external_root=external_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    supply_path = resolved_root / "stablecoin_supply_daily.csv"
    flow_path = resolved_root / "stablecoin_exchange_flows_daily.csv"
    existing_supply_rows = _read_csv_rows(supply_path)
    existing_flow_rows = _read_csv_rows(flow_path)
    end_date = datetime.now(UTC).date() - timedelta(days=1)
    if end_date < date(2017, 1, 1):
        raise RuntimeError("invalid system clock for CryptoQuant daily sync")
    supply_plan = _build_sync_plan(
        existing_rows=existing_supply_rows,
        requested_mode=mode,
        lookback_days=lookback_days,
        refresh_overlap_days=refresh_overlap_days,
        end_date=end_date,
        key_fields=("token_id",),
    )
    flow_plan = _build_sync_plan(
        existing_rows=existing_flow_rows,
        requested_mode=mode,
        lookback_days=lookback_days,
        refresh_overlap_days=refresh_overlap_days,
        end_date=end_date,
        key_fields=("token_id", "exchange"),
    )
    start_date = min(supply_plan["start_date"], flow_plan["start_date"])
    stablecoin_supply_rows: list[dict[str, Any]] = []
    stablecoin_flow_rows: list[dict[str, Any]] = []
    token_summaries: list[dict[str, Any]] = []
    for token in selected_tokens:
        supply_data = _merge_metric_frames(
            _fetch_cryptoquant_series(
                access_token=access_token,
                path="/stablecoin/network-data/supply",
                params={"token": token.token_id},
                start_date=supply_plan["start_date"],
                end_date=supply_plan["end_date"],
            ),
            _fetch_cryptoquant_series(
                access_token=access_token,
                path="/stablecoin/network-data/tokens-transferred",
                params={"token": token.token_id},
                start_date=supply_plan["start_date"],
                end_date=supply_plan["end_date"],
            ),
            _fetch_cryptoquant_series(
                access_token=access_token,
                path="/stablecoin/network-data/addresses-count",
                params={"token": token.token_id},
                start_date=supply_plan["start_date"],
                end_date=supply_plan["end_date"],
            ),
        )
        token_supply_rows = [
            {
                "date_utc": row["date_utc"],
                "token_id": token.token_id,
                "window": DEFAULT_WINDOW,
                "supply_total": row.get("supply_total"),
                "supply_circulating": row.get("supply_circulating"),
                "supply_minted": row.get("supply_minted"),
                "supply_burned": row.get("supply_burned"),
                "supply_issued": row.get("supply_issued"),
                "supply_redeemed": row.get("supply_redeemed"),
                "tokens_transferred_total": row.get("tokens_transferred_total"),
                "tokens_transferred_mean": row.get("tokens_transferred_mean"),
                "addresses_active_count": row.get("addresses_active_count"),
                "addresses_active_sender_count": row.get("addresses_active_sender_count"),
                "addresses_active_receiver_count": row.get("addresses_active_receiver_count"),
                "addresses_active_sender_percent": row.get("addresses_active_sender_percent"),
                "addresses_active_receiver_percent": row.get("addresses_active_receiver_percent"),
                "source": "cryptoquant_api",
            }
            for row in supply_data
        ]
        stablecoin_supply_rows.extend(token_supply_rows)

        exchange_row_count = 0
        token_flow_exchanges = _flow_exchange_scopes_for_token(token, selected_exchanges)
        flow_exchange_errors: list[dict[str, str]] = []
        for exchange_scope in token_flow_exchanges:
            flow_data = _merge_metric_frames(
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/reserve",
                    params={"token": token.token_id, "exchange": exchange_scope.exchange},
                    start_date=flow_plan["start_date"],
                    end_date=flow_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/inflow",
                    params={"token": token.token_id, "exchange": exchange_scope.exchange},
                    start_date=flow_plan["start_date"],
                    end_date=flow_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/outflow",
                    params={"token": token.token_id, "exchange": exchange_scope.exchange},
                    start_date=flow_plan["start_date"],
                    end_date=flow_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/netflow",
                    params={"token": token.token_id, "exchange": exchange_scope.exchange},
                    start_date=flow_plan["start_date"],
                    end_date=flow_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/transactions-count",
                    params={"token": token.token_id, "exchange": exchange_scope.exchange},
                    start_date=flow_plan["start_date"],
                    end_date=flow_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/addresses-count",
                    params={"token": token.token_id, "exchange": exchange_scope.exchange},
                    start_date=flow_plan["start_date"],
                    end_date=flow_plan["end_date"],
                ),
            )
            token_flow_rows = [
                {
                    "date_utc": row["date_utc"],
                    "token_id": token.token_id,
                    "exchange": exchange_scope.exchange,
                    "window": DEFAULT_WINDOW,
                    "reserve": row.get("reserve"),
                    "inflow_total": row.get("inflow_total"),
                    "inflow_top10": row.get("inflow_top10"),
                    "inflow_mean": row.get("inflow_mean"),
                    "outflow_total": row.get("outflow_total"),
                    "outflow_top10": row.get("outflow_top10"),
                    "outflow_mean": row.get("outflow_mean"),
                    "netflow_total": row.get("netflow_total"),
                    "transactions_count_inflow": row.get("transactions_count_inflow"),
                    "transactions_count_outflow": row.get("transactions_count_outflow"),
                    "addresses_count_inflow": row.get("addresses_count_inflow"),
                    "addresses_count_outflow": row.get("addresses_count_outflow"),
                    "source": "cryptoquant_api",
                }
                for row in flow_data
            ]
            exchange_row_count += len(token_flow_rows)
            stablecoin_flow_rows.extend(token_flow_rows)
        token_summaries.append(
            {
                "token_id": token.token_id,
                "supply_row_count": len(token_supply_rows),
                "exchange_flow_row_count": exchange_row_count,
                "requested_flow_exchanges": [exchange.exchange for exchange in token_flow_exchanges],
                "configured_flow_exchanges": list(token.flow_exchanges) if token.flow_exchanges is not None else None,
            }
        )

    merged_supply_rows = _merge_csv_rows(
        existing_rows=existing_supply_rows,
        replacement_rows=stablecoin_supply_rows,
        key_fields=("date_utc", "token_id"),
    )
    merged_flow_rows = _merge_csv_rows(
        existing_rows=existing_flow_rows,
        replacement_rows=stablecoin_flow_rows,
        key_fields=("date_utc", "token_id", "exchange"),
    )
    _write_csv_rows(supply_path, STABLECOIN_SUPPLY_HEADERS, merged_supply_rows)
    _write_csv_rows(flow_path, STABLECOIN_EXCHANGE_FLOW_HEADERS, merged_flow_rows)

    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": _utc_now(),
            "external_root": str(resolved_root),
            "supply_output_path": str(supply_path),
            "exchange_flow_output_path": str(flow_path),
            "requested_mode": str(mode).strip().lower() or DEFAULT_SYNC_MODE,
            "effective_mode_supply": supply_plan["effective_mode"],
            "effective_mode_exchange_flows": flow_plan["effective_mode"],
            "lookback_days": int(lookback_days),
            "refresh_overlap_days": int(refresh_overlap_days),
            "sync_start_date_utc": start_date.isoformat(),
            "sync_end_date_utc": end_date.isoformat(),
            "requested_token_ids": [token.token_id for token in selected_tokens],
            "requested_exchanges": [exchange.exchange for exchange in selected_exchanges],
            "written_supply_row_count": len(stablecoin_supply_rows),
            "stored_supply_row_count": len(merged_supply_rows),
            "written_exchange_flow_row_count": len(stablecoin_flow_rows),
            "stored_exchange_flow_row_count": len(merged_flow_rows),
            "tokens": token_summaries,
            "input_watermarks": {
                "sync_start_date_utc": start_date.isoformat(),
                "sync_end_date_utc": end_date.isoformat(),
            },
            "upstream_versions": {
                "api_base": CRYPTOQUANT_API_BASE,
                "default_token_ids": [token.token_id for token in DEFAULT_STABLECOIN_TOKEN_SPECS],
                "default_exchanges": [exchange.exchange for exchange in DEFAULT_EXCHANGE_SCOPES],
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


def run_cryptoquant_reflexivity_sync(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    mode: str = DEFAULT_SYNC_MODE,
    refresh_overlap_days: int = DEFAULT_REFRESH_OVERLAP_DAYS,
    external_root: Path | None = None,
    asset_ids: Iterable[str] | None = None,
    exchanges: Iterable[str] | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    access_token = _resolve_cryptoquant_api_token()
    selected_assets = _select_reflexivity_assets(asset_ids)
    selected_exchanges = _select_exchange_scopes(exchanges)
    resolved_root = resolve_onchain_cryptoquant_external_root(external_root=external_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    exchange_flow_path = resolved_root / "reflexivity_exchange_flows_daily.csv"
    market_indicator_path = resolved_root / "reflexivity_market_indicators_daily.csv"
    existing_exchange_rows = _read_csv_rows(exchange_flow_path)
    existing_market_rows = _read_csv_rows(market_indicator_path)
    end_date = datetime.now(UTC).date() - timedelta(days=1)
    exchange_plan = _build_sync_plan(
        existing_rows=existing_exchange_rows,
        requested_mode=mode,
        lookback_days=lookback_days,
        refresh_overlap_days=refresh_overlap_days,
        end_date=end_date,
        key_fields=("asset_id", "exchange"),
    )
    market_plan = _build_sync_plan(
        existing_rows=existing_market_rows,
        requested_mode=mode,
        lookback_days=lookback_days,
        refresh_overlap_days=refresh_overlap_days,
        end_date=end_date,
        key_fields=("asset_id",),
    )
    start_date = min(exchange_plan["start_date"], market_plan["start_date"])
    exchange_rows: list[dict[str, Any]] = []
    market_rows: list[dict[str, Any]] = []
    asset_summaries: list[dict[str, Any]] = []
    for asset in selected_assets:
        asset_exchange_row_count = 0
        for exchange_scope in selected_exchanges:
            flow_data = _merge_metric_frames(
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.exchange_flow_namespace}/exchange-flows/reserve",
                    params={"exchange": exchange_scope.exchange},
                    start_date=exchange_plan["start_date"],
                    end_date=exchange_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.exchange_flow_namespace}/exchange-flows/inflow",
                    params={"exchange": exchange_scope.exchange},
                    start_date=exchange_plan["start_date"],
                    end_date=exchange_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.exchange_flow_namespace}/exchange-flows/outflow",
                    params={"exchange": exchange_scope.exchange},
                    start_date=exchange_plan["start_date"],
                    end_date=exchange_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.exchange_flow_namespace}/exchange-flows/netflow",
                    params={"exchange": exchange_scope.exchange},
                    start_date=exchange_plan["start_date"],
                    end_date=exchange_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.exchange_flow_namespace}/exchange-flows/transactions-count",
                    params={"exchange": exchange_scope.exchange},
                    start_date=exchange_plan["start_date"],
                    end_date=exchange_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.exchange_flow_namespace}/exchange-flows/addresses-count",
                    params={"exchange": exchange_scope.exchange},
                    start_date=exchange_plan["start_date"],
                    end_date=exchange_plan["end_date"],
                ),
            )
            asset_exchange_rows = [
                {
                    "date_utc": row["date_utc"],
                    "asset_id": asset.asset_id,
                    "exchange": exchange_scope.exchange,
                    "window": DEFAULT_WINDOW,
                    "reserve": row.get("reserve"),
                    "reserve_usd": row.get("reserve_usd"),
                    "inflow_total": row.get("inflow_total"),
                    "inflow_top10": row.get("inflow_top10"),
                    "inflow_mean": row.get("inflow_mean"),
                    "outflow_total": row.get("outflow_total"),
                    "outflow_top10": row.get("outflow_top10"),
                    "outflow_mean": row.get("outflow_mean"),
                    "netflow_total": row.get("netflow_total"),
                    "transactions_count_inflow": row.get("transactions_count_inflow"),
                    "transactions_count_outflow": row.get("transactions_count_outflow"),
                    "addresses_count_inflow": row.get("addresses_count_inflow"),
                    "addresses_count_outflow": row.get("addresses_count_outflow"),
                    "source": "cryptoquant_api",
                }
                for row in flow_data
            ]
            exchange_rows.extend(asset_exchange_rows)
            asset_exchange_row_count += len(asset_exchange_rows)

        asset_market_row_count = 0
        if asset.market_indicator_namespace:
            market_data = _merge_metric_frames(
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.market_indicator_namespace}/market-indicator/sopr",
                    params={},
                    start_date=market_plan["start_date"],
                    end_date=market_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.market_indicator_namespace}/market-indicator/sopr-ratio",
                    params={},
                    start_date=market_plan["start_date"],
                    end_date=market_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.market_indicator_namespace}/market-indicator/stablecoin-supply-ratio",
                    params={},
                    start_date=market_plan["start_date"],
                    end_date=market_plan["end_date"],
                ),
                _fetch_cryptoquant_series(
                    access_token=access_token,
                    path=f"/{asset.market_indicator_namespace}/market-indicator/realized-price",
                    params={},
                    start_date=market_plan["start_date"],
                    end_date=market_plan["end_date"],
                ),
            )
            asset_market_rows = [
                {
                    "date_utc": row["date_utc"],
                    "asset_id": asset.asset_id,
                    "window": DEFAULT_WINDOW,
                    "sopr": row.get("sopr"),
                    "a_sopr": row.get("a_sopr"),
                    "sth_sopr": row.get("sth_sopr"),
                    "lth_sopr": row.get("lth_sopr"),
                    "sopr_ratio": row.get("sopr_ratio"),
                    "stablecoin_supply_ratio": row.get("stablecoin_supply_ratio"),
                    "realized_price": row.get("realized_price"),
                    "source": "cryptoquant_api",
                }
                for row in market_data
            ]
            market_rows.extend(asset_market_rows)
            asset_market_row_count += len(asset_market_rows)
        asset_summaries.append(
            {
                "asset_id": asset.asset_id,
                "exchange_flow_row_count": asset_exchange_row_count,
                "market_indicator_row_count": asset_market_row_count,
            }
        )

    merged_exchange_rows = _merge_csv_rows(
        existing_rows=existing_exchange_rows,
        replacement_rows=exchange_rows,
        key_fields=("date_utc", "asset_id", "exchange"),
    )
    merged_market_rows = _merge_csv_rows(
        existing_rows=existing_market_rows,
        replacement_rows=market_rows,
        key_fields=("date_utc", "asset_id"),
    )
    _write_csv_rows(exchange_flow_path, REFLEXIVITY_EXCHANGE_FLOW_HEADERS, merged_exchange_rows)
    _write_csv_rows(market_indicator_path, REFLEXIVITY_MARKET_HEADERS, merged_market_rows)
    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": _utc_now(),
            "external_root": str(resolved_root),
            "exchange_flow_output_path": str(exchange_flow_path),
            "market_indicator_output_path": str(market_indicator_path),
            "requested_mode": str(mode).strip().lower() or DEFAULT_SYNC_MODE,
            "effective_mode_exchange_flows": exchange_plan["effective_mode"],
            "effective_mode_market_indicators": market_plan["effective_mode"],
            "lookback_days": int(lookback_days),
            "refresh_overlap_days": int(refresh_overlap_days),
            "sync_start_date_utc": start_date.isoformat(),
            "sync_end_date_utc": end_date.isoformat(),
            "requested_asset_ids": [asset.asset_id for asset in selected_assets],
            "requested_exchanges": [exchange.exchange for exchange in selected_exchanges],
            "written_exchange_flow_row_count": len(exchange_rows),
            "stored_exchange_flow_row_count": len(merged_exchange_rows),
            "written_market_indicator_row_count": len(market_rows),
            "stored_market_indicator_row_count": len(merged_market_rows),
            "assets": asset_summaries,
            "input_watermarks": {
                "sync_start_date_utc": start_date.isoformat(),
                "sync_end_date_utc": end_date.isoformat(),
            },
            "upstream_versions": {
                "api_base": CRYPTOQUANT_API_BASE,
                "default_asset_ids": [asset.asset_id for asset in DEFAULT_REFLEXIVITY_ASSET_SPECS],
                "default_exchanges": [exchange.exchange for exchange in DEFAULT_EXCHANGE_SCOPES],
            },
        },
        evidence_family=ARTIFACT_FAMILY,
        contract_version=CONTRACT_VERSION,
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    latest_summary_path = resolved_root / "latest_reflexivity_sync_summary.json"
    latest_summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["latest_summary_path"] = str(latest_summary_path)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["report_path"] = str(report_path)
    return summary
