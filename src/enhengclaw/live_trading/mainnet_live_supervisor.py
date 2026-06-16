from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from argparse import Namespace
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.live_risk_controls import classify_exception_strategy
from enhengclaw.live_trading.mainnet_core_loop_runner import run_mainnet_core_loop
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import MULTIPHASE_TARGET_ENGINE
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.unattended_budget_hook import budget_gate_enabled, budget_store_from_payload
from enhengclaw.quant_research.contracts import write_json


DEFAULT_SUPERVISOR_CONFIG = "config/live_trading/hv_balanced_binance_usdm_live_supervisor_candidate.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mainnet hv_balanced live supervisor. It is meant for a server-side timer/supervisor. "
            "Default operator state is unarmed, so it calls the core loop in no-order observation mode."
        )
    )
    parser.add_argument("--config", default=DEFAULT_SUPERVISOR_CONFIG)
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--reference-run", default="")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument(
        "--fast-follow-entry-second",
        action="store_true",
        help=(
            "Run as an independent fast-follow invocation after a successful reduce_first. "
            "The core loop may execute another reduce_first residual or entry_second, but never a mixed stage."
        ),
    )
    parser.add_argument(
        "--fast-follow-chain-depth",
        type=int,
        default=0,
        help="Internal fast-follow chain depth used to cap repeated reduce_first residual follow-ups.",
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_live_supervisor(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_live_supervisor(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    core_loop_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_core_loop,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    command_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", DEFAULT_SUPERVISOR_CONFIG))
    payload = live_config.payload
    supervisor_cfg = _supervisor_config(payload)
    requested_cycles = int(getattr(args, "cycles", None) or supervisor_cfg.get("max_cycles_per_invocation", 1) or 1)
    max_cycles = int(supervisor_cfg.get("max_cycles_per_invocation", 1) or 1)
    cycles = max(1, requested_cycles)
    max_cycles = max(1, max_cycles)
    interval_seconds = float(
        getattr(args, "interval_seconds", None)
        if getattr(args, "interval_seconds", None) is not None
        else supervisor_cfg.get("interval_seconds", 0.0) or 0.0
    )
    interval_seconds = max(0.0, interval_seconds)
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-live-supervisor"
    run_root = live_config.artifact_root.parent / "mainnet_live_supervisor" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    max_heartbeat_age = float(dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900) or 900)
    recovered_heartbeats: list[dict[str, Any]] = []
    if _as_bool(supervisor_cfg.get("recover_stale_heartbeats"), default=True):
        recovered_heartbeats = state_store.recover_stale_running_heartbeats(
            now=started,
            max_heartbeat_age_seconds=max_heartbeat_age,
            recovery_run_id=run_id,
            reason="mainnet live supervisor startup recovery",
        )
    local_state_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=max_heartbeat_age,
        ignore_run_id=run_id,
    )
    local_state_health = _ignore_running_health_monitor_for_supervisor(local_state_health)
    operator_state = state_store.read_operator_state()
    target_engine = _supervisor_target_engine(args=args, payload=payload, supervisor_cfg=supervisor_cfg)
    blockers = _config_blockers(
        payload=payload,
        supervisor_cfg=supervisor_cfg,
        requested_cycles=cycles,
        max_cycles=max_cycles,
    )
    blockers.extend(str(item) for item in list(local_state_health.get("blockers") or []))
    write_json(run_root / "heartbeat_recovery.json", {"recovered_heartbeats": recovered_heartbeats})
    write_json(run_root / "local_state_health.json", local_state_health)
    write_json(run_root / "operator_state.json", operator_state)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live_supervisor",
        status="running",
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        artifact_root=str(run_root),
        extra={
            "component": "mainnet_live_supervisor",
            "live_delta_armed": bool(operator_state.get("live_delta_armed")),
        },
    )

    cycle_rows: list[dict[str, Any]] = []
    for cycle_index in range(1, cycles + 1):
        cycle = _run_cycle(
            args=args,
            run_id=run_id,
            payload=payload,
            supervisor_cfg=supervisor_cfg,
            cycle_index=cycle_index,
            blocked_before_cycle=bool(blockers),
            state_store=state_store,
            core_loop_runner=core_loop_runner,
            env=env or os.environ,
            now_fn=now_fn,
            target_engine=target_engine,
        )
        cycle_rows.append(cycle)
        write_json(run_root / f"cycle_{cycle_index:03d}.json", cycle)
        state_store.record_live_artifact(
            run_id=run_id,
            artifact_type="mainnet_live_supervisor_cycle",
            artifact_id=f"{run_id}:cycle:{cycle_index:03d}",
            payload=cycle,
        )
        cycle_blockers = [str(item) for item in list(cycle.get("blockers") or [])]
        if cycle_blockers:
            blockers.extend(cycle_blockers)
            if _as_bool(supervisor_cfg.get("disarm_on_blocker"), default=True):
                _disarm_live_delta(
                    state_store=state_store,
                    run_id=run_id,
                    reason=f"supervisor blocker cycle {cycle_index}: {','.join(sorted(set(cycle_blockers)))}",
                    cycle=cycle,
                )
            break
        if cycle_index < cycles and interval_seconds > 0.0:
            sleep_fn(interval_seconds)

    if blockers and _as_bool(supervisor_cfg.get("disarm_on_blocker"), default=True):
        latest_state = state_store.read_operator_state()
        if bool(latest_state.get("live_delta_armed")):
            _disarm_live_delta(
                state_store=state_store,
                run_id=run_id,
                reason=f"supervisor pre-cycle blocker: {','.join(sorted(set(blockers)))}",
                cycle={"blockers": sorted(set(blockers))},
            )

    submitted_total = int(sum(int(row.get("orders_submitted") or 0) for row in cycle_rows))
    fill_total = int(sum(int(row.get("fill_count") or 0) for row in cycle_rows))
    completed = not blockers and len(cycle_rows) == cycles
    finished = datetime.now(UTC)
    final_operator_state = state_store.read_operator_state()
    fast_follow_schedule = _maybe_schedule_fast_follow_entry_second(
        args=args,
        run_id=run_id,
        payload=payload,
        supervisor_cfg=supervisor_cfg,
        cycle_rows=cycle_rows,
        completed=completed,
        state_store=state_store,
        command_runner=command_runner or _run_command,
    )
    summary = {
        "run_id": run_id,
        "status": "mainnet_live_supervisor_completed" if completed else "mainnet_live_supervisor_blocked",
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": finished.isoformat().replace("+00:00", "Z"),
        "artifact_root": str(run_root),
        "config": str(live_config.path),
        "mode": "mainnet_live_supervisor",
        "configured_cycle_count": int(cycles),
        "requested_cycle_count": int(requested_cycles),
        "max_cycles_per_invocation": int(max_cycles),
        "completed_cycle_count": int(len(cycle_rows)),
        "interval_seconds": float(interval_seconds),
        "fast_follow_entry_second_requested": bool(getattr(args, "fast_follow_entry_second", False)),
        "fast_follow_entry_second_schedule": fast_follow_schedule,
        "target_engine": target_engine,
        "recovered_heartbeat_count": int(len(recovered_heartbeats)),
        "orders_submitted": submitted_total,
        "fill_count": fill_total,
        "live_delta_armed_at_start": bool(operator_state.get("live_delta_armed")),
        "live_delta_armed_at_finish": bool(final_operator_state.get("live_delta_armed")),
        "live_delta_authorized": bool(any(bool(row.get("live_delta_authorized")) for row in cycle_rows)),
        "recurring_mainnet_enabled": True,
        "supervisor_uses_core_loop": True,
        "cycles": cycle_rows,
    }
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="mainnet_live_supervisor_summary",
        artifact_id=f"{run_id}:summary",
        payload=summary,
    )
    state_store.write_heartbeat(
        run_id=run_id,
        mode="live_supervisor",
        status=str(summary["status"]),
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(run_root),
        blockers=list(summary["blockers"]),
        extra={"live_delta_armed": bool(final_operator_state.get("live_delta_armed"))},
    )
    return summary, 0 if completed else 2


def _run_cycle(
    *,
    args: argparse.Namespace,
    run_id: str,
    payload: dict[str, Any],
    supervisor_cfg: dict[str, Any],
    cycle_index: int,
    blocked_before_cycle: bool,
    state_store: LiveTradingStateStore,
    core_loop_runner: Callable[..., tuple[dict[str, Any], int]],
    env: Mapping[str, str],
    now_fn: Callable[[], datetime] | None,
    target_engine: str,
) -> dict[str, Any]:
    operator_state = state_store.read_operator_state()
    live_delta_armed = bool(operator_state.get("live_delta_armed"))
    allow_live_delta_when_armed = _as_bool(supervisor_cfg.get("allow_live_delta_when_armed"), default=True)
    blockers: list[str] = []
    fast_follow_invocation_gate = _fast_follow_invocation_authorization_gate(
        args=args,
        payload=payload,
        supervisor_cfg=supervisor_cfg,
        state_store=state_store,
    )
    if fast_follow_invocation_gate["status"] != "passed":
        blockers.append("fast_follow_invocation_owner_authorization_gate_blocked")
        blockers.extend(str(item) for item in list(fast_follow_invocation_gate.get("blockers") or []))
    execute_live_delta = bool(
        live_delta_armed
        and allow_live_delta_when_armed
        and fast_follow_invocation_gate["status"] == "passed"
    )
    cycle: dict[str, Any] = {
        "cycle_index": int(cycle_index),
        "status": "not_run",
        "blockers": blockers,
        "operator_paused": bool(operator_state.get("paused")),
        "live_delta_armed": live_delta_armed,
        "execute_live_delta_requested": execute_live_delta,
        "fast_follow_invocation_authorization_gate": fast_follow_invocation_gate,
        "target_engine": str(target_engine),
        "orders_submitted": 0,
        "fill_count": 0,
        "live_delta_authorized": False,
    }
    if blocked_before_cycle:
        blockers.append("prior_supervisor_blocker")
    if bool(operator_state.get("paused")):
        blockers.append("operator_paused")
    if live_delta_armed and not allow_live_delta_when_armed:
        blockers.append("supervisor_live_delta_armed_but_config_disallows_live_delta")
    if (
        live_delta_armed
        and str(target_engine).strip().lower() == MULTIPHASE_TARGET_ENGINE
        and not _as_bool(supervisor_cfg.get("allow_multiphase_live_delta"), default=False)
    ):
        blockers.append("supervisor_multiphase_target_engine_live_delta_not_explicitly_allowed")
    if blockers:
        cycle["status"] = "cycle_skipped"
        cycle["blockers"] = sorted(set(blockers))
        cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
        return cycle

    core_args = Namespace(
        config=str(getattr(args, "config", "")),
        as_of=str(getattr(args, "as_of", "now") or "now"),
        fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
        symbols=str(getattr(args, "symbols", "") or ""),
        public_market_data=bool(getattr(args, "public_market_data", False)),
        reference_run=str(getattr(args, "reference_run", "") or ""),
        target_engine=str(target_engine),
        cycles=1,
        interval_seconds=0.0,
        execute_live_delta=execute_live_delta,
        operator_enable_live_delta_for_this_run=execute_live_delta,
        i_understand_this_places_real_mainnet_delta_orders=execute_live_delta,
        i_understand_daily_realized_pnl_gate_is_active=False,
        confirm_mainnet_delta_execution="",
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
        ignore_heartbeat_run_id=run_id,
        capital_topup=_supervisor_capital_topup_enabled(supervisor_cfg),
        fast_follow_entry_second=bool(getattr(args, "fast_follow_entry_second", False)),
    )
    try:
        if now_fn is None:
            core_summary, core_exit = core_loop_runner(core_args, env=env)
        else:
            core_summary, core_exit = core_loop_runner(core_args, env=env, now_fn=now_fn)
    except Exception as exc:  # pragma: no cover - exercised by explicit exception tests.
        blockers.append(f"supervisor_core_loop_exception:{type(exc).__name__}:{exc}")
        cycle["status"] = "cycle_exception"
        cycle["blockers"] = sorted(set(blockers))
        cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
        return cycle

    core_blockers = [str(item) for item in list(core_summary.get("blockers") or [])]
    blockers.extend(core_blockers)
    cycle.update(
        {
            "core_loop_status": str(core_summary.get("status") or ""),
            "core_loop_exit_code": int(core_exit),
            "core_loop_artifact_root": str(core_summary.get("artifact_root") or ""),
            "core_loop_execution_requested": bool(core_summary.get("execution_requested")),
            "orders_submitted": int(core_summary.get("orders_submitted") or 0),
            "fill_count": int(core_summary.get("fill_count") or 0),
            "live_delta_authorized": bool(core_summary.get("live_delta_authorized")),
            "core_loop_summary": core_summary,
        }
    )
    if core_exit != 0:
        blockers.append(f"core_loop_failed:{core_summary.get('status')}")
    if blockers:
        cycle["status"] = "cycle_blocked"
    elif execute_live_delta:
        cycle["status"] = "cycle_live_delta_completed"
    else:
        cycle["status"] = "cycle_observed_no_order"
    cycle["blockers"] = sorted(set(blockers))
    cycle["exception_policy"] = classify_exception_strategy(cycle["blockers"], context={"cycle_index": cycle_index})
    return cycle


def _supervisor_config(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(payload.get("mainnet_live_supervisor") or {})
    if not cfg:
        cfg = dict(payload.get("supervisor") or {})
    return cfg


def _ignore_running_health_monitor_for_supervisor(local_state_health: dict[str, Any]) -> dict[str, Any]:
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
        {**dict(row), "ignored_for_supervisor": str(row.get("run_id")) in ignored}
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


def _supervisor_target_engine(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    supervisor_cfg: dict[str, Any],
) -> str:
    raw = str(getattr(args, "target_engine", "") or "").strip().lower()
    if raw:
        return raw
    supervisor_raw = str(supervisor_cfg.get("target_engine") or "").strip().lower()
    if supervisor_raw:
        return supervisor_raw
    core = dict(payload.get("core_loop") or {})
    return str(core.get("target_engine") or "single_phase").strip().lower() or "single_phase"


def _config_blockers(
    *,
    payload: dict[str, Any],
    supervisor_cfg: dict[str, Any],
    requested_cycles: int,
    max_cycles: int,
) -> list[str]:
    blockers: list[str] = []
    risk = dict(payload.get("risk") or {})
    binance = dict(payload.get("binance") or {})
    core = dict(payload.get("core_loop") or {})
    if str(binance.get("venue") or "").strip().lower() != "usdm_futures":
        blockers.append("mainnet_live_supervisor_requires_usdm_futures")
    if bool(risk.get("trading_enabled", False)):
        blockers.append("mainnet_live_supervisor_requires_config_trading_enabled_false")
    if int(max_cycles) != 1:
        blockers.append(f"mainnet_live_supervisor_requires_max_cycles_one:{max_cycles}")
    if int(requested_cycles) > int(max_cycles):
        blockers.append(f"mainnet_live_supervisor_requested_cycles_above_config_max:{requested_cycles}>{max_cycles}")
    if _as_bool(supervisor_cfg.get("allow_live_delta_when_armed"), default=True):
        if not bool(core.get("live_delta_enabled", False)):
            blockers.append("mainnet_live_supervisor_requires_core_loop_live_delta_enabled")
        if not bool(core.get("submit_orders", False)):
            blockers.append("mainnet_live_supervisor_requires_core_loop_submit_orders")
        if not bool(core.get("auto_confirm_delta_after_preflight", False)):
            blockers.append("mainnet_live_supervisor_requires_core_loop_auto_confirm")
    if _supervisor_capital_topup_enabled(supervisor_cfg):
        topup = dict(payload.get("capital_topup") or {})
        allowed = _csv_set(topup.get("allowed_delta_classifications") or "")
        allowed_stages = _csv_set(core.get("allowed_execution_stages") or "")
        min_additional = float(topup.get("min_additional_allocated_capital_usdt") or 0.0)
        if not _as_bool(topup.get("enabled"), default=False):
            blockers.append("mainnet_live_supervisor_capital_topup_enabled_without_topup_config")
        if not _as_bool(topup.get("live_execution_enabled"), default=False):
            blockers.append("mainnet_live_supervisor_capital_topup_live_execution_disabled")
        if "entry_second" not in allowed_stages:
            blockers.append("mainnet_live_supervisor_capital_topup_requires_entry_second_stage_allowed")
        disallowed = sorted(allowed - {"increase_same_side", "new_entry", "rebalance_deadband", "dust_residual", "no_delta"})
        if disallowed:
            blockers.append(f"mainnet_live_supervisor_capital_topup_disallowed_classifications:{','.join(disallowed)}")
        if min_additional < 25.0:
            blockers.append(f"mainnet_live_supervisor_capital_topup_min_additional_below_floor:{min_additional}<25.0")
        if not _as_bool(topup.get("require_balanced_all_or_none"), default=True):
            blockers.append("mainnet_live_supervisor_capital_topup_requires_balanced_all_or_none")
    return blockers


def _supervisor_capital_topup_enabled(supervisor_cfg: dict[str, Any]) -> bool:
    return _as_bool(supervisor_cfg.get("capital_topup_enabled"), default=False)


def _disarm_live_delta(
    *,
    state_store: LiveTradingStateStore,
    run_id: str,
    reason: str,
    cycle: dict[str, Any],
) -> None:
    state_store.record_operator_action(
        run_id=run_id,
        action_type="disarm-live-delta",
        reason=reason,
        payload={
            "source": "mainnet_live_supervisor",
            "cycle_index": cycle.get("cycle_index"),
            "blockers": list(cycle.get("blockers") or []),
        },
    )


def _maybe_schedule_fast_follow_entry_second(
    *,
    args: argparse.Namespace,
    run_id: str,
    payload: dict[str, Any],
    supervisor_cfg: dict[str, Any],
    cycle_rows: list[dict[str, Any]],
    completed: bool,
    state_store: LiveTradingStateStore,
    command_runner: Callable[[list[str]], tuple[int, str, str]],
) -> dict[str, Any]:
    if not _as_bool(supervisor_cfg.get("fast_follow_entry_second_enabled"), default=False):
        return {"status": "skipped", "reason": "fast_follow_entry_second_disabled"}
    if not completed or not cycle_rows:
        return {"status": "skipped", "reason": "supervisor_not_completed"}
    cycle = dict(cycle_rows[-1])
    gate = _reduce_first_fast_follow_source_gate(cycle)
    if gate["status"] != "passed":
        return {"status": "skipped", "reason": "latest_cycle_not_reduce_first_source", "source_gate": gate}

    depth = max(0, int(getattr(args, "fast_follow_chain_depth", 0) or 0))
    fast_follow_policy = _fast_follow_policy(supervisor_cfg)
    max_depth = _fast_follow_max_chain_depth(
        supervisor_cfg=supervisor_cfg,
        policy=fast_follow_policy,
        source_gate=gate,
    )
    if depth >= max_depth:
        return {
            "status": "skipped",
            "reason": "fast_follow_chain_depth_exhausted",
            "source_gate": gate,
            "chain_depth": int(depth),
            "max_chain_depth": int(max_depth),
        }
    next_depth = int(depth + 1)
    owner_gate = _fast_follow_owner_authorization_gate(
        args=args,
        payload=payload,
        state_store=state_store,
        depth=depth,
        next_depth=next_depth,
        max_depth=max_depth,
        policy=fast_follow_policy,
    )
    if owner_gate["status"] != "passed":
        return {
            "status": "skipped",
            "reason": "fast_follow_owner_authorization_gate_blocked",
            "source_gate": gate,
            "authorization_gate": owner_gate,
            "chain_depth": int(depth),
            "next_chain_depth": next_depth,
            "max_chain_depth": int(max_depth),
        }

    delay = _fast_follow_delay_context(
        payload=payload,
        supervisor_cfg=supervisor_cfg,
        policy=fast_follow_policy,
        source_gate=gate,
    )
    delay_seconds = int(delay["delay_seconds"])
    unit_suffix = "".join(ch for ch in str(run_id).replace("-mainnet-live-supervisor", "") if ch.isalnum())[-24:]
    unit_name = f"enhengclaw-mainnet-fast-follow-after-reduce-{unit_suffix}"
    repo_root = str(supervisor_cfg.get("repo_root") or "/root/enhengclaw_live_runner/repo")
    env_wrapper = str(supervisor_cfg.get("env_wrapper") or "/root/enhengclaw_live_runner/bin/with-live-env")
    python_path = str(supervisor_cfg.get("python_path") or "/root/enhengclaw_live_runner/venv/bin/python")
    script_path = str(supervisor_cfg.get("supervisor_script") or "scripts/live_trading/run_hv_balanced_mainnet_live_supervisor.py")
    config_path = str(getattr(args, "config", "") or DEFAULT_SUPERVISOR_CONFIG)
    runtime_max_seconds = int(fast_follow_policy.get("runtime_max_seconds") or 420)
    cmd = [
        "systemd-run",
        "--collect",
        f"--unit={unit_name}",
        "--description=EnhengClaw fast-follow after reconciled reduce_first",
        f"--on-active={delay_seconds}s",
        f"--property=WorkingDirectory={repo_root}",
        "--property=Environment=PYTHONUNBUFFERED=1",
        f"--property=RuntimeMaxSec={runtime_max_seconds}",
        env_wrapper,
        python_path,
        script_path,
        "--config",
        config_path,
        "--cycles",
        "1",
        "--fast-follow-entry-second",
        "--fast-follow-chain-depth",
        str(depth + 1),
    ]
    exit_code, stdout, stderr = command_runner(cmd)
    return {
        "status": "scheduled" if int(exit_code) == 0 else "failed",
        "source_gate": gate,
        "delay_seconds": int(delay_seconds),
        "delay_reason": str(delay.get("reason") or ""),
        "delay_context": delay,
        "fast_follow_policy": fast_follow_policy,
        "authorization_gate": owner_gate,
        "chain_depth": next_depth,
        "max_chain_depth": int(max_depth),
        "unit_name": unit_name,
        "command": cmd,
        "exit_code": int(exit_code),
        "stdout": str(stdout).strip(),
        "stderr": str(stderr).strip(),
    }


def _fast_follow_owner_authorization_gate(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    state_store: LiveTradingStateStore,
    depth: int,
    next_depth: int,
    max_depth: int,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Bind fast-follow scheduling to explicit owner arm authorization.

    The main timer can run with a fresh epoch, but a transient fast-follow is a
    second systemd entry point. Require the latest arm-live-delta action to
    opt into that derived entry point and bind it to the currently open budget
    epoch plus a chain-depth and cleanup contract.
    """
    blockers: list[str] = []
    if not _as_bool(policy.get("owner_authorization_required"), default=True):
        return {"status": "passed", "blockers": [], "authorization_required": False}

    if not budget_gate_enabled(payload):
        blockers.append("fast_follow_requires_unattended_budget_gate_enabled")

    epoch = None
    try:
        epoch = budget_store_from_payload(payload).read_current_epoch()
    except Exception as exc:  # pragma: no cover - defensive live-state guard.
        blockers.append(f"fast_follow_budget_epoch_unreadable:{type(exc).__name__}:{exc}")

    latest_arm = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
    if not latest_arm:
        blockers.append("fast_follow_missing_owner_arm_action")
        latest_arm = {}

    authorized = _as_bool(latest_arm.get("fast_follow_authorized"), default=False)
    cleanup_required = _as_bool(latest_arm.get("fast_follow_cleanup_required"), default=False)
    auth_epoch_id = str(latest_arm.get("fast_follow_epoch_id") or latest_arm.get("epoch_id") or "").strip()
    auth_decision = str(latest_arm.get("fast_follow_owner_decision") or "").strip()
    authorized_depth = _int(latest_arm.get("fast_follow_max_chain_depth"))

    if not authorized:
        blockers.append("fast_follow_owner_authorization_missing")
    if auth_decision and auth_decision != "approve_fast_follow_under_current_budget_epoch":
        blockers.append(f"fast_follow_owner_decision_unrecognized:{auth_decision}")
    if not auth_decision:
        blockers.append("fast_follow_owner_decision_missing")
    if not cleanup_required:
        blockers.append("fast_follow_cleanup_contract_missing")
    if authorized_depth <= 0:
        blockers.append("fast_follow_owner_max_chain_depth_missing")
    elif int(next_depth) > authorized_depth:
        blockers.append(f"fast_follow_owner_chain_depth_exhausted:{next_depth}>{authorized_depth}")
    if int(next_depth) > int(max_depth):
        blockers.append(f"fast_follow_policy_chain_depth_exhausted:{next_depth}>{max_depth}")
    if epoch is None:
        blockers.append("fast_follow_requires_open_budget_epoch")
    else:
        if auth_epoch_id != epoch.epoch_id:
            blockers.append(f"fast_follow_epoch_mismatch:{auth_epoch_id or 'missing'}!={epoch.epoch_id}")
        if int(next_depth) > int(epoch.max_live_cycles):
            blockers.append(f"fast_follow_epoch_cycle_cap_too_small:{next_depth}>{epoch.max_live_cycles}")

    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "authorization_required": True,
        "latest_arm_action_id": str(latest_arm.get("action_id") or ""),
        "latest_arm_run_id": str(latest_arm.get("run_id") or ""),
        "owner_decision": auth_decision,
        "fast_follow_authorized": bool(authorized),
        "cleanup_required": bool(cleanup_required),
        "authorized_epoch_id": auth_epoch_id,
        "current_open_epoch_id": epoch.epoch_id if epoch is not None else "",
        "current_epoch_status": epoch.status if epoch is not None else "",
        "chain_depth": int(depth),
        "next_chain_depth": int(next_depth),
        "owner_max_chain_depth": int(authorized_depth),
        "policy_max_chain_depth": int(max_depth),
        "invocation_is_fast_follow": bool(getattr(args, "fast_follow_entry_second", False)),
    }


def _fast_follow_invocation_authorization_gate(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    supervisor_cfg: dict[str, Any],
    state_store: LiveTradingStateStore,
) -> dict[str, Any]:
    """Validate a transient fast-follow entry point before it can execute.

    Scheduling a follow-up is one authorization surface; the child systemd-run
    invocation is another. Bind the child invocation to the same owner payload,
    currently open budget epoch, and chain-depth ceiling before live flags are
    passed into the core loop.
    """
    if not bool(getattr(args, "fast_follow_entry_second", False)):
        return {"status": "passed", "blockers": [], "authorization_required": False}

    policy = _fast_follow_policy(supervisor_cfg)
    current_depth = max(0, int(getattr(args, "fast_follow_chain_depth", 0) or 0))
    policy_max_depth = _fast_follow_invocation_policy_max_depth(
        supervisor_cfg=supervisor_cfg,
        policy=policy,
    )
    gate = _fast_follow_owner_authorization_gate(
        args=args,
        payload=payload,
        state_store=state_store,
        depth=max(0, current_depth - 1),
        next_depth=current_depth,
        max_depth=policy_max_depth,
        policy=policy,
    )
    blockers = [str(item) for item in list(gate.get("blockers") or [])]
    if current_depth <= 0:
        blockers.append("fast_follow_invocation_chain_depth_missing")
    wrapped = dict(gate)
    wrapped.update(
        {
            "status": "passed" if not blockers else "blocked",
            "blockers": sorted(set(blockers)),
            "authorization_required": bool(gate.get("authorization_required", True)),
            "validation_mode": "fast_follow_invocation",
            "current_chain_depth": int(current_depth),
            "policy_max_chain_depth": int(policy_max_depth),
        }
    )
    return wrapped


def _fast_follow_invocation_policy_max_depth(
    *,
    supervisor_cfg: dict[str, Any],
    policy: dict[str, Any],
) -> int:
    legacy = max(0, _int_or_default(supervisor_cfg.get("fast_follow_max_chain_invocations"), 3))
    if str(policy.get("mode") or "").strip().lower() != "reconcile_aware":
        return legacy
    hard_cap = _int(policy.get("max_chain_invocations_hard_cap")) or legacy
    return max(1, int(hard_cap))


def _reduce_first_fast_follow_source_gate(cycle: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    stage = _cycle_execution_stage(cycle)
    orders = int(cycle.get("orders_submitted") or 0)
    fills = int(cycle.get("fill_count") or 0)
    core = dict(cycle.get("core_loop_summary") or {})
    core_cycles = list(core.get("cycles") or [])
    core_cycle = dict(core_cycles[-1]) if core_cycles and isinstance(core_cycles[-1], dict) else {}
    post_trade = dict(core_cycle.get("post_trade_reconcile") or {})
    policy_gate = dict(core_cycle.get("live_delta_policy_gate") or {})
    deferred_phase_counts = _dict_ints(policy_gate.get("deferred_phase_counts"))
    target_position_count = _int(policy_gate.get("target_position_count"))
    current_position_count = _int(policy_gate.get("current_position_count"))
    if stage != "reduce_first":
        blockers.append(f"fast_follow_source_requires_reduce_first:{stage or 'missing'}")
    if orders <= 0:
        blockers.append("fast_follow_source_requires_submitted_orders")
    if fills <= 0 or fills != orders:
        blockers.append(f"fast_follow_source_fill_count_mismatch:{fills}!={orders}")
    if str(core_cycle.get("status") or "") != "cycle_executed_reconciled":
        blockers.append(f"fast_follow_source_core_cycle_not_reconciled:{core_cycle.get('status') or 'missing'}")
    if str(post_trade.get("status") or "") != "passed_live_position_monitor":
        blockers.append(f"fast_follow_source_post_trade_reconcile_not_passed:{post_trade.get('status') or 'missing'}")
    if list(cycle.get("blockers") or []) or list(core.get("blockers") or []):
        blockers.append("fast_follow_source_has_blockers")
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "execution_stage": stage,
        "orders_submitted": orders,
        "fill_count": fills,
        "core_cycle_status": str(core_cycle.get("status") or ""),
        "post_trade_reconcile_status": str(post_trade.get("status") or ""),
        "deferred_phase_counts": deferred_phase_counts,
        "deferred_entry_second_count": int(deferred_phase_counts.get("entry_second", 0)),
        "target_position_count": int(target_position_count),
        "current_position_count": int(current_position_count),
    }


def _fast_follow_policy(supervisor_cfg: dict[str, Any]) -> dict[str, Any]:
    policy = dict(supervisor_cfg.get("fast_follow_policy") or {})
    if not policy:
        return {
            "mode": "legacy_fixed",
            "entry_after_reduce_delay_seconds": int(float(supervisor_cfg.get("fast_follow_entry_second_delay_seconds", 90) or 90)),
            "residual_reduce_delay_seconds": int(float(supervisor_cfg.get("fast_follow_entry_second_delay_seconds", 90) or 90)),
            "min_delay_seconds": 60,
            "max_delay_seconds": 120,
            "max_chain_invocations_hard_cap": _int_or_default(
                supervisor_cfg.get("fast_follow_max_chain_invocations"), 3
            ),
            "owner_authorization_required": True,
            "runtime_max_seconds": 420,
        }
    hard_cap_raw = policy.get(
        "max_chain_invocations_hard_cap",
        supervisor_cfg.get("fast_follow_max_chain_invocations", 3),
    )
    return {
        "mode": str(policy.get("mode") or "legacy_fixed"),
        "entry_after_reduce_delay_seconds": int(float(policy.get("entry_after_reduce_delay_seconds", 20) or 20)),
        "residual_reduce_delay_seconds": int(float(policy.get("residual_reduce_delay_seconds", 30) or 30)),
        "min_delay_seconds": int(float(policy.get("min_delay_seconds", 10) or 10)),
        "max_delay_seconds": int(float(policy.get("max_delay_seconds", 90) or 90)),
        "max_chain_invocations_hard_cap": _int_or_default(hard_cap_raw, 3),
        "owner_authorization_required": _as_bool(policy.get("owner_authorization_required"), default=True),
        "runtime_max_seconds": max(60, int(float(policy.get("runtime_max_seconds", 420) or 420))),
    }


def _fast_follow_delay_context(
    *,
    payload: dict[str, Any],
    supervisor_cfg: dict[str, Any],
    policy: dict[str, Any],
    source_gate: dict[str, Any],
) -> dict[str, Any]:
    core = dict(payload.get("core_loop") or {})
    core_min_delay = _fast_follow_core_min_delay_seconds(core)
    if str(policy.get("mode") or "").strip().lower() != "reconcile_aware":
        delay = int(float(supervisor_cfg.get("fast_follow_entry_second_delay_seconds", 90) or 90))
        clamped = max(core_min_delay, max(60, min(120, delay)))
        return {
            "delay_seconds": clamped,
            "reason": "legacy_fixed_delay",
            "raw_delay_seconds": int(delay),
            "core_min_delay_seconds": int(core_min_delay),
        }
    deferred_entry_count = _int(source_gate.get("deferred_entry_second_count"))
    if deferred_entry_count > 0:
        raw_delay = _int(policy.get("entry_after_reduce_delay_seconds")) or 20
        reason = "deferred_entry_second_after_reconciled_reduce"
    else:
        raw_delay = _int(policy.get("residual_reduce_delay_seconds")) or 30
        reason = "residual_reduce_first_after_reconciled_reduce"
    min_delay = _int(policy.get("min_delay_seconds")) or 10
    max_delay = _int(policy.get("max_delay_seconds")) or 90
    configured_delay = max(min_delay, min(max_delay, int(raw_delay)))
    return {
        "delay_seconds": max(core_min_delay, configured_delay),
        "reason": reason,
        "raw_delay_seconds": int(raw_delay),
        "policy_min_delay_seconds": int(min_delay),
        "policy_max_delay_seconds": int(max_delay),
        "configured_delay_seconds": int(configured_delay),
        "core_min_delay_seconds": int(core_min_delay),
    }


def _fast_follow_max_chain_depth(
    *,
    supervisor_cfg: dict[str, Any],
    policy: dict[str, Any],
    source_gate: dict[str, Any],
) -> int:
    legacy = max(0, _int_or_default(supervisor_cfg.get("fast_follow_max_chain_invocations"), 3))
    if str(policy.get("mode") or "").strip().lower() != "reconcile_aware":
        return legacy
    hard_cap = max(1, _int(policy.get("max_chain_invocations_hard_cap")) or legacy or 1)
    target_legs = max(1, _int(source_gate.get("target_position_count")) or _int(source_gate.get("current_position_count")) or legacy or 1)
    return min(hard_cap, target_legs)


def _cycle_execution_stage(cycle: dict[str, Any]) -> str:
    core = dict(cycle.get("core_loop_summary") or {})
    core_cycles = list(core.get("cycles") or [])
    core_cycle = dict(core_cycles[-1]) if core_cycles and isinstance(core_cycles[-1], dict) else {}
    policy = dict(core_cycle.get("live_delta_policy_gate") or {})
    stage = str(policy.get("execution_stage") or "").strip().lower()
    if stage:
        return stage
    delta = dict(core_cycle.get("delta_preflight") or {})
    return str(delta.get("execution_stage") or "").strip().lower()


def _run_command(cmd: list[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, str(exc.stdout or ""), str(exc.stderr or exc)
    return int(completed.returncode), str(completed.stdout), str(completed.stderr)


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv_set(raw: Any) -> set[str]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(item) for item in raw]
    else:
        values = str(raw or "").split(",")
    return {item.strip().lower() for item in values if item.strip()}


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _int_or_default(value: Any, default: int) -> int:
    if value is None:
        return int(default)
    if isinstance(value, str) and not value.strip():
        return int(default)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _fast_follow_core_min_delay_seconds(core: dict[str, Any]) -> int:
    return max(0, int(float(core.get("fast_follow_entry_second_min_delay_seconds", 60.0) or 60.0)))


def _dict_ints(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(item) for key, item in value.items()}


if __name__ == "__main__":
    raise SystemExit(main())
