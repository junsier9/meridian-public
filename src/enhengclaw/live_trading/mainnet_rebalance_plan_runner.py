from __future__ import annotations

import argparse
import copy
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
)
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.daily_rebalance_slot_gate import (
    FROZEN_TARGET_SNAPSHOT_ARTIFACT,
    REBALANCE_SLOT_POST_FILL_CLEANUP_ACTION,
    REBALANCE_SLOT_REEXECUTION_ACTION,
    REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
    REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
    apply_frozen_snapshot_to_portfolio,
    build_frozen_target_snapshot,
    completed_slot_execution_gate,
    hold_execution_plan,
    target_position_overrides,
    target_reference_prices,
)
from enhengclaw.live_trading.execution_planner import (
    build_execution_plan,
    build_order_sizing_report,
    summarize_order_sizing_report,
    summarize_dust_residual_order_sizing,
)
from enhengclaw.live_trading.frozen_frontier_live import (
    FRONTIER_PLAN_ARTIFACT,
    FrontierResolution,
    resolve_live_frontier,
)
from enhengclaw.live_trading.hv_balanced_live_signal import (
    augment_panel_with_overlay_shock_gauges,
    build_live_hv_balanced_snapshot,
    file_sha256,
    is_rebalance_slot,
    load_frozen_config,
)
from enhengclaw.live_trading.live_pit_universe import (
    LIVE_UNIVERSE_ARTIFACT,
    LIVE_UNIVERSE_SCHEMA,
    MODE_PIT_ROLLING,
    apply_live_pit_universe,
    evaluate_universe_churn_gate,
    find_prior_live_universe_artifact,
    resolve_live_universe_policy,
    write_universe_change_log,
)
from enhengclaw.live_trading.market_data import (
    fetch_live_spot_close_frame,
    fetch_public_live_feature_panel,
    parse_symbol_exchange_filters,
    resolve_config_symbols,
)
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.unattended_budget_hook import budget_gate_enabled, budget_store_from_payload
from enhengclaw.live_trading.wallet_compounding_policy import (
    V2_FLAG as WALLET_V2_FLAG,
    resolve_effective_caps,
)
from enhengclaw.quant_research.contracts import write_json


SINGLE_PHASE_TARGET_ENGINE = "single_phase"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Current-position-aware mainnet rebalance plan gate. "
            "It reads live positions and writes a delta execution plan, but never submits orders."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public data.")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--api-key-env", default="", help="Override API key environment variable name.")
    parser.add_argument("--api-secret-env", default="", help="Override API secret environment variable name.")
    parser.add_argument(
        "--capital-topup",
        action="store_true",
        help=(
            "Generate a no-order capital top-up plan from the latest closed rebalance slot. "
            "This scales current target weights to fresh wallet capital and blocks reduce/flip/exit deltas."
        ),
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_current_position_rebalance_plan(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_current_position_rebalance_plan(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    market_client_factory: Callable[..., Any] = BinanceUsdmClient,
    account_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml"))
    payload = live_config.payload
    capital_topup_requested = bool(getattr(args, "capital_topup", False))
    run_kind = "mainnet-capital-topup-plan" if capital_topup_requested else "mainnet-rebalance-plan"
    run_dir = "mainnet_capital_topup_plan" if capital_topup_requested else "mainnet_rebalance_plan"
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-{run_kind}"
    run_root = live_config.artifact_root.parent / run_dir / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    blockers = _config_blockers(payload)
    credentials = _credential_context(payload=payload, args=args, env=env or os.environ)
    blockers.extend(credentials["blockers"])
    account_snapshot = {"status": "not_run", "blockers": list(blockers)}
    capital_allocation_context = {"status": "not_run", "capital_topup_requested": bool(capital_topup_requested), "blockers": []}
    capital_topup_gate = {"status": "not_requested", "blockers": [], "warnings": []}
    current_positions: dict[str, float] = {}
    current_mark_prices: dict[str, float] = {}
    current_symbol_filters: dict[str, dict[str, Any]] = {}
    if not blockers:
        account_client = _build_mainnet_client(credentials, account_client_factory)
        permission_client = _build_permission_client(credentials, permission_client_factory)
        account_snapshot = _account_snapshot(
            account_client,
            permission_client=permission_client,
            expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
            expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
            max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
        )
        blockers.extend(account_snapshot["blockers"])
        current_positions = {
            str(row["symbol"]): float(row["positionAmt"])
            for row in list(account_snapshot.get("open_positions_redacted") or [])
        }
        current_mark_prices = {
            str(row["symbol"]): float(row.get("markPrice") or 0.0)
            for row in list(account_snapshot.get("open_positions_redacted") or [])
            if float(row.get("markPrice") or 0.0) > 0.0
        }
        current_symbol_filters = _safe_exchange_filters(account_client, symbols=sorted(current_positions))
    write_json(run_root / "account_snapshot.json", account_snapshot)
    write_json(run_root / "capital_allocation_context.json", capital_allocation_context)
    write_json(run_root / "capital_topup_gate.json", capital_topup_gate)
    pd.DataFrame(list(account_snapshot.get("open_positions_redacted") or [])).to_csv(run_root / "current_positions.csv", index=False)
    if blockers:
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            warnings=[],
            started_at=started,
            artifact_root=run_root,
            latest_decision_id=None,
            latest_portfolio_id=None,
            current_positions=current_positions,
            planned_order_count=0,
            submitted_order_count=0,
            fill_count=0,
            risk_gate_status="not_run",
            execution_plan_status="not_run",
        )
        _write_empty_strategy_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    frozen_path = live_config.strategy_config_path
    frozen_config = load_frozen_config(frozen_path)
    config_sha = file_sha256(frozen_path)
    expected_sha = str(dict(payload.get("strategy") or {}).get("frozen_config_sha256") or "").strip()
    if expected_sha and expected_sha != config_sha:
        blockers.append(f"frozen_config_sha256_mismatch:expected={expected_sha}:actual={config_sha}")

    # Frozen 12-factor frontier resolution (default-off). Persist the verdict for the
    # arm→submit binding, and fail closed if it is armed-but-invalid.
    frontier = resolve_live_frontier(live_config, payload)
    write_json(run_root / FRONTIER_PLAN_ARTIFACT, frontier.to_artifact())
    if frontier.is_blocked:
        blockers.extend(f"frontier:{item}" for item in (frontier.blockers or ["unspecified"]))

    panel, market_data_audit, symbol_filters = _load_panel(
        args=args,
        payload=payload,
        frozen_config=frozen_config,
        market_client_factory=market_client_factory,
        frontier=frontier,
    )
    symbol_filters = {**current_symbol_filters, **symbol_filters}
    market_data_audit = _apply_live_universe_churn_gate(
        run_root=run_root,
        run_id=run_id,
        market_data_audit=market_data_audit,
    )
    write_json(run_root / "market_data_audit.json", market_data_audit)
    write_json(run_root / "symbol_exchange_filters.json", symbol_filters)
    # Fail closed on any armed-frontier feature-assembly failure (sidecar import/exception/partial,
    # spot outage). Empty for default-off (helper not invoked) => baseline blocker flow unchanged.
    blockers.extend(f"frontier_feature:{item}" for item in (market_data_audit.get("frontier_feature_blockers") or []))
    # Fail closed on any PIT rolling universe gate (size != top_n, un-admitted symbol, invalid
    # policy). Empty for default-off => baseline blocker flow unchanged.
    blockers.extend(f"universe:{item}" for item in (market_data_audit.get("universe_blockers") or []))
    if market_data_audit.get("live_universe"):
        write_json(run_root / LIVE_UNIVERSE_ARTIFACT, market_data_audit["live_universe"])
        # Read-only day-over-day universe churn trail (traceability only; best-effort, never fed
        # back into selection and never able to crash/block the run). Drift PREVENTION is the
        # live_universe.json copy bound into plan_hash at submit; this is the audit view.
        write_universe_change_log(
            run_root=run_root, run_id=run_id, live_universe=market_data_audit["live_universe"]
        )
    if panel.empty:
        blockers.append("empty_market_data_panel")
    if "timestamp_ms" not in panel.columns:
        blockers.append("market_data_panel_missing_timestamp_ms")
    strategy_cfg = dict(payload.get("strategy") or {})
    rebalance_interval_days = int(strategy_cfg.get("rebalance_interval_days", 10) or 10)
    rebalance_epoch_ms = int(strategy_cfg.get("rebalance_epoch_ms", 0) or 0)
    decision_time_context = (
        _resolve_decision_time_context(
            panel,
            _requested_as_of(args=args, capital_topup_requested=capital_topup_requested),
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
        )
        if "timestamp_ms" in panel.columns
        else {"decision_time_ms": None, "blockers": ["market_data_panel_missing_timestamp_ms"]}
    )
    write_json(run_root / "decision_time_context.json", decision_time_context)
    decision_time_ms = decision_time_context.get("decision_time_ms")
    if decision_time_ms is None:
        blockers.extend(str(item) for item in list(decision_time_context.get("blockers") or []))
        if not list(decision_time_context.get("blockers") or []):
            blockers.append("as_of_before_available_panel")
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            warnings=[],
            started_at=started,
            artifact_root=run_root,
            latest_decision_id=None,
            latest_portfolio_id=None,
            current_positions=current_positions,
            planned_order_count=0,
            submitted_order_count=0,
            fill_count=0,
            risk_gate_status="not_run",
            execution_plan_status="not_run",
        )
        _write_empty_strategy_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    capital_allocation_context = _resolve_capital_allocation_context(
        payload=payload,
        account_snapshot=account_snapshot,
        capital_topup_requested=capital_topup_requested,
    )
    write_json(run_root / "capital_allocation_context.json", capital_allocation_context)
    blockers.extend(str(item) for item in list(capital_allocation_context.get("blockers") or []))
    if blockers:
        if capital_topup_requested and list(capital_allocation_context.get("blockers") or []):
            capital_topup_gate = {
                "status": "blocked",
                "blockers": list(capital_allocation_context.get("blockers") or []),
                "warnings": list(capital_allocation_context.get("warnings") or []),
            }
            write_json(run_root / "capital_topup_gate.json", capital_topup_gate)
        summary = _summary(
            run_id=run_id,
            status="blocked",
            blockers=blockers,
            warnings=[],
            started_at=started,
            artifact_root=run_root,
            latest_decision_id=None,
            latest_portfolio_id=None,
            current_positions=current_positions,
            planned_order_count=0,
            submitted_order_count=0,
            fill_count=0,
            risk_gate_status="not_run",
            execution_plan_status="not_run",
            open_order_count=int(account_snapshot.get("open_order_count") or 0),
            capital_allocation_context=capital_allocation_context,
            capital_topup_gate=capital_topup_gate,
        )
        _write_empty_strategy_artifacts(run_root)
        write_json(run_root / "run_summary.json", summary)
        return summary, 2

    panel = panel.loc[pd.to_numeric(panel["timestamp_ms"], errors="coerce").le(int(decision_time_ms))].copy()
    snapshot = build_live_hv_balanced_snapshot(
        panel,
        config=frozen_config,
        config_sha256=config_sha,
        decision_time_ms=int(decision_time_ms),
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
        frontier=frontier,
    )
    portfolio_config = frontier.effective_config if (frontier.is_armed_ready and frontier.effective_config) else frozen_config
    portfolio = build_target_portfolio(
        snapshot,
        config=portfolio_config,
        allocated_capital_usdt=float(capital_allocation_context.get("resolved_allocated_capital_usdt") or 0.0),
    )
    risk_payload = _risk_payload_plan_only(payload, capital_allocation_context=capital_allocation_context)
    risk_gate = evaluate_risk_gate(
        portfolio,
        mode="plan_only",
        config=risk_payload,
        live_confirmed=False,
    )
    mark_prices = {**current_mark_prices, **_mark_prices(snapshot.scores)}
    execution_deadband = dict(payload.get("execution_deadband") or {})
    order_sizing_report = build_order_sizing_report(
        portfolio,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
    )
    min_capital_report = summarize_order_sizing_report(
        order_sizing_report,
        allocated_capital_usdt=portfolio.allocated_capital_usdt,
    )
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
        allow_live_order_submission=False,
    )
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    decision_metadata = snapshot.metadata()
    candidate_frozen_snapshot = build_frozen_target_snapshot(
        target_engine=SINGLE_PHASE_TARGET_ENGINE,
        portfolio=portfolio,
        order_sizing_report=order_sizing_report,
        capital_allocation_context=capital_allocation_context,
        decision_metadata=decision_metadata,
        created_at=started,
    )
    stored_frozen_snapshot = state_store.read_rebalance_slot_target(str(candidate_frozen_snapshot["slot_id"]))
    frozen_slot_gate = {
        "status": "freeze_new_slot_target",
        "slot_id": str(candidate_frozen_snapshot["slot_id"]),
        "candidate_target_hash": str(candidate_frozen_snapshot["target_hash"]),
        "active_target_hash": str(candidate_frozen_snapshot["target_hash"]),
        "blockers": [],
        "warnings": [],
    }
    if stored_frozen_snapshot is None:
        frozen_target_snapshot = state_store.write_rebalance_slot_target(candidate_frozen_snapshot)
    else:
        frozen_target_snapshot = dict(stored_frozen_snapshot)
        frozen_slot_gate.update(
            {
                "status": "reuse_frozen_slot_target",
                "active_target_hash": str(frozen_target_snapshot.get("target_hash") or ""),
                "stored_status": str(frozen_target_snapshot.get("status") or ""),
            }
        )
        if str(frozen_target_snapshot.get("target_hash") or "") != str(candidate_frozen_snapshot.get("target_hash") or ""):
            frozen_slot_gate["warnings"] = [
                "same_slot_candidate_target_drift_ignored_in_favor_of_frozen_snapshot"
            ]
    portfolio = apply_frozen_snapshot_to_portfolio(portfolio, frozen_target_snapshot)
    capital_allocation_context = _capital_context_with_resolved_allocated_capital(
        capital_allocation_context,
        resolved_allocated_capital_usdt=float(frozen_target_snapshot.get("resolved_capital_usdt") or 0.0),
    )
    capital_allocation_context["frozen_rebalance_slot_target"] = {
        "slot_id": str(frozen_target_snapshot.get("slot_id") or ""),
        "target_hash": str(frozen_target_snapshot.get("target_hash") or ""),
        "status": str(frozen_target_snapshot.get("status") or ""),
    }
    risk_payload = _risk_payload_plan_only(payload, capital_allocation_context=capital_allocation_context)
    risk_gate = evaluate_risk_gate(
        portfolio,
        mode="plan_only",
        config=risk_payload,
        live_confirmed=False,
    )
    frozen_target_positions = target_position_overrides(frozen_target_snapshot)
    frozen_reference_prices = target_reference_prices(frozen_target_snapshot)
    order_sizing_report = build_order_sizing_report(
        portfolio,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
        target_position_overrides=frozen_target_positions,
        target_reference_prices=frozen_reference_prices,
    )
    min_capital_report = summarize_order_sizing_report(
        order_sizing_report,
        allocated_capital_usdt=portfolio.allocated_capital_usdt,
    )
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
        target_position_overrides=frozen_target_positions,
        target_reference_prices=frozen_reference_prices,
        allow_live_order_submission=False,
    )
    if dict(frozen_target_snapshot).get("completed_at_utc"):
        frozen_slot_gate["completed_at_utc"] = frozen_target_snapshot.get("completed_at_utc")
    slot_id = str(frozen_target_snapshot.get("slot_id") or "")
    target_hash = str(frozen_target_snapshot.get("target_hash") or "")
    completed_gate = completed_slot_execution_gate(
        slot_record=frozen_target_snapshot,
        plan=plan,
        reexecution_authorization=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_REEXECUTION_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        post_fill_cleanup_authorization=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_POST_FILL_CLEANUP_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        risk_only_reduce_cleanup_authorization=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        risk_only_reduce_cleanup_consumed=state_store.latest_operator_action(
            action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        ),
        current_budget_epoch_id=_current_unattended_budget_epoch_id(payload),
    )
    frozen_slot_gate["completed_slot_execution_gate"] = completed_gate
    if bool(completed_gate.get("hold_until_next_rebalance_slot")):
        plan = hold_execution_plan(plan)
        frozen_slot_gate["status"] = "hold_until_next_rebalance_slot"
    write_json(run_root / FROZEN_TARGET_SNAPSHOT_ARTIFACT, frozen_target_snapshot)
    write_json(run_root / "frozen_slot_gate.json", frozen_slot_gate)
    write_json(run_root / "capital_allocation_context.json", capital_allocation_context)
    capital_topup_gate_requested = _capital_topup_gate_requested(
        payload=payload,
        explicit_requested=capital_topup_requested,
        capital_allocation_context=capital_allocation_context,
        plan=plan,
    )
    capital_topup_gate = _capital_topup_plan_gate(
        payload=payload,
        requested=capital_topup_gate_requested,
        capital_allocation_context=capital_allocation_context,
        order_sizing_report=order_sizing_report,
        plan=plan,
    )
    write_json(run_root / "capital_topup_gate.json", capital_topup_gate)
    dust_delta_summary = summarize_dust_residual_order_sizing(order_sizing_report)
    capital_deployment_deferred = str(capital_topup_gate.get("status") or "") == "deferred"
    plan_hard_blockers = list(plan.blockers)
    dust_delta_only = (
        bool(dust_delta_summary.get("is_dust_residual_only"))
        and not plan.intents
        and (not plan.blockers or sorted(set(plan.blockers)) == sorted(set(dust_delta_summary.get("dust_blockers") or [])))
    )
    if dust_delta_only:
        plan.status = "dust_noop"
        plan.blockers = list(dust_delta_summary.get("dust_blockers") or [])
        plan_hard_blockers = []
    normalized_dust_delta_summary = dict(dust_delta_summary)
    if not dust_delta_only:
        normalized_dust_delta_summary["is_dust_residual_only"] = False
    blockers.extend([*snapshot.blockers, *portfolio.blockers, *risk_gate.blockers, *plan_hard_blockers])
    blockers.extend(str(item) for item in list(capital_topup_gate.get("blockers") or []))
    warnings = list(risk_gate.warnings)
    warnings.extend(str(item) for item in list(capital_topup_gate.get("warnings") or []))
    if dust_delta_only:
        warnings.append("dust_delta_noop:all_delta_orders_below_min_order_constraints")
    warnings.extend(str(item) for item in list(frozen_slot_gate.get("warnings") or []))
    runtime_gate_context = {
        "mode": "mainnet_current_position_rebalance_plan_gate",
        "plan_only": True,
        "current_position_aware": True,
        "frozen_rebalance_slot_target": True,
        "mainnet_order_submission_authorized": False,
        "recurring_mainnet_authorized": False,
        "config_trading_enabled": bool(dict(payload.get("risk") or {}).get("trading_enabled", False)),
        "requested_as_of": decision_time_context.get("requested_as_of"),
        "resolved_as_of_mode": decision_time_context.get("resolved_as_of_mode"),
        "resolved_decision_time_ms": decision_time_context.get("decision_time_ms"),
        "resolved_decision_date_utc": decision_time_context.get("decision_date_utc"),
        "dust_delta_summary": dust_delta_summary,
        "capital_allocation_context": capital_allocation_context,
        "capital_topup_gate": capital_topup_gate,
        "frozen_slot_gate": frozen_slot_gate,
    }
    _write_strategy_artifacts(
        run_root,
        snapshot=snapshot,
        portfolio=portfolio,
        risk_gate=risk_gate,
        order_sizing_report=order_sizing_report,
        min_capital_report=min_capital_report,
        plan=plan,
        runtime_gate_context=runtime_gate_context,
    )
    status = "mainnet_current_position_rebalance_plan_ready" if not blockers else "blocked"
    if not blockers and capital_deployment_deferred:
        status = "mainnet_current_position_rebalance_deferred"
    if not blockers and not plan.intents:
        if str(plan.status) == "hold_until_next_rebalance_slot":
            status = "mainnet_current_position_rebalance_hold_until_next_rebalance_slot"
        else:
            status = (
                "mainnet_current_position_rebalance_dust_noop"
                if dust_delta_only
                else "mainnet_current_position_rebalance_noop"
            )
    summary = _summary(
        run_id=run_id,
        status=status,
        blockers=blockers,
        warnings=warnings,
        started_at=started,
        artifact_root=run_root,
        latest_decision_id=snapshot.decision_id,
        latest_portfolio_id=portfolio.portfolio_id,
        current_positions=current_positions,
        planned_order_count=len(plan.intents),
        submitted_order_count=0,
        fill_count=0,
        risk_gate_status="passed" if risk_gate.passed else "blocked",
        execution_plan_status=plan.status,
        active_execution_phase=plan.active_execution_phase,
        phase_counts=plan.phase_counts,
        deferred_phase_counts=plan.deferred_phase_counts,
        dust_delta_summary=normalized_dust_delta_summary,
        reduce_only_intent_count=sum(1 for intent in plan.intents if intent.reduce_only),
        non_reduce_only_intent_count=sum(1 for intent in plan.intents if not intent.reduce_only),
        target_position_count=len(portfolio.positions),
        open_order_count=int(account_snapshot.get("open_order_count") or 0),
        capital_allocation_context=capital_allocation_context,
        capital_topup_gate=capital_topup_gate,
        frozen_slot_gate=frozen_slot_gate,
    )
    write_json(run_root / "run_summary.json", summary)
    return summary, 0 if status in {
        "mainnet_current_position_rebalance_plan_ready",
        "mainnet_current_position_rebalance_noop",
        "mainnet_current_position_rebalance_dust_noop",
        "mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
        "mainnet_current_position_rebalance_deferred",
    } else 2


def _requested_as_of(*, args: argparse.Namespace, capital_topup_requested: bool) -> str:
    raw = str(getattr(args, "as_of", "now") or "now").strip()
    if capital_topup_requested and raw.lower() in {"", "now"}:
        return "latest_closed_rebalance_slot"
    return raw or "now"


def _current_unattended_budget_epoch_id(payload: dict[str, Any]) -> str | None:
    if not budget_gate_enabled(payload):
        return None
    try:
        epoch = budget_store_from_payload(payload).read_current_epoch()
    except Exception:
        return ""
    return epoch.epoch_id if epoch is not None else ""


def _first_optional_float(*values: Any) -> float | None:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return float(parsed)
    return None


def _target_sizing_buffer_context(
    *,
    section: dict[str, Any],
    payload: dict[str, Any],
    risk: dict[str, Any],
    fallback_section: dict[str, Any] | None = None,
    legacy_dynamic_key: str | None = None,
) -> dict[str, Any]:
    fallback = dict(fallback_section or {})
    explicit_margin = _first_optional_float(
        section.get("target_margin_safety_buffer_usdt"),
        fallback.get("target_margin_safety_buffer_usdt"),
    )
    explicit_operating = _first_optional_float(
        section.get("target_operating_buffer_usdt"),
        fallback.get("target_operating_buffer_usdt"),
    )
    if explicit_margin is not None or explicit_operating is not None:
        deployment = dict(payload.get("capital_deployment") or {})
        margin = explicit_margin
        if margin is None:
            margin = _first_optional_float(
                deployment.get("margin_safety_buffer_usdt"),
                risk.get("min_margin_cushion_after_plan_usdt"),
                risk.get("min_available_balance_after_plan_usdt"),
                risk.get("min_available_balance_usdt"),
            )
        operating = explicit_operating if explicit_operating is not None else 0.0
        margin = max(0.0, float(margin or 0.0))
        operating = max(0.0, float(operating or 0.0))
        return {
            "reserve_available_balance_usdt": float(margin + operating),
            "target_margin_safety_buffer_usdt": float(margin),
            "target_operating_buffer_usdt": float(operating),
            "target_sizing_buffer_source": "target_margin_safety_plus_operating_buffer",
            "target_sizing_formula": (
                "(total_wallet_balance_usdt - target_margin_safety_buffer_usdt "
                "- target_operating_buffer_usdt) * sizing_multiplier "
                "- gross_notional_safety_buffer_usdt"
            ),
        }

    reserve = _first_optional_float(section.get("reserve_available_balance_usdt"))
    source = "legacy_reserve_available_balance"
    if reserve is None and legacy_dynamic_key:
        reserve = _first_optional_float(section.get(legacy_dynamic_key))
        if reserve is not None:
            source = f"legacy_{legacy_dynamic_key}"
    if reserve is None:
        reserve = _first_optional_float(risk.get("min_margin_cushion_after_plan_usdt"))
        if reserve is not None:
            source = "legacy_risk_min_margin_cushion_after_plan"
    return {
        "reserve_available_balance_usdt": float(reserve or 0.0),
        "target_margin_safety_buffer_usdt": 0.0,
        "target_operating_buffer_usdt": 0.0,
        "target_sizing_buffer_source": source,
        "target_sizing_formula": (
            "(total_wallet_balance_usdt - reserve_available_balance_usdt) "
            "* sizing_multiplier - gross_notional_safety_buffer_usdt"
        ),
    }


def _resolve_capital_allocation_context(
    *,
    payload: dict[str, Any],
    account_snapshot: dict[str, Any],
    capital_topup_requested: bool,
) -> dict[str, Any]:
    capital = dict(payload.get("capital") or {})
    topup = dict(payload.get("capital_topup") or {})
    risk = dict(payload.get("risk") or {})
    baseline = _float(capital.get("allocated_capital_usdt"))
    total_wallet = _float(account_snapshot.get("total_wallet_balance_usdt"))
    available = _float(account_snapshot.get("available_balance_usdt"))
    if not capital_topup_requested:
        sizing_basis = str(capital.get("sizing_basis") or "static_allocated_capital_usdt").strip()
        multiplier = _capital_sizing_multiplier(sizing_basis, capital=capital, topup=capital)
        if multiplier > 0.0:
            blockers: list[str] = []
            warnings: list[str] = []
            if total_wallet <= 0.0:
                blockers.append("capital_dynamic_total_wallet_balance_not_positive")
            buffer_context = _target_sizing_buffer_context(
                section=capital,
                payload=payload,
                risk=risk,
                legacy_dynamic_key="dynamic_reserve_available_balance_usdt",
            )
            reserve_available = float(buffer_context["reserve_available_balance_usdt"])
            gross_safety = _optional_float(capital.get("gross_notional_safety_buffer_usdt"))
            if gross_safety is None:
                gross_safety = _optional_float(capital.get("safety_buffer_usdt"))
            gross_safety = float(gross_safety or 0.0)
            raw_resolved = max(0.0, (float(total_wallet) - reserve_available) * float(multiplier) - gross_safety)
            max_allocated = _optional_float(capital.get("max_allocated_capital_usdt"))
            resolved = min(raw_resolved, float(max_allocated)) if max_allocated is not None and max_allocated > 0.0 else raw_resolved
            min_allocated = _optional_float(capital.get("min_allocated_capital_usdt"))
            if min_allocated is not None and resolved < float(min_allocated):
                blockers.append(f"capital_dynamic_resolved_allocated_below_min:{resolved}<{float(min_allocated)}")
            return {
                "status": "blocked" if blockers else "dynamic_config",
                "capital_topup_requested": False,
                "capital_dynamic_requested": True,
                "blockers": sorted(set(blockers)),
                "warnings": sorted(set(warnings)),
                "sizing_basis": sizing_basis,
                "sizing_multiplier": float(multiplier),
                "baseline_allocated_capital_usdt": float(baseline),
                "raw_resolved_allocated_capital_usdt": float(raw_resolved),
                "capped_resolved_allocated_capital_usdt": float(resolved),
                "resolved_allocated_capital_usdt": float(resolved),
                "raw_additional_allocated_capital_usdt": float(resolved - baseline),
                "additional_allocated_capital_usdt": float(resolved - baseline),
                "total_wallet_balance_usdt": float(total_wallet),
                "available_balance_usdt": float(available),
                "reserve_available_balance_usdt": float(reserve_available),
                "target_margin_safety_buffer_usdt": float(buffer_context["target_margin_safety_buffer_usdt"]),
                "target_operating_buffer_usdt": float(buffer_context["target_operating_buffer_usdt"]),
                "target_sizing_buffer_source": str(buffer_context["target_sizing_buffer_source"]),
                "target_sizing_formula": str(buffer_context["target_sizing_formula"]),
                "gross_notional_safety_buffer_usdt": float(gross_safety),
                "dynamic_risk_caps_from_resolved_capital": _as_bool(
                    capital.get("dynamic_risk_caps_from_resolved_capital"),
                    default=True,
                ),
            }
        return {
            "status": "static_config",
            "capital_topup_requested": False,
            "capital_dynamic_requested": False,
            "blockers": [],
            "warnings": [],
            "sizing_basis": sizing_basis,
            "baseline_allocated_capital_usdt": float(baseline),
            "resolved_allocated_capital_usdt": float(baseline),
            "additional_allocated_capital_usdt": 0.0,
            "total_wallet_balance_usdt": float(total_wallet),
            "available_balance_usdt": float(available),
        }
    blockers: list[str] = []
    warnings: list[str] = []
    if not _as_bool(topup.get("enabled"), default=False):
        blockers.append("capital_topup_disabled_in_config")
    sizing_basis = str(topup.get("sizing_basis") or capital.get("sizing_basis") or "static_allocated_capital_usdt").strip()
    multiplier = _capital_sizing_multiplier(sizing_basis, capital=capital, topup=topup)
    if multiplier <= 0.0:
        blockers.append(f"capital_topup_unsupported_sizing_basis:{sizing_basis or 'missing'}")
    if total_wallet <= 0.0:
        blockers.append("capital_topup_total_wallet_balance_not_positive")
    buffer_context = _target_sizing_buffer_context(
        section=topup,
        payload=payload,
        risk=risk,
        fallback_section=capital,
    )
    reserve_available = float(buffer_context["reserve_available_balance_usdt"])
    gross_safety = _optional_float(topup.get("gross_notional_safety_buffer_usdt"))
    if gross_safety is None:
        gross_safety = _optional_float(topup.get("safety_buffer_usdt"))
    gross_safety = float(gross_safety or 0.0)
    raw_resolved = max(0.0, (float(total_wallet) - reserve_available) * float(multiplier) - gross_safety)
    max_allocated = _optional_float(topup.get("max_allocated_capital_usdt"))
    if max_allocated is not None and max_allocated > 0.0:
        capped_resolved = min(raw_resolved, float(max_allocated))
    else:
        capped_resolved = raw_resolved
    min_allocated = _optional_float(topup.get("min_allocated_capital_usdt"))
    if min_allocated is not None and capped_resolved < float(min_allocated):
        blockers.append(f"capital_topup_resolved_allocated_below_min:{capped_resolved}<{float(min_allocated)}")
    raw_additional = float(capped_resolved - baseline)
    resolved = float(capped_resolved)
    additional = float(raw_additional)
    min_additional = _optional_float(topup.get("min_additional_allocated_capital_usdt"))
    if min_additional is not None and raw_additional > 0.0 and raw_additional < float(min_additional):
        warnings.append(f"capital_topup_additional_allocated_below_min:{raw_additional}<{float(min_additional)}")
        resolved = float(baseline)
        additional = 0.0
    if raw_additional <= 0.0:
        warnings.append(f"capital_topup_no_additional_allocated_capital:{raw_additional}")
        resolved = float(baseline)
        additional = 0.0
    return {
        "status": "blocked" if blockers else "capital_topup_resolved",
        "capital_topup_requested": True,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "sizing_basis": sizing_basis,
        "sizing_multiplier": float(multiplier),
        "baseline_allocated_capital_usdt": float(baseline),
        "raw_resolved_allocated_capital_usdt": float(raw_resolved),
        "capped_resolved_allocated_capital_usdt": float(capped_resolved),
        "resolved_allocated_capital_usdt": float(resolved),
        "raw_additional_allocated_capital_usdt": float(raw_additional),
        "additional_allocated_capital_usdt": float(additional),
        "total_wallet_balance_usdt": float(total_wallet),
        "available_balance_usdt": float(available),
        "reserve_available_balance_usdt": float(reserve_available),
        "target_margin_safety_buffer_usdt": float(buffer_context["target_margin_safety_buffer_usdt"]),
        "target_operating_buffer_usdt": float(buffer_context["target_operating_buffer_usdt"]),
        "target_sizing_buffer_source": str(buffer_context["target_sizing_buffer_source"]),
        "target_sizing_formula": str(buffer_context["target_sizing_formula"]),
        "gross_notional_safety_buffer_usdt": float(gross_safety),
        "dynamic_risk_caps_from_resolved_capital": _as_bool(topup.get("dynamic_risk_caps_from_resolved_capital"), default=True),
    }


def _capital_context_with_resolved_allocated_capital(
    context: dict[str, Any],
    *,
    resolved_allocated_capital_usdt: float,
) -> dict[str, Any]:
    updated = dict(context)
    baseline = _float(updated.get("baseline_allocated_capital_usdt"))
    resolved = float(resolved_allocated_capital_usdt)
    updated["resolved_allocated_capital_usdt"] = resolved
    updated["additional_allocated_capital_usdt"] = float(resolved - baseline)
    return updated


def _capital_topup_plan_gate(
    *,
    payload: dict[str, Any],
    requested: bool,
    capital_allocation_context: dict[str, Any],
    order_sizing_report: pd.DataFrame,
    plan: Any,
) -> dict[str, Any]:
    if not requested:
        return {"status": "not_requested", "blockers": [], "warnings": []}
    topup = dict(payload.get("capital_topup") or {})
    allowed = _csv_set(
        topup.get("allowed_delta_classifications")
        or "increase_same_side,new_entry,rebalance_deadband,dust_residual,no_delta"
    )
    blockers: list[str] = []
    warnings = list(capital_allocation_context.get("warnings") or [])
    rows = [dict(row) for _, row in order_sizing_report.iterrows()] if not order_sizing_report.empty else []
    disallowed: list[str] = []
    reduce_like: list[str] = []
    target_symbols: list[str] = []
    executable_entry_symbols: list[str] = []
    dust_symbols: list[str] = []
    incomplete_entry: list[str] = []
    require_balanced_all_or_none = _as_bool(topup.get("require_balanced_all_or_none"), default=True)
    allow_dust_noop_in_all_or_none = _as_bool(
        topup.get("allow_dust_residual_noop_in_all_or_none"), default=False
    )
    additional_allocated = _float(capital_allocation_context.get("additional_allocated_capital_usdt"))
    deployment = dict(payload.get("capital_deployment") or {})
    deployment_enabled = _as_bool(deployment.get("enabled"), default=False)
    for row in rows:
        symbol = _cell_str(row.get("symbol"))
        classification = _cell_str(row.get("delta_classification"))
        phase = _cell_str(row.get("execution_phase"))
        reduce_only = _as_bool(row.get("reduce_only"), default=False)
        has_target = _as_bool(row.get("has_target"), default=False)
        executable = _as_bool(row.get("executable"), default=False)
        no_order_required = _as_bool(row.get("no_order_required"), default=False)
        row_blockers = _cell_str(row.get("blockers"))
        if has_target:
            target_symbols.append(symbol)
        if classification not in allowed and classification not in {"blocked"}:
            disallowed.append(f"{symbol}:{classification}")
        if classification != "dust_residual" and (
            phase == "reduce_first"
            or reduce_only
            or classification in {"reduce_same_side", "flip_position", "exit_stale_symbol", "exit_target_removed"}
        ):
            reduce_like.append(f"{symbol}:{classification or phase}")
        if has_target and classification == "dust_residual":
            dust_symbols.append(symbol)
        if has_target and classification in {"increase_same_side", "new_entry"}:
            if executable and phase == "entry_second" and not no_order_required:
                executable_entry_symbols.append(symbol)
            else:
                reason = row_blockers or phase or "not_executable"
                incomplete_entry.append(f"{symbol}:{classification}:{reason}")
        elif has_target and classification == "blocked":
            incomplete_entry.append(f"{symbol}:blocked:{row_blockers or 'blocked'}")
    deployment_gate = _capital_deployment_gate(
        payload=payload,
        rows=rows,
        capital_allocation_context=capital_allocation_context,
        additional_allocated_usdt=additional_allocated,
        executable_entry_symbols=executable_entry_symbols,
        dust_symbols=dust_symbols,
        incomplete_entry=incomplete_entry,
        require_balanced_all_or_none=require_balanced_all_or_none,
    )
    if disallowed:
        blockers.append(f"capital_topup_disallowed_delta_classification:{','.join(sorted(set(disallowed)))}")
    if reduce_like:
        blockers.append(f"capital_topup_disallows_reduce_flip_exit:{','.join(sorted(set(reduce_like)))}")
    if require_balanced_all_or_none and additional_allocated > 0.0 and executable_entry_symbols:
        if dust_symbols and not allow_dust_noop_in_all_or_none:
            dust_blocker = f"capital_topup_all_or_none_dust_residual_leg:{','.join(sorted(set(dust_symbols)))}"
            if not (
                deployment_enabled
                and _as_bool(deployment.get("defer_if_all_or_none_has_dust_leg"), default=False)
            ):
                blockers.append(dust_blocker)
        if incomplete_entry:
            blockers.append(f"capital_topup_all_or_none_incomplete_entry:{','.join(sorted(set(incomplete_entry)))}")
    active_phase = str(getattr(plan, "active_execution_phase", "") or "")
    if active_phase not in {"entry_second", "noop", "dust_noop", "deadband_noop"}:
        blockers.append(f"capital_topup_requires_entry_second_or_noop_active_phase:{active_phase or 'missing'}")
    if any(bool(getattr(intent, "reduce_only", False)) for intent in list(getattr(plan, "intents", []) or [])):
        blockers.append("capital_topup_plan_contains_reduce_only_intents")
    defer_reasons = list(deployment_gate.get("defer_reasons") or [])
    if defer_reasons:
        warnings.append(f"capital_deployment_deferred:{','.join(defer_reasons)}")
    status = "passed"
    if blockers:
        status = "blocked"
    elif defer_reasons:
        status = "deferred"
    return {
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "allowed_delta_classifications": sorted(allowed),
        "active_execution_phase": active_phase,
        "planned_delta_order_count": int(len(list(getattr(plan, "intents", []) or []))),
        "reduce_like_row_count": int(len(reduce_like)),
        "disallowed_row_count": int(len(disallowed)),
        "require_balanced_all_or_none": bool(require_balanced_all_or_none),
        "allow_dust_residual_noop_in_all_or_none": bool(allow_dust_noop_in_all_or_none),
        "target_leg_count": int(len(set(target_symbols))),
        "executable_entry_leg_count": int(len(set(executable_entry_symbols))),
        "dust_leg_count": int(len(set(dust_symbols))),
        "incomplete_entry_leg_count": int(len(set(incomplete_entry))),
        "executable_entry_symbols": sorted(set(executable_entry_symbols)),
        "dust_symbols": sorted(set(dust_symbols)),
        "deployment_gate": deployment_gate,
        "deferred": status == "deferred",
        "defer_status": str(
            deployment.get("defer_status") or "entry_second_all_or_none_deferred_for_margin_or_dust"
        ),
        "defer_reasons": sorted(set(defer_reasons)),
    }


def _capital_deployment_gate(
    *,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    capital_allocation_context: dict[str, Any],
    additional_allocated_usdt: float,
    executable_entry_symbols: list[str],
    dust_symbols: list[str],
    incomplete_entry: list[str],
    require_balanced_all_or_none: bool,
) -> dict[str, Any]:
    deployment = dict(payload.get("capital_deployment") or {})
    if not _as_bool(deployment.get("enabled"), default=False):
        return {"status": "not_configured", "enabled": False, "blockers": [], "defer_reasons": []}
    risk = dict(payload.get("risk") or {})
    available = _float(capital_allocation_context.get("available_balance_usdt"))
    wallet = _float(capital_allocation_context.get("total_wallet_balance_usdt"))
    configured_buffer = _optional_float(deployment.get("margin_safety_buffer_usdt"))
    min_abs = _optional_float(risk.get("min_available_balance_after_plan_usdt", risk.get("min_available_balance_usdt")))
    min_cushion = _optional_float(risk.get("min_margin_cushion_after_plan_usdt"))
    min_ratio = _optional_float(risk.get("min_available_balance_ratio_after_plan"))
    candidates = [0.0]
    for value in (configured_buffer, min_abs, min_cushion):
        if value is not None:
            candidates.append(float(value))
    if min_ratio is not None and wallet > 0.0:
        candidates.append(float(min_ratio) * wallet)
    required_buffer = max(candidates)
    surplus = max(0.0, available - required_buffer)
    min_surplus = _optional_float(deployment.get("min_deployable_surplus_usdt"))
    min_surplus = float(min_surplus or 0.0)
    max_fraction = _optional_float(deployment.get("max_deploy_fraction_of_surplus"))
    max_fraction = 1.0 if max_fraction is None else max(0.0, min(1.0, float(max_fraction)))
    deployable_budget = surplus * max_fraction
    planned_margin = _planned_entry_initial_margin_from_rows(rows=rows, payload=payload)
    post_available = available - planned_margin
    defer_reasons: list[str] = []
    if additional_allocated_usdt > 0.0 and executable_entry_symbols:
        if surplus < min_surplus:
            defer_reasons.append(f"deployable_surplus_below_min:{surplus}<{min_surplus}")
        if planned_margin > deployable_budget:
            defer_reasons.append(
                f"planned_entry_initial_margin_exceeds_deployable_budget:{planned_margin}>{deployable_budget}"
            )
        if (
            _as_bool(deployment.get("defer_if_post_plan_available_below_buffer"), default=True)
            and post_available < required_buffer
        ):
            defer_reasons.append(f"post_plan_available_below_margin_safety_buffer:{post_available}<{required_buffer}")
        if (
            require_balanced_all_or_none
            and dust_symbols
            and _as_bool(deployment.get("defer_if_all_or_none_has_dust_leg"), default=False)
        ):
            defer_reasons.append(f"all_or_none_dust_residual_leg:{','.join(sorted(set(dust_symbols)))}")
        if require_balanced_all_or_none and incomplete_entry and _as_bool(
            deployment.get("defer_if_all_or_none_incomplete_entry"), default=False
        ):
            defer_reasons.append(f"all_or_none_incomplete_entry:{','.join(sorted(set(incomplete_entry)))}")
    return {
        "status": "deferred" if defer_reasons else "passed",
        "enabled": True,
        "blockers": [],
        "defer_reasons": sorted(set(defer_reasons)),
        "margin_safety_buffer_usdt": configured_buffer,
        "required_margin_safety_buffer_usdt": float(required_buffer),
        "available_balance_usdt": float(available),
        "total_wallet_balance_usdt": float(wallet),
        "deployable_surplus_usdt": float(surplus),
        "min_deployable_surplus_usdt": float(min_surplus),
        "max_deploy_fraction_of_surplus": float(max_fraction),
        "deployable_budget_usdt": float(deployable_budget),
        "planned_entry_initial_margin_usdt": float(planned_margin),
        "post_plan_available_balance_usdt": float(post_available),
        "defer_if_post_plan_available_below_buffer": _as_bool(
            deployment.get("defer_if_post_plan_available_below_buffer"), default=True
        ),
        "defer_if_all_or_none_has_dust_leg": _as_bool(
            deployment.get("defer_if_all_or_none_has_dust_leg"), default=False
        ),
    }


def _planned_entry_initial_margin_from_rows(*, rows: list[dict[str, Any]], payload: dict[str, Any]) -> float:
    leverage = int(float(dict(payload.get("binance") or {}).get("max_leverage") or 0))
    divisor = float(leverage) if leverage > 0 else 1.0
    total = 0.0
    for row in rows:
        if _cell_str(row.get("execution_phase")) != "entry_second":
            continue
        if _as_bool(row.get("reduce_only"), default=False) or _as_bool(row.get("no_order_required"), default=False):
            continue
        if not _as_bool(row.get("executable"), default=False):
            continue
        total += max(0.0, _float(row.get("rounded_notional_usdt"))) / divisor
    return float(total)


def _capital_topup_gate_requested(
    *,
    payload: dict[str, Any],
    explicit_requested: bool,
    capital_allocation_context: dict[str, Any],
    plan: Any,
) -> bool:
    if explicit_requested:
        return True
    if not bool(capital_allocation_context.get("capital_dynamic_requested")):
        return False
    topup = dict(payload.get("capital_topup") or {})
    if not _as_bool(topup.get("enabled"), default=False):
        return False
    if not _as_bool(topup.get("enforce_all_or_none_for_dynamic_entries"), default=True):
        return False
    active_phase = str(getattr(plan, "active_execution_phase", "") or "").strip().lower()
    return active_phase in {"entry_second", "noop", "dust_noop", "deadband_noop"}


def _capital_sizing_multiplier(sizing_basis: str, *, capital: dict[str, Any], topup: dict[str, Any]) -> float:
    normalized = str(sizing_basis or "").strip().lower()
    if normalized in {"static", "static_allocated_capital_usdt"}:
        return 0.0
    if normalized in {"total_wallet_balance_usdt_x_2", "total_wallet_balance_x_2"}:
        return 2.0
    if normalized in {"total_wallet_balance_usdt_x_max_gross_leverage", "total_wallet_balance_x_max_gross_leverage"}:
        return _float(topup.get("max_gross_leverage") or capital.get("max_gross_leverage") or 0.0)
    marker = "total_wallet_balance_usdt_x_"
    if normalized.startswith(marker):
        return _float(normalized[len(marker):])
    return 0.0


def _live_universe_policy_config(
    *,
    frozen_config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    live_policy = payload.get("universe_policy")
    if not isinstance(live_policy, Mapping) or not live_policy:
        return frozen_config

    scoped = copy.deepcopy(frozen_config)
    merged_policy = dict(scoped.get("universe_policy") or {})
    merged_policy.update(copy.deepcopy(dict(live_policy)))
    scoped["universe_policy"] = merged_policy
    return scoped


def _load_panel(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    frozen_config: dict[str, Any],
    market_client_factory: Callable[..., Any],
    frontier: FrontierResolution | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]:
    fixture_panel = str(getattr(args, "fixture_panel", "") or "").strip()
    if fixture_panel:
        return pd.read_csv(resolve_repo_path(fixture_panel)), {"source": "fixture_panel"}, {}
    market_data = dict(payload.get("market_data") or {})
    if not (bool(market_data.get("public_data_enabled", False)) or bool(getattr(args, "public_market_data", False))):
        return pd.DataFrame(), {"source": "missing_public_market_data_flag"}, {}
    market_client = market_client_factory(base_url=BINANCE_USDM_MAINNET_BASE_URL)
    # Live universe selector (DEFAULT-OFF). With universe_policy.live_selection_mode absent
    # or 'fixed' this is byte-for-byte the existing per-day cross-sectional top-N over the
    # hand-pinned market_data.symbols. ONLY an explicit 'pit_rolling' opts into the
    # hash-pinned candidate allowlist (operator-admitted superset) the PIT roll selects from.
    live_universe_config = _live_universe_policy_config(frozen_config=frozen_config, payload=payload)
    universe_policy = resolve_live_universe_policy(live_universe_config)
    if universe_policy.is_pit_rolling:
        symbols = list(universe_policy.candidate_symbols)
    else:
        symbols = resolve_config_symbols(payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    panel, market_data_audit, symbol_filters = fetch_public_live_feature_panel(
        client=market_client,
        config=live_universe_config,
        symbols=symbols,
        daily_limit=int(market_data.get("daily_limit", 140) or 140),
        four_hour_limit=int(market_data.get("four_hour_limit", 840) or 840),
    )
    # PIT rolling universe re-mark + fail-closed gate. Default-OFF (is_fixed) => not reached,
    # so the (panel, audit, filters) tuple stays byte-identical to the baseline path.
    if not universe_policy.is_fixed:
        panel, market_data_audit = _append_live_pit_universe(
            panel=panel,
            audit=market_data_audit,
            resolution=universe_policy,
            decision_time_ms=_pit_universe_decision_time_ms(panel=panel, args=args, payload=payload),
        )
    # Default-OFF: ONLY an ARMED frontier extends the panel. Mirror the scorer's own gate
    # (is_armed_ready) — a blocked/dormant/None frontier (incl. blocked-but-overlay-configured,
    # which carries overlay_enabled=True) leaves the (panel, audit, filters) tuple byte-identical.
    if frontier is not None and frontier.is_armed_ready:
        panel, market_data_audit = _append_frontier_live_features(
            panel=panel,
            audit=market_data_audit,
            args=args,
            payload=payload,
            symbols=symbols,
            market_client_factory=market_client_factory,
            frontier=frontier,
        )
    return panel, market_data_audit, symbol_filters


def _pit_universe_decision_time_ms(
    *,
    panel: pd.DataFrame,
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> int | None:
    """Resolve the exact decision row the runner will score, so the PIT universe size /
    new-symbol gate + binding anchor on it (not just the latest bar). Reuses the same pure
    ``_resolve_decision_time_context`` / ``_requested_as_of`` the runner uses; returns None
    (=> gate falls back to the latest bar) when the panel has no timestamps yet."""
    if panel.empty or "timestamp_ms" not in panel.columns:
        return None
    strategy_cfg = dict(payload.get("strategy") or {})
    context = _resolve_decision_time_context(
        panel,
        _requested_as_of(args=args, capital_topup_requested=bool(getattr(args, "capital_topup", False))),
        rebalance_interval_days=int(strategy_cfg.get("rebalance_interval_days", 10) or 10),
        rebalance_epoch_ms=int(strategy_cfg.get("rebalance_epoch_ms", 0) or 0),
    )
    value = context.get("decision_time_ms")
    return None if value is None else int(value)


def _append_live_pit_universe(
    *,
    panel: pd.DataFrame,
    audit: dict[str, Any],
    resolution: Any,
    decision_time_ms: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """PIT rolling universe re-mark (default-off; only reached for a pit_rolling/blocked policy).

    Mirrors the armed-frontier extension pattern: every fail-closed reason is appended to
    ``audit['universe_blockers']`` (the runner merges them as ``universe:<blocker>``), the
    deterministic binding goes to ``audit['live_universe']``, and the panel is returned
    unchanged on any failure — never crashes, never silently scores a stale per-day marking."""
    audit = dict(audit or {})
    if resolution.is_blocked:
        audit["universe_blockers"] = list(resolution.blockers)
        audit["live_universe"] = {
            "schema": LIVE_UNIVERSE_SCHEMA,
            "status": "blocked",
            "live_selection_mode": MODE_PIT_ROLLING,
            "blockers": list(resolution.blockers),
        }
        return panel, audit
    try:
        result = apply_live_pit_universe(panel, resolution=resolution, decision_time_ms=decision_time_ms)
    except Exception as exc:  # defence-in-depth: an unexpected failure must fail closed.
        blockers = [f"pit_universe_exception:{exc.__class__.__name__}"]
        audit["universe_blockers"] = blockers
        audit["live_universe"] = {
            "schema": LIVE_UNIVERSE_SCHEMA,
            "status": "blocked",
            "live_selection_mode": MODE_PIT_ROLLING,
            "blockers": blockers,
        }
        return panel, audit
    audit["universe_blockers"] = list(result.blockers)
    audit["live_universe"] = result.artifact
    return result.panel, audit


def _apply_live_universe_churn_gate(
    *,
    run_root: Path,
    run_id: str,
    market_data_audit: dict[str, Any],
) -> dict[str, Any]:
    audit = dict(market_data_audit or {})
    live_universe = audit.get("live_universe")
    if not isinstance(live_universe, dict) or not live_universe:
        return audit
    prior = find_prior_live_universe_artifact(run_root=run_root, run_id=run_id)
    churn_gate = evaluate_universe_churn_gate(current=live_universe, prior=prior)
    live_universe = dict(live_universe)
    live_universe["churn_gate_verdict"] = churn_gate
    existing_blockers = [str(item) for item in list(audit.get("universe_blockers") or [])]
    existing_blockers.extend(str(item) for item in list(churn_gate.get("blockers") or []))
    live_universe["blockers"] = sorted(
        set(
            str(item)
            for item in list(live_universe.get("blockers") or [])
            + list(churn_gate.get("blockers") or [])
        )
    )
    if churn_gate.get("status") == "blocked":
        live_universe["status"] = "blocked"
    audit["live_universe"] = live_universe
    audit["universe_blockers"] = sorted(set(existing_blockers))
    audit["universe_churn_gate"] = churn_gate
    return audit


def _import_append_live_12factor_sidecars() -> Callable[..., Any]:
    """Lazy import seam for the proven p10a sidecar builder. It lives under scripts/ (no package
    __init__, excluded from the wheel), so a module-top import would crash an unattended runner
    launched from outside the repo root. Isolated here so the caller can fail closed on ImportError
    and so tests can patch it. Raises on import failure — the caller MUST catch."""
    from scripts.live_trading.run_hv_balanced_12factor_p10a_pit_safe_live_feature_builder import (
        append_live_12factor_sidecars,
    )

    return append_live_12factor_sidecars


# The 12-factor multiphase aggregate scores len(PHASES)=10 staggered sleeves spanning the last
# ~10 decision days, and the hourly CoinGlass factor coinglass_taker_imb_intraday_dispersion_24h
# is computed from a trailing 24h window of hourly data. The historical p10a default (3 days) only
# yields ~2 eligible decision days, so 8/10 sleeves SILENTLY fail closed at arm time (the multiphase
# snapshot blocks with no_decision_eligible_rows). The hourly lookback must cover the full sleeve
# span + the 24h dispersion window + slack for the latest-closed-bar / provider lag. Overridable via
# strategy.frontier.sidecar.sidecar_hour_lookback_days; fail-closed if ever still insufficient.
_MULTIPHASE_SLEEVE_SPAN_DAYS = 10  # must match len(mainnet_multiphase_target_shadow.PHASES)
_FRONTIER_SIDECAR_HOUR_LOOKBACK_DEFAULT_DAYS = _MULTIPHASE_SLEEVE_SPAN_DAYS + 4


def _frontier_sidecar_args(args: argparse.Namespace, payload: dict[str, Any]) -> argparse.Namespace:
    """Build the Namespace the p10a sidecar path reads (all via getattr(...,default), so only the
    settlement-warmup override matters). Sidecar config may be tuned under
    strategy.frontier.sidecar.* in the live YAML."""
    sidecar_cfg = dict(dict(dict(payload.get("strategy") or {}).get("frontier") or {}).get("sidecar") or {})
    return argparse.Namespace(
        config=str(getattr(args, "config", "") or ""),
        symbols=str(getattr(args, "symbols", "") or ""),
        mode="live-binance-public",
        base_url=BINANCE_USDM_MAINNET_BASE_URL,
        request_timeout_seconds=float(sidecar_cfg.get("request_timeout_seconds", 20.0) or 20.0),
        coinglass_request_sleep_seconds=float(sidecar_cfg.get("coinglass_request_sleep_seconds", 0.03) or 0.03),
        settlement_lookback_days=int(sidecar_cfg.get("settlement_lookback_days", 125) or 125),
        settlement_hour_limit=int(sidecar_cfg.get("settlement_hour_limit", 1000) or 1000),
        settlement_page_limit=int(sidecar_cfg.get("settlement_page_limit", 5) or 5),
        settlement_request_sleep_seconds=float(sidecar_cfg.get("settlement_request_sleep_seconds", 0.05) or 0.05),
        settlement_request_max_attempts=int(sidecar_cfg.get("settlement_request_max_attempts", 3) or 3),
        settlement_request_retry_sleep_seconds=float(
            sidecar_cfg.get("settlement_request_retry_sleep_seconds", 0.25) or 0.25
        ),
        sidecar_lookback_days=int(sidecar_cfg.get("sidecar_lookback_days", 70) or 70),
        sidecar_hour_lookback_days=int(
            sidecar_cfg.get("sidecar_hour_lookback_days", _FRONTIER_SIDECAR_HOUR_LOOKBACK_DEFAULT_DAYS)
            or _FRONTIER_SIDECAR_HOUR_LOOKBACK_DEFAULT_DAYS
        ),
        # Research parity: the frozen frontier was fit on the research (perp-spot)/spot basis, so the
        # live funding_basis_residual must use the same source (NOT the live premiumIndex, which leaves
        # a ~0.0028 gap). Overridable via strategy.frontier.sidecar.funding_basis_source.
        funding_basis_source=str(sidecar_cfg.get("funding_basis_source", "perp_spot") or "perp_spot"),
        availability_lag_seconds=int(sidecar_cfg.get("availability_lag_seconds", 60) or 60),
        # #9: fail closed on PARTIAL CoinGlass coverage. Default to requiring ALL symbols so a
        # silent partial fetch (e.g. 19/20 on a timeout) BLOCKS the cycle instead of trading a
        # degraded universe whose factor balance no longer matches the frozen 20-symbol frontier.
        # Explicitly overridable (incl. a lower value) via strategy.frontier.sidecar.min_symbol_coverage.
        min_symbol_coverage=float(
            1.0 if sidecar_cfg.get("min_symbol_coverage") is None else sidecar_cfg.get("min_symbol_coverage")
        ),
    )


def _frontier_decision_time(args: argparse.Namespace) -> datetime:
    """Provisional sidecar decision-time. NEVER feed the runner's semantic --as-of modes
    (e.g. 'latest_closed_rebalance_slot') to the builder's parser — use an ISO --as-of if given,
    else now()."""
    as_of = str(getattr(args, "as_of", "now") or "now").strip()
    if as_of and as_of.lower() != "now":
        try:
            return datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def _append_frontier_live_features(
    *,
    panel: pd.DataFrame,
    audit: dict[str, Any],
    args: argparse.Namespace,
    payload: dict[str, Any],
    symbols: list[str],
    market_client_factory: Callable[..., Any],
    frontier: FrontierResolution,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Armed-frontier panel extension (default-off; only reached when frontier.is_armed_ready):
      1. 12-factor derivatives sidecars (4 CoinGlass + settlement) via a GUARDED fail-closed import;
      2. spot_close fetch + dth60 overlay shock gauges, only when the overlay is enabled.
    Every failure path appends a blocker (surfaced under audit['frontier_feature_blockers'], which
    the runner merges into its decision blockers) and returns the panel UNCHANGED — never crashes,
    never zero-fills. A missing factor column ALSO fails closed independently in
    build_live_hv_balanced_snapshot (missing_feature_columns / frontier_overlay_gauge_columns_missing)."""
    audit = dict(audit or {})
    blockers: list[str] = []

    try:
        append_live_12factor_sidecars = _import_append_live_12factor_sidecars()
    except Exception as exc:  # ImportError in an unattended/installed context, etc.
        blockers.append("sidecar_builder_import_unavailable")
        audit["frontier_sidecars"] = {
            "status": "blocked",
            "blockers": ["sidecar_builder_import_unavailable"],
            "exception_type": exc.__class__.__name__,
        }
        audit["frontier_feature_blockers"] = blockers
        return panel, audit

    try:
        panel, sidecar_audit = append_live_12factor_sidecars(
            panel=panel,
            symbols=list(symbols),
            decision_time=_frontier_decision_time(args),
            args=_frontier_sidecar_args(args, payload),
            now_fn=lambda: datetime.now(UTC),
        )
    except Exception as exc:
        blockers.append(f"sidecar_builder_exception:{exc.__class__.__name__}")
        audit["frontier_sidecars"] = {"status": "blocked", "exception_type": exc.__class__.__name__}
        audit["frontier_feature_blockers"] = blockers
        return panel, audit
    audit["frontier_sidecars"] = sidecar_audit
    # Partial sidecar failure (some symbols NaN) marks the builder audit blocked — propagate it so
    # the run fails closed rather than silently scoring the surviving symbol subset.
    blockers.extend(str(item) for item in (sidecar_audit.get("blockers") or []))

    if frontier.overlay_enabled:
        daily_limit = int(dict(payload.get("market_data") or {}).get("daily_limit", 140) or 140)
        try:
            spot = fetch_live_spot_close_frame(
                client=market_client_factory(base_url=BINANCE_SPOT_MAINNET_BASE_URL),
                symbols=list(symbols),
                daily_limit=daily_limit,
            )
        except Exception as exc:
            spot = pd.DataFrame(columns=["subject", "date_utc", "spot_close"])
            blockers.append(f"spot_close_fetch_exception:{exc.__class__.__name__}")
        if not spot.empty and {"subject", "date_utc"}.issubset(panel.columns):
            panel = panel.merge(spot, on=["subject", "date_utc"], how="left")
        # The gauge is research-defined on spot_close; without it augment fails closed (returns the
        # panel unchanged). Flag it so a spot outage forces a blocked run instead of a silent skip.
        if "spot_close" not in panel.columns:
            blockers.append("frontier_overlay_spot_close_unavailable")
        panel = augment_panel_with_overlay_shock_gauges(panel)
        audit["overlay_shock_gauges_augmented"] = "shock_co_occurrence_index" in panel.columns

    audit["frontier_feature_blockers"] = blockers
    return panel, audit


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
            blockers.append(f"mainnet_rebalance_requires_one_way_position_side:{symbol}:{row.get('positionSide')}")
        margin_type = str(row.get("marginType") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            blockers.append(f"margin_type_mismatch:{symbol}:expected={expected_margin_type}:actual={margin_type or 'missing'}")
        leverage = int(_float(row.get("leverage")))
        if max_allowed_leverage > 0 and leverage > max_allowed_leverage:
            blockers.append(f"leverage_above_max:{symbol}:max={max_allowed_leverage}:actual={leverage}")
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


def _write_strategy_artifacts(
    run_root: Path,
    *,
    snapshot: Any,
    portfolio: Any,
    risk_gate: Any,
    order_sizing_report: pd.DataFrame,
    min_capital_report: dict[str, Any],
    plan: Any,
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


def _write_empty_strategy_artifacts(run_root: Path) -> None:
    write_json(run_root / "runtime_gate_context.json", {"plan_only": True, "mainnet_order_submission_authorized": False})
    write_json(run_root / "decision_snapshot.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "decision_scores.csv", index=False)
    write_json(run_root / "target_portfolio.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "target_positions.csv", index=False)
    write_json(run_root / "risk_gate.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "order_sizing_report.csv", index=False)
    write_json(run_root / "min_executable_capital_report.json", {"status": "not_run"})
    write_json(run_root / "execution_plan.json", {"status": "not_run"})
    pd.DataFrame().to_csv(run_root / "execution_plan.csv", index=False)
    pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "fills.csv", index=False)


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    warnings: list[str],
    started_at: datetime,
    artifact_root: Path,
    latest_decision_id: str | None,
    latest_portfolio_id: str | None,
    current_positions: dict[str, float],
    planned_order_count: int,
    submitted_order_count: int,
    fill_count: int,
    risk_gate_status: str,
    execution_plan_status: str,
    active_execution_phase: str = "",
    phase_counts: dict[str, int] | None = None,
    deferred_phase_counts: dict[str, int] | None = None,
    dust_delta_summary: dict[str, Any] | None = None,
    reduce_only_intent_count: int = 0,
    non_reduce_only_intent_count: int = 0,
    target_position_count: int = 0,
    open_order_count: int = 0,
    capital_allocation_context: dict[str, Any] | None = None,
    capital_topup_gate: dict[str, Any] | None = None,
    frozen_slot_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capital_context = dict(capital_allocation_context or {})
    topup_gate = dict(capital_topup_gate or {})
    slot_gate = dict(frozen_slot_gate or {})
    return {
        "run_id": run_id,
        "mode": "live",
        "environment": "mainnet",
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "artifact_root": str(artifact_root),
        "latest_decision_id": latest_decision_id,
        "latest_portfolio_id": latest_portfolio_id,
        "current_position_aware": True,
        "plan_only": True,
        "mainnet_order_submission_authorized": False,
        "recurring_mainnet_enabled": False,
        "orders_submitted": int(submitted_order_count),
        "fill_count": int(fill_count),
        "open_order_count": int(open_order_count),
        "current_position_count": int(sum(1 for value in current_positions.values() if abs(float(value)) > 1e-12)),
        "target_position_count": int(target_position_count),
        "planned_delta_order_count": int(planned_order_count),
        "reduce_only_intent_count": int(reduce_only_intent_count),
        "non_reduce_only_intent_count": int(non_reduce_only_intent_count),
        "risk_gate_status": risk_gate_status,
        "execution_plan_status": execution_plan_status,
        "active_execution_phase": active_execution_phase,
        "phase_counts": dict(phase_counts or {}),
        "deferred_phase_counts": dict(deferred_phase_counts or {}),
        "dust_delta_noop": bool(dict(dust_delta_summary or {}).get("is_dust_residual_only")),
        "dust_delta_symbols": list(dict(dust_delta_summary or {}).get("dust_symbols") or []),
        "dust_delta_blockers": list(dict(dust_delta_summary or {}).get("dust_blockers") or []),
        "capital_topup_requested": bool(capital_context.get("capital_topup_requested", False)),
        "capital_dynamic_requested": bool(capital_context.get("capital_dynamic_requested", False)),
        "capital_topup_gate_status": str(topup_gate.get("status") or "not_requested"),
        "capital_topup_gate_blockers": list(topup_gate.get("blockers") or []),
        "capital_sizing_basis": str(capital_context.get("sizing_basis") or ""),
        "baseline_allocated_capital_usdt": float(capital_context.get("baseline_allocated_capital_usdt") or 0.0),
        "resolved_allocated_capital_usdt": float(capital_context.get("resolved_allocated_capital_usdt") or 0.0),
        "additional_allocated_capital_usdt": float(capital_context.get("additional_allocated_capital_usdt") or 0.0),
        "frozen_rebalance_slot_target": bool(slot_gate),
        "rebalance_slot_id": str(slot_gate.get("slot_id") or ""),
        "rebalance_slot_target_hash": str(slot_gate.get("active_target_hash") or ""),
        "rebalance_slot_gate_status": str(slot_gate.get("status") or ""),
        "hold_until_next_rebalance_slot": str(slot_gate.get("status") or "") == "hold_until_next_rebalance_slot",
    }


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    venue = str(binance.get("venue") or "").strip().lower()
    if venue != "usdm_futures":
        blockers.append(f"mainnet_rebalance_plan_requires_mainnet_usdm_venue:actual={venue or 'missing'}")
    max_leverage = _max_allowed_leverage(binance)
    if max_leverage <= 0:
        blockers.append("mainnet_rebalance_plan_requires_positive_max_leverage")
    if max_leverage > 2:
        blockers.append(f"mainnet_rebalance_plan_max_leverage_above_pilot_cap:{max_leverage}>2")
    return blockers


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


def _safe_exchange_filters(client: Any, *, symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    try:
        parsed = parse_symbol_exchange_filters(dict(client.exchange_info().payload))
    except Exception:
        return {}
    output: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        item = parsed.get(symbol)
        if item is not None:
            output[symbol] = item.to_dict()
    return output


def _apply_wallet_v2_caps(
    *,
    risk: dict[str, Any],
    capital: dict[str, Any],
    capital_context: dict[str, Any],
) -> dict[str, Any]:
    """v2 equity-tracking caps: CEILINGS (min) + a true absolute ceiling, replacing the
    legacy max(pin, resolved) lift so caps can never act as floors / leave the book
    unbounded. Fail-closed blockers are stashed under ``risk["_wallet_v2_blockers"]`` and
    propagated by ``evaluate_risk_gate``. In Phase 1 ``sizing_equity_usdt`` /
    ``applied_book_prev_usdt`` are not yet populated in ``capital_context``; the equity is
    then backed out from the already-resolved capital and the absolute ceiling is still
    pinned (k_abs * wallet), so risk_gate fails closed on any overshoot."""
    resolved = float(capital_context.get("resolved_allocated_capital_usdt") or 0.0)
    lev = _float(capital.get("leverage_mult")) or 2.0
    equity = capital_context.get("sizing_equity_usdt")
    if equity is None:
        equity = resolved / max(lev, 1e-9)
    eff = resolve_effective_caps(
        equity=float(equity),
        wallet_balance=float(capital_context.get("total_wallet_balance_usdt") or 0.0),
        capital=capital,
        risk=risk,
        applied_book_prev=_optional_float(capital_context.get("applied_book_prev_usdt")),
        deposit_growth_override=_optional_float(capital_context.get("deposit_growth_override")),
    )
    risk.update(eff["risk_caps"])
    risk["_wallet_v2_diagnostics"] = eff["diagnostics"]
    if eff["blockers"]:
        risk["_wallet_v2_blockers"] = list(eff["blockers"])
    return risk


def _risk_payload_plan_only(
    payload: dict[str, Any],
    *,
    capital_allocation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scoped = copy.deepcopy(payload)
    risk = dict(scoped.get("risk") or {})
    risk["trading_enabled"] = False
    capital_context = dict(capital_allocation_context or {})
    capital = dict(scoped.get("capital") or {})
    if _as_bool(capital.get(WALLET_V2_FLAG), default=False):
        # v2 (equity-tracking compounding): caps are CEILINGS (min) + a TRUE absolute
        # ceiling, so the book can never auto-lift without bound. Fully replaces the
        # legacy max(pin, resolved) lift for this run. Off-path (flag false) keeps the
        # legacy `elif` branch below byte-for-byte unchanged.
        risk = _apply_wallet_v2_caps(risk=risk, capital=capital, capital_context=capital_context)
    elif bool(capital_context.get("dynamic_risk_caps_from_resolved_capital")):
        resolved = float(capital_context.get("resolved_allocated_capital_usdt") or 0.0)
        topup = dict(scoped.get("capital_topup") or {})
        cap_cfg = topup if bool(capital_context.get("capital_topup_requested")) else capital
        risk["max_allocated_capital_usdt"] = max(_float(risk.get("max_allocated_capital_usdt")), resolved)
        risk["max_gross_notional_usdt"] = max(_float(risk.get("max_gross_notional_usdt")), resolved)
        max_symbol_weight_cap = _optional_float(cap_cfg.get("max_symbol_weight_cap"))
        if max_symbol_weight_cap is None:
            max_symbol_weight_cap = _optional_float(topup.get("max_symbol_weight_cap"))
        if max_symbol_weight_cap is not None and max_symbol_weight_cap > 0.0:
            risk["max_symbol_notional_usdt"] = max(
                _float(risk.get("max_symbol_notional_usdt")),
                float(resolved * max_symbol_weight_cap),
            )
        max_order_weight_cap = _optional_float(cap_cfg.get("max_order_weight_cap"))
        if max_order_weight_cap is None:
            max_order_weight_cap = _optional_float(topup.get("max_order_weight_cap"))
        if max_order_weight_cap is not None and max_order_weight_cap > 0.0:
            risk["max_order_notional_usdt"] = max(
                _float(risk.get("max_order_notional_usdt")),
                float(resolved * max_order_weight_cap),
            )
    scoped["risk"] = risk
    return scoped


def _resolve_decision_time_context(
    panel: pd.DataFrame,
    as_of: str,
    *,
    rebalance_interval_days: int,
    rebalance_epoch_ms: int = 0,
) -> dict[str, Any]:
    timestamps = pd.to_numeric(panel["timestamp_ms"], errors="coerce").dropna().astype("int64")
    normalized = str(as_of or "now").strip()
    if timestamps.empty:
        return {
            "requested_as_of": normalized,
            "resolved_as_of_mode": "unavailable",
            "decision_time_ms": None,
            "blockers": ["as_of_before_available_panel"],
        }
    unique_timestamps = pd.Series(sorted(set(int(item) for item in timestamps.tolist())), dtype="int64")
    normalized_lower = normalized.lower()
    if normalized_lower in {"", "now"}:
        eligible = unique_timestamps
        mode = "latest_closed_bar"
    elif normalized_lower in {"latest_closed_rebalance_slot", "latest_rebalance_slot", "last_rebalance_slot"}:
        eligible = unique_timestamps.loc[
            unique_timestamps.map(
                lambda value: is_rebalance_slot(
                    decision_time_ms=int(value),
                    rebalance_interval_days=int(rebalance_interval_days),
                    epoch_ms=int(rebalance_epoch_ms),
                )
            )
        ]
        mode = "latest_closed_rebalance_slot"
    else:
        as_of_ms = _parse_as_of_ms(normalized)
        eligible = unique_timestamps.loc[unique_timestamps.le(as_of_ms)]
        mode = "explicit_as_of"
    if eligible.empty:
        blocker = (
            "no_closed_rebalance_slot_available"
            if mode == "latest_closed_rebalance_slot"
            else "as_of_before_available_panel"
        )
        return {
            "requested_as_of": normalized,
            "resolved_as_of_mode": mode,
            "decision_time_ms": None,
            "rebalance_interval_days": int(rebalance_interval_days),
            "rebalance_epoch_ms": int(rebalance_epoch_ms),
            "latest_available_timestamp_ms": int(unique_timestamps.max()),
            "blockers": [blocker],
        }
    decision_time_ms = int(eligible.max())
    return {
        "requested_as_of": normalized,
        "resolved_as_of_mode": mode,
        "decision_time_ms": decision_time_ms,
        "decision_date_utc": datetime.fromtimestamp(decision_time_ms / 1000, tz=UTC).date().isoformat(),
        "rebalance_interval_days": int(rebalance_interval_days),
        "rebalance_epoch_ms": int(rebalance_epoch_ms),
        "latest_available_timestamp_ms": int(unique_timestamps.max()),
        "blockers": [],
    }


def _resolve_decision_time_ms(
    panel: pd.DataFrame,
    as_of: str,
    *,
    rebalance_interval_days: int = 10,
    rebalance_epoch_ms: int = 0,
) -> int | None:
    context = _resolve_decision_time_context(
        panel,
        as_of,
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
    )
    value = context.get("decision_time_ms")
    return None if value is None else int(value)


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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any, *, default: bool = False) -> bool:
    parsed = _optional_bool(value)
    return bool(default) if parsed is None else bool(parsed)


def _csv_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
