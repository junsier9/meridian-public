from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.mainnet_delta_execution_runner import run_mainnet_delta_execution
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import (
    MULTIPHASE_TARGET_ENGINE,
    run_mainnet_multiphase_current_position_rebalance_plan,
    write_json,
)
from enhengclaw.live_trading.state_store import LiveTradingStateStore


EXECUTABLE_STAGES = {"reduce_first", "entry_second"}
NOOP_STATUSES = {
    "mainnet_current_position_rebalance_noop",
    "mainnet_current_position_rebalance_dust_noop",
    "mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a staged, no-order migration/follow-up plan for moving hv_balanced mainnet "
            "execution from the current live positions into the 10-phase equal-sleeve target. "
            "This runner never submits Binance orders; live execution still goes through the "
            "explicit mainnet delta execution runner."
        )
    )
    parser.add_argument(
        "--config",
        default="config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_noorder_candidate.yaml",
    )
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--api-secret-env", default="")
    parser.add_argument(
        "--stage",
        default="auto",
        choices=["auto", "reduce_first", "entry_second"],
        help="Expected active execution stage. auto accepts whichever single stage the fresh plan emits.",
    )
    parser.add_argument(
        "--previous-stage-artifact",
        default="",
        help="Optional prior delta execution artifact root used only for audit linkage.",
    )
    parser.add_argument(
        "--ignore-heartbeat-run-id",
        default="",
        help="Comma-separated heartbeat run ids to ignore during the downstream delta dry-run preflight.",
    )
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_multiphase_migration(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_multiphase_migration(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    target_plan_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_multiphase_current_position_rebalance_plan,
    delta_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_delta_execution,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    """Coordinate a no-order staged migration plan.

    The runner builds a fresh multiphase current-position-aware target plan, validates the
    active stage, then delegates to the existing delta runner in dry-run mode. It deliberately
    does not expose a new live-order code path.
    """

    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(str(getattr(args, "config", "")))
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-multiphase-migration"
    run_root = live_config.artifact_root.parent / "mainnet_multiphase_migration" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    target_args = _target_plan_args(args)
    target_summary, target_exit_code = target_plan_runner(target_args, env=env or os.environ, now_fn=now_fn)
    write_json(run_root / "target_plan_summary.json", target_summary)

    target_artifact_root = str(target_summary.get("artifact_root") or "")
    active_stage = str(target_summary.get("active_execution_phase") or "").strip().lower()
    expected_stage = str(getattr(args, "stage", "auto") or "auto").strip().lower()
    blockers: list[str] = []

    if target_exit_code != 0:
        blockers.append(f"target_plan_exit_code:{target_exit_code}")
    for blocker in list(target_summary.get("blockers") or []):
        blockers.append(str(blocker))
    if not target_artifact_root:
        blockers.append("target_plan_artifact_root_missing")
    if expected_stage != "auto" and active_stage != expected_stage:
        blockers.append(f"stage_mismatch:expected={expected_stage}:actual={active_stage or 'missing'}")

    delta_summary: dict[str, Any] = {"status": "not_run", "blockers": []}
    delta_exit_code = 0
    if not blockers and str(target_summary.get("status") or "") not in NOOP_STATUSES:
        if active_stage not in EXECUTABLE_STAGES:
            blockers.append(f"active_stage_not_executable:{active_stage or 'missing'}")
        else:
            delta_args = _delta_dry_run_args(args, plan_root=target_artifact_root)
            delta_summary, delta_exit_code = delta_runner(delta_args, env=env or os.environ, now_fn=now_fn)
            write_json(run_root / "delta_dry_run_summary.json", delta_summary)
            if delta_exit_code != 0:
                blockers.append(f"delta_dry_run_exit_code:{delta_exit_code}")
            for blocker in list(delta_summary.get("blockers") or []):
                blockers.append(str(blocker))
    elif not blockers:
        write_json(run_root / "delta_dry_run_summary.json", delta_summary)
    else:
        write_json(run_root / "delta_dry_run_summary.json", delta_summary)

    operator_next_steps = _operator_next_steps(
        args=args,
        target_summary=target_summary,
        delta_summary=delta_summary,
        active_stage=active_stage,
        blocked=bool(blockers),
    )
    write_json(run_root / "operator_next_steps.json", operator_next_steps)

    status = _status_for(
        blockers=blockers,
        target_summary=target_summary,
        delta_summary=delta_summary,
        active_stage=active_stage,
    )
    summary = {
        "run_id": run_id,
        "mode": "no_order_multiphase_migration",
        "environment": "mainnet",
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "artifact_root": str(run_root),
        "config": str(getattr(args, "config", "")),
        "expected_stage": expected_stage,
        "active_execution_phase": active_stage,
        "previous_stage_artifact": str(getattr(args, "previous_stage_artifact", "") or ""),
        "target_plan_artifact_root": target_artifact_root,
        "target_plan_status": target_summary.get("status"),
        "target_plan_exit_code": int(target_exit_code),
        "target_plan_order_count": int(target_summary.get("planned_delta_order_count", target_summary.get("planned_order_count", 0)) or 0),
        "target_plan_phase_counts": dict(target_summary.get("phase_counts") or {}),
        "target_plan_deferred_phase_counts": dict(target_summary.get("deferred_phase_counts") or {}),
        "delta_dry_run_artifact_root": delta_summary.get("artifact_root"),
        "delta_dry_run_status": delta_summary.get("status"),
        "delta_dry_run_exit_code": int(delta_exit_code),
        "required_confirmation": delta_summary.get("required_confirmation", ""),
        "orders_submitted": 0,
        "fill_count": 0,
        "mainnet_order_submission_authorized": False,
        "runner_never_submits_orders": True,
        "operator_next_steps": operator_next_steps,
    }
    write_json(run_root / "run_summary.json", summary)

    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="mainnet_multiphase_migration",
        artifact_id=f"{run_id}:migration",
        payload=summary,
    )
    return summary, 0 if not blockers else 2


def _target_plan_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        config=str(getattr(args, "config", "")),
        as_of=str(getattr(args, "as_of", "now") or "now"),
        fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
        symbols=str(getattr(args, "symbols", "") or ""),
        public_market_data=bool(getattr(args, "public_market_data", False)),
        api_key_env=str(getattr(args, "api_key_env", "") or ""),
        api_secret_env=str(getattr(args, "api_secret_env", "") or ""),
        target_plan=True,
        execute_live_delta=False,
        capital_topup=False,
    )


def _delta_dry_run_args(args: argparse.Namespace, *, plan_root: str) -> argparse.Namespace:
    return argparse.Namespace(
        config=str(getattr(args, "config", "")),
        plan_artifact=str(plan_root),
        execute_mainnet_delta_orders=False,
        operator_enable_mainnet_delta_for_this_run=False,
        i_understand_this_places_real_mainnet_delta_orders=False,
        i_understand_daily_loss_budget_is_review_only=False,
        i_understand_daily_realized_pnl_gate_is_active=False,
        confirm_mainnet_delta_execution="",
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
        ignore_heartbeat_run_id=str(getattr(args, "ignore_heartbeat_run_id", "") or ""),
    )


def _operator_next_steps(
    *,
    args: argparse.Namespace,
    target_summary: dict[str, Any],
    delta_summary: dict[str, Any],
    active_stage: str,
    blocked: bool,
) -> dict[str, Any]:
    target_status = str(target_summary.get("status") or "")
    if blocked:
        return {
            "status": "blocked",
            "action": "do_not_submit_orders",
            "reason": "migration_or_delta_dry_run_blocked",
        }
    if target_status in NOOP_STATUSES:
        return {
            "status": "noop",
            "action": "hold_and_monitor",
            "reason": target_status,
        }
    required_confirmation = str(delta_summary.get("required_confirmation") or "")
    plan_artifact = str(target_summary.get("artifact_root") or "")
    command = _live_delta_command(
        config=str(getattr(args, "config", "")),
        plan_artifact=plan_artifact,
        confirmation=required_confirmation,
    )
    next_follow_up_stage = "entry_second" if active_stage == "reduce_first" else "auto"
    follow_up_command = [
        "python",
        "scripts/live_trading/run_hv_balanced_mainnet_multiphase_migration.py",
        "--config",
        str(getattr(args, "config", "")),
        "--stage",
        next_follow_up_stage,
        "--previous-stage-artifact",
        "<delta_execution_artifact_root>",
    ]
    return {
        "status": "ready",
        "action": "operator_may_run_existing_delta_runner_after_review",
        "active_execution_phase": active_stage,
        "required_confirmation": required_confirmation,
        "live_delta_command_requires_manual_execution": True,
        "live_delta_command": command,
        "after_successful_execution_run_follow_up_command": follow_up_command,
        "notes": [
            "This migration runner did not submit orders.",
            "Execute only one stage, then reconcile, then rerun this migration runner for the next stage.",
        ],
    }


def _live_delta_command(
    *,
    config: str,
    plan_artifact: str,
    confirmation: str,
) -> list[str]:
    command = [
        "python",
        "scripts/live_trading/run_hv_balanced_mainnet_delta_execution.py",
        "--config",
        config,
        "--plan-artifact",
        plan_artifact,
        "--execute-mainnet-delta-orders",
        "--operator-enable-mainnet-delta-for-this-run",
        "--i-understand-this-places-real-mainnet-delta-orders",
    ]
    command.extend(["--confirm-mainnet-delta-execution", confirmation])
    return command


def _status_for(
    *,
    blockers: list[str],
    target_summary: dict[str, Any],
    delta_summary: dict[str, Any],
    active_stage: str,
) -> str:
    if blockers:
        return "mainnet_multiphase_migration_blocked"
    target_status = str(target_summary.get("status") or "")
    if target_status in NOOP_STATUSES:
        return "mainnet_multiphase_migration_noop"
    delta_status = str(delta_summary.get("status") or "")
    if active_stage in EXECUTABLE_STAGES and delta_status == "mainnet_delta_execution_ready":
        return "mainnet_multiphase_migration_stage_ready"
    if delta_status == "mainnet_delta_execution_noop":
        return "mainnet_multiphase_migration_noop"
    return "mainnet_multiphase_migration_observed"


if __name__ == "__main__":
    raise SystemExit(main())
