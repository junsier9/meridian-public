from __future__ import annotations

import argparse
import json
import math
import os
import time
from argparse import Namespace
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.mainnet_health_monitor import run_mainnet_health_monitor
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.unattended_budget_hook import budget_store_from_payload
from enhengclaw.live_trading.unattended_epoch_controller import (
    build_fast_follow_entry_second_owner_payload,
    evaluate_unattended_epoch_runtime_gate,
    resolve_turnover_budget_from_proof,
    resolve_unattended_epoch_controller_bounds,
    run_unattended_epoch_controller,
    terminal_cleanup,
)
from enhengclaw.quant_research.contracts import read_json, write_json


UNATTENDED_DAILY_POLICY_SUMMARY_VERSION = "unattended_daily_policy.v1"
DEFAULT_POLICY_CONFIG = "config/live_trading/hv_balanced_binance_usdm_live_supervisor_candidate.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Daily unattended policy controller. It creates a fresh slot approval/epoch, "
            "optionally opens the supervisor timer for one bounded window, and terminal-cleans up."
        )
    )
    parser.add_argument("--config", default=DEFAULT_POLICY_CONFIG)
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--reference-run", default="")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enable-supervisor-timer", action="store_true")
    parser.add_argument("--run-health-monitor", action="store_true")
    parser.add_argument("--max-gross-turnover-usdt", type=float, default=None)
    parser.add_argument("--max-live-cycles", type=int, default=None)
    parser.add_argument("--max-age-seconds", type=int, default=None)
    parser.add_argument("--approval-ttl-seconds", type=int, default=None)
    parser.add_argument("--timer-window-seconds", type=int, default=None)
    parser.add_argument("--max-timer-fires", type=int, default=None)
    parser.add_argument("--systemd-timer-name", default="")
    parser.add_argument("--wait-for-supervisor-artifact-seconds", type=float, default=None)
    parser.add_argument("--poll-interval-seconds", type=float, default=None)
    parser.add_argument("--no-terminal-cleanup-after-success", action="store_true")
    parser.add_argument("--no-terminal-cleanup-on-failure", action="store_true")
    args = parser.parse_args(argv)
    summary, exit_code = run_unattended_daily_policy(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_unattended_daily_policy(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    command_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
    epoch_controller_runner: Callable[..., tuple[dict[str, Any], int]] = run_unattended_epoch_controller,
    health_monitor_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_health_monitor,
    supervisor_summary_reader: Callable[[Path, set[str], datetime], dict[str, Any] | None] | None = None,
    notification_sender: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], int]:
    started = _coerce_utc((now_fn or (lambda: datetime.now(UTC)))())
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-unattended-daily-policy"
    live_config = load_live_trading_config(getattr(args, "config", DEFAULT_POLICY_CONFIG))
    payload = live_config.payload
    policy_cfg = _policy_config(payload)
    run_root = live_config.artifact_root.parent / "unattended_daily_policy" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    invocation_marker = {
        "schema_version": "unattended_daily_policy_invocation.v1",
        "run_id": run_id,
        "invocation_id": run_id,
        "started_at_utc": _iso(started),
        "artifact_root": str(run_root),
        "config": str(live_config.path),
        "service_failed_state_classification_rule": (
            "A systemd failed state is fresh only when a newer invocation marker, heartbeat, "
            "or summary exists after the expected timer-fire boundary; otherwise classify it "
            "as stale_failed_service_carryover."
        ),
    }
    write_json(run_root / "invocation_marker.json", invocation_marker)

    command_runner = command_runner or _run_command
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    budget_store = budget_store_from_payload(payload)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="unattended_daily_policy",
        status="running",
        started_at_utc=_iso(started),
        artifact_root=str(run_root),
        extra={"component": "unattended_daily_policy"},
    )

    blockers: list[str] = []
    controller_summary, controller_exit = epoch_controller_runner(
        _controller_args(
            args=args,
            policy_cfg=policy_cfg,
            apply=bool(getattr(args, "apply", False)),
            parent_run_id=run_id,
        ),
        env=env or os.environ,
        now_fn=now_fn,
        command_runner=command_runner,
        notification_sender=notification_sender,
    )
    controller_status = str(controller_summary.get("status") or "")
    if int(controller_exit) != 0:
        blockers.append(f"unattended_epoch_controller_failed:{controller_status}")
    blockers.extend(str(item) for item in list(controller_summary.get("blockers") or []))

    timer_name = _timer_name(args=args, policy_cfg=policy_cfg)
    enable_timer = _as_bool(policy_cfg.get("enable_supervisor_timer"), default=False) or bool(
        getattr(args, "enable_supervisor_timer", False)
    )
    run_health = _as_bool(policy_cfg.get("run_health_monitor_after_supervisor"), default=False) or bool(
        getattr(args, "run_health_monitor", False)
    )
    cleanup_after_success = not bool(getattr(args, "no_terminal_cleanup_after_success", False)) and _as_bool(
        policy_cfg.get("terminal_cleanup_after_success"),
        default=True,
    )
    cleanup_on_failure = not bool(getattr(args, "no_terminal_cleanup_on_failure", False)) and _as_bool(
        policy_cfg.get("terminal_cleanup_on_failure"),
        default=True,
    )
    wait_seconds = _float_arg_or_config(
        args,
        "wait_for_supervisor_artifact_seconds",
        policy_cfg,
        default=900.0,
    )
    poll_seconds = max(
        0.1,
        _float_arg_or_config(args, "poll_interval_seconds", policy_cfg, default=5.0),
    )

    timer_enable: dict[str, Any] | None = None
    supervisor_wait: dict[str, Any] | None = None
    supervisor_waits: list[dict[str, Any]] = []
    supervisor_summary: dict[str, Any] | None = None
    supervisor_summaries: list[dict[str, Any]] = []
    fast_follow_entry_second_authorizations: list[dict[str, Any]] = []
    fast_follow_entry_second_schedules: list[dict[str, Any]] = []
    health_summary: dict[str, Any] | None = None
    health_exit: int | None = None
    terminal_cleanup_result: dict[str, Any] | None = None
    controller_cleanup = dict(controller_summary.get("terminal_cleanup") or {})
    status = "unattended_daily_policy_blocked" if blockers else "unattended_daily_policy_ready"

    if not blockers and controller_status == "hold_until_next_rebalance_slot":
        status = "hold_until_next_rebalance_slot"
    elif not blockers and not bool(getattr(args, "apply", False)):
        status = "unattended_daily_policy_dry_run_ready"
    elif not blockers and controller_status not in {"unattended_epoch_armed", "unattended_epoch_approval_already_active"}:
        blockers.append(f"unattended_daily_policy_unexpected_controller_status:{controller_status}")
        status = "unattended_daily_policy_blocked"
    elif not blockers and not enable_timer:
        status = "unattended_daily_policy_armed_timer_off"
    elif not blockers:
        existing_supervisor_run_ids = _supervisor_run_ids(live_config.artifact_root.parent)
        timer_enable = _enable_timer(timer_name=timer_name, command_runner=command_runner)
        if timer_enable.get("status") != "enabled":
            blockers.extend(str(item) for item in list(timer_enable.get("blockers") or []))
        else:
            max_fires = max(1, _int_arg_or_config(args, "max_timer_fires", policy_cfg, default=1))
            for fire_index in range(1, max_fires + 1):
                supervisor_wait = _wait_for_supervisor_summary(
                    live_config.artifact_root.parent,
                    existing_run_ids=existing_supervisor_run_ids,
                    started_after=started,
                    timeout_seconds=wait_seconds,
                    poll_interval_seconds=poll_seconds,
                    sleep_fn=sleep_fn,
                    reader=supervisor_summary_reader,
                )
                supervisor_waits.append(supervisor_wait)
                supervisor_summary = dict(supervisor_wait.get("summary") or {})
                if supervisor_wait.get("status") != "observed":
                    blockers.append(str(supervisor_wait.get("status") or "supervisor_artifact_not_observed"))
                    break
                run_id_seen = str(supervisor_summary.get("run_id") or supervisor_wait.get("run_id") or "")
                if run_id_seen:
                    existing_supervisor_run_ids.add(run_id_seen)
                supervisor_summaries.append(supervisor_summary)
                blockers.extend(_supervisor_completion_blockers(supervisor_summary))
                if blockers:
                    break
                follow_context = _entry_second_follow_context(supervisor_summary)
                if not bool(follow_context.get("required")):
                    break
                if fire_index >= max_fires:
                    blockers.append("unattended_daily_policy_fast_follow_scheduled_beyond_max_timer_fires")
                    break
                schedule = dict(supervisor_summary.get("fast_follow_entry_second_schedule") or {})
                if schedule.get("status") == "scheduled":
                    blockers.append("unattended_daily_policy_fast_follow_scheduled_before_entry_second_proof")
                    break
                authorization = _authorize_fast_follow_entry_second(
                    args=args,
                    policy_cfg=policy_cfg,
                    parent_run_id=run_id,
                    source_supervisor_summary=supervisor_summary,
                    state_store=state_store,
                    epoch_controller_runner=epoch_controller_runner,
                    env=env or os.environ,
                    now_fn=now_fn,
                    command_runner=command_runner,
                    notification_sender=notification_sender,
                )
                fast_follow_entry_second_authorizations.append(authorization)
                if authorization.get("status") != "authorized":
                    blockers.extend(str(item) for item in list(authorization.get("blockers") or []))
                    break
                fast_follow_schedule = _schedule_fast_follow_entry_second(
                    args=args,
                    payload=payload,
                    policy_cfg=policy_cfg,
                    source_supervisor_summary=supervisor_summary,
                    authorization=authorization,
                    command_runner=command_runner,
                    now=_coerce_utc((now_fn or (lambda: datetime.now(UTC)))()),
                )
                fast_follow_entry_second_schedules.append(fast_follow_schedule)
                if fast_follow_schedule.get("status") != "scheduled":
                    blockers.extend(str(item) for item in list(fast_follow_schedule.get("blockers") or []))
                    break
            status = (
                "unattended_daily_policy_timer_fire_completed"
                if not blockers
                else "unattended_daily_policy_blocked"
            )

    if blockers and bool(getattr(args, "apply", False)) and cleanup_on_failure and not controller_cleanup:
        terminal_cleanup_result = terminal_cleanup(
            state_store=state_store,
            budget_store=budget_store,
            run_id=run_id,
            now=started,
            reason="unattended daily policy failure",
            blockers=blockers,
            timer_name=timer_name,
            artifact_root=run_root / "terminal_cleanup",
            command_runner=command_runner,
            notification_sender=notification_sender,
            env=env or os.environ,
        )
    elif status == "unattended_daily_policy_timer_fire_completed" and cleanup_after_success:
        terminal_cleanup_result = terminal_cleanup(
            state_store=state_store,
            budget_store=budget_store,
            run_id=run_id,
            now=started,
            reason="unattended daily policy completed timer fire",
            blockers=[],
            timer_name=timer_name,
            artifact_root=run_root / "terminal_cleanup",
            command_runner=command_runner,
            notification_sender=notification_sender,
            env=env or os.environ,
        )
    elif controller_cleanup:
        terminal_cleanup_result = controller_cleanup

    if (
        run_health
        and status == "unattended_daily_policy_timer_fire_completed"
        and supervisor_wait is not None
        and supervisor_wait.get("status") == "observed"
    ):
        health_summary, health_exit = health_monitor_runner(
            Namespace(
                config=str(live_config.path),
                recent_runs=None,
                max_seconds_since_latest_run=None,
                systemd_timer_name=timer_name,
                skip_systemd_check=False,
            ),
            env=env or os.environ,
            now_fn=now_fn,
            command_runner=command_runner,
        )
        if int(health_exit) != 0:
            blockers.append(f"unattended_daily_policy_health_monitor_alerted:{health_summary.get('status')}")
            blockers.extend(str(item.get("code")) for item in list(health_summary.get("alerts") or []))
            status = "unattended_daily_policy_blocked"

    finished = _coerce_utc((now_fn or (lambda: datetime.now(UTC)))())
    latest_approval = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
    runtime_gate_after = evaluate_unattended_epoch_runtime_gate(
        state_store=state_store,
        payload=payload,
        now=finished,
        approval_action=latest_approval,
        budget_store=budget_store,
        require_approval=True,
        require_budget_epoch=True,
    )
    operator_state_after = state_store.read_operator_state()
    current_epoch = budget_store.read_current_epoch()
    orders_submitted = int(sum(int(dict(item).get("orders_submitted") or 0) for item in supervisor_summaries))
    fill_count = int(sum(int(dict(item).get("fill_count") or 0) for item in supervisor_summaries))
    summary = {
        "schema_version": UNATTENDED_DAILY_POLICY_SUMMARY_VERSION,
        "run_id": run_id,
        "status": status if not blockers else "unattended_daily_policy_blocked",
        "started_at_utc": _iso(started),
        "finished_at_utc": _iso(finished),
        "artifact_root": str(run_root),
        "invocation_marker": invocation_marker,
        "invocation_marker_path": str(run_root / "invocation_marker.json"),
        "config": str(live_config.path),
        "apply": bool(getattr(args, "apply", False)),
        "enable_supervisor_timer": bool(enable_timer),
        "run_health_monitor_after_supervisor": bool(run_health),
        "timer_name": timer_name,
        "timer_window_seconds": int(_int_arg_or_config(args, "timer_window_seconds", policy_cfg, default=900)),
        "max_timer_fires": int(_int_arg_or_config(args, "max_timer_fires", policy_cfg, default=1)),
        "blockers": sorted(set(blockers)),
        "controller_summary": controller_summary,
        "controller_exit_code": int(controller_exit),
        "timer_enable": timer_enable,
        "supervisor_wait": supervisor_wait,
        "supervisor_waits": supervisor_waits,
        "supervisor_summary": supervisor_summary,
        "supervisor_summaries": supervisor_summaries,
        "fast_follow_entry_second_authorizations": fast_follow_entry_second_authorizations,
        "fast_follow_entry_second_schedules": fast_follow_entry_second_schedules,
        "health_summary": health_summary,
        "health_exit_code": health_exit,
        "terminal_cleanup": terminal_cleanup_result,
        "runtime_gate_after": runtime_gate_after,
        "operator_state_after": operator_state_after,
        "open_budget_epoch_after": asdict(current_epoch) if current_epoch is not None else None,
        "orders_submitted": orders_submitted,
        "fill_count": fill_count,
    }
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="unattended_daily_policy_summary",
        artifact_id=f"{run_id}:summary",
        payload=summary,
    )
    state_store.write_heartbeat(
        run_id=run_id,
        mode="unattended_daily_policy",
        status=str(summary["status"]),
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(run_root),
        blockers=list(summary["blockers"]),
    )
    ok_statuses = {
        "hold_until_next_rebalance_slot",
        "unattended_daily_policy_dry_run_ready",
        "unattended_daily_policy_armed_timer_off",
        "unattended_daily_policy_timer_fire_completed",
    }
    return summary, 0 if summary["status"] in ok_statuses else 2


def _controller_args(
    *,
    args: argparse.Namespace,
    policy_cfg: dict[str, Any],
    apply: bool,
    parent_run_id: str = "",
    fast_follow_entry_second: bool = False,
) -> Namespace:
    return Namespace(
        config=str(getattr(args, "config", DEFAULT_POLICY_CONFIG)),
        as_of=str(getattr(args, "as_of", "now") or "now"),
        fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
        symbols=str(getattr(args, "symbols", "") or ""),
        public_market_data=bool(getattr(args, "public_market_data", False)),
        reference_run=str(getattr(args, "reference_run", "") or ""),
        target_engine=str(getattr(args, "target_engine", "") or ""),
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
        apply=bool(apply),
        max_gross_turnover_usdt=_arg_or_config(args, "max_gross_turnover_usdt", policy_cfg),
        max_live_cycles=_arg_or_config(args, "max_live_cycles", policy_cfg),
        max_age_seconds=_arg_or_config(args, "max_age_seconds", policy_cfg),
        approval_ttl_seconds=_arg_or_config(args, "approval_ttl_seconds", policy_cfg),
        timer_window_seconds=_arg_or_config(args, "timer_window_seconds", policy_cfg),
        max_timer_fires=_arg_or_config(args, "max_timer_fires", policy_cfg),
        systemd_timer_name=_timer_name(args=args, policy_cfg=policy_cfg),
        ignore_heartbeat_run_id=str(parent_run_id or ""),
        fast_follow_entry_second=bool(fast_follow_entry_second),
        no_terminal_cleanup_on_failure=bool(getattr(args, "no_terminal_cleanup_on_failure", False)),
    )


def _policy_config(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(payload.get("unattended_daily_policy") or {})
    controller = dict(payload.get("unattended_epoch_controller") or {})
    merged = dict(controller)
    merged.update(cfg)
    return merged


def _enable_timer(
    *,
    timer_name: str,
    command_runner: Callable[[list[str]], tuple[int, str, str]],
) -> dict[str, Any]:
    if not timer_name:
        return {
            "status": "blocked",
            "timer_name": "",
            "blockers": ["unattended_daily_policy_missing_supervisor_timer_name"],
        }
    code, stdout, stderr = command_runner(["systemctl", "enable", "--now", str(timer_name)])
    return {
        "status": "enabled" if int(code) == 0 else "blocked",
        "timer_name": str(timer_name),
        "exit_code": int(code),
        "stdout": str(stdout),
        "stderr": str(stderr),
        "blockers": [] if int(code) == 0 else [f"unattended_daily_policy_timer_enable_failed:{int(code)}"],
    }


def _wait_for_supervisor_summary(
    root: Path,
    *,
    existing_run_ids: set[str],
    started_after: datetime,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep_fn: Callable[[float], None],
    reader: Callable[[Path, set[str], datetime], dict[str, Any] | None] | None,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    attempts = 0
    while True:
        attempts += 1
        summary = (
            reader(root, existing_run_ids, started_after)
            if reader is not None
            else _latest_supervisor_summary(root, existing_run_ids=existing_run_ids, started_after=started_after)
        )
        if summary is not None:
            return {
                "status": "observed",
                "attempts": int(attempts),
                "run_id": str(summary.get("run_id") or ""),
                "artifact_root": str(summary.get("artifact_root") or ""),
                "summary": summary,
            }
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return {
                "status": "unattended_daily_policy_supervisor_artifact_timeout",
                "attempts": int(attempts),
                "timeout_seconds": float(timeout_seconds),
            }
        sleep_fn(min(float(poll_interval_seconds), remaining))


def _supervisor_run_ids(root: Path) -> set[str]:
    supervisor_root = Path(root) / "mainnet_live_supervisor"
    return {path.parent.name for path in supervisor_root.glob("*/run_summary.json")}


def _latest_supervisor_summary(
    root: Path,
    *,
    existing_run_ids: set[str],
    started_after: datetime,
) -> dict[str, Any] | None:
    supervisor_root = Path(root) / "mainnet_live_supervisor"
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for summary_path in supervisor_root.glob("*/run_summary.json"):
        run_id = summary_path.parent.name
        if run_id in existing_run_ids:
            continue
        try:
            payload = dict(read_json(summary_path))
        except Exception:
            continue
        observed_time = _parse_utc_optional(payload.get("started_at_utc")) or _parse_utc_optional(
            payload.get("finished_at_utc")
        )
        if observed_time is None or observed_time < started_after:
            continue
        payload.setdefault("artifact_root", str(summary_path.parent))
        rows.append((observed_time, payload))
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows[0][1] if rows else None


def _supervisor_completion_blockers(summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(summary.get("status") or "") != "mainnet_live_supervisor_completed":
        blockers.append(f"unattended_daily_policy_supervisor_not_completed:{summary.get('status')}")
    blockers.extend(str(item) for item in list(summary.get("blockers") or []))
    orders = int(summary.get("orders_submitted") or 0)
    fills = int(summary.get("fill_count") or 0)
    if orders != fills:
        blockers.append(f"unattended_daily_policy_order_fill_count_mismatch:{orders}!={fills}")
    if orders > 0 and not bool(summary.get("live_delta_authorized")):
        blockers.append("unattended_daily_policy_live_orders_without_authorization")
    post_trade_status = _post_trade_reconcile_status(summary)
    if orders > 0 and post_trade_status != "passed_live_position_monitor":
        blockers.append(f"unattended_daily_policy_post_trade_reconcile_not_passed:{post_trade_status or 'missing'}")
    return sorted(set(blockers))


def _post_trade_reconcile_status(summary: dict[str, Any]) -> str:
    cycles = list(summary.get("cycles") or [])
    supervisor_cycle = dict(cycles[-1]) if cycles and isinstance(cycles[-1], dict) else {}
    core = dict(supervisor_cycle.get("core_loop_summary") or {})
    core_cycles = list(core.get("cycles") or [])
    core_cycle = dict(core_cycles[-1]) if core_cycles and isinstance(core_cycles[-1], dict) else {}
    post_trade = dict(core_cycle.get("post_trade_reconcile") or {})
    return str(post_trade.get("status") or "").strip()


def _entry_second_follow_context(summary: dict[str, Any]) -> dict[str, Any]:
    cycles = list(summary.get("cycles") or [])
    supervisor_cycle = dict(cycles[-1]) if cycles and isinstance(cycles[-1], dict) else {}
    core = dict(supervisor_cycle.get("core_loop_summary") or {})
    core_cycles = list(core.get("cycles") or [])
    core_cycle = dict(core_cycles[-1]) if core_cycles and isinstance(core_cycles[-1], dict) else {}
    policy = dict(core_cycle.get("live_delta_policy_gate") or {})
    strategy_target = dict(core_cycle.get("strategy_target") or {})
    phase_counts = dict(policy.get("phase_counts") or strategy_target.get("phase_counts") or {})
    deferred_phase_counts = dict(policy.get("deferred_phase_counts") or strategy_target.get("deferred_phase_counts") or {})
    execution_stage = str(policy.get("execution_stage") or "").strip().lower()
    orders = int(core.get("orders_submitted") or summary.get("orders_submitted") or 0)
    fills = int(core.get("fill_count") or summary.get("fill_count") or 0)
    post_trade_status = _post_trade_reconcile_status(summary)
    deferred_entry_second = int(deferred_phase_counts.get("entry_second") or 0)
    required = (
        execution_stage == "reduce_first"
        and orders > 0
        and fills == orders
        and post_trade_status == "passed_live_position_monitor"
        and deferred_entry_second > 0
    )
    return {
        "required": bool(required),
        "execution_stage": execution_stage,
        "orders_submitted": orders,
        "fill_count": fills,
        "post_trade_reconcile_status": post_trade_status,
        "phase_counts": phase_counts,
        "deferred_phase_counts": deferred_phase_counts,
        "deferred_entry_second_count": deferred_entry_second,
        "source_supervisor_run_id": str(summary.get("run_id") or ""),
        "source_core_run_id": str(core.get("run_id") or ""),
    }


def _authorize_fast_follow_entry_second(
    *,
    args: argparse.Namespace,
    policy_cfg: dict[str, Any],
    parent_run_id: str,
    source_supervisor_summary: dict[str, Any],
    state_store: LiveTradingStateStore,
    epoch_controller_runner: Callable[..., tuple[dict[str, Any], int]],
    env: Mapping[str, str],
    now_fn: Callable[[], datetime] | None,
    command_runner: Callable[[list[str]], tuple[int, str, str]],
    notification_sender: Callable[[str, dict[str, Any]], dict[str, Any]] | None,
) -> dict[str, Any]:
    current = _coerce_utc((now_fn or (lambda: datetime.now(UTC)))())
    source_approval = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
    if not source_approval:
        return {
            "status": "blocked",
            "blockers": ["unattended_daily_policy_fast_follow_missing_source_approval"],
        }
    source_created = _parse_utc_optional(source_approval.get("created_at_utc"))
    if source_created is not None and current <= source_created:
        current = source_created + timedelta(seconds=1)
    proof_args = _controller_args(
        args=args,
        policy_cfg=policy_cfg,
        apply=False,
        parent_run_id=parent_run_id,
        fast_follow_entry_second=True,
    )
    proof_summary, proof_exit = epoch_controller_runner(
        proof_args,
        env=env,
        now_fn=now_fn,
        command_runner=command_runner,
        notification_sender=notification_sender,
    )
    proof = dict(proof_summary.get("fresh_no_order_proof") or {})
    blockers = []
    if int(proof_exit) != 0:
        blockers.append(f"unattended_daily_policy_entry_second_proof_controller_failed:{proof_summary.get('status')}")
    blockers.extend(str(item) for item in list(proof_summary.get("blockers") or []))
    bounds = resolve_unattended_epoch_controller_bounds(args=proof_args, controller_cfg=policy_cfg)
    bounds = resolve_turnover_budget_from_proof(bounds=bounds, proof=proof)
    follow_context = _entry_second_follow_context(source_supervisor_summary)
    payload_result = build_fast_follow_entry_second_owner_payload(
        run_id=parent_run_id,
        now=current,
        proof=proof,
        source_approval=source_approval,
        bounds=bounds,
        source_supervisor_run_id=str(follow_context.get("source_supervisor_run_id") or ""),
        source_core_run_id=str(follow_context.get("source_core_run_id") or ""),
    )
    blockers.extend(str(item) for item in list(payload_result.get("blockers") or []))
    result = {
        "status": "blocked" if blockers else "ready",
        "blockers": sorted(set(blockers)),
        "source_approval_action_id": str(source_approval.get("action_id") or ""),
        "source_supervisor": follow_context,
        "entry_second_controller_summary": proof_summary,
        "entry_second_controller_exit_code": int(proof_exit),
        "entry_second_proof": proof,
        "resolved_bounds": bounds,
        "payload_result": payload_result,
    }
    if blockers:
        return result
    record = state_store.record_operator_action(
        run_id=f"{parent_run_id}-fast-follow-entry-second",
        action_type="arm-live-delta",
        reason="fresh entry_second no-order proof fast-follow approval",
        created_at_utc=_iso(current),
        payload=dict(payload_result["payload"]),
    )
    result.update(
        {
            "status": "authorized",
            "owner_approval_record": record,
        }
    )
    return result


def _schedule_fast_follow_entry_second(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    policy_cfg: dict[str, Any],
    source_supervisor_summary: dict[str, Any],
    authorization: dict[str, Any],
    command_runner: Callable[[list[str]], tuple[int, str, str]],
    now: datetime,
) -> dict[str, Any]:
    supervisor_cfg = dict(payload.get("mainnet_live_supervisor") or {})
    core_cfg = dict(payload.get("core_loop") or {})
    source_finished = _parse_utc_optional(source_supervisor_summary.get("finished_at_utc"))
    min_delay = float(core_cfg.get("fast_follow_entry_second_min_delay_seconds", 60.0) or 60.0)
    configured_max_age = float(core_cfg.get("fast_follow_entry_second_max_age_seconds", 180.0) or 180.0)
    auth_record = dict(authorization.get("owner_approval_record") or {})
    deadline = _fast_follow_authorization_deadline(auth_record)
    age_seconds = None
    schedule_at: datetime | None = None
    if source_finished is not None:
        age_seconds = max(0.0, (_coerce_utc(now) - source_finished).total_seconds())
    delay_seconds = 0
    blockers: list[str] = []
    if not auth_record:
        blockers.append("unattended_daily_policy_fast_follow_owner_approval_missing")
    if deadline is None:
        blockers.append("unattended_daily_policy_fast_follow_authorization_deadline_missing")
    if age_seconds is None:
        blockers.append("unattended_daily_policy_fast_follow_source_finish_time_missing")
    else:
        delay_seconds = max(0, int(math.ceil(float(min_delay) - float(age_seconds))))
        schedule_at = _coerce_utc(now) + timedelta(seconds=int(delay_seconds))
        if deadline is not None and schedule_at > deadline:
            blockers.append(
                "unattended_daily_policy_fast_follow_authorization_window_expired:"
                f"{_iso(schedule_at)}>{_iso(deadline)}"
            )
    if blockers:
        return {
            "status": "blocked",
            "blockers": sorted(set(blockers)),
            "source_finished_at_utc": str(source_supervisor_summary.get("finished_at_utc") or ""),
            "age_seconds": age_seconds,
            "delay_seconds": int(delay_seconds),
            "scheduled_for_utc": _iso(schedule_at) if schedule_at is not None else "",
            "authorization_deadline_utc": _iso(deadline) if deadline is not None else "",
            "configured_max_age_seconds": float(configured_max_age),
        }
    source_run_id = str(source_supervisor_summary.get("run_id") or "fast-follow-entry-second")
    unit_suffix = "".join(ch for ch in str(source_run_id).replace("-mainnet-live-supervisor", "") if ch.isalnum())[-24:]
    unit_name = f"meridian-alpha-mainnet-fast-follow-entry-second-{unit_suffix}"
    repo_root = str(supervisor_cfg.get("repo_root") or "/root/meridian_alpha_live_runner/repo")
    env_wrapper = str(supervisor_cfg.get("env_wrapper") or "/root/meridian_alpha_live_runner/bin/with-live-env")
    python_path = str(supervisor_cfg.get("python_path") or "/root/meridian_alpha_live_runner/venv/bin/python")
    script_path = str(
        supervisor_cfg.get("supervisor_script") or "scripts/live_trading/run_hv_balanced_mainnet_live_supervisor.py"
    )
    runtime_max_seconds = int(float(supervisor_cfg.get("fast_follow_runtime_max_seconds") or 420))
    cmd = [
        "systemd-run",
        "--collect",
        f"--unit={unit_name}",
        "--description=Meridian fast-follow entry_second after fresh no-order proof",
        f"--on-active={int(delay_seconds)}s",
        f"--property=WorkingDirectory={repo_root}",
        "--property=Environment=PYTHONUNBUFFERED=1",
        f"--property=RuntimeMaxSec={runtime_max_seconds}",
        env_wrapper,
        python_path,
        script_path,
        "--config",
        str(getattr(args, "config", DEFAULT_POLICY_CONFIG)),
        "--cycles",
        "1",
        "--fast-follow-entry-second",
        "--fast-follow-chain-depth",
        "1",
    ]
    exit_code, stdout, stderr = command_runner(cmd)
    return {
        "status": "scheduled" if int(exit_code) == 0 else "blocked",
        "blockers": [] if int(exit_code) == 0 else [f"unattended_daily_policy_fast_follow_systemd_run_failed:{int(exit_code)}"],
        "unit_name": unit_name,
        "command": cmd,
        "exit_code": int(exit_code),
        "stdout": str(stdout).strip(),
        "stderr": str(stderr).strip(),
        "source_supervisor_run_id": source_run_id,
        "owner_approval_action_id": str(auth_record.get("action_id") or ""),
        "age_seconds": age_seconds,
        "delay_seconds": int(delay_seconds),
        "scheduled_for_utc": _iso(schedule_at) if schedule_at is not None else "",
        "authorization_deadline_utc": _iso(deadline) if deadline is not None else "",
        "configured_max_age_seconds": float(configured_max_age),
        "max_age_source": "owner_approval_timer_window",
    }


def _timer_name(*, args: argparse.Namespace, policy_cfg: dict[str, Any]) -> str:
    return str(
        getattr(args, "systemd_timer_name", "")
        or policy_cfg.get("supervisor_timer_name")
        or policy_cfg.get("systemd_timer_name")
        or policy_cfg.get("timer_name")
        or ""
    ).strip()


def _arg_or_config(args: argparse.Namespace, name: str, policy_cfg: dict[str, Any]) -> Any:
    value = getattr(args, name, None)
    return value if value is not None else policy_cfg.get(name)


def _int_arg_or_config(args: argparse.Namespace, name: str, policy_cfg: dict[str, Any], *, default: int) -> int:
    value = _arg_or_config(args, name, policy_cfg)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _float_arg_or_config(args: argparse.Namespace, name: str, policy_cfg: dict[str, Any], *, default: float) -> float:
    value = _arg_or_config(args, name, policy_cfg)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _fast_follow_authorization_deadline(approval: dict[str, Any]) -> datetime | None:
    deadlines: list[datetime] = []
    expires_at = _parse_utc_optional(approval.get("approval_expires_at_utc"))
    if expires_at is not None:
        deadlines.append(expires_at)
    window = dict(approval.get("timer_window") or approval.get("timer_window_utc") or {})
    window_latest = _parse_utc_optional(
        window.get("timer_enable_latest_utc")
        or window.get("enable_latest_utc")
        or window.get("end_at_utc")
        or window.get("end_utc")
        or approval.get("timer_enable_latest_utc")
    )
    if window_latest is not None:
        deadlines.append(window_latest)
    return min(deadlines) if deadlines else None


def classify_unattended_daily_policy_service_state(
    service_status: dict[str, Any],
    *,
    expected_timer_fire_after_utc: Any = None,
    latest_invocation_started_at_utc: Any = None,
    latest_summary_status: str = "",
    latest_summary_finished_at_utc: Any = None,
) -> dict[str, Any]:
    active_state = str(service_status.get("ActiveState") or service_status.get("active_state") or "").strip()
    result = str(service_status.get("Result") or service_status.get("result") or "").strip()
    failed = active_state == "failed" or result in {"failed", "exit-code", "signal", "timeout"}
    boundary = _parse_utc_optional(expected_timer_fire_after_utc)
    invocation_started = _parse_utc_optional(latest_invocation_started_at_utc)
    summary_finished = _parse_utc_optional(latest_summary_finished_at_utc)
    latest_observed = max([item for item in [invocation_started, summary_finished] if item is not None], default=None)
    ok_statuses = {
        "hold_until_next_rebalance_slot",
        "unattended_daily_policy_dry_run_ready",
        "unattended_daily_policy_armed_timer_off",
        "unattended_daily_policy_timer_fire_completed",
    }
    if not failed:
        status = "service_not_failed"
        fresh = False
    elif boundary is not None and (latest_observed is None or latest_observed <= boundary):
        status = "stale_failed_service_carryover"
        fresh = False
    elif latest_summary_status in ok_statuses:
        status = "failed_service_state_after_success_artifact"
        fresh = False
    else:
        status = "fresh_failed_service_invocation"
        fresh = True
    return {
        "status": status,
        "fresh_failure": bool(fresh),
        "active_state": active_state,
        "result": result,
        "expected_timer_fire_after_utc": _iso(boundary) if boundary is not None else "",
        "latest_invocation_started_at_utc": _iso(invocation_started) if invocation_started is not None else "",
        "latest_summary_finished_at_utc": _iso(summary_finished) if summary_finished is not None else "",
        "latest_summary_status": str(latest_summary_status or ""),
        "latest_observed_at_utc": _iso(latest_observed) if latest_observed is not None else "",
    }


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_utc_optional(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _coerce_utc(parsed)


def _coerce_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


def _run_command(cmd: list[str]) -> tuple[int, str, str]:
    import subprocess

    completed = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=30)
    return int(completed.returncode), str(completed.stdout), str(completed.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
