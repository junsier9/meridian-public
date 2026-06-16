from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.unattended_epoch_controller import (
    clone_approval_payload_for_rearm,
    evaluate_unattended_epoch_runtime_gate,
)
from enhengclaw.quant_research.contracts import write_json


DEFAULT_HEALTH_CONFIG = "config/live_trading/hv_balanced_binance_usdm_live_supervisor_candidate.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only health monitor for the mainnet no-order supervisor timer. "
            "It checks recent artifacts, sends Telegram alerts on failures, and disarms live delta."
        )
    )
    parser.add_argument("--config", default=DEFAULT_HEALTH_CONFIG)
    parser.add_argument("--recent-runs", type=int, default=None)
    parser.add_argument("--max-seconds-since-latest-run", type=float, default=None)
    parser.add_argument("--systemd-timer-name", default="")
    parser.add_argument("--skip-systemd-check", action="store_true")
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_health_monitor(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_health_monitor(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    command_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
    telegram_sender: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-health-monitor"
    live_config = load_live_trading_config(getattr(args, "config", DEFAULT_HEALTH_CONFIG))
    payload = live_config.payload
    health_cfg = _health_config(payload)
    health_cfg["_state_config"] = dict(payload.get("state") or {})
    no_order_expected = _as_bool(health_cfg.get("no_order_expected"), default=True)
    recent_count = int(getattr(args, "recent_runs", None) or health_cfg.get("recent_run_count", 3) or 3)
    recent_count = max(1, recent_count)
    max_latest_age = float(
        getattr(args, "max_seconds_since_latest_run", None)
        if getattr(args, "max_seconds_since_latest_run", None) is not None
        else health_cfg.get("max_seconds_since_latest_supervisor_run", 1200.0) or 1200.0
    )
    max_latest_age = max(1.0, max_latest_age)
    max_heartbeat_age = float(
        health_cfg.get("max_running_heartbeat_age_seconds")
        or dict(payload.get("risk") or {}).get("max_heartbeat_age_seconds", 900)
        or 900
    )
    run_root = live_config.artifact_root.parent / "mainnet_health_monitor" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    state_store.write_heartbeat(
        run_id=run_id,
        mode="mainnet_health_monitor",
        status="running",
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        artifact_root=str(run_root),
        extra={"component": "mainnet_health_monitor"},
    )

    alerts: list[dict[str, Any]] = []
    scoped_timer_checks = _as_bool(
        health_cfg.get("scope_timer_checks_to_active_unattended_epoch"),
        default=False,
    )
    active_unattended_epoch_gate: dict[str, Any] = {"status": "not_evaluated", "scoped": False}
    supervisor_timer_checks_required = True
    operator_state_snapshot = state_store.read_operator_state()
    if scoped_timer_checks:
        latest_owner_approval = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
        active_unattended_epoch_gate = evaluate_unattended_epoch_runtime_gate(
            state_store=state_store,
            payload={"state": dict(payload.get("state") or {})},
            now=started,
            approval_action=latest_owner_approval,
            require_approval=True,
            require_budget_epoch=True,
        )
        active_unattended_epoch_gate["scoped"] = True
        supervisor_timer_checks_required = active_unattended_epoch_gate.get("status") == "passed"
        if not supervisor_timer_checks_required and bool(operator_state_snapshot.get("live_delta_armed")):
            alerts.append(
                _alert(
                    "critical",
                    "live_delta_armed_without_active_unattended_epoch",
                    "Live delta is armed without a valid unattended approval, open epoch, and timer window.",
                    metrics={"active_unattended_epoch_gate": active_unattended_epoch_gate},
                )
            )
    timer_name = str(getattr(args, "systemd_timer_name", "") or health_cfg.get("systemd_timer_name") or "").strip()
    require_systemd = bool(health_cfg.get("require_systemd_timer_active", True)) and not bool(
        getattr(args, "skip_systemd_check", False)
    )
    if scoped_timer_checks and not supervisor_timer_checks_required:
        require_systemd = False
    timer_status = _systemd_timer_status(
        timer_name=timer_name,
        require_systemd=require_systemd,
        command_runner=command_runner or _run_command,
    )
    if scoped_timer_checks and not supervisor_timer_checks_required:
        timer_status = {
            **timer_status,
            "status": "skipped_inactive_unattended_epoch",
            "required": False,
            "active_unattended_epoch_gate": active_unattended_epoch_gate,
        }
    alerts.extend(_systemd_alerts(timer_status))

    supervisor_runs = _load_recent_supervisor_runs(live_config.artifact_root.parent, limit=recent_count)
    supervisor_artifact_checks = {
        "status": "required",
        "required": True,
        "reason": "",
    }
    if scoped_timer_checks and not supervisor_timer_checks_required:
        supervisor_artifact_checks = {
            "status": "skipped_inactive_unattended_epoch",
            "required": False,
            "reason": "no valid unattended approval/open epoch/timer window is active",
        }
    else:
        alerts.extend(
            _artifact_alerts(
                supervisor_runs,
                required_count=recent_count,
                now=started,
                max_latest_age_seconds=max_latest_age,
                no_order_expected=no_order_expected,
            )
        )
    heartbeat_health = state_store.evaluate_local_state_health(
        now=started,
        max_heartbeat_age_seconds=max_heartbeat_age,
        ignore_run_id=run_id,
    )
    alerts.extend(_heartbeat_alerts(heartbeat_health, max_heartbeat_age_seconds=max_heartbeat_age))

    critical_alerts = [item for item in alerts if item.get("level") == "critical"]
    warning_alerts = [item for item in alerts if item.get("level") == "warning"]
    disarm_record: dict[str, Any] | None = None
    if alerts and bool(health_cfg.get("disarm_on_alert", True)):
        # B2: persist the underlying supervisor blockers (not just the alert codes) into the disarm
        # record. A health-monitor relay disarm otherwise carries ONLY alert_codes, so the
        # _auto_rearm_disarm_is_recoverable hard-fragment check (which matches against `blockers`)
        # finds nothing and the force-added `unattended_budget` TERMINAL-disarm guard is silently
        # bypassed — letting auto-rearm resume against an exhausted budget epoch. Threading the real
        # blockers makes that guard fire precisely when a budget (or other hard) blocker is present.
        relayed_blockers = sorted(
            {str(b) for run in supervisor_runs for b in (run.get("blockers") or []) if str(b)}
        )
        disarm_record = state_store.record_operator_action(
            run_id=run_id,
            action_type="disarm-live-delta",
            reason="mainnet health monitor alert",
            payload={
                "source": "mainnet_health_monitor",
                "alert_codes": [str(item.get("code")) for item in alerts],
                "blockers": relayed_blockers,
                "critical_alert_count": len(critical_alerts),
                "warning_alert_count": len(warning_alerts),
            },
        )

    auto_rearm_gate, auto_rearm_record = _maybe_auto_rearm_live_delta(
        state_store=state_store,
        health_cfg=health_cfg,
        alerts=alerts,
        supervisor_runs=supervisor_runs,
        now=started,
        run_id=run_id,
        no_order_expected=no_order_expected,
    )

    telegram = _maybe_send_telegram(
        alerts=alerts,
        env=env or os.environ,
        health_cfg=health_cfg,
        sender=telegram_sender or _send_telegram_message,
        run_id=run_id,
    )
    finished = datetime.now(UTC)
    summary = {
        "run_id": run_id,
        "status": "mainnet_health_monitor_passed" if not alerts else "mainnet_health_monitor_alerted",
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": finished.isoformat().replace("+00:00", "Z"),
        "artifact_root": str(run_root),
        "config": str(live_config.path),
        "mode": "mainnet_health_monitor",
        "no_order_expected": bool(no_order_expected),
        "recent_run_count_required": recent_count,
        "recent_run_count_observed": len(supervisor_runs),
        "max_seconds_since_latest_supervisor_run": max_latest_age,
        "max_running_heartbeat_age_seconds": max_heartbeat_age,
        "alerts": alerts,
        "critical_alert_count": len(critical_alerts),
        "warning_alert_count": len(warning_alerts),
        "systemd_timer_status": timer_status,
        "scope_timer_checks_to_active_unattended_epoch": bool(scoped_timer_checks),
        "active_unattended_epoch_gate": active_unattended_epoch_gate,
        "supervisor_timer_checks_required": bool(supervisor_timer_checks_required),
        "supervisor_artifact_checks": supervisor_artifact_checks,
        "supervisor_runs": supervisor_runs,
        "heartbeat_health": heartbeat_health,
        "telegram": telegram,
        "disarm_record": disarm_record,
        "auto_rearm_gate": auto_rearm_gate,
        "auto_rearm_record": auto_rearm_record,
        "live_delta_armed_after": bool(state_store.read_operator_state().get("live_delta_armed")),
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(run_root / "run_summary.json", summary)
    write_json(run_root / "alerts.json", {"alerts": alerts})
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="mainnet_health_monitor_summary",
        artifact_id=f"{run_id}:summary",
        payload=summary,
    )
    state_store.write_heartbeat(
        run_id=run_id,
        mode="mainnet_health_monitor",
        status=str(summary["status"]),
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(run_root),
        blockers=[str(item.get("code")) for item in alerts],
        extra={"critical_alert_count": len(critical_alerts), "warning_alert_count": len(warning_alerts)},
    )
    exit_code = 0 if not alerts else int(health_cfg.get("exit_code_on_alert", 2) or 2)
    return summary, exit_code


def _health_config(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload.get("mainnet_health_monitor") or payload.get("health_monitor") or {})


def _load_recent_supervisor_runs(root: Path, *, limit: int) -> list[dict[str, Any]]:
    supervisor_root = Path(root) / "mainnet_live_supervisor"
    rows: list[dict[str, Any]] = []
    for summary_path in supervisor_root.glob("*/run_summary.json"):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        row = _summarize_supervisor_run(payload, summary_path=summary_path)
        rows.append(row)
    rows.sort(key=lambda item: str(item.get("started_at_utc") or item.get("finished_at_utc") or ""), reverse=True)
    return rows[:limit]


def _summarize_supervisor_run(payload: dict[str, Any], *, summary_path: Path) -> dict[str, Any]:
    cycles = list(payload.get("cycles") or [])
    cycle = dict(cycles[-1]) if cycles and isinstance(cycles[-1], dict) else {}
    core = dict(cycle.get("core_loop_summary") or {})
    core_cycles = list(core.get("cycles") or [])
    core_cycle = dict(core_cycles[-1]) if core_cycles and isinstance(core_cycles[-1], dict) else {}
    account_reconcile = dict(core_cycle.get("account_reconcile") or {})
    daily_pnl = dict(core_cycle.get("daily_realized_pnl_gate") or {})
    margin = dict(core_cycle.get("margin_cushion_gate") or {})
    delta_preflight = dict(core_cycle.get("delta_preflight") or {})
    policy = dict(core_cycle.get("live_delta_policy_gate") or {})
    return {
        "run_id": payload.get("run_id"),
        "artifact_root": payload.get("artifact_root") or str(summary_path.parent),
        "summary_path": str(summary_path),
        "started_at_utc": payload.get("started_at_utc"),
        "finished_at_utc": payload.get("finished_at_utc"),
        "status": payload.get("status"),
        "blockers": list(payload.get("blockers") or []),
        "live_delta_armed_at_start": bool(payload.get("live_delta_armed_at_start")),
        "live_delta_armed_at_finish": bool(payload.get("live_delta_armed_at_finish")),
        "orders_submitted": int(payload.get("orders_submitted") or 0),
        "fill_count": int(payload.get("fill_count") or 0),
        "cycle_status": cycle.get("status"),
        "execute_live_delta_requested": bool(cycle.get("execute_live_delta_requested")),
        "live_delta_authorized": bool(cycle.get("live_delta_authorized")),
        "core_loop_status": cycle.get("core_loop_status") or core.get("status"),
        "core_loop_execution_requested": bool(
            cycle.get("core_loop_execution_requested")
            if cycle.get("core_loop_execution_requested") is not None
            else core.get("execution_requested")
        ),
        "core_loop_orders_submitted": int(core.get("orders_submitted") or 0),
        "core_loop_fill_count": int(core.get("fill_count") or 0),
        "account_reconcile_status": account_reconcile.get("status"),
        "open_order_count": int(core_cycle.get("open_order_count") or 0),
        "daily_pnl_status": daily_pnl.get("status"),
        "daily_realized_pnl_usdt": daily_pnl.get("daily_realized_pnl_usdt"),
        "margin_cushion_status": margin.get("status"),
        "available_balance_usdt": margin.get("available_balance_usdt"),
        "delta_preflight_status": delta_preflight.get("status"),
        "execution_stage": policy.get("execution_stage"),
        "planned_delta_order_count": int(core_cycle.get("planned_delta_order_count") or policy.get("planned_delta_order_count") or 0),
        "planned_execution_phases": list(policy.get("planned_execution_phases") or []),
    }


def _artifact_alerts(
    supervisor_runs: list[dict[str, Any]],
    *,
    required_count: int,
    now: datetime,
    max_latest_age_seconds: float,
    no_order_expected: bool = True,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if not supervisor_runs:
        return [_alert("critical", "missing_supervisor_artifacts", "No recent mainnet supervisor artifacts found.")]
    if len(supervisor_runs) < required_count:
        alerts.append(
            _alert(
                "warning",
                "insufficient_recent_supervisor_runs",
                f"Only {len(supervisor_runs)} supervisor artifacts found; expected {required_count}.",
            )
        )
    latest = supervisor_runs[0]
    latest_time = _parse_utc(latest.get("finished_at_utc") or latest.get("started_at_utc"))
    age = max(0.0, (now - latest_time).total_seconds())
    if age > max_latest_age_seconds:
        alerts.append(
            _alert(
                "critical",
                "stale_latest_supervisor_run",
                f"Latest supervisor run is {age:.1f}s old; max allowed is {max_latest_age_seconds:.1f}s.",
                run=latest,
                metrics={"age_seconds": round(age, 3), "max_age_seconds": float(max_latest_age_seconds)},
            )
        )
    for run in supervisor_runs:
        alerts.extend(_single_run_alerts(run, no_order_expected=no_order_expected))
    return alerts


def _single_run_alerts(run: dict[str, Any], *, no_order_expected: bool = True) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if str(run.get("status") or "") != "mainnet_live_supervisor_completed":
        alerts.append(_alert("critical", "supervisor_run_not_completed", f"Supervisor run status is {run.get('status')}.", run=run))
    blockers = [str(item) for item in list(run.get("blockers") or [])]
    if blockers:
        alerts.append(_alert("critical", "supervisor_run_blockers", f"Supervisor run has blockers: {','.join(blockers)}.", run=run))
    if no_order_expected and (bool(run.get("live_delta_armed_at_start")) or bool(run.get("live_delta_armed_at_finish"))):
        alerts.append(_alert("critical", "live_delta_armed_during_noorder_timer", "Live delta was armed during no-order timer observation.", run=run))
    if no_order_expected and (bool(run.get("execute_live_delta_requested")) or bool(run.get("core_loop_execution_requested"))):
        alerts.append(_alert("critical", "live_delta_execution_requested", "No-order timer requested live delta execution.", run=run))
    orders = int(run.get("orders_submitted") or 0) + int(run.get("core_loop_orders_submitted") or 0)
    fills = int(run.get("fill_count") or 0) + int(run.get("core_loop_fill_count") or 0)
    if no_order_expected and (orders > 0 or fills > 0):
        alerts.append(
            _alert(
                "critical",
                "supervisor_order_or_fill_nonzero",
                f"No-order timer observed nonzero orders/fills: orders={orders}, fills={fills}.",
                run=run,
                metrics={"orders": orders, "fills": fills},
            )
        )
    if not no_order_expected and (orders > 0 or fills > 0) and not bool(run.get("live_delta_authorized")):
        alerts.append(
            _alert(
                "critical",
                "live_order_or_fill_without_authorization",
                f"Live-capable timer observed orders/fills without live_delta_authorized=true: orders={orders}, fills={fills}.",
                run=run,
                metrics={"orders": orders, "fills": fills},
            )
        )
    if not no_order_expected and orders != fills:
        alerts.append(
            _alert(
                "critical",
                "live_order_fill_count_mismatch",
                f"Live-capable timer observed submitted/fill mismatch: orders={orders}, fills={fills}.",
                run=run,
                metrics={"orders": orders, "fills": fills},
            )
        )
    if int(run.get("open_order_count") or 0) > 0:
        alerts.append(_alert("critical", "open_orders_present", f"Open orders present: {run.get('open_order_count')}.", run=run))
    if str(run.get("account_reconcile_status") or "") != "passed_live_position_monitor":
        alerts.append(
            _alert(
                "critical",
                "account_reconcile_not_passed",
                f"Account reconcile/API read status is {run.get('account_reconcile_status')}.",
                run=run,
            )
        )
    if str(run.get("core_loop_status") or "") != "mainnet_core_loop_completed":
        alerts.append(_alert("critical", "core_loop_not_completed", f"Core loop status is {run.get('core_loop_status')}.", run=run))
    if not _daily_pnl_status_is_inert(run.get("daily_pnl_status")):
        alerts.append(_alert("critical", "daily_pnl_gate_not_passed", f"Daily PnL gate status is {run.get('daily_pnl_status')}.", run=run))
    if str(run.get("margin_cushion_status") or "") != "passed":
        alerts.append(_alert("critical", "margin_cushion_gate_not_passed", f"Margin cushion gate status is {run.get('margin_cushion_status')}.", run=run))
    return alerts


def _daily_pnl_status_is_inert(status: Any) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {"passed", "removed", "disabled", "not_applicable", ""}


def _heartbeat_alerts(health: dict[str, Any], *, max_heartbeat_age_seconds: float) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if int(health.get("orphan_paper_order_count") or 0) > 0:
        alerts.append(_alert("critical", "orphan_paper_orders_present", f"Orphan paper orders: {health.get('orphan_paper_order_count')}."))
    if int(health.get("orphan_paper_fill_count") or 0) > 0:
        alerts.append(_alert("critical", "orphan_paper_fills_present", f"Orphan paper fills: {health.get('orphan_paper_fill_count')}."))
    for row in list(health.get("running_heartbeats") or []):
        age = float(row.get("age_seconds") or 0.0)
        if age > max_heartbeat_age_seconds:
            alerts.append(
                _alert(
                    "critical",
                    "heartbeat_residue",
                    f"Running heartbeat residue {row.get('run_id')} age {age:.1f}s exceeds {max_heartbeat_age_seconds:.1f}s.",
                    metrics={"run_id": row.get("run_id"), "mode": row.get("mode"), "age_seconds": age},
                )
            )
    return alerts


def _maybe_auto_rearm_live_delta(
    *,
    state_store: LiveTradingStateStore,
    health_cfg: dict[str, Any],
    alerts: list[dict[str, Any]],
    supervisor_runs: list[dict[str, Any]],
    now: datetime,
    run_id: str,
    no_order_expected: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    enabled = _as_bool(health_cfg.get("auto_rearm_live_delta"), default=False)
    gate: dict[str, Any] = {"enabled": enabled, "status": "skipped_disabled"}
    if not enabled:
        return gate, None
    if alerts:
        gate["status"] = "blocked_current_health_alerts"
        gate["alert_codes"] = [str(item.get("code")) for item in alerts]
        return gate, None
    if _as_bool(health_cfg.get("auto_rearm_requires_live_capable_timer"), default=True) and no_order_expected:
        gate["status"] = "blocked_no_order_timer"
        gate["no_order_expected"] = True
        return gate, None

    operator_state = state_store.read_operator_state()
    gate["operator_state"] = {
        "paused": bool(operator_state.get("paused")),
        "live_delta_armed": bool(operator_state.get("live_delta_armed")),
        "live_delta_last_action_type": operator_state.get("live_delta_last_action_type"),
    }
    if bool(operator_state.get("paused")):
        gate["status"] = "blocked_operator_paused_or_kill_switch"
        return gate, None
    if bool(operator_state.get("live_delta_armed")):
        gate["status"] = "skipped_already_armed"
        return gate, None
    if str(operator_state.get("live_delta_last_action_type") or "") != "disarm-live-delta":
        gate["status"] = "blocked_latest_live_delta_action_not_disarm"
        return gate, None

    last_disarm = state_store.latest_operator_action(action_type="disarm-live-delta", status="applied")
    if not last_disarm:
        gate["status"] = "blocked_missing_disarm_record"
        return gate, None
    gate["last_disarm_action_id"] = last_disarm.get("action_id")
    gate["last_disarm_run_id"] = last_disarm.get("run_id")
    gate["last_disarm_created_at_utc"] = last_disarm.get("created_at_utc")

    recoverable_gate = _auto_rearm_disarm_is_recoverable(last_disarm, health_cfg=health_cfg)
    gate["recoverable_disarm_gate"] = recoverable_gate
    if recoverable_gate.get("status") != "passed":
        gate["status"] = "blocked_last_disarm_not_recoverable"
        return gate, None

    disarm_time = _parse_utc(last_disarm.get("created_at_utc"))
    min_age_seconds = float(health_cfg.get("auto_rearm_min_seconds_since_disarm", 900.0) or 900.0)
    age_seconds = max(0.0, (now - disarm_time).total_seconds())
    gate["seconds_since_last_disarm"] = round(age_seconds, 3)
    gate["min_seconds_since_last_disarm"] = min_age_seconds
    if age_seconds < min_age_seconds:
        gate["status"] = "blocked_disarm_too_recent"
        return gate, None

    required_clean = int(health_cfg.get("auto_rearm_required_clean_supervisor_runs", 3) or 3)
    required_clean = max(1, required_clean)
    post_disarm_runs = [
        run
        for run in supervisor_runs
        if _parse_utc(run.get("finished_at_utc") or run.get("started_at_utc")) > disarm_time
    ]
    clean_runs = [run for run in post_disarm_runs if _is_clean_auto_rearm_supervisor_run(run)]
    gate["required_clean_supervisor_runs"] = required_clean
    gate["post_disarm_supervisor_run_ids"] = [str(run.get("run_id")) for run in post_disarm_runs]
    gate["clean_supervisor_run_ids"] = [str(run.get("run_id")) for run in clean_runs]
    if len(post_disarm_runs) < required_clean:
        gate["status"] = "blocked_insufficient_post_disarm_supervisor_runs"
        return gate, None
    if len(clean_runs) < required_clean or [
        str(run.get("run_id")) for run in post_disarm_runs[:required_clean]
    ] != [str(run.get("run_id")) for run in clean_runs[:required_clean]]:
        gate["status"] = "blocked_post_disarm_runs_not_clean"
        return gate, None

    latest_owner_approval = state_store.latest_operator_action(action_type="arm-live-delta", status="applied")
    unattended_gate = evaluate_unattended_epoch_runtime_gate(
        state_store=state_store,
        payload={"state": health_cfg.get("_state_config", {})},
        now=now,
        approval_action=latest_owner_approval,
        require_approval=True,
        require_budget_epoch=True,
    )
    gate["unattended_epoch_runtime_gate"] = unattended_gate
    if unattended_gate.get("status") != "passed":
        gate["status"] = "blocked_unattended_epoch_runtime_gate"
        return gate, None

    record = state_store.record_operator_action(
        run_id=run_id,
        action_type="arm-live-delta",
        reason=f"auto rearm after {required_clean} clean supervisor/health runs",
        payload=clone_approval_payload_for_rearm(
            dict(latest_owner_approval or {}),
            extra={
                "source": "mainnet_health_monitor_auto_rearm",
                "last_disarm_action_id": last_disarm.get("action_id"),
                "last_disarm_run_id": last_disarm.get("run_id"),
                "clean_supervisor_run_ids": [str(run.get("run_id")) for run in clean_runs[:required_clean]],
                "seconds_since_last_disarm": round(age_seconds, 3),
            },
        ),
    )
    gate["status"] = "auto_rearmed"
    gate["auto_rearm_action_id"] = record.get("action_id")
    return gate, record


def _auto_rearm_disarm_is_recoverable(
    last_disarm: dict[str, Any], *, health_cfg: dict[str, Any]
) -> dict[str, Any]:
    alert_codes = {str(item) for item in list(last_disarm.get("alert_codes") or []) if str(item)}
    blockers = [str(item) for item in list(last_disarm.get("blockers") or []) if str(item)]
    hard_codes = _csv_set(
        health_cfg.get("auto_rearm_blocked_alert_codes"),
        default={
            "heartbeat_residue",
            "live_delta_armed_during_noorder_timer",
            "live_delta_execution_requested",
            "live_order_fill_count_mismatch",
            "live_order_or_fill_without_authorization",
            "open_orders_present",
            "orphan_paper_fills_present",
            "orphan_paper_orders_present",
            "supervisor_order_or_fill_nonzero",
        },
    )
    hard_fragments = _csv_set(
        health_cfg.get("auto_rearm_blocked_blocker_fragments"),
        default={
            "heartbeat_residue",
            "open_orders",
            "order_or_fill",
            "position_drift",
            "pnl_breach",
            "unauthorized",
            "unknown_status",
        },
    )
    # FORCE-ADD (not merely a default): a restricted-unattended budget disarm
    # (budget/turnover/cycle exhausted, stale epoch, orphan reservation) is a
    # TERMINAL stop, not a transient throttle. It must never auto-rearm, or the
    # machine would oscillate disarm/rearm against an exhausted epoch. Because the
    # operator config OVERRIDES the default set, this fragment is added
    # unconditionally so an operator cannot drop it. All budget blocker codes
    # share the `unattended_budget` substring.
    hard_fragments = set(hard_fragments) | {"unattended_budget", "unattended_approval", "unattended_timer"}
    blocked_codes = sorted(alert_codes.intersection(hard_codes))
    blocked_fragments = sorted(
        fragment for fragment in hard_fragments if any(fragment in blocker for blocker in blockers)
    )
    if blocked_codes or blocked_fragments:
        return {
            "status": "blocked_hard_disarm_reason",
            "alert_codes": sorted(alert_codes),
            "blockers": blockers,
            "blocked_alert_codes": blocked_codes,
            "blocked_blocker_fragments": blocked_fragments,
        }
    return {"status": "passed", "alert_codes": sorted(alert_codes), "blockers": blockers}


def _is_clean_auto_rearm_supervisor_run(run: dict[str, Any]) -> bool:
    if str(run.get("status") or "") != "mainnet_live_supervisor_completed":
        return False
    if list(run.get("blockers") or []):
        return False
    if bool(run.get("live_delta_armed_at_start")) or bool(run.get("live_delta_armed_at_finish")):
        return False
    if bool(run.get("execute_live_delta_requested")) or bool(run.get("core_loop_execution_requested")):
        return False
    if int(run.get("orders_submitted") or 0) + int(run.get("core_loop_orders_submitted") or 0) > 0:
        return False
    if int(run.get("fill_count") or 0) + int(run.get("core_loop_fill_count") or 0) > 0:
        return False
    if int(run.get("open_order_count") or 0) > 0:
        return False
    if str(run.get("account_reconcile_status") or "") != "passed_live_position_monitor":
        return False
    if str(run.get("core_loop_status") or "") != "mainnet_core_loop_completed":
        return False
    if not _daily_pnl_status_is_inert(run.get("daily_pnl_status")):
        return False
    if str(run.get("margin_cushion_status") or "") != "passed":
        return False
    return True


def _systemd_timer_status(
    *,
    timer_name: str,
    require_systemd: bool,
    command_runner: Callable[[list[str]], tuple[int, str, str]],
) -> dict[str, Any]:
    if not require_systemd:
        return {"status": "skipped", "timer_name": timer_name, "required": False}
    if not timer_name:
        return {"status": "blocked", "timer_name": "", "required": True, "blockers": ["missing_systemd_timer_name"]}
    active_code, active_out, active_err = command_runner(["systemctl", "is-active", timer_name])
    enabled_code, enabled_out, enabled_err = command_runner(["systemctl", "is-enabled", timer_name])
    list_code, list_out, list_err = command_runner(["systemctl", "list-timers", "--all", timer_name, "--no-pager"])
    return {
        "status": "ok" if active_code == 0 and str(active_out).strip() == "active" and enabled_code == 0 else "blocked",
        "timer_name": timer_name,
        "required": True,
        "is_active_stdout": str(active_out).strip(),
        "is_active_exit_code": int(active_code),
        "is_active_stderr": str(active_err).strip(),
        "is_enabled_stdout": str(enabled_out).strip(),
        "is_enabled_exit_code": int(enabled_code),
        "is_enabled_stderr": str(enabled_err).strip(),
        "list_timers_exit_code": int(list_code),
        "list_timers_stdout": str(list_out).strip(),
        "list_timers_stderr": str(list_err).strip(),
    }


def _systemd_alerts(status: dict[str, Any]) -> list[dict[str, Any]]:
    if status.get("required") is False:
        return []
    if status.get("status") == "ok":
        return []
    return [
        _alert(
            "critical",
            "systemd_timer_not_active",
            f"Systemd timer {status.get('timer_name') or '<missing>'} is not active/enabled.",
            metrics=status,
        )
    ]


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv_set(value: Any, *, default: set[str]) -> set[str]:
    if value is None:
        return set(default)
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _maybe_send_telegram(
    *,
    alerts: list[dict[str, Any]],
    env: Mapping[str, str],
    health_cfg: dict[str, Any],
    sender: Callable[[str, str, str], dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    if not alerts:
        return {"status": "skipped_no_alerts"}
    token_env = str(health_cfg.get("telegram_bot_token_env") or "TELEGRAM_BOT_TOKEN").strip()
    chat_env = str(health_cfg.get("telegram_chat_id_env") or "TELEGRAM_CHAT_ID").strip()
    token = str(env.get(token_env, "") or "").strip()
    chat_id = str(env.get(chat_env, "") or "").strip()
    if not token or not chat_id:
        return {
            "status": "skipped_missing_credentials",
            "telegram_bot_token_env": token_env,
            "telegram_chat_id_env": chat_env,
        }
    text = _telegram_text(alerts, run_id=run_id)
    try:
        result = sender(token, chat_id, text)
    except Exception as exc:  # pragma: no cover - network errors depend on runtime.
        return {"status": "failed", "error": f"{type(exc).__name__}:{exc}"}
    return {"status": "sent", "result": result}


def _telegram_text(alerts: list[dict[str, Any]], *, run_id: str) -> str:
    codes = ", ".join(str(item.get("code")) for item in alerts[:8])
    suffix = "" if len(alerts) <= 8 else f" (+{len(alerts) - 8} more)"
    return (
        "[EnhengClaw mainnet health alert]\n"
        f"run_id={run_id}\n"
        f"alert_count={len(alerts)}\n"
        f"codes={codes}{suffix}\n"
        "action=live_delta_disarmed; no new mainnet entries should be opened"
    )


def _send_telegram_message(token: str, chat_id: str, text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - operator-supplied Telegram endpoint.
        body = response.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"raw_body": body}
    return {"status_code": int(getattr(response, "status", 0) or 0), "payload": parsed}


def _run_command(cmd: list[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, str(exc.stdout or ""), str(exc.stderr or exc)
    return int(completed.returncode), str(completed.stdout), str(completed.stderr)


def _alert(
    level: str,
    code: str,
    message: str,
    *,
    run: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {"level": level, "code": code, "message": message}
    if run:
        item.update(
            {
                "run_id": run.get("run_id"),
                "artifact_root": run.get("artifact_root"),
                "started_at_utc": run.get("started_at_utc"),
                "finished_at_utc": run.get("finished_at_utc"),
            }
        )
    if metrics:
        item["metrics"] = metrics
    return item


def _parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0, tz=UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
