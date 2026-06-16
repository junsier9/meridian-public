from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.market_data import resolve_config_symbols
from enhengclaw.quant_research.contracts import write_json
from enhengclaw.quant_research.coinglass_derivatives import resolve_coinglass_api_key


BASE_URL = "https://open-api-v4.coinglass.com/api"
DEFAULT_CONFIG = "config/live_trading/hv_balanced_binance_usdm_shadow_loop.yaml"
PROVIDER = "coinglass"
EXCHANGE = "Binance"
CORE_FACTOR_IDS = frozenset(
    {
        "top_trader_long_pct_smooth_5",
        "taker_imb_intraday_dispersion_24h",
        "quality_funding_oi",
        "liq_cascade_recency_score_5d",
        "orderbook_squeeze_veto",
    }
)


@dataclass(frozen=True, slots=True)
class EndpointCall:
    endpoint_id: str
    path: str
    interval: str
    lookback: timedelta
    limit: int
    extra_params: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FactorSpec:
    factor_id: str
    endpoint_calls: tuple[EndpointCall, ...]
    freshness_seconds: int


FACTOR_SPECS: tuple[FactorSpec, ...] = (
    FactorSpec(
        factor_id="top_trader_long_pct_smooth_5",
        endpoint_calls=(
            EndpointCall(
                endpoint_id="futures_top_long_short_position_ratio",
                path="/futures/top-long-short-position-ratio/history",
                interval="1d",
                lookback=timedelta(days=8),
                limit=10,
            ),
        ),
        freshness_seconds=36 * 3600,
    ),
    FactorSpec(
        factor_id="taker_imb_intraday_dispersion_24h",
        endpoint_calls=(
            EndpointCall(
                endpoint_id="futures_taker_buy_sell_volume",
                path="/futures/v2/taker-buy-sell-volume/history",
                interval="1h",
                lookback=timedelta(hours=30),
                limit=40,
            ),
        ),
        freshness_seconds=6 * 3600,
    ),
    FactorSpec(
        factor_id="quality_funding_oi",
        endpoint_calls=(
            EndpointCall(
                endpoint_id="futures_funding_rate_history",
                path="/futures/funding-rate/history",
                interval="1d",
                lookback=timedelta(days=8),
                limit=10,
            ),
            EndpointCall(
                endpoint_id="futures_open_interest_history_usd",
                path="/futures/open-interest/history",
                interval="1d",
                lookback=timedelta(days=8),
                limit=10,
                extra_params={"unit": "usd"},
            ),
        ),
        freshness_seconds=36 * 3600,
    ),
    FactorSpec(
        factor_id="funding_basis_residual_implied_repo_30",
        endpoint_calls=(
            EndpointCall(
                endpoint_id="futures_funding_rate_history",
                path="/futures/funding-rate/history",
                interval="1d",
                lookback=timedelta(days=36),
                limit=40,
            ),
            EndpointCall(
                endpoint_id="futures_price_history",
                path="/futures/price/history",
                interval="1d",
                lookback=timedelta(days=36),
                limit=40,
            ),
            EndpointCall(
                endpoint_id="spot_price_history",
                path="/spot/price/history",
                interval="1d",
                lookback=timedelta(days=36),
                limit=40,
            ),
        ),
        freshness_seconds=36 * 3600,
    ),
    FactorSpec(
        factor_id="liq_cascade_recency_score_5d",
        endpoint_calls=(
            EndpointCall(
                endpoint_id="futures_liquidation_history",
                path="/futures/liquidation/history",
                interval="1h",
                lookback=timedelta(days=35),
                limit=1000,
            ),
            EndpointCall(
                endpoint_id="futures_open_interest_history_usd",
                path="/futures/open-interest/history",
                interval="1h",
                lookback=timedelta(days=35),
                limit=1000,
                extra_params={"unit": "usd"},
            ),
        ),
        freshness_seconds=6 * 3600,
    ),
    FactorSpec(
        factor_id="orderbook_squeeze_veto",
        endpoint_calls=(
            EndpointCall(
                endpoint_id="futures_orderbook_ask_bids_history",
                path="/futures/orderbook/ask-bids-history",
                interval="1h",
                lookback=timedelta(hours=30),
                limit=40,
            ),
        ),
        freshness_seconds=6 * 3600,
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Default-off hv_balanced CoinGlass provider sidecar shadow; writes evidence only, no orders."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--decision-artifact-root", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_provider_sidecar_shadow(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_provider_sidecar_shadow(
    args: argparse.Namespace,
    *,
    http_get_json_fn: Callable[[str], Any] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    live_config = load_live_trading_config(getattr(args, "config", DEFAULT_CONFIG))
    payload = live_config.payload
    now = now_fn or (lambda: datetime.now(UTC))
    started = _ensure_utc(now())
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-provider-sidecar-shadow"
    output_root = _resolve_output_root(args=args, live_artifact_root=live_config.artifact_root, run_id=run_id)
    output_root.mkdir(parents=True, exist_ok=True)
    decision_artifact_root = _optional_path(str(getattr(args, "decision_artifact_root", "") or ""))
    target_context = _load_target_context(decision_artifact_root)
    symbols = _resolve_symbols(
        payload,
        override_symbols=str(getattr(args, "symbols", "") or ""),
        target_context=target_context,
    )
    as_of_ms = _parse_as_of_ms(str(getattr(args, "as_of", "now") or "now"), now_fn=now)

    api_key_present = bool(resolve_coinglass_api_key())
    http_get = http_get_json_fn
    if http_get is None:
        if not api_key_present:
            summary = _blocked_summary(
                run_id=run_id,
                output_root=output_root,
                started=started,
                live_config_path=live_config.path,
                symbols=symbols,
                blockers=["coinglass_api_key_missing"],
                decision_artifact_root=decision_artifact_root,
                target_context=target_context,
            )
            _write_outputs(output_root, summary=summary, observations=[], endpoint_results=[])
            return summary, 2
        http_get = _http_get_json

    observations: list[dict[str, Any]] = []
    endpoint_results: list[dict[str, Any]] = []
    for symbol in symbols:
        for spec in FACTOR_SPECS:
            observation, raw_results = _observe_factor(
                symbol=symbol,
                spec=spec,
                as_of_ms=as_of_ms,
                http_get_json_fn=http_get,
                now_fn=now,
                target_context=target_context,
            )
            observations.append(observation)
            endpoint_results.extend(raw_results)

    summary = _build_summary(
        run_id=run_id,
        output_root=output_root,
        started=started,
        live_config_path=live_config.path,
        symbols=symbols,
        observations=observations,
        endpoint_results=endpoint_results,
        decision_artifact_root=decision_artifact_root,
        target_context=target_context,
    )
    _write_outputs(output_root, summary=summary, observations=observations, endpoint_results=endpoint_results)
    return summary, 0 if summary["status"] == "provider_sidecar_shadow_ready" else 2


def _http_get_json(url: str) -> Any:
    api_key = resolve_coinglass_api_key()
    if not api_key:
        raise RuntimeError("CoinglassAPI env var is missing")
    request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _observe_factor(
    *,
    symbol: str,
    spec: FactorSpec,
    as_of_ms: int,
    http_get_json_fn: Callable[[str], Any],
    now_fn: Callable[[], datetime],
    target_context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    endpoint_results: list[dict[str, Any]] = []
    by_endpoint: dict[str, dict[str, Any]] = {}
    for call in spec.endpoint_calls:
        result = _fetch_endpoint(
            symbol=symbol,
            call=call,
            as_of_ms=as_of_ms,
            http_get_json_fn=http_get_json_fn,
            now_fn=now_fn,
        )
        endpoint_results.append(result)
        by_endpoint[call.endpoint_id] = result
    computed_first = _compute_factor(spec.factor_id, by_endpoint)
    computed_second = _compute_factor(spec.factor_id, by_endpoint)
    deterministic = _json_stable(computed_first) == _json_stable(computed_second)
    latest_provider_time_ms = _max_int(
        [
            int(item.get("provider_timestamp_ms"))
            for item in endpoint_results
            if item.get("provider_timestamp_ms") is not None
        ]
    )
    available_at_ms = _max_int(
        [
            int(item.get("available_at_ms"))
            for item in endpoint_results
            if item.get("available_at_ms") is not None
        ]
    )
    decision_time_ms = available_at_ms or int(_ensure_utc(now_fn()).timestamp() * 1000)
    latency_ms = float(sum(float(item.get("request_latency_ms") or 0.0) for item in endpoint_results))
    raw_status = _raw_status(endpoint_results)
    readiness = str(computed_first.get("readiness") or "missing")
    if readiness == "ready" and latest_provider_time_ms is not None:
        freshness_seconds = max(0.0, (decision_time_ms - latest_provider_time_ms) / 1000.0)
        if freshness_seconds > spec.freshness_seconds:
            readiness = "stale"
            computed_first["readiness"] = "stale"
            computed_first.setdefault("blockers", []).append(
                f"stale_provider_timestamp:{freshness_seconds:.0f}s>{spec.freshness_seconds}s"
            )
    else:
        freshness_seconds = None
    pit_ok = (
        latest_provider_time_ms is not None
        and available_at_ms is not None
        and latest_provider_time_ms <= available_at_ms <= decision_time_ms
    )
    fallback_ok = readiness == "ready" or computed_first.get("factor_value") is None
    observation = {
        "decision_time": _iso_from_ms(decision_time_ms),
        "decision_time_ms": decision_time_ms,
        "hv_decision_time": target_context.get("hv_decision_time"),
        "hv_decision_time_ms": target_context.get("hv_decision_time_ms"),
        "symbol": symbol,
        "provider": PROVIDER,
        "factor_id": spec.factor_id,
        "endpoint": ",".join(call.path for call in spec.endpoint_calls),
        "endpoint_ids": [call.endpoint_id for call in spec.endpoint_calls],
        "provider_timestamp": _iso_from_ms(latest_provider_time_ms) if latest_provider_time_ms is not None else None,
        "provider_timestamp_ms": latest_provider_time_ms,
        "available_at": _iso_from_ms(available_at_ms) if available_at_ms is not None else None,
        "available_at_ms": available_at_ms,
        "request_latency_ms": round(latency_ms, 3),
        "endpoint_latencies_ms": {
            str(item.get("endpoint_id")): round(float(item.get("request_latency_ms") or 0.0), 3)
            for item in endpoint_results
        },
        "raw_status": raw_status,
        "normalized_value": computed_first.get("normalized_value"),
        "factor_value": computed_first.get("factor_value") if readiness == "ready" else None,
        "readiness": readiness,
        "status": readiness,
        "blockers": sorted(set(str(item) for item in list(computed_first.get("blockers") or []))),
        "pit_ok": bool(pit_ok),
        "fallback_ok": bool(fallback_ok),
        "determinism_ok": bool(deterministic),
        "freshness_seconds": freshness_seconds,
        "applied_to_live": False,
        "overlay_action": "not_applied_shadow_only" if readiness == "ready" else "not_ready_no_overlay",
        "raw_payload_sha256": _sha256_text(_json_stable([item.get("payload_sha256") for item in endpoint_results])),
        "factor_input_sha256": _sha256_text(_json_stable({key: value.get("rows", []) for key, value in by_endpoint.items()})),
        "notes": computed_first.get("notes", []),
    }
    return observation, endpoint_results


def _fetch_endpoint(
    *,
    symbol: str,
    call: EndpointCall,
    as_of_ms: int,
    http_get_json_fn: Callable[[str], Any],
    now_fn: Callable[[], datetime],
) -> dict[str, Any]:
    start_ms = max(0, as_of_ms - int(call.lookback.total_seconds() * 1000))
    params = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "interval": call.interval,
        "limit": call.limit,
        "start_time": start_ms,
        "end_time": as_of_ms,
    }
    params.update(dict(call.extra_params or {}))
    url = f"{BASE_URL}{call.path}?{urlencode(params)}"
    requested_at = _ensure_utc(now_fn())
    started = time.perf_counter()
    payload: Any = None
    error: str | None = None
    try:
        payload = http_get_json_fn(url)
    except Exception as exc:  # noqa: BLE001 - provider sidecar must record provider failures.
        error = f"{type(exc).__name__}:{exc}"
    latency_ms = (time.perf_counter() - started) * 1000.0
    available_at = _ensure_utc(now_fn())
    rows = _extract_rows(payload)
    filtered = []
    for row in rows:
        row_ts = _row_time_ms(row)
        if row_ts is None or row_ts <= as_of_ms:
            filtered.append(row)
    provider_timestamp_ms = _max_int([_row_time_ms(row) for row in filtered])
    payload_code = str(payload.get("code")) if isinstance(payload, dict) and payload.get("code") is not None else None
    payload_msg = str(payload.get("msg")) if isinstance(payload, dict) and payload.get("msg") is not None else None
    raw_status = "success" if error is None and filtered else "missing"
    if error:
        raw_status = "error"
    return {
        "provider": PROVIDER,
        "symbol": symbol,
        "endpoint_id": call.endpoint_id,
        "endpoint": call.path,
        "params_without_secret": params,
        "requested_at": requested_at.isoformat().replace("+00:00", "Z"),
        "available_at": available_at.isoformat().replace("+00:00", "Z"),
        "available_at_ms": int(available_at.timestamp() * 1000),
        "request_latency_ms": round(latency_ms, 3),
        "raw_status": raw_status,
        "error": error,
        "payload_code": payload_code,
        "payload_msg": payload_msg,
        "row_count": len(filtered),
        "provider_timestamp_ms": provider_timestamp_ms,
        "provider_timestamp": _iso_from_ms(provider_timestamp_ms) if provider_timestamp_ms is not None else None,
        "observed_response_keys": _observed_keys(filtered),
        "payload_sha256": _sha256_text(_json_stable(_sanitize_payload(payload))),
        "sample": _sanitize_payload(filtered[0]) if filtered else None,
        "rows": filtered,
    }


def _compute_factor(factor_id: str, by_endpoint: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if factor_id == "top_trader_long_pct_smooth_5":
        rows = _rows(by_endpoint, "futures_top_long_short_position_ratio")
        values = [
            _float_from_row(row, "top_position_long_percent", "top_trader_long_pct", "long_percent", "longShortRatio")
            for row in _sorted_rows(rows)
        ]
        return _compute_top_trader(rows, values)
    if factor_id == "taker_imb_intraday_dispersion_24h":
        return _compute_taker_dispersion(_rows(by_endpoint, "futures_taker_buy_sell_volume"))
    if factor_id == "quality_funding_oi":
        return _compute_quality_funding_oi(
            funding_rows=_rows(by_endpoint, "futures_funding_rate_history"),
            oi_rows=_rows(by_endpoint, "futures_open_interest_history_usd"),
        )
    if factor_id == "funding_basis_residual_implied_repo_30":
        return _compute_funding_basis_residual(
            funding_rows=_rows(by_endpoint, "futures_funding_rate_history"),
            futures_price_rows=_rows(by_endpoint, "futures_price_history"),
            spot_price_rows=_rows(by_endpoint, "spot_price_history"),
        )
    if factor_id == "liq_cascade_recency_score_5d":
        return _compute_liq_cascade(
            liquidation_rows=_rows(by_endpoint, "futures_liquidation_history"),
            oi_rows=_rows(by_endpoint, "futures_open_interest_history_usd"),
        )
    if factor_id == "orderbook_squeeze_veto":
        return _compute_orderbook_squeeze(_rows(by_endpoint, "futures_orderbook_ask_bids_history"))
    return {"readiness": "missing", "factor_value": None, "normalized_value": None, "blockers": ["unknown_factor"]}


def _compute_top_trader(rows: list[Any], values: list[float | None]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if len(clean) < 5:
        return _not_ready("top_trader_window_lt_5", row_count=len(rows), value_count=len(clean))
    window = clean[-5:]
    return {
        "readiness": "ready",
        "factor_value": float(sum(window) / len(window)),
        "normalized_value": {"window_count": len(window), "latest_long_pct": window[-1], "mean_5": sum(window) / len(window)},
        "blockers": [],
        "notes": ["5-bar rolling mean of CoinGlass top-trader long percent."],
    }


def _compute_taker_dispersion(rows: list[Any]) -> dict[str, Any]:
    imbalances: list[float] = []
    for row in _sorted_rows(rows)[-24:]:
        buy = _float_from_row(row, "taker_buy_volume_usd", "buy_volume_usd", "buy")
        sell = _float_from_row(row, "taker_sell_volume_usd", "sell_volume_usd", "sell")
        if buy is None or sell is None or buy + sell <= 0:
            continue
        imbalances.append((buy - sell) / (buy + sell))
    if len(imbalances) < 24:
        return _not_ready("taker_imbalance_window_lt_24h", row_count=len(rows), value_count=len(imbalances))
    dispersion = float(statistics.stdev(imbalances)) if len(imbalances) > 1 else 0.0
    return {
        "readiness": "ready",
        "factor_value": dispersion,
        "normalized_value": {
            "hour_count": len(imbalances),
            "latest_imbalance": imbalances[-1],
            "std_24h": dispersion,
        },
        "blockers": [],
        "notes": ["24 hourly taker imbalance dispersion; no zero-fill on missing rows."],
    }


def _compute_quality_funding_oi(*, funding_rows: list[Any], oi_rows: list[Any]) -> dict[str, Any]:
    funding = _series_by_time(funding_rows, value_aliases=("close", "funding_rate", "c"))
    oi = _series_by_time(oi_rows, value_aliases=("close", "open_interest_value", "sum_open_interest_value", "c"))
    common = sorted(set(funding).intersection(oi))
    if len(common) < 6:
        return _not_ready("funding_oi_common_window_lt_6", funding_count=len(funding), oi_count=len(oi), common_count=len(common))
    latest = common[-1]
    lag = common[-6]
    latest_oi = oi[latest]
    lag_oi = oi[lag]
    if lag_oi == 0:
        return _not_ready("oi_lag_zero", common_count=len(common))
    oi_change_5 = (latest_oi / lag_oi) - 1.0
    factor = funding[latest] * oi_change_5
    return {
        "readiness": "ready",
        "factor_value": float(factor),
        "normalized_value": {
            "latest_funding_rate": funding[latest],
            "oi_change_5": oi_change_5,
            "latest_open_interest_value": latest_oi,
            "common_count": len(common),
        },
        "blockers": [],
        "notes": ["funding_rate * 5-bar OI percentage change."],
    }


def _compute_funding_basis_residual(
    *,
    funding_rows: list[Any],
    futures_price_rows: list[Any],
    spot_price_rows: list[Any],
) -> dict[str, Any]:
    funding = _series_by_time(funding_rows, value_aliases=("close", "funding_rate", "c"))
    futures_price = _series_by_time(futures_price_rows, value_aliases=("close", "price", "c"))
    spot_price = _series_by_time(spot_price_rows, value_aliases=("close", "price", "c"))
    common = sorted(set(funding).intersection(futures_price).intersection(spot_price))
    if len(common) < 30:
        return _not_ready(
            "funding_basis_common_window_lt_30",
            funding_count=len(funding),
            futures_price_count=len(futures_price),
            spot_price_count=len(spot_price),
            common_count=len(common),
        )
    window = common[-30:]
    basis_values: list[float] = []
    funding_values: list[float] = []
    close_returns: list[float] = []
    prev_spot: float | None = None
    for ts in window:
        spot = spot_price[ts]
        fut = futures_price[ts]
        if spot == 0:
            continue
        basis_values.append((fut - spot) / spot)
        funding_values.append(funding[ts])
        if prev_spot not in (None, 0):
            close_returns.append(abs((spot / float(prev_spot)) - 1.0))
        prev_spot = spot
    if len(basis_values) < 30 or len(funding_values) < 30:
        return _not_ready("funding_basis_clean_window_lt_30", common_count=len(common), clean_count=len(basis_values))
    atr_proxy = float(sum(close_returns[-20:]) / len(close_returns[-20:])) if close_returns[-20:] else 0.0
    if atr_proxy <= 0:
        return _not_ready("diagnostic_atr_proxy_unavailable", common_count=len(common), clean_count=len(basis_values))
    factor = (float(sum(funding_values) / len(funding_values)) - float(sum(basis_values) / len(basis_values))) / atr_proxy
    return {
        "readiness": "ready",
        "factor_value": float(factor),
        "normalized_value": {
            "common_count": len(common),
            "funding_mean_30": float(sum(funding_values) / len(funding_values)),
            "basis_mean_30": float(sum(basis_values) / len(basis_values)),
            "atr_proxy_20_from_spot_abs_returns": atr_proxy,
            "normalization_quality": "diagnostic_vendor_price_not_canonical",
        },
        "blockers": [],
        "notes": [
            "Live implementability approximation using CoinGlass futures/spot price; Binance canonical price remains required before score use."
        ],
    }


def _compute_liq_cascade(*, liquidation_rows: list[Any], oi_rows: list[Any]) -> dict[str, Any]:
    liq_by_time: dict[int, dict[str, float]] = {}
    for row in liquidation_rows:
        ts = _row_time_ms(row)
        if ts is None:
            continue
        long_liq = _float_from_row(row, "long_liquidation_usd", "longLiquidationUsd", "long_liquidation")
        short_liq = _float_from_row(row, "short_liquidation_usd", "shortLiquidationUsd", "short_liquidation")
        liq_by_time[ts] = {"long": float(long_liq or 0.0), "short": float(short_liq or 0.0)}
    oi = _series_by_time(oi_rows, value_aliases=("close", "open_interest_value", "sum_open_interest_value", "c"))
    common = sorted(set(liq_by_time).intersection(oi))
    if len(common) < 120:
        return _not_ready("liquidation_oi_common_window_lt_120h", liquidation_count=len(liq_by_time), oi_count=len(oi), common_count=len(common))
    liq_to_oi: list[float] = []
    signed_imbalance: list[float] = []
    for ts in common:
        total = liq_by_time[ts]["long"] + liq_by_time[ts]["short"]
        oi_value = oi[ts]
        liq_to_oi.append(total / oi_value if oi_value else 0.0)
        signed_imbalance.append((liq_by_time[ts]["long"] - liq_by_time[ts]["short"]) / total if total else 0.0)
    rolling_window = min(720, len(liq_to_oi))
    baseline = liq_to_oi[-rolling_window:]
    mean = float(sum(baseline) / len(baseline))
    stdev = float(statistics.stdev(baseline)) if len(baseline) > 1 else 0.0
    decay = math.log(2.0) / (5.0 * 24.0)
    state = 0.0
    for value, signed in zip(liq_to_oi[-120:], signed_imbalance[-120:], strict=False):
        state *= math.exp(-decay)
        z = ((value - mean) / stdev) if stdev > 0 else 0.0
        if z > 2.5:
            state += min(z, 10.0) * (1.0 if signed >= 0 else -1.0)
    return {
        "readiness": "ready",
        "factor_value": float(state),
        "normalized_value": {
            "common_hour_count": len(common),
            "rolling_baseline_hours": rolling_window,
            "latest_liq_to_oi": liq_to_oi[-1],
            "latest_signed_imbalance": signed_imbalance[-1],
            "recency_score_5d": state,
        },
        "blockers": [],
        "notes": ["Hourly live approximation of liquidation cascade recency; no missing-row zero-fill."],
    }


def _compute_orderbook_squeeze(rows: list[Any]) -> dict[str, Any]:
    imbalances: list[float] = []
    latest_depth: dict[str, float] = {}
    for row in _sorted_rows(rows)[-24:]:
        bids = _float_from_row(row, "bids_usd", "orderbook_bids_usd", "bid_usd", "bids")
        asks = _float_from_row(row, "asks_usd", "orderbook_asks_usd", "ask_usd", "asks")
        if bids is None or asks is None or bids + asks <= 0:
            continue
        imbalances.append((bids - asks) / (bids + asks))
        latest_depth = {"bids_usd": bids, "asks_usd": asks, "total_depth_usd": bids + asks}
    if len(imbalances) < 12:
        return _not_ready("orderbook_window_lt_12h", row_count=len(rows), value_count=len(imbalances))
    latest_imbalance = imbalances[-1]
    factor = abs(latest_imbalance)
    return {
        "readiness": "ready",
        "factor_value": float(factor),
        "normalized_value": {
            "hour_count": len(imbalances),
            "latest_orderbook_imbalance": latest_imbalance,
            "mean_abs_imbalance_24h": float(sum(abs(x) for x in imbalances) / len(imbalances)),
            **latest_depth,
        },
        "blockers": [],
        "notes": ["Orderbook imbalance magnitude for shadow squeeze veto diagnostics only."],
    }


def _build_summary(
    *,
    run_id: str,
    output_root: Path,
    started: datetime,
    live_config_path: Path,
    symbols: list[str],
    observations: list[dict[str, Any]],
    endpoint_results: list[dict[str, Any]],
    decision_artifact_root: Path | None,
    target_context: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    factor_ids = sorted({str(row.get("factor_id")) for row in observations})
    ready = [row for row in observations if row.get("readiness") == "ready"]
    core = [row for row in observations if row.get("factor_id") in CORE_FACTOR_IDS]
    core_ready = [row for row in core if row.get("readiness") == "ready"]
    expected_core = max(1, len(symbols) * len(CORE_FACTOR_IDS))
    core_ready_fraction = len(core_ready) / expected_core
    symbols_core_ready = {
        symbol
        for symbol in symbols
        if all(
            any(row.get("symbol") == symbol and row.get("factor_id") == factor_id and row.get("readiness") == "ready" for row in core)
            for factor_id in CORE_FACTOR_IDS
        )
    }
    symbol_coverage_fraction = len(symbols_core_ready) / max(1, len(symbols))
    latencies = [float(item.get("request_latency_ms") or 0.0) for item in endpoint_results]
    p95_latency_ms = _percentile(latencies, 95)
    pit_violations = [
        row
        for row in observations
        if row.get("readiness") == "ready" and not bool(row.get("pit_ok"))
    ]
    fallback_violations = [row for row in observations if not bool(row.get("fallback_ok"))]
    deterministic_violations = [row for row in observations if not bool(row.get("determinism_ok"))]
    stale_rows = [row for row in observations if row.get("readiness") == "stale"]
    if core_ready_fraction < 0.95:
        blockers.append(f"core_factor_ready_fraction_below_95pct:{core_ready_fraction:.4f}")
    if symbol_coverage_fraction < 0.95:
        blockers.append(f"symbol_core_coverage_below_95pct:{symbol_coverage_fraction:.4f}")
    if p95_latency_ms > 10_000:
        blockers.append(f"latency_p95_gt_10s:{p95_latency_ms:.3f}")
    if stale_rows:
        blockers.append(f"stale_observation_count:{len(stale_rows)}")
    if pit_violations:
        blockers.append(f"pit_violation_count:{len(pit_violations)}")
    if fallback_violations:
        blockers.append(f"fallback_violation_count:{len(fallback_violations)}")
    if deterministic_violations:
        blockers.append(f"determinism_mismatch_count:{len(deterministic_violations)}")
    return {
        "run_id": run_id,
        "status": "provider_sidecar_shadow_ready" if not blockers else "provider_sidecar_shadow_blocked",
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(output_root),
        "config": str(live_config_path),
        "decision_artifact_root": str(decision_artifact_root) if decision_artifact_root else "",
        "target_context": target_context,
        "provider": PROVIDER,
        "applied_to_live": False,
        "alpha_score_changed": False,
        "live_config_changed": False,
        "exchange_order_submission": "disabled",
        "symbol_count": len(symbols),
        "symbols": symbols,
        "factor_ids": factor_ids,
        "observation_count": len(observations),
        "ready_observation_count": len(ready),
        "core_factor_ids": sorted(CORE_FACTOR_IDS),
        "core_ready_observation_count": len(core_ready),
        "core_ready_fraction": core_ready_fraction,
        "symbol_core_coverage_fraction": symbol_coverage_fraction,
        "latency_p95_ms": p95_latency_ms,
        "latency_gate_passed": p95_latency_ms <= 10_000,
        "freshness_gate_passed": not stale_rows,
        "pit_gate_passed": not pit_violations,
        "fallback_gate_passed": not fallback_violations,
        "determinism_gate_passed": not deterministic_violations,
        "endpoint_request_count": len(endpoint_results),
        "endpoint_success_count": sum(item.get("raw_status") == "success" for item in endpoint_results),
        "endpoint_error_count": sum(item.get("raw_status") == "error" for item in endpoint_results),
        "readiness_counts": _counts(str(row.get("readiness") or "missing") for row in observations),
        "factor_readiness": _factor_readiness(observations),
        "outputs": {
            "summary": str(output_root / "provider_sidecar_shadow_summary.json"),
            "observations_jsonl": str(output_root / "provider_sidecar_observations.jsonl"),
            "observations_csv": str(output_root / "provider_sidecar_observations.csv"),
            "endpoint_manifest_jsonl": str(output_root / "provider_sidecar_endpoint_manifest.jsonl"),
        },
    }


def _blocked_summary(
    *,
    run_id: str,
    output_root: Path,
    started: datetime,
    live_config_path: Path,
    symbols: list[str],
    blockers: list[str],
    decision_artifact_root: Path | None,
    target_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "provider_sidecar_shadow_blocked",
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(output_root),
        "config": str(live_config_path),
        "decision_artifact_root": str(decision_artifact_root) if decision_artifact_root else "",
        "target_context": target_context,
        "provider": PROVIDER,
        "applied_to_live": False,
        "alpha_score_changed": False,
        "live_config_changed": False,
        "exchange_order_submission": "disabled",
        "symbol_count": len(symbols),
        "symbols": symbols,
        "observation_count": 0,
    }


def _write_outputs(
    output_root: Path,
    *,
    summary: dict[str, Any],
    observations: list[dict[str, Any]],
    endpoint_results: list[dict[str, Any]],
) -> None:
    write_json(output_root / "provider_sidecar_shadow_summary.json", summary)
    write_json(output_root / "run_summary.json", summary)
    _write_jsonl(output_root / "provider_sidecar_observations.jsonl", observations)
    _write_jsonl(output_root / "provider_sidecar_endpoint_manifest.jsonl", [_strip_rows(item) for item in endpoint_results])
    _write_csv(output_root / "provider_sidecar_observations.csv", observations)


def _resolve_output_root(*, args: argparse.Namespace, live_artifact_root: Path, run_id: str) -> Path:
    raw = str(getattr(args, "output_root", "") or "").strip()
    if raw:
        return resolve_repo_path(raw)
    return (live_artifact_root.parent / "provider_sidecar_shadow" / run_id).resolve()


def _resolve_symbols(payload: dict[str, Any], *, override_symbols: str, target_context: dict[str, Any]) -> list[str]:
    target_symbols = [str(item).strip().upper() for item in list(target_context.get("target_symbols") or []) if str(item).strip()]
    if override_symbols:
        return resolve_config_symbols(payload, override_symbols=override_symbols)
    if target_symbols:
        seen: set[str] = set()
        return [symbol for symbol in target_symbols if not (symbol in seen or seen.add(symbol))]
    return resolve_config_symbols(payload)


def _load_target_context(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"source": "config_symbols_only", "target_symbols": []}
    context: dict[str, Any] = {"source": str(path), "target_symbols": []}
    target_positions = path / "target_positions.csv"
    if target_positions.exists():
        with target_positions.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            context["target_symbols"] = sorted(
                {
                    str(row.get("usdm_symbol") or row.get("symbol") or "").strip().upper()
                    for row in reader
                    if str(row.get("usdm_symbol") or row.get("symbol") or "").strip()
                }
            )
    snapshot_path = path / "decision_snapshot.json"
    if snapshot_path.exists():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            snapshot = {}
        decision_time_ms = _maybe_int(snapshot.get("decision_time_ms"))
        context["hv_decision_id"] = snapshot.get("decision_id")
        context["hv_decision_time_ms"] = decision_time_ms
        context["hv_decision_time"] = _iso_from_ms(decision_time_ms) if decision_time_ms is not None else None
    return context


def _parse_as_of_ms(raw: str, *, now_fn: Callable[[], datetime]) -> int:
    value = str(raw or "now").strip()
    if not value or value.lower() == "now":
        return int(_ensure_utc(now_fn()).timestamp() * 1000)
    if value.isdigit():
        parsed = int(value)
        return parsed if parsed > 10_000_000_000 else parsed * 1000
    try:
        parsed_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(_ensure_utc(parsed_dt).timestamp() * 1000)
    except ValueError:
        parsed_date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
        return int(parsed_date.timestamp() * 1000)


def _optional_path(raw: str) -> Path | None:
    if not raw.strip():
        return None
    return resolve_repo_path(raw)


def _rows(by_endpoint: dict[str, dict[str, Any]], endpoint_id: str) -> list[Any]:
    return list(dict(by_endpoint.get(endpoint_id) or {}).get("rows") or [])


def _compute_missing_endpoint_blockers(by_endpoint: dict[str, dict[str, Any]]) -> list[str]:
    return [f"endpoint_error:{key}" for key, value in by_endpoint.items() if value.get("raw_status") == "error"]


def _not_ready(reason: str, **context: Any) -> dict[str, Any]:
    return {
        "readiness": "not_ready",
        "factor_value": None,
        "normalized_value": {"reason": reason, **context},
        "blockers": [reason],
        "notes": [],
    }


def _series_by_time(rows: list[Any], *, value_aliases: tuple[str, ...]) -> dict[int, float]:
    output: dict[int, float] = {}
    for row in rows:
        ts = _row_time_ms(row)
        value = _float_from_row(row, *value_aliases)
        if ts is None or value is None:
            continue
        output[ts] = value
    return dict(sorted(output.items()))


def _float_from_row(row: Any, *keys: str) -> float | None:
    if not isinstance(row, dict):
        return None
    for key in keys:
        if key in row:
            value = _maybe_float(row.get(key))
            if value is not None:
                return value
    return None


def _maybe_float(value: Any) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _maybe_int(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _row_time_ms(row: Any) -> int | None:
    if isinstance(row, dict):
        for key in ("time", "timestamp", "date", "open_time_ms", "t"):
            if key not in row:
                continue
            parsed = _parse_timestamp_value(row.get(key))
            if parsed is not None:
                return parsed
    if isinstance(row, list) and row:
        return _parse_timestamp_value(row[0])
    return None


def _parse_timestamp_value(value: Any) -> int | None:
    parsed = _maybe_int(value)
    if parsed is not None:
        return parsed * 1000 if parsed < 10_000_000_000 else parsed
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            try:
                return int(datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
            except ValueError:
                return None
    return None


def _extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("list", "result", "rows", "data"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return nested
            return [data]
    if isinstance(payload, list):
        return payload
    return []


def _sorted_rows(rows: list[Any]) -> list[Any]:
    return sorted(rows, key=lambda row: _row_time_ms(row) or 0)


def _observed_keys(rows: list[Any]) -> list[str]:
    keys: set[str] = set()
    for row in rows[:10]:
        if isinstance(row, dict):
            keys.update(str(key) for key in row.keys())
    return sorted(keys)


def _raw_status(endpoint_results: list[dict[str, Any]]) -> str:
    statuses = [str(item.get("raw_status") or "missing") for item in endpoint_results]
    if any(status == "error" for status in statuses):
        return "error"
    if all(status == "success" for status in statuses):
        return "success"
    if any(status == "success" for status in statuses):
        return "partial"
    return "missing"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_from_ms(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _max_int(values: Iterable[int | None]) -> int | None:
    clean = [int(value) for value in values if value is not None]
    return max(clean) if clean else None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * pct / 100.0
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _factor_readiness(observations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for row in observations:
        factor_id = str(row.get("factor_id") or "")
        readiness = str(row.get("readiness") or "missing")
        output.setdefault(factor_id, {})
        output[factor_id][readiness] = output[factor_id].get(readiness, 0) + 1
    return {key: dict(sorted(value.items())) for key, value in sorted(output.items())}


def _sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "<nested>"
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item, depth=depth + 1) for key, item in list(value.items())[:32]}
    if isinstance(value, list):
        return [_sanitize_payload(item, depth=depth + 1) for item in value[:5]]
    if isinstance(value, str):
        return value[:160] + "...<truncated>" if len(value) > 160 else value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _json_stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strip_rows(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "rows"}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(_json_stable(row))
            handle.write("\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "decision_time",
        "symbol",
        "provider",
        "factor_id",
        "endpoint",
        "provider_timestamp",
        "available_at",
        "request_latency_ms",
        "raw_status",
        "readiness",
        "factor_value",
        "pit_ok",
        "fallback_ok",
        "determinism_ok",
        "applied_to_live",
        "overlay_action",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


if __name__ == "__main__":
    raise SystemExit(main())
