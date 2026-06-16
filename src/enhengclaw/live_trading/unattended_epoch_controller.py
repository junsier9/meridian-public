from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import urllib.parse
import urllib.request
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.daily_rebalance_slot_gate import FROZEN_TARGET_SNAPSHOT_ARTIFACT
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.live_trading.unattended_budget_hook import budget_store_from_payload, projected_turnover_usdt
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore
from enhengclaw.quant_research.contracts import read_json, write_json


UNATTENDED_EPOCH_APPROVAL_CONTRACT = "limited_unattended_epoch_owner_approval.v1"
UNATTENDED_EPOCH_CONTROLLER_SUMMARY_VERSION = "unattended_epoch_controller.v1"
_RESERVED_OPERATOR_ACTION_FIELDS = {
    "action_id",
    "action_type",
    "created_at_utc",
    "reason",
    "run_id",
    "status",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create one limited unattended epoch for a fresh closed rebalance slot. "
            "Default mode is dry-run; --apply is required to open budget/arm."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_supervisor_candidate.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--reference-run", default="")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-gross-turnover-usdt", type=float, default=None)
    parser.add_argument("--max-live-cycles", type=int, default=None)
    parser.add_argument("--max-age-seconds", type=int, default=None)
    parser.add_argument("--approval-ttl-seconds", type=int, default=None)
    parser.add_argument("--timer-window-seconds", type=int, default=None)
    parser.add_argument("--max-timer-fires", type=int, default=None)
    parser.add_argument("--systemd-timer-name", default="")
    parser.add_argument("--ignore-heartbeat-run-id", default="")
    parser.add_argument("--fast-follow-entry-second-proof", dest="fast_follow_entry_second", action="store_true")
    parser.add_argument("--no-terminal-cleanup-on-failure", action="store_true")
    args = parser.parse_args(argv)
    summary, exit_code = run_unattended_epoch_controller(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_unattended_epoch_controller(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    no_order_runner: Callable[..., tuple[dict[str, Any], int]] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    command_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
    notification_sender: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], int]:
    started = _coerce_utc((now_fn or (lambda: datetime.now(UTC)))())
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-unattended-epoch-controller"
    live_config = load_live_trading_config(getattr(args, "config", ""))
    payload = live_config.payload
    controller_cfg = _controller_config(payload)
    run_root = live_config.artifact_root.parent / "unattended_epoch_controller" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()
    budget_store = budget_store_from_payload(payload)
    state_store.write_heartbeat(
        run_id=run_id,
        mode="unattended_epoch_controller",
        status="running",
        started_at_utc=_iso(started),
        artifact_root=str(run_root),
        extra={"component": "unattended_epoch_controller"},
    )

    if no_order_runner is None:
        from enhengclaw.live_trading.mainnet_core_loop_runner import run_mainnet_core_loop

        no_order_runner = run_mainnet_core_loop

    no_order_args = Namespace(
        config=str(live_config.path),
        as_of=str(getattr(args, "as_of", "now") or "now"),
        fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
        symbols=str(getattr(args, "symbols", "") or ""),
        public_market_data=bool(getattr(args, "public_market_data", False)),
        reference_run=str(getattr(args, "reference_run", "") or ""),
        target_engine=str(getattr(args, "target_engine", "") or ""),
        cycles=1,
        interval_seconds=0.0,
        execute_live_delta=False,
        operator_enable_live_delta_for_this_run=False,
        i_understand_this_places_real_mainnet_delta_orders=False,
        i_understand_daily_realized_pnl_gate_is_active=False,
        confirm_mainnet_delta_execution="",
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
        ignore_heartbeat_run_id=_ignore_heartbeat_run_ids(run_id, getattr(args, "ignore_heartbeat_run_id", "")),
        capital_topup=False,
        fast_follow_entry_second=bool(getattr(args, "fast_follow_entry_second", False)),
    )
    try:
        if now_fn is None:
            no_order_summary, no_order_exit = no_order_runner(no_order_args, env=env or os.environ)
        else:
            no_order_summary, no_order_exit = no_order_runner(no_order_args, env=env or os.environ, now_fn=now_fn)
    except Exception as exc:  # pragma: no cover - direct unit tests cover cleanup instead.
        no_order_summary = {
            "status": "unattended_epoch_no_order_runner_exception",
            "blockers": [f"no_order_runner_exception:{type(exc).__name__}:{exc}"],
        }
        no_order_exit = 2

    proof = build_no_order_proof(no_order_summary, no_order_exit=no_order_exit)
    blockers = [str(item) for item in list(proof.get("blockers") or [])]
    if no_order_exit != 0:
        blockers.append(f"fresh_no_order_proof_failed:{proof.get('status')}")

    slot = dict(proof.get("slot") or {})
    slot_id = str(slot.get("slot_id") or "")
    target_hash = str(slot.get("target_hash") or "")
    slot_status = str(slot.get("status") or "").strip().lower()
    if proof.get("status") == "passed" and not slot_id:
        blockers.append("unattended_epoch_controller_missing_rebalance_slot")
    if proof.get("status") == "passed" and proof.get("planned_order_count", 0) <= 0 and slot_status != "completed":
        blockers.append("unattended_epoch_controller_no_planned_orders_for_open_slot")

    apply_changes = bool(getattr(args, "apply", False))
    cleanup_on_failure = not bool(getattr(args, "no_terminal_cleanup_on_failure", False))
    opened_epoch_id = ""
    budget_open_result: dict[str, Any] | None = None
    owner_approval_record: dict[str, Any] | None = None
    runtime_gate: dict[str, Any] | None = None
    terminal_cleanup_result: dict[str, Any] | None = None
    status = "unattended_epoch_controller_blocked" if blockers else "unattended_epoch_controller_ready"

    if not blockers and slot_status == "completed":
        status = "hold_until_next_rebalance_slot"
    elif not blockers:
        existing_approval = state_store.latest_operator_action(
            action_type="arm-live-delta",
            status="applied",
            slot_id=slot_id,
            target_hash=target_hash,
        )
        if existing_approval:
            existing_gate = evaluate_unattended_epoch_runtime_gate(
                state_store=state_store,
                payload=payload,
                now=started,
                approval_action=existing_approval,
                budget_store=budget_store,
                require_approval=True,
                require_budget_epoch=True,
            )
            if existing_gate.get("status") == "passed":
                runtime_gate = existing_gate
                status = "unattended_epoch_approval_already_active"
        if status == "unattended_epoch_controller_ready":
            bounds = _controller_bounds(args=args, controller_cfg=controller_cfg)
            blockers.extend(list(bounds.get("blockers") or []))
            if not blockers:
                bounds = resolve_turnover_budget_from_proof(bounds=bounds, proof=proof)
                blockers.extend(list(bounds.get("blockers") or []))
            if not blockers and budget_store.read_current_epoch() is not None:
                blockers.append("unattended_epoch_controller_open_budget_epoch_already_exists")
            if not blockers:
                approval_payload = build_owner_approval_payload(
                    run_id=run_id,
                    now=started,
                    proof=proof,
                    epoch_id=f"{run_id}:epoch",
                    bounds=bounds,
                    timer_name=_timer_name(args=args, controller_cfg=controller_cfg),
                )
                if apply_changes:
                    budget_open_result = budget_store.open_epoch(
                        epoch_id=str(approval_payload["epoch_id"]),
                        max_live_cycles=int(bounds["max_live_cycles"]),
                        max_gross_turnover_usdt=float(bounds["max_gross_turnover_usdt"]),
                        max_age_seconds=int(bounds["max_age_seconds"]),
                        now_utc=started,
                        reason="limited unattended epoch controller approval",
                        payload={
                            "source": "unattended_epoch_controller",
                            "slot_id": slot_id,
                            "target_hash": target_hash,
                            "approval_expires_at_utc": approval_payload["approval_expires_at_utc"],
                            "max_timer_fires_authorized": bounds["max_timer_fires"],
                            "turnover_budget": dict(bounds.get("turnover_budget") or {}),
                        },
                    )
                    opened_epoch_id = str(budget_open_result.get("epoch_id") or "")
                    if str(budget_open_result.get("status") or "") != "opened":
                        blockers.extend(str(item) for item in list(budget_open_result.get("blockers") or []))
                    else:
                        owner_approval_record = state_store.record_operator_action(
                            run_id=run_id,
                            action_type="arm-live-delta",
                            reason="limited unattended epoch approval",
                            created_at_utc=_iso(started),
                            payload=approval_payload,
                        )
                        runtime_gate = evaluate_unattended_epoch_runtime_gate(
                            state_store=state_store,
                            payload=payload,
                            now=started,
                            approval_action=owner_approval_record,
                            budget_store=budget_store,
                            require_approval=True,
                            require_budget_epoch=True,
                        )
                        if runtime_gate.get("status") != "passed":
                            blockers.extend(str(item) for item in list(runtime_gate.get("blockers") or []))
                else:
                    owner_approval_record = {
                        "status": "dry_run_not_recorded",
                        "payload": approval_payload,
                    }
                status = "unattended_epoch_armed" if apply_changes and not blockers else "unattended_epoch_dry_run_ready"

    if blockers:
        status = "unattended_epoch_controller_blocked"
        if apply_changes and cleanup_on_failure:
            terminal_cleanup_result = terminal_cleanup(
                state_store=state_store,
                budget_store=budget_store,
                run_id=run_id,
                now=started,
                reason="unattended epoch controller failure",
                blockers=blockers,
                epoch_id=opened_epoch_id,
                timer_name=_timer_name(args=args, controller_cfg=controller_cfg),
                artifact_root=run_root,
                command_runner=command_runner or _run_command,
                notification_sender=notification_sender,
                env=env or os.environ,
            )

    finished = datetime.now(UTC)
    summary = {
        "schema_version": UNATTENDED_EPOCH_CONTROLLER_SUMMARY_VERSION,
        "run_id": run_id,
        "status": status,
        "started_at_utc": _iso(started),
        "finished_at_utc": _iso(finished),
        "artifact_root": str(run_root),
        "config": str(live_config.path),
        "apply": bool(apply_changes),
        "blockers": sorted(set(blockers)),
        "fresh_no_order_proof": proof,
        "budget_open_result": budget_open_result,
        "owner_approval_record": owner_approval_record,
        "runtime_gate": runtime_gate,
        "terminal_cleanup": terminal_cleanup_result,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="unattended_epoch_controller_summary",
        artifact_id=f"{run_id}:summary",
        payload=summary,
    )
    state_store.write_heartbeat(
        run_id=run_id,
        mode="unattended_epoch_controller",
        status=status,
        started_at_utc=str(summary["started_at_utc"]),
        updated_at_utc=str(summary["finished_at_utc"]),
        finished_at_utc=str(summary["finished_at_utc"]),
        artifact_root=str(run_root),
        blockers=list(summary["blockers"]),
    )
    return summary, 0 if status in {
        "unattended_epoch_armed",
        "unattended_epoch_dry_run_ready",
        "unattended_epoch_approval_already_active",
        "hold_until_next_rebalance_slot",
    } else 2


def evaluate_unattended_epoch_runtime_gate(
    *,
    state_store: LiveTradingStateStore,
    payload: dict[str, Any],
    now: datetime,
    approval_action: dict[str, Any] | None = None,
    budget_store: UnattendedBudgetStore | None = None,
    require_approval: bool = True,
    require_budget_epoch: bool = True,
) -> dict[str, Any]:
    current = _coerce_utc(now)
    approval = dict(approval_action or {})
    if not approval:
        approval = dict(state_store.latest_operator_action(action_type="arm-live-delta", status="applied") or {})

    blockers: list[str] = []
    if not approval:
        if require_approval:
            blockers.append("unattended_approval_missing_arm_action")
        return {
            "status": "blocked" if blockers else "not_required",
            "required": bool(require_approval),
            "blockers": blockers,
        }

    if str(approval.get("status") or "applied") != "applied":
        blockers.append("unattended_approval_action_not_applied")

    contract = str(approval.get("contract_version") or approval.get("approval_contract_version") or "").strip()
    if require_approval and contract != UNATTENDED_EPOCH_APPROVAL_CONTRACT:
        blockers.append("unattended_approval_contract_missing_or_mismatch")

    expires_raw = str(approval.get("approval_expires_at_utc") or "").strip()
    expires_at = _parse_utc_optional(expires_raw)
    if expires_at is None:
        blockers.append("unattended_approval_expiry_missing_or_invalid")
    elif current > expires_at:
        blockers.append(f"unattended_approval_expired:{_iso(current)}>{_iso(expires_at)}")

    window = dict(approval.get("timer_window") or approval.get("timer_window_utc") or {})
    earliest_raw = str(
        window.get("timer_enable_earliest_utc")
        or window.get("enable_earliest_utc")
        or window.get("start_at_utc")
        or window.get("start_utc")
        or approval.get("timer_enable_earliest_utc")
        or ""
    ).strip()
    latest_raw = str(
        window.get("timer_enable_latest_utc")
        or window.get("enable_latest_utc")
        or window.get("end_at_utc")
        or window.get("end_utc")
        or approval.get("timer_enable_latest_utc")
        or ""
    ).strip()
    earliest = _parse_utc_optional(earliest_raw)
    latest = _parse_utc_optional(latest_raw)
    if earliest is None or latest is None:
        blockers.append("unattended_timer_window_missing_or_invalid")
    else:
        if latest < earliest:
            blockers.append("unattended_timer_window_inverted")
        if current < earliest:
            blockers.append(f"unattended_timer_window_not_started:{_iso(current)}<{_iso(earliest)}")
        if current > latest:
            blockers.append(f"unattended_timer_window_expired:{_iso(current)}>{_iso(latest)}")

    max_timer_fires = _optional_int(
        approval.get("max_timer_fires")
        or approval.get("max_timer_fires_authorized")
        or window.get("max_timer_fires")
        or window.get("max_timer_fires_authorized")
    )
    if max_timer_fires is None or max_timer_fires <= 0:
        blockers.append("unattended_timer_max_fires_missing_or_invalid")

    slot_id = _approval_text(approval, "slot_id", "rebalance_slot_id")
    target_hash = _approval_text(approval, "target_hash", "rebalance_target_hash")
    slot_record: dict[str, Any] | None = None
    if not slot_id:
        blockers.append("unattended_approval_slot_id_missing")
    else:
        slot_record = state_store.read_rebalance_slot_target(slot_id)
        if slot_record is None:
            blockers.append("unattended_approval_slot_missing")
        else:
            slot_status = str(slot_record.get("status") or "").strip().lower()
            if slot_status == "completed" or str(slot_record.get("completed_at_utc") or "").strip():
                blockers.append("unattended_approval_slot_completed")
            active_hash = str(slot_record.get("target_hash") or "")
            if target_hash and active_hash and target_hash != active_hash:
                blockers.append(
                    "unattended_approval_slot_target_hash_mismatch:"
                    f"expected={target_hash}:actual={active_hash}"
                )
    if not target_hash:
        blockers.append("unattended_approval_target_hash_missing")

    expected_epoch_id = _approval_text(approval, "expected_epoch_id", "budget_epoch_id", "epoch_id")
    current_epoch_id = ""
    current_epoch_payload: dict[str, Any] | None = None
    if require_budget_epoch:
        store = budget_store
        if store is None:
            sqlite_ref = str(dict(payload.get("state") or {}).get("sqlite_path") or "").strip()
            if not sqlite_ref:
                blockers.append("unattended_approval_budget_store_path_missing")
            else:
                store = budget_store_from_payload(payload)
        current_epoch = store.read_current_epoch() if store is not None else None
        if current_epoch is None:
            blockers.append("unattended_approval_requires_open_budget_epoch")
        else:
            current_epoch_id = current_epoch.epoch_id
            epoch_age_seconds = None
            try:
                epoch_age_seconds = max(0.0, (current - _parse_utc_optional(current_epoch.created_at_utc)).total_seconds())
            except (TypeError, AttributeError):
                blockers.append("unattended_approval_epoch_created_at_unparseable")
            if epoch_age_seconds is not None and int(current_epoch.max_age_seconds) > 0:
                if epoch_age_seconds > float(current_epoch.max_age_seconds):
                    blockers.append(
                        "unattended_approval_epoch_stale:"
                        f"{epoch_age_seconds:.0f}>{int(current_epoch.max_age_seconds)}"
                    )
            current_epoch_payload = {
                "epoch_id": current_epoch.epoch_id,
                "max_live_cycles": int(current_epoch.max_live_cycles),
                "consumed_cycles": int(current_epoch.consumed_cycles),
                "max_gross_turnover_usdt": float(current_epoch.max_gross_turnover_usdt),
                "consumed_turnover_usdt": float(current_epoch.consumed_turnover_usdt),
                "max_age_seconds": int(current_epoch.max_age_seconds),
                "age_seconds": epoch_age_seconds,
                "status": str(current_epoch.status),
            }
            if max_timer_fires is not None and max_timer_fires > 0:
                if int(current_epoch.max_live_cycles) > int(max_timer_fires):
                    blockers.append(
                        "unattended_approval_epoch_cycles_exceed_max_timer_fires:"
                        f"{int(current_epoch.max_live_cycles)}>{int(max_timer_fires)}"
                    )
                if int(current_epoch.consumed_cycles) >= int(max_timer_fires):
                    blockers.append(
                        "unattended_approval_timer_fires_exhausted:"
                        f"{int(current_epoch.consumed_cycles)}>={int(max_timer_fires)}"
                    )
        if not expected_epoch_id:
            blockers.append("unattended_approval_expected_epoch_missing")
        elif current_epoch_id and expected_epoch_id != current_epoch_id:
            blockers.append(
                "unattended_approval_epoch_mismatch:"
                f"expected={expected_epoch_id}:actual={current_epoch_id}"
            )

    return {
        "status": "passed" if not blockers else "blocked",
        "required": bool(require_approval),
        "blockers": sorted(set(blockers)),
        "approval_action_id": str(approval.get("action_id") or ""),
        "approval_created_at_utc": str(approval.get("created_at_utc") or ""),
        "approval_expires_at_utc": expires_raw,
        "timer_window": {
            "timer_enable_earliest_utc": earliest_raw,
            "timer_enable_latest_utc": latest_raw,
            "max_timer_fires_authorized": max_timer_fires,
        },
        "slot_id": slot_id,
        "target_hash": target_hash,
        "slot_status": str(dict(slot_record or {}).get("status") or ""),
        "expected_epoch_id": expected_epoch_id,
        "current_open_epoch_id": current_epoch_id,
        "current_open_epoch": current_epoch_payload,
    }


def clone_approval_payload_for_rearm(
    approval_action: dict[str, Any],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        str(key): value
        for key, value in dict(approval_action or {}).items()
        if str(key) not in _RESERVED_OPERATOR_ACTION_FIELDS
    }
    payload["source_owner_approval_action_id"] = str(dict(approval_action or {}).get("action_id") or "")
    payload.update(dict(extra or {}))
    return payload


def build_no_order_proof(summary: dict[str, Any], *, no_order_exit: int) -> dict[str, Any]:
    root_summary = dict(summary or {})
    core_summary = _extract_core_summary(root_summary)
    cycle = _latest_cycle(core_summary)
    plan_root = str(cycle.get("plan_artifact_root") or "")
    delta_root = str(cycle.get("delta_preflight_artifact_root") or "")
    frozen_snapshot = _read_artifact_json(plan_root, FROZEN_TARGET_SNAPSHOT_ARTIFACT) or dict(cycle.get("frozen_target_snapshot") or {})
    frozen_gate = _read_artifact_json(plan_root, "frozen_slot_gate.json") or dict(cycle.get("frozen_slot_gate") or {})
    planned_orders = (
        dict(dict(cycle.get("delta_preflight_artifacts") or {}).get("planned_delta_orders") or {})
        or _read_artifact_json(delta_root, "planned_delta_orders.json")
    )
    rows = [dict(row) for row in list(planned_orders.get("rows") or []) if isinstance(row, dict)]
    row_count = _int(planned_orders.get("row_count") or len(rows) or cycle.get("planned_delta_order_count"))
    blockers: list[str] = []
    orders_submitted = _int(root_summary.get("orders_submitted") or core_summary.get("orders_submitted"))
    fill_count = _int(root_summary.get("fill_count") or core_summary.get("fill_count"))
    if int(no_order_exit) != 0:
        blockers.append(f"fresh_no_order_exit_nonzero:{int(no_order_exit)}")
    if orders_submitted != 0:
        blockers.append(f"fresh_no_order_submitted_orders_nonzero:{orders_submitted}")
    if fill_count != 0:
        blockers.append(f"fresh_no_order_fill_count_nonzero:{fill_count}")
    if bool(root_summary.get("live_delta_authorized")) or bool(core_summary.get("live_delta_authorized")):
        blockers.append("fresh_no_order_live_delta_authorized")
    if bool(root_summary.get("execution_requested")) or bool(core_summary.get("execution_requested")):
        blockers.append("fresh_no_order_execution_requested")
    if row_count > 0 and not rows:
        blockers.append("fresh_no_order_planned_orders_missing")
    projected = projected_turnover_usdt(planned_orders) if planned_orders else None
    delta_preflight = dict(cycle.get("delta_preflight") or {})
    policy_gate = dict(cycle.get("live_delta_policy_gate") or {})
    execution_stage = str(
        delta_preflight.get("execution_stage")
        or policy_gate.get("execution_stage")
        or core_summary.get("execution_stage")
        or ""
    ).strip().lower()
    slot = {
        "slot_id": str(frozen_snapshot.get("slot_id") or frozen_gate.get("slot_id") or ""),
        "target_hash": str(
            frozen_snapshot.get("target_hash")
            or frozen_gate.get("active_target_hash")
            or frozen_gate.get("candidate_target_hash")
            or ""
        ),
        "status": str(frozen_snapshot.get("status") or frozen_gate.get("stored_status") or ""),
        "frozen_slot_gate_status": str(frozen_gate.get("status") or ""),
        "completed_at_utc": str(frozen_snapshot.get("completed_at_utc") or frozen_gate.get("completed_at_utc") or ""),
    }
    if slot["completed_at_utc"]:
        slot["status"] = "completed"
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "no_order_exit_code": int(no_order_exit),
        "run_id": str(root_summary.get("run_id") or core_summary.get("run_id") or ""),
        "artifact_root": str(root_summary.get("artifact_root") or core_summary.get("artifact_root") or ""),
        "core_loop_artifact_root": str(core_summary.get("artifact_root") or ""),
        "plan_artifact_root": plan_root,
        "delta_preflight_artifact_root": delta_root,
        "orders_submitted": orders_submitted,
        "fill_count": fill_count,
        "execution_stage": execution_stage,
        "planned_order_count": int(row_count),
        "planned_orders": {"row_count": int(row_count), "rows": rows},
        "projected_turnover_usdt": projected,
        "slot": slot,
        "frozen_target_snapshot": frozen_snapshot,
        "frozen_slot_gate": frozen_gate,
    }


def build_owner_approval_payload(
    *,
    run_id: str,
    now: datetime,
    proof: dict[str, Any],
    epoch_id: str,
    bounds: dict[str, Any],
    timer_name: str,
) -> dict[str, Any]:
    current = _coerce_utc(now)
    expires = current + timedelta(seconds=int(bounds["approval_ttl_seconds"]))
    window_end = current + timedelta(seconds=int(bounds["timer_window_seconds"]))
    rows = [dict(row) for row in list(dict(proof.get("planned_orders") or {}).get("rows") or [])]
    symbols = sorted({_cell_str(row.get("symbol")).upper() for row in rows if _cell_str(row.get("symbol"))})
    sides = sorted({_cell_str(row.get("side")).upper() for row in rows if _cell_str(row.get("side"))})
    reduce_only_values = sorted(
        {
            bool(row.get("reduce_only"))
            if isinstance(row.get("reduce_only"), bool)
            else str(row.get("reduce_only")).strip().lower() in {"1", "true", "yes", "y", "on"}
            for row in rows
            if "reduce_only" in row
        }
    )
    slot = dict(proof.get("slot") or {})
    payload: dict[str, Any] = {
        "contract_version": UNATTENDED_EPOCH_APPROVAL_CONTRACT,
        "source": "unattended_epoch_controller",
        "controller_run_id": str(run_id),
        "epoch_id": str(epoch_id),
        "expected_epoch_id": str(epoch_id),
        "budget_epoch_id": str(epoch_id),
        "slot_id": str(slot.get("slot_id") or ""),
        "target_hash": str(slot.get("target_hash") or ""),
        "expected_execution_stage": str(proof.get("execution_stage") or ""),
        "expected_symbols": symbols,
        "allowed_symbols": symbols,
        "expected_sides": sides,
        "expected_max_order_count": int(proof.get("planned_order_count") or 0),
        "expected_max_turnover_usdt": float(bounds["max_gross_turnover_usdt"]),
        "turnover_budget": dict(bounds.get("turnover_budget") or {}),
        "approval_created_at_utc": _iso(current),
        "approval_expires_at_utc": _iso(expires),
        "max_timer_fires": int(bounds["max_timer_fires"]),
        "timer_window": {
            "timer_name": str(timer_name or ""),
            "timer_enable_earliest_utc": _iso(current),
            "timer_enable_latest_utc": _iso(window_end),
            "max_timer_fires_authorized": int(bounds["max_timer_fires"]),
        },
        "no_order_canary": {
            "passed": proof.get("status") == "passed",
            "status": str(proof.get("status") or ""),
            "run_id": str(proof.get("run_id") or ""),
            "artifact_root": str(proof.get("artifact_root") or ""),
            "orders_submitted": int(proof.get("orders_submitted") or 0),
            "fill_count": int(proof.get("fill_count") or 0),
        },
    }
    if len(reduce_only_values) == 1:
        payload["expected_reduce_only"] = bool(reduce_only_values[0])
    if bool(bounds.get("fast_follow_entry_second_authorized")):
        payload.update(
            {
                "fast_follow_authorized": False,
                "fast_follow_owner_decision": "pending_fresh_entry_second_no_order_proof",
                "fast_follow_epoch_id": str(epoch_id),
                "fast_follow_max_chain_depth": int(bounds.get("fast_follow_max_chain_depth") or 1),
                "fast_follow_cleanup_required": True,
                "fast_follow_requires_fresh_no_order_proof": True,
            }
        )
    payload["approval_hash"] = _sha256_json(payload)
    return payload


def build_fast_follow_entry_second_owner_payload(
    *,
    run_id: str,
    now: datetime,
    proof: dict[str, Any],
    source_approval: dict[str, Any],
    bounds: dict[str, Any],
    source_supervisor_run_id: str = "",
    source_core_run_id: str = "",
) -> dict[str, Any]:
    current = _coerce_utc(now)
    source = dict(source_approval)
    resolved_bounds = resolve_turnover_budget_from_proof(bounds=dict(bounds), proof=proof)
    blockers = [str(item) for item in list(resolved_bounds.get("blockers") or [])]
    rows = [dict(row) for row in list(dict(proof.get("planned_orders") or {}).get("rows") or [])]
    symbols = sorted({_cell_str(row.get("symbol")).upper() for row in rows if _cell_str(row.get("symbol"))})
    sides = sorted({_cell_str(row.get("side")).upper() for row in rows if _cell_str(row.get("side"))})
    reduce_only_values = sorted(
        {
            bool(row.get("reduce_only"))
            if isinstance(row.get("reduce_only"), bool)
            else str(row.get("reduce_only")).strip().lower() in {"1", "true", "yes", "y", "on"}
            for row in rows
            if "reduce_only" in row
        }
    )
    proof_slot = dict(proof.get("slot") or {})
    source_slot_id = str(source.get("slot_id") or source.get("rebalance_slot_id") or "").strip()
    source_hash = str(source.get("target_hash") or source.get("rebalance_target_hash") or "").strip()
    proof_slot_id = str(proof_slot.get("slot_id") or "").strip()
    proof_hash = str(proof_slot.get("target_hash") or "").strip()
    if str(proof.get("status") or "") != "passed":
        blockers.append(f"fast_follow_entry_second_no_order_proof_not_passed:{proof.get('status') or 'missing'}")
    if int(proof.get("orders_submitted") or 0) != 0 or int(proof.get("fill_count") or 0) != 0:
        blockers.append("fast_follow_entry_second_no_order_proof_submitted_orders")
    if str(proof.get("execution_stage") or "").strip().lower() != "entry_second":
        blockers.append(
            "fast_follow_entry_second_no_order_proof_stage_mismatch:"
            f"{str(proof.get('execution_stage') or 'missing').strip().lower() or 'missing'}"
        )
    if not rows or int(proof.get("planned_order_count") or 0) <= 0:
        blockers.append("fast_follow_entry_second_no_order_proof_missing_planned_orders")
    if source_slot_id and proof_slot_id != source_slot_id:
        blockers.append(f"fast_follow_entry_second_slot_mismatch:{proof_slot_id or 'missing'}!={source_slot_id}")
    if source_hash and proof_hash != source_hash:
        blockers.append(f"fast_follow_entry_second_target_hash_mismatch:{proof_hash or 'missing'}!={source_hash}")
    if str(proof_slot.get("status") or "").strip().lower() == "completed":
        blockers.append("fast_follow_entry_second_slot_already_completed")
    if reduce_only_values != [False]:
        blockers.append("fast_follow_entry_second_requires_non_reduce_only_orders")
    if not symbols:
        blockers.append("fast_follow_entry_second_missing_symbols")
    if not sides:
        blockers.append("fast_follow_entry_second_missing_sides")
    epoch_id = str(source.get("epoch_id") or source.get("budget_epoch_id") or source.get("expected_epoch_id") or "").strip()
    if not epoch_id:
        blockers.append("fast_follow_entry_second_missing_epoch_id")
    max_turnover = _optional_float(resolved_bounds.get("max_gross_turnover_usdt"))
    if max_turnover is None or max_turnover <= 0.0:
        blockers.append("fast_follow_entry_second_expected_turnover_invalid")
    if blockers:
        return {
            "status": "blocked",
            "blockers": sorted(set(blockers)),
            "proof": dict(proof),
            "resolved_bounds": resolved_bounds,
        }

    payload = dict(source)
    payload.pop("action_id", None)
    payload.pop("action_type", None)
    payload.pop("created_at_utc", None)
    payload.pop("reason", None)
    payload.pop("run_id", None)
    payload.pop("status", None)
    payload.pop("approval_hash", None)
    payload.update(
        {
            "contract_version": str(source.get("contract_version") or UNATTENDED_EPOCH_APPROVAL_CONTRACT),
            "source": "unattended_daily_policy_fast_follow_entry_second",
            "fast_follow_controller_run_id": str(run_id),
            "epoch_id": epoch_id,
            "expected_epoch_id": epoch_id,
            "budget_epoch_id": epoch_id,
            "slot_id": proof_slot_id,
            "target_hash": proof_hash,
            "fast_follow_authorized": True,
            "fast_follow_owner_decision": "approve_fast_follow_under_current_budget_epoch",
            "fast_follow_epoch_id": epoch_id,
            "fast_follow_max_chain_depth": int(source.get("fast_follow_max_chain_depth") or bounds.get("fast_follow_max_chain_depth") or 1),
            "fast_follow_cleanup_required": True,
            "fast_follow_requires_fresh_no_order_proof": True,
            "fast_follow_fresh_no_order_proof_recorded_at_utc": _iso(current),
            "fast_follow_source_authorization_action_id": str(source_approval.get("action_id") or ""),
            "fast_follow_source_supervisor_run_id": str(source_supervisor_run_id or ""),
            "fast_follow_source_core_run_id": str(source_core_run_id or ""),
            "fast_follow_expected_execution_stage": "entry_second",
            "fast_follow_expected_symbols": symbols,
            "fast_follow_allowed_symbols": symbols,
            "fast_follow_expected_sides": sides,
            "fast_follow_allowed_sides": sides,
            "fast_follow_expected_reduce_only": False,
            "fast_follow_expected_max_order_count": int(proof.get("planned_order_count") or len(rows)),
            "fast_follow_expected_max_turnover_usdt": float(max_turnover),
            "fast_follow_turnover_budget": dict(resolved_bounds.get("turnover_budget") or {}),
            "fast_follow_no_order_canary": {
                "passed": True,
                "status": str(proof.get("status") or ""),
                "run_id": str(proof.get("run_id") or ""),
                "artifact_root": str(proof.get("artifact_root") or ""),
                "orders_submitted": int(proof.get("orders_submitted") or 0),
                "fill_count": int(proof.get("fill_count") or 0),
                "projected_turnover_usdt": _optional_float(proof.get("projected_turnover_usdt")),
                "slot": proof_slot,
            },
        }
    )
    payload["approval_hash"] = _sha256_json(payload)
    return {
        "status": "ready",
        "blockers": [],
        "payload": payload,
        "proof": dict(proof),
        "resolved_bounds": resolved_bounds,
    }


def _fast_follow_entry_second_intent(proof: dict[str, Any]) -> tuple[list[str], list[str]]:
    snapshot = dict(proof.get("frozen_target_snapshot") or {})
    positions = [dict(item) for item in list(snapshot.get("positions") or []) if isinstance(item, dict)]
    symbols = sorted({_cell_str(item.get("symbol")).upper() for item in positions if _cell_str(item.get("symbol"))})
    sides = sorted(
        {
            "BUY" if _optional_float(item.get("target_position_amt")) > 0.0 else "SELL"
            for item in positions
            if _cell_str(item.get("symbol")) and _optional_float(item.get("target_position_amt")) not in {None, 0.0}
        }
    )
    if symbols:
        return symbols, sides or ["BUY", "SELL"]

    rows = [dict(row) for row in list(dict(proof.get("planned_orders") or {}).get("rows") or [])]
    fallback_symbols = sorted({_cell_str(row.get("symbol")).upper() for row in rows if _cell_str(row.get("symbol"))})
    return fallback_symbols, ["BUY", "SELL"]


def resolve_turnover_budget_from_proof(*, bounds: dict[str, Any], proof: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(bounds)
    blockers = [str(item) for item in list(bounds.get("blockers") or [])]
    projected = _optional_float(proof.get("projected_turnover_usdt"))
    hard_cap = _optional_float(bounds.get("operator_hard_cap_usdt"))
    mode = str(bounds.get("turnover_budget_mode") or "fixed").strip().lower()
    buffer = _optional_float(bounds.get("turnover_buffer"))
    dynamic_modes = {"proof_buffered", "proof_buffered_hard_cap", "dynamic", "dynamic_proof_buffered"}
    if projected is None:
        blockers.append("unattended_epoch_controller_projected_turnover_unknown")
        resolved["blockers"] = sorted(set(blockers))
        return resolved
    if mode in dynamic_modes:
        if buffer is None or buffer < 1.0:
            blockers.append("unattended_epoch_controller_turnover_buffer_invalid")
            resolved_budget = 0.0
            buffered = 0.0
        else:
            buffered = math.ceil(float(projected) * float(buffer) * 100.0) / 100.0
            resolved_budget = float(buffered)
        resolved["max_gross_turnover_usdt"] = float(resolved_budget)
        resolved["turnover_budget"] = {
            "mode": mode,
            "projected_turnover_usdt": float(projected),
            "turnover_buffer": float(buffer or 0.0),
            "buffered_turnover_usdt": float(buffered),
            "operator_hard_cap_usdt": None if hard_cap is None else float(hard_cap),
            "operator_hard_cap_enforced": False,
            "resolved_max_gross_turnover_usdt": float(resolved_budget),
        }
    else:
        if hard_cap is None or hard_cap <= 0.0:
            blockers.append("unattended_epoch_controller_fixed_turnover_budget_required")
            resolved["blockers"] = sorted(set(blockers))
            return resolved
        if float(projected) > float(hard_cap) + 1e-9:
            blockers.append(
                "unattended_epoch_controller_projected_turnover_exceeds_budget:"
                f"{float(projected):.8f}>{float(hard_cap):.8f}"
            )
        resolved["max_gross_turnover_usdt"] = float(hard_cap)
        resolved["turnover_budget"] = {
            "mode": "fixed",
            "projected_turnover_usdt": float(projected),
            "turnover_buffer": 1.0,
            "buffered_turnover_usdt": float(projected),
            "operator_hard_cap_usdt": float(hard_cap),
            "operator_hard_cap_enforced": True,
            "resolved_max_gross_turnover_usdt": float(hard_cap),
        }
    resolved["blockers"] = sorted(set(blockers))
    return resolved


def terminal_cleanup(
    *,
    state_store: LiveTradingStateStore,
    budget_store: UnattendedBudgetStore,
    run_id: str,
    now: datetime,
    reason: str,
    blockers: list[str],
    epoch_id: str = "",
    timer_name: str = "",
    artifact_root: Path | str | None = None,
    command_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
    notification_sender: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    current = _coerce_utc(now)
    command_runner = command_runner or _run_command
    timer_disable: dict[str, Any]
    if timer_name:
        code, stdout, stderr = command_runner(["systemctl", "disable", "--now", str(timer_name)])
        timer_disable = {
            "status": "attempted",
            "timer_name": str(timer_name),
            "exit_code": int(code),
            "stdout": str(stdout),
            "stderr": str(stderr),
        }
    else:
        timer_disable = {"status": "skipped_missing_timer_name", "timer_name": ""}

    target_epoch_id = str(epoch_id or "")
    if not target_epoch_id:
        current_epoch = budget_store.read_current_epoch()
        target_epoch_id = current_epoch.epoch_id if current_epoch is not None else ""
    orphan_audit = budget_store.unreconciled_reservations(epoch_id=target_epoch_id or None)
    close_result = {"status": "skipped_no_epoch_id", "epoch_id": ""}
    if target_epoch_id:
        close_result = budget_store.close_epoch(
            epoch_id=target_epoch_id,
            now_utc=current,
            reason=str(reason or ""),
        )
    disarm_record = state_store.record_operator_action(
        run_id=run_id,
        action_type="disarm-live-delta",
        reason=str(reason or "unattended terminal cleanup"),
        created_at_utc=_iso(current),
        payload={
            "source": "unattended_epoch_controller_terminal_cleanup",
            "blockers": sorted(set(str(item) for item in blockers)),
            "timer_disable": timer_disable,
            "budget_epoch_close": close_result,
            "orphan_reservations_preserved": orphan_audit,
        },
    )
    result = {
        "status": "terminal_cleanup_completed",
        "run_id": str(run_id),
        "reason": str(reason or ""),
        "blockers": sorted(set(str(item) for item in blockers)),
        "cleaned_at_utc": _iso(current),
        "timer_disable": timer_disable,
        "disarm_record": disarm_record,
        "budget_epoch_close": close_result,
        "orphan_reservations_preserved": orphan_audit,
    }
    result["notification"] = _send_cleanup_notification(
        result,
        env=env or os.environ,
        notification_sender=notification_sender,
    )
    if artifact_root is not None:
        root = Path(artifact_root)
        root.mkdir(parents=True, exist_ok=True)
        write_json(root / "terminal_cleanup.json", result)
    return result


def _controller_config(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload.get("unattended_epoch_controller") or {})


def _controller_bounds(*, args: argparse.Namespace, controller_cfg: dict[str, Any]) -> dict[str, Any]:
    cli_turnover_cap = _optional_float(getattr(args, "max_gross_turnover_usdt", None))
    configured_hard_cap = _optional_float(
        controller_cfg.get("operator_hard_cap_usdt", controller_cfg.get("max_gross_turnover_usdt"))
    )
    operator_hard_cap = cli_turnover_cap if cli_turnover_cap is not None else configured_hard_cap
    turnover_budget_mode = str(controller_cfg.get("turnover_budget_mode") or "fixed").strip().lower()
    dynamic_budget = turnover_budget_mode in {
        "proof_buffered",
        "proof_buffered_hard_cap",
        "dynamic",
        "dynamic_proof_buffered",
    }
    turnover_buffer = _optional_float(controller_cfg.get("turnover_buffer", 1.0))
    max_live_cycles = _optional_int(
        getattr(args, "max_live_cycles", None)
        if getattr(args, "max_live_cycles", None) is not None
        else controller_cfg.get("max_live_cycles", 1)
    )
    max_age = _optional_int(
        getattr(args, "max_age_seconds", None)
        if getattr(args, "max_age_seconds", None) is not None
        else controller_cfg.get("max_age_seconds", 900)
    )
    ttl = _optional_int(
        getattr(args, "approval_ttl_seconds", None)
        if getattr(args, "approval_ttl_seconds", None) is not None
        else controller_cfg.get("approval_ttl_seconds", 900)
    )
    window = _optional_int(
        getattr(args, "timer_window_seconds", None)
        if getattr(args, "timer_window_seconds", None) is not None
        else controller_cfg.get("timer_window_seconds", 900)
    )
    max_fires = _optional_int(
        getattr(args, "max_timer_fires", None)
        if getattr(args, "max_timer_fires", None) is not None
        else controller_cfg.get("max_timer_fires", 1)
    )
    fast_follow_authorized = _bool(controller_cfg.get("fast_follow_entry_second_authorized"), default=False)
    fast_follow_depth = _optional_int(controller_cfg.get("fast_follow_max_chain_depth", 1)) or 1
    blockers: list[str] = []
    if not dynamic_budget and (operator_hard_cap is None or operator_hard_cap <= 0.0):
        blockers.append("unattended_epoch_controller_fixed_turnover_budget_required")
    if dynamic_budget:
        if turnover_buffer is None or turnover_buffer < 1.0:
            blockers.append("unattended_epoch_controller_turnover_buffer_invalid")
    if max_live_cycles is None or max_live_cycles <= 0:
        blockers.append("unattended_epoch_controller_max_live_cycles_invalid")
    if max_age is None or max_age <= 0:
        blockers.append("unattended_epoch_controller_max_age_seconds_invalid")
    if ttl is None or ttl <= 0:
        blockers.append("unattended_epoch_controller_approval_ttl_seconds_invalid")
    if window is None or window <= 0:
        blockers.append("unattended_epoch_controller_timer_window_seconds_invalid")
    if max_fires is None or max_fires <= 0:
        blockers.append("unattended_epoch_controller_max_timer_fires_invalid")
    if max_live_cycles is not None and max_fires is not None and max_live_cycles > max_fires:
        blockers.append(f"unattended_epoch_controller_budget_cycles_exceed_timer_fires:{max_live_cycles}>{max_fires}")
    if fast_follow_authorized:
        if max_live_cycles is None or max_live_cycles < 2:
            blockers.append("unattended_epoch_controller_fast_follow_requires_two_budget_cycles")
        if max_fires is None or max_fires < 2:
            blockers.append("unattended_epoch_controller_fast_follow_requires_two_timer_fires")
        if fast_follow_depth <= 0:
            blockers.append("unattended_epoch_controller_fast_follow_depth_invalid")
    return {
        "blockers": blockers,
        "max_gross_turnover_usdt": float(operator_hard_cap or 0.0),
        "operator_hard_cap_usdt": None if operator_hard_cap is None else float(operator_hard_cap),
        "turnover_budget_mode": turnover_budget_mode or "fixed",
        "turnover_buffer": float(turnover_buffer or 0.0),
        "max_live_cycles": int(max_live_cycles or 0),
        "max_age_seconds": int(max_age or 0),
        "approval_ttl_seconds": int(ttl or 0),
        "timer_window_seconds": int(window or 0),
        "max_timer_fires": int(max_fires or 0),
        "fast_follow_entry_second_authorized": bool(fast_follow_authorized),
        "fast_follow_max_chain_depth": int(fast_follow_depth),
    }


def resolve_unattended_epoch_controller_bounds(
    *, args: argparse.Namespace, controller_cfg: dict[str, Any]
) -> dict[str, Any]:
    return _controller_bounds(args=args, controller_cfg=controller_cfg)


def _timer_name(*, args: argparse.Namespace, controller_cfg: dict[str, Any]) -> str:
    return str(
        getattr(args, "systemd_timer_name", "")
        or controller_cfg.get("systemd_timer_name")
        or controller_cfg.get("timer_name")
        or ""
    ).strip()


def _ignore_heartbeat_run_ids(run_id: str, raw_parent_ids: Any) -> str:
    values = [str(run_id)]
    if isinstance(raw_parent_ids, (list, tuple, set)):
        raw_values = [str(item) for item in raw_parent_ids]
    else:
        raw_values = str(raw_parent_ids or "").split(",")
    values.extend(item.strip() for item in raw_values if item.strip())
    return ",".join(dict.fromkeys(values))


def _extract_core_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if str(summary.get("mode") or "") == "core_loop":
        return dict(summary)
    for supervisor_cycle in reversed(list(summary.get("cycles") or [])):
        if not isinstance(supervisor_cycle, dict):
            continue
        nested = dict(supervisor_cycle.get("core_loop_summary") or {})
        if nested:
            return nested
    return dict(summary)


def _latest_cycle(core_summary: dict[str, Any]) -> dict[str, Any]:
    cycles = [dict(item) for item in list(core_summary.get("cycles") or []) if isinstance(item, dict)]
    return cycles[-1] if cycles else {}


def _read_artifact_json(root: str, name: str) -> dict[str, Any]:
    if not str(root or "").strip():
        return {}
    try:
        path = resolve_repo_path(root) / name
        if path.exists():
            return dict(read_json(path))
    except Exception:
        return {}
    return {}


def _send_cleanup_notification(
    cleanup: dict[str, Any],
    *,
    env: Mapping[str, str],
    notification_sender: Callable[[str, dict[str, Any]], dict[str, Any]] | None,
) -> dict[str, Any]:
    text = (
        "Meridian unattended terminal cleanup completed: "
        f"{cleanup.get('run_id')} blockers={','.join(list(cleanup.get('blockers') or []))}"
    )
    if notification_sender is not None:
        try:
            return dict(notification_sender(text, cleanup))
        except Exception as exc:  # pragma: no cover - defensive only.
            return {"status": "failed", "error": f"{type(exc).__name__}:{exc}"}
    token = str(env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(env.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return {"status": "skipped_missing_telegram_env"}
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            timeout=10.0,
        ) as response:
            return {"status": "sent", "http_status": int(response.status)}
    except Exception as exc:  # pragma: no cover - network disabled in tests.
        return {"status": "failed", "error": f"{type(exc).__name__}:{exc}"}


def _run_command(cmd: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    return completed.returncode, completed.stdout, completed.stderr


def _approval_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    return ""


def _parse_utc_optional(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _coerce_utc(parsed)


def _coerce_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


def _optional_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return float(parsed)


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _sha256_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
