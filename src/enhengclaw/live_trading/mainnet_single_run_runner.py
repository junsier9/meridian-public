from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import UTC, datetime
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
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.execution_planner import (
    build_execution_plan,
    build_order_sizing_report,
    summarize_order_sizing_report,
)
from enhengclaw.live_trading.hv_balanced_live_signal import build_live_hv_balanced_snapshot, file_sha256, load_frozen_config
from enhengclaw.live_trading.market_data import fetch_public_live_feature_panel, resolve_config_symbols
from enhengclaw.live_trading.models import ExecutionPlan, OrderIntent
from enhengclaw.live_trading.order_router import (
    BinanceOrderSnapshot,
    recover_unknown_order_status,
    submit_mainnet_strategy_single_run_order_intent,
)
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import write_json


MAINNET_SINGLE_RUN_CONFIRMATION = (
    "LIVE_STRATEGY_SINGLE_RUN:HV_BALANCED:MAINNET:ALLOCATED=500:MAX_ORDER=100:"
    "ONE_WAY:CROSS_MAX_LEVERAGE=2:NO_DAILY_PNL_GATE"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-run mainnet hv_balanced strategy pilot runner.")
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public data.")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--execute-mainnet-strategy-orders", action="store_true")
    parser.add_argument("--operator-enable-live-for-this-run", action="store_true")
    parser.add_argument("--i-understand-this-places-real-mainnet-strategy-orders", action="store_true")
    parser.add_argument("--i-understand-daily-loss-budget-is-review-only", action="store_true")
    parser.add_argument("--confirm-mainnet-single-run", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_single_run_pilot(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_single_run_pilot(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    market_client_factory: Callable[..., Any] = BinanceUsdmClient,
    order_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml"))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-single-run"
    run_root = live_config.artifact_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()

    execute = bool(getattr(args, "execute_mainnet_strategy_orders", False))
    blockers = _config_blockers(payload)
    if execute:
        blockers.extend(_execute_confirmation_blockers(args))
    local_state_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=float(dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900) or 900),
        ignore_run_id=run_id,
    )
    blockers.extend(list(local_state_health.get("blockers") or []))
    operator_state = state_store.read_operator_state()
    if bool(operator_state.get("paused")):
        blockers.append("operator_paused")
    write_json(run_root / "local_state_health.json", local_state_health)
    write_json(run_root / "operator_state.json", operator_state)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live",
        status="running",
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        artifact_root=str(run_root),
    )

    frozen_path = live_config.strategy_config_path
    frozen_config = load_frozen_config(frozen_path)
    config_sha = file_sha256(frozen_path)
    expected_sha = str(dict(payload.get("strategy") or {}).get("frozen_config_sha256") or "").strip()
    if expected_sha and expected_sha != config_sha:
        blockers.append(f"frozen_config_sha256_mismatch:expected={expected_sha}:actual={config_sha}")

    panel, market_data_audit, symbol_filters = _load_panel(
        args=args,
        payload=payload,
        frozen_config=frozen_config,
        market_client_factory=market_client_factory,
    )
    write_json(run_root / "market_data_audit.json", market_data_audit)
    write_json(run_root / "symbol_exchange_filters.json", symbol_filters)
    if panel.empty:
        blockers.append("empty_market_data_panel")
    if "timestamp_ms" not in panel.columns:
        blockers.append("market_data_panel_missing_timestamp_ms")
    decision_time_ms = (
        _resolve_decision_time_ms(panel, str(getattr(args, "as_of", "now") or "now"))
        if "timestamp_ms" in panel.columns
        else None
    )
    if decision_time_ms is None:
        blockers.append("as_of_before_available_panel")
        return _blocked_summary(
            run_id=run_id,
            started=started,
            run_root=run_root,
            state_store=state_store,
            blockers=blockers,
            preflight_status="not_run",
        )
    panel = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").le(int(decision_time_ms))].copy()
    snapshot = build_live_hv_balanced_snapshot(
        panel,
        config=frozen_config,
        config_sha256=config_sha,
        decision_time_ms=int(decision_time_ms),
        rebalance_interval_days=int(dict(payload.get("strategy") or {}).get("rebalance_interval_days", 10) or 10),
    )
    portfolio = build_target_portfolio(
        snapshot,
        config=frozen_config,
        allocated_capital_usdt=float(dict(payload.get("capital") or {}).get("allocated_capital_usdt", 0.0) or 0.0),
    )
    risk_mode = "live" if execute else "plan_only"
    risk_payload_for_this_run = _risk_payload_for_this_run(payload, execute=execute)
    risk_gate = evaluate_risk_gate(
        portfolio,
        mode=risk_mode,
        config=risk_payload_for_this_run,
        live_confirmed=execute and bool(getattr(args, "operator_enable_live_for_this_run", False)),
        local_state_health=local_state_health,
    )
    mark_prices = _mark_prices(snapshot.scores)
    order_sizing_report = build_order_sizing_report(
        portfolio,
        mode=risk_mode,
        current_positions={},
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
    )
    min_capital_report = summarize_order_sizing_report(
        order_sizing_report,
        allocated_capital_usdt=portfolio.allocated_capital_usdt,
    )
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode=risk_mode,
        current_positions={},
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        allow_live_order_submission=execute,
    )
    _write_strategy_artifacts(
        run_root,
        snapshot=snapshot,
        portfolio=portfolio,
        risk_gate=risk_gate,
        order_sizing_report=order_sizing_report,
        min_capital_report=min_capital_report,
        plan=plan,
        runtime_gate_context=_runtime_gate_context(payload, execute=execute),
    )
    blockers.extend([*snapshot.blockers, *portfolio.blockers, *risk_gate.blockers, *plan.blockers])
    if blockers:
        return _blocked_summary(
            run_id=run_id,
            started=started,
            run_root=run_root,
            state_store=state_store,
            blockers=blockers,
            latest_decision_id=snapshot.decision_id,
            latest_portfolio_id=portfolio.portfolio_id,
            preflight_status="not_run",
        )
    if not execute:
        summary = _summary(
            run_id=run_id,
            status="mainnet_single_run_plan_ready",
            blockers=[],
            started_at=started,
            artifact_root=run_root,
            latest_decision_id=snapshot.decision_id,
            latest_portfolio_id=portfolio.portfolio_id,
            submitted_order_count=0,
            fill_count=0,
            preflight_status="not_run",
            reconciliation_status="not_run",
        )
        _persist_summary(run_root, state_store, summary)
        return summary, 0

    credentials = _resolve_credentials(payload, env or os.environ)
    blockers.extend(credentials["blockers"])
    order_client = None if blockers else _build_mainnet_order_client(credentials, order_client_factory)
    permission_client = None if blockers else _build_permission_client(credentials, permission_client_factory)
    preflight = {"status": "not_run", "blockers": list(blockers)}
    if order_client is not None and permission_client is not None:
        preflight = _mainnet_preflight(
            order_client,
            permission_client=permission_client,
            expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
            expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
            max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
            target_symbols=[intent.symbol for intent in plan.intents],
            required_available_balance=float(dict(payload.get("capital") or {}).get("allocated_capital_usdt", 0.0) or 0.0),
        )
        blockers.extend(preflight["blockers"])
    write_json(run_root / "mainnet_preflight.json", preflight)
    write_json(run_root / "account_before.json", preflight.get("account_snapshot", {}))
    if blockers or order_client is None:
        return _blocked_summary(
            run_id=run_id,
            started=started,
            run_root=run_root,
            state_store=state_store,
            blockers=blockers,
            latest_decision_id=snapshot.decision_id,
            latest_portfolio_id=portfolio.portfolio_id,
            preflight_status=str(preflight.get("status") or "blocked"),
        )
    execution = _execute_mainnet_plan(order_client, plan)
    reconciliation = _reconcile_after_execution(order_client, execution=execution)
    _write_execution_artifacts(run_root, execution=execution, reconciliation=reconciliation)
    blockers.extend(execution["blockers"])
    blockers.extend(reconciliation["blockers"])
    status = "mainnet_single_run_orders_submitted" if not blockers else "mainnet_single_run_reconcile_required"
    summary = _summary(
        run_id=run_id,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
        latest_decision_id=snapshot.decision_id,
        latest_portfolio_id=portfolio.portfolio_id,
        submitted_order_count=int(execution["submitted_order_count"]),
        fill_count=int(execution["fill_count"]),
        preflight_status=str(preflight.get("status") or "unknown"),
        reconciliation_status=str(reconciliation.get("status") or "unknown"),
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status == "mainnet_single_run_orders_submitted" else 2


def _risk_payload_for_this_run(payload: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    scoped = copy.deepcopy(payload)
    risk = dict(scoped.get("risk") or {})
    if execute:
        risk["trading_enabled"] = True
    scoped["risk"] = risk
    return scoped


def _runtime_gate_context(payload: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    risk = dict(payload.get("risk") or {})
    return {
        "config_trading_enabled": bool(risk.get("trading_enabled", False)),
        "runtime_trading_enabled_override": bool(execute),
    }


def _load_panel(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    frozen_config: dict[str, Any],
    market_client_factory: Callable[..., Any],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]:
    fixture_panel = str(getattr(args, "fixture_panel", "") or "").strip()
    if fixture_panel:
        return pd.read_csv(resolve_repo_path(fixture_panel)), {"source": "fixture_panel"}, {}
    market_data = dict(payload.get("market_data") or {})
    if not (bool(market_data.get("public_data_enabled", False)) or bool(getattr(args, "public_market_data", False))):
        return pd.DataFrame(), {"source": "missing_public_market_data_flag"}, {}
    market_client = market_client_factory(base_url=BINANCE_USDM_MAINNET_BASE_URL)
    symbols = resolve_config_symbols(payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    return fetch_public_live_feature_panel(
        client=market_client,
        config=frozen_config,
        symbols=symbols,
        daily_limit=int(market_data.get("daily_limit", 140) or 140),
        four_hour_limit=int(market_data.get("four_hour_limit", 840) or 840),
    )


def _mainnet_preflight(
    client: Any,
    *,
    permission_client: Any,
    expected_position_mode: str,
    expected_margin_type: str,
    max_allowed_leverage: int,
    target_symbols: list[str],
    required_available_balance: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    account = dict(client.account_information_v3().payload)
    account_config = dict(client.account_config().payload)
    position_mode = dict(client.position_mode().payload)
    open_orders = list(client.current_all_open_orders().payload or [])
    position_risk = [dict(item) for item in list(client.position_information_v2().payload or []) if isinstance(item, dict)]
    api_key_permissions = dict(permission_client.api_key_restrictions().payload)
    open_positions = _open_positions(account)
    target_position_risk = _target_position_risk_rows(position_risk, target_symbols=target_symbols)
    available_balance = _float(account.get("availableBalance"))
    total_wallet_balance = _float(account.get("totalWalletBalance"))
    dual = bool(position_mode.get("dualSidePosition", False))
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
    if open_positions:
        blockers.append(f"mainnet_open_positions_exist:{len(open_positions)}")
    blockers.extend(
        _position_risk_config_blockers(
            target_position_risk,
            expected_margin_type=expected_margin_type,
            max_allowed_leverage=max_allowed_leverage,
            target_symbols=target_symbols,
        )
    )
    if required_available_balance > 0.0 and available_balance < required_available_balance:
        blockers.append(f"mainnet_available_balance_below_allocated:{available_balance}<{required_available_balance}")
    blockers.extend(_api_key_permission_blockers(api_key_permissions))
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "canTrade": can_trade,
        "position_mode": actual_mode,
        "open_order_count": len(open_orders),
        "open_position_count": len(open_positions),
        "available_balance_usdt": float(available_balance),
        "total_wallet_balance_usdt": float(total_wallet_balance),
        "required_available_balance_usdt": float(required_available_balance),
        "api_key_permissions": _redacted_api_key_permissions(api_key_permissions),
        "position_risk": target_position_risk,
        "account_snapshot": {
            "available_balance_usdt": float(available_balance),
            "total_wallet_balance_usdt": float(total_wallet_balance),
            "open_positions_redacted": open_positions,
            "open_orders_redacted": _redacted_open_orders(open_orders),
        },
    }


def _execute_mainnet_plan(client: Any, plan: ExecutionPlan) -> dict[str, Any]:
    submitted: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    blockers: list[str] = []
    recoveries: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for intent in plan.intents:
        try:
            snapshot = submit_mainnet_strategy_single_run_order_intent(client, intent)
        except BinanceUsdmUnknownExecutionStatus:
            recovery = recover_unknown_order_status(client, symbol=intent.symbol, client_order_id=intent.client_order_id)
            recoveries.append(recovery.to_dict())
            if recovery.status != "resolved":
                blockers.extend(recovery.blockers or [f"unknown_order_recovery_required:{intent.symbol}:{intent.client_order_id}"])
                break
            blockers.append(f"unknown_order_status_recovered_stop_for_reconcile:{intent.symbol}:{intent.client_order_id}")
            break
        except BinanceUsdmRequestError as exc:
            rejection = {
                "intent_id": intent.intent_id,
                "symbol": intent.symbol,
                "client_order_id": intent.client_order_id,
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
            rejections.append(rejection)
            blockers.append(f"mainnet_order_rejected:{intent.symbol}:http_{exc.status_code}:{_binance_error_code(exc.detail)}")
            break
        submitted.append(_order_row(snapshot, intent=intent))
        if snapshot.status != "FILLED":
            blockers.append(f"mainnet_order_not_filled:{intent.symbol}:{snapshot.status}")
            break
        fills.append(_fill_row(snapshot, intent=intent))
    status = "submitted" if not blockers else "reconcile_required"
    return {
        "status": status,
        "blockers": sorted(set(blockers)),
        "submitted_order_count": int(len(submitted)),
        "fill_count": int(len(fills)),
        "submitted_orders": submitted,
        "fills": fills,
        "recoveries": recoveries,
        "rejections": rejections,
    }


def _reconcile_after_execution(client: Any, *, execution: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    account = dict(client.account_information_v3().payload)
    open_orders = [dict(item) for item in list(client.current_all_open_orders().payload or []) if isinstance(item, dict)]
    open_positions = _open_positions(account)
    fills = list(execution.get("fills") or [])
    expected_by_symbol: dict[str, float] = {}
    for row in fills:
        signed = float(row.get("quantity") or 0.0)
        if str(row.get("side") or "").upper() == "SELL":
            signed *= -1.0
        expected_by_symbol[str(row.get("symbol") or "")] = expected_by_symbol.get(str(row.get("symbol") or ""), 0.0) + signed
    actual_by_symbol = {str(row["symbol"]): float(row["positionAmt"]) for row in open_positions}
    for symbol, expected in expected_by_symbol.items():
        actual = actual_by_symbol.get(symbol, 0.0)
        if abs(actual - expected) > 1e-9:
            blockers.append(f"position_mismatch:{symbol}:expected={expected}:actual={actual}")
    if open_orders:
        blockers.append(f"mainnet_open_orders_after_execution:{len(open_orders)}")
    return {
        "status": "reconciled" if not blockers else "reconcile_required",
        "blockers": sorted(set(blockers)),
        "expected_position_count": int(len(expected_by_symbol)),
        "open_position_count": int(len(open_positions)),
        "open_order_count": int(len(open_orders)),
        "expected_positions": expected_by_symbol,
        "open_positions_redacted": open_positions,
        "open_orders_redacted": _redacted_open_orders(open_orders),
    }


def _write_strategy_artifacts(
    run_root,
    *,
    snapshot: Any,
    portfolio: Any,
    risk_gate: Any,
    order_sizing_report: pd.DataFrame,
    min_capital_report: dict[str, Any],
    plan: ExecutionPlan,
    runtime_gate_context: dict[str, Any],
) -> None:
    write_json(run_root / "runtime_gate_context.json", runtime_gate_context)
    write_json(run_root / "decision_snapshot.json", snapshot.metadata())
    snapshot.scores.to_csv(run_root / "decision_scores.csv", index=False)
    write_json(run_root / "target_portfolio.json", portfolio.metadata())
    portfolio.positions_frame().to_csv(run_root / "target_positions.csv", index=False)
    write_json(run_root / "risk_gate.json", risk_gate.to_dict())
    order_sizing_report.to_csv(run_root / "order_sizing_report.csv", index=False)
    write_json(run_root / "min_executable_capital_report.json", min_capital_report)
    write_json(run_root / "execution_plan.json", plan.metadata())
    plan.intents_frame().to_csv(run_root / "execution_plan.csv", index=False)
    pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "fills.csv", index=False)


def _write_execution_artifacts(run_root, *, execution: dict[str, Any], reconciliation: dict[str, Any]) -> None:
    write_json(run_root / "mainnet_order_execution.json", execution)
    write_json(run_root / "reconciliation.json", reconciliation)
    write_json(run_root / "account_after.json", reconciliation)
    pd.DataFrame(execution["submitted_orders"]).to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame(execution["fills"]).to_csv(run_root / "fills.csv", index=False)


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root,
    latest_decision_id: str | None = None,
    latest_portfolio_id: str | None = None,
    submitted_order_count: int = 0,
    fill_count: int = 0,
    preflight_status: str = "not_run",
    reconciliation_status: str = "not_run",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": "live",
        "environment": "mainnet",
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "latest_decision_id": latest_decision_id,
        "latest_portfolio_id": latest_portfolio_id,
        "artifact_root": str(artifact_root),
        "mainnet_single_run_only": True,
        "recurring_loop_enabled": False,
        "order_base_url": BINANCE_USDM_MAINNET_BASE_URL,
        "required_confirmation": MAINNET_SINGLE_RUN_CONFIRMATION,
        "preflight_status": preflight_status,
        "reconciliation_status": reconciliation_status,
        "submitted_order_count": int(submitted_order_count),
        "fill_count": int(fill_count),
    }


def _blocked_summary(
    *,
    run_id: str,
    started: datetime,
    run_root,
    state_store: LiveTradingStateStore,
    blockers: list[str],
    latest_decision_id: str | None = None,
    latest_portfolio_id: str | None = None,
    preflight_status: str = "not_run",
) -> tuple[dict[str, Any], int]:
    summary = _summary(
        run_id=run_id,
        status="blocked",
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
        latest_decision_id=latest_decision_id,
        latest_portfolio_id=latest_portfolio_id,
        preflight_status=preflight_status,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 2


def _persist_summary(run_root, state_store: LiveTradingStateStore, summary: dict[str, Any]) -> None:
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", str(summary["run_id"]), summary)
    state_store.write_heartbeat(
        run_id=str(summary["run_id"]),
        mode="live",
        status=str(summary["status"]),
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(summary["artifact_root"]),
        blockers=list(summary.get("blockers") or []),
    )


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    venue = str(binance.get("venue") or "").strip().lower()
    if venue != "usdm_futures":
        blockers.append(f"mainnet_single_run_requires_mainnet_venue:actual={venue or 'missing'}")
    max_leverage = _max_allowed_leverage(binance)
    if max_leverage < 1:
        blockers.append("mainnet_single_run_requires_positive_max_leverage")
    if max_leverage > 2:
        blockers.append(f"mainnet_single_run_max_leverage_above_pilot_cap:{max_leverage}>2")
    return blockers


def _execute_confirmation_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "operator_enable_live_for_this_run", False)):
        blockers.append("missing_operator_enable_live_for_this_run")
    if not bool(getattr(args, "i_understand_this_places_real_mainnet_strategy_orders", False)):
        blockers.append("missing_mainnet_strategy_order_understanding_flag")
    confirmation = str(getattr(args, "confirm_mainnet_single_run", "") or "").strip()
    if confirmation != MAINNET_SINGLE_RUN_CONFIRMATION:
        blockers.append("missing_exact_mainnet_single_run_confirmation")
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


def _build_mainnet_order_client(credentials: dict[str, Any], client_factory: Callable[..., Any]) -> Any:
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


def _resolve_decision_time_ms(panel: pd.DataFrame, as_of: str) -> int | None:
    timestamps = pd.to_numeric(panel["timestamp_ms"], errors="coerce").dropna().astype("int64")
    if timestamps.empty:
        return None
    normalized = str(as_of or "now").strip()
    if normalized.lower() in {"", "now"}:
        return int(timestamps.max())
    as_of_ms = _parse_as_of_ms(normalized)
    eligible = timestamps.loc[timestamps.le(as_of_ms)]
    if eligible.empty:
        return None
    return int(eligible.max())


def _parse_as_of_ms(value: str) -> int:
    normalized = str(value).strip()
    if normalized.isdigit() or (normalized.startswith("-") and normalized[1:].isdigit()):
        return int(normalized)
    timestamp = pd.Timestamp(normalized)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return int(timestamp.timestamp() * 1000)


def _mark_prices(scores: pd.DataFrame) -> dict[str, float]:
    if scores.empty:
        return {}
    return {
        str(row["usdm_symbol"]): float(row["perp_close"])
        for _, row in scores.iterrows()
        if "usdm_symbol" in row and "perp_close" in row
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


def _order_row(snapshot: BinanceOrderSnapshot, *, intent: OrderIntent) -> dict[str, Any]:
    row = snapshot.to_dict()
    row.update(
        {
            "intent_id": intent.intent_id,
            "target_position_amt": intent.target_position_amt,
            "current_position_amt": intent.current_position_amt,
            "delta_position_amt": intent.delta_position_amt,
        }
    )
    row.pop("raw", None)
    return row


def _fill_row(snapshot: BinanceOrderSnapshot, *, intent: OrderIntent) -> dict[str, Any]:
    notional = abs(float(snapshot.executed_quantity) * float(snapshot.average_price))
    return {
        "client_order_id": snapshot.client_order_id,
        "intent_id": intent.intent_id,
        "symbol": snapshot.symbol,
        "side": snapshot.side,
        "price": float(snapshot.average_price),
        "quantity": float(snapshot.executed_quantity),
        "notional_usdt": float(notional),
        "reduce_only": bool(snapshot.reduce_only),
        "order_id": snapshot.order_id,
    }


def _open_positions(account: dict[str, Any]) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for item in list(account.get("positions") or []):
        amount = _float(item.get("positionAmt"))
        if abs(amount) <= 1e-12:
            continue
        positions.append(
            {
                "symbol": str(item.get("symbol") or ""),
                "positionSide": str(item.get("positionSide") or ""),
                "positionAmt": amount,
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


def _target_position_risk_rows(position_risk: list[dict[str, Any]], *, target_symbols: list[str]) -> list[dict[str, Any]]:
    symbols = {str(symbol).upper() for symbol in target_symbols}
    rows: list[dict[str, Any]] = []
    for item in position_risk:
        symbol = str(item.get("symbol") or "").upper()
        if symbol not in symbols:
            continue
        rows.append(
            {
                "symbol": symbol,
                "positionSide": str(item.get("positionSide") or ""),
                "positionAmt": str(item.get("positionAmt") or ""),
                "notional": str(item.get("notional") or ""),
                "leverage": str(item.get("leverage") or ""),
                "marginType": str(item.get("marginType") or ""),
                "isolated": _optional_bool(item.get("isolated")),
            }
        )
    return sorted(rows, key=lambda row: (str(row.get("symbol") or ""), str(row.get("positionSide") or "")))


def _position_risk_config_blockers(
    rows: list[dict[str, Any]],
    *,
    expected_margin_type: str,
    max_allowed_leverage: int,
    target_symbols: list[str],
) -> list[str]:
    blockers: list[str] = []
    by_symbol = {str(row.get("symbol") or "").upper(): row for row in rows if str(row.get("positionSide") or "BOTH") in {"", "BOTH"}}
    for symbol in sorted({str(item).upper() for item in target_symbols}):
        row = by_symbol.get(symbol)
        if row is None:
            blockers.append(f"position_risk_missing:{symbol}")
            continue
        margin_type = str(row.get("marginType") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            blockers.append(f"margin_type_mismatch:{symbol}:expected={expected_margin_type}:actual={margin_type or 'missing'}")
        leverage = int(_float(row.get("leverage")))
        if max_allowed_leverage > 0 and leverage > max_allowed_leverage:
            blockers.append(f"leverage_above_max:{symbol}:max={max_allowed_leverage}:actual={leverage}")
    return blockers


def _max_allowed_leverage(binance: dict[str, Any]) -> int:
    raw = binance.get("max_leverage")
    if raw is None:
        raw = binance.get("leverage")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _binance_error_code(detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return "unknown_code"
    code = payload.get("code") if isinstance(payload, dict) else None
    return f"code_{code}" if code is not None else "unknown_code"


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


if __name__ == "__main__":
    raise SystemExit(main())
