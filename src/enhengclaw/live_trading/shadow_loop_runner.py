from __future__ import annotations

import argparse
import json
import time
from argparse import Namespace
from datetime import UTC, datetime
from typing import Any

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.paper_runner import run_paper_controlled_from_args
from enhengclaw.live_trading.provider_sidecar_shadow import run_provider_sidecar_shadow
from enhengclaw.live_trading.testnet_strategy_runner import run_testnet_strategy_auto_order
from enhengclaw.quant_research.contracts import write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean short-cycle shadow loop: paper-only plus testnet dry-run, no exchange orders."
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_shadow_loop.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public data.")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument(
        "--run-provider-sidecar-shadow",
        action="store_true",
        help="After each hv_balanced paper target is generated, record CoinGlass provider sidecar evidence only.",
    )
    parser.add_argument(
        "--inject-failure-cycle",
        type=int,
        default=0,
        help="Testing gate only: fail the selected cycle at --inject-failure-stage.",
    )
    parser.add_argument(
        "--inject-failure-stage",
        choices=["", "before_paper", "after_paper", "before_testnet", "after_testnet"],
        default="",
        help="Testing gate only: deterministic shadow-loop failure injection point.",
    )
    parser.add_argument(
        "--inject-failure-message",
        default="injected_shadow_loop_failure",
        help="Testing gate only: message written into injected-failure artifacts.",
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_shadow_loop(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_shadow_loop(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_shadow_loop.yaml"))
    payload = live_config.payload
    loop_config = dict(payload.get("shadow_loop") or {})
    cycles = int(getattr(args, "cycles", None) or loop_config.get("max_cycles_per_invocation", 1) or 1)
    interval_seconds = float(
        getattr(args, "interval_seconds", None)
        if getattr(args, "interval_seconds", None) is not None
        else loop_config.get("interval_seconds", 0.0) or 0.0
    )
    run_paper = bool(loop_config.get("run_paper", True))
    run_testnet_dry_run = bool(loop_config.get("run_testnet_dry_run", True))
    require_testnet_zero = bool(loop_config.get("require_testnet_submitted_order_count_zero", True))
    provider_sidecar_config = dict(payload.get("provider_sidecar_shadow") or {})
    run_provider_sidecar = bool(
        provider_sidecar_config.get("enabled", False) or bool(getattr(args, "run_provider_sidecar_shadow", False))
    )
    cycles = max(1, cycles)
    interval_seconds = max(0.0, interval_seconds)
    started = datetime.now(UTC)
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-shadow-loop"
    loop_root = live_config.artifact_root.parent / "shadow_loop" / run_id
    loop_root.mkdir(parents=True, exist_ok=True)
    cycle_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for cycle_index in range(1, cycles + 1):
        cycle_started = datetime.now(UTC)
        cycle = _run_cycle(
            args=args,
            cycle_index=cycle_index,
            run_paper=run_paper,
            run_testnet_dry_run=run_testnet_dry_run,
            require_testnet_zero=require_testnet_zero,
            run_provider_sidecar=run_provider_sidecar,
        )
        cycle["cycle_index"] = int(cycle_index)
        cycle["started_at_utc"] = cycle_started.isoformat().replace("+00:00", "Z")
        cycle["finished_at_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        cycle_rows.append(cycle)
        blockers.extend(str(item) for item in cycle.get("blockers", []))
        write_json(loop_root / f"cycle_{cycle_index:03d}.json", cycle)
        if blockers:
            break
        if cycle_index < cycles and interval_seconds > 0.0:
            time.sleep(interval_seconds)
    summary = {
        "run_id": run_id,
        "status": "shadow_loop_completed" if not blockers and len(cycle_rows) == cycles else "shadow_loop_blocked",
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(loop_root),
        "config": str(live_config.path),
        "sqlite_path": str(live_config.sqlite_path),
        "configured_cycle_count": int(cycles),
        "completed_cycle_count": int(len(cycle_rows)),
        "interval_seconds": float(interval_seconds),
        "paper_only": bool(run_paper),
        "testnet_dry_run_only": bool(run_testnet_dry_run),
        "exchange_order_submission": "disabled",
        "provider_sidecar_shadow_enabled": bool(run_provider_sidecar),
        "provider_sidecar_ready_cycle_count": int(
            sum(row.get("provider_sidecar_status") == "provider_sidecar_shadow_ready" for row in cycle_rows)
        ),
        "testnet_submitted_order_count_total": int(
            sum(int(row.get("testnet_submitted_order_count") or 0) for row in cycle_rows)
        ),
        "paper_executed_cycle_count": int(sum(row.get("paper_status") == "paper_executed" for row in cycle_rows)),
        "paper_duplicate_skipped_cycle_count": int(
            sum(row.get("paper_effective_status") == "paper_duplicate_skipped_no_new_fill" for row in cycle_rows)
        ),
        "cycles": cycle_rows,
    }
    write_json(loop_root / "shadow_loop_summary.json", summary)
    write_json(loop_root / "run_summary.json", summary)
    return summary, 0 if summary["status"] == "shadow_loop_completed" else 2


def _run_cycle(
    *,
    args: argparse.Namespace,
    cycle_index: int,
    run_paper: bool,
    run_testnet_dry_run: bool,
    require_testnet_zero: bool,
    run_provider_sidecar: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    cycle: dict[str, Any] = {
        "cycle_index": int(cycle_index),
        "blockers": blockers,
        "paper_status": "not_run",
        "paper_effective_status": "not_run",
        "testnet_status": "not_run",
        "testnet_submitted_order_count": 0,
        "testnet_fill_count": 0,
        "provider_sidecar_status": "not_run",
    }
    if run_paper:
        try:
            _maybe_inject_failure(args, cycle_index, "before_paper")
            paper_summary, paper_exit_code = run_paper_controlled_from_args(
                Namespace(
                    config=str(getattr(args, "config", "")),
                    as_of=str(getattr(args, "as_of", "now") or "now"),
                    fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
                    symbols=str(getattr(args, "symbols", "") or ""),
                    public_market_data=bool(getattr(args, "public_market_data", False)),
                )
            )
            cycle["paper_status"] = str(paper_summary.get("status") or "")
            cycle["paper_exit_code"] = int(paper_exit_code)
            cycle["paper_artifact_root"] = str(paper_summary.get("artifact_root") or "")
            cycle["paper_blockers"] = list(paper_summary.get("blockers") or [])
            if paper_exit_code == 0 and paper_summary.get("status") == "paper_executed":
                cycle["paper_effective_status"] = "paper_executed"
            elif _is_duplicate_paper_block(paper_summary):
                cycle["paper_effective_status"] = "paper_duplicate_skipped_no_new_fill"
            else:
                blockers.append(f"paper_shadow_cycle_failed:{cycle_index}:{paper_summary.get('status')}")
            if run_provider_sidecar and not blockers and str(cycle.get("paper_artifact_root") or "").strip():
                sidecar_summary, sidecar_exit_code = run_provider_sidecar_shadow(
                    Namespace(
                        config=str(getattr(args, "config", "")),
                        decision_artifact_root=str(cycle.get("paper_artifact_root") or ""),
                        symbols=str(getattr(args, "symbols", "") or ""),
                        as_of=str(getattr(args, "as_of", "now") or "now"),
                        output_root="",
                    )
                )
                cycle["provider_sidecar_status"] = str(sidecar_summary.get("status") or "")
                cycle["provider_sidecar_exit_code"] = int(sidecar_exit_code)
                cycle["provider_sidecar_artifact_root"] = str(sidecar_summary.get("artifact_root") or "")
                cycle["provider_sidecar_blockers"] = list(sidecar_summary.get("blockers") or [])
                if sidecar_exit_code != 0:
                    blockers.append(f"provider_sidecar_shadow_cycle_failed:{cycle_index}:{sidecar_summary.get('status')}")
            _maybe_inject_failure(args, cycle_index, "after_paper")
        except Exception as exc:  # noqa: BLE001 - gate runner must fail closed on any cycle exception.
            cycle["paper_status"] = "exception"
            cycle["paper_effective_status"] = "exception"
            cycle["paper_exit_code"] = 99
            _record_cycle_exception(cycle, blockers, "paper", cycle_index, exc)
    if run_testnet_dry_run and not blockers:
        try:
            _maybe_inject_failure(args, cycle_index, "before_testnet")
            testnet_summary, testnet_exit_code = run_testnet_strategy_auto_order(
                Namespace(
                    config=str(getattr(args, "config", "")),
                    as_of=str(getattr(args, "as_of", "now") or "now"),
                    fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
                    symbols=str(getattr(args, "symbols", "") or ""),
                    public_market_data=bool(getattr(args, "public_market_data", False)),
                    execute_testnet_strategy_orders=False,
                    i_understand_this_uses_binance_usdm_testnet=False,
                    confirm_testnet_risk="",
                )
            )
            submitted_count = int(testnet_summary.get("submitted_order_count") or 0)
            fill_count = int(testnet_summary.get("fill_count") or 0)
            cycle["testnet_status"] = str(testnet_summary.get("status") or "")
            cycle["testnet_exit_code"] = int(testnet_exit_code)
            cycle["testnet_artifact_root"] = str(testnet_summary.get("artifact_root") or "")
            cycle["testnet_blockers"] = list(testnet_summary.get("blockers") or [])
            cycle["testnet_submitted_order_count"] = submitted_count
            cycle["testnet_fill_count"] = fill_count
            if testnet_exit_code != 0 or testnet_summary.get("status") != "testnet_strategy_plan_ready":
                blockers.append(f"testnet_dry_run_cycle_failed:{cycle_index}:{testnet_summary.get('status')}")
            if require_testnet_zero and submitted_count != 0:
                blockers.append(f"testnet_dry_run_submitted_orders:{cycle_index}:{submitted_count}")
            if fill_count != 0:
                blockers.append(f"testnet_dry_run_fills:{cycle_index}:{fill_count}")
            _maybe_inject_failure(args, cycle_index, "after_testnet")
        except Exception as exc:  # noqa: BLE001 - dry-run leakage checks must still be written.
            if cycle["testnet_status"] == "not_run":
                cycle["testnet_status"] = "exception"
            cycle["testnet_exit_code"] = 99
            _record_cycle_exception(cycle, blockers, "testnet", cycle_index, exc)
    elif run_testnet_dry_run and blockers:
        cycle["testnet_status"] = "skipped_due_to_prior_blocker"
    cycle["blockers"] = sorted(set(blockers))
    return cycle


def _is_duplicate_paper_block(summary: dict[str, Any]) -> bool:
    if str(summary.get("status") or "") != "blocked":
        return False
    blockers = [str(item) for item in list(summary.get("blockers") or [])]
    has_duplicate = any(item.startswith("duplicate_paper_plan_already_executed:") for item in blockers)
    tolerated_residual_prefixes = (
        "duplicate_paper_plan_already_executed:",
        "quantity_below_min:",
        "notional_below_min:",
    )
    return has_duplicate and all(item.startswith(tolerated_residual_prefixes) for item in blockers)


class InjectedShadowLoopFailure(RuntimeError):
    pass


def _maybe_inject_failure(args: argparse.Namespace, cycle_index: int, stage: str) -> None:
    inject_cycle = int(getattr(args, "inject_failure_cycle", 0) or 0)
    inject_stage = str(getattr(args, "inject_failure_stage", "") or "")
    if inject_cycle == int(cycle_index) and inject_stage == stage:
        message = str(getattr(args, "inject_failure_message", "") or "injected_shadow_loop_failure")
        raise InjectedShadowLoopFailure(f"{stage}:{message}")


def _record_cycle_exception(
    cycle: dict[str, Any],
    blockers: list[str],
    stage: str,
    cycle_index: int,
    exc: Exception,
) -> None:
    exception_type = type(exc).__name__
    exception_message = str(exc)
    cycle[f"{stage}_exception_type"] = exception_type
    cycle[f"{stage}_exception_message"] = exception_message
    blockers.append(f"{stage}_shadow_cycle_exception:{cycle_index}:{exception_type}")


if __name__ == "__main__":
    raise SystemExit(main())
