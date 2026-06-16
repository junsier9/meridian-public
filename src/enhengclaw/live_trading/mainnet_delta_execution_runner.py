from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
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
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.execution_planner import summarize_dust_residual_order_sizing
from enhengclaw.live_trading.frozen_frontier_live import FRONTIER_PLAN_ARTIFACT, resolve_frontier_live_plan
from enhengclaw.live_trading.live_pit_universe import LIVE_UNIVERSE_ARTIFACT
from enhengclaw.live_trading.wallet_compounding_policy import MIN_LEVERAGE, leverage_policy_blockers
from enhengclaw.live_trading.live_risk_controls import (
    evaluate_account_snapshot_age_gate,
    evaluate_margin_cushion_gate,
    removed_daily_realized_pnl_gate,
)
from enhengclaw.live_trading.models import OrderIntent
from enhengclaw.live_trading.order_router import (
    BinanceOrderSnapshot,
    recover_unknown_order_status,
    submit_mainnet_strategy_delta_order_intent,
)
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import write_json


CONFIRMATION_PREFIX = "LIVE_DELTA_EXECUTION:HV_BALANCED:MAINNET"
LIVE_EXECUTION_STAGES = {"reduce_first", "entry_second"}
NOOP_EXECUTION_STAGES = {"noop", "dust_noop", "deadband_noop"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a previously approved current-position-aware mainnet delta plan. "
            "Default mode is signed read-only dry-run validation; live orders require exact confirmation."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate.yaml")
    parser.add_argument("--plan-artifact", required=True)
    parser.add_argument("--execute-mainnet-delta-orders", action="store_true")
    parser.add_argument(
        "--prepare-planned-symbol-account-settings",
        action="store_true",
        help=(
            "Modify only planned non-reduce symbols' Binance account settings, then stop before order submission. "
            "This is for live-delta preflight and explicit operator setting repair, not no-order observation."
        ),
    )
    parser.add_argument("--operator-enable-mainnet-delta-for-this-run", action="store_true")
    parser.add_argument("--operator-enable-mainnet-account-settings-for-this-run", action="store_true")
    parser.add_argument("--i-understand-this-places-real-mainnet-delta-orders", action="store_true")
    parser.add_argument("--i-understand-this-modifies-mainnet-account-settings", action="store_true")
    parser.add_argument("--i-understand-daily-loss-budget-is-review-only", action="store_true")
    parser.add_argument("--i-understand-daily-realized-pnl-gate-is-active", action="store_true")
    parser.add_argument("--confirm-mainnet-delta-execution", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--ignore-heartbeat-run-id", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_delta_execution(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_delta_execution(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    mainnet_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    clock = now_fn or (lambda: datetime.now(UTC))
    started = clock()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate.yaml"))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-delta-execution"
    run_root = live_config.artifact_root.parent / "mainnet_delta_execution" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()

    execute = bool(getattr(args, "execute_mainnet_delta_orders", False))
    prepare_settings = bool(getattr(args, "prepare_planned_symbol_account_settings", False))
    blockers = _config_blockers(payload)
    if prepare_settings:
        blockers.extend(_account_setting_prepare_confirmation_blockers(args, payload=payload))
    plan = _load_source_plan(getattr(args, "plan_artifact", ""))
    blockers.extend(plan["blockers"])
    execution_stage = str(plan.get("execution_stage") or "missing")
    required_confirmation = _required_confirmation(
        plan_hash=str(plan.get("plan_hash") or "missing"),
        execution_stage=execution_stage,
    )
    if execute:
        blockers.extend(
            _execute_confirmation_blockers(
                args,
                required_confirmation=required_confirmation,
                execution_stage=execution_stage,
            )
        )

    local_state_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=float(dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900) or 900),
        ignore_run_ids=_ignore_heartbeat_run_ids(run_id, getattr(args, "ignore_heartbeat_run_id", "")),
    )
    local_state_health = _ignore_running_orchestrator_for_delta_execution(local_state_health)
    blockers.extend(list(local_state_health.get("blockers") or []))
    operator_state = state_store.read_operator_state()
    if bool(operator_state.get("paused")):
        blockers.append("operator_paused")
    frontier_submit_gate = _frontier_submit_gate(
        plan=plan, payload=payload, operator_state=operator_state
    )
    blockers.extend(list(frontier_submit_gate.get("blockers") or []))
    write_json(run_root / "frontier_submit_gate.json", frontier_submit_gate)
    write_json(run_root / "local_state_health.json", local_state_health)
    write_json(run_root / "operator_state.json", operator_state)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live",
        status="running",
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        artifact_root=str(run_root),
    )

    credentials = _resolve_credentials(payload, env or os.environ)
    blockers.extend(credentials["blockers"])
    mainnet_client = None
    permission_client = None
    if not blockers:
        mainnet_client = _build_mainnet_client(credentials, mainnet_client_factory)
        permission_client = _build_permission_client(credentials, permission_client_factory)

    before = {"status": "not_run", "blockers": list(blockers)}
    preflight = {"status": "not_run", "blockers": list(blockers)}
    daily_pnl_gate = removed_daily_realized_pnl_gate(config=payload)
    account_setting_preparation = {"status": "not_requested", "blockers": [], "enabled": False}
    expected_current = dict(plan.get("expected_current_positions") or {})
    intents = _execution_intents(plan)
    planned_rows = _planned_order_rows(plan=plan, intents=intents)
    if mainnet_client is not None and permission_client is not None:
        before = _account_snapshot(
            mainnet_client,
            permission_client=permission_client,
            expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
            expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
            max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
            now_fn=clock,
        )
        auto_prepare_enabled = bool(
            (execute or prepare_settings) and _auto_prepare_planned_symbol_settings_enabled(payload)
        )
        account_setting_preparation = _prepare_planned_symbol_account_settings(
            mainnet_client,
            before=before,
            planned_rows=planned_rows,
            expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
            target_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
            position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
            enabled=auto_prepare_enabled,
        )
        blockers.extend(list(account_setting_preparation.get("blockers") or []))
        if (
            account_setting_preparation.get("status") in {"prepared", "not_required"}
            and int(account_setting_preparation.get("setting_call_count") or 0) > 0
            and not list(account_setting_preparation.get("blockers") or [])
        ):
            # #5: the account was just MODIFIED (leverage changed). Never let a transient REST
            # failure on the re-snapshot crash the runner with the account in a changed state —
            # fail closed with a blocker so the cycle is blocked (and disarmed) cleanly instead.
            try:
                before = _account_snapshot(
                    mainnet_client,
                    permission_client=permission_client,
                    expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
                    expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
                    max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
                    now_fn=clock,
                )
            except Exception as exc:  # noqa: BLE001 — fail closed; the supervisor would otherwise crash mid-cycle.
                blockers.append(f"account_resnapshot_after_leverage_change_failed:{exc.__class__.__name__}")
        preflight = _execution_preflight(
            before=before,
            expected_current_positions=expected_current,
            intents=intents,
            planned_rows=planned_rows,
            execution_stage=execution_stage,
            source_margin_cushion_gate=plan.get("margin_cushion_gate"),
            source_pre_reduce_only_margin_cushion_gate=plan.get("pre_reduce_only_margin_cushion_gate"),
            max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
            config=payload,
            position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
            now_ms=int(clock().timestamp() * 1000),
        )
        blockers.extend(preflight["blockers"])
    _write_pre_execution_artifacts(
        run_root,
        source_plan=plan,
        before=before,
        preflight=preflight,
        daily_pnl_gate=daily_pnl_gate,
        account_setting_preparation=account_setting_preparation,
        planned_rows=planned_rows,
        required_confirmation=required_confirmation,
        execute=execute,
    )
    if blockers or mainnet_client is None:
        return _finish(
            run_root=run_root,
            state_store=state_store,
            run_id=run_id,
            started=started,
            status="blocked",
            blockers=blockers,
            source_plan=plan,
            required_confirmation=required_confirmation,
            planned_rows=planned_rows,
            preflight_status=str(preflight.get("status") or "blocked"),
            account_setting_preparation=account_setting_preparation,
        )
    if not intents:
        return _finish(
            run_root=run_root,
            state_store=state_store,
            run_id=run_id,
            started=started,
            status="mainnet_delta_execution_noop",
            blockers=[],
            source_plan=plan,
            required_confirmation=required_confirmation,
            planned_rows=planned_rows,
            preflight_status=str(preflight.get("status") or "passed"),
            account_setting_preparation=account_setting_preparation,
        )
    if not execute:
        return _finish(
            run_root=run_root,
            state_store=state_store,
            run_id=run_id,
            started=started,
            status="mainnet_delta_execution_ready",
            blockers=[],
            source_plan=plan,
            required_confirmation=required_confirmation,
            planned_rows=planned_rows,
            preflight_status=str(preflight.get("status") or "passed"),
            account_setting_preparation=account_setting_preparation,
        )

    # #4 + #2: re-validate operator state AND in-flight concurrency IMMEDIATELY before submit. The
    # entry-time operator_state read, frontier submit gate, and local-state-health check all ran
    # BEFORE the account/leverage/preflight Binance REST calls (100ms-1s+). An operator pause /
    # kill-switch / disarm-live-delta, OR a concurrently-started live run, during that window would
    # otherwise slip through to a live submit. Re-check with the SAME ignore set so the intended
    # fast-follow handoff (which ignores its parent) is preserved.
    fresh_operator_state = state_store.read_operator_state()
    pre_submit_blockers: list[str] = []
    if bool(fresh_operator_state.get("paused")):
        pre_submit_blockers.append("operator_paused_before_submit")
    if bool(operator_state.get("live_delta_armed")) and not bool(fresh_operator_state.get("live_delta_armed")):
        pre_submit_blockers.append("operator_disarmed_before_submit")
    pre_submit_blockers.extend(
        list(_frontier_submit_gate(plan=plan, payload=payload, operator_state=fresh_operator_state).get("blockers") or [])
    )
    fresh_health = state_store.evaluate_local_state_health(
        now=clock(),
        max_heartbeat_age_seconds=float(dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900) or 900),
        ignore_run_ids=_ignore_heartbeat_run_ids(run_id, getattr(args, "ignore_heartbeat_run_id", "")),
    )
    fresh_health = _ignore_running_orchestrator_for_delta_execution(fresh_health)
    pre_submit_blockers.extend(
        item for item in list(fresh_health.get("blockers") or []) if str(item).startswith("active_run_in_progress")
    )
    if pre_submit_blockers:
        write_json(
            run_root / "pre_submit_revalidation.json",
            {"blockers": sorted(set(pre_submit_blockers)), "checked_at_utc": clock().isoformat().replace("+00:00", "Z")},
        )
        return _finish(
            run_root=run_root,
            state_store=state_store,
            run_id=run_id,
            started=started,
            status="blocked",
            blockers=sorted(set(pre_submit_blockers)),
            source_plan=plan,
            required_confirmation=required_confirmation,
            planned_rows=planned_rows,
            preflight_status=str(preflight.get("status") or "passed"),
            account_setting_preparation=account_setting_preparation,
        )

    execution = _execute_delta_plan(
        mainnet_client,
        intents=intents,
        planned_rows=planned_rows,
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
    )
    write_json(run_root / "mainnet_delta_execution.json", execution)
    pd.DataFrame(execution["submitted_orders"]).to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame(execution["fills"]).to_csv(run_root / "fills.csv", index=False)
    after = _account_snapshot(
        mainnet_client,
        permission_client=permission_client,
        expected_position_mode=str(dict(payload.get("binance") or {}).get("position_mode") or "one_way"),
        expected_margin_type=str(dict(payload.get("binance") or {}).get("margin_type") or "").strip().lower(),
        max_allowed_leverage=_max_allowed_leverage(dict(payload.get("binance") or {})),
        now_fn=clock,
    )
    reconciliation = _reconcile_after_execution(
        after=after,
        execution=execution,
        expected_current_positions=expected_current,
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
    )
    write_json(run_root / "account_after.json", after)
    write_json(run_root / "reconciliation.json", reconciliation)
    blockers.extend(execution["blockers"])
    blockers.extend(reconciliation["blockers"])
    status = "mainnet_delta_orders_submitted" if not blockers else "mainnet_delta_reconcile_required"
    post_trade_reconcile = _direct_delta_post_trade_reconcile_record(
        reconciliation=reconciliation,
        run_root=run_root,
    )
    return _finish(
        run_root=run_root,
        state_store=state_store,
        run_id=run_id,
        started=started,
        status=status,
        blockers=blockers,
        source_plan=plan,
        required_confirmation=required_confirmation,
        planned_rows=planned_rows,
        preflight_status=str(preflight.get("status") or "unknown"),
        reconciliation_status=str(reconciliation.get("status") or "unknown"),
        post_trade_reconcile=post_trade_reconcile,
        submitted_order_count=int(execution["submitted_order_count"]),
        fill_count=int(execution["fill_count"]),
        account_setting_preparation=account_setting_preparation,
    )


def _load_source_plan(path_value: str) -> dict[str, Any]:
    blockers: list[str] = []
    plan_root = resolve_repo_path(str(path_value or ""))
    if not str(path_value or "").strip():
        return {"status": "missing", "blockers": ["missing_plan_artifact"]}
    if not plan_root.exists() or not plan_root.is_dir():
        return {"status": "missing", "blockers": [f"plan_artifact_not_found:{plan_root}"], "plan_root": str(plan_root)}
    required = [
        "run_summary.json",
        "runtime_gate_context.json",
        "execution_plan.json",
        "execution_plan.csv",
        "order_sizing_report.csv",
        "risk_gate.json",
        "target_portfolio.json",
        "current_positions.csv",
    ]
    missing = [name for name in required if not (plan_root / name).exists()]
    blockers.extend(f"plan_artifact_missing_file:{name}" for name in missing)
    summary = _read_json(plan_root / "run_summary.json")
    runtime_gate = _read_json(plan_root / "runtime_gate_context.json")
    execution_plan = _read_json(plan_root / "execution_plan.json")
    risk_gate = _read_json(plan_root / "risk_gate.json")
    target_portfolio = _read_json(plan_root / "target_portfolio.json")
    margin_cushion_gate = _source_plan_margin_cushion_gate(plan_root)
    pre_reduce_only_margin_cushion_gate = _source_plan_pre_reduce_only_margin_cushion_gate(plan_root)
    intents_frame = _read_csv(plan_root / "execution_plan.csv")
    sizing_frame = _read_csv(plan_root / "order_sizing_report.csv")
    current_frame = _read_csv(plan_root / "current_positions.csv")
    target_frame = _read_csv(plan_root / "target_positions.csv")
    # frontier_plan.json, live_universe.json and decision_snapshot.json are hashed when present
    # (skipped when absent), so tampering with the recorded frontier verdict, the resolved PIT
    # rolling universe, OR the scoring decision snapshot invalidates plan_hash -> the operator
    # confirmation token no longer matches and submit is refused. (#3: binds the decision-snapshot
    # provenance to the operator-confirmed plan; the submitted orders themselves are already bound
    # via execution_plan.csv above.) All are absent on old/baseline plans => hash byte-for-byte
    # unchanged; both the dry-run and execute calls recompute the same hash, so auto-confirm holds.
    plan_hash = _plan_artifact_hash(
        plan_root, [*required, "decision_snapshot.json", FRONTIER_PLAN_ARTIFACT, LIVE_UNIVERSE_ARTIFACT]
    )
    blockers.extend(_source_plan_blockers(summary, runtime_gate, execution_plan, risk_gate, intents_frame, sizing_frame))
    stage_gate = _source_plan_stage_gate(summary=summary, execution_plan=execution_plan, intents_frame=intents_frame)
    blockers.extend(list(stage_gate.get("blockers") or []))
    expected_current = _expected_current_positions(current_frame=current_frame, intents_frame=intents_frame)
    return {
        "status": "ok" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "plan_root": str(plan_root),
        "plan_hash": plan_hash,
        "execution_stage": stage_gate.get("execution_stage"),
        "stage_gate": stage_gate,
        "run_summary": summary,
        "runtime_gate_context": runtime_gate,
        "execution_plan": execution_plan,
        "risk_gate": risk_gate,
        "margin_cushion_gate": margin_cushion_gate,
        "pre_reduce_only_margin_cushion_gate": pre_reduce_only_margin_cushion_gate,
        "target_portfolio": target_portfolio,
        "target_positions_frame": target_frame,
        "intents_frame": intents_frame,
        "sizing_frame": sizing_frame,
        "current_positions_frame": current_frame,
        "expected_current_positions": expected_current,
    }


def _source_plan_blockers(
    summary: dict[str, Any],
    runtime_gate: dict[str, Any],
    execution_plan: dict[str, Any],
    risk_gate: dict[str, Any],
    intents_frame: pd.DataFrame,
    sizing_frame: pd.DataFrame,
) -> list[str]:
    blockers: list[str] = []
    summary_status = str(summary.get("status") or "")
    execution_plan_status = str(execution_plan.get("status") or "")
    dust_summary = summarize_dust_residual_order_sizing(sizing_frame)
    dust_source_noop = (
        summary_status == "mainnet_current_position_rebalance_dust_noop"
        and execution_plan_status == "dust_noop"
        and bool(dust_summary.get("is_dust_residual_only"))
    )
    if summary_status != "mainnet_current_position_rebalance_plan_ready" and not dust_source_noop:
        blockers.append(f"source_plan_status_not_ready:{summary.get('status')}")
    if list(summary.get("blockers") or []):
        blockers.append("source_plan_has_blockers")
    if summary.get("current_position_aware") is not True:
        blockers.append("source_plan_not_current_position_aware")
    if summary.get("plan_only") is not True:
        blockers.append("source_plan_not_plan_only")
    if int(summary.get("orders_submitted") or 0) != 0 or int(summary.get("fill_count") or 0) != 0:
        blockers.append("source_plan_has_order_side_effects")
    if summary.get("recurring_mainnet_enabled") is not False:
        blockers.append("source_plan_recurring_mainnet_not_false")
    if summary.get("mainnet_order_submission_authorized") is not False:
        blockers.append("source_plan_order_submission_authorized_unexpectedly")
    if runtime_gate.get("current_position_aware") is not True:
        blockers.append("runtime_gate_not_current_position_aware")
    if runtime_gate.get("mainnet_order_submission_authorized") is not False:
        blockers.append("runtime_gate_order_submission_authorized_unexpectedly")
    if str(risk_gate.get("decision") or "") != "allow_plan" or risk_gate.get("passed") is not True:
        blockers.append("source_risk_gate_not_passed")
    if list(risk_gate.get("blockers") or []):
        blockers.append("source_risk_gate_has_blockers")
    if execution_plan_status != "ok" and not dust_source_noop:
        blockers.append(f"source_execution_plan_not_ok:{execution_plan.get('status')}")
    if str(execution_plan.get("mode") or "") != "plan_only":
        blockers.append(f"source_execution_plan_not_plan_only:{execution_plan.get('mode')}")
    if list(execution_plan.get("blockers") or []) and not dust_source_noop:
        blockers.append("source_execution_plan_has_blockers")
    if intents_frame.empty:
        if not dust_source_noop:
            blockers.append("source_execution_plan_has_no_delta_intents")
    else:
        client_ids = intents_frame.get("client_order_id", pd.Series(dtype="object")).astype(str)
        if client_ids.duplicated().any():
            blockers.append("source_execution_plan_duplicate_client_order_ids")
        for _, row in intents_frame.iterrows():
            symbol = str(row.get("symbol") or "")
            quantity = _float(row.get("quantity"))
            delta = _float(row.get("delta_position_amt"))
            side = str(row.get("side") or "").upper()
            if quantity <= 0:
                blockers.append(f"source_intent_non_positive_quantity:{symbol}")
            if delta > 0 and side != "BUY":
                blockers.append(f"source_intent_side_mismatch:{symbol}:delta_positive_side={side}")
            if delta < 0 and side != "SELL":
                blockers.append(f"source_intent_side_mismatch:{symbol}:delta_negative_side={side}")
    if not sizing_frame.empty and "blockers" in sizing_frame.columns:
        bad = sizing_frame.loc[sizing_frame["blockers"].fillna("").astype(str).str.strip().ne("")]
        for _, row in bad.iterrows():
            row_blockers = [item for item in str(row.get("blockers") or "").split(";") if item]
            row_is_dust = str(row.get("execution_phase") or "") == "dust_noop" and all(
                item.startswith(("quantity_below_min:", "notional_below_min:")) for item in row_blockers
            )
            if not dust_source_noop and not row_is_dust:
                blockers.append(f"source_order_sizing_blocked:{row.get('symbol')}")
    return blockers


def _source_plan_stage_gate(
    *,
    summary: dict[str, Any],
    execution_plan: dict[str, Any],
    intents_frame: pd.DataFrame,
) -> dict[str, Any]:
    blockers: list[str] = []
    summary_stage = _normalize_execution_phase(summary.get("active_execution_phase"))
    plan_stage = _normalize_execution_phase(execution_plan.get("active_execution_phase"))
    execution_stage = plan_stage or summary_stage
    if summary_stage and plan_stage and summary_stage != plan_stage:
        blockers.append(f"source_plan_active_execution_phase_mismatch:summary={summary_stage}:execution_plan={plan_stage}")
    if isinstance(intents_frame, pd.DataFrame) and not intents_frame.empty:
        row_phases: list[str] = []
        missing_phase_symbols: list[str] = []
        non_reduce_symbols: list[str] = []
        reduce_symbols: list[str] = []
        for _, row in intents_frame.iterrows():
            symbol = str(row.get("symbol") or "")
            phase = _normalize_execution_phase(row.get("execution_phase"))
            if not phase:
                missing_phase_symbols.append(symbol or "unknown")
                continue
            row_phases.append(phase)
            if phase == "reduce_first" and not _bool(row.get("reduce_only")):
                non_reduce_symbols.append(symbol or "unknown")
            if phase == "entry_second" and _bool(row.get("reduce_only")):
                reduce_symbols.append(symbol or "unknown")
        executable_phases = sorted({phase for phase in row_phases if phase not in NOOP_EXECUTION_STAGES and phase != "blocked"})
        if missing_phase_symbols:
            blockers.append(f"source_plan_missing_row_execution_phase:{','.join(sorted(set(missing_phase_symbols)))}")
        if not execution_stage:
            blockers.append("source_plan_missing_active_execution_phase")
        elif execution_stage not in LIVE_EXECUTION_STAGES:
            blockers.append(f"source_plan_active_execution_phase_not_executable:{execution_stage}")
        if len(executable_phases) > 1:
            blockers.append(f"source_plan_mixed_execution_phases:{','.join(executable_phases)}")
        elif len(executable_phases) == 1 and execution_stage and execution_stage != executable_phases[0]:
            blockers.append(f"source_plan_execution_phase_mismatch:active={execution_stage}:rows={executable_phases[0]}")
        if non_reduce_symbols:
            blockers.append(f"source_reduce_first_has_non_reduce_only_intents:{','.join(sorted(set(non_reduce_symbols)))}")
        if reduce_symbols:
            blockers.append(f"source_entry_second_has_reduce_only_intents:{','.join(sorted(set(reduce_symbols)))}")
    elif not execution_stage and str(execution_plan.get("status") or "") == "dust_noop":
        execution_stage = "dust_noop"
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "execution_stage": execution_stage or "missing",
        "summary_active_execution_phase": summary_stage or "",
        "execution_plan_active_execution_phase": plan_stage or "",
        "planned_execution_phases": sorted(set(row_phases)) if isinstance(intents_frame, pd.DataFrame) and not intents_frame.empty else [],
    }


def _execution_intents(plan: dict[str, Any]) -> list[OrderIntent]:
    if plan.get("status") != "ok":
        return []
    frame = plan.get("intents_frame")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    plan_hash = str(plan.get("plan_hash") or "")
    intents: list[OrderIntent] = []
    for seq, (_, row) in enumerate(frame.iterrows(), start=1):
        raw_intent = OrderIntent(
            intent_id=str(row["intent_id"]),
            portfolio_id=str(row["portfolio_id"]),
            symbol=str(row["symbol"]),
            side=str(row["side"]),
            position_side=str(row.get("position_side") or "BOTH"),
            order_type=str(row.get("order_type") or "MARKET"),
            quantity=float(row["quantity"]),
            reduce_only=_bool(row.get("reduce_only")),
            target_position_amt=float(row["target_position_amt"]),
            current_position_amt=float(row["current_position_amt"]),
            delta_position_amt=float(row["delta_position_amt"]),
            max_slippage_bps=float(row.get("max_slippage_bps") or 20.0),
            client_order_id=str(row["client_order_id"]),
            execution_phase=str(row.get("execution_phase") or ""),
            delta_classification=str(row.get("delta_classification") or ""),
            final_target_position_amt=_float(row.get("final_target_position_amt", row.get("target_position_amt"))),
            second_phase_required=_bool(row.get("second_phase_required")),
        )
        intents.append(replace(raw_intent, client_order_id=_delta_client_order_id(plan_hash=plan_hash, symbol=raw_intent.symbol, seq=seq)))
    return intents


def _planned_order_rows(*, plan: dict[str, Any], intents: list[OrderIntent]) -> list[dict[str, Any]]:
    if not intents:
        return []
    sizing = plan.get("sizing_frame")
    sizing_by_symbol: dict[str, dict[str, Any]] = {}
    if isinstance(sizing, pd.DataFrame) and not sizing.empty:
        sizing_by_symbol = {
            str(row.get("symbol") or ""): dict(row)
            for _, row in sizing.iterrows()
        }
    rows: list[dict[str, Any]] = []
    for seq, intent in enumerate(intents, start=1):
        sizing_row = sizing_by_symbol.get(intent.symbol, {})
        rounded_notional = _float(sizing_row.get("rounded_notional_usdt"))
        rows.append(
            {
                "seq": int(seq),
                "intent_id": intent.intent_id,
                "portfolio_id": intent.portfolio_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "position_side": intent.position_side,
                "order_type": intent.order_type,
                "quantity": float(intent.quantity),
                "reduce_only": bool(intent.reduce_only),
                "source_client_order_id": str(sizing_row.get("client_order_id") or ""),
                "client_order_id": intent.client_order_id,
                "current_position_amt": float(intent.current_position_amt),
                "target_position_amt": float(intent.target_position_amt),
                "final_target_position_amt": float(intent.final_target_position_amt),
                "delta_position_amt": float(intent.delta_position_amt),
                "execution_phase": str(intent.execution_phase),
                "delta_classification": str(intent.delta_classification),
                "second_phase_required": bool(intent.second_phase_required),
                "rounded_notional_usdt": float(rounded_notional),
                "estimated_initial_margin_usdt": float(0.0 if intent.reduce_only else rounded_notional),
            }
        )
    return rows


def _execution_preflight(
    *,
    before: dict[str, Any],
    expected_current_positions: dict[str, float],
    intents: list[OrderIntent],
    planned_rows: list[dict[str, Any]],
    execution_stage: str,
    max_allowed_leverage: int,
    config: dict[str, Any],
    position_tolerance: float,
    now_ms: int | None = None,
    source_margin_cushion_gate: Any = None,
    source_pre_reduce_only_margin_cushion_gate: Any = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(list(before.get("blockers") or []))
    effective_now_ms = int(now_ms) if now_ms is not None else int(datetime.now(UTC).timestamp() * 1000)
    snapshot_age_gate = evaluate_account_snapshot_age_gate(
        before,
        config=config,
        now_ms=effective_now_ms,
        require_configured=False,
    )
    blockers.extend(list(snapshot_age_gate.get("blockers") or []))
    actual_positions = {
        str(row["symbol"]): float(row["positionAmt"])
        for row in list(before.get("open_positions_redacted") or [])
    }
    blockers.extend(
        _position_match_blockers(
            expected=expected_current_positions,
            actual=actual_positions,
            tolerance=float(position_tolerance),
        )
    )
    blockers.extend(
        _planned_symbol_setting_blockers(
            before=before,
            planned_rows=planned_rows,
            expected_margin_type=str(dict(config.get("binance") or {}).get("margin_type") or "").strip().lower(),
            max_allowed_leverage=max_allowed_leverage,
        )
    )
    estimated_margin = _estimated_additional_initial_margin(planned_rows, max_allowed_leverage=max_allowed_leverage)
    available = float(before.get("available_balance_usdt") or 0.0)
    if estimated_margin > 0.0 and available + 1e-9 < estimated_margin:
        blockers.append(f"available_balance_below_estimated_delta_initial_margin:{available}<{estimated_margin}")
    computed_margin_gate = evaluate_margin_cushion_gate(
        {
            "available_balance_usdt": available,
            "total_wallet_balance_usdt": float(before.get("total_wallet_balance_usdt") or 0.0),
        },
        config=config,
        planned_additional_initial_margin_usdt=estimated_margin,
        # Fail-closed: when no plan-stage source margin gate is present this computed
        # gate is the only margin defense on the delta preflight, so an unconfigured
        # margin cushion must block rather than silently pass. The host config carries
        # all three thresholds (min_available_balance_after_plan_usdt /
        # _ratio_after_plan / min_margin_cushion_after_plan_usdt), so this only tightens
        # the no-source fallback path; when a source gate exists it is selected instead.
        require_configured=True,
    )
    margin_gate, margin_gate_source, margin_gate_selection_blockers = _select_preflight_margin_cushion_gate(
        source_margin_cushion_gate=source_margin_cushion_gate,
        computed_margin_gate=computed_margin_gate,
        estimated_margin=estimated_margin,
    )
    blockers.extend(margin_gate_selection_blockers)
    blockers.extend(list(margin_gate.get("blockers") or []))
    result = {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "current_position_match": not _position_match_blockers(
            expected=expected_current_positions,
            actual=actual_positions,
            tolerance=float(position_tolerance),
        ),
        "execution_stage": str(execution_stage or "missing"),
        "planned_execution_phases": _planned_execution_phases(planned_rows),
        "planned_delta_order_count": int(len(intents)),
        "estimated_additional_initial_margin_usdt": float(estimated_margin),
        "available_balance_usdt": float(available),
        "estimated_margin_cushion_usdt": float(available - estimated_margin),
        "margin_cushion_gate": margin_gate,
        "margin_cushion_gate_source": margin_gate_source,
        "computed_delta_preflight_margin_cushion_gate": computed_margin_gate,
        "account_snapshot_age_gate": snapshot_age_gate,
        "open_order_count": int(before.get("open_order_count") or 0),
        "open_position_count": int(before.get("open_position_count") or 0),
    }
    if isinstance(source_pre_reduce_only_margin_cushion_gate, dict) and source_pre_reduce_only_margin_cushion_gate:
        result["source_pre_reduce_only_margin_cushion_gate"] = source_pre_reduce_only_margin_cushion_gate
    return result


def _select_preflight_margin_cushion_gate(
    *,
    source_margin_cushion_gate: Any,
    computed_margin_gate: dict[str, Any],
    estimated_margin: float,
) -> tuple[dict[str, Any], str, list[str]]:
    if not isinstance(source_margin_cushion_gate, dict) or not source_margin_cushion_gate:
        return computed_margin_gate, "computed_delta_preflight", []
    status = str(source_margin_cushion_gate.get("status") or "").strip().lower()
    if status not in {"passed", "blocked"}:
        return computed_margin_gate, "computed_delta_preflight", ["source_plan_margin_gate_invalid_status"]
    source_planned_margin = _float(source_margin_cushion_gate.get("planned_additional_initial_margin_usdt"))
    if abs(float(source_planned_margin) - float(estimated_margin)) > 1e-6:
        return (
            computed_margin_gate,
            "computed_delta_preflight",
            [
                "source_plan_margin_gate_planned_margin_mismatch:"
                f"{float(source_planned_margin)}!={float(estimated_margin)}"
            ],
        )
    selected = dict(source_margin_cushion_gate)
    selected["source"] = "source_plan_artifact"
    return selected, "source_plan_artifact", []


def _planned_symbol_setting_blockers(
    *,
    before: dict[str, Any],
    planned_rows: list[dict[str, Any]],
    expected_margin_type: str,
    max_allowed_leverage: int,
) -> list[str]:
    blockers: list[str] = []
    settings_by_symbol = {
        str(row.get("symbol") or "").upper(): dict(row)
        for row in list(before.get("position_settings_redacted") or [])
        if str(row.get("symbol") or "").strip()
    }
    for row in list(before.get("open_positions_redacted") or []):
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in settings_by_symbol:
            settings_by_symbol[symbol] = dict(row)
    for row in planned_rows:
        if bool(row.get("reduce_only")):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        setting = settings_by_symbol.get(symbol)
        if not setting:
            blockers.append(f"planned_symbol_position_risk_missing:{symbol}")
            continue
        if str(setting.get("positionSide") or "BOTH") != "BOTH":
            blockers.append(f"planned_symbol_requires_one_way_position_side:{symbol}:{setting.get('positionSide')}")
        margin_type = str(setting.get("marginType") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            blockers.append(f"planned_symbol_margin_type_mismatch:{symbol}:expected={expected_margin_type}:actual={margin_type or 'missing'}")
        lev_val = _float(setting.get("leverage"))
        if lev_val != lev_val or lev_val < float(MIN_LEVERAGE) or lev_val >= float("inf"):
            # Fail-closed: unreadable / <1x venue leverage must block, never silently read 0.
            blockers.append(f"planned_symbol_leverage_unreadable_or_below_min:{symbol}:actual={setting.get('leverage')!r}")
        elif max_allowed_leverage > 0 and int(lev_val) > max_allowed_leverage:
            blockers.append(f"planned_symbol_leverage_above_max:{symbol}:max={max_allowed_leverage}:actual={int(lev_val)}")
    return blockers


def _prepare_planned_symbol_account_settings(
    client: Any,
    *,
    before: dict[str, Any],
    planned_rows: list[dict[str, Any]],
    expected_margin_type: str,
    target_leverage: int,
    position_tolerance: float,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "status": "not_requested",
            "enabled": False,
            "blockers": [],
            "setting_call_count": 0,
            "changed_setting_count": 0,
            "actions": [],
        }
    actions: list[dict[str, Any]] = []
    blockers: list[str] = []
    planned_symbols = set(_planned_non_reduce_symbols(planned_rows))
    if int(before.get("open_order_count") or 0) != 0:
        blockers.append(f"account_setting_prepare_open_orders_exist:{before.get('open_order_count')}")
    unsafe_before = [
        str(item)
        for item in list(before.get("blockers") or [])
        if not _account_setting_prepare_can_handle_snapshot_blocker(str(item), planned_symbols)
    ]
    if unsafe_before:
        blockers.extend(f"account_setting_prepare_blocked_by_account_snapshot:{item}" for item in unsafe_before)
    settings_by_symbol = _settings_by_symbol(before)
    open_position_by_symbol = {
        str(row.get("symbol") or "").upper(): _float(row.get("positionAmt"))
        for row in list(before.get("open_positions_redacted") or [])
    }
    for symbol in sorted(planned_symbols):
        setting = settings_by_symbol.get(symbol)
        if not setting:
            blockers.append(f"account_setting_prepare_position_risk_missing:{symbol}")
            continue
        position_side = str(setting.get("positionSide") or "BOTH")
        if position_side != "BOTH":
            blockers.append(f"account_setting_prepare_requires_one_way_position_side:{symbol}:{position_side}")
            continue
        margin_type = str(setting.get("marginType") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            current_amount = abs(float(open_position_by_symbol.get(symbol, 0.0) or 0.0))
            if current_amount > float(position_tolerance):
                blockers.append(
                    f"account_setting_prepare_margin_type_mismatch_on_open_position:{symbol}:"
                    f"expected={expected_margin_type}:actual={margin_type or 'missing'}"
                )
            elif not blockers:
                action = _change_margin_type_action(
                    client,
                    symbol=symbol,
                    target_margin_type=expected_margin_type,
                    actual_margin_type=margin_type,
                )
                actions.append(action)
                if str(action.get("status") or "") == "rejected":
                    blockers.append(
                        f"account_setting_prepare_rejected:{symbol}:{action.get('action')}:"
                        f"http_{action.get('status_code')}:{action.get('error_code')}"
                    )
        lev_val = _float(setting.get("leverage"))
        if lev_val != lev_val or lev_val < float(MIN_LEVERAGE) or lev_val >= float("inf"):
            # Fail-closed: do not silently leave a stale/unreadable venue leverage in place.
            blockers.append(f"account_setting_prepare_leverage_unreadable_or_below_min:{symbol}:actual={setting.get('leverage')!r}")
        elif target_leverage > 0 and int(lev_val) > target_leverage and not blockers:
            action = _change_leverage_action(
                client,
                symbol=symbol,
                target_leverage=target_leverage,
                actual_leverage=int(lev_val),
            )
            actions.append(action)
            if str(action.get("status") or "") == "rejected":
                blockers.append(
                    f"account_setting_prepare_rejected:{symbol}:{action.get('action')}:"
                    f"http_{action.get('status_code')}:{action.get('error_code')}"
                )
        if blockers:
            break
    call_count = int(sum(1 for action in actions if bool(action.get("call_sent"))))
    changed_count = int(sum(1 for action in actions if str(action.get("status") or "") in {"changed", "already_set"}))
    if blockers:
        status = "blocked"
    elif call_count > 0:
        status = "prepared"
    else:
        status = "not_required"
    return {
        "status": status,
        "enabled": True,
        "blockers": sorted(set(blockers)),
        "setting_call_count": call_count,
        "changed_setting_count": changed_count,
        "target_margin_type": expected_margin_type,
        "target_max_leverage": int(target_leverage),
        "planned_non_reduce_symbols": sorted(planned_symbols),
        "actions": actions,
    }


def _account_setting_prepare_can_handle_snapshot_blocker(blocker: str, planned_symbols: set[str]) -> bool:
    parts = str(blocker or "").split(":")
    if len(parts) >= 2 and parts[0] == "leverage_above_max":
        return parts[1].upper() in planned_symbols
    return False


def _settings_by_symbol(before: dict[str, Any]) -> dict[str, dict[str, Any]]:
    settings = {
        str(row.get("symbol") or "").upper(): dict(row)
        for row in list(before.get("position_settings_redacted") or [])
        if str(row.get("symbol") or "").strip()
    }
    for row in list(before.get("open_positions_redacted") or []):
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in settings:
            settings[symbol] = dict(row)
    return settings


def _planned_non_reduce_symbols(planned_rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(row.get("symbol") or "").upper()
            for row in planned_rows
            if str(row.get("symbol") or "").strip() and not bool(row.get("reduce_only"))
        }
    )


def _change_margin_type_action(
    client: Any,
    *,
    symbol: str,
    target_margin_type: str,
    actual_margin_type: str,
) -> dict[str, Any]:
    binance_margin_type = _binance_margin_type(target_margin_type)
    action = {
        "symbol": symbol,
        "action": "change_margin_type",
        "from": actual_margin_type or "missing",
        "to": target_margin_type,
        "binance_margin_type": binance_margin_type,
        "call_sent": False,
    }
    try:
        response = client.change_margin_type(symbol=symbol, margin_type=binance_margin_type)
    except BinanceUsdmRequestError as exc:
        code = _binance_error_code(exc.detail)
        if code == "-4046":
            action.update({"status": "already_set", "call_sent": True, "status_code": exc.status_code, "error_code": code})
            return action
        action.update({"status": "rejected", "call_sent": True, "status_code": exc.status_code, "error_code": code})
        return action
    payload = dict(getattr(response, "payload", {}) or {})
    action.update({"status": "changed", "call_sent": True, "status_code": getattr(response, "status_code", 200), "response": payload})
    return action


def _change_leverage_action(
    client: Any,
    *,
    symbol: str,
    target_leverage: int,
    actual_leverage: int,
) -> dict[str, Any]:
    action = {
        "symbol": symbol,
        "action": "change_initial_leverage",
        "from": int(actual_leverage),
        "to": int(target_leverage),
        "call_sent": False,
    }
    try:
        response = client.change_initial_leverage(symbol=symbol, leverage=int(target_leverage))
    except BinanceUsdmRequestError as exc:
        action.update(
            {
                "status": "rejected",
                "call_sent": True,
                "status_code": exc.status_code,
                "error_code": _binance_error_code(exc.detail),
            }
        )
        return action
    payload = dict(getattr(response, "payload", {}) or {})
    action.update({"status": "changed", "call_sent": True, "status_code": getattr(response, "status_code", 200), "response": payload})
    return action


def _binance_margin_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"cross", "crossed"}:
        return "CROSSED"
    if normalized == "isolated":
        return "ISOLATED"
    return normalized.upper()


def _position_match_blockers(*, expected: dict[str, float], actual: dict[str, float], tolerance: float) -> list[str]:
    blockers: list[str] = []
    symbols = sorted(set(expected) | set(actual))
    for symbol in symbols:
        exp = float(expected.get(symbol, 0.0) or 0.0)
        act = float(actual.get(symbol, 0.0) or 0.0)
        if abs(exp) <= tolerance and abs(act) <= tolerance:
            continue
        if symbol not in expected and abs(act) > tolerance:
            blockers.append(f"unexpected_live_position:{symbol}:actual={act}")
            continue
        if abs(exp - act) > tolerance:
            blockers.append(f"position_drift:{symbol}:expected={exp}:actual={act}")
    return blockers


def _estimated_additional_initial_margin(planned_rows: list[dict[str, Any]], *, max_allowed_leverage: int) -> float:
    leverage = max(float(max_allowed_leverage), 1.0)
    gross_new_risk = sum(
        float(row.get("rounded_notional_usdt") or 0.0)
        for row in planned_rows
        if not bool(row.get("reduce_only"))
    )
    return float(gross_new_risk / leverage)


def _execute_delta_plan(
    client: Any, *, intents: list[OrderIntent], planned_rows: list[dict[str, Any]], position_tolerance: float = 1e-9
) -> dict[str, Any]:
    blockers: list[str] = []
    submitted: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    planned_by_intent = {str(row["intent_id"]): dict(row) for row in planned_rows}
    for intent in intents:
        try:
            snapshot = submit_mainnet_strategy_delta_order_intent(client, intent)
        except BinanceUsdmUnknownExecutionStatus:
            recovery = recover_unknown_order_status(client, symbol=intent.symbol, client_order_id=intent.client_order_id)
            recoveries.append(recovery.to_dict())
            if recovery.status != "resolved":
                blockers.extend(recovery.blockers or [f"unknown_order_recovery_required:{intent.symbol}:{intent.client_order_id}"])
                break
            blockers.append(f"unknown_order_status_recovered_stop_for_reconcile:{intent.symbol}:{intent.client_order_id}")
            break
        except BinanceUsdmRequestError as exc:
            rejections.append(
                {
                    "intent_id": intent.intent_id,
                    "symbol": intent.symbol,
                    "client_order_id": intent.client_order_id,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )
            blockers.append(f"mainnet_delta_order_rejected:{intent.symbol}:http_{exc.status_code}:{_binance_error_code(exc.detail)}")
            break
        submitted.append(_order_row(snapshot, intent=intent, planned_row=planned_by_intent.get(intent.intent_id, {})))
        if bool(snapshot.reduce_only) != bool(intent.reduce_only):
            blockers.append(f"mainnet_delta_order_reduce_only_mismatch:{intent.symbol}:{snapshot.client_order_id}")
            break
        if snapshot.status != "FILLED":
            blockers.append(f"mainnet_delta_order_not_filled:{intent.symbol}:{snapshot.status}")
            break
        # #1: a FILLED status must mean the full requested quantity executed. Binance returns
        # executedQty == origQty for a full fill; defensively reject any under-fill (an API quirk,
        # a stale snapshot, or a cancellation that left a partial) so a wrong/mis-sized position
        # cannot slip through silently and corrupt the next cycle's delta baseline.
        executed_qty = snapshot.executed_quantity
        requested_qty = float(intent.quantity)
        if executed_qty is None or abs(float(executed_qty) - requested_qty) > max(
            float(position_tolerance), abs(requested_qty) * 1e-6
        ):
            blockers.append(
                f"mainnet_delta_order_underfilled_under_filled_status:{intent.symbol}:executed={executed_qty}:requested={requested_qty}"
            )
            break
        fills.append(_fill_row(snapshot, intent=intent))
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


def _reconcile_after_execution(
    *,
    after: dict[str, Any],
    execution: dict[str, Any],
    expected_current_positions: dict[str, float],
    position_tolerance: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(list(after.get("blockers") or []))
    actual = {
        str(row["symbol"]): float(row["positionAmt"])
        for row in list(after.get("open_positions_redacted") or [])
    }
    expected = dict(expected_current_positions)
    for row in list(execution.get("fills") or []):
        symbol = str(row.get("symbol") or "")
        signed_qty = float(row.get("quantity") or 0.0)
        if str(row.get("side") or "").upper() == "SELL":
            signed_qty *= -1.0
        expected[symbol] = float(expected.get(symbol, 0.0) or 0.0) + signed_qty
    blockers.extend(_position_match_blockers(expected=expected, actual=actual, tolerance=float(position_tolerance)))
    if int(after.get("open_order_count") or 0) != 0:
        blockers.append(f"mainnet_open_orders_after_delta_execution:{after.get('open_order_count')}")
    if int(execution.get("submitted_order_count") or 0) != int(execution.get("fill_count") or 0):
        blockers.append(
            f"mainnet_delta_submitted_fill_count_mismatch:{execution.get('submitted_order_count')}!={execution.get('fill_count')}"
        )
    return {
        "status": "reconciled" if not blockers else "reconcile_required",
        "blockers": sorted(set(blockers)),
        "expected_positions": expected,
        "open_positions_redacted": list(after.get("open_positions_redacted") or []),
        "open_order_count": int(after.get("open_order_count") or 0),
        "open_position_count": int(after.get("open_position_count") or 0),
        "submitted_order_count": int(execution.get("submitted_order_count") or 0),
        "fill_count": int(execution.get("fill_count") or 0),
    }


def _direct_delta_post_trade_reconcile_record(*, reconciliation: dict[str, Any], run_root: Path) -> dict[str, Any]:
    status = (
        "direct_delta_reconciled"
        if str(reconciliation.get("status") or "") == "reconciled"
        else "direct_delta_reconcile_required"
    )
    return {
        "status": status,
        "source": "mainnet_delta_execution_runner",
        "accepted_by_prior_live_submission_gate": False,
        "reason": (
            "direct_delta_internal_account_after_reconcile_only; "
            "prior live submission gate still requires passed_live_position_monitor"
        ),
        "blockers": list(reconciliation.get("blockers") or []),
        "artifact_root": str(run_root),
        "reconciliation_artifact": str(run_root / "reconciliation.json"),
        "reconciliation_sha256": _sha256_or_empty(run_root / "reconciliation.json"),
        "account_after_artifact": str(run_root / "account_after.json"),
        "account_after_sha256": _sha256_or_empty(run_root / "account_after.json"),
    }


def _sha256_or_empty(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_pre_execution_artifacts(
    run_root: Path,
    *,
    source_plan: dict[str, Any],
    before: dict[str, Any],
    preflight: dict[str, Any],
    daily_pnl_gate: dict[str, Any],
    account_setting_preparation: dict[str, Any],
    planned_rows: list[dict[str, Any]],
    required_confirmation: str,
    execute: bool,
) -> None:
    source_manifest = {
        "plan_root": source_plan.get("plan_root"),
        "plan_hash": source_plan.get("plan_hash"),
        "source_run_id": dict(source_plan.get("run_summary") or {}).get("run_id"),
        "source_status": dict(source_plan.get("run_summary") or {}).get("status"),
        "current_position_aware": dict(source_plan.get("run_summary") or {}).get("current_position_aware"),
        "execution_stage": source_plan.get("execution_stage"),
        "stage_gate": dict(source_plan.get("stage_gate") or {}),
        "planned_delta_order_count": int(len(planned_rows)),
        "required_confirmation": required_confirmation,
        "execute_requested": bool(execute),
    }
    write_json(run_root / "source_plan_manifest.json", source_manifest)
    write_json(run_root / "account_before.json", before)
    write_json(run_root / "mainnet_delta_preflight.json", preflight)
    write_json(run_root / "daily_realized_pnl_gate.json", daily_pnl_gate)
    write_json(run_root / "account_setting_preparation.json", account_setting_preparation)
    write_json(
        run_root / "planned_delta_orders.json",
        {
            "row_count": int(len(planned_rows)),
            "current_position_aware": True,
            "execution_stage": source_plan.get("execution_stage"),
            "planned_execution_phases": _planned_execution_phases(planned_rows),
            "rows": planned_rows,
        },
    )
    pd.DataFrame(planned_rows).to_csv(run_root / "planned_delta_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "submitted_orders.csv", index=False)
    pd.DataFrame().to_csv(run_root / "fills.csv", index=False)
    write_json(run_root / "mainnet_delta_execution.json", {"status": "not_run", "blockers": []})
    write_json(run_root / "reconciliation.json", {"status": "not_run", "blockers": []})


def _finish(
    *,
    run_root: Path,
    state_store: LiveTradingStateStore,
    run_id: str,
    started: datetime,
    status: str,
    blockers: list[str],
    source_plan: dict[str, Any],
    required_confirmation: str,
    planned_rows: list[dict[str, Any]],
    preflight_status: str = "not_run",
    reconciliation_status: str = "not_run",
    post_trade_reconcile: dict[str, Any] | None = None,
    submitted_order_count: int = 0,
    fill_count: int = 0,
    account_setting_preparation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    account_setting_preparation = dict(account_setting_preparation or {})
    source_summary = dict(source_plan.get("run_summary") or {})
    target_position_count = int(
        _float(source_summary.get("target_position_count"))
        or _frame_row_count(source_plan.get("target_positions_frame"))
    )
    current_position_count = int(
        _float(source_summary.get("current_position_count"))
        or _current_position_frame_count(source_plan.get("current_positions_frame"))
    )
    phase_counts = _dict_or_empty(source_summary.get("phase_counts"))
    if not phase_counts:
        phase_counts = _dict_or_empty(dict(source_plan.get("execution_plan") or {}).get("phase_counts"))
    deferred_phase_counts = _dict_or_empty(source_summary.get("deferred_phase_counts"))
    if not deferred_phase_counts:
        deferred_phase_counts = _dict_or_empty(dict(source_plan.get("execution_plan") or {}).get("deferred_phase_counts"))
    summary = {
        "run_id": run_id,
        "mode": "live",
        "environment": "mainnet",
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "artifact_root": str(run_root),
        "source_plan_root": source_plan.get("plan_root"),
        "source_plan_hash": source_plan.get("plan_hash"),
        "source_plan_run_id": dict(source_plan.get("run_summary") or {}).get("run_id"),
        "required_confirmation": required_confirmation,
        "execution_stage": source_plan.get("execution_stage"),
        "stage_gate": dict(source_plan.get("stage_gate") or {}),
        "planned_execution_phases": _planned_execution_phases(planned_rows),
        "current_position_aware": True,
        "mainnet_delta_execution_only": True,
        "recurring_mainnet_enabled": False,
        "order_base_url": BINANCE_USDM_MAINNET_BASE_URL,
        "preflight_status": preflight_status,
        "reconciliation_status": reconciliation_status,
        "planned_delta_order_count": int(len(planned_rows)),
        "reduce_only_intent_count": int(sum(bool(row.get("reduce_only")) for row in planned_rows)),
        "non_reduce_only_intent_count": int(sum(not bool(row.get("reduce_only")) for row in planned_rows)),
        "target_position_count": int(target_position_count),
        "current_position_count": int(current_position_count),
        "phase_counts": phase_counts,
        "deferred_phase_counts": deferred_phase_counts,
        "source_plan_target_position_count": int(target_position_count),
        "source_plan_current_position_count": int(current_position_count),
        "source_plan_phase_counts": phase_counts,
        "source_plan_deferred_phase_counts": deferred_phase_counts,
        "submitted_order_count": int(submitted_order_count),
        "fill_count": int(fill_count),
        "account_setting_preparation_status": str(account_setting_preparation.get("status") or "not_run"),
        "account_setting_call_count": int(account_setting_preparation.get("setting_call_count") or 0),
        "account_setting_changed_count": int(account_setting_preparation.get("changed_setting_count") or 0),
    }
    if post_trade_reconcile:
        summary["post_trade_reconcile"] = dict(post_trade_reconcile)
        summary["post_trade_reconcile_status"] = str(post_trade_reconcile.get("status") or "")
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live",
        status=status,
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(run_root),
        blockers=list(summary.get("blockers") or []),
    )
    success = {"mainnet_delta_execution_ready", "mainnet_delta_execution_noop", "mainnet_delta_orders_submitted"}
    return summary, 0 if status in success else 2


def _ignore_heartbeat_run_ids(run_id: str, raw_parent_ids: Any) -> list[str]:
    values = [str(run_id)]
    if isinstance(raw_parent_ids, (list, tuple, set)):
        raw_values = [str(item) for item in raw_parent_ids]
    else:
        raw_values = str(raw_parent_ids or "").split(",")
    values.extend(item.strip() for item in raw_values if item.strip())
    return values


def _ignore_running_orchestrator_for_delta_execution(local_state_health: dict[str, Any]) -> dict[str, Any]:
    ignored_modes = {"mainnet_health_monitor", "unattended_daily_policy"}
    ignored = {
        str(row.get("run_id"))
        for row in list(local_state_health.get("running_heartbeats") or [])
        if str(row.get("mode") or "") in ignored_modes and str(row.get("run_id") or "")
    }
    if not ignored:
        return local_state_health
    filtered = dict(local_state_health)
    filtered["running_heartbeats"] = [
        {**dict(row), "ignored_for_delta_execution": str(row.get("run_id") or "") in ignored}
        for row in list(local_state_health.get("running_heartbeats") or [])
    ]
    filtered["ignored_running_health_monitor_run_ids"] = sorted(ignored)
    filtered["ignored_orchestrator_run_ids"] = sorted(ignored)
    filtered["blockers"] = [
        str(item)
        for item in list(local_state_health.get("blockers") or [])
        if str(item) not in {f"active_run_in_progress:{run_id}" for run_id in ignored}
    ]
    filtered["status"] = "ok" if not filtered["blockers"] else str(local_state_health.get("status") or "blocked")
    return filtered


def _account_snapshot(
    client: Any,
    *,
    permission_client: Any,
    expected_position_mode: str,
    expected_margin_type: str,
    max_allowed_leverage: int,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    fetched_at = (now_fn or (lambda: datetime.now(UTC)))()
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    fetched_at_ms = int(fetched_at.timestamp() * 1000)
    blockers: list[str] = []
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
            blockers.append(f"mainnet_delta_requires_one_way_position_side:{symbol}:{row.get('positionSide')}")
        margin_type = str(row.get("marginType") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            blockers.append(f"margin_type_mismatch:{symbol}:expected={expected_margin_type}:actual={margin_type or 'missing'}")
        blockers.extend(
            leverage_policy_blockers(
                row.get("leverage"),
                symbol=symbol,
                max_allowed_leverage=max_allowed_leverage,
                min_leverage=MIN_LEVERAGE,
            )
        )
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "fetched_at_ms": fetched_at_ms,
        "account_config_readable": bool(account_config),
        "api_key_permissions": _redacted_api_key_permissions(api_key_permissions),
        "canTrade": can_trade,
        "position_mode": actual_mode,
        "open_order_count": int(len(open_orders)),
        "open_position_count": int(len(open_positions)),
        "available_balance_usdt": float(_float(account.get("availableBalance"))),
        "total_wallet_balance_usdt": float(_float(account.get("totalWalletBalance"))),
        "open_orders_redacted": _redacted_open_orders(open_orders),
        "position_settings_redacted": _redacted_position_settings(position_risk),
        "open_positions_redacted": open_positions,
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


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    venue = str(binance.get("venue") or "").strip().lower()
    if venue != "usdm_futures":
        blockers.append(f"mainnet_delta_requires_mainnet_usdm_venue:actual={venue or 'missing'}")
    max_leverage = _max_allowed_leverage(binance)
    if max_leverage <= 0:
        blockers.append("mainnet_delta_requires_positive_max_leverage")
    if max_leverage > 2:
        blockers.append(f"mainnet_delta_max_leverage_above_cap:{max_leverage}>2")
    risk = dict(payload.get("risk") or {})
    if bool(risk.get("trading_enabled", False)):
        blockers.append("mainnet_delta_requires_config_trading_enabled_false")
    if bool(risk.get("require_manual_live_confirm", False)) is not True:
        blockers.append("mainnet_delta_requires_manual_live_confirm")
    return blockers


def _execute_confirmation_blockers(
    args: argparse.Namespace,
    *,
    required_confirmation: str,
    execution_stage: str,
) -> list[str]:
    blockers: list[str] = []
    normalized_stage = _normalize_execution_phase(execution_stage)
    if normalized_stage not in LIVE_EXECUTION_STAGES:
        blockers.append(f"mainnet_delta_execution_stage_not_executable:{normalized_stage or 'missing'}")
    if not bool(getattr(args, "operator_enable_mainnet_delta_for_this_run", False)):
        blockers.append("missing_operator_enable_mainnet_delta_for_this_run")
    if not bool(getattr(args, "i_understand_this_places_real_mainnet_delta_orders", False)):
        blockers.append("missing_mainnet_delta_order_understanding_flag")
    confirmation = str(getattr(args, "confirm_mainnet_delta_execution", "") or "").strip()
    if confirmation != required_confirmation:
        blockers.append("missing_exact_mainnet_delta_confirmation")
    return blockers


def _account_setting_prepare_confirmation_blockers(args: argparse.Namespace, *, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not _auto_prepare_planned_symbol_settings_enabled(payload):
        blockers.append("account_setting_prepare_disabled_in_config")
    if bool(getattr(args, "execute_mainnet_delta_orders", False)):
        return blockers
    if not bool(getattr(args, "operator_enable_mainnet_account_settings_for_this_run", False)):
        blockers.append("missing_operator_enable_mainnet_account_settings_for_this_run")
    if not bool(getattr(args, "i_understand_this_modifies_mainnet_account_settings", False)):
        blockers.append("missing_i_understand_this_modifies_mainnet_account_settings")
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


def _redacted_position_settings(position_risk: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in position_risk:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "positionSide": str(item.get("positionSide") or "BOTH"),
                "marginType": str(item.get("marginType") or ""),
                "leverage": str(item.get("leverage") or ""),
                "isolated": _optional_bool(item.get("isolated")),
            }
        )
    return sorted(rows, key=lambda row: str(row["symbol"]))


def _order_row(snapshot: BinanceOrderSnapshot, *, intent: OrderIntent, planned_row: dict[str, Any]) -> dict[str, Any]:
    row = snapshot.to_dict()
    row.update(
        {
            "intent_id": intent.intent_id,
            "target_position_amt": intent.target_position_amt,
            "final_target_position_amt": intent.final_target_position_amt,
            "current_position_amt": intent.current_position_amt,
            "delta_position_amt": intent.delta_position_amt,
            "execution_phase": intent.execution_phase,
            "delta_classification": intent.delta_classification,
            "second_phase_required": bool(intent.second_phase_required),
            "planned_rounded_notional_usdt": float(planned_row.get("rounded_notional_usdt") or 0.0),
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
        "execution_phase": intent.execution_phase,
        "delta_classification": intent.delta_classification,
        "order_id": snapshot.order_id,
    }


def _source_plan_margin_cushion_gate(plan_root: Path) -> dict[str, Any] | None:
    gate = _read_json(plan_root / "margin_cushion_gate.json")
    if not isinstance(gate, dict) or not gate:
        return None
    status = str(gate.get("status") or "").strip().lower()
    if status not in {"passed", "blocked"}:
        return None
    return gate


def _source_plan_pre_reduce_only_margin_cushion_gate(plan_root: Path) -> dict[str, Any] | None:
    gate = _read_json(plan_root / "pre_reduce_only_margin_cushion_gate.json")
    return gate if isinstance(gate, dict) and gate else None


def _expected_current_positions(*, current_frame: pd.DataFrame, intents_frame: pd.DataFrame) -> dict[str, float]:
    expected: dict[str, float] = {}
    if not current_frame.empty and {"symbol", "positionAmt"}.issubset(set(current_frame.columns)):
        for _, row in current_frame.iterrows():
            symbol = str(row.get("symbol") or "")
            if symbol:
                expected[symbol] = _float(row.get("positionAmt"))
    if isinstance(intents_frame, pd.DataFrame) and not intents_frame.empty:
        for _, row in intents_frame.iterrows():
            symbol = str(row.get("symbol") or "")
            if symbol and symbol not in expected:
                expected[symbol] = _float(row.get("current_position_amt"))
    return {symbol: float(amount) for symbol, amount in expected.items() if abs(float(amount)) > 1e-12}


def _required_confirmation(*, plan_hash: str, execution_stage: str) -> str:
    digest = str(plan_hash or "missing")[:16]
    stage_token = _confirmation_stage_token(execution_stage)
    return f"{CONFIRMATION_PREFIX}:PLAN_SHA256={digest}:CURRENT_POSITION_AWARE:ONE_WAY:CROSS_MAX_LEVERAGE=2:EXECUTION_STAGE={stage_token}:DELTA_ONLY:NO_RECURRING:NO_DAILY_PNL_GATE"


def _confirmation_stage_token(execution_stage: str) -> str:
    normalized = _normalize_execution_phase(execution_stage)
    if not normalized:
        return "MISSING"
    return normalized.upper()


def _normalize_execution_phase(value: Any) -> str:
    return str(value or "").strip().lower()


def _planned_execution_phases(planned_rows: list[dict[str, Any]]) -> list[str]:
    return sorted({phase for phase in (_normalize_execution_phase(row.get("execution_phase")) for row in planned_rows) if phase})


def _delta_client_order_id(*, plan_hash: str, symbol: str, seq: int) -> str:
    digest = hashlib.sha256(f"delta:{plan_hash}:{symbol}:{seq}".encode("utf-8")).hexdigest()[:18]
    return f"hvbal-dl-{digest}-{seq}"


def _plan_artifact_hash(plan_root: Path, names: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        path = plan_root / name
        if not path.exists():
            continue
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _frontier_submit_gate(
    *, plan: dict[str, Any], payload: dict[str, Any], operator_state: dict[str, Any]
) -> dict[str, Any]:
    """Arm→submit binding for the frozen frontier. The plan runner persisted its frontier
    verdict as ``frontier_plan.json``; here we refuse to submit unless a FRESH resolution
    from the current live config + operator state still agrees.

    Non-breaking by construction:
      * absent (old plans) or dormant (default-off) -> ``not_applicable``, no new blocker.
      * plan was ``blocked`` at arm  -> block (must never reach submit).
      * plan was ``armed_ready``     -> re-resolve; block on disarm, terminal kill-switch,
                                        or any arm-binding drift between plan and submit.
    """
    plan_root = str(plan.get("plan_root") or "")
    plan_frontier = _read_json(Path(plan_root) / FRONTIER_PLAN_ARTIFACT) if plan_root else {}
    plan_status = str(plan_frontier.get("status") or "absent") if plan_frontier else "absent"
    if plan_status in {"absent", "dormant"}:
        return {"status": "not_applicable", "plan_frontier_status": plan_status, "blockers": []}
    if plan_status == "blocked":
        return {
            "status": "blocked",
            "plan_frontier_status": "blocked",
            "plan_arm_binding": plan_frontier.get("arm_binding"),
            "blockers": ["frontier_plan_was_blocked_at_arm"],
        }
    # plan_status == "armed_ready": bind to a fresh resolution.
    fresh = resolve_frontier_live_plan(payload, operator_state=operator_state)
    plan_binding = str(plan_frontier.get("arm_binding") or "")
    fresh_binding = str(fresh.arm_binding or "")
    blockers: list[str] = []
    if not fresh.is_armed_ready:
        blockers.append("frontier_disarmed_or_invalid_since_plan")
    if bool(fresh.terminal_disarm):
        blockers.append("frontier_terminal_disarm_at_submit")
    if not plan_binding or plan_binding != fresh_binding:
        blockers.append(
            f"frontier_arm_submit_binding_mismatch:{plan_binding[:12]}!={fresh_binding[:12]}"
        )
    return {
        "status": "armed_ready" if not blockers else "blocked",
        "plan_frontier_status": "armed_ready",
        "plan_arm_binding": plan_binding,
        "resolved_arm_binding": fresh_binding,
        "resolved_status": fresh.status,
        "terminal_disarm": bool(fresh.terminal_disarm),
        "blockers": sorted(set(blockers)),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _max_allowed_leverage(binance: dict[str, Any]) -> int:
    raw = binance.get("max_leverage")
    if raw is None:
        raw = binance.get("leverage")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _auto_prepare_planned_symbol_settings_enabled(payload: dict[str, Any]) -> bool:
    binance = dict(payload.get("binance") or {})
    return bool(
        _optional_bool(binance.get("auto_prepare_planned_symbol_settings"))
        or _optional_bool(binance.get("auto_prepare_cross_2x"))
    )


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


def _bool(value: Any) -> bool:
    optional = _optional_bool(value)
    return bool(optional) if optional is not None else bool(value)


def _dict_or_empty(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(_float(item)) for key, item in value.items()}


def _frame_row_count(value: Any) -> int:
    if isinstance(value, pd.DataFrame):
        return int(len(value.index))
    return 0


def _current_position_frame_count(value: Any) -> int:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return 0
    if "positionAmt" not in value.columns:
        return int(len(value.index))
    return int(sum(abs(_float(row.get("positionAmt"))) > 1e-12 for _, row in value.iterrows()))


def _float(value: Any) -> float:
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _binance_error_code(detail: Any) -> str:
    try:
        payload = json.loads(str(detail))
        return str(payload.get("code") or "unknown")
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
