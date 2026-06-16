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
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmClient,
    BinanceUsdmRequestError,
    BinanceUsdmUnknownExecutionStatus,
)
from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.order_router import parse_order_snapshot, recover_unknown_order_status
from enhengclaw.quant_research.contracts import write_json


TESTNET_FLATTEN_CONFIRMATION = "I_UNDERSTAND_THIS_SUBMITS_REDUCE_ONLY_BINANCE_USDM_TESTNET_ORDERS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Testnet-only reduce-only flatten runner.")
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_testnet_sizing.yaml")
    parser.add_argument("--execute-testnet-flatten", action="store_true")
    parser.add_argument("--i-understand-this-uses-binance-usdm-testnet", action="store_true")
    parser.add_argument("--confirm-testnet-flatten", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_testnet_reduce_only_flatten(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_testnet_reduce_only_flatten(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_testnet_sizing.yaml"))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-testnet-flatten"
    run_root = live_config.artifact_root.parent / "testnet_flatten" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    blockers = _config_blockers(payload)
    execute = bool(getattr(args, "execute_testnet_flatten", False))
    if execute:
        blockers.extend(_execute_confirmation_blockers(args))
    credentials = _resolve_credentials(payload, env or os.environ)
    blockers.extend(credentials["blockers"])
    client = None if blockers else _build_testnet_client(credentials, client_factory)
    before = {"status": "not_run", "blockers": list(blockers)}
    plan_rows: list[dict[str, Any]] = []
    if client is not None:
        before = _account_snapshot(client, expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"))
        blockers.extend(before["blockers"])
        if not blockers:
            plan_rows = _build_flatten_plan(before["open_positions_redacted"], run_id=run_id)
    _write_pre_execution_artifacts(run_root, before=before, plan_rows=plan_rows)
    if blockers or client is None:
        return _finish(
            run_root=run_root,
            run_id=run_id,
            started=started,
            status="blocked",
            blockers=blockers,
            before=before,
            plan_rows=plan_rows,
        )
    if not plan_rows:
        return _finish(
            run_root=run_root,
            run_id=run_id,
            started=started,
            status="testnet_already_flat",
            blockers=[],
            before=before,
            plan_rows=plan_rows,
        )
    if not execute:
        return _finish(
            run_root=run_root,
            run_id=run_id,
            started=started,
            status="testnet_flatten_plan_ready",
            blockers=[],
            before=before,
            plan_rows=plan_rows,
        )

    execution = _execute_flatten_plan(client, plan_rows)
    write_json(run_root / "testnet_flatten_execution.json", execution)
    pd.DataFrame(execution["submitted_orders"]).to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame(execution["fills"]).to_csv(run_root / "fills.csv", index=False)
    blockers.extend(execution["blockers"])
    after = _account_snapshot(client, expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"))
    write_json(run_root / "account_after.json", after)
    reconciliation_blockers = _reconciliation_blockers(after)
    blockers.extend(reconciliation_blockers)
    reconciliation = {
        "status": "passed" if not reconciliation_blockers and not blockers else "blocked",
        "blockers": sorted(set([*execution["blockers"], *reconciliation_blockers])),
        "open_order_count_after": after.get("open_order_count"),
        "open_position_count_after": after.get("open_position_count"),
        "submitted_order_count": execution["submitted_order_count"],
        "fill_count": execution["fill_count"],
    }
    write_json(run_root / "reconciliation.json", reconciliation)
    status = "testnet_reduce_only_flatten_executed" if not blockers else "testnet_flatten_reconcile_required"
    return _finish(
        run_root=run_root,
        run_id=run_id,
        started=started,
        status=status,
        blockers=blockers,
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
            response = client.submit_testnet_strategy_order(**params)
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
            blockers.append(f"testnet_flatten_order_rejected:{row['symbol']}:http_{exc.status_code}:{_binance_error_code(exc.detail)}")
            break
        order_row = snapshot.to_dict()
        order_row.pop("raw", None)
        order_row["planned_position_amt"] = float(row["position_amt"])
        submitted.append(order_row)
        if snapshot.status != "FILLED":
            blockers.append(f"testnet_flatten_order_not_filled:{row['symbol']}:{snapshot.status}")
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


def _account_snapshot(client: Any, *, expected_position_mode: str) -> dict[str, Any]:
    blockers: list[str] = []
    account = dict(client.account_information_v3().payload)
    account_config = dict(client.account_config().payload)
    position_mode_payload = dict(client.position_mode().payload)
    open_orders = list(client.current_all_open_orders().payload or [])
    open_positions = _open_positions(account)
    dual = bool(position_mode_payload.get("dualSidePosition", False))
    actual_mode = "hedge" if dual else "one_way"
    can_trade = _optional_bool(account.get("canTrade"))
    if can_trade is None:
        can_trade = _optional_bool(account_config.get("canTrade"))
    if can_trade is not True:
        blockers.append("testnet_account_cannot_trade")
    if expected_position_mode and expected_position_mode != actual_mode:
        blockers.append(f"position_mode_mismatch:expected={expected_position_mode}:actual={actual_mode}")
    if open_orders:
        blockers.append(f"testnet_open_orders_exist:{len(open_orders)}")
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "account_config_readable": bool(account_config),
        "canTrade": can_trade,
        "position_mode": actual_mode,
        "open_order_count": int(len(open_orders)),
        "open_position_count": int(len(open_positions)),
        "available_balance_usdt": float(_float(account.get("availableBalance"))),
        "total_wallet_balance_usdt": float(_float(account.get("totalWalletBalance"))),
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
                "side": side,
                "order_type": "MARKET",
                "quantity": quantity,
                "reduce_only": True,
                "client_order_id": _client_order_id(run_id=run_id, symbol=str(item["symbol"]), seq=seq),
            }
        )
    return rows


def _write_pre_execution_artifacts(run_root: Path, *, before: dict[str, Any], plan_rows: list[dict[str, Any]]) -> None:
    write_json(run_root / "account_before.json", before)
    write_json(run_root / "flatten_plan.json", {"row_count": len(plan_rows), "rows": plan_rows})
    pd.DataFrame(plan_rows).to_csv(run_root / "flatten_plan.csv", index=False)
    pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "fills.csv", index=False)
    write_json(run_root / "reconciliation.json", {"status": "not_run", "blockers": []})


def _finish(
    *,
    run_root: Path,
    run_id: str,
    started: datetime,
    status: str,
    blockers: list[str],
    before: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    after: dict[str, Any] | None = None,
    submitted_order_count: int = 0,
    fill_count: int = 0,
) -> tuple[dict[str, Any], int]:
    summary = {
        "run_id": run_id,
        "mode": "testnet",
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "artifact_root": str(run_root),
        "testnet_only": True,
        "order_base_url": BINANCE_USDM_TESTNET_BASE_URL,
        "flatten_order_generation": "reduce_only_testnet_only",
        "planned_order_count": int(len(plan_rows)),
        "submitted_order_count": int(submitted_order_count),
        "fill_count": int(fill_count),
        "open_position_count_before": int(before.get("open_position_count") or 0),
        "open_order_count_before": int(before.get("open_order_count") or 0),
        "open_position_count_after": None if after is None else int(after.get("open_position_count") or 0),
        "open_order_count_after": None if after is None else int(after.get("open_order_count") or 0),
    }
    write_json(run_root / "run_summary.json", summary)
    success_statuses = {"testnet_already_flat", "testnet_flatten_plan_ready", "testnet_reduce_only_flatten_executed"}
    return summary, 0 if status in success_statuses else 2


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    venue = str(dict(payload.get("binance") or {}).get("venue") or "").strip().lower()
    if venue != "usdm_futures_testnet":
        return [f"testnet_flatten_requires_testnet_venue:actual={venue or 'missing'}"]
    return []


def _execute_confirmation_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "i_understand_this_uses_binance_usdm_testnet", False)):
        blockers.append("missing_testnet_understanding_flag")
    confirmation = str(getattr(args, "confirm_testnet_flatten", "") or "").strip()
    if confirmation != TESTNET_FLATTEN_CONFIRMATION:
        blockers.append("missing_exact_testnet_flatten_confirmation")
    return blockers


def _resolve_credentials(payload: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(binance.get("api_key_env") or "DEMO_TESTNET_API_KEY").strip()
    api_secret_env = str(binance.get("api_secret_env") or "DEMO_TESTNET_SECRET_KEY").strip()
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


def _build_testnet_client(credentials: dict[str, Any], client_factory: Callable[..., Any]) -> Any:
    return client_factory(
        base_url=BINANCE_USDM_TESTNET_BASE_URL,
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        recv_window_ms=credentials["recv_window_ms"],
        timeout_seconds=credentials["timeout_seconds"],
    )


def _reconciliation_blockers(after: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if int(after.get("open_order_count") or 0) != 0:
        blockers.append(f"residual_testnet_open_orders:{after.get('open_order_count')}")
    if int(after.get("open_position_count") or 0) != 0:
        blockers.append(f"residual_testnet_open_positions:{after.get('open_position_count')}")
    return blockers


def _open_positions(account: dict[str, Any]) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for item in list(account.get("positions") or []):
        amount = _float(item.get("positionAmt"))
        if abs(amount) <= 1e-12:
            continue
        positions.append(
            {
                "symbol": str(item.get("symbol") or ""),
                "positionSide": str(item.get("positionSide") or "BOTH") or "BOTH",
                "positionAmt": amount,
                "entryPrice": _float(item.get("entryPrice")),
                "unrealizedProfit": _float(item.get("unrealizedProfit")),
            }
        )
    return positions


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
    return f"hvbal-fl-{digest}-{seq}"


def _binance_error_code(detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return "code_unknown"
    code = payload.get("code")
    return f"code_{code}" if code is not None else "code_unknown"


if __name__ == "__main__":
    raise SystemExit(main())
