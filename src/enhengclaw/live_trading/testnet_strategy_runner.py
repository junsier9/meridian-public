from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_USDM_MAINNET_BASE_URL,
    BINANCE_USDM_TESTNET_BASE_URL,
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
    submit_testnet_strategy_order_intent,
)
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import write_json


TESTNET_STRATEGY_CONFIRMATION = "I_UNDERSTAND_THIS_SUBMITS_BINANCE_USDM_TESTNET_STRATEGY_ORDERS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Testnet-only hv_balanced strategy auto-order runner.")
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_testnet_sizing.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public data.")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--execute-testnet-strategy-orders", action="store_true")
    parser.add_argument("--i-understand-this-uses-binance-usdm-testnet", action="store_true")
    parser.add_argument("--confirm-testnet-risk", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_testnet_strategy_auto_order(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_testnet_strategy_auto_order(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    market_client_factory: Callable[..., Any] = BinanceUsdmClient,
    order_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_testnet_sizing.yaml"))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-testnet-strategy"
    run_root = live_config.artifact_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    blockers = _config_blockers(payload)
    execute = bool(getattr(args, "execute_testnet_strategy_orders", False))
    if execute:
        blockers.extend(_execute_confirmation_blockers(args))
    local_state_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=float(dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900) or 900),
        ignore_run_id=run_id,
    )
    blockers.extend(list(local_state_health.get("blockers") or []))
    write_json(run_root / "local_state_health.json", local_state_health)
    operator_state = state_store.read_operator_state()
    write_json(run_root / "operator_state.json", operator_state)
    if bool(operator_state.get("paused")):
        blockers.append("operator_paused")
    state_store.write_heartbeat(
        run_id=run_id,
        mode="testnet",
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
    risk_gate = evaluate_risk_gate(
        portfolio,
        mode="testnet",
        config=payload,
        live_confirmed=False,
        local_state_health=local_state_health,
    )
    mark_prices = _mark_prices(snapshot.scores)
    order_sizing_report = build_order_sizing_report(
        portfolio,
        mode="testnet",
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
        mode="testnet",
        current_positions={},
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        allow_testnet_order_submission=True,
    )
    _write_strategy_artifacts(
        run_root,
        snapshot=snapshot,
        portfolio=portfolio,
        risk_gate=risk_gate,
        order_sizing_report=order_sizing_report,
        min_capital_report=min_capital_report,
        plan=plan,
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
        )
    if not execute:
        summary = _summary(
            run_id=run_id,
            status="testnet_strategy_plan_ready",
            blockers=[],
            started_at=started,
            artifact_root=run_root,
            latest_decision_id=snapshot.decision_id,
            latest_portfolio_id=portfolio.portfolio_id,
            submitted_order_count=0,
            fill_count=0,
        )
        _persist_summary(run_root, state_store, summary)
        return summary, 0

    credentials = _resolve_credentials(payload, env or os.environ)
    blockers.extend(credentials["blockers"])
    order_client = None if blockers else _build_testnet_order_client(credentials, order_client_factory)
    preflight = {"status": "not_run", "blockers": list(blockers)}
    if order_client is not None:
        preflight = _testnet_preflight(order_client, expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"))
        blockers.extend(preflight["blockers"])
    write_json(run_root / "testnet_preflight.json", preflight)
    if blockers or order_client is None:
        return _blocked_summary(
            run_id=run_id,
            started=started,
            run_root=run_root,
            state_store=state_store,
            blockers=blockers,
            latest_decision_id=snapshot.decision_id,
            latest_portfolio_id=portfolio.portfolio_id,
        )
    execution = _execute_testnet_plan(order_client, plan)
    _write_execution_artifacts(run_root, execution=execution)
    blockers.extend(execution["blockers"])
    status = "testnet_strategy_orders_submitted" if not blockers else "testnet_strategy_reconcile_required"
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
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status == "testnet_strategy_orders_submitted" else 2


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


def _execute_testnet_plan(client: Any, plan: ExecutionPlan) -> dict[str, Any]:
    submitted: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    blockers: list[str] = []
    recoveries: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for intent in plan.intents:
        try:
            snapshot = submit_testnet_strategy_order_intent(client, intent)
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
            blockers.append(f"testnet_order_rejected:{intent.symbol}:http_{exc.status_code}:{_binance_error_code(exc.detail)}")
            break
        submitted.append(_order_row(snapshot, intent=intent))
        if snapshot.status != "FILLED":
            blockers.append(f"testnet_order_not_filled:{intent.symbol}:{snapshot.status}")
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


def _testnet_preflight(client: Any, *, expected_position_mode: str) -> dict[str, Any]:
    blockers: list[str] = []
    account = dict(client.account_information_v3().payload)
    account_config = dict(client.account_config().payload)
    position_mode = dict(client.position_mode().payload)
    open_orders = list(client.current_all_open_orders().payload or [])
    open_positions = _open_positions(account)
    available_balance = _float(account.get("availableBalance"))
    total_wallet_balance = _float(account.get("totalWalletBalance"))
    dual = bool(position_mode.get("dualSidePosition", False))
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
    if open_positions:
        blockers.append(f"testnet_open_positions_exist:{len(open_positions)}")
    if available_balance <= 0.0:
        blockers.append("testnet_available_balance_not_positive")
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "account_config_readable": bool(account_config),
        "canTrade": can_trade,
        "position_mode": actual_mode,
        "open_order_count": len(open_orders),
        "open_position_count": len(open_positions),
        "available_balance_usdt": float(available_balance),
        "total_wallet_balance_usdt": float(total_wallet_balance),
        "open_positions_redacted": open_positions,
    }


def _write_strategy_artifacts(
    run_root: Path,
    *,
    snapshot: Any,
    portfolio: Any,
    risk_gate: Any,
    order_sizing_report: pd.DataFrame,
    min_capital_report: dict[str, Any],
    plan: ExecutionPlan,
) -> None:
    write_json(run_root / "decision_snapshot.json", snapshot.metadata())
    snapshot.scores.to_csv(run_root / "decision_scores.csv", index=False)
    write_json(run_root / "target_portfolio.json", portfolio.metadata())
    portfolio.positions_frame().to_csv(run_root / "target_positions.csv", index=False)
    write_json(run_root / "risk_gate.json", risk_gate.to_dict())
    order_sizing_report.to_csv(run_root / "order_sizing_report.csv", index=False)
    write_json(run_root / "min_executable_capital_report.json", min_capital_report)
    write_json(run_root / "execution_plan.json", plan.metadata())
    plan.intents_frame().to_csv(run_root / "execution_plan.csv", index=False)


def _write_execution_artifacts(run_root: Path, *, execution: dict[str, Any]) -> None:
    write_json(run_root / "testnet_order_execution.json", execution)
    pd.DataFrame(execution["submitted_orders"]).to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame(execution["fills"]).to_csv(run_root / "fills.csv", index=False)
    write_json(run_root / "reconciliation.json", {"status": execution["status"], "blockers": execution["blockers"]})


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


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    latest_decision_id: str | None = None,
    latest_portfolio_id: str | None = None,
    submitted_order_count: int = 0,
    fill_count: int = 0,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": "testnet",
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "latest_decision_id": latest_decision_id,
        "latest_portfolio_id": latest_portfolio_id,
        "artifact_root": str(artifact_root),
        "testnet_only": True,
        "order_base_url": BINANCE_USDM_TESTNET_BASE_URL,
        "market_data_base_url": BINANCE_USDM_MAINNET_BASE_URL,
        "strategy_order_generation": "enabled_testnet_only",
        "submitted_order_count": int(submitted_order_count),
        "fill_count": int(fill_count),
    }


def _blocked_summary(
    *,
    run_id: str,
    started: datetime,
    run_root: Path,
    state_store: LiveTradingStateStore,
    blockers: list[str],
    latest_decision_id: str | None = None,
    latest_portfolio_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    summary = _summary(
        run_id=run_id,
        status="blocked",
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
        latest_decision_id=latest_decision_id,
        latest_portfolio_id=latest_portfolio_id,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 2


def _persist_summary(run_root: Path, state_store: LiveTradingStateStore, summary: dict[str, Any]) -> None:
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", str(summary["run_id"]), summary)
    state_store.write_heartbeat(
        run_id=str(summary["run_id"]),
        mode="testnet",
        status=str(summary["status"]),
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(summary["artifact_root"]),
        blockers=list(summary.get("blockers") or []),
    )


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    venue = str(dict(payload.get("binance") or {}).get("venue") or "").strip().lower()
    if venue != "usdm_futures_testnet":
        blockers.append(f"testnet_strategy_requires_testnet_venue:actual={venue or 'missing'}")
    return blockers


def _execute_confirmation_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "i_understand_this_uses_binance_usdm_testnet", False)):
        blockers.append("missing_testnet_understanding_flag")
    confirmation = str(getattr(args, "confirm_testnet_risk", "") or "").strip()
    if confirmation != TESTNET_STRATEGY_CONFIRMATION:
        blockers.append("missing_exact_testnet_strategy_confirmation")
    return blockers


def _resolve_credentials(payload: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_TESTNET_API_KEY").strip()
    api_secret_env = str(binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_TESTNET_API_SECRET").strip()
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


def _build_testnet_order_client(credentials: dict[str, Any], client_factory: Callable[..., Any]) -> Any:
    return client_factory(
        base_url=BINANCE_USDM_TESTNET_BASE_URL,
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
            }
        )
    return positions


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
