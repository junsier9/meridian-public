from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from enhengclaw.utils.subject_keys import SubjectKey


BINANCE_TRADE_PROVIDER_KIND = "binance_trade"
ALCHEMY_EVM_BLOCK_PROVIDER_KIND = "alchemy_evm_block"
ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND = "alchemy_bitcoin_block"
ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND = "alchemy_solana_block"

BINANCE_PROVIDER_ID = "binance.spot.ws"
LEGACY_ALCHEMY_PROVIDER_ID = "alchemy.eth.rpc"


def binance_trade_provider_payload(
    *,
    symbol: str,
    websocket_url: str,
    receive_timeout_seconds: float,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    max_reconnect_attempts: int | None,
    provider_id: str = BINANCE_PROVIDER_ID,
    subject_key: str | None = None,
) -> dict[str, Any]:
    normalized_symbol = _non_empty_string(symbol, field="symbol").upper()
    expected_subject_key = _expected_subject_key(
        symbol=normalized_symbol,
        venue="binance",
        instrument_type="spot",
    )
    return normalize_provider_payload(
        {
            "kind": BINANCE_TRADE_PROVIDER_KIND,
            "provider_id": provider_id,
            "subject_key": expected_subject_key if subject_key is None else subject_key,
            "symbol": normalized_symbol,
            "websocket_url": websocket_url,
            "receive_timeout_seconds": receive_timeout_seconds,
            "initial_backoff_seconds": initial_backoff_seconds,
            "max_backoff_seconds": max_backoff_seconds,
            "max_reconnect_attempts": max_reconnect_attempts,
        }
    )


def alchemy_evm_block_provider_payload(
    *,
    symbol: str,
    network: str,
    poll_interval_seconds: float,
    request_timeout_seconds: float,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    max_retry_attempts: int | None,
    degraded_after_failures: int,
    include_block_details: bool,
    endpoint_url: str | None = None,
    provider_id: str | None = None,
    subject_key: str | None = None,
) -> dict[str, Any]:
    normalized_symbol = _non_empty_string(symbol, field="symbol").upper()
    derived_provider_id = provider_id or f"alchemy.{normalized_symbol.lower()}.rpc"
    expected_subject_key = _expected_subject_key(
        symbol=normalized_symbol,
        venue="alchemy",
        instrument_type="onchain",
    )
    return normalize_provider_payload(
        {
            "kind": ALCHEMY_EVM_BLOCK_PROVIDER_KIND,
            "provider_id": derived_provider_id,
            "subject_key": expected_subject_key if subject_key is None else subject_key,
            "symbol": normalized_symbol,
            "network": network,
            "endpoint_url": endpoint_url,
            "poll_interval_seconds": poll_interval_seconds,
            "request_timeout_seconds": request_timeout_seconds,
            "initial_backoff_seconds": initial_backoff_seconds,
            "max_backoff_seconds": max_backoff_seconds,
            "max_retry_attempts": max_retry_attempts,
            "degraded_after_failures": degraded_after_failures,
            "include_block_details": include_block_details,
        }
    )


def alchemy_solana_block_provider_payload(
    *,
    symbol: str,
    network: str,
    poll_interval_seconds: float,
    request_timeout_seconds: float,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    max_retry_attempts: int | None,
    degraded_after_failures: int,
    include_block_details: bool = True,
    endpoint_url: str | None = None,
    provider_id: str | None = None,
    subject_key: str | None = None,
    commitment: str = "finalized",
    encoding: str = "json",
    transaction_details: str = "none",
) -> dict[str, Any]:
    normalized_symbol = _non_empty_string(symbol, field="symbol").upper()
    derived_provider_id = provider_id or f"alchemy.{normalized_symbol.lower()}.rpc"
    expected_subject_key = _expected_subject_key(
        symbol=normalized_symbol,
        venue="alchemy",
        instrument_type="onchain",
    )
    return normalize_provider_payload(
        {
            "kind": ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND,
            "provider_id": derived_provider_id,
            "subject_key": expected_subject_key if subject_key is None else subject_key,
            "symbol": normalized_symbol,
            "network": network,
            "endpoint_url": endpoint_url,
            "poll_interval_seconds": poll_interval_seconds,
            "request_timeout_seconds": request_timeout_seconds,
            "initial_backoff_seconds": initial_backoff_seconds,
            "max_backoff_seconds": max_backoff_seconds,
            "max_retry_attempts": max_retry_attempts,
            "degraded_after_failures": degraded_after_failures,
            "include_block_details": include_block_details,
            "commitment": commitment,
            "encoding": encoding,
            "transaction_details": transaction_details,
        }
    )


def alchemy_bitcoin_block_provider_payload(
    *,
    symbol: str,
    network: str,
    poll_interval_seconds: float,
    request_timeout_seconds: float,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    max_retry_attempts: int | None,
    degraded_after_failures: int,
    include_block_details: bool,
    endpoint_url: str | None = None,
    provider_id: str | None = None,
    subject_key: str | None = None,
) -> dict[str, Any]:
    normalized_symbol = _non_empty_string(symbol, field="symbol").upper()
    derived_provider_id = provider_id or f"alchemy.{normalized_symbol.lower()}.rpc"
    expected_subject_key = _expected_subject_key(
        symbol=normalized_symbol,
        venue="alchemy",
        instrument_type="onchain",
    )
    return normalize_provider_payload(
        {
            "kind": ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND,
            "provider_id": derived_provider_id,
            "subject_key": expected_subject_key if subject_key is None else subject_key,
            "symbol": normalized_symbol,
            "network": network,
            "endpoint_url": endpoint_url,
            "poll_interval_seconds": poll_interval_seconds,
            "request_timeout_seconds": request_timeout_seconds,
            "initial_backoff_seconds": initial_backoff_seconds,
            "max_backoff_seconds": max_backoff_seconds,
            "max_retry_attempts": max_retry_attempts,
            "degraded_after_failures": degraded_after_failures,
            "include_block_details": include_block_details,
        }
    )


def build_legacy_provider_payloads(
    *,
    binance_websocket_url: str,
    binance_receive_timeout_seconds: float,
    binance_initial_backoff_seconds: float,
    binance_max_backoff_seconds: float,
    binance_max_reconnect_attempts: int | None,
    alchemy_poll_interval_seconds: float,
    alchemy_request_timeout_seconds: float,
    alchemy_initial_backoff_seconds: float,
    alchemy_max_backoff_seconds: float,
    alchemy_max_retry_attempts: int | None,
    alchemy_degraded_after_failures: int,
    disable_eth_get_block_by_number: bool,
    alchemy_endpoint_url: str | None,
) -> list[dict[str, Any]]:
    return [
        binance_trade_provider_payload(
            symbol="BTCUSDT",
            websocket_url=binance_websocket_url,
            receive_timeout_seconds=binance_receive_timeout_seconds,
            initial_backoff_seconds=binance_initial_backoff_seconds,
            max_backoff_seconds=binance_max_backoff_seconds,
            max_reconnect_attempts=binance_max_reconnect_attempts,
        ),
        binance_trade_provider_payload(
            symbol="ETHUSDT",
            websocket_url=binance_websocket_url,
            receive_timeout_seconds=binance_receive_timeout_seconds,
            initial_backoff_seconds=binance_initial_backoff_seconds,
            max_backoff_seconds=binance_max_backoff_seconds,
            max_reconnect_attempts=binance_max_reconnect_attempts,
        ),
        alchemy_evm_block_provider_payload(
            symbol="ETH",
            network="eth-mainnet",
            provider_id=LEGACY_ALCHEMY_PROVIDER_ID,
            poll_interval_seconds=alchemy_poll_interval_seconds,
            request_timeout_seconds=alchemy_request_timeout_seconds,
            initial_backoff_seconds=alchemy_initial_backoff_seconds,
            max_backoff_seconds=alchemy_max_backoff_seconds,
            max_retry_attempts=alchemy_max_retry_attempts,
            degraded_after_failures=alchemy_degraded_after_failures,
            include_block_details=not disable_eth_get_block_by_number,
            endpoint_url=alchemy_endpoint_url,
        ),
    ]


def load_provider_payloads_from_config(path: str | Path) -> list[dict[str, Any]]:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        providers = payload.get("providers")
    else:
        providers = payload
    if not isinstance(providers, list):
        raise ValueError("provider config must define a 'providers' list or be a list itself")
    return [normalize_provider_payload(item) for item in providers]


def normalize_provider_payload(raw_provider: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_provider, dict):
        raise ValueError("provider config entries must be JSON objects")
    kind = _non_empty_string(raw_provider.get("kind"), field="kind")
    provider_id = _non_empty_string(raw_provider.get("provider_id"), field="provider_id")
    symbol = _non_empty_string(raw_provider.get("symbol"), field="symbol").upper()
    if kind == BINANCE_TRADE_PROVIDER_KIND:
        subject_key = _validate_subject_key(
            raw_provider.get("subject_key"),
            symbol=symbol,
            venue="binance",
            instrument_type="spot",
        )
        return {
            "kind": kind,
            "provider_id": provider_id,
            "subject_key": subject_key,
            "symbol": symbol,
            "websocket_url": _non_empty_string(
                raw_provider.get("websocket_url", "wss://stream.binance.com:9443/ws"),
                field="websocket_url",
            ),
            "receive_timeout_seconds": float(raw_provider.get("receive_timeout_seconds", 20.0)),
            "initial_backoff_seconds": float(raw_provider.get("initial_backoff_seconds", 1.0)),
            "max_backoff_seconds": float(raw_provider.get("max_backoff_seconds", 5.0)),
            "max_reconnect_attempts": _optional_int(raw_provider.get("max_reconnect_attempts")),
        }
    if kind == ALCHEMY_EVM_BLOCK_PROVIDER_KIND:
        subject_key = _validate_subject_key(
            raw_provider.get("subject_key"),
            symbol=symbol,
            venue="alchemy",
            instrument_type="onchain",
        )
        return {
            "kind": kind,
            "provider_id": provider_id,
            "subject_key": subject_key,
            "symbol": symbol,
            "network": _non_empty_string(raw_provider.get("network"), field="network"),
            "endpoint_url": _optional_string(raw_provider.get("endpoint_url")),
            "poll_interval_seconds": float(raw_provider.get("poll_interval_seconds", 5.0)),
            "request_timeout_seconds": float(raw_provider.get("request_timeout_seconds", 10.0)),
            "initial_backoff_seconds": float(raw_provider.get("initial_backoff_seconds", 1.0)),
            "max_backoff_seconds": float(raw_provider.get("max_backoff_seconds", 20.0)),
            "max_retry_attempts": _optional_int(raw_provider.get("max_retry_attempts", 5)),
            "degraded_after_failures": int(raw_provider.get("degraded_after_failures", 3)),
            "include_block_details": bool(raw_provider.get("include_block_details", True)),
        }
    if kind == ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND:
        subject_key = _validate_subject_key(
            raw_provider.get("subject_key"),
            symbol=symbol,
            venue="alchemy",
            instrument_type="onchain",
        )
        return {
            "kind": kind,
            "provider_id": provider_id,
            "subject_key": subject_key,
            "symbol": symbol,
            "network": _non_empty_string(raw_provider.get("network"), field="network"),
            "endpoint_url": _optional_string(raw_provider.get("endpoint_url")),
            "poll_interval_seconds": float(raw_provider.get("poll_interval_seconds", 5.0)),
            "request_timeout_seconds": float(raw_provider.get("request_timeout_seconds", 10.0)),
            "initial_backoff_seconds": float(raw_provider.get("initial_backoff_seconds", 1.0)),
            "max_backoff_seconds": float(raw_provider.get("max_backoff_seconds", 20.0)),
            "max_retry_attempts": _optional_int(raw_provider.get("max_retry_attempts", 5)),
            "degraded_after_failures": int(raw_provider.get("degraded_after_failures", 3)),
            "include_block_details": bool(raw_provider.get("include_block_details", True)),
        }
    if kind == ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND:
        subject_key = _validate_subject_key(
            raw_provider.get("subject_key"),
            symbol=symbol,
            venue="alchemy",
            instrument_type="onchain",
        )
        return {
            "kind": kind,
            "provider_id": provider_id,
            "subject_key": subject_key,
            "symbol": symbol,
            "network": _non_empty_string(raw_provider.get("network"), field="network"),
            "endpoint_url": _optional_string(raw_provider.get("endpoint_url")),
            "poll_interval_seconds": float(raw_provider.get("poll_interval_seconds", 5.0)),
            "request_timeout_seconds": float(raw_provider.get("request_timeout_seconds", 10.0)),
            "initial_backoff_seconds": float(raw_provider.get("initial_backoff_seconds", 1.0)),
            "max_backoff_seconds": float(raw_provider.get("max_backoff_seconds", 20.0)),
            "max_retry_attempts": _optional_int(raw_provider.get("max_retry_attempts", 5)),
            "degraded_after_failures": int(raw_provider.get("degraded_after_failures", 3)),
            "include_block_details": bool(raw_provider.get("include_block_details", True)),
            "commitment": _non_empty_string(raw_provider.get("commitment", "finalized"), field="commitment"),
            "encoding": _non_empty_string(raw_provider.get("encoding", "json"), field="encoding"),
            "transaction_details": _non_empty_string(
                raw_provider.get("transaction_details", "none"),
                field="transaction_details",
            ),
        }
    raise ValueError(f"unsupported shadow provider kind '{kind}'")


def alchemy_endpoint_url_for_network(
    network: str,
    endpoint_url: str | None = None,
    *,
    api_key_env_var: str = "ALCHEMY_API_KEY",
) -> str:
    if endpoint_url:
        return str(endpoint_url)
    api_key = os.getenv(api_key_env_var, "").strip()
    if not api_key:
        return f"https://{network}.g.alchemy.com/v2/<missing>"
    return f"https://{network}.g.alchemy.com/v2/{api_key}"


def provider_family(provider: dict[str, Any]) -> str:
    kind = provider.get("kind")
    if kind == BINANCE_TRADE_PROVIDER_KIND:
        return "binance"
    if kind in {
        ALCHEMY_EVM_BLOCK_PROVIDER_KIND,
        ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND,
        ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND,
    }:
        return "alchemy"
    raise ValueError(f"unsupported provider family for kind '{kind}'")


def provider_identity(provider: dict[str, Any]) -> str:
    return str(provider.get("subject_key") or provider.get("provider_id") or "unknown")


def provider_subject_keys(providers: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(provider["subject_key"]) for provider in providers)


def binance_socket_symbols(providers: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        str(provider["symbol"]).upper()
        for provider in providers
        if provider.get("kind") == BINANCE_TRADE_PROVIDER_KIND
    )


def group_providers_by_family(providers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"binance": [], "alchemy": []}
    for provider in providers:
        grouped[provider_family(provider)].append(provider)
    return grouped


def _validate_subject_key(
    value: object,
    *,
    symbol: str,
    venue: str,
    instrument_type: str,
) -> str:
    expected = _expected_subject_key(
        symbol=symbol,
        venue=venue,
        instrument_type=instrument_type,
    )
    observed = _non_empty_string(value, field="subject_key")
    if observed != expected:
        raise ValueError(
            "subject_key does not match the canonical stable string for the provider config: "
            f"expected '{expected}', observed '{observed}'"
        )
    return observed


def _expected_subject_key(*, symbol: str, venue: str, instrument_type: str) -> str:
    return SubjectKey.build(
        symbol=symbol,
        venue=venue,
        instrument_type=instrument_type,
    ).as_stable_string()


def _optional_string(value: object) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        raise ValueError("integer field cannot be boolean")
    return int(value)


def _non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()
