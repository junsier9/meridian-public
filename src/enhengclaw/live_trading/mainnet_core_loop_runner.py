from __future__ import annotations

import argparse
import json
import os
import time
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import BINANCE_USDM_MAINNET_BASE_URL, BinanceUsdmClient
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.daily_rebalance_slot_gate import (
    FROZEN_TARGET_SNAPSHOT_ARTIFACT,
    REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
)
from enhengclaw.live_trading.live_position_monitor import run_live_position_monitor
from enhengclaw.live_trading.live_risk_controls import (
    classify_exception_strategy,
    evaluate_margin_cushion_gate,
    evaluate_per_order_notional_gate,
    removed_daily_realized_pnl_gate,
)
from enhengclaw.live_trading.mainnet_delta_execution_runner import run_mainnet_delta_execution
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import (
    MULTIPHASE_TARGET_ENGINE,
    run_mainnet_multiphase_current_position_rebalance_plan,
)
from enhengclaw.live_trading.mainnet_rebalance_plan_runner import run_mainnet_current_position_rebalance_plan
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.unattended_budget_hook import (
    budget_gate_enabled,
    budget_store_from_payload,
    per_order_gate_enabled,
    per_order_hard_multiplier,
    post_submit_reconcile,
    pre_submit_budget_blockers,
    projected_turnover_usdt,
    realized_turnover_usdt,
    reconcile_or_block_realized,
    reservation_key,
    reserved_ok,
    resolved_per_order_notional_cap,
)
from enhengclaw.live_trading.unattended_epoch_controller import evaluate_unattended_epoch_runtime_gate
from enhengclaw.quant_research.contracts import read_json, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mainnet hv_balanced core closed-loop scaffold. It reconciles the account, builds a "
            "current-position-aware target/delta plan, runs live gates, and can only execute delta "
            "orders when explicitly enabled. Default mode submits zero orders."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_core_loop.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--reference-run", default="")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument("--execute-live-delta", action="store_true")
    parser.add_argument("--operator-enable-live-delta-for-this-run", action="store_true")
    parser.add_argument("--i-understand-this-places-real-mainnet-delta-orders", action="store_true")
    parser.add_argument("--i-understand-daily-realized-pnl-gate-is-active", action="store_true")
    parser.add_argument("--confirm-mainnet-delta-execution", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--ignore-heartbeat-run-id", default="")
    parser.add_argument(
        "--capital-topup",
        action="store_true",
        help=(
            "After a static latest-closed-rebalance-slot plan is noop/dust, try one controlled "
            "capital top-up plan that can only add to existing targets."
        ),
    )
    parser.add_argument(
        "--fast-follow-entry-second",
        action="store_true",
        help=(
            "Allow the live cooldown gate to be bypassed after a recent reconciled reduce_first. "
            "The fresh plan may execute another reduce_first residual or entry_second, but never a mixed stage."
        ),
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_core_loop(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_core_loop(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    monitor_runner: Callable[..., tuple[dict[str, Any], int]] = run_live_position_monitor,
    plan_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_current_position_rebalance_plan,
    delta_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_delta_execution,
    account_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_core_loop.yaml"))
    payload = live_config.payload
    core_cfg = dict(payload.get("core_loop") or {})
    requested_cycles = int(getattr(args, "cycles", None) or core_cfg.get("max_cycles_per_invocation", 1) or 1)
    max_cycles = int(core_cfg.get("max_cycles_per_invocation", 1) or 1)
    cycles = max(1, requested_cycles)
    interval_seconds = float(
        getattr(args, "interval_seconds", None)
        if getattr(args, "interval_seconds", None) is not None
        else core_cfg.get("interval_seconds", 0.0) or 0.0
    )
    max_cycles = max(1, max_cycles)
    interval_seconds = max(0.0, interval_seconds)
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-core-loop"
    run_root = live_config.artifact_root.parent / "mainnet_core_loop" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()

    execute_live_delta = bool(getattr(args, "execute_live_delta", False))
    target_engine = _core_loop_target_engine(args=args, payload=payload)
    blockers = _config_blockers(payload, execute_live_delta=execute_live_delta)
    if (
        target_engine == MULTIPHASE_TARGET_ENGINE
        and execute_live_delta
        and not _as_bool(core_cfg.get("allow_multiphase_live_delta"), default=False)
    ):
        blockers.append("mainnet_core_loop_multiphase_target_engine_live_delta_not_explicitly_allowed")
    if execute_live_delta and cycles > max_cycles:
        blockers.append(f"mainnet_core_loop_requested_cycles_above_config_max:{cycles}>{max_cycles}")
    local_state_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=float(dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900) or 900),
        ignore_run_ids=[run_id, str(getattr(args, "ignore_heartbeat_run_id", "") or "")],
    )
    local_state_health = _ignore_running_health_monitor_for_core_loop(local_state_health)
    blockers.extend(list(local_state_health.get("blockers") or []))
    operator_state = state_store.read_operator_state()
    if bool(operator_state.get("paused")):
        blockers.append("operator_paused")
    fast_follow_entry_second = bool(getattr(args, "fast_follow_entry_second", False))
    live_delta_cooldown = _live_delta_cooldown_context(
        state_store=state_store,
        payload=payload,
        now=started,
        fast_follow_entry_second=fast_follow_entry_second,
    )
    credentials = _credential_context(payload=payload, env=env or os.environ)
    blockers.extend(credentials["blockers"])
    write_json(run_root / "local_state_health.json", local_state_health)
    write_json(run_root / "operator_state.json", operator_state)
    write_json(run_root / "live_delta_cooldown_context.json", live_delta_cooldown)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live",
        status="running",
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        artifact_root=str(run_root),
    )

    cycle_rows: list[dict[str, Any]] = []
    for cycle_index in range(1, cycles + 1):
        cycle = _run_cycle(
            args=args,
            payload=payload,
            state_store=state_store,
            run_id=run_id,
            cycle_index=cycle_index,
            env=env or os.environ,
            credentials=credentials,
            blocked_before_cycle=bool(blockers),
            monitor_runner=monitor_runner,
            plan_runner=plan_runner,
            delta_runner=delta_runner,
            account_client_factory=account_client_factory,
            now=started if cycle_index == 1 else datetime.now(UTC),
            fast_follow_entry_second=fast_follow_entry_second,
            target_engine=target_engine,
            live_delta_cooldown_context=live_delta_cooldown,
        )
        cycle_rows.append(cycle)
        write_json(run_root / f"cycle_{cycle_index:03d}.json", cycle)
        state_store.record_live_artifact(
            run_id=run_id,
            artifact_type="core_loop_cycle",
            artifact_id=f"{run_id}:cycle:{cycle_index:03d}",
            payload=cycle,
        )
        blockers.extend(str(item) for item in list(cycle.get("blockers") or []))
        if blockers:
            break
        if cycle_index < cycles and interval_seconds > 0.0:
            sleep_fn(interval_seconds)

    submitted_total = int(sum(int(row.get("orders_submitted") or 0) for row in cycle_rows))
    fill_total = int(sum(int(row.get("fill_count") or 0) for row in cycle_rows))
    clean_cycle_count = int(
        sum(
            str(row.get("status") or "")
            in {
                "cycle_plan_only_ready",
                "cycle_noop",
                "cycle_dust_noop",
                "cycle_hold_until_next_rebalance_slot",
                "cycle_deferred",
                "cycle_executed_reconciled",
            }
            for row in cycle_rows
        )
    )
    status = "mainnet_core_loop_completed" if not blockers and len(cycle_rows) == cycles else "mainnet_core_loop_blocked"
    resolved_live_delta_cooldown = _resolved_live_delta_cooldown(cycle_rows, fallback=live_delta_cooldown)
    summary = {
        "run_id": run_id,
        "status": status,
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(run_root),
        "config": str(live_config.path),
        "configured_cycle_count": int(cycles),
        "requested_cycle_count": int(requested_cycles),
        "max_cycles_per_invocation": int(max_cycles),
        "completed_cycle_count": int(len(cycle_rows)),
        "clean_cycle_count": clean_cycle_count,
        "mode": "core_loop",
        "account_reconcile": True,
        "strategy_target": True,
        "current_position_aware_delta": True,
        "risk_gate_stack": True,
        "execution_requested": execute_live_delta,
        "target_engine": target_engine,
        "fast_follow_entry_second_requested": bool(fast_follow_entry_second),
        "orders_submitted": submitted_total,
        "fill_count": fill_total,
        "live_delta_authorized": bool(execute_live_delta and submitted_total > 0 and not blockers),
        "recurring_mainnet_enabled": False,
        "live_delta_cooldown": resolved_live_delta_cooldown,
        "cycles": cycle_rows,
    }
    write_json(run_root / "live_delta_cooldown.json", resolved_live_delta_cooldown)
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="core_loop_summary",
        artifact_id=f"{run_id}:summary",
        payload=summary,
    )
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live",
        status=status,
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(run_root),
        blockers=list(summary["blockers"]),
    )
    return summary, 0 if status == "mainnet_core_loop_completed" else 2


def _run_cycle(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    state_store: LiveTradingStateStore,
    run_id: str,
    cycle_index: int,
    env: Mapping[str, str],
    credentials: dict[str, Any],
    blocked_before_cycle: bool,
    monitor_runner: Callable[..., tuple[dict[str, Any], int]],
    plan_runner: Callable[..., tuple[dict[str, Any], int]],
    delta_runner: Callable[..., tuple[dict[str, Any], int]],
    account_client_factory: Callable[..., Any],
    now: datetime,
    fast_follow_entry_second: bool,
    target_engine: str,
    live_delta_cooldown_context: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    cycle: dict[str, Any] = {
        "cycle_index": int(cycle_index),
        "status": "not_run",
        "blockers": blockers,
        "orders_submitted": 0,
        "fill_count": 0,
        "live_delta_authorized": False,
        "target_engine": str(target_engine),
        "capital_topup_requested": bool(getattr(args, "capital_topup", False)),
        "capital_topup_attempted": False,
    }
    if blocked_before_cycle:
        cycle["status"] = "cycle_skipped_prior_blocker"
        cycle["blockers"] = ["prior_core_loop_blocker"]
        cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
        return cycle

    monitor_summary, monitor_exit = monitor_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            reference_run=str(getattr(args, "reference_run", "") or ""),
            api_key_env="",
            api_secret_env="",
            max_abs_position_drift_qty=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
        ),
        env=env,
    )
    cycle["account_reconcile"] = _phase_record(monitor_summary, monitor_exit)
    cycle["monitor_artifact_root"] = str(monitor_summary.get("artifact_root") or "")
    if monitor_exit != 0:
        blockers.append(f"account_reconcile_failed:{monitor_summary.get('status')}")
        blockers.extend(str(item) for item in list(monitor_summary.get("blockers") or []))
    monitor_report = _read_optional_json(str(monitor_summary.get("artifact_root") or ""), "monitor_report.json")
    cycle["account_reconcile_artifacts"] = _account_artifact_payload(str(monitor_summary.get("artifact_root") or ""))
    account_summary = dict(monitor_report.get("account") or {})
    if not account_summary:
        account_summary = {
            "available_balance_usdt": monitor_summary.get("available_balance_usdt", 0.0),
            "total_wallet_balance_usdt": monitor_summary.get("total_wallet_balance_usdt", 0.0),
        }
    open_order_count = int(float(monitor_summary.get("open_order_count") or account_summary.get("open_order_count") or 0))
    cycle["open_order_count"] = open_order_count
    if open_order_count != 0:
        blockers.append(f"mainnet_open_orders_exist:{open_order_count}")

    daily_gate = removed_daily_realized_pnl_gate(config=payload)
    cycle["daily_realized_pnl_gate"] = daily_gate

    if blockers:
        cycle["plan_status"] = "skipped_due_to_pre_plan_gate"
        cycle["status"] = "cycle_blocked"
        cycle["blockers"] = sorted(set(blockers))
        cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
        return cycle

    target_as_of = _core_loop_target_as_of(args=args, payload=payload)
    cycle["target_as_of"] = target_as_of
    effective_plan_runner = _target_plan_runner(plan_runner=plan_runner, target_engine=target_engine)
    plan_summary, plan_exit = effective_plan_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            as_of=target_as_of,
            fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
            symbols=str(getattr(args, "symbols", "") or ""),
            public_market_data=bool(getattr(args, "public_market_data", False)),
            api_key_env="",
            api_secret_env="",
            capital_topup=False,
            target_engine=str(target_engine),
        ),
        env=env,
    )
    cycle["strategy_target"] = _phase_record(plan_summary, plan_exit)
    cycle["plan_artifact_root"] = str(plan_summary.get("artifact_root") or "")
    cycle["plan_status"] = str(plan_summary.get("status") or "")
    cycle["planned_delta_order_count"] = int(plan_summary.get("planned_delta_order_count") or 0)
    cycle["strategy_plan_artifacts"] = _strategy_plan_artifact_payload(cycle["plan_artifact_root"])
    if plan_exit != 0:
        blockers.append(f"strategy_target_failed:{plan_summary.get('status')}")
        blockers.extend(str(item) for item in list(plan_summary.get("blockers") or []))
    blockers.extend(_plan_data_freshness_blockers(cycle["plan_artifact_root"], payload=payload))

    if not blockers and _should_attempt_capital_topup(args=args, payload=payload, static_plan_summary=plan_summary):
        cycle["static_strategy_target"] = cycle["strategy_target"]
        cycle["static_plan_artifact_root"] = cycle["plan_artifact_root"]
        cycle["static_plan_status"] = cycle["plan_status"]
        cycle["static_strategy_plan_artifacts"] = cycle["strategy_plan_artifacts"]
        topup_summary, topup_exit = effective_plan_runner(
            Namespace(
                config=str(getattr(args, "config", "")),
                as_of=target_as_of,
                fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
                symbols=str(getattr(args, "symbols", "") or ""),
                public_market_data=bool(getattr(args, "public_market_data", False)),
                api_key_env="",
                api_secret_env="",
                capital_topup=True,
                target_engine=str(target_engine),
            ),
            env=env,
        )
        cycle["capital_topup_attempted"] = True
        cycle["capital_topup_strategy_target"] = _phase_record(topup_summary, topup_exit)
        cycle["capital_topup_plan_artifact_root"] = str(topup_summary.get("artifact_root") or "")
        cycle["capital_topup_plan_status"] = str(topup_summary.get("status") or "")
        if topup_exit == 0:
            plan_summary = topup_summary
            plan_exit = topup_exit
            cycle["capital_topup_selected"] = True
            cycle["strategy_target"] = _phase_record(plan_summary, plan_exit)
            cycle["plan_artifact_root"] = str(plan_summary.get("artifact_root") or "")
            cycle["plan_status"] = str(plan_summary.get("status") or "")
            cycle["planned_delta_order_count"] = int(plan_summary.get("planned_delta_order_count") or 0)
            cycle["strategy_plan_artifacts"] = _strategy_plan_artifact_payload(cycle["plan_artifact_root"])
            blockers.extend(_plan_data_freshness_blockers(cycle["plan_artifact_root"], payload=payload))
        else:
            cycle["capital_topup_selected"] = False
            cycle["capital_topup_fallback_to_static_plan"] = True
            cycle["capital_topup_blockers"] = list(topup_summary.get("blockers") or [])
        if (
            bool(cycle.get("capital_topup_selected"))
            and bool(getattr(args, "execute_live_delta", False))
            and not _capital_topup_live_execution_enabled(payload)
        ):
            blockers.append("capital_topup_live_execution_disabled_in_config")

    plan_status = str(plan_summary.get("status") or "")
    frozen_target_snapshot = _read_optional_json(cycle["plan_artifact_root"], FROZEN_TARGET_SNAPSHOT_ARTIFACT)
    frozen_slot_gate = _read_optional_json(cycle["plan_artifact_root"], "frozen_slot_gate.json")
    if frozen_target_snapshot:
        cycle["frozen_target_snapshot"] = {
            "slot_id": str(frozen_target_snapshot.get("slot_id") or ""),
            "target_hash": str(frozen_target_snapshot.get("target_hash") or ""),
            "status": str(frozen_target_snapshot.get("status") or ""),
        }
    if frozen_slot_gate:
        cycle["frozen_slot_gate"] = frozen_slot_gate
    if not blockers and plan_status == "mainnet_current_position_rebalance_hold_until_next_rebalance_slot":
        cycle["margin_cushion_gate"] = {
            "status": "skipped",
            "reason": "hold_until_next_rebalance_slot_has_no_delta_orders",
            "planned_additional_initial_margin_usdt": 0.0,
            "blockers": [],
            "warnings": [],
        }
        cycle["execution_status"] = "hold_until_next_rebalance_slot"
        cycle["status"] = "cycle_hold_until_next_rebalance_slot"
        cycle["dust_delta_noop"] = bool(plan_summary.get("dust_delta_noop"))
        cycle["dust_delta_symbols"] = list(plan_summary.get("dust_delta_symbols") or [])
        cycle["blockers"] = []
        cycle["exception_policy"] = classify_exception_strategy([], context={"cycle_index": cycle_index})
        return cycle
    plan_margin_gate = _plan_margin_cushion_gate(cycle["plan_artifact_root"])
    planned_margin = (
        _float(plan_margin_gate.get("planned_additional_initial_margin_usdt"))
        if plan_margin_gate is not None
        else _planned_additional_initial_margin_usdt(cycle["plan_artifact_root"], payload=payload)
    )
    if plan_status == "mainnet_current_position_rebalance_deferred":
        margin_gate = plan_margin_gate or evaluate_margin_cushion_gate(
            account_summary,
            config=payload,
            planned_additional_initial_margin_usdt=0.0,
            require_configured=True,
        )
        deferred_if_executed_margin_gate = _plan_deferred_if_executed_margin_cushion_gate(
            cycle["plan_artifact_root"]
        ) or evaluate_margin_cushion_gate(
            account_summary,
            config=payload,
            planned_additional_initial_margin_usdt=planned_margin,
            require_configured=True,
        )
        cycle["margin_cushion_gate"] = margin_gate
        cycle["deferred_if_executed_margin_cushion_gate"] = deferred_if_executed_margin_gate
        pre_reduce_only_margin_gate = _plan_pre_reduce_only_margin_cushion_gate(cycle["plan_artifact_root"])
        if pre_reduce_only_margin_gate is not None:
            cycle["pre_reduce_only_margin_cushion_gate"] = pre_reduce_only_margin_gate
        blockers.extend(str(item) for item in list(margin_gate.get("blockers") or []))
        if blockers:
            cycle["execution_status"] = "skipped_due_to_gate_blocker"
            cycle["status"] = "cycle_blocked"
            cycle["blockers"] = sorted(set(blockers))
            cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
            return cycle
        cycle["execution_status"] = "deferred_no_live_delta"
        cycle["status"] = "cycle_deferred"
        cycle["capital_deployment_deferred"] = True
        cycle["capital_topup_gate_status"] = str(plan_summary.get("capital_topup_gate_status") or "")
        cycle["capital_topup_gate_blockers"] = list(plan_summary.get("capital_topup_gate_blockers") or [])
        cycle["blockers"] = []
        cycle["exception_policy"] = classify_exception_strategy([], context={"cycle_index": cycle_index})
        return cycle
    margin_gate = plan_margin_gate or evaluate_margin_cushion_gate(
        account_summary,
        config=payload,
        planned_additional_initial_margin_usdt=planned_margin,
        require_configured=True,
    )
    cycle["margin_cushion_gate"] = margin_gate
    pre_reduce_only_margin_gate = _plan_pre_reduce_only_margin_cushion_gate(cycle["plan_artifact_root"])
    if pre_reduce_only_margin_gate is not None:
        cycle["pre_reduce_only_margin_cushion_gate"] = pre_reduce_only_margin_gate
    blockers.extend(str(item) for item in list(margin_gate.get("blockers") or []))

    if blockers:
        cycle["execution_status"] = "skipped_due_to_gate_blocker"
        cycle["status"] = "cycle_blocked"
        cycle["blockers"] = sorted(set(blockers))
        cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
        return cycle
    if plan_status in {
        "mainnet_current_position_rebalance_noop",
        "mainnet_current_position_rebalance_dust_noop",
        "mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
    }:
        if plan_status.endswith("_hold_until_next_rebalance_slot"):
            cycle["execution_status"] = "hold_until_next_rebalance_slot"
            cycle["status"] = "cycle_hold_until_next_rebalance_slot"
        else:
            cycle["execution_status"] = "noop_dust_delta" if plan_status.endswith("_dust_noop") else "noop_no_delta"
            cycle["status"] = "cycle_dust_noop" if plan_status.endswith("_dust_noop") else "cycle_noop"
        cycle["dust_delta_noop"] = bool(plan_summary.get("dust_delta_noop"))
        cycle["dust_delta_symbols"] = list(plan_summary.get("dust_delta_symbols") or [])
        if not plan_status.endswith("_hold_until_next_rebalance_slot"):
            completion = _mark_frozen_rebalance_slot_completed(
                state_store=state_store,
                run_id=run_id,
                frozen_target_snapshot=frozen_target_snapshot,
                artifact_root=cycle["plan_artifact_root"],
                reason=str(cycle["execution_status"]),
            )
            if completion is not None:
                cycle["frozen_rebalance_slot_completion"] = completion
        cycle["blockers"] = []
        cycle["exception_policy"] = classify_exception_strategy([], context={"cycle_index": cycle_index})
        return cycle

    plan_root = str(plan_summary.get("artifact_root") or "")
    dry_run_summary, dry_run_exit = delta_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            plan_artifact=plan_root,
            execute_mainnet_delta_orders=False,
            prepare_planned_symbol_account_settings=bool(getattr(args, "execute_live_delta", False)),
            operator_enable_mainnet_delta_for_this_run=False,
            operator_enable_mainnet_account_settings_for_this_run=bool(getattr(args, "execute_live_delta", False)),
            i_understand_this_places_real_mainnet_delta_orders=False,
            i_understand_this_modifies_mainnet_account_settings=bool(getattr(args, "execute_live_delta", False)),
            i_understand_daily_loss_budget_is_review_only=False,
            i_understand_daily_realized_pnl_gate_is_active=False,
            confirm_mainnet_delta_execution="",
            position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
            ignore_heartbeat_run_id=_nested_ignore_heartbeat_run_ids(run_id, getattr(args, "ignore_heartbeat_run_id", "")),
        ),
        env=env,
    )
    cycle["delta_preflight"] = _phase_record(dry_run_summary, dry_run_exit)
    cycle["delta_preflight_artifact_root"] = str(dry_run_summary.get("artifact_root") or "")
    cycle["delta_preflight_artifacts"] = _delta_preflight_artifact_payload(cycle["delta_preflight_artifact_root"])
    if dry_run_exit != 0:
        blockers.append(f"delta_preflight_failed:{dry_run_summary.get('status')}")
        blockers.extend(str(item) for item in list(dry_run_summary.get("blockers") or []))
    live_delta_policy = _live_delta_policy_gate(
        payload=payload,
        dry_run_summary=dry_run_summary,
        fast_follow_entry_second=fast_follow_entry_second,
    )
    cycle["live_delta_policy_gate"] = live_delta_policy
    blockers.extend(str(item) for item in list(live_delta_policy.get("blockers") or []))
    live_delta_tempo = _live_delta_tempo_gate(
        payload=payload,
        cooldown_context=live_delta_cooldown_context,
        dry_run_summary=dry_run_summary,
        now=now,
        fast_follow_entry_second=fast_follow_entry_second,
    )
    cycle["live_delta_cooldown"] = live_delta_tempo
    cycle["live_delta_tempo_gate"] = live_delta_tempo
    if bool(getattr(args, "execute_live_delta", False)):
        blockers.extend(str(item) for item in list(live_delta_tempo.get("blockers") or []))
    # ---- Restricted-unattended pre-submit safety gates ----
    # Both default-off; only consulted when execute_live_delta and the cycle is
    # otherwise clean and about to submit, so attended / canary / single-run flows
    # are untouched. Per-order notional (defence-in-depth sanity ceiling) runs
    # FIRST; the budget RESERVE-BEFORE-SUBMIT runs only if the cycle is still
    # clean. Any blocker cascades into the same `blockers` list checked just
    # below, so the supervisor's disarm_on_blocker halts the loop.
    budget_reserved = False
    budget_store = None
    budget_reservation_key = ""
    execute_delta = bool(getattr(args, "execute_live_delta", False))
    if execute_delta and not blockers and (per_order_gate_enabled(payload) or budget_gate_enabled(payload)):
        planned_orders_json = _read_optional_json(
            str(cycle.get("delta_preflight_artifact_root") or ""), "planned_delta_orders.json"
        )
        owner_intent_gate = _live_delta_owner_intent_gate(
            state_store=state_store,
            payload=payload,
            dry_run_summary=dry_run_summary,
            planned_orders_json=planned_orders_json,
            now=now,
            fast_follow_entry_second=fast_follow_entry_second,
        )
        cycle["live_delta_owner_intent_gate"] = owner_intent_gate
        blockers.extend(str(item) for item in list(owner_intent_gate.get("blockers") or []))
        if per_order_gate_enabled(payload):
            capital_context = _read_optional_json(
                str(cycle.get("plan_artifact_root") or ""), "capital_allocation_context.json"
            )
            per_order_gate = evaluate_per_order_notional_gate(
                list(planned_orders_json.get("rows") or []),
                per_order_notional_cap_usdt=resolved_per_order_notional_cap(
                    payload, capital_context, capital_topup_selected=bool(cycle.get("capital_topup_selected"))
                ),
                hard_multiplier=per_order_hard_multiplier(payload),
                require_configured=True,
            )
            cycle["per_order_notional_gate"] = per_order_gate
            blockers.extend(str(item) for item in list(per_order_gate.get("blockers") or []))
        if budget_gate_enabled(payload) and not blockers:
            budget_store = budget_store_from_payload(payload)
            budget_epoch = budget_store.read_current_epoch()
            # A missing/empty dry-run artifact is "turnover unknown" -> fail closed
            # (None), never a free 0.0-turnover reserve. projected_turnover_usdt
            # only legitimately returns 0.0 for an explicit empty-rows plan, which
            # should not reach a live submit anyway.
            projected = projected_turnover_usdt(planned_orders_json) if planned_orders_json else None
            plan_ref = str(dry_run_summary.get("plan_hash") or cycle.get("plan_artifact_root") or "")
            budget_reservation_key = reservation_key(
                budget_epoch.epoch_id if budget_epoch is not None else "no_epoch", plan_ref, cycle_index
            )
            budget_blockers, budget_result = pre_submit_budget_blockers(
                budget_store,
                enabled=True,
                epoch=budget_epoch,
                projected_turnover=projected,
                run_id=run_id,
                reservation_key=budget_reservation_key,
                now=now,
            )
            cycle["unattended_budget_gate"] = budget_result
            blockers.extend(budget_blockers)
            budget_reserved = reserved_ok(budget_result)
    if blockers:
        cycle["execution_status"] = "skipped_due_to_delta_preflight_blocker"
        cycle["status"] = "cycle_blocked"
        cycle["blockers"] = sorted(set(blockers))
        cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
        return cycle

    if not bool(getattr(args, "execute_live_delta", False)):
        cycle["execution_status"] = "dry_run_ready_no_live_delta_requested"
        cycle["required_confirmation"] = str(dry_run_summary.get("required_confirmation") or "")
        cycle["status"] = "cycle_plan_only_ready"
        cycle["blockers"] = []
        cycle["exception_policy"] = classify_exception_strategy([], context={"cycle_index": cycle_index})
        return cycle

    confirm_value = str(getattr(args, "confirm_mainnet_delta_execution", "") or "")
    if bool(dict(payload.get("core_loop") or {}).get("auto_confirm_delta_after_preflight", False)):
        confirm_value = str(dry_run_summary.get("required_confirmation") or "")
    execution_summary, execution_exit = delta_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            plan_artifact=plan_root,
            execute_mainnet_delta_orders=True,
            prepare_planned_symbol_account_settings=False,
            operator_enable_mainnet_delta_for_this_run=bool(getattr(args, "operator_enable_live_delta_for_this_run", False)),
            operator_enable_mainnet_account_settings_for_this_run=bool(
                getattr(args, "operator_enable_live_delta_for_this_run", False)
            ),
            i_understand_this_places_real_mainnet_delta_orders=bool(
                getattr(args, "i_understand_this_places_real_mainnet_delta_orders", False)
            ),
            i_understand_this_modifies_mainnet_account_settings=bool(
                getattr(args, "i_understand_this_places_real_mainnet_delta_orders", False)
            ),
            i_understand_daily_loss_budget_is_review_only=False,
            i_understand_daily_realized_pnl_gate_is_active=bool(
                getattr(args, "i_understand_daily_realized_pnl_gate_is_active", False)
            ),
            confirm_mainnet_delta_execution=confirm_value,
            position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
            ignore_heartbeat_run_id=_nested_ignore_heartbeat_run_ids(run_id, getattr(args, "ignore_heartbeat_run_id", "")),
        ),
        env=env,
    )
    cycle["execution"] = _phase_record(execution_summary, execution_exit)
    cycle["execution_artifact_root"] = str(execution_summary.get("artifact_root") or "")
    cycle["orders_submitted"] = int(execution_summary.get("submitted_order_count") or 0)
    cycle["fill_count"] = int(execution_summary.get("fill_count") or 0)
    if execution_exit != 0:
        blockers.append(f"delta_execution_failed:{execution_summary.get('status')}")
        blockers.extend(str(item) for item in list(execution_summary.get("blockers") or []))
    cycle["execution_artifacts"] = _execution_artifact_payload(cycle["execution_artifact_root"])

    # Reconcile the budget reservation to realized turnover (bumps UP only) and
    # clear the orphan flag. If the process crashed before reaching here, the
    # reservation stays unreconciled and the NEXT cycle's pre-submit orphan check
    # fails closed.
    if budget_reserved and budget_store is not None:
        execution_json = _read_optional_json(
            str(cycle.get("execution_artifact_root") or ""), "mainnet_delta_execution.json"
        )
        realized = realized_turnover_usdt(execution_json)
        # B1: if orders WERE submitted but realized turnover is unmeasurable (execution artifact
        # missing/corrupt), do NOT reconcile — leave the reservation as an orphan so the NEXT
        # cycle's pre-submit orphan check also fails closed — and disarm THIS cycle. Silently
        # reconciling with the projected debit would clear the orphan and hide the crash,
        # under-counting the budget (turnover bound + crash-safety bypass).
        may_reconcile, b1_blocker = reconcile_or_block_realized(
            orders_submitted=int(cycle.get("orders_submitted") or 0), realized_turnover=realized
        )
        if not may_reconcile:
            cycle["unattended_budget_reconcile"] = {
                "status": "blocked_unmeasured_realized_turnover",
                "passed": False,
                "reservation_key": budget_reservation_key,
            }
            blockers.append(str(b1_blocker))
        else:
            cycle["unattended_budget_reconcile"] = post_submit_reconcile(
                budget_store,
                reserved=True,
                reservation_key=budget_reservation_key,
                realized_turnover=realized,
                now=now,
            )

    post_monitor_summary: dict[str, Any] = {}
    post_monitor_exit = 0
    if int(cycle["orders_submitted"]) > 0 or execution_exit != 0:
        post_monitor_summary, post_monitor_exit = monitor_runner(
            Namespace(
                config=str(getattr(args, "config", "")),
                reference_run=str(execution_summary.get("artifact_root") or ""),
                api_key_env="",
                api_secret_env="",
                max_abs_position_drift_qty=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
            ),
            env=env,
        )
        cycle["post_trade_reconcile"] = _phase_record(post_monitor_summary, post_monitor_exit)
        cycle["post_trade_reconcile_artifacts"] = _account_artifact_payload(str(post_monitor_summary.get("artifact_root") or ""))
        if post_monitor_exit != 0:
            blockers.append(f"post_trade_reconcile_failed:{post_monitor_summary.get('status')}")
            blockers.extend(str(item) for item in list(post_monitor_summary.get("blockers") or []))
    status = "cycle_executed_reconciled" if not blockers else "cycle_reconcile_required"
    cycle["status"] = status
    cycle["blockers"] = sorted(set(blockers))
    cycle["live_delta_authorized"] = status == "cycle_executed_reconciled" and int(cycle["orders_submitted"]) > 0
    if cycle["live_delta_authorized"]:
        completion_gate = _post_execution_slot_completion_gate(dry_run_summary)
        cycle["frozen_rebalance_slot_completion_gate"] = completion_gate
        if completion_gate["status"] == "ready_to_complete":
            completion = _mark_frozen_rebalance_slot_completed(
                state_store=state_store,
                run_id=run_id,
                frozen_target_snapshot=frozen_target_snapshot,
                artifact_root=cycle["execution_artifact_root"],
                reason="cycle_executed_reconciled",
            )
            if completion is not None:
                cycle["frozen_rebalance_slot_completion"] = completion
        else:
            cycle["frozen_rebalance_slot_completion_deferred"] = completion_gate
        cleanup_consumption = _record_risk_only_reduce_cleanup_consumed(
            state_store=state_store,
            run_id=run_id,
            cycle=cycle,
            frozen_target_snapshot=frozen_target_snapshot,
            frozen_slot_gate=frozen_slot_gate,
        )
        if cleanup_consumption is not None:
            cycle["risk_only_reduce_cleanup_consumption"] = cleanup_consumption
    cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
    return cycle


def _mark_frozen_rebalance_slot_completed(
    *,
    state_store: LiveTradingStateStore,
    run_id: str,
    frozen_target_snapshot: dict[str, Any],
    artifact_root: str,
    reason: str,
) -> dict[str, Any] | None:
    snapshot = dict(frozen_target_snapshot or {})
    slot_id = str(snapshot.get("slot_id") or "").strip()
    if not slot_id:
        return None
    record = state_store.mark_rebalance_slot_target_completed(
        slot_id=slot_id,
        run_id=run_id,
        artifact_root=str(artifact_root or ""),
        reason=str(reason or ""),
    )
    if record is None:
        return None
    return {
        "slot_id": str(record.get("slot_id") or slot_id),
        "target_hash": str(record.get("target_hash") or snapshot.get("target_hash") or ""),
        "status": str(record.get("status") or ""),
        "completed_at_utc": str(record.get("completed_at_utc") or ""),
        "completion_reason": str(record.get("completion_reason") or ""),
    }


def _post_execution_slot_completion_gate(dry_run_summary: dict[str, Any]) -> dict[str, Any]:
    deferred_phase_counts = _dict_ints(
        dry_run_summary.get("deferred_phase_counts") or dry_run_summary.get("source_plan_deferred_phase_counts")
    )
    pending = {phase: int(count) for phase, count in deferred_phase_counts.items() if int(count) > 0}
    if pending:
        return {
            "status": "deferred_pending_execution_phases",
            "blockers": [],
            "deferred_phase_counts": pending,
            "hold_slot_open": True,
        }
    return {
        "status": "ready_to_complete",
        "blockers": [],
        "deferred_phase_counts": {},
        "hold_slot_open": False,
    }


def _record_risk_only_reduce_cleanup_consumed(
    *,
    state_store: LiveTradingStateStore,
    run_id: str,
    cycle: dict[str, Any],
    frozen_target_snapshot: dict[str, Any],
    frozen_slot_gate: dict[str, Any],
) -> dict[str, Any] | None:
    completed_gate = dict(dict(frozen_slot_gate or {}).get("completed_slot_execution_gate") or {})
    if str(completed_gate.get("status") or "") != "risk_only_reduce_cleanup_allowed":
        return None
    authorization = dict(completed_gate.get("authorization") or {})
    if not authorization:
        return None
    snapshot = dict(frozen_target_snapshot or {})
    slot_id = str(completed_gate.get("slot_id") or snapshot.get("slot_id") or authorization.get("slot_id") or "")
    target_hash = str(
        completed_gate.get("target_hash")
        or snapshot.get("target_hash")
        or authorization.get("target_hash")
        or ""
    )
    if not slot_id or not target_hash:
        return None
    record = state_store.record_operator_action(
        run_id=run_id,
        action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
        reason="risk-only reduce cleanup live delta consumed",
        status="applied",
        payload={
            "slot_id": slot_id,
            "target_hash": target_hash,
            "budget_epoch_id": str(completed_gate.get("budget_epoch_id") or authorization.get("budget_epoch_id") or ""),
            "source_authorization_action_id": str(authorization.get("action_id") or ""),
            "source_authorization_created_at_utc": str(authorization.get("created_at_utc") or ""),
            "no_order_canary": dict(completed_gate.get("no_order_canary") or {}),
            "single_use_consumed": True,
            "cycle_index": int(cycle.get("cycle_index") or 0),
            "execution_artifact_root": str(cycle.get("execution_artifact_root") or ""),
            "orders_submitted": int(cycle.get("orders_submitted") or 0),
            "fill_count": int(cycle.get("fill_count") or 0),
        },
    )
    return {
        "action_id": str(record.get("action_id") or ""),
        "action_type": str(record.get("action_type") or ""),
        "slot_id": slot_id,
        "target_hash": target_hash,
        "source_authorization_action_id": str(record.get("source_authorization_action_id") or ""),
        "budget_epoch_id": str(record.get("budget_epoch_id") or ""),
        "single_use_consumed": True,
    }


def _live_delta_owner_intent_gate(
    *,
    state_store: LiveTradingStateStore,
    payload: dict[str, Any],
    dry_run_summary: dict[str, Any],
    planned_orders_json: dict[str, Any],
    now: datetime,
    fast_follow_entry_second: bool = False,
) -> dict[str, Any]:
    """Bind the runtime-recomputed live delta plan to the latest owner arm payload."""
    core = dict(payload.get("core_loop") or {})
    required = budget_gate_enabled(payload) or _as_bool(core.get("live_delta_owner_intent_gate_enabled"), default=False)
    if not required:
        return {"status": "not_required", "required": False, "blockers": []}

    rows = [dict(row) for row in list(planned_orders_json.get("rows") or []) if isinstance(row, dict)]
    row_count = _int(planned_orders_json.get("row_count") or len(rows))
    actual_stage = str(dry_run_summary.get("execution_stage") or "").strip().lower()
    actual_symbols = sorted({_cell_str(row.get("symbol")).strip().upper() for row in rows if _cell_str(row.get("symbol")).strip()})
    actual_sides = sorted({_cell_str(row.get("side")).strip().upper() for row in rows if _cell_str(row.get("side")).strip()})
    actual_reduce_only_values = sorted(
        {
            "true" if _as_bool(row.get("reduce_only"), default=False) else "false"
            for row in rows
            if "reduce_only" in row
        }
    )
    projected = projected_turnover_usdt(planned_orders_json) if planned_orders_json else None
    latest_arm = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
    blockers: list[str] = []
    if latest_arm is None:
        blockers.append("live_delta_owner_intent_missing_arm_action")
        latest_arm = {}
    fast_follow_requested = bool(fast_follow_entry_second)
    fast_follow_authorized = _as_bool(latest_arm.get("fast_follow_authorized"), default=False)
    if fast_follow_requested and not fast_follow_authorized:
        blockers.append("live_delta_owner_intent_fast_follow_authorization_missing")

    unattended_runtime_gate = evaluate_unattended_epoch_runtime_gate(
        state_store=state_store,
        payload=payload,
        now=now,
        approval_action=latest_arm if latest_arm else None,
        require_approval=budget_gate_enabled(payload),
        require_budget_epoch=budget_gate_enabled(payload),
    )
    if budget_gate_enabled(payload):
        blockers.extend(str(item) for item in list(unattended_runtime_gate.get("blockers") or []))

    expected_stage = _owner_payload_text(
        latest_arm,
        "expected_execution_stage",
        "expected_stage",
        "live_delta_expected_stage",
    ).lower()
    fast_follow_expected_stage = _owner_payload_text(
        latest_arm,
        "fast_follow_expected_execution_stage",
        "fast_follow_expected_stage",
    ).lower()
    expected_symbols = sorted(
        _owner_payload_values(
            latest_arm,
            "expected_symbols",
            "expected_symbol",
            "live_delta_expected_symbols",
            "live_delta_expected_symbol",
            upper=True,
        )
    )
    fast_follow_expected_symbols = sorted(
        _owner_payload_values(
            latest_arm,
            "fast_follow_expected_symbols",
            "fast_follow_expected_symbol",
            upper=True,
        )
    )
    allowed_symbols = sorted(
        _owner_payload_values(
            latest_arm,
            "allowed_symbols",
            "allowed_symbol",
            "allowed_symbol_set",
            "live_delta_allowed_symbols",
            "live_delta_allowed_symbol",
            "live_delta_allowed_symbol_set",
            upper=True,
        )
    )
    fast_follow_allowed_symbols = sorted(
        _owner_payload_values(
            latest_arm,
            "fast_follow_allowed_symbols",
            "fast_follow_allowed_symbol",
            "fast_follow_allowed_symbol_set",
            upper=True,
        )
    )
    expected_sides = sorted(
        _owner_payload_values(
            latest_arm,
            "expected_sides",
            "expected_side",
            "live_delta_expected_sides",
            "live_delta_expected_side",
            upper=True,
        )
    )
    fast_follow_expected_sides = sorted(
        _owner_payload_values(
            latest_arm,
            "fast_follow_expected_sides",
            "fast_follow_expected_side",
            upper=True,
        )
    )
    fast_follow_allowed_sides = sorted(
        _owner_payload_values(
            latest_arm,
            "fast_follow_allowed_sides",
            "fast_follow_allowed_side",
            upper=True,
        )
    )
    expected_reduce_only = _owner_payload_optional_bool(
        latest_arm,
        "expected_reduce_only",
        "live_delta_expected_reduce_only",
    )
    fast_follow_expected_reduce_only = _owner_payload_optional_bool(
        latest_arm,
        "fast_follow_expected_reduce_only",
    )
    expected_max_order_count = _owner_payload_optional_int(
        latest_arm,
        "expected_max_order_count",
        "expected_max_orders",
        "live_delta_expected_max_order_count",
    )
    fast_follow_expected_max_order_count = _owner_payload_optional_int(
        latest_arm,
        "fast_follow_expected_max_order_count",
        "fast_follow_expected_max_orders",
    )
    expected_max_turnover = _owner_payload_optional_float(
        latest_arm,
        "expected_max_turnover_usdt",
        "expected_turnover_ceiling_usdt",
        "live_delta_expected_max_turnover_usdt",
    )
    fast_follow_expected_max_turnover = _owner_payload_optional_float(
        latest_arm,
        "fast_follow_expected_max_turnover_usdt",
        "fast_follow_expected_turnover_ceiling_usdt",
    )
    if fast_follow_requested:
        if not fast_follow_expected_stage:
            blockers.append("live_delta_owner_intent_fast_follow_missing_expected_stage")
        if not fast_follow_expected_symbols:
            blockers.append("live_delta_owner_intent_fast_follow_missing_expected_symbols")
        if not fast_follow_expected_sides:
            blockers.append("live_delta_owner_intent_fast_follow_missing_expected_sides")
        if fast_follow_expected_reduce_only is None:
            blockers.append("live_delta_owner_intent_fast_follow_missing_expected_reduce_only")
        if fast_follow_expected_max_order_count is None:
            blockers.append("live_delta_owner_intent_fast_follow_missing_expected_max_order_count")
        if fast_follow_expected_max_turnover is None:
            blockers.append("live_delta_owner_intent_fast_follow_missing_expected_max_turnover_usdt")
        effective_expected_stage = fast_follow_expected_stage
        effective_expected_symbols = fast_follow_expected_symbols
        effective_allowed_symbols = fast_follow_allowed_symbols
        effective_expected_sides = fast_follow_expected_sides
        effective_allowed_sides = fast_follow_allowed_sides
        effective_expected_reduce_only = fast_follow_expected_reduce_only
        effective_expected_max_order_count = fast_follow_expected_max_order_count
        effective_expected_max_turnover = fast_follow_expected_max_turnover
    else:
        effective_expected_stage = expected_stage
        effective_expected_symbols = expected_symbols
        effective_allowed_symbols = allowed_symbols
        effective_expected_sides = expected_sides
        effective_allowed_sides = []
        effective_expected_reduce_only = expected_reduce_only
        effective_expected_max_order_count = expected_max_order_count
        effective_expected_max_turnover = expected_max_turnover
    authorized_epoch_id = _owner_payload_text(
        latest_arm,
        "expected_epoch_id",
        "budget_epoch_id",
        "fast_follow_epoch_id",
        "epoch_id",
    )
    current_epoch_id = ""
    if budget_gate_enabled(payload):
        current_epoch = budget_store_from_payload(payload).read_current_epoch()
        current_epoch_id = current_epoch.epoch_id if current_epoch is not None else ""
        if not current_epoch_id:
            blockers.append("live_delta_owner_intent_requires_open_budget_epoch")
        if not authorized_epoch_id:
            blockers.append("live_delta_owner_intent_missing_expected_epoch")
        elif current_epoch_id and authorized_epoch_id != current_epoch_id:
            blockers.append(
                f"live_delta_owner_intent_epoch_mismatch:expected={authorized_epoch_id}:actual={current_epoch_id}"
            )

    if not effective_expected_stage:
        blockers.append("live_delta_owner_intent_missing_expected_stage")
    elif effective_expected_stage != actual_stage:
        blockers.append(
            "live_delta_owner_intent_stage_mismatch:"
            f"expected={effective_expected_stage}:actual={actual_stage or 'missing'}"
        )
    if not effective_expected_symbols and not effective_allowed_symbols:
        blockers.append("live_delta_owner_intent_missing_expected_symbols")
    elif effective_expected_symbols and set(effective_expected_symbols) != set(actual_symbols):
        blockers.append(
            "live_delta_owner_intent_symbol_mismatch:"
            f"expected={','.join(effective_expected_symbols) or 'missing'}:actual={','.join(actual_symbols) or 'missing'}"
        )
    if effective_allowed_symbols:
        unexpected_symbols = sorted(set(actual_symbols) - set(effective_allowed_symbols))
        if unexpected_symbols:
            blockers.append(
                "live_delta_owner_intent_symbol_not_allowed:"
                f"allowed={','.join(effective_allowed_symbols) or 'missing'}:actual={','.join(actual_symbols) or 'missing'}"
            )
    if effective_expected_max_turnover is None or effective_expected_max_turnover <= 0.0:
        blockers.append("live_delta_owner_intent_missing_expected_max_turnover_usdt")
    elif projected is None:
        blockers.append("live_delta_owner_intent_projected_turnover_unknown")
    elif float(projected) > float(effective_expected_max_turnover) + 1e-9:
        blockers.append(
            "live_delta_owner_intent_turnover_exceeds:"
            f"{float(projected):.8f}>{float(effective_expected_max_turnover):.8f}"
        )
    if row_count > 0 and not rows:
        blockers.append("live_delta_owner_intent_planned_orders_missing")
    if effective_expected_max_order_count is not None and row_count > int(effective_expected_max_order_count):
        blockers.append(
            f"live_delta_owner_intent_order_count_exceeds:{row_count}>{int(effective_expected_max_order_count)}"
        )
    if effective_expected_sides and set(effective_expected_sides) != set(actual_sides):
        blockers.append(
            "live_delta_owner_intent_side_mismatch:"
            f"expected={','.join(effective_expected_sides) or 'missing'}:actual={','.join(actual_sides) or 'missing'}"
        )
    if effective_allowed_sides:
        unexpected_sides = sorted(set(actual_sides) - set(effective_allowed_sides))
        if unexpected_sides:
            blockers.append(
                "live_delta_owner_intent_side_not_allowed:"
                f"allowed={','.join(effective_allowed_sides) or 'missing'}:actual={','.join(actual_sides) or 'missing'}"
            )
    if effective_expected_reduce_only is not None:
        expected_value = "true" if effective_expected_reduce_only else "false"
        if set(actual_reduce_only_values) != {expected_value}:
            blockers.append(
                "live_delta_owner_intent_reduce_only_mismatch:"
                f"expected={expected_value}:actual={','.join(actual_reduce_only_values) or 'missing'}"
            )
    return {
        "status": "passed" if not blockers else "blocked",
        "required": True,
        "blockers": sorted(set(blockers)),
        "owner_action_id": str(latest_arm.get("action_id") or ""),
        "owner_action_created_at_utc": str(latest_arm.get("created_at_utc") or ""),
        "authorized_epoch_id": authorized_epoch_id,
        "current_open_epoch_id": current_epoch_id,
        "fast_follow_entry_second_requested": bool(fast_follow_requested),
        "fast_follow_authorized": bool(fast_follow_authorized),
        "expected_execution_stage": effective_expected_stage,
        "base_expected_execution_stage": expected_stage,
        "fast_follow_expected_execution_stage": fast_follow_expected_stage,
        "actual_execution_stage": actual_stage,
        "expected_symbols": effective_expected_symbols,
        "allowed_symbols": effective_allowed_symbols,
        "base_expected_symbols": expected_symbols,
        "base_allowed_symbols": allowed_symbols,
        "fast_follow_expected_symbols": fast_follow_expected_symbols,
        "fast_follow_allowed_symbols": fast_follow_allowed_symbols,
        "actual_symbols": actual_symbols,
        "expected_sides": effective_expected_sides,
        "allowed_sides": effective_allowed_sides,
        "base_expected_sides": expected_sides,
        "fast_follow_expected_sides": fast_follow_expected_sides,
        "fast_follow_allowed_sides": fast_follow_allowed_sides,
        "actual_sides": actual_sides,
        "expected_reduce_only": effective_expected_reduce_only,
        "base_expected_reduce_only": expected_reduce_only,
        "fast_follow_expected_reduce_only": fast_follow_expected_reduce_only,
        "actual_reduce_only_values": actual_reduce_only_values,
        "expected_max_order_count": effective_expected_max_order_count,
        "base_expected_max_order_count": expected_max_order_count,
        "fast_follow_expected_max_order_count": fast_follow_expected_max_order_count,
        "actual_order_count": row_count,
        "expected_max_turnover_usdt": effective_expected_max_turnover,
        "base_expected_max_turnover_usdt": expected_max_turnover,
        "fast_follow_expected_max_turnover_usdt": fast_follow_expected_max_turnover,
        "projected_turnover_usdt": projected,
        "unattended_epoch_runtime_gate": unattended_runtime_gate,
    }


def _owner_payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (list, tuple, set)):
            values = [str(item).strip() for item in value if str(item).strip()]
            if values:
                return values[0]
        else:
            text = str(value or "").strip()
            if text:
                return text
    return ""


def _owner_payload_values(payload: dict[str, Any], *keys: str, upper: bool = False) -> set[str]:
    values: set[str] = set()
    for key in keys:
        raw = payload.get(key)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple, set)):
            candidates = [str(item) for item in raw]
        else:
            candidates = str(raw).split(",")
        for item in candidates:
            text = str(item).strip()
            if text:
                values.add(text.upper() if upper else text)
    return values


def _owner_payload_optional_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        try:
            value = float(payload.get(key))
        except (TypeError, ValueError):
            return None
        if pd.isna(value):
            return None
        return float(value)
    return None


def _owner_payload_optional_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in payload:
            continue
        try:
            return int(float(payload.get(key)))
        except (TypeError, ValueError):
            return None
    return None


def _owner_payload_optional_bool(payload: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in payload:
            return _as_bool(payload.get(key), default=False)
    return None


def _config_blockers(payload: dict[str, Any], *, execute_live_delta: bool) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    risk = dict(payload.get("risk") or {})
    core = dict(payload.get("core_loop") or {})
    venue = str(binance.get("venue") or "").strip().lower()
    if venue != "usdm_futures":
        blockers.append(f"mainnet_core_loop_requires_mainnet_usdm_venue:actual={venue or 'missing'}")
    if bool(risk.get("trading_enabled", False)):
        blockers.append("mainnet_core_loop_requires_config_trading_enabled_false")
    if execute_live_delta and not bool(core.get("live_delta_enabled", False)):
        blockers.append("mainnet_core_loop_live_delta_disabled_in_config")
    if execute_live_delta and not bool(core.get("submit_orders", False)):
        blockers.append("mainnet_core_loop_submit_orders_false")
    if bool(core.get("submit_orders", False)) and not bool(core.get("live_delta_enabled", False)):
        blockers.append("mainnet_core_loop_submit_orders_without_live_delta_enabled")
    if execute_live_delta and bool(core.get("auto_confirm_delta_after_preflight", False)) and not bool(core.get("submit_orders", False)):
        blockers.append("mainnet_core_loop_auto_confirm_without_submit_orders")
    return blockers


def _live_delta_policy_gate(
    *,
    payload: dict[str, Any],
    dry_run_summary: dict[str, Any],
    fast_follow_entry_second: bool = False,
) -> dict[str, Any]:
    core = dict(payload.get("core_loop") or {})
    blockers: list[str] = []
    stage = str(dry_run_summary.get("execution_stage") or "").strip().lower()
    allowed_stages = _csv_set(core.get("allowed_execution_stages"))
    if allowed_stages and stage not in allowed_stages:
        blockers.append(f"live_delta_execution_stage_not_allowed:{stage or 'missing'}")
    planned_orders = int(dry_run_summary.get("planned_delta_order_count") or 0)
    order_cap_gate = _live_delta_order_cap_gate(
        payload=payload,
        dry_run_summary=dry_run_summary,
        execution_stage=stage,
        planned_orders=planned_orders,
    )
    blockers.extend(str(item) for item in list(order_cap_gate.get("blockers") or []))
    planned_phases = [str(item).strip().lower() for item in list(dry_run_summary.get("planned_execution_phases") or []) if str(item).strip()]
    if len(set(planned_phases)) > 1:
        blockers.append(f"live_delta_mixed_planned_execution_phases:{','.join(sorted(set(planned_phases)))}")
    fast_follow_allowed_stages = {"reduce_first", "entry_second"}
    if bool(fast_follow_entry_second) and stage not in fast_follow_allowed_stages:
        blockers.append(f"fast_follow_after_reduce_requires_reduce_first_or_entry_second_stage:{stage or 'missing'}")
    phase_counts = _dict_ints(dry_run_summary.get("phase_counts") or dry_run_summary.get("source_plan_phase_counts"))
    deferred_phase_counts = _dict_ints(
        dry_run_summary.get("deferred_phase_counts") or dry_run_summary.get("source_plan_deferred_phase_counts")
    )
    target_position_count = _int(
        dry_run_summary.get("target_position_count", dry_run_summary.get("source_plan_target_position_count", 0))
    )
    current_position_count = _int(
        dry_run_summary.get("current_position_count", dry_run_summary.get("source_plan_current_position_count", 0))
    )
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "execution_stage": stage,
        "fast_follow_entry_second": bool(fast_follow_entry_second),
        "fast_follow_after_reduce_allowed_stages": sorted(fast_follow_allowed_stages),
        "allowed_execution_stages": sorted(allowed_stages),
        "planned_delta_order_count": int(planned_orders),
        "max_live_delta_order_count_per_cycle": int(order_cap_gate.get("effective_max_live_delta_order_count") or 0),
        "legacy_max_live_delta_order_count_per_cycle": int(order_cap_gate.get("legacy_max_live_delta_order_count") or 0),
        "live_delta_order_cap_gate": order_cap_gate,
        "phase_counts": phase_counts,
        "deferred_phase_counts": deferred_phase_counts,
        "target_position_count": int(target_position_count),
        "current_position_count": int(current_position_count),
        "planned_execution_phases": sorted(set(planned_phases)),
    }


def _live_delta_order_cap_gate(
    *,
    payload: dict[str, Any],
    dry_run_summary: dict[str, Any],
    execution_stage: str,
    planned_orders: int,
) -> dict[str, Any]:
    core = dict(payload.get("core_loop") or {})
    policy = dict(core.get("live_delta_order_cap_policy") or {})
    mode = str(policy.get("mode") or "legacy_fixed").strip().lower()
    legacy_max = _int(core.get("max_live_delta_order_count_per_cycle"))
    target_count = _int(
        dry_run_summary.get("target_position_count", dry_run_summary.get("source_plan_target_position_count", 0))
    )
    current_count = _int(
        dry_run_summary.get("current_position_count", dry_run_summary.get("source_plan_current_position_count", 0))
    )
    reduce_count = _int(dry_run_summary.get("reduce_only_intent_count"))
    blockers: list[str] = []
    if mode != "target_leg_aware":
        effective = legacy_max
        basis = "legacy_max_live_delta_order_count_per_cycle" if legacy_max > 0 else "disabled"
    else:
        hard_max = _int(policy.get("hard_max_order_count")) or legacy_max
        if str(execution_stage) == "reduce_first":
            allowance = max(0, _int(policy.get("reduce_first_extra_stale_exit_allowance")))
            basis_count = max(target_count, current_count, reduce_count, int(planned_orders))
            effective = basis_count + allowance
            basis = str(policy.get("reduce_first_cap_basis") or "max_current_or_target_position_count")
        elif str(execution_stage) == "entry_second":
            basis_count = target_count if target_count > 0 else int(planned_orders)
            effective = basis_count
            basis = str(policy.get("entry_second_cap_basis") or "target_position_count")
        else:
            basis_count = int(planned_orders)
            effective = basis_count
            basis = "planned_delta_order_count"
        if hard_max > 0:
            effective = min(int(effective), int(hard_max))
        else:
            hard_max = 0
    if effective > 0 and int(planned_orders) > int(effective):
        blockers.append(f"live_delta_planned_order_count_above_effective_cap:{int(planned_orders)}>{int(effective)}")
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "mode": mode,
        "basis": basis,
        "execution_stage": str(execution_stage or ""),
        "planned_delta_order_count": int(planned_orders),
        "effective_max_live_delta_order_count": int(effective),
        "legacy_max_live_delta_order_count": int(legacy_max),
        "hard_max_order_count": int(_int(policy.get("hard_max_order_count")) or legacy_max),
        "target_position_count": int(target_count),
        "current_position_count": int(current_count),
        "planned_reduce_only_order_count": int(reduce_count),
    }


def _live_delta_cooldown_context(
    *,
    state_store: LiveTradingStateStore,
    payload: dict[str, Any],
    now: datetime,
    fast_follow_entry_second: bool = False,
) -> dict[str, Any]:
    core = dict(payload.get("core_loop") or {})
    cooldown_seconds = float(core.get("min_seconds_between_live_delta_executions", 0.0) or 0.0)
    latest = state_store.latest_live_order_submission()
    blockers: list[str] = []
    age_seconds: float | None = None
    if latest:
        anchor = latest.get("finished_at_utc") or latest.get("started_at_utc") or latest.get("created_at_utc")
        try:
            last_dt = datetime.fromisoformat(str(anchor).replace("Z", "+00:00"))
            age_seconds = max(0.0, (now.astimezone(UTC) - last_dt.astimezone(UTC)).total_seconds())
        except ValueError:
            blockers.append("live_delta_cooldown_last_submission_timestamp_unparseable")
    fast_follow_gate = _fast_follow_entry_second_cooldown_gate(
        latest=latest,
        age_seconds=age_seconds,
        core=core,
        approval_gate=_fast_follow_entry_second_approval_gate(
            state_store=state_store,
            payload=payload,
            now=now,
            requested=bool(fast_follow_entry_second),
        ),
        now=now,
        requested=bool(fast_follow_entry_second),
    )
    return {
        "status": "context_ready" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "min_seconds_between_live_delta_executions": float(cooldown_seconds),
        "latest_live_order_submission": latest,
        "seconds_since_latest_live_order_submission": age_seconds,
        "fast_follow_entry_second_requested": bool(fast_follow_entry_second),
        "fast_follow_entry_second_gate": fast_follow_gate,
        "fast_follow_entry_second_approval_gate": fast_follow_gate.get("approval_gate"),
    }


def _live_delta_tempo_gate(
    *,
    payload: dict[str, Any],
    cooldown_context: dict[str, Any],
    dry_run_summary: dict[str, Any],
    now: datetime,
    fast_follow_entry_second: bool = False,
) -> dict[str, Any]:
    core = dict(payload.get("core_loop") or {})
    cooldown_seconds = float(core.get("min_seconds_between_live_delta_executions", 0.0) or 0.0)
    latest = dict(cooldown_context.get("latest_live_order_submission") or {})
    age_seconds = cooldown_context.get("seconds_since_latest_live_order_submission")
    stage = str(dry_run_summary.get("execution_stage") or "").strip().lower()
    blockers = [str(item) for item in list(cooldown_context.get("blockers") or [])]
    cooldown_active = bool(
        latest
        and age_seconds is not None
        and cooldown_seconds > 0.0
        and float(age_seconds) < float(cooldown_seconds)
    )
    bypass_reason = ""
    if bool(fast_follow_entry_second):
        fast_follow_gate = _fast_follow_entry_second_cooldown_gate(
            latest=latest,
            age_seconds=float(age_seconds) if age_seconds is not None else None,
            core=core,
            approval_gate=dict(cooldown_context.get("fast_follow_entry_second_approval_gate") or {}),
            now=now,
            requested=True,
        )
        blockers.extend(str(item) for item in list(fast_follow_gate.get("blockers") or []))
        bypass_reason = "recent_reconciled_reduce_first_fast_follow"
    else:
        fast_follow_gate = _fast_follow_entry_second_cooldown_gate(
            latest=latest,
            age_seconds=float(age_seconds) if age_seconds is not None else None,
            core=core,
            approval_gate={},
            now=None,
            requested=False,
        )
        # Prior-submission integrity applies to BOTH the risk-reducing (reduce_first)
        # and risk-adding (entry_second) stages: a restart after fill-but-before-
        # reconcile must fail closed on either stage. Previously only reduce_first (and
        # the fast-follow entry_second branch) ran this check, so a regular entry_second
        # could proceed once the cooldown elapsed even if the prior submission had not
        # reconciled -- the asymmetry this closes.
        blockers.extend(_prior_live_submission_integrity_blockers(latest))
        if stage == "reduce_first":
            if cooldown_active:
                bypass_reason = "reduce_first_risk_reduction_after_prior_reconcile"
        elif cooldown_active:
            blockers.append(f"live_delta_cooldown_active:{float(age_seconds)}<{cooldown_seconds}")
    status = "blocked"
    if not blockers:
        if bool(fast_follow_entry_second):
            status = "fast_follow_entry_second_allowed"
        elif stage == "reduce_first" and cooldown_active:
            status = "reduce_first_cooldown_bypassed"
        else:
            status = "passed"
    return {
        "status": status,
        "blockers": sorted(set(blockers)),
        "execution_stage": stage,
        "min_seconds_between_live_delta_executions": float(cooldown_seconds),
        "latest_live_order_submission": latest,
        "seconds_since_latest_live_order_submission": age_seconds,
        "cooldown_active": bool(cooldown_active),
        "cooldown_bypassed": bool(bypass_reason and not blockers),
        "cooldown_bypass_reason": bypass_reason if not blockers else "",
        "fast_follow_entry_second_requested": bool(fast_follow_entry_second),
        "fast_follow_entry_second_gate": fast_follow_gate,
    }


def _prior_live_submission_integrity_blockers(latest: dict[str, Any]) -> list[str]:
    if not latest:
        return []
    blockers: list[str] = []
    submitted = _int(latest.get("submitted_order_count"))
    fills = _int(latest.get("fill_count"))
    if submitted <= 0:
        blockers.append("prior_live_submission_missing_orders")
    if fills <= 0 or fills != submitted:
        blockers.append(f"prior_live_submission_fill_count_mismatch:{fills}!={submitted}")
    post_reconcile = str(latest.get("post_trade_reconcile_status") or "").strip()
    if post_reconcile != "passed_live_position_monitor":
        blockers.append(f"prior_live_submission_reconcile_not_passed:{post_reconcile or 'missing'}")
    return blockers


def _fast_follow_entry_second_cooldown_gate(
    *,
    latest: dict[str, Any],
    age_seconds: float | None,
    core: dict[str, Any],
    approval_gate: dict[str, Any] | None = None,
    now: datetime | None = None,
    requested: bool,
) -> dict[str, Any]:
    if not requested:
        return {"status": "not_requested", "blockers": []}
    blockers: list[str] = []
    enabled = _as_bool(core.get("fast_follow_entry_second_enabled"), default=False)
    min_delay = float(core.get("fast_follow_entry_second_min_delay_seconds", 60.0) or 60.0)
    configured_max_age = float(core.get("fast_follow_entry_second_max_age_seconds", 180.0) or 180.0)
    max_age = configured_max_age
    max_age_source = "core_config"
    approval_gate_payload = dict(approval_gate or {})
    if approval_gate_payload.get("status") == "passed" and now is not None:
        timer_window = dict(approval_gate_payload.get("timer_window") or {})
        latest_raw = str(timer_window.get("timer_enable_latest_utc") or "").strip()
        latest_at = _parse_utc_optional(latest_raw)
        if latest_at is not None:
            max_age = max(
                configured_max_age,
                max(0.0, (latest_at - now.astimezone(UTC)).total_seconds()) + (age_seconds or 0.0),
            )
            max_age_source = "unattended_approval_timer_window"
    if not enabled:
        blockers.append("fast_follow_entry_second_disabled_in_config")
    if approval_gate_payload and approval_gate_payload.get("status") not in {"passed", "not_required"}:
        blockers.extend(
            f"fast_follow_entry_second_unattended_approval_gate:{item}"
            for item in list(approval_gate_payload.get("blockers") or [])
        )
    if not latest:
        blockers.append("fast_follow_entry_second_missing_prior_live_submission")
    else:
        stage = str(latest.get("execution_stage") or "").strip().lower()
        if stage != "reduce_first":
            blockers.append(f"fast_follow_entry_second_requires_prior_reduce_first:{stage or 'missing'}")
        submitted = int(latest.get("submitted_order_count") or 0)
        fills = int(latest.get("fill_count") or 0)
        if submitted <= 0:
            blockers.append("fast_follow_entry_second_prior_submission_missing_orders")
        if fills <= 0 or fills != submitted:
            blockers.append(f"fast_follow_entry_second_prior_fill_count_mismatch:{fills}!={submitted}")
        post_reconcile = str(latest.get("post_trade_reconcile_status") or "").strip()
        if post_reconcile != "passed_live_position_monitor":
            blockers.append(f"fast_follow_entry_second_prior_reconcile_not_passed:{post_reconcile or 'missing'}")
    if age_seconds is None:
        blockers.append("fast_follow_entry_second_prior_age_missing")
    else:
        if age_seconds < min_delay:
            blockers.append(f"fast_follow_entry_second_too_early:{age_seconds}<{min_delay}")
        if age_seconds > max_age:
            blockers.append(f"fast_follow_entry_second_window_expired:{age_seconds}>{max_age}")
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "enabled": bool(enabled),
        "min_delay_seconds": float(min_delay),
        "max_age_seconds": float(max_age),
        "configured_max_age_seconds": float(configured_max_age),
        "max_age_source": max_age_source,
        "approval_gate_status": str(approval_gate_payload.get("status") or "not_evaluated"),
        "approval_gate_blockers": list(approval_gate_payload.get("blockers") or []),
        "approval_gate": approval_gate_payload,
        "prior_execution_stage": str(latest.get("execution_stage") or "") if latest else "",
        "prior_run_id": str(latest.get("run_id") or "") if latest else "",
        "prior_fill_count": int(latest.get("fill_count") or 0) if latest else 0,
        "prior_submitted_order_count": int(latest.get("submitted_order_count") or 0) if latest else 0,
    }


def _fast_follow_entry_second_approval_gate(
    *,
    state_store: LiveTradingStateStore,
    payload: dict[str, Any],
    now: datetime,
    requested: bool,
) -> dict[str, Any]:
    if not requested or not budget_gate_enabled(payload):
        return {"status": "not_required", "blockers": []}
    latest_approval = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
    return evaluate_unattended_epoch_runtime_gate(
        state_store=state_store,
        payload=payload,
        now=now,
        approval_action=latest_approval,
        budget_store=budget_store_from_payload(payload),
        require_approval=True,
        require_budget_epoch=True,
    )


def _parse_utc_optional(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _should_attempt_capital_topup(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    static_plan_summary: dict[str, Any],
) -> bool:
    if not bool(getattr(args, "capital_topup", False)):
        return False
    core = dict(payload.get("core_loop") or {})
    if not _as_bool(core.get("capital_topup_after_static_noop"), default=True):
        return False
    status = str(static_plan_summary.get("status") or "")
    if status in {
        "mainnet_current_position_rebalance_noop",
        "mainnet_current_position_rebalance_dust_noop",
    }:
        return True
    return status == "mainnet_current_position_rebalance_plan_ready"


def _capital_topup_live_execution_enabled(payload: dict[str, Any]) -> bool:
    return _as_bool(dict(payload.get("capital_topup") or {}).get("live_execution_enabled"), default=False)


def _plan_margin_cushion_gate(plan_root: str) -> dict[str, Any] | None:
    gate = _read_optional_json(plan_root, "margin_cushion_gate.json")
    if not isinstance(gate, dict):
        return None
    status = str(gate.get("status") or "").strip().lower()
    if status not in {"passed", "blocked"}:
        return None
    return gate


def _plan_pre_reduce_only_margin_cushion_gate(plan_root: str) -> dict[str, Any] | None:
    gate = _read_optional_json(plan_root, "pre_reduce_only_margin_cushion_gate.json")
    return gate if isinstance(gate, dict) and gate else None


def _plan_deferred_if_executed_margin_cushion_gate(plan_root: str) -> dict[str, Any] | None:
    gate = _read_optional_json(plan_root, "deferred_if_executed_margin_cushion_gate.json")
    return gate if isinstance(gate, dict) and gate else None


def _planned_additional_initial_margin_usdt(plan_root: str, *, payload: dict[str, Any]) -> float:
    rows = _read_csv_records(plan_root, "order_sizing_report.csv")
    leverage = int(float(dict(payload.get("binance") or {}).get("max_leverage") or 0))
    if leverage <= 0:
        return 0.0
    total = 0.0
    for row in rows:
        if _as_bool(row.get("no_order_required"), default=False):
            continue
        if _as_bool(row.get("reduce_only"), default=False):
            continue
        phase = _cell_str(row.get("execution_phase")).strip().lower()
        if phase in {"", "noop", "dust_noop", "deadband_noop", "reduce_first"}:
            continue
        if _cell_str(row.get("blockers")).strip():
            continue
        notional = _float(row.get("rounded_notional_usdt"))
        if notional <= 0.0:
            notional = abs(_float(row.get("order_delta_position_amt"))) * _float(row.get("mark_price"))
        total += max(0.0, notional / float(leverage))
    return float(total)


def _csv_set(raw: Any) -> set[str]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(item) for item in raw]
    else:
        values = str(raw or "").split(",")
    return {item.strip().lower() for item in values if item.strip()}


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _nested_ignore_heartbeat_run_ids(run_id: str, raw_parent_ids: Any) -> str:
    values = [str(run_id)]
    if isinstance(raw_parent_ids, (list, tuple, set)):
        raw_values = [str(item) for item in raw_parent_ids]
    else:
        raw_values = str(raw_parent_ids or "").split(",")
    values.extend(item.strip() for item in raw_values if item.strip())
    return ",".join(dict.fromkeys(values))


def _ignore_running_health_monitor_for_core_loop(local_state_health: dict[str, Any]) -> dict[str, Any]:
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
        {**dict(row), "ignored_for_core_loop": str(row.get("run_id")) in ignored}
        for row in list(local_state_health.get("running_heartbeats") or [])
    ]
    filtered["ignored_running_health_monitor_run_ids"] = sorted(ignored)
    filtered["ignored_orchestrator_run_ids"] = sorted(ignored)
    filtered["blockers"] = [
        str(item)
        for item in list(local_state_health.get("blockers") or [])
        if not any(str(item) == f"active_run_in_progress:{run_id}" for run_id in ignored)
    ]
    filtered["status"] = "ok" if not filtered["blockers"] else "blocked"
    return filtered


def _core_loop_target_as_of(*, args: argparse.Namespace, payload: dict[str, Any]) -> str:
    raw = str(getattr(args, "as_of", "") or "").strip()
    if raw.lower() not in {"", "now", "auto"}:
        return raw
    core = dict(payload.get("core_loop") or {})
    return str(core.get("target_as_of") or "latest_closed_rebalance_slot").strip() or "latest_closed_rebalance_slot"


def _core_loop_target_engine(*, args: argparse.Namespace, payload: dict[str, Any]) -> str:
    raw = str(getattr(args, "target_engine", "") or "").strip().lower()
    if raw:
        return raw
    core = dict(payload.get("core_loop") or {})
    return str(core.get("target_engine") or "single_phase").strip().lower() or "single_phase"


def _target_plan_runner(
    *,
    plan_runner: Callable[..., tuple[dict[str, Any], int]],
    target_engine: str,
) -> Callable[..., tuple[dict[str, Any], int]]:
    if str(target_engine or "").strip().lower() == MULTIPHASE_TARGET_ENGINE:
        return run_mainnet_multiphase_current_position_rebalance_plan
    return plan_runner


def _credential_context(*, payload: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
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
        "api_key": api_key,
        "api_secret": api_secret,
        "recv_window_ms": int(binance.get("recv_window_ms") or 5000),
        "timeout_seconds": float(binance.get("timeout_seconds") or 10.0),
        "blockers": blockers,
    }


def _phase_record(summary: dict[str, Any], exit_code: int) -> dict[str, Any]:
    record = {
        "status": str(summary.get("status") or ""),
        "exit_code": int(exit_code),
        "blockers": list(summary.get("blockers") or []),
        "artifact_root": str(summary.get("artifact_root") or ""),
        "orders_submitted": int(summary.get("orders_submitted", summary.get("submitted_order_count", 0)) or 0),
        "fill_count": int(summary.get("fill_count") or 0),
    }
    for key in [
        "execution_stage",
        "planned_execution_phases",
        "planned_delta_order_count",
        "reduce_only_intent_count",
        "non_reduce_only_intent_count",
        "target_position_count",
        "current_position_count",
        "phase_counts",
        "deferred_phase_counts",
        "source_plan_target_position_count",
        "source_plan_current_position_count",
        "source_plan_phase_counts",
        "source_plan_deferred_phase_counts",
    ]:
        if key in summary:
            record[key] = summary.get(key)
    return record


def _resolved_live_delta_cooldown(cycles: list[dict[str, Any]], *, fallback: dict[str, Any]) -> dict[str, Any]:
    for cycle in reversed(cycles):
        gate = dict(cycle.get("live_delta_cooldown") or cycle.get("live_delta_tempo_gate") or {})
        if gate:
            return gate
    return dict(fallback)


def _plan_data_freshness_blockers(plan_root: str, *, payload: dict[str, Any]) -> list[str]:
    if not plan_root:
        return ["missing_plan_artifact_for_data_freshness_gate"]
    root = resolve_repo_path(plan_root)
    audit = _read_optional_json(str(root), "market_data_audit.json")
    decision = _read_optional_json(str(root), "decision_snapshot.json")
    blockers: list[str] = []
    if not audit:
        blockers.append("market_data_audit_missing")
    if str(audit.get("source") or "") == "binance_usdm_public_rest":
        if int(float(audit.get("row_count") or 0)) <= 0:
            blockers.append("market_data_empty")
        if int(float(audit.get("closed_daily_rows") or 0)) <= 0:
            blockers.append("daily_market_data_stale_or_empty")
        if int(float(audit.get("closed_four_hour_rows") or 0)) <= 0:
            blockers.append("four_hour_market_data_stale_or_empty")
        funding_errors = [str(item) for item in list(audit.get("funding_history_error_symbols") or []) if str(item)]
        allowed_errors = int(dict(payload.get("risk") or {}).get("max_funding_history_error_symbols", 0) or 0)
        if len(funding_errors) > allowed_errors:
            blockers.append(f"funding_history_errors:{','.join(funding_errors)}")
    if decision and decision.get("rebalance_slot") is not True:
        blockers.append("strategy_target_not_rebalance_slot")
    if decision and str(decision.get("status") or "") != "ok":
        blockers.append(f"strategy_target_snapshot_not_ok:{decision.get('status')}")
    return blockers


def _execution_artifact_payload(root: str) -> dict[str, Any]:
    if not root:
        return {}
    payload = {
        "submitted_orders": _read_csv_records(root, "submitted_orders.csv"),
        "fills": _read_csv_records(root, "fills.csv"),
        "account_after": _read_optional_json(root, "account_after.json"),
        "reconciliation": _read_optional_json(root, "reconciliation.json"),
    }
    return payload


def _account_artifact_payload(root: str) -> dict[str, Any]:
    if not root:
        return {}
    report = _read_optional_json(root, "monitor_report.json")
    return {
        "monitor_report": report,
        "account": dict(report.get("account") or {}),
        "reference": dict(report.get("reference") or {}),
    }


def _strategy_plan_artifact_payload(root: str) -> dict[str, Any]:
    if not root:
        return {}
    return {
        "run_summary": _read_optional_json(root, "run_summary.json"),
        "decision_snapshot": _read_optional_json(root, "decision_snapshot.json"),
        "target_portfolio": _read_optional_json(root, "target_portfolio.json"),
        "risk_gate": _read_optional_json(root, "risk_gate.json"),
        "execution_plan": _read_optional_json(root, "execution_plan.json"),
        "margin_cushion_gate": _read_optional_json(root, "margin_cushion_gate.json"),
        "deferred_if_executed_margin_cushion_gate": _read_optional_json(
            root,
            "deferred_if_executed_margin_cushion_gate.json",
        ),
        "capital_allocation_context": _read_optional_json(root, "capital_allocation_context.json"),
        "capital_topup_gate": _read_optional_json(root, "capital_topup_gate.json"),
        "market_data_audit": _read_optional_json(root, "market_data_audit.json"),
        "current_positions": _read_csv_records(root, "current_positions.csv"),
        "target_positions": _read_csv_records(root, "target_positions.csv"),
        "delta_orders": _read_csv_records(root, "execution_plan.csv"),
        "order_sizing_report": _read_csv_records(root, "order_sizing_report.csv"),
    }


def _delta_preflight_artifact_payload(root: str) -> dict[str, Any]:
    if not root:
        return {}
    return {
        "run_summary": _read_optional_json(root, "run_summary.json"),
        "account_before": _read_optional_json(root, "account_before.json"),
        "mainnet_delta_preflight": _read_optional_json(root, "mainnet_delta_preflight.json"),
        "daily_realized_pnl_gate": _read_optional_json(root, "daily_realized_pnl_gate.json"),
        "planned_delta_orders": _read_optional_json(root, "planned_delta_orders.json"),
        "submitted_orders": _read_csv_records(root, "submitted_orders.csv"),
        "fills": _read_csv_records(root, "fills.csv"),
    }


def _read_optional_json(root: str, name: str) -> dict[str, Any]:
    if not root:
        return {}
    try:
        candidate = resolve_repo_path(root) / name
        if candidate.exists():
            return dict(read_json(candidate))
    except Exception:
        return {}
    return {}


def _read_csv_records(root: str, name: str) -> list[dict[str, Any]]:
    if not root:
        return []
    try:
        candidate = resolve_repo_path(root) / name
        if not candidate.exists() or candidate.stat().st_size == 0:
            return []
        return [dict(row) for _, row in pd.read_csv(candidate).iterrows()]
    except Exception:
        return []


def _float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        parsed = float(value)
        if pd.isna(parsed):
            return 0.0
        return parsed
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _dict_ints(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(item) for key, item in value.items()}


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
