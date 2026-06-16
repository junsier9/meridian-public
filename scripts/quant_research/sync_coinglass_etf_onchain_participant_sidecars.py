from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_capability_matrix import BASE_URL  # noqa: E402
from enhengclaw.quant_research.coinglass_derivatives import resolve_coinglass_api_key  # noqa: E402
from enhengclaw.quant_research.contracts import utc_now  # noqa: E402


CONTRACT_VERSION = "coinglass_etf_onchain_participant_sidecars.v1"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "coinglass"
DEFAULT_REPORT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-coinglass-etf-onchain-participant-sidecars"
)
DAY_MS = 86_400_000
STABLECOIN_SYMBOLS = {"USDT", "USDC"}
EXCHANGE_ENTITY_PATTERNS = (
    "binance",
    "coinbase",
    "okx",
    "okex",
    "bybit",
    "kraken",
    "bitfinex",
    "gemini",
    "bitstamp",
    "huobi",
    "kucoin",
    "gate",
    "crypto.com",
    "bitget",
    "mexc",
    "upbit",
    "bithumb",
    "bitmart",
    "robinhood",
    "deribit",
)


HttpGetJson = Callable[[str], Any]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sync PIT-lagged CoinGlass ETF and on-chain participant sidecars. "
            "ETF rows are daily full-list pulls; whale rows use ms start/end "
            "windows; exchange transfers are page-based latest-event pulls."
        )
    )
    parser.add_argument("--pit-lag-days", type=int, default=1)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--exchange-symbols", default="USDT,USDC")
    parser.add_argument("--exchange-pages", type=int, default=50)
    parser.add_argument("--exchange-per-page", type=int, default=100)
    parser.add_argument("--exchange-min-usd", type=float, default=1_000_000.0)
    parser.add_argument("--whale-symbols", default="BTC,ETH,USDT")
    parser.add_argument("--whale-lookback-days", type=int, default=180)
    parser.add_argument("--whale-window-days", type=int, default=7)
    parser.add_argument("--sleep-seconds", type=float, default=0.05)
    return parser


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("unreachable CoinGlass request state")


def _url(path: str, params: dict[str, Any] | None = None) -> str:
    query = urlencode({key: value for key, value in dict(params or {}).items() if value is not None})
    return f"{BASE_URL}{path}" + (f"?{query}" if query else "")


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("list", "rows", "result"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
            return [data]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _csv_items(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _coerce_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return float(out)


def _coerce_int(value: Any) -> int | None:
    try:
        out = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    return out


def _timestamp_ms(value: Any) -> int | None:
    raw = _coerce_int(value)
    if raw is None:
        return None
    if raw < 10_000_000_000:
        raw *= 1000
    return raw


def _date_from_ms(timestamp_ms: int) -> date:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date()


def _date_ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


def _iso_from_ms(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _decision_day(source_ms: int, pit_lag_days: int) -> date:
    return _date_from_ms(source_ms) + timedelta(days=pit_lag_days)


def _safe_slug(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = raw.strip("_")
    return raw or "unknown"


def _rolling_z(series: pd.Series, window: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window=window, min_periods=min(10, window)).mean()
    std = values.rolling(window=window, min_periods=min(10, window)).std(ddof=0)
    return (values - mean) / std.mask(std == 0.0)


def _frame_date_bounds(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or "date_utc" not in frame.columns:
        return {"row_count": int(len(frame)), "first_date_utc": None, "last_date_utc": None}
    return {
        "row_count": int(len(frame)),
        "first_date_utc": str(frame["date_utc"].min()),
        "last_date_utc": str(frame["date_utc"].max()),
    }


def fetch_etf_rows(http_get_json_fn: HttpGetJson, *, sleep_seconds: float = 0.0) -> dict[str, list[dict[str, Any]]]:
    endpoints = {
        "bitcoin_flow": ("/etf/bitcoin/flow-history", {}),
        "ethereum_flow": ("/etf/ethereum/flow-history", {}),
        "bitcoin_ibit_history": ("/etf/bitcoin/history", {"ticker": "IBIT"}),
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for key, (path, params) in endpoints.items():
        payload = http_get_json_fn(_url(path, params))
        out[key] = _extract_rows(payload)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return out


def build_etf_daily_state(
    *,
    bitcoin_flow_rows: Iterable[dict[str, Any]],
    ethereum_flow_rows: Iterable[dict[str, Any]],
    bitcoin_ibit_rows: Iterable[dict[str, Any]],
    pit_lag_days: int,
) -> pd.DataFrame:
    records: dict[str, dict[str, Any]] = {}

    def record_for(day: date) -> dict[str, Any]:
        key = day.isoformat()
        if key not in records:
            records[key] = {
                "date_utc": key,
                "timestamp_ms": _date_ms(day),
                "pit_lag_days": int(pit_lag_days),
                "pit_policy": "daily_source_date_plus_lag",
                "source": "coinglass_etf_flow_history|coinglass_etf_history_ibit",
            }
        return records[key]

    def add_flow(asset: str, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            source_ms = _timestamp_ms(row.get("timestamp"))
            if source_ms is None:
                continue
            day = _decision_day(source_ms, pit_lag_days)
            rec = record_for(day)
            rec[f"{asset}_etf_source_timestamp_ms"] = source_ms
            rec[f"{asset}_etf_source_date_utc"] = _date_from_ms(source_ms).isoformat()
            rec[f"{asset}_etf_flow_usd"] = _coerce_float(row.get("flow_usd"))
            rec[f"{asset}_etf_price_usd"] = _coerce_float(row.get("price_usd"))
            etf_flows = row.get("etf_flows")
            if not isinstance(etf_flows, list):
                continue
            for item in etf_flows:
                if not isinstance(item, dict):
                    continue
                ticker = _safe_slug(item.get("etf_ticker") or item.get("ticker"))
                rec[f"{asset}_etf_flow_usd_{ticker}"] = _coerce_float(item.get("flow_usd"))

    add_flow("btc", bitcoin_flow_rows)
    add_flow("eth", ethereum_flow_rows)

    for row in bitcoin_ibit_rows:
        source_ms = _timestamp_ms(row.get("market_date") or row.get("assets_date"))
        if source_ms is None:
            continue
        day = _decision_day(source_ms, pit_lag_days)
        rec = record_for(day)
        rec["ibit_source_timestamp_ms"] = source_ms
        rec["ibit_source_date_utc"] = _date_from_ms(source_ms).isoformat()
        rec["ibit_market_price"] = _coerce_float(row.get("market_price"))
        rec["ibit_nav"] = _coerce_float(row.get("nav"))
        rec["ibit_net_assets"] = _coerce_float(row.get("net_assets"))
        rec["ibit_premium_discount"] = _coerce_float(row.get("premium_discount"))
        rec["ibit_btc_holdings"] = _coerce_float(row.get("btc_holdings"))
        rec["ibit_shares_outstanding"] = _coerce_float(row.get("shares_outstanding"))

    frame = pd.DataFrame(records.values()).sort_values("timestamp_ms").reset_index(drop=True)
    if frame.empty:
        return frame
    for column in ("btc_etf_flow_usd", "eth_etf_flow_usd"):
        if column in frame.columns:
            frame[f"{column}_3d_sum"] = pd.to_numeric(frame[column], errors="coerce").rolling(3, min_periods=1).sum()
            frame[f"{column}_10d_sum"] = pd.to_numeric(frame[column], errors="coerce").rolling(10, min_periods=1).sum()
            frame[f"{column}_z30"] = _rolling_z(frame[column], 30)
    if {"btc_etf_flow_usd", "eth_etf_flow_usd"}.issubset(frame.columns):
        total_flow = pd.to_numeric(frame["btc_etf_flow_usd"], errors="coerce").fillna(0.0) + pd.to_numeric(
            frame["eth_etf_flow_usd"], errors="coerce"
        ).fillna(0.0)
        frame["total_btc_eth_etf_flow_usd"] = total_flow
        frame["total_btc_eth_etf_flow_usd_10d_sum"] = total_flow.rolling(10, min_periods=1).sum()
        frame["total_btc_eth_etf_flow_usd_z30"] = _rolling_z(total_flow, 30)
    return frame


def fetch_exchange_transfer_rows(
    *,
    symbols: Iterable[str],
    pages: int,
    per_page: int,
    min_usd: float,
    http_get_json_fn: HttpGetJson,
    sleep_seconds: float = 0.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for symbol in symbols:
        for page in range(1, pages + 1):
            params = {"symbol": symbol, "min_usd": min_usd, "per_page": per_page, "page": page}
            try:
                payload = http_get_json_fn(_url("/exchange/chain/tx/list", params))
            except HTTPError as exc:
                warnings.append(f"exchange_chain_tx_list:{symbol}:page_{page}:http_{exc.code}")
                break
            batch = _extract_rows(payload)
            if not batch:
                break
            for row in batch:
                row = dict(row)
                row["_requested_symbol"] = str(symbol)
                row["_page"] = int(page)
                rows.append(row)
            if len(batch) < per_page:
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    deduped: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        tx_hash = str(row.get("transaction_hash") or "").strip()
        key = tx_hash or f"nohash:{index}"
        deduped[key] = row
    return list(deduped.values()), warnings


def build_exchange_transfers_daily(
    rows: Iterable[dict[str, Any]],
    *,
    pit_lag_days: int,
) -> pd.DataFrame:
    records: dict[str, dict[str, Any]] = {}

    def record_for(day: date) -> dict[str, Any]:
        key = day.isoformat()
        if key not in records:
            records[key] = {
                "date_utc": key,
                "timestamp_ms": _date_ms(day),
                "pit_lag_days": int(pit_lag_days),
                "pit_policy": "event_date_plus_lag",
                "source": "coinglass_exchange_chain_tx_list",
                "exchange_transfer_count": 0,
                "exchange_transfer_total_usd": 0.0,
                "exchange_transfer_stablecoin_total_usd": 0.0,
                "exchange_transfer_type1_usd": 0.0,
                "exchange_transfer_type2_usd": 0.0,
                "exchange_transfer_type_other_usd": 0.0,
                "exchange_transfer_type1_count": 0,
                "exchange_transfer_type2_count": 0,
                "exchange_transfer_type_other_count": 0,
            }
        return records[key]

    for row in rows:
        source_ms = _timestamp_ms(row.get("transaction_time"))
        amount_usd = _coerce_float(row.get("amount_usd"))
        if source_ms is None or amount_usd is None:
            continue
        day = _decision_day(source_ms, pit_lag_days)
        rec = record_for(day)
        source_date = _date_from_ms(source_ms).isoformat()
        rec["source_event_date_min_utc"] = min(str(rec.get("source_event_date_min_utc") or source_date), source_date)
        rec["source_event_date_max_utc"] = max(str(rec.get("source_event_date_max_utc") or source_date), source_date)
        rec["source_event_timestamp_min_utc"] = min(
            str(rec.get("source_event_timestamp_min_utc") or _iso_from_ms(source_ms)),
            str(_iso_from_ms(source_ms)),
        )
        rec["source_event_timestamp_max_utc"] = max(
            str(rec.get("source_event_timestamp_max_utc") or _iso_from_ms(source_ms)),
            str(_iso_from_ms(source_ms)),
        )
        rec["exchange_transfer_count"] += 1
        rec["exchange_transfer_total_usd"] += amount_usd
        asset = str(row.get("asset_symbol") or row.get("_requested_symbol") or "").upper()
        if asset in STABLECOIN_SYMBOLS:
            rec["exchange_transfer_stablecoin_total_usd"] += amount_usd
        if asset:
            slug = _safe_slug(asset)
            rec[f"exchange_transfer_{slug}_usd"] = float(rec.get(f"exchange_transfer_{slug}_usd") or 0.0) + amount_usd
            rec[f"exchange_transfer_{slug}_count"] = int(rec.get(f"exchange_transfer_{slug}_count") or 0) + 1
        exchange = _safe_slug(row.get("exchange_name"))
        rec[f"exchange_transfer_{exchange}_usd"] = float(rec.get(f"exchange_transfer_{exchange}_usd") or 0.0) + amount_usd
        transfer_type = _coerce_int(row.get("transfer_type"))
        if transfer_type == 1:
            rec["exchange_transfer_type1_usd"] += amount_usd
            rec["exchange_transfer_type1_count"] += 1
        elif transfer_type == 2:
            rec["exchange_transfer_type2_usd"] += amount_usd
            rec["exchange_transfer_type2_count"] += 1
        else:
            rec["exchange_transfer_type_other_usd"] += amount_usd
            rec["exchange_transfer_type_other_count"] += 1

    frame = pd.DataFrame(records.values()).sort_values("timestamp_ms").reset_index(drop=True)
    if frame.empty:
        return frame
    frame["exchange_netflow_type2_minus_type1_usd"] = (
        pd.to_numeric(frame["exchange_transfer_type2_usd"], errors="coerce").fillna(0.0)
        - pd.to_numeric(frame["exchange_transfer_type1_usd"], errors="coerce").fillna(0.0)
    )
    frame["exchange_transfer_total_usd_3d_sum"] = pd.to_numeric(
        frame["exchange_transfer_total_usd"], errors="coerce"
    ).rolling(3, min_periods=1).sum()
    frame["exchange_transfer_total_usd_z30"] = _rolling_z(frame["exchange_transfer_total_usd"], 30)
    frame["exchange_netflow_type2_minus_type1_usd_z30"] = _rolling_z(
        frame["exchange_netflow_type2_minus_type1_usd"], 30
    )
    frame["exchange_transfer_direction_semantics"] = "raw_transfer_type_unverified"
    return frame


def fetch_whale_transfer_rows(
    *,
    symbols: Iterable[str],
    start_ms: int,
    end_ms: int,
    window_days: int,
    http_get_json_fn: HttpGetJson,
    sleep_seconds: float = 0.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    window_ms = max(1, int(window_days)) * DAY_MS
    min_split_window_ms = 6 * 3_600_000

    def fetch_window(symbol: str, window_start_ms: int, window_end_ms: int) -> list[dict[str, Any]]:
        params = {"symbol": symbol, "start_time": window_start_ms, "end_time": window_end_ms}
        try:
            payload = http_get_json_fn(_url("/chain/v2/whale-transfer", params))
        except HTTPError as exc:
            warnings.append(f"whale_transfer:{symbol}:{_iso_from_ms(window_start_ms)}:http_{exc.code}")
            return []
        batch = _extract_rows(payload)
        if len(batch) >= 1000 and window_end_ms - window_start_ms > min_split_window_ms:
            midpoint = window_start_ms + (window_end_ms - window_start_ms) // 2
            return fetch_window(symbol, window_start_ms, midpoint) + fetch_window(symbol, midpoint + 1, window_end_ms)
        if len(batch) >= 1000:
            warnings.append(f"whale_transfer:{symbol}:{_iso_from_ms(window_start_ms)}:hit_1000_row_page_cap")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        return batch

    for symbol in symbols:
        cursor = int(start_ms)
        while cursor <= end_ms:
            cur_end = min(cursor + window_ms - 1, end_ms)
            batch = fetch_window(str(symbol), cursor, cur_end)
            for row in batch:
                source_ms = _timestamp_ms(row.get("block_timestamp"))
                if source_ms is None or source_ms < start_ms or source_ms > end_ms:
                    continue
                row = dict(row)
                row["_requested_symbol"] = str(symbol)
                rows.append(row)
            cursor = cur_end + 1
    deduped: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        tx_hash = str(row.get("transaction_hash") or "").strip()
        key = f"{row.get('_requested_symbol')}:{tx_hash}" if tx_hash else f"nohash:{index}"
        deduped[key] = row
    return list(deduped.values()), warnings


def _is_exchange_entity(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(pattern in text for pattern in EXCHANGE_ENTITY_PATTERNS)


def _whale_direction(row: dict[str, Any]) -> str:
    from_exchange = _is_exchange_entity(row.get("from"))
    to_exchange = _is_exchange_entity(row.get("to"))
    if from_exchange and to_exchange:
        return "exchange_to_exchange"
    if to_exchange:
        return "to_exchange"
    if from_exchange:
        return "from_exchange"
    return "unknown_direction"


def build_whale_transfers_daily(
    rows: Iterable[dict[str, Any]],
    *,
    pit_lag_days: int,
) -> pd.DataFrame:
    records: dict[str, dict[str, Any]] = {}

    def record_for(day: date) -> dict[str, Any]:
        key = day.isoformat()
        if key not in records:
            records[key] = {
                "date_utc": key,
                "timestamp_ms": _date_ms(day),
                "pit_lag_days": int(pit_lag_days),
                "pit_policy": "event_date_plus_lag",
                "source": "coinglass_chain_v2_whale_transfer",
                "whale_transfer_count": 0,
                "whale_transfer_total_usd": 0.0,
                "whale_to_exchange_usd": 0.0,
                "whale_from_exchange_usd": 0.0,
                "whale_exchange_to_exchange_usd": 0.0,
                "whale_unknown_direction_usd": 0.0,
                "whale_to_exchange_count": 0,
                "whale_from_exchange_count": 0,
                "whale_exchange_to_exchange_count": 0,
                "whale_unknown_direction_count": 0,
            }
        return records[key]

    for row in rows:
        source_ms = _timestamp_ms(row.get("block_timestamp"))
        amount_usd = _coerce_float(row.get("amount_usd"))
        if source_ms is None or amount_usd is None:
            continue
        day = _decision_day(source_ms, pit_lag_days)
        rec = record_for(day)
        source_date = _date_from_ms(source_ms).isoformat()
        rec["source_event_date_min_utc"] = min(str(rec.get("source_event_date_min_utc") or source_date), source_date)
        rec["source_event_date_max_utc"] = max(str(rec.get("source_event_date_max_utc") or source_date), source_date)
        rec["source_event_timestamp_min_utc"] = min(
            str(rec.get("source_event_timestamp_min_utc") or _iso_from_ms(source_ms)),
            str(_iso_from_ms(source_ms)),
        )
        rec["source_event_timestamp_max_utc"] = max(
            str(rec.get("source_event_timestamp_max_utc") or _iso_from_ms(source_ms)),
            str(_iso_from_ms(source_ms)),
        )
        rec["whale_transfer_count"] += 1
        rec["whale_transfer_total_usd"] += amount_usd
        asset = str(row.get("asset_symbol") or row.get("_requested_symbol") or "").upper()
        if asset:
            slug = _safe_slug(asset)
            rec[f"whale_{slug}_total_usd"] = float(rec.get(f"whale_{slug}_total_usd") or 0.0) + amount_usd
            rec[f"whale_{slug}_count"] = int(rec.get(f"whale_{slug}_count") or 0) + 1
        direction = _whale_direction(row)
        rec[f"whale_{direction}_usd"] += amount_usd
        rec[f"whale_{direction}_count"] += 1

    frame = pd.DataFrame(records.values()).sort_values("timestamp_ms").reset_index(drop=True)
    if frame.empty:
        return frame
    frame["whale_net_to_exchange_usd"] = (
        pd.to_numeric(frame["whale_to_exchange_usd"], errors="coerce").fillna(0.0)
        - pd.to_numeric(frame["whale_from_exchange_usd"], errors="coerce").fillna(0.0)
    )
    frame["whale_transfer_total_usd_3d_sum"] = pd.to_numeric(
        frame["whale_transfer_total_usd"], errors="coerce"
    ).rolling(3, min_periods=1).sum()
    frame["whale_transfer_total_usd_z30"] = _rolling_z(frame["whale_transfer_total_usd"], 30)
    frame["whale_net_to_exchange_usd_z30"] = _rolling_z(frame["whale_net_to_exchange_usd"], 30)
    return frame


def build_participant_context(
    *,
    etf_daily: pd.DataFrame,
    exchange_daily: pd.DataFrame,
    whale_daily: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for label, frame in (("etf", etf_daily), ("exchange", exchange_daily), ("whale", whale_daily)):
        if frame.empty or "date_utc" not in frame.columns:
            continue
        prepared = frame.copy()
        rename: dict[str, str] = {}
        if "source" in prepared.columns:
            rename["source"] = f"source_{label}"
        if "pit_policy" in prepared.columns:
            rename["pit_policy"] = f"pit_policy_{label}"
        frames.append(prepared.rename(columns=rename))
    if not frames:
        return pd.DataFrame()
    merged = frames[0]
    for frame in frames[1:]:
        shared = [column for column in ("date_utc", "timestamp_ms", "pit_lag_days") if column in frame.columns]
        merged = pd.merge(merged, frame, how="outer", on=shared, suffixes=("", "_rhs"))
    source_columns = [column for column in merged.columns if column.startswith("source_")]
    if source_columns:
        merged["participant_context_sources"] = merged[source_columns].apply(
            lambda row: "|".join(sorted({str(item) for item in row.dropna() if str(item)})),
            axis=1,
        )
        merged = merged.drop(columns=[column for column in source_columns if column != "participant_context_sources"])
    pit_policy_columns = [column for column in merged.columns if column.startswith("pit_policy_")]
    if pit_policy_columns:
        merged["participant_context_pit_policies"] = merged[pit_policy_columns].apply(
            lambda row: "|".join(sorted({str(item) for item in row.dropna() if str(item)})),
            axis=1,
        )
        merged = merged.drop(columns=pit_policy_columns)
    merged = merged.sort_values("timestamp_ms").reset_index(drop=True)
    return merged


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")


def _input_summary(rows: Iterable[dict[str, Any]], timestamp_field: str) -> dict[str, Any]:
    timestamps = [
        value
        for value in (_timestamp_ms(row.get(timestamp_field)) for row in rows)
        if value is not None
    ]
    if not timestamps:
        return {"row_count": 0, "first_time_utc": None, "last_time_utc": None}
    return {
        "row_count": int(len(timestamps)),
        "first_time_utc": _iso_from_ms(min(timestamps)),
        "last_time_utc": _iso_from_ms(max(timestamps)),
    }


def sync_sidecars(
    *,
    pit_lag_days: int,
    output_root: Path,
    report_dir: Path,
    exchange_symbols: list[str],
    exchange_pages: int,
    exchange_per_page: int,
    exchange_min_usd: float,
    whale_symbols: list[str],
    whale_lookback_days: int,
    whale_window_days: int,
    sleep_seconds: float,
    http_get_json_fn: HttpGetJson = _http_get_json,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    report_dir = report_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    etf_rows = fetch_etf_rows(http_get_json_fn, sleep_seconds=sleep_seconds)
    etf_daily = build_etf_daily_state(
        bitcoin_flow_rows=etf_rows["bitcoin_flow"],
        ethereum_flow_rows=etf_rows["ethereum_flow"],
        bitcoin_ibit_rows=etf_rows["bitcoin_ibit_history"],
        pit_lag_days=pit_lag_days,
    )

    exchange_rows, exchange_warnings = fetch_exchange_transfer_rows(
        symbols=exchange_symbols,
        pages=exchange_pages,
        per_page=exchange_per_page,
        min_usd=exchange_min_usd,
        http_get_json_fn=http_get_json_fn,
        sleep_seconds=sleep_seconds,
    )
    exchange_daily = build_exchange_transfers_daily(exchange_rows, pit_lag_days=pit_lag_days)

    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    start_ms = end_ms - int(whale_lookback_days) * DAY_MS
    whale_rows, whale_warnings = fetch_whale_transfer_rows(
        symbols=whale_symbols,
        start_ms=start_ms,
        end_ms=end_ms,
        window_days=whale_window_days,
        http_get_json_fn=http_get_json_fn,
        sleep_seconds=sleep_seconds,
    )
    whale_daily = build_whale_transfers_daily(whale_rows, pit_lag_days=pit_lag_days)
    participant_context = build_participant_context(
        etf_daily=etf_daily,
        exchange_daily=exchange_daily,
        whale_daily=whale_daily,
    )

    paths = {
        "etf_daily_state": output_root / "etf_daily_state_1d.csv.gz",
        "exchange_transfers": output_root / "exchange_transfers_1d.csv.gz",
        "whale_transfers": output_root / "whale_transfers_1d.csv.gz",
        "participant_context": output_root / "participant_context_1d.csv.gz",
    }
    _write_frame(etf_daily, paths["etf_daily_state"])
    _write_frame(exchange_daily, paths["exchange_transfers"])
    _write_frame(whale_daily, paths["whale_transfers"])
    _write_frame(participant_context, paths["participant_context"])

    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "pit_lag_days": int(pit_lag_days),
        "paths": {key: str(path) for key, path in paths.items()},
        "endpoint_contract": {
            "etf": {
                "paths": [
                    "/etf/bitcoin/flow-history",
                    "/etf/ethereum/flow-history",
                    "/etf/bitcoin/history?ticker=IBIT",
                ],
                "native_timestamp": "timestamp or market_date in milliseconds",
                "pit_policy": "daily source date plus pit_lag_days",
            },
            "exchange_transfers": {
                "path": "/exchange/chain/tx/list",
                "native_timestamp": "transaction_time in seconds",
                "pagination": "page/per_page latest-event feed",
                "limitation": "start/end filters were not used because local probes showed they are ignored",
                "direction_semantics": "transfer_type retained as raw vendor code; no semantic inflow/outflow promotion",
            },
            "whale_transfers": {
                "path": "/chain/v2/whale-transfer",
                "native_timestamp": "block_timestamp in seconds",
                "pagination": "start_time/end_time in milliseconds over fixed windows",
            },
        },
        "inputs": {
            "etf_bitcoin_flow": _input_summary(etf_rows["bitcoin_flow"], "timestamp"),
            "etf_ethereum_flow": _input_summary(etf_rows["ethereum_flow"], "timestamp"),
            "etf_bitcoin_ibit": _input_summary(etf_rows["bitcoin_ibit_history"], "market_date"),
            "exchange_transfer_events": _input_summary(exchange_rows, "transaction_time"),
            "whale_transfer_events": _input_summary(whale_rows, "block_timestamp"),
        },
        "outputs": {
            "etf_daily_state": _frame_date_bounds(etf_daily),
            "exchange_transfers": _frame_date_bounds(exchange_daily),
            "whale_transfers": _frame_date_bounds(whale_daily),
            "participant_context": _frame_date_bounds(participant_context),
        },
        "parameters": {
            "exchange_symbols": exchange_symbols,
            "exchange_pages": int(exchange_pages),
            "exchange_per_page": int(exchange_per_page),
            "exchange_min_usd": float(exchange_min_usd),
            "whale_symbols": whale_symbols,
            "whale_lookback_days": int(whale_lookback_days),
            "whale_window_days": int(whale_window_days),
        },
        "warnings": {
            "exchange": exchange_warnings,
            "whale": whale_warnings,
        },
        "research_status": {
            "sidecar_data_layer_filled": True,
            "alpha_rerun_allowed": False,
            "reason": "sidecars exist, but they are not yet integrated into the daily feature panel or falsified as a pre-registered transition.",
        },
    }
    report_path = report_dir / "coinglass_etf_onchain_participant_sidecars.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = sync_sidecars(
            pit_lag_days=args.pit_lag_days,
            output_root=args.output_root,
            report_dir=args.report_dir,
            exchange_symbols=_csv_items(args.exchange_symbols),
            exchange_pages=args.exchange_pages,
            exchange_per_page=args.exchange_per_page,
            exchange_min_usd=args.exchange_min_usd,
            whale_symbols=_csv_items(args.whale_symbols),
            whale_lookback_days=args.whale_lookback_days,
            whale_window_days=args.whale_window_days,
            sleep_seconds=args.sleep_seconds,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"report_path": report["report_path"], "outputs": report["outputs"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
