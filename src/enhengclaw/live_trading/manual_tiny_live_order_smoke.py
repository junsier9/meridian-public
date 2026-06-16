from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmClient,
    BinanceUsdmUnknownExecutionStatus,
)
from enhengclaw.live_trading.config import DEFAULT_LIVE_CONFIG_PATH, load_live_trading_config
from enhengclaw.live_trading.market_data import parse_symbol_exchange_filters
from enhengclaw.live_trading.order_router import (
    BinanceOrderSnapshot,
    parse_order_snapshot,
    query_order_by_client_id,
    recover_unknown_order_status,
)
from enhengclaw.quant_research.contracts import write_json


DEFAULT_MAX_NOTIONAL_USDT = Decimal("60")
CLIENT_ORDER_ID_ALLOWED = set(".ABCDEFGHIJKLMNOPQRSTUVWXYZ:/abcdefghijklmnopqrstuvwxyz0123456789_-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manual tiny live Binance USD-M order smoke runner. "
            "It is mainnet-only, operator-parameterized, and opens then reduce-only closes one MARKET order."
        )
    )
    parser.add_argument("--config", default=str(DEFAULT_LIVE_CONFIG_PATH))
    parser.add_argument("--api-key-env", default="", help="Override API key environment variable name.")
    parser.add_argument("--api-secret-env", default="", help="Override API secret environment variable name.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", required=True, choices=("BUY", "SELL"))
    parser.add_argument("--notional-usdt", required=True)
    parser.add_argument("--max-notional-usdt", default=str(DEFAULT_MAX_NOTIONAL_USDT))
    parser.add_argument("--client-order-id", default="")
    parser.add_argument("--execute", action="store_true", help="Actually submit live mainnet entry and reduce-only close orders.")
    parser.add_argument("--i-understand-this-places-a-real-mainnet-order", action="store_true")
    parser.add_argument(
        "--confirm-risk",
        default="",
        help="Must exactly match the required confirmation string printed by dry-run.",
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_manual_tiny_live_order_smoke(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_manual_tiny_live_order_smoke(
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
    symbol = str(getattr(args, "symbol", "") or "").strip().upper()
    side = str(getattr(args, "side", "") or "").strip().upper()
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-manual-live-order-smoke-{symbol or 'UNKNOWN'}"
    run_root = live_config.artifact_root.parent / "manual_live_order_smoke" / run_id
    credentials = _credential_context(live_config.payload, args=args, env=env or os.environ)
    request_context = {
        "run_id": run_id,
        "environment": "mainnet",
        "base_url": BINANCE_USDM_MAINNET_BASE_URL,
        "manual_only": True,
        "strategy_order_generation": "disabled",
        "smoke_shape": "open_then_reduce_only_close",
        "symbol": symbol,
        "side": side,
        "api_key_env": credentials["api_key_env"],
        "api_secret_env": credentials["api_secret_env"],
        "api_key_present": credentials["api_key_present"],
        "api_secret_present": credentials["api_secret_present"],
        "api_key_length": credentials["api_key_length"],
        "api_secret_length": credentials["api_secret_length"],
    }
    blockers = _basic_blockers(args=args, symbol=symbol, side=side, credentials=credentials)
    result: dict[str, Any] = {
        "status": "blocked",
        "request": {key: value for key, value in request_context.items() if key not in {"api_key_length", "api_secret_length"}},
        "blockers": blockers,
        "side_effects": {"entry_orders_submitted": 0, "close_orders_submitted": 0, "orders_canceled": 0},
    }
    if blockers:
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            symbol=symbol,
            side=side,
            executed=False,
        )
        _persist(run_root, request_context=request_context, result=result, summary=summary)
        return summary, 2

    client = client_factory(
        base_url=BINANCE_USDM_MAINNET_BASE_URL,
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        recv_window_ms=credentials["recv_window_ms"],
        timeout_seconds=credentials["timeout_seconds"],
    )
    preflight = _preflight(client=client, payload=live_config.payload, symbol=symbol)
    order_plan, plan_blockers = _build_order_plan(
        args=args,
        symbol=symbol,
        side=side,
        preflight=preflight,
        started=started,
    )
    blockers.extend(preflight["blockers"])
    blockers.extend(plan_blockers)
    required_confirmation = order_plan.get("required_confirmation")
    result.update(
        {
            "status": "dry_run_preflight_passed" if not blockers else "blocked",
            "preflight": preflight,
            "order_plan": order_plan,
            "blockers": sorted(set(blockers)),
        }
    )
    execute = bool(getattr(args, "execute", False))
    if not execute:
        summary = _summary(
            run_id=run_id,
            status="dry_run_preflight_passed" if not blockers else "blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            symbol=symbol,
            side=side,
            executed=False,
            required_confirmation=required_confirmation,
        )
        _persist(run_root, request_context=request_context, result=result, summary=summary)
        return summary, 0 if not blockers else 2

    blockers.extend(_execution_confirmation_blockers(args=args, required_confirmation=str(required_confirmation or "")))
    if blockers:
        result["status"] = "blocked"
        result["blockers"] = sorted(set(blockers))
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
            symbol=symbol,
            side=side,
            executed=False,
            required_confirmation=required_confirmation,
        )
        _persist(run_root, request_context=request_context, result=result, summary=summary)
        return summary, 2

    execution_result = _execute_open_close_smoke(client=client, order_plan=order_plan, symbol=symbol)
    final_check = _final_position_check(client=client, symbol=symbol)
    final_blockers = [*execution_result["blockers"], *final_check["blockers"]]
    status = "manual_live_order_smoke_completed" if not final_blockers else "manual_live_order_smoke_needs_reconcile"
    result.update(
        {
            "status": status,
            "execution": execution_result,
            "final_check": final_check,
            "blockers": sorted(set(final_blockers)),
            "side_effects": execution_result["side_effects"],
        }
    )
    summary = _summary(
        run_id=run_id,
        status=status,
        blockers=final_blockers,
        started_at=started,
        artifact_root=run_root,
        symbol=symbol,
        side=side,
        executed=True,
        required_confirmation=required_confirmation,
        entry_client_order_id=order_plan.get("entry_client_order_id"),
        close_client_order_id=order_plan.get("close_client_order_id"),
    )
    _persist(run_root, request_context=request_context, result=result, summary=summary)
    return summary, 0 if status == "manual_live_order_smoke_completed" else 2


def _credential_context(payload: dict[str, Any], *, args: argparse.Namespace, env: Mapping[str, str]) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(getattr(args, "api_key_env", "") or binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_API_KEY").strip()
    api_secret_env = str(
        getattr(args, "api_secret_env", "") or binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_API_SECRET"
    ).strip()
    api_key = str(getenv_compat(api_key_env, "", env=env) or "").strip()
    api_secret = str(getenv_compat(api_secret_env, "", env=env) or "").strip()
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
    }


def _basic_blockers(
    *,
    args: argparse.Namespace,
    symbol: str,
    side: str,
    credentials: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not credentials["api_key"]:
        blockers.append(f"missing_api_key_env:{credentials['api_key_env']}")
    if not credentials["api_secret"]:
        blockers.append(f"missing_api_secret_env:{credentials['api_secret_env']}")
    if not symbol:
        blockers.append("manual_live_smoke_requires_symbol")
    if side not in {"BUY", "SELL"}:
        blockers.append(f"manual_live_smoke_invalid_side:{side}")
    for field_name in ("notional_usdt", "max_notional_usdt"):
        try:
            value = _decimal(getattr(args, field_name))
        except ValueError as exc:
            blockers.append(f"invalid_{field_name}:{exc}")
            continue
        if value <= 0:
            blockers.append(f"{field_name}_must_be_positive")
    return blockers


def _preflight(*, client: Any, payload: dict[str, Any], symbol: str) -> dict[str, Any]:
    blockers: list[str] = []
    account = dict(client.account_information_v3().payload)
    account_config = dict(client.account_config().payload)
    position_mode_payload = dict(client.position_mode().payload)
    exchange_info = dict(client.exchange_info().payload)
    premium_index = dict(client.premium_index(symbol=symbol).payload)
    open_orders = [dict(item) for item in list(client.current_all_open_orders().payload or []) if isinstance(item, dict)]
    open_positions = _open_positions(account)
    can_trade = _optional_bool(account_config.get("canTrade"))
    dual_side = _optional_bool(position_mode_payload.get("dualSidePosition"))
    mode = "hedge" if dual_side else "one_way" if dual_side is False else None
    expected_mode = str(dict(payload.get("binance") or {}).get("position_mode") or "one_way").strip().lower()
    if can_trade is not True:
        blockers.append(f"account_config_canTrade_not_true:{can_trade}")
    if mode != "one_way" or expected_mode != "one_way":
        blockers.append(f"position_mode_not_one_way:expected={expected_mode}:actual={mode}")
    if open_positions:
        blockers.append(f"open_positions_exist:{len(open_positions)}")
    if open_orders:
        blockers.append(f"open_orders_exist:{len(open_orders)}")
    return {
        "account_readable": True,
        "can_trade": can_trade,
        "position_mode": mode,
        "dual_side_position": dual_side,
        "open_position_count": len(open_positions),
        "open_order_count": len(open_orders),
        "open_positions_redacted": open_positions,
        "open_orders_redacted": _redacted_open_orders(open_orders),
        "exchange_info": exchange_info,
        "premium_index": {
            "symbol": premium_index.get("symbol"),
            "markPrice": premium_index.get("markPrice"),
            "indexPrice": premium_index.get("indexPrice"),
            "lastFundingRate": premium_index.get("lastFundingRate"),
        },
        "blockers": blockers,
    }


def _build_order_plan(
    *,
    args: argparse.Namespace,
    symbol: str,
    side: str,
    preflight: dict[str, Any],
    started: datetime,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    requested_notional = _decimal(getattr(args, "notional_usdt"))
    max_notional = _decimal(getattr(args, "max_notional_usdt"))
    mark_price = _decimal(preflight["premium_index"].get("markPrice") or preflight["premium_index"].get("indexPrice"))
    if mark_price <= 0:
        blockers.append("mark_price_unavailable_or_non_positive")
        mark_price = Decimal("0")
    filters = parse_symbol_exchange_filters(dict(preflight.get("exchange_info") or {}))
    symbol_filter = filters.get(symbol)
    if symbol_filter is None:
        blockers.append(f"symbol_missing_from_exchange_info:{symbol}")
        step_size = Decimal("0")
        min_qty = Decimal("0")
        min_notional = Decimal("0")
    else:
        if not symbol_filter.tradable_usdm_perp:
            blockers.append(f"symbol_not_tradable_usdm_perp:{symbol}")
        step_size = _decimal(symbol_filter.step_size)
        min_qty = _decimal(symbol_filter.min_qty)
        min_notional = _decimal(symbol_filter.min_notional)
    if step_size <= 0:
        blockers.append(f"missing_step_size:{symbol}")
    if min_qty <= 0:
        blockers.append(f"missing_min_qty:{symbol}")
    if min_notional <= 0:
        blockers.append(f"missing_min_notional:{symbol}")
    raw_qty = Decimal("0") if mark_price <= 0 else requested_notional / mark_price
    min_notional_qty = Decimal("0") if mark_price <= 0 else min_notional / mark_price
    quantity = _ceil_to_step(max(raw_qty, min_qty, min_notional_qty), step_size) if step_size > 0 else Decimal("0")
    estimated_notional = quantity * mark_price
    if requested_notional > max_notional:
        blockers.append(f"requested_notional_exceeds_max:{requested_notional}>{max_notional}")
    if estimated_notional > max_notional:
        blockers.append(f"estimated_notional_exceeds_max:{_fmt_decimal(estimated_notional)}>{_fmt_decimal(max_notional)}")
    client_order_id = str(getattr(args, "client_order_id", "") or "").strip() or _default_client_order_id(started, symbol, side)
    close_client_order_id = f"{client_order_id}-c"
    blockers.extend(_client_order_id_blockers(client_order_id, field_name="client_order_id"))
    blockers.extend(_client_order_id_blockers(close_client_order_id, field_name="close_client_order_id"))
    quantity_str = _fmt_decimal(quantity)
    confirmation = _confirmation_string(
        symbol=symbol,
        side=side,
        quantity=quantity_str,
        max_notional=_fmt_decimal(max_notional),
    )
    return (
        {
            "symbol": symbol,
            "side": side,
            "close_side": "SELL" if side == "BUY" else "BUY",
            "requested_notional_usdt": _fmt_decimal(requested_notional),
            "max_notional_usdt": _fmt_decimal(max_notional),
            "mark_price": _fmt_decimal(mark_price),
            "quantity": quantity_str,
            "estimated_notional_usdt": _fmt_decimal(estimated_notional),
            "min_qty": _fmt_decimal(min_qty),
            "step_size": _fmt_decimal(step_size),
            "min_notional": _fmt_decimal(min_notional),
            "entry_client_order_id": client_order_id,
            "close_client_order_id": close_client_order_id,
            "required_confirmation": confirmation,
            "order_type": "MARKET",
            "position_side": "BOTH",
            "new_order_resp_type": "RESULT",
        },
        blockers,
    )


def _confirmation_string(*, symbol: str, side: str, quantity: str, max_notional: str) -> str:
    return f"LIVE_MANUAL_SMOKE:{symbol}:{side}:QTY={quantity}:MAX_NOTIONAL={max_notional}:ONE_WAY"


def _execution_confirmation_blockers(*, args: argparse.Namespace, required_confirmation: str) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "i_understand_this_places_a_real_mainnet_order", False)):
        blockers.append("missing_live_order_understanding_flag")
    supplied = str(getattr(args, "confirm_risk", "") or "").strip()
    if supplied != required_confirmation:
        blockers.append("confirm_risk_mismatch")
    return blockers


def _execute_open_close_smoke(*, client: Any, order_plan: dict[str, Any], symbol: str) -> dict[str, Any]:
    blockers: list[str] = []
    side_effects = {"entry_orders_submitted": 0, "close_orders_submitted": 0, "orders_canceled": 0}
    entry_snapshot: dict[str, Any] | None = None
    close_snapshot: dict[str, Any] | None = None
    try:
        entry_snapshot = _submit_or_recover_order(
            client=client,
            params={
                "symbol": symbol,
                "side": order_plan["side"],
                "positionSide": "BOTH",
                "type": "MARKET",
                "quantity": order_plan["quantity"],
                "reduceOnly": "false",
                "newClientOrderId": order_plan["entry_client_order_id"],
                "newOrderRespType": "RESULT",
            },
            client_order_id=order_plan["entry_client_order_id"],
            symbol=symbol,
            side_effects=side_effects,
            side_effect_key="entry_orders_submitted",
        )
        filled_qty = _decimal(entry_snapshot.get("executed_quantity") or 0)
        if filled_qty <= 0:
            blockers.append("entry_order_not_filled_no_close_submitted")
        else:
            close_snapshot = _submit_or_recover_order(
                client=client,
                params={
                    "symbol": symbol,
                    "side": order_plan["close_side"],
                    "positionSide": "BOTH",
                    "type": "MARKET",
                    "quantity": _fmt_decimal(filled_qty),
                    "reduceOnly": "true",
                    "newClientOrderId": order_plan["close_client_order_id"],
                    "newOrderRespType": "RESULT",
                },
                client_order_id=order_plan["close_client_order_id"],
                symbol=symbol,
                side_effects=side_effects,
                side_effect_key="close_orders_submitted",
            )
            if _decimal(close_snapshot.get("executed_quantity") or 0) <= 0:
                blockers.append("close_order_not_filled_reconcile_required")
    except Exception as exc:
        blockers.append(f"manual_live_order_smoke_failed:{type(exc).__name__}:{exc}")
    return {
        "entry_order": entry_snapshot,
        "close_order": close_snapshot,
        "blockers": blockers,
        "side_effects": side_effects,
    }


def _submit_or_recover_order(
    *,
    client: Any,
    params: dict[str, Any],
    client_order_id: str,
    symbol: str,
    side_effects: dict[str, int],
    side_effect_key: str,
) -> dict[str, Any]:
    try:
        response = client.submit_manual_live_order_smoke(**params)
        side_effects[side_effect_key] += 1
        snapshot = parse_order_snapshot(dict(response.payload))
    except BinanceUsdmUnknownExecutionStatus:
        side_effects[side_effect_key] += 1
        recovery = recover_unknown_order_status(client, symbol=symbol, client_order_id=client_order_id)
        if recovery.status != "resolved":
            raise RuntimeError(f"unknown_status_recovery_failed:{recovery.to_dict()}")
        return {
            **recovery.to_dict(),
            "status": recovery.order_status,
            "executed_quantity": recovery.filled_quantity or 0.0,
            "unknown_status_recovered": True,
        }
    queried = query_order_by_client_id(client, symbol=symbol, client_order_id=client_order_id)
    if queried.executed_quantity >= snapshot.executed_quantity:
        snapshot = queried
    return snapshot.to_dict()


def _final_position_check(*, client: Any, symbol: str) -> dict[str, Any]:
    blockers: list[str] = []
    account = dict(client.account_information_v3().payload)
    open_orders = [dict(item) for item in list(client.current_all_open_orders().payload or []) if isinstance(item, dict)]
    positions = _open_positions(account)
    symbol_positions = [item for item in positions if item["symbol"] == symbol]
    symbol_open_orders = [item for item in open_orders if str(item.get("symbol") or "").upper() == symbol]
    if symbol_positions:
        blockers.append(f"residual_symbol_position_exists:{symbol}:{len(symbol_positions)}")
    if symbol_open_orders:
        blockers.append(f"residual_symbol_open_orders_exist:{symbol}:{len(symbol_open_orders)}")
    return {
        "symbol": symbol,
        "symbol_open_position_count": len(symbol_positions),
        "symbol_open_order_count": len(symbol_open_orders),
        "open_positions_redacted": symbol_positions,
        "open_orders_redacted": _redacted_open_orders(symbol_open_orders),
        "blockers": blockers,
    }


def _open_positions(account: dict[str, Any]) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for item in list(account.get("positions") or []):
        if not isinstance(item, dict):
            continue
        amount = _decimal(item.get("positionAmt") or "0")
        if abs(amount) <= Decimal("0.000000000001"):
            continue
        positions.append(
            {
                "symbol": str(item.get("symbol") or ""),
                "positionSide": str(item.get("positionSide") or ""),
                "positionAmt": _fmt_decimal(amount),
                "notional": str(item.get("notional") or ""),
            }
        )
    return positions


def _redacted_open_orders(open_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": str(item.get("symbol") or ""),
            "orderId": item.get("orderId"),
            "clientOrderId": str(item.get("clientOrderId") or ""),
            "side": str(item.get("side") or ""),
            "positionSide": str(item.get("positionSide") or ""),
            "status": str(item.get("status") or ""),
            "type": str(item.get("type") or ""),
            "origQty": str(item.get("origQty") or ""),
        }
        for item in open_orders
    ]


def _default_client_order_id(started: datetime, symbol: str, side: str) -> str:
    slug = "".join(char.lower() for char in symbol if char.isalnum())[:10]
    return f"hvlsm-{started.strftime('%H%M%S')}-{slug}-{side[0].lower()}"


def _client_order_id_blockers(value: str, *, field_name: str) -> list[str]:
    blockers: list[str] = []
    if not value:
        blockers.append(f"{field_name}_required")
    if len(value) > 36:
        blockers.append(f"{field_name}_too_long:{len(value)}")
    if any(char not in CLIENT_ORDER_ID_ALLOWED for char in value):
        blockers.append(f"{field_name}_contains_invalid_character")
    return blockers


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


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not a decimal: {value!r}") from exc


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return Decimal("0")
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _fmt_decimal(value: Decimal | float | int | str) -> str:
    decimal = _decimal(value)
    text = format(decimal.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    symbol: str,
    side: str,
    executed: bool,
    required_confirmation: str | None = None,
    entry_client_order_id: str | None = None,
    close_client_order_id: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "environment": "mainnet",
        "symbol": symbol,
        "side": side,
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "executed": executed,
        "required_confirmation": required_confirmation,
        "entry_client_order_id": entry_client_order_id,
        "close_client_order_id": close_client_order_id,
        "artifact_root": str(artifact_root),
        "strategy_order_generation": "disabled",
    }


def _persist(
    run_root: Path,
    *,
    request_context: dict[str, Any],
    result: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    write_json(run_root / "request_context.json", request_context)
    write_json(run_root / "manual_live_order_smoke_result.json", result)
    write_json(run_root / "run_summary.json", summary)


if __name__ == "__main__":
    raise SystemExit(main())
