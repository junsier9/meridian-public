from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .coinglass_derivatives import resolve_coinglass_api_key


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = ROOT / "artifacts" / "quant_research" / "provider_smoke"
BASE_URL = "https://open-api-v4.coinglass.com/api"
DEFAULT_LIMIT = 5


@dataclass(frozen=True)
class EndpointProbe:
    endpoint_id: str
    family: str
    path: str
    params: dict[str, Any]
    classification: str
    timestamp_field: str | None
    pagination_model: str
    max_result_limit: int | None
    pit_risk_notes: str
    history_probe_days: int | None = None


ENDPOINTS: tuple[EndpointProbe, ...] = (
    EndpointProbe(
        endpoint_id="spot_price_history",
        family="spot_ohlcv",
        path="/spot/price/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Use native bar time as UTC bucket; no forward fill across listing boundaries.",
        history_probe_days=720,
    ),
    EndpointProbe(
        endpoint_id="spot_taker_buy_sell_volume",
        family="spot_flow",
        path="/spot/taker-buy-sell-volume/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Spot flow can enter research only after coverage and timestamp audit.",
        history_probe_days=180,
    ),
    EndpointProbe(
        endpoint_id="spot_cvd_history",
        family="spot_flow",
        path="/spot/cvd/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="CVD fields are vendor-derived; require PIT and formula audit before score use.",
        history_probe_days=180,
    ),
    EndpointProbe(
        endpoint_id="spot_footprint_history",
        family="spot_flow",
        path="/spot/volume/footprint-history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Treat as short-history sidecar until history window is proven.",
        history_probe_days=90,
    ),
    EndpointProbe(
        endpoint_id="futures_price_history",
        family="futures_core",
        path="/futures/price/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Use as perp price spine and OI-value derivation input only with provenance.",
        history_probe_days=365,
    ),
    EndpointProbe(
        endpoint_id="futures_open_interest_history_usd",
        family="futures_core",
        path="/futures/open-interest/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "unit": "usd", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Native USD OI is preferred; derived values need overlap error audit.",
        history_probe_days=365,
    ),
    EndpointProbe(
        endpoint_id="futures_open_interest_history_coin",
        family="futures_core",
        path="/futures/open-interest/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "unit": "coin", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Can derive USD OI only with perp close and explicit provenance flag.",
        history_probe_days=365,
    ),
    EndpointProbe(
        endpoint_id="futures_funding_rate_history",
        family="futures_core",
        path="/futures/funding-rate/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Funding bars must align to decision timestamp and exchange funding conventions.",
        history_probe_days=365,
    ),
    EndpointProbe(
        endpoint_id="futures_taker_buy_sell_volume",
        family="futures_core",
        path="/futures/v2/taker-buy-sell-volume/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Use raw taker fields with source coverage sidecar; no imputed zero volumes.",
        history_probe_days=365,
    ),
    EndpointProbe(
        endpoint_id="futures_liquidation_history",
        family="microstructure",
        path="/futures/liquidation/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Sparse liquidation activations need event-rule landing or fail coverage gates.",
        history_probe_days=180,
    ),
    EndpointProbe(
        endpoint_id="futures_orderbook_ask_bids_history",
        family="microstructure",
        path="/futures/orderbook/ask-bids-history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="core_research_input",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Depth units must stay explicit; do not mix quantity and USD fields.",
        history_probe_days=30,
    ),
    EndpointProbe(
        endpoint_id="futures_global_long_short_account_ratio",
        family="participant_state",
        path="/futures/global-long-short-account-ratio/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Participant ratios are contextual unless falsification proves transmission.",
        history_probe_days=180,
    ),
    EndpointProbe(
        endpoint_id="futures_top_long_short_position_ratio",
        family="participant_state",
        path="/futures/top-long-short-position-ratio/history",
        params={"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1h", "limit": DEFAULT_LIMIT},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="start_time/end_time with limit",
        max_result_limit=1000,
        pit_risk_notes="Top-trader ratios need source stability audit and symbol holdouts.",
        history_probe_days=180,
    ),
    EndpointProbe(
        endpoint_id="bitcoin_etf_flow_history",
        family="etf",
        path="/etf/bitcoin/flow-history",
        params={},
        classification="sidecar_context",
        timestamp_field="date",
        pagination_model="full list/no documented page params",
        max_result_limit=None,
        pit_risk_notes="Daily ETF flow must be lagged at least one decision bar unless publication time is known.",
    ),
    EndpointProbe(
        endpoint_id="ethereum_etf_flow_history",
        family="etf",
        path="/etf/ethereum/flow-history",
        params={},
        classification="sidecar_context",
        timestamp_field="date",
        pagination_model="full list/no documented page params",
        max_result_limit=None,
        pit_risk_notes="Daily ETF flow must be lagged at least one decision bar unless publication time is known.",
    ),
    EndpointProbe(
        endpoint_id="bitcoin_etf_history_ibit",
        family="etf",
        path="/etf/bitcoin/history",
        params={"ticker": "IBIT"},
        classification="sidecar_context",
        timestamp_field="date",
        pagination_model="ticker-filtered history",
        max_result_limit=None,
        pit_risk_notes="Premium/discount and assets fields are daily sidecars; apply PIT lag.",
    ),
    EndpointProbe(
        endpoint_id="exchange_assets_binance",
        family="onchain",
        path="/exchange/assets",
        params={"exchange": "Binance", "per_page": 5, "page": 1},
        classification="sidecar_context",
        timestamp_field=None,
        pagination_model="page/per_page snapshot",
        max_result_limit=None,
        pit_risk_notes="Snapshot has no native historical decision timestamp; quarantine from score promotion.",
    ),
    EndpointProbe(
        endpoint_id="exchange_chain_tx_list_usdt",
        family="onchain",
        path="/exchange/chain/tx/list",
        params={"symbol": "USDT", "min_usd": 1000000, "per_page": 5, "page": 1},
        classification="sidecar_context",
        timestamp_field="txTime",
        pagination_model="page/per_page with start_time and min_usd filters",
        max_result_limit=None,
        pit_risk_notes="Exchange transfer feed needs chain/entity semantics and daily PIT aggregation.",
        history_probe_days=30,
    ),
    EndpointProbe(
        endpoint_id="whale_transfer_btc",
        family="onchain",
        path="/chain/v2/whale-transfer",
        params={"symbol": "BTC"},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="start_time/end_time",
        max_result_limit=None,
        pit_risk_notes="Whale transfers are event sidecars; do not replace holder-state data.",
        history_probe_days=30,
    ),
    EndpointProbe(
        endpoint_id="option_exchange_oi_history_btc",
        family="options",
        path="/option/exchange-oi-history",
        params={"symbol": "BTC", "unit": "USD", "range": "1h"},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="range parameter",
        max_result_limit=None,
        pit_risk_notes="Aggregate options OI supports regime gates, not dealer-gamma topology.",
    ),
    EndpointProbe(
        endpoint_id="option_exchange_volume_history_btc",
        family="options",
        path="/option/exchange-vol-history",
        params={"symbol": "BTC", "unit": "USD", "range": "1h"},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="range parameter",
        max_result_limit=None,
        pit_risk_notes="Aggregate option volume is market-wide; avoid symbol-level overclaiming.",
    ),
    EndpointProbe(
        endpoint_id="option_max_pain_btc",
        family="options",
        path="/option/max-pain",
        params={"symbol": "BTC"},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="current/list endpoint",
        max_result_limit=None,
        pit_risk_notes="Max-pain must be used only with known observation date and expiry alignment.",
    ),
    EndpointProbe(
        endpoint_id="option_vs_futures_oi_ratio_btc",
        family="options",
        path="/index/option-vs-futures-oi-ratio",
        params={"symbol": "BTC"},
        classification="sidecar_context",
        timestamp_field="time",
        pagination_model="current/list endpoint",
        max_result_limit=None,
        pit_risk_notes="Market-level diagnostic/regime sidecar; no direct promotion without falsification.",
    ),
    EndpointProbe(
        endpoint_id="pi_cycle_indicator",
        family="vendor_indicator",
        path="/index/pi-cycle-indicator",
        params={},
        classification="diagnostic_only",
        timestamp_field="time",
        pagination_model="vendor indicator list",
        max_result_limit=None,
        pit_risk_notes="Vendor-computed opaque indicator; quarantine from promotion-grade score manifests.",
    ),
    EndpointProbe(
        endpoint_id="bull_market_peak_indicator",
        family="vendor_indicator",
        path="/bull-market-peak-indicator",
        params={},
        classification="diagnostic_only",
        timestamp_field="time",
        pagination_model="vendor indicator list",
        max_result_limit=None,
        pit_risk_notes="Vendor-computed opaque indicator; quarantine from promotion-grade score manifests.",
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _url_for(probe: EndpointProbe, params: dict[str, Any]) -> str:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return f"{BASE_URL}{probe.path}" + (f"?{query}" if query else "")


def _extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("list", "result", "rows"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return nested
            return [data]
    if isinstance(payload, list):
        return payload
    return []


def _sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return "<nested>"
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item, depth=depth + 1) for key, item in list(value.items())[:20]}
    if isinstance(value, list):
        return [_sanitize_value(item, depth=depth + 1) for item in value[:3]]
    if isinstance(value, str):
        if len(value) > 96:
            return value[:96] + "...<truncated>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _observed_keys(rows: list[Any]) -> list[str]:
    keys: set[str] = set()
    for row in rows[:10]:
        if isinstance(row, dict):
            keys.update(str(key) for key in row.keys())
    return sorted(keys)


def _timestamp_bounds(rows: list[Any], timestamp_field: str | None) -> dict[str, Any]:
    if not timestamp_field:
        return {"native_timestamp_field": None, "timezone": "not_applicable"}
    candidate_fields = tuple(
        dict.fromkeys(
            [
                timestamp_field,
                "time",
                "timestamp",
                "date",
                "txTime",
                "transaction_time",
                "block_timestamp",
                "market_date",
                "assets_date",
            ]
        )
    )
    values: list[int] = []
    resolved_field: str | None = None
    for row in rows:
        if isinstance(row, dict):
            for field in candidate_fields:
                if field not in row:
                    continue
                try:
                    raw = int(float(str(row[field])))
                except (TypeError, ValueError):
                    continue
                if raw < 10_000_000_000:
                    raw *= 1000
                values.append(raw)
                resolved_field = resolved_field or field
                break
            if "time_list" in row and isinstance(row["time_list"], list):
                for item in row["time_list"]:
                    try:
                        raw = int(float(str(item)))
                    except (TypeError, ValueError):
                        continue
                    if raw < 10_000_000_000:
                        raw *= 1000
                    values.append(raw)
                resolved_field = resolved_field or "time_list"
        elif isinstance(row, list) and row:
            try:
                raw = int(float(str(row[0])))
            except (TypeError, ValueError):
                continue
            if raw < 10_000_000_000:
                raw *= 1000
            values.append(raw)
            resolved_field = resolved_field or "array[0]"
    if not values:
        return {"native_timestamp_field": timestamp_field, "timezone": "UTC", "first_time_ms": None, "last_time_ms": None}
    first_ms = min(values)
    last_ms = max(values)
    return {
        "native_timestamp_field": resolved_field or timestamp_field,
        "timezone": "UTC",
        "first_time_ms": first_ms,
        "last_time_ms": last_ms,
        "first_time_utc": datetime.fromtimestamp(first_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z"),
        "last_time_utc": datetime.fromtimestamp(last_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z"),
    }


def _probe_once(
    probe: EndpointProbe,
    *,
    params: dict[str, Any],
    http_get_json_fn: Callable[[str], Any],
) -> dict[str, Any]:
    url = _url_for(probe, params)
    payload = http_get_json_fn(url)
    rows = _extract_rows(payload)
    payload_code = str(payload.get("code")) if isinstance(payload, dict) and payload.get("code") is not None else None
    payload_msg = str(payload.get("msg")) if isinstance(payload, dict) and payload.get("msg") is not None else None
    return {
        "url_path": probe.path,
        "params_without_secret": params,
        "payload_code": payload_code,
        "payload_msg": payload_msg,
        "row_count": len(rows),
        "observed_response_keys": _observed_keys(rows),
        "timestamp_observation": _timestamp_bounds(rows, probe.timestamp_field),
        "sample": _sanitize_value(rows[0]) if rows else None,
    }


def _history_params(probe: EndpointProbe, *, days_back: int) -> dict[str, Any]:
    end_time = datetime.now(UTC) - timedelta(days=days_back)
    start_time = end_time - timedelta(days=7)
    params = dict(probe.params)
    params["start_time"] = int(start_time.timestamp() * 1000)
    params["end_time"] = int(end_time.timestamp() * 1000)
    params.setdefault("limit", DEFAULT_LIMIT)
    return params


def build_coinglass_capability_matrix(
    *,
    output_root: Path | None = None,
    http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    resolved_output_root = (output_root or ARTIFACT_ROOT).resolve()
    http_get = http_get_json_fn or _http_get_json
    matrix_entries: list[dict[str, Any]] = []
    samples: dict[str, Any] = {}

    for probe in ENDPOINTS:
        entry = {
            "endpoint_id": probe.endpoint_id,
            "family": probe.family,
            "path": probe.path,
            "classification": probe.classification,
            "plan_availability": "not_checked",
            "observed_response_keys": [],
            "native_timestamp_field": probe.timestamp_field,
            "timezone": "UTC" if probe.timestamp_field else "not_applicable",
            "history_window_observed": None,
            "pagination_model": probe.pagination_model,
            "max_result_limit": probe.max_result_limit,
            "pit_risk_notes": probe.pit_risk_notes,
            "status": "not_run",
            "row_count": 0,
        }
        try:
            recent = _probe_once(probe, params=dict(probe.params), http_get_json_fn=http_get)
            samples[probe.endpoint_id] = recent
            entry["plan_availability"] = "available" if recent["row_count"] > 0 else "available_empty_response"
            entry["observed_response_keys"] = recent["observed_response_keys"]
            entry["row_count"] = recent["row_count"]
            entry["status"] = "success"
            ts = dict(recent["timestamp_observation"])
            entry["native_timestamp_field"] = ts.get("native_timestamp_field")
            entry["timezone"] = ts.get("timezone")
            if ts.get("first_time_utc") or ts.get("last_time_utc"):
                entry["history_window_observed"] = {
                    "recent_first_time_utc": ts.get("first_time_utc"),
                    "recent_last_time_utc": ts.get("last_time_utc"),
                }
            if probe.history_probe_days is not None:
                history = _probe_once(
                    probe,
                    params=_history_params(probe, days_back=probe.history_probe_days),
                    http_get_json_fn=http_get,
                )
                samples[f"{probe.endpoint_id}_history_probe"] = history
                history_ts = dict(history["timestamp_observation"])
                entry["history_window_observed"] = {
                    **dict(entry.get("history_window_observed") or {}),
                    "history_probe_days_back": probe.history_probe_days,
                    "history_probe_row_count": history["row_count"],
                    "history_probe_first_time_utc": history_ts.get("first_time_utc"),
                    "history_probe_last_time_utc": history_ts.get("last_time_utc"),
                }
                if history["row_count"] <= 0:
                    entry["classification"] = (
                        "diagnostic_only" if probe.classification == "diagnostic_only" else "blocked_or_short_history"
                    )
        except HTTPError as exc:
            entry["status"] = "error"
            entry["plan_availability"] = "blocked_or_error"
            entry["classification"] = "diagnostic_only" if probe.classification == "diagnostic_only" else "blocked_or_short_history"
            entry["error_type"] = "HTTPError"
            entry["http_status"] = exc.code
            entry["error"] = str(exc)[:240]
        except (RuntimeError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            entry["status"] = "error"
            entry["plan_availability"] = "blocked_or_error"
            entry["classification"] = "diagnostic_only" if probe.classification == "diagnostic_only" else "blocked_or_short_history"
            entry["error_type"] = type(exc).__name__
            entry["error"] = str(exc)[:240]
        matrix_entries.append(entry)

    summary = {
        "generated_at_utc": _utc_now(),
        "provider": "coinglass",
        "secret_policy": "No API keys or authorization headers are written to these artifacts.",
        "endpoint_count": len(matrix_entries),
        "success_count": sum(1 for item in matrix_entries if item.get("status") == "success"),
        "error_count": sum(1 for item in matrix_entries if item.get("status") == "error"),
        "classification_counts": _count_by(matrix_entries, "classification"),
        "family_counts": _count_by(matrix_entries, "family"),
        "endpoints": matrix_entries,
    }

    resolved_output_root.mkdir(parents=True, exist_ok=True)
    matrix_path = resolved_output_root / "coinglass_capability_matrix.json"
    samples_path = resolved_output_root / "coinglass_endpoint_samples.json"
    report_path = resolved_output_root / "coinglass_capability_matrix_report.md"
    matrix_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    samples_path.write_text(json.dumps(samples, indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(_render_report(summary, matrix_path=matrix_path, samples_path=samples_path), encoding="utf-8")
    return {
        **summary,
        "matrix_path": str(matrix_path),
        "samples_path": str(samples_path),
        "report_path": str(report_path),
    }


def _count_by(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in entries:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _render_report(summary: dict[str, Any], *, matrix_path: Path, samples_path: Path) -> str:
    lines = [
        "# CoinGlass Capability Matrix Smoke Report",
        "",
        f"`Generated at UTC: {summary['generated_at_utc']}`",
        "",
        "No API keys or authorization headers are written to these artifacts.",
        "",
        "## Summary",
        "",
        f"- endpoints checked: {summary['endpoint_count']}",
        f"- success: {summary['success_count']}",
        f"- errors: {summary['error_count']}",
        f"- matrix: `{matrix_path.as_posix()}`",
        f"- sanitized samples: `{samples_path.as_posix()}`",
        "",
        "## Endpoint Matrix",
        "",
        "| endpoint | family | status | classification | rows | observed keys | history observation |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in summary["endpoints"]:
        keys = ", ".join(item.get("observed_response_keys") or []) or "-"
        hist = item.get("history_window_observed")
        if isinstance(hist, dict):
            parts = [
                f"{key}={value}"
                for key, value in hist.items()
                if value is not None and key in {"history_probe_days_back", "history_probe_row_count", "history_probe_first_time_utc", "history_probe_last_time_utc"}
            ]
            hist_text = "; ".join(parts) if parts else "-"
        else:
            hist_text = "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("endpoint_id")),
                    str(item.get("family")),
                    str(item.get("status")),
                    str(item.get("classification")),
                    str(item.get("row_count", 0)),
                    keys.replace("|", "/"),
                    hist_text.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            "Bulk backfill remains blocked for endpoint families whose rows are empty, errored, or classified as `blocked_or_short_history` until the parameter shape and history window are rechecked.",
            "",
        ]
    )
    return "\n".join(lines)
