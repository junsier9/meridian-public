from __future__ import annotations

import argparse
import json
import os
import time
from argparse import Namespace
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmClient
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.live_position_monitor import run_live_position_monitor
from enhengclaw.live_trading.live_risk_controls import (
    classify_exception_strategy,
    evaluate_margin_cushion_gate,
    removed_daily_realized_pnl_gate,
)
from enhengclaw.live_trading.mainnet_rebalance_plan_runner import run_mainnet_current_position_rebalance_plan
from enhengclaw.quant_research.contracts import read_json, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Unattended mainnet scheduler scaffold. Default mode is reconcile-only plus plan-only; "
            "it never submits live delta orders."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_unattended_plan_only.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--reference-run", default="")
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument("--allow-live-delta", action="store_true")
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_unattended_scheduler(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_unattended_scheduler(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    monitor_runner: Callable[..., tuple[dict[str, Any], int]] = run_live_position_monitor,
    plan_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_current_position_rebalance_plan,
    account_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_unattended_plan_only.yaml"))
    payload = live_config.payload
    scheduler_cfg = dict(payload.get("unattended_scheduler") or {})
    cycles = int(getattr(args, "cycles", None) or scheduler_cfg.get("max_cycles_per_invocation", 1) or 1)
    interval_seconds = float(
        getattr(args, "interval_seconds", None)
        if getattr(args, "interval_seconds", None) is not None
        else scheduler_cfg.get("interval_seconds", 0.0) or 0.0
    )
    cycles = max(1, cycles)
    interval_seconds = max(0.0, interval_seconds)
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-unattended-scheduler"
    run_root = live_config.artifact_root.parent / "mainnet_unattended_scheduler" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = _config_blockers(payload, allow_live_delta=bool(getattr(args, "allow_live_delta", False)))
    credentials = _credential_context(payload=payload, env=env or os.environ)
    blockers.extend(credentials["blockers"])
    cycle_rows: list[dict[str, Any]] = []
    for cycle_index in range(1, cycles + 1):
        cycle = _run_cycle(
            args=args,
            payload=payload,
            cycle_index=cycle_index,
            env=env or os.environ,
            credentials=credentials,
            monitor_runner=monitor_runner,
            plan_runner=plan_runner,
            account_client_factory=account_client_factory,
            now=started if cycle_index == 1 else datetime.now(UTC),
            blocked_before_cycle=bool(blockers),
        )
        cycle_rows.append(cycle)
        blockers.extend(str(item) for item in list(cycle.get("blockers") or []))
        write_json(run_root / f"cycle_{cycle_index:03d}.json", cycle)
        if blockers:
            break
        if cycle_index < cycles and interval_seconds > 0.0:
            sleep_fn(interval_seconds)
    clean_cycles = int(sum(str(row.get("status") or "") == "cycle_passed_plan_only" for row in cycle_rows))
    min_clean = int(scheduler_cfg.get("min_clean_cycles_before_live_delta", 3) or 3)
    if bool(getattr(args, "allow_live_delta", False)) and clean_cycles < min_clean:
        blockers.append(f"insufficient_clean_cycles_for_live_delta:{clean_cycles}<{min_clean}")
    summary = {
        "run_id": run_id,
        "status": "mainnet_unattended_observation_completed" if not blockers and len(cycle_rows) == cycles else "mainnet_unattended_observation_blocked",
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(run_root),
        "config": str(live_config.path),
        "configured_cycle_count": int(cycles),
        "completed_cycle_count": int(len(cycle_rows)),
        "clean_cycle_count": int(clean_cycles),
        "min_clean_cycles_before_live_delta": int(min_clean),
        "interval_seconds": float(interval_seconds),
        "mode": "reconcile_only_plus_plan_only",
        "orders_submitted": 0,
        "orders_canceled": 0,
        "live_delta_authorized": False,
        "recurring_mainnet_enabled": False,
        "cycles": cycle_rows,
    }
    write_json(run_root / "run_summary.json", summary)
    return summary, 0 if summary["status"] == "mainnet_unattended_observation_completed" else 2


def _run_cycle(
    *,
    args: argparse.Namespace,
    payload: dict[str, Any],
    cycle_index: int,
    env: Mapping[str, str],
    credentials: dict[str, Any],
    monitor_runner: Callable[..., tuple[dict[str, Any], int]],
    plan_runner: Callable[..., tuple[dict[str, Any], int]],
    account_client_factory: Callable[..., Any],
    now: datetime,
    blocked_before_cycle: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    cycle: dict[str, Any] = {
        "cycle_index": int(cycle_index),
        "status": "not_run",
        "blockers": blockers,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "live_delta_authorized": False,
    }
    if blocked_before_cycle:
        cycle["status"] = "cycle_skipped_prior_blocker"
        cycle["blockers"] = ["prior_scheduler_blocker"]
        return cycle
    monitor_summary, monitor_exit = monitor_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            reference_run=str(getattr(args, "reference_run", "") or ""),
            api_key_env="",
            api_secret_env="",
            max_abs_position_drift_qty=float(getattr(args, "max_abs_position_drift_qty", 1e-9) or 1e-9),
        ),
        env=env,
    )
    cycle["monitor_status"] = str(monitor_summary.get("status") or "")
    cycle["monitor_exit_code"] = int(monitor_exit)
    cycle["monitor_artifact_root"] = str(monitor_summary.get("artifact_root") or "")
    cycle["monitor_blockers"] = list(monitor_summary.get("blockers") or [])
    if monitor_exit != 0:
        blockers.append(f"monitor_failed:{monitor_summary.get('status')}")
        blockers.extend(str(item) for item in list(monitor_summary.get("blockers") or []))
    monitor_report = _read_optional_json(str(monitor_summary.get("artifact_root") or ""), "monitor_report.json")
    account_summary = dict(monitor_report.get("account") or {})
    if not account_summary:
        account_summary = {
            "available_balance_usdt": monitor_summary.get("available_balance_usdt", 0.0),
            "total_wallet_balance_usdt": monitor_summary.get("total_wallet_balance_usdt", 0.0),
        }
    daily_gate = removed_daily_realized_pnl_gate(config=payload)
    margin_gate = evaluate_margin_cushion_gate(
        account_summary,
        config=payload,
        planned_additional_initial_margin_usdt=0.0,
        require_configured=True,
    )
    cycle["daily_realized_pnl_gate"] = daily_gate
    cycle["margin_cushion_gate"] = margin_gate
    blockers.extend(str(item) for item in list(margin_gate.get("blockers") or []))
    if not blockers:
        plan_summary, plan_exit = plan_runner(
            Namespace(
                config=str(getattr(args, "config", "")),
                as_of=str(getattr(args, "as_of", "now") or "now"),
                fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
                symbols=str(getattr(args, "symbols", "") or ""),
                public_market_data=bool(getattr(args, "public_market_data", False)),
                api_key_env="",
                api_secret_env="",
            ),
            env=env,
        )
        cycle["plan_status"] = str(plan_summary.get("status") or "")
        cycle["plan_exit_code"] = int(plan_exit)
        cycle["plan_artifact_root"] = str(plan_summary.get("artifact_root") or "")
        cycle["planned_delta_order_count"] = int(plan_summary.get("planned_delta_order_count") or 0)
        if plan_exit != 0:
            blockers.append(f"plan_only_rebalance_failed:{plan_summary.get('status')}")
            blockers.extend(str(item) for item in list(plan_summary.get("blockers") or []))
    else:
        cycle["plan_status"] = "skipped_due_to_gate_blocker"
        cycle["plan_exit_code"] = 0
        cycle["planned_delta_order_count"] = 0
    exception_policy = classify_exception_strategy(blockers, context={"cycle_index": cycle_index})
    cycle["exception_policy"] = exception_policy
    cycle["blockers"] = sorted(set(blockers))
    cycle["status"] = "cycle_passed_plan_only" if not blockers else "cycle_blocked"
    return cycle


def _config_blockers(payload: dict[str, Any], *, allow_live_delta: bool) -> list[str]:
    blockers: list[str] = []
    risk = dict(payload.get("risk") or {})
    scheduler = dict(payload.get("unattended_scheduler") or {})
    if bool(risk.get("trading_enabled", False)):
        blockers.append("unattended_scheduler_requires_config_trading_enabled_false")
    if bool(scheduler.get("live_delta_enabled", False)):
        blockers.append("unattended_scheduler_live_delta_enabled_in_config")
    if allow_live_delta:
        blockers.append("unattended_scheduler_live_delta_not_implemented")
    return blockers


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


if __name__ == "__main__":
    raise SystemExit(main())
