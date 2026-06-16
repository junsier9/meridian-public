from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_SPOT_MAINNET_BASE_URL,
    BINANCE_USDM_MAINNET_BASE_URL,
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmClient,
)
from enhengclaw.live_trading.config import DEFAULT_LIVE_CONFIG_PATH, load_live_trading_config
from enhengclaw.live_trading.market_data import parse_symbol_exchange_filters, resolve_config_symbols
from enhengclaw.quant_research.contracts import write_json


READ_ONLY_ENDPOINTS = {
    "account_information_v3": "/fapi/v3/account",
    "account_config": "/fapi/v1/accountConfig",
    "position_mode": "/fapi/v1/positionSide/dual",
    "open_orders": "/fapi/v1/openOrders",
    "exchange_info": "/fapi/v1/exchangeInfo",
}
API_KEY_PERMISSION_ENDPOINT = "/sapi/v1/account/apiRestrictions"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only signed Binance USD-M account probe; checks API access, permissions, position mode, and symbol rules."
    )
    parser.add_argument("--config", default=str(DEFAULT_LIVE_CONFIG_PATH))
    parser.add_argument("--environment", default="mainnet", choices=("mainnet", "testnet"))
    parser.add_argument("--api-key-env", default="", help="Override API key environment variable name.")
    parser.add_argument("--api-secret-env", default="", help="Override API secret environment variable name.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols to inspect; defaults to live config symbols.")
    parser.add_argument("--max-symbols", type=int, default=20, help="Maximum symbols to include in min-order rule summary.")
    args = parser.parse_args(argv)
    summary, exit_code = run_read_only_account_probe(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_read_only_account_probe(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", DEFAULT_LIVE_CONFIG_PATH))
    environment = str(getattr(args, "environment", "mainnet") or "mainnet").strip().lower()
    base_url = _base_url_for_environment(environment)
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-account-probe-{environment}"
    run_root = live_config.artifact_root.parent / "account_probe" / run_id
    credential_context = _credential_context(
        payload=live_config.payload,
        args=args,
        env=env or os.environ,
    )
    symbols = resolve_config_symbols(
        live_config.payload,
        override_symbols=str(getattr(args, "symbols", "") or "").strip() or None,
    )[: max(int(getattr(args, "max_symbols", 20) or 20), 1)]
    request_context = {
        "run_id": run_id,
        "environment": environment,
        "base_url": base_url,
        "read_only": True,
        "symbols": symbols,
        "endpoint_paths": {
            **READ_ONLY_ENDPOINTS,
            **({"api_key_permissions": API_KEY_PERMISSION_ENDPOINT} if environment == "mainnet" else {}),
        },
        "api_key_env": credential_context["api_key_env"],
        "api_secret_env": credential_context["api_secret_env"],
        "api_key_present": credential_context["api_key_present"],
        "api_secret_present": credential_context["api_secret_present"],
        "api_key_length": credential_context["api_key_length"],
        "api_secret_length": credential_context["api_secret_length"],
        "forbidden_methods": ["new_order", "new_order_test", "cancel_order"],
    }
    blockers = list(credential_context["blockers"])
    if blockers:
        result = _empty_probe_result(
            environment=environment,
            base_url=base_url,
            symbols=symbols,
            blockers=blockers,
        )
        summary = _summary(
            run_id=run_id,
            environment=environment,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            account_readable=False,
            can_trade=None,
            position_mode=None,
        )
        _persist_probe_artifacts(run_root, request_context=request_context, result=result, summary=summary)
        return summary, 2

    client = client_factory(
        base_url=base_url,
        api_key=credential_context["api_key"],
        api_secret=credential_context["api_secret"],
        recv_window_ms=credential_context["recv_window_ms"],
        timeout_seconds=credential_context["timeout_seconds"],
    )
    endpoint_results: dict[str, dict[str, Any]] = {}
    expected_endpoints = set(READ_ONLY_ENDPOINTS)
    account_payload = _safe_endpoint_call(endpoint_results, "account_information_v3", client.account_information_v3)
    config_payload = _safe_endpoint_call(endpoint_results, "account_config", client.account_config)
    position_payload = _safe_endpoint_call(endpoint_results, "position_mode", client.position_mode)
    open_orders_payload = _safe_endpoint_call(endpoint_results, "open_orders", client.current_all_open_orders)
    exchange_payload = _safe_endpoint_call(endpoint_results, "exchange_info", client.exchange_info)
    api_key_permissions_payload = None
    if environment == "mainnet":
        expected_endpoints.add("api_key_permissions")
        permissions_client = client_factory(
            base_url=BINANCE_SPOT_MAINNET_BASE_URL,
            api_key=credential_context["api_key"],
            api_secret=credential_context["api_secret"],
            recv_window_ms=credential_context["recv_window_ms"],
            timeout_seconds=credential_context["timeout_seconds"],
        )
        api_key_permissions_payload = _safe_endpoint_call(
            endpoint_results,
            "api_key_permissions",
            permissions_client.api_key_restrictions,
            endpoint_path=API_KEY_PERMISSION_ENDPOINT,
            base_url=BINANCE_SPOT_MAINNET_BASE_URL,
        )

    blockers.extend(_endpoint_blockers(endpoint_results, expected_names=expected_endpoints))
    account_summary = _summarize_account(account_payload)
    open_orders_summary = _summarize_open_orders(open_orders_payload)
    permissions = _summarize_permissions(config_payload)
    api_key_permissions = _summarize_api_key_permissions(api_key_permissions_payload)
    position_mode = _summarize_position_mode(position_payload, config_payload)
    min_order_rules, rule_blockers = _min_order_rules(exchange_payload, symbols=symbols)
    blockers.extend(rule_blockers)
    blockers.extend(_account_state_blockers(account_summary, open_orders_summary))
    blockers.extend(_api_key_permission_blockers(api_key_permissions, require_mainnet=environment == "mainnet"))
    blockers.extend(_semantic_blockers(live_config.payload, permissions=permissions, position_mode=position_mode))
    status = "passed_read_only_account_probe" if not blockers else "blocked"
    result = {
        "status": status,
        "environment": environment,
        "base_url": base_url,
        "read_only": True,
        "credential_probe": {
            "api_key_env": credential_context["api_key_env"],
            "api_secret_env": credential_context["api_secret_env"],
            "api_key_present": credential_context["api_key_present"],
            "api_secret_present": credential_context["api_secret_present"],
            "api_key_length": credential_context["api_key_length"],
            "api_secret_length": credential_context["api_secret_length"],
        },
        "endpoint_results": endpoint_results,
        "account": account_summary,
        "open_orders": open_orders_summary,
        "permissions": permissions,
        "api_key_permissions": api_key_permissions,
        "position_mode": position_mode,
        "min_order_rules": min_order_rules,
        "blockers": sorted(set(blockers)),
        "ip_whitelist_boundary": {
            "signed_read_only_endpoints_accepted_current_host": not any(
                str(item).startswith("read_only_endpoint_failed:") for item in blockers
            ),
            "ip_restrict": api_key_permissions.get("ip_restrict"),
            "api_whitelist_entries_readable": False,
            "operator_ui_verification_required": True,
        },
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }
    summary = _summary(
        run_id=run_id,
        environment=environment,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
        account_readable=account_summary["account_readable"],
        can_trade=permissions.get("can_trade"),
        position_mode=position_mode.get("mode"),
        open_order_count=open_orders_summary["open_order_count"],
        open_position_count=account_summary["open_position_count"],
        api_key_enable_reading=api_key_permissions.get("enable_reading"),
        api_key_enable_futures=api_key_permissions.get("enable_futures"),
        api_key_enable_withdrawals=api_key_permissions.get("enable_withdrawals"),
        api_key_ip_restrict=api_key_permissions.get("ip_restrict"),
    )
    _persist_probe_artifacts(run_root, request_context=request_context, result=result, summary=summary)
    return summary, 0 if status == "passed_read_only_account_probe" else 2


def _base_url_for_environment(environment: str) -> str:
    if environment == "mainnet":
        return BINANCE_USDM_MAINNET_BASE_URL
    if environment == "testnet":
        return BINANCE_USDM_TESTNET_BASE_URL
    raise ValueError(f"unsupported Binance USD-M environment: {environment}")


def _credential_context(
    *,
    payload: dict[str, Any],
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(getattr(args, "api_key_env", "") or binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_API_KEY").strip()
    api_secret_env = str(
        getattr(args, "api_secret_env", "") or binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_API_SECRET"
    ).strip()
    api_key = str(getenv_compat(api_key_env, "", env=env) or "").strip()
    api_secret = str(getenv_compat(api_secret_env, "", env=env) or "").strip()
    blockers: list[str] = []
    if not api_key:
        blockers.append(f"missing_api_key_env:{api_key_env}")
    if not api_secret:
        blockers.append(f"missing_api_secret_env:{api_secret_env}")
    return {
        "api_key_env": api_key_env,
        "api_secret_env": api_secret_env,
        "api_key": api_key,
        "api_secret": api_secret,
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "api_key_length": len(api_key),
        "api_secret_length": len(api_secret),
        "recv_window_ms": int(binance.get("recv_window_ms") or 5000),
        "timeout_seconds": float(binance.get("timeout_seconds") or 10.0),
        "blockers": blockers,
    }


def _safe_endpoint_call(
    endpoint_results: dict[str, dict[str, Any]],
    name: str,
    fn: Callable[[], Any],
    *,
    endpoint_path: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any] | None:
    path = endpoint_path or READ_ONLY_ENDPOINTS[name]
    try:
        response = fn()
    except Exception as exc:
        endpoint_results[name] = {
            "path": path,
            "base_url": base_url,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        return None
    payload = response.payload
    endpoint_results[name] = {
        "path": path,
        "base_url": base_url,
        "status": "ok",
        "status_code": int(getattr(response, "status_code", 200)),
    }
    return dict(payload) if isinstance(payload, dict) else {"payload": payload}


def _endpoint_blockers(endpoint_results: dict[str, dict[str, Any]], *, expected_names: set[str] | None = None) -> list[str]:
    blockers: list[str] = []
    for name, result in sorted(endpoint_results.items()):
        if result.get("status") != "ok":
            blockers.append(f"read_only_endpoint_failed:{name}:{result.get('error_type')}:{result.get('error')}")
    missing = sorted(set(expected_names or set(READ_ONLY_ENDPOINTS)) - set(endpoint_results))
    blockers.extend(f"read_only_endpoint_not_called:{name}" for name in missing)
    return blockers


def _summarize_account(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "account_readable": False,
            "asset_count": 0,
            "position_count": 0,
            "open_position_count": 0,
            "assets_with_wallet_balance_count": 0,
        }
    positions = [dict(item) for item in list(payload.get("positions") or []) if isinstance(item, dict)]
    assets = [dict(item) for item in list(payload.get("assets") or []) if isinstance(item, dict)]
    return {
        "account_readable": True,
        "asset_count": len(assets),
        "position_count": len(positions),
        "open_position_count": sum(1 for item in positions if abs(_float(item.get("positionAmt"))) > 0.0),
        "assets_with_wallet_balance_count": sum(1 for item in assets if abs(_float(item.get("walletBalance"))) > 0.0),
        "available_balance_present": "availableBalance" in payload,
        "total_wallet_balance_present": "totalWalletBalance" in payload,
    }


def _summarize_open_orders(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "open_orders_readable": False,
            "open_order_count": 0,
            "open_orders_redacted": [],
        }
    rows = payload.get("payload") if "payload" in payload else []
    orders = [dict(item) for item in list(rows or []) if isinstance(item, dict)]
    return {
        "open_orders_readable": True,
        "open_order_count": len(orders),
        "open_orders_redacted": [
            {
                "symbol": str(item.get("symbol") or ""),
                "orderId": item.get("orderId"),
                "clientOrderId": str(item.get("clientOrderId") or ""),
                "side": str(item.get("side") or ""),
                "type": str(item.get("type") or ""),
                "status": str(item.get("status") or ""),
                "origQty": str(item.get("origQty") or ""),
                "executedQty": str(item.get("executedQty") or ""),
                "reduceOnly": bool(item.get("reduceOnly", False)),
            }
            for item in orders
        ],
    }


def _summarize_permissions(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    return {
        "account_config_readable": bool(payload),
        "can_trade": _optional_bool(payload.get("canTrade")),
        "can_deposit": _optional_bool(payload.get("canDeposit")),
        "can_withdraw": _optional_bool(payload.get("canWithdraw")),
        "multi_assets_margin": _optional_bool(payload.get("multiAssetsMargin")),
        "fee_tier": payload.get("feeTier"),
        "trade_group_id": payload.get("tradeGroupId"),
    }


def _summarize_api_key_permissions(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    return {
        "api_key_permissions_readable": bool(payload),
        "ip_restrict": _optional_bool(payload.get("ipRestrict")),
        "enable_reading": _optional_bool(payload.get("enableReading")),
        "enable_withdrawals": _optional_bool(payload.get("enableWithdrawals")),
        "enable_internal_transfer": _optional_bool(payload.get("enableInternalTransfer")),
        "enable_margin": _optional_bool(payload.get("enableMargin")),
        "enable_futures": _optional_bool(payload.get("enableFutures")),
        "permits_universal_transfer": _optional_bool(payload.get("permitsUniversalTransfer")),
        "enable_spot_and_margin_trading": _optional_bool(payload.get("enableSpotAndMarginTrading")),
        "enable_portfolio_margin_trading": _optional_bool(payload.get("enablePortfolioMarginTrading")),
        "trading_authority_expiration_time": payload.get("tradingAuthorityExpirationTime"),
        "create_time": payload.get("createTime"),
    }


def _summarize_position_mode(
    position_payload: dict[str, Any] | None,
    config_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(position_payload or {})
    fallback = dict(config_payload or {})
    dual = _optional_bool(payload.get("dualSidePosition"))
    if dual is None:
        dual = _optional_bool(fallback.get("dualSidePosition"))
    mode = None
    if dual is not None:
        mode = "hedge" if dual else "one_way"
    return {
        "position_mode_readable": bool(position_payload),
        "dual_side_position": dual,
        "mode": mode,
    }


def _min_order_rules(
    exchange_payload: dict[str, Any] | None,
    *,
    symbols: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not exchange_payload:
        return {}, ["exchange_info_unavailable_for_min_order_rules"]
    parsed = parse_symbol_exchange_filters(exchange_payload)
    rules: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for symbol in symbols:
        item = parsed.get(symbol)
        if item is None:
            blockers.append(f"symbol_missing_from_exchange_info:{symbol}")
            continue
        rules[symbol] = {
            **item.to_dict(),
            "tradable_usdm_perp": item.tradable_usdm_perp,
        }
        if not item.tradable_usdm_perp:
            blockers.append(f"symbol_not_tradable_usdm_perp:{symbol}")
        if item.min_qty <= 0.0:
            blockers.append(f"missing_min_qty:{symbol}")
        if item.step_size <= 0.0:
            blockers.append(f"missing_step_size:{symbol}")
        if item.min_notional <= 0.0:
            blockers.append(f"missing_min_notional:{symbol}")
    return rules, blockers


def _account_state_blockers(account_summary: dict[str, Any], open_orders_summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    open_orders = int(open_orders_summary.get("open_order_count") or 0)
    open_positions = int(account_summary.get("open_position_count") or 0)
    if open_orders > 0:
        blockers.append(f"mainnet_open_orders_exist:{open_orders}")
    if open_positions > 0:
        blockers.append(f"mainnet_open_positions_exist:{open_positions}")
    return blockers


def _api_key_permission_blockers(api_key_permissions: dict[str, Any], *, require_mainnet: bool) -> list[str]:
    if not require_mainnet:
        return []
    blockers: list[str] = []
    if not bool(api_key_permissions.get("api_key_permissions_readable")):
        blockers.append("api_key_permissions_unreadable")
        return blockers
    if api_key_permissions.get("enable_reading") is not True:
        blockers.append(f"api_key_enableReading_not_true:{api_key_permissions.get('enable_reading')}")
    if api_key_permissions.get("enable_futures") is not True:
        blockers.append(f"api_key_enableFutures_not_true:{api_key_permissions.get('enable_futures')}")
    if api_key_permissions.get("enable_withdrawals") is not False:
        blockers.append(f"api_key_enableWithdrawals_not_false:{api_key_permissions.get('enable_withdrawals')}")
    if api_key_permissions.get("ip_restrict") is not True:
        blockers.append(f"api_key_ipRestrict_not_true:{api_key_permissions.get('ip_restrict')}")
    return blockers


def _semantic_blockers(
    payload: dict[str, Any],
    *,
    permissions: dict[str, Any],
    position_mode: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if permissions.get("can_trade") is not True:
        blockers.append(f"account_config_canTrade_not_true:{permissions.get('can_trade')}")
    expected = _normalize_position_mode(dict(payload.get("binance") or {}).get("position_mode"))
    actual = _normalize_position_mode(position_mode.get("mode"))
    if expected and actual and expected != actual:
        blockers.append(f"position_mode_mismatch:expected={expected}:actual={actual}")
    if expected and actual is None:
        blockers.append(f"position_mode_unreadable:expected={expected}")
    return blockers


def _empty_probe_result(
    *,
    environment: str,
    base_url: str,
    symbols: list[str],
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "environment": environment,
        "base_url": base_url,
        "read_only": True,
        "symbols": symbols,
        "endpoint_results": {},
        "blockers": sorted(set(blockers)),
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }


def _summary(
    *,
    run_id: str,
    environment: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    account_readable: bool,
    can_trade: bool | None,
    position_mode: str | None,
    open_order_count: int = 0,
    open_position_count: int = 0,
    api_key_enable_reading: bool | None = None,
    api_key_enable_futures: bool | None = None,
    api_key_enable_withdrawals: bool | None = None,
    api_key_ip_restrict: bool | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "environment": environment,
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "account_readable": account_readable,
        "can_trade": can_trade,
        "position_mode": position_mode,
        "open_order_count": int(open_order_count),
        "open_position_count": int(open_position_count),
        "api_key_enable_reading": api_key_enable_reading,
        "api_key_enable_futures": api_key_enable_futures,
        "api_key_enable_withdrawals": api_key_enable_withdrawals,
        "api_key_ip_restrict": api_key_ip_restrict,
        "artifact_root": str(artifact_root),
        "read_only": True,
    }


def _persist_probe_artifacts(
    run_root: Path,
    *,
    request_context: dict[str, Any],
    result: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    write_json(run_root / "request_context.json", request_context)
    write_json(run_root / "account_probe_result.json", result)
    write_json(run_root / "run_summary.json", summary)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    if value in {0, 1}:
        return bool(value)
    return None


def _normalize_position_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"oneway", "one_way", "single", "both"}:
        return "one_way"
    if normalized in {"hedge", "hedge_mode", "dual"}:
        return "hedge"
    return normalized


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
