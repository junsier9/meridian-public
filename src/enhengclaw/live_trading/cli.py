from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import BINANCE_USDM_MAINNET_BASE_URL, BinanceUsdmClient
from enhengclaw.live_trading.config import LIVE_MODES, load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.execution_planner import (
    build_execution_plan,
    build_order_sizing_report,
    summarize_order_sizing_report,
)
from enhengclaw.live_trading.hv_balanced_live_signal import build_live_hv_balanced_snapshot, file_sha256, load_frozen_config
from enhengclaw.live_trading.market_data import fetch_public_live_feature_panel, resolve_config_symbols
from enhengclaw.live_trading.models import ExecutionPlan, LiveDecisionSnapshot, OrderIntent, TargetPortfolio
from enhengclaw.live_trading.paper_broker import PaperExecutionResult, simulate_paper_execution
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.daily_rebalance_slot_gate import REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION
from enhengclaw.quant_research.contracts import write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed hv_balanced Binance USD-M plan runner.")
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm.yaml")
    parser.add_argument("--mode", default="plan_only", choices=sorted(LIVE_MODES))
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public-data plan/paper runs.")
    parser.add_argument("--public-market-data", action="store_true", help="Use Binance USD-M public REST data when no fixture is supplied.")
    parser.add_argument(
        "--operator-action",
        default="none",
        choices=(
            "none",
            "kill-switch",
            "pause",
            "resume",
            "arm-live-delta",
            "disarm-live-delta",
            "force-reconcile",
            "flatten-plan",
            "confirm-flatten-plan",
            "execute-flatten-paper",
            REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
        ),
        help="Record an operator action or generate a local reduce-only flatten plan.",
    )
    parser.add_argument("--operator-reason", default="", help="Short operator reason for pause/resume/flatten-plan.")
    parser.add_argument(
        "--operator-payload-json",
        default="",
        help=(
            "Optional JSON object or @path JSON object to persist with operator actions "
            "(for example owner live-delta expected stage/symbol/turnover payload)."
        ),
    )
    parser.add_argument("--confirm-plan-id", default="", help="Exact flatten plan_id to confirm or execute in paper.")
    parser.add_argument("--i-understand-this-is-live", action="store_true")
    args = parser.parse_args(argv)
    summary, exit_code = run_from_args(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_from_args(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started = datetime.now(UTC)
    mode = str(args.mode or "plan_only").strip().lower()
    live_config = load_live_trading_config(args.config)
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-{mode}"
    run_root = live_config.artifact_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    payload = live_config.payload
    operator_action = str(getattr(args, "operator_action", "none") or "none").strip().lower().replace("_", "-")
    operator_reason = str(getattr(args, "operator_reason", "") or "").strip()
    risk_payload = dict(payload.get("risk") or {})
    local_state_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=float(risk_payload.get("max_heartbeat_age_seconds", 900) or 900),
        ignore_run_id=run_id,
    )
    state_store.write_heartbeat(
        run_id=run_id,
        mode=mode,
        status="running",
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        artifact_root=str(run_root),
    )
    write_json(run_root / "local_state_health.json", local_state_health)
    operator_state = state_store.read_operator_state()
    write_json(run_root / "operator_state.json", operator_state)
    if operator_action == REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION:
        return _run_authorize_risk_only_reduce_cleanup(
            run_id=run_id,
            run_root=run_root,
            started=started,
            state_store=state_store,
            mode=mode,
            operator_reason=operator_reason,
            operator_payload=_operator_payload_from_arg(getattr(args, "operator_payload_json", "")),
        )
    if operator_action in {"kill-switch", "pause", "resume", "arm-live-delta", "disarm-live-delta"}:
        operator_payload = _operator_payload_from_arg(getattr(args, "operator_payload_json", ""))
        action_record = state_store.record_operator_action(
            run_id=run_id,
            action_type=operator_action,
            reason=operator_reason,
            created_at_utc=started.isoformat().replace("+00:00", "Z"),
            payload=operator_payload,
        )
        operator_state = state_store.read_operator_state()
        write_json(run_root / "operator_action.json", action_record)
        write_json(run_root / "operator_state.json", operator_state)
        summary = _summary(
            run_id=run_id,
            mode=mode,
            status=_operator_pause_status(operator_action),
            blockers=[],
            started_at=started,
            artifact_root=run_root,
        )
        _persist_summary(run_root, state_store, summary)
        return summary, 0
    if operator_action == "force-reconcile":
        return _run_force_reconcile(
            run_id=run_id,
            run_root=run_root,
            started=started,
            state_store=state_store,
            mode=mode,
            local_state_health=local_state_health,
            operator_reason=operator_reason,
            max_heartbeat_age_seconds=float(risk_payload.get("max_heartbeat_age_seconds", 900) or 900),
        )
    if operator_action == "confirm-flatten-plan":
        return _run_confirm_flatten_plan(
            run_id=run_id,
            run_root=run_root,
            started=started,
            state_store=state_store,
            mode=mode,
            local_state_health=local_state_health,
            confirm_plan_id=str(getattr(args, "confirm_plan_id", "") or "").strip(),
            operator_reason=operator_reason,
        )
    if operator_action == "execute-flatten-paper":
        return _run_execute_flatten_paper(
            run_id=run_id,
            run_root=run_root,
            started=started,
            state_store=state_store,
            mode=mode,
            local_state_health=local_state_health,
            confirm_plan_id=str(getattr(args, "confirm_plan_id", "") or "").strip(),
            operator_reason=operator_reason,
        )
    frozen_path = live_config.strategy_config_path
    frozen_config = load_frozen_config(frozen_path)
    config_sha = file_sha256(frozen_path)
    blockers: list[str] = list(local_state_health.get("blockers") or [])
    expected_sha = str(dict(payload.get("strategy") or {}).get("frozen_config_sha256") or "").strip()
    if expected_sha and expected_sha != config_sha:
        blockers.append(f"frozen_config_sha256_mismatch:expected={expected_sha}:actual={config_sha}")
    if bool(operator_state.get("paused")) and operator_action != "flatten-plan":
        blockers.append("operator_paused")
    if mode == "live" and not bool(args.i_understand_this_is_live):
        blockers.append("missing_live_confirmation_flag")
    if mode in {"testnet", "live"}:
        blockers.append(f"{mode}_execution_not_enabled_in_phase1")
    market_data_payload = dict(payload.get("market_data") or {})
    public_market_data_enabled = bool(market_data_payload.get("public_data_enabled", False)) or bool(
        getattr(args, "public_market_data", False)
    )
    if not str(args.fixture_panel or "").strip() and not public_market_data_enabled:
        blockers.append("missing_fixture_panel_or_live_market_data_source")
    if blockers:
        summary = _summary(
            run_id=run_id,
            mode=mode,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
        )
        _persist_summary(run_root, state_store, summary)
        return summary, 2

    market_data_audit: dict[str, Any] = {"source": "fixture_panel"}
    symbol_filters: dict[str, dict[str, Any]] = {}
    if str(args.fixture_panel or "").strip():
        panel_path = resolve_repo_path(str(args.fixture_panel))
        panel = pd.read_csv(panel_path)
    else:
        try:
            base_url_env = str(dict(payload.get("binance") or {}).get("base_url_env") or "ENHENGCLAW_BINANCE_USDM_BASE_URL")
            base_url = str(getenv_compat(base_url_env, "") or "").strip() or BINANCE_USDM_MAINNET_BASE_URL
            client = BinanceUsdmClient(base_url=base_url)
            symbols = resolve_config_symbols(payload, override_symbols=str(getattr(args, "symbols", "") or ""))
            panel, market_data_audit, symbol_filters = fetch_public_live_feature_panel(
                client=client,
                config=frozen_config,
                symbols=symbols,
                daily_limit=int(market_data_payload.get("daily_limit", 140) or 140),
                four_hour_limit=int(market_data_payload.get("four_hour_limit", 840) or 840),
            )
        except Exception as exc:
            blockers.append(f"public_market_data_fetch_failed:{type(exc).__name__}:{exc}")
            summary = _summary(
                run_id=run_id,
                mode=mode,
                status="blocked",
                blockers=blockers,
                started_at=started,
                artifact_root=run_root,
            )
            _persist_summary(run_root, state_store, summary)
            return summary, 2
    if "timestamp_ms" not in panel.columns:
        blockers.append("fixture_panel_missing_timestamp_ms")
        summary = _summary(run_id=run_id, mode=mode, status="blocked", blockers=blockers, started_at=started, artifact_root=run_root)
        _persist_summary(run_root, state_store, summary)
        return summary, 2
    decision_time_ms = _resolve_decision_time_ms(panel, str(getattr(args, "as_of", "now") or "now"))
    if decision_time_ms is None:
        blockers.append("as_of_before_available_panel")
        summary = _summary(run_id=run_id, mode=mode, status="blocked", blockers=blockers, started_at=started, artifact_root=run_root)
        _persist_summary(run_root, state_store, summary)
        return summary, 2
    panel = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").le(decision_time_ms)].copy()
    if operator_action == "flatten-plan":
        return _run_operator_flatten_plan(
            args=args,
            run_id=run_id,
            run_root=run_root,
            started=started,
            state_store=state_store,
            payload=payload,
            frozen_config=frozen_config,
            config_sha=config_sha,
            panel=panel,
            mode=mode,
            market_data_audit=market_data_audit,
            symbol_filters=symbol_filters,
            local_state_health=local_state_health,
            operator_state=operator_state,
            operator_reason=operator_reason,
        )
    rebalance_days = int(dict(payload.get("strategy") or {}).get("rebalance_interval_days", 10) or 10)
    snapshot = build_live_hv_balanced_snapshot(
        panel,
        config=frozen_config,
        config_sha256=config_sha,
        decision_time_ms=decision_time_ms,
        rebalance_interval_days=rebalance_days,
    )
    capital = dict(payload.get("capital") or {})
    portfolio = build_target_portfolio(
        snapshot,
        config=frozen_config,
        allocated_capital_usdt=float(capital.get("allocated_capital_usdt", 0.0) or 0.0),
    )
    risk_gate = evaluate_risk_gate(
        portfolio,
        mode=mode,
        config=payload,
        live_confirmed=bool(args.i_understand_this_is_live),
        local_state_health=local_state_health,
    )
    mark_prices = {
        str(row["usdm_symbol"]): float(row["perp_close"])
        for _, row in snapshot.scores.iterrows()
        if "usdm_symbol" in row and "perp_close" in row
    }
    current_positions = state_store.read_paper_positions() if mode == "paper" else {}
    order_sizing_report = build_order_sizing_report(
        portfolio,
        mode=mode,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
    )
    min_executable_capital_report = summarize_order_sizing_report(
        order_sizing_report,
        allocated_capital_usdt=portfolio.allocated_capital_usdt,
    )
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode=mode,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
    )
    if mode == "paper" and state_store.has_paper_execution(plan.plan_id):
        duplicate_blocker = f"duplicate_paper_plan_already_executed:{plan.plan_id}"
        plan.blockers = sorted(set([*plan.blockers, duplicate_blocker]))
        plan.status = "blocked"
    paper_execution: PaperExecutionResult | None = None
    if mode == "paper" and risk_gate.passed and plan.status == "ok":
        paper_execution = simulate_paper_execution(
            plan,
            mark_prices=mark_prices,
            run_id=run_id,
            created_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            current_positions=current_positions,
        )
    _write_pipeline_artifacts(
        run_root,
        snapshot=snapshot,
        portfolio=portfolio,
        risk_gate=risk_gate,
        plan=plan,
        order_sizing_report=order_sizing_report,
        min_executable_capital_report=min_executable_capital_report,
        market_data_audit=market_data_audit,
        symbol_filters=symbol_filters,
        local_state_health=local_state_health,
        paper_execution=paper_execution,
    )
    state_store.write_json_row("decision_snapshots", "decision_id", snapshot.decision_id, snapshot.metadata())
    state_store.write_json_row("target_portfolios", "portfolio_id", portfolio.portfolio_id, portfolio.metadata())
    state_store.write_json_row("risk_gate_results", "risk_gate_id", risk_gate.risk_gate_id, risk_gate.to_dict())
    state_store.write_json_row("execution_plans", "plan_id", plan.plan_id, plan.metadata())
    if paper_execution is not None and paper_execution.status == "filled":
        state_store.record_paper_execution(paper_execution)
    paper_blockers = paper_execution.blockers if paper_execution is not None else []
    if mode == "plan_only" and risk_gate.passed and plan.status == "ok":
        status = "passed_plan_only"
    elif mode == "paper" and risk_gate.passed and plan.status == "ok" and not paper_blockers:
        status = "paper_executed"
    else:
        status = "blocked"
    summary = _summary(
        run_id=run_id,
        mode=mode,
        status=status,
        blockers=[*snapshot.blockers, *portfolio.blockers, *risk_gate.blockers, *plan.blockers, *paper_blockers],
        started_at=started,
        artifact_root=run_root,
        latest_decision_id=snapshot.decision_id,
        latest_portfolio_id=portfolio.portfolio_id,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status in {"passed_plan_only", "paper_executed"} else 2


def _operator_pause_status(operator_action: str) -> str:
    if operator_action == "kill-switch":
        return "operator_kill_switch_engaged"
    if operator_action == "pause":
        return "operator_paused"
    if operator_action == "arm-live-delta":
        return "operator_live_delta_armed"
    if operator_action == "disarm-live-delta":
        return "operator_live_delta_disarmed"
    return "operator_resumed"


def _operator_payload_from_arg(raw_value: Any) -> dict[str, Any]:
    raw = str(raw_value or "").strip()
    if not raw:
        return {}
    if raw.startswith("@"):
        payload_path = resolve_repo_path(raw[1:])
        loaded = json.loads(payload_path.read_text(encoding="utf-8"))
    elif raw.startswith("{"):
        loaded = json.loads(raw)
    else:
        candidate = resolve_repo_path(raw)
        if candidate.exists():
            loaded = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("operator_payload_json_must_be_object")
    return dict(loaded)


def _run_authorize_risk_only_reduce_cleanup(
    *,
    run_id: str,
    run_root: Path,
    started: datetime,
    state_store: LiveTradingStateStore,
    mode: str,
    operator_reason: str,
    operator_payload: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    payload = dict(operator_payload or {})
    canary = dict(payload.get("no_order_canary") or payload.get("risk_only_reduce_cleanup_no_order_canary") or {})
    slot_id = _payload_first_text(payload, canary, "slot_id", "rebalance_slot_id")
    target_hash = _payload_first_text(payload, canary, "target_hash", "rebalance_target_hash")
    budget_epoch_id = _payload_first_text(
        payload,
        canary,
        "budget_epoch_id",
        "unattended_budget_epoch_id",
        "expected_epoch_id",
        "epoch_id",
    )
    canary_status = _payload_first_text(
        payload,
        canary,
        "no_order_canary_status",
        "risk_only_reduce_cleanup_no_order_canary_status",
        "canary_status",
        "status",
    )
    canary_artifact_root = _payload_first_text(
        payload,
        canary,
        "no_order_canary_artifact_root",
        "risk_only_reduce_cleanup_no_order_canary_artifact_root",
        "artifact_root",
    )
    canary_run_id = _payload_first_text(payload, canary, "no_order_canary_run_id", "run_id")
    canary_passed = (
        _payload_optional_bool(
            payload,
            canary,
            "no_order_canary_passed",
            "risk_only_reduce_cleanup_no_order_canary_passed",
            "canary_passed",
        )
        is True
        or canary_status.strip().lower() in {"passed", "ready"}
    )
    orders_submitted = _payload_optional_int(payload, canary, "orders_submitted", "submitted_order_count")
    order_submission_authorized = _payload_optional_bool(
        payload,
        canary,
        "mainnet_order_submission_authorized",
        "live_delta_authorized",
    )
    if orders_submitted is not None and int(orders_submitted) != 0:
        canary_passed = False
    if order_submission_authorized is True:
        canary_passed = False

    blockers: list[str] = []
    if not slot_id:
        blockers.append("risk_only_reduce_cleanup_authorization_missing_slot_id")
    if not target_hash:
        blockers.append("risk_only_reduce_cleanup_authorization_missing_target_hash")
    if not budget_epoch_id:
        blockers.append("risk_only_reduce_cleanup_authorization_missing_budget_epoch")
    if not canary_passed:
        blockers.append("risk_only_reduce_cleanup_authorization_no_order_canary_missing_or_failed")
    if not canary_artifact_root and not canary_run_id:
        blockers.append("risk_only_reduce_cleanup_authorization_no_order_canary_artifact_missing")

    action_record = state_store.record_operator_action(
        run_id=run_id,
        action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
        reason=operator_reason,
        status="applied" if not blockers else "blocked",
        created_at_utc=started.isoformat().replace("+00:00", "Z"),
        payload={
            **payload,
            "slot_id": slot_id,
            "target_hash": target_hash,
            "budget_epoch_id": budget_epoch_id,
            "single_use": True,
            "risk_only_reduce_cleanup_authorized": not blockers,
            "no_order_canary": {
                **canary,
                "status": canary_status,
                "passed": bool(canary_passed),
                "artifact_root": canary_artifact_root,
                "run_id": canary_run_id,
                "orders_submitted": orders_submitted,
                "mainnet_order_submission_authorized": order_submission_authorized,
            },
            "mainnet_order_submission_authorized": False,
            "runner_never_submits_orders": True,
            "blockers": sorted(set(blockers)),
        },
    )
    write_json(run_root / "operator_action.json", action_record)
    summary = _summary(
        run_id=run_id,
        mode=mode,
        status="risk_only_reduce_cleanup_authorized" if not blockers else "blocked",
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if not blockers else 2


def _payload_first_text(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> str:
    for source in (primary, secondary):
        for key in keys:
            value = source.get(key)
            if isinstance(value, (list, tuple, set)):
                values = [str(item).strip() for item in value if str(item).strip()]
                if values:
                    return values[0]
            else:
                text = str(value or "").strip()
                if text:
                    return text
    return ""


def _payload_optional_bool(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> bool | None:
    for source in (primary, secondary):
        for key in keys:
            if key in source:
                value = source.get(key)
                if isinstance(value, bool):
                    return bool(value)
                return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "passed", "ready"}
    return None


def _payload_optional_int(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> int | None:
    for source in (primary, secondary):
        for key in keys:
            if key not in source:
                continue
            try:
                return int(float(source.get(key)))
            except (TypeError, ValueError):
                return None
    return None


def _run_force_reconcile(
    *,
    run_id: str,
    run_root: Path,
    started: datetime,
    state_store: LiveTradingStateStore,
    mode: str,
    local_state_health: dict[str, Any],
    operator_reason: str,
    max_heartbeat_age_seconds: float,
) -> tuple[dict[str, Any], int]:
    write_json(run_root / "local_state_health_before.json", dict(local_state_health or {}))
    recovered_heartbeats = state_store.recover_stale_running_heartbeats(
        now=started,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        recovery_run_id=run_id,
        reason=operator_reason,
        ignore_run_id=run_id,
    )
    local_state_health_after = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        ignore_run_id=run_id,
    )
    operator_state = state_store.read_operator_state()
    paper_positions = state_store.read_paper_positions()
    blockers = list(local_state_health_after.get("blockers") or [])
    reconcile_status = "reconciled" if not blockers else "reconcile_required"
    action_record = state_store.record_operator_action(
        run_id=run_id,
        action_type="force-reconcile",
        reason=operator_reason,
        status=reconcile_status,
        created_at_utc=started.isoformat().replace("+00:00", "Z"),
        payload={
            "mode": mode,
            "read_only": True,
            "exchange_order_submission": "disabled",
            "recovered_heartbeat_count": int(len(recovered_heartbeats)),
            "paper_open_position_count": int(len(paper_positions)),
            "blockers": blockers,
        },
    )
    reconciliation = {
        "status": reconcile_status,
        "blockers": sorted(set(blockers)),
        "mode": mode,
        "read_only": True,
        "exchange_order_submission": "disabled",
        "recovered_heartbeat_count": int(len(recovered_heartbeats)),
        "recovered_heartbeats": recovered_heartbeats,
        "operator_paused": bool(operator_state.get("paused")),
        "paper_open_position_count": int(len(paper_positions)),
        "paper_positions": paper_positions,
    }
    write_json(run_root / "operator_action.json", action_record)
    write_json(run_root / "operator_state.json", operator_state)
    write_json(run_root / "heartbeat_recovery.json", {"recovered_heartbeats": recovered_heartbeats})
    write_json(run_root / "local_state_health_after.json", local_state_health_after)
    write_json(run_root / "local_state_health.json", local_state_health_after)
    write_json(run_root / "account_before.json", {"mode": mode, "paper_positions": paper_positions})
    write_json(run_root / "account_after.json", {"mode": mode, "paper_positions": paper_positions})
    write_json(run_root / "reconciliation.json", reconciliation)
    pd.DataFrame(columns=["symbol", "side", "quantity", "client_order_id"]).to_csv(
        run_root / "submitted_orders.csv", index=False
    )
    pd.DataFrame(columns=["symbol", "side", "quantity", "price", "client_order_id"]).to_csv(
        run_root / "fills.csv", index=False
    )
    status = "forced_reconcile_completed" if reconcile_status == "reconciled" else "forced_reconcile_required"
    summary = _summary(
        run_id=run_id,
        mode=mode,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status == "forced_reconcile_completed" else 2


def _write_pipeline_artifacts(
    run_root: Path,
    *,
    snapshot: Any,
    portfolio: Any,
    risk_gate: Any,
    plan: Any,
    order_sizing_report: pd.DataFrame | None = None,
    min_executable_capital_report: dict[str, Any] | None = None,
    market_data_audit: dict[str, Any] | None = None,
    symbol_filters: dict[str, dict[str, Any]] | None = None,
    local_state_health: dict[str, Any] | None = None,
    paper_execution: PaperExecutionResult | None = None,
) -> None:
    write_json(run_root / "local_state_health.json", dict(local_state_health or {}))
    write_json(run_root / "market_data_audit.json", dict(market_data_audit or {}))
    write_json(run_root / "symbol_exchange_filters.json", dict(symbol_filters or {}))
    write_json(run_root / "decision_snapshot.json", snapshot.metadata())
    snapshot.scores.to_csv(run_root / "decision_scores.csv", index=False)
    write_json(run_root / "target_portfolio.json", portfolio.metadata())
    portfolio.positions_frame().to_csv(run_root / "target_positions.csv", index=False)
    write_json(run_root / "risk_gate.json", risk_gate.to_dict())
    if order_sizing_report is None:
        pd.DataFrame().to_csv(run_root / "order_sizing_report.csv", index=False)
    else:
        order_sizing_report.to_csv(run_root / "order_sizing_report.csv", index=False)
    write_json(
        run_root / "min_executable_capital_report.json",
        dict(min_executable_capital_report or {"status": "not_available", "blockers": []}),
    )
    write_json(run_root / "execution_plan.json", plan.metadata())
    plan.intents_frame().to_csv(run_root / "execution_plan.csv", index=False)
    if paper_execution is not None:
        write_json(run_root / "paper_execution.json", paper_execution.metadata())
        paper_execution.submitted_orders.to_csv(run_root / "submitted_orders.csv", index=False)
        paper_execution.fills.to_csv(run_root / "fills.csv", index=False)
        write_json(run_root / "account_before.json", paper_execution.account_before)
        write_json(run_root / "account_after.json", paper_execution.account_after)
        write_json(run_root / "reconciliation.json", paper_execution.reconciliation)
    else:
        pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
        pd.DataFrame().to_csv(run_root / "fills.csv", index=False)
        write_json(run_root / "account_before.json", {})
        write_json(run_root / "account_after.json", {})
        write_json(run_root / "reconciliation.json", {"status": "not_applicable_no_live_orders"})


def _run_operator_flatten_plan(
    *,
    args: argparse.Namespace,
    run_id: str,
    run_root: Path,
    started: datetime,
    state_store: LiveTradingStateStore,
    payload: dict[str, Any],
    frozen_config: dict[str, Any],
    config_sha: str,
    panel: pd.DataFrame,
    mode: str,
    market_data_audit: dict[str, Any],
    symbol_filters: dict[str, dict[str, Any]],
    local_state_health: dict[str, Any],
    operator_state: dict[str, Any],
    operator_reason: str,
) -> tuple[dict[str, Any], int]:
    blockers = list(local_state_health.get("blockers") or [])
    current_positions = state_store.read_paper_positions()
    decision_time_ms = _resolve_decision_time_ms(panel, str(getattr(args, "as_of", "now") or "now"))
    if decision_time_ms is None:
        blockers.append("as_of_before_available_panel")
        decision_time_ms = 0
    mark_prices = _latest_mark_prices(panel, decision_time_ms=decision_time_ms)
    if not current_positions:
        blockers.append("no_paper_positions_to_flatten")
    missing_prices = sorted(symbol for symbol in current_positions if symbol not in mark_prices)
    blockers.extend(f"missing_mark_price:{symbol}" for symbol in missing_prices)
    snapshot = LiveDecisionSnapshot(
        decision_id=f"operator_flatten:{int(decision_time_ms)}",
        strategy_label=str(frozen_config.get("strategy_label") or "hv_balanced_operator"),
        config_sha256=config_sha,
        decision_time_ms=int(decision_time_ms),
        decision_date_utc=datetime.fromtimestamp(int(decision_time_ms) / 1000, tz=UTC).date().isoformat()
        if decision_time_ms
        else "1970-01-01",
        rebalance_slot=False,
        input_bar_end_ms=int(decision_time_ms),
        status="ok" if not blockers else "blocked",
        blockers=blockers,
        scores=panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").eq(int(decision_time_ms))].copy(),
    )
    portfolio = TargetPortfolio(
        portfolio_id=f"{snapshot.decision_id}:portfolio",
        decision_id=snapshot.decision_id,
        strategy_label=snapshot.strategy_label,
        allocated_capital_usdt=float(dict(payload.get("capital") or {}).get("allocated_capital_usdt", 0.0) or 0.0),
        portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0,
        target_gross_weight=0.0,
        target_net_weight=0.0,
        status="ok" if not blockers else "blocked",
        blockers=blockers,
        positions=[],
    )
    risk_gate = evaluate_risk_gate(
        portfolio,
        mode=mode,
        config=payload,
        live_confirmed=bool(getattr(args, "i_understand_this_is_live", False)),
        local_state_health=local_state_health,
    )
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode=mode,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
    )
    action_record = state_store.record_operator_action(
        run_id=run_id,
        action_type="flatten-plan",
        reason=operator_reason,
        status="planned" if plan.status == "ok" else "blocked",
        created_at_utc=started.isoformat().replace("+00:00", "Z"),
        payload={
            "plan_id": plan.plan_id,
            "portfolio_id": plan.portfolio_id,
            "mode": plan.mode,
            "current_positions": current_positions,
            "mark_prices": mark_prices,
            "plan_intents": [intent.to_dict() for intent in plan.intents],
        },
    )
    write_json(run_root / "operator_action.json", action_record)
    write_json(run_root / "operator_state.json", operator_state)
    _write_pipeline_artifacts(
        run_root,
        snapshot=snapshot,
        portfolio=portfolio,
        risk_gate=risk_gate,
        plan=plan,
        market_data_audit=market_data_audit,
        symbol_filters=symbol_filters,
        local_state_health=local_state_health,
    )
    state_store.write_json_row("decision_snapshots", "decision_id", snapshot.decision_id, snapshot.metadata())
    state_store.write_json_row("target_portfolios", "portfolio_id", portfolio.portfolio_id, portfolio.metadata())
    state_store.write_json_row("risk_gate_results", "risk_gate_id", risk_gate.risk_gate_id, risk_gate.to_dict())
    state_store.write_json_row("execution_plans", "plan_id", plan.plan_id, plan.metadata())
    status = "flatten_plan_generated" if risk_gate.passed and plan.status == "ok" else "blocked"
    summary = _summary(
        run_id=run_id,
        mode=mode,
        status=status,
        blockers=[*snapshot.blockers, *portfolio.blockers, *risk_gate.blockers, *plan.blockers],
        started_at=started,
        artifact_root=run_root,
        latest_decision_id=snapshot.decision_id,
        latest_portfolio_id=portfolio.portfolio_id,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status == "flatten_plan_generated" else 2


def _run_confirm_flatten_plan(
    *,
    run_id: str,
    run_root: Path,
    started: datetime,
    state_store: LiveTradingStateStore,
    mode: str,
    local_state_health: dict[str, Any],
    confirm_plan_id: str,
    operator_reason: str,
) -> tuple[dict[str, Any], int]:
    blockers = list(local_state_health.get("blockers") or [])
    if not confirm_plan_id:
        blockers.append("missing_confirm_plan_id")
    planned = None
    if confirm_plan_id:
        planned = state_store.latest_operator_action(
            action_type="flatten-plan",
            status="planned",
            plan_id=confirm_plan_id,
        )
        if planned is None:
            blockers.append(f"flatten_plan_not_found_for_confirmation:{confirm_plan_id}")
    action_record = state_store.record_operator_action(
        run_id=run_id,
        action_type="confirm-flatten-plan",
        reason=operator_reason,
        status="confirmed" if not blockers else "blocked",
        created_at_utc=started.isoformat().replace("+00:00", "Z"),
        payload={
            "plan_id": confirm_plan_id,
            "planned_action_id": None if planned is None else planned.get("action_id"),
            "blockers": blockers,
        },
    )
    write_json(run_root / "operator_action.json", action_record)
    status = "flatten_plan_confirmed" if not blockers else "blocked"
    summary = _summary(
        run_id=run_id,
        mode=mode,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status == "flatten_plan_confirmed" else 2


def _run_execute_flatten_paper(
    *,
    run_id: str,
    run_root: Path,
    started: datetime,
    state_store: LiveTradingStateStore,
    mode: str,
    local_state_health: dict[str, Any],
    confirm_plan_id: str,
    operator_reason: str,
) -> tuple[dict[str, Any], int]:
    blockers = list(local_state_health.get("blockers") or [])
    if mode != "paper":
        blockers.append("execute_flatten_paper_requires_paper_mode")
    if not confirm_plan_id:
        blockers.append("missing_confirm_plan_id")
    planned = None
    confirmed = None
    if confirm_plan_id:
        planned = state_store.latest_operator_action(
            action_type="flatten-plan",
            status="planned",
            plan_id=confirm_plan_id,
        )
        confirmed = state_store.latest_operator_action(
            action_type="confirm-flatten-plan",
            status="confirmed",
            plan_id=confirm_plan_id,
        )
        if planned is None:
            blockers.append(f"flatten_plan_not_found_for_execution:{confirm_plan_id}")
        if confirmed is None:
            blockers.append(f"flatten_plan_confirmation_missing:{confirm_plan_id}")
        if state_store.has_paper_execution(confirm_plan_id):
            blockers.append(f"duplicate_paper_plan_already_executed:{confirm_plan_id}")
    plan = None
    current_positions = state_store.read_paper_positions()
    planned_positions = {}
    mark_prices = {}
    if planned is not None:
        planned_positions = {
            str(symbol): float(amount)
            for symbol, amount in dict(planned.get("current_positions") or {}).items()
            if abs(float(amount)) > 1e-12
        }
        mark_prices = {str(symbol): float(price) for symbol, price in dict(planned.get("mark_prices") or {}).items()}
        blockers.extend(_position_mismatch_blockers(planned_positions, current_positions))
        intent_rows = [dict(row) for row in list(planned.get("plan_intents") or [])]
        if not intent_rows:
            blockers.append("flatten_plan_has_no_intents")
        if any(not bool(row.get("reduce_only")) for row in intent_rows):
            blockers.append("flatten_plan_contains_non_reduce_only_intent")
        if not blockers:
            plan = ExecutionPlan(
                plan_id=str(planned["plan_id"]),
                portfolio_id=str(planned.get("portfolio_id") or "operator_flatten:portfolio"),
                mode="paper",
                status="ok",
                blockers=[],
                intents=[OrderIntent(**row) for row in intent_rows],
            )
    paper_execution: PaperExecutionResult | None = None
    if not blockers and plan is not None:
        paper_execution = simulate_paper_execution(
            plan,
            mark_prices=mark_prices,
            run_id=run_id,
            created_at_utc=started.isoformat().replace("+00:00", "Z"),
            current_positions=current_positions,
        )
        blockers.extend(paper_execution.blockers)
    action_record = state_store.record_operator_action(
        run_id=run_id,
        action_type="execute-flatten-paper",
        reason=operator_reason,
        status="executed" if not blockers else "blocked",
        created_at_utc=started.isoformat().replace("+00:00", "Z"),
        payload={
            "plan_id": confirm_plan_id,
            "planned_action_id": None if planned is None else planned.get("action_id"),
            "confirmed_action_id": None if confirmed is None else confirmed.get("action_id"),
            "blockers": blockers,
        },
    )
    write_json(run_root / "operator_action.json", action_record)
    if paper_execution is not None and not blockers:
        write_json(run_root / "paper_execution.json", paper_execution.metadata())
        paper_execution.submitted_orders.to_csv(run_root / "submitted_orders.csv", index=False)
        paper_execution.fills.to_csv(run_root / "fills.csv", index=False)
        write_json(run_root / "account_before.json", paper_execution.account_before)
        write_json(run_root / "account_after.json", paper_execution.account_after)
        write_json(run_root / "reconciliation.json", paper_execution.reconciliation)
        if plan is not None:
            write_json(run_root / "execution_plan.json", plan.metadata())
            plan.intents_frame().to_csv(run_root / "execution_plan.csv", index=False)
        state_store.record_paper_execution(paper_execution)
    else:
        pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
        pd.DataFrame().to_csv(run_root / "fills.csv", index=False)
        write_json(run_root / "account_before.json", {"mode": "paper", "positions": current_positions})
        write_json(run_root / "account_after.json", {})
        write_json(run_root / "reconciliation.json", {"status": "paper_flatten_blocked", "blockers": sorted(set(blockers))})
        if plan is not None:
            write_json(run_root / "execution_plan.json", plan.metadata())
            plan.intents_frame().to_csv(run_root / "execution_plan.csv", index=False)
    status = "flatten_paper_executed" if not blockers else "blocked"
    summary = _summary(
        run_id=run_id,
        mode=mode,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
    )
    _persist_summary(run_root, state_store, summary)
    return summary, 0 if status == "flatten_paper_executed" else 2


def _summary(
    *,
    run_id: str,
    mode: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    latest_decision_id: str | None = None,
    latest_portfolio_id: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": mode,
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "latest_decision_id": latest_decision_id,
        "latest_portfolio_id": latest_portfolio_id,
        "artifact_root": str(artifact_root),
    }


def _persist_summary(run_root: Path, state_store: LiveTradingStateStore, summary: dict[str, Any]) -> None:
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", str(summary["run_id"]), summary)
    state_store.write_heartbeat(
        run_id=str(summary["run_id"]),
        mode=str(summary["mode"]),
        status=str(summary["status"]),
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(summary["artifact_root"]),
        blockers=list(summary.get("blockers") or []),
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


def _latest_mark_prices(panel: pd.DataFrame, *, decision_time_ms: int) -> dict[str, float]:
    if panel.empty:
        return {}
    rows = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").eq(int(decision_time_ms))]
    output: dict[str, float] = {}
    for _, row in rows.iterrows():
        symbol = str(row.get("usdm_symbol") or "").strip()
        if not symbol:
            continue
        price = float(pd.to_numeric(pd.Series([row.get("perp_close")]), errors="coerce").fillna(0.0).iloc[0])
        if price > 0.0:
            output[symbol] = price
    return output


def _position_mismatch_blockers(planned_positions: dict[str, float], current_positions: dict[str, float]) -> list[str]:
    blockers: list[str] = []
    symbols = sorted(set(planned_positions) | set(current_positions))
    for symbol in symbols:
        planned = float(planned_positions.get(symbol, 0.0) or 0.0)
        current = float(current_positions.get(symbol, 0.0) or 0.0)
        if abs(planned - current) > 1e-12:
            blockers.append(f"paper_position_changed_since_flatten_plan:{symbol}")
    return blockers


if __name__ == "__main__":
    raise SystemExit(main())
