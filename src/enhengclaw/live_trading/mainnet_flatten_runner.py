from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_SPOT_MAINNET_BASE_URL,
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmClient,
    BinanceUsdmRequestError,
    BinanceUsdmUnknownExecutionStatus,
)
from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.order_router import parse_order_snapshot, recover_unknown_order_status
from enhengclaw.quant_research.contracts import write_json


MAINNET_FLATTEN_CONFIRMATION = (
    "LIVE_REDUCE_ONLY_FLATTEN:HV_BALANCED:MAINNET:ALL_POSITIONS:"
    "ONE_WAY:CROSS_MAX_LEVERAGE=2:REDUCE_ONLY:NO_RECURRING"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mainnet reduce-only flatten runner for hv_balanced operator exits. "
            "Default mode is signed read-only dry-run planning; execution requires explicit confirmation."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml")
    parser.add_argument("--execute-mainnet-flatten", action="store_true")
    parser.add_argument("--operator-enable-mainnet-flatten-for-this-run", action="store_true")
    parser.add_argument("--i-understand-this-places-real-mainnet-reduce-only-orders", action="store_true")
    parser.add_argument("--confirm-mainnet-flatten", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_reduce_only_flatten(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_reduce_only_flatten(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    mainnet_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml"))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-flatten"
    run_root = live_config.artifact_root.parent / "mainnet_flatten" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    execute = bool(getattr(args, "execute_mainnet_flatten", False))
    blockers = _config_blockers(payload)
    if execute:
        blockers.extend(_execute_confirmation_blockers(args))
    credentials = _resolve_credentials(payload, env or os.environ)
    blockers.extend(credentials["blockers"])
    mainnet_client = None
    permission_client = None
    if not blockers:
        mainnet_client = _build_mainnet_client(credentials, mainnet_client_factory)
        permission_client = _build_permission_client(credentials, permission_client_factory)

    before = {"status": "not_run", "blockers": list(blockers)}
    plan_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if mainnet_client is not None and permission_client is not None:
        before = _account_snapshot(
            mainnet_client,
            permission_client=permission_client,
            expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
            expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
            max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
        )
        blockers.extend(before["blockers"])
        warnings.extend(before["warnings"])
        if not blockers:
            plan_rows = _build_flatten_plan(before["open_positions_redacted"], run_id=run_id)
    _write_pre_execution_artifacts(run_root, before=before, plan_rows=plan_rows, warnings=warnings)

    if blockers or mainnet_client is None:
        return _finish(
            run_root=run_root,
            run_id=run_id,
            started=started,
            status="blocked",
            blockers=blockers,
            warnings=warnings,
            before=before,
            plan_rows=plan_rows,
        )
    if not plan_rows:
        return _finish(
            run_root=run_root,
            run_id=run_id,
            started=started,
            status="mainnet_already_flat",
            blockers=[],
            warnings=warnings,
            before=before,
            plan_rows=plan_rows,
        )
    if not execute:
        return _finish(
            run_root=run_root,
            run_id=run_id,
            started=started,
            status="mainnet_flatten_plan_ready",
            blockers=[],
            warnings=warnings,
            before=before,
            plan_rows=plan_rows,
        )

    execution = _execute_flatten_plan(mainnet_client, plan_rows)
    write_json(run_root / "mainnet_flatten_execution.json", execution)
    pd.DataFrame(execution["submitted_orders"]).to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame(execution["fills"]).to_csv(run_root / "fills.csv", index=False)
    blockers.extend(execution["blockers"])
    after = _account_snapshot(
        mainnet_client,
        permission_client=permission_client,
        expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
        expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
        max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
    )
    write_json(run_root / "account_after.json", after)
    warnings.extend(after["warnings"])
    reconciliation_blockers = _reconciliation_blockers(after=after, execution=execution)
    blockers.extend(reconciliation_blockers)
    reconciliation = {
        "status": "passed" if not reconciliation_blockers and not blockers else "blocked",
        "blockers": sorted(set([*execution["blockers"], *reconciliation_blockers])),
        "warnings": sorted(set(warnings)),
        "open_order_count_after": after.get("open_order_count"),
        "open_position_count_after": after.get("open_position_count"),
        "submitted_order_count": execution["submitted_order_count"],
        "fill_count": execution["fill_count"],
        "all_submitted_orders_reduce_only": _all_submitted_orders_reduce_only(execution),
    }
    write_json(run_root / "reconciliation.json", reconciliation)
    status = "mainnet_reduce_only_flatten_executed" if not blockers else "mainnet_flatten_reconcile_required"
    return _finish(
        run_root=run_root,
        run_id=run_id,
        started=started,
        status=status,
        blockers=blockers,
        warnings=warnings,
        before=before,
        after=after,
        plan_rows=plan_rows,
        submitted_order_count=int(execution["submitted_order_count"]),
        fill_count=int(execution["fill_count"]),
    )


def _execute_flatten_plan(client: Any, plan_rows: list[dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    submitted: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for row in plan_rows:
        params = {
            "symbol": row["symbol"],
            "side": row["side"],
            "positionSide": row["position_side"],
            "type": "MARKET",
            "quantity": row["quantity"],
            "reduceOnly": "true",
            "newClientOrderId": row["client_order_id"],
            "newOrderRespType": "RESULT",
        }
        try:
            response = client.submit_mainnet_reduce_only_order(**params)
            snapshot = parse_order_snapshot(dict(response.payload))
        except BinanceUsdmUnknownExecutionStatus:
            recovery = recover_unknown_order_status(client, symbol=str(row["symbol"]), client_order_id=str(row["client_order_id"]))
            recoveries.append(recovery.to_dict())
            blockers.append(f"unknown_order_status_recovered_stop_for_reconcile:{row['symbol']}:{row['client_order_id']}")
            break
        except BinanceUsdmRequestError as exc:
            rejections.append(
                {
                    "symbol": row["symbol"],
                    "client_order_id": row["client_order_id"],
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )
            blockers.append(f"mainnet_flatten_order_rejected:{row['symbol']}:http_{exc.status_code}:{_binance_error_code(exc.detail)}")
            break
        order_row = snapshot.to_dict()
        order_row.pop("raw", None)
        order_row["planned_position_amt"] = float(row["position_amt"])
        submitted.append(order_row)
        if not snapshot.reduce_only:
            blockers.append(f"mainnet_flatten_order_not_reduce_only:{row['symbol']}:{snapshot.client_order_id}")
            break
        if snapshot.status != "FILLED":
            blockers.append(f"mainnet_flatten_order_not_filled:{row['symbol']}:{snapshot.status}")
            break
        fills.append(
            {
                "symbol": snapshot.symbol,
                "side": snapshot.side,
                "quantity": float(snapshot.executed_quantity),
                "price": float(snapshot.average_price),
                "notional_usdt": float(abs(snapshot.executed_quantity * snapshot.average_price)),
                "reduce_only": bool(snapshot.reduce_only),
                "client_order_id": snapshot.client_order_id,
                "order_id": snapshot.order_id,
            }
        )
    return {
        "status": "submitted" if not blockers else "reconcile_required",
        "blockers": sorted(set(blockers)),
        "submitted_order_count": int(len(submitted)),
        "fill_count": int(len(fills)),
        "submitted_orders": submitted,
        "fills": fills,
        "recoveries": recoveries,
        "rejections": rejections,
    }


def _account_snapshot(
    client: Any,
    *,
    permission_client: Any,
    expected_position_mode: str,
    expected_margin_type: str,
    max_allowed_leverage: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    account = dict(client.account_information_v3().payload)
    account_config = dict(client.account_config().payload)
    position_mode_payload = dict(client.position_mode().payload)
    open_orders = [dict(item) for item in list(client.current_all_open_orders().payload or []) if isinstance(item, dict)]
    position_risk = [dict(item) for item in list(client.position_information_v2().payload or []) if isinstance(item, dict)]
    api_key_permissions = dict(permission_client.api_key_restrictions().payload)
    open_positions = _open_positions(account=account, position_risk=position_risk)
    dual = bool(position_mode_payload.get("dualSidePosition", False))
    actual_mode = "hedge" if dual else "one_way"
    can_trade = _optional_bool(account.get("canTrade"))
    if can_trade is None:
        can_trade = _optional_bool(account_config.get("canTrade"))
    if can_trade is not True:
        blockers.append("mainnet_account_cannot_trade")
    if expected_position_mode and expected_position_mode != actual_mode:
        blockers.append(f"position_mode_mismatch:expected={expected_position_mode}:actual={actual_mode}")
    if open_orders:
        blockers.append(f"mainnet_open_orders_exist:{len(open_orders)}")
    blockers.extend(_api_key_permission_blockers(api_key_permissions))
    for row in open_positions:
        symbol = str(row["symbol"])
        if str(row.get("positionSide") or "BOTH") != "BOTH":
            blockers.append(f"mainnet_flatten_requires_one_way_position_side:{symbol}:{row.get('positionSide')}")
        margin_type = str(row.get("marginType") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            warnings.append(f"margin_type_differs_from_config:{symbol}:expected={expected_margin_type}:actual={margin_type or 'missing'}")
        leverage = int(_float(row.get("leverage")))
        if max_allowed_leverage > 0 and leverage > max_allowed_leverage:
            warnings.append(f"leverage_above_config_but_reduce_only_exit_allowed:{symbol}:max={max_allowed_leverage}:actual={leverage}")
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "account_config_readable": bool(account_config),
        "api_key_permissions": _redacted_api_key_permissions(api_key_permissions),
        "canTrade": can_trade,
        "position_mode": actual_mode,
        "open_order_count": int(len(open_orders)),
        "open_position_count": int(len(open_positions)),
        "available_balance_usdt": float(_float(account.get("availableBalance"))),
        "total_wallet_balance_usdt": float(_float(account.get("totalWalletBalance"))),
        "open_orders_redacted": _redacted_open_orders(open_orders),
        "open_positions_redacted": open_positions,
    }


def _build_flatten_plan(open_positions: list[dict[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seq, item in enumerate(sorted(open_positions, key=lambda row: str(row["symbol"])), start=1):
        amount = float(item["positionAmt"])
        side = "SELL" if amount > 0.0 else "BUY"
        quantity = _format_quantity(abs(amount))
        rows.append(
            {
                "seq": int(seq),
                "symbol": str(item["symbol"]),
                "position_side": str(item.get("positionSide") or "BOTH") or "BOTH",
                "position_amt": float(amount),
                "notional_usdt": float(_float(item.get("notional"))),
                "unrealized_pnl_usdt": float(_float(item.get("unrealizedProfit"))),
                "side": side,
                "order_type": "MARKET",
                "quantity": quantity,
                "reduce_only": True,
                "client_order_id": _client_order_id(run_id=run_id, symbol=str(item["symbol"]), seq=seq),
            }
        )
    return rows


def _write_pre_execution_artifacts(
    run_root: Path,
    *,
    before: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    write_json(run_root / "account_before.json", before)
    write_json(
        run_root / "flatten_plan.json",
        {
            "row_count": len(plan_rows),
            "reduce_only": True,
            "mainnet": True,
            "warnings": sorted(set(warnings)),
            "rows": plan_rows,
        },
    )
    pd.DataFrame(plan_rows).to_csv(run_root / "flatten_plan.csv", index=False)
    pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "fills.csv", index=False)
    write_json(run_root / "reconciliation.json", {"status": "not_run", "blockers": [], "warnings": sorted(set(warnings))})


def _finish(
    *,
    run_root: Path,
    run_id: str,
    started: datetime,
    status: str,
    blockers: list[str],
    warnings: list[str],
    before: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    after: dict[str, Any] | None = None,
    submitted_order_count: int = 0,
    fill_count: int = 0,
) -> tuple[dict[str, Any], int]:
    summary = {
        "run_id": run_id,
        "mode": "live",
        "environment": "mainnet",
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "artifact_root": str(run_root),
        "mainnet_reduce_only_flatten": True,
        "recurring_mainnet_enabled": False,
        "order_base_url": BINANCE_USDM_MAINNET_BASE_URL,
        "required_confirmation": MAINNET_FLATTEN_CONFIRMATION,
        "flatten_order_generation": "reduce_only_mainnet_explicit_confirm_only",
        "planned_order_count": int(len(plan_rows)),
        "submitted_order_count": int(submitted_order_count),
        "fill_count": int(fill_count),
        "open_position_count_before": int(before.get("open_position_count") or 0),
        "open_order_count_before": int(before.get("open_order_count") or 0),
        "open_position_count_after": None if after is None else int(after.get("open_position_count") or 0),
        "open_order_count_after": None if after is None else int(after.get("open_order_count") or 0),
    }
    write_json(run_root / "run_summary.json", summary)
    success_statuses = {"mainnet_already_flat", "mainnet_flatten_plan_ready", "mainnet_reduce_only_flatten_executed"}
    return summary, 0 if status in success_statuses else 2


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    venue = str(binance.get("venue") or "").strip().lower()
    if venue != "usdm_futures":
        blockers.append(f"mainnet_flatten_requires_mainnet_usdm_venue:actual={venue or 'missing'}")
    max_leverage = _max_allowed_leverage(binance)
    if max_leverage <= 0:
        blockers.append("mainnet_flatten_requires_positive_max_leverage")
    if max_leverage > 2:
        blockers.append(f"mainnet_flatten_max_leverage_above_pilot_cap:{max_leverage}>2")
    return blockers


def _execute_confirmation_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "operator_enable_mainnet_flatten_for_this_run", False)):
        blockers.append("missing_operator_enable_mainnet_flatten_for_this_run")
    if not bool(getattr(args, "i_understand_this_places_real_mainnet_reduce_only_orders", False)):
        blockers.append("missing_mainnet_reduce_only_order_understanding_flag")
    confirmation = str(getattr(args, "confirm_mainnet_flatten", "") or "").strip()
    if confirmation != MAINNET_FLATTEN_CONFIRMATION:
        blockers.append("missing_exact_mainnet_flatten_confirmation")
    return blockers


def _resolve_credentials(payload: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_API_KEY").strip()
    api_secret_env = str(binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_API_SECRET").strip()
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
        "recv_window_ms": int(binance.get("recv_window_ms") or 5000),
        "timeout_seconds": float(binance.get("timeout_seconds") or 10.0),
        "blockers": blockers,
    }


def _build_mainnet_client(credentials: dict[str, Any], client_factory: Callable[..., Any]) -> Any:
    return client_factory(
        base_url=BINANCE_USDM_MAINNET_BASE_URL,
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        recv_window_ms=credentials["recv_window_ms"],
        timeout_seconds=credentials["timeout_seconds"],
    )


def _build_permission_client(credentials: dict[str, Any], client_factory: Callable[..., Any]) -> Any:
    return client_factory(
        base_url=BINANCE_SPOT_MAINNET_BASE_URL,
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        recv_window_ms=credentials["recv_window_ms"],
        timeout_seconds=credentials["timeout_seconds"],
    )


def _reconciliation_blockers(*, after: dict[str, Any], execution: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if int(after.get("open_order_count") or 0) != 0:
        blockers.append(f"residual_mainnet_open_orders:{after.get('open_order_count')}")
    if int(after.get("open_position_count") or 0) != 0:
        blockers.append(f"residual_mainnet_open_positions:{after.get('open_position_count')}")
    if int(execution.get("submitted_order_count") or 0) != int(execution.get("fill_count") or 0):
        blockers.append(
            f"mainnet_flatten_submitted_fill_count_mismatch:{execution.get('submitted_order_count')}!={execution.get('fill_count')}"
        )
    if not _all_submitted_orders_reduce_only(execution):
        blockers.append("mainnet_flatten_submitted_non_reduce_only_order")
    return blockers


def _all_submitted_orders_reduce_only(execution: dict[str, Any]) -> bool:
    orders = [dict(item) for item in list(execution.get("submitted_orders") or []) if isinstance(item, dict)]
    return all(bool(item.get("reduce_only")) or bool(item.get("reduceOnly")) for item in orders)


def _open_positions(*, account: dict[str, Any], position_risk: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risk_by_symbol = {str(item.get("symbol") or "").upper(): dict(item) for item in position_risk}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(account.get("positions") or []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        amount = _float(item.get("positionAmt"))
        if not symbol or abs(amount) <= 1e-12:
            continue
        seen.add(symbol)
        rows.append(_merged_position(symbol=symbol, account_row=item, risk_row=risk_by_symbol.get(symbol, {})))
    for symbol, item in sorted(risk_by_symbol.items()):
        if symbol in seen:
            continue
        amount = _float(item.get("positionAmt"))
        if abs(amount) <= 1e-12:
            continue
        rows.append(_merged_position(symbol=symbol, account_row={}, risk_row=item))
    return sorted(rows, key=lambda row: str(row["symbol"]))


def _merged_position(symbol: str, account_row: dict[str, Any], risk_row: dict[str, Any]) -> dict[str, Any]:
    amount = _float(risk_row.get("positionAmt") if risk_row.get("positionAmt") is not None else account_row.get("positionAmt"))
    unrealized = risk_row.get("unRealizedProfit")
    if unrealized is None:
        unrealized = risk_row.get("unrealizedProfit")
    if unrealized is None:
        unrealized = account_row.get("unrealizedProfit")
    return {
        "symbol": symbol,
        "positionSide": str(risk_row.get("positionSide") or account_row.get("positionSide") or "BOTH"),
        "positionAmt": float(amount),
        "notional": float(_float(risk_row.get("notional") if risk_row.get("notional") is not None else account_row.get("notional"))),
        "entryPrice": float(_float(risk_row.get("entryPrice") if risk_row.get("entryPrice") is not None else account_row.get("entryPrice"))),
        "markPrice": float(_float(risk_row.get("markPrice"))),
        "unrealizedProfit": float(_float(unrealized)),
        "marginType": str(risk_row.get("marginType") or ""),
        "leverage": str(risk_row.get("leverage") or ""),
        "isolated": _optional_bool(risk_row.get("isolated")),
    }


def _api_key_permission_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not payload:
        return ["api_key_permissions_unreadable"]
    if _optional_bool(payload.get("enableReading")) is not True:
        blockers.append(f"api_key_enableReading_not_true:{_optional_bool(payload.get('enableReading'))}")
    if _optional_bool(payload.get("enableFutures")) is not True:
        blockers.append(f"api_key_enableFutures_not_true:{_optional_bool(payload.get('enableFutures'))}")
    if _optional_bool(payload.get("enableWithdrawals")) is not False:
        blockers.append(f"api_key_enableWithdrawals_not_false:{_optional_bool(payload.get('enableWithdrawals'))}")
    if _optional_bool(payload.get("ipRestrict")) is not True:
        blockers.append(f"api_key_ipRestrict_not_true:{_optional_bool(payload.get('ipRestrict'))}")
    return blockers


def _redacted_api_key_permissions(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ip_restrict": _optional_bool(payload.get("ipRestrict")),
        "enable_reading": _optional_bool(payload.get("enableReading")),
        "enable_futures": _optional_bool(payload.get("enableFutures")),
        "enable_withdrawals": _optional_bool(payload.get("enableWithdrawals")),
        "enable_margin": _optional_bool(payload.get("enableMargin")),
        "enable_spot_and_margin_trading": _optional_bool(payload.get("enableSpotAndMarginTrading")),
        "permits_universal_transfer": _optional_bool(payload.get("permitsUniversalTransfer")),
    }


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
            "executedQty": str(item.get("executedQty") or ""),
            "reduceOnly": bool(item.get("reduceOnly", False)),
        }
        for item in open_orders
    ]


def _max_allowed_leverage(binance: dict[str, Any]) -> int:
    raw = binance.get("max_leverage")
    if raw is None:
        raw = binance.get("leverage")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


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


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_quantity(value: float) -> str:
    formatted = f"{float(value):.12f}".rstrip("0").rstrip(".")
    return formatted if formatted else "0"


def _client_order_id(*, run_id: str, symbol: str, seq: int) -> str:
    digest = hashlib.sha256(f"{run_id}:{symbol}:{seq}".encode("utf-8")).hexdigest()[:12]
    return f"hvbal-mf-{digest}-{seq}"


def _binance_error_code(detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return "code_unknown"
    code = payload.get("code")
    return f"code_{code}" if code is not None else "code_unknown"


if __name__ == "__main__":
    raise SystemExit(main())
